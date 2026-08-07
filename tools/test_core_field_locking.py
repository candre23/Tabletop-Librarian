#!/usr/bin/env python3
from pathlib import Path
import json, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.characters.schema import load_character_schema
from app.creation import create_draft, load_draft, save_draft, load_creation_workflow
from app.system_packs import load_system_pack

def main():
    pack=load_system_pack(ROOT/'data/system_packs/ttl_test_minimal')
    assert pack.valid and pack.manifest
    schema,issues=load_character_schema(pack.root/pack.manifest.character_schema)
    assert schema is not None, [i.format() for i in issues]
    workflow,issues=load_creation_workflow(pack.root/pack.manifest.creation, schema=schema)
    assert workflow is not None, [i.format() for i in issues]
    assert workflow.steps[0].lock_after == ['background']
    assert workflow.steps[1].lock_after == ['archetype']
    assert workflow.core_field_ids() == ['background','archetype']
    with tempfile.TemporaryDirectory() as td:
        draft=create_draft('tester',pack.manifest.id,pack.manifest.version,schema.schema_version,draft_root=Path(td))
        assert draft.locked_fields == []
        draft.locked_fields.append('background'); save_draft(draft,draft_root=Path(td))
        reopened=load_draft('tester',draft.draft_id,draft_root=Path(td))
        assert reopened.locked_fields == ['background']
        # Backward compatibility: old drafts without locked_fields still load.
        payload=json.loads(reopened.path.read_text()); payload.pop('locked_fields',None); reopened.path.write_text(json.dumps(payload))
        legacy=load_draft('tester',draft.draft_id,draft_root=Path(td)); assert legacy.locked_fields == []
    create=(ROOT/'app/templates/characters/create.html').read_text()
    edit=(ROOT/'app/templates/characters/edit.html').read_text()
    web=(ROOT/'app/characters/web.py').read_text()
    assert 'Unlock Core Aspects' in create and 'Unlock Core Aspects' in edit
    assert 'field_id in core_fields and not unlock_core' in web
    assert 'return _render_character_edit_page' in web
    print('PASS: core-field locking regression test')
    print('  step lock declarations: OK')
    print('  persistent draft locks: OK')
    print('  legacy draft compatibility: OK')
    print('  post-creation soft lock UI: OK')
    print('  inline save-error rendering: OK')
    return 0
if __name__=='__main__': raise SystemExit(main())
