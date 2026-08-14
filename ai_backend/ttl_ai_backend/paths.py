from __future__ import annotations

import os
import platform
from pathlib import Path


def app_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "Tabletop Librarian" / "AI Backend"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Tabletop Librarian" / "AI Backend"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "tabletop-librarian-ai"


def config_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "Tabletop Librarian" / "AI Backend"
    if system == "Darwin":
        return app_data_dir()
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tabletop-librarian-ai"


def default_models_dir() -> Path:
    return app_data_dir() / "models"


def default_runtime_dir() -> Path:
    return app_data_dir() / "runtime"


def default_log_dir() -> Path:
    return app_data_dir() / "logs"
