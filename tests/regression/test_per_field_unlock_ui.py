#!/usr/bin/env python3
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
templates = ROOT / "app" / "templates"
env = Environment(loader=FileSystemLoader(str(templates)))

for name in ("characters/create.html", "characters/edit.html"):
    env.get_template(name)

create = (templates / "characters" / "create.html").read_text()
edit = (templates / "characters" / "edit.html").read_text()
web = (ROOT / "app" / "characters" / "web.py").read_text()

assert "Unlock Core Aspects" not in create
assert "Unlock Core Aspects" not in edit
assert "ttl-core-lock-bar" not in create
assert "ttl-core-lock-bar" not in edit
assert "ttl-core-lock-mark" not in create
assert "ttl-core-lock-mark" not in edit
assert "unlock_field={{ field_id }}" in create
assert "unlock_field={{ field_id }}" in edit
assert "&#128274;" in create and "&#128274;" in edit
assert "&#128275;" in create and "&#128275;" in edit
assert "unlocked_field" in create and "unlocked_field" in edit
assert 'request.query_params.get("unlock_field")' in web
assert 'form_data.get("unlocked_field")' in web
assert "field_id != unlocked_field" in web

print("PASS: per-field core-aspect unlock UI regression test")
