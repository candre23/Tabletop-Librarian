from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import re
import tempfile
import uuid


DRAFT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
USER_ID_RE = re.compile(r"[^A-Za-z0-9_.@-]+")
DEFAULT_DRAFT_ROOT = Path("data/character_drafts")


class DraftStorageError(RuntimeError):
    pass


@dataclass(slots=True)
class CharacterDraft:
    draft_id: str
    owner: str
    system_id: str
    system_version: str
    character_schema: int
    current_step: int
    locked_fields: list[str]
    data: dict[str, Any]
    created_at: str
    updated_at: str
    path: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_owner(owner: str) -> str:
    owner = str(owner or "").strip()
    if not owner:
        raise DraftStorageError("Draft owner is required.")
    safe = USER_ID_RE.sub("_", owner).strip("._")
    if not safe:
        raise DraftStorageError("Draft owner is invalid.")
    return safe


def _draft_path(owner: str, draft_id: str, root: Path) -> Path:
    if not DRAFT_ID_RE.fullmatch(draft_id):
        raise DraftStorageError(
            "Draft id must contain lowercase letters, digits, '_' or '-'."
        )
    return root / _safe_owner(owner) / f"{draft_id}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def create_draft(
    owner: str,
    system_id: str,
    system_version: str,
    character_schema: int,
    *,
    initial_data: dict[str, Any] | None = None,
    draft_id: str | None = None,
    draft_root: Path | str = DEFAULT_DRAFT_ROOT,
) -> CharacterDraft:
    root = Path(draft_root)
    draft_id = draft_id or uuid.uuid4().hex[:12]
    path = _draft_path(owner, draft_id, root)

    if path.exists():
        raise DraftStorageError(f"Draft {draft_id!r} already exists.")

    now = _utc_now()
    draft = CharacterDraft(
        draft_id=draft_id,
        owner=owner,
        system_id=system_id,
        system_version=system_version,
        character_schema=character_schema,
        current_step=0,
        locked_fields=[],
        data=dict(initial_data or {}),
        created_at=now,
        updated_at=now,
        path=path,
    )
    save_draft(draft, draft_root=root)
    return draft


def load_draft(
    owner: str,
    draft_id: str,
    *,
    draft_root: Path | str = DEFAULT_DRAFT_ROOT,
) -> CharacterDraft:
    root = Path(draft_root)
    path = _draft_path(owner, draft_id, root)

    if not path.is_file():
        raise DraftStorageError("Character draft does not exist.")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DraftStorageError(f"Could not read character draft: {exc}") from exc

    required = {
        "draft_id",
        "owner",
        "system_id",
        "system_version",
        "character_schema",
        "current_step",
        "created_at",
        "updated_at",
        "data",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise DraftStorageError(
            "Character draft is missing required keys: " + ", ".join(missing)
        )

    if payload["owner"] != owner:
        raise DraftStorageError("Character draft owner mismatch.")
    if not isinstance(payload["data"], dict):
        raise DraftStorageError("Character draft data must be an object.")
    if not isinstance(payload["current_step"], int) or payload["current_step"] < 0:
        raise DraftStorageError("Character draft current_step is invalid.")

    locked_fields = payload.get("locked_fields", [])
    if not isinstance(locked_fields, list) or not all(isinstance(item, str) for item in locked_fields):
        raise DraftStorageError("Character draft locked_fields is invalid.")

    return CharacterDraft(
        draft_id=payload["draft_id"],
        owner=payload["owner"],
        system_id=payload["system_id"],
        system_version=payload["system_version"],
        character_schema=payload["character_schema"],
        current_step=payload["current_step"],
        locked_fields=list(dict.fromkeys(locked_fields)),
        data=payload["data"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        path=path,
    )


def save_draft(
    draft: CharacterDraft,
    *,
    draft_root: Path | str = DEFAULT_DRAFT_ROOT,
) -> CharacterDraft:
    root = Path(draft_root)
    path = _draft_path(draft.owner, draft.draft_id, root)
    draft.updated_at = _utc_now()

    _atomic_write_json(
        path,
        {
            "draft_id": draft.draft_id,
            "owner": draft.owner,
            "system_id": draft.system_id,
            "system_version": draft.system_version,
            "character_schema": draft.character_schema,
            "current_step": draft.current_step,
            "locked_fields": list(dict.fromkeys(draft.locked_fields)),
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
            "data": draft.data,
        },
    )
    draft.path = path
    return draft


def list_drafts(
    owner: str,
    *,
    draft_root: Path | str = DEFAULT_DRAFT_ROOT,
) -> list[dict[str, Any]]:
    owner_dir = Path(draft_root) / _safe_owner(owner)
    if not owner_dir.exists():
        return []

    rows: list[dict[str, Any]] = []
    for path in sorted(owner_dir.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("owner") != owner:
            continue
        rows.append(
            {
                "draft_id": payload.get("draft_id", path.stem),
                "system_id": payload.get("system_id"),
                "system_version": payload.get("system_version"),
                "character_schema": payload.get("character_schema"),
                "current_step": payload.get("current_step", 0),
                "locked_fields": payload.get("locked_fields", []),
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
                "data": payload.get("data", {}),
            }
        )
    return rows


def delete_draft(
    owner: str,
    draft_id: str,
    *,
    draft_root: Path | str = DEFAULT_DRAFT_ROOT,
) -> None:
    path = _draft_path(owner, draft_id, Path(draft_root))
    path.unlink(missing_ok=True)
