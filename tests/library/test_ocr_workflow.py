from __future__ import annotations

import os
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
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

# Progress comes from the OCRmyPDF progress hook, not terminal/Rich parsing.
with tempfile.TemporaryDirectory() as temp_name:
    progress = Path(temp_name) / "progress.json"
    progress.write_text(
        '{"desc":"Scanning contents","unit":"page","current":7,"total":26}',
        encoding="utf-8",
    )
    ocr._apply_progress_file(progress)
    status = ocr.ocr_job_status()
    assert status["stage"] == "ocr_scan", status
    assert status["current_page"] == 7 and status["total_pages"] == 26, status
    assert 26.0 < status["percent"] < 27.0, status

    progress.write_text(
        '{"desc":"Linearizing","unit":"%","current":50,"total":100}',
        encoding="utf-8",
    )
    ocr._apply_progress_file(progress)
    status = ocr.ocr_job_status()
    assert status["stage"] == "ocr_postprocess", status
    assert status["current_page"] == 0 and status["total_pages"] == 0, status
    assert status["percent"] == 50.0, status

# Library Management should distinguish an image-only source with and without
# a valid persistent local OCR derivative.
with tempfile.TemporaryDirectory() as temp_name:
    from app.library import manager

    root = Path(temp_name)
    source = root / "scan.pdf"
    make_pdf(source)
    ocr.OCR_PDF_DIR = root / "ocr" / "pdf"
    ocr.OCR_META_DIR = root / "ocr" / "meta"

    folder = {"visibility": "players", "file_visibility": {}}
    record = manager._document_record(source, folder, False, "file")
    assert record is not None and record["text_status"] == "scanned", record
    assert record["ocr_status"] == "required", record

    derivative = ocr._pdf_path(source)
    derivative.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(derivative, "OCR text")
    ocr._write_metadata(source, derivative, 1)
    record = manager._document_record(source, folder, False, "file")
    assert record is not None and record["ocr_status"] == "complete", record

# OCR completion marks the knowledgebase stale but does not rebuild it.
with tempfile.TemporaryDirectory() as temp_name:
    from app import knowledgebase

    root = Path(temp_name)
    source = root / "queued.pdf"
    make_pdf(source)
    knowledgebase.STATE_DIR = root / "kb"
    knowledgebase.STATE_FILE = knowledgebase.STATE_DIR / "state.json"

    original_documents = ocr.ocr_documents
    original_run = ocr._run_ocr
    try:
        ocr.ocr_documents = lambda: [{
            "key": "queued",
            "path": str(source),
            "ocr_ready": False,
            "display_name": "queued",
        }]
        ocr._run_ocr = lambda path: path
        ocr._cancel_event.clear()
        ocr._worker(["queued"])
        job = ocr.ocr_job_status()
        assert job["stage"] == "complete", job
        assert "Update Knowledgebase" in job["message"], job
        kb = knowledgebase.knowledgebase_status()
        assert kb["needs_update"] is True, kb
        assert kb["last_reason"] == "OCR text is available; knowledgebase update required", kb
    finally:
        ocr.ocr_documents = original_documents
        ocr._run_ocr = original_run

print("PASS: OCR progress, library status tags, and manual knowledgebase update behavior")

# CBZ/CBR archives use persistent OCR PDF derivatives and preserve natural page order.
with tempfile.TemporaryDirectory() as temp_name:
    import io
    import zipfile
    from PIL import Image
    from app.library import manager
    from app.readers import comic

    root = Path(temp_name)
    comic_source = root / "comic.cbz"
    ocr.OCR_PDF_DIR = root / "ocr" / "pdf"
    ocr.OCR_META_DIR = root / "ocr" / "meta"
    ocr.OCR_WORK_DIR = root / "ocr" / "work"
    extract.TEXT_CACHE_DIR = root / "text"

    def image_bytes(label: str) -> bytes:
        image = Image.new("RGB", (320, 480), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return buffer.getvalue()

    with zipfile.ZipFile(comic_source, "w") as archive:
        archive.writestr("10.jpg", image_bytes("10"))
        archive.writestr("2.jpg", image_bytes("2"))
        archive.writestr("1.jpg", image_bytes("1"))

    assert comic.cbz_pages(comic_source) == ["1.jpg", "2.jpg", "10.jpg"]

    assembled = root / "assembled.pdf"
    pages = ocr._build_comic_input_pdf(comic_source, assembled)
    assert pages == 3
    doc = fitz.open(assembled)
    try:
        assert doc.page_count == 3
    finally:
        doc.close()

    folder = {"visibility": "players", "file_visibility": {}}
    record = manager._document_record(comic_source, folder, False, "file")
    assert record is not None and record["type"] == "CBZ", record
    assert record["ocr_status"] == "required", record

    derivative = ocr._pdf_path(comic_source)
    derivative.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(derivative, "Comic OCR text")
    ocr._write_metadata(comic_source, derivative, 3)
    record = manager._document_record(comic_source, folder, False, "file")
    assert record is not None and record["ocr_status"] == "complete", record

    result = extract.extract_document(record, force=True)
    assert result["status"] == "extracted", result
    cached = extract.load_cached_text(comic_source)
    assert cached is not None and cached["ocr_derived"] is True, cached
    assert "Comic OCR text" in cached["pages"][0]["text"]

    original_cbr_pages = comic.cbr_page_files
    fake_cbr = root / "comic.cbr"
    fake_cbr.write_bytes(b"placeholder")
    cbr_pages_dir = root / "cbr-pages"
    cbr_pages_dir.mkdir()
    for name in ("10.jpg", "2.jpg", "1.jpg"):
        (cbr_pages_dir / name).write_bytes(image_bytes(name))
    try:
        comic.cbr_page_files = lambda path: sorted(
            cbr_pages_dir.glob("*.jpg"),
            key=lambda item: comic._natural_sort_key(item.name),
        )
        assembled_cbr = root / "assembled-cbr.pdf"
        assert ocr._build_comic_input_pdf(fake_cbr, assembled_cbr) == 3
    finally:
        comic.cbr_page_files = original_cbr_pages

print("PASS: CBZ/CBR OCR derivative support and natural comic page ordering")
