#!/usr/bin/env python3
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.library.manager as manager


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        source_root = temp / "Shadowrun Anarchy"
        core = source_root / "Core"
        supplements = source_root / "Supplements"
        missions = supplements / "Missions"

        missions.mkdir(parents=True)
        core.mkdir(parents=True)

        (source_root / "overview.pdf").write_bytes(b"%PDF-1.4\n")
        (core / "core-rules.pdf").write_bytes(b"%PDF-1.4\n")
        (supplements / "contract-brief.txt").write_text("test")
        (missions / "mission-one.md").write_text("# Mission")

        library_file = temp / "library.json"
        old_library_file = manager.LIBRARY_FILE
        old_mark_changed = manager.mark_library_changed

        manager.LIBRARY_FILE = library_file
        changes = []
        manager.mark_library_changed = changes.append

        try:
            manager.add_folder("Shadowrun", "players")
            result = manager.add_source("Shadowrun", str(source_root))

            assert result["type"] == "directory"
            assert result["added_count"] == 4

            folder = manager.get_folder("Shadowrun")
            assert folder is not None

            source_paths = {
                source["path"]
                for source in folder["sources"]
                if source["type"] == "directory"
            }

            assert source_paths == {
                str(source_root.resolve()),
                str(core.resolve()),
                str(supplements.resolve()),
                str(missions.resolve()),
            }

            scan = manager.scan_folder(folder, generate_covers=False)
            filenames = {
                document["filename"]
                for document in scan["documents"]
            }

            assert filenames == {
                "overview.pdf",
                "core-rules.pdf",
                "contract-brief.txt",
                "mission-one.md",
            }

            # Removing one independently registered child removes only that
            # child's directly contained documents. Grandchildren remain
            # because they are independent sources.
            removed = manager.remove_source(
                "Shadowrun",
                "directory",
                str(supplements.resolve()),
            )
            assert removed is True

            folder = manager.get_folder("Shadowrun")
            scan = manager.scan_folder(folder, generate_covers=False)
            filenames = {
                document["filename"]
                for document in scan["documents"]
            }

            assert "contract-brief.txt" not in filenames
            assert "mission-one.md" in filenames

            # Re-adding an already registered parent should restore missing
            # descendants instead of rejecting the entire operation.
            refill = manager.add_source("Shadowrun", str(source_root))
            assert refill["added_count"] == 1

            folder = manager.get_folder("Shadowrun")
            source_paths = {
                source["path"]
                for source in folder["sources"]
                if source["type"] == "directory"
            }
            assert str(supplements.resolve()) in source_paths

            # No duplicates are introduced.
            assert len(source_paths) == 4

        finally:
            manager.LIBRARY_FILE = old_library_file
            manager.mark_library_changed = old_mark_changed

    print("PASS: recursive library source regression test")
    print("  parent + all descendant directories registered: OK")
    print("  nested documents discovered: OK")
    print("  subfolders independently removable: OK")
    print("  re-adding parent fills missing descendants: OK")
    print("  duplicate source entries prevented: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
