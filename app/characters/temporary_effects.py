from __future__ import annotations

from typing import Any

SUPPORTED_OPERATIONS = {"add", "subtract", "multiply", "override"}


def normalize_temporary_effects(raw: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}

    result: dict[str, list[dict[str, Any]]] = {}
    for field_id, rows in raw.items():
        if not isinstance(field_id, str) or not isinstance(rows, list):
            continue

        clean_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            operation = str(row.get("operation") or "").strip().lower()
            if operation not in SUPPORTED_OPERATIONS:
                continue

            try:
                value = float(row.get("value"))
            except (TypeError, ValueError):
                continue

            clean_rows.append(
                {
                    "label": str(row.get("label") or "Temporary effect").strip()
                    or "Temporary effect",
                    "operation": operation,
                    "value": int(value) if value.is_integer() else value,
                    "duration": str(row.get("duration") or "").strip(),
                }
            )

        if clean_rows:
            result[field_id] = clean_rows

    return result


def effective_value(
    base_value: int | float,
    modifiers: list[dict[str, Any]] | None,
) -> int | float:
    value = float(base_value)

    for row in modifiers or []:
        operation = str(row.get("operation") or "").strip().lower()
        amount = float(row.get("value"))

        if operation == "add":
            value += amount
        elif operation == "subtract":
            value -= amount
        elif operation == "multiply":
            value *= amount
        elif operation == "override":
            value = amount

    return int(value) if value.is_integer() else value



def build_effective_character_values(
    *,
    data: dict[str, Any],
    effects: dict[str, list[dict[str, Any]]],
    engine=None,
    modifiers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_temporary_effects(effects)

    def transform(field_id: str, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return value
        rows = normalized.get(field_id)
        if not rows:
            return value
        return effective_value(value, rows)

    if engine is None:
        return {
            field_id: transform(field_id, value)
            for field_id, value in data.items()
        }

    return engine.calculate(
        data,
        modifiers=modifiers,
        value_transform=transform,
    )


def temporary_influence_map(
    *,
    effects: dict[str, list[dict[str, Any]]],
    engine=None,
) -> dict[str, list[str]]:
    normalized = normalize_temporary_effects(effects)
    direct = set(normalized)
    influences: dict[str, set[str]] = {
        field_id: {field_id}
        for field_id in direct
    }

    if engine is not None:
        for rule_id in engine.order:
            sources: set[str] = set()
            rule = engine.calculated[rule_id]
            for dependency in rule.dependencies:
                if dependency in direct:
                    sources.add(dependency)
                sources.update(influences.get(dependency, set()))
            if rule_id in direct:
                sources.add(rule_id)
            if sources:
                influences[rule_id] = sources

    return {
        field_id: sorted(source_ids)
        for field_id, source_ids in influences.items()
    }
