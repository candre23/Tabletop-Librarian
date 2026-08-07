from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import re
import tempfile
import uuid

from app.characters.schema import CharacterSchema, load_character_schema, validate_character_data\nfrom app.compendium import load_compendium
from app.rules import load_rule_engine
from app.system_packs import load_system_pack


CHARACTER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
USER_ID_RE = re.compile(r"[^A-Za-z0-9_.@-]+")
DEFAULT_CHARACTER_ROOT = Path("data/characters")
DEFAULT_PACK_ROOT = Path("data/system_packs")


class CharacterStorageError(RuntimeError):
    pass


@dataclass(slots=True)
class CharacterRecord:
    character_id: str
    owner: str
    system_id: str
    system_version: str
    character_schema: int
    data: dict[str, Any]
    created_at: str
    updated_at: str
    path: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_owner(owner: str) -> str:
    owner = str(owner or "").strip()
    if not owner:
        raise CharacterStorageError("Character owner is required.")
    safe = USER_ID_RE.sub("_", owner).strip("._")
    if not safe:
        raise CharacterStorageError("Character owner is invalid.")
    return safe


def _character_path(owner: str, character_id: str, root: Path) -> Path:
    if not CHARACTER_ID_RE.fullmatch(character_id):
        raise CharacterStorageError(
            "Character id must contain lowercase letters, digits, '_' or '-'."
        )
    return root / _safe_owner(owner) / f"{character_id}.json"


def _load_system(system_id: str, pack_root: Path):
    pack = load_system_pack(pack_root / system_id)
    if not pack.valid or pack.manifest is None:
        detail = "; ".join(issue.format() for issue in pack.issues)
        raise CharacterStorageError(
            f"System Pack {system_id!r} is invalid or unavailable. {detail}"
        )

    schema, issues = load_character_schema(
        pack.root / pack.manifest.character_schema
    )
    if schema is None:
        detail = "; ".join(issue.format() for issue in issues)
        raise CharacterStorageError(
            f"Character schema for {system_id!r} is invalid. {detail}"
        )

    engine, rule_issues = load_rule_engine(
        pack.root / pack.manifest.rules if pack.manifest.rules else None,
        known_fields=set(schema.fields),
    )
    if engine is None:
        detail = "; ".join(issue.format() for issue in rule_issues)
        raise CharacterStorageError(f"System rules are invalid. {detail}")

    compendium, compendium_issues = load_compendium(
        pack.root,
        pack.manifest.compendium,
    )
    if compendium is None:
        detail = "; ".join(issue.format() for issue in compendium_issues)
        raise CharacterStorageError(f"System compendium is invalid. {detail}")

    return pack, schema, engine, compendium


def _apply_rules(pack, schema, engine, data: dict[str, Any]) -> tuple[dict[str, Any], list]:
    try:
        return engine.apply(data)
    except Exception as exc:
        raise CharacterStorageError(f"Rule evaluation failed: {exc}") from exc


def _validate_all(schema, data, rule_issues, compendium=None) -> None:
    schema_issues = validate_character_data(schema, data)
    blocking_rules = [
        issue for issue in rule_issues if issue.severity == "error"
    ]
    reference_errors = []

    if compendium is not None:
        for field_id, field in schema.fields.items():
            if field.type != "reference" or not field.entity:
                continue
            value = data.get(field_id)
            if value not in (None, "") and compendium.get(field.entity, str(value)) is None:
                reference_errors.append(
                    f"ERROR: {field_id}: Unknown {field.entity} reference {value!r}."
                )

    if schema_issues or blocking_rules or reference_errors:
        details = [issue.format() for issue in schema_issues]
        details.extend(issue.format() for issue in blocking_rules)
        details.extend(reference_errors)
        raise CharacterStorageError(
            "Character data failed validation: " + "; ".join(details)
        )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def create_character(
    owner: str,
    system_id: str,
    *,
    initial_data: dict[str, Any] | None = None,
    character_id: str | None = None,
    character_root: Path | str = DEFAULT_CHARACTER_ROOT,
    pack_root: Path | str = DEFAULT_PACK_ROOT,
) -> CharacterRecord:
    root = Path(character_root)
    pack, schema, engine, compendium = _load_system(system_id, Path(pack_root))

    data = schema.default_data()
    if initial_data:
        data.update(initial_data)

    data, rule_issues = _apply_rules(pack, schema, engine, data)
    _validate_all(schema, data, rule_issues, compendium)

    character_id = character_id or uuid.uuid4().hex[:12]
    path = _character_path(owner, character_id, root)

    if path.exists():
        raise CharacterStorageError(
            f"Character {character_id!r} already exists."
        )

    now = _utc_now()
    payload = {
        "character_id": character_id,
        "owner": owner,
        "system_id": pack.manifest.id,
        "system_version": pack.manifest.version,
        "character_schema": schema.schema_version,
        "created_at": now,
        "updated_at": now,
        "data": data,
    }
    _atomic_write_json(path, payload)

    return CharacterRecord(
        character_id,
        owner,
        pack.manifest.id,
        pack.manifest.version,
        schema.schema_version,
        data,
        now,
        now,
        path,
    )


