from __future__ import annotations

import argparse

from .app import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Tabletop Librarian Local AI Backend Manager")
    parser.add_argument("--start-server", action="store_true", help="open the manager and start the configured server")
    args = parser.parse_args()
    run(start_server=args.start_server)


if __name__ == "__main__":
    main()
