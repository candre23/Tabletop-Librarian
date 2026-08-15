#!/usr/bin/env bash
set -euo pipefail

PREFIX="${TTL_AI_PREFIX:-$HOME/.local/opt/ttl-ai-backend}"
BIN_DIR="${TTL_AI_BIN_DIR:-$HOME/.local/bin}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/tabletop-librarian-ai"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/tabletop-librarian-ai"
PURGE_DATA=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge-data) PURGE_DATA=1; shift ;;
    --help|-h)
      echo "Usage: ./uninstall.sh [--purge-data]"
      echo "By default downloaded models, llama.cpp runtimes, and settings are preserved."
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

rm -rf "$PREFIX"
rm -f "$BIN_DIR/ttl-ai-backend" "$DESKTOP_DIR/tabletop-librarian-ai.desktop"
rm -f "$HOME/.config/autostart/tabletop-librarian-ai.desktop"

if [[ "$PURGE_DATA" == "1" ]]; then
  rm -rf "$CONFIG_DIR" "$DATA_DIR"
  echo "TTL AI Backend removed, including settings, runtimes, and downloaded models."
else
  echo "TTL AI Backend removed. Settings, runtimes, and downloaded models were preserved."
fi
