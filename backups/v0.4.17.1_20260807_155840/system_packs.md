# Tabletop Librarian System Pack Specification

System Packs define game-system-specific character data, rules, catalog content,
creation workflows, and layouts while keeping Tabletop Librarian's core engine
system-neutral.

This document is the authoritative project reference for the pack format as it
evolves through v0.4.

## Core principles

- System Packs are data, not executable plugins.
- No arbitrary Python, JavaScript, shell commands, filesystem access, or network
  access may be supplied by a pack.
- Character mechanics that affect legality, calculation, validation, selectable
  options, or automatic sheet behavior must ultimately be structured data.
- RAG/LLM features may discover, explain, or propose structured content, but are
  not the authoritative runtime rules engine.
- Stable IDs are used for character and compendium references.
- Human-readable YAML/JSON is authoritative; generated caches are disposable.
- Pack validation should fail clearly rather than silently merge incompatible
  definitions.

## Pack directory

A pack currently lives under `data/system_packs/<pack_id>/`.

Typical layout:

```text
data/system_packs/
  eldritch/
    manifest.yaml
    character.yaml
    rules.yaml
    creation.yaml
    compendium/
      abilities.yaml
      skills.yaml
      races.yaml
      occupations.yaml
      advantages.yaml
      equipment.yaml
      spells.yaml
    layouts/
      editor.yaml
      print.html
      print.css
    assets/
    sources/
      source_map.yaml
    modules/
    migrations/
```

Only `manifest.yaml` and the declared character schema are required by the
current implementation. Other sections are optional.

## Manifest

Minimum example:

```yaml
id: eldritch
name: Eldritch
version: 0.1.0
pack_format: 1
character_schema: character.yaml
rules: rules.yaml
compendium:
  - compendium/skills.yaml
  - compendium/equipment.yaml
```

`pack_format` identifies compatibility with TTL's System Pack schema.
`version` identifies the revision of the individual game-system pack.

All declared files must use safe paths relative to the pack root.

## Character schema

`character.yaml` declares fields. Initial field types are:

- `text`
- `integer`
- `decimal`
- `boolean`
- `enum`
- `reference`
- `multi_reference`
- `collection`
- `object`
- `calculated`
- `resource`
- `notes`

Example:

```yaml
schema_version: 1
fields:
  name:
    type: text
    label: Character Name
    required: true

  occupation:
    type: reference
    label: Occupation
    entity: occupation

  level:
    type: integer
    default: 1
    min: 1
    max: 20
```

A saved character records the System Pack and schema version separately from
its character-specific data.

## Rules

`rules.yaml` currently supports safe calculated and validation expressions.
Expressions are parsed and interpreted by TTL; Python `eval` is not used.

Current expression features include arithmetic, comparisons, boolean logic,
conditional expressions, and a small allowlist of numeric functions.
Calculated fields are dependency-ordered and circular dependencies are errors.

The editor reevaluates rules live when editable character values change. Saving
runs the authoritative calculation and validation again before writing data.

### Modifier channels and compendium effects

`rules.yaml` may declare numeric modifier channels:

```yaml
modifiers:
  strength_bonus:
    default: 0
    aggregate: sum
```

Supported aggregation methods are currently `sum`, `max`, and `min`.

Compendium entries can contribute numeric values to those declared channels:

```yaml
effects:
  strength_bonus: 1
```

Effects may also be conditional while retaining the simple numeric shorthand:

```yaml
effects:
  strength_bonus:
    value: 2
    when: level >= 5
```

Multiple contributions to the same modifier are supported:

```yaml
effects:
  strength_bonus:
    - value: 1
    - value: 2
      when: level >= 5
      label: Veteran training
```

Conditional effects currently reference non-calculated character fields only.
This prevents an effect from qualifying itself through a calculated value or
modifier feedback loop.

Only selected entities referenced by the character contribute effects. The
resolved modifier values are virtual rule inputs: they are available to
calculated and validation expressions but are not written into character JSON.

For example:

```yaml
calculated:
  effective_strength:
    formula: strength + strength_bonus

  fortitude_save:
    formula: effective_strength + level
```

This supports deterministic chains such as a selected skill modifying a stat,
with that calculated stat then affecting a saving throw.

### Calculation provenance

