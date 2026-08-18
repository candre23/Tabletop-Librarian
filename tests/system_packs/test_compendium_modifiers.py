#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.schema import load_character_schema
from app.characters.storage import create_character, load_character, save_character
from app.characters.web import _evaluate_character_values
from app.compendium import load_compendium
from app.rules import (
    load_rule_engine,
    resolve_compendium_modifiers,
    validate_compendium_effects,
)
from app.system_packs import load_system_pack


def main() -> int:
    pack_root = ROOT / "tests" / "fixtures" / "system_packs"
    pack = load_system_pack(pack_root / "ttl_test_minimal")
    assert pack.valid and pack.manifest is not None, [
        issue.format() for issue in pack.issues
    ]

    schema, issues = load_character_schema(
        pack.root / pack.manifest.character_schema
    )
    assert schema is not None, [issue.format() for issue in issues]

    compendium, issues = load_compendium(
        pack.root,
        pack.manifest.compendium,
    )
    assert compendium is not None, [issue.format() for issue in issues]

    engine, issues = load_rule_engine(
        pack.root / pack.manifest.rules,
        known_fields=set(schema.fields),
    )
    assert engine is not None, [issue.format() for issue in issues]
    assert not validate_compendium_effects(compendium, engine)

    data = schema.default_data()
    data["name"] = "Modifier Test"
    data["level"] = 2
    data["skills"] = ["athletics", "stealth"]

    modifiers = resolve_compendium_modifiers(
        schema,
        compendium,
        data,
        engine,
    )
    assert modifiers["skill_power_bonus"] == 4

    calculated, issues = engine.apply(data, modifiers=modifiers)
    assert calculated["power_score"] == 8
    assert "skill_power_bonus" not in calculated

    live_values, live_issues = _evaluate_character_values(
        pack,
        schema,
        schema.default_data(),
        {
            "name": "Live Modifier Test",
            "level": 2,
            "skills": ["athletics", "stealth"],
        },
    )
    assert live_values["power_score"] == 8
    assert not [issue for issue in live_issues if issue.severity == "error"]

    with tempfile.TemporaryDirectory() as temp_dir:
        character_root = Path(temp_dir) / "characters"

        record = create_character(
            "test-user",
            pack.manifest.id,
            initial_data={
                "name": "Stored Modifier Test",
                "level": 2,
                "skills": ["athletics", "stealth"],
            },
            character_root=character_root,
            pack_root=pack_root,
        )
        assert record.data["power_score"] == 8

        record.data["skills"] = ["athletics"]
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
        assert reopened.data["power_score"] == 5

    print("PASS: compendium-driven modifier regression test")
    print("  declared modifier channel: OK")
    print("  multi-reference effect aggregation: OK")
    print("  chained calculated rule input: OK")
    print("  live evaluation: OK")
    print("  authoritative save/load recalculation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
