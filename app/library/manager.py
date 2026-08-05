from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import LIBRARY_FILE, SUPPORTED_EXTENSIONS
from app.storage import read_json, write_json

logger = logging.getLogger(__name__)


def _default_library() -> dict[str, Any]:
    return {"folders": []}


def get_library() -> dict[str, Any]:
    return read_json(LIBRARY_FILE, _default_library())


def save_library(data: dict[str, Any]) -> None:
    write_json(LIBRARY_FILE, data)


def list_folders() -> list[dict[str, Any]]:
    folders = get_library().get("folders", [])
    return sorted(folders, key=lambda item: item.get("name", "").casefold())


def get_folder(name: str) -> dict[str, Any] | None:
    normalized = name.strip().casefold()
    for folder in get_library().get("folders", []):
        if str(folder.get("name", "")).casefold() == normalized:
            return folder
    return None


def add_folder(name: str, path_text: str, visibility: str = "players") -> dict[str, Any]:
    name = name.strip()
    path_text = path_text.strip()

    if not name:
        raise ValueError("Folder name is required.")

    if "/" in name or "\\" in name:
        raise ValueError("Folder name cannot contain slashes.")

    if get_folder(name):
        raise ValueError("A library folder with that name already exists.")

    path = Path(path_text).expanduser()

    if not path.exists():
        raise ValueError("That directory does not exist.")

    if not path.is_dir():
        raise ValueError("The selected path is not a directory.")

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Unable to access directory: {exc}") from exc

    visibility = "gm" if visibility == "gm" else "players"

    data = get_library()
    folder = {
        "name": name,
        "path": str(resolved),
        "visibility": visibility,
        "cover": None,
    }
    data.setdefault("folders", []).append(folder)
    save_library(data)

    logger.info("Library folder added: %s -> %s", name, resolved)
    return folder


def remove_folder(name: str) -> bool:
    data = get_library()
    folders = data.get("folders", [])
    normalized = name.strip().casefold()

    new_folders = [
        folder
        for folder in folders
        if str(folder.get("name", "")).casefold() != normalized
    ]

    if len(new_folders) == len(folders):
        return False

    data["folders"] = new_folders
    save_library(data)
    logger.info("Library folder removed: %s", name)
    return True


def scan_folder(folder: dict[str, Any]) -> dict[str, Any]:
    path = Path(folder["path"])
    result = {
        "available": False,
        "documents": [],
        "error": None,
    }

    if not path.exists() or not path.is_dir():
        result["error"] = "Physical directory is unavailable."
        logger.warning("Library path unavailable: %s", path)
        return result

    documents: list[dict[str, Any]] = []

    try:
        for item in path.iterdir():
            if not item.is_file():
                continue

            extension = item.suffix.casefold()
            doc_type = SUPPORTED_EXTENSIONS.get(extension)
            if not doc_type:
                continue

            documents.append(
                {
                    "filename": item.name,
                    "display_name": item.stem,
                    "type": doc_type,
                    "extension": extension,
                }
            )
    except OSError as exc:
        result["error"] = f"Unable to scan directory: {exc}"
        logger.exception("Failed to scan library directory %s", path)
        return result

    documents.sort(key=lambda item: item["display_name"].casefold())

    result["available"] = True
    result["documents"] = documents
    return result
