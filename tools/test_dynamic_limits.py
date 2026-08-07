#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.schema import load_character_schema
from app.characters.storage import CharacterStorageError, create_character
from app.characters.web import _limit_state
from app.compendium import load_compendium
from app.rules import evaluate_limits, load_rule_engine, validate_limit_schema
from app.system_packs import load_system_pack


def main() -> int:
    pack_root = ROOT / "data/system_packs"
    pack = load_system_pack(pack_root / "ttl_test_minimal")
    assert pack.valid and pack.manifest is not None, [
        issue.format() for issue in pack.issues
    ]

    schema, issues = load_character_schema(pack.root / pack.manifest.character_schema)
    assert schema is not None, [issue.format() for issue in issues]

    compendium, issues = load_compendium(pack.root, pack.manifest.compendium)
    assert compendium is not None, [issue.format() for issue in issues]

    engine, issues = load_rule_engine(
        pack.root / pack.manifest.rules,
        known_fields=set(schema.fields),
    )
    assert engine is not None, [issue.format() for issue in issues]
    assert not validate_limit_schema(schema, engine)

    data = schema.default_data()
    data.update({
        "name": "Capacity Test",
        "level": 1,
        "skills": ["athletics", "lore"],
    })

    results, limit_issues = evaluate_limits(schema, compendium, data, engine)
    skill_limit = next(result for result in results if result.id == "skill_count")
    assert skill_limit.count == 2
    assert skill_limit.maximum == 2
    assert skill_limit.remaining == 0
    assert not [issue for issue in limit_issues if issue.severity == "error"]

    data["skills"] = ["athletics", "lore", "stealth"]
    results, limit_issues = evaluate_limits(schema, compendium, data, engine)
    skill_limit = next(result for result in results if result.id == "skill_count")
    assert skill_limit.count == 3
    assert skill_limit.maximum == 2
    assert skill_limit.over_by == 1
    assert any(issue.severity == "error" for issue in limit_issues)

    data["level"] = 3
    results, limit_issues = evaluate_limits(schema, compendium, data, engine)
    skill_limit = next(result for result in results if result.id == "skill_count")
    assert skill_limit.maximum == 3
    assert not [issue for issue in limit_issues if issue.severity == "error"]

    live, live_issues = _limit_state(pack, schema, data, ["skills"])
    assert live["skills"][0]["count"] == 3
    assert live["skills"][0]["maximum"] == 3
    assert not [issue for issue in live_issues if issue.severity == "error"]

    with tempfile.TemporaryDirectory() as temp_dir:
        character_root = Path(temp_dir) / "characters"
        try:
            create_character(
                "test-user",
                pack.manifest.id,
                initial_data={
                    "name": "Too Many Skills",
                    "level": 1,
                    "skills": ["athletics", "lore", "stealth"],
                },
                character_root=character_root,
                pack_root=pack_root,
            )
        except CharacterStorageError as exc:
            assert "only 2 are allowed" in str(exc)
        else:
            raise AssertionError("Over-cap character was accepted by storage")

    # Filtered limit smoke test using compendium tags. This is the same
    # mechanism used for things like spell level/type capacities.
    with tempfile.TemporaryDirectory() as temp_dir:
        rules_path = Path(temp_dir) / "rules.yaml"
        rules_path.write_text(
            """
limits:
  physical_skill_count:
    field: skills
    label: Physical skills
    maximum: 1
    where:
      tags: physical
""".strip()
            + "\n"
        )
        filtered_engine, issues = load_rule_engine(
            rules_path,
            known_fields=set(schema.fields),
        )
        assert filtered_engine is not None, [issue.format() for issue in issues]
        assert not validate_limit_schema(schema, filtered_engine)

        filtered = schema.default_data()
        filtered["skills"] = ["athletics", "lore", "stealth"]
        results, issues = evaluate_limits(
            schema,
            compendium,
            filtered,
            filtered_engine,
        )
        result = results[0]
        assert result.count == 1
        assert result.maximum == 1
        assert not [issue for issue in issues if issue.severity == "error"]

    create_template = (ROOT / "app/templates/characters/create.html").read_text()
    edit_template = (ROOT / "app/templates/characters/edit.html").read_text()
    assert 'data-limit-status="{{ field_id }}"' in create_template
    assert 'data-limit-status="{{ field_id }}"' in edit_template
    assert "renderLimits(result.limits)" in create_template
    assert "renderLimits(result.limits)" in edit_template

    print("PASS: dynamic collection-limit regression test")
    print("  level-dependent maximum: OK")
    print("  authoritative over-cap rejection: OK")
    print("  live limit state: OK")
    print("  filtered tag capacity: OK")
    print("  creation/editor count badges: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
