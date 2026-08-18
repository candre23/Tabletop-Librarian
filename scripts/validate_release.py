#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.0.0"
EXPECTED_PACKS = {"generic_d20"}
REQUIRED_DOCS = {
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/INSTALLATION.md",
    "docs/USER_GUIDE.md",
    "docs/AI_BACKEND.md",
    "docs/SYSTEM_PACKS.md",
    "docs/PIPELINES.md",
    "docs/OCR.md",
    "docs/DEVELOPMENT.md",
    "docs/BUILDING_RELEASES.md",
    "docs/RELEASE_CHECKLIST.md",
    "docs/reference/SRD_CC_v5.2.1.pdf",
    "docs/reference/SRD_5.2_cover.png",
}


def project_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Unable to find version in {path}")
    return match.group(1)


def fail(message: str, problems: list[str]) -> None:
    problems.append(message)


def main() -> int:
    problems: list[str] = []

    server_version = project_version(ROOT / "pyproject.toml")
    backend_version = project_version(ROOT / "ai_backend" / "pyproject.toml")
    if server_version != EXPECTED_VERSION:
        fail(f"Server version is {server_version}, expected {EXPECTED_VERSION}", problems)
    if backend_version != EXPECTED_VERSION:
        fail(f"AI Backend version is {backend_version}, expected {EXPECTED_VERSION}", problems)

    config_text = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    if f'APP_VERSION = "{EXPECTED_VERSION}"' not in config_text:
        fail("app/config.py APP_VERSION is not synchronized", problems)

    pack_root = ROOT / "data" / "system_packs"
    packs = {path.name for path in pack_root.iterdir() if path.is_dir()} if pack_root.is_dir() else set()
    if packs != EXPECTED_PACKS:
        fail(f"Bundled System Packs are {sorted(packs)}, expected {sorted(EXPECTED_PACKS)}", problems)

    favicon = ROOT / "app" / "static" / "favicon.png"
    if not favicon.is_file():
        fail("app/static/favicon.png is missing", problems)
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    if "favicon.png" not in base:
        fail("base.html does not reference favicon.png", problems)

    for rel in sorted(REQUIRED_DOCS):
        if not (ROOT / rel).is_file():
            fail(f"Required release/documentation file missing: {rel}", problems)

    obsolete = [
        ROOT / "BUNDLE_INFO.txt",
        ROOT / "PROJECT_TREE.txt",
        ROOT / "OCR_WORKFLOW.md",
        ROOT / "PIPELINE_PRESETS.md",
        ROOT / "system_packs_spec_v1.md",
    ]
    for path in obsolete:
        if path.exists():
            fail(f"Obsolete/generated root file remains: {path.name}", problems)

    # Release packaging must not contain historical beta/test pack exclusions.
    for rel in (
        "app/runtime.py",
        "packaging/linux/build_releases.py",
        "packaging/server/windows/build.ps1",
        "packaging/server/windows/installer.iss",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "framework2_demo" in text or "ttl_test_minimal" in text:
            fail(f"Historical development System Pack reference remains in {rel}", problems)

    # Test fixture belongs outside release data.
    fixture = ROOT / "tests" / "fixtures" / "system_packs" / "ttl_test_minimal" / "manifest.yaml"
    if not fixture.is_file():
        fail("Test-only minimal System Pack fixture is missing", problems)

    if problems:
        print("Release validation FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("Release validation PASS")
    print(f"  Server: {server_version}")
    print(f"  AI Backend: {backend_version}")
    print(f"  Bundled System Packs: {', '.join(sorted(packs))}")
    print("  Favicon: present")
    print("  Documentation/licenses: present")
    print("  Test fixture isolation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
