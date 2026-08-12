"""OCRmyPDF script plugin that reports progress to TTLibrarian.

This file is loaded by the external ``ocrmypdf`` CLI process. It deliberately
uses only the standard library plus OCRmyPDF's own hook API so it works with
Ubuntu's distro-installed OCRmyPDF even when TTLibrarian runs in a venv.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from time import time

from ocrmypdf import hookimpl


def _progress_path() -> Path | None:
    raw = os.environ.get("TTL_OCR_PROGRESS_FILE", "").strip()
    return Path(raw) if raw else None


class TTLProgressBar:
    def __init__(self, *, total=None, desc=None, unit=None, disable=False, **kwargs):
        self.total = total
        self.desc = str(desc or "Processing")
        self.unit = str(unit or "")
        self.disable = bool(disable)
        self.current = 0.0
        self._write()

    def __enter__(self):
        self._write()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None and self.total is not None:
            try:
                self.current = float(self.total)
            except (TypeError, ValueError):
                pass
            self._write()
        return False

    def update(self, n=1, *, completed=None):
        if completed is not None:
            try:
                self.current = float(completed)
            except (TypeError, ValueError):
                pass
        else:
            try:
                self.current += float(n)
            except (TypeError, ValueError):
                pass
        self._write()

    def _write(self) -> None:
        path = _progress_path()
        if path is None:
            return
        payload = {
            "desc": self.desc,
            "unit": self.unit,
            "current": self.current,
            "total": self.total,
            "updated_at": time(),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_text(json.dumps(payload), encoding="utf-8")
            temp.replace(path)
        except OSError:
            # Progress reporting must never make OCR itself fail.
            pass


@hookimpl
def get_progressbar_class():
    return TTLProgressBar
