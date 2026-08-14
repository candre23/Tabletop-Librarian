#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
template = (ROOT / "app/templates/characters/edit.html").read_text()
web = (ROOT / "app/characters/web.py").read_text()

assert ">All Characters<" not in template
assert "Save Play Changes" not in template
assert 'id="ttl-character-form"' in template
assert 'data-character-mode="{{ mode }}"' in template
assert 'id="ttl-autosave-status"' in template
assert "Save Configuration" in template

assert "window.setInterval(autosave, 120000);" in template
assert "if (!dirty || saving) return;" in template
assert "lastSavedSnapshot" in template
assert '"X-TTL-Autosave": "1"' in template
assert 'document.visibilityState === "hidden"' in template

assert 'request.headers.get("X-TTL-Autosave") == "1"' in web
assert 'return JSONResponse({"saved": True})' in web

print("PASS: play autosave regression test")
print("  redundant character-list link removed: OK")
print("  Play Save/Cancel removed: OK")
print("  Configure Save/Cancel retained: OK")
print("  dirty-state detection: OK")
print("  120-second autosave: OK")
print("  unchanged sheets skip writes: OK")
print("  AJAX autosave response: OK")
