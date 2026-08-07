# Tabletop Librarian System Pack Specification

**Status:** Draft v1  
**Intended project filename:** `system_packs.md`  
**Applies to:** Tabletop Librarian v0.4+  
**Purpose:** Define the structure, responsibilities, and compatibility rules for modular tabletop RPG System Packs.

---

## 1. Overview

A **System Pack** is a self-contained collection of declarative files that teaches Tabletop Librarian how to represent, create, validate, calculate, display, and eventually export characters for a tabletop RPG system.

System Packs are intentionally modular. A small game may contain only a handful of files and a small compendium. A large game may contain many modules spanning dozens of sourcebooks and thousands of selectable entities.

A System Pack must not require custom Python code.

The core architectural boundary is:

> **The System Pack defines how a game works and what structured content is available. Tabletop Librarian provides the runtime engine. The LLM may discover, explain, and propose content, but it is not the authoritative rules engine.**

---

## 2. Design Goals

System Packs must support:

- Very small and very large RPG systems.
- Systems with radically different character creation methods.
- Systems with or without classes, races, skills, levels, equipment, spells, or similar concepts.
- Large catalogs of skills, powers, classes, professions, races, weapons, gear, spells, feats, advantages, and other entities.
- Deterministic calculations and validation.
- Interdependent character statistics.
- Eligibility and prerequisite rules.
- Content divided across multiple books or supplements.
- Optional sourcebook/module activation.
- Source provenance and page references.
- Human-readable storage.
- Safe sharing and installation.
- Future packaging as a single installable archive.
- Future LLM-assisted compendium generation and maintenance.

System Packs should remain understandable and editable without proprietary development tools.

---

## 3. Architectural Responsibilities

### 3.1 System Pack responsibilities

A System Pack may define:

- Character data structure.
- Character creation workflow.
- Deterministic formulas.
- Validation rules.
- Eligibility requirements.
- Derived values.
- Effects and modifiers.
- Entity types.
- Structured compendium content.
- Optional system modules.
- Source provenance.
- Editor layout.
- Print/export layout.
- Assets.
- Character data migrations.

### 3.2 Tabletop Librarian core responsibilities

TTL core owns:

- System Pack discovery and loading.
- YAML/JSON parsing.
- Pack validation.
- Safe expression evaluation.
- Dependency tracking.
- Circular dependency detection.
- Character storage.
- User permissions.
- Dynamic editor rendering.
- Character creation workflow rendering.
- Calculation updates.
- Pack installation and removal.
- Module activation.
- Source-document linking.
- RAG/LLM integration.
- Future `.ttlpack` archive handling.

### 3.3 LLM responsibilities

The LLM may:

- Explain rules.
- Search sourcebooks.
- Recommend options.
- Discover uncataloged content.
- Propose structured compendium entries.
- Propose rules or formulas for review.
- Assist with System Pack creation.
- Assist with importing source material.

The LLM must not be required for:

- Character legality checks.
- Runtime calculations.
- Eligibility checks.
- Prerequisite enforcement.
- Automatic bonuses.
- Resource totals.
- Deterministic character-sheet behavior.

If information affects character legality, calculation, validation, selectable options, or automatic behavior, it should ultimately exist as structured System Pack data.

---

## 4. Directory Structure

Initial System Packs are ordinary directories.

Example:

```text
data/
  system_packs/
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
        logo.png
        icons/

      sources/
        source_map.yaml

      modules/
        optional_module_a/
        optional_module_b/

      migrations/
```

Only files declared by the pack or permitted by the pack format are loaded.

The precise set of compendium files is not fixed.

A game may define:

```text
skills/
moves/
edges/
implants/
powers/
occupations/
classes/
ancestries/
vehicles/
```

or any other entity categories it needs.

---

## 5. Required Files

A System Pack requires:

```text
manifest.yaml
character.yaml
```

The following are optional:

```text
rules.yaml
creation.yaml
compendium/
layouts/
assets/
sources/
modules/
migrations/
```