def load_character(
    owner: str,
    character_id: str,
    *,
    character_root: Path | str = DEFAULT_CHARACTER_ROOT,
    pack_root: Path | str = DEFAULT_PACK_ROOT,
) -> CharacterRecord:
    root = Path(character_root)
    path = _character_path(owner, character_id, root)

    if not path.is_file():
        raise CharacterStorageError("Character does not exist.")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CharacterStorageError(
            f"Could not read character file: {exc}"
        ) from exc

    required = {
        "character_id", "owner", "system_id", "system_version",
        "character_schema", "created_at", "updated_at", "data",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise CharacterStorageError(
            "Character file is missing required keys: "
            + ", ".join(missing)
        )

    if payload["owner"] != owner:
        raise CharacterStorageError("Character owner mismatch.")

    pack, schema, engine = _load_system(
        payload["system_id"],
        Path(pack_root),
    )

    if payload["character_schema"] != schema.schema_version:
        raise CharacterStorageError(
            "Character schema version does not match the installed System Pack. "
            "A migration will be required."
        )

    data, rule_issues = _apply_rules(
        pack,
        schema,
        engine,
        payload["data"],
    )
    _validate_all(schema, data, rule_issues, compendium)

    return CharacterRecord(
        payload["character_id"],
        payload["owner"],
        payload["system_id"],
        payload["system_version"],
        payload["character_schema"],
        data,
        payload["created_at"],
        payload["updated_at"],
        path,
    )


def save_character(
    record: CharacterRecord,
    *,
    character_root: Path | str = DEFAULT_CHARACTER_ROOT,
    pack_root: Path | str = DEFAULT_PACK_ROOT,
) -> CharacterRecord:
    root = Path(character_root)
    pack, schema, engine = _load_system(
        record.system_id,
        Path(pack_root),
    )

    if record.character_schema != schema.schema_version:
        raise CharacterStorageError(
            "Character schema version does not match the installed System Pack."
        )

    record.data, rule_issues = _apply_rules(
        pack,
        schema,
        engine,
        record.data,
    )
    _validate_all(schema, record.data, rule_issues, compendium)

    record.updated_at = _utc_now()
    record.system_version = pack.manifest.version
    path = _character_path(record.owner, record.character_id, root)

    _atomic_write_json(
        path,
        {
            "character_id": record.character_id,
            "owner": record.owner,
            "system_id": record.system_id,
            "system_version": record.system_version,
            "character_schema": record.character_schema,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "data": record.data,
        },
    )

    record.path = path
    return record


def list_characters(
    owner: str,
    *,
    character_root: Path | str = DEFAULT_CHARACTER_ROOT,
) -> list[dict[str, Any]]:
    owner_dir = Path(character_root) / _safe_owner(owner)
    if not owner_dir.exists():
        return []

    results = []

    for path in sorted(owner_dir.glob("*.json"), key=lambda p: p.name.casefold()):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if payload.get("owner") != owner:
            continue

        results.append(
            {
                "character_id": payload.get("character_id", path.stem),
                "system_id": payload.get("system_id"),
                "system_version": payload.get("system_version"),
                "character_schema": payload.get("character_schema"),
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
                "data": payload.get("data", {}),
                "path": path,
            }
        )

    return results


def delete_character(
    owner: str,
    character_id: str,
    *,
    character_root: Path | str = DEFAULT_CHARACTER_ROOT,
) -> bool:
    path = _character_path(owner, character_id, Path(character_root))
    if not path.exists():
        return False
    path.unlink()
    return True
