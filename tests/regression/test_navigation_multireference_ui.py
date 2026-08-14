#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jinja2 import Environment, FileSystemLoader
from app.characters.schema import load_character_schema
from app.characters.storage import create_character, load_character
from app.characters.web import _reference_options
from app.compendium import load_compendium
from app.system_packs import load_system_pack


def main() -> int:
    templates = PROJECT_ROOT / "app" / "templates"
    env = Environment(loader=FileSystemLoader(str(templates)))

    # Syntax/load check all templates touched by the change.
    for name in (
        "base.html",
        "_global_nav.html",
        "home.html",
        "characters/index.html",
        "characters/create.html",
        "characters/edit.html",
    ):
        env.get_template(name)

    edit_text = (templates / "characters" / "edit.html").read_text()
    create_text = (templates / "characters" / "create.html").read_text()
    nav_text = (templates / "_global_nav.html").read_text()

    assert "ttl-multi-reference-native" in edit_text
    assert "ttl-multi-reference-native" in create_text
    assert "Hold Ctrl/Cmd" not in edit_text
    assert "Hold Ctrl/Cmd" not in create_text
    assert "ttl-multi-chip" in edit_text
    assert "ttl-multi-chip" in create_text
    assert 'href="/characters"' in nav_text
    assert 'href="/search"' in nav_text
    assert 'href="/uploads"' in nav_text

    pack_root = PROJECT_ROOT / "data" / "system_packs"
    pack = load_system_pack(pack_root / "ttl_test_minimal")
    assert pack.valid and pack.manifest is not None

    schema, issues = load_character_schema(pack.root / pack.manifest.character_schema)
    assert schema is not None, [issue.format() for issue in issues]

    compendium, issues = load_compendium(pack.root, pack.manifest.compendium)
    assert compendium is not None, [issue.format() for issue in issues]

    options = _reference_options(schema, compendium)
    skill_ids = {item.id for item in options["skills"]}
    assert {"athletics", "stealth"} <= skill_ids

    with tempfile.TemporaryDirectory() as temp_dir:
        character_root = Path(temp_dir) / "characters"
        record = create_character(
            "test-user",
            pack.manifest.id,
            initial_data={
                "name": "Safe Multi Test",
                "archetype": "Adventurer",
                "background": "traveler",
                "skills": ["athletics", "stealth"],
            },
            character_root=character_root,
            pack_root=pack_root,
        )
        reopened = load_character(
            "test-user",
            record.character_id,
            character_root=character_root,
            pack_root=pack_root,
        )
        assert reopened.data["skills"] == ["athletics", "stealth"]

    print("PASS: v0.4.8.2 navigation + multi-reference regression test")
    print("  global navigation templates: OK")
    print("  safe add/remove multi-reference widget: OK")
    print("  saved multi-reference values persist: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
