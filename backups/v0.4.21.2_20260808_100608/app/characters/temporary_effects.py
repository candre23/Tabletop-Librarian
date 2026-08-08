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
