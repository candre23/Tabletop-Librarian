from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "data" / "system_packs" / "generic_d20"

def load(name):
    return yaml.safe_load((PACK / name).read_text(encoding="utf-8"))

def test_spell_compendium_has_effect_and_scaling_text():
    cantrips = load("compendium/cantrips.yaml")["entries"]
    spells = load("compendium/spells.yaml")["entries"]
    acid = next(x for x in cantrips if x["id"] == "acid_splash")
    burning = next(x for x in spells if x["id"] == "burning_hands")
    assert "Cantrip Upgrade." in acid["description"]
    assert "Using a Higher-Level Spell Slot." in burning["description"]
    assert all(x.get("description") for x in cantrips + spells)

def test_spell_slot_tracking_fields_present():
    fields = load("character.yaml")["fields"]
    for level in range(1, 10):
        assert fields[f"spell_slot_{level}_used"]["play_editable"] is True
        assert fields[f"spell_slot_{level}_used"]["max_field"] == f"spell_slot_{level}_max"
        assert fields[f"spell_slot_{level}_max"]["type"] == "calculated"
    assert fields["pact_slots_used"]["play_editable"] is True

def test_completed_character_exposes_state_for_visibility():
    text = (ROOT / "app/templates/characters/edit.html").read_text(encoding="utf-8")
    assert "window.ttlCharacterState = {{ record.data|tojson }};" in text
    assert 'field.raw.get("max_field")' in text
