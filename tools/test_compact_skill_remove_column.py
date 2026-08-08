#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
css = (ROOT / "app/static/css/main.css").read_text()

marker = "v0.4.19.3: compact square remove column for skill tables"
assert marker in css
block = css[css.rindex(marker):]

assert ".ttl-skill-table th:last-child" in block
assert "width: 26px;" in block
assert "height: 26px;" in block
assert "width: 24px;" in block
assert "height: 24px;" in block
assert "place-items: center;" in block

print("PASS: compact skill remove-column regression test")
