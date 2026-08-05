from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

_storage_lock = threading.RLock()


def read_json(path: Path, default: Any) -> Any:
    with _storage_lock:
        if not path.exists():
            return default

        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    with _storage_lock:
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_suffix(path.suffix + ".tmp")
        backup_path = path.with_suffix(path.suffix + ".bak")

        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        # Validate before replacing the authoritative file.
        with temp_path.open("r", encoding="utf-8") as handle:
            json.load(handle)

        if path.exists():
            shutil.copy2(path, backup_path)

        os.replace(temp_path, path)
