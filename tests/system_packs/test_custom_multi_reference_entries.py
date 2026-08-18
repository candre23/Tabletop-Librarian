from pathlib import Path

from app.characters.schema import load_character_schema
from app.characters.layout import complete_character_layout, load_character_layout
from app.rules import load_rule_engine, evaluate_limits
from app.compendium.loader import load_compendium

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "data" / "system_packs" / "generic_d20"


def test_generic_d20_custom_skill_and_feat_companions():
    schema, issues = load_character_schema(PACK / "character.yaml")
    assert schema is not None
    assert not [issue for issue in issues if issue.severity == "error"]
    assert schema.fields["class_skills"].raw["custom_entries_field"] == "class_skills_custom"
    assert schema.fields["feats"].raw["custom_entries_field"] == "feats_custom"
    assert schema.fields["class_skills_custom"].type == "collection"
    assert schema.fields["feats_custom"].type == "collection"


def test_custom_class_skill_counts_toward_limit():
    schema, issues = load_character_schema(PACK / "character.yaml")
    assert schema is not None
    import yaml
    manifest = yaml.safe_load((PACK / "manifest.yaml").read_text(encoding="utf-8"))
    compendium, compendium_issues = load_compendium(PACK, manifest["compendium"])
    assert compendium is not None
    engine, rule_issues = load_rule_engine(PACK / "rules.yaml", known_fields=set(schema.fields))
    assert engine is not None
    data = schema.default_data()
    data.update({
        "character_class": "fighter", "species": "dragonborn", "background": "soldier",
        "class_skills": ["athletics"],
        "class_skills_custom": [{"name": "Streetwise", "description": "Local contacts and rumors."}],
        "bonus_skills": [], "bonus_skills_custom": [],
    })
    results, issues = evaluate_limits(schema, compendium, data, engine)
    row = next(result for result in results if result.id == "class_skill_count")
    assert row.count == 2
    assert row.maximum == 2


def test_hidden_custom_companions_do_not_create_other_tab():
    schema, issues = load_character_schema(PACK / "character.yaml")
    assert schema is not None
    layout, layout_issues = load_character_layout(PACK / "layout.yaml", schema=schema)
    assert layout is not None
    complete = complete_character_layout(layout, schema)
    assert "class_skills_custom" not in complete.field_ids
    assert "feats_custom" not in complete.field_ids
