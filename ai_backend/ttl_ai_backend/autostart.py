from __future__ import annotations

import os
import platform
import shlex
import sys
from pathlib import Path


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}" --start-server'
    return f'"{Path(sys.executable)}" -m ttl_ai_backend --start-server'


def set_autostart(enabled: bool) -> None:
    system = platform.system()
    if system == "Windows":
        _set_windows(enabled)
    elif system == "Linux":
        _set_linux(enabled)
    else:
        raise RuntimeError(f"Automatic startup is not yet supported on {system}.")


def _set_windows(enabled: bool) -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, "Tabletop Librarian AI Backend", 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, "Tabletop Librarian AI Backend")
            except FileNotFoundError:
                pass


def _set_linux(enabled: bool) -> None:
    path = Path.home() / ".config" / "autostart" / "tabletop-librarian-ai.desktop"
    if not enabled:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=Tabletop Librarian AI Backend",
                f"Exec={_command()}",
                "Terminal=false",
                "X-GNOME-Autostart-enabled=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
