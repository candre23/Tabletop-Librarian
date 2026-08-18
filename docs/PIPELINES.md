# Advanced Ask Pipeline Presets

Advanced Ask behavior is defined by JSON pipeline presets rather than a single hard-coded prompt chain. Basic Ask does not use these presets.

## Locations

TTL loads `*.json` from:

1. `pipelines/` for shipped presets;
2. `data/pipelines/` for user/local overrides.

A user preset with the same `id` overrides the shipped preset.

## Format version 1

Core fields include:

```json
{
  "format_version": 1,
  "id": "example-model-rules-v1",
  "name": "Example Model - Rules v1",
  "description": "Short description",
  "stages": [
    {"type": "planner"},
    {"type": "retrieve"},
    {"type": "rank"},
    {"type": "select"},
    {"type": "analysis"},
    {"type": "decision"},
    {"type": "rescue_if_unknown"},
    {"type": "compose"}
  ],
  "prompts": {}
}
```

Recognized stage types are `planner`, `retrieve`, `rank`, `select`, `analysis`, `decision`, `rescue_if_unknown`, and `compose`.

Presets can also define sampling, evidence/retrieval limits, progress checkpoints, rescue behavior, prompts, optional stage-specific model aliases, `tested_with`, and `default` metadata.

The shipped `qwen3.5-9b-v10` preset is the accepted benchmark pipeline developed for a Qwen 3.5 9B GGUF configuration. It is a model-tuned preset, not a requirement to use that model.

## Developing presets

Use a copy under `data/pipelines/`, give it a new ID, and benchmark one change at a time against a fixed question set. Validate complete end-to-end runs rather than only regenerating the final answer against fixed evidence.
