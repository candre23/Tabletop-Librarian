from __future__ import annotations

import re
from collections import defaultdict

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'.+-]*")
CITATION_RE = re.compile(r"\[(\d{1,2})\]")

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "to", "of", "in", "on",
    "at", "by", "with", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "will", "would", "should", "could", "can", "may",
    "this", "that", "these", "those", "it", "its", "they", "their",
    "we", "you", "your", "our", "not", "no", "if", "then", "than",
}


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in TOKEN_RE.findall(text)
        if len(token) >= 2 and token.casefold() not in STOPWORDS
    }


def _clean_claim(text: str) -> str:
    text = CITATION_RE.sub(" ", text)
    text = re.sub(r"[*_`#>]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _answer_claims(answer: str) -> dict[int, list[str]]:
    claims: dict[int, list[str]] = defaultdict(list)

    for line in answer.replace("\r\n", "\n").split("\n"):
        numbers = [int(value) for value in CITATION_RE.findall(line)]
        if not numbers:
            continue

        claim = _clean_claim(line)
        if not claim:
            continue

        for number in numbers:
            claims[number].append(claim)

    return claims


def _candidate_passages(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    pieces = [
        re.sub(r"\s+", " ", piece).strip()
        for piece in re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z0-9*#-])", normalized)
    ]
    pieces = [piece for piece in pieces if len(piece) >= 20]

    candidates: list[str] = []
    for index, piece in enumerate(pieces):
        candidates.append(piece)

        if index + 1 < len(pieces):
            combined = f"{piece} {pieces[index + 1]}"
            if len(combined) <= 700:
                candidates.append(combined)

        if index + 2 < len(pieces):
            combined = f"{piece} {pieces[index + 1]} {pieces[index + 2]}"
            if len(combined) <= 700:
                candidates.append(combined)

    return candidates


def _score(claim: str, passage: str) -> float:
    claim_tokens = _tokens(claim)
    passage_tokens = _tokens(passage)

    if not claim_tokens or not passage_tokens:
        return 0.0

    overlap = claim_tokens & passage_tokens
    if not overlap:
        return 0.0

    claim_coverage = len(overlap) / len(claim_tokens)
    passage_coverage = len(overlap) / len(passage_tokens)
    score = (claim_coverage * 0.82) + (passage_coverage * 0.18)

    distinctive = [
        token for token in claim_tokens
        if len(token) >= 5 or any(char.isdigit() for char in token)
    ]
    if distinctive:
        matched = sum(1 for token in distinctive if token in passage_tokens)
        score += 0.25 * (matched / len(distinctive))

    return score


def attach_citation_excerpts(answer: str, sources: list[dict]) -> None:
    claims = _answer_claims(answer)

    for index, source in enumerate(sources, start=1):
        source_text = str(source.get("text", "")).strip()
        source["citation_excerpt"] = source_text[:520]

        cited_claims = claims.get(index, [])
        if not cited_claims or not source_text:
            continue

        candidates = _candidate_passages(source_text)
        if not candidates:
            continue

        best_passage = None
        best_score = 0.0

        for claim in cited_claims:
            for passage in candidates:
                score = _score(claim, passage)
                if score > best_score:
                    best_score = score
                    best_passage = passage

        if best_passage and best_score >= 0.20:
            source["citation_excerpt"] = best_passage[:700]
