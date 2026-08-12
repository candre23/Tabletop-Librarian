from __future__ import annotations

import os
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fitz

from app import ocr
from app.search import extract


def make_pdf(path: Path, text: str = "") -> None:
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


with tempfile.TemporaryDirectory() as temp_name:
    root = Path(temp_name)
    source = root / "source.pdf"
    derivative_root = root / "ocr"
    text_cache = root / "text"
    make_pdf(source)

    ocr.OCR_PDF_DIR = derivative_root / "pdf"
    ocr.OCR_META_DIR = derivative_root / "meta"
    extract.TEXT_CACHE_DIR = text_cache

    output = ocr._pdf_path(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(output, "Persistent OCR text from the local derivative.")
    ocr._write_metadata(source, output, 1)

    assert ocr.current_ocr_pdf(source) == output, "current OCR derivative was not recognized"

    document = {
        "path": str(source),
        "type": "PDF",
        "text_status": "scanned",
    }
    result = extract.extract_document(document, force=True)
    assert result["status"] == "extracted", result
    cached = extract.load_cached_text(source)
    assert cached is not None
    assert cached.get("ocr_derived") is True
    assert "Persistent OCR text" in cached["pages"][0]["text"]
    assert cached["path"] == str(source.resolve()), "cache identity must remain the read-only source path"
    assert cached["extracted_from"] == str(output.resolve())

    # A changed source must invalidate the permanent derivative until OCR is rerun.
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert ocr.current_ocr_pdf(source) is None, "source changes must invalidate stale OCR derivatives"
    assert extract.load_cached_text(source) is None, "source changes must invalidate extracted text"

print("PASS: persistent local OCR derivative and source-change invalidation")
