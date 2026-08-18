from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_creation_exposes_saved_state_to_shared_pack_widgets():
    text = (
        ROOT / "app/templates/characters/create.html"
    ).read_text(encoding="utf-8")
    assert "window.ttlCharacterState = ttlDraftState;" in text


def test_shared_visibility_falls_back_to_saved_character_state():
    text = (
        ROOT / "app/static/js/pack_widgets.js"
    ).read_text(encoding="utf-8")
    assert "const saved = window.ttlCharacterState;" in text
    assert "hasOwnProperty.call(saved, fieldId)" in text


def test_closed_compendium_dialog_does_not_rebuild_large_result_list():
    text = (
        ROOT / "app/templates/characters/create.html"
    ).read_text(encoding="utf-8")
    assert text.count("if (dialog.open) renderResults();") >= 2
