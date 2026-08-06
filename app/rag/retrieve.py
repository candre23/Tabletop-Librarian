from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from app.library.manager import list_folders, player_can_see_folder, scan_folder
from app.rag.chunks import load_chunks
from app.rag.embeddings import semantic_scores

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")

LEXICAL_WEIGHT = 0.45
SEMANTIC_WEIGHT = 0.55
RRF_K = 60


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def _visible_documents(user_role: str) -> dict[str, dict[str, Any]]:
    visible: dict[str, dict[str, Any]] = {}

    for folder in list_folders():
        if user_role != "gm" and not player_can_see_folder(folder):
            continue

        scan = scan_folder(folder, generate_covers=False)

        for document in scan["documents"]:
            if user_role != "gm" and document.get("visibility") != "players":
                continue

            visible.setdefault(
                document["path"],
                {
                    "folder_name": folder["name"],
                    "doc_key": document["key"],
                    "display_name": document["display_name"],
                    "filename": document["filename"],
                    "type": document["type"],
                },
            )

    return visible


def available_rag_scope(
    user_role: str,
    selected_folder: str | None = None,
    selected_documents: list[str] | None = None,
) -> dict[str, Any]:
    visible = _visible_documents(user_role)
    folder_names = sorted(
        {item["folder_name"] for item in visible.values()},
        key=str.casefold,
    )

    selected_folder = (selected_folder or "").strip()
    if selected_folder and selected_folder not in folder_names:
        selected_folder = ""

    requested_documents = set(selected_documents or [])
    documents = []
    validated_selected_paths = []

    for path, item in visible.items():
        if selected_folder and item["folder_name"] != selected_folder:
            continue

        selected = path in requested_documents
        if selected:
            validated_selected_paths.append(path)

        documents.append(
            {
                "path": path,
                "folder_name": item["folder_name"],
                "doc_key": item["doc_key"],
                "display_name": item["display_name"],
                "filename": item["filename"],
                "type": item["type"],
                "selected": selected,
            }
        )

    documents.sort(
        key=lambda item: (
            item["folder_name"].casefold(),
            item["display_name"].casefold(),
        )
    )

    return {
        "folders": folder_names,
        "documents": documents,
        "selected_folder": selected_folder,
        "selected_document_paths": validated_selected_paths,
    }


def _lexical_ranking(query: str, eligible: list[dict], limit: int = 40) -> list[dict]:
    query_tokens = _tokens(query)

    if not query_tokens:
        return []

    document_frequency = Counter()
    tokenized = []

    for chunk in eligible:
        counts = Counter(_tokens(chunk.get("text", "")))
        tokenized.append((chunk, counts))

        for token in set(query_tokens):
            if token in counts:
                document_frequency[token] += 1

    corpus_size = len(tokenized)
    phrase = query.strip().casefold()
    scored = []

    for chunk, counts in tokenized:
        score = 0.0

        for token in query_tokens:
            tf = counts.get(token, 0)

            if not tf:
                continue

            df = document_frequency.get(token, 0)
            idf = math.log((corpus_size + 1) / (df + 1)) + 1.0
            score += (1.0 + math.log(tf)) * idf

        if phrase and phrase in chunk.get("text", "").casefold():
            score += 6.0

        if score > 0:
            scored.append(
                {
                    "chunk_id": chunk["id"],
                    "lexical_score": score,
                }
            )

    scored.sort(key=lambda item: -item["lexical_score"])
    return scored[:limit]


def retrieve_chunks(
    query: str,
    user_role: str,
    limit: int = 8,
    folder_scope: str | None = None,
    document_paths: list[str] | None = None,
) -> list[dict]:
    chunks = load_chunks()

    if not chunks:
        return []

    visible = _visible_documents(user_role)

    folder_scope = (folder_scope or "").strip()
    if folder_scope:
        visible = {
            path: item
            for path, item in visible.items()
            if item["folder_name"] == folder_scope
        }

    if document_paths:
        allowed_paths = set(document_paths)
        visible = {
            path: item
            for path, item in visible.items()
            if path in allowed_paths
        }

    eligible = [chunk for chunk in chunks if chunk.get("path") in visible]

    if not eligible:
        return []

    chunk_map = {chunk["id"]: chunk for chunk in eligible}
    allowed_ids = set(chunk_map)

    lexical = _lexical_ranking(query, eligible, limit=40)
    semantic = semantic_scores(query, allowed_chunk_ids=allowed_ids, limit=40)

    combined = {}

    for rank, item in enumerate(lexical, start=1):
        chunk_id = item["chunk_id"]
        entry = combined.setdefault(
            chunk_id,
            {
                "hybrid_score": 0.0,
                "lexical_score": None,
                "semantic_score": None,
            },
        )
        entry["lexical_score"] = item["lexical_score"]
        entry["hybrid_score"] += LEXICAL_WEIGHT / (RRF_K + rank)

    for rank, item in enumerate(semantic, start=1):
        chunk_id = item["chunk_id"]
        entry = combined.setdefault(
            chunk_id,
            {
                "hybrid_score": 0.0,
                "lexical_score": None,
                "semantic_score": None,
            },
        )
        entry["semantic_score"] = item["semantic_score"]
        entry["hybrid_score"] += SEMANTIC_WEIGHT / (RRF_K + rank)

    ranked = sorted(
        combined.items(),
        key=lambda item: -item[1]["hybrid_score"],
    )

    results = []

    for chunk_id, scores in ranked[:limit]:
        chunk = chunk_map.get(chunk_id)

        if not chunk:
            continue

        results.append(
            {
                **chunk,
                **visible[chunk["path"]],
                **scores,
            }
        )

    return results
