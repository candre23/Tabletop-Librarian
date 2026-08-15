#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${TTL_INSTALL_DIR:-/opt/tabletop-librarian}"
DATA_DIR="${TTL_DATA_DIR:-/var/lib/tabletop-librarian}"
CACHE_DIR="${TTL_CACHE_DIR:-/var/cache/tabletop-librarian}"
LOG_DIR="${TTL_LOG_DIR:-/var/log/tabletop-librarian}"
ENV_FILE="${TTL_ENV_FILE:-/etc/tabletop-librarian.env}"
SERVICE_FILE="${TTL_SERVICE_FILE:-/etc/systemd/system/tabletop-librarian.service}"
SERVICE_NAME="tabletop-librarian.service"
PURGE_DATA=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge-data) PURGE_DATA=1; shift ;;
    --help|-h)
      echo "Usage: sudo ./uninstall.sh [--purge-data]"
      echo "By default user data under $DATA_DIR is preserved."
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: Run as root, for example: sudo ./uninstall.sh" >&2
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
fi
rm -f "$SERVICE_FILE"
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
fi
rm -rf "$INSTALL_DIR" "$CACHE_DIR" "$LOG_DIR"
rm -f "$ENV_FILE"

if [[ "$PURGE_DATA" == "1" ]]; then
  rm -rf "$DATA_DIR"
  echo "Tabletop Librarian removed, including user data."
else
  echo "Tabletop Librarian removed. User data was preserved at: $DATA_DIR"
fi
