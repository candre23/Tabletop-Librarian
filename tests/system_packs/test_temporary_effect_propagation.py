#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.schema import load_character_schema
from app.characters.temporary_effects import (
    build_effective_character_values,
    temporary_influence_map,
)
from app.compendium import load_compendium
from app.rules import load_rule_engine, resolve_compendium_modifiers
from app.system_packs import load_system_pack

pack = load_system_pack(ROOT / "data/system_packs/ttl_test_minimal")
assert pack.valid and pack.manifest is not None

schema, issues = load_character_schema(pack.root / pack.manifest.character_schema)
assert schema is not None, [i.format() for i in issues]

engine, issues = load_rule_engine(
    pack.root / pack.manifest.rules,
    known_fields=set(schema.fields),
)
assert engine is not None, [i.format() for i in issues]

compendium, issues = load_compendium(pack.root, pack.manifest.compendium)
assert compendium is not None, [i.format() for i in issues]

data = schema.default_data()
data.update({
    "name": "Propagation Test",
    "level": 4,
    "skills": ["acrobatics"],
})

# Permanent calculation at level 4 with Acrobatics (no modifier):
permanent_modifiers = resolve_compendium_modifiers(
    schema, compendium, data, engine
)
permanent = engine.calculate(data, modifiers=permanent_modifiers)
assert permanent["power_score"] == 8

# Curse temporarily reduces level by 2. Compendium effects and calculated
# fields must see the effective level 2, while permanent data remains level 4.
effects = {
    "level": [
        {
            "label": "Curse",
            "operation": "subtract",
            "value": 2,
            "duration": "one day",
        }
    ]
}

adjusted_inputs = build_effective_character_values(
    data=data,
    effects=effects,
    engine=None,
)
assert adjusted_inputs["level"] == 2
assert data["level"] == 4

effective_modifiers = resolve_compendium_modifiers(
    schema, compendium, adjusted_inputs, engine
)
effective = build_effective_character_values(
    data=data,
    effects=effects,
    engine=engine,
    modifiers=effective_modifiers,
)

assert effective["level"] == 2
assert effective["power_score"] == 4
assert data["level"] == 4
assert permanent["power_score"] == 8

influences = temporary_influence_map(effects=effects, engine=engine)
assert influences["level"] == ["level"]
assert "level" in influences["power_score"]

# Direct modifier to a calculated field must feed later calculated dependencies.
# The minimal pack has only one calculated field, so validate the transform API
# directly by temporarily altering power_score itself.
direct = {
    "power_score": [
        {"label": "Battle Focus", "operation": "add", "value": 3}
    ]
}
effective_direct = build_effective_character_values(
    data=data,
    effects=direct,
    engine=engine,
    modifiers=permanent_modifiers,
)
assert effective_direct["power_score"] == 11

template = (ROOT / "app/templates/characters/edit.html").read_text()
assert "temporary_effective_values" in template
assert "temporary_influences" in template
assert "Affected by temporary changes to:" in template

print("PASS: temporary-effect propagation regression test")
print("  base-field temporary effect feeds calculations: OK")
print("  permanent character data remains untouched: OK")
print("  calculated-field temporary modifier: OK")
print("  dependency influence warning: OK")
