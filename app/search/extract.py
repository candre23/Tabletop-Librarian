from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import fitz

from app.config import CACHE_DIR
from app.knowledgebase import invalidate_text, mark_text_current
from app.library.manager import list_folders, scan_folder

logger = logging.getLogger(__name__)

TEXT_CACHE_DIR = CACHE_DIR / "text"
CACHE_VERSION = 1


def _cache_key(path: Path) -> str:
    raw = str(path.resolve()).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:24]


def cache_path_for(path: Path) -> Path:
    return TEXT_CACHE_DIR / f"{_cache_key(path)}.json"


def _source_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _cache_is_current(path: Path, data: dict[str, Any]) -> bool:
    if data.get("cache_version") != CACHE_VERSION:
        return False

    try:
        return data.get("source") == _source_signature(path)
    except OSError:
        return False


def load_cached_text(path: Path) -> dict[str, Any] | None:
    cache = cache_path_for(path)

    if not cache.exists():
        return None

    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not _cache_is_current(path, data):
        # A configured library source may be temporarily offline. The library
        # manifest decides whether the document still belongs to TTL; keep its
        # last known extracted text available while the canonical file cannot
        # be stat'ed. A successful source scan will later identify true deletes.
        if path.exists():
            return None
        if data.get("cache_version") != CACHE_VERSION:
            return None
        if str(data.get("path") or "") != str(path.expanduser().resolve(strict=False)):
            return None

    return data


def extract_pdf(path: Path) -> dict[str, Any]:
    pages = []

    document = fitz.open(path)
    try:
        for index in range(document.page_count):
            text = document.load_page(index).get_text("text").strip()
            pages.append(
                {
                    "page": index + 1,
                    "text": text,
                }
            )
    finally:
        document.close()

    return {
        "kind": "paged",
        "pages": pages,
    }


def extract_text_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "kind": "text",
        "pages": [
            {
                "page": 1,
                "text": text,
            }
        ],
    }


def extract_document(document: dict[str, Any], force: bool = False) -> dict[str, Any]:
    path = Path(document["path"])
    cache = cache_path_for(path)

    if not force:
        cached = load_cached_text(path)
        if cached is not None:
            return {
                "status": "cached",
                "path": str(path),
                "pages": len(cached.get("pages", [])),
                "characters": cached.get("characters", 0),
            }

    extracted_from = path
    if document["type"] == "PDF":
        if document.get("text_status") == "scanned":
            from app.ocr import current_ocr_pdf
            ocr_path = current_ocr_pdf(path)
            if ocr_path is None:
                return {
                    "status": "skipped_scanned",
                    "path": str(path),
                    "pages": 0,
                    "characters": 0,
                }
            extracted_from = ocr_path
        extracted = extract_pdf(extracted_from)
    elif document["type"] in {"CBZ", "CBR"}:
        from app.ocr import current_ocr_pdf
        ocr_path = current_ocr_pdf(path)
        if ocr_path is None:
            return {
                "status": "skipped_scanned",
                "path": str(path),
                "pages": 0,
                "characters": 0,
            }
        extracted_from = ocr_path
        extracted = extract_pdf(extracted_from)
    elif document["type"] in {"Text", "Markdown"}:
        extracted = extract_text_file(path)
    else:
        return {
            "status": "unsupported",
            "path": str(path),
            "pages": 0,
            "characters": 0,
        }

    characters = sum(len(page.get("text", "")) for page in extracted["pages"])

    payload = {
        "cache_version": CACHE_VERSION,
        "source": _source_signature(path),
        "path": str(path.resolve()),
        "filename": path.name,
        "display_name": document.get("display_name") or path.stem,
        "type": document["type"],
        "kind": extracted["kind"],
        "pages": extracted["pages"],
        "characters": characters,
        "extracted_from": str(extracted_from.resolve()),
        "ocr_derived": extracted_from != path,
    }

    TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    logger.info(
        "Extracted text: %s (%s pages, %s chars)",
        path,
        len(payload["pages"]),
        characters,
    )

    return {
        "status": "extracted",
        "path": str(path),
        "pages": len(payload["pages"]),
        "characters": characters,
    }


def build_text_cache(force: bool = False) -> dict[str, Any]:
    summary = {
        "documents_seen": 0,
        "extracted": 0,
        "cached": 0,
        "skipped_scanned": 0,
        "unsupported": 0,
        "errors": 0,
        "pages": 0,
        "characters": 0,
        "changed_paths": [],
        "removed_paths": [],
    }

    seen_paths: set[str] = set()
    unavailable_paths: set[str] = set()
    changed_paths: set[str] = set()

    for folder in list_folders():
        scan = scan_folder(folder, generate_covers=False)

        for document in scan["documents"]:
            path = document["path"]

            if path in seen_paths:
                continue

            seen_paths.add(path)
            summary["documents_seen"] += 1

            if document.get("source_available") is False:
                unavailable_paths.add(path)
                # Preserve the last successful extraction/chunks/vectors. An
                # unavailable source is not evidence that the document changed.
                continue

            try:
                result = extract_document(document, force=force)
            except Exception:
                logger.exception("Text extraction failed: %s", path)
                summary["errors"] += 1
                continue

            status = result["status"]

            if status in summary:
                summary[status] += 1

            if status == "extracted":
                changed_paths.add(str(Path(path).resolve()))

            summary["pages"] += result.get("pages", 0)
            summary["characters"] += result.get("characters", 0)

    # Remove orphaned or stale extracted-text entries. A stale cache can occur
    # when a formerly searchable source changes into a scanned/unsupported file.
    # Downstream incremental stages need the path so they can discard old chunks
    # and vectors for that document.
    removed_paths: set[str] = set()
    if TEXT_CACHE_DIR.exists():
        for cache in TEXT_CACHE_DIR.glob("*.json"):
            try:
                cached_data = json.loads(cache.read_text(encoding="utf-8"))
                cached_path = str(cached_data.get("path") or "")
            except Exception:
                cached_path = ""

            remove_cache = False
            if not cached_path or cached_path not in seen_paths:
                remove_cache = True
            elif cached_path in unavailable_paths:
                remove_cache = False
            else:
                source = Path(cached_path)
                if not _cache_is_current(source, cached_data):
                    remove_cache = True

            if remove_cache:
                cache.unlink(missing_ok=True)
                if cached_path:
                    if cached_path in seen_paths:
                        changed_paths.add(cached_path)
                    else:
                        removed_paths.add(cached_path)

    summary["changed_paths"] = sorted(changed_paths)
    summary["removed_paths"] = sorted(removed_paths)

    if summary["errors"] == 0:
        mark_text_current()

    return summary

def text_cache_status() -> dict[str, Any]:
    status = {
        "cached_documents": 0,
        "pages": 0,
        "characters": 0,
        "cache_bytes": 0,
    }

    if not TEXT_CACHE_DIR.exists():
        return status

    for cache in TEXT_CACHE_DIR.glob("*.json"):
        try:
            status["cache_bytes"] += cache.stat().st_size
            data = json.loads(cache.read_text(encoding="utf-8"))
            status["cached_documents"] += 1
            status["pages"] += len(data.get("pages", []))
            status["characters"] += data.get("characters", 0)
        except Exception:
            continue

    return status


def clear_text_cache() -> None:
    if TEXT_CACHE_DIR.exists():
        for item in TEXT_CACHE_DIR.glob("*.json"):
            item.unlink(missing_ok=True)
    invalidate_text()
