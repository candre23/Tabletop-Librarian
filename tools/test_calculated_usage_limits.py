#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.schema import load_character_schema
from app.compendium import load_compendium
from app.rules.engine import load_rule_engine
from app.rules.limits import evaluate_limits, validate_limit_schema

PACK = ROOT / "data/system_packs/shadowrun_anarchy"

schema, schema_issues = load_character_schema(PACK / "character.yaml")
assert schema is not None and not [i for i in schema_issues if i.severity == "error"], schema_issues
engine, rule_issues = load_rule_engine(PACK / "rules.yaml", known_fields=set(schema.fields))
assert engine is not None and not [i for i in rule_issues if i.severity == "error"], rule_issues
assert not validate_limit_schema(schema, engine)
compendium, comp_issues = load_compendium(PACK, [
    "compendium/skills.yaml", "compendium/qualities.yaml", "compendium/shadow_amps.yaml", "compendium/weapons.yaml"
])
assert not [i for i in comp_issues if i.severity == "error"], comp_issues

data = {field_id: field.default for field_id, field in schema.fields.items()}
data.update({
    "name": "Test Runner",
    "game_level": "Street Runner",
    "metatype": "Human",
    "strength": 4, "agility": 4, "willpower": 4, "logic": 3, "charisma": 2, "edge": 2,
    "skills": [
        {"skill":"athletics","custom_name":"","rating":2,"specialization":"","knowledge":False},
        {"skill":"firearms","custom_name":"","rating":3,"specialization":"Pistols","knowledge":False},
        {"skill":"stealth","custom_name":"","rating":2,"specialization":"","knowledge":False},
        {"skill":"intimidation","custom_name":"","rating":2,"specialization":"","knowledge":False},
        {"skill":"close_combat","custom_name":"","rating":2,"specialization":"","knowledge":False},
        {"skill":"","custom_name":"Seattle Gangs","rating":0,"specialization":"","knowledge":True},
    ],
    "armor": {"current": 9, "max": 9},
    "shadow_amps": [
        {"amp":"cyberware_base","custom_name":"Cyberarm","category":"Cyberware","amp_level":2,"amp_cost":2,"essence_cost":1,"description":"test"},
    ],
    "qualities": [
        {"quality":"guts","custom_name":"","polarity":"Positive","description":""},
        {"quality":"catlike","custom_name":"","polarity":"Positive","description":""},
        {"quality":"shifty","custom_name":"","polarity":"Negative","description":""},
    ],
    "weapons": [{"weapon":"ares_predator_v","custom_name":"","damage":"6P","close":"OK","near":"-2","far":"—","notes":""}],
    "gear": [{"name":"Fake SIN","notes":""}],
    "contacts": [{"name":"Fixer","role":"Fixer","notes":""}],
})
results, issues = evaluate_limits(schema, compendium, data, engine)
by_id = {r.id:r for r in results}
assert by_id["attribute_points"].count == 12
assert by_id["skill_points"].count == 12
assert by_id["rated_skill_slots"].count == 5
assert by_id["specialization_count"].count == 1
assert by_id["shadow_amp_points"].count == 2
assert by_id["positive_qualities"].count == 2
assert by_id["negative_qualities"].count == 1
assert not [i for i in issues if i.severity == "error"], issues

# Awakened cost is included automatically.
data["awakened"] = True
results, _ = evaluate_limits(schema, compendium, data, engine)
by_id = {r.id:r for r in results}
assert by_id["shadow_amp_points"].count == 4

print("PASS: calculated usage limits")
print("  numeric multi-field usage: OK")
print("  structured collection sums/counts: OK")
print("  resource maximum helper: OK")
print("  Shadowrun Phase 2 budget rules: OK")
