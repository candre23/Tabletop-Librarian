#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Tabletop Librarian"
SERVICE_NAME="tabletop-librarian.service"
DEFAULT_INSTALL_DIR="/opt/tabletop-librarian"
DEFAULT_DATA_DIR="/var/lib/tabletop-librarian"
DEFAULT_CACHE_DIR="/var/cache/tabletop-librarian"
DEFAULT_LOG_DIR="/var/log/tabletop-librarian"
DEFAULT_ENV_FILE="/etc/tabletop-librarian.env"
DEFAULT_SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
DEFAULT_PORT=8080

INSTALL_DIR="${TTL_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
DATA_DIR="${TTL_DATA_DIR:-$DEFAULT_DATA_DIR}"
CACHE_DIR="${TTL_CACHE_DIR:-$DEFAULT_CACHE_DIR}"
LOG_DIR="${TTL_LOG_DIR:-$DEFAULT_LOG_DIR}"
ENV_FILE="${TTL_ENV_FILE:-$DEFAULT_ENV_FILE}"
SERVICE_FILE="${TTL_SERVICE_FILE:-$DEFAULT_SERVICE_FILE}"
PORT="${TTL_PORT:-}"
HOST="${TTL_HOST:-0.0.0.0}"
INSTALL_SERVICE="${TTL_INSTALL_SERVICE:-1}"
ASSUME_YES="${TTL_ASSUME_YES:-0}"
SKIP_OS_DEPS="${TTL_SKIP_OS_DEPS:-0}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD_DIR="$SOURCE_DIR/payload"
BACKUP_DIR=""

usage() {
  cat <<EOF
Usage: sudo ./install.sh [options]

Options:
  --port PORT          Server port (default: preserve existing, otherwise 8080)
  --host HOST          Bind address (default: 0.0.0.0)
  --no-service         Install files but do not create/start a systemd service
  --yes                Accept defaults without interactive prompts
  --help               Show this help

Environment overrides:
  TTL_INSTALL_DIR, TTL_DATA_DIR, TTL_CACHE_DIR, TTL_LOG_DIR
  TTL_PORT, TTL_HOST, TTL_INSTALL_SERVICE, TTL_SERVICE_USER
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="${2:?missing port}"; shift 2 ;;
    --host) HOST="${2:?missing host}"; shift 2 ;;
    --no-service) INSTALL_SERVICE=0; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: Run this installer as root, for example: sudo ./install.sh" >&2
  exit 1
fi

if [[ ! -d "$PAYLOAD_DIR/app" || ! -f "$PAYLOAD_DIR/pyproject.toml" ]]; then
  echo "ERROR: Release payload is incomplete." >&2
  exit 1
fi

existing_value() {
  local key="$1"
  if [[ -f "$ENV_FILE" ]]; then
    sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
  fi
}

if [[ -z "$PORT" ]]; then
  PORT="$(existing_value TTL_PORT)"
  PORT="${PORT:-$DEFAULT_PORT}"
fi

if [[ "$HOST" == "0.0.0.0" ]]; then
  old_host="$(existing_value TTL_HOST)"
  [[ -n "$old_host" ]] && HOST="$old_host"
fi

if [[ "$SKIP_OS_DEPS" != "1" ]]; then
  echo "Installing operating-system dependencies..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      python3 python3-venv python3-pip python3-dev \
      tesseract-ocr ocrmypdf ghostscript \
      7zip || {
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
          python3 python3-venv python3-pip python3-dev \
          tesseract-ocr ocrmypdf ghostscript p7zip-full
      }
    DEBIAN_FRONTEND=noninteractive apt-get install -y unrar 2>/dev/null || true
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 python3-pip python3-devel tesseract ghostscript || true
    dnf install -y ocrmypdf p7zip p7zip-plugins unrar || true
  else
    echo "ERROR: Automatic OS dependency installation currently supports apt or dnf." >&2
    exit 1
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3 is unavailable after dependency installation." >&2
  exit 1
fi

port_available() {
  python3 - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("0.0.0.0", port))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
raise SystemExit(0)
PY
}

valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( "$1" >= 1 && "$1" <= 65535 ))
}

next_free_port() {
  local candidate="${1:-$DEFAULT_PORT}"
  while (( candidate <= 65535 )); do
    if port_available "$candidate"; then
      echo "$candidate"
      return 0
    fi
    ((candidate++))
  done
  return 1
}

if ! valid_port "$PORT"; then
  echo "ERROR: Invalid port: $PORT" >&2
  exit 1
fi

# If this is an upgrade of a currently running TTL service, its own configured
# port will naturally be occupied. Preserve it instead of treating it as a conflict.
service_active=0
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
  service_active=1
