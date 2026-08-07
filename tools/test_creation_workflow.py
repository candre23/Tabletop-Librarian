#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.characters.schema import load_character_schema
from app.creation import load_creation_workflow
from app.system_packs import load_system_pack


def main() -> int:
    pack = load_system_pack("data/system_packs/ttl_test_minimal")
    if not pack.valid or pack.manifest is None:
        print("FAIL: minimal System Pack is invalid")
        for issue in pack.issues:
            print(" ", issue.format())
        return 1

    schema, schema_issues = load_character_schema(
        pack.root / pack.manifest.character_schema
    )
    if schema is None:
        print("FAIL: schema invalid")
        for issue in schema_issues:
            print(" ", issue.format())
        return 1

    workflow, issues = load_creation_workflow(
        pack.root / pack.manifest.creation,
        schema=schema,
    )
    if workflow is None:
        print("FAIL: creation workflow invalid")
        for issue in issues:
            print(" ", issue.format())
        return 1

    assert [step.id for step in workflow.steps] == [
        "identity",
        "advancement",
        "notes",
    ]
    assert workflow.step("identity").fields == ["name", "background"]
    assert "power_score" not in workflow.field_ids()

    # Verify the loader rejects duplicate step IDs and unknown schema fields.
    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "creation.yaml"
        bad_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "steps": [
                        {"id": "one", "fields": ["name"]},
                        {"id": "one", "fields": ["missing_field"]},
                    ],
                },
                sort_keys=False,
            )
        )
        bad_workflow, bad_issues = load_creation_workflow(
            bad_path,
            schema=schema,
        )
        assert bad_workflow is None
        assert any("Duplicate step id" in issue.message for issue in bad_issues)

    print("PASS: creation workflow smoke test")
    print("  ordered steps: OK")
    print("  schema field references: OK")
    print("  required-field coverage: OK")
    print("  duplicate step detection: OK")
    print("  calculated input protection: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
