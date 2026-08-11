#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
css = (ROOT / "app/static/css/main.css").read_text()

marker = "v0.4.22.15 unified light application theme"
assert marker in css
section = css[css.index(marker):]

assert "--ttl-app-bg: #e8eef1;" in section
assert "body:not(.ttl-character-ui)" in section
assert "background: #fff;" in section
assert ".ttl-global-nav" in section
assert "background: #dbe8ee;" in section
assert "table:not(.markdown-document table)" in section
assert "dialog" in section

# Dark values from the previous normalization may remain earlier in the CSS,
# but the unified light block must come later and therefore win the cascade.
old_marker = "v0.4.22.14 application visual normalization"
assert old_marker in css
assert css.index(marker) > css.index(old_marker)

print("PASS: unified light-theme regression")
print("  light application background: OK")
print("  light panels/forms/tables: OK")
print("  light global navigation: OK")
print("  light reader/admin utility surfaces: OK")
print("  final cascade overrides previous dark normalization: OK")
