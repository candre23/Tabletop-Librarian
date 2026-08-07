from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

from app.library.manager import list_folders, player_can_see_folder, scan_folder
from app.rag.chunks import load_chunks
from app.rag.embeddings import semantic_scores

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

LEXICAL_WEIGHT = 0.48
SEMANTIC_WEIGHT = 0.52
RRF_K = 60

LEXICAL_STRENGTH_WEIGHT = 0.0045
QUERY_COVERAGE_WEIGHT = 0.0050
PHRASE_ANCHOR_WEIGHT = 0.0090
RARE_COVERAGE_WEIGHT = 0.0060
PASSAGE_WEIGHT = 0.0100
NEIGHBOR_RESCUE_PARENT_LIMIT = 40
NEIGHBOR_RESCUE_RADIUS = 2
NEIGHBOR_RESCUE_WEIGHT = 0.0120

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
    "by", "can", "could", "did", "do", "does", "for", "from", "had", "has",
    "have", "he", "her", "hers", "him", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "me", "my", "of", "on", "or", "our", "she",
    "should", "so", "some", "that", "the", "their", "them", "then", "there",
    "they", "this", "to", "was", "we", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "would", "you", "your",
}

QUERY_EXPANSIONS = {
    "skill": {"ability", "abilities"},
    "skills": {"ability", "abilities"},
    "try": {"attempt", "roll", "check"},
    "tries": {"attempt", "roll", "check"},
    "trying": {"attempt", "roll", "check"},
    "purchase": {"purchased", "buy", "bought", "rank"},
    "purchased": {"purchase", "buy", "bought", "rank"},
    "unpurchased": {"untrained", "unrestricted", "restricted", "rank"},
    "never": {"without", "zero", "none"},
    "hitpoint": {"hp", "hitpoints"},
    "hitpoints": {"hp", "hitpoint"},
    "tedious": {"slow", "long", "tough"},
    "dangerous": {"threat", "challenge", "combat"},
    "marching": {"position", "positioning", "order"},
}

EXACT_PHRASE_BONUS = 15.0
NGRAM_BONUS = 9.0
RARE_TERM_BONUS = 8.5
ALL_RARE_TERMS_BONUS = 12.0
COVERAGE_BONUS = 6.0


def _stem(token: str) -> str:
    if len(token) > 5 and token.endswith("ied"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        base = token[:-3]
        if len(base) >= 3:
            return base
    if len(token) > 4 and token.endswith("ed"):
        base = token[:-2]
        if base.endswith("s"):
            return base + "e"
        return base
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []

    for raw in TOKEN_RE.findall(text):
        token = raw.casefold()
        variants = {token, _stem(token)}

        compact = re.sub(r"['_-]+", "", token)
        if compact:
            variants.add(compact)
            variants.add(_stem(compact))

        if "-" in token or "_" in token:
            for part in re.split(r"[-_]+", token):
                if part:
                    variants.add(part)
                    variants.add(_stem(part))

        for variant in variants:
            if variant:
                tokens.append(variant)

    return tokens


def _query_tokens(text: str) -> list[str]:
    base = [token for token in _tokens(text) if token not in STOPWORDS]
    expanded = list(base)

    for token in base:
        for expansion in QUERY_EXPANSIONS.get(token, set()):
            expanded.extend(_tokens(expansion))

    return expanded or _tokens(text)


def _query_phrases(query: str) -> list[str]:
    words = [
        token.casefold()
        for token in TOKEN_RE.findall(query)
        if token.casefold() not in STOPWORDS
    ]

    phrases: list[str] = []

    for quoted in re.findall(r'["“](.+?)["”]', query):
        normalized = re.sub(r"\s+", " ", quoted.casefold()).strip()
        if normalized:
            phrases.append(normalized)

    for size in (4, 3, 2):
        for start in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[start:start + size]).strip()
            if phrase and phrase not in phrases:
                phrases.append(phrase)

    return phrases[:20]


