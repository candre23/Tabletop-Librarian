from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "app" / "static"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "server.log"

APP_HOST = "0.0.0.0"
APP_PORT = 8080
APP_NAME = "Tabletop Librarian"
APP_VERSION = "0.1.1"
