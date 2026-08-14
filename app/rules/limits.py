from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.rules.engine import RuleEngine, RuleIssue
from app.rules.modifiers import resolve_compendium_modifiers


@dataclass(slots=True)
class LimitResult:
    id: str
    field: str
    label: str
    count: int
    maximum: int | None
    remaining: int | None
    over_by: int
    maximum_expression: str
    maximum_display: str
    inputs: list[dict[str, Any]]
    where: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "field": self.field,
            "label": self.label,
            "count": self.count,
            "maximum": self.maximum,
            "remaining": self.remaining,
            "over_by": self.over_by,
            "maximum_expression": self.maximum_expression,
            "maximum_display": self.maximum_display,
            "inputs": self.inputs,
            "where": self.where,
        }



def _format_limit_message(template: str, **values: Any) -> str:
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def _matches_where(entity, where: dict[str, Any] | None) -> bool:
    if not where:
        return True

    tags = where.get("tags")
    if tags:
        required = [tags] if isinstance(tags, str) else tags
        if not isinstance(required, list):
            return False
        entity_tags = set(entity.tags or [])
        if any(not isinstance(tag, str) or tag not in entity_tags for tag in required):
            return False

    metadata = where.get("metadata")
    if metadata:
        if not isinstance(metadata, dict):
            return False
        for key, expected in metadata.items():
            if entity.data.get(key) != expected:
                return False

    return True


def _count_selected(field, value: Any, compendium, where: dict[str, Any] | None) -> int:
    if not isinstance(value, list):
        return 0

    if not where:
        return len(value)

    if not field.entity:
        return 0

    count = 0
    for entity_id in value:
        entity = compendium.get(field.entity, str(entity_id))
        if entity is not None and _matches_where(entity, where):
            count += 1
    return count


def validate_limit_schema(schema, engine: RuleEngine) -> list[RuleIssue]:
    issues: list[RuleIssue] = []

    for limit_id, definition in engine.limits.items():
        field = schema.fields.get(definition.field)
        if field is None:
            # load_rule_engine normally catches this, but keep this validator
            # useful if called independently.
            issues.append(
                RuleIssue(
                    "error",
                    f"Limit references unknown field {definition.field!r}.",
                    limit_id,
                )
            )
            continue

        if definition.usage is None and field.type not in {"multi_reference", "collection"}:
            issues.append(
                RuleIssue(
                    "error",
                    "Count limits require a multi_reference or collection field; use usage for calculated limits.",
                    limit_id,
                )
            )

        where = definition.where
        if not where:
            continue

        if field.type != "multi_reference" or not field.entity:
            issues.append(
                RuleIssue(
                    "error",
                    "Filtered limits currently require a multi_reference field with an entity type.",
                    limit_id,
                )
            )
            continue

        unknown_keys = sorted(set(where) - {"tags", "metadata"})
        if unknown_keys:
            issues.append(
                RuleIssue(
                    "error",
                    "Unsupported where key(s): " + ", ".join(unknown_keys),
                    limit_id,
                )
            )

        tags = where.get("tags")
        if tags is not None:
            if isinstance(tags, str):
                tags = [tags]
            if not isinstance(tags, list) or not all(
                isinstance(tag, str) and tag.strip() for tag in tags
            ):
                issues.append(
                    RuleIssue(
                        "error",
                        "where.tags must be a string or list of non-empty strings.",
                        limit_id,
                    )
                )

        metadata = where.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            issues.append(
                RuleIssue(
                    "error",
                    "where.metadata must be a mapping/object.",
                    limit_id,
                )
            )

    return issues


