from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import copy
import re
import yaml

FIELD_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")

SUPPORTED_FIELD_TYPES = {
    "text", "integer", "decimal", "boolean", "enum",
    "reference", "multi_reference", "collection", "object",
    "calculated", "resource", "notes",
}

COLLECTION_ITEM_TYPES = {
    "text", "integer", "decimal", "boolean", "enum",
    "reference", "notes",
}


@dataclass(slots=True)
class CharacterSchemaIssue:
    severity: str
    message: str
    field: str | None = None

    def format(self) -> str:
        return (
            f"{self.severity.upper()}: {self.field}: {self.message}"
            if self.field
            else f"{self.severity.upper()}: {self.message}"
        )


@dataclass(slots=True)
class CharacterField:
    id: str
    type: str
    label: str
    required: bool = False
    default: Any = None
    entity: str | None = None
    options: list[Any] = field(default_factory=list)
    item_schema: dict[str, "CharacterField"] | None = None
    minimum: float | int | None = None
    maximum: float | int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CharacterSchema:
    path: Path
    schema_version: int
    fields: dict[str, CharacterField]
    raw: dict[str, Any]

    def default_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field_id, definition in self.fields.items():
            if "default" in definition.raw:
                data[field_id] = copy.deepcopy(definition.default)
            elif definition.type in {"collection", "multi_reference"}:
                data[field_id] = []
            elif definition.type == "object":
                data[field_id] = {}
            elif definition.type == "boolean":
                data[field_id] = False
        return data


def default_collection_item(field: CharacterField) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for item_id, item in (field.item_schema or {}).items():
        if "default" in item.raw:
            row[item_id] = copy.deepcopy(item.default)
        elif item.type == "boolean":
            row[item_id] = False
    return row


def _type_matches(field_type: str, value: Any) -> bool:
    if value is None:
        return True
    if field_type in {"text", "notes", "reference"}:
        return isinstance(value, str)
    if field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if field_type == "decimal":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "enum":
        return isinstance(value, (str, int, float, bool))
    if field_type in {"multi_reference", "collection"}:
        return isinstance(value, list)
    if field_type == "object":
        return isinstance(value, dict)
    if field_type == "calculated":
        return True
    if field_type == "resource":
        return isinstance(value, (int, float, dict)) and not isinstance(value, bool)
    return False


