#!/usr/bin/env python3
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.characters.schema import load_character_schema
from app.characters.storage import create_character, load_character
from app.characters.web import _reference_options
from app.compendium import load_compendium
from app.system_packs import load_system_pack


def main() -> int:
    pack_root = PROJECT_ROOT / 'tests' / 'fixtures' / 'system_packs'
    pack = load_system_pack(pack_root / 'ttl_test_minimal')
    assert pack.valid and pack.manifest is not None

    schema, issues = load_character_schema(pack.root / pack.manifest.character_schema)
    assert schema is not None, [issue.format() for issue in issues]

    compendium, issues = load_compendium(pack.root, pack.manifest.compendium)
    assert compendium is not None, [issue.format() for issue in issues]

    options = _reference_options(schema, compendium)
    assert 'skills' in options
    assert {'athletics', 'stealth'} <= {item.id for item in options['skills']}

    with tempfile.TemporaryDirectory() as temp_dir:
        character_root = Path(temp_dir) / 'characters'
        record = create_character(
            'test-user',
            pack.manifest.id,
            initial_data={
                'name': 'Reopen Test',
                'archetype': 'Adventurer',
                'background': 'traveler',
                'skills': ['athletics', 'stealth'],
            },
            character_root=character_root,
            pack_root=pack_root,
        )
        reopened = load_character(
            'test-user',
            record.character_id,
            character_root=character_root,
            pack_root=pack_root,
        )
        assert reopened.data['skills'] == ['athletics', 'stealth']
        selected = set(reopened.data['skills'])
        rendered_choices = {item.id for item in options['skills']}
        assert selected <= rendered_choices

    print('PASS: multi-reference reopen regression test')
    print('  saved skills persist: OK')
    print('  editor reloads skill choices: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
