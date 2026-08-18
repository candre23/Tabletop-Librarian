# Tabletop Librarian System Pack Specification

This document describes the System Pack format implemented by Tabletop Librarian 1.0.0.

System Packs are data-only definitions. They do not contain executable code. A portable pack uses the `.ttlsys` extension and is a ZIP archive with `manifest.yaml` at the archive root (or inside one top-level folder).

## Directory layout

A typical pack looks like:

```text
my_system/
  manifest.yaml
  character.yaml
  rules.yaml
  creation.yaml
  advancement.yaml
  layout.yaml
  compendium/
    skills.yaml
    equipment.yaml
    ...
  README.md
```

Only `manifest.yaml` and the referenced character schema are fundamentally required. Rules, creation, advancement, layouts, and compendium files are optional unless the manifest points to them.

## Manifest

Current pack format: **2**. TTL also accepts format 1 packs for compatibility.

Example:

```yaml
id: my_system
name: My System
version: '1.0'
pack_format: 2
description: Example system
author: Example Author
license: Unlicense
requires_ttl: '>=1.0.0'
character_schema: character.yaml
rules: rules.yaml
creation: creation.yaml
advancement: advancement.yaml
compendium:
  - compendium/skills.yaml
  - compendium/equipment.yaml
layouts:
  character: layout.yaml
```

`id` must use lowercase letters, digits, `.`, `_`, or `-`, and begin with a letter or digit.

## Character schema

`character.yaml` uses schema version 1:

```yaml
schema_version: 1
fields:
  name:
    type: text
    label: Name
    required: true
  level:
    type: integer
    label: Level
    default: 1
    min: 1
    max: 20
```

Supported top-level field types:

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

Collection item fields support `text`, `integer`, `decimal`, `boolean`, `enum`, `reference`, and `notes`.

Common field properties:

- `label`
- `required`
- `default`
- `min` / `max`
- `options` for enum fields
- `entity` for reference fields
- `play_editable`
- `item_schema` for collections

### Resources

A resource stores current/max values:

```yaml
stamina:
  type: resource
  label: Stamina
  default:
    current: 5
    max: 5
  play_editable: true
```

### Collections

Collections store structured rows:

```yaml
weapons:
  type: collection
  label: Weapons
  item_schema:
    weapon:
      type: reference
      entity: weapon
      label: Weapon
    notes:
      type: notes
      label: Notes
```

Useful collection UI metadata implemented by TTL includes:

- `row_label`
- `allow_custom`
- `custom_name_field`
- `autofill`
- `blank_label`
- `show_when_reference_blank`

Generic D20 uses these to label the blank weapon/armor selection as `Custom`, hide the freeform custom-name field when a standard item is selected, and copy standard item values into editable collection fields.

### Standard + custom multi-reference entries

A `multi_reference` field can declare a companion custom-entry collection:

```yaml
class_skills:
  type: multi_reference
  entity: skill
  label: Class Skills
  custom_entries_field: custom_class_skills

custom_class_skills:
  type: collection
  label: Custom Class Skills
  ui_hidden: true
  item_schema:
    name:
      type: text
      required: true
    description:
      type: text
```

The selector exposes `<Custom>`. Standard references retain compendium effects and eligibility; custom rows store freeform descriptive data.

`ui_hidden: true` prevents internal companion fields from becoming an automatic fallback layout section.

## Compendium

Each compendium YAML file declares an entity type and entries:

```yaml
entity: skill
entries:
  - id: athletics
    name: Athletics
    description: Perform difficult physical feats.
    tags: [physical]
    effects:
      athletics_prof: 1
    source:
      book: core
      page: 10
```

Common entry metadata includes:

- `id`
- `name`
- `description`
- `tags`
- `effects`
- `eligibility`
- `source`

System-specific metadata is preserved and can be used by UI autofill behavior.

### Eligibility

A compendium entry may provide:

```yaml
eligibility:
  rule: level >= 4
  message: Requires level 4+.
```

The selector can show all options or hide currently unavailable entries. Selecting an unavailable option is prevented/flagged by the character workflow.

## Rules

`rules.yaml` can define `modifiers`, `calculated`, `validation`, and `limits`.

### Modifiers

```yaml
modifiers:
  defense_bonus:
    label: Defense Bonus
    default: 0
    aggregate: sum
```

