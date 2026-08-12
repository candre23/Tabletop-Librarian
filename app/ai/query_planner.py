from __future__ import annotations

import json
from typing import Any

from app.ai.provider import chat_completion


PLANNER_SYSTEM_PROMPT = """You are a retrieval planner for tabletop RPG rules.

Do not answer the user's rules question. Your only task is to generate a small
set of focused search queries that will help another system retrieve the rules
needed to answer it.

You receive:
- the user's original wording;
- the selected RPG system name;
- authoritative character-sheet context, when selected;
- a bounded vocabulary extracted from that System Pack.

Instructions:
- Preserve the original user question as a search query.
- Produce no more than 4 search queries total.
- Translate ordinary-language concepts into likely game terms when useful.
  Prefer terminology present in the supplied System Pack vocabulary.
- Consider relevant character interactions. Example pattern: if a character
  is magical and the question concerns augmentation, searching for interaction
  rules involving magic/Essence may be useful.
- Do not dump arbitrary character-sheet entries into the searches.
- Do not decide whether the character can or cannot do something.
- Do not invent a mechanical rule.
- followup_terms should contain at most 6 concise rule concepts that would be
  worth a second lookup only if the first-pass evidence actually mentions
  them.
- Return JSON only:
  {"queries":["..."],"followup_terms":["..."]}
"""


def _safe_json_object(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else {}
        except Exception:
            pass
    return {}


def _clean_terms(values, *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        value = " ".join(str(value or "").split()).strip()
        if not value:
            continue
        value = value[:180]
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def plan_retrieval_queries(
    *,
    question: str,
    character_context: dict[str, Any] | None,
    cancel_event=None,
) -> dict[str, Any]:
    question = " ".join(str(question or "").split()).strip()

    system_name = ""
    character_text = ""
    vocabulary: list[str] = []
    if character_context:
        system_name = str(character_context.get("system_name") or "").strip()
        character_text = str(character_context.get("text") or "").strip()
        vocabulary = _clean_terms(
            character_context.get("system_vocabulary") or [],
            limit=280,
        )

    user_prompt = (
        f"Original question:\n{question}\n\n"
        f"RPG system:\n{system_name or '(not specified)'}\n\n"
        "System Pack vocabulary:\n"
        + (
            ", ".join(vocabulary)
            if vocabulary
            else "(No System Pack vocabulary available.)"
        )
        + "\n\nSelected character context:\n"
        + (character_text if character_text else "(No character selected.)")
    )

    completion = chat_completion(
        [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        cancel_event=cancel_event,
    )

    parsed = _safe_json_object(completion.get("content", ""))

    # Original question is always query 1, regardless of planner output.
    queries = [question]
    seen = {question.casefold()}
    for value in _clean_terms(parsed.get("queries"), limit=4):
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        queries.append(value)
        if len(queries) >= 4:
            break

    return {
        "queries": queries,
        "followup_terms": _clean_terms(
            parsed.get("followup_terms"),
            limit=6,
        ),
        "model": completion.get("model", ""),
    }
