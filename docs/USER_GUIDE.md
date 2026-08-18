# User Guide

## Accounts and roles

TTL supports GM and player accounts. GMs administer the library, knowledgebase, System Packs, users, and AI settings. Players see material made available to them and manage their own characters. GMs can open player characters directly for play/configuration without creating separate copies.

## Library

The Library Manager can register physical directories and upload documents. Adding a physical directory discovers descendant directories so nested collections can be represented independently.

Supported reader formats:

- PDF
- CBZ
- CBR
- PNG/JPEG/WebP/GIF
- TXT
- Markdown

The source library may be read-only. TTL stores generated covers, OCR derivatives, extracted text, chunks, and embeddings in its own data/cache locations rather than modifying source books.

## OCR

Scanned documents can be converted to persistent searchable PDF derivatives. The source file remains unchanged. OCR state is tied to the source path, size, and modification time so TTL knows when an OCR derivative has become stale.

See [OCR](OCR.md).

## Knowledgebase

The Knowledgebase turns supported library documents into AI-searchable reference material in stages:

1. extracted text;
2. context chunks;
3. semantic embeddings.

**Update Knowledgebase** is incremental. Unchanged documents reuse existing work. **Rebuild Entire Knowledgebase** is intended for changes to embedding/indexing behavior or deliberate clean rebuilds.

The first semantic embedding build may need internet access to download the selected embedding model.

## Ask and AI

TTL supports Basic and Advanced Ask modes. Retrieval respects library visibility permissions.

Basic Ask uses a simpler retrieval/final-answer path. Advanced Ask uses a configurable pipeline preset with planning, retrieval, evidence ranking/selection, analysis, decision, optional rescue, and composition stages.

When a character is selected, TTL can provide authoritative character state to the AI separately from retrieved rules evidence. Character-sheet state is context, not a cited rules source.

## Characters

Characters are controlled by System Packs. A pack may define:

- character fields and defaults;
- calculated values and validation rules;
- compendium entities;
- guided creation steps;
- advancement actions;
- layout and conditional UI sections.

Characters can include structured collections, standard and custom multi-reference entries, temporary effects, and play-editable resources.

### Portable characters

Characters can be exported as `.ttlchar` ZIP packages containing an authoritative character record and manifest. Imports validate against the matching locally installed System Pack.

### Portable systems

System Packs are portable `.ttlsys` ZIP packages. Importing a replacement version can migrate existing characters while preserving compatible fields and warning about values requiring review.

## Generic D20

TTL 1.0 includes **Generic D20 1.0**, derived from SRD 5.2.1. It demonstrates:

- guided level-1 creation;
- 12 classes and SRD subclasses;
- species/background choices;
- ability scores and background boosts;
- skills, feats, weapons, armor, cantrips, and spells;
- conditional character-builder controls;
- standard/custom skills, feats, weapons, and armor;
- calculated saves, skill modifiers, proficiency, initiative, and spell values;
- level advancement support through level 20.

Generic D20 intentionally remains system-neutral in naming and is not an official Wizards of the Coast product.
