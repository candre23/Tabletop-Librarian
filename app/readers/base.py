from __future__ import annotations

from pathlib import Path


def safe_document_path(folder_path: str, filename: str) -> Path | None:
    base = Path(folder_path).resolve()
    candidate = (base / filename).resolve()

    try:
        candidate.relative_to(base)
    except ValueError:
        return None

    if not candidate.is_file():
        return None

    return candidate
