from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .hardware import HardwareProfile

PINNED_LLAMA_CPP_RELEASE = "b10430"
GITHUB_RELEASE = f"https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{PINNED_LLAMA_CPP_RELEASE}"


@dataclass(frozen=True, slots=True)
class RuntimeAsset:
    tag: str
    name: str
    url: str
    backend: str



def runtime_backend_matches(system: str, selected_backend: str, installed_backend: str) -> bool:
    if not installed_backend:
        return False
    if selected_backend == installed_backend:
        return True
    # Linux currently uses the official Vulkan archive when CUDA is requested.
    return system == "Linux" and selected_backend == "cuda" and installed_backend == "vulkan"

def server_executable_name() -> str:
    return "llama-server.exe" if platform.system() == "Windows" else "llama-server"


def find_server(runtime_dir: Path) -> Path | None:
    direct = runtime_dir / server_executable_name()
    if direct.is_file():
        return direct
    if runtime_dir.exists():
        for path in runtime_dir.rglob(server_executable_name()):
            if path.is_file():
                return path
    found = shutil.which("llama-server")
    return Path(found) if found else None


def _asset_patterns(system: str, machine: str, backend: str) -> tuple[re.Pattern[str], ...]:
    x64 = machine.lower() in {"x86_64", "amd64", "x64"}
    if not x64:
        raise RuntimeError(f"Automatic llama.cpp runtime installation is not yet supported for {machine}.")
    if system == "Windows":
        if backend == "cuda":
            tokens = (
                r"llama-b\d+-bin-win-cuda-12\.4-x64\.zip$",
                r"cudart-llama-bin-win-cuda-12\.4-x64\.zip$",
            )
        else:
            token = {
                "vulkan": r"llama-b\d+-bin-win-vulkan-x64\.zip$",
                "openvino": r"llama-b\d+-bin-win-openvino-[^-]+-x64\.zip$",
                "cpu": r"llama-b\d+-bin-win-cpu-x64\.zip$",
            }.get(backend, r"llama-b\d+-bin-win-cpu-x64\.zip$")
            tokens = (token,)
    elif system == "Linux":
        # Current official releases do not ship a Linux CUDA archive. The portable
        # Vulkan build is used here for NVIDIA until Phase 4 packaging supplies a
        # dedicated CUDA runtime.
        effective = "vulkan" if backend == "cuda" else backend
        token = {
            "vulkan": r"llama-b\d+-bin-ubuntu-vulkan-x64\.tar\.gz$",
            "openvino": r"llama-b\d+-bin-ubuntu-openvino-[^-]+-x64\.tar\.gz$",
            "cpu": r"llama-b\d+-bin-ubuntu-x64\.tar\.gz$",
        }.get(effective, r"llama-b\d+-bin-ubuntu-x64\.tar\.gz$")
        tokens = (token,)
    else:
        raise RuntimeError(f"Automatic llama.cpp runtime installation is not supported on {system} yet.")
    return tuple(re.compile(token, re.IGNORECASE) for token in tokens)


