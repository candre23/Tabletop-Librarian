from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

from app.system_packs.portability import import_system_pack_package


def make_package(version: str, schema_version: int, extra: str = "") -> bytes:
    manifest = f'''id: test-system\nname: Test System\nversion: "{version}"\npack_format: 1\ncharacter_schema: character.yaml\n'''
    character = f'''schema_version: {schema_version}\nfields:\n  name:\n    type: text\n    required: true\n  score:\n    type: integer\n    default: 0\n{extra}'''
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.yaml", manifest)
        zf.writestr("character.yaml", character)
    return buf.getvalue()


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    packs = root / "data/system_packs"
    chars = root / "data/characters"
    packs.mkdir(parents=True)
    chars.mkdir(parents=True)

    first = import_system_pack_package(make_package("1.0", 1), pack_root=packs, character_root=chars)
    assert first.version == "1.0"
    assert first.replaced_version is None

    owner = chars / "gm"
    owner.mkdir()
    payload = {
        "character_id": "abc123",
        "owner": "gm",
        "system_id": "test-system",
        "system_version": "1.0",
        "character_schema": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "data": {"name": "Alice", "score": 7},
        "temporary_effects": {},
    }
    (owner / "abc123.json").write_text(json.dumps(payload), encoding="utf-8")

    second = import_system_pack_package(
        make_package("2.0", 2, "  note:\n    type: text\n    default: migrated\n"),
        pack_root=packs,
        character_root=chars,
    )
    assert second.replaced_version == "1.0"
    assert second.migrated_characters == 1
    migrated = json.loads((owner / "abc123.json").read_text(encoding="utf-8"))
    assert migrated["system_version"] == "2.0"
    assert migrated["character_schema"] == 2
    assert migrated["data"]["name"] == "Alice"
    assert migrated["data"]["score"] == 7
    assert migrated["data"]["note"] == "migrated"

print("System Pack import/update migration tests passed.")
