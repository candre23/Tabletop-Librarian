from __future__ import annotations

import shutil

from app.config import BUNDLED_SYSTEM_PACKS_DIR, SYSTEM_PACKS_DIR



def seed_bundled_system_packs() -> None:
    """Seed bundled System Packs into writable data storage without overwriting user copies."""
    if not BUNDLED_SYSTEM_PACKS_DIR.is_dir():
        return
    SYSTEM_PACKS_DIR.mkdir(parents=True, exist_ok=True)
    for source in BUNDLED_SYSTEM_PACKS_DIR.iterdir():
        if not source.is_dir():
            continue
        target = SYSTEM_PACKS_DIR / source.name
        if not target.exists():
            shutil.copytree(source, target)
