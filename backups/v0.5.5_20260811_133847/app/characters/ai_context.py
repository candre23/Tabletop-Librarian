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



def _clean_hint(value: str) -> str:
    value = " ".join(str(value or "").split()).strip()
    return value[:120]


def _dedupe_hints(values: list[str], *, limit: int = 32) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = _clean_hint(value)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _field_search_hints(
    field: CharacterField,
    value: Any,
    compendium: Compendium,
) -> list[str]:
    """Extract bounded human-readable option names useful for RAG retrieval."""
    hints: list[str] = []

    if field.type == "reference":
        rendered = _entity_name(compendium, field.entity, value)
        if rendered:
            hints.append(rendered)
        return hints

    if field.type == "multi_reference":
        if isinstance(value, list):
            for item in value:
                rendered = _entity_name(compendium, field.entity, item)
                if rendered:
                    hints.append(rendered)
        return hints

    if field.type != "collection" or not isinstance(value, list):
        return hints

    name_like_ids = {
        "name",
        "custom_name",
        "skill",
        "quality",
        "weapon",
        "item",
        "gear",
        "amp",
        "shadow_amp",
        "contact",
        "cue",
        "disposition",
    }

    for row in value:
        if not isinstance(row, dict):
            continue
        for item_id, item_field in (field.item_schema or {}).items():
            item_value = row.get(item_id)
            if item_value in (None, "", False):
                continue
            if item_field.type == "reference":
                rendered = _entity_name(compendium, item_field.entity, item_value)
                if rendered:
                    hints.append(rendered)
            elif item_id in name_like_ids:
                rendered = _format_scalar(item_field, item_value, compendium)
                if rendered:
                    hints.append(rendered)

    return hints


def character_retrieval_query(
    question: str,
    context: dict[str, Any] | None,
    *,
    max_hints: int = 18,
) -> str:
    """Augment retrieval with sheet terms the user may refer to indirectly."""
    question = " ".join(str(question or "").split()).strip()
    if not context:
        return question

    groups = context.get("search_hint_groups")
    if not isinstance(groups, list):
        return question

    lowered = question.casefold()
    selected: list[str] = []

    # Prefer a section explicitly referenced by the user's wording.
    for group in groups:
        if not isinstance(group, dict):
            continue
        label = str(group.get("label") or "").strip()
        field_id = str(group.get("field_id") or "").strip()
        label_words = label.casefold()
        field_words = field_id.casefold().replace("_", " ")
        candidates = {
            label_words,
            label_words.rstrip("s"),
            field_words,
            field_words.rstrip("s"),
        }
        if any(term and term in lowered for term in candidates):
            selected.extend(
                str(item)
                for item in group.get("hints", [])
                if str(item).strip()
            )

    # Exact item names named by the user are always relevant.
    all_hints = [
        str(item)
        for group in groups
        if isinstance(group, dict)
        for item in group.get("hints", [])
        if str(item).strip()
    ]
    for hint in all_hints:
        if hint.casefold() in lowered:
            selected.append(hint)

    # Do not append the entire character sheet to an indirect question.
    # Doing so can overwhelm the user's actual wording and retrieve unrelated
    # rules merely because those options happen to be on the sheet.
    selected = _dedupe_hints(selected, limit=max_hints)
    if not selected:
        return question

    return (
        question
        + "\nRelevant selected character-sheet terms: "
        + "; ".join(selected)
    )


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
    structured_fields: list[dict[str, Any]] = []
    search_hint_groups: list[dict[str, Any]] = []

    for field_id, field in schema.fields.items():
        base_value = record.data.get(field_id)
        effective_value = effective.get(field_id, base_value)

        if field.type == "collection":
            rows = _format_collection(field, base_value, compendium)
            hints = _dedupe_hints(
                _field_search_hints(field, base_value, compendium),
                limit=24,
            )
            if rows:
                lines.append(f"{field.label}:")
                lines.extend(rows)
                structured_fields.append(
                    {
                        "field_id": field_id,
                        "label": field.label,
                        "type": field.type,
                        "rows": rows,
                    }
                )
            if hints:
                search_hint_groups.append(
                    {
                        "field_id": field_id,
                        "label": field.label,
                        "hints": hints,
                    }
                )
            continue

        rendered = _format_scalar(field, effective_value, compendium)
        if rendered == "" and base_value in (None, "", [], {}):
            continue

        base_rendered = _format_scalar(field, base_value, compendium)
        is_temporarily_modified = bool(
            base_rendered
            and rendered
            and base_rendered != rendered
            and isinstance(base_value, (int, float))
            and not isinstance(base_value, bool)
        )
        if is_temporarily_modified:
            lines.append(
                f"{field.label}: {rendered} (base {base_rendered}; temporary effects active)"
            )
        else:
            lines.append(f"{field.label}: {rendered}")

        structured_fields.append(
            {
                "field_id": field_id,
                "label": field.label,
                "type": field.type,
                "value": rendered,
                "base_value": base_rendered,
                "temporary_modified": is_temporarily_modified,
            }
        )
        hints = _dedupe_hints(
            _field_search_hints(field, base_value, compendium),
            limit=24,
        )
        if hints:
            search_hint_groups.append(
                {
                    "field_id": field_id,
                    "label": field.label,
                    "hints": hints,
                }
            )

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
        "structured_fields": structured_fields,
        "search_hint_groups": search_hint_groups,
        "text": "\n".join(lines).strip(),
    }
