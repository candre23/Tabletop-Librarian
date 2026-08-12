#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.query_planner import _safe_json_object
from app.characters.ai_context import build_character_ai_context
from app.characters.storage import create_character

assert _safe_json_object('{"queries":["a"],"followup_terms":["b"]}')["queries"] == ["a"]
assert _safe_json_object('prefix {"queries":["x"],"followup_terms":[]} suffix')["queries"] == ["x"]
assert _safe_json_object("bad") == {}

# Real Shadowrun context should expose system vocabulary that can bridge
# ordinary-language phrasing to game terminology.
with tempfile.TemporaryDirectory() as td:
    char_root = Path(td) / "characters"
    record = create_character(
        "tester",
        "shadowrun_anarchy",
        initial_data={
            "name": "Planner Test",
            "game_level": "Street Runner",
            "metatype": "Human",
            "awakened": True,
            "essence": 6.0,
        },
        character_root=char_root,
        pack_root=ROOT / "data/system_packs",
    )
    context = build_character_ai_context(
        "tester",
        record.character_id,
        character_root=char_root,
        pack_root=ROOT / "data/system_packs",
    )
    vocab = " ".join(context["system_vocabulary"]).casefold()
    assert "cyberware" in vocab
    assert "bioware" in vocab
    assert "essence" in vocab
    assert "awakened" in vocab

main = (ROOT / "app/main.py").read_text()
ask = (ROOT / "app/templates/ask.html").read_text()
planner = (ROOT / "app/ai/query_planner.py").read_text()

assert 'reasoning_mode: str = "basic"' in main
assert 'if reasoning_mode == "advanced":' in main
assert "plan_retrieval_queries" in main
assert "planned_queries" in main
assert "candidates_by_id" in main
assert "eligible_followups" in main
assert "in evidence_text" in main
assert "[:12]" in main
assert "Basic single-query retrieval" in main

assert 'name="reasoning_mode"' in ask
assert 'value="basic"' in ask
assert 'value="advanced"' in ask
assert "Single retrieval" in ask
assert "Multi-step retrieval" in ask

assert "Do not answer the user's rules question." in planner
assert "Produce no more than 4 search queries total." in planner
assert "Original question is always query 1" in planner

print("PASS: selectable Basic / Advanced reasoning")
print("  Basic remains default: OK")
print("  Advanced planner is retrieval-only: OK")
print("  System Pack vocabulary includes cyberware/bioware/Essence: OK")
print("  multi-query retrieval is bounded: OK")
print("  follow-up retrieval is evidence-gated and one-hop: OK")
