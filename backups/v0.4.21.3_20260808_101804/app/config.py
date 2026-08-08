from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATE_DIR = APP_DIR / "templates"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
CACHE_DIR = PROJECT_ROOT / "cache"
COVER_CACHE_DIR = CACHE_DIR / "covers"
MANUAL_COVER_DIR = DATA_DIR / "covers"
UPLOAD_DIR = DATA_DIR / "uploads"
PDF_STATUS_CACHE_DIR = CACHE_DIR / "pdf_status"

CONFIG_FILE = DATA_DIR / "config.json"
USERS_FILE = DATA_DIR / "users.json"
LIBRARY_FILE = DATA_DIR / "library.json"
LOG_FILE = LOG_DIR / "server.log"

APP_HOST = "0.0.0.0"
APP_PORT = 8080
APP_NAME = "Tabletop Librarian"
APP_VERSION = "0.4.21.2"

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
