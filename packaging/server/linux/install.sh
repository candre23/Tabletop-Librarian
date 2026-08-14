#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this installer as root (for example: sudo ./install.sh)." >&2
  exit 1
fi

PAYLOAD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
INSTALL_DIR="${TTL_INSTALL_DIR:-/opt/tabletop-librarian}"
DATA_DIR="${TTL_DATA_DIR:-/var/lib/tabletop-librarian}"
CACHE_DIR="${TTL_CACHE_DIR:-/var/cache/tabletop-librarian}"
LOG_DIR="${TTL_LOG_DIR:-/var/log/tabletop-librarian}"
ENV_FILE="/etc/tabletop-librarian.env"
SERVICE_FILE="/etc/systemd/system/tabletop-librarian.service"
SERVICE_USER="${TTL_SERVICE_USER:-tabletop-librarian}"
PORT="${TTL_PORT:-8080}"

port_in_use() {
  python3 - "$1" <<'PY'
import socket, sys
port=int(sys.argv[1])
s=socket.socket()
try:
    s.bind(('0.0.0.0', port))
except OSError:
    raise SystemExit(0)
else:
    s.close(); raise SystemExit(1)
PY
}

if port_in_use "$PORT"; then
  if [[ -t 0 ]]; then
    echo "Port $PORT is already in use."
    read -r -p "Choose a different TTL port [8082]: " reply
    PORT="${reply:-8082}"
  else
    echo "ERROR: Port $PORT is already in use. Set TTL_PORT to another port." >&2
    exit 1
  fi
fi

if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip tesseract-ocr ocrmypdf 7zip
  DEBIAN_FRONTEND=noninteractive apt-get install -y 7zip-rar || true
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 python3-pip tesseract ocrmypdf p7zip p7zip-plugins || true
else
  echo "ERROR: This installer currently supports apt- and dnf-based Linux systems." >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

mkdir -p "$INSTALL_DIR" "$DATA_DIR" "$CACHE_DIR" "$LOG_DIR"
rm -rf "$INSTALL_DIR/app" "$INSTALL_DIR/pipelines" "$INSTALL_DIR/data"
cp -a "$PAYLOAD_DIR/app" "$PAYLOAD_DIR/pipelines" "$INSTALL_DIR/"
cp "$PAYLOAD_DIR/pyproject.toml" "$PAYLOAD_DIR/run.py" "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/data"
cp -a "$PAYLOAD_DIR/data/system_packs" "$INSTALL_DIR/data/"

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$INSTALL_DIR/.venv/bin/python" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"$INSTALL_DIR/.venv/bin/python" -m pip install "$INSTALL_DIR"

chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" "$CACHE_DIR" "$LOG_DIR"
cat > "$ENV_FILE" <<EOF
TTL_HOST=0.0.0.0
TTL_PORT=$PORT
TTL_DATA_DIR=$DATA_DIR
TTL_CACHE_DIR=$CACHE_DIR
TTL_LOG_DIR=$LOG_DIR
EOF
chmod 0644 "$ENV_FILE"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Tabletop Librarian Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/run.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now tabletop-librarian.service

echo
echo "Tabletop Librarian installed."
echo "Server port: $PORT"
echo "Data: $DATA_DIR"
echo "Config: $ENV_FILE"
echo "Service: tabletop-librarian.service"
