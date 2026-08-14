from __future__ import annotations

import os
import sys
from pathlib import Path


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


def _int_from_env(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        port = int(value)
    except ValueError:
        return default
    return port if 1 <= port <= 65535 else default


SOURCE_ROOT = Path(__file__).resolve().parent.parent
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    RESOURCE_ROOT = Path(sys._MEIPASS)
else:
    RESOURCE_ROOT = SOURCE_ROOT

PROJECT_ROOT = RESOURCE_ROOT
APP_DIR = RESOURCE_ROOT / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATE_DIR = APP_DIR / "templates"

# Source/development runs retain the historical in-tree locations. Packaged
# installers set these environment variables to writable system locations.
DATA_DIR = _path_from_env("TTL_DATA_DIR", SOURCE_ROOT / "data")
LOG_DIR = _path_from_env("TTL_LOG_DIR", SOURCE_ROOT / "logs")
CACHE_DIR = _path_from_env("TTL_CACHE_DIR", SOURCE_ROOT / "cache")

BUNDLED_SYSTEM_PACKS_DIR = RESOURCE_ROOT / "data" / "system_packs"
SYSTEM_PACKS_DIR = DATA_DIR / "system_packs"
CHARACTER_DIR = DATA_DIR / "characters"
CHARACTER_DRAFT_DIR = DATA_DIR / "character_drafts"
ADVANCEMENT_DRAFT_DIR = DATA_DIR / "advancement_drafts"
SYSTEM_PACK_BACKUP_DIR = DATA_DIR / "system_pack_backups"

COVER_CACHE_DIR = CACHE_DIR / "covers"
MANUAL_COVER_DIR = DATA_DIR / "covers"
UPLOAD_DIR = DATA_DIR / "uploads"
PDF_STATUS_CACHE_DIR = CACHE_DIR / "pdf_status"
OCR_DATA_DIR = DATA_DIR / "ocr"

CONFIG_FILE = DATA_DIR / "config.json"
USERS_FILE = DATA_DIR / "users.json"
LIBRARY_FILE = DATA_DIR / "library.json"
LIBRARY_MANIFEST_FILE = DATA_DIR / "library_manifest.json"
LOG_FILE = LOG_DIR / "server.log"

APP_HOST = os.environ.get("TTL_HOST", "0.0.0.0").strip() or "0.0.0.0"
APP_PORT = _int_from_env("TTL_PORT", 8080)
APP_NAME = "Tabletop Librarian"
APP_VERSION = "0.5.23"

SUPPORTED_EXTENSIONS = {
    ".pdf": "PDF",
    ".cbz": "CBZ",
    ".cbr": "CBR",
    ".png": "Image",
    ".jpg": "Image",
    ".jpeg": "Image",
    ".webp": "Image",
    ".gif": "Image",
    ".txt": "Text",
    ".md": "Markdown",
}

COVER_WIDTH = 400
COVER_HEIGHT = 600
