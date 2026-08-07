from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.characters.schema import load_character_schema, validate_character_data
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
from app.characters.storage import (
    CharacterStorageError,
    create_character,
    delete_character,
    list_characters,
    load_character,
    save_character,
)
from app.system_packs import discover_system_packs, load_system_pack
from app.rules import load_rule_engine


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PACK_ROOT = Path("data/system_packs")
CHARACTER_ROOT = Path("data/characters")
DRAFT_ROOT = Path("data/character_drafts")


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


def _coerce_form_value(field, form: dict[str, Any]) -> Any:
    key = f"field__{field.id}"

    if field.type == "boolean":
        return key in form

    raw = form.get(key)

    if field.type in {"text", "notes", "reference"}:
        return "" if raw is None else str(raw)

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
    return raw


def _evaluate_character_values(pack, schema, current_data, submitted):
    data = dict(current_data)

    for field_id, field in schema.fields.items():
        if not _editable_field(field):
            continue
        if field_id not in submitted:
            continue
        data[field_id] = _coerce_json_value(field, submitted[field_id])

    if not pack.manifest.rules:
        return data, []

    engine, load_issues = load_rule_engine(
        pack.root / pack.manifest.rules,
        known_fields=set(schema.fields),
    )
    if engine is None:
        detail = "; ".join(issue.format() for issue in load_issues)
        raise CharacterStorageError(f"System rules are invalid. {detail}")

    return engine.apply(data)


def _editable_field(field) -> bool:
    return field.type in {
        "text",
        "notes",
        "integer",
        "decimal",
        "boolean",
        "enum",
        "reference",
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
        if field.type == "reference"
        and field.entity
        and (allowed is None or field_id in allowed)
    }


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
        if field.type != "reference" or not field.entity:
            continue
        value = data.get(field_id)
        if value in (None, ""):
            continue
        if compendium.get(field.entity, str(value)) is None:
            reference_messages.append(
                f"{field.label}: unknown {field.entity} selection {value!r}."
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

    return templates.TemplateResponse(
        request=request,
        name="characters/index.html",
        context={
            "username": username,
            "role": role,
            "characters": characters,
            "drafts": drafts,
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
            "calculated_fields": calculated_fields,
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
        values, rule_issues = _evaluate_character_values(
            pack,
            schema,
            draft.data,
            submitted,
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

    return {
        "ok": True,
        "calculated": {
            field_id: values.get(field_id)
            for field_id, field in schema.fields.items()
            if field.type == "calculated"
        },
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
    form_data = dict(await request.form())
    action = str(form_data.get("action") or "next")

    try:
        for field_id in step.fields:
            field = schema.fields[field_id]
            if not _editable_field(field):
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
    blocking_rules = [
        issue for issue in rule_issues if issue.severity == "error"
    ]

    if schema_issues or reference_messages or blocking_rules:
        messages = [issue.format() for issue in schema_issues]
        messages.extend(reference_messages)
        messages.extend(issue.format() for issue in blocking_rules)
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
        )

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

    compendium, compendium_issues = load_compendium(
        pack.root,
        pack.manifest.compendium,
    )
    if compendium is None:
        detail = "; ".join(issue.format() for issue in compendium_issues)
        raise HTTPException(
            status_code=500,
            detail=f"System compendium is invalid: {detail}",
        )

    reference_options = {
        field_id: compendium.all(field.entity)
        for field_id, field in schema.fields.items()
        if field.type == "reference" and field.entity
    }

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
        },
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
        values, rule_issues = _evaluate_character_values(
            pack,
            schema,
            record.data,
            submitted,
        )
    except (ValueError, CharacterStorageError) as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": str(exc)},
        )

    schema_issues = validate_character_data(schema, values)

    return {
        "ok": True,
        "calculated": {
            field_id: values.get(field_id)
            for field_id, field in schema.fields.items()
            if field.type == "calculated"
        },
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
        ],
    }


@router.post("/characters/{character_id}/save")
async def character_save(request: Request, character_id: str):
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

    _, schema = _load_pack_schema(record.system_id)
    form_data = dict(await request.form())

    for field_id, field in schema.fields.items():
        if not _editable_field(field):
            continue

        try:
            value = _coerce_form_value(field, form_data)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid value for {field.label}.",
            ) from exc

        record.data[field_id] = value

    try:
        save_character(
            record,
            character_root=CHARACTER_ROOT,
            pack_root=PACK_ROOT,
        )
    except CharacterStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
