#!/usr/bin/env bash
set -euo pipefail

PREFIX="${TTL_AI_PREFIX:-$HOME/.local/opt/ttl-ai-backend}"
BIN_DIR="${TTL_AI_BIN_DIR:-$HOME/.local/bin}"
APP_DIR="$PREFIX/app"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD_DIR="$SOURCE_DIR/payload/ai_backend"

if [[ ${EUID:-$(id -u)} -eq 0 && -z "${TTL_AI_ALLOW_ROOT:-}" ]]; then
  echo "ERROR: Install the TTL AI Backend as the desktop user, not with sudo." >&2
  exit 1
fi

if [[ ! -d "$PAYLOAD_DIR/ttl_ai_backend" ]]; then
  echo "ERROR: Backend release payload is incomplete." >&2
  exit 1
fi

install_os_deps() {
  if command -v python3 >/dev/null 2>&1 && python3 - <<'PY' >/dev/null 2>&1
import tkinter
PY
  then
    return 0
  fi

  echo "Python/Tkinter is required for the Backend Manager."
  if command -v apt-get >/dev/null 2>&1; then
    echo "Installing with sudo apt..."
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-tk pciutils
  elif command -v dnf >/dev/null 2>&1; then
    echo "Installing with sudo dnf..."
    sudo dnf install -y python3 python3-tkinter pciutils
  else
    echo "ERROR: Install Python 3 with Tkinter, then rerun this installer." >&2
    return 1
  fi
}

install_os_deps

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"
cp -a "$PAYLOAD_DIR/ttl_ai_backend" "$APP_DIR/"
if [[ -d "$SOURCE_DIR/documentation" ]]; then
  cp -a "$SOURCE_DIR/documentation" "$PREFIX/"
fi

cat > "$BIN_DIR/ttl-ai-backend" <<EOF
#!/usr/bin/env bash
export TTL_AI_LAUNCHER="$BIN_DIR/ttl-ai-backend"
exec python3 -m ttl_ai_backend "\$@"
EOF
# Put the private application directory on sys.path without requiring pip/venv.
python3 - "$BIN_DIR/ttl-ai-backend" "$APP_DIR" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
app = sys.argv[2]
text = p.read_text()
text = text.replace('exec python3 -m ttl_ai_backend', f'exec env PYTHONPATH="{app}" python3 -m ttl_ai_backend')
p.write_text(text)
PY
chmod 0755 "$BIN_DIR/ttl-ai-backend"

cat > "$DESKTOP_DIR/tabletop-librarian-ai.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TTL AI Backend
Comment=Local llama.cpp backend manager for Tabletop Librarian
Exec=$BIN_DIR/ttl-ai-backend
Terminal=false
Categories=Utility;
StartupNotify=true
EOF
chmod 0644 "$DESKTOP_DIR/tabletop-librarian-ai.desktop"

echo
echo "TTL AI Backend installed independently."
echo "Application: $PREFIX"
echo "Launcher:    $BIN_DIR/ttl-ai-backend"
echo "The Manager will install the selected llama.cpp runtime and models on demand."
echo "If $BIN_DIR is not on PATH, launch it by its full path or from your application menu."
