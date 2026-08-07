from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.characters.schema import default_collection_item, load_character_schema, validate_character_data
from app.characters.layout import complete_character_layout, load_character_layout
from app.compendium import load_compendium
from app.creation import (
    DraftStorageError,
    create_draft,
    delete_draft,
    list_drafts,
    load_creation_workflow,
    load_draft,
    save_draft,
)
from app.advancement import (
    AdvancementDraftError,
    create_advancement_draft, delete_advancement_draft, list_advancement_drafts,
    load_advancement_draft, save_advancement_draft, load_advancement_workflow,
)
from app.characters.storage import (
    CharacterStorageError,
    create_character,
    delete_character,
    list_characters,
    load_character,
    save_character,
)
from app.system_packs import discover_system_packs, load_system_pack
from app.rules import (
    evaluate_limits,
    load_rule_engine,
    reference_eligibility,
    resolve_compendium_modifier_details,
    resolve_compendium_modifiers,
    selected_eligibility_issues,
)


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PACK_ROOT = Path("data/system_packs")
CHARACTER_ROOT = Path("data/characters")
DRAFT_ROOT = Path("data/character_drafts")
ADVANCEMENT_DRAFT_ROOT = Path("data/advancement_drafts")


def _identity_from_request(request: Request) -> tuple[str, str]:
    """
    Read the authenticated identity from the existing session without coupling
    the character module to one exact auth implementation.
    """
    try:
        session = request.session
    except Exception:
        session = {}

    username: str | None = None
    role = "player"

    direct_user = session.get("user")
    if isinstance(direct_user, dict):
        username = (
            direct_user.get("username")
            or direct_user.get("name")
            or direct_user.get("id")
        )
        role = str(direct_user.get("role") or role)
    elif isinstance(direct_user, str):
        username = direct_user

    for key in ("username", "user_id", "login"):
        if not username and session.get(key):
            username = str(session[key])

    if session.get("role"):
        role = str(session["role"])

    if not username:
        raise HTTPException(status_code=401, detail="Login required.")

    return username, role.lower()


def _character_name(data: dict[str, Any], fallback: str) -> str:
    for key in ("name", "character_name", "title"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _pack_summaries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pack in discover_system_packs(PACK_ROOT):
        if not pack.valid or pack.manifest is None:
            continue
        rows.append(
            {
                "id": pack.manifest.id,
                "name": pack.manifest.name,
                "version": pack.manifest.version,
                "description": pack.manifest.description,
                "has_creation": bool(pack.manifest.creation),
            }
        )
    return rows


def _load_pack_schema(system_id: str):
    pack = load_system_pack(PACK_ROOT / system_id)
    if not pack.valid or pack.manifest is None:
        raise HTTPException(status_code=404, detail="System Pack not found.")

    schema, issues = load_character_schema(
        pack.root / pack.manifest.character_schema
    )
    if schema is None:
        detail = "; ".join(issue.format() for issue in issues)
        raise HTTPException(
            status_code=500,
            detail=f"System Pack character schema is invalid: {detail}",
        )

    return pack, schema


def _load_advancement(system_id: str):
    pack, schema = _load_pack_schema(system_id)
    if not pack.manifest.advancement:
        return pack, schema, None
    engine, issues = load_rule_engine(pack.root / pack.manifest.rules if pack.manifest.rules else None, known_fields=set(schema.fields))
    if engine is None:
        raise HTTPException(status_code=500, detail="System rules are invalid.")
    workflow, issues = load_advancement_workflow(pack.root / pack.manifest.advancement, schema=schema, engine=engine)
    if workflow is None:
        raise HTTPException(status_code=500, detail="Advancement workflow is invalid: " + "; ".join(i.format() for i in issues))
    return pack, schema, workflow

def _available_advancement_actions(pack, schema, data):
    if not pack.manifest.advancement: return []
    _pack, _schema, workflow = _load_advancement(pack.manifest.id)
    engine, _ = load_rule_engine(pack.root / pack.manifest.rules if pack.manifest.rules else None, known_fields=set(schema.fields))
    rows=[]
    for action in workflow.actions:
        available=True
        if action.available_when:
            try: available=bool(engine.evaluate_expression(action.available_when,data))
            except Exception: available=False
        rows.append({"id":action.id,"title":action.title,"description":action.description,"available":available})
    return rows

def _coerce_form_value(field, form: dict[str, Any]) -> Any:
    key = f"field__{field.id}"

    if field.type == "boolean":
        return key in form

    if field.type == "multi_reference":
        if hasattr(form, "getlist"):
            return [str(item) for item in form.getlist(key) if str(item)]
        raw_multi = form.get(key)
        if raw_multi in (None, ""):
            return []
        if isinstance(raw_multi, list):
            return [str(item) for item in raw_multi if str(item)]
        return [str(raw_multi)]

    if field.type == "collection":
        raw_collection = form.get(key)
        if raw_collection in (None, ""):
            return []
        try:
            value = json.loads(str(raw_collection))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid collection JSON.") from exc
        if not isinstance(value, list):
            raise ValueError("Collection value must be a list.")
        return value

    raw = form.get(key)

    if field.type in {"text", "notes", "reference"}:
        return "" if raw is None else str(raw)
    if field.type == "multi_reference":
        if raw in (None, ""):
            return []
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item)]
        return [str(raw)]

    if field.type == "integer":
        if raw in (None, ""):
            return None
        return int(str(raw))

    if field.type == "decimal":
        if raw in (None, ""):
            return None
        return float(str(raw))

    if field.type == "enum":
        return raw

    # Complex fields are not edited by this first generic UI. Preserve them.
    return None



