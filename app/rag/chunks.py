from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.config import CACHE_DIR
from app.library.manager import list_folders, scan_folder
from app.search.extract import load_cached_text

RAG_CACHE_DIR = CACHE_DIR / "rag"
CHUNK_CACHE_FILE = RAG_CACHE_DIR / "chunks.json"
CHUNK_VERSION = 1

TARGET_CHARS = 1800
OVERLAP_CHARS = 250
MIN_CHARS = 120
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")


def _chunk_id(path: str, page: int, ordinal: int, text: str) -> str:
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


def build_chunk_cache() -> dict[str, int]:
    RAG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    chunks = []
    seen_paths = set()
    documents = 0
    pages = 0
    characters = 0

    for folder in list_folders():
        scan = scan_folder(folder, generate_covers=False)

        for document in scan["documents"]:
            path_text = document["path"]

            if path_text in seen_paths:
                continue

            seen_paths.add(path_text)

            if document["type"] not in {"PDF", "Text", "Markdown"}:
                continue

            cached = load_cached_text(Path(path_text))
            if cached is None:
                continue

            documents += 1

            for page_data in cached.get("pages", []):
                page_number = int(page_data.get("page", 1))
                page_text = page_data.get("text", "")

                if not page_text.strip():
                    continue

                pages += 1

                for ordinal, chunk_text in enumerate(chunk_page(page_text)):
                    characters += len(chunk_text)
                    chunks.append(
                        {
                            "id": _chunk_id(
                                path_text,
                                page_number,
                                ordinal,
                                chunk_text,
                            ),
                            "path": path_text,
                            "filename": document["filename"],
                            "display_name": document["display_name"],
                            "type": document["type"],
                            "page": page_number,
                            "ordinal": ordinal,
                            "text": chunk_text,
                        }
                    )

    payload = {
        "chunk_version": CHUNK_VERSION,
        "documents": documents,
        "pages": pages,
        "characters": characters,
        "chunks": chunks,
    }

    CHUNK_CACHE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "documents": documents,
        "pages": pages,
        "chunks": len(chunks),
        "characters": characters,
    }


def load_chunks() -> list[dict]:
    if not CHUNK_CACHE_FILE.exists():
        return []

    try:
        data = json.loads(CHUNK_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    if data.get("chunk_version") != CHUNK_VERSION:
        return []

    return data.get("chunks", [])


def chunk_cache_status() -> dict[str, int]:
    if not CHUNK_CACHE_FILE.exists():
        return {
            "documents": 0,
            "pages": 0,
            "chunks": 0,
            "characters": 0,
            "cache_bytes": 0,
        }

    try:
        data = json.loads(CHUNK_CACHE_FILE.read_text(encoding="utf-8"))
        return {
            "documents": data.get("documents", 0),
            "pages": data.get("pages", 0),
            "chunks": len(data.get("chunks", [])),
            "characters": data.get("characters", 0),
            "cache_bytes": CHUNK_CACHE_FILE.stat().st_size,
        }
    except Exception:
        return {
            "documents": 0,
            "pages": 0,
            "chunks": 0,
            "characters": 0,
            "cache_bytes": 0,
        }


def clear_chunk_cache() -> None:
    CHUNK_CACHE_FILE.unlink(missing_ok=True)
