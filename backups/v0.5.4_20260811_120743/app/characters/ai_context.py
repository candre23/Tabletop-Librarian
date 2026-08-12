from __future__ import annotations

from pathlib import Path
from typing import Any

from app.characters.schema import CharacterField, load_character_schema
from app.characters.storage import CharacterRecord, CharacterStorageError, load_character
from app.characters.temporary_effects import (
    build_effective_character_values,
    normalize_temporary_effects,
)
from app.compendium import Compendium, load_compendium
from app.rules import (
    load_rule_engine,
    resolve_compendium_modifiers,
)
from app.system_packs import load_system_pack


def _entity_name(compendium: Compendium, entity_type: str | None, value: Any) -> str:
    if value in (None, ""):
        return ""
    if not entity_type:
        return str(value)
    entity = compendium.get(entity_type, str(value))
    return entity.name if entity is not None else str(value)


def _format_scalar(field: CharacterField, value: Any, compendium: Compendium) -> str:
    if value is None:
        return ""
    if field.type == "reference":
        return _entity_name(compendium, field.entity, value)
    if field.type == "multi_reference":
        if not isinstance(value, list):
            return ""
        return ", ".join(
            _entity_name(compendium, field.entity, item)
            for item in value
            if item not in (None, "")
        )
    if field.type == "boolean":
        return "Yes" if bool(value) else "No"
    if field.type == "resource":
        if isinstance(value, dict):
            current = value.get("current")
            maximum = value.get("max")
            if maximum not in (None, ""):
                return f"{current} / {maximum}"
            return "" if current is None else str(current)
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _format_collection(
    field: CharacterField,
    rows: Any,
    compendium: Compendium,
) -> list[str]:
    if not isinstance(rows, list):
        return []

    result: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue

        cells: list[str] = []
        for item_id, item_field in (field.item_schema or {}).items():
            value = row.get(item_id)
            rendered = _format_scalar(item_field, value, compendium)
            if rendered == "":
                continue
            cells.append(f"{item_field.label}: {rendered}")

        if cells:
            result.append(f"  {index}. " + "; ".join(cells))

    return result


def build_character_ai_context(
    owner: str,
    character_id: str,
    *,
    character_root: Path | str,
    pack_root: Path | str,
) -> dict[str, Any]:
    """Return authoritative, human-readable character context for Ask."""
    character_root = Path(character_root)
    pack_root = Path(pack_root)

    record = load_character(
        owner,
        character_id,
        character_root=character_root,
        pack_root=pack_root,
    )

    pack = load_system_pack(pack_root / record.system_id)
    if not pack.valid or pack.manifest is None:
        detail = "; ".join(issue.format() for issue in pack.issues)
        raise CharacterStorageError(
            f"Character System Pack is unavailable or invalid. {detail}"
        )

    schema, schema_issues = load_character_schema(
        pack.root / pack.manifest.character_schema
    )
    if schema is None:
        detail = "; ".join(issue.format() for issue in schema_issues)
        raise CharacterStorageError(f"Character schema is invalid. {detail}")

    compendium, compendium_issues = load_compendium(
        pack.root,
        pack.manifest.compendium,
    )
    if compendium is None:
        detail = "; ".join(issue.format() for issue in compendium_issues)
        raise CharacterStorageError(f"Character compendium is invalid. {detail}")

    engine = None
    modifiers = None
    if pack.manifest.rules:
        engine, rule_issues = load_rule_engine(
            pack.root / pack.manifest.rules,
            known_fields=set(schema.fields),
        )
        if engine is None:
            detail = "; ".join(issue.format() for issue in rule_issues)
            raise CharacterStorageError(f"Character rules are invalid. {detail}")

        adjusted_inputs = build_effective_character_values(
            data=dict(record.data),
            effects=record.temporary_effects,
            engine=None,
        )
        modifiers = resolve_compendium_modifiers(
            schema,
            compendium,
            adjusted_inputs,
            engine,
        )

    effective = build_effective_character_values(
        data=dict(record.data),
        effects=record.temporary_effects,
        engine=engine,
        modifiers=modifiers,
    )
    effects = normalize_temporary_effects(record.temporary_effects)

    name = str(
        record.data.get("name")
        or record.data.get("character_name")
        or record.character_id
    ).strip()

    lines = [
        f"Character: {name}",
        f"Owner: {record.owner}",
        f"System: {pack.manifest.name} {record.system_version}",
        "",
        "Sheet values:",
    ]

    for field_id, field in schema.fields.items():
        base_value = record.data.get(field_id)
        effective_value = effective.get(field_id, base_value)

        if field.type == "collection":
            rows = _format_collection(field, base_value, compendium)
            if rows:
                lines.append(f"{field.label}:")
                lines.extend(rows)
            continue

        rendered = _format_scalar(field, effective_value, compendium)
        if rendered == "" and base_value in (None, "", [], {}):
            continue

        base_rendered = _format_scalar(field, base_value, compendium)
        if (
            base_rendered
            and rendered
            and base_rendered != rendered
            and isinstance(base_value, (int, float))
            and not isinstance(base_value, bool)
        ):
            lines.append(
                f"{field.label}: {rendered} (base {base_rendered}; temporary effects active)"
            )
        else:
            lines.append(f"{field.label}: {rendered}")

    if effects:
        lines.extend(["", "Active temporary effects:"])
        for field_id, rows in effects.items():
            field = schema.fields.get(field_id)
            label = field.label if field else field_id
            for row in rows:
                duration = f"; reminder: {row['duration']}" if row.get("duration") else ""
                lines.append(
                    f"- {label}: {row['label']} "
                    f"({row['operation']} {row['value']}{duration})"
                )

    return {
        "record": record,
        "name": name,
        "owner": record.owner,
        "system_id": record.system_id,
        "system_name": pack.manifest.name,
        "system_version": record.system_version,
        "text": "\n".join(lines).strip(),
    }
