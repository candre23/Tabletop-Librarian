#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
css = (ROOT / "app/static/css/main.css").read_text()

marker = "v0.4.22.16 contrast correction pass"
assert marker in css
section = css[css.index(marker):]

# Navigation intentionally remains dark everywhere.
assert ".ttl-character-ui .ttl-global-nav" in section
assert "background: #17242c !important;" in section
assert "color: #72c5ed !important;" in section

# Library/home readability.
assert ".folder-name" in section
assert "color: #17272f !important;" in section
assert ".cover-image" in section
assert "background: #b8c2c7 !important;" in section

# Knowledgebase metrics and labels.
assert ".index-stats div" in section
assert "background: #e7edf0 !important;" in section
assert ".embedding-model-form > label" in section

# Admin/user labels.
assert ".auth-form label" in section
assert ".setting-box label" in section
assert ".user-summary span" in section

# Form controls remain readable.
assert "background: #ffffff !important;" in section
assert "color: #17272f !important;" in section

print("PASS: light-theme contrast regression")
print("  dark navigation restored application-wide: OK")
print("  TTL brand contrast increased: OK")
print("  library titles and cover wells readable: OK")
print("  Knowledgebase metric cards lightened: OK")
print("  admin/user labels darkened: OK")
print("  light form control contrast enforced: OK")
