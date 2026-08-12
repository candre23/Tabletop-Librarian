from __future__ import annotations

import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path

from fastapi.responses import FileResponse, Response

from app.config import CACHE_DIR

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
CBR_CACHE_DIR = CACHE_DIR / "comics"


def cbz_pages(path: Path) -> list[str]:
    with zipfile.ZipFile(path, "r") as archive:
        return sorted(
            [
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and Path(name).suffix.casefold() in IMAGE_EXTENSIONS
            ],
            key=str.casefold,
        )


def _find_unrar() -> str | None:
    return shutil.which("unrar")


def _find_7zip() -> str | None:
    return shutil.which("7zz") or shutil.which("7z")


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
    )


def _extract_cbr(path: Path) -> Path:
    cache_path = _cbr_cache_path(path)
    marker = cache_path / ".complete"

    if marker.exists():
        return cache_path

    if cache_path.exists():
        shutil.rmtree(cache_path)

    cache_path.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    if _find_unrar():
        result = _extract_with_unrar(path, cache_path)
        if result.returncode == 0:
            marker.touch()
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
            marker.touch()
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
        key=lambda item: str(item.relative_to(cache_path)).casefold(),
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
