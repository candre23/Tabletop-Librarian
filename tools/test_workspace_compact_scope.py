#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ask=(ROOT/"app/templates/ask.html").read_text()

assert "locked_document_key and not workspace_compact" in ask
assert "locked_folder and not workspace_compact" in ask

print("PASS: workspace compact scope cleanup")
print("  locked-document banner suppressed: OK")
print("  locked-folder fallback banner suppressed: OK")
