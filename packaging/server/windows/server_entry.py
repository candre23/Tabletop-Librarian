from __future__ import annotations

import configparser
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn


def _program_data_root() -> Path:
    root = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return Path(root) / "Tabletop Librarian"


def _load_installed_environment() -> tuple[str, int, Path, Path]:
    root = _program_data_root()
    data_dir = root / "data"
    cache_dir = root / "cache"
    log_dir = root / "logs"
    config_path = root / "server.ini"

    parser = configparser.ConfigParser()
    if config_path.is_file():
        parser.read(config_path, encoding="utf-8")

    host = parser.get("server", "host", fallback="0.0.0.0").strip() or "0.0.0.0"
    try:
        port = parser.getint("server", "port", fallback=8080)
    except ValueError:
        port = 8080
    if not 1 <= port <= 65535:
        port = 8080

    for path in (data_dir, cache_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)

    os.environ["TTL_DATA_DIR"] = str(data_dir)
    os.environ["TTL_CACHE_DIR"] = str(cache_dir)
    os.environ["TTL_LOG_DIR"] = str(log_dir)
    os.environ["TTL_HOST"] = host
    os.environ["TTL_PORT"] = str(port)
    return host, port, log_dir / "server.log", root / "server.pid"


def _configure_logging(log_file: Path) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def main() -> int:
    host, port, log_file, pid_file = _load_installed_environment()
    _configure_logging(log_file)

    pid_file.write_text(str(os.getpid()), encoding="ascii")

    # Import only after the installer-controlled environment is established.
    # Import the ASGI application object directly so PyInstaller can discover
    # app.main and its dependency graph during static analysis. Passing
    # "app.main:app" as a string works in source installs but is invisible to
    # PyInstaller's module scanner.
    from app.config import APP_NAME, APP_VERSION
    from app.main import app as asgi_app

    logging.getLogger(__name__).info(
        "Starting %s v%s on %s:%s",
        APP_NAME,
        APP_VERSION,
        host,
        port,
    )
    try:
        uvicorn.run(
            asgi_app,
            host=host,
            port=port,
            reload=False,
            access_log=True,
            log_config=None,
        )
    except Exception:
        logging.getLogger(__name__).exception("TTL Server terminated unexpectedly")
        return 1
    finally:
        try:
            if pid_file.is_file() and pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
                pid_file.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