def _coerce_json_value(field, raw: Any) -> Any:
    if field.type == "boolean":
        return bool(raw)
    if field.type in {"text", "notes", "reference"}:
        return "" if raw is None else str(raw)
    if field.type == "integer":
        if raw in (None, ""):
            return None
        return int(raw)
    if field.type == "decimal":
        if raw in (None, ""):
            return None
        return float(raw)
    if field.type == "enum":
        return raw
    if field.type == "collection":
        if raw in (None, ""):
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            value = json.loads(raw)
            if not isinstance(value, list):
                raise ValueError("Collection value must be a list.")
            return value
        raise ValueError("Collection value must be a list.")
    return raw


def _evaluate_character_values_with_explanations(
    pack,
    schema,
    current_data,
    submitted,
):
    data = dict(current_data)

    for field_id, field in schema.fields.items():
        if not _editable_field(field):
            continue
        if field_id not in submitted:
            continue
        data[field_id] = _coerce_json_value(field, submitted[field_id])

    if not pack.manifest.rules:
        return data, [], {}

    engine, load_issues = load_rule_engine(
        pack.root / pack.manifest.rules,
        known_fields=set(schema.fields),
    )
    if engine is None:
        detail = "; ".join(issue.format() for issue in load_issues)
        raise CharacterStorageError(f"System rules are invalid. {detail}")

    compendium = _load_compendium_for_pack(pack)
    modifiers, modifier_sources = resolve_compendium_modifier_details(
        schema,
        compendium,
        data,
        engine,
    )

    values, issues = engine.apply(data, modifiers=modifiers)
    labels = {
        field_id: field.label
        for field_id, field in schema.fields.items()
    }
    explanations = engine.explain(
        data,
        modifiers=modifiers,
        modifier_sources=modifier_sources,
        labels=labels,
    )
    return values, issues, explanations


def _evaluate_character_values(pack, schema, current_data, submitted):
    values, issues, _ = _evaluate_character_values_with_explanations(
        pack,
        schema,
        current_data,
        submitted,
    )
    return values, issues


def _editable_field(field) -> bool:
    return field.type in {
        "text",
        "notes",
        "integer",
        "decimal",
        "boolean",
        "enum",
        "reference",
        "multi_reference",
        "collection",
    }


def _load_creation(system_id: str):
    pack, schema = _load_pack_schema(system_id)
    if not pack.manifest.creation:
        return pack, schema, None

    workflow, issues = load_creation_workflow(
        pack.root / pack.manifest.creation,
        schema=schema,
    )
    if workflow is None:
        detail = "; ".join(issue.format() for issue in issues)
        raise HTTPException(
            status_code=500,
            detail=f"System Pack creation workflow is invalid: {detail}",
        )
    return pack, schema, workflow


def _load_character_layout_for_pack(pack, schema):
    relative = pack.manifest.layouts.get("character") if pack.manifest else None
    if not relative:
        return complete_character_layout(None, schema)

    layout, _issues = load_character_layout(
        pack.root / relative,
        schema=schema,
    )
    return complete_character_layout(layout, schema)


def _load_compendium_for_pack(pack):
    compendium, issues = load_compendium(
        pack.root,
        pack.manifest.compendium,
    )
    if compendium is None:
        detail = "; ".join(issue.format() for issue in issues)
        raise HTTPException(
            status_code=500,
            detail=f"System compendium is invalid: {detail}",
        )
    return compendium


def _reference_options(schema, compendium, field_ids=None):
    allowed = set(field_ids) if field_ids is not None else None
    return {
        field_id: compendium.all(field.entity)
        for field_id, field in schema.fields.items()
        if field.type in {"reference", "multi_reference"}
        and field.entity
        and (allowed is None or field_id in allowed)
    }


def _collection_reference_options(schema, compendium, field_ids=None):
    allowed = set(field_ids) if field_ids is not None else None
    result: dict[str, dict[str, list[Any]]] = {}

    for field_id, field in schema.fields.items():
        if field.type != "collection":
            continue
        if allowed is not None and field_id not in allowed:
            continue

        nested: dict[str, list[Any]] = {}
        for item_id, item_field in (field.item_schema or {}).items():
            if item_field.type == "reference" and item_field.entity:
                nested[item_id] = compendium.all(item_field.entity)

        if nested:
            result[field_id] = nested

    return result


