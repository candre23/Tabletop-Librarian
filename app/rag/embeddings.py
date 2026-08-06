from __future__ import annotations

import json
import logging
from threading import Lock
from typing import Any

import numpy as np

from app.config import CACHE_DIR, DATA_DIR
from app.rag.chunks import load_chunks

logger = logging.getLogger(__name__)

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_DIR = DATA_DIR / "models" / "embeddings" / "all-MiniLM-L6-v2-openvino"

RAG_CACHE_DIR = CACHE_DIR / "rag"
EMBEDDINGS_FILE = RAG_CACHE_DIR / "embeddings.npy"
EMBEDDING_META_FILE = RAG_CACHE_DIR / "embeddings.json"

EMBEDDING_VERSION = 1
BATCH_SIZE = 32

_model = None
_model_lock = Lock()


def _load_model():
    global _model

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        from sentence_transformers import SentenceTransformer

        if MODEL_DIR.exists() and any(MODEL_DIR.iterdir()):
            logger.info("Loading local OpenVINO embedding model: %s", MODEL_DIR)
            model = SentenceTransformer(
                str(MODEL_DIR),
                backend="openvino",
                device="cpu",
            )
        else:
            logger.info("Downloading/exporting OpenVINO embedding model: %s", MODEL_ID)
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            model = SentenceTransformer(
                MODEL_ID,
                backend="openvino",
                device="cpu",
            )
            model.save_pretrained(str(MODEL_DIR))
            logger.info("Saved local OpenVINO embedding model: %s", MODEL_DIR)

        _model = model
        return _model


def embedding_status() -> dict[str, Any]:
    result = {
        "model": MODEL_ID,
        "backend": "OpenVINO / CPU",
        "model_ready": MODEL_DIR.exists() and any(MODEL_DIR.iterdir()),
        "vectors": 0,
        "dimensions": 0,
        "cache_bytes": 0,
    }

    if not EMBEDDING_META_FILE.exists() or not EMBEDDINGS_FILE.exists():
        return result

    try:
        metadata = json.loads(EMBEDDING_META_FILE.read_text(encoding="utf-8"))
        result["vectors"] = len(metadata.get("chunk_ids", []))
        result["dimensions"] = int(metadata.get("dimensions", 0))
        result["cache_bytes"] = (
            EMBEDDINGS_FILE.stat().st_size
            + EMBEDDING_META_FILE.stat().st_size
        )
    except Exception:
        pass

    return result


def clear_embeddings() -> None:
    EMBEDDINGS_FILE.unlink(missing_ok=True)
    EMBEDDING_META_FILE.unlink(missing_ok=True)


def build_embeddings() -> dict[str, Any]:
    chunks = load_chunks()

    if not chunks:
        raise RuntimeError("Build the RAG corpus before creating embeddings.")

    texts = [chunk.get("text", "") for chunk in chunks]
    chunk_ids = [chunk["id"] for chunk in chunks]

    model = _load_model()

    logger.info("Embedding %s RAG chunks with OpenVINO", len(texts))

    vectors = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    vectors = np.asarray(vectors, dtype=np.float32)

    RAG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_FILE, vectors)

    metadata = {
        "embedding_version": EMBEDDING_VERSION,
        "model": MODEL_ID,
        "backend": "openvino",
        "dimensions": int(vectors.shape[1]),
        "chunk_ids": chunk_ids,
    }

    EMBEDDING_META_FILE.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "vectors": int(vectors.shape[0]),
        "dimensions": int(vectors.shape[1]),
        "cache_bytes": (
            EMBEDDINGS_FILE.stat().st_size
            + EMBEDDING_META_FILE.stat().st_size
        ),
    }


def _load_embedding_cache():
    if not EMBEDDINGS_FILE.exists() or not EMBEDDING_META_FILE.exists():
        return None, None

    try:
        metadata = json.loads(EMBEDDING_META_FILE.read_text(encoding="utf-8"))

        if metadata.get("embedding_version") != EMBEDDING_VERSION:
            return None, None

        vectors = np.load(EMBEDDINGS_FILE, mmap_mode="r")

        if vectors.shape[0] != len(metadata.get("chunk_ids", [])):
            return None, None

        return vectors, metadata
    except Exception:
        logger.exception("Unable to load embedding cache")
        return None, None


def semantic_scores(
    query: str,
    allowed_chunk_ids: set[str] | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
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
            (
                index
                for index, chunk_id in enumerate(chunk_ids)
                if chunk_id in allowed_chunk_ids
            ),
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
        results.append(
            {
                "chunk_id": chunk_ids[absolute_index],
                "semantic_score": float(scores[absolute_index]),
            }
        )

    return results