A minimal pack may therefore contain only:

```text
minimal_game/
  manifest.yaml
  character.yaml
```

---

# 6. `manifest.yaml`

The manifest identifies the pack and declares its components.

Example:

```yaml
id: eldritch
name: Eldritch Role-Playing System
version: 0.1.0
pack_format: 1

description: Character support for Eldritch RPG

requires_ttl: ">=0.4.0"

character_schema: character.yaml
rules: rules.yaml
creation: creation.yaml

compendium:
  - compendium/abilities.yaml
  - compendium/skills.yaml
  - compendium/races.yaml
  - compendium/equipment.yaml

layouts:
  editor: layouts/editor.yaml
  print_html: layouts/print.html
  print_css: layouts/print.css
```

## 6.1 Required manifest properties

### `id`

Stable machine-readable identifier.

Requirements:

- Unique among installed System Packs.
- Lowercase recommended.
- Must not change between ordinary pack revisions.
- Must not depend on the display name.

Example:

```yaml
id: eldritch
```

### `name`

Human-readable system name.

### `version`

Version of this particular System Pack.

Example:

```yaml
version: 0.1.0
```

### `pack_format`

Version of the TTL System Pack specification used by the pack.

Example:

```yaml
pack_format: 1
```

`pack_format` and `version` have different purposes:

- `pack_format` describes compatibility with TTL's System Pack schema.
- `version` describes revisions to this particular game pack.

## 6.2 Optional manifest properties

Likely fields include:

```yaml
description:
author:
license:
homepage:
requires_ttl:
character_schema:
rules:
creation:
compendium:
layouts:
assets:
sources:
modules:
```

The exact v1 schema will be finalized during implementation.

---

# 7. `character.yaml`

`character.yaml` defines the structure of saved character data.

The schema must not assume universal RPG concepts such as:

- race
- class
- level
- skill
- strength
- hit points

Those concepts are created by the System Pack if the game uses them.

Example:

```yaml
fields:
  name:
    type: text
    required: true

  level:
    type: integer
    default: 1

  race:
    type: reference
    entity: race

  occupation:
    type: reference
    entity: occupation

  abilities:
    type: collection
    entity: ability_entry

  inventory:
    type: collection
    entity: item_entry
```

## 7.1 Initial field types

The v1 format should support at least:

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

Additional types may be added as actual systems require them.

## 7.2 References

References use stable entity IDs, not display names.

Example:

```yaml
race: dwarf
occupation: warrior
```

The displayed name may later change without breaking saved characters.

## 7.3 Collections

Collections represent repeated structured data such as:

- skills
- equipment
- spells
- attacks
- contacts
- powers
- cybernetics

A collection entry may reference a compendium entity and contain character-specific overrides or state.

---

# 8. Saved Character Files

Saved characters should contain character-specific information only.

System definitions should not be duplicated into every character file.

Example:

```json
{
  "system_id": "eldritch",
  "system_version": "0.1.0",
  "character_schema": 1,
  "data": {
    "name": "Gegdin",
    "level": 1
  }
}
```

The file records:

- System Pack ID.
- System Pack version.
- Character schema version.
- Character-specific data.

This provides a basis for future migrations.

---

# 9. `rules.yaml`

`rules.yaml` defines deterministic system behavior.

Possible rule categories include:

```yaml
calculated:
validation:
eligibility:
effects:
derived_collections:
```

These categories are conceptual and may be refined during implementation.

---

## 9.1 Calculated values

Example:

```yaml
calculated:
  resilience:
    formula: resistance_mrv * 2 + willpower_mrv + arcanum_tree_mrv
```

Calculated values automatically update when their dependencies change.

TTL must build a dependency graph and evaluate calculations in dependency order.

Circular references must be rejected.

---

## 9.2 Validation

Validation identifies illegal or inconsistent character states.

Example:

