from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path
import sys

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import ocr
from app.library import manager
from app.search import extract


def make_image_bytes() -> bytes:
    image = Image.new("RGB", (200, 300), "white")
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


with tempfile.TemporaryDirectory() as temp_name:
    root = Path(temp_name)
    source_root = root / "share"
    source_root.mkdir()
    nested = source_root / "Comics"
    nested.mkdir()
    source = nested / "book.cbz"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("1.jpg", make_image_bytes())

    manager.LIBRARY_MANIFEST_FILE = root / "library_manifest.json"
    ocr.OCR_PDF_DIR = root / "ocr" / "pdf"
    ocr.OCR_META_DIR = root / "ocr" / "meta"
    ocr.OCR_WORK_DIR = root / "ocr" / "work"
    extract.TEXT_CACHE_DIR = root / "text"

    folder = {
        "name": "Test",
        "visibility": "players",
        "file_visibility": {},
        "sources": [
            {"type": "directory", "path": str(source_root)},
            {"type": "directory", "path": str(nested)},
        ],
    }

    first = manager.scan_folder(folder, generate_covers=False)
    docs = [doc for doc in first["documents"] if doc["path"] == str(source.resolve())]
    assert len(docs) == 1 and docs[0]["source_available"] is True, first

    derivative = ocr._pdf_path(source)
    derivative.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(derivative, "OCR comic text")
    ocr._write_metadata(source, derivative, 1)
    assert ocr.current_ocr_pdf(source) == derivative

    # Simulate a whole network share outage. The canonical path disappears, but
    # TTL must keep the remembered virtual-library entry and local derivative.
    offline_root = root / "share.offline"
    source_root.rename(offline_root)
    offline_scan = manager.scan_folder(folder, generate_covers=False)
    offline_docs = [doc for doc in offline_scan["documents"] if doc["path"] == str(source)]
    assert len(offline_docs) == 1, offline_scan
    assert offline_docs[0]["source_available"] is False, offline_docs[0]
    assert derivative.exists(), "temporary source outage must not delete OCR derivative"
    assert ocr.cached_ocr_pdf_for_unavailable_source(source) == derivative

    # Restore the share, then remove only the nested directory while the parent
    # source remains reachable. The reachable configured ancestor proves that
    # this is a real deletion rather than an outage.
    offline_root.rename(source_root)
    source.unlink()
    nested.rmdir()
    removed_scan = manager.scan_folder(folder, generate_covers=False)
    assert not any(doc.get("path") == str(source) for doc in removed_scan["documents"]), removed_scan
    assert not derivative.exists(), "confirmed source deletion must remove OCR derivative"
    assert not ocr._meta_path(source).exists(), "confirmed source deletion must remove OCR metadata"

print("PASS: offline source manifest preservation and confirmed-delete OCR cleanup")
