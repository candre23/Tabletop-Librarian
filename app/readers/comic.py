from __future__ import annotations

import hashlib
import json
import re
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from fastapi.responses import FileResponse, Response

from app.config import CACHE_DIR

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
CBR_CACHE_DIR = CACHE_DIR / "comics"


def _natural_sort_key(value: str) -> list[tuple[int, object]]:
    """Sort archive paths naturally while keeping directory context."""
    return [
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in re.split(r"(\d+)", value)
    ]


def cbz_pages(path: Path) -> list[str]:
    with zipfile.ZipFile(path, "r") as archive:
        return sorted(
            [
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and Path(name).suffix.casefold() in IMAGE_EXTENSIONS
            ],
            key=_natural_sort_key,
        )


def _packaged_tool(*parts: str) -> str | None:
    if not getattr(sys, "frozen", False):
        return None
    candidate = Path(sys.executable).resolve().parent.joinpath(*parts)
    return str(candidate) if candidate.is_file() else None


def _find_unrar() -> str | None:
    configured = os.environ.get("TTL_UNRAR", "").strip()
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("unrar") or _packaged_tool("vendor", "unrar", "unrar.exe")


def _find_7zip() -> str | None:
    configured = os.environ.get("TTL_7ZIP", "").strip()
    if configured and Path(configured).is_file():
        return configured

    found = shutil.which("7zz") or shutil.which("7z")
    if found:
        return found

    packaged = _packaged_tool("vendor", "7zip", "7z.exe")
    if packaged:
        return packaged

    if os.name == "nt":
        for root_name in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(root_name, "").strip()
            if not root:
                continue
            candidate = Path(root) / "7-Zip" / "7z.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _cbr_cache_path(path: Path) -> Path:
    raw = str(path.resolve()).encode("utf-8", errors="surrogatepass")
    key = hashlib.sha256(raw).hexdigest()[:24]
    return CBR_CACHE_DIR / key


