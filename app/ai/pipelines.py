from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.config import DATA_DIR, RESOURCE_ROOT
from app.ai.provider import chat_completion
from app.rag.retrieve import retrieve_chunks

BUILTIN_PIPELINE_DIR = RESOURCE_ROOT / "pipelines"
USER_PIPELINE_DIR = DATA_DIR / "pipelines"
PIPELINE_FORMAT_VERSION = 1
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")


class PipelinePresetError(RuntimeError):
    pass


@dataclass(frozen=True)
class PipelinePreset:
    preset_id: str
    name: str
    description: str
    path: Path
    data: dict[str, Any]


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_json_object(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else {}
        except Exception:
            pass
    return {}


def _clean_terms(values: Any, *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        value = _normalize(value)[:180]
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _context_text(row: dict[str, Any]) -> str:
    return str(row.get("context_text") or row.get("text") or "").strip()


def _token_set(text: str) -> set[str]:
    return {m.group(0).casefold() for m in _WORD_RE.finditer(str(text or ""))}


def _near_duplicate(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if str(a.get("path") or "") != str(b.get("path") or ""):
        return False
    a_tokens = _token_set(_context_text(a))
    b_tokens = _token_set(_context_text(b))
    if not a_tokens or not b_tokens:
        return False
    return len(a_tokens & b_tokens) / min(len(a_tokens), len(b_tokens)) >= 0.82


def _validate_preset(data: dict[str, Any], path: Path) -> PipelinePreset:
    if int(data.get("format_version", 0) or 0) != PIPELINE_FORMAT_VERSION:
        raise PipelinePresetError(
            f"Unsupported pipeline preset format in {path.name}; expected format_version {PIPELINE_FORMAT_VERSION}."
        )
    preset_id = _normalize(data.get("id"))
    name = _normalize(data.get("name"))
    description = _normalize(data.get("description"))
    if not preset_id or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", preset_id):
        raise PipelinePresetError(f"Invalid pipeline preset id in {path.name}.")
    if not name:
        raise PipelinePresetError(f"Pipeline preset {path.name} has no name.")
    stages = data.get("stages")
    if not isinstance(stages, list) or not stages:
        raise PipelinePresetError(f"Pipeline preset {path.name} has no stages.")
    allowed = {
        "planner", "retrieve", "rank", "select", "analysis", "decision",
        "rescue_if_unknown", "compose",
    }
    for stage in stages:
        if not isinstance(stage, dict) or _normalize(stage.get("type")) not in allowed:
            raise PipelinePresetError(f"Pipeline preset {path.name} contains an invalid stage.")
    prompts = data.get("prompts") or {}
    if not isinstance(prompts, dict):
        raise PipelinePresetError(f"Pipeline preset {path.name} prompts must be an object.")
    return PipelinePreset(preset_id, name, description, path, data)


def _load_file(path: Path) -> PipelinePreset:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PipelinePresetError(f"Could not read pipeline preset {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelinePresetError(f"Pipeline preset {path.name} must contain a JSON object.")
    return _validate_preset(data, path)


def list_pipeline_presets() -> list[PipelinePreset]:
    # User presets intentionally override a shipped preset with the same ID.
    by_id: dict[str, PipelinePreset] = {}
    for directory in (BUILTIN_PIPELINE_DIR, USER_PIPELINE_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                preset = _load_file(path)
            except PipelinePresetError:
                continue
            by_id[preset.preset_id] = preset
    return sorted(by_id.values(), key=lambda item: (item.name.casefold(), item.preset_id))


def pipeline_options_for_ui() -> list[dict[str, str]]:
    return [
        {"id": p.preset_id, "name": p.name, "description": p.description}
        for p in list_pipeline_presets()
    ]


def get_pipeline_preset(preset_id: str) -> PipelinePreset:
    preset_id = _normalize(preset_id)
    presets = list_pipeline_presets()
    if not presets:
        raise PipelinePresetError("No Advanced Ask pipeline presets are installed.")
    if preset_id:
        for preset in presets:
            if preset.preset_id == preset_id:
                return preset
        raise PipelinePresetError(f"Unknown Advanced Ask pipeline preset: {preset_id}")
    default = next((p for p in presets if bool(p.data.get("default"))), None)
    return default or presets[0]


def _sampling(preset: PipelinePreset, stage: str) -> dict[str, Any]:
    sampling = preset.data.get("sampling") or {}
    common = sampling.get("default") if isinstance(sampling, dict) else {}
    stage_settings = sampling.get(stage) if isinstance(sampling, dict) else {}
    result: dict[str, Any] = {}
    for source in (common, stage_settings):
        if not isinstance(source, dict):
            continue
        for key in ("temperature", "max_tokens", "model"):
            if key in source:
                result[key] = source[key]
    return result


def _call_model(preset: PipelinePreset, stage: str, messages: list[dict[str, str]], cancel_event=None) -> dict[str, Any]:
    kwargs = _sampling(preset, stage)
    return chat_completion(messages, cancel_event=cancel_event, **kwargs)


def _merge_candidates(retrieval_batches: list[tuple[str, list[dict[str, Any]]]], original_question: str) -> list[dict[str, Any]]:
    original_key = _normalize(original_question).casefold()
    merged: dict[str, dict[str, Any]] = {}
    for query, rows in retrieval_batches:
        qkey = _normalize(query).casefold()
        seen: set[str] = set()
        for rank, row in enumerate(rows, 1):
            cid = str(row.get("id") or "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            score = float(row.get("evidence_score", 0.0))
            item = merged.get(cid)
            if item is None:
                item = dict(row)
                item.update(
                    best_evidence_score=score,
                    retrieval_hits=0,
                    retrieval_rr=0.0,
                    original_query_hit=False,
                    best_retrieval_rank=rank,
                    original_query_rank=None,
                    original_query_evidence_score=None,
                )
                merged[cid] = item
            elif score > float(item.get("best_evidence_score", 0.0)):
                keep = {
                    key: item[key]
                    for key in (
                        "retrieval_hits", "retrieval_rr", "original_query_hit",
                        "best_retrieval_rank", "original_query_rank",
                        "original_query_evidence_score",
                    )
                }
                item.update(row)
                item.update(keep)
                item["best_evidence_score"] = score
            item["retrieval_hits"] += 1
            item["retrieval_rr"] += 1.0 / rank
            item["best_retrieval_rank"] = min(int(item["best_retrieval_rank"]), rank)
            if qkey == original_key:
                item["original_query_hit"] = True
                item["original_query_rank"] = rank
                item["original_query_evidence_score"] = score
    return list(merged.values())


def _content_terms(text: str, extra_stop: set[str] | None = None) -> set[str]:
    stop = {
        "shadowrun", "anarchy", "character", "characters", "rule", "rules", "using", "use",
        "does", "doesnt", "have", "has", "able", "even", "though", "when", "the", "and",
        "for", "with", "from", "this", "that", "what", "are", "is", "can", "her", "she",
        "his", "their", "into", "other",
    }
    if extra_stop:
        stop.update(extra_stop)
    return {t for t in _token_set(text) if len(t) >= 3 and t not in stop}


def _rank_query_aware(
    retrieval_batches: list[tuple[str, list[dict[str, Any]]]],
    question: str,
    *,
    character_stop_terms: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = _merge_candidates(retrieval_batches, question)
    query_terms = [_content_terms(q, character_stop_terms) for q, _ in retrieval_batches]
    for item in rows:
        text_terms = _content_terms(_context_text(item), character_stop_terms)
        max_cov = 0.0
        for terms in query_terms:
            if terms:
                max_cov = max(max_cov, len(text_terms & terms) / len(terms))
        base = float(item.get("best_evidence_score", 0.0))
        passage = float(item.get("passage_score", 0.0) or 0.0)
        item["pipeline_score"] = base + 0.030 * max_cov + 0.010 * passage
    return sorted(
        rows,
        key=lambda x: (
            -float(x.get("pipeline_score", 0.0)),
            -float(x.get("best_evidence_score", 0.0)),
            int(x.get("best_retrieval_rank", 9999)),
        ),
    )


def _build_candidate_prompt(question: str, ranked: list[dict[str, Any]], *, max_candidates: int) -> tuple[str, dict[str, dict[str, Any]]]:
    lines: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for item in ranked[:max_candidates]:
        cid = str(item.get("id") or "")
        if not cid:
            continue
        by_id[cid] = item
        text = _normalize(_context_text(item))
        if len(text) > 700:
            text = text[:700] + "..."
        lines.append(f"ID={cid} | page={item.get('page')} | {text}")
    return f"Question:\n{question}\n\nCandidate passages:\n" + "\n\n".join(lines), by_id


def _select_ids(parsed: dict[str, Any], by_id: dict[str, dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cid in _clean_terms(parsed.get("ids"), limit=limit):
        if cid in by_id and cid not in seen:
            selected.append(by_id[cid])
            seen.add(cid)
    return selected


def _guarded_select(
    preset: PipelinePreset,
    question: str,
    ranked: list[dict[str, Any]],
    batches: list[tuple[str, list[dict[str, Any]]]],
    *,
    cancel_event,
    limit: int,
    max_candidates: int,
) -> list[dict[str, Any]]:
    prompt, by_id = _build_candidate_prompt(question, ranked, max_candidates=max_candidates)
    completion = _call_model(
        preset,
        "selector",
        [
            {"role": "system", "content": str((preset.data.get("prompts") or {}).get("selector") or "")},
            {"role": "user", "content": prompt},
        ],
        cancel_event,
    )
    llm_selected = _select_ids(_safe_json_object(completion.get("content", "")), by_id, limit=limit)
    rank_position = {str(row.get("id") or ""): idx for idx, row in enumerate(ranked)}
    anchors: list[dict[str, Any]] = []
    ranked_by_id = {str(row.get("id") or ""): row for row in ranked if row.get("id")}

    for _query, batch in batches[:4]:
        available = [ranked_by_id[str(raw.get("id"))] for raw in batch if str(raw.get("id") or "") in ranked_by_id]
        available.sort(key=lambda row: rank_position.get(str(row.get("id") or ""), 999999))
        chosen = next((row for row in available if not any(_near_duplicate(row, kept) for kept in anchors)), None)
        if chosen is not None:
            anchors.append(chosen)
        if len(anchors) >= 4:
            break

    selected: list[dict[str, Any]] = []
    for item in anchors + llm_selected + ranked:
        cid = str(item.get("id") or "")
        if not cid or any(str(x.get("id") or "") == cid for x in selected):
            continue
        if any(_near_duplicate(item, kept) for kept in selected):
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _rescue_procedural_anchor(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    strong = (
        "if a player wishes to", "a player may", "a character may", "you can buy", "can buy",
        "may buy", "buy a new", "can add", "may add", "wishes to add", "add a shadow amp",
        "cannot", "may not", "must", "requires", "required", "provided", "unless",
        "cost would reduce", "essence cost",
    )
    medium = (
        "purchase", "purchasing", "acquire", "acquiring", "install", "prerequisite", "limit",
        "maximum", "minimum", "cost", "allowed", "permitted", "spend", "pay", "reduce",
    )
    best: dict[str, Any] | None = None
    best_key: tuple[Any, ...] | None = None
    for idx, item in enumerate(candidates):
        text = _normalize(_context_text(item)).casefold()
        s = sum(1 for phrase in strong if phrase in text)
        m = sum(1 for phrase in medium if phrase in text)
        if not s and not m:
            continue
        key = (s * 4 + m, s, m, float(item.get("pipeline_score", 0.0)), -idx)
        if best_key is None or key > best_key:
            best_key = key
            best = item
    return best


def _numbered_prompt(question: str, character_text: str, selected: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for i, source in enumerate(selected, 1):
        page_label = f", page {source.get('page')}" if source.get("page") else ""
        blocks.append(f"[{i}] {source.get('display_name')}{page_label}\n{_context_text(source)}")
    return (
        f"Question:\n{question}\n\n"
        f"Selected character context (current sheet state; not a numbered source):\n{character_text or '(none)'}\n\n"
        "Numbered source passages:\n\n" + ("\n\n".join(blocks) if blocks else "(none)")
    )


def _decision_token(raw: str) -> str:
    value = _normalize(raw).upper().replace(" ", "_")
    if value.startswith("YES"):
        return "YES"
    if value.startswith("NO"):
        return "NO"
    return "CANNOT_DETERMINE"


def _compose(decision: str, analysis: str) -> str:
    lead = "Yes." if decision == "YES" else "No." if decision == "NO" else "Cannot determine from the retrieved rules."
    body = str(analysis or "").strip()
    # The analysis prompt asks for no final conclusion, but small models sometimes add one.
    # Do not try to rewrite it; deterministic composition keeps the tested behavior intact.
    return f"{lead}\n\n{body}" if body else lead


def execute_advanced_pipeline(
    *,
    preset: PipelinePreset,
    question: str,
    role: str,
    character_context: dict[str, Any] | None,
    folder_scope: str | None,
    document_paths: list[str] | None,
    cancel_event,
    progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    data = preset.data
    prompts = data.get("prompts") or {}
    limits = data.get("limits") or {}
    progress_map = data.get("progress") or {}
    character_text = str((character_context or {}).get("text") or "")
    character_stop_terms = _token_set(str((character_context or {}).get("name") or ""))
    system_name = str((character_context or {}).get("system_name") or "").strip()
    vocabulary = _clean_terms((character_context or {}).get("system_vocabulary") or [], limit=280)

    def tick(name: str, default: int, label: str) -> None:
        if progress:
            value = progress_map.get(name, default)
            try:
                value = int(value)
            except Exception:
                value = default
            progress(max(1, min(98, value)), label)

    tick("planner", 20, "Planning searches")
    planner_user = (
        f"Original question:\n{_normalize(question)}\n\n"
        f"RPG system:\n{system_name or '(not specified)'}\n\n"
        "System Pack vocabulary:\n" + (", ".join(vocabulary) if vocabulary else "(none)") +
        "\n\nCharacter context is supplied only so exact game terms in the question can be recognized. "
        "Do not plan searches from unrelated sheet facts.\n" + character_text
    )
    planner_completion = _call_model(
        preset,
        "planner",
        [
            {"role": "system", "content": str(prompts.get("planner") or "")},
            {"role": "user", "content": planner_user},
        ],
        cancel_event,
    )
    parsed = _safe_json_object(planner_completion.get("content", ""))
    queries = [_normalize(question)]
    seen = {queries[0].casefold()}
    for value in _clean_terms(parsed.get("queries"), limit=int(limits.get("planner_queries", 4))):
        if value.casefold() not in seen:
            queries.append(value)
            seen.add(value.casefold())
        if len(queries) >= int(limits.get("planner_queries", 4)):
            break

    tick("retrieve", 38, "Retrieving rule passages")
    batches: list[tuple[str, list[dict[str, Any]]]] = []
    for query in queries:
        if cancel_event is not None and cancel_event.is_set():
            from app.ai.provider import AIRequestCancelled
            raise AIRequestCancelled("AI request cancelled.")
        rows = retrieve_chunks(
            query,
            role,
            limit=int(limits.get("retrieve_per_query", 6)),
            folder_scope=folder_scope,
            document_paths=document_paths,
        )
        batches.append((query, rows))

    tick("rank", 50, "Ranking evidence")
    ranker = str(data.get("ranker") or "query_aware")
    if ranker != "query_aware":
        raise PipelinePresetError(f"Preset {preset.preset_id} requests unsupported ranker: {ranker}")
    ranked = _rank_query_aware(batches, question, character_stop_terms=character_stop_terms)

    tick("select", 62, "Selecting controlling rules")
    selector = str(data.get("selector") or "guarded_llm")
    if selector != "guarded_llm":
        raise PipelinePresetError(f"Preset {preset.preset_id} requests unsupported selector: {selector}")
    selected = _guarded_select(
        preset,
        question,
        ranked,
        batches,
        cancel_event=cancel_event,
        limit=int(limits.get("evidence", 8)),
        max_candidates=int(limits.get("selector_candidates", 24)),
    )

    tick("analysis", 78, "Analyzing rules")
    analysis_completion = _call_model(
        preset,
        "analysis",
        [
            {"role": "system", "content": str(prompts.get("analysis") or "")},
            {"role": "user", "content": _numbered_prompt(question, character_text, selected)},
        ],
        cancel_event,
    )
    analysis = str(analysis_completion.get("content") or "").strip()

    tick("decision", 88, "Classifying answer")
    decision_completion = _call_model(
        preset,
        "decision",
        [
            {"role": "system", "content": str(prompts.get("decision") or "")},
            {"role": "user", "content": f"Question:\n{question}\n\nRule analysis:\n{analysis}"},
        ],
        cancel_event,
    )
    decision = _decision_token(str(decision_completion.get("content") or ""))

    if decision == "CANNOT_DETERMINE" and bool(data.get("rescue", {}).get("enabled", True)):
        tick("rescue_planner", 91, "Identifying missing rule")
        rescue_planner_completion = _call_model(
            preset,
            "rescue_planner",
            [
                {"role": "system", "content": str(prompts.get("rescue_planner") or "")},
                {"role": "user", "content": f"Question:\n{question}\n\nFirst rules analysis that lacked enough evidence:\n{analysis}"},
            ],
            cancel_event,
        )
        rescue_parsed = _safe_json_object(rescue_planner_completion.get("content", ""))
        rescue_queries = _clean_terms(rescue_parsed.get("queries"), limit=int(limits.get("rescue_queries", 2)))
        if not rescue_queries:
            rescue_queries = [f"governing rule or procedure for: {question}"]

        tick("rescue_retrieve", 93, "Retrieving missing rule")
        rescue_batches: list[tuple[str, list[dict[str, Any]]]] = []
        for query in rescue_queries:
            rows = retrieve_chunks(
                query,
                role,
                limit=int(limits.get("retrieve_per_query", 6)),
                folder_scope=folder_scope,
                document_paths=document_paths,
            )
            rescue_batches.append((query, rows))
        rescue_ranked = _rank_query_aware(rescue_batches, question, character_stop_terms=character_stop_terms)

        tick("rescue_select", 95, "Selecting rescue evidence")
        rescue_prompt, rescue_by_id = _build_candidate_prompt(
            question,
            rescue_ranked,
            max_candidates=int(limits.get("rescue_selector_candidates", 16)),
        )
        rescue_selector_completion = _call_model(
            preset,
            "rescue_selector",
            [
                {"role": "system", "content": str(prompts.get("rescue_selector") or "")},
                {"role": "user", "content": f"First analysis / stated evidence gap:\n{analysis}\n\n{rescue_prompt}"},
            ],
            cancel_event,
        )
        rescue_candidates = rescue_ranked[: int(limits.get("rescue_selector_candidates", 16))]
        rescue_selected: list[dict[str, Any]] = []
        anchor = _rescue_procedural_anchor(rescue_candidates)
        if anchor is not None:
            rescue_selected.append(anchor)
        for item in _select_ids(
            _safe_json_object(rescue_selector_completion.get("content", "")),
            rescue_by_id,
            limit=int(limits.get("rescue_evidence", 4)),
        ) + rescue_candidates:
            if len(rescue_selected) >= int(limits.get("rescue_evidence", 4)):
                break
            cid = str(item.get("id") or "")
            if not cid or any(str(x.get("id") or "") == cid for x in rescue_selected):
                continue
            if any(_near_duplicate(item, kept) for kept in rescue_selected):
                continue
            rescue_selected.append(item)

        merged: list[dict[str, Any]] = []
        for item in rescue_selected + selected:
            cid = str(item.get("id") or "")
            if not cid or any(str(x.get("id") or "") == cid for x in merged):
                continue
            if any(_near_duplicate(item, kept) for kept in merged):
                continue
            merged.append(item)
            if len(merged) >= int(limits.get("evidence", 8)):
                break
        selected = merged

        tick("rescue_analysis", 96, "Reanalyzing with rescued rule")
        analysis_completion = _call_model(
            preset,
            "analysis",
            [
                {"role": "system", "content": str(prompts.get("analysis") or "")},
                {"role": "user", "content": _numbered_prompt(question, character_text, selected)},
            ],
            cancel_event,
        )
        analysis = str(analysis_completion.get("content") or "").strip()
        decision_completion = _call_model(
            preset,
            "decision",
            [
                {"role": "system", "content": str(prompts.get("decision") or "")},
                {"role": "user", "content": f"Question:\n{question}\n\nRule analysis:\n{analysis}"},
            ],
            cancel_event,
        )
        decision = _decision_token(str(decision_completion.get("content") or ""))

    tick("compose", 98, "Assembling answer")
    answer = _compose(decision, analysis)
    model = str(analysis_completion.get("model") or decision_completion.get("model") or "")
    return {
        "answer": answer,
        "analysis": analysis,
        "decision": decision,
        "sources": selected,
        "model": model,
        "preset_id": preset.preset_id,
        "preset_name": preset.name,
    }