def _passages(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_parts: list[str] = []

    for paragraph in re.split(r"\n\s*\n+|\n+", normalized):
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if not paragraph:
            continue

        if len(paragraph) <= 700:
            raw_parts.append(paragraph)
            continue

        raw_parts.extend(
            part.strip()
            for part in SENTENCE_SPLIT_RE.split(paragraph)
            if part.strip()
        )

    parts = [part for part in raw_parts if len(part) >= 25]
    windows: list[str] = []

    for i, part in enumerate(parts):
        windows.append(part)

        if i + 1 < len(parts):
            combined = f"{part} {parts[i + 1]}"
            if len(combined) <= 900:
                windows.append(combined)

        if i + 2 < len(parts):
            combined = f"{part} {parts[i + 1]} {parts[i + 2]}"
            if len(combined) <= 1100:
                windows.append(combined)

    return windows or ([normalized.strip()] if normalized.strip() else [])


def _passage_score(query: str, passage: str) -> float:
    query_tokens = set(_query_tokens(query))
    passage_tokens = set(_tokens(passage))

    if not query_tokens or not passage_tokens:
        return 0.0

    overlap = query_tokens & passage_tokens
    if not overlap:
        return 0.0

    query_coverage = len(overlap) / len(query_tokens)
    passage_coverage = len(overlap) / len(passage_tokens)

    score = (query_coverage * 0.82) + (passage_coverage * 0.18)

    folded = re.sub(r"\s+", " ", passage.casefold())
    for phrase in _query_phrases(query):
        if phrase in folded:
            score += min(0.35, 0.08 * len(phrase.split()))

    return score


def _best_passage_score(query: str, text: str) -> float:
    return max(
        (_passage_score(query, passage) for passage in _passages(text)),
        default=0.0,
    )


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
    selected_document_keys: list[str] | None = None,
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
    requested_document_keys = set(selected_document_keys or [])
    documents = []
    validated_selected_paths = []
    validated_selected_keys = []

    for path, item in visible.items():
        if selected_folder and item["folder_name"] != selected_folder:
            continue

        selected = (
            path in requested_documents
            or item["doc_key"] in requested_document_keys
        )
        if selected:
            validated_selected_paths.append(path)
            validated_selected_keys.append(item["doc_key"])

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
        "selected_document_keys": validated_selected_keys,
    }


def _lexical_features(
    query: str,
    eligible: list[dict],
) -> tuple[list[dict], dict[str, dict[str, float]]]:
    query_tokens = _query_tokens(query)

    if not query_tokens:
        return [], {}

    unique_query_tokens = list(dict.fromkeys(query_tokens))
    query_phrases = _query_phrases(query)
    document_frequency = Counter()
    tokenized = []

    for chunk in eligible:
        counts = Counter(_tokens(chunk.get("text", "")))
        tokenized.append((chunk, counts))

        for token in unique_query_tokens:
            if token in counts:
                document_frequency[token] += 1

    corpus_size = len(tokenized)
    rare_threshold = max(3, math.ceil(corpus_size * 0.01))
    rare_tokens = {
        token
        for token in unique_query_tokens
        if 0 < document_frequency.get(token, 0) <= rare_threshold
    }

    scored: list[dict] = []
    features: dict[str, dict[str, float]] = {}
    normalized_query = re.sub(r"\s+", " ", query.strip().casefold())

    for chunk, counts in tokenized:
        chunk_text = chunk.get("text", "")
        chunk_folded = re.sub(r"\s+", " ", chunk_text.casefold())

        score = 0.0
        matched_tokens = set()
        matched_rare = set()

        for token in unique_query_tokens:
            tf = counts.get(token, 0)
            if not tf:
                continue

            matched_tokens.add(token)
            df = document_frequency.get(token, 0)
            idf = math.log((corpus_size + 1) / (df + 1)) + 1.0
            score += (1.0 + math.log(tf)) * (idf ** 2)

            if token in rare_tokens:
                matched_rare.add(token)
                score += RARE_TERM_BONUS * idf

        coverage = (
            len(matched_tokens) / len(unique_query_tokens)
            if unique_query_tokens
            else 0.0
        )
        rare_coverage = (
            len(matched_rare) / len(rare_tokens)
            if rare_tokens
            else 0.0
        )

        phrase_hits = 0
        longest_phrase_words = 0

        for phrase in query_phrases:
            if phrase in chunk_folded:
                phrase_hits += 1
                longest_phrase_words = max(
                    longest_phrase_words,
                    len(phrase.split()),
                )

        if normalized_query and normalized_query in chunk_folded:
            score += EXACT_PHRASE_BONUS
            phrase_hits += 2
            longest_phrase_words = max(
                longest_phrase_words,
                len(normalized_query.split()),
            )

        if phrase_hits:
            score += NGRAM_BONUS * phrase_hits

        if matched_tokens:
            score += COVERAGE_BONUS * coverage

        if rare_tokens and matched_rare:
            if matched_rare == rare_tokens:
                score += ALL_RARE_TERMS_BONUS
            else:
                score += ALL_RARE_TERMS_BONUS * rare_coverage

        chunk_id = chunk["id"]
        features[chunk_id] = {
            "coverage": coverage,
            "rare_coverage": rare_coverage,
            "phrase_hits": float(phrase_hits),
            "longest_phrase_words": float(longest_phrase_words),
            "lexical_score": score,
        }

        if score > 0:
            scored.append(
                {
                    "chunk_id": chunk_id,
                    "lexical_score": score,
                }
            )

    scored.sort(key=lambda item: -item["lexical_score"])
    return scored, features


