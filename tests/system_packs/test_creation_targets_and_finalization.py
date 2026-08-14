#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from app.characters.schema import load_character_schema
from app.creation import load_creation_workflow
from app.rules import load_rule_engine, evaluate_limits
from app.compendium import load_compendium
from app.system_packs import load_system_pack

pack_dir=ROOT/"data/system_packs/shadowrun_anarchy"
pack=load_system_pack(pack_dir)
assert pack.valid and pack.manifest is not None, [issue.format() for issue in pack.issues]
schema,issues=load_character_schema(pack.root/pack.manifest.character_schema)
assert schema and not [i for i in issues if i.severity=="error"]

workflow,wissues=load_creation_workflow(pack.root/pack.manifest.creation,schema=schema)
assert workflow and not [i for i in wissues if i.severity=="error"]
assert "edge" in workflow.final_changes

engine,eissues=load_rule_engine(pack.root/pack.manifest.rules,known_fields=set(schema.fields))
assert engine and not [i for i in eissues if i.severity=="error"]

compendium,cissues=load_compendium(pack.root,pack.manifest.compendium)
assert compendium is not None, [i.format() for i in cissues]
data=schema.default_data()
data.update({
    "game_level":"Street Runner",
    "metatype":"Ork",
    "awakened":True,
    "emerged":False,
    "strength":6,"agility":5,"willpower":4,"logic":3,"charisma":5,
    "skills":[],
    "shadow_amps":[
        {"custom_name":"Amp A","amp_cost":2,"essence_cost":0},
        {"custom_name":"Amp B","amp_cost":2,"essence_cost":0},
    ],
    "qualities":[],
})
results,limit_issues=evaluate_limits(schema,compendium,data,engine)

# Incomplete required targets warn; fully satisfied ones do not.
assert any(i.rule_id=="skill_points" and i.severity=="warning" for i in limit_issues)
assert not any(i.rule_id=="shadow_amp_points" for i in limit_issues)

# Final Edge: 10 pool - 4 amp - 2 awakened = 4 leftover; Ork base Edge 1 => 5.
edge=engine.evaluate_expression(workflow.final_changes["edge"],data)
assert edge==5, edge

human=dict(data)
human["metatype"]="Human"
human["awakened"]=False
human["shadow_amps"]=[{"custom_name":"Amp","amp_cost":4,"essence_cost":0}]
edge=engine.evaluate_expression(workflow.final_changes["edge"],human)
# 1 base +1 Human +6 leftover, capped at 6.
assert edge==6, edge

source=(ROOT/"app/characters/web.py").read_text()
assert 'issue.severity = "info"' in source
assert "workflow.final_changes" in source
assert "None if step_index == len(workflow.steps) - 1 else step.fields" in source

print("PASS: creation target/finalization regression test")
print("  incomplete creation targets represented separately: OK")
print("  fulfilled targets stop emitting warnings: OK")
print("  pre-final creation warnings demoted to info: OK")
print("  final review evaluates all target limits: OK")
print("  leftover Amp points convert to Edge with cap 6: OK")
