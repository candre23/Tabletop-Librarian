from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from threading import Event, Lock, Thread
from time import sleep, time
from typing import Any

import fitz

from app.config import OCR_DATA_DIR

logger = logging.getLogger(__name__)

OCR_PDF_DIR = OCR_DATA_DIR / "pdf"
OCR_META_DIR = OCR_DATA_DIR / "meta"
OCR_METADATA_VERSION = 1

_state_lock = Lock()
_cancel_event = Event()
_process_lock = Lock()
_active_process: subprocess.Popen[str] | None = None
_job_state: dict[str, Any] = {
    "running": False,
    "stage": "idle",
    "message": "Ready",
    "current": 0,
    "total": 0,
    "percent": 0.0,
    "current_file": "",
    "current_page": 0,
    "total_pages": 0,
    "completed": 0,
    "failed": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "cancelled": False,
}

_PERCENT_RE = re.compile(r"(?<!\d)(100|[1-9]?\d)\s*%")
_PAGE_RE = re.compile(r"(?:page|pages?)\s+(\d+)\s*(?:of|/)\s*(\d+)", re.IGNORECASE)


def _set_state(**updates: Any) -> None:
    with _state_lock:
        _job_state.update(updates)


def ocr_job_status() -> dict[str, Any]:
    with _state_lock:
        return dict(_job_state)


def ocr_executable() -> str | None:
    return shutil.which("ocrmypdf")


def tesseract_executable() -> str | None:
    return shutil.which("tesseract")


def ocr_available() -> bool:
    return bool(ocr_executable() and tesseract_executable())


def _source_key(path: Path) -> str:
    raw = str(path.resolve()).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:24]


def _source_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _pdf_path(path: Path) -> Path:
    return OCR_PDF_DIR / f"{_source_key(path)}.pdf"


def _meta_path(path: Path) -> Path:
    return OCR_META_DIR / f"{_source_key(path)}.json"


def _load_metadata(path: Path) -> dict[str, Any] | None:
    meta = _meta_path(path)
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("metadata_version") != OCR_METADATA_VERSION:
        return None
    return data


def current_ocr_pdf(path: Path) -> Path | None:
    """Return the persistent local OCR derivative when it matches the source."""
    try:
        source = path.resolve(strict=True)
        signature = _source_signature(source)
    except OSError:
        return None

    data = _load_metadata(source)
    if not data or data.get("status") != "complete":
        return None
    if data.get("source_path") != str(source) or data.get("source") != signature:
        return None

    output = Path(str(data.get("ocr_path") or ""))
    if output != _pdf_path(source) or not output.exists():
        return None
    return output


def _page_count(path: Path) -> int:
    try:
        document = fitz.open(path)
        try:
            return int(document.page_count)
        finally:
            document.close()
    except Exception:
        return 0


def _library_pdf_documents() -> list[dict[str, Any]]:
    # Delayed import avoids a module cycle through library.manager -> pdf_status.
    from app.library.manager import list_folders, scan_folder

    by_path: dict[str, dict[str, Any]] = {}
    for folder in list_folders():
        scan = scan_folder(folder, generate_covers=False)
        for document in scan.get("documents", []):
            if document.get("type") != "PDF":
                continue
            by_path[str(document["path"])] = document
    return list(by_path.values())


def ocr_documents() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in _library_pdf_documents():
        if document.get("text_status") != "scanned":
            continue
        source = Path(document["path"])
        derivative = current_ocr_pdf(source)
        rows.append(
            {
                **document,
                "ocr_ready": derivative is not None,
                "ocr_path": str(derivative) if derivative else "",
            }
        )
    rows.sort(key=lambda item: (item["ocr_ready"], str(item["display_name"]).casefold()))
    return rows


def ocr_status() -> dict[str, Any]:
    rows = ocr_documents()
    ready = [row for row in rows if row["ocr_ready"]]
    required = [row for row in rows if not row["ocr_ready"]]
    stored_bytes = 0
    if OCR_PDF_DIR.exists():
        for item in OCR_PDF_DIR.glob("*.pdf"):
            try:
                stored_bytes += item.stat().st_size
            except OSError:
                pass
    return {
        "available": ocr_available(),
        "ocrmypdf": ocr_executable() or "",
        "tesseract": tesseract_executable() or "",
        "scanned_documents": len(rows),
        "ready_documents": len(ready),
        "required_documents": len(required),
        "stored_bytes": stored_bytes,
        "documents": rows,
        "job": ocr_job_status(),
    }


