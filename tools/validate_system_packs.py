#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.system_packs import discover_system_packs, validate_system_pack


DEFAULT_PACK_DIR = Path("data/system_packs")


def print_pack(pack) -> bool:
    name = pack.manifest.name if pack.manifest else pack.root.name
    pack_id = pack.manifest.id if pack.manifest else "unknown"
    version = pack.manifest.version if pack.manifest else "unknown"

    status = "VALID" if pack.valid else "INVALID"
    print(f"{status}: {name} [{pack_id}] v{version}")
    print(f"  {pack.root}")

    for issue in pack.issues:
        print(f"  {issue.format()}")

    if not pack.issues:
        print("  No validation issues.")

    return pack.valid


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Tabletop Librarian System Packs."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help=(
            "Optional path to one System Pack. "
            "Without a path, validates all packs in data/system_packs."
        ),
    )
    args = parser.parse_args()

    if args.path:
        return 0 if print_pack(validate_system_pack(args.path)) else 1

    packs = discover_system_packs(DEFAULT_PACK_DIR)

    if not packs:
        print(f"No System Packs found in {DEFAULT_PACK_DIR}.")
        return 0

    valid = True
    for index, pack in enumerate(packs):
        if index:
            print()
        valid = print_pack(pack) and valid

    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
