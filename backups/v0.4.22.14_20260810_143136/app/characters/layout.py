from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re
import yaml

ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


@dataclass(slots=True)
class LayoutIssue:
    severity: str
    message: str
    field: str | None = None


@dataclass(slots=True)
class LayoutSection:
    id: str
    title: str
    fields: list[str]
    columns: int = 1
    description: str | None = None
    color: str | None = None
    span: int = 12
    field_options: dict[str, dict[str, Any]] = field(default_factory=dict)

    def display_for(self, field_id: str) -> str:
        return str(self.field_options.get(field_id, {}).get("display") or "default")

    def span_for(self, field_id: str) -> int:
        value = self.field_options.get(field_id, {}).get("span", 1)
        return value if isinstance(value, int) and value > 0 else 1


@dataclass(slots=True)
class LayoutTab:
    id: str
    title: str
    sections: list[LayoutSection] = field(default_factory=list)


@dataclass(slots=True)
class CharacterLayout:
    path: Path
    tabs: list[LayoutTab]
    raw: dict[str, Any]

    @property
    def field_ids(self) -> list[str]:
        result: list[str] = []
        for tab in self.tabs:
            for section in tab.sections:
                result.extend(section.fields)
        return result


def _parse_section(
    raw: Any,
    issues: list[LayoutIssue],
    location: str,
) -> LayoutSection | None:
    if not isinstance(raw, dict):
        issues.append(LayoutIssue("error", "Section must be a mapping/object.", location))
        return None

    section_id = raw.get("id")
    if not isinstance(section_id, str) or not ID_RE.fullmatch(section_id):
        issues.append(LayoutIssue("error", "Section id must be a valid non-empty id.", f"{location}.id"))
        return None

    title = raw.get("title", section_id.replace("_", " ").title())
    if not isinstance(title, str) or not title.strip():
        issues.append(LayoutIssue("error", "Section title must be a non-empty string.", f"{location}.title"))
        title = section_id

    raw_fields = raw.get("fields")
    field_options: dict[str, dict[str, Any]] = {}
    if not isinstance(raw_fields, list) or not raw_fields:
        issues.append(LayoutIssue("error", "Section fields must be a non-empty list.", f"{location}.fields"))
        fields: list[str] = []
    else:
        fields = []
        for item in raw_fields:
            if isinstance(item, str) and item:
                fields.append(item)
                continue
            if isinstance(item, dict):
                item_id = item.get("id")
                if not isinstance(item_id, str) or not item_id:
                    issues.append(LayoutIssue("error", "Field layout objects require a non-empty id.", f"{location}.fields"))
                    continue
                display = item.get("display", "default")
                if display not in {"default", "inline", "stat", "value", "resource", "table", "block"}:
                    issues.append(LayoutIssue("error", f"Unsupported field display mode {display!r}.", f"{location}.fields"))
                    display = "default"
                item_span = item.get("span", 1)
                if not isinstance(item_span, int) or item_span < 1 or item_span > 4:
                    issues.append(LayoutIssue("error", "Field span must be an integer from 1 to 4.", f"{location}.fields"))
                    item_span = 1
                fields.append(item_id)
                field_options[item_id] = {"display": display, "span": item_span}
                continue
            issues.append(LayoutIssue("error", "Section fields must be ids or field layout objects.", f"{location}.fields"))

    columns = raw.get("columns", 1)
    if not isinstance(columns, int) or not 1 <= columns <= 4:
        issues.append(LayoutIssue("error", "columns must be an integer from 1 to 4.", f"{location}.columns"))
        columns = 1

    color = raw.get("color")
    if color is not None and (
        not isinstance(color, str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", color)
    ):
        issues.append(LayoutIssue("error", "color must be a semantic color name.", f"{location}.color"))
        color = None

    span = raw.get("span", 12)
    if not isinstance(span, int) or span < 1 or span > 12:
        issues.append(LayoutIssue("error", "span must be an integer from 1 to 12.", f"{location}.span"))
        span = 12

    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        issues.append(LayoutIssue("error", "description must be a string.", f"{location}.description"))
        description = None

    return LayoutSection(
        id=section_id,
        title=title.strip(),
        fields=fields,
        columns=columns,
        description=description.strip() if isinstance(description, str) else None,
        color=color,
        span=span,
        field_options=field_options,
    )


def load_character_layout(
    path: Path | str,
    *,
    schema=None,
) -> tuple[CharacterLayout | None, list[LayoutIssue]]:
    path = Path(path)
    issues: list[LayoutIssue] = []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [LayoutIssue("error", "Layout file does not exist.")]
    except yaml.YAMLError as exc:
        return None, [LayoutIssue("error", f"Invalid YAML: {exc}")]
    except OSError as exc:
        return None, [LayoutIssue("error", f"Could not read layout: {exc}")]

    if not isinstance(raw, dict):
        return None, [LayoutIssue("error", "Layout root must be a mapping/object.")]

    raw_tabs = raw.get("tabs")
    if not isinstance(raw_tabs, list) or not raw_tabs:
        return None, [LayoutIssue("error", "Layout requires a non-empty tabs list.", "tabs")]

    tabs: list[LayoutTab] = []
    seen_tabs: set[str] = set()
    seen_sections: set[str] = set()
    seen_fields: set[str] = set()

    for tab_index, raw_tab in enumerate(raw_tabs):
        location = f"tabs[{tab_index}]"
        if not isinstance(raw_tab, dict):
            issues.append(LayoutIssue("error", "Tab must be a mapping/object.", location))
            continue

        tab_id = raw_tab.get("id")
        if not isinstance(tab_id, str) or not ID_RE.fullmatch(tab_id):
            issues.append(LayoutIssue("error", "Tab id must be a valid non-empty id.", f"{location}.id"))
            continue
        if tab_id in seen_tabs:
            issues.append(LayoutIssue("error", f"Duplicate tab id {tab_id!r}.", f"{location}.id"))
        seen_tabs.add(tab_id)

        title = raw_tab.get("title", tab_id.replace("_", " ").title())
        if not isinstance(title, str) or not title.strip():
            issues.append(LayoutIssue("error", "Tab title must be a non-empty string.", f"{location}.title"))
            title = tab_id

        raw_sections = raw_tab.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections:
            issues.append(LayoutIssue("error", "Tab requires a non-empty sections list.", f"{location}.sections"))
            raw_sections = []

        sections: list[LayoutSection] = []
        for section_index, raw_section in enumerate(raw_sections):
            section_location = f"{location}.sections[{section_index}]"
            section = _parse_section(raw_section, issues, section_location)
            if section is None:
                continue

            if section.id in seen_sections:
                issues.append(LayoutIssue("error", f"Duplicate section id {section.id!r}.", f"{section_location}.id"))
            seen_sections.add(section.id)

            for field_id in section.fields:
                if schema is not None and field_id not in schema.fields:
                    issues.append(LayoutIssue("error", f"Unknown character field {field_id!r}.", f"{section_location}.fields"))
                if field_id in seen_fields:
                    issues.append(LayoutIssue("error", f"Character field {field_id!r} appears more than once.", f"{section_location}.fields"))
                seen_fields.add(field_id)

            sections.append(section)

        tabs.append(LayoutTab(id=tab_id, title=title.strip(), sections=sections))

    if schema is not None:
        missing = [field_id for field_id in schema.fields if field_id not in seen_fields]
        if missing:
            issues.append(
                LayoutIssue(
                    "warning",
                    "Fields omitted from layout will appear in an automatic Other tab: "
                    + ", ".join(missing),
                    "tabs",
                )
            )

    if any(issue.severity == "error" for issue in issues):
        return None, issues

    return CharacterLayout(path=path, tabs=tabs, raw=raw), issues


def fallback_character_layout(schema) -> CharacterLayout:
    return CharacterLayout(
        path=Path("<generated>"),
        tabs=[
            LayoutTab(
                id="character",
                title="Character",
                sections=[
                    LayoutSection(
                        id="character",
                        title="Character",
                        fields=list(schema.fields),
                        columns=2,
                    )
                ],
            )
        ],
        raw={},
    )


def complete_character_layout(
    layout: CharacterLayout | None,
    schema,
) -> CharacterLayout:
    if layout is None:
        return fallback_character_layout(schema)

    placed = set(layout.field_ids)
    missing = [field_id for field_id in schema.fields if field_id not in placed]
    if not missing:
        return layout

    tabs = list(layout.tabs)
    tabs.append(
        LayoutTab(
            id="other",
            title="Other",
            sections=[
                LayoutSection(
                    id="other",
                    title="Other",
                    fields=missing,
                    columns=2,
                )
            ],
        )
    )
    return CharacterLayout(path=layout.path, tabs=tabs, raw=layout.raw)
