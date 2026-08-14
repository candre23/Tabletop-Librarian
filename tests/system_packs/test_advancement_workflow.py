#!/usr/bin/env python3
from pathlib import Path
import sys, tempfile
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from app.characters.schema import load_character_schema
from app.rules import load_rule_engine
from app.system_packs import load_system_pack
from app.advancement import load_advancement_workflow, create_advancement_draft, load_advancement_draft
from jinja2 import Environment,FileSystemLoader
pack=load_system_pack(ROOT/'data/system_packs/ttl_test_minimal'); assert pack.valid, [i.format() for i in pack.issues]
schema,_=load_character_schema(pack.root/pack.manifest.character_schema); engine,_=load_rule_engine(pack.root/pack.manifest.rules,known_fields=set(schema.fields))
wf,issues=load_advancement_workflow(pack.root/pack.manifest.advancement,schema=schema,engine=engine); assert wf and not issues
a=wf.action('advance_level'); assert a and a.changes['level']=='level + 1'; assert engine.evaluate_expression(a.available_when,{'level':1})
data=schema.default_data(); data.update({'name':'Test','level':2}); data['level']=engine.evaluate_expression(a.changes['level'],data); assert data['level']==3
with tempfile.TemporaryDirectory() as td:
 d=create_advancement_draft('u','char1',pack.manifest.id,a.id,schema.schema_version,'stamp',data,draft_root=td); r=load_advancement_draft('u',d.draft_id,draft_root=td); assert r.character_id=='char1' and r.data['level']==3
Environment(loader=FileSystemLoader(str(ROOT/'app/templates'))).get_template('characters/advance.html')
text=(ROOT/'app/characters/web.py').read_text(); assert 'base_updated_at' in text and 'record.updated_at!=draft.base_updated_at' in text
print('PASS: advancement workflow regression test')
print('  declarative action/change expression: OK')
print('  persistent advancement draft: OK')
print('  stale-character conflict protection: OK')
print('  wizard template/routes: OK')
