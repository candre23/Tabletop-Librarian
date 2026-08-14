#!/usr/bin/env python3
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.uploads as uploads

template = (ROOT / "app/templates/uploads.html").read_text()
main = (ROOT / "app/main.py").read_text()
css = (ROOT / "app/static/css/main.css").read_text()

assert 'action="/uploads/delete"' in template
assert "danger-button" in template
assert "confirm('Delete this incoming upload?" in template
assert '@app.post("/uploads/delete")' in main
assert "currently used as a library source" in main

assert "body:not(.ttl-character-ui) .upload-row" in css
assert "background: #eef3f5 !important;" in css
assert ".upload-info strong" in css
assert ".upload-actions" in css

# Exact staging deletion helper must not delete arbitrary files.
with tempfile.TemporaryDirectory() as td:
    temp = Path(td)
    old_upload_dir = uploads.UPLOAD_DIR
    uploads.UPLOAD_DIR = temp / "uploads"

    try:
        staged = uploads.unique_upload_path("gm", "pending.txt")
        staged.write_text("pending")
        assert uploads.delete_upload(str(staged)) is True
        assert not staged.exists()

        outside = temp / "outside.txt"
        outside.write_text("do not delete")
        assert uploads.delete_upload(str(outside)) is False
        assert outside.exists()
    finally:
        uploads.UPLOAD_DIR = old_upload_dir

print("PASS: upload deletion + contrast regression")
print("  incoming upload rows use light readable background: OK")
print("  GM delete control present: OK")
print("  staged upload deletion works: OK")
print("  arbitrary filesystem deletion blocked: OK")
print("  assigned-source protection present: OK")