def _focused_context(
    query: str,
    primary: dict,
    by_path: dict[str, list[dict]],
) -> str:
    siblings = by_path.get(primary["path"], [])
    if not siblings:
        return primary.get("text", "")

    try:
        index = next(
            i for i, chunk in enumerate(siblings)
            if chunk["id"] == primary["id"]
        )
    except StopIteration:
        return primary.get("text", "")

    candidate_chunks = []
    start = max(0, index - 2)
    end = min(len(siblings), index + 3)

    for sibling_index in range(start, end):
        chunk = siblings[sibling_index]
        offset = sibling_index - index

        if offset == 0:
            label = "Primary retrieved passage"
        elif offset < 0:
            label = f"Previous adjacent passage {abs(offset)}"
        else:
            label = f"Next adjacent passage {offset}"

        candidate_chunks.append((label, chunk))

    candidates: list[tuple[float, str, int, str]] = []

    for label, chunk in candidate_chunks:
        page = int(chunk.get("page", 1))
        for passage in _passages(chunk.get("text", "")):
            candidates.append(
                (
                    _passage_score(query, passage),
                    label,
                    page,
                    passage,
                )
            )

    candidates.sort(key=lambda item: -item[0])

    selected = []
    seen = set()

    for score, label, page, passage in candidates:
        normalized = passage.casefold()
        if normalized in seen:
            continue

        seen.add(normalized)
        selected.append(
            f"[{label}, page {page}, relevance {score:.3f}]\n{passage}"
        )

        if len(selected) >= 4:
            break

    if not selected:
        return primary.get("text", "")

    return "\n\n".join(selected)[:2800]


RULE_LABEL_RE = re.compile(
    r"(?im)^\s*(?:"
    r"too\s+tough\s+rule|"
    r"too\s+weak\s+rule|"
    r"design\s+note|"
    r"gm(?:'s)?\s+note|"
    r"game\s+master(?:'s)?\s+note|"
    r"optional\s+rule|"
    r"special\s+rule|"
    r"important\s+rule|"
    r"rule"
    r")\s*[:.-]"
)


def _rule_label_score(query: str, text: str) -> float:
    matches = list(RULE_LABEL_RE.finditer(text or ""))
    if not matches:
        return 0.0

    passages = _passages(text)
    best = 0.0

    for passage in passages:
        if RULE_LABEL_RE.search(passage):
            best = max(best, _passage_score(query, passage))

    # A labeled rule is valuable even if wording differs from the question.
    return min(1.0, 0.35 + best)


