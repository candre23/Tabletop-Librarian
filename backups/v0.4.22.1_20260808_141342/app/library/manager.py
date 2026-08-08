from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.knowledgebase import mark_library_changed
from app.config import LIBRARY_FILE, SUPPORTED_EXTENSIONS
from app.library.covers import ensure_cover
from app.library.pdf_status import detect_pdf_text_status
from app.storage import read_json, write_json

logger = logging.getLogger(__name__)


def _default_library() -> dict[str, Any]:
    return {"folders": []}


def document_key(path: Path) -> str:
    raw = str(path.resolve()).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:24]


def _normalize_library(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    changed = False

    for folder in data.setdefault("folders", []):
        folder.setdefault("visibility", "players")
        folder.setdefault("sources", [])
        folder.setdefault("file_visibility", {})

        # Migrate the old one-folder/one-directory structure.
        old_path = folder.pop("path", None)
        if old_path:
            resolved = str(Path(old_path).expanduser().resolve())
            if not any(
                source.get("type") == "directory" and source.get("path") == resolved
                for source in folder["sources"]
            ):
                folder["sources"].append({"type": "directory", "path": resolved})
            changed = True

        # Migrate old cover filename where possible.
        old_cover = folder.get("cover")
        if old_cover and not Path(str(old_cover)).is_absolute():
            for source in folder["sources"]:
                if source.get("type") != "directory":
                    continue
                candidate = Path(source["path"]) / str(old_cover)
                if candidate.exists():
                    folder["cover"] = str(candidate.resolve())
                    changed = True
                    break

    return data, changed


def get_library() -> dict[str, Any]:
    data = read_json(LIBRARY_FILE, _default_library())
    data, changed = _normalize_library(data)
    if changed:
        save_library(data)
    return data


def save_library(data: dict[str, Any]) -> None:
    write_json(LIBRARY_FILE, data)


def list_folders() -> list[dict[str, Any]]:
    return sorted(
        get_library().get("folders", []),
        key=lambda folder: folder.get("name", "").casefold(),
    )


def get_folder(name: str) -> dict[str, Any] | None:
    normalized = name.strip().casefold()

    for folder in get_library().get("folders", []):
        if str(folder.get("name", "")).casefold() == normalized:
            return folder

    return None


def add_folder(name: str, visibility: str = "players") -> dict[str, Any]:
    name = name.strip()

    if not name:
        raise ValueError("Folder name is required.")

    if "/" in name or "\\" in name:
        raise ValueError("Folder name cannot contain slashes.")

    if get_folder(name):
        raise ValueError("A library folder with that name already exists.")

    folder = {
        "name": name,
        "visibility": "gm" if visibility == "gm" else "players",
        "cover": None,
        "sources": [],
        "file_visibility": {},
    }

    data = get_library()
    data.setdefault("folders", []).append(folder)
    save_library(data)
    mark_library_changed(f"Virtual folder added: {name}")

    logger.info("Virtual library folder added: %s", name)
    return folder


def remove_folder(name: str) -> bool:
    data = get_library()
    normalized = name.strip().casefold()
    folders = data.get("folders", [])

    new_folders = [
        folder
        for folder in folders
        if str(folder.get("name", "")).casefold() != normalized
    ]

    if len(new_folders) == len(folders):
        return False

    data["folders"] = new_folders
    save_library(data)
    mark_library_changed(f"Virtual folder removed: {name}")
    logger.info("Virtual library folder removed: %s", name)
    return True


def set_folder_visibility(name: str, visibility: str) -> bool:
    data = get_library()
    normalized = name.strip().casefold()
    visibility = "gm" if visibility == "gm" else "players"

    for folder in data.get("folders", []):
        if str(folder.get("name", "")).casefold() == normalized:
            folder["visibility"] = visibility
            save_library(data)
            logger.info("Folder visibility changed: %s -> %s", name, visibility)
            return True

    return False


def add_source(folder_name: str, path_text: str) -> dict[str, str]:
    path = Path(path_text.strip()).expanduser()

    if not path.exists():
        raise ValueError("That path does not exist.")

    if not path.is_dir() and not path.is_file():
        raise ValueError("The selected path is not a regular file or directory.")

    resolved = path.resolve(strict=True)
    source_type = "directory" if resolved.is_dir() else "file"

    if source_type == "file":
        if resolved.suffix.casefold() not in SUPPORTED_EXTENSIONS:
            raise ValueError("That file type is not currently supported.")

    data = get_library()
    normalized = folder_name.strip().casefold()

    for folder in data.get("folders", []):
        if str(folder.get("name", "")).casefold() != normalized:
            continue

        source = {"type": source_type, "path": str(resolved)}

        if source in folder.setdefault("sources", []):
            raise ValueError("That physical source is already assigned to this folder.")

        folder["sources"].append(source)
        save_library(data)
        mark_library_changed(f"Library source added to {folder_name}: {resolved.name}")
        logger.info(
            "Physical source added to %s: %s (%s)",
            folder_name,
            resolved,
            source_type,
        )
        return source

    raise ValueError("Virtual folder not found.")


def remove_source(folder_name: str, source_type: str, source_path: str) -> bool:
    data = get_library()
    normalized = folder_name.strip().casefold()

    for folder in data.get("folders", []):
        if str(folder.get("name", "")).casefold() != normalized:
            continue

        sources = folder.setdefault("sources", [])
        new_sources = [
            source
            for source in sources
            if not (
                source.get("type") == source_type
                and source.get("path") == source_path
            )
        ]

        if len(new_sources) == len(sources):
            return False

        folder["sources"] = new_sources
        save_library(data)
        mark_library_changed(f"Library source removed from {folder_name}: {Path(source_path).name}")
        logger.info("Physical source removed from %s: %s", folder_name, source_path)
        return True

    return False


def set_file_visibility(folder_name: str, file_path: str, visibility: str) -> bool:
    data = get_library()
    normalized = folder_name.strip().casefold()

    for folder in data.get("folders", []):
        if str(folder.get("name", "")).casefold() != normalized:
            continue

        overrides = folder.setdefault("file_visibility", {})

        if visibility == "inherit":
            overrides.pop(file_path, None)
        else:
            overrides[file_path] = "gm" if visibility == "gm" else "players"

        save_library(data)
        logger.info(
            "File visibility changed in %s: %s -> %s",
            folder_name,
            file_path,
            visibility,
        )
        return True

    return False


def set_folder_cover(folder_name: str, file_path: str | None) -> bool:
    data = get_library()
    normalized = folder_name.strip().casefold()

    for folder in data.get("folders", []):
        if str(folder.get("name", "")).casefold() == normalized:
            folder["cover"] = file_path or None
            save_library(data)
            logger.info("Folder cover changed: %s -> %s", folder_name, file_path)
            return True

    return False


def _document_record(
    path: Path,
    folder: dict[str, Any],
    generate_covers: bool,
    source_type: str,
) -> dict[str, Any] | None:
    extension = path.suffix.casefold()
    doc_type = SUPPORTED_EXTENSIONS.get(extension)

    if not doc_type:
        return None

    resolved = path.resolve()
    resolved_text = str(resolved)
    override = folder.get("file_visibility", {}).get(resolved_text)
    effective_visibility = override or folder.get("visibility", "players")

    cover_available = False
    if generate_covers:
        cover_available = (
            ensure_cover(str(resolved.parent), resolved.name, doc_type) is not None
        )

    text_status = None
    if doc_type == "PDF":
        text_status = detect_pdf_text_status(resolved)

    return {
        "key": document_key(resolved),
        "path": resolved_text,
        "filename": resolved.name,
        "display_name": resolved.stem,
        "type": doc_type,
        "extension": extension,
        "source_type": source_type,
        "source_name": resolved.parent.name,
        "visibility": effective_visibility,
        "visibility_override": override or "inherit",
        "cover_available": cover_available,
        "text_status": text_status,
    }


def scan_folder(folder: dict[str, Any], generate_covers: bool = True) -> dict[str, Any]:
    result = {
        "available": True,
        "documents": [],
        "missing_sources": [],
        "error": None,
    }

    documents_by_path: dict[str, dict[str, Any]] = {}

    for source in folder.get("sources", []):
        source_path = Path(source.get("path", ""))
        source_type = source.get("type")

        if not source_path.exists():
            result["missing_sources"].append(str(source_path))
            continue

        try:
            if source_type == "directory":
                for item in source_path.iterdir():
                    if not item.is_file():
                        continue

                    record = _document_record(
                        item,
                        folder,
                        generate_covers,
                        "directory",
                    )

                    if record:
                        documents_by_path[record["path"]] = record

            elif source_type == "file" and source_path.is_file():
                record = _document_record(
                    source_path,
                    folder,
                    generate_covers,
                    "file",
                )

                if record:
                    documents_by_path[record["path"]] = record

        except OSError as exc:
            logger.exception("Failed to scan source %s", source_path)
            result["missing_sources"].append(f"{source_path}: {exc}")

    documents = sorted(
        documents_by_path.values(),
        key=lambda item: (item["display_name"].casefold(), item["path"].casefold()),
    )

    result["documents"] = documents
    return result


def get_document(
    folder: dict[str, Any],
    key: str,
    generate_cover: bool = False,
) -> dict[str, Any] | None:
    scan = scan_folder(folder, generate_covers=generate_cover)

    for document in scan["documents"]:
        if document["key"] == key:
            return document

    return None


def player_can_see_folder(folder: dict[str, Any]) -> bool:
    if folder.get("visibility", "players") == "players":
        return True

    return "players" in folder.get("file_visibility", {}).values()
