from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import copy
from functools import lru_cache
import re
import yaml

ENTITY_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
ENTITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


@dataclass(slots=True)
class CompendiumIssue:
    severity: str
    message: str
    file: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    field: str | None = None

    def format(self) -> str:
        parts = [p for p in (self.file, self.entity_type, self.entity_id, self.field) if p]
        prefix = ": ".join(parts)
        return f"{self.severity.upper()}: {prefix + ': ' if prefix else ''}{self.message}"


@dataclass(slots=True)
class CompendiumEntity:
    entity_type: str
    id: str
    name: str
    tags: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    source_file: str | None = None


@dataclass(slots=True)
class Compendium:
    entities: dict[str, dict[str, CompendiumEntity]] = field(default_factory=dict)

    def get(self, entity_type: str, entity_id: str) -> CompendiumEntity | None:
        return self.entities.get(entity_type, {}).get(entity_id)

    def all(self, entity_type: str) -> list[CompendiumEntity]:
        return sorted(
            self.entities.get(entity_type, {}).values(),
            key=lambda item: item.name.casefold(),
        )

    def has_type(self, entity_type: str) -> bool:
        return entity_type in self.entities


def _load_file(root: Path, relative_path: str, compendium: Compendium, issues: list[CompendiumIssue]) -> None:
    path = root / relative_path
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(CompendiumIssue("error", f"Could not read YAML: {exc}", file=relative_path))
        return

    if not isinstance(raw, dict):
        issues.append(CompendiumIssue("error", "Compendium root must be a mapping/object.", file=relative_path))
        return

    entity_type = raw.get("entity")
    entries = raw.get("entries")

    if not isinstance(entity_type, str) or not ENTITY_TYPE_RE.fullmatch(entity_type):
        issues.append(CompendiumIssue("error", "Invalid entity type.", file=relative_path, field="entity"))
        return

    if not isinstance(entries, list):
        issues.append(CompendiumIssue("error", "entries must be a list.", file=relative_path, entity_type=entity_type))
        return

    bucket = compendium.entities.setdefault(entity_type, {})

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append(CompendiumIssue("error", "Entry must be a mapping/object.", file=relative_path, entity_type=entity_type, field=f"entries[{index}]"))
            continue

        entity_id = entry.get("id")
        name = entry.get("name")

        if not isinstance(entity_id, str) or not ENTITY_ID_RE.fullmatch(entity_id):
            issues.append(CompendiumIssue("error", "Invalid entity id.", file=relative_path, entity_type=entity_type, field=f"entries[{index}].id"))
            continue

        if not isinstance(name, str) or not name.strip():
            issues.append(CompendiumIssue("error", "Entity name must be non-empty.", file=relative_path, entity_type=entity_type, entity_id=entity_id))
            continue

        if entity_id in bucket:
            issues.append(CompendiumIssue("error", f"Duplicate entity id; already defined in {bucket[entity_id].source_file}.", file=relative_path, entity_type=entity_type, entity_id=entity_id))
            continue

        tags = entry.get("tags", []) or []
        if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
            issues.append(CompendiumIssue("error", "tags must be a list of non-empty strings.", file=relative_path, entity_type=entity_type, entity_id=entity_id))
            tags = []

        bucket[entity_id] = CompendiumEntity(
            entity_type=entity_type,
            id=entity_id,
            name=name.strip(),
            tags=[tag.strip() for tag in tags],
            data=copy.deepcopy(entry),
            source_file=relative_path,
        )


def _validate_references(compendium: Compendium, issues: list[CompendiumIssue]) -> None:
    for entity_type, bucket in compendium.entities.items():
        for entity_id, entity in bucket.items():
            refs = entity.data.get("references", []) or []
            if not isinstance(refs, list):
                issues.append(CompendiumIssue("error", "references must be a list.", file=entity.source_file, entity_type=entity_type, entity_id=entity_id))
                continue

            for index, ref in enumerate(refs):
                if not isinstance(ref, dict):
                    issues.append(CompendiumIssue("error", "Reference must be a mapping/object.", file=entity.source_file, entity_type=entity_type, entity_id=entity_id, field=f"references[{index}]"))
                    continue

                target_type = ref.get("entity")
                target_id = ref.get("id")

                if not isinstance(target_type, str) or not isinstance(target_id, str):
                    issues.append(CompendiumIssue("error", "Reference requires entity and id.", file=entity.source_file, entity_type=entity_type, entity_id=entity_id, field=f"references[{index}]"))
                    continue

                if compendium.get(target_type, target_id) is None:
                    issues.append(CompendiumIssue("error", f"Unknown reference {target_type}:{target_id}.", file=entity.source_file, entity_type=entity_type, entity_id=entity_id, field=f"references[{index}]"))


def _compendium_fingerprint(root: Path, declared_files: tuple[str, ...]) -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    for relative_path in declared_files:
        path = root / relative_path
        try:
            stat = path.stat()
            rows.append((relative_path, stat.st_mtime_ns, stat.st_size))
        except OSError:
            rows.append((relative_path, -1, -1))
    return tuple(rows)


@lru_cache(maxsize=32)
def _load_compendium_cached(
    root_text: str,
    declared_files: tuple[str, ...],
    fingerprint: tuple[tuple[str, int, int], ...],
) -> tuple[Compendium | None, tuple[CompendiumIssue, ...]]:
    del fingerprint  # cache key only
    root = Path(root_text)
    compendium = Compendium()
    issues: list[CompendiumIssue] = []

    for relative_path in declared_files:
        _load_file(root, relative_path, compendium, issues)

    _validate_references(compendium, issues)

    if any(issue.severity == "error" for issue in issues):
        return None, tuple(issues)

    return compendium, tuple(issues)


def load_compendium(root: Path | str, declared_files: list[str]) -> tuple[Compendium | None, list[CompendiumIssue]]:
    root = Path(root).expanduser().resolve()
    declared = tuple(declared_files)
    compendium, issues = _load_compendium_cached(
        str(root),
        declared,
        _compendium_fingerprint(root, declared),
    )
    return compendium, list(issues)
