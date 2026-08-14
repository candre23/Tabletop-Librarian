from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .paths import config_dir, default_models_dir, default_runtime_dir


CURRENT_SETTINGS_VERSION = 5
DEFAULT_BACKEND_PORT = 8081


@dataclass(slots=True)
class BackendSettings:
    settings_version: int = CURRENT_SETTINGS_VERSION
    model_path: str = ""
    models_dir: str = str(default_models_dir())
    runtime_dir: str = str(default_runtime_dir())
    server_path: str = ""
    runtime_backend: str = ""
    backend: str = "auto"
    host: str = "0.0.0.0"
    port: int = DEFAULT_BACKEND_PORT
    context_size: int = 16384
    parallel_slots: int = 1
    prompt_cache_ram_mb: int = 0
    gpu_layers: str = "auto"
    flash_attention: str = "auto"
    reasoning: str = "off"
    alias: str = ""
    api_key: str = ""
    start_with_os: bool = False
    advanced_open: bool = False

    @property
    def endpoint(self) -> str:
        host = self.host
        if host in {"0.0.0.0", "::"}:
            host = "127.0.0.1"
        return f"http://{host}:{self.port}/v1"

    def ensure_api_key(self) -> str:
        if not self.api_key:
            self.api_key = secrets.token_urlsafe(32)
        return self.api_key


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config_dir() / "settings.json")

    def load(self) -> BackendSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            settings = BackendSettings()
            settings.ensure_api_key()
            return settings
        allowed = BackendSettings.__dataclass_fields__.keys()
        data: dict[str, Any] = {k: v for k, v in raw.items() if k in allowed}
        settings = BackendSettings(**data)
        # Prototype releases used 8080, which conflicts with the TTL Server on
        # same-machine deployments. Migrate only pre-v2 settings that still use
        # that old default; explicitly configured non-default ports are retained.
        stored_version = int(raw.get("settings_version", 1) or 1)
        if stored_version < 2 and settings.port == 8080:
            settings.port = DEFAULT_BACKEND_PORT
        settings.settings_version = CURRENT_SETTINGS_VERSION
        settings.ensure_api_key()
        return settings

    def save(self, settings: BackendSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
