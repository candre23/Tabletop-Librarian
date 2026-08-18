from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Callable

from app.knowledgebase import mark_library_changed
from app.config import LIBRARY_FILE, LIBRARY_MANIFEST_FILE, RESOURCE_ROOT, SUPPORTED_EXTENSIONS
from app.library.covers import ensure_cover, save_manual_cover
from app.library.pdf_status import detect_pdf_text_status
from app.storage import read_json, write_json

logger = logging.getLogger(__name__)


LIBRARY_MANIFEST_VERSION = 1


BUNDLED_SRD_FOLDER_NAME = "D20 SRD"
BUNDLED_SRD_PDF = RESOURCE_ROOT / "docs" / "reference" / "SRD_CC_v5.2.1.pdf"
BUNDLED_SRD_COVER = RESOURCE_ROOT / "docs" / "reference" / "SRD_cover.jpg"


def _seed_initial_library() -> dict[str, Any]:
    data = _default_library()

    if not BUNDLED_SRD_PDF.exists():
        return data

    resolved_pdf = BUNDLED_SRD_PDF.resolve(strict=False)
    folder = {
        "name": BUNDLED_SRD_FOLDER_NAME,
        "visibility": "players",
        "cover": str(resolved_pdf),
        "sources": [{"type": "file", "path": str(resolved_pdf)}],
        "file_visibility": {},
    }
    data.setdefault("folders", []).append(folder)

    if BUNDLED_SRD_COVER.exists():
        try:
            save_manual_cover(str(resolved_pdf.parent), resolved_pdf.name, BUNDLED_SRD_COVER)
        except Exception:
            logger.exception("Unable to seed bundled SRD manual cover")

    logger.info("Seeded initial library with bundled SRD folder")
    return data


def _default_manifest() -> dict[str, Any]:
    return {"version": LIBRARY_MANIFEST_VERSION, "sources": {}}


def _manifest_source_key(folder_name: str, source_type: str, source_path: str) -> str:
    raw = f"{folder_name.casefold()}\0{source_type}\0{source_path}".encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:32]


def _load_manifest() -> dict[str, Any]:
    data = read_json(LIBRARY_MANIFEST_FILE, _default_manifest())
    if data.get("version") != LIBRARY_MANIFEST_VERSION or not isinstance(data.get("sources"), dict):
        return _default_manifest()
    return data


def _save_manifest(data: dict[str, Any]) -> None:
    data["version"] = LIBRARY_MANIFEST_VERSION
    data.setdefault("sources", {})
    write_json(LIBRARY_MANIFEST_FILE, data)


def _manifest_documents(folder_name: str, source_type: str, source_path: str) -> list[dict[str, Any]]:
    key = _manifest_source_key(folder_name, source_type, source_path)
    entry = _load_manifest().get("sources", {}).get(key, {})
    docs = entry.get("documents", [])
    return [dict(item) for item in docs if isinstance(item, dict)]


