#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.schema import load_character_schema
from app.compendium import load_compendium
from app.rules import (
    load_rule_engine,
    resolve_compendium_modifier_details,
    validate_compendium_effects,
)
from app.system_packs import load_system_pack


def main() -> int:
    pack = load_system_pack(ROOT / "tests/fixtures/system_packs/ttl_test_minimal")
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
    assert not validate_compendium_effects(
        compendium,
        engine,
        schema=schema,
    )

    low = schema.default_data()
    low.update({"name": "Low Lore", "level": 4, "skills": ["lore"]})
    modifiers, sources = resolve_compendium_modifier_details(
        schema, compendium, low, engine
    )
    assert modifiers["skill_power_bonus"] == 2
    assert [row["source_name"] for row in sources["skill_power_bonus"]] == ["Lore"]

    high = dict(low)
    high["level"] = 5
    modifiers, sources = resolve_compendium_modifier_details(
        schema, compendium, high, engine
    )
    assert modifiers["skill_power_bonus"] == 4
    assert [row["source_name"] for row in sources["skill_power_bonus"]] == [
        "Lore",
        "Lore veteran bonus",
    ]
    assert sources["skill_power_bonus"][1]["condition"] == "level >= 5"

    values, _ = engine.apply(high, modifiers=modifiers)
    assert values["power_score"] == 14

    print("PASS: conditional compendium effects regression test")
    print("  backward-compatible numeric effects: OK")
    print("  conditional effect activation: OK")
    print("  multiple contributions per modifier: OK")
    print("  provenance source labels/conditions: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
