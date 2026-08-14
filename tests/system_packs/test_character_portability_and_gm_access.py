#!/usr/bin/env python3
from pathlib import Path
import json
import sys
import tempfile
import zipfile
from io import BytesIO

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app.characters.portability import (
    CharacterPackageError,
    export_character_package,
    import_character_package,
    parse_character_package,
)
from app.characters.storage import create_character, load_character_raw, list_characters

PACK_ROOT=ROOT/"data/system_packs"

with tempfile.TemporaryDirectory() as td:
    char_root=Path(td)/"characters"

    source=create_character(
        "Alice",
        "ttl_test_minimal",
        initial_data={"name":"Portable Alice"},
        character_root=char_root,
        pack_root=PACK_ROOT,
    )

    blob,filename=export_character_package(source)
    assert filename.endswith(".ttlchar")
    manifest,payload=parse_character_package(blob)
    assert manifest["format"]=="ttl-character"
    assert payload["owner"]=="Alice"

    imported=import_character_package(
        blob,
        target_owner="Bob",
        collision="copy",
        character_root=char_root,
        pack_root=PACK_ROOT,
    )
    assert imported.owner=="Bob"
    assert imported.data["name"]=="Portable Alice"

    # Same ID in same destination -> copy must get a new ID.
    second=import_character_package(
        blob,
        target_owner="Alice",
        collision="copy",
        character_root=char_root,
        pack_root=PACK_ROOT,
    )
    assert second.character_id != source.character_id

    # Replace retains the imported ID.
    replacement=import_character_package(
        blob,
        target_owner="Alice",
        collision="replace",
        character_root=char_root,
        pack_root=PACK_ROOT,
    )
    assert replacement.character_id == source.character_id

    # Packages may not carry executable content.
    bad=BytesIO()
    with zipfile.ZipFile(bad,"w") as z:
        z.writestr("manifest.json",json.dumps(manifest))
        z.writestr("character.json",json.dumps(payload))
        z.writestr("assets/hack.js","alert(1)")
    try:
        parse_character_package(bad.getvalue())
        raise AssertionError("Executable asset should have been rejected.")
    except CharacterPackageError:
        pass

web=(ROOT/"app/characters/web.py").read_text()
index=(ROOT/"app/templates/characters/index.html").read_text()
edit=(ROOT/"app/templates/characters/edit.html").read_text()

assert "character_groups" in web
assert "role == \"gm\"" in web
assert "_target_owner(" in web
assert '@router.get("/characters/{character_id}/export")' in web
assert '@router.post("/characters/import")' in web
assert "Import Character" in index
assert "Import as a new copy" in index
assert "Replace existing character" in index
assert "Owner: {{ character_owner }}" in edit
assert "character_owner_query" in edit
assert 'remove.action = "/characters/{{ record.character_id }}/temporary-effects{{ character_owner_query }}";' in edit
assert 'href="{{ character_url }}" title="Relock' in edit
advance=(ROOT/"app/templates/characters/advance.html").read_text()
assert '/delete{% if draft.owner != username %}?owner=' in advance

print("PASS: character portability + GM access regression")
print("  .ttlchar export/import: OK")
print("  copy collision creates new character ID: OK")
print("  replace collision preserves imported ID: OK")
print("  executable package content rejected: OK")
print("  GM grouped-character UI and owner routing present: OK")
