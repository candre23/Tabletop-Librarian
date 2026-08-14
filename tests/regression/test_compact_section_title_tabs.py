#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
css = (ROOT / "app/static/css/main.css").read_text()

anchor = ".ttl-character-ui .ttl-sheet-section {\n    position: relative;"
assert anchor in css
block = css[css.rindex(anchor):]

assert ".ttl-character-ui .ttl-sheet-section {" in block
assert "position: relative;" in block
assert "display: block;" in block
assert "padding-top: 22px;" in block

assert ".ttl-character-ui .ttl-sheet-section-heading {" in block
assert "position: absolute;" in block
assert "width: max-content;" in block
assert "min-width: 0;" in block
assert "flex-direction: row;" in block

assert ".ttl-character-ui .ttl-sheet-section-heading p {" in block
assert "display: none;" in block

print("PASS: compact top-left section title tabs")