```yaml
validation:
  mastery_rank:
    rule: mastery.rank <= mastery.specialization.rank
    message: Mastery cannot exceed its linked Specialization.
```

Validation may either:

- prevent a change, or
- allow the state while displaying an error/warning,

depending on the rule's configured severity.

Potential severities:

```text
error
warning
info
```

---

## 9.3 Eligibility

Eligibility controls selectable options.

Example:

```yaml
eligibility:
  advanced_demolitions:
    any:
      - occupation_tag: military_engineer
      - occupation_tag: demolitions_specialist
```

Eligibility should be usable for:

- skills
- classes
- professions
- feats
- powers
- equipment
- spells
- advancement choices
- any custom entity type

---

## 9.4 Effects and modifiers

Effects describe how selections change other character values.

Example:

```yaml
effects:
  racial_speed_bonus:
    when: character.race == "some_race"
    apply:
      target: abilities.speed
      add: 1
```

Effects may come from:

- race/ancestry
- class/profession
- skills
- feats
- powers
- equipment
- conditions
- temporary effects
- user-entered modifiers

The engine must preserve the origin of modifiers when practical so the UI can explain totals.

Example conceptual result:

```text
Agility: 17
  Base: 14
  Elf: +2
  Light Armor Training: +1
```

---

# 10. Safe Expression Language

System Pack formulas must never execute arbitrary Python, JavaScript, shell commands, or other executable code.

TTL will provide a restricted expression evaluator.

Expected capabilities include:

- Numeric literals.
- String literals.
- Boolean literals.
- Field references.
- Arithmetic.
- Parentheses.
- Comparisons.
- Boolean operators.
- Conditional expressions.
- Safe built-in functions.
- Collection aggregation where required.

Possible examples:

```text
strength + 2
level * 3
max(1, endurance)
mastery.rank <= specialization.rank
race == "human"
sum(skills.cost)
```

The exact grammar will be defined separately during implementation.

Unsupported expressions must fail validation before the pack is activated.

---

# 11. `creation.yaml`

`creation.yaml` defines the character creation workflow.

TTL must not assume that every game uses the same creation order.

Examples of valid game structures include:

```text
Race -> Class -> Attributes -> Skills -> Equipment
```

```text
Attributes -> Point-buy abilities -> Advantages/Disadvantages
```

```text
Playbook -> Moves -> Ratings
```

or any other sequence.

Example:

```yaml
steps:
  - id: identity
    title: Identity
    fields:
      - name

  - id: race
    type: entity_select
    entity: race
    target: race

  - id: occupation
    type: entity_select
    entity: occupation
    target: occupation

  - id: abilities
    type: allocation
    entity: ability
    target: abilities
    budget:
      formula: 30
```

## 11.1 Conditional steps

Steps may appear conditionally.

Example:

```yaml
when: character.race == "human"
```

## 11.2 Creation workflow versus character editor

The creation workflow and ordinary character editor are separate concepts.

Creation may:

- restrict the order of choices,
- enforce creation-only budgets,
- hide later-level options,
- guide new users.

The normal character editor may expose the same fields differently after creation is complete.

---

# 12. Compendium

The compendium stores structured game content.

Examples include:

- abilities
- skills
- races
- ancestries
- classes
- occupations
- professions
- advantages
- disadvantages
- feats
- edges
- powers
- spells
- weapons
- armor
- equipment
- vehicles
- cybernetics
- creatures

TTL does not hardcode these categories.

---

# 13. Generic Compendium Entity Format

Each compendium file declares an entity type and contains entries.

Example:

```yaml
entity: skill

entries:
  - id: stealth
    name: Stealth
    restricted: false

  - id: surgery
    name: Surgery
    restricted: true
    requirements:
      any:
        - occupation: physician
        - tag: medical_training
```

Each entity requires at least:

```yaml
id:
name:
```

Everything else is system-defined metadata interpreted by rules, workflows, and layouts.

---

# 14. Large Compendiums

