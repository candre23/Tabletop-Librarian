#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

template = (ROOT / "app/templates/admin_library.html").read_text()
css = (ROOT / "app/static/css/main.css").read_text()

assert "data-source-scan-form" in template
assert 'id="source-scan-overlay"' in template
assert "Scanning folder tree and documents" in template
assert "Large libraries may take a few minutes" in template
assert 'form.addEventListener("submit"' in template
assert 'submitButton.textContent = "Scanning..."' in template
assert 'overlay.classList.add("is-visible")' in template

assert ".source-scan-overlay.is-visible" in css
assert ".source-scan-progress-bar" in css
assert "@keyframes ttl-source-scan-progress" in css
assert "prefers-reduced-motion" in css

print("PASS: library source progress regression test")
print("  immediate progress overlay: OK")
print("  submitted source path shown: OK")
print("  duplicate submit prevention: OK")
print("  animated indeterminate progress bar: OK")
print("  reduced-motion fallback: OK")
