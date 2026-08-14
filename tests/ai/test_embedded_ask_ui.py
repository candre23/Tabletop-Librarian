#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

base = (ROOT / "app/templates/base.html").read_text()
ask = (ROOT / "app/templates/ask.html").read_text()
css = (ROOT / "app/static/css/main.css").read_text()
main = (ROOT / "app/main.py").read_text()

assert "{% if not embed %}" in base
assert '{% include "_global_nav.html" %}' in base
assert "ttl-embedded-page" in base
assert "ttl-embedded-shell" in base

# GET and POST Ask routes must both propagate embed state.
assert '"embed": embed == "1"' in main
assert '"embed": embed,' in main
assert '<input type="hidden" name="embed" value="1">' in ask

marker = "body.ttl-embedded-page .ask-embedded-panel"
assert marker in css
section = css[css.index(marker):]
assert "body.ttl-embedded-page .ask-embedded-panel" in section
assert "background: #f7f9fa !important;" in section
assert ".reader-ai-pane-toolbar" in section
assert "background: #dbe8ee !important;" in section
assert ".ask-folder-dialog-topline" in section
assert ".ask-folder-frame" in section

print("PASS: embedded Ask UI regression")
print("  embedded Ask omits duplicate global nav: OK")
print("  embedded state survives form submission: OK")
print("  Ask-this-file pane header uses light high-contrast styling: OK")
print("  Ask-this-folder dialog header uses light high-contrast styling: OK")
print("  embedded Ask content uses unified light palette: OK")
