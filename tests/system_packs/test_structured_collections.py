#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader

from app.characters.schema import (
    default_collection_item,
    load_character_schema,
    validate_character_data,
)
from app.characters.storage import create_character, load_character, save_character
from app.characters.web import _collection_reference_options
from app.compendium import load_compendium
from app.rules import (
    load_rule_engine,
    resolve_compendium_modifier_details,
)
from app.system_packs import load_system_pack


def main() -> int:
    pack_root = ROOT / "tests/fixtures/system_packs"
    pack = load_system_pack(pack_root / "ttl_test_minimal")
    assert pack.valid and pack.manifest is not None, [
        issue.format() for issue in pack.issues
    ]

    schema, issues = load_character_schema(
        pack.root / pack.manifest.character_schema
    )
    assert schema is not None, [issue.format() for issue in issues]

    inventory = schema.fields["inventory"]
    assert inventory.type == "collection"
    assert set(inventory.item_schema) == {
        "item",
        "custom_name",
        "quantity",
        "equipped",
        "notes",
    }

    default_row = default_collection_item(inventory)
    assert default_row == {
        "quantity": 1,
        "equipped": False,
        "notes": "",
        "custom_name": "",
    }

    valid_data = schema.default_data()
    valid_data.update({
        "name": "Collection Test",
        "inventory": [
            {
                "item": "rope",
                "quantity": 2,
                "equipped": False,
                "notes": "50 ft",
            },
            {
                "item": "ring_of_power",
                "quantity": 1,
                "equipped": True,
                "notes": "",
            },
        ],
    })
    assert not validate_character_data(schema, valid_data)

    invalid_data = dict(valid_data)
    invalid_data["inventory"] = [{"item": "rope", "quantity": 0}]
    issues = validate_character_data(schema, invalid_data)
    assert any(issue.field == "inventory[0].quantity" for issue in issues)

    compendium, issues = load_compendium(
        pack.root,
        pack.manifest.compendium,
    )
    assert compendium is not None, [issue.format() for issue in issues]

    nested_options = _collection_reference_options(schema, compendium)
    assert nested_options["inventory"]["item"]
    assert any(
        entity.id == "ring_of_power"
        for entity in nested_options["inventory"]["item"]
    )

    engine, issues = load_rule_engine(
        pack.root / pack.manifest.rules,
        known_fields=set(schema.fields),
    )
    assert engine is not None, [issue.format() for issue in issues]

    modifiers, sources = resolve_compendium_modifier_details(
        schema,
        compendium,
        valid_data,
        engine,
    )
    assert modifiers["skill_power_bonus"] == 2
    assert any(
        row["source_name"] == "Ring of Power"
        for row in sources["skill_power_bonus"]
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        character_root = Path(temp_dir) / "characters"
        record = create_character(
            "test-user",
            pack.manifest.id,
            initial_data=valid_data,
            character_root=character_root,
            pack_root=pack_root,
        )
        assert len(record.data["inventory"]) == 2
        assert record.data["power_score"] == 4

        record.data["inventory"][0]["quantity"] = 3
        save_character(
            record,
            character_root=character_root,
            pack_root=pack_root,
        )

        reopened = load_character(
            "test-user",
            record.character_id,
            character_root=character_root,
            pack_root=pack_root,
        )
        assert reopened.data["inventory"][0]["quantity"] == 3
        assert reopened.data["inventory"][1]["item"] == "ring_of_power"

    templates = ROOT / "app/templates"
    env = Environment(loader=FileSystemLoader(str(templates)))
    for name in ("characters/create.html", "characters/edit.html"):
        env.get_template(name)
        text = (templates / name).read_text()
        assert "data-structured-collection" in text
        assert "data-row-remove" in text
        assert "data-row-up" in text
        assert "data-row-down" in text

    print("PASS: structured collection regression test")
    print("  typed item schema validation: OK")
    print("  add/remove/reorder UI hooks: OK")
    print("  nested compendium references: OK")
    print("  persistence: OK")
    print("  collection item modifier effects: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
