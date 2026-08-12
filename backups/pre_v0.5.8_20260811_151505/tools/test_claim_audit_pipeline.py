#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.answer_verifier import AUDITOR_SYSTEM_PROMPT, REVISION_SYSTEM_PROMPT, _safe_json_object

sample = _safe_json_object(
    'prefix {"findings":[{"claim":"Mary can spend 6 Essence","status":"numeric_error",'
    '"evidence":[1],"reason":"minimum is 0.5","required_change":"correct"}]} suffix'
)
assert sample["findings"][0]["status"] == "numeric_error"

main = (ROOT / "app/main.py").read_text()
ask = (ROOT / "app/templates/ask.html").read_text()

assert "audit_answer_claims" in main
assert "revise_answer_from_audit" in main
assert '"Auditing mechanical claims"' in main
assert '"Revising {len(findings)} flagged claim"' in main
assert '"Audit passed"' in main
assert "if findings:" in main

assert "Do NOT answer the user's original rules question" in AUDITOR_SYSTEM_PROMPT
assert "Do NOT rewrite the draft" in AUDITOR_SYSTEM_PROMPT
assert "unsupported|contradicted|numeric_error|source_role_error|speculative" in AUDITOR_SYSTEM_PROMPT
assert "allows an untrained/default method" in AUDITOR_SYSTEM_PROMPT
assert "explicit minimum/maximum" in AUDITOR_SYSTEM_PROMPT

assert "Change only what is necessary" in REVISION_SYSTEM_PROMPT
assert "Do not introduce a new mechanical claim" in REVISION_SYSTEM_PROMPT
assert "numeric boundary error" in REVISION_SYSTEM_PROMPT
assert "Multi-step + audit" in ask

print("PASS: claim audit + targeted revision pipeline")