TTL also retains a runtime explanation trace for calculated fields. The trace is
derived from the same rule evaluation that produces the value and is not stored
as separate character state. It includes:

- the calculated field's current value
- a human-readable version of its formula
- additive/subtractive term values when the expression can be decomposed that way
- direct field and calculated-field inputs
- resolved modifier values
- the named compendium entities that contributed each modifier value

Modifier channels may include an optional display label:

```yaml
modifiers:
  strength_bonus:
    label: Strength Bonus
    default: 0
    aggregate: sum
```

The character UI can expose this trace through an information control beside a
calculated value. Chained calculated fields retain their immediate dependency
information, so a derived saving throw can identify the effective stat it used,
while that effective stat has its own explanation.

### Compendium eligibility

Compendium entries may declare deterministic selection requirements:

```yaml
eligibility:
  rule: archetype == "Warrior" and level >= 3
  message: Requires Warrior archetype and level 3.
```

A string shorthand is also accepted:

```yaml
eligibility: level >= 3
```

Eligibility currently references non-calculated character fields only. This
keeps option legality independent from the bonuses granted by the option being
checked and prevents self-qualifying circular rules.

The character editor and creation workflow reevaluate eligibility live.
Ineligible unselected options are unavailable, existing illegal selections are
shown as errors, and authoritative character storage rejects illegal
selections.


### Dynamic collection limits

`rules.yaml` may cap the number of selections in a `multi_reference` or
`collection` field. The maximum is a safe expression and can change with level,
stats, modifiers, or calculated fields:

```yaml
limits:
  skill_count:
    field: skills
    label: Skills
    maximum: 3 + floor(level / 3)
    message: Skills: {count} selected, but only {maximum} are allowed.
```

The UI reevaluates limits live and displays the current count beside the field
(e.g. `4 / 5`). Exceeding a limit produces an error but never silently removes
selections. Creation step advancement and authoritative character saves both
reject over-cap characters.

Limits may optionally warn when close to capacity:

```yaml
    warn_at_remaining: 1
    warning_message: Only {remaining} {label} slot remains.
```

A limit may count only compendium entries matching tags and/or exact metadata:

```yaml
limits:
  level_one_spell_slots:
    field: spells
    label: Level 1 spells
    maximum: level_one_spell_slots
    where:
      tags: spell
      metadata:
        spell_level: 1
```

`where.tags` requires all listed tags. `where.metadata` performs exact matching
against compendium entry metadata. Filtered limits currently require a
`multi_reference` field backed by a compendium entity type.

Limit results retain the maximum expression and its current input values so the
UI can explain why the current capacity is what it is.

Future rule categories may include derived collections and richer prerequisite relationships.

### Core-field locking

Creation steps may soft-lock selected fields after that step is successfully completed:

```yaml
steps:
  - id: identity
    fields: [name, background]
    lock_after: [background]
```

A `lock_after` field must be an input in that same step. Locked fields remain visible but are not normally editable when revisiting earlier creation steps. The union of all `lock_after` fields becomes the character's **core aspects** after creation. The character editor protects those fields by default. Each protected field has its own padlock control; confirming an unlock affects only that field for the current page session. Saving or leaving the page returns it to the locked state.

This is a soft safety mechanism rather than an assertion that the game can never change the value. It is intended for ancestry/race, initial class/archetype, background/history, and similar choices where changes should be deliberate.

## Compendium

The compendium stores structured system entities such as skills, occupations,
races, classes, spells, weapons, gear, advantages, and other game-specific
content. Entity types are intentionally generic rather than hard-coded into
TTL.

Each declared compendium file contains one entity type:

```yaml
entity: skill
entries:
  - id: stealth
    name: Stealth
    tags: [physical]
```

Every entry requires:

- a stable `id`
- a display `name`

Entries may contain arbitrary system-specific metadata. TTL currently treats
that metadata as opaque except for reserved generic structures such as `tags`
and `references`.

IDs must be unique within an entity type across all active files in the pack.

### Explicit cross-file references

Generic references that TTL itself should validate use:

```yaml
references:
  - entity: skill
    id: stealth
```

The loader verifies that the target entity exists.

Character fields of type `reference` may declare an entity type:

```yaml
background:
  type: reference
  entity: background
```

The character editor can populate those fields from the matching compendium
entries, and character storage verifies that saved IDs actually exist.

