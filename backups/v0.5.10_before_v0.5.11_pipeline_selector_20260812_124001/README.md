# Tabletop Librarian v0.3.5

Self-hosted tabletop RPG library, rules helper, and character resource server.

## Phase 0.3 work

- RAG context chunks with page/source metadata
- OpenVINO CPU semantic embeddings
- all-MiniLM-L6-v2 embedding model
- Locally saved converted OpenVINO model
- Hybrid lexical + semantic retrieval
- Folder- and file-scoped hybrid retrieval
- Stopword filtering, rare-term lexical reranking, and stronger exact-match scoring
- Permission-aware retrieval for GM/player access

## Run

```bash
source .venv/bin/activate
python run.py
```

For first-time semantic setup:

1. Open Knowledgebase Tools and build/refresh Extracted Text.
2. Build the RAG corpus.
3. Build Semantic Embeddings from Knowledgebase Tools.

The first embedding build requires internet access to obtain the model.

- Selectable embedding models: Fast, Balanced, and Quality


## Knowledgebase maintenance

GM navigation includes a single **Knowledgebase** tool page for extracted text, context chunks, semantic embeddings, retrieval testing, and local AI provider settings. Knowledgebase Tools tracks these stages in dependency order and warns when library contents have changed since the last complete build.


### Recursive physical sources

Adding a directory as a physical library source automatically registers that
directory and each descendant directory as an independent physical source.
This makes nested documents available immediately while still allowing any
subfolder source to be removed separately later.


### Physical source scan progress

Adding a physical directory now displays an immediate progress overlay while
TTL discovers descendant source folders and scans the resulting library
contents. The indicator is intentionally indeterminate because source-folder
discovery and document inspection do not have a reliable total-work estimate
before the scan begins.


### Live physical-source scan progress

Physical-source imports run in a background worker while the Library Manager
polls live scan status. The progress overlay reports the actual filename being
inspected and the running number of supported documents processed. The final
scan result is reused when the Library Manager reloads so the newly imported
folder does not immediately undergo the same expensive scan a second time.


### Knowledgebase polling

The Knowledgebase Tools page uses lightweight embedding-status polling during
and after builds. Completion no longer schedules repeated full-page reloads,
so page controls remain responsive after a knowledgebase update finishes.


### Shadowrun: Anarchy Phase 2

The first real System Pack now includes the Core Rulebook creation workflow, live calculated point budgets, and starter structured compendium content. Calculated-usage limits are a generic TTL feature and can be reused by other systems with point-buy creation.


### v0.4.22.8 character compatibility fixes

- Additive System Pack fields with defaults are merged into older character
  data before rules are evaluated.
- Stale or invalid completed characters open an in-app recovery page instead
  of exposing a raw framework error, and can always be deleted there.
- Untouched collection-editor placeholder rows are discarded before
  validation, while actual custom entries remain intact.

### v0.4.22.9 creation validation timing

Creation-wizard validation rules now remain dormant until every workflow input
needed by the rule has reached its creation step. This prevents rules about
future attribute, resource, or equipment choices from blocking earlier steps.
The complete ruleset remains authoritative when the finished character is
validated.

### v0.4.22.10 creation guidance and finalization

Creation limits can now declare `require_full: true`. During the relevant
wizard step an unresolved target is presented as informational guidance; once
the target is met the message disappears. On final review and completed
characters, unresolved targets remain warnings.

Creation workflows can also declare safe `final_changes` expressions that are
applied immediately before character creation. Shadowrun: Anarchy uses this
to derive final Edge from base Edge, Human metatype bonus, and leftover Shadow
Amp points, capped at 6.

### v0.4.22.11 Play-mode structured collections

Read-only structured collections render their actual rows and populated
subfields in Play mode instead of only an entry count. Reference fields
resolve to compendium names. The display responds to the character container
width for future narrow tri-pane use.

### v0.4.22.12 conditional collection rule helper

The safe rules language now includes `nonempty_count_where()` for validating
structured collections conditionally.

Shadowrun: Anarchy Knowledge Skills now follow the Core rules: every ordinary
Skill rating always consumes Skill points; the free Knowledge Skill must be a
custom, unrated row. Marking a normal rated Skill as Knowledge no longer
refunds its rating and is rejected by validation.

### v0.4.22.13 creation navigation and derived trackers

Creation drafts remember the furthest step reached. Completed steps remain
clickable after navigating backward, and jumping saves the current step's data.

Workflow titles are semantic; the UI supplies step numbering once.

The safe rules language includes `resource(current, max)` for declarative
resource finalization. Shadowrun: Anarchy now initializes Armor, Physical and
Stun tracks at Finish. Armor Track is no longer edited or warned about during
creation, and the redundant second armor-aware Skill limit has been removed.

