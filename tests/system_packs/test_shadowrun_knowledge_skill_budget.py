#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app.characters.schema import load_character_schema
from app.compendium import load_compendium
from app.rules import load_rule_engine, evaluate_limits
from app.system_packs import load_system_pack

pack=load_system_pack(ROOT/"data/system_packs/shadowrun_anarchy")
assert pack.valid and pack.manifest is not None

schema,schema_issues=load_character_schema(pack.root/pack.manifest.character_schema)
assert schema is not None, [i.format() for i in schema_issues]

compendium,comp_issues=load_compendium(pack.root,pack.manifest.compendium)
assert compendium is not None, [i.format() for i in comp_issues]

engine,rule_issues=load_rule_engine(
    pack.root/pack.manifest.rules,
    known_fields=set(schema.fields),
)
assert engine is not None, [i.format() for i in rule_issues]

data=schema.default_data()
data.update({
    "game_level":"Street Runner",
    "metatype":"Human",
    "armor_rating":"9",
})

# 3 Conjuring + 9 elsewhere = 12 spent.
data["skills"]=[
    {"skill":"conjuring","custom_name":"","rating":3,"specialization":"","knowledge":False},
    {"skill":"athletics","custom_name":"","rating":5,"specialization":"","knowledge":False},
    {"skill":"stealth","custom_name":"","rating":4,"specialization":"","knowledge":False},
]
results,issues=evaluate_limits(schema,compendium,data,engine)
skill_limit=next(r for r in results if r.id=="skill_points")
assert skill_limit.count==12, skill_limit.count

# Toggling Conjuring to Knowledge must NOT refund its rating.
data["skills"][0]["knowledge"]=True
results,issues=evaluate_limits(schema,compendium,data,engine)
skill_limit=next(r for r in results if r.id=="skill_points")
assert skill_limit.count==12, skill_limit.count

validation=engine.validate(data)
ids={issue.rule_id for issue in validation}
assert "knowledge_skill_unrated" in ids
assert "knowledge_skill_custom" in ids

# Proper free Knowledge Skill: custom, unrated, and contributes zero points.
data["skills"][0]["knowledge"]=False
data["skills"].append({
    "skill":"",
    "custom_name":"Seattle Gang Politics",
    "rating":0,
    "specialization":"",
    "knowledge":True,
})
results,issues=evaluate_limits(schema,compendium,data,engine)
skill_limit=next(r for r in results if r.id=="skill_points")
assert skill_limit.count==12, skill_limit.count

validation=engine.validate(data)
ids={issue.rule_id for issue in validation}
assert "knowledge_skill_unrated" not in ids
assert "knowledge_skill_custom" not in ids

# New collection row defaults to rating zero, suitable for Knowledge entry.
assert schema.fields["skills"].item_schema["rating"].default == 0

print("PASS: Shadowrun Knowledge Skill budget regression")
print("  rated Skill points always count: OK")
print("  Knowledge checkbox cannot refund rated Skill points: OK")
print("  listed Skill cannot satisfy free Knowledge Skill: OK")
print("  custom unrated Knowledge Skill costs zero: OK")
print("  new Skill row starts at rating 0: OK")
