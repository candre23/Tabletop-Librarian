#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.layout import load_character_layout
from app.characters.schema import load_character_schema
from app.system_packs import load_system_pack

pack = load_system_pack(ROOT / "data/system_packs/shadowrun_anarchy")
assert pack.valid and pack.manifest is not None

schema, schema_issues = load_character_schema(
    pack.root / pack.manifest.character_schema
)
assert schema is not None, [issue.format() for issue in schema_issues]

layout, layout_issues = load_character_layout(
    pack.root / pack.manifest.layouts["character"],
    schema=schema,
)
assert layout is not None, [issue.message for issue in layout_issues]

weapons = None
for tab in layout.tabs:
    for section in tab.sections:
        if section.id == "weapons":
            weapons = section
            break

assert weapons is not None
assert weapons.color == "plum"
assert weapons.body_color == "green"

template = (ROOT / "app/templates/characters/edit.html").read_text()
css = (ROOT / "app/static/css/main.css").read_text()

assert "ttl-section-body-color-{{ section.body_color }}" in template
assert ".ttl-section-body-color-green" in css
assert "body:not(.ttl-character-ui) .panel" in css
assert "body:not(.ttl-character-ui) .ttl-global-nav" in css
assert "body:not(.ttl-character-ui) table:not(.markdown-document table)" in css
assert "--ttl-app-bg:" in css
assert "--ttl-line:" in css

print("PASS: application visual normalization regression")
print("  Shadowrun Weapons title = plum: OK")
print("  Shadowrun Weapons body = green: OK")
print("  independent section body color support: OK")
print("  normalized non-character application chrome: OK")
print("  character UI remains independently scoped: OK")