def evaluate_limits(
    schema,
    compendium,
    data: dict[str, Any],
    engine: RuleEngine,
) -> tuple[list[LimitResult], list[RuleIssue]]:
    if not engine.limits:
        return [], []

    modifiers = resolve_compendium_modifiers(
        schema,
        compendium,
        data,
        engine,
    )
    labels = {
        field_id: field.label
        for field_id, field in schema.fields.items()
    }
    for modifier_id, modifier in engine.modifiers.items():
        labels[modifier_id] = modifier.label

    results: list[LimitResult] = []
    issues: list[RuleIssue] = []

    for limit_id, definition in engine.limits.items():
        field = schema.fields.get(definition.field)
        if field is None:
            continue

        if definition.usage is None:
            count = _count_selected(
                field,
                data.get(definition.field),
                compendium,
                definition.where,
            )
        else:
            try:
                raw_usage = engine.evaluate_expression(
                    definition.usage,
                    data,
                    modifiers=modifiers,
                )
            except Exception as exc:
                issues.append(RuleIssue("error", f"Could not evaluate usage: {exc}", limit_id))
                raw_usage = 0

            if isinstance(raw_usage, bool) or not isinstance(raw_usage, (int, float)):
                issues.append(RuleIssue("error", "Usage expression must evaluate to a number.", limit_id))
                count = 0
            elif float(raw_usage).is_integer() and raw_usage >= 0:
                count = int(raw_usage)
            else:
                issues.append(RuleIssue("error", "Usage expression must evaluate to a non-negative whole number.", limit_id))
                count = 0

        try:
            raw_maximum = engine.evaluate_expression(
                definition.maximum,
                data,
                modifiers=modifiers,
            )
        except Exception as exc:
            issues.append(
                RuleIssue(
                    "error",
                    f"Could not evaluate maximum: {exc}",
                    limit_id,
                )
            )
            results.append(
                LimitResult(
                    limit_id,
                    definition.field,
                    definition.label,
                    count,
                    None,
                    None,
                    0,
                    definition.maximum,
                    engine.format_expression(definition.maximum, labels),
                    [],
                    definition.where,
                )
            )
            continue

        if isinstance(raw_maximum, bool) or not isinstance(raw_maximum, (int, float)):
            issues.append(
                RuleIssue(
                    "error",
                    "Maximum expression must evaluate to a number.",
                    limit_id,
                )
            )
            maximum = None
        elif float(raw_maximum).is_integer():
            maximum = int(raw_maximum)
            if maximum < 0:
                issues.append(
                    RuleIssue(
                        "error",
                        "Maximum expression must not evaluate below zero.",
                        limit_id,
                    )
                )
                maximum = None
        else:
            issues.append(
                RuleIssue(
                    "error",
                    "Maximum expression must evaluate to a whole number.",
                    limit_id,
                )
            )
            maximum = None

        inputs: list[dict[str, Any]] = []
        for dependency in engine.expression_dependencies(definition.maximum):
            try:
                value = engine.evaluate_expression(
                    dependency,
                    data,
                    modifiers=modifiers,
                )
            except Exception:
                value = data.get(dependency)
            inputs.append(
                {
                    "id": dependency,
                    "label": labels.get(
                        dependency,
                        dependency.replace("_", " ").title(),
                    ),
                    "value": value,
                }
            )

        remaining = None if maximum is None else maximum - count
        over_by = 0 if maximum is None else max(0, count - maximum)

        result = LimitResult(
            limit_id,
            definition.field,
            definition.label,
            count,
            maximum,
            remaining,
            over_by,
            definition.maximum,
            engine.format_expression(definition.maximum, labels),
            inputs,
            definition.where,
        )
        results.append(result)

        if maximum is None:
            continue

        if count > maximum:
            message = _format_limit_message(
                definition.message,
                count=count,
                maximum=maximum,
                remaining=remaining,
                over_by=over_by,
                label=definition.label,
            )
            issues.append(RuleIssue("error", message, limit_id))
        elif (
            remaining is not None
            and remaining > 0
            and (
                definition.require_full
                or (
                    definition.warn_at_remaining is not None
                    and remaining <= definition.warn_at_remaining
                )
            )
        ):
            warning_message = definition.warning_message or (
                "{label}: {count} of {maximum} selected; "
                "{remaining} remaining."
            )
            issues.append(
                RuleIssue(
                    "warning",
                    _format_limit_message(
                        warning_message,
                        count=count,
                        maximum=maximum,
                        remaining=remaining,
                        over_by=0,
                        label=definition.label,
                    ),
                    limit_id,
                )
            )

    return results, issues
