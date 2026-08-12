#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.pipelines import get_pipeline_preset, list_pipeline_presets

presets = list_pipeline_presets()
assert presets, "at least one Advanced Ask pipeline preset must be installed"
preset = get_pipeline_preset("qwen3.5-9b-v10")
data = preset.data

assert data["format_version"] == 1
assert data["ranker"] == "query_aware"
assert data["selector"] == "guarded_llm"
assert data["sampling"]["default"]["temperature"] == 0.0
assert data["limits"]["planner_queries"] == 4
assert data["limits"]["evidence"] == 8
assert data["rescue"]["enabled"] is True
assert [stage["type"] for stage in data["stages"]] == [
    "planner", "retrieve", "rank", "select", "analysis", "decision",
    "rescue_if_unknown", "compose",
]

prompts = data["prompts"]
assert "ACTION, OPTION, OR RULE INTERACTION" in prompts["planner"]
assert "DO NOT search the rulebook for that exact custom name" in prompts["planner"]
assert "Do not invent restrictions or prerequisites" in prompts["analysis"]
assert "Return exactly one token: YES, NO, or CANNOT_DETERMINE" in prompts["decision"]
assert "one evidence-rescue pass" in prompts["rescue_planner"]

main = (ROOT / "app/main.py").read_text()
ask = (ROOT / "app/templates/ask.html").read_text()
pipeline_code = (ROOT / "app/ai/pipelines.py").read_text()
provider = (ROOT / "app/ai/provider.py").read_text()

assert "execute_advanced_pipeline" in main
assert "get_pipeline_preset" in main
assert 'name="pipeline_preset"' in ask
assert "Advanced pipeline preset" in ask
assert "BUILTIN_PIPELINE_DIR" in pipeline_code
assert "USER_PIPELINE_DIR" in pipeline_code
assert "_rescue_procedural_anchor" in pipeline_code
assert "CANNOT_DETERMINE" in pipeline_code
assert "temperature: float | None = None" in provider

print("PASS: v0.5.10 modular Advanced Ask pipeline")
print("  v10 preset loads and validates: OK")
print("  per-request temperature override support: OK")
print("  guarded selector + rescue anchor primitives: OK")
print("  preset selectable from Ask UI: OK")
