#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app.characters.ai_context import build_character_ai_context, character_retrieval_query
from app.characters.storage import create_character

PACK_ROOT=ROOT/"data/system_packs"

with tempfile.TemporaryDirectory() as td:
    char_root=Path(td)/"characters"
    record=create_character(
        "tester",
        "shadowrun_anarchy",
        initial_data={
            "name":"Analysis Runner",
            "game_level":"Street Runner",
            "metatype":"Human",
            "skills":[
                {
                    "skill":"piloting_other",
                    "custom_name":"",
                    "rating":3,
                    "specialization":"",
                    "knowledge":False,
                }
            ],
            "qualities":[
                {
                    "quality":"guts",
                    "custom_name":"",
                    "polarity":"Positive",
                    "description":"",
                }
            ],
        },
        character_root=char_root,
        pack_root=PACK_ROOT,
    )

    context=build_character_ai_context(
        "tester",
        record.character_id,
        character_root=char_root,
        pack_root=PACK_ROOT,
    )

    assert isinstance(context["structured_fields"],list)
    assert isinstance(context["search_hint_groups"],list)

    skills=next(g for g in context["search_hint_groups"] if g["field_id"]=="skills")
    assert "piloting" in " ".join(skills["hints"]).casefold()

    qualities=next(g for g in context["search_hint_groups"] if g["field_id"]=="qualities")
    assert "guts" in " ".join(qualities["hints"]).casefold()

    query=character_retrieval_query("What are the effects of my qualities?",context)
    assert query.startswith("What are the effects of my qualities?")
    assert "Guts" in query

    indirect=character_retrieval_query("Can I fly a helicopter?",context)
    assert indirect == "Can I fly a helicopter?"

main=(ROOT/"app/main.py").read_text()
ask=(ROOT/"app/templates/ask.html").read_text()

assert "retrieval_query = character_retrieval_query" in main
assert "Apply explicit rules literally, including exceptions, defaults, and untrained rules." in main
assert "Character context tells you what the selected character currently has" in main
assert "does not by itself forbid an action unless a supplied rule says it does" in main
assert "Give the direct answer first, then the minimum explanation needed." in main
assert "Do not pad the answer with unrelated character details or rules." in main
assert "Character-aware</div>" in ask

print("PASS: character-aware rules analysis")
print("  structured character evidence: OK")
print("  category-aware retrieval hints: OK")
print("  indirect-question retrieval stays focused: OK")
print("  sheet/rules/conclusion reasoning contract: OK")
print("  rules citation boundary retained: OK")
