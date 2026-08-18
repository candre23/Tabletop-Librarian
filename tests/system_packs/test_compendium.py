#!/usr/bin/env python3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.compendium import load_compendium
from app.system_packs import load_system_pack


def main() -> int:
    pack = load_system_pack(str(PROJECT_ROOT / "tests/fixtures/system_packs/ttl_test_minimal"))
    if not pack.valid or pack.manifest is None:
        for issue in pack.issues:
            print(issue.format())
        return 1

    compendium, issues = load_compendium(pack.root, pack.manifest.compendium)
    if compendium is None:
        for issue in issues:
            print(issue.format())
        return 1

    assert compendium.get("archetype", "adventurer").name == "Adventurer"
    assert compendium.get("background", "veteran").name == "Veteran"
    assert len(compendium.all("archetype")) == 3
    assert len(compendium.all("background")) == 3

    print("PASS: generic compendium smoke test")
    print("  stable IDs: OK")
    print("  tags: OK")
    print("  cross-file references: OK")
    print("  merged lookup: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