A compendium category may be split across files.

Example:

```text
compendium/
  skills/
    core.yaml
    magic.yaml
    psionics.yaml
    technical.yaml
```

A large pack should not require one enormous YAML file.

TTL should merge all enabled entries of the same entity type into a logical entity collection.

Duplicate IDs within the active namespace are errors unless an explicit override mechanism is later defined.

---

# 15. Modular Sourcebook Support

Large systems may organize content into optional modules.

Example:

```text
rifts/
  manifest.yaml
  character.yaml
  rules.yaml
  creation.yaml

  modules/
    core/
    magic/
    psionics/
    north_america/
    sourcebook_12/
```

A module may contribute:

- compendium entities
- rules
- creation options
- layouts
- assets
- source mappings

This allows users to enable only the books/content they actually use.

Example future behavior:

```text
Enabled:
  Core Rules
  Book A
  Book C

Disabled:
  Book B
```

Only enabled module content appears in character creation and selection interfaces.

---

# 16. Module Dependencies

Modules may eventually declare dependencies.

Example:

```yaml
id: advanced_magic
requires:
  - core
  - magic
```

TTL must reject activation if required modules are unavailable.

Circular module dependencies are invalid.

---

# 17. Source Provenance

Structured compendium entries should optionally identify their original source.

Example:

```yaml
source:
  document_key: eldritch_core
  page: 17
  section: Abilities
```

Entries may have multiple sources:

```yaml
sources:
  - document_key: core
    page: 17

  - document_key: revised_rules
    page: 4
    priority: revised
```

Source provenance enables:

- "View Rule" links.
- Direct source-page navigation.
- Conflict investigation.
- Rule revision tracking.
- LLM-assisted verification.
- Compendium maintenance.

---

# 18. Rule Revisions and Conflicts

A System Pack must not silently merge conflicting rules.

Where possible, structured entries should preserve:

- original source
- revised source
- priority
- edition
- module
- effective status

Potential future metadata:

```yaml
sources:
  - document_key: core
    page: 39
    status: superseded

  - document_key: monsters
    page: 4
    status: current
```

The exact conflict model will be refined after real-world packs demonstrate the required complexity.

---

# 19. Lazy Compendium Model

Large systems should not require complete manual cataloging before they become usable.

TTL may support a **lazy compendium** workflow:

1. User searches for an uncataloged option.
2. RAG searches relevant sourcebooks.
3. LLM proposes a structured entry.
4. Supporting citations are shown.
5. User/GM reviews the proposal.
6. Accepted data is written into a compendium file.
7. Future character operations use the structured entry deterministically.

The LLM-generated proposal is never authoritative until accepted into structured pack data.

This model allows large systems to grow organically through actual use.

---

# 20. Layouts

System Packs may provide layouts separately from the underlying character schema.

Possible files:

```text
layouts/
  editor.yaml
  print.html
  print.css
```

## 20.1 Editor layout

Defines how fields are organized in the browser editor.

Likely concepts:

- sections
- tabs
- columns
- groups
- repeating rows
- resource trackers
- entity lists
- notes
- portrait/image fields

## 20.2 Print/export layout

A pack may supply HTML/CSS used to render a printable or portable character sheet.

The architectural relationship is:

```text
System Pack template + Character JSON -> Rendered HTML
```

The character page must not require custom hardcoded TTL routes or system-specific Python.

---

# 21. Assets

System Packs may contain non-executable assets.

Examples:

```text
assets/
  logo.png
  background.webp
  icons/
```

Allowed asset types will be restricted.

Executable files must not be permitted.

---

# 22. Pack Validation

TTL must validate a System Pack before activation.

Validation should include at least:

- Manifest syntax.
- Supported `pack_format`.
- Required files.
- Duplicate entity IDs.
- Invalid references.
- Missing references.
- Invalid expressions.
- Circular calculated-value dependencies.
- Invalid creation steps.
- Unknown field types.
- Invalid module dependencies.
- Unsafe paths.
- Unsupported asset types.

