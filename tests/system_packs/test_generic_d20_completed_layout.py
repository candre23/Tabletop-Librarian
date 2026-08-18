from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]

def _layout():
    return yaml.safe_load((ROOT / "data/system_packs/generic_d20/layout.yaml").read_text(encoding="utf-8"))

def _schema():
    return yaml.safe_load((ROOT / "data/system_packs/generic_d20/character.yaml").read_text(encoding="utf-8"))

def test_completed_layout_is_compact_and_balanced():
    sections = {s["id"]: s for s in _layout()["tabs"][0]["sections"]}
    assert sections["attacks"]["span"] == 6
    assert sections["armor"]["span"] == 6
    assert sections["ability_build"]["hide_in_play"] is True
    assert "spell_slots" not in sections
    assert "pact_magic_slots" not in sections

def test_feats_are_unified_after_creation():
    sections = {s["id"]: s for s in _layout()["tabs"][0]["sections"]}
    assert "human_feat" not in sections
    feat_field = sections["features"]["fields"][0]
    assert feat_field["id"] == "feats"
    assert feat_field["include_reference_fields"] == ["origin_feat", "bonus_origin_feat"]
    schema = _schema()["fields"]
    assert schema["origin_feat"]["ui_hidden"] is True
    assert schema["bonus_origin_feat"]["ui_hidden"] is True

def test_weapon_and_armor_equipped_and_multiline_fields():
    schema = _schema()["fields"]
    weapons = schema["weapons"]["item_schema"]
    armor = schema["armor_items"]["item_schema"]
    assert weapons["equipped"]["type"] == "boolean"
    assert weapons["custom_name"]["type"] == "notes"
    assert weapons["notes"]["type"] == "notes"
    assert armor["custom_name"]["type"] == "notes"
    assert armor["notes"]["type"] == "notes"

def test_spell_slots_are_inside_spellcasting_section():
    sections = {s["id"]: s for s in _layout()["tabs"][0]["sections"]}
    fields = [x if isinstance(x, str) else x["id"] for x in sections["spellcasting"]["fields"]]
    assert "spell_slot_1_used" in fields
    assert "spell_slot_9_used" in fields
    assert "pact_slots_used" in fields

def test_layout_template_supports_play_only_cleanup_options():
    text = (ROOT / "app/templates/characters/edit.html").read_text(encoding="utf-8")
    assert "section.hide_in_play" in text
    assert "hide_add_in_play" in text
    assert "include_reference_fields" in text
