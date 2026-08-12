from __future__ import annotations

import json
from typing import Any

from app.ai.provider import chat_completion

AUDITOR_SYSTEM_PROMPT = """You are the claim auditor for Tabletop Librarian.

You receive the user's original question, authoritative character-sheet
context, numbered source passages, and a draft answer from another model call.

Do NOT answer the user's original rules question. Do NOT rewrite the draft.
Audit only mechanical claims in the draft: permissions, prohibitions,
prerequisites, exceptions, numeric values/ranges/boundaries, formulas,
skill/category relationships, and causal consequences.

A claim is problematic when it is unsupported, contradicted, numerically
inconsistent, based on an example/NPC/adventure/conversion passage as though
it were a controlling rule, or speculative beyond the supplied evidence.

Important:
- Character-sheet context establishes character state only.
- Do not treat absence from the sheet as proof of prohibition unless a rule
  explicitly requires the missing feature.
- If a passage explicitly allows an untrained/default method, a claim that the
  named skill is mandatory is contradicted.
- If an explicit minimum/maximum is provided, audit arithmetic against that
  boundary.
- Do not flag style or harmless wording differences.
- Do not invent a replacement rule.

Return JSON only:
{
  "findings": [
    {
      "claim": "problematic claim",
      "status": "unsupported|contradicted|numeric_error|source_role_error|speculative",
      "evidence": [1, 2],
      "reason": "brief evidence-grounded explanation",
      "required_change": "remove|qualify|correct"
    }
  ]
}
If there is no material mechanical problem, return {"findings":[]}.
"""

REVISION_SYSTEM_PROMPT = """You are the targeted answer reviser for Tabletop Librarian.

You receive the original question, authoritative character context, numbered
source passages, the original draft answer, and a structured claim audit.

Return the FINAL ANSWER.

Rules:
- Preserve the draft's correct content and concise style.
- Change only what is necessary to resolve the auditor's findings.
- Do not introduce a new mechanical claim unless directly supported by the
  supplied numbered passages.
- If a finding says a claim is contradicted, replace it only with what the
  cited evidence supports.
- If a finding identifies a numeric boundary error, recompute from the
  explicit boundary in the evidence.
- If a finding says a claim is unsupported or speculative, remove or qualify it.
- Character-sheet facts are authoritative state but do not receive numbered citations.
- Cite material rules claims using [1], [2], etc.
- Lead with the direct answer and mention only relevant character facts.
- Do not mention the audit, verifier, draft, or revision process.
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
            value = json.loads(text[start:end + 1])
            return value if isinstance(value, dict) else {}
        except Exception:
            pass
    return {}

def audit_answer_claims(*, question: str, draft_answer: str, character_block: str, source_text: str, cancel_event=None) -> dict[str, Any]:
    user_prompt = (
        f"Question:\n{question}\n\n"
        f"{character_block}\n\n"
        f"Numbered source passages:\n\n{source_text}\n\n"
        f"Draft answer to audit:\n\n{draft_answer}"
    )
    completion = chat_completion(
        [
            {"role": "system", "content": AUDITOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        cancel_event=cancel_event,
    )
    parsed = _safe_json_object(completion.get("content", ""))
    findings = parsed.get("findings")
    if not isinstance(findings, list):
        findings = []

    allowed_status = {"unsupported", "contradicted", "numeric_error", "source_role_error", "speculative"}
    allowed_change = {"remove", "qualify", "correct"}
    cleaned = []

    for finding in findings[:12]:
        if not isinstance(finding, dict):
            continue
        claim = " ".join(str(finding.get("claim") or "").split()).strip()
        status = str(finding.get("status") or "").strip()
        reason = " ".join(str(finding.get("reason") or "").split()).strip()
        required_change = str(finding.get("required_change") or "").strip()
        if not claim or status not in allowed_status or not reason:
            continue

        evidence = []
        for item in finding.get("evidence") or []:
            try:
                number = int(item)
            except (TypeError, ValueError):
                continue
            if number > 0 and number not in evidence:
                evidence.append(number)

        cleaned.append({
            "claim": claim,
            "status": status,
            "evidence": evidence[:6],
            "reason": reason[:600],
            "required_change": required_change if required_change in allowed_change else "correct",
        })

    return {"findings": cleaned, "model": completion.get("model", "")}

def revise_answer_from_audit(*, question: str, draft_answer: str, audit: dict[str, Any], character_block: str, source_text: str, cancel_event=None) -> dict[str, Any]:
    findings = audit.get("findings") if isinstance(audit, dict) else []
    if not findings:
        return {"content": draft_answer, "model": "", "revised": False}

    user_prompt = (
        f"Question:\n{question}\n\n"
        f"{character_block}\n\n"
        f"Numbered source passages:\n\n{source_text}\n\n"
        f"Original draft:\n\n{draft_answer}\n\n"
        f"Claim audit:\n{json.dumps({'findings': findings}, ensure_ascii=False, indent=2)}"
    )
    completion = chat_completion(
        [
            {"role": "system", "content": REVISION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        cancel_event=cancel_event,
    )
    content = str(completion.get("content") or "").strip()
    return {
        "content": content or draft_answer,
        "model": completion.get("model", ""),
        "revised": bool(content),
    }
