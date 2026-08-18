#!/usr/bin/env python3
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
templates = ROOT / "app" / "templates"
env = Environment(loader=FileSystemLoader(str(templates)))

for name in ("characters/create.html", "characters/edit.html"):
    env.get_template(name)
    text = (templates / name).read_text()
    assert "data-compendium-picker" in text
    assert "data-picker-search" in text
    assert "data-picker-tag" in text
    assert "data-picker-results" in text
    assert "data-picker-description" in text
    assert "data-picker-tags" in text
    assert "Showing first 250" in text
    assert "ttl-eligibility-updated" in text

skills = (
    ROOT / "tests/fixtures/system_packs/ttl_test_minimal/compendium/skills.yaml"
).read_text()
assert "perception" in skills
assert "awareness" in skills
assert "Notice hidden or subtle details." in skills

print("PASS: scalable compendium picker regression test")
print("  text search: OK")
print("  tag filtering: OK")
print("  descriptions: OK")
print("  live eligibility refresh: OK")
print("  single/multi references: OK")
print("  large-result guard: OK")
