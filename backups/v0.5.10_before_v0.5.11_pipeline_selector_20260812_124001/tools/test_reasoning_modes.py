#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.pipelines import get_pipeline_preset, pipeline_options_for_ui
from app.characters.ai_context import build_character_ai_context
from app.characters.storage import create_character

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

options = pipeline_options_for_ui()
assert any(item["id"] == "qwen3.5-9b-v10" for item in options)
assert get_pipeline_preset("").preset_id == "qwen3.5-9b-v10"

main = (ROOT / "app/main.py").read_text()
ask = (ROOT / "app/templates/ask.html").read_text()

assert 'reasoning_mode: str = "basic"' in main
assert 'if reasoning_mode == "advanced":' in main
assert "execute_advanced_pipeline" in main
assert "Basic single-query retrieval" in main
assert 'name="reasoning_mode"' in ask
assert 'value="basic"' in ask
assert 'value="advanced"' in ask
assert "Single retrieval" in ask
assert "Multi-step retrieval" in ask
assert 'name="pipeline_preset"' in ask

print("PASS: selectable Basic / Advanced reasoning")
print("  Basic remains default and single-query: OK")
print("  Advanced is preset-driven: OK")
print("  System Pack vocabulary includes cyberware/bioware/Essence: OK")
print("  Advanced preset selector is present: OK")