A pack should either load successfully or fail clearly.

TTL should not partially activate a malformed pack.

---

# 23. Validation Reporting

Validation errors should be actionable.

Example:

```text
System Pack validation failed

compendium/skills.yaml
  Entry: advanced_demolitions
  Error: Unknown occupation reference "combat_engineer"

rules.yaml
  Rule: total_defense
  Error: Circular dependency:
         total_defense -> armor_bonus -> total_defense
```

This validation tooling will also support future pack authors and LLM-generated content.

---

# 24. Pack Security

System Packs are data, not plugins.

They must not execute arbitrary code.

Disallowed:

- Python.
- JavaScript executed as pack logic.
- Shell scripts.
- Native executables.
- Dynamic imports.
- Arbitrary filesystem access.
- Network requests.

All logic must pass through TTL's restricted expression/rule engine.

This is essential because System Packs are intended to become shareable files.

---

# 25. Future `.ttlpack` Packaging

The initial implementation uses ordinary directories.

Later, the exact same directory may be packaged as:

```text
eldritch.ttlpack
```

A `.ttlpack` will be a ZIP-compatible archive containing the System Pack contents.

Example archive root:

```text
manifest.yaml
character.yaml
rules.yaml
creation.yaml
compendium/
layouts/
assets/
sources/
modules/
migrations/
```

There should not be an unnecessary enclosing directory inside the archive.

---

# 26. Pack Installation

Future `.ttlpack` installation should:

1. Accept the archive.
2. Inspect it without executing anything.
3. Reject unsafe archive paths.
4. Read `manifest.yaml`.
5. Check `pack_format`.
6. Check TTL version compatibility.
7. Validate all referenced files.
8. Validate formulas and references.
9. Extract to a temporary directory.
10. Atomically install to:

```text
data/system_packs/<pack_id>/
```

11. Activate only after successful validation.

A failed installation must not damage an existing installed pack.

---

# 27. Pack Updates

Installing a newer version of an existing pack should eventually support:

- version comparison
- backup of existing pack
- character compatibility checks
- required migrations
- rollback on failure

Pack updates must never silently destroy user-created compendium additions.

The strategy for separating upstream pack content from local user additions remains to be designed.

---

# 28. Character Migrations

A System Pack may eventually contain:

```text
migrations/
```

Migrations update saved character data when the character schema changes.

A character records its originating schema/version.

Example:

```json
{
  "system_id": "eldritch",
  "system_version": "0.1.0",
  "character_schema": 1
}
```

A newer pack may contain migration rules to transform schema 1 to schema 2.

Migration logic must also be declarative and non-executable.

---

# 29. Entity Identity and Namespaces

All referenced entities require stable IDs.

Example:

```yaml
id: long_sword
name: Long Sword
```

IDs are machine identifiers.

Names are presentation values.

IDs should remain stable when:

- spelling changes
- display names change
- capitalization changes
- localization is added

Large modular systems may eventually require explicit namespacing, for example:

```text
core.long_sword
book12.long_sword_variant
```

The exact namespace mechanism will be determined during implementation.

---

# 30. Tags

Tags are expected to be an important generic mechanism.

Example:

```yaml
tags:
  - military
  - technical
  - trained_only
```

Tags can support:

- eligibility
- filtering
- categorization
- rule targeting
- creation workflows
- LLM discovery

Tags should supplement explicit relationships rather than replace them when a direct reference is more appropriate.

---

# 31. Scalability Requirements

The architecture must remain practical for both:

```text
20 skills
10 equipment items
4 character archetypes
```

and:

```text
1,000+ skills
hundreds of classes/professions
thousands of equipment entries
dozens of sourcebooks
```

Therefore:

- Compendium data must be split-capable.
- Modules must be optional.
- Content should be loaded/indexed efficiently.
- The character editor should not load thousands of options into a single uncontrolled dropdown.
- Search/filter interfaces will be required for large entity collections.
- Structured data and sourcebook RAG must coexist.

