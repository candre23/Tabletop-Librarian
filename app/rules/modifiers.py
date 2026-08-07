from __future__ import annotations

from typing import Any

from app.rules.engine import RuleEngine, RuleIssue


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_effect_rows(value: Any) -> list[dict[str, Any]]:
    if _is_number(value):
        return [{"value": value}]
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    return []


def validate_compendium_effects(
    compendium,
    engine: RuleEngine,
    schema=None,
) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    allowed_condition_fields = None
    row_condition_fields: dict[str, set[str]] = {}

    if schema is not None:
        allowed_condition_fields = {
            field_id
            for field_id, field in schema.fields.items()
            if field.type != "calculated"
        }

        for field in schema.fields.values():
            if field.type != "collection":
                continue
            row_ids = set((field.item_schema or {}).keys())
            for item_field in (field.item_schema or {}).values():
                if item_field.type == "reference" and item_field.entity:
                    row_condition_fields.setdefault(
                        item_field.entity,
                        set(),
                    ).update(row_ids)

    for entity_type, bucket in compendium.entities.items():
        for entity_id, entity in bucket.items():
            effects = entity.data.get("effects")
            if effects is None:
                continue

            if not isinstance(effects, dict):
                issues.append(
                    RuleIssue(
                        "error",
                        f"{entity_type}:{entity_id} effects must be a mapping/object.",
                        f"{entity_type}:{entity_id}",
                    )
                )
                continue

            for modifier_id, raw_effect in effects.items():
                if modifier_id not in engine.modifiers:
                    issues.append(
                        RuleIssue(
                            "error",
                            f"{entity_type}:{entity_id} references unknown modifier "
                            f"{modifier_id!r}.",
                            f"{entity_type}:{entity_id}",
                        )
                    )
                    continue

                rows = _normalize_effect_rows(raw_effect)
                if not rows:
                    issues.append(
                        RuleIssue(
                            "error",
                            f"{entity_type}:{entity_id} effect {modifier_id!r} must "
                            "be numeric, an effect mapping, or a list of effect mappings.",
                            f"{entity_type}:{entity_id}",
                        )
                    )
                    continue

                for index, row in enumerate(rows):
                    rule_id = f"{entity_type}:{entity_id}:{modifier_id}[{index}]"

                    if not isinstance(row, dict):
                        issues.append(
                            RuleIssue(
                                "error",
                                f"{entity_type}:{entity_id} effect {modifier_id!r} "
                                "list entries must be mappings/objects.",
                                rule_id,
                            )
                        )
                        continue

                    value = row.get("value")
                    if not _is_number(value):
                        issues.append(
                            RuleIssue(
                                "error",
                                f"{entity_type}:{entity_id} effect {modifier_id!r} "
                                "requires numeric value.",
                                rule_id,
                            )
                        )

                    when = row.get("when")
                    if when is None:
                        continue

                    if not isinstance(when, str) or not when.strip():
                        issues.append(
                            RuleIssue(
                                "error",
                                f"{entity_type}:{entity_id} effect {modifier_id!r} "
                                "when must be a non-empty expression string.",
                                rule_id,
                            )
                        )
                        continue

                    try:
                        dependencies = engine.condition_dependencies(when)
                    except Exception as exc:
                        issues.append(
                            RuleIssue(
                                "error",
                                f"Invalid conditional effect expression: {exc}",
                                rule_id,
                            )
                        )
                        continue

                    if allowed_condition_fields is not None:
                        allowed = set(allowed_condition_fields)
                        allowed.update(
                            row_condition_fields.get(entity_type, set())
                        )
                        unknown = sorted(
                            dependency
                            for dependency in dependencies
                            if dependency not in allowed
                        )
                        if unknown:
                            issues.append(
                                RuleIssue(
                                    "error",
                                    "Conditional effects may reference non-calculated "
                                    "character fields and valid collection-row fields; "
                                    "unknown or unsupported dependencies: "
                                    + ", ".join(unknown),
                                    rule_id,
                                )
                            )

    return issues