def release_runtime_assets(profile: HardwareProfile, backend: str) -> list[RuntimeAsset]:
    request = urllib.request.Request(GITHUB_RELEASE, headers={"User-Agent": "TTL-AI-Backend/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        release = json.load(response)
    patterns = _asset_patterns(profile.system, profile.machine, backend)
    result: list[RuntimeAsset] = []
    actual_backend = "vulkan" if profile.system == "Linux" and backend == "cuda" else backend
    assets = release.get("assets", [])
    for pattern in patterns:
        match = None
        for asset in assets:
            name = str(asset.get("name", ""))
            if pattern.search(name):
                match = RuntimeAsset(
                    tag=str(release.get("tag_name", PINNED_LLAMA_CPP_RELEASE)),
                    name=name,
                    url=str(asset["browser_download_url"]),
                    backend=actual_backend,
                )
                break
        if not match:
            raise RuntimeError(
                f"Pinned llama.cpp {PINNED_LLAMA_CPP_RELEASE} does not contain a compatible asset for "
                f"{profile.system} / {backend}."
            )
        result.append(match)
    return result


def describe_process_exit(code: int, backend: str = "") -> str:
    """Return a user-facing explanation for known process exit codes."""
    normalized = code & 0xFFFFFFFF
    hex_code = f"0x{normalized:08X}"

    if normalized == 0xC0000005:
        if backend == "vulkan":
            return (
                f"Windows access violation ({hex_code}). The llama.cpp Vulkan runtime crashed during "
                "GPU initialization. This usually indicates a graphics-driver or Vulkan compatibility "
                "problem with this GPU. Update the GPU driver and retry; if it persists, choose CPU "
                "or another supported backend."
            )
        return (
            f"Windows access violation ({hex_code}). llama.cpp crashed while initializing the selected "
            "runtime. Update the GPU driver/runtime and retry, or choose another backend."
        )

    if normalized == 0xC0000135:
        return (
            f"Windows loader failure ({hex_code}). A required DLL could not be found. Reinstall the "
            "selected llama.cpp runtime and update the GPU driver/runtime package."
        )

    if normalized == 0xC000007B:
        return (
            f"Windows loader failure ({hex_code}). A required executable or DLL has an incompatible "
            "architecture or is damaged. Reinstall the selected llama.cpp runtime."
        )

    return ""


def validate_runtime(server: Path, backend: str, timeout: float = 15.0) -> str:
    """Verify that llama-server can launch and that accelerator builds see a device."""
    if not server.is_file():
        raise RuntimeError(f"llama-server not found: {server}")
    try:
        proc = subprocess.run(
            [str(server), "--list-devices"],
            cwd=str(server.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except OSError as exc:
        detail = getattr(exc, "winerror", None)
        suffix = f" (Windows error {detail})" if detail is not None else ""
        raise RuntimeError(
            "llama-server could not be launched" + suffix + ". "
            "This usually means a required runtime DLL or graphics driver component is missing."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("llama-server runtime self-test timed out.") from exc

    output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    if proc.returncode != 0:
        known = describe_process_exit(proc.returncode, backend)
        detail = known or output or f"process exited with code {proc.returncode}"
        if known and output:
            detail += f"\n\nllama.cpp output: {output}"
        raise RuntimeError(f"llama-server runtime self-test failed: {detail}")

    lower = output.lower()
    if backend == "vulkan" and "vulkan" not in lower:
        raise RuntimeError(
            "The Vulkan llama.cpp runtime launches, but no Vulkan device was detected. "
            "Install/update the GPU vendor's Windows graphics driver and verify Vulkan support, then retry. "
            f"llama.cpp reported: {output or 'no devices'}"
        )
    if backend == "cuda" and "cuda" not in lower:
        raise RuntimeError(
            "The CUDA llama.cpp runtime launches, but no CUDA device was detected. "
            "Install/update the NVIDIA driver and retry. "
            f"llama.cpp reported: {output or 'no devices'}"
        )
    return output

def _extract_archive(archive: Path, runtime_dir: Path) -> None:
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(runtime_dir)
    elif archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(runtime_dir, filter="data")
    else:
        raise RuntimeError(f"Unsupported llama.cpp archive: {archive.name}")


def install_runtime(
    assets: list[RuntimeAsset],
    runtime_dir: Path,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    if not assets:
        raise RuntimeError("No llama.cpp runtime assets were selected.")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    downloads: list[Path] = []
    try:
        for index, asset in enumerate(assets):
            archive = runtime_dir / asset.name
            partial = archive.with_suffix(archive.suffix + ".part")
            request = urllib.request.Request(asset.url, headers={"User-Agent": "TTL-AI-Backend/0.1"})
            with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as fh:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        # Each archive owns an equal share of the visible progress bar.
                        if total:
                            aggregate_done = int(((index + (done / total)) / len(assets)) * 1_000_000)
                            progress(aggregate_done, 1_000_000)
                        else:
                            progress(done, 0)
            partial.replace(archive)
            downloads.append(archive)

        # Remove the previous runtime payload only after every required archive is downloaded.
        keep = {p.resolve() for p in downloads}
        for child in list(runtime_dir.iterdir()):
            if child.resolve() in keep:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for archive in downloads:
            _extract_archive(archive, runtime_dir)
        server = find_server(runtime_dir)
        if not server:
            raise RuntimeError("llama-server was not found after extracting the runtime archive.")
        if platform.system() != "Windows":
            server.chmod(server.stat().st_mode | 0o111)
        validate_runtime(server, assets[0].backend)
        for archive in downloads:
            try:
                archive.unlink()
            except OSError:
                pass
        return server
    except Exception:
        for partial in runtime_dir.glob("*.part"):
            try:
                partial.unlink()
            except OSError:
                pass
        raise
