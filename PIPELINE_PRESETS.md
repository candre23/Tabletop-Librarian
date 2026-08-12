# Tabletop Librarian Advanced Ask Pipeline Presets

Pipeline presets make Advanced Ask model-specific without hard-coding one prompt chain into TTLibrarian. A preset is a UTF-8 JSON file that selects the Advanced Ask workflow primitives, prompts, sampling settings, evidence limits, rescue behavior, and progress checkpoints.

Basic Ask does not use pipeline presets.

## Locations and precedence

TTL loads `*.json` presets from both locations:

1. `pipelines/` - presets shipped with TTLibrarian.
2. `data/pipelines/` - local/user presets.

A preset in `data/pipelines/` with the same `id` as a shipped preset overrides the shipped copy. This allows local experiments without editing application files and allows separately distributed presets to be installed by copying one JSON file into `data/pipelines/`.

Invalid preset files are ignored by the UI. They should be validated before distribution.

## Format version 1

Required top-level fields:

```json
{
  "format_version": 1,
  "id": "example-model-rules-v1",
  "name": "Example Model - Rules v1",
  "description": "Short description shown in the Ask UI.",
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

`id` must contain only lowercase letters, digits, `.`, `_`, and `-`, begin with a letter or digit, and be no more than 64 characters.

`default: true` marks the preset TTL should select when Advanced Ask is opened without an explicit preset. If multiple presets claim to be default, the first one by display-name ordering wins; distribute only one default preset in normal installations.

`tested_with` is optional metadata. TTL does not enforce it. It is intended to record model names/configurations used to validate the preset.

## Workflow primitives

Format v1 recognizes these stage types:

- `planner` - LLM converts the question/character context into retrieval queries.
- `retrieve` - bounded RAG retrieval for planner queries.
- `rank` - deterministic evidence ranking.
- `select` - LLM evidence selection with deterministic guardrails.
- `analysis` - LLM applies the selected rules to the character without being asked for a Yes/No token.
- `decision` - LLM reduces the analysis to `YES`, `NO`, or `CANNOT_DETERMINE`.
- `rescue_if_unknown` - optional one-pass retrieval/selection/re-analysis path after `CANNOT_DETERMINE`.
- `compose` - deterministic user-facing composition of decision + analysis.

Format v1 expects the core stages in their logical dependency order. Presets can disable the rescue pass with `"rescue": {"enabled": false}`. New workflow primitives require a TTL code update and a future preset-format revision if they change compatibility.

## Ranker and selector

Format v1 currently supports:

```json
"ranker": "query_aware",
"selector": "guarded_llm"
```

`query_aware` combines the RAG evidence score with direct planner-query term coverage and passage relevance.

`guarded_llm` runs the selector prompt, while also retaining one strong distinct result from each of the first four planner retrieval branches. This is the behavior validated by the Qwen 3.5 9B v10 benchmark pipeline.

The rescue selector uses a separate single procedural/governing anchor. It does not preserve one result from every rescue query.

## Sampling

Sampling can be set globally for the preset and overridden by stage:

```json
"sampling": {
  "default": {
    "temperature": 0.0,
    "max_tokens": 1200
  },
  "planner": {
    "temperature": 0.1
  },
  "analysis": {
    "model": "optional-server-model-alias"
  }
}
```

Supported keys are:

- `temperature`: 0.0 to 2.0
- `max_tokens`: 64 to 8192
- `model`: optional OpenAI-compatible model/alias override for that stage

If omitted, TTL uses the AI-provider settings. Per-stage values are sent in each `/chat/completions` request; the backend does not need to be restarted to change them.

A preset usually should not hard-code `model`. Leaving it unset allows the user to switch the model in TTL's AI Provider configuration while keeping the chosen pipeline preset. `tested_with` should document what was actually validated.

## Limits

Format v1 recognizes these optional limits:

```json
"limits": {
  "planner_queries": 4,
  "retrieve_per_query": 6,
  "selector_candidates": 24,
  "evidence": 8,
  "rescue_queries": 2,
  "rescue_selector_candidates": 16,
  "rescue_evidence": 4
}
```

These control context size and latency. A larger model is not necessarily improved by increasing every limit; benchmark changes rather than assuming more evidence is better.

## Prompts

Format v1 prompt keys are:

- `planner`
- `selector`
- `analysis`
- `decision`
- `rescue_planner`
- `rescue_selector`

Prompts are plain JSON strings. They should describe outputs strictly when a downstream deterministic stage expects structure. Planner/selector prompts should request JSON only. The decision prompt should request exactly one of `YES`, `NO`, or `CANNOT_DETERMINE`.

The analysis prompt should cite numbered evidence as `[1]`, `[2]`, etc. TTL's final source list is built from the same selected passages.

## Progress checkpoints

A preset can map workflow checkpoints to percentages:

```json
"progress": {
  "planner": 20,
  "retrieve": 38,
  "rank": 50,
  "select": 62,
  "analysis": 78,
  "decision": 88,
  "rescue_planner": 91,
  "rescue_retrieve": 93,
  "rescue_select": 95,
  "rescue_analysis": 96,
  "compose": 98
}
```

The values drive the existing circular Ask progress meter. TTL clamps preset values to the user-facing working range.

## Developing a new preset

Use a copy of an existing preset in `data/pipelines/`, give it a new `id` and `name`, and change one variable at a time. The recommended process is:

1. Choose a fixed model build and quantization.
2. Establish benchmark questions with known rule answers and several different reasoning patterns.
3. Run full end-to-end repetitions, not just repeated final generations against fixed evidence.
4. Change one prompt/stage/limit/sampling parameter at a time.
5. Keep regressions, not only improvements, in the benchmark set.
6. Record the tested model in `tested_with` and give the preset a new ID when behavior changes materially.

Do not assume a preset validated for one model family, parameter count, quantization, or revision will transfer cleanly to another.

## Shipped Qwen 3.5 9B preset

`pipelines/qwen3.5-9b-v10.json` reproduces the accepted v10 benchmark pipeline developed for `qwen3.5-9b-q5` at temperature 0.0. It uses:

- custom-aware mechanics-first planning;
- four-query bounded retrieval;
- query-aware deterministic ranking;
- guarded LLM evidence selection;
- analysis-only rule application;
- decision-only classification;
- one `CANNOT_DETERMINE` rescue pass;
- one deterministic procedural/governing rescue anchor;
- deterministic final answer composition.

This is a model-tuned preset, not a claim that Qwen 3.5 9B is the only supported model.
