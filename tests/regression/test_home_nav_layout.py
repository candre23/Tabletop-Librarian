#!/usr/bin/env python3
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
templates = ROOT / "app" / "templates"
env = Environment(loader=FileSystemLoader(str(templates)))

for name in ("_global_nav.html", "home.html"):
    env.get_template(name)

nav = (templates / "_global_nav.html").read_text()
home = (templates / "home.html").read_text()

assert "ttl-global-nav-account" in nav
assert "ttl-global-nav-user" in nav
assert "{{ nav_username }}" in nav
assert "(GM)" in nav
assert 'action="/logout"' in nav

assert "ttl-home-title-row" in home
assert "ttl-home-search" in home
assert "Signed in as" not in home

print("PASS: home/nav layout regression test")
