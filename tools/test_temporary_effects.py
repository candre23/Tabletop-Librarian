#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.storage import create_character, load_character, save_character
from app.characters.temporary_effects import effective_value, normalize_temporary_effects

assert effective_value(4, [{"operation":"multiply","value":2}]) == 8
assert effective_value(10, [
    {"operation":"add","value":2},
    {"operation":"subtract","value":1},
]) == 11
assert effective_value(5, [{"operation":"override","value":12}]) == 12

effects = normalize_temporary_effects({
    "power_score": [
        {
            "label": "Battle Focus",
            "operation": "add",
            "value": 3,
            "duration": "scene",
        }
    ]
})
assert effects["power_score"][0]["label"] == "Battle Focus"
assert effects["power_score"][0]["duration"] == "scene"

with tempfile.TemporaryDirectory() as temp_dir:
    root = Path(temp_dir) / "characters"
    pack_root = ROOT / "data/system_packs"

    record = create_character(
        "test-user",
        "ttl_test_minimal",
        initial_data={"name": "Temp Test"},
        character_root=root,
        pack_root=pack_root,
    )
    record.temporary_effects = effects
    save_character(record, character_root=root, pack_root=pack_root)

    reopened = load_character(
        "test-user",
        record.character_id,
        character_root=root,
        pack_root=pack_root,
    )
    assert reopened.temporary_effects["power_score"][0]["label"] == "Battle Focus"

template = (ROOT / "app/templates/characters/edit.html").read_text()
assert "data-temp-modifier-open" in template
assert "is-temporarily-modified" in template
assert "Temporary Modifier" in template
assert 'name="duration"' in template
assert 'value="multiply"' in template
assert 'value="override"' in template

web = (ROOT / "app/characters/web.py").read_text()
assert '@router.post("/characters/{character_id}/temporary-effects")' in web
assert "SUPPORTED_OPERATIONS" in web

print("PASS: temporary effects regression test")
print("  add/subtract/multiply/override: OK")
print("  separate character envelope persistence: OK")
print("  optional duration/reminder: OK")
print("  red effective-value UI: OK")
