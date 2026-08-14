from __future__ import annotations

import os
import tempfile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        os.environ["TTL_DATA_DIR"] = str(root / "data")
        os.environ["TTL_CACHE_DIR"] = str(root / "cache")
        os.environ["TTL_LOG_DIR"] = str(root / "logs")
        os.environ["TTL_PORT"] = "18080"

        from app import config

        assert config.DATA_DIR == root / "data"
        assert config.CACHE_DIR == root / "cache"
        assert config.LOG_DIR == root / "logs"
        assert config.APP_PORT == 18080
        assert config.TEMPLATE_DIR.is_dir()
        assert config.STATIC_DIR.is_dir()
        print("PASS: relocatable server packaging configuration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
