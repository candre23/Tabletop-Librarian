from __future__ import annotations

import os
import queue
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import BackendSettings
from .paths import config_dir


@dataclass(frozen=True, slots=True)
class ServerCommand:
    executable: Path
    arguments: tuple[str, ...]


def derive_alias(model_path: str) -> str:
    name = Path(model_path).stem.lower()
    for token in ("-gguf", ".gguf"):
        name = name.replace(token, "")
    return name


def build_server_command(settings: BackendSettings) -> ServerCommand:
    server = Path(settings.server_path)
    model = Path(settings.model_path)
    if not server.is_file():
        raise FileNotFoundError(f"llama-server not found: {server}")
    if not model.is_file():
        raise FileNotFoundError(f"Model not found: {model}")
    alias = settings.alias.strip() or derive_alias(settings.model_path)
    key_file = config_dir() / "api-key.txt"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(settings.ensure_api_key() + "\n", encoding="utf-8")
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    args = [
        "--model", str(model),
        "--alias", alias,
        "--host", settings.host,
        "--port", str(settings.port),
        "--ctx-size", str(settings.context_size),
        "--parallel", str(settings.parallel_slots),
        "--cache-ram", str(settings.prompt_cache_ram_mb),
    ]
    if settings.backend == "cpu":
        # CPU means CPU-only. Some llama.cpp builds include optional accelerator
        # backends (for example OpenVINO) that can otherwise be selected even
        # when the user intends to run on host CPU/RAM only.
        args.extend(["--device", "none", "--n-gpu-layers", "0"])
    else:
        args.extend(["--n-gpu-layers", str(settings.gpu_layers)])
    args.extend([
        "--flash-attn", settings.flash_attention,
        "--reasoning", settings.reasoning,
        "--api-key-file", str(key_file),
        "--no-webui",
    ])
    return ServerCommand(server, tuple(args))


def local_addresses(port: int) -> list[str]:
    addresses = {"127.0.0.1"}
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                addresses.add(ip)
    except OSError:
        pass
    ordered = sorted(addresses, key=lambda x: (x.startswith("127."), x))
    return [f"http://{ip}:{port}/v1" for ip in ordered]




def port_is_available(host: str, port: int) -> bool:
    """Return True when the requested listen port can be bound locally."""
    bind_host = host.strip() or "0.0.0.0"
    if bind_host == "::":
        family = socket.AF_INET6
    else:
        family = socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
        return True
    except OSError:
        return False


def health_url(settings: BackendSettings) -> str:
    return f"http://127.0.0.1:{settings.port}/health"


def is_healthy(settings: BackendSettings, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(health_url(settings), timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


class ServerProcess:
    def __init__(self, on_line: Callable[[str], None] | None = None, on_exit: Callable[[int], None] | None = None) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.on_line = on_line
        self.on_exit = on_exit
        self._reader: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, settings: BackendSettings) -> None:
        if self.running:
            return
        command = build_server_command(settings)
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [str(command.executable), *command.arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        proc = self.process
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            if self.on_line:
                self.on_line(line.rstrip())
        code = proc.wait()
        if self.on_exit:
            self.on_exit(code)

    def stop(self) -> None:
        proc = self.process
        if not proc or proc.poll() is not None:
            self.process = None
            return
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        self.process = None
