from __future__ import annotations

from typing import Any

from app.rules.engine import RuleEngine, RuleIssue


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_compendium_effects(compendium, engine: RuleEngine) -> list[RuleIssue]:
    issues: list[RuleIssue] = []

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

            for modifier_id, value in effects.items():
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

                if not _is_number(value):
                    issues.append(
                        RuleIssue(
                            "error",
                            f"{entity_type}:{entity_id} effect {modifier_id!r} "
                            "must be numeric.",
                            f"{entity_type}:{entity_id}",
                        )
                    )

    return issues


def resolve_compendium_modifiers(
    schema,
    compendium,
    data: dict[str, Any],
    engine: RuleEngine,
) -> dict[str, float]:
    contributions: dict[str, list[float]] = {
        modifier_id: []
        for modifier_id in engine.modifiers
    }

    for field_id, field in schema.fields.items():
        if field.type not in {"reference", "multi_reference"} or not field.entity:
            continue

        raw_value = data.get(field_id)

        if field.type == "reference":
            selected = [] if raw_value in (None, "") else [raw_value]
        elif isinstance(raw_value, list):
            selected = raw_value
        else:
            selected = []

        for entity_id in selected:
            entity = compendium.get(field.entity, str(entity_id))
            if entity is None:
                continue

            effects = entity.data.get("effects") or {}
            if not isinstance(effects, dict):
                continue

            for modifier_id, value in effects.items():
                if modifier_id not in contributions:
                    continue
                if _is_number(value):
                    contributions[modifier_id].append(float(value))

    resolved: dict[str, float] = {}

    for modifier_id, definition in engine.modifiers.items():
        values = contributions.get(modifier_id, [])
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

    return resolved