Supported aggregate behavior is defined by TTL's rule/modifier engine. Compendium entries and temporary effects can contribute modifier values.

### Calculated values

```yaml
calculated:
  defense:
    formula: 10 + agility_mod + defense_bonus
```

Calculated expressions are evaluated in dependency order.

### Validation

```yaml
validation:
  legal_level:
    rule: level >= 1 and level <= 20
    message: Level must be between 1 and 20.
    severity: error
```

Validation severity can be `error` or `warning`.

### Limits

Limits constrain list/collection selections and can optionally require a full allocation:

```yaml
limits:
  class_skills:
    field: class_skills
    label: Class Skills
    maximum: '2'
    require_full: true
    message: 'Class Skills: {count} selected; choose {maximum}.'
    warning_message: 'Class Skills: {count} / {maximum}.'
```

Limits may also use conditional `where`, custom `usage` expressions, and remaining-capacity warnings.

## Safe expression language

TTL parses rule expressions with a restricted expression evaluator, not Python `eval`.

Supported operators include:

- arithmetic: `+ - * / // % **`
- unary `+`, `-`, `not`
- boolean `and`, `or`
- comparisons: `== != < <= > >=`
- conditional expression: `A if condition else B`

Safe functions:

- `abs`
- `min`
- `max`
- `round`
- `floor`
- `ceil`
- `count`
- `rowsum`
- `rowsum_where`
- `rowcount`
- `nonempty_count`
- `nonempty_count_where`
- `resource`
- `resource_max`

Attribute access, indexing, imports, lambdas, arbitrary calls, and private/special names are not permitted.

## Creation workflow

`creation.yaml` uses workflow version 1:

```yaml
version: 1
title: Create Character
steps:
  - id: identity
    title: Identity
    description: Choose core character information.
    fields:
      - name
      - archetype
    lock_after:
      - archetype
final_changes:
  hp_current: hp_max
```

Fields may appear in only one creation step. Calculated fields cannot be direct inputs. Required fields without defaults must be reachable in creation.

`lock_after` can make selected identity/system-defining values immutable after the step is completed.

`final_changes` applies safe expressions immediately before final character creation.

Creation drafts persist while moving between steps and remember the furthest completed step so completed steps can be revisited.

## Advancement

`advancement.yaml` uses version 1:

```yaml
version: 1
actions:
  - id: gain_level
    title: Gain a Level
    available_when: level < 20
    changes:
      level: level + 1
    steps:
      - id: review
        title: Review Level Up
        fields:
          - hp_max
          - notes
```

An action can define:

- `available_when`
- deterministic `changes`
- one or more interactive review/input steps

Advancement drafts detect stale character data so a draft cannot silently overwrite a character modified elsewhere.

## Character layout

The manifest can point `layouts.character` to a layout file.

A layout contains tabs and sections. Common section metadata includes:

- `id`
- `title`
- `fields`
- `columns`
- `span`
- `color`
- `body_color`
- `visible_when`

Fields can also specify display modes such as stat/block/table according to the character templates.

`visible_when` supports conditional UI sections driven by current character values. Generic D20 uses this for Human-only fields, species-specific options, and spellcasting sections.

If an explicit layout is invalid/incomplete, TTL can fall back to a generic layout; pack authors should run the validator before distribution.

## Temporary effects

TTL can apply temporary modifier operations to character fields during play. These remain separate from the authoritative base character data and are included in effective values/AI character context.

## Portability

### `.ttlsys`

A System Pack package is a ZIP file using the `.ttlsys` extension. TTL enforces archive member/expanded-size limits and rejects unsafe paths.

When replacing an installed pack, TTL:

1. validates the staged pack;
2. backs up the old pack;
3. migrates compatible character fields;
4. removes obsolete references;
5. warns about incompatible values requiring review;
6. atomically swaps the pack directory where possible.

### `.ttlchar`

Characters can be exported/imported independently as `.ttlchar` packages. The matching System Pack must be installed locally for validation.

## Validation

Validate installed/source packs with:

```bash
python tools/validate_system_packs.py
```

Pack authors should validate before creating a `.ttlsys` archive and again after importing it into a clean TTL installation.

## Built-in example

`data/system_packs/generic_d20/` is the canonical 1.0 example. It demonstrates pack format 2, conditional layouts, eligibility, limits, calculated values, guided creation, advancement, structured collections, standard/custom references, and compendium autofill metadata.