def _revision_signal(text: str) -> bool:
    folded = re.sub(r"\s+", " ", text.casefold())
    patterns = (
        r"\bnow (?:is|are|uses?|calculated|determined|equals?|requires?)\b",
        r"\brevised\b",
        r"\bupdated\b",
        r"\bchanged\b",
        r"\breplaces?\b",
        r"\binstead\b",
        r"\bnew rule\b",
        r"\bno longer\b",
    )
    return any(re.search(pattern, folded) for pattern in patterns)


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

    lexical, lexical_features = _lexical_features(query, eligible)
    lexical = lexical[:100]
    semantic = semantic_scores(
        query,
        allowed_chunk_ids=allowed_ids,
        limit=100,
    )

    combined: dict[str, dict[str, Any]] = {}

    for rank, item in enumerate(lexical, start=1):
        chunk_id = item["chunk_id"]
        entry = combined.setdefault(
            chunk_id,
            {
                "hybrid_score": 0.0,
                "lexical_score": None,
                "semantic_score": None,
                "lexical_rank": None,
                "semantic_rank": None,
            },
        )
        entry["lexical_score"] = item["lexical_score"]
        entry["lexical_rank"] = rank
        entry["hybrid_score"] += LEXICAL_WEIGHT / (RRF_K + rank)

    for rank, item in enumerate(semantic, start=1):
        chunk_id = item["chunk_id"]
        entry = combined.setdefault(
            chunk_id,
            {
                "hybrid_score": 0.0,
                "lexical_score": None,
                "semantic_score": None,
                "lexical_rank": None,
                "semantic_rank": None,
            },
        )
        entry["semantic_score"] = item["semantic_score"]
        entry["semantic_rank"] = rank
        entry["hybrid_score"] += SEMANTIC_WEIGHT / (RRF_K + rank)

    max_lexical = max(
        (
            float(item["lexical_score"])
            for item in lexical
            if item.get("lexical_score") is not None
        ),
        default=0.0,
    )

    # Passage-level scoring is run only on candidates already discovered by
    # lexical or semantic retrieval, keeping the extra cost small.
    for chunk_id, entry in combined.items():
        feature = lexical_features.get(chunk_id, {})
        lexical_score = float(feature.get("lexical_score", 0.0))
        lexical_strength = (
            lexical_score / max_lexical
            if max_lexical > 0
            else 0.0
        )
        coverage = float(feature.get("coverage", 0.0))
        rare_coverage = float(feature.get("rare_coverage", 0.0))
        phrase_hits = float(feature.get("phrase_hits", 0.0))
        longest_phrase_words = float(
            feature.get("longest_phrase_words", 0.0)
        )

        phrase_anchor = 0.0
        if phrase_hits:
            phrase_anchor = min(
                1.0,
                0.35
                + (0.18 * phrase_hits)
                + (0.08 * max(0.0, longest_phrase_words - 1.0)),
            )

        chunk_text = chunk_map[chunk_id].get("text", "")
        passage_score = _best_passage_score(query, chunk_text)
        rule_label_score = _rule_label_score(query, chunk_text)

        entry["evidence_score"] = (
            entry["hybrid_score"]
            + (LEXICAL_STRENGTH_WEIGHT * lexical_strength)
            + (QUERY_COVERAGE_WEIGHT * coverage)
            + (PHRASE_ANCHOR_WEIGHT * phrase_anchor)
            + (RARE_COVERAGE_WEIGHT * rare_coverage)
            + (PASSAGE_WEIGHT * passage_score)
            + (0.0110 * rule_label_score)
        )
        entry["query_coverage"] = coverage
        entry["rare_coverage"] = rare_coverage
        entry["phrase_anchor"] = phrase_anchor
        entry["passage_score"] = passage_score

    ranked = sorted(
        combined.items(),
        key=lambda item: (
            -item[1]["evidence_score"],
            item[1]["semantic_rank"] or 9999,
            item[1]["lexical_rank"] or 9999,
        ),
    )

    # Second-stage rescue: a highly relevant passage can sit just outside a
    # chunk boundary. Inspect nearby chunks around the strongest first-stage
    # candidates, score those neighbors directly, and allow them into the
    # final competition even if they were not strong standalone hybrid hits.
    by_path_pre: dict[str, list[dict]] = defaultdict(list)
    chunk_positions: dict[str, tuple[str, int]] = {}

    for chunk in eligible:
        by_path_pre[chunk["path"]].append(chunk)

    for path_key in by_path_pre:
        by_path_pre[path_key].sort(
            key=lambda chunk: (
                int(chunk.get("page", 1)),
                int(chunk.get("ordinal", 0)),
            )
        )
        for position, chunk in enumerate(by_path_pre[path_key]):
            chunk_positions[chunk["id"]] = (path_key, position)

    rescue_scores: dict[str, float] = {}

    for parent_id, parent_scores in ranked[:NEIGHBOR_RESCUE_PARENT_LIMIT]:
        location = chunk_positions.get(parent_id)
        if not location:
            continue

        path_key, position = location
        siblings = by_path_pre[path_key]
        parent_evidence = float(parent_scores.get("evidence_score", 0.0))

        start = max(0, position - NEIGHBOR_RESCUE_RADIUS)
        end = min(len(siblings), position + NEIGHBOR_RESCUE_RADIUS + 1)

        for neighbor_position in range(start, end):
            neighbor = siblings[neighbor_position]
            neighbor_id = neighbor["id"]

            if neighbor_id == parent_id:
                continue

            neighbor_text = neighbor.get("text", "")
            passage_score = _best_passage_score(query, neighbor_text)
            rule_label_score = _rule_label_score(query, neighbor_text)

            if passage_score <= 0 and rule_label_score <= 0:
                continue

            distance = abs(neighbor_position - position)
            distance_factor = 1.0 if distance == 1 else 0.72
            rescue_score = (
                parent_evidence * 0.55 * distance_factor
                + NEIGHBOR_RESCUE_WEIGHT * passage_score
                + 0.0140 * rule_label_score
            )

            rescue_scores[neighbor_id] = max(
                rescue_scores.get(neighbor_id, 0.0),
                rescue_score,
            )

    for neighbor_id, rescue_score in rescue_scores.items():
        if neighbor_id in combined:
            combined[neighbor_id]["evidence_score"] = max(
                float(combined[neighbor_id]["evidence_score"]),
                rescue_score,
            )
            combined[neighbor_id]["neighbor_rescued"] = True
            continue

        feature = lexical_features.get(neighbor_id, {})
        combined[neighbor_id] = {
            "hybrid_score": 0.0,
            "lexical_score": feature.get("lexical_score"),
            "semantic_score": None,
            "lexical_rank": None,
            "semantic_rank": None,
            "query_coverage": float(feature.get("coverage", 0.0)),
            "rare_coverage": float(feature.get("rare_coverage", 0.0)),
            "phrase_anchor": 0.0,
            "passage_score": _best_passage_score(
                query,
                chunk_map[neighbor_id].get("text", ""),
            ),
            "evidence_score": rescue_score,
            "neighbor_rescued": True,
        }

    ranked = sorted(
        combined.items(),
        key=lambda item: (
            -item[1]["evidence_score"],
            item[1]["semantic_rank"] or 9999,
            item[1]["lexical_rank"] or 9999,
        ),
    )

    by_path: dict[str, list[dict]] = defaultdict(list)
    for chunk in eligible:
        by_path[chunk["path"]].append(chunk)

    for path in by_path:
        by_path[path].sort(
            key=lambda chunk: (
                int(chunk.get("page", 1)),
                int(chunk.get("ordinal", 0)),
            )
        )

    results = []

    for chunk_id, scores in ranked[:limit]:
        chunk = chunk_map.get(chunk_id)
        if not chunk:
            continue

        focused = _focused_context(query, chunk, by_path)

        results.append(
            {
                **chunk,
                **visible[chunk["path"]],
                **scores,
                "context_text": focused,
                "revision_candidate": _revision_signal(focused),
            }
        )

    return results
