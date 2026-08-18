from pathlib import Path


def test_initial_library_seeds_bundled_srd():
    text = (Path(__file__).resolve().parents[2] / "app" / "library" / "manager.py").read_text(encoding="utf-8")
    assert 'BUNDLED_SRD_FOLDER_NAME = "D20 SRD"' in text
    assert 'SRD_CC_v5.2.1.pdf' in text
    assert 'SRD_cover.jpg' in text
    assert 'save_manual_cover' in text
