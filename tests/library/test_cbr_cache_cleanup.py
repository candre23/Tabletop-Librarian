from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.library.manager as manager
import app.ocr as ocr
import app.readers.comic as comic


def _marker(cache: Path, source: Path, signature: dict[str, int] | None = None) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    if signature is None:
        signature = {"size": 1, "mtime_ns": 1}
    (cache / ".complete").write_text(
        json.dumps({"source_path": str(source), "source": signature}) + "\n",
        encoding="utf-8",
    )
    (cache / "page1.jpg").write_bytes(b"abc")


def main() -> None:
    original_cache = comic.CBR_CACHE_DIR
    original_known = manager.known_library_document_paths
    original_current = ocr.current_ocr_pdf
    original_cached = ocr.cached_ocr_pdf_for_unavailable_source

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cache_root = root / "cache"
        comic.CBR_CACHE_DIR = cache_root

        online = root / "online.cbr"
        online.write_bytes(b"rar")
        online_sig = comic._cbr_source_signature(online)
        online_cache = comic._cbr_cache_path(online)
        _marker(online_cache, online, online_sig)

        offline = root / "offline.cbr"
        offline_cache = comic._cbr_cache_path(offline)
        _marker(offline_cache, offline)

        redundant = root / "redundant.cbr"
        redundant.write_bytes(b"rar")
        redundant_cache = comic._cbr_cache_path(redundant)
        _marker(redundant_cache, redundant, comic._cbr_source_signature(redundant))
        redundant_pdf = root / "redundant.pdf"
        redundant_pdf.write_bytes(b"pdf")

        orphan = root / "orphan.cbr"
        orphan_cache = comic._cbr_cache_path(orphan)
        _marker(orphan_cache, orphan)

        partial = cache_root / "partial"
        partial.mkdir(parents=True)
        (partial / "page.jpg").write_bytes(b"junk")

        manager.known_library_document_paths = lambda: {str(online), str(offline), str(redundant)}
        ocr.current_ocr_pdf = lambda path: redundant_pdf if Path(path) == redundant else None
        ocr.cached_ocr_pdf_for_unavailable_source = lambda path: None

        result = comic.cleanup_cbr_cache()
        assert online_cache.exists(), "current online fallback cache should be kept"
        assert offline_cache.exists(), "known offline fallback cache should be kept"
        assert not redundant_cache.exists(), "OCR-complete CBR cache should be removed"
        assert not orphan_cache.exists(), "orphaned CBR cache should be removed"
        assert not partial.exists(), "partial extraction cache should be removed"
        assert result["removed"] == 3, result
        assert result["kept"] == 2, result

        # Explicit removal helper should remove one source cache immediately.
        assert comic.remove_cbr_cache(online) is True
        assert not online_cache.exists()

    comic.CBR_CACHE_DIR = original_cache
    manager.known_library_document_paths = original_known
    ocr.current_ocr_pdf = original_current
    ocr.cached_ocr_pdf_for_unavailable_source = original_cached
    print("CBR cache cleanup tests passed")


if __name__ == "__main__":
    main()
