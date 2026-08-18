from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_generic_d20_custom_weapon_and_armor_metadata():
    schema = yaml.safe_load(
        (ROOT / "data/system_packs/generic_d20/character.yaml").read_text(encoding="utf-8")
    )
    weapons = schema["fields"]["weapons"]["item_schema"]
    armor = schema["fields"]["armor_items"]["item_schema"]

    assert weapons["weapon"]["blank_label"] == "Custom"
    assert weapons["custom_name"]["show_when_reference_blank"] == "weapon"
    assert armor["armor"]["blank_label"] == "Custom"
    assert armor["custom_name"]["show_when_reference_blank"] == "armor"


def test_character_templates_support_conditional_custom_collection_fields():
    for name in ("create.html", "edit.html", "advance.html"):
        text = (
            ROOT / "app/templates/characters" / name
        ).read_text(encoding="utf-8")
        assert "blank_label" in text
        assert "data-show-when-reference-blank" in text
        assert "refreshConditionalCollectionFields" in text
