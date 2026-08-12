from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from threading import Lock, Thread
from time import time
from typing import Any

from app.config import CACHE_DIR
from app.knowledgebase import invalidate_chunks, mark_chunks_current
from app.library.manager import list_folders, scan_folder
from app.search.extract import load_cached_text

RAG_CACHE_DIR = CACHE_DIR / "rag"
CHUNK_CACHE_FILE = RAG_CACHE_DIR / "chunks.json"
CHUNK_VERSION = 1

TARGET_CHARS = 1800
OVERLAP_CHARS = 250
MIN_CHARS = 120
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")

_build_lock = Lock()
_build_state: dict[str, Any] = {
    "running": False,
    "stage": "idle",
    "message": "Ready",
    "current": 0,
    "total": 0,
    "percent": 0.0,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _set_build_state(**updates: Any) -> None:
    with _build_lock:
        _build_state.update(updates)


def chunk_build_status() -> dict[str, Any]:
    with _build_lock:
        return dict(_build_state)


def _chunk_id(path: str, page: int, ordinal: int, text: str) -> str:
    # Preserve the established ID format so existing embeddings for unchanged
    # documents remain reusable across the incremental-indexing upgrade.
    raw = f"{path}\0{page}\0{ordinal}\0{text[:200]}".encode(
        "utf-8",
        errors="surrogatepass",
    )
    return hashlib.sha256(raw).hexdigest()[:24]


def _split_large_block(block: str) -> list[str]:
    if len(block) <= TARGET_CHARS:
        return [block]

    pieces = []
    start = 0

    while start < len(block):
        end = min(start + TARGET_CHARS, len(block))

        if end < len(block):
            preferred = max(
                block.rfind(". ", start, end),
                block.rfind("! ", start, end),
                block.rfind("? ", start, end),
                block.rfind("\n", start, end),
            )
            if preferred > start + TARGET_CHARS // 2:
                end = preferred + 1

        piece = block[start:end].strip()
        if piece:
            pieces.append(piece)

        if end >= len(block):
            break

        start = max(end - OVERLAP_CHARS, start + 1)

    return pieces


def chunk_page(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").strip()

    if not text:
        return []

    if len(text) < MIN_CHARS:
        return [text]

    paragraphs = [
        paragraph.strip()
        for paragraph in PARAGRAPH_SPLIT_RE.split(text)
        if paragraph.strip()
    ]

    blocks = []
    for paragraph in paragraphs:
        blocks.extend(_split_large_block(paragraph))

    chunks = []
    current = ""

    for block in blocks:
        candidate = block if not current else f"{current}\n\n{block}"

        if len(candidate) <= TARGET_CHARS:
            current = candidate
            continue

        if current:
            chunks.append(current)

        current = block

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if len(chunk.strip()) >= MIN_CHARS]


def _load_chunk_payload() -> dict[str, Any] | None:
    if not CHUNK_CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CHUNK_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("chunk_version") != CHUNK_VERSION:
        return None
    if not isinstance(data.get("chunks"), list):
        return None
    return data


def _document_chunks(path_text: str, cached: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    filename = str(cached.get("filename") or Path(path_text).name)
    display_name = str(cached.get("display_name") or Path(path_text).stem)
    document_type = str(cached.get("type") or "PDF")
    chunks: list[dict[str, Any]] = []
    pages = 0
    characters = 0

    for page_data in cached.get("pages", []):
        page_number = int(page_data.get("page", 1))
        page_text = str(page_data.get("text", ""))
        if not page_text.strip():
            continue

        for ordinal, chunk_text in enumerate(chunk_page(page_text)):
            characters += len(chunk_text)
            chunks.append(
                {
                    "id": _chunk_id(path_text, page_number, ordinal, chunk_text),
                    "path": path_text,
                    "filename": filename,
                    "display_name": display_name,
                    "type": document_type,
                    "page": page_number,
                    "ordinal": ordinal,
                    "text": chunk_text,
                }
            )
        pages += 1

    return chunks, pages, characters


def _current_cached_documents() -> list[tuple[str, dict[str, Any]]]:
    planned: list[tuple[str, dict[str, Any]]] = []
    seen_paths: set[str] = set()

    for folder in list_folders():
        scan = scan_folder(folder, generate_covers=False)
        for document in scan["documents"]:
            path_text = str(Path(document["path"]).resolve())
            if path_text in seen_paths:
                continue
            seen_paths.add(path_text)
            if document["type"] not in {"PDF", "Text", "Markdown", "CBZ", "CBR"}:
                continue
            cached = load_cached_text(Path(path_text))
            if cached is None:
                continue
            if not any(str(page.get("text", "")).strip() for page in cached.get("pages", [])):
                continue
            planned.append((path_text, cached))

    return planned


def _payload_from_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    documents = {str(chunk.get("path") or "") for chunk in chunks if chunk.get("path")}
    pages = {
        (str(chunk.get("path") or ""), int(chunk.get("page", 1)))
        for chunk in chunks
        if chunk.get("path")
    }
    return {
        "chunk_version": CHUNK_VERSION,
        "documents": len(documents),
        "pages": len(pages),
        "characters": sum(len(str(chunk.get("text", ""))) for chunk in chunks),
        "chunks": chunks,
    }


def build_chunk_cache(
    *,
    changed_paths: list[str] | set[str] | None = None,
    removed_paths: list[str] | set[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build or incrementally update the context-chunk cache.

    Normal knowledgebase updates pass the paths whose extracted text changed and
    paths removed from the library. Existing chunks for every other document are
    copied through untouched. A missing/incompatible chunk cache automatically
    falls back to a full build.
    """
    RAG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    old_payload = _load_chunk_payload()
    full_rebuild = force or old_payload is None

    changed = {str(Path(path).resolve()) for path in (changed_paths or [])}
    removed = {str(Path(path).resolve()) for path in (removed_paths or [])}
    affected = changed | removed

    if full_rebuild:
        _set_build_state(
            stage="scanning",
            message="Scanning indexed documents and counting pages...",
            current=0,
            total=0,
            percent=0.0,
        )
        planned = _current_cached_documents()
        total_pages = sum(
            sum(1 for page in cached.get("pages", []) if str(page.get("text", "")).strip())
            for _, cached in planned
        )
        _set_build_state(
            stage="chunking",
            message=f"Building context chunks from {total_pages:,} pages...",
            current=0,
            total=total_pages,
            percent=0.0,
        )
        chunks: list[dict[str, Any]] = []
        pages_done = 0
        for path_text, cached in planned:
            document_chunks, document_pages, _ = _document_chunks(path_text, cached)
            chunks.extend(document_chunks)
            pages_done += document_pages
            _set_build_state(
                stage="chunking",
                message=f"Processed {pages_done:,} of {total_pages:,} pages",
                current=pages_done,
                total=total_pages,
                percent=(pages_done / total_pages * 100.0) if total_pages else 100.0,
            )
        removed_chunk_ids: list[str] = []
        new_chunk_ids = [chunk["id"] for chunk in chunks]
        updated_documents = len({chunk["path"] for chunk in chunks})
        removed_documents = 0
    else:
        old_chunks = list(old_payload.get("chunks", []))
        removed_chunk_ids = [
            str(chunk.get("id") or "")
            for chunk in old_chunks
            if str(Path(str(chunk.get("path") or "")).resolve()) in affected
        ]
        chunks = [
            chunk
            for chunk in old_chunks
            if str(Path(str(chunk.get("path") or "")).resolve()) not in affected
        ]

        cached_by_path: dict[str, dict[str, Any]] = {}
        total_pages = 0
        for path_text in sorted(changed):
            cached = load_cached_text(Path(path_text))
            if cached is None:
                continue
            cached_by_path[path_text] = cached
            total_pages += sum(
                1 for page in cached.get("pages", []) if str(page.get("text", "")).strip()
            )

        _set_build_state(
            stage="chunking",
            message=(
                f"Updating context chunks for {len(changed):,} changed document"
                f"{'s' if len(changed) != 1 else ''}..."
            ),
            current=0,
            total=total_pages,
            percent=0.0,
        )

        pages_done = 0
        new_chunk_ids: list[str] = []
        for path_text in sorted(changed):
            cached = cached_by_path.get(path_text)
            if cached is None:
                continue
            document_chunks, document_pages, _ = _document_chunks(path_text, cached)
            chunks.extend(document_chunks)
            new_chunk_ids.extend(chunk["id"] for chunk in document_chunks)
            pages_done += document_pages
            _set_build_state(
                stage="chunking",
                message=f"Processed {pages_done:,} of {total_pages:,} changed pages",
                current=pages_done,
                total=total_pages,
                percent=(pages_done / total_pages * 100.0) if total_pages else 100.0,
            )

        updated_documents = len(changed)
        removed_documents = len(removed)

    # Keep deterministic document/page ordering for stable retrieval and vector files.
    chunks.sort(
        key=lambda chunk: (
            str(chunk.get("path", "")).casefold(),
            int(chunk.get("page", 1)),
            int(chunk.get("ordinal", 0)),
        )
    )

    _set_build_state(
        stage="saving",
        message="Saving context chunk cache...",
        current=pages_done,
        total=total_pages,
        percent=100.0,
    )
    payload = _payload_from_chunks(chunks)
    CHUNK_CACHE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    mark_chunks_current()

    return {
        "documents": payload["documents"],
        "pages": payload["pages"],
        "chunks": len(chunks),
        "characters": payload["characters"],
        "updated_documents": updated_documents,
        "removed_documents": removed_documents,
        "changed_paths": sorted(changed),
        "removed_paths": sorted(removed),
        "removed_chunk_ids": [chunk_id for chunk_id in removed_chunk_ids if chunk_id],
        "new_chunk_ids": new_chunk_ids,
        "full_rebuild": full_rebuild,
    }


def _background_build_worker() -> None:
    try:
        result = build_chunk_cache(force=True)
        _set_build_state(
            running=False,
            stage="complete",
            message=(
                f"Complete: {result['documents']:,} documents, "
                f"{result['pages']:,} pages, {result['chunks']:,} chunks"
            ),
            current=result["pages"],
            total=result["pages"],
            percent=100.0,
            finished_at=time(),
            error=None,
        )
    except Exception as exc:
        _set_build_state(
            running=False,
            stage="error",
            message=f"Context chunk build failed: {exc}",
            finished_at=time(),
            error=str(exc),
        )


def start_chunk_build() -> dict[str, Any]:
    with _build_lock:
        if _build_state["running"]:
            return dict(_build_state)
        _build_state.update(
            {
                "running": True,
                "stage": "starting",
                "message": "Starting context chunk build...",
                "current": 0,
                "total": 0,
                "percent": 0.0,
                "started_at": time(),
                "finished_at": None,
                "error": None,
            }
        )
    Thread(target=_background_build_worker, name="ttlibrarian-chunk-build", daemon=True).start()
    return chunk_build_status()


def load_chunks() -> list[dict]:
    payload = _load_chunk_payload()
    return list(payload.get("chunks", [])) if payload else []


def chunk_cache_status() -> dict[str, int]:
    payload = _load_chunk_payload()
    if payload is None:
        return {
            "documents": 0,
            "pages": 0,
            "chunks": 0,
            "characters": 0,
            "cache_bytes": 0,
        }
    return {
        "documents": int(payload.get("documents", 0)),
        "pages": int(payload.get("pages", 0)),
        "chunks": len(payload.get("chunks", [])),
        "characters": int(payload.get("characters", 0)),
        "cache_bytes": CHUNK_CACHE_FILE.stat().st_size,
    }


def clear_chunk_cache() -> None:
    if chunk_build_status()["running"]:
        raise RuntimeError("Cannot clear context chunks while a build is running.")
    CHUNK_CACHE_FILE.unlink(missing_ok=True)
    invalidate_chunks()
