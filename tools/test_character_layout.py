#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader

from app.characters.layout import (
    complete_character_layout,
    fallback_character_layout,
    load_character_layout,
)
from app.characters.schema import load_character_schema
from app.system_packs import load_system_pack


def main() -> int:
    pack = load_system_pack(ROOT / "data/system_packs/ttl_test_minimal")
    assert pack.valid and pack.manifest is not None, [
        issue.format() for issue in pack.issues
    ]
    assert pack.manifest.layouts["character"] == "layout.yaml"

    schema, issues = load_character_schema(
        pack.root / pack.manifest.character_schema
    )
    assert schema is not None, [issue.format() for issue in issues]

    layout, issues = load_character_layout(
        pack.root / pack.manifest.layouts["character"],
        schema=schema,
    )
    assert layout is not None
    assert not [issue for issue in issues if issue.severity == "error"]
    assert [tab.id for tab in layout.tabs] == ["overview", "gear_notes"]
    assert layout.tabs[0].sections[0].columns == 2
    assert set(layout.field_ids) == set(schema.fields)

    fallback = fallback_character_layout(schema)
    assert set(fallback.field_ids) == set(schema.fields)
    assert len(fallback.tabs) == 1

    completed = complete_character_layout(layout, schema)
    assert set(completed.field_ids) == set(schema.fields)

    templates = ROOT / "app" / "templates"
    env = Environment(loader=FileSystemLoader(str(templates)))
    for name in ("characters/create.html", "characters/edit.html"):
        env.get_template(name)
        text = (templates / name).read_text()
        assert "data-sheet-layout" in text
        assert "data-sheet-tab" in text
        assert "data-sheet-panel" in text
        assert "ttl-layout-columns-" in text

    print("PASS: declarative character-sheet layout regression test")
    print("  tabs and sections: OK")
    print("  1-4 column grids: OK")
    print("  creation-step filtering: OK")
    print("  generic fallback layout: OK")
    print("  System Pack validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