def _eligibility_state(pack, schema, data, field_ids=None):
    engine, issues = load_rule_engine(
        pack.root / pack.manifest.rules if pack.manifest.rules else None,
        known_fields=set(schema.fields),
    )
    if engine is None:
        detail = "; ".join(issue.format() for issue in issues)
        raise CharacterStorageError(f"System rules are invalid. {detail}")

    compendium = _load_compendium_for_pack(pack)
    state = reference_eligibility(
        schema,
        compendium,
        data,
        engine,
        field_ids,
    )
    selected_issues = selected_eligibility_issues(
        schema,
        compendium,
        data,
        engine,
        field_ids,
    )
    return state, selected_issues


def _limit_state(pack, schema, data, field_ids=None):
    engine, issues = load_rule_engine(
        pack.root / pack.manifest.rules if pack.manifest.rules else None,
        known_fields=set(schema.fields),
    )
    if engine is None:
        detail = "; ".join(issue.format() for issue in issues)
        raise CharacterStorageError(f"System rules are invalid. {detail}")

    compendium = _load_compendium_for_pack(pack)
    results, limit_issues = evaluate_limits(
        schema,
        compendium,
        data,
        engine,
    )

    if field_ids is not None:
        field_set = set(field_ids)
        results = [result for result in results if result.field in field_set]
        limit_ids = {result.id for result in results}
        limit_issues = [
            issue for issue in limit_issues
            if issue.rule_id in limit_ids
        ]

    by_field: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_field.setdefault(result.field, []).append(result.as_dict())

    return by_field, limit_issues


def _step_validation_issues(schema, compendium, data, field_ids):
    field_set = set(field_ids)
    issues = [
        issue
        for issue in validate_character_data(schema, data)
        if issue.field in field_set
    ]

    reference_messages: list[str] = []
    for field_id in field_ids:
        field = schema.fields[field_id]
        if field.type not in {"reference", "multi_reference"} or not field.entity:
            continue

        value = data.get(field_id)
        if field.type == "reference":
            values = [] if value in (None, "") else [value]
        else:
            values = value if isinstance(value, list) else []

        for item in values:
            if compendium.get(field.entity, str(item)) is None:
                reference_messages.append(
                    f"{field.label}: unknown {field.entity} selection {item!r}."
                )

    return issues, reference_messages


def _draft_display_name(data: dict[str, Any], system_id: str) -> str:
    name = _character_name(data, "")
    return name or f"Untitled {system_id} character"


@router.get("/characters", response_class=HTMLResponse)
async def characters_home(request: Request):
    username, role = _identity_from_request(request)

    characters = []
    for row in list_characters(username, character_root=CHARACTER_ROOT):
        characters.append(
            {
                **row,
                "display_name": _character_name(
                    row.get("data") or {},
                    row["character_id"],
                ),
            }
        )

    drafts = []
    for row in list_drafts(username, draft_root=DRAFT_ROOT):
        drafts.append(
            {
                **row,
                "display_name": _draft_display_name(
                    row.get("data") or {},
                    row.get("system_id") or "system",
                ),
            }
        )

    advancement_drafts = []
    for row in list_advancement_drafts(username, draft_root=ADVANCEMENT_DRAFT_ROOT):
        advancement_drafts.append({**row, "display_name": _draft_display_name(row.get("data") or {}, row.get("system_id") or "system")})

    return templates.TemplateResponse(
        request=request,
        name="characters/index.html",
        context={
            "username": username,
            "role": role,
            "characters": characters,
            "drafts": drafts,
            "advancement_drafts": advancement_drafts,
            "packs": _pack_summaries(),
        },
    )


@router.post("/characters/create/start")
async def character_creation_start(
    request: Request,
    system_id: str = Form(...),
    character_name: str = Form(""),
):
    username, _ = _identity_from_request(request)
    pack, schema, workflow = _load_creation(system_id)

    if workflow is None:
        name = character_name.strip()
        if not name:
            raise HTTPException(
                status_code=400,
                detail="Character name is required for this System Pack.",
            )

        initial_data: dict[str, Any] = {}
        for candidate in ("name", "character_name", "title"):
            if candidate in schema.fields:
                initial_data[candidate] = name
                break

        try:
            record = create_character(
                username,
                pack.manifest.id,
                initial_data=initial_data,
                character_root=CHARACTER_ROOT,
                pack_root=PACK_ROOT,
            )
        except CharacterStorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return RedirectResponse(
            url=f"/characters/{record.character_id}",
            status_code=303,
        )

    try:
        draft = create_draft(
            username,
            pack.manifest.id,
            pack.manifest.version,
            schema.schema_version,
            initial_data=schema.default_data(),
            draft_root=DRAFT_ROOT,
        )
    except DraftStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(
        url=f"/characters/create/{draft.draft_id}",
        status_code=303,
    )


def _core_fields_for_pack(pack, schema) -> set[str]:
    if not pack.manifest.creation:
        return set()
    workflow, issues = load_creation_workflow(
        pack.root / pack.manifest.creation,
        schema=schema,
    )
    if workflow is None:
        return set()
    return set(workflow.core_field_ids())


