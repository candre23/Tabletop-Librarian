#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
css = (ROOT / "app/static/css/main.css").read_text()

anchor = "--ttl-app-bg: #e8eef1;"
assert anchor in css
section = css[css.index(anchor):]

assert "--ttl-app-bg: #e8eef1;" in section
assert "body:not(.ttl-character-ui)" in section
assert "background: #fff;" in section
assert ".ttl-global-nav" in section
assert "background: #dbe8ee;" in section
assert "table:not(.markdown-document table)" in section
assert "dialog" in section

# Dark normalization values may remain earlier in the CSS, but the unified
# light variables must appear after the dark application palette.
dark_anchor = "--ttl-app-bg: #10171b;"
assert dark_anchor in css
assert css.index(anchor) > css.index(dark_anchor)

print("PASS: unified light-theme regression")
print("  light application background: OK")
print("  light panels/forms/tables: OK")
print("  light global navigation: OK")
print("  light reader/admin utility surfaces: OK")
print("  final cascade overrides previous dark normalization: OK")
