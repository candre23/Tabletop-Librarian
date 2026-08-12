from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import fitz

from app.config import PDF_STATUS_CACHE_DIR

logger = logging.getLogger(__name__)

DETECTOR_VERSION = 3


def _cache_path(path: Path) -> Path:
    raw = str(path.resolve()).encode("utf-8", errors="surrogatepass")
    key = hashlib.sha256(raw).hexdigest()[:24]
    return PDF_STATUS_CACHE_DIR / f"{key}.json"


def detect_pdf_text_status(path: Path) -> str:
    cache = _cache_path(path)

    try:
        stat = path.stat()
        source_signature = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    except OSError:
        source_signature = None

    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if (
                data.get("detector_version") == DETECTOR_VERSION
                and data.get("source") == source_signature
            ):
                status = data.get("status")
                if status in {"searchable", "scanned"}:
                    return status
        except Exception:
            pass

    status = "scanned"
    diagnostic = {
        "sampled_pages": 0,
        "pages_with_words": 0,
        "total_words": 0,
        "total_text_chars": 0,
    }

    try:
        document = fitz.open(path)

        try:
            page_count = document.page_count

            if page_count > 0:
                sample_count = min(12, page_count)

                if sample_count == 1:
                    indexes = [0]
                else:
                    indexes = sorted(
                        {
                            round(i * (page_count - 1) / (sample_count - 1))
                            for i in range(sample_count)
                        }
                    )

                for index in indexes:
                    try:
                        page = document.load_page(index)
                        words = page.get_text("words")
                        text = page.get_text("text").strip()
                    except Exception:
                        words = []
                        text = ""

                    diagnostic["sampled_pages"] += 1
                    diagnostic["total_words"] += len(words)
                    diagnostic["total_text_chars"] += len(text)

                    if len(words) >= 5:
                        diagnostic["pages_with_words"] += 1

                sampled = diagnostic["sampled_pages"]
                pages_with_words = diagnostic["pages_with_words"]
                total_words = diagnostic["total_words"]

                # Treat as searchable only when there is meaningful extracted
                # text on multiple sampled pages. A few stray words, page
                # labels, or metadata are not enough to make an image scan
                # meaningfully searchable.
                if sampled <= 2:
                    searchable = total_words >= 25
                else:
                    required_pages = max(2, round(sampled * 0.25))
                    searchable = (
                        pages_with_words >= required_pages
                        and total_words >= 50
                    )

                status = "searchable" if searchable else "scanned"

        finally:
            document.close()

    except Exception:
        logger.exception("Unable to inspect PDF text content: %s", path)
        # If inspection itself fails, don't falsely label the PDF as scanned.
        status = "searchable"

    PDF_STATUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache.write_text(
        json.dumps(
            {
                "detector_version": DETECTOR_VERSION,
                "source": source_signature,
                "status": status,
                **diagnostic,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    logger.info(
        "PDF text status: %s -> %s (%s words across %s sampled pages)",
        path,
        status,
        diagnostic["total_words"],
        diagnostic["sampled_pages"],
    )

    return status
