#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
template = (ROOT / "app/templates/admin_knowledgebase.html").read_text()

assert 'fetch("/admin/rag/embeddings/status"' in template
assert "setInterval(poll, 1000);" in template
assert "window.location.reload()" not in template
assert "window.location.href" not in template

print("PASS: knowledgebase polling regression test")
print("  lightweight embedding-status polling retained: OK")
print("  repeated full-page reload removed: OK")
