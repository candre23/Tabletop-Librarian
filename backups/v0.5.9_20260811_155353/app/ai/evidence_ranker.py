from __future__ import annotations

import re
from typing import Any

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")


def _context_text(row: dict[str, Any]) -> str:
    return str(row.get("context_text") or row.get("text") or "").strip()


def _token_set(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _WORD_RE.finditer(text)}


def _near_duplicate(a: dict[str, Any], b: dict[str, Any]) -> bool:
    # Focused contexts can overlap heavily when neighboring chunks from the same
    # page are retrieved. Keep one copy so the final model sees more distinct
    # rules instead of the same paragraph several times.
    if str(a.get("path") or "") != str(b.get("path") or ""):
        return False

    a_tokens = _token_set(_context_text(a))
    b_tokens = _token_set(_context_text(b))
    if not a_tokens or not b_tokens:
        return False

    overlap = len(a_tokens & b_tokens) / min(len(a_tokens), len(b_tokens))
    return overlap >= 0.82


def rank_evidence(
    retrieval_batches: list[tuple[str, list[dict[str, Any]]]],
    *,
    original_question: str,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Merge and deterministically rank evidence from multiple retrieval passes.

    ``evidence_score`` is useful inside a single retrieval query, but planner
    queries can have different score distributions. This ranker therefore adds
    query-independent signals: reciprocal rank, cross-query agreement, and a
    modest preference for passages also found by the user's original wording.
    """
    original_key = " ".join(str(original_question or "").split()).casefold()
    merged: dict[str, dict[str, Any]] = {}

    for query, rows in retrieval_batches:
        query_key = " ".join(str(query or "").split()).casefold()
        seen_in_batch: set[str] = set()
        for rank, row in enumerate(rows, start=1):
            chunk_id = str(row.get("id") or "")
            if not chunk_id or chunk_id in seen_in_batch:
                continue
            seen_in_batch.add(chunk_id)

            item = merged.get(chunk_id)
            if item is None:
                item = dict(row)
                item["retrieval_hits"] = 0
                item["retrieval_rr"] = 0.0
                item["original_query_hit"] = False
                item["best_retrieval_rank"] = rank
                item["best_evidence_score"] = float(row.get("evidence_score", 0.0))
                merged[chunk_id] = item
            elif float(row.get("evidence_score", 0.0)) > float(
                item.get("best_evidence_score", 0.0)
            ):
                # Keep the strongest focused context/metadata representation.
                preserved = {
                    "retrieval_hits": item["retrieval_hits"],
                    "retrieval_rr": item["retrieval_rr"],
                    "original_query_hit": item["original_query_hit"],
                    "best_retrieval_rank": item["best_retrieval_rank"],
                }
                item.update(row)
                item.update(preserved)
                item["best_evidence_score"] = float(row.get("evidence_score", 0.0))

            item["retrieval_hits"] += 1
            item["retrieval_rr"] += 1.0 / rank
            item["best_retrieval_rank"] = min(int(item["best_retrieval_rank"]), rank)
            if query_key == original_key:
                item["original_query_hit"] = True

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            -int(item.get("retrieval_hits", 0)),
            -float(item.get("retrieval_rr", 0.0)),
            -int(bool(item.get("original_query_hit"))),
            -float(item.get("best_evidence_score", item.get("evidence_score", 0.0))),
            int(item.get("best_retrieval_rank", 9999)),
            str(item.get("path") or ""),
            int(item.get("page") or 0),
            int(item.get("ordinal") or 0),
        ),
    )

    selected: list[dict[str, Any]] = []
    deferred_duplicates: list[dict[str, Any]] = []
    for item in ranked:
        if any(_near_duplicate(item, kept) for kept in selected):
            deferred_duplicates.append(item)
            continue
        selected.append(item)
        if len(selected) >= limit:
            break

    # If the scope contains fewer distinct passages than requested, duplicates
    # are better than throwing potentially useful evidence away entirely.
    if len(selected) < limit:
        for item in deferred_duplicates:
            selected.append(item)
            if len(selected) >= limit:
                break

    return selected
