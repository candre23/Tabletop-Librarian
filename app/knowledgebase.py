from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import CACHE_DIR

STATE_DIR = CACHE_DIR / "knowledgebase"
STATE_FILE = STATE_DIR / "state.json"
TEXT_CACHE_DIR = CACHE_DIR / "text"
RAG_CACHE_DIR = CACHE_DIR / "rag"
CHUNK_CACHE_FILE = RAG_CACHE_DIR / "chunks.json"
EMBEDDINGS_FILE = RAG_CACHE_DIR / "embeddings.npy"
EMBEDDING_META_FILE = RAG_CACHE_DIR / "embeddings.json"

_lock = Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_state() -> dict[str, Any]:
    # Existing installs should start from their current cache state rather than
    # showing a false "library changed" warning immediately after upgrading.
    text_ready = TEXT_CACHE_DIR.exists() and any(TEXT_CACHE_DIR.glob("*.json"))
    chunks_ready = CHUNK_CACHE_FILE.exists()
    embeddings_ready = EMBEDDINGS_FILE.exists() and EMBEDDING_META_FILE.exists()
    return {
        "version": 1,
        "library_revision": 1,
        "text_revision": 1 if text_ready else 0,
        "chunk_revision": 1 if chunks_ready else 0,
        "embedding_revision": 1 if embeddings_ready else 0,
        "library_changed_at": None,
        "last_reason": "",
    }


def _load_unlocked() -> dict[str, Any]:
    if not STATE_FILE.exists():
        state = _default_state()
        _save_unlocked(state)
        return state
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        raw = _default_state()
    state = _default_state()
    state.update({key: value for key, value in raw.items() if key in state})
    return state


def _save_unlocked(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE_FILE)


def knowledgebase_status() -> dict[str, Any]:
    with _lock:
        state = _load_unlocked()
    revision = int(state.get("library_revision", 0))
    text_revision = int(state.get("text_revision", 0))
    chunk_revision = int(state.get("chunk_revision", 0))
    embedding_revision = int(state.get("embedding_revision", 0))
    return {
        **state,
        "text_current": text_revision == revision,
        "chunks_current": chunk_revision == revision,
        "embeddings_current": embedding_revision == revision,
        "needs_update": embedding_revision != revision,
        "library_changed": bool(state.get("library_changed_at")) and embedding_revision != revision,
    }


def mark_library_changed(reason: str = "Library contents changed") -> dict[str, Any]:
    with _lock:
        state = _load_unlocked()
        state["library_revision"] = int(state.get("library_revision", 0)) + 1
        state["library_changed_at"] = _now()
        state["last_reason"] = str(reason or "Library contents changed")
        _save_unlocked(state)
        return dict(state)


def mark_text_current() -> None:
    with _lock:
        state = _load_unlocked()
        state["text_revision"] = int(state["library_revision"])
        _save_unlocked(state)


def mark_chunks_current() -> None:
    with _lock:
        state = _load_unlocked()
        revision = int(state["library_revision"])
        # Chunks are only current if they were built from current extracted text.
        if int(state.get("text_revision", 0)) == revision:
            state["chunk_revision"] = revision
        _save_unlocked(state)


def mark_embeddings_current() -> None:
    with _lock:
        state = _load_unlocked()
        revision = int(state["library_revision"])
        # Embeddings are only current if they were built from current chunks.
        if int(state.get("chunk_revision", 0)) == revision:
            state["embedding_revision"] = revision
            state["library_changed_at"] = None
            state["last_reason"] = ""
        _save_unlocked(state)


def invalidate_text() -> None:
    with _lock:
        state = _load_unlocked()
        state["text_revision"] = 0
        state["chunk_revision"] = 0
        state["embedding_revision"] = 0
        _save_unlocked(state)


def invalidate_chunks() -> None:
    with _lock:
        state = _load_unlocked()
        state["chunk_revision"] = 0
        state["embedding_revision"] = 0
        _save_unlocked(state)


def invalidate_embeddings() -> None:
    with _lock:
        state = _load_unlocked()
        state["embedding_revision"] = 0
        _save_unlocked(state)
