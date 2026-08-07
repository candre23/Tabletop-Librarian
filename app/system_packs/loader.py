from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re

import yaml


PACK_FORMAT_VERSION = 1
PACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(slots=True)
class PackIssue:
    severity: str
    message: str
    file: str | None = None
    field: str | None = None

    def format(self) -> str:
        location = ""
        if self.file:
            location = self.file
            if self.field:
                location += f":{self.field}"
            location += ": "
        return f"{self.severity.upper()}: {location}{self.message}"


@dataclass(slots=True)
class PackManifest:
    id: str
    name: str
    version: str
    pack_format: int
    description: str = ""
    requires_ttl: str | None = None
    character_schema: str = "character.yaml"
    rules: str | None = None
    creation: str | None = None
    advancement: str | None = None
    compendium: list[str] = field(default_factory=list)
    layouts: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SystemPack:
    root: Path
    manifest: PackManifest | None
    issues: list[PackIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.manifest is not None and not any(
            issue.severity == "error" for issue in self.issues
        )


def _safe_yaml(path: Path) -> tuple[Any, list[PackIssue]]:
    issues: list[PackIssue] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError:
        return None, [
            PackIssue("error", "Required file does not exist.", file=path.name)
        ]
    except yaml.YAMLError as exc:
        return None, [
            PackIssue("error", f"Invalid YAML: {exc}", file=path.name)
        ]
    except OSError as exc:
        return None, [
            PackIssue("error", f"Could not read file: {exc}", file=path.name)
        ]

    return data, issues


def _is_safe_relative_path(value: str) -> bool:
    if not value:
        return False

    candidate = Path(value)

    if candidate.is_absolute():
        return False

    return all(part not in ("", ".", "..") for part in candidate.parts)


def _validate_declared_file(
    root: Path,
    relative_path: str | None,
    label: str,
    issues: list[PackIssue],
    required: bool = False,
) -> None:
    if not relative_path:
        if required:
            issues.append(
                PackIssue(
                    "error",
                    f"{label} is required.",
                    file="manifest.yaml",
                    field=label,
                )
            )
        return

    if not isinstance(relative_path, str) or not _is_safe_relative_path(relative_path):
        issues.append(
            PackIssue(
                "error",
                "Path must be a safe relative path inside the System Pack.",
                file="manifest.yaml",
                field=label,
            )
        )
        return

    target = (root / relative_path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        issues.append(
            PackIssue(
                "error",
                "Path escapes the System Pack directory.",
                file="manifest.yaml",
                field=label,
            )
        )
        return

    if not target.is_file():
        issues.append(
            PackIssue(
                "error",
                f"Declared file does not exist: {relative_path}",
                file="manifest.yaml",
                field=label,
            )
        )


def _parse_manifest(root: Path) -> tuple[PackManifest | None, list[PackIssue]]:
    manifest_path = root / "manifest.yaml"
    raw, issues = _safe_yaml(manifest_path)

    if issues:
        return None, issues

    if not isinstance(raw, dict):
        return None, [
            PackIssue(
                "error",
                "Manifest root must be a YAML mapping/object.",
                file="manifest.yaml",
            )
        ]

    required = ("id", "name", "version", "pack_format")
    for field_name in required:
        if field_name not in raw:
            issues.append(
                PackIssue(
                    "error",
                    "Required field is missing.",
                    file="manifest.yaml",
                    field=field_name,
                )
            )

    if issues:
        return None, issues

    pack_id = raw.get("id")
    name = raw.get("name")
    version = raw.get("version")
    pack_format = raw.get("pack_format")

    if not isinstance(pack_id, str) or not PACK_ID_RE.fullmatch(pack_id):
        issues.append(
            PackIssue(
                "error",
                "Pack id must contain only lowercase letters, digits, '.', '_' or '-'.",
                file="manifest.yaml",
                field="id",
            )
        )

    if not isinstance(name, str) or not name.strip():
        issues.append(
            PackIssue(
                "error",
                "Pack name must be a non-empty string.",
                file="manifest.yaml",
                field="name",
            )
        )

    if not isinstance(version, str) or not version.strip():
        issues.append(
            PackIssue(
                "error",
                "Pack version must be a non-empty string.",
                file="manifest.yaml",
                field="version",
            )
        )

    if not isinstance(pack_format, int):
        issues.append(
            PackIssue(
                "error",
                "pack_format must be an integer.",
                file="manifest.yaml",
                field="pack_format",
            )
        )
    elif pack_format != PACK_FORMAT_VERSION:
        issues.append(
            PackIssue(
                "error",
                f"Unsupported pack format {pack_format}; this TTL build supports "
                f"format {PACK_FORMAT_VERSION}.",
                file="manifest.yaml",
                field="pack_format",
            )
        )

    character_schema = raw.get("character_schema", "character.yaml")
    rules = raw.get("rules")
    creation = raw.get("creation")
    advancement = raw.get("advancement")
    compendium = raw.get("compendium", [])
    layouts = raw.get("layouts", {})

    if not isinstance(compendium, list) or not all(
        isinstance(item, str) for item in compendium
    ):
        issues.append(
            PackIssue(
                "error",
                "compendium must be a list of relative file paths.",
                file="manifest.yaml",
                field="compendium",
            )
        )
        compendium = []

    if not isinstance(layouts, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in layouts.items()
    ):
        issues.append(
            PackIssue(
                "error",
                "layouts must be a mapping of layout names to relative file paths.",
                file="manifest.yaml",
                field="layouts",
            )
        )
        layouts = {}

    if issues:
        return None, issues

    manifest = PackManifest(
        id=pack_id,
        name=name.strip(),
        version=version.strip(),
        pack_format=pack_format,
        description=str(raw.get("description") or "").strip(),
        requires_ttl=(
            str(raw["requires_ttl"]).strip()
            if raw.get("requires_ttl") is not None
            else None
        ),
        character_schema=character_schema,
        rules=rules,
        creation=creation,
        advancement=advancement,
        compendium=list(compendium),
        layouts=dict(layouts),
        raw=raw,
    )

    return manifest, issues


def _validate_character_schema(root: Path, relative_path: str) -> list[PackIssue]:
    from app.characters.schema import load_character_schema

    schema, schema_issues = load_character_schema(root / relative_path)
    return [
        PackIssue(issue.severity, issue.message, file=relative_path, field=issue.field)
        for issue in schema_issues
    ]


def validate_system_pack(root: Path | str) -> SystemPack:
    root = Path(root).expanduser().resolve()
    manifest, issues = _parse_manifest(root)

    pack = SystemPack(root=root, manifest=manifest, issues=list(issues))

    if manifest is None:
        return pack

    _validate_declared_file(
        root,
        manifest.character_schema,
        "character_schema",
        pack.issues,
        required=True,
    )
    _validate_declared_file(root, manifest.rules, "rules", pack.issues)
    _validate_declared_file(root, manifest.creation, "creation", pack.issues)
    _validate_declared_file(root, manifest.advancement, "advancement", pack.issues)

    for index, item in enumerate(manifest.compendium):
        _validate_declared_file(
            root,
            item,
            f"compendium[{index}]",
            pack.issues,
        )

    for layout_name, item in manifest.layouts.items():
        _validate_declared_file(
            root,
            item,
            f"layouts.{layout_name}",
            pack.issues,
        )

    if not any(
        issue.severity == "error"
        and issue.field == "character_schema"
        for issue in pack.issues
    ):
        pack.issues.extend(
            _validate_character_schema(root, manifest.character_schema)
        )

    character_layout_path = manifest.layouts.get("character")
    if character_layout_path and not any(
        issue.severity == "error"
        and issue.field == "layouts.character"
        for issue in pack.issues
    ):
        from app.characters.layout import load_character_layout
        from app.characters.schema import load_character_schema

        layout_schema, _layout_schema_issues = load_character_schema(
            root / manifest.character_schema
        )
        if layout_schema is not None:
            _layout, layout_issues = load_character_layout(
                root / character_layout_path,
                schema=layout_schema,
            )
            for issue in layout_issues:
                pack.issues.append(
                    PackIssue(
                        issue.severity,
                        issue.message,
                        file=character_layout_path,
                        field=issue.field,
                    )
                )

    if manifest.creation and not any(
        issue.severity == "error" and issue.field == "creation"
        for issue in pack.issues
    ):
        from app.characters.schema import load_character_schema
        from app.creation import load_creation_workflow

        creation_schema, _creation_schema_issues = load_character_schema(
            root / manifest.character_schema
        )
        if creation_schema is not None:
            _workflow, creation_issues = load_creation_workflow(
                root / manifest.creation,
                schema=creation_schema,
            )
            for issue in creation_issues:
                pack.issues.append(
                    PackIssue(
                        issue.severity,
                        issue.message,
                        file=manifest.creation,
                        field=issue.field,
                    )
                )

    if manifest.advancement and not any(
        issue.severity == "error" and issue.field == "advancement"
        for issue in pack.issues
    ):
        from app.characters.schema import load_character_schema
        from app.rules import load_rule_engine
        from app.advancement import load_advancement_workflow
        advancement_schema, _ = load_character_schema(root / manifest.character_schema)
        if advancement_schema is not None:
            advancement_engine, _ = load_rule_engine(root / manifest.rules if manifest.rules else None, known_fields=set(advancement_schema.fields))
            if advancement_engine is not None:
                _advancement, advancement_issues = load_advancement_workflow(root / manifest.advancement, schema=advancement_schema, engine=advancement_engine)
                for issue in advancement_issues:
                    pack.issues.append(PackIssue(issue.severity, issue.message, file=manifest.advancement, field=issue.field))

    if manifest.rules and not any(
        issue.severity == "error" and issue.field == "rules"
        for issue in pack.issues
    ):
        from app.characters.schema import load_character_schema
        from app.rules import load_rule_engine
        schema, _schema_issues = load_character_schema(
            root / manifest.character_schema
        )
        if schema is not None:
            _engine, rule_issues = load_rule_engine(
                root / manifest.rules,
                known_fields=set(schema.fields),
            )
            for issue in rule_issues:
                pack.issues.append(
                    PackIssue(
                        issue.severity,
                        issue.message,
                        file=manifest.rules,
                        field=issue.rule_id,
                    )
                )

    from app.compendium import load_compendium
    from app.characters.schema import load_character_schema

    compendium, compendium_issues = load_compendium(
        root,
        manifest.compendium,
    )

    for issue in compendium_issues:
        pack.issues.append(
            PackIssue(
                issue.severity,
                issue.message,
                file=issue.file,
                field=".".join(
                    part
                    for part in (
                        issue.entity_type,
                        issue.entity_id,
                        issue.field,
                    )
                    if part
                )
                or None,
            )
        )

    if compendium is not None:
        schema, _schema_issues = load_character_schema(
            root / manifest.character_schema
        )

        if schema is not None:
            from app.rules import (
                load_rule_engine,
                validate_compendium_effects,
                validate_compendium_eligibility,
                validate_limit_schema,
            )

            effect_engine, effect_rule_issues = load_rule_engine(
                root / manifest.rules if manifest.rules else None,
                known_fields=set(schema.fields),
            )

            if effect_engine is not None:
                for issue in validate_compendium_effects(
                    compendium,
                    effect_engine,
                    schema=schema,
                ):
                    pack.issues.append(
                        PackIssue(
                            issue.severity,
                            issue.message,
                            file=manifest.rules or "compendium",
                            field=issue.rule_id,
                        )
                    )

                for issue in validate_compendium_eligibility(
                    compendium,
                    effect_engine,
                    schema,
                ):
                    pack.issues.append(
                        PackIssue(
                            issue.severity,
                            issue.message,
                            file="compendium",
                            field=issue.rule_id,
                        )
                    )

                for issue in validate_limit_schema(schema, effect_engine):
                    pack.issues.append(
                        PackIssue(
                            issue.severity,
                            issue.message,
                            file=manifest.rules or "rules",
                            field=issue.rule_id,
                        )
                    )

            for field_id, field in schema.fields.items():
                if field.type == "collection":
                    for item_id, item_field in (field.item_schema or {}).items():
                        if item_field.type != "reference" or not item_field.entity:
                            continue
                        if not compendium.has_type(item_field.entity):
                            pack.issues.append(
                                PackIssue(
                                    "error",
                                    f"Unknown compendium entity type {item_field.entity!r}.",
                                    file=manifest.character_schema,
                                    field=f"{field_id}.item_schema.{item_id}.entity",
                                )
                            )
                    continue

                if field.type not in {
                    "reference",
                    "multi_reference",
                }:
                    continue

                if not field.entity:
                    continue

                if not compendium.has_type(field.entity):
                    pack.issues.append(
                        PackIssue(
                            "error",
                            f"Unknown compendium entity type {field.entity!r}.",
                            file=manifest.character_schema,
                            field=f"{field_id}.entity",
                        )
                    )
                    continue

                if "default" not in field.raw:
                    continue

                default = field.default
                if field.type == "reference":
                    values = [] if default in (None, "") else [default]
                elif field.type == "multi_reference":
                    values = default if isinstance(default, list) else []
                else:
                    values = []

                for value in values:
                    if compendium.get(field.entity, str(value)) is None:
                        pack.issues.append(
                            PackIssue(
                                "error",
                                f"Default references unknown entity "
                                f"{field.entity}:{value}.",
                                file=manifest.character_schema,
                                field=f"{field_id}.default",
                            )
                        )

    return pack


def load_system_pack(root: Path | str) -> SystemPack:
    """Load and validate one System Pack directory."""
    return validate_system_pack(root)


def discover_system_packs(base_dir: Path | str) -> list[SystemPack]:
    base_dir = Path(base_dir).expanduser()

    if not base_dir.exists():
        return []

    packs: list[SystemPack] = []

    for child in sorted(base_dir.iterdir(), key=lambda path: path.name.casefold()):
        if not child.is_dir():
            continue
        if not (child / "manifest.yaml").is_file():
            continue
        packs.append(validate_system_pack(child))

    return packs
