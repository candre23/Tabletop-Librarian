from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.library.manager import list_folders, player_can_see_folder, scan_folder
from app.search.extract import load_cached_text

WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")


def _terms(query: str) -> list[str]:
    return [term.casefold() for term in WORD_RE.findall(query)]


def _make_snippet(text: str, query: str, terms: list[str], radius: int = 180) -> str:
    if not text:
        return ""

    folded = text.casefold()
    index = folded.find(query.casefold())

    if index < 0:
        positions = [folded.find(term) for term in terms]
        positions = [position for position in positions if position >= 0]
        index = min(positions) if positions else 0

    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)

    snippet = text[start:end].replace("\n", " ").strip()
    snippet = re.sub(r"\s+", " ", snippet)

    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"

    return snippet


def _page_score(text: str, query: str, terms: list[str]) -> int:
    folded = text.casefold()

    if not all(term in folded for term in terms):
        return 0

    score = 0
    phrase = query.strip().casefold()

    if phrase:
        score += folded.count(phrase) * 20

    for term in terms:
        score += folded.count(term) * 3

    positions = [folded.find(term) for term in terms]
    if positions and max(positions) - min(positions) <= 250:
        score += 10

    return score


def search_library(query: str, user_role: str, limit: int = 100) -> dict[str, Any]:
    terms = _terms(query)

    if not terms:
        return {
            "query": query,
            "results": [],
            "searched_documents": 0,
            "uncached_documents": 0,
        }

    results: list[dict[str, Any]] = []
    searched_documents = 0
    uncached_documents = 0

    for folder in list_folders():
        if user_role != "gm" and not player_can_see_folder(folder):
            continue

        scan = scan_folder(folder, generate_covers=False)

        for document in scan["documents"]:
            if user_role != "gm" and document.get("visibility") != "players":
                continue

            if document["type"] not in {"PDF", "Text", "Markdown"}:
                continue

            path = Path(document["path"])
            cached = load_cached_text(path)

            if cached is None:
                uncached_documents += 1
                continue

            searched_documents += 1

            for page in cached.get("pages", []):
                text = page.get("text", "")
                score = _page_score(text, query, terms)

                if score <= 0:
                    continue

                results.append(
                    {
                        "folder_name": folder["name"],
                        "doc_key": document["key"],
                        "display_name": document["display_name"],
                        "type": document["type"],
                        "page": page.get("page", 1),
                        "score": score,
                        "snippet": _make_snippet(text, query, terms),
                    }
                )

    results.sort(
        key=lambda item: (
            -item["score"],
            item["display_name"].casefold(),
            item["page"],
        )
    )

    return {
        "query": query,
        "results": results[:limit],
        "searched_documents": searched_documents,
        "uncached_documents": uncached_documents,
    }
