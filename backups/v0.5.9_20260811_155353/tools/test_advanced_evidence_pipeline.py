#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.evidence_ranker import rank_evidence


def row(chunk_id, score, text, *, path="rules.pdf", page=1, ordinal=0):
    return {
        "id": chunk_id,
        "evidence_score": score,
        "context_text": text,
        "text": text,
        "path": path,
        "display_name": path,
        "page": page,
        "ordinal": ordinal,
    }


question = "Can Mary get cybernetic implants?"
batches = [
    (question, [row("a", 0.8, "Cyberware costs Essence.", page=10), row("b", 0.7, "Generic gear.", page=2)]),
    ("cyberware essence", [row("a", 0.75, "Cyberware costs Essence.", page=10), row("c", 0.95, "Essence cannot fall below the stated minimum.", page=11)]),
]
ranked = rank_evidence(batches, original_question=question, limit=3)
assert ranked[0]["id"] == "a", "cross-query agreement should outrank a one-query hit"
assert ranked[0]["retrieval_hits"] == 2
assert ranked[0]["original_query_hit"] is True

# Near-identical focused contexts from one document should not crowd out a
# distinct rule when enough distinct evidence exists.
duplicate_text = " ".join(["same"] * 20 + ["cyberware", "essence", "minimum"])
batches = [
    (question, [
        row("d1", 0.9, duplicate_text, page=20, ordinal=1),
        row("d2", 0.89, duplicate_text + " extra", page=20, ordinal=2),
        row("unique", 0.5, "Awakened characters use the stated augmentation interaction rule.", path="magic.pdf", page=4),
    ])
]
ranked = rank_evidence(batches, original_question=question, limit=2)
assert {item["id"] for item in ranked} == {"d1", "unique"}

main = (ROOT / "app/main.py").read_text()
ask = (ROOT / "app/templates/ask.html").read_text()

assert "rank_evidence" in main
assert "audit_answer_claims" not in main
assert "revise_answer_from_audit" not in main
assert '"Ranking evidence"' in main
assert '"Generating final answer"' in main
assert '"Final answer received"' in main
assert '"Auditing mechanical claims"' not in main
assert '"Revising {len(findings)} flagged claim"' not in main
assert "Multi-step retrieval" in ask
assert "Multi-step + audit" not in ask

print("PASS: simplified Advanced evidence pipeline")
print("  deterministic cross-query evidence ranking: OK")
print("  near-duplicate pruning: OK")
print("  verifier/auditor/reviser calls removed: OK")
print("  Advanced uses planner + one final answer call: OK")