def _display_field_value(field, value, reference_options) -> str:
    if field.type == "boolean":
        return "Yes" if value else "No"
    if field.type in {"reference", "multi_reference"}:
        options = {entity.id: entity.name for entity in reference_options.get(field.id, [])}
        if field.type == "reference":
            return options.get(str(value), str(value or "None"))
        values = value if isinstance(value, list) else []
        names = [options.get(str(item), str(item)) for item in values]
        return ", ".join(names) if names else "None"
    if field.type == "collection":
        rows = value if isinstance(value, list) else []
        if not rows:
            return "None"
        return f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}"
    if value is None or value == "":
        return "None"
    return str(value)


def _render_character_edit_page(
    request: Request,
    *,
    username: str,
    role: str,
    record,
    pack,
    schema,
    error: str | None = None,
    status_code: int = 200,
    unlocked_field: str | None = None,
):
    compendium = _load_compendium_for_pack(pack)
    reference_options = _reference_options(schema, compendium)
    collection_reference_options = _collection_reference_options(
        schema,
        compendium,
    )
    character_layout = _load_character_layout_for_pack(pack, schema)
    core_fields = _core_fields_for_pack(pack, schema)
    return templates.TemplateResponse(
        request=request,
        name="characters/edit.html",
        context={
            "username": username,
            "role": role,
            "record": record,
            "pack": pack,
            "schema": schema,
            "editable_field": _editable_field,
            "reference_options": reference_options,
            "collection_reference_options": collection_reference_options,
            "collection_item_default": default_collection_item,
            "character_layout": character_layout,
            "core_fields": core_fields,
            "unlocked_field": unlocked_field,
            "display_field_value": _display_field_value,
            "error": error,
            "advancement_actions": _available_advancement_actions(pack, schema, record.data),
        },
        status_code=status_code,
    )


