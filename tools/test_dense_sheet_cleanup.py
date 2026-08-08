#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
edit=(ROOT/'app/templates/characters/edit.html').read_text()
create=(ROOT/'app/templates/characters/create.html').read_text()
advance=(ROOT/'app/templates/characters/advance.html').read_text()
web=(ROOT/'app/characters/web.py').read_text()
css=(ROOT/'app/static/css/main.css').read_text()

assert 'ttl-character-summary-meta' in edit
assert 'Level {{ record.data.get("level") }}' in edit
assert 'changed_fields' in web
assert 'ttl-inline-advancement' in edit
assert 'ttl-advancement-actions' not in edit
assert 'data-picker-entity="{{ field.entity or' in edit
for text in (edit,create,advance):
    assert 'ttl-skill-table' in text
assert 'live_schema_issues' in web
assert 'issue.message != "Required field is missing."' in web
assert '.ttl-sheet-section {' in css
assert 'grid-template-columns: max-content minmax(0, 1fr)' in css
assert '.ttl-step-head h2' in css and 'background: transparent' in css
print('PASS: v0.4.19.1 dense sheet cleanup regression test')