### v0.4.22.14 visual normalization

TTL's non-character pages now use a consistent compact technical visual
language: squared panels and controls, unified borders and focus states,
denser spacing, consistent notices/tables, and navigation matching the
character workspace chrome while retaining the dark application theme.

Character-layout sections may declare `body_color` independently from their
heading `color`. Shadowrun: Anarchy uses a plum Weapons heading with a green
body tint. The Shadowrun: Anarchy pack is considered beta-complete pending
real playtesting.

### v0.4.22.15 unified light theme

TTL now uses the character-sheet light palette throughout the application.
Library, Search, Uploads, Knowledgebase, Users, reader controls, admin panels,
tables, forms, dialogs, and global navigation all use the same compact
high-contrast visual language as the character interface. This removes the
abrupt dark-to-light transition when moving into character workflows while
preserving the dense spacing and squared technical style introduced in the
previous normalization pass.

### v0.4.22.16 light-theme contrast corrections

The unified light theme now uses a dark navigation bar consistently across all
pages while retaining light content surfaces. The TTL brand is brighter for
better contrast. Pale legacy labels were darkened, home/library titles were
made readable, cover-image wells use neutral gray instead of black, and
Knowledgebase metric cards are explicitly light with dark text. Form controls
and remaining RAG/admin components also receive high-contrast light overrides.


### v0.4.22.18 embedded Ask cleanup

Ask views embedded inside the document reader and folder dialog no longer
render a second copy of TTL's global navigation or the global knowledgebase
warning. Embedded pages use a dedicated full-pane shell. The reader AI header,
folder Ask dialog header, and embedded Ask content now use the unified light
high-contrast palette, while the application's single outer global navigation
bar remains dark.

### v0.4.22.19 full-width reader workspace

Document-reader pages now opt out of TTL's normal centered content-width
constraint and use essentially the full browser viewport. This is especially
important when Ask This File is open: additional horizontal screen space is
distributed between the document and AI panes rather than left unused.
Ordinary Library, admin, character-list, and other application pages retain
their constrained readable width.

### v0.4.22.20 embedding progress contrast

The Knowledgebase semantic-embedding progress panel now uses the unified light
palette instead of the remaining dark-theme surface. Status text is dark,
the progress track is light gray, and the active fill uses a high-contrast
blue.

### v0.4.22.21 GM character access and .ttlchar portability

Players continue to see and manage their own completed characters. GM accounts
see completed characters grouped by owner and can open the same authoritative
player character in Play or Configure mode without creating a copy. GM edits,
temporary effects, and advancement actions therefore affect the player's
actual sheet.

Characters can be exported as self-contained `.ttlchar` ZIP packages containing
`manifest.json` and authoritative `character.json`. Imports validate against
the locally installed System Pack before modifying the character collection.
Players import into their own account; GMs may select any existing account.
ID collisions may be imported as a new copy or explicitly replace the existing
character.

The package format rejects executable/script content. Future ordinary character
assets may live under `assets/`; currently accepted asset types are standard
web images.


### v0.4.22.22 application error pages

Browser-facing FastAPI errors now render through TTL's normal interface rather
than exposing the framework's default JSON response. HTTP 400/401/403/404/405,
409, 413, 422 and other HTTP errors receive a consistent light-theme error
page with appropriate navigation. Unexpected server errors show a short
reference ID while the full exception is written to the server log.

API/fetch requests continue to receive JSON error payloads when the request
does not advertise `text/html`, preserving existing live UI endpoints.


## v0.5 Character-aware AI

### v0.5.1 selected-character Ask context

Ask can now receive one selected completed character as authoritative structured
context. Players may select their own characters; GMs may select any character
they are authorized to view. The selector is available in standalone Ask and
embedded Ask-this-file/folder views.

Character context is deliberately separated from RAG evidence. It establishes
the character's current sheet state, including resolved compendium names,
calculated values, resources, structured collections, and active temporary
effects. It is not numbered or cited as a book source. Rules, procedures, and
mechanical explanations must still be supported by retrieved numbered source
passages.

Character-only questions can proceed even when RAG retrieves no relevant book
passage. This provides the foundation for later character-aware rules guidance
and the tri-pane play workspace without allowing the AI to modify character
data or treat the sheet as a source of rules.


### v0.5.2 AI backend preflight and request cancellation

All user-facing generation requests now use a reusable AI backend health check
before generation starts. Ask performs a two-second `/models` reachability
check in the browser before submitting the question, and repeats the check on
the server to cover races between preflight and generation. An offline or
unstarted backend therefore reports immediately instead of entering the normal
generation progress sequence and waiting for the full provider timeout.

