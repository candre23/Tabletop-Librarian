#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
css = (ROOT / "app/static/css/main.css").read_text()

anchor = "body:not(.ttl-character-ui) .embedding-progress,"
assert anchor in css
section = css[css.index(anchor):]

assert "background: #e7edf0 !important;" in section
assert "color: #17272f !important;" in section
assert "background: #c7d2d7 !important;" in section
assert "background: #5fa4c7 !important;" in section
assert "progress::-webkit-progress-bar" in section
assert "progress::-moz-progress-bar" in section

print("PASS: embedding progress contrast regression")
print("  light progress panel: OK")
print("  dark readable status text: OK")
print("  visible light track: OK")
print("  high-contrast blue progress fill: OK")