def _render_creation_page(
    request: Request,
    *,
    username: str,
    role: str,
    draft,
    pack,
    schema,
    workflow,
    error: str | None = None,
    status_code: int = 200,
    unlocked_field: str | None = None,
):
    if draft.character_schema != schema.schema_version:
        raise HTTPException(
            status_code=409,
            detail="This draft was created with a different character schema version.",
        )

    if not workflow.steps:
        raise HTTPException(status_code=500, detail="Creation workflow has no steps.")

    draft.current_step = max(0, min(draft.current_step, len(workflow.steps) - 1))
    step = workflow.steps[draft.current_step]
    compendium = _load_compendium_for_pack(pack)
    reference_options = _reference_options(schema, compendium, step.fields)
    collection_reference_options = _collection_reference_options(
        schema,
        compendium,
        step.fields,
    )
    character_layout = _load_character_layout_for_pack(pack, schema)

    calculated_fields = [
        (field_id, field)
        for field_id, field in schema.fields.items()
        if field.type == "calculated"
    ]

    return templates.TemplateResponse(
        request=request,
        name="characters/create.html",
        context={
            "username": username,
            "role": role,
            "draft": draft,
            "pack": pack,
            "schema": schema,
            "workflow": workflow,
            "step": step,
            "step_index": draft.current_step,
            "step_number": draft.current_step + 1,
            "step_count": len(workflow.steps),
            "is_first": draft.current_step == 0,
            "is_last": draft.current_step == len(workflow.steps) - 1,
            "reference_options": reference_options,
            "collection_reference_options": collection_reference_options,
            "collection_item_default": default_collection_item,
            "character_layout": character_layout,
            "calculated_fields": calculated_fields,
            "locked_fields": set(draft.locked_fields),
            "unlocked_field": unlocked_field,
            "display_field_value": _display_field_value,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/characters/create/{draft_id}", response_class=HTMLResponse)
async def character_creation_page(request: Request, draft_id: str):
    username, role = _identity_from_request(request)
    try:
        draft = load_draft(username, draft_id, draft_root=DRAFT_ROOT)
    except DraftStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    pack, schema, workflow = _load_creation(draft.system_id)
    if workflow is None:
        raise HTTPException(
            status_code=409,
            detail="This System Pack no longer defines a creation workflow.",
        )

    return _render_creation_page(
        request,
        username=username,
        role=role,
        draft=draft,
        pack=pack,
        schema=schema,
        workflow=workflow,
        unlocked_field=request.query_params.get("unlock_field"),
    )


@router.post("/characters/create/{draft_id}/evaluate")
async def character_creation_evaluate(request: Request, draft_id: str):
    username, _ = _identity_from_request(request)
    try:
        draft = load_draft(username, draft_id, draft_root=DRAFT_ROOT)
    except DraftStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    pack, schema, workflow = _load_creation(draft.system_id)
    if workflow is None:
        raise HTTPException(status_code=409, detail="Creation workflow is unavailable.")

    step_index = max(0, min(draft.current_step, len(workflow.steps) - 1))
    step = workflow.steps[step_index]

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid evaluation request.") from exc

    submitted = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(submitted, dict):
        raise HTTPException(status_code=400, detail="Evaluation values must be an object.")

    submitted = {
        key: value
        for key, value in submitted.items()
        if key in step.fields
    }

    try:
        values, rule_issues, explanations = (
            _evaluate_character_values_with_explanations(
                pack,
                schema,
                draft.data,
                submitted,
            )
        )
    except (ValueError, CharacterStorageError) as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": str(exc)},
        )

    compendium = _load_compendium_for_pack(pack)
    schema_issues, reference_messages = _step_validation_issues(
        schema,
        compendium,
        values,
        step.fields,
    )
    eligibility, eligibility_issues = _eligibility_state(
        pack,
        schema,
        values,
        step.fields,
    )
    limits, limit_issues = _limit_state(
        pack,
        schema,
        values,
        step.fields,
    )

    issues = [
        {
            "severity": issue.severity,
            "message": issue.message,
            "field": issue.field,
        }
        for issue in schema_issues
    ]
    issues.extend(
        {"severity": "error", "message": message}
        for message in reference_messages
    )
    issues.extend(
        {
            "severity": issue.severity,
            "message": issue.message,
            "rule_id": issue.rule_id,
        }
        for issue in rule_issues
    )
    issues.extend(
        {
            "severity": issue.severity,
            "message": issue.message,
            "rule_id": issue.rule_id,
        }
        for issue in eligibility_issues
    )
    issues.extend(
        {
            "severity": issue.severity,
            "message": issue.message,
            "rule_id": issue.rule_id,
        }
        for issue in limit_issues
    )

    return {
        "ok": True,
        "calculated": {
            field_id: values.get(field_id)
            for field_id, field in schema.fields.items()
            if field.type == "calculated"
        },
        "explanations": explanations,
        "eligibility": eligibility,
        "limits": limits,
        "issues": issues,
    }


@router.post("/characters/create/{draft_id}/step")
async def character_creation_step(request: Request, draft_id: str):
    username, role = _identity_from_request(request)
    try:
        draft = load_draft(username, draft_id, draft_root=DRAFT_ROOT)
    except DraftStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    pack, schema, workflow = _load_creation(draft.system_id)
    if workflow is None:
        raise HTTPException(status_code=409, detail="Creation workflow is unavailable.")

    step_index = max(0, min(draft.current_step, len(workflow.steps) - 1))
    step = workflow.steps[step_index]
    form_data = await request.form()
    action = str(form_data.get("action") or "next")
    unlocked_field = str(form_data.get("unlocked_field") or "").strip() or None

    try:
        for field_id in step.fields:
            field = schema.fields[field_id]
            if not _editable_field(field):
                continue
            if field_id in draft.locked_fields and field_id != unlocked_field:
                continue
            draft.data[field_id] = _coerce_form_value(field, form_data)

        draft.data, rule_issues = _evaluate_character_values(
            pack,
            schema,
            draft.data,
            {},
        )
    except (ValueError, CharacterStorageError) as exc:
        return _render_creation_page(
            request,
            username=username,
            role=role,
            draft=draft,
            pack=pack,
            schema=schema,
            workflow=workflow,
            error=str(exc),
            status_code=400,
            unlocked_field=unlocked_field,
        )

    if action in {"back", "exit"}:
        if action == "back":
            draft.current_step = max(0, step_index - 1)
        save_draft(draft, draft_root=DRAFT_ROOT)
        return RedirectResponse(
            url=(
                "/characters"
                if action == "exit"
                else f"/characters/create/{draft.draft_id}"
            ),
            status_code=303,
        )

    compendium = _load_compendium_for_pack(pack)
    schema_issues, reference_messages = _step_validation_issues(
        schema,
        compendium,
        draft.data,
        step.fields,
    )
    _eligibility, eligibility_issues = _eligibility_state(
        pack,
        schema,
        draft.data,
        step.fields,
    )
    _limits, limit_issues = _limit_state(
        pack,
        schema,
        draft.data,
        step.fields,
    )
    blocking_rules = [
        issue for issue in rule_issues if issue.severity == "error"
    ]

    blocking_limits = [
        issue for issue in limit_issues if issue.severity == "error"
    ]

    if (
        schema_issues
        or reference_messages
        or blocking_rules
        or eligibility_issues
        or blocking_limits
    ):
        messages = [issue.format() for issue in schema_issues]
        messages.extend(reference_messages)
        messages.extend(issue.format() for issue in blocking_rules)
        messages.extend(issue.format() for issue in eligibility_issues)
        messages.extend(issue.format() for issue in blocking_limits)
        return _render_creation_page(
            request,
            username=username,
            role=role,
            draft=draft,
            pack=pack,
            schema=schema,
            workflow=workflow,
            error=" ".join(messages),
            status_code=400,
            unlocked_field=unlocked_field,
        )

    for field_id in step.lock_after:
        if field_id not in draft.locked_fields:
            draft.locked_fields.append(field_id)

    if action == "finish" or step_index == len(workflow.steps) - 1:
        try:
            record = create_character(
                username,
                pack.manifest.id,
                initial_data=draft.data,
                character_root=CHARACTER_ROOT,
                pack_root=PACK_ROOT,
            )
        except CharacterStorageError as exc:
            return _render_creation_page(
                request,
                username=username,
                role=role,
                draft=draft,
                pack=pack,
                schema=schema,
                workflow=workflow,
                error=str(exc),
                status_code=400,
            )

        delete_draft(username, draft.draft_id, draft_root=DRAFT_ROOT)
        return RedirectResponse(
            url=f"/characters/{record.character_id}?created=1",
            status_code=303,
        )

    draft.current_step = step_index + 1
    save_draft(draft, draft_root=DRAFT_ROOT)
    return RedirectResponse(
        url=f"/characters/create/{draft.draft_id}",
        status_code=303,
    )


@router.post("/characters/create/{draft_id}/delete")
async def character_creation_delete(request: Request, draft_id: str):
    username, _ = _identity_from_request(request)
    try:
        load_draft(username, draft_id, draft_root=DRAFT_ROOT)
    except DraftStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    delete_draft(username, draft_id, draft_root=DRAFT_ROOT)
    return RedirectResponse(url="/characters", status_code=303)


@router.post("/characters/create")
async def characters_create(
    request: Request,
    system_id: str = Form(...),
    character_name: str = Form(...),
):
    username, _ = _identity_from_request(request)
    pack, schema = _load_pack_schema(system_id)

    initial_data: dict[str, Any] = {}
    name_field = None
    for candidate in ("name", "character_name", "title"):
        if candidate in schema.fields:
            name_field = candidate
            break

    if name_field:
        initial_data[name_field] = character_name.strip()

    try:
        record = create_character(
            username,
            pack.manifest.id,
            initial_data=initial_data,
            character_root=CHARACTER_ROOT,
            pack_root=PACK_ROOT,
        )
    except CharacterStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(
        url=f"/characters/{record.character_id}",
        status_code=303,
    )


def _render_advancement_page(request, *, username, role, draft, pack, schema, workflow, action, error=None, status_code=200):
    step_index=max(0,min(draft.current_step,len(action.steps)-1)); step=action.steps[step_index]
    compendium=_load_compendium_for_pack(pack)
    return templates.TemplateResponse(request=request,name="characters/advance.html",context={
        "username":username,"role":role,"draft":draft,"pack":pack,"schema":schema,
        "workflow":action,"step":step,"step_index":step_index,"step_number":step_index+1,"step_count":len(action.steps),
        "is_first":step_index==0,"is_last":step_index==len(action.steps)-1,"reference_options":_reference_options(schema,compendium,step.fields),
        "collection_reference_options":_collection_reference_options(schema,compendium,step.fields),"collection_item_default":default_collection_item,
        "character_layout":_load_character_layout_for_pack(pack,schema),"calculated_fields":[(fid,f) for fid,f in schema.fields.items() if f.type=="calculated"],
        "locked_fields":set(),"core_fields":set(),"unlocked_field":None,"display_field_value":_display_field_value,"error":error,
        "source_character_id":draft.character_id,
    },status_code=status_code)

@router.post("/characters/{character_id}/advance/{action_id}/start")
async def character_advancement_start(request:Request, character_id:str, action_id:str):
    username,_=_identity_from_request(request)
    try: record=load_character(username,character_id,character_root=CHARACTER_ROOT,pack_root=PACK_ROOT)
    except CharacterStorageError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc
    pack,schema,workflow=_load_advancement(record.system_id)
    if workflow is None: raise HTTPException(status_code=409,detail="This System Pack does not define advancement.")
    action=workflow.action(action_id)
    if action is None: raise HTTPException(status_code=404,detail="Advancement action not found.")
    engine,_=load_rule_engine(pack.root / pack.manifest.rules if pack.manifest.rules else None,known_fields=set(schema.fields))
    if action.available_when and not engine.evaluate_expression(action.available_when,record.data): raise HTTPException(status_code=409,detail="This advancement is not currently available.")
    data=dict(record.data)
    for fid,expr in action.changes.items(): data[fid]=engine.evaluate_expression(expr,data)
    data,_=_evaluate_character_values(pack,schema,data,{})
    draft=create_advancement_draft(username,character_id,record.system_id,action.id,record.character_schema,record.updated_at,data,draft_root=ADVANCEMENT_DRAFT_ROOT)
    return RedirectResponse(url=f"/characters/advance/{draft.draft_id}",status_code=303)

@router.get("/characters/advance/{draft_id}",response_class=HTMLResponse)
async def character_advancement_page(request:Request,draft_id:str):
    username,role=_identity_from_request(request)
    try: draft=load_advancement_draft(username,draft_id,draft_root=ADVANCEMENT_DRAFT_ROOT)
    except AdvancementDraftError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc
    pack,schema,workflow=_load_advancement(draft.system_id); action=workflow.action(draft.action_id) if workflow else None
    if action is None: raise HTTPException(status_code=409,detail="Advancement action is unavailable.")
    return _render_advancement_page(request,username=username,role=role,draft=draft,pack=pack,schema=schema,workflow=workflow,action=action)

@router.post("/characters/advance/{draft_id}/evaluate")
async def character_advancement_evaluate(request:Request,draft_id:str):
    username,_=_identity_from_request(request)
    try: draft=load_advancement_draft(username,draft_id,draft_root=ADVANCEMENT_DRAFT_ROOT)
    except AdvancementDraftError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc
    pack,schema,workflow=_load_advancement(draft.system_id); action=workflow.action(draft.action_id); step=action.steps[draft.current_step]
    payload=await request.json(); submitted=payload.get("values") if isinstance(payload,dict) else None
    if not isinstance(submitted,dict): raise HTTPException(status_code=400,detail="Evaluation values must be an object.")
    submitted={k:v for k,v in submitted.items() if k in step.fields}
    try: values,rule_issues,explanations=_evaluate_character_values_with_explanations(pack,schema,draft.data,submitted)
    except (ValueError,CharacterStorageError) as exc: return JSONResponse(status_code=400,content={"ok":False,"error":str(exc)})
    eligibility,eligibility_issues=_eligibility_state(pack,schema,values,step.fields); limits,limit_issues=_limit_state(pack,schema,values,step.fields)
    return {"ok":True,"calculated":{fid:values.get(fid) for fid,f in schema.fields.items() if f.type=="calculated"},"explanations":explanations,"eligibility":eligibility,"limits":limits,"issues":[{"severity":i.severity,"message":i.message,"rule_id":getattr(i,'rule_id',None)} for i in [*rule_issues,*eligibility_issues,*limit_issues]]}

@router.post("/characters/advance/{draft_id}/step")
async def character_advancement_step(request:Request,draft_id:str):
    username,role=_identity_from_request(request)
    try: draft=load_advancement_draft(username,draft_id,draft_root=ADVANCEMENT_DRAFT_ROOT)
    except AdvancementDraftError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc
    pack,schema,workflow=_load_advancement(draft.system_id); action=workflow.action(draft.action_id); step_index=max(0,min(draft.current_step,len(action.steps)-1)); step=action.steps[step_index]
    form=await request.form(); command=str(form.get("action") or "next")
    try:
        for fid in step.fields:
            field=schema.fields[fid]
            if _editable_field(field): draft.data[fid]=_coerce_form_value(field,form)
        draft.data,rule_issues=_evaluate_character_values(pack,schema,draft.data,{})
    except (ValueError,CharacterStorageError) as exc:
        return _render_advancement_page(request,username=username,role=role,draft=draft,pack=pack,schema=schema,workflow=workflow,action=action,error=str(exc),status_code=400)
    if command in {"back","exit"}:
        if command=="back": draft.current_step=max(0,step_index-1)
        save_advancement_draft(draft,draft_root=ADVANCEMENT_DRAFT_ROOT)
        return RedirectResponse(url="/characters" if command=="exit" else f"/characters/advance/{draft.draft_id}",status_code=303)
    compendium=_load_compendium_for_pack(pack); schema_issues,refs=_step_validation_issues(schema,compendium,draft.data,step.fields); _,elig=_eligibility_state(pack,schema,draft.data,step.fields); _,limits=_limit_state(pack,schema,draft.data,step.fields)
    blocking=[i for i in rule_issues if i.severity=="error"]+[i for i in limits if i.severity=="error"]
    if schema_issues or refs or elig or blocking:
        msgs=[i.format() for i in schema_issues]+refs+[i.format() for i in elig]+[i.format() for i in blocking]
        return _render_advancement_page(request,username=username,role=role,draft=draft,pack=pack,schema=schema,workflow=workflow,action=action,error=" ".join(msgs),status_code=400)
    if command=="finish" or step_index==len(action.steps)-1:
        try: record=load_character(username,draft.character_id,character_root=CHARACTER_ROOT,pack_root=PACK_ROOT)
        except CharacterStorageError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc
        if record.updated_at!=draft.base_updated_at:
            return _render_advancement_page(request,username=username,role=role,draft=draft,pack=pack,schema=schema,workflow=workflow,action=action,error="This character changed after the advancement was started. Discard this advancement draft and start again so newer edits are not overwritten.",status_code=409)
        record.data=dict(draft.data)
        try: save_character(record,character_root=CHARACTER_ROOT,pack_root=PACK_ROOT)
        except CharacterStorageError as exc: return _render_advancement_page(request,username=username,role=role,draft=draft,pack=pack,schema=schema,workflow=workflow,action=action,error=str(exc),status_code=400)
        delete_advancement_draft(username,draft.draft_id,draft_root=ADVANCEMENT_DRAFT_ROOT)
        return RedirectResponse(url=f"/characters/{record.character_id}?advanced=1",status_code=303)
    draft.current_step=step_index+1; save_advancement_draft(draft,draft_root=ADVANCEMENT_DRAFT_ROOT)
    return RedirectResponse(url=f"/characters/advance/{draft.draft_id}",status_code=303)

@router.post("/characters/advance/{draft_id}/delete")
async def character_advancement_delete(request:Request,draft_id:str):
    username,_=_identity_from_request(request); delete_advancement_draft(username,draft_id,draft_root=ADVANCEMENT_DRAFT_ROOT); return RedirectResponse(url="/characters",status_code=303)

@router.get("/characters/{character_id}", response_class=HTMLResponse)
async def character_edit(request: Request, character_id: str):
    username, role = _identity_from_request(request)

    try:
        record = load_character(
            username,
            character_id,
            character_root=CHARACTER_ROOT,
            pack_root=PACK_ROOT,
        )
    except CharacterStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    pack, schema = _load_pack_schema(record.system_id)
    return _render_character_edit_page(
        request,
        username=username,
        role=role,
        record=record,
        pack=pack,
        schema=schema,
        unlocked_field=request.query_params.get("unlock_field"),
    )



@router.post("/characters/{character_id}/evaluate")
async def character_evaluate(request: Request, character_id: str):
    username, _ = _identity_from_request(request)

    try:
        record = load_character(
            username,
            character_id,
            character_root=CHARACTER_ROOT,
            pack_root=PACK_ROOT,
        )
    except CharacterStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    pack, schema = _load_pack_schema(record.system_id)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid evaluation request.") from exc

    submitted = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(submitted, dict):
        raise HTTPException(status_code=400, detail="Evaluation values must be an object.")

    try:
        values, rule_issues, explanations = (
            _evaluate_character_values_with_explanations(
                pack,
                schema,
                record.data,
                submitted,
            )
        )
    except (ValueError, CharacterStorageError) as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": str(exc)},
        )

    schema_issues = validate_character_data(schema, values)
    eligibility, eligibility_issues = _eligibility_state(
        pack,
        schema,
        values,
    )
    limits, limit_issues = _limit_state(
        pack,
        schema,
        values,
    )

    return {
        "ok": True,
        "calculated": {
            field_id: values.get(field_id)
            for field_id, field in schema.fields.items()
            if field.type == "calculated"
        },
        "explanations": explanations,
        "eligibility": eligibility,
        "limits": limits,
        "issues": [
            {
                "severity": issue.severity,
                "message": issue.message,
                "field": issue.field,
            }
            for issue in schema_issues
        ] + [
            {
                "severity": issue.severity,
                "message": issue.message,
                "rule_id": issue.rule_id,
            }
            for issue in rule_issues
        ] + [
            {
                "severity": issue.severity,
                "message": issue.message,
                "rule_id": issue.rule_id,
            }
            for issue in eligibility_issues
        ] + [
            {
                "severity": issue.severity,
                "message": issue.message,
                "rule_id": issue.rule_id,
            }
            for issue in limit_issues
        ],
    }


