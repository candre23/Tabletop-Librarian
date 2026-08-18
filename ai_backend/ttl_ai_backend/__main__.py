from __future__ import annotations

import argparse

from .app import run
from .config import SettingsStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Tabletop Librarian Local AI Backend Manager")
    parser.add_argument("--start-server", action="store_true", help="open the manager and start the configured server")
    parser.add_argument("--set-port", type=int, metavar="PORT", help="set the backend listen port and exit")
    args = parser.parse_args()

    if args.set_port is not None:
        if not 1 <= args.set_port <= 65535:
            parser.error("--set-port must be between 1 and 65535")
        store = SettingsStore()
        settings = store.load()
        settings.port = args.set_port
        store.save(settings)
        return

    run(start_server=args.start_server)


if __name__ == "__main__":
    main()
