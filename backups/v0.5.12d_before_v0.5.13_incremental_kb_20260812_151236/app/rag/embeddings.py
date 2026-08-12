from __future__ import annotations

import json
import logging
import re
from threading import Lock, Thread
from time import time
from typing import Any

import numpy as np

from app.config import CACHE_DIR, DATA_DIR
from app.knowledgebase import invalidate_embeddings, mark_embeddings_current
from app.rag.chunks import load_chunks

logger = logging.getLogger(__name__)

MODEL_OPTIONS = {
    "fast": {
        "label": "Fast",
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "description": "Fastest ingest. Good general retrieval quality. 384 dimensions.",
    },
    "balanced": {
        "label": "Balanced",
        "model": "sentence-transformers/all-MiniLM-L12-v2",
        "description": "Moderate ingest cost and strong overall retrieval quality. 384 dimensions.",
    },
    "quality": {
        "label": "Semantic Quality",
        "model": "sentence-transformers/all-mpnet-base-v2",
        "description": "Much slower ingest, but stronger on some difficult semantic paraphrases. 768 dimensions.",
    },
}

DEFAULT_MODEL_KEY = "balanced"
SETTINGS_FILE = DATA_DIR / "rag_settings.json"
MODEL_ROOT = DATA_DIR / "models" / "embeddings"

RAG_CACHE_DIR = CACHE_DIR / "rag"
EMBEDDINGS_FILE = RAG_CACHE_DIR / "embeddings.npy"
EMBEDDING_META_FILE = RAG_CACHE_DIR / "embeddings.json"

EMBEDDING_VERSION = 2
BATCH_SIZE = 32

_model = None
_loaded_model_id = None
_model_lock = Lock()

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


def _safe_model_dir_name(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model_id)


def _load_settings() -> dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {"embedding_model": DEFAULT_MODEL_KEY}
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"embedding_model": DEFAULT_MODEL_KEY}
    key = data.get("embedding_model", DEFAULT_MODEL_KEY)
    if key not in MODEL_OPTIONS:
        key = DEFAULT_MODEL_KEY
    return {"embedding_model": key}