@router.post("/characters/{character_id}/save")
async def character_save(request: Request, character_id: str):
    username, role = _identity_from_request(request)

    try:
        record = load_character(
            username,
            character_id,
            character_root=CHARACTER_ROOT,
            pack_root=PACK_ROOT,
        )
    except CharacterStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    pack, schema = _load_pack_schema(record.system_id)
    form_data = await request.form()
    unlocked_field = str(form_data.get("unlocked_field") or "").strip() or None
    core_fields = _core_fields_for_pack(pack, schema)

    for field_id, field in schema.fields.items():
        if not _editable_field(field):
            continue
        if field_id in core_fields and field_id != unlocked_field:
            continue
        try:
            record.data[field_id] = _coerce_form_value(field, form_data)
        except ValueError:
            return _render_character_edit_page(
                request, username=username, role=role, record=record, pack=pack,
                schema=schema, error=f"Invalid value for {field.label}.",
                status_code=400, unlocked_field=unlocked_field,
            )

    try:
        save_character(
            record,
            character_root=CHARACTER_ROOT,
            pack_root=PACK_ROOT,
        )
    except CharacterStorageError as exc:
        return _render_character_edit_page(
            request, username=username, role=role, record=record, pack=pack,
            schema=schema, error=str(exc), status_code=400,
            unlocked_field=unlocked_field,
        )

    return RedirectResponse(
        url=f"/characters/{character_id}?saved=1",
        status_code=303,
    )


@router.post("/characters/{character_id}/delete")
async def character_delete(request: Request, character_id: str):
    username, _ = _identity_from_request(request)

    # Load first so ownership is verified before deletion.
    try:
        load_character(
            username,
            character_id,
            character_root=CHARACTER_ROOT,
            pack_root=PACK_ROOT,
        )
    except CharacterStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    delete_character(
        username,
        character_id,
        character_root=CHARACTER_ROOT,
    )

    return RedirectResponse(url="/characters", status_code=303)
