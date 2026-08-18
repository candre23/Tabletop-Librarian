#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

web = (ROOT / "app/characters/web.py").read_text()
template = (ROOT / "app/templates/characters/edit.html").read_text()
css = (ROOT / "app/static/css/main.css").read_text()

# Finished-character GET must pass requested mode through to renderer.
char_route = web[web.index('@router.get("/characters/{character_id}"'):]
assert 'mode=request.query_params.get("mode") or "play"' in char_route

# Creation page must not pass an unsupported mode kwarg.
creation_route = web[
    web.index('@router.get("/characters/create/{draft_id}"'):
    web.index('@router.post("/characters/create/{draft_id}/evaluate"')
]
assert 'mode=request.query_params.get("mode")' not in creation_route

# Only removable/configure skill tables may receive the square final column.
assert "ttl-skill-table-removable" in template
assert '.ttl-skill-table-removable th:last-child' in css
assert '.ttl-skill-table-removable td:last-child' in css

play_start = template.index('<table class="ttl-skill-table ttl-play-table ttl-description-picker-table">')
play_block = template[play_start:template.index('</table>', play_start) + 8]
assert "ttl-skill-table-removable" not in play_block
assert "<th>Description</th>" in play_block

print("PASS: play-mode UI fixes")
print("  Configure query mode honored: OK")
print("  creation route stray mode kwarg removed: OK")
print("  play skill description column remains full width: OK")
print("  remove column remains compact only in configure mode: OK")
