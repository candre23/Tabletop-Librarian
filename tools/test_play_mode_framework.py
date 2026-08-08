#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.layout import load_character_layout
from app.characters.schema import load_character_schema, validate_character_data
from app.system_packs import load_system_pack

pack = load_system_pack(ROOT / "data/system_packs/ttl_test_minimal")
assert pack.valid and pack.manifest is not None, [i.format() for i in pack.issues]

schema, issues = load_character_schema(pack.root / pack.manifest.character_schema)
assert schema is not None, [i.format() for i in issues]

assert schema.fields["name"].play_editable is False
assert schema.fields["inventory"].play_editable is True
assert schema.fields["hit_points"].play_editable is True
assert schema.fields["hit_points"].type == "resource"
assert schema.fields["hit_points"].default == {"current": 10, "max": 10}
assert schema.fields["inventory"].raw["allow_custom"] is True

data = schema.default_data()
data["name"] = "Play Test"
data["inventory"] = [{
    "item": "",
    "custom_name": "Ancient Brass Key",
    "quantity": 1,
    "equipped": False,
    "notes": "Adventure-specific",
}]
issues = validate_character_data(schema, data)
assert not [i for i in issues if i.severity == "error"], [i.format() for i in issues]

layout, issues = load_character_layout(
    pack.root / pack.manifest.layouts["character"],
    schema=schema,
)
assert layout is not None
advancement = next(
    section
    for tab in layout.tabs
    for section in tab.sections
    if section.id == "advancement"
)
assert advancement.color == "teal"
assert advancement.span == 12
assert advancement.display_for("hit_points") == "resource"

template = (ROOT / "app/templates/characters/edit.html").read_text()
assert '?mode=configure' in template
assert 'name="mode" value="{{ mode }}"' in template
assert 'mode == "play" and not field.play_editable' in template
assert 'field.type == "resource"' in template
assert 'data-collection-add-custom' in template
assert 'mode == "configure"' in template

print("PASS: play-mode framework regression test")
print("  play-editable schema metadata: OK")
print("  current/max resource model: OK")
print("  custom collection entries: OK")
print("  semantic layout metadata: OK")
print("  Play/Configure template integration: OK")
