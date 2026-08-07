from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.rules.engine import RuleEngine, RuleEngineError, RuleIssue


@dataclass(slots=True)
class EligibilityResult:
    eligible: bool
    message: str | None = None


def _eligibility_definition(entity) -> tuple[str | None, str | None]:
    raw = entity.data.get("eligibility")
    if raw is None:
        return None, None

    if isinstance(raw, str):
        return raw, "Requirements are not met."

    if isinstance(raw, dict):
        rule = raw.get("rule")
        message = raw.get("message")
        if isinstance(rule, str):
            return rule, str(message).strip() if message else "Requirements are not met."

    return None, None


def validate_compendium_eligibility(
    compendium,
    engine: RuleEngine,
    schema,
) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    allowed_fields = {
        field_id
        for field_id, field in schema.fields.items()
        if field.type != "calculated"
    }

    for entity_type, bucket in compendium.entities.items():
        for entity_id, entity in bucket.items():
            raw = entity.data.get("eligibility")
            if raw is None:
                continue

            rule, _message = _eligibility_definition(entity)
            rule_id = f"{entity_type}:{entity_id}"

            if rule is None:
                issues.append(
                    RuleIssue(
                        "error",
                        "eligibility must be a non-empty expression string or a "
                        "mapping with rule/message.",
                        rule_id,
                    )
                )
                continue

            try:
                dependencies = engine.condition_dependencies(rule)
            except RuleEngineError as exc:
                issues.append(RuleIssue("error", str(exc), rule_id))
                continue

            unknown = sorted(dependencies - allowed_fields)
            if unknown:
                issues.append(
                    RuleIssue(
                        "error",
                        "Eligibility expressions may currently reference only "
                        "non-calculated character fields. Unknown/unsupported: "
                        + ", ".join(unknown),
                        rule_id,
                    )
                )

    return issues


def evaluate_entity_eligibility(
    entity,
    data: dict[str, Any],
    engine: RuleEngine,
) -> EligibilityResult:
    rule, message = _eligibility_definition(entity)
    if rule is None:
        return EligibilityResult(True, None)

    try:
        eligible = bool(engine.evaluate_condition(rule, data))
    except RuleEngineError as exc:
        return EligibilityResult(False, f"Eligibility evaluation failed: {exc}")

    return EligibilityResult(eligible, None if eligible else message)


def reference_eligibility(
    schema,
    compendium,
    data: dict[str, Any],
    engine: RuleEngine,
    field_ids=None,
) -> dict[str, dict[str, dict[str, Any]]]:
    allowed = set(field_ids) if field_ids is not None else None
    output: dict[str, dict[str, dict[str, Any]]] = {}

    for field_id, field in schema.fields.items():
        if field.type not in {"reference", "multi_reference"} or not field.entity:
            continue
        if allowed is not None and field_id not in allowed:
            continue

        field_map: dict[str, dict[str, Any]] = {}
        for entity in compendium.all(field.entity):
            result = evaluate_entity_eligibility(entity, data, engine)
            field_map[entity.id] = {
                "eligible": result.eligible,
                "message": result.message,
            }
        output[field_id] = field_map

    return output


def selected_eligibility_issues(
    schema,
    compendium,
    data: dict[str, Any],
    engine: RuleEngine,
    field_ids=None,
) -> list[RuleIssue]:
    allowed = set(field_ids) if field_ids is not None else None
    issues: list[RuleIssue] = []

    for field_id, field in schema.fields.items():
        if field.type not in {"reference", "multi_reference"} or not field.entity:
            continue
        if allowed is not None and field_id not in allowed:
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
            result = evaluate_entity_eligibility(entity, data, engine)
            if not result.eligible:
                issues.append(
                    RuleIssue(
                        "error",
                        f"{field.label}: {entity.name} is not eligible. "
                        f"{result.message or 'Requirements are not met.'}",
                        f"{field_id}:{entity.id}",
                    )
                )

    return issues
