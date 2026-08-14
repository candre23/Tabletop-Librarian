#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
css = (ROOT / "app/static/css/main.css").read_text()
pdf = (ROOT / "app/templates/reader_pdf.html").read_text()
text = (ROOT / "app/templates/reader_text.html").read_text()

marker = "body:not(.ttl-character-ui) > .shell:has(.reader-shell)"
assert marker in css
section = css[css.index(marker):]

assert 'body:not(.ttl-character-ui) > .shell:has(.reader-shell)' in section
assert "width: calc(100vw - 16px) !important;" in section
assert "max-width: none !important;" in section
assert ".reader-split.with-ai" in section
assert "minmax(430px, .8fr)" in section

assert 'class="reader-shell"' in pdf
assert 'class="reader-split"' in pdf
assert 'class="reader-shell text-reader-shell"' in text

# The final override must come after the ordinary light-theme shell rules.
embedded_marker = "body.ttl-embedded-page .ask-embedded-panel"
assert embedded_marker in css
assert css.index(marker) > css.index(embedded_marker)

print("PASS: full-width reader workspace regression")
print("  normal application shell override: OK")
print("  reader width follows browser viewport: OK")
print("  dual-pane layout expands on large displays: OK")
print("  PDF and text readers covered: OK")
