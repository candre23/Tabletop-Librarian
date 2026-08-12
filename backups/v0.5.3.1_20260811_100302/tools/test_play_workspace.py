#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

main=(ROOT/"app/main.py").read_text()
workspace=(ROOT/"app/templates/workspace.html").read_text()
ask=(ROOT/"app/templates/ask.html").read_text()
character=(ROOT/"app/templates/characters/edit.html").read_text()
pdf=(ROOT/"app/templates/reader_pdf.html").read_text()
text=(ROOT/"app/templates/reader_text.html").read_text()
css=(ROOT/"app/static/css/main.css").read_text()

assert '@app.get("/workspace"' in main
assert "def _workspace_document_options" in main
assert '"embed": embed == "1"' in main
assert '"workspace": workspace == "1"' in main
assert 'lock_character: str = ""' in main

assert 'class="ttl-workspace-grid mode-search-small"' in workspace
assert 'data-workspace-mode="search-small"' in workspace
assert 'data-workspace-mode="search-large"' in workspace
assert 'data-workspace-mode="book-focus"' in workspace
assert 'lock_character=1' in workspace
assert 'embed=1&workspace=1' in workspace
assert 'embed=1' in workspace
assert 'ttl-source-jump' in workspace
assert 'bookFrame?.contentWindow?.postMessage' in workspace

assert 'character_locked and selected_character' in ask
assert 'name="lock_character"' in ask

assert 'ttl-character-embedded' in character
assert '{% if not embed %}{% include "_global_nav.html" %}{% endif %}' in character
assert '>Workspace</a>' in character

assert '{% if not workspace %}<button type="button" class="secondary-button compact-button" id="ask-file-toggle"' in pdf
assert 'href="/workspace?document=' in pdf
assert 'href="/workspace?document=' in text

assert "v0.5.3 tri-pane play workspace foundation" in css
assert ".ttl-workspace-grid.mode-search-large" in css
assert ".ttl-workspace-grid.mode-book-focus" in css
assert 'grid-template-areas:' in css

print("PASS: tri-pane play workspace foundation")
print("  workspace character/document selectors: OK")
print("  1/3 Ask, 2/3 Ask, and Book Focus modes: OK")
print("  embedded character/reader presentation: OK")
print("  locked character-aware Ask context: OK")
print("  sibling Ask-to-book source navigation forwarding: OK")
