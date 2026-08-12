from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from threading import Event, Lock, Thread
from time import time
from typing import Any

import fitz
from PIL import Image

from app.config import OCR_DATA_DIR

logger = logging.getLogger(__name__)

OCR_PDF_DIR = OCR_DATA_DIR / "pdf"
OCR_META_DIR = OCR_DATA_DIR / "meta"
OCR_WORK_DIR = OCR_DATA_DIR / "work"
OCR_METADATA_VERSION = 1
OCR_DOCUMENT_TYPES = {"PDF", "CBZ", "CBR"}

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
    "progress_description": "",
    "completed": 0,
    "failed": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "cancelled": False,
}

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


def cached_ocr_pdf_for_unavailable_source(path: Path) -> Path | None:
    """Return the last known OCR derivative only when the source is unavailable.

    This deliberately does not permit stale derivatives when the source exists: if
    the original has changed, current_ocr_pdf() must invalidate it.
    """
    source = path.expanduser().resolve(strict=False)
    if source.exists():
        return None
    data = _load_metadata(source)
    if not data or data.get("status") != "complete":
        return None
    if data.get("source_path") != str(source):
        return None
    output = Path(str(data.get("ocr_path") or ""))
    if output != _pdf_path(source) or not output.exists():
        return None
    return output


def remove_ocr_derivative(path: Path) -> bool:
    """Delete TTL-managed OCR artifacts tied to one canonical source path."""
    source = path.expanduser().resolve(strict=False)
    removed = False
    for target in (_pdf_path(source), _meta_path(source)):
        try:
            if target.exists():
                target.unlink()
                removed = True
        except OSError:
            logger.exception("Unable to remove OCR artifact %s", target)
    # Any abandoned comic assembly/progress files for this source are safe to drop.
    if OCR_WORK_DIR.exists():
        prefix = _source_key(source)
        for target in OCR_WORK_DIR.glob(f"{prefix}*"):
            try:
                if target.is_file():
                    target.unlink()
            except OSError:
                logger.exception("Unable to remove OCR work artifact %s", target)
    return removed


def _page_count(path: Path) -> int:
    try:
        document = fitz.open(path)
        try:
            return int(document.page_count)
        finally:
            document.close()
    except Exception:
        return 0


def _library_ocr_documents() -> list[dict[str, Any]]:
    # Delayed import avoids a module cycle through library.manager -> pdf_status.
    from app.library.manager import list_folders, scan_folder

    by_path: dict[str, dict[str, Any]] = {}
    for folder in list_folders():
        scan = scan_folder(folder, generate_covers=False)
        for document in scan.get("documents", []):
            doc_type = str(document.get("type") or "")
            if doc_type not in OCR_DOCUMENT_TYPES:
                continue
            if doc_type == "PDF" and document.get("text_status") != "scanned":
                continue
            by_path[str(document["path"])] = document
    return list(by_path.values())


def ocr_documents() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in _library_ocr_documents():
        source = Path(document["path"])
        source_available = document.get("source_available") is not False
        derivative = current_ocr_pdf(source)
        if derivative is None and not source_available:
            derivative = cached_ocr_pdf_for_unavailable_source(source)
        rows.append(
            {
                **document,
                "ocr_ready": derivative is not None,
                "ocr_path": str(derivative) if derivative else "",
                "ocr_can_run": source_available,
            }
        )
    rows.sort(key=lambda item: (item["ocr_ready"], str(item["display_name"]).casefold()))
    return rows


def ocr_status() -> dict[str, Any]:
    rows = ocr_documents()
    ready = [row for row in rows if row["ocr_ready"]]
    required = [row for row in rows if not row["ocr_ready"] and row.get("ocr_can_run", True)]
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


def _reader_thread(stream: Any, output_chunks: list[str]) -> None:
    """Retain OCRmyPDF console output for diagnostics without parsing Rich UI text."""
    try:
        retained = 0
        while True:
            chunk = stream.read(256)
            if not chunk:
                break
            output_chunks.append(chunk)
            retained += len(chunk)
            while retained > 65536 and len(output_chunks) > 1:
                retained -= len(output_chunks.pop(0))
    except Exception:
        logger.debug("Unable to capture OCR diagnostic output", exc_info=True)