fi
existing_port="$(existing_value TTL_PORT)"
if ! port_available "$PORT" && ! { [[ "$service_active" == "1" && "$PORT" == "$existing_port" ]]; }; then
  suggestion="$(next_free_port $((PORT + 1)))" || {
    echo "ERROR: No free TCP port found." >&2
    exit 1
  }
  if [[ "$ASSUME_YES" == "1" || ! -t 0 ]]; then
    echo "Port $PORT is already in use; using $suggestion instead."
    PORT="$suggestion"
  else
    echo "Port $PORT is already in use."
    read -r -p "Use available port $suggestion? [Y/n]: " answer
    case "${answer:-Y}" in
      [Nn]*)
        read -r -p "Enter TTL server port: " PORT
        valid_port "$PORT" && port_available "$PORT" || { echo "ERROR: Port unavailable." >&2; exit 1; }
        ;;
      *) PORT="$suggestion" ;;
    esac
  fi
fi

if [[ -n "${TTL_SERVICE_USER:-}" ]]; then
  SERVICE_USER="$TTL_SERVICE_USER"
elif [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
  SERVICE_USER="$SUDO_USER"
else
  SERVICE_USER="tabletop-librarian"
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
  fi
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "ERROR: Service user does not exist: $SERVICE_USER" >&2
  exit 1
fi
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

if [[ "$service_active" == "1" ]]; then
  echo "Stopping existing $SERVICE_NAME for upgrade..."
  systemctl stop "$SERVICE_NAME"
fi

rollback() {
  code=$?
  if [[ $code -ne 0 && -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]]; then
    echo "Installation failed; restoring previous application files..." >&2
    rm -rf "$INSTALL_DIR"
    mv "$BACKUP_DIR" "$INSTALL_DIR"
    if [[ "$service_active" == "1" ]]; then
      systemctl start "$SERVICE_NAME" 2>/dev/null || true
    fi
  fi
  exit $code
}
trap rollback EXIT

if [[ -d "$INSTALL_DIR" ]]; then
  BACKUP_DIR="${INSTALL_DIR}.previous.$(date +%Y%m%d%H%M%S)"
  mv "$INSTALL_DIR" "$BACKUP_DIR"
fi
mkdir -p "$INSTALL_DIR" "$DATA_DIR" "$CACHE_DIR" "$LOG_DIR"
cp -a "$PAYLOAD_DIR/app" "$PAYLOAD_DIR/pipelines" "$INSTALL_DIR/"
cp "$PAYLOAD_DIR/pyproject.toml" "$PAYLOAD_DIR/run.py" "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/docs"
cp -a "$PAYLOAD_DIR/data/system_packs" "$INSTALL_DIR/data/"
cp -a "$PAYLOAD_DIR/docs/reference" "$INSTALL_DIR/docs/"

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel

# TTL's current embedding pipeline uses OpenVINO on CPU. Install the official
# CPU-only PyTorch wheel first so pip does not pull an unusable CUDA/NCCL stack
# onto Intel/AMD CPU-only servers simply as a transitive dependency.
"$INSTALL_DIR/.venv/bin/python" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"$INSTALL_DIR/.venv/bin/python" -m pip install --no-build-isolation "$INSTALL_DIR"

mkdir -p "$DATA_DIR/system_packs" "$DATA_DIR/characters" "$CACHE_DIR" "$LOG_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR" "$CACHE_DIR" "$LOG_DIR"
chmod 0750 "$DATA_DIR" "$CACHE_DIR" "$LOG_DIR"

umask 022
cat > "$ENV_FILE" <<EOF
TTL_HOST=$HOST
TTL_PORT=$PORT
TTL_DATA_DIR=$DATA_DIR
TTL_CACHE_DIR=$CACHE_DIR
TTL_LOG_DIR=$LOG_DIR
EOF
chmod 0644 "$ENV_FILE"

if [[ "$INSTALL_SERVICE" == "1" ]]; then
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "ERROR: systemd is unavailable. Re-run with --no-service for a manual installation." >&2
    exit 1
  fi
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Tabletop Librarian Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/run.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME" >/dev/null
  systemctl start "$SERVICE_NAME"
fi

rm -rf "$BACKUP_DIR"
BACKUP_DIR=""
trap - EXIT

lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "$APP_NAME installation complete."
echo "Application: $INSTALL_DIR"
echo "Data:        $DATA_DIR"
echo "Cache:       $CACHE_DIR"
echo "Logs:        $LOG_DIR"
echo "Config:      $ENV_FILE"
echo "Server URL:  http://127.0.0.1:$PORT"
[[ -n "$lan_ip" ]] && echo "LAN URL:     http://$lan_ip:$PORT"
if [[ "$INSTALL_SERVICE" == "1" ]]; then
  echo "Service:     $SERVICE_NAME (running as $SERVICE_USER)"
else
  echo "Start manually with: sudo -u $SERVICE_USER env $(tr '\n' ' ' < "$ENV_FILE") $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/run.py"
fi
