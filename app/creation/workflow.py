from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re

import yaml

from app.characters.schema import CharacterSchema


CREATION_FORMAT_VERSION = 1
STEP_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


@dataclass(slots=True)
class CreationIssue:
    severity: str
    message: str
    field: str | None = None

    def format(self) -> str:
        if self.field:
            return f"{self.severity.upper()}: {self.field}: {self.message}"
        return f"{self.severity.upper()}: {self.message}"


@dataclass(slots=True)
class CreationStep:
    id: str
    title: str
    fields: list[str]
    description: str = ""
    lock_after: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CreationWorkflow:
    path: Path
    version: int
    title: str
    steps: list[CreationStep]
    final_changes: dict[str, str]
    raw: dict[str, Any]

    def field_ids(self) -> list[str]:
        result: list[str] = []
        for step in self.steps:
            result.extend(step.fields)
        return result

    def core_field_ids(self) -> list[str]:
        result: list[str] = []
        for step in self.steps:
            for field_id in step.lock_after:
                if field_id not in result:
                    result.append(field_id)
        return result

    def step(self, step_id: str) -> CreationStep | None:
        for item in self.steps:
            if item.id == step_id:
                return item
        return None


def load_creation_workflow(
    path: Path | str,
    *,
    schema: CharacterSchema,
) -> tuple[CreationWorkflow | None, list[CreationIssue]]:
    path = Path(path)
    issues: list[CreationIssue] = []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [CreationIssue("error", "Creation workflow file does not exist.")]
    except yaml.YAMLError as exc:
        return None, [CreationIssue("error", f"Invalid YAML: {exc}")]
    except OSError as exc:
        return None, [CreationIssue("error", f"Could not read creation workflow: {exc}")]

    if not isinstance(raw, dict):
        return None, [CreationIssue("error", "Creation workflow root must be a mapping/object.")]

    version = raw.get("version", CREATION_FORMAT_VERSION)
    if not isinstance(version, int) or version < 1:
        issues.append(CreationIssue("error", "version must be a positive integer.", "version"))
        version = CREATION_FORMAT_VERSION
    elif version != CREATION_FORMAT_VERSION:
        issues.append(CreationIssue("error", f"Unsupported creation workflow version {version}; this TTL build supports version {CREATION_FORMAT_VERSION}.", "version"))

    title = raw.get("title", "Create Character")
    if not isinstance(title, str) or not title.strip():
        issues.append(CreationIssue("error", "title must be a non-empty string.", "title"))
        title = "Create Character"

    raw_final_changes = raw.get("final_changes", {})
    final_changes: dict[str, str] = {}
    if raw_final_changes is None:
        raw_final_changes = {}
    if not isinstance(raw_final_changes, dict):
        issues.append(
            CreationIssue(
                "error",
                "final_changes must be a mapping of character fields to rule expressions.",
                "final_changes",
            )
        )
        raw_final_changes = {}
    for field_id, expression in raw_final_changes.items():
        location = f"final_changes.{field_id}"
        if not isinstance(field_id, str) or field_id not in schema.fields:
            issues.append(
                CreationIssue("error", f"Unknown character field {field_id!r}.", location)
            )
            continue
        if schema.fields[field_id].type == "calculated":
            issues.append(
                CreationIssue("error", "Calculated fields cannot be final-change targets.", location)
            )
            continue
        if not isinstance(expression, str) or not expression.strip():
            issues.append(
                CreationIssue("error", "Final change must be a non-empty rule expression.", location)
            )
            continue
        final_changes[field_id] = expression.strip()

    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        issues.append(CreationIssue("error", "steps must be a non-empty list.", "steps"))
        raw_steps = []

    steps: list[CreationStep] = []
    seen_step_ids: set[str] = set()
    workflow_fields: list[str] = []
    locked_once: set[str] = set()

    for index, definition in enumerate(raw_steps):
        location = f"steps[{index}]"
        if not isinstance(definition, dict):
            issues.append(CreationIssue("error", "Step must be a mapping/object.", location))
            continue

        step_id = definition.get("id")
        if not isinstance(step_id, str) or not STEP_ID_RE.fullmatch(step_id):
            issues.append(CreationIssue("error", "Step id is invalid.", f"{location}.id"))
            continue
        if step_id in seen_step_ids:
            issues.append(CreationIssue("error", "Duplicate step id.", f"{location}.id"))
            continue
        seen_step_ids.add(step_id)

        step_title = definition.get("title", step_id.replace("_", " ").title())
        if not isinstance(step_title, str) or not step_title.strip():
            issues.append(CreationIssue("error", "Step title must be non-empty.", f"{location}.title"))
            step_title = step_id

        description = definition.get("description", "")
        if description is None: description = ""
        if not isinstance(description, str):
            issues.append(CreationIssue("error", "description must be a string.", f"{location}.description"))
            description = ""

        fields = definition.get("fields")
        if not isinstance(fields, list) or not fields:
            issues.append(CreationIssue("error", "fields must be a non-empty list.", f"{location}.fields"))
            fields = []

        clean_fields: list[str] = []
        seen_fields: set[str] = set()
        for field_index, field_id in enumerate(fields):
            field_location = f"{location}.fields[{field_index}]"
            if not isinstance(field_id, str) or not field_id:
                issues.append(CreationIssue("error", "Field id must be a non-empty string.", field_location)); continue
            if field_id not in schema.fields:
                issues.append(CreationIssue("error", f"Unknown character field {field_id!r}.", field_location)); continue
            if field_id in seen_fields:
                issues.append(CreationIssue("error", "Field is repeated within this step.", field_location)); continue
            if schema.fields[field_id].type == "calculated":
                issues.append(CreationIssue("error", "Calculated fields cannot be direct creation inputs.", field_location)); continue
            seen_fields.add(field_id); clean_fields.append(field_id); workflow_fields.append(field_id)

        raw_lock_after = definition.get("lock_after", [])
        if raw_lock_after is None: raw_lock_after = []
        if not isinstance(raw_lock_after, list):
            issues.append(CreationIssue("error", "lock_after must be a list of field ids.", f"{location}.lock_after")); raw_lock_after=[]
        clean_lock_after: list[str] = []
        for lock_index, field_id in enumerate(raw_lock_after):
            lock_location=f"{location}.lock_after[{lock_index}]"
            if not isinstance(field_id, str) or not field_id:
                issues.append(CreationIssue("error", "Locked field id must be a non-empty string.", lock_location)); continue
            if field_id not in clean_fields:
                issues.append(CreationIssue("error", "lock_after fields must be inputs in the same creation step.", lock_location)); continue
            if field_id in clean_lock_after:
                issues.append(CreationIssue("error", "Field is repeated in lock_after.", lock_location)); continue
            if field_id in locked_once:
                issues.append(CreationIssue("error", "Field is already locked by an earlier creation step.", lock_location)); continue
            clean_lock_after.append(field_id); locked_once.add(field_id)

        steps.append(CreationStep(id=step_id, title=step_title.strip(), description=description.strip(), fields=clean_fields, lock_after=clean_lock_after, raw=dict(definition)))

    duplicate_workflow_fields = sorted(field_id for field_id in set(workflow_fields) if workflow_fields.count(field_id) > 1)
    for field_id in duplicate_workflow_fields:
        issues.append(CreationIssue("error", "Character field appears in more than one creation step.", f"fields.{field_id}"))

    workflow_field_set=set(workflow_fields)
    for field_id, definition in schema.fields.items():
        if not definition.required or "default" in definition.raw: continue
        if field_id not in workflow_field_set:
            issues.append(CreationIssue("error", "Required character field has no default and is not included in the creation workflow.", f"fields.{field_id}"))

    if any(issue.severity == "error" for issue in issues):
        return None, issues

    return CreationWorkflow(
        path=path,
        version=version,
        title=title.strip(),
        steps=steps,
        final_changes=final_changes,
        raw=raw,
    ), issues
