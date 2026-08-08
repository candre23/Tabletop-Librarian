#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
css = (ROOT / "app/static/css/main.css").read_text()

for rel in (
    "app/templates/characters/index.html",
    "app/templates/characters/edit.html",
    "app/templates/characters/create.html",
    "app/templates/characters/advance.html",
):
    text = (ROOT / rel).read_text()
    assert '<body class="ttl-character-ui">' in text, rel
    assert '<style>' not in text, f"legacy page-local style remains in {rel}"

required_css = (
    ".ttl-character-ui",
    "--sheet-paper",
    ".ttl-character-ui .ttl-global-nav",
    ".ttl-character-ui .ttl-char-wrap",
    ".ttl-character-ui .ttl-sheet-section",
    "nth-child(6n + 2)",
    "nth-child(6n + 3)",
    ".ttl-character-ui .ttl-field input:not([type=\"checkbox\"])",
    ".ttl-character-ui .ttl-collection-row",
    ".ttl-character-ui .ttl-picker-dialog",
)
for marker in required_css:
    assert marker in css, marker

assert "max-width: 1680px" in css
assert "font-size: 9.5px" in css
assert "border-radius: 1px" in css

print("PASS: dense character-sheet UI regression test")
print("  character pages scoped to new visual system: OK")
print("  legacy page-local spacious styles removed: OK")
print("  near-full-width sheet canvas: OK")
print("  compact typography/controls: OK")
print("  alternating section color bands: OK")
print("  compact collections/pickers/workflow controls: OK")
