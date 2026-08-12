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

    Passage relevance remains the dominant signal. Planner-query agreement is
    only a modest bonus, and several strong results from the user's original
    wording are guaranteed to survive into the final evidence set.
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
                item["original_query_rank"] = None
                item["original_query_evidence_score"] = None
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
                    "original_query_rank": item.get("original_query_rank"),
                    "original_query_evidence_score": item.get("original_query_evidence_score"),
                }
                item.update(row)
                item.update(preserved)
                item["best_evidence_score"] = float(row.get("evidence_score", 0.0))

            item["retrieval_hits"] += 1
            item["retrieval_rr"] += 1.0 / rank
            item["best_retrieval_rank"] = min(int(item["best_retrieval_rank"]), rank)
            if query_key == original_key:
                item["original_query_hit"] = True
                item["original_query_rank"] = rank
                item["original_query_evidence_score"] = float(
                    row.get("evidence_score", 0.0)
                )

    # Cross-query recurrence is intentionally a small bonus rather than the
    # primary sort key. A highly specific controlling passage should not lose
    # merely because several broader planner queries all found the same generic
    # discussion.
    for item in merged.values():
        base = float(item.get("best_evidence_score", item.get("evidence_score", 0.0)))
        repeat_bonus = 0.025 * min(max(int(item.get("retrieval_hits", 1)) - 1, 0), 3)
        rr_bonus = 0.0125 * min(float(item.get("retrieval_rr", 0.0)), 2.0)
        original_bonus = 0.025 if item.get("original_query_hit") else 0.0
        item["evidence_rank_score"] = base + repeat_bonus + rr_bonus + original_bonus

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            -float(item.get("evidence_rank_score", 0.0)),
            -float(item.get("best_evidence_score", item.get("evidence_score", 0.0))),
            -int(bool(item.get("original_query_hit"))),
            int(item.get("best_retrieval_rank", 9999)),
            str(item.get("path") or ""),
            int(item.get("page") or 0),
            int(item.get("ordinal") or 0),
        ),
    )

    selected: list[dict[str, Any]] = []
    deferred_duplicates: list[dict[str, Any]] = []

    def add_distinct(item: dict[str, Any]) -> bool:
        if any(_near_duplicate(item, kept) for kept in selected):
            deferred_duplicates.append(item)
            return False
        selected.append(item)
        return True

    # Preserve up to three of the strongest passages retrieved by the user's
    # original wording. These are selected by their score in that retrieval,
    # not by how often planner-generated searches happened to rediscover them.
    original_reserve = min(3, limit)
    original_candidates = sorted(
        (item for item in merged.values() if item.get("original_query_hit")),
        key=lambda item: (
            -float(item.get("original_query_evidence_score") or 0.0),
            int(item.get("original_query_rank") or 9999),
            str(item.get("path") or ""),
            int(item.get("page") or 0),
            int(item.get("ordinal") or 0),
        ),
    )
    for item in original_candidates:
        if len(selected) >= original_reserve:
            break
        add_distinct(item)

    for item in ranked:
        if len(selected) >= limit:
            break
        if any(str(item.get("id") or "") == str(kept.get("id") or "") for kept in selected):
            continue
        add_distinct(item)

    # If the scope contains fewer distinct passages than requested, duplicates
    # are better than throwing potentially useful evidence away entirely.
    if len(selected) < limit:
        for item in deferred_duplicates:
            if any(str(item.get("id") or "") == str(kept.get("id") or "") for kept in selected):
                continue
            selected.append(item)
            if len(selected) >= limit:
                break

    # Present passages to the model in relevance order even though some slots
    # were reserved for original-query evidence.
    selected.sort(
        key=lambda item: (
            -float(item.get("evidence_rank_score", 0.0)),
            -float(item.get("best_evidence_score", item.get("evidence_score", 0.0))),
            int(item.get("best_retrieval_rank", 9999)),
        )
    )
    return selected
