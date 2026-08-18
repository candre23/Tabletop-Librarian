from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compendium_loader_uses_file_fingerprint_cache():
    text = (ROOT / 'app/compendium/loader.py').read_text(encoding='utf-8')
    assert '@lru_cache(maxsize=32)' in text
    assert '_compendium_fingerprint' in text


def test_system_pack_loader_uses_runtime_cache():
    text = (ROOT / 'app/system_packs/loader.py').read_text(encoding='utf-8')
    assert '_system_pack_fingerprint' in text
    assert '_load_system_pack_cached' in text


def test_rule_parser_and_engine_are_cached():
    text = (ROOT / 'app/rules/engine.py').read_text(encoding='utf-8')
    assert '@lru_cache(maxsize=4096)\ndef _parse' in text
    assert '_load_rule_engine_cached' in text


def test_creation_owns_cross_step_visibility_and_static_js_is_content_versioned():
    create = (ROOT / 'app/templates/characters/create.html').read_text(encoding='utf-8')
    widgets = (ROOT / 'app/static/js/pack_widgets.js').read_text(encoding='utf-8')
    web = (ROOT / 'app/characters/web.py').read_text(encoding='utf-8')

    assert 'window.ttlCreationPageOwnsVisibility = true;' in create
    assert 'if (window.ttlCreationPageOwnsVisibility) return;' in widgets
    assert 'pack_widgets_version' in web
    assert 'pack_widgets.js?v={{ pack_widgets_version }}' in create
