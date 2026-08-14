from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
import json
import re
import tempfile
import uuid
import zipfile

from app.characters.storage import (
    CharacterRecord,
    CharacterStorageError,
    create_character,
    delete_character,
    load_character_raw,
    save_character,
)


FORMAT_NAME = "ttl-character"
FORMAT_VERSION = 1
ALLOWED_ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
}
EXECUTABLE_EXTENSIONS = {
    ".py", ".pyc", ".pyo", ".js", ".mjs", ".cjs", ".sh", ".bash", ".zsh",
    ".bat", ".cmd", ".ps1", ".exe", ".dll", ".so", ".dylib", ".jar", ".class",
    ".com", ".msi", ".scr", ".vbs", ".hta",
}


class CharacterPackageError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return value or "character"


def _character_name(record: CharacterRecord) -> str:
    for key in ("name", "character_name", "title"):
        value = record.data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return record.character_id


def export_character_package(record: CharacterRecord) -> tuple[bytes, str]:
    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "character_id": record.character_id,
        "name": _character_name(record),
        "system_id": record.system_id,
        "system_version": record.system_version,
        "character_schema": record.character_schema,
        "exported_at": _utc_now(),
    }
    character = {
        "character_id": record.character_id,
        "owner": record.owner,
        "system_id": record.system_id,
        "system_version": record.system_version,
        "character_schema": record.character_schema,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "data": record.data,
        "temporary_effects": record.temporary_effects,
        "preferences": record.preferences,
    }

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        archive.writestr(
            "character.json",
            json.dumps(character, indent=2, ensure_ascii=False) + "\n",
        )

    filename = _safe_filename(_character_name(record)) + ".ttlchar"
    return buffer.getvalue(), filename


def parse_character_package(content: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    if not content:
        raise CharacterPackageError("The character package is empty.")

    try:
        with zipfile.ZipFile(BytesIO(content), "r") as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}

            if "manifest.json" not in names or "character.json" not in names:
                raise CharacterPackageError(
                    "Character package must contain manifest.json and character.json."
                )

            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise CharacterPackageError("Character package contains an unsafe path.")

                suffix = Path(path.name).suffix.casefold()
                if suffix in EXECUTABLE_EXTENSIONS:
                    raise CharacterPackageError(
                        f"Executable package content is not allowed: {info.filename}"
                    )

                if info.filename not in {"manifest.json", "character.json"}:
                    if not path.parts or path.parts[0] != "assets":
                        raise CharacterPackageError(
                            f"Unexpected package file: {info.filename}"
                        )
                    if info.is_dir():
                        continue
                    if suffix not in ALLOWED_ASSET_EXTENSIONS:
                        raise CharacterPackageError(
                            f"Unsupported character asset type: {info.filename}"
                        )

            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            character = json.loads(archive.read("character.json").decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise CharacterPackageError("The uploaded file is not a valid .ttlchar package.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CharacterPackageError("Character package JSON is invalid.") from exc

    if not isinstance(manifest, dict) or not isinstance(character, dict):
        raise CharacterPackageError("Character package metadata is invalid.")

    if manifest.get("format") != FORMAT_NAME:
        raise CharacterPackageError("Unsupported character package format.")

    if manifest.get("format_version") != FORMAT_VERSION:
        raise CharacterPackageError(
            f"Unsupported character package version: {manifest.get('format_version')!r}."
        )

    required = {
        "character_id", "system_id", "system_version", "character_schema", "data",
    }
    missing = sorted(required - set(character))
    if missing:
        raise CharacterPackageError(
            "Character package is missing required fields: " + ", ".join(missing)
        )

    if not isinstance(character.get("data"), dict):
        raise CharacterPackageError("Character data must be an object.")

    return manifest, character


def import_character_package(
    content: bytes,
    *,
    target_owner: str,
    collision: str,
    character_root: Path,
    pack_root: Path,
) -> CharacterRecord:
    _manifest, payload = parse_character_package(content)
    collision = collision.strip().lower()
    if collision not in {"copy", "replace"}:
        raise CharacterPackageError("Import collision mode must be copy or replace.")

    system_id = str(payload.get("system_id") or "").strip()
    original_id = str(payload.get("character_id") or "").strip()
    if not system_id or not original_id:
        raise CharacterPackageError("Character package identity is incomplete.")

    # Validate the imported data against the locally installed System Pack
    # without touching the real character collection.
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            probe = create_character(
                target_owner,
                system_id,
                initial_data=dict(payload["data"]),
                character_id=original_id,
                character_root=Path(temp_dir),
                pack_root=pack_root,
            )
            probe.temporary_effects = payload.get("temporary_effects") or {}
            probe.preferences = dict(payload.get("preferences") or {})
            save_character(
                probe,
                character_root=Path(temp_dir),
                pack_root=pack_root,
            )
        except CharacterStorageError as exc:
            raise CharacterPackageError(
                "Character cannot be imported with the installed System Pack: "
                + str(exc)
            ) from exc

    existing_path = character_root / re.sub(
        r"[^A-Za-z0-9_.@-]+", "_", target_owner
    ).strip("._") / f"{original_id}.json"
    exists = existing_path.is_file()

    if exists and collision == "copy":
        character_id = uuid.uuid4().hex[:12]
    else:
        character_id = original_id

    replacement_backup: tuple[Path, bytes] | None = None
    if exists and collision == "replace":
        try:
            existing = load_character_raw(
                target_owner,
                original_id,
                character_root=character_root,
            )
            replacement_backup = (existing.path, existing.path.read_bytes())
        except (CharacterStorageError, OSError) as exc:
            raise CharacterPackageError(str(exc)) from exc
        delete_character(
            target_owner,
            original_id,
            character_root=character_root,
        )

    try:
        record = create_character(
            target_owner,
            system_id,
            initial_data=dict(payload["data"]),
            character_id=character_id,
            character_root=character_root,
            pack_root=pack_root,
        )
        record.temporary_effects = payload.get("temporary_effects") or {}
        record.preferences = dict(payload.get("preferences") or {})
        record = save_character(
            record,
            character_root=character_root,
            pack_root=pack_root,
        )
    except CharacterStorageError as exc:
        if replacement_backup is not None:
            backup_path, backup_bytes = replacement_backup
            try:
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_bytes(backup_bytes)
            except OSError:
                pass
        raise CharacterPackageError(str(exc)) from exc

    return record