def resolve_compendium_modifier_details(
    schema,
    compendium,
    data: dict[str, Any],
    engine: RuleEngine,
) -> tuple[dict[str, float], dict[str, list[dict[str, Any]]]]:
    contributions: dict[str, list[tuple[float, dict[str, Any]]]] = {
        modifier_id: []
        for modifier_id in engine.modifiers
    }

    selections: list[
        tuple[str, Any, str, str, str, dict[str, Any] | None]
    ] = []

    for field_id, field in schema.fields.items():
        raw_value = data.get(field_id)

        if field.type == "reference" and field.entity:
            if raw_value not in (None, ""):
                selections.append(
                    (
                        field.entity,
                        raw_value,
                        field_id,
                        field.label,
                        "",
                        None,
                    )
                )

        elif field.type == "multi_reference" and field.entity:
            if isinstance(raw_value, list):
                for entity_id in raw_value:
                    selections.append(
                        (
                            field.entity,
                            entity_id,
                            field_id,
                            field.label,
                            "",
                            None,
                        )
                    )

        elif field.type == "collection" and isinstance(raw_value, list):
            for row_index, row in enumerate(raw_value):
                if not isinstance(row, dict):
                    continue
                for item_id, item_field in (field.item_schema or {}).items():
                    if item_field.type != "reference" or not item_field.entity:
                        continue
                    entity_id = row.get(item_id)
                    if entity_id in (None, ""):
                        continue
                    selections.append(
                        (
                            item_field.entity,
                            entity_id,
                            field_id,
                            field.label,
                            f"{item_field.label} row {row_index + 1}",
                            row,
                        )
                    )

    for (
        entity_type,
        entity_id,
        field_id,
        field_label,
        row_label,
        row_context,
    ) in selections:
        entity = compendium.get(entity_type, str(entity_id))
        if entity is None:
            continue

        effects = entity.data.get("effects") or {}
        if not isinstance(effects, dict):
            continue

        for modifier_id, raw_effect in effects.items():
            if modifier_id not in contributions:
                continue

            for row in _normalize_effect_rows(raw_effect):
                if not isinstance(row, dict):
                    continue

                value = row.get("value")
                if not _is_number(value):
                    continue

                when = row.get("when")
                if when is not None:
                    if not isinstance(when, str) or not when.strip():
                        continue
                    condition_context = dict(data)
                    if row_context:
                        condition_context.update(row_context)
                    try:
                        if not engine.evaluate_condition(
                            when,
                            condition_context,
                        ):
                            continue
                    except Exception:
                        continue

                numeric_value = float(value)
                source = {
                    "value": numeric_value,
                    "source_name": str(row.get("label") or entity.name),
                    "entity_type": entity.entity_type,
                    "entity_id": entity.id,
                    "field_id": field_id,
                    "field_label": field_label,
                }
                if row_label:
                    source["row_label"] = row_label
                if when:
                    source["condition"] = when

                contributions[modifier_id].append((numeric_value, source))

    resolved: dict[str, float] = {}
    sources: dict[str, list[dict[str, Any]]] = {}

    for modifier_id, definition in engine.modifiers.items():
        rows = contributions.get(modifier_id, [])
        values = [value for value, _ in rows]
        default = float(definition.default)

        if definition.aggregate == "sum":
            resolved[modifier_id] = default + sum(values)
        elif definition.aggregate == "max":
            resolved[modifier_id] = max([default, *values])
        elif definition.aggregate == "min":
            resolved[modifier_id] = min([default, *values])
        else:
            raise RuntimeError(
                f"Unsupported modifier aggregation {definition.aggregate!r}."
            )

        source_rows = [dict(source) for _, source in rows]
        if default:
            source_rows.insert(
                0,
                {
                    "value": default,
                    "source_name": "Default",
                    "entity_type": None,
                    "entity_id": None,
                    "field_id": None,
                    "field_label": None,
                },
            )
        sources[modifier_id] = source_rows

    return resolved, sources


def resolve_compendium_modifiers(
    schema,
    compendium,
    data: dict[str, Any],
    engine: RuleEngine,
) -> dict[str, float]:
    resolved, _ = resolve_compendium_modifier_details(
        schema,
        compendium,
        data,
        engine,
    )
    return resolved
