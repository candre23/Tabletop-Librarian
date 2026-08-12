#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
main=(ROOT/"app/main.py").read_text()
ask=(ROOT/"app/templates/ask.html").read_text()
workspace=(ROOT/"app/templates/workspace.html").read_text()
css=(ROOT/"app/static/css/main.css").read_text()

assert 'workspace_compact: str = ""' in main
assert '"workspace_compact": workspace_compact == "1"' in main
assert 'workspace_compact = str(form.get("workspace_compact"' in main
assert '"workspace_compact": workspace_compact,' in main
assert 'workspace_compact=1' in workspace

assert 'ask-workspace-compact' in ask
assert '{% if not workspace_compact %}' in ask
assert 'selected_character_context and not workspace_compact' in ask
assert 'locked_document_key and not workspace_compact' in ask
assert 'name="workspace_compact" value="1"' in ask

assert "v0.5.3.2 compact Ask presentation inside tri-pane workspace" in css
assert ".ask-workspace-compact textarea" in css

print("PASS: compact workspace Ask regression")
