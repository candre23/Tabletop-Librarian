from __future__ import annotations

import re
from pathlib import Path

from app.config import SUPPORTED_EXTENSIONS, UPLOAD_DIR

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._() \-\[\]]+")


def safe_username(username: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", username).strip(" .")
    return cleaned or "user"


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    cleaned = SAFE_NAME_RE.sub("_", name).strip(" .")
    return cleaned or "upload"


def user_upload_dir(username: str) -> Path:
    return UPLOAD_DIR / safe_username(username)


def unique_upload_path(username: str, filename: str) -> Path:
    directory = user_upload_dir(username)
    directory.mkdir(parents=True, exist_ok=True)

    clean = safe_filename(filename)
    stem = Path(clean).stem
    suffix = Path(clean).suffix

    candidate = directory / clean
    number = 2

    while candidate.exists():
        candidate = directory / f"{stem} ({number}){suffix}"
        number += 1

    return candidate


def supported_upload(filename: str) -> bool:
    return Path(filename).suffix.casefold() in SUPPORTED_EXTENSIONS


def list_uploads() -> list[dict]:
    uploads = []

    if not UPLOAD_DIR.exists():
        return uploads

    for user_dir in sorted(UPLOAD_DIR.iterdir(), key=lambda item: item.name.casefold()):
        if not user_dir.is_dir():
            continue

        for item in sorted(user_dir.iterdir(), key=lambda entry: entry.name.casefold()):
            if not item.is_file():
                continue
            if item.suffix.casefold() not in SUPPORTED_EXTENSIONS:
                continue

            uploads.append(
                {
                    "username": user_dir.name,
                    "filename": item.name,
                    "path": str(item.resolve()),
                    "display_name": item.stem,
                }
            )

    return uploads
