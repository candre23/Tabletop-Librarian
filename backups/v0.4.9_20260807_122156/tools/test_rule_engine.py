#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rules import load_rule_engine


def main() -> int:
    content = (
        "calculated:\n"
        "  base_bonus:\n"
        "    formula: level * 2\n"
        "  final_bonus:\n"
        "    formula: base_bonus + strength\n"
        "validation:\n"
        "  minimum_strength:\n"
        "    rule: strength >= 1\n"
        "    message: Strength must be positive.\n"
        "    severity: error\n"
    )

    with tempfile.TemporaryDirectory(prefix="ttl_rules_") as temp_dir:
        path = Path(temp_dir) / "rules.yaml"
        path.write_text(content)

        engine, issues = load_rule_engine(
            path,
            known_fields={
                "level", "strength", "base_bonus", "final_bonus"
            },
        )

        if engine is None:
            for issue in issues:
                print(issue.format())
            return 1

        values, validation = engine.apply(
            {"level": 3, "strength": 4}
        )
        assert values["base_bonus"] == 6
        assert values["final_bonus"] == 10
        assert validation == []

        _, validation = engine.apply(
            {"level": 3, "strength": 0}
        )
        assert len(validation) == 1

        print("PASS: safe rule engine smoke test")
        print("  dependency ordering: OK")
        print("  expression evaluation: OK")
        print("  validation rules: OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
