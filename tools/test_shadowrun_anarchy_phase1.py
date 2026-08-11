#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.layout import load_character_layout
from app.characters.schema import load_character_schema
from app.rules import load_rule_engine
from app.system_packs import load_system_pack
from app.characters.storage import create_character, load_character, save_character
import tempfile

pack_root = ROOT / "data/system_packs/shadowrun_anarchy"
pack = load_system_pack(pack_root)
assert pack.valid, [issue.format() for issue in pack.issues]
assert pack.manifest is not None
assert pack.manifest.id == "shadowrun_anarchy"
assert pack.manifest.version == "0.1.0"
assert pack.manifest.creation is None

schema, schema_issues = load_character_schema(pack_root / "character.yaml")
assert schema is not None, [issue.format() for issue in schema_issues]

required = {
    "name", "tags", "strength", "agility", "willpower", "logic",
    "charisma", "edge", "skills", "shadow_amps", "qualities",
    "dispositions", "cues", "weapons", "armor", "physical_condition",
    "stun_condition", "matrix_condition", "gear", "contacts", "street_cred",
}
assert required.issubset(schema.fields)
assert schema.fields["armor"].play_editable is True
assert schema.fields["physical_condition"].play_editable is True
assert schema.fields["stun_condition"].play_editable is True
assert schema.fields["matrix_condition"].play_editable is True
assert schema.fields["plot_points"].play_editable is True

layout, layout_issues = load_character_layout(pack_root / "layout.yaml", schema=schema)
assert layout is not None, [issue.message for issue in layout_issues]
assert len(layout.tabs) == 1
sections = layout.tabs[0].sections
assert any(section.id == "skills" and section.span == 6 for section in sections)
assert any(section.id == "shadow_amps" and section.span == 6 for section in sections)
assert any(section.id == "weapons" and section.span == 12 for section in sections)

engine, engine_issues = load_rule_engine(pack_root / "rules.yaml", known_fields=set(schema.fields))
assert engine is not None, [issue.format() for issue in engine_issues]
values = engine.calculate(schema.default_data())
assert values["unarmed_damage"] == 1
assert values["physical_capacity"] == 9
assert values["stun_capacity"] == 9

sample = schema.default_data()
sample.update({"strength": 6, "willpower": 5})
values = engine.calculate(sample)
assert values["unarmed_damage"] == 3
assert values["physical_capacity"] == 11
assert values["stun_capacity"] == 11

with tempfile.TemporaryDirectory() as temp_dir:
    character_root = Path(temp_dir) / "characters"
    record = create_character(
        "phase1-test",
        "shadowrun_anarchy",
        initial_data={
            "name": "Phase One Runner",
            "strength": 6,
            "willpower": 5,
            "skills": [
                {
                    "name": "Firearms",
                    "rating": 4,
                    "specialization": "Pistols",
                    "knowledge": False,
                }
            ],
        },
        character_root=character_root,
        pack_root=ROOT / "data/system_packs",
    )
    reopened = load_character(
        "phase1-test",
        record.character_id,
        character_root=character_root,
        pack_root=ROOT / "data/system_packs",
    )
    assert reopened.data["name"] == "Phase One Runner"
    assert reopened.data["physical_capacity"] == 11
    assert reopened.data["stun_capacity"] == 11
    assert reopened.data["skills"][0]["name"] == "Firearms"

css = (ROOT / "app/static/css/main.css").read_text()
assert "container-type: inline-size" in css
assert "@container (max-width: 900px)" in css
assert "@container (max-width: 700px)" in css

print("PASS: Shadowrun Anarchy Phase 1 System Pack")
print("  pack/schema/layout validation: OK")
print("  official sheet field families represented: OK")
print("  Physical/Stun capacity formulas: OK")
print("  play-editable resources: OK")
print("  create/load persistence: OK")
print("  container-responsive sheet framework: OK")
