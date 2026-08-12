from __future__ import annotations

import hashlib
import io
import logging
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.config import COVER_CACHE_DIR, COVER_HEIGHT, COVER_WIDTH, MANUAL_COVER_DIR
from app.readers.comic import cbr_page_files

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
ARCHIVE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def cover_key(folder_path: str, filename: str) -> str:
    raw = f"{folder_path}\0{filename}".encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:24]


def cached_cover_path(folder_path: str, filename: str) -> Path:
    return COVER_CACHE_DIR / f"{cover_key(folder_path, filename)}.webp"


def manual_cover_path(folder_path: str, filename: str) -> Path:
    return MANUAL_COVER_DIR / f"{cover_key(folder_path, filename)}.webp"


def get_cover_path(folder_path: str, filename: str) -> Path | None:
    manual = manual_cover_path(folder_path, filename)
    if manual.exists():
        return manual

    cached = cached_cover_path(folder_path, filename)
    if cached.exists():
        return cached

    return None


def save_manual_cover(folder_path: str, filename: str, source_path: Path) -> Path:
    MANUAL_COVER_DIR.mkdir(parents=True, exist_ok=True)
    destination = manual_cover_path(folder_path, filename)

    with Image.open(source_path) as source:
        image = _fit_cover(source.convert("RGB"))
        image.save(destination, "WEBP", quality=88, method=4)

    return destination


def remove_manual_cover(folder_path: str, filename: str) -> None:
    manual_cover_path(folder_path, filename).unlink(missing_ok=True)


def ensure_cover(folder_path: str, filename: str, doc_type: str) -> Path | None:
    source = Path(folder_path) / filename
    destination = cached_cover_path(folder_path, filename)

    if destination.exists():
        return destination

    COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if doc_type == "PDF":
            image = _pdf_cover(source)
        elif doc_type == "CBZ":
            image = _cbz_cover(source)
        elif doc_type == "CBR":
            image = _cbr_cover(source)
        elif doc_type == "Image":
            image = _image_cover(source)
        elif doc_type in {"Text", "Markdown"}:
            image = _text_cover(source.stem)
        else:
            image = None

        if image is None:
            return None

        image = _fit_cover(image)
        image.save(destination, "WEBP", quality=84, method=4)
        logger.info("Generated cover for %s", source)
        return destination

    except Exception:
        logger.exception("Cover generation failed for %s", source)
        return None


def invalidate_cover(folder_path: str, filename: str) -> None:
    path = cached_cover_path(folder_path, filename)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Unable to remove cached cover %s", path)


def _pdf_cover(path: Path) -> Image.Image:
    document = fitz.open(path)
    try:
        if document.page_count < 1:
            raise ValueError("PDF contains no pages")
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        return image
    finally:
        document.close()


def _image_cover(path: Path) -> Image.Image:
    with Image.open(path) as source:
        source.seek(0)
        return source.convert("RGB").copy()


def _cbz_cover(path: Path) -> Image.Image:
    with zipfile.ZipFile(path, "r") as archive:
        names = sorted(
            (
                name
                for name in archive.namelist()
                if Path(name).suffix.casefold() in ARCHIVE_IMAGE_EXTENSIONS
                and not name.endswith("/")
            ),
            key=str.casefold,
        )
        if not names:
            raise ValueError("CBZ contains no supported images")

        data = archive.read(names[0])
        with Image.open(io.BytesIO(data)) as source:
            return source.convert("RGB").copy()


def _find_7zip() -> str:
    executable = shutil.which("7zz") or shutil.which("7z")
    if not executable:
        raise RuntimeError("7-Zip command-line executable not found")
    return executable


def _cbr_cover(path: Path) -> Image.Image:
    pages = cbr_page_files(path)

    if not pages:
        raise ValueError("CBR contains no supported images")

    with Image.open(pages[0]) as source:
        return source.convert("RGB").copy()

def _text_cover(title: str) -> Image.Image:
    image = Image.new("RGB", (COVER_WIDTH, COVER_HEIGHT), (36, 40, 44))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)

    words = title.replace("_", " ").split()
    lines = []
    line = ""

    for word in words:
        candidate = word if not line else f"{line} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= COVER_WIDTH - 70:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word

    if line:
        lines.append(line)

    line_height = 34
    total_height = len(lines) * line_height
    y = max(60, (COVER_HEIGHT - total_height) // 2)

    for text in lines[:10]:
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (COVER_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), text, fill=(235, 238, 240), font=font)
        y += line_height

    return image


def _fit_cover(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image.convert("RGB"))
    image.thumbnail((COVER_WIDTH, COVER_HEIGHT), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (COVER_WIDTH, COVER_HEIGHT), (24, 27, 30))
    x = (COVER_WIDTH - image.width) // 2
    y = (COVER_HEIGHT - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas
