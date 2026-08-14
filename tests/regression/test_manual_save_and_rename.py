#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
template = (ROOT / "app/templates/characters/edit.html").read_text()
web = (ROOT / "app/characters/web.py").read_text()

assert "Unsaved changes - click to save manually" in template
assert 'autosaveStatus?.addEventListener("click"' in template
assert "window.setInterval(autosave, 120000);" in template
assert 'autosaveStatus.disabled = state !== "dirty";' in template

assert 'mode == "configure" and "name" in schema.fields' in web
assert 'submitted_name = form_data.get("field__name")' in web
assert 'record.data["name"] = str(submitted_name).strip()' in web

# Display/list naming is sourced from authoritative character data.
assert 'def _character_name(data:' in web
assert 'row.get("data") or {}' in web

print("PASS: manual save and rename regression test")
print("  dirty autosave status is clickable: OK")
print("  120-second autosave retained: OK")
print("  configure name explicitly persisted: OK")
print("  play/list display name derives from saved data: OK")
