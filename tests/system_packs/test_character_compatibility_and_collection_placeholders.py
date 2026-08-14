#!/usr/bin/env python3
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.schema import load_character_schema, default_collection_item
from app.characters.storage import (
    create_character,
    load_character,
    load_character_raw,
)
from app.characters.web import _normalize_collection_rows


def main() -> int:
    pack_root = ROOT / "data/system_packs"
    pack_dir = pack_root / "shadowrun_anarchy"
    schema, issues = load_character_schema(pack_dir / "character.yaml")
    assert schema is not None, [issue.format() for issue in issues]

    # Collection editor default rows must be discarded when untouched.
    for field_id in ("skills", "shadow_amps", "qualities", "weapons"):
        field = schema.fields[field_id]
        placeholder = default_collection_item(field)
        assert _normalize_collection_rows(field, [placeholder]) == [], field_id

    # A genuinely named custom entry must remain.
    skills = schema.fields["skills"]
    custom_skill = default_collection_item(skills)
    custom_skill["custom_name"] = "Seattle Gangs"
    normalized = _normalize_collection_rows(skills, [custom_skill])
    assert len(normalized) == 1
    assert normalized[0]["custom_name"] == "Seattle Gangs"

    # Additive schema defaults must be merged into older saved data before
    # rule evaluation. Simulate an older character lacking armor_rating.
    with tempfile.TemporaryDirectory() as temp_dir:
        character_root = Path(temp_dir) / "characters"

        record = create_character(
            "compat-test",
            "shadowrun_anarchy",
            initial_data={"name": "Compatibility Test"},
            character_root=character_root,
            pack_root=pack_root,
        )

        payload = json.loads(record.path.read_text())
        payload["data"].pop("armor_rating", None)
        record.path.write_text(json.dumps(payload, indent=2) + "\n")

        reopened = load_character(
            "compat-test",
            record.character_id,
            character_root=character_root,
            pack_root=pack_root,
        )
        assert reopened.data["armor_rating"] == "9"

        raw = load_character_raw(
            "compat-test",
            record.character_id,
            character_root=character_root,
        )
        assert raw.character_id == record.character_id

    recovery = (ROOT / "app/templates/characters/recovery.html").read_text()
    assert "This character cannot be opened" in recovery
    assert "/delete" in recovery

    print("PASS: character compatibility + collection placeholder regression")
    print("  untouched collection rows discarded: OK")
    print("  custom collection rows retained: OK")
    print("  additive schema defaults merged for old characters: OK")
    print("  raw character recovery loader: OK")
    print("  in-app recovery/delete page: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