def _friendly_progress_stage(description: str) -> tuple[str, str, bool]:
    text = description.casefold()
    if "scanning" in text or "scan" in text:
        return "ocr_scan", "Scanning pages", True
    if text.strip() == "ocr" or text.startswith("ocr ") or "ocr" in text:
        return "ocr", "Recognizing text", True
    if any(term in text for term in (
        "linear", "recompress", "deflat", "jbig", "optimiz", "postprocess",
        "pdf/a", "conversion", "metadata", "graft",
    )):
        return "ocr_postprocess", "Postprocessing OCR PDF", False
    return "ocr_processing", description or "Processing OCR PDF", False


def _apply_progress_file(progress_file: Path) -> None:
    try:
        payload = json.loads(progress_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    description = str(payload.get("desc") or "Processing OCR PDF")
    stage, label, page_phase = _friendly_progress_stage(description)
    try:
        current = float(payload.get("current") or 0.0)
    except (TypeError, ValueError):
        current = 0.0
    try:
        total = float(payload.get("total") or 0.0)
    except (TypeError, ValueError):
        total = 0.0

    percent = (100.0 * current / total) if total > 0 else 0.0
    percent = max(0.0, min(100.0, percent))
    updates: dict[str, Any] = {
        "stage": stage,
        "message": label,
        "percent": percent,
        "progress_description": description,
    }
    if page_phase and total > 0:
        updates["current_page"] = max(0, int(round(current)))
        updates["total_pages"] = max(0, int(round(total)))
    else:
        updates["current_page"] = 0
        updates["total_pages"] = 0
    _set_state(**updates)


def _normalized_image_bytes(data: bytes, suffix: str) -> tuple[bytes, int, int]:
    """Return PDF-embeddable image bytes and dimensions.

    JPEG and PNG pages are passed through unchanged. Other supported comic
    image formats are normalized to PNG so PyMuPDF can embed them reliably.
    """
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError("Comic page has invalid image dimensions.")
        if suffix.casefold() in {".jpg", ".jpeg", ".png"}:
            return data, width, height
        frame = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        buffer = io.BytesIO()
        frame.save(buffer, format="PNG")
        return buffer.getvalue(), width, height


def _append_image_page(document: fitz.Document, data: bytes, suffix: str) -> None:
    image_bytes, width_px, height_px = _normalized_image_bytes(data, suffix)
    # Most comic scans contain no useful physical-DPI metadata. Treating them
    # as 150 DPI yields sensible PDF page dimensions while preserving every
    # source pixel for OCR.
    width_pt = max(1.0, width_px * 72.0 / 150.0)
    height_pt = max(1.0, height_px * 72.0 / 150.0)
    page = document.new_page(width=width_pt, height=height_pt)
    page.insert_image(page.rect, stream=image_bytes)


def _build_comic_input_pdf(source: Path, output: Path) -> int:
    from app.readers.comic import cbz_pages, cbr_page_files

    suffix = source.suffix.casefold()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    assembled = fitz.open()
    try:
        if suffix == ".cbz":
            import zipfile

            pages = cbz_pages(source)
            total = len(pages)
            if not total:
                raise RuntimeError(f"No supported image pages were found in {source.name}.")
            with zipfile.ZipFile(source, "r") as archive:
                for index, name in enumerate(pages, start=1):
                    if _cancel_event.is_set():
                        raise InterruptedError("OCR cancelled by user.")
                    _set_state(
                        stage="ocr_prepare",
                        message="Preparing comic pages",
                        current_page=index,
                        total_pages=total,
                        percent=100.0 * index / total,
                        progress_description="Preparing comic pages",
                    )
                    data = archive.read(name)
                    _append_image_page(assembled, data, Path(name).suffix)
        elif suffix == ".cbr":
            pages = cbr_page_files(source)
            total = len(pages)
            if not total:
                raise RuntimeError(f"No supported image pages were found in {source.name}.")
            for index, page_path in enumerate(pages, start=1):
                if _cancel_event.is_set():
                    raise InterruptedError("OCR cancelled by user.")
                _set_state(
                    stage="ocr_prepare",
                    message="Preparing comic pages",
                    current_page=index,
                    total_pages=total,
                    percent=100.0 * index / total,
                    progress_description="Preparing comic pages",
                )
                _append_image_page(assembled, page_path.read_bytes(), page_path.suffix)
        else:
            raise ValueError(f"Unsupported comic archive type: {source.suffix}")

        if assembled.page_count == 0:
            raise RuntimeError(f"No supported image pages were found in {source.name}.")
        assembled.save(output, garbage=3, deflate=True)
        return int(assembled.page_count)
    finally:
        assembled.close()
        if not output.exists() or output.stat().st_size == 0:
            output.unlink(missing_ok=True)


def _prepare_ocr_input(source: Path) -> tuple[Path, int, Path | None]:
    suffix = source.suffix.casefold()
    if suffix == ".pdf":
        return source, _page_count(source), None
    if suffix in {".cbz", ".cbr"}:
        OCR_WORK_DIR.mkdir(parents=True, exist_ok=True)
        temporary = OCR_WORK_DIR / f"{_source_key(source)}.input.pdf"
        total_pages = _build_comic_input_pdf(source, temporary)
        return temporary, total_pages, temporary
    raise ValueError(f"OCR is not supported for {source.suffix or source.name}.")


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
    ocr_input, total_pages, temporary_input = _prepare_ocr_input(source)
    progress_file = output.with_suffix(".progress.json")
    progress_file.unlink(missing_ok=True)
    _set_state(current_page=0, total_pages=0, percent=0.0, progress_description="")

    progress_plugin = Path(__file__).with_name("ocr_progress_plugin.py")
    command = [
        executable,
        "--skip-text",
        "--rotate-pages",
        "--deskew",
        "--jobs", "1",
        "--output-type", "pdf",
        "--plugin", str(progress_plugin),
        str(ocr_input),
        str(temp_output),
    ]
    logger.info("Starting OCR: %s", source)
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["TTL_OCR_PROGRESS_FILE"] = str(progress_file)
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

    output_chunks: list[str] = []
    reader = Thread(target=_reader_thread, args=(process.stdout, output_chunks), daemon=True)
    reader.start()

    try:
        while process.poll() is None:
            _apply_progress_file(progress_file)
            if _cancel_event.wait(0.2):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise InterruptedError("OCR cancelled by user.")
        _apply_progress_file(progress_file)
        reader.join(timeout=2)
        if _cancel_event.is_set():
            raise InterruptedError("OCR cancelled by user.")
        if process.returncode != 0:
            diagnostic = "".join(output_chunks).strip()
            if diagnostic:
                logger.error("OCRmyPDF output for %s:\n%s", source, diagnostic)
            detail = f" OCRmyPDF output: {diagnostic[-2000:]}" if diagnostic else ""
            raise RuntimeError(
                f"OCRmyPDF exited with status {process.returncode} while processing {source.name}." + detail
            )
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
        progress_file.unlink(missing_ok=True)
        if temporary_input is not None:
            temporary_input.unlink(missing_ok=True)


def _worker(document_keys: list[str] | None) -> None:
    knowledgebase_marked_stale = False
    try:
        rows = ocr_documents()
        if document_keys is None:
            selected = [row for row in rows if not row["ocr_ready"] and row.get("ocr_can_run", True)]
        else:
            allowed = set(document_keys)
            selected = [
                row for row in rows
                if row["key"] in allowed and not row["ocr_ready"] and row.get("ocr_can_run", True)
            ]

        if not selected:
            _set_state(
                running=False,
                stage="complete",
                message="No documents currently require OCR.",
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
                total_pages=0,
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
            if not knowledgebase_marked_stale:
                from app.knowledgebase import mark_library_changed
                mark_library_changed("OCR text is available; knowledgebase update required")
                knowledgebase_marked_stale = True

        if _cancel_event.is_set():
            raise InterruptedError("OCR cancelled by user.")
        _set_state(
            running=False,
            stage="complete",
            message=(
                f"OCR complete for {len(selected)} document{'s' if len(selected) != 1 else ''}. "
                "Run Update Knowledgebase when you are ready to index the new OCR text."
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
            progress_description="",
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