`multi_reference` uses the same entity-type concept; dedicated multi-selection
UI will be added later.

## Creation workflow

`creation.yaml` is reserved for a declarative, system-specific character
creation sequence. TTL must not assume universal concepts such as race, class,
level, or attributes.

Creation steps may eventually include conditions, selection limits, eligibility
rules, and compendium-backed choices. Normal character editing remains separate
from the creation workflow.

## Provenance

Structured entities may carry source information, for example:

```yaml
source:
  document_key: eldritch_core
  page: 17
  section: Abilities
```

Multiple sources, priorities, and revision/conflict handling will be formalized
later. Conflicting authoritative rules must never be silently merged.

## Modules

Large systems may eventually split optional books or supplements into modules.
Modules may contribute entities, rules, creation steps, layouts, assets, and
source mappings. Dependency and override precedence are not yet finalized.

## Packaging

The planned `.ttlpack` format is a ZIP-compatible archive containing the pack
with `manifest.yaml` at its root. Installation must validate paths and content
before atomically activating the pack.

## Current implementation status

Implemented through TTL v0.4.17:

- manifest discovery and validation
- safe declared paths
- character schema and storage
- safe calculated/validation rule engine
- live character-rule recalculation
- generic compendium loading
- stable entity IDs
- tags
- duplicate-ID detection
- explicit cross-file reference validation
- character reference-field validation
- compendium-backed single-reference editor choices
- declarative creation workflow loading and validation
- ordered creation steps with schema-field references
- required-field coverage validation for creation workflows
- persistent per-user character-creation drafts
- resumable multi-step creation wizard
- compendium-backed choices during creation
- live rule/calculated-field updates during creation
- final creation through the normal authoritative character validator
- multi-reference compendium fields in the editor and creation wizard
- navigation from the home page to the character manager
- cancellation of stale live-evaluation requests during navigation
- app-wide compact navigation and safer multi-reference editing
- declared numeric modifier channels (`sum`, `max`, `min`)
- compendium entities contributing numeric effects to modifier channels
- live and saved character calculations using selected-entity effects
- calculation provenance with named modifier sources and UI explanations
- conditional compendium effects with multiple contributions per modifier
- dynamic collection limits with live count/maximum display
- filtered capacities by compendium tags/metadata
- authoritative over-cap validation without silent selection removal

Still intentionally unresolved or future work:

- searchable/paginated UX for very large compendium selection lists
- richer prerequisite relationships and calculated-condition support
- module activation/dependencies/overrides
- rule precedence across modules/books
- namespaces beyond current entity-type + ID lookup
- migration syntax
- localization
- editor/print layout schema
- staged LLM-proposed compendium entries
- `.ttlpack` installation and sharing


### Collection-row effect activation

Conditional effects on compendium entities referenced from a structured collection may use fields from that collection row as well as normal character fields. This distinguishes possession from active use.

```yaml
effects:
  strength_bonus:
    value: 2
    when: equipped == True
```

An unconditional effect applies merely because the referenced entity is present. Conditions may combine row and character state, such as `equipped == True and level >= 5`.


## Character-sheet layout

System Packs may define a presentation layout without changing the character
data schema. `manifest.yaml` declares it through the existing layouts map:

```yaml
layouts:
  character: layout.yaml
```

A character layout contains tabs and titled sections:

```yaml
tabs:
  - id: overview
    title: Overview
    sections:
      - id: identity
        title: Identity
        columns: 2
        fields:
          - name
          - ancestry
          - class
          - level
```

Sections support one through four columns and an optional description. A field
may appear only once. Fields omitted from a valid layout are placed into an
automatic `Other` tab so data cannot become inaccessible because of a layout
omission.

If a System Pack does not provide a character layout, TTL generates the same
generic field layout automatically.


## Scalable compendium selection

Character `reference` and `multi_reference` fields use a searchable compendium
picker rather than exposing a large dropdown. Search matches names, stable
ids, tags, and descriptions, and results can be filtered by tag.

Eligibility remains authoritative. Ineligible entries remain visible with
their requirement information; selected entries remain removable if later
changes make them invalid.

The browser renders at most 250 matching entries at once and asks for a more
specific search when more matches remain. Character data continues to store
stable compendium ids.