def _write_metadata(source: Path, output: Path, pages: int) -> None:
    OCR_META_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata_version": OCR_METADATA_VERSION,
        "status": "complete",
        "source_path": str(source.resolve()),
        "source": _source_signature(source),
        "ocr_path": str(output),
        "pages": pages,
        "completed_at": time(),
    }
    temp = _meta_path(source).with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(_meta_path(source))


def _update_progress_from_text(text: str, total_pages: int) -> None:
    percentages = _PERCENT_RE.findall(text)
    pages = _PAGE_RE.findall(text)
    updates: dict[str, Any] = {}
    if percentages:
        percent = max(0.0, min(100.0, float(percentages[-1])))
        updates["percent"] = percent
        if total_pages:
            updates["current_page"] = min(total_pages, max(1, round(total_pages * percent / 100.0)))
    if pages:
        current, total = pages[-1]
        current_i, total_i = int(current), int(total)
        updates.update(
            current_page=current_i,
            total_pages=total_i,
            percent=(100.0 * current_i / total_i) if total_i else 0.0,
        )
    if updates:
        _set_state(**updates)


def _reader_thread(stream: Any, total_pages: int) -> None:
    try:
        tail = ""
        while True:
            chunk = stream.read(256)
            if not chunk:
                break
            combined = tail + chunk
            _update_progress_from_text(combined, total_pages)
            tail = combined[-80:]
    except Exception:
        logger.debug("Unable to parse OCR progress output", exc_info=True)


def _run_ocr(source: Path) -> Path:
    global _active_process

    executable = ocr_executable()
    if not executable or not tesseract_executable():
        raise RuntimeError(
            "OCR dependencies are unavailable. Install OCRmyPDF and Tesseract "
            "on the TTLibrarian host (Ubuntu: sudo apt install ocrmypdf tesseract-ocr)."
        )

    OCR_PDF_DIR.mkdir(parents=True, exist_ok=True)
    OCR_META_DIR.mkdir(parents=True, exist_ok=True)
    output = _pdf_path(source)
    temp_output = output.with_suffix(".working.pdf")
    temp_output.unlink(missing_ok=True)
    total_pages = _page_count(source)
    _set_state(current_page=0, total_pages=total_pages, percent=0.0)

    command = [
        executable,
        "--skip-text",
        "--rotate-pages",
        "--deskew",
        "--jobs", "1",
        "--output-type", "pdf",
        "--progress-bar",
        str(source),
        str(temp_output),
    ]
    logger.info("Starting OCR: %s", source)
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=0,
        env=env,
    )
    with _process_lock:
        _active_process = process

    reader = Thread(target=_reader_thread, args=(process.stdout, total_pages), daemon=True)
    reader.start()

    try:
        while process.poll() is None:
            if _cancel_event.wait(0.2):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise InterruptedError("OCR cancelled by user.")
        reader.join(timeout=2)
        if _cancel_event.is_set():
            raise InterruptedError("OCR cancelled by user.")
        if process.returncode != 0:
            raise RuntimeError(f"OCRmyPDF exited with status {process.returncode} while processing {source.name}.")
        if not temp_output.exists() or temp_output.stat().st_size == 0:
            raise RuntimeError(f"OCRmyPDF did not create a usable output for {source.name}.")
        temp_output.replace(output)
        _write_metadata(source, output, total_pages)
        _set_state(percent=100.0, current_page=total_pages)
        logger.info("OCR complete: %s -> %s", source, output)
        return output
    finally:
        with _process_lock:
            if _active_process is process:
                _active_process = None
        if process.poll() is None:
            process.kill()
        temp_output.unlink(missing_ok=True)


