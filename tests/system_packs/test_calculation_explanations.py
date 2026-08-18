#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader

from app.characters.schema import load_character_schema
from app.characters.web import _evaluate_character_values_with_explanations
from app.compendium import load_compendium
from app.rules import (
    load_rule_engine,
    resolve_compendium_modifier_details,
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
    assert engine.modifiers["skill_power_bonus"].label == "Skill Power Bonus"

    data = schema.default_data()
    data.update(
        {
            "name": "Explanation Test",
            "level": 2,
            "skills": ["athletics", "stealth"],
        }
    )

    modifiers, sources = resolve_compendium_modifier_details(
        schema,
        compendium,
        data,
        engine,
    )
    assert modifiers["skill_power_bonus"] == 4
    assert [row["source_name"] for row in sources["skill_power_bonus"]] == [
        "Athletics",
        "Stealth",
    ]

    labels = {field_id: field.label for field_id, field in schema.fields.items()}
    explanations = engine.explain(
        data,
        modifiers=modifiers,
        modifier_sources=sources,
        labels=labels,
    )
    power = explanations["power_score"]
    assert power["value"] == 8
    assert power["formula_display"] == "Level × 2 + Skill Power Bonus"
    assert power["terms"][0]["label"] == "Level × 2"
    assert power["terms"][0]["value"] == 4
    assert power["terms"][1]["label"] == "Skill Power Bonus"
    assert power["terms"][1]["value"] == 4
    assert [row["source_name"] for row in power["terms"][1]["sources"]] == [
        "Athletics",
        "Stealth",
    ]

    live_values, live_issues, live_explanations = (
        _evaluate_character_values_with_explanations(
            pack,
            schema,
            schema.default_data(),
            {
                "name": "Live Explanation Test",
                "level": 2,
                "skills": ["athletics", "stealth"],
            },
        )
    )
    assert live_values["power_score"] == 8
    assert not [issue for issue in live_issues if issue.severity == "error"]
    assert live_explanations["power_score"]["value"] == 8

    templates = ROOT / "app" / "templates"
    env = Environment(loader=FileSystemLoader(str(templates)))
    for name in ("characters/create.html", "characters/edit.html"):
        env.get_template(name)
        text = (templates / name).read_text()
        assert "ttl-info-button" in text
        assert "ttl-calculation-dialog" in text
        assert "renderExplanations" in text

    print("PASS: calculation explanation regression test")
    print("  modifier source provenance: OK")
    print("  additive term breakdown: OK")
    print("  human-readable formula labels: OK")
    print("  live evaluation explanation payload: OK")
    print("  creation/editor info controls: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
