#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
template = (ROOT / "app/templates/admin_library.html").read_text()
css = (ROOT / "app/static/css/main.css").read_text()

content_start = template.index("{% block content %}")
content_end = template.index("{% endblock %}", content_start)
content = template[content_start:content_end]

assert "data-source-scan-form" in content
assert 'id="source-scan-overlay"' in content
assert "Scanning folder tree and documents" in content
assert "Large libraries may take a few minutes" in content
assert 'form.addEventListener("submit"' in content
assert 'submitButton.textContent = "Scanning..."' in content
assert 'overlay.classList.add("is-visible")' in content

# It must not have been accidentally inserted into the title block.
title_start = template.index("{% block title %}")
title_end = template.index("{% endblock %}", title_start)
title_block = template[title_start:title_end]
assert "source-scan-overlay" not in title_block

assert ".source-scan-overlay.is-visible" in css
assert ".source-scan-progress-bar" in css
assert "@keyframes ttl-source-scan-progress" in css

print("PASS: library source progress regression test")
print("  overlay rendered inside content block: OK")
print("  not misplaced in title block: OK")
print("  immediate submit feedback hooks: OK")
print("  animated progress bar: OK")
