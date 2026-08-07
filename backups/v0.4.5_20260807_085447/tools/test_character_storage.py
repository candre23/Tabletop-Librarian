#!/usr/bin/env python3
from pathlib import Path
import shutil
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.characters import (
    CharacterStorageError,
    create_character,
    delete_character,
    list_characters,
    load_character,
    save_character,
)
from app.characters.schema import load_character_schema
from app.system_packs import load_system_pack

def main() -> int:
    pack = load_system_pack("data/system_packs/ttl_test_minimal")
    if not pack.valid or pack.manifest is None:
        print("FAIL: minimal System Pack is invalid")
        for issue in pack.issues:
            print(" ", issue.format())
        return 1

    schema, issues = load_character_schema(pack.root / pack.manifest.character_schema)
    if schema is None:
        print("FAIL: character schema is invalid")
        for issue in issues:
            print(" ", issue.format())
        return 1

    temp_root = Path(tempfile.mkdtemp(prefix="ttl_character_test_"))
    try:
        record = create_character(
            "test_user",
            "ttl_test_minimal",
            initial_data={"name": "Test Hero"},
            character_id="testhero",
            character_root=temp_root,
        )
        assert record.data["level"] == 1
        assert record.data["archetype"] == "Adventurer"

        loaded = load_character("test_user", "testhero", character_root=temp_root)
        loaded.data["level"] = 2
        loaded.data["notes"] = "Storage smoke test."
        save_character(loaded, character_root=temp_root)

        listed = list_characters("test_user", character_root=temp_root)
        assert len(listed) == 1

        loaded_again = load_character("test_user", "testhero", character_root=temp_root)
        assert loaded_again.data["level"] == 2

        try:
            loaded_again.data["level"] = 999
            save_character(loaded_again, character_root=temp_root)
        except CharacterStorageError:
            pass
        else:
            raise RuntimeError("Invalid numeric range was not rejected.")

        assert delete_character("test_user", "testhero", character_root=temp_root)

        print("PASS: character schema + storage smoke test")
        print(f"  System Pack: {pack.manifest.name}")
        print(f"  Schema version: {schema.schema_version}")
        print(f"  Fields: {len(schema.fields)}")
        print("  Create/load/save/list/delete: OK")
        print("  Validation rejection: OK")
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

if __name__ == "__main__":
    raise SystemExit(main())
