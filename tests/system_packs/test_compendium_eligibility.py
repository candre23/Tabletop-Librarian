#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.characters.schema import load_character_schema
from app.characters.storage import CharacterStorageError, create_character
from app.characters.web import _eligibility_state
from app.compendium import load_compendium
from app.rules import (
    load_rule_engine,
    reference_eligibility,
    selected_eligibility_issues,
    validate_compendium_eligibility,
)
from app.system_packs import load_system_pack


def main() -> int:
    pack_root = ROOT / "data" / "system_packs"
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
    assert not validate_compendium_eligibility(compendium, engine, schema)

    novice = schema.default_data()
    novice.update({"name": "Novice", "level": 2, "archetype": "Warrior"})
    state = reference_eligibility(schema, compendium, novice, engine)
    assert state["skills"]["battle_training"]["eligible"] is False
    assert "level 3" in state["skills"]["battle_training"]["message"]

    veteran = dict(novice)
    veteran["level"] = 3
    state = reference_eligibility(schema, compendium, veteran, engine)
    assert state["skills"]["battle_training"]["eligible"] is True

    wrong_class = dict(veteran)
    wrong_class["archetype"] = "Scholar"
    wrong_class["skills"] = ["battle_training"]
    eligibility_issues = selected_eligibility_issues(
        schema,
        compendium,
        wrong_class,
        engine,
    )
    assert len(eligibility_issues) == 1
    assert "Battle Training" in eligibility_issues[0].message

    live_state, live_issues = _eligibility_state(pack, schema, novice, ["skills"])
    assert live_state["skills"]["battle_training"]["eligible"] is False
    assert not live_issues

    create_template = (ROOT / "app" / "templates" / "characters" / "create.html").read_text()
    edit_template = (ROOT / "app" / "templates" / "characters" / "edit.html").read_text()
    for template_text in (create_template, edit_template):
        assert "function renderEligibility" in template_text
        assert "ttl-multi-chip-ineligible" in template_text
        assert "result.eligibility" in template_text

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            create_character(
                "test-user",
                pack.manifest.id,
                initial_data={
                    "name": "Illegal Selection",
                    "level": 3,
                    "archetype": "Scholar",
                    "skills": ["battle_training"],
                },
                character_root=Path(temp_dir) / "characters",
                pack_root=pack_root,
            )
        except CharacterStorageError as exc:
            assert "Battle Training is not eligible" in str(exc)
        else:
            raise AssertionError("Illegal compendium selection was accepted")

    print("PASS: compendium eligibility regression test")
    print("  declarative eligibility expression: OK")
    print("  live option eligibility: OK")
    print("  selected ineligible detection: OK")
    print("  authoritative storage rejection: OK")
    print("  creation/editor live eligibility UI: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