---

# 32. System Pack / RAG Boundary

Use structured pack data for facts that affect runtime behavior.

Examples that should be structured:

- Whether a profession may select a skill.
- Skill prerequisites.
- Racial bonuses.
- Attribute calculations.
- Weapon damage.
- Armor values.
- Advancement costs.
- Spell eligibility.
- Remaining allocation points.
- Derived statistics.
- Validation rules.

RAG/LLM is appropriate for:

- Narrative descriptions.
- Rule explanations.
- Lore.
- Recommendations.
- Finding relevant sourcebook material.
- Discovering uncataloged content.
- Proposing structured additions.

Rule of thumb:

> If changing the answer could make a character mechanically legal or illegal, or alter a calculated value, it belongs in structured data.

---

# 33. Initial Implementation Sequence

The recommended v0.4 implementation order is:

## v0.4.1 - System Pack loader and manifest

- Discover pack directories.
- Parse `manifest.yaml`.
- Basic compatibility checks.
- Display installed System Packs.

## v0.4.2 - Character schema

- Parse `character.yaml`.
- Implement basic field types.
- Validate character data.
- Save human-readable character JSON.

## v0.4.3 - Expression/rule engine

- Restricted expression parser.
- Calculated fields.
- Dependency tracking.
- Circular dependency detection.
- Validation rules.

## v0.4.4 - Compendium engine

- Generic entity loader.
- Stable IDs.
- Cross-file references.
- Tags.
- Multiple files per entity type.
- Pack validation.

## v0.4.5 - Creation workflow

- Parse `creation.yaml`.
- Render steps.
- Conditional steps.
- Entity selection.
- Allocation steps.

## v0.4.6 - Character editor

- Generic editor from schema/layout.
- Calculated-value updates.
- Validation messages.
- Compendium search/select controls.

## v0.4.7 - Layout and export

- Editor layouts.
- Print layouts.
- Self-contained HTML export.

## Later

- Optional modules.
- `.ttlpack` installation.
- Declarative migrations.
- Lazy LLM-assisted compendium construction.
- Pack authoring tools.
- LLM-assisted pack generation.

---

# 34. Open Design Questions

The following should remain intentionally unresolved until implementation or real-world System Packs expose the best solution:

1. Exact safe-expression grammar.
2. Exact editor layout schema.
3. Exact module override/conflict behavior.
4. Entity namespace syntax.
5. Local user additions versus upstream System Pack updates.
6. Character migration syntax.
7. Localization.
8. Pack dependency support between separate System Packs.
9. Whether compendium files remain YAML only or allow JSON.
10. Performance/indexing strategy for very large compendiums.
11. Exact rule precedence model when supplements revise core rules.
12. How LLM-generated proposed entries are staged before acceptance.

These should be decided based on concrete needs rather than predicted prematurely.

---

# 35. Guiding Principles

1. **Modularity first.**
2. **System-neutral core.**
3. **Structured mechanics, RAG-assisted knowledge.**
4. **No executable pack code.**
5. **Human-readable authoritative data.**
6. **Stable IDs, mutable display names.**
7. **Small systems stay simple.**
8. **Large systems scale by modules and split compendiums.**
9. **Source provenance is preserved whenever possible.**
10. **Invalid packs fail clearly and atomically.**
11. **The schema evolves from real system requirements, not speculation.**
12. **A System Pack directory should eventually be directly packageable as a single `.ttlpack` file without structural changes.**

---

## 36. Current Status

This document establishes the initial System Pack architecture for Tabletop Librarian v0.4.

It is a working specification rather than a permanently frozen standard.

As implementation proceeds:

- ambiguities should be clarified here,
- schema decisions should be recorded here,
- incompatible changes should update `pack_format`,
- and examples should be updated to reflect the actual implementation.

The specification should remain the authoritative design reference for System Pack development.
