from __future__ import annotations

import argparse
import os
import shutil
import stat
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist" / "linux"

SERVER_FILES = [
    "app",
    "pipelines",
    "data/system_packs",
    "pyproject.toml",
    "run.py",
]
BACKEND_FILES = [
    "ai_backend/ttl_ai_backend",
]


def _copy_path(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _copy_payload(stage: Path, paths: list[str]) -> None:
    for rel in paths:
        src = ROOT / rel
        if not src.exists():
            raise RuntimeError(f"Required release payload is missing: {rel}")
        _copy_path(src, stage / "payload" / rel)


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _archive(stage: Path, output: Path) -> None:
    with tarfile.open(output, "w:gz", format=tarfile.PAX_FORMAT) as tf:
        tf.add(stage, arcname=stage.name)


def build_server(version: str) -> Path:
    name = f"TTL-Server-Linux-x86_64-{version}"
    stage = DIST / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    _copy_payload(stage, SERVER_FILES)
    for script in ("install.sh", "uninstall.sh"):
        src = ROOT / "packaging" / "server" / "linux" / script
        shutil.copy2(src, stage / script)
        _make_executable(stage / script)
    (stage / "VERSION").write_text(version + "\n", encoding="utf-8")
    (stage / "README.txt").write_text(
        "Tabletop Librarian Server for Linux x86_64\n\n"
        "Install:   sudo ./install.sh\n"
        "Uninstall: sudo ./uninstall.sh\n\n"
        "The installer preserves existing user data on upgrades.\n"
        "The Local AI Backend is a separate product and is not included.\n",
        encoding="utf-8",
    )
    output = DIST / f"{name}.tar.gz"
    _archive(stage, output)
    return output


def build_backend(version: str) -> Path:
    name = f"TTL-AI-Linux-x86_64-{version}"
    stage = DIST / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    _copy_payload(stage, BACKEND_FILES)
    for script in ("install.sh", "uninstall.sh"):
        src = ROOT / "packaging" / "backend" / "linux" / script
        shutil.copy2(src, stage / script)
        _make_executable(stage / script)
    (stage / "VERSION").write_text(version + "\n", encoding="utf-8")
    (stage / "README.txt").write_text(
        "TTL Local AI Backend for Linux x86_64\n\n"
        "Install:   ./install.sh\n"
        "Uninstall: ./uninstall.sh\n\n"
        "This package is independent of the Tabletop Librarian Server.\n"
        "The Backend Manager downloads the selected llama.cpp runtime and models on demand.\n",
        encoding="utf-8",
    )
    output = DIST / f"{name}.tar.gz"
    _archive(stage, output)
    return output


def _version_from_pyproject(path: Path) -> str:
    import re

    text = path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Unable to determine version from {path}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build independent Tabletop Librarian Linux release archives")
    parser.add_argument("--output-dir", type=Path, help="override dist/linux output directory")
    args = parser.parse_args()

    global DIST
    if args.output_dir:
        DIST = args.output_dir.resolve()
    DIST.mkdir(parents=True, exist_ok=True)

    server_version = _version_from_pyproject(ROOT / "pyproject.toml")
    backend_version = _version_from_pyproject(ROOT / "ai_backend" / "pyproject.toml")
    server = build_server(server_version)
    backend = build_backend(backend_version)
    print(server)
    print(backend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