def _store_manifest_documents(
    folder_name: str,
    source_type: str,
    source_path: str,
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    data = _load_manifest()
    key = _manifest_source_key(folder_name, source_type, source_path)
    old = data.setdefault("sources", {}).get(key, {})
    previous = [dict(item) for item in old.get("documents", []) if isinstance(item, dict)]
    data["sources"][key] = {
        "folder": folder_name,
        "source_type": source_type,
        "source_path": source_path,
        "documents": [dict(item) for item in documents],
    }
    _save_manifest(data)
    return previous


def _drop_manifest_source(folder_name: str, source_type: str, source_path: str) -> list[dict[str, Any]]:
    data = _load_manifest()
    key = _manifest_source_key(folder_name, source_type, source_path)
    entry = data.setdefault("sources", {}).pop(key, None)
    if entry is not None:
        _save_manifest(data)
    if not isinstance(entry, dict):
        return []
    return [dict(item) for item in entry.get("documents", []) if isinstance(item, dict)]


def _cleanup_removed_ocr(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> None:
    current_paths = {str(item.get("path") or "") for item in current}
    removed = [item for item in previous if str(item.get("path") or "") not in current_paths]
    if not removed:
        return
    try:
        from app.ocr import remove_ocr_derivative
        from app.readers.comic import remove_cbr_cache
        for item in removed:
            path = str(item.get("path") or "")
            if path:
                source = Path(path)
                remove_ocr_derivative(source)
                if source.suffix.casefold() == ".cbr":
                    remove_cbr_cache(source)
    except Exception:
        logger.exception("Unable to clean OCR derivatives for removed library documents")




def _missing_source_is_confirmed_removed(folder: dict[str, Any], source_path: Path) -> bool:
    """Return True only when a reachable configured ancestor proves deletion.

    Recursive library imports register descendant directories as independent
    sources. If one descendant disappears while its configured parent is still
    reachable, that is a real removal. If the whole mount/share disappears, no
    configured ancestor is reachable and TTL conservatively treats it as offline.
    """
    target = source_path.expanduser().resolve(strict=False)
    for candidate in folder.get("sources", []):
        if candidate.get("type") != "directory":
            continue
        ancestor = Path(str(candidate.get("path") or "")).expanduser().resolve(strict=False)
        if ancestor == target:
            continue
        try:
            target.relative_to(ancestor)
        except ValueError:
            continue
        try:
            if ancestor.exists() and ancestor.is_dir():
                return True
        except OSError:
            continue
    return False



def known_library_document_paths() -> set[str]:
    """Return canonical document paths remembered by the persistent source manifest.

    This includes documents belonging to sources that are currently offline, so
    cache maintenance never equates a network outage with deletion.
    """
    paths: set[str] = set()
    manifest = _load_manifest()
    for entry in manifest.get("sources", {}).values():
        if not isinstance(entry, dict):
            continue
        for document in entry.get("documents", []):
            if not isinstance(document, dict):
                continue
            path = str(document.get("path") or "")
            if path:
                paths.add(path)
    return paths

def _offline_manifest_documents(folder_name: str, source_type: str, source_path: str) -> list[dict[str, Any]]:
    docs = _manifest_documents(folder_name, source_type, source_path)
    for item in docs:
        item["source_available"] = False
    return docs


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
    if not LIBRARY_FILE.exists():
        data = _seed_initial_library()
        data, changed = _normalize_library(data)
        save_library(data)
        return data

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

    removed_folder = next(
        (folder for folder in folders if str(folder.get("name", "")).casefold() == normalized),
        None,
    )
    if removed_folder:
        for source in removed_folder.get("sources", []):
            prior = _drop_manifest_source(
                str(removed_folder.get("name", name)),
                str(source.get("type") or ""),
                str(source.get("path") or ""),
            )
            _cleanup_removed_ocr(prior, [])

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


def _directory_sources(root: Path) -> list[Path]:
    """Return root plus all descendant directories as independent sources."""
    directories = [root]

    try:
        descendants = [
            path
            for path in root.rglob("*")
            if path.is_dir()
        ]
    except OSError as exc:
        raise ValueError(f"Unable to scan subfolders under {root}: {exc}") from exc

    directories.extend(
        sorted(
            descendants,
            key=lambda path: (
                len(path.relative_to(root).parts),
                str(path).casefold(),
            ),
        )
    )

    resolved: list[Path] = []
    seen: set[str] = set()

    for path in directories:
        try:
            candidate = path.resolve(strict=True)
        except OSError:
            continue

        key = str(candidate)
        if key in seen:
            continue

        seen.add(key)
        resolved.append(candidate)

    return resolved


def add_source(folder_name: str, path_text: str) -> dict[str, Any]:
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

        sources = folder.setdefault("sources", [])
        existing = {
            (str(source.get("type")), str(source.get("path")))
            for source in sources
        }

        if source_type == "file":
            candidates = [
                {"type": "file", "path": str(resolved)}
            ]
        else:
            candidates = [
                {"type": "directory", "path": str(directory)}
                for directory in _directory_sources(resolved)
            ]

        added: list[dict[str, str]] = []

        for source in candidates:
            key = (source["type"], source["path"])
            if key in existing:
                continue

            sources.append(source)
            existing.add(key)
            added.append(source)

        if not added:
            raise ValueError(
                "That physical source and all discovered subfolders are already "
                "assigned to this folder."
            )

        save_library(data)

        if source_type == "directory":
            mark_library_changed(
                f"Library source tree added to {folder_name}: "
                f"{resolved.name} ({len(added)} source folder"
                f"{'s' if len(added) != 1 else ''})"
            )
        else:
            mark_library_changed(
                f"Library source added to {folder_name}: {resolved.name}"
            )

        logger.info(
            "Physical source added to %s: %s (%s); %d source entr%s added",
            folder_name,
            resolved,
            source_type,
            len(added),
            "ies" if len(added) != 1 else "y",
        )

        return {
            "type": source_type,
            "path": str(resolved),
            "added_count": len(added),
            "added_sources": added,
        }

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
        prior = _drop_manifest_source(folder_name, source_type, source_path)
        _cleanup_removed_ocr(prior, [])
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
    ocr_status = None
    if doc_type == "PDF":
        text_status = detect_pdf_text_status(resolved)
        if text_status == "scanned":
            # The source remains image-only by design. A persistent local OCR
            # derivative changes Library Management status without modifying
            # the read-only source file.
            from app.ocr import current_ocr_pdf
            ocr_status = "complete" if current_ocr_pdf(resolved) is not None else "required"
    elif doc_type in {"CBZ", "CBR"}:
        # Comic archives are inherently page-image containers. Their OCR text
        # lives in the same persistent local PDF derivative cache as scans.
        from app.ocr import current_ocr_pdf
        ocr_status = "complete" if current_ocr_pdf(resolved) is not None else "required"

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
        "ocr_status": ocr_status,
    }


def scan_folder(
    folder: dict[str, Any],
    generate_covers: bool = True,
    progress_callback: Callable[[str, Path, int], None] | None = None,
) -> dict[str, Any]:
    result = {
        "available": True,
        "documents": [],
        "missing_sources": [],
        "error": None,
    }

    documents_by_path: dict[str, dict[str, Any]] = {}
    scanned_count = 0
    folder_name = str(folder.get("name") or "")

    for source in folder.get("sources", []):
        source_path = Path(source.get("path", ""))
        source_type = str(source.get("type") or "")
        source_path_text = str(source_path)
        source_documents: list[dict[str, Any]] = []

        if not source_path.exists():
            if _missing_source_is_confirmed_removed(folder, source_path):
                previous = _store_manifest_documents(
                    folder_name, source_type, source_path_text, []
                )
                _cleanup_removed_ocr(previous, [])
                continue
            result["missing_sources"].append(source_path_text)
            for record in _offline_manifest_documents(folder_name, source_type, source_path_text):
                documents_by_path[str(record.get("path") or "")] = record
            continue

        try:
            if source_type == "directory":
                for item in source_path.iterdir():
                    if not item.is_file():
                        continue
                    if item.suffix.casefold() not in SUPPORTED_EXTENSIONS:
                        continue

                    scanned_count += 1
                    if progress_callback is not None:
                        progress_callback("document", item, scanned_count)

                    record = _document_record(
                        item,
                        folder,
                        generate_covers,
                        "directory",
                    )

                    if record:
                        record["source_available"] = True
                        source_documents.append(record)
                        documents_by_path[record["path"]] = record

            elif source_type == "file" and source_path.is_file():
                scanned_count += 1
                if progress_callback is not None:
                    progress_callback("document", source_path, scanned_count)

                record = _document_record(
                    source_path,
                    folder,
                    generate_covers,
                    "file",
                )

                if record:
                    record["source_available"] = True
                    source_documents.append(record)
                    documents_by_path[record["path"]] = record

            # A successful scan is authoritative for this source. Only now is
            # absence evidence of a real deletion.
            previous = _store_manifest_documents(
                folder_name, source_type, source_path_text, source_documents
            )
            _cleanup_removed_ocr(previous, source_documents)

        except OSError as exc:
            logger.exception("Failed to scan source %s", source_path)
            result["missing_sources"].append(f"{source_path}: {exc}")
            for record in _offline_manifest_documents(folder_name, source_type, source_path_text):
                documents_by_path[str(record.get("path") or "")] = record

    documents = sorted(
        (item for path, item in documents_by_path.items() if path),
        key=lambda item: (item["display_name"].casefold(), item["path"].casefold()),
    )

    result["documents"] = documents
    result["available"] = not bool(result["missing_sources"])
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
