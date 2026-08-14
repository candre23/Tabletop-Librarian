#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
css = (ROOT / "app/static/css/main.css").read_text()

marker = ".ttl-temp-dialog {"
assert marker in css
block = css[css.index(marker):]

assert "width: min(760px, calc(100vw - 36px));" in block
assert "max-height: min(820px, calc(100vh - 36px));" in block
assert "overflow: auto;" in block
assert "grid-template-columns: minmax(150px, 1.5fr)" in block
assert "@media (max-width: 820px)" in block
assert "@media (max-width: 520px)" in block

print("PASS: temporary modifier dialog layout regression test")
