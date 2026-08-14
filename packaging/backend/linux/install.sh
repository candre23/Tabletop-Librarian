#!/usr/bin/env bash
set -euo pipefail

PREFIX="${TTL_AI_PREFIX:-$HOME/.local/opt/ttl-ai-backend}"
BIN_DIR="${TTL_AI_BIN_DIR:-$HOME/.local/bin}"
SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../ai_backend" && pwd)"

mkdir -p "$PREFIX" "$BIN_DIR"
python3 -m venv "$PREFIX/.venv"
"$PREFIX/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$PREFIX/.venv/bin/python" -m pip install "$SOURCE_ROOT"
cat > "$BIN_DIR/ttl-ai-backend" <<EOF
#!/usr/bin/env bash
exec "$PREFIX/.venv/bin/python" -m ttl_ai_backend "\$@"
EOF
chmod +x "$BIN_DIR/ttl-ai-backend"

echo "TTL AI Backend installed independently at $PREFIX"
echo "Launch with: $BIN_DIR/ttl-ai-backend"
echo "The Manager will install the appropriate llama.cpp runtime and models on first use."
