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
    (question, [
        row("specific", 0.88, "Cyberware costs Essence.", page=10),
        row("original2", 0.79, "Augmentations reduce Essence.", page=11),
        row("original3", 0.72, "Essence has a minimum threshold.", page=12),
        row("original4", 0.60, "Generic gear rule.", page=2),
    ]),
    ("awakened augmentation", [
        row("generic", 0.76, "Awakened characters have a Magic rating.", path="magic.pdf", page=4),
        row("specific", 0.73, "Cyberware costs Essence.", page=10),
    ]),
    ("magic essence", [
        row("generic", 0.75, "Awakened characters have a Magic rating.", path="magic.pdf", page=4),
    ]),
    ("bioware awakened", [
        row("generic", 0.74, "Awakened characters have a Magic rating.", path="magic.pdf", page=4),
    ]),
]
ranked = rank_evidence(batches, original_question=question, limit=4)
ids = [item["id"] for item in ranked]
assert ids[0] == "specific", "stronger passage relevance should beat generic recurrence"
assert {"specific", "original2", "original3"}.issubset(ids), (
    "three strong original-question results should survive planner-query competition"
)
assert next(item for item in ranked if item["id"] == "generic")["retrieval_hits"] == 3
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
assert "Apply explicit rules literally, including exceptions, defaults, and untrained rules." in main
assert "does not by itself forbid an action unless a supplied rule says it does" in main
assert "Do not invent restrictions, classifications, interactions, or rules" in main
assert "determine the answer using three internal steps" not in main
assert "For direct comparisons, prefer explicit comparable statistics" not in main
assert "Multi-step retrieval" in ask
assert "Multi-step + audit" not in ask

print("PASS: v0.5.9 Advanced evidence pipeline")
print("  passage relevance dominates cross-query recurrence: OK")
print("  original-question evidence reservation: OK")
print("  near-duplicate pruning: OK")
print("  compact final-answer prompt: OK")
print("  Advanced remains planner + one final answer call: OK")