def _save_settings(settings: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def selected_model_key() -> str:
    return _load_settings()["embedding_model"]


def selected_model() -> dict[str, str]:
    key = selected_model_key()
    return {"key": key, **MODEL_OPTIONS[key]}


def model_options() -> list[dict[str, Any]]:
    selected = selected_model_key()
    return [{"key": key, **option, "selected": key == selected} for key, option in MODEL_OPTIONS.items()]


def _set_build_state(**updates: Any) -> None:
    with _build_lock:
        _build_state.update(updates)


def embedding_build_status() -> dict[str, Any]:
    with _build_lock:
        return dict(_build_state)


def set_embedding_model(model_key: str) -> dict[str, str]:
    global _model, _loaded_model_id
    if embedding_build_status()["running"]:
        raise RuntimeError("Cannot change embedding model while a build is running.")
    if model_key not in MODEL_OPTIONS:
        raise ValueError("Unknown embedding model selection.")
    settings = _load_settings()
    changed = settings.get("embedding_model") != model_key
    settings["embedding_model"] = model_key
    _save_settings(settings)
    if changed:
        clear_embeddings()
        with _model_lock:
            _model = None
            _loaded_model_id = None
    return selected_model()


def _model_dir(model_id: str):
    return MODEL_ROOT / _safe_model_dir_name(model_id)


def _load_model():
    global _model, _loaded_model_id
    model_info = selected_model()
    model_id = model_info["model"]
    if _model is not None and _loaded_model_id == model_id:
        return _model
    with _model_lock:
        if _model is not None and _loaded_model_id == model_id:
            return _model
        from sentence_transformers import SentenceTransformer
        local_dir = _model_dir(model_id)
        if local_dir.exists() and any(local_dir.iterdir()):
            _set_build_state(stage="loading_model", message=f"Loading {model_info['label']} model and compiling OpenVINO...")
            logger.info("Loading local OpenVINO embedding model: %s", local_dir)
            model = SentenceTransformer(str(local_dir), backend="openvino", device="cpu")
        else:
            _set_build_state(stage="downloading_model", message=f"Downloading and preparing {model_info['label']} model...")
            logger.info("Downloading/exporting OpenVINO embedding model: %s", model_id)
            local_dir.mkdir(parents=True, exist_ok=True)
            model = SentenceTransformer(model_id, backend="openvino", device="cpu")
            _set_build_state(stage="saving_model", message=f"Saving local {model_info['label']} model...")
            model.save_pretrained(str(local_dir))
            logger.info("Saved local OpenVINO embedding model: %s", local_dir)
        _model = model
        _loaded_model_id = model_id
        return _model


def embedding_status() -> dict[str, Any]:
    model_info = selected_model()
    model_id = model_info["model"]
    local_dir = _model_dir(model_id)
    result = {
        "model_key": model_info["key"],
        "model_label": model_info["label"],
        "model": model_id,
        "description": model_info["description"],
        "backend": "OpenVINO / CPU",
        "model_ready": local_dir.exists() and any(local_dir.iterdir()),
        "vectors": 0,
        "dimensions": 0,
        "cache_bytes": 0,
        "cache_matches_model": False,
    }
    if not EMBEDDING_META_FILE.exists() or not EMBEDDINGS_FILE.exists():
        return result
    try:
        metadata = json.loads(EMBEDDING_META_FILE.read_text(encoding="utf-8"))
        if metadata.get("model") != model_id:
            return result
        result["vectors"] = len(metadata.get("chunk_ids", []))
        result["dimensions"] = int(metadata.get("dimensions", 0))
        result["cache_bytes"] = EMBEDDINGS_FILE.stat().st_size + EMBEDDING_META_FILE.stat().st_size
        result["cache_matches_model"] = True
    except Exception:
        pass
    return result


def clear_embeddings() -> None:
    if embedding_build_status()["running"]:
        raise RuntimeError("Cannot clear embeddings while a build is running.")
    EMBEDDINGS_FILE.unlink(missing_ok=True)
    EMBEDDING_META_FILE.unlink(missing_ok=True)
    invalidate_embeddings()


def build_embeddings() -> dict[str, Any]:
    chunks = load_chunks()
    if not chunks:
        raise RuntimeError("Build the RAG corpus before creating embeddings.")
    texts = [chunk.get("text", "") for chunk in chunks]
    chunk_ids = [chunk["id"] for chunk in chunks]
    total = len(texts)
    model_info = selected_model()
    model_id = model_info["model"]

    _set_build_state(stage="loading_model", message=f"Preparing {model_info['label']} model...", current=0, total=total, percent=0.0)
    model = _load_model()
    logger.info("Embedding %s RAG chunks with %s using OpenVINO", total, model_id)

    vector_batches = []
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        _set_build_state(
            stage="embedding",
            message=f"Embedding chunks {start + 1:,}-{end:,} of {total:,}...",
            current=start,
            total=total,
            percent=(start / total) * 100.0,
        )
        batch_vectors = model.encode(
            texts[start:end],
            batch_size=BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        vector_batches.append(np.asarray(batch_vectors, dtype=np.float32))
        _set_build_state(
            stage="embedding",
            message=f"Embedded {end:,} of {total:,} chunks",
            current=end,
            total=total,
            percent=(end / total) * 100.0,
        )

    _set_build_state(stage="saving_index", message="Saving embedding index...", current=total, total=total, percent=100.0)
    vectors = np.vstack(vector_batches)
    RAG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_FILE, vectors)
    metadata = {
        "embedding_version": EMBEDDING_VERSION,
        "model": model_id,
        "model_key": model_info["key"],
        "backend": "openvino",
        "dimensions": int(vectors.shape[1]),
        "chunk_ids": chunk_ids,
    }
    EMBEDDING_META_FILE.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    mark_embeddings_current()
    return {
        "model": model_id,
        "model_label": model_info["label"],
        "vectors": int(vectors.shape[0]),
        "dimensions": int(vectors.shape[1]),
        "cache_bytes": EMBEDDINGS_FILE.stat().st_size + EMBEDDING_META_FILE.stat().st_size,
    }


def _background_build_worker() -> None:
    try:
        result = build_embeddings()
        _set_build_state(
            running=False,
            stage="complete",
            message=f"Complete: {result['vectors']:,} vectors, {result['dimensions']} dimensions",
            current=result["vectors"],
            total=result["vectors"],
            percent=100.0,
            finished_at=time(),
            error=None,
        )
    except Exception as exc:
        logger.exception("Embedding build failed")
        _set_build_state(running=False, stage="error", message=f"Embedding build failed: {exc}", finished_at=time(), error=str(exc))


def start_embedding_build() -> dict[str, Any]:
    with _build_lock:
        if _build_state["running"]:
            return dict(_build_state)
        _build_state.update({
            "running": True,
            "stage": "starting",
            "message": "Starting embedding build...",
            "current": 0,
            "total": 0,
            "percent": 0.0,
            "started_at": time(),
            "finished_at": None,
            "error": None,
        })
    Thread(target=_background_build_worker, name="ttlibrarian-embedding-build", daemon=True).start()
    return embedding_build_status()


def _load_embedding_cache():
    if not EMBEDDINGS_FILE.exists() or not EMBEDDING_META_FILE.exists():
        return None, None
    try:
        metadata = json.loads(EMBEDDING_META_FILE.read_text(encoding="utf-8"))
        if metadata.get("embedding_version") != EMBEDDING_VERSION:
            return None, None
        if metadata.get("model") != selected_model()["model"]:
            return None, None
        vectors = np.load(EMBEDDINGS_FILE, mmap_mode="r")
        if vectors.shape[0] != len(metadata.get("chunk_ids", [])):
            return None, None
        return vectors, metadata
    except Exception:
        logger.exception("Unable to load embedding cache")
        return None, None


def semantic_scores(query: str, allowed_chunk_ids: set[str] | None = None, limit: int = 40) -> list[dict[str, Any]]:
    vectors, metadata = _load_embedding_cache()
    if vectors is None or metadata is None:
        return []
    model = _load_model()
    query_vector = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]
    query_vector = np.asarray(query_vector, dtype=np.float32)
    scores = np.asarray(vectors @ query_vector, dtype=np.float32)
    chunk_ids = metadata["chunk_ids"]

    if allowed_chunk_ids is None:
        candidate_indexes = np.arange(len(chunk_ids))
    else:
        candidate_indexes = np.fromiter(
            (index for index, chunk_id in enumerate(chunk_ids) if chunk_id in allowed_chunk_ids),
            dtype=np.int64,
        )

    if candidate_indexes.size == 0:
        return []

    candidate_scores = scores[candidate_indexes]
    count = min(limit, candidate_indexes.size)

    if count == candidate_indexes.size:
        order = np.argsort(candidate_scores)[::-1]
    else:
        partial = np.argpartition(candidate_scores, -count)[-count:]
        order = partial[np.argsort(candidate_scores[partial])[::-1]]

    results = []
    for relative_index in order:
        absolute_index = int(candidate_indexes[relative_index])
        results.append({
            "chunk_id": chunk_ids[absolute_index],
            "semantic_score": float(scores[absolute_index]),
        })
    return results
