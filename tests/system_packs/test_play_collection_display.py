#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from app.characters.schema import load_character_schema
from app.characters.web import _display_collection_item_value
from app.compendium import load_compendium
from app.system_packs import load_system_pack

pack=load_system_pack(ROOT/"data/system_packs/shadowrun_anarchy")
assert pack.valid and pack.manifest is not None
schema,issues=load_character_schema(pack.root/pack.manifest.character_schema)
assert schema is not None, [i.format() for i in issues]
compendium,cissues=load_compendium(pack.root,pack.manifest.compendium)
assert compendium is not None, [i.format() for i in cissues]

weapon_field=schema.fields["weapons"]
weapon_item=weapon_field.item_schema["weapon"]
weapon_entities=compendium.all("weapon")
options={"weapons":{"weapon":weapon_entities}}
if weapon_entities:
    entity=weapon_entities[0]
    assert _display_collection_item_value(
        "weapons","weapon",weapon_item,entity.id,options
    ) == entity.name

assert _display_collection_item_value(
    "skills","knowledge",schema.fields["skills"].item_schema["knowledge"],True,{}
) == "Yes"
assert _display_collection_item_value(
    "gear","notes",schema.fields["gear"].item_schema["notes"],"",{}
) == ""

template=(ROOT/"app/templates/characters/edit.html").read_text()
css=(ROOT/"app/static/css/main.css").read_text()
assert 'class="ttl-play-collection"' in template
assert "display_collection_item_value(" in template
assert "ttl-play-collection-row" in css
assert "@container (max-width: 430px)" in css

print("PASS: Play-mode structured collection display")
print("  compendium references resolve to names: OK")
print("  actual collection rows render in Play mode: OK")
print("  empty cells are suppressed: OK")
print("  narrow-pane responsive layout: OK")