def _parse_field(
    field_id: str,
    definition: Any,
    issues: list[CharacterSchemaIssue],
    *,
    path_prefix: str = "",
    collection_item: bool = False,
) -> CharacterField | None:
    field_path = f"{path_prefix}.{field_id}" if path_prefix else field_id

    if not isinstance(field_id, str) or not FIELD_ID_RE.fullmatch(field_id):
        issues.append(CharacterSchemaIssue("error", "Invalid field id.", field_path))
        return None

    if not isinstance(definition, dict):
        issues.append(
            CharacterSchemaIssue(
                "error",
                "Field definition must be a mapping/object.",
                field_path,
            )
        )
        return None

    field_type = definition.get("type")
    allowed_types = COLLECTION_ITEM_TYPES if collection_item else SUPPORTED_FIELD_TYPES
    if field_type not in allowed_types:
        message = (
            f"Unsupported collection item field type: {field_type!r}"
            if collection_item
            else f"Unknown field type: {field_type!r}"
        )
        issues.append(CharacterSchemaIssue("error", message, f"{field_path}.type"))
        return None

    required = definition.get("required", False)
    if not isinstance(required, bool):
        issues.append(
            CharacterSchemaIssue(
                "error",
                "required must be true or false.",
                f"{field_path}.required",
            )
        )
        required = False

    label = definition.get("label", field_id.replace("_", " ").title())
    if not isinstance(label, str) or not label.strip():
        issues.append(
            CharacterSchemaIssue(
                "error",
                "label must be a non-empty string.",
                f"{field_path}.label",
            )
        )
        label = field_id

    entity = definition.get("entity")
    if field_type in {"reference", "multi_reference"}:
        if entity is not None and (
            not isinstance(entity, str) or not entity.strip()
        ):
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    "entity must be a non-empty string.",
                    f"{field_path}.entity",
                )
            )

    options = definition.get("options", [])
    if field_type == "enum":
        if not isinstance(options, list) or not options:
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    "enum fields require a non-empty options list.",
                    f"{field_path}.options",
                )
            )
            options = []
    elif options is not None and not isinstance(options, list):
        issues.append(
            CharacterSchemaIssue(
                "error",
                "options must be a list.",
                f"{field_path}.options",
            )
        )
        options = []

    minimum = definition.get("min")
    maximum = definition.get("max")
    if minimum is not None and (
        not isinstance(minimum, (int, float)) or isinstance(minimum, bool)
    ):
        issues.append(
            CharacterSchemaIssue(
                "error",
                "min must be numeric.",
                f"{field_path}.min",
            )
        )
        minimum = None
    if maximum is not None and (
        not isinstance(maximum, (int, float)) or isinstance(maximum, bool)
    ):
        issues.append(
            CharacterSchemaIssue(
                "error",
                "max must be numeric.",
                f"{field_path}.max",
            )
        )
        maximum = None
    if minimum is not None and maximum is not None and minimum > maximum:
        issues.append(
            CharacterSchemaIssue(
                "error",
                "min cannot be greater than max.",
                field_path,
            )
        )

    default = copy.deepcopy(definition.get("default"))
    if "default" in definition:
        if not _type_matches(field_type, default):
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    f"Default value does not match field type {field_type!r}.",
                    field_path,
                )
            )
        elif (
            field_type == "enum"
            and default is not None
            and default not in options
        ):
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    "Default value is not present in enum options.",
                    field_path,
                )
            )

    item_schema: dict[str, CharacterField] | None = None
    if field_type == "collection":
        raw_item_schema = definition.get("item_schema")
        if not isinstance(raw_item_schema, dict) or not raw_item_schema:
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    "collection fields require a non-empty item_schema mapping.",
                    f"{field_path}.item_schema",
                )
            )
        else:
            item_schema = {}
            for item_id, item_definition in raw_item_schema.items():
                parsed = _parse_field(
                    item_id,
                    item_definition,
                    issues,
                    path_prefix=f"{field_path}.item_schema",
                    collection_item=True,
                )
                if parsed is not None:
                    item_schema[item_id] = parsed

    return CharacterField(
        id=field_id,
        type=field_type,
        label=label.strip(),
        required=required,
        default=default,
        entity=entity.strip() if isinstance(entity, str) else None,
        options=list(options) if isinstance(options, list) else [],
        item_schema=item_schema,
        minimum=minimum,
        maximum=maximum,
        raw=copy.deepcopy(definition),
    )


def load_character_schema(
    path: Path | str,
) -> tuple[CharacterSchema | None, list[CharacterSchemaIssue]]:
    path = Path(path)
    issues: list[CharacterSchemaIssue] = []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [
            CharacterSchemaIssue(
                "error",
                "Character schema file does not exist.",
            )
        ]
    except yaml.YAMLError as exc:
        return None, [
            CharacterSchemaIssue("error", f"Invalid YAML: {exc}")
        ]
    except OSError as exc:
        return None, [
            CharacterSchemaIssue(
                "error",
                f"Could not read schema: {exc}",
            )
        ]

    if not isinstance(raw, dict):
        return None, [
            CharacterSchemaIssue(
                "error",
                "Character schema root must be a mapping/object.",
            )
        ]

    schema_version = raw.get("schema_version", 1)
    if not isinstance(schema_version, int) or schema_version < 1:
        issues.append(
            CharacterSchemaIssue(
                "error",
                "schema_version must be a positive integer.",
                "schema_version",
            )
        )
        schema_version = 1

    raw_fields = raw.get("fields")
    if not isinstance(raw_fields, dict):
        return None, issues + [
            CharacterSchemaIssue(
                "error",
                "Character schema must contain a 'fields' mapping.",
                "fields",
            )
        ]

    fields: dict[str, CharacterField] = {}
    for field_id, definition in raw_fields.items():
        parsed = _parse_field(
            field_id,
            definition,
            issues,
        )
        if parsed is not None:
            fields[field_id] = parsed

    if any(issue.severity == "error" for issue in issues):
        return None, issues

    return CharacterSchema(
        path=path,
        schema_version=schema_version,
        fields=fields,
        raw=raw,
    ), issues