def _rebuild_knowledgebase_after_ocr() -> None:
    from app.knowledgebase import invalidate_chunks, invalidate_embeddings
    from app.rag.chunks import build_chunk_cache
    from app.rag.embeddings import embedding_build_status, start_embedding_build
    from app.search.extract import build_text_cache

    _set_state(stage="extracting", message="OCR complete. Refreshing extracted text...", percent=0.0, current_page=0, total_pages=0)
    text_summary = build_text_cache(force=False)
    if text_summary.get("errors"):
        raise RuntimeError(f"Text refresh completed with {text_summary['errors']} error(s).")

    _set_state(stage="chunking", message="Rebuilding context chunks...", percent=0.0)
    invalidate_chunks()
    build_chunk_cache()

    # Do not let an older in-flight embedding job mark stale vectors current.
    while embedding_build_status().get("running"):
        _set_state(stage="embedding_wait", message="Waiting for the current embedding build to finish before rebuilding it...", percent=0.0)
        sleep(0.5)
    invalidate_embeddings()
    _set_state(stage="embedding", message="Starting semantic embedding rebuild...", percent=0.0)
    start_embedding_build()


def _worker(document_keys: list[str] | None) -> None:
    try:
        rows = ocr_documents()
        if document_keys is None:
            selected = [row for row in rows if not row["ocr_ready"]]
        else:
            allowed = set(document_keys)
            selected = [row for row in rows if row["key"] in allowed and not row["ocr_ready"]]

        if not selected:
            _set_state(
                running=False,
                stage="complete",
                message="No PDFs currently require OCR.",
                current=0,
                total=0,
                percent=100.0,
                finished_at=time(),
            )
            return

        _set_state(total=len(selected), completed=0, failed=0)
        for index, document in enumerate(selected, start=1):
            if _cancel_event.is_set():
                raise InterruptedError("OCR cancelled by user.")
            source = Path(document["path"])
            _set_state(
                stage="ocr",
                message=f"OCR {index} of {len(selected)}: {source.name}",
                current=index,
                current_file=source.name,
                percent=0.0,
                current_page=0,
                total_pages=_page_count(source),
            )
            try:
                _run_ocr(source)
            except InterruptedError:
                raise
            except Exception:
                logger.exception("OCR failed: %s", source)
                _set_state(failed=ocr_job_status()["failed"] + 1)
                raise
            _set_state(completed=index)

        if _cancel_event.is_set():
            raise InterruptedError("OCR cancelled by user.")
        _rebuild_knowledgebase_after_ocr()
        _set_state(
            running=False,
            stage="complete",
            message=(
                f"OCR complete for {len(selected)} PDF{'s' if len(selected) != 1 else ''}. "
                "Text and chunks were refreshed; semantic embeddings are rebuilding in the background."
            ),
            percent=100.0,
            current_page=0,
            total_pages=0,
            finished_at=time(),
            error=None,
        )
    except InterruptedError as exc:
        _set_state(
            running=False,
            stage="cancelled",
            message=str(exc),
            finished_at=time(),
            cancelled=True,
            error=None,
        )
    except Exception as exc:
        logger.exception("OCR job failed")
        _set_state(
            running=False,
            stage="error",
            message=f"OCR job failed: {exc}",
            finished_at=time(),
            error=str(exc),
        )


def start_ocr_job(document_keys: list[str] | None = None) -> dict[str, Any]:
    if not ocr_available():
        raise RuntimeError(
            "OCR dependencies are unavailable. Install OCRmyPDF and Tesseract "
            "on the TTLibrarian host (Ubuntu: sudo apt install ocrmypdf tesseract-ocr)."
        )
    with _state_lock:
        if _job_state["running"]:
            raise RuntimeError("An OCR job is already running.")
        _job_state.update(
            running=True,
            stage="starting",
            message="Preparing OCR job...",
            current=0,
            total=0,
            percent=0.0,
            current_file="",
            current_page=0,
            total_pages=0,
            completed=0,
            failed=0,
            started_at=time(),
            finished_at=None,
            error=None,
            cancelled=False,
        )
    _cancel_event.clear()
    Thread(target=_worker, args=(document_keys,), daemon=True, name="ttl-ocr").start()
    return ocr_job_status()


def cancel_ocr_job() -> dict[str, Any]:
    state = ocr_job_status()
    if not state["running"]:
        return state
    _cancel_event.set()
    with _process_lock:
        process = _active_process
    if process is not None and process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass
    _set_state(message="Cancelling OCR after the current subprocess stops...")
    return ocr_job_status()