def _extract_with_unrar(path: Path, cache_path: Path) -> subprocess.CompletedProcess:
    unrar = _find_unrar()
    if not unrar:
        raise FileNotFoundError("unrar is not installed")

    return subprocess.run(
        [
            unrar,
            "x",
            "-o+",
            "-idq",
            str(path),
            str(cache_path) + "/",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        creationflags=_subprocess_creationflags(),
    )


def _extract_with_7zip(path: Path, cache_path: Path) -> subprocess.CompletedProcess:
    sevenzip = _find_7zip()
    if not sevenzip:
        raise FileNotFoundError("7-Zip is not installed")

    return subprocess.run(
        [
            sevenzip,
            "x",
            "-y",
            f"-o{cache_path}",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        creationflags=_subprocess_creationflags(),
    )


def _cbr_source_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _cbr_cache_current(path: Path, marker: Path) -> bool:
    if not marker.exists():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        return payload.get("source") == _cbr_source_signature(path)
    except Exception:
        return False


def _write_cbr_marker(path: Path, marker: Path) -> None:
    marker.write_text(
        json.dumps({
            "source_path": str(path.expanduser().resolve(strict=False)),
            "source": _cbr_source_signature(path),
        }) + "\n",
        encoding="utf-8",
    )


def remove_cbr_cache(path: Path) -> bool:
    """Remove the extracted-image cache for one canonical CBR source."""
    cache_path = _cbr_cache_path(path.expanduser().resolve(strict=False))
    if not cache_path.exists():
        return False
    shutil.rmtree(cache_path, ignore_errors=True)
    return not cache_path.exists()


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def cbr_cache_status() -> dict[str, int]:
    directories = 0
    bytes_used = 0
    if CBR_CACHE_DIR.exists():
        for item in CBR_CACHE_DIR.iterdir():
            if item.is_dir():
                directories += 1
                bytes_used += _directory_size(item)
    return {"directories": directories, "bytes": bytes_used}


def cleanup_cbr_cache() -> dict[str, int]:
    """Remove obsolete CBR extraction caches without touching offline sources.

    The library manifest remains authoritative when a source is temporarily
    unavailable. A cache tied to a known offline CBR is preserved unless a
    persistent OCR PDF already supersedes it.
    """
    from app.library.manager import known_library_document_paths
    from app.ocr import current_ocr_pdf, cached_ocr_pdf_for_unavailable_source

    CBR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    all_known_paths = {
        str(Path(value).expanduser().resolve(strict=False))
        for value in known_library_document_paths()
    }
    known_paths = {
        value for value in all_known_paths
        if Path(value).suffix.casefold() == ".cbr"
    }
    manifest_is_authoritative = bool(all_known_paths)
    expected = {
        _cbr_cache_path(Path(value)).name: Path(value)
        for value in known_paths
    }

    removed = 0
    bytes_freed = 0
    kept = 0
    for item in list(CBR_CACHE_DIR.iterdir()):
        if not item.is_dir():
            try:
                size = item.stat().st_size
                item.unlink()
                removed += 1
                bytes_freed += size
            except OSError:
                pass
            continue

        source = expected.get(item.name)
        marker = item / ".complete"
        should_remove = not marker.exists() or (source is None and manifest_is_authoritative)

        # When no manifest documents exist yet, be conservative with complete
        # caches rather than treating an uninitialized/offline library as empty.
        if source is None and marker.exists() and not manifest_is_authoritative:
            try:
                payload = json.loads(marker.read_text(encoding="utf-8"))
                source_text = str(payload.get("source_path") or "")
                source = Path(source_text) if source_text else None
            except Exception:
                source = None

        if not should_remove and source is not None:
            derivative = current_ocr_pdf(source)
            if derivative is None and not source.exists():
                derivative = cached_ocr_pdf_for_unavailable_source(source)
            if derivative is not None:
                should_remove = True
            elif source.exists() and not _cbr_cache_current(source, marker):
                should_remove = True

        if should_remove:
            size = _directory_size(item)
            shutil.rmtree(item, ignore_errors=True)
            if not item.exists():
                removed += 1
                bytes_freed += size
        else:
            kept += 1

    return {"removed": removed, "kept": kept, "bytes_freed": bytes_freed}


def _extract_cbr(path: Path) -> Path:
    cache_path = _cbr_cache_path(path)
    marker = cache_path / ".complete"

    if _cbr_cache_current(path, marker):
        return cache_path

    if cache_path.exists():
        shutil.rmtree(cache_path)

    cache_path.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    if _find_unrar():
        result = _extract_with_unrar(path, cache_path)
        if result.returncode == 0:
            _write_cbr_marker(path, marker)
            return cache_path

        errors.append(
            "unrar failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

        shutil.rmtree(cache_path, ignore_errors=True)
        cache_path.mkdir(parents=True, exist_ok=True)

    if _find_7zip():
        result = _extract_with_7zip(path, cache_path)
        if result.returncode == 0:
            _write_cbr_marker(path, marker)
            return cache_path

        errors.append(
            "7-Zip failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    shutil.rmtree(cache_path, ignore_errors=True)

    if not errors:
        raise RuntimeError("Neither unrar nor 7-Zip is available for CBR extraction.")

    raise RuntimeError("\n\n".join(errors))


def cbr_page_files(path: Path) -> list[Path]:
    cache_path = _extract_cbr(path)

    pages = [
        item
        for item in cache_path.rglob("*")
        if item.is_file()
        and item.name != ".complete"
        and item.suffix.casefold() in IMAGE_EXTENSIONS
    ]

    return sorted(
        pages,
        key=lambda item: _natural_sort_key(str(item.relative_to(cache_path))),
    )


def cbr_pages(path: Path) -> list[str]:
    cache_path = _extract_cbr(path)
    return [str(item.relative_to(cache_path)) for item in cbr_page_files(path)]


def comic_pages(path: Path) -> list[str]:
    if path.suffix.casefold() == ".cbz":
        return cbz_pages(path)

    if path.suffix.casefold() == ".cbr":
        return cbr_pages(path)

    raise ValueError("Unsupported comic archive")


def comic_page(path: Path, page_index: int):
    if path.suffix.casefold() == ".cbz":
        pages = cbz_pages(path)

        if page_index < 0 or page_index >= len(pages):
            return Response(status_code=404)

        name = pages[page_index]
        suffix = Path(name).suffix.casefold()

        with zipfile.ZipFile(path, "r") as archive:
            data = archive.read(name)

        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(suffix, "application/octet-stream")

        return Response(
            content=data,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=3600"},
        )

    if path.suffix.casefold() == ".cbr":
        pages = cbr_page_files(path)

        if page_index < 0 or page_index >= len(pages):
            return Response(status_code=404)

        page = pages[page_index]

        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(page.suffix.casefold(), "application/octet-stream")

        return FileResponse(
            page,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=3600"},
        )

    return Response(status_code=415)
