#!/usr/bin/env python3
from pathlib import Path
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from app.characters.schema import load_character_schema
from app.creation import create_draft, load_draft, save_draft, load_creation_workflow
from app.rules import load_rule_engine, evaluate_limits
from app.compendium import load_compendium
from app.system_packs import load_system_pack

pack=load_system_pack(ROOT/"data/system_packs/shadowrun_anarchy")
assert pack.valid and pack.manifest is not None
schema,issues=load_character_schema(pack.root/pack.manifest.character_schema)
assert schema is not None, [i.format() for i in issues]
workflow,wissues=load_creation_workflow(pack.root/pack.manifest.creation,schema=schema)
assert workflow is not None, [i.format() for i in wissues]

assert workflow.steps[2].title=="Metatype"
assert not any(step.title[:1].isdigit() for step in workflow.steps)

template=(ROOT/"app/templates/characters/create.html").read_text()
assert "{{ loop.index }}. {{ workflow_step.title }}" in template
assert "{{ step_number }}. {{ step.title }}" in template
assert 'value="jump:{{ position }}"' in template
assert "position <= max_step_reached" in template

with tempfile.TemporaryDirectory() as td:
    draft=create_draft("tester","shadowrun_anarchy","0.2.6",schema.schema_version,
                       initial_data=schema.default_data(),draft_root=td)
    draft.current_step=8
    draft.max_step_reached=8
    save_draft(draft,draft_root=td)
    payload=json.loads(draft.path.read_text())
    payload.pop("max_step_reached",None)
    draft.path.write_text(json.dumps(payload,indent=2)+"\n")
    reopened=load_draft("tester",draft.draft_id,draft_root=td)
    assert reopened.current_step==8
    assert reopened.max_step_reached==8

engine,eissues=load_rule_engine(pack.root/pack.manifest.rules,known_fields=set(schema.fields))
assert engine is not None, [i.format() for i in eissues]
compendium,cissues=load_compendium(pack.root,pack.manifest.compendium)
assert compendium is not None, [i.format() for i in cissues]

data=schema.default_data()
data.update({"game_level":"Street Runner","metatype":"Human","armor_rating":"6"})
results,_=evaluate_limits(schema,compendium,data,engine)
assert next(r for r in results if r.id=="skill_points").maximum==14

data["metatype"]="Ork"
results,_=evaluate_limits(schema,compendium,data,engine)
assert next(r for r in results if r.id=="skill_points").maximum==13

data["metatype"]="Troll"
results,_=evaluate_limits(schema,compendium,data,engine)
assert next(r for r in results if r.id=="skill_points").maximum==12

assert "armor_track_matches_choice" not in {r.id for r in engine.validation}
assert "skill_points_after_armor" not in engine.limits
assert "armor" not in workflow.step("armor").fields

final=schema.default_data()
final.update({
    "metatype":"Ork",
    "armor_rating":"6",
    "strength":6,
    "willpower":4,
})
armor=engine.evaluate_expression(workflow.final_changes["armor"],final)
physical=engine.evaluate_expression(workflow.final_changes["physical_condition"],final)
stun=engine.evaluate_expression(workflow.final_changes["stun_condition"],final)
assert armor=={"current":6,"max":6}, armor
assert physical=={"current":11,"max":11}, physical
assert stun=={"current":10,"max":10}, stun

print("PASS: creation navigation + Shadowrun armor regression")
print("  single step numbering: OK")
print("  persistent completed-step navigation: OK")
print("  old draft compatibility: OK")
print("  Human Street Runner + Armor 6 = 14 Skill points: OK")
print("  Ork Street Runner + Armor 6 = 13 Skill points: OK")
print("  Armor Track setup warning removed: OK")
print("  Armor/Physical/Stun tracks initialize at Finish: OK")
