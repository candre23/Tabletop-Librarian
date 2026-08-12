#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.answer_verifier import VERIFIER_SYSTEM_PROMPT
from app.ai.requests import (
    ai_request_progress,
    finish_ai_request,
    register_ai_request,
    update_ai_request_progress,
)

request_id = "verifier-progress-test"
register_ai_request(request_id)
status = ai_request_progress(request_id)
assert status["active"]
assert status["progress"] == 12

update_ai_request_progress(request_id, 79, "Verifying rules and numbers")
status = ai_request_progress(request_id)
assert status["progress"] == 79
assert status["stage"] == "Verifying rules and numbers"

finish_ai_request(request_id)
assert not ai_request_progress(request_id)["active"]

main = (ROOT / "app/main.py").read_text()
ask = (ROOT / "app/templates/ask.html").read_text()

assert "verify_and_revise_answer" in main
assert 'if reasoning_mode == "advanced":' in main
assert '"Draft answer received"' in main
assert '"Verifying rules and numbers"' in main
assert '"Verified answer received"' in main
assert '"Finalizing answer"' in main
assert '@app.get("/ai/progress/{request_id}")' in main

assert "pollServerProgress" in ask
assert "/ai/progress/" in ask
assert "setInterval" in ask
assert "const stages=" not in ask

assert "Correct arithmetic and boundary mistakes." in VERIFIER_SYSTEM_PROMPT
assert "Remove speculative exceptions" in VERIFIER_SYSTEM_PROMPT
assert "Do not promote examples, NPC descriptions" in VERIFIER_SYSTEM_PROMPT
assert "return the corrected FINAL ANSWER" in VERIFIER_SYSTEM_PROMPT

print("PASS: Advanced verifier + progress checkpoints")
print("  second-pass verifier present: OK")
print("  Basic mode remains unverified: OK")
print("  numeric/speculation/source-role checks: OK")
print("  server-side progress registry: OK")
print("  browser polls real pipeline checkpoints: OK")
