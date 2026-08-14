#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app.characters.ai_context import character_retrieval_query

context={
    "search_hint_groups":[
        {"field_id":"skills","label":"Skills","hints":["Heavy Weapons","Sorcery","Negotiation"]},
        {"field_id":"qualities","label":"Qualities","hints":["Guts","Lucky","Allergy (Orcs)"]},
    ]
}

# Indirect question should remain clean instead of receiving every sheet item.
question="Can Mary fly a helicopter?"
assert character_retrieval_query(question,context)==question

# Explicit category reference should still expand relevant entries only.
quality_query=character_retrieval_query(
    "What are the effects of my qualities?",
    context,
)
assert "Guts" in quality_query
assert "Lucky" in quality_query
assert "Heavy Weapons" not in quality_query

# Explicit named item should enrich retrieval.
named=character_retrieval_query(
    "How does Guts work?",
    context,
)
assert "Guts" in named
assert "Sorcery" not in named

main=(ROOT/"app/main.py").read_text()
ask=(ROOT/"app/templates/ask.html").read_text()

assert "Give the direct answer first, then the minimum explanation needed." in main
assert "Do not pad the answer with unrelated character details or rules." in main
assert "Do not invent restrictions, classifications, interactions, or rules" in main
assert "apply explicit rules literally, including exceptions, defaults, and untrained rules." in main.lower()
assert "Character-aware</div>" in ask

print("PASS: concise character-aware analysis")
print("  indirect retrieval no longer polluted by full sheet: OK")
print("  explicit category expansion retained: OK")
print("  exact item expansion retained: OK")
print("  direct-answer-first prompt contract: OK")
print("  unrelated character summary prohibited: OK")
