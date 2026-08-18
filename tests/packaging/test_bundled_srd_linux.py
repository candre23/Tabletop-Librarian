from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_linux_release_payload_contains_srd_reference_directory():
    text = (ROOT / "packaging/linux/build_releases.py").read_text(encoding="utf-8")
    assert '"docs/reference"' in text


def test_linux_installer_copies_srd_reference_directory():
    text = (ROOT / "packaging/server/linux/install.sh").read_text(encoding="utf-8")
    assert 'cp -a "$PAYLOAD_DIR/docs/reference" "$INSTALL_DIR/docs/"' in text


def test_library_seeder_uses_installed_reference_path():
    text = (ROOT / "app/library/manager.py").read_text(encoding="utf-8")
    assert 'RESOURCE_ROOT / "docs" / "reference" / "SRD_CC_v5.2.1.pdf"' in text
    assert 'RESOURCE_ROOT / "docs" / "reference" / "SRD_cover.jpg"' in text
