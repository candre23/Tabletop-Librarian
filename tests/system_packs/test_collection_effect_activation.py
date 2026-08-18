#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.characters.schema import load_character_schema
from app.compendium import load_compendium
from app.rules import load_rule_engine, resolve_compendium_modifier_details, validate_compendium_effects
from app.system_packs import load_system_pack

def main():
    pack=load_system_pack(ROOT/'tests/fixtures/system_packs/ttl_test_minimal')
    assert pack.valid and pack.manifest is not None, [i.format() for i in pack.issues]
    schema,issues=load_character_schema(pack.root/pack.manifest.character_schema); assert schema is not None
    compendium,issues=load_compendium(pack.root,pack.manifest.compendium); assert compendium is not None
    engine,issues=load_rule_engine(pack.root/pack.manifest.rules,known_fields=set(schema.fields)); assert engine is not None
    assert not validate_compendium_effects(compendium,engine,schema=schema)
    data=schema.default_data(); data.update({'name':'Activation Test','level':1,'inventory':[{'item':'ring_of_power','quantity':1,'equipped':False,'notes':''},{'item':'lucky_charm','quantity':1,'equipped':False,'notes':''}]})
    mods,sources=resolve_compendium_modifier_details(schema,compendium,data,engine)
    assert mods['skill_power_bonus']==1
    names=[r['source_name'] for r in sources['skill_power_bonus']]
    assert 'Lucky Charm' in names and 'Ring of Power' not in names
    data['inventory'][0]['equipped']=True
    mods,sources=resolve_compendium_modifier_details(schema,compendium,data,engine)
    assert mods['skill_power_bonus']==3
    names=[r['source_name'] for r in sources['skill_power_bonus']]
    assert 'Lucky Charm' in names and 'Ring of Power' in names
    print('PASS: collection-row effect activation regression test')
    print('  passive possession effect: OK')
    print('  equipped-only effect: OK')
    print('  row-state condition validation: OK')
    print('  inactive effect omitted from provenance: OK')
    return 0
if __name__=='__main__': raise SystemExit(main())