Ask also exposes a Cancel button while a request is active. Cancellation stops
the pending browser navigation immediately and signals TTL's server-side
request registry. Cancellable provider calls use OpenAI-compatible streaming;
when cancellation is requested TTL closes the provider response stream. Local
OpenAI-compatible servers that stop generation on client disconnect (including
llama.cpp-style servers) receive a best-effort backend abort. Even when a
provider does not stop its generation, the TTL web UI no longer waits for it.

The health-check, cancellation registry, and cancellable provider call are
generic AI-layer facilities intended for reuse by later v0.5 AI workflows.


### v0.5.3 tri-pane play workspace foundation

TTL now provides a `/workspace` play view that combines the existing
character-aware Ask interface, document reader, and live character sheet
without duplicating their underlying implementations.

The default desktop layout keeps the character sheet on the right. On the
left, Ask occupies the upper one-third and the book viewer the lower
two-thirds. The user can switch to a two-thirds Ask layout, or Book Focus:
the book receives the full left side while Ask and the character sheet share
the right side. The selected layout is remembered in the browser.

The workspace toolbar selects the active completed character and library
document. Players see their own characters; GMs retain the v0.4 all-character
visibility rules. Ask receives the selected character as locked authoritative
context and the selected document as its rules scope.

Reader and character pages now support embedded workspace presentation, so
only the outer workspace shows TTL's global navigation. Source-citation jumps
from the Ask pane are forwarded to the sibling book pane, preserving the
existing PDF/text source navigation behavior.

This is intentionally a composition layer: the normal Character, Ask, and
Reader pages remain independently usable and authoritative. Later v0.5 work
can add richer pane communication without coupling those subsystems together.


### v0.5.3.1 workspace rendering hotfix

The initial workspace exposed stale static CSS caching: browsers could receive
the new workspace HTML while reusing the pre-workspace stylesheet. All TTL
templates now version the shared stylesheet URL using the running application
version.

The workspace also has an explicit body-level page class and direct
full-viewport shell rules instead of depending on `:has()` for critical
layout. Embedded character sheets additionally inspect the actual `embed=1`
request parameter when deciding whether to suppress their own global
navigation.


### v0.5.3.2 compact workspace Ask

The Ask pane inside the tri-pane Play Workspace now uses a dedicated compact
presentation. Because the workspace toolbar already identifies the active
character and book, the embedded Ask pane suppresses its large title,
character banner, and locked-document scope summary. The normal standalone
Ask page and ordinary Ask-this-file/folder views retain those elements.

Compact mode persists across Ask submissions and leaves the question,
Ask/Cancel/progress controls, answer, and sources available.


### v0.5.3.3 compact workspace scope cleanup

Workspace-compact Ask now suppresses both locked-document and locked-folder
scope banners. Previously the hidden document banner could fall through to the
folder banner, leaving a redundant "Searching <folder>" box in the workspace.


### v0.5.4 character-aware rules analysis

Character-aware Ask now uses the selected sheet during retrieval as well as
generation. The character context exposes structured field metadata and
bounded search-hint groups for named skills, qualities, weapons, gear, powers,
and other reference/collection entries. When a user refers indirectly to a
sheet category ("my qualities", "my weapons", etc.), TTL adds the actual sheet
item names to the RAG query so the relevant definitions have a better chance
to enter the evidence set. If no category is explicit, a bounded set of
character option names is supplied as secondary retrieval context.

The AI reasoning contract now distinguishes relevant Character sheet facts,
cited Rules evidence, and a character-specific Conclusion. Character sheet
values remain authoritative state but are never treated as proof of a rule.
Rules claims must still come from numbered RAG passages, and the conclusion
may not introduce a new uncited mechanical premise. If evidence is
insufficient, the assistant must say so rather than infer the missing rule.

This remains read-only AI assistance. No character modifications are proposed
or applied in v0.5.4.


### v0.5.4.1 concise character-aware analysis

The v0.5.4 retrieval fallback was too aggressive for indirect questions. If a
question did not explicitly name a sheet category or item, TTL appended a
broad set of character option names to the RAG query. This could cause
unrelated skills, qualities, and gear to dominate retrieval. Indirect
questions now use the user's question unchanged. Character-sheet expansion is
reserved for explicit references such as "my qualities", "my weapons", or an
item actually named in the question.

The generation contract is also concise-first. Character-specific questions
lead with the direct answer when one is supported, mention only sheet facts
that materially affect that answer, and cite the controlling rules. The
Character / Rules / Conclusion structure is optional for genuinely complex
questions rather than mandatory for simple ones.


