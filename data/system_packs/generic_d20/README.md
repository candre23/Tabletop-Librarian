# Generic D20 System Pack v1.0

Generic D20 is Tabletop Librarian's built-in 5E-compatible example System Pack. It is derived from SRD 5.2.1 and is intended to provide a broadly familiar, openly licensed system for first-run use and demonstration.

## v1.0 scope

- Guided level 1 creation.
- All 12 SRD classes and their SRD subclasses.
- All 4 SRD backgrounds.
- All 9 SRD species, including lineage/ancestry selections.
- All 18 skills, class/background skill proficiency handling, and later Expertise tracking.
- SRD Origin, General, Fighting Style, and Epic Boon feats.
- Complete SRD class cantrip and spell lists as structured selectable entries.
- Complete SRD weapon and armor tables.
- Automatic ability modifiers, proficiency bonus, saving throws, skill modifiers, initiative, speed, spell attack bonus, and spell save DC.
- Level advancement action through level 20.

## Current generic-engine limitations

Generic D20 v1.0 deliberately focuses on single-class characters. Multiclass spell-slot calculation and automatic injection of every class/species feature are not represented as deterministic pack logic yet. Level-up feature choices and post-level-1 Hit Point increases are recorded by the player/GM. Armor Class is initialized to the unarmored value at creation and remains player-editable so equipped armor, shields, and special class formulas can be recorded correctly.

## License and attribution

This work includes material from the System Reference Document 5.2.1 (“SRD 5.2.1”) by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the Creative Commons Attribution 4.0 International License, available at https://creativecommons.org/licenses/by/4.0/legalcode.

Generic D20 is 5E compatible. The name “Generic D20” is Tabletop Librarian's system-pack name and is not an official Wizards of the Coast product.


## Picker and sheet usability

Generic D20 uses conditional character-sheet sections so Human-only, species-specific, and spellcasting-only choices appear only when relevant. Standard weapon and armor selections can populate their ordinary rules values into editable character rows; custom/special variants remain editable.


## Character-builder behavior

Generic D20 drives fixed background Origin feats automatically. Human-only choices,
species ancestry/lineage controls, and class spellcasting controls are shown only when
applicable. Background ability boosts that are not permitted by the selected background
are disabled and reset to zero. Standard weapons and armor carry metadata used by TTL
to prefill their normal attack/damage/AC values.


## Custom skills and feats

Skill and feat selectors include a `<Custom>` choice. Custom rows store a freeform name and description alongside standard compendium selections. Standard entries retain their normal compendium effects and eligibility rules; custom entries are descriptive unless the GM/system pack supplies their mechanics separately.
