from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
CSS = ROOT / "app" / "static" / "css" / "main.css"
CONFIG = ROOT / "app" / "config.py"

env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
for path in TEMPLATES.rglob("*.html"):
    env.parse(path.read_text(encoding="utf-8"))

nav = env.get_template("_global_nav.html")
html = nav.render(
    request=SimpleNamespace(session={"username": "Test GM", "role": "gm"}),
    app_version="0.5.17a",
)

assert 'href="/">Bookshelf</a>' in html
assert 'href="/">Home</a>' not in html
assert 'data-ttl-about-open' in html
assert 'id="ttl-about-dialog"' in html
assert 'Tabletop Librarian' in html
assert 'Version 0.5.17a' in html
assert 'https://github.com/candre23/Tabletop-Librarian' in html

css = CSS.read_text(encoding="utf-8")
assert ".ttl-global-nav" in css
assert "position: sticky;" in css
assert "top: 0;" in css
assert ".ttl-about-dialog" in css

config = CONFIG.read_text(encoding="utf-8")
assert 'APP_VERSION = "0.5.17a"' in config

print("Navigation/About UI regression passed.")