### v0.5.5 selectable Basic / Advanced reasoning

Ask now offers two retrieval modes. Basic is the default and preserves the
v0.5.4.1 pipeline: one character-aware retrieval query followed by the final
answer call.

Advanced is experimental. TTL first asks the configured model to act only as
a semantic retrieval planner. The planner receives the original question,
selected character state, system identity, and bounded vocabulary extracted
from the active System Pack. It returns up to four focused search queries and
up to six possible follow-up concepts. The original user question is always
retained as the first search.

TTL retrieves each planned query, deduplicates chunks, keeps the strongest
evidence score seen for each chunk, then allows one bounded follow-up hop.
A follow-up concept is searched only if that concept appears in first-pass
evidence. This prevents a planner guess from causing open-ended recursive
searches. The combined evidence is capped at twelve passages before the normal
citation-constrained answer stage.

The planner never changes character data and is explicitly instructed not to
answer the rules question. Basic remains available for questions that do not
need the extra planning call.


### v0.5.6 Advanced answer verification + real progress checkpoints

Advanced reasoning now adds a second model pass after the draft answer. The
verifier receives the original question, authoritative character context, the
same numbered evidence passages, and the draft. It returns the corrected final
answer rather than a critique.

The verifier is specifically instructed to check mechanical claims, numeric
ranges and boundaries, prerequisites, permissions/prohibitions, unsupported
exceptions, and source-role mistakes. It removes speculation not supported by
the supplied passages and preserves the existing character-state versus
numbered-rules citation boundary. Basic reasoning remains unchanged and does
not incur the verification call.

The circular Ask progress meter now polls real server-side request state rather
than advancing only on elapsed-time guesses. Advanced requests expose these
checkpoints: character context, query planning, first-pass retrieval, related
rule lookup, evidence assembly, draft generation, draft received, verification,
verified answer received, and finalization. Basic requests use the shorter
subset appropriate to their pipeline.


### v0.5.7 claim audit + targeted revision

Advanced verification now uses a constrained claim-audit pipeline. The auditor
returns structured findings only for unsupported, contradicted, numeric,
source-role, or speculative mechanical claims and is prohibited from answering
the question or rewriting the draft.

If findings exist, a targeted revision call receives the original draft plus
the audit and may change only what is necessary to resolve those findings. If
the audit passes, TTL uses the original draft unchanged and skips the revision
call.

Progress now reports Draft answer received, Auditing mechanical claims,
Revising N flagged claims, Revised answer received, or Audit passed. Basic mode
remains unchanged.

### v0.5.8 simplified Advanced retrieval pipeline

Advanced reasoning now uses two model calls only: one retrieval-planning call
and one final answer call. The v0.5.6 verifier and v0.5.7 claim-audit/targeted
revision stages have been removed from the live pipeline.

Evidence gathered across the planner's bounded searches and evidence-gated
follow-up lookups is merged with deterministic cross-query ranking. Passages
receive preference when multiple searches independently retrieve them, when
they rank highly within those searches, and when the user's original wording
also retrieves them. Heavily overlapping passages from the same document are
pruned when distinct evidence is available.

The Ask progress meter now reflects the simplified Advanced checkpoints:
character context, search planning, first-pass retrieval, related-rule lookup,
evidence ranking, evidence assembly, final-answer generation, final answer
received, and finalization. No diagnostic/audit UI is exposed to players.



### v0.5.10 modular Advanced Ask pipelines

Advanced Ask workflows are now loaded from JSON pipeline presets rather than being hard-coded into the Ask route. Shipped presets live in `pipelines/`; local/user presets can be placed in `data/pipelines/` and selected from the Ask UI. The initial `qwen3.5-9b-v10` preset reproduces the validated Qwen 3.5 9B workflow and uses per-request temperature 0.0 without changing the backend startup configuration. See `PIPELINE_PRESETS.md` for the preset standard and development guidance.

### v0.5.9 relevance-first evidence + compact final prompt

Advanced reasoning keeps the v0.5.8 two-call architecture but changes evidence
selection so passage relevance is the dominant ranking signal. Cross-query
recurrence now provides only a modest bonus instead of outranking a stronger
passage simply because several planner searches rediscovered it.

Up to three of the strongest passages from the user's original question are
reserved in the final evidence set before planner-query evidence fills the
remaining slots. Near-duplicate pruning remains in place.

The final-answer system prompt has also been reduced to a compact set of
small-model-safe rules: use character context for sheet state, numbered sources
for rules, apply explicit defaults/exceptions literally, do not treat missing
sheet entries as prohibitions, do not invent unsupported restrictions, and say
when the supplied evidence is insufficient.
