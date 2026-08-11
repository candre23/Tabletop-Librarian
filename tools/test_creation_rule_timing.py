#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.schema import load_character_schema
from app.creation import load_creation_workflow
from app.rules import load_rule_engine
from app.characters.web import _creation_applicable_rule_issues
from app.system_packs import load_system_pack

pack_root = ROOT / "data/system_packs"
pack = load_system_pack(pack_root / "shadowrun_anarchy")
assert pack.valid, [i.format() for i in pack.issues]

schema, schema_issues = load_character_schema(pack.root / pack.manifest.character_schema)
assert schema is not None, [i.format() for i in schema_issues]
workflow, workflow_issues = load_creation_workflow(
    pack.root / pack.manifest.creation,
    schema=schema,
)
assert workflow is not None, [i.format() for i in workflow_issues]

engine, engine_issues = load_rule_engine(
    pack.root / pack.manifest.rules,
    known_fields=set(schema.fields),
)
assert engine is not None, [i.format() for i in engine_issues]

data = schema.default_data()
data["metatype"] = "Ork"
data["strength"] = 1
_, all_issues = engine.apply(data)
assert any(i.rule_id == "ork_bonus" for i in all_issues)

# Step 3 (index 2): metatype has been selected, but Strength is a Step 5 input.
step3 = _creation_applicable_rule_issues(
    pack, schema, workflow, 2, all_issues
)
assert not any(i.rule_id == "ork_bonus" for i in step3)
assert not any(i.rule_id == "armor_track_matches_choice" for i in step3)

# Step 5 (index 4): Strength is now being assigned, so the rule becomes active.
step5 = _creation_applicable_rule_issues(
    pack, schema, workflow, 4, all_issues
)
assert any(i.rule_id == "ork_bonus" for i in step5)

# Human Edge belongs to the Shadow Amp/Edge step, not the initial theme step.
data = schema.default_data()
data["metatype"] = "Human"
data["edge"] = 1
_, human_issues = engine.apply(data)
assert any(i.rule_id == "human_edge_bonus" for i in human_issues)
step1 = _creation_applicable_rule_issues(
    pack, schema, workflow, 0, human_issues
)
assert not any(i.rule_id == "human_edge_bonus" for i in step1)
step7 = _creation_applicable_rule_issues(
    pack, schema, workflow, 6, human_issues
)
assert any(i.rule_id == "human_edge_bonus" for i in step7)

# At the final step, all validation rules are eligible to surface.
final_issues = _creation_applicable_rule_issues(
    pack, schema, workflow, len(workflow.steps) - 1, all_issues
)
assert {i.rule_id for i in final_issues} == {i.rule_id for i in all_issues}

print("PASS: creation rule timing regression test")
print("  future-step metatype bonuses hidden: OK")
print("  metatype bonus activates on attribute step: OK")
print("  future Edge warning hidden: OK")
print("  all rules active by final step: OK")
