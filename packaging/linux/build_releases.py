from __future__ import annotations

import argparse
import hashlib
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

TESTED_PLATFORM = "Ubuntu 26.04 LTS x86_64"
SUPPORT_NOTE = (
    "Officially tested on Ubuntu 26.04 LTS x86_64. "
    "Other Linux distributions are community-supported and may require adaptation."
)


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
        target = stage / "payload" / rel
        _copy_path(src, target)




def _copy_release_docs(stage: Path, *, server: bool) -> None:
    docs = stage / "documentation"
    docs.mkdir(parents=True, exist_ok=True)
    for rel in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"):
        shutil.copy2(ROOT / rel, docs / Path(rel).name)
    selected = ["INSTALLATION.md", "AI_BACKEND.md"]
    if server:
        selected.extend(["USER_GUIDE.md", "SYSTEM_PACKS.md", "OCR.md", "PIPELINES.md"])
    for name in selected:
        shutil.copy2(ROOT / "docs" / name, docs / name)
    if server:
        reference = docs / "reference"
        shutil.copytree(ROOT / "docs" / "reference", reference)

def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _archive(stage: Path, output: Path) -> None:
    with tarfile.open(output, "w:gz", format=tarfile.PAX_FORMAT) as tf:
        tf.add(stage, arcname=stage.name)


def _write_release_info(stage: Path, *, product: str, version: str) -> None:
    (stage / "RELEASE_INFO.txt").write_text(
        f"Product: {product}\n"
        f"Version: {version}\n"
        f"Architecture: Linux x86_64\n"
        f"Tested platform: {TESTED_PLATFORM}\n"
        f"Support: {SUPPORT_NOTE}\n",
        encoding="utf-8",
    )


def build_server(version: str) -> Path:
    name = f"TTL-Server-Linux-x86_64-{version}"
    stage = DIST / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    _copy_payload(stage, SERVER_FILES)
    _copy_release_docs(stage, server=True)
    for script in ("install.sh", "uninstall.sh"):
        src = ROOT / "packaging" / "server" / "linux" / script
        shutil.copy2(src, stage / script)
        _make_executable(stage / script)
    (stage / "VERSION").write_text(version + "\n", encoding="utf-8")
    _write_release_info(stage, product="Tabletop Librarian Server", version=version)
    (stage / "README.txt").write_text(
        "Tabletop Librarian Server for Linux x86_64\n\n"
        "Install:   sudo ./install.sh\n"
        "Uninstall: sudo ./uninstall.sh\n\n"
        "The installer preserves existing user data on upgrades and normal uninstall.\n"
        "Use uninstall.sh --purge-data only when you intentionally want to remove user data.\n\n"
        "The Local AI Backend is a separate product and is not included.\n\n"
        f"{SUPPORT_NOTE}\n",
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
    _copy_release_docs(stage, server=False)
    for script in ("install.sh", "uninstall.sh"):
        src = ROOT / "packaging" / "backend" / "linux" / script
        shutil.copy2(src, stage / script)
        _make_executable(stage / script)
    (stage / "VERSION").write_text(version + "\n", encoding="utf-8")
    _write_release_info(stage, product="TTL Local AI Backend", version=version)
    (stage / "README.txt").write_text(
        "TTL Local AI Backend for Linux x86_64\n\n"
        "Install:   ./install.sh\n"
        "Uninstall: ./uninstall.sh\n\n"
        "This package is independent of the Tabletop Librarian Server.\n"
        "The Backend Manager downloads the selected llama.cpp runtime and models on demand.\n"
        "Normal uninstall preserves settings, models, and downloaded runtimes.\n\n"
        f"{SUPPORT_NOTE}\n",
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_release_manifest(server: Path, backend: Path, server_version: str, backend_version: str) -> None:
    manifest = DIST / "LINUX_RELEASE_MANIFEST.txt"
    manifest.write_text(
        "Tabletop Librarian Linux Release Assets\n"
        "======================================\n\n"
        f"Tested platform: {TESTED_PLATFORM}\n"
        f"Support policy: {SUPPORT_NOTE}\n\n"
        f"Server:  {server.name}\n"
        f"Version: {server_version}\n"
        f"SHA256:  {_sha256(server)}\n\n"
        f"Backend: {backend.name}\n"
        f"Version: {backend_version}\n"
        f"SHA256:  {_sha256(backend)}\n",
        encoding="utf-8",
    )

    checksums = DIST / "SHA256SUMS.txt"
    checksums.write_text(
        f"{_sha256(server)}  {server.name}\n"
        f"{_sha256(backend)}  {backend.name}\n",
        encoding="utf-8",
    )


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
    _write_release_manifest(server, backend, server_version, backend_version)
    print(server)
    print(backend)
    print(DIST / "SHA256SUMS.txt")
    print(DIST / "LINUX_RELEASE_MANIFEST.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