def _validate_scalar_field(
    definition: CharacterField,
    value: Any,
    field_path: str,
) -> list[CharacterSchemaIssue]:
    issues: list[CharacterSchemaIssue] = []

    if definition.required and (
        value is None
        or value == ""
    ):
        issues.append(
            CharacterSchemaIssue(
                "error",
                "Required field is missing.",
                field_path,
            )
        )
        return issues

    if not _type_matches(definition.type, value):
        issues.append(
            CharacterSchemaIssue(
                "error",
                f"Value does not match field type {definition.type!r}.",
                field_path,
            )
        )
        return issues

    if (
        definition.type == "enum"
        and value is not None
        and value not in definition.options
    ):
        issues.append(
            CharacterSchemaIssue(
                "error",
                "Value is not one of the allowed enum options.",
                field_path,
            )
        )

    if definition.type in {"integer", "decimal"} and value is not None:
        if definition.minimum is not None and value < definition.minimum:
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    f"Value must be >= {definition.minimum}.",
                    field_path,
                )
            )
        if definition.maximum is not None and value > definition.maximum:
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    f"Value must be <= {definition.maximum}.",
                    field_path,
                )
            )

    return issues


def validate_character_data(
    schema: CharacterSchema,
    data: dict[str, Any],
    *,
    reject_unknown_fields: bool = True,
) -> list[CharacterSchemaIssue]:
    issues: list[CharacterSchemaIssue] = []

    if not isinstance(data, dict):
        return [
            CharacterSchemaIssue(
                "error",
                "Character data must be a mapping/object.",
            )
        ]

    if reject_unknown_fields:
        for key in data:
            if key not in schema.fields:
                issues.append(
                    CharacterSchemaIssue(
                        "error",
                        "Unknown character field.",
                        key,
                    )
                )

    for field_id, definition in schema.fields.items():
        present = field_id in data
        value = data.get(field_id)

        if definition.required and (
            not present
            or value is None
            or value == ""
        ):
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    "Required field is missing.",
                    field_id,
                )
            )
            continue

        if not present:
            continue

        if definition.type != "collection":
            issues.extend(
                _validate_scalar_field(
                    definition,
                    value,
                    field_id,
                )
            )
            continue

        if not isinstance(value, list):
            issues.append(
                CharacterSchemaIssue(
                    "error",
                    "Value does not match field type 'collection'.",
                    field_id,
                )
            )
            continue

        item_schema = definition.item_schema or {}
        for index, row in enumerate(value):
            row_path = f"{field_id}[{index}]"
            if not isinstance(row, dict):
                issues.append(
                    CharacterSchemaIssue(
                        "error",
                        "Collection row must be a mapping/object.",
                        row_path,
                    )
                )
                continue

            if reject_unknown_fields:
                for item_key in row:
                    if item_key not in item_schema:
                        issues.append(
                            CharacterSchemaIssue(
                                "error",
                                "Unknown collection item field.",
                                f"{row_path}.{item_key}",
                            )
                        )

            for item_id, item_definition in item_schema.items():
                item_present = item_id in row
                item_value = row.get(item_id)
                item_path = f"{row_path}.{item_id}"

                if item_definition.required and (
                    not item_present
                    or item_value is None
                    or item_value == ""
                ):
                    issues.append(
                        CharacterSchemaIssue(
                            "error",
                            "Required field is missing.",
                            item_path,
                        )
                    )
                    continue

                if not item_present:
                    continue

                issues.extend(
                    _validate_scalar_field(
                        item_definition,
                        item_value,
                        item_path,
                    )
                )

    return issues
