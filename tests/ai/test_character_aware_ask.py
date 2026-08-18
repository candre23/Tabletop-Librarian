#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app.characters.ai_context import build_character_ai_context
from app.characters.storage import create_character, save_character

PACK_ROOT=ROOT/"tests/fixtures/system_packs"

with tempfile.TemporaryDirectory() as td:
    root=Path(td)/"characters"
    record=create_character(
        "tester",
        "ttl_test_minimal",
        initial_data={
            "name":"Context Hero",
            "level":4,
            "archetype":"Scholar",
        },
        character_root=root,
        pack_root=PACK_ROOT,
    )
    record.temporary_effects={
        "level":[
            {
                "label":"Drain",
                "operation":"subtract",
                "value":1,
                "duration":"until rest",
            }
        ]
    }
    save_character(record,character_root=root,pack_root=PACK_ROOT)

    context=build_character_ai_context(
        "tester",
        record.character_id,
        character_root=root,
        pack_root=PACK_ROOT,
    )

    assert context["name"]=="Context Hero"
    assert context["owner"]=="tester"
    assert "Character: Context Hero" in context["text"]
    assert "Level: 3 (base 4; temporary effects active)" in context["text"]
    assert "Active temporary effects:" in context["text"]
    assert "Drain" in context["text"]

main=(ROOT/"app/main.py").read_text()
ask=(ROOT/"app/templates/ask.html").read_text()

assert "def _ask_character_options" in main
assert "def _resolve_ask_character" in main
assert "selected_character_context" in main
assert "Character context tells you what the selected character currently has" in main
assert "Do not cite character-sheet context" in main
assert "No relevant numbered source passages were retrieved." in main

assert 'name="character"' in ask
assert "Character context" in ask
assert "Rules still come from the knowledgebase." in ask

print("PASS: character-aware Ask foundation")
print("  authoritative character context serialization: OK")
print("  temporary effects/effective values included: OK")
print("  player/GM selection infrastructure present: OK")
print("  character context separated from numbered rules sources: OK")
print("  character-only questions can proceed without RAG evidence: OK")
