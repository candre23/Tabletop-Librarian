from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import copy
import io
import json
import os
import shutil
import tempfile
import zipfile

from app.characters.schema import CharacterField, CharacterSchema, default_collection_item, load_character_schema, validate_character_data
from app.compendium import load_compendium
from app.system_packs.loader import validate_system_pack

MAX_PACKAGE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 5000


class SystemPackPackageError(RuntimeError):
    pass


@dataclass(slots=True)
class CharacterMigrationResult:
    owner: str
    character_id: str
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SystemPackImportResult:
    system_id: str
    name: str
    version: str
    replaced_version: str | None
    migrated_characters: int
    warnings: list[str] = field(default_factory=list)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_MEMBERS:
        raise SystemPackPackageError("System Pack contains too many files.")
    expanded = sum(max(0, int(info.file_size)) for info in infos)
    if expanded > MAX_EXPANDED_BYTES:
        raise SystemPackPackageError("Expanded System Pack is too large.")

    root = target.resolve()
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or "\x00" in name:
            raise SystemPackPackageError("System Pack contains an unsafe path.")
        parts = [part for part in name.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise SystemPackPackageError("System Pack contains an unsafe path.")
        destination = (target / Path(*parts)).resolve()
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise SystemPackPackageError("System Pack contains an unsafe path.") from exc
        if info.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def _find_pack_root(extracted: Path) -> Path:
    if (extracted / "manifest.yaml").is_file():
        return extracted
    children = [p for p in extracted.iterdir() if p.is_dir() and not p.name.startswith("__MACOSX")]
    files = [p for p in extracted.iterdir() if p.is_file() and p.name not in {".DS_Store"}]
    if len(children) == 1 and not files and (children[0] / "manifest.yaml").is_file():
        return children[0]
    raise SystemPackPackageError("A .ttlsys package must contain manifest.yaml at its root, or inside one top-level folder.")


def _compatible_value(old: CharacterField, new: CharacterField, value: Any, *, field_path: str, warnings: list[str]) -> tuple[bool, Any]:
    if value is None:
        return True, None
    if new.type == "calculated":
        return False, None
    if old.type == new.type:
        if new.type == "enum" and value not in new.options:
            warnings.append(f"{field_path}: old value {value!r} is not valid in the new enum and was reset.")
            return False, None
        if new.type == "collection":
            if not isinstance(value, list):
                return False, None
            rows = []
            old_items = old.item_schema or {}
            new_items = new.item_schema or {}
            for index, raw_row in enumerate(value):
                if not isinstance(raw_row, dict):
                    warnings.append(f"{field_path}[{index}]: invalid collection row was dropped.")
                    continue
                row = default_collection_item(new)
                for item_id, new_item in new_items.items():
                    if item_id not in raw_row or item_id not in old_items:
                        continue
                    ok, converted = _compatible_value(old_items[item_id], new_item, raw_row[item_id], field_path=f"{field_path}[{index}].{item_id}", warnings=warnings)
                    if ok:
                        row[item_id] = copy.deepcopy(converted)
                rows.append(row)
            return True, rows
        return True, copy.deepcopy(value)

    if old.type == "integer" and new.type == "decimal" and isinstance(value, int) and not isinstance(value, bool):
        return True, value
    if old.type == "decimal" and new.type == "integer" and isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer():
            return True, int(value)
        warnings.append(f"{field_path}: decimal value {value!r} cannot be represented as an integer and was reset.")
        return False, None
    string_types = {"text", "notes", "reference"}
    if old.type in string_types and new.type in string_types and isinstance(value, str):
        return True, value

    warnings.append(f"{field_path}: field type changed from {old.type} to {new.type}; old value was not converted.")
    return False, None


def _filter_references(schema: CharacterSchema, data: dict[str, Any], compendium, warnings: list[str]) -> None:
    if compendium is None:
        return
    for field_id, field in schema.fields.items():
        value = data.get(field_id)
        if field.type == "reference" and field.entity and value not in (None, ""):
            if compendium.get(field.entity, str(value)) is None:
                warnings.append(f"{field_id}: reference {value!r} no longer exists and was reset.")
                data.pop(field_id, None)
        elif field.type == "multi_reference" and field.entity and isinstance(value, list):
            kept = [item for item in value if compendium.get(field.entity, str(item)) is not None]
            if len(kept) != len(value):
                warnings.append(f"{field_id}: {len(value) - len(kept)} obsolete reference(s) were removed.")
            data[field_id] = kept
        elif field.type == "collection" and isinstance(value, list):
            for row_index, row in enumerate(value):
                if not isinstance(row, dict):
                    continue
                for item_id, item in (field.item_schema or {}).items():
                    item_value = row.get(item_id)
                    if item.type == "reference" and item.entity and item_value not in (None, "") and compendium.get(item.entity, str(item_value)) is None:
                        warnings.append(f"{field_id}[{row_index}].{item_id}: obsolete reference {item_value!r} was reset.")
                        row.pop(item_id, None)


def _migrate_data(old_schema: CharacterSchema | None, new_schema: CharacterSchema, old_data: dict[str, Any], compendium) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    data = new_schema.default_data()
    if old_schema is None:
        for field_id, value in old_data.items():
            if field_id in new_schema.fields:
                data[field_id] = copy.deepcopy(value)
        warnings.append("Old System Pack schema was unavailable; migration used matching field IDs only.")
    else:
        for field_id, new_field in new_schema.fields.items():
            if field_id not in old_data or field_id not in old_schema.fields:
                continue
            ok, converted = _compatible_value(old_schema.fields[field_id], new_field, old_data[field_id], field_path=field_id, warnings=warnings)
            if ok:
                data[field_id] = converted
        removed = [field_id for field_id in old_data if field_id not in new_schema.fields]
        if removed:
            warnings.append("Removed field(s) not carried forward: " + ", ".join(sorted(removed)))
    _filter_references(new_schema, data, compendium, warnings)
    return data, warnings


def _character_files(character_root: Path, system_id: str) -> list[tuple[Path, dict[str, Any]]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    if not character_root.exists():
        return rows
    for path in character_root.glob("*/*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("system_id") == system_id and isinstance(payload.get("data"), dict):
            rows.append((path, payload))
    return rows


def import_system_pack_package(content: bytes, *, pack_root: Path | str = Path("data/system_packs"), character_root: Path | str = Path("data/characters")) -> SystemPackImportResult:
    if not content:
        raise SystemPackPackageError("System Pack package is empty.")
    if len(content) > MAX_PACKAGE_BYTES:
        raise SystemPackPackageError("System Pack package is too large.")

    pack_root = Path(pack_root)
    character_root = Path(character_root)
    pack_root.mkdir(parents=True, exist_ok=True)

    try:
        zf = zipfile.ZipFile(io.BytesIO(content), "r")
    except zipfile.BadZipFile as exc:
        raise SystemPackPackageError("The .ttlsys file is not a valid ZIP package.") from exc

    with tempfile.TemporaryDirectory(prefix="ttl-system-pack-") as temp_name:
        extracted = Path(temp_name) / "extract"
        extracted.mkdir()
        with zf:
            _safe_extract(zf, extracted)
        staged_root = _find_pack_root(extracted)
        staged_pack = validate_system_pack(staged_root)
        if not staged_pack.valid or staged_pack.manifest is None:
            detail = "; ".join(issue.format() for issue in staged_pack.issues)
            raise SystemPackPackageError("System Pack validation failed: " + detail)

        manifest = staged_pack.manifest
        destination = pack_root / manifest.id
        old_pack = validate_system_pack(destination) if destination.is_dir() else None
        replaced_version = old_pack.manifest.version if old_pack and old_pack.manifest else None
        old_schema = None
        if old_pack and old_pack.valid and old_pack.manifest:
            old_schema, _ = load_character_schema(old_pack.root / old_pack.manifest.character_schema)

        new_schema, schema_issues = load_character_schema(staged_root / manifest.character_schema)
        if new_schema is None:
            raise SystemPackPackageError("New character schema is invalid: " + "; ".join(issue.format() for issue in schema_issues))
        compendium, compendium_issues = load_compendium(staged_root, manifest.compendium)
        if compendium is None:
            raise SystemPackPackageError("New compendium is invalid: " + "; ".join(issue.format() for issue in compendium_issues))

        chars = _character_files(character_root, manifest.id)
        migrated: list[tuple[Path, dict[str, Any], list[str]]] = []
        all_warnings: list[str] = []
        for path, payload in chars:
            new_data, warnings = _migrate_data(old_schema, new_schema, payload["data"], compendium)
            updated = copy.deepcopy(payload)
            updated["data"] = new_data
            effects = updated.get("temporary_effects")
            if isinstance(effects, dict):
                removed_effects = sorted(field_id for field_id in effects if field_id not in new_schema.fields)
                for field_id in removed_effects:
                    effects.pop(field_id, None)
                if removed_effects:
                    warnings.append("Temporary effect(s) for removed field(s) were discarded: " + ", ".join(removed_effects))
            schema_errors = validate_character_data(new_schema, new_data)
            if schema_errors:
                warnings.append("Character needs manual review under the new schema: " + "; ".join(issue.format() for issue in schema_errors))
            updated["system_version"] = manifest.version
            updated["character_schema"] = new_schema.schema_version
            migrated.append((path, updated, warnings))
            if warnings:
                label = str(payload.get("data", {}).get("name") or payload.get("character_id") or path.stem)
                all_warnings.extend(f"{label}: {warning}" for warning in warnings)

        backup_root = Path("data/system_pack_backups") / manifest.id / _utc_stamp()
        if destination.exists():
            backup_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(destination, backup_root)

        replacement = Path(temp_name) / "replacement"
        shutil.copytree(staged_root, replacement)
        old_temp = None
        try:
            if destination.exists():
                old_temp = pack_root / f".{manifest.id}.old-{os.getpid()}"
                if old_temp.exists():
                    shutil.rmtree(old_temp)
                os.replace(destination, old_temp)
            os.replace(replacement, destination)
            for path, payload, _warnings in migrated:
                temp_file = path.with_name(f".{path.name}.migration.tmp")
                temp_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                os.replace(temp_file, path)
            if old_temp and old_temp.exists():
                shutil.rmtree(old_temp)
        except Exception:
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            if old_temp and old_temp.exists():
                os.replace(old_temp, destination)
            raise

        return SystemPackImportResult(
            system_id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            replaced_version=replaced_version,
            migrated_characters=len(migrated),
            warnings=all_warnings,
        )
