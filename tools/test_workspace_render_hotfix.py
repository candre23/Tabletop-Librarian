#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
base=(ROOT/"app/templates/base.html").read_text()
workspace=(ROOT/"app/templates/workspace.html").read_text()
character=(ROOT/"app/templates/characters/edit.html").read_text()
web=(ROOT/"app/characters/web.py").read_text()
css=(ROOT/"app/static/css/main.css").read_text()
main=(ROOT/"app/main.py").read_text()

for path in (ROOT/"app/templates").rglob("*.html"):
    text=path.read_text()
    if "/static/css/main.css" in text:
        assert '/static/css/main.css?v={{ app_version }}"' in text, path

assert "ttl-workspace-page" in base
assert '"workspace_page": True' in main
assert "body.ttl-workspace-page > .shell" in css
assert "width: calc(100vw - 12px) !important;" in css
assert "body.ttl-workspace-page .ttl-workspace-grid" in css

assert 'request.query_params.get("embed") == "1"' in character
assert '{% if not is_embedded %}{% include "_global_nav.html" %}{% endif %}' in character
assert 'templates.env.globals["app_version"] = APP_VERSION' in web

assert 'data-workspace-mode="search-small"' in workspace
assert 'data-workspace-mode="search-large"' in workspace
assert 'data-workspace-mode="book-focus"' in workspace
assert 'grid.classList.add("mode-"+next)' in workspace
assert ".ttl-workspace-grid.mode-search-large" in css
assert ".ttl-workspace-grid.mode-book-focus" in css

print("PASS: workspace render hotfix")
print("  stylesheet cache-busting application-wide: OK")
print("  explicit full-width workspace body/shell: OK")
print("  embedded character nav suppression hardened: OK")
print("  layout-mode JS/CSS retained: OK")
