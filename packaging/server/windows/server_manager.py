from __future__ import annotations

import argparse
import configparser
import os
import socket
import subprocess
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox


APP_TITLE = "TTL Server Manager"
SERVER_EXE = "Tabletop-Librarian-Server.exe"


def program_data_root() -> Path:
    root = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return Path(root) / "Tabletop Librarian"


def config_path() -> Path:
    return program_data_root() / "server.ini"


def pid_path() -> Path:
    return program_data_root() / "server.pid"


def log_path() -> Path:
    return program_data_root() / "logs" / "server.log"


def read_server_config() -> tuple[str, int]:
    parser = configparser.ConfigParser()
    path = config_path()
    if path.is_file():
        parser.read(path, encoding="utf-8")

    host = parser.get("server", "host", fallback="0.0.0.0").strip() or "0.0.0.0"
    try:
        port = parser.getint("server", "port", fallback=8080)
    except ValueError:
        port = 8080
    if not 1 <= port <= 65535:
        port = 8080
    return host, port


def local_url() -> str:
    _, port = read_server_config()
    return f"http://127.0.0.1:{port}"


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def read_pid() -> int | None:
    try:
        value = int(pid_path().read_text(encoding="ascii").strip())
        return value if value > 0 else None
    except (OSError, ValueError):
        return None


def server_executable() -> Path:
    return Path(sys.executable).resolve().with_name(SERVER_EXE)


class ServerManager(tk.Tk):
    def __init__(self, *, start_server: bool = False, minimized: bool = False) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("500x285")
        self.minsize(500, 285)
        self.resizable(False, False)

        try:
            self.iconbitmap(default=str(Path(sys.executable).resolve()))
        except tk.TclError:
            pass

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        outer = tk.Frame(self, padx=18, pady=16)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="Tabletop Librarian Server",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")

        self.status_var = tk.StringVar(value="Checking...")
        self.status_label = tk.Label(
            outer,
            textvariable=self.status_var,
            font=("Segoe UI", 11, "bold"),
        )
        self.status_label.pack(anchor="w", pady=(14, 2))

        self.url_var = tk.StringVar(value=local_url())
        url_row = tk.Frame(outer)
        url_row.pack(fill="x", pady=(5, 12))
        tk.Label(url_row, text="Server URL:", width=12, anchor="w").pack(side="left")
        tk.Entry(
            url_row,
            textvariable=self.url_var,
            state="readonly",
            readonlybackground="white",
        ).pack(side="left", fill="x", expand=True)

        button_row = tk.Frame(outer)
        button_row.pack(fill="x", pady=(4, 10))

        self.start_button = tk.Button(
            button_row, text="Start Server", width=15, command=self.start_server
        )
        self.start_button.pack(side="left", padx=(0, 8))

        self.stop_button = tk.Button(
            button_row, text="Stop Server", width=15, command=self.stop_server
        )
        self.stop_button.pack(side="left", padx=(0, 8))

        self.open_button = tk.Button(
            button_row, text="Open TTL", width=15, command=self.open_ttl
        )
        self.open_button.pack(side="left")

        utility_row = tk.Frame(outer)
        utility_row.pack(fill="x", pady=(3, 0))

        tk.Button(
            utility_row, text="View Log", width=15, command=self.view_log
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            utility_row, text="Open Data Folder", width=15, command=self.open_data
        ).pack(side="left")

        tk.Label(
            outer,
            text="Closing this Manager does not stop a running TTL Server.",
            fg="#555555",
        ).pack(anchor="w", pady=(18, 0))

        self.after(100, self.refresh_status)

        if start_server:
            self.after(300, self.start_server)
        if minimized:
            self.after(500, self.iconify)

    def refresh_status(self) -> None:
        _, port = read_server_config()
        running = port_open(port)
        self.url_var.set(local_url())

        if running:
            self.status_var.set("Running")
            self.status_label.configure(fg="#177245")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.open_button.configure(state="normal")
        else:
            self.status_var.set("Stopped")
            self.status_label.configure(fg="#a12622")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.open_button.configure(state="disabled")

        self.after(1000, self.refresh_status)

    def start_server(self) -> None:
        _, port = read_server_config()
        if port_open(port):
            return

        exe = server_executable()
        if not exe.is_file():
            messagebox.showerror(
                APP_TITLE,
                f"TTL Server executable was not found:\n\n{exe}",
                parent=self,
            )
            return

        flags = 0
        if os.name == "nt":
            flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )

        try:
            subprocess.Popen(
                [str(exe)],
                cwd=str(exe.parent),
                creationflags=flags,
                close_fds=True,
            )
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Unable to start TTL Server:\n\n{exc}",
                parent=self,
            )
            return

        self.status_var.set("Starting...")
        self.status_label.configure(fg="#805500")

    def stop_server(self) -> None:
        pid = read_pid()
        command: list[str]

        if pid is not None:
            command = ["taskkill.exe", "/PID", str(pid), "/T", "/F"]
        else:
            command = ["taskkill.exe", "/IM", SERVER_EXE, "/T", "/F"]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode not in (0, 128):
            detail = (result.stderr or result.stdout or "").strip()
            messagebox.showerror(
                APP_TITLE,
                "Unable to stop TTL Server."
                + (f"\n\n{detail}" if detail else ""),
                parent=self,
            )
            return

        try:
            pid_path().unlink()
        except OSError:
            pass

        self.status_var.set("Stopping...")
        self.status_label.configure(fg="#805500")

    def open_ttl(self) -> None:
        webbrowser.open(local_url())

    def view_log(self) -> None:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        subprocess.Popen(["notepad.exe", str(path)])

    def open_data(self) -> None:
        path = program_data_root()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--minimized", action="store_true")
    args, _ = parser.parse_known_args()

    app = ServerManager(start_server=args.start, minimized=args.minimized)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
