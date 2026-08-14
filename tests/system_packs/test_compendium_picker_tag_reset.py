#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

for rel in (
    "app/templates/characters/create.html",
    "app/templates/characters/edit.html",
):
    text = (ROOT / rel).read_text()
    assert 'if (tagFilter) {' in text
    assert 'tagFilter.value = "";' in text
    open_pos = text.index('openButton?.addEventListener("click"')
    reset_pos = text.index('tagFilter.value = "";', open_pos)
    render_pos = text.index("renderResults();", open_pos)
    assert reset_pos < render_pos

print("PASS: compendium picker tag-reset regression test")
