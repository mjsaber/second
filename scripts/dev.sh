#!/usr/bin/env bash
# scripts/dev.sh — Start the Tauri dev server with hot-reload.
set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info() { echo -e "${BLUE}[info]${NC}  $*"; }
ok()   { echo -e "${GREEN}[ok]${NC}    $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail() { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ---------------------------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Ensure PATH includes cargo
# ---------------------------------------------------------------------------
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# ---------------------------------------------------------------------------
# Quick sanity checks
# ---------------------------------------------------------------------------
if [ ! -d "node_modules" ]; then
    fail "node_modules not found. Run ./scripts/setup.sh first."
fi

if ! command -v cargo &>/dev/null; then
    fail "cargo not found. Run ./scripts/setup.sh first."
fi

if [ ! -f "src-tauri/Cargo.toml" ]; then
    fail "src-tauri/Cargo.toml not found. Are you in the right directory?"
fi

if [ ! -d "backend/.venv" ]; then
    warn "Python venv not found at backend/.venv — Python sidecar may not work."
    warn "Run ./scripts/setup.sh to create it."
fi

# ---------------------------------------------------------------------------
# Start the Tauri dev server
# ---------------------------------------------------------------------------
info "Starting Tauri dev server..."
info "  Frontend: http://localhost:1420 (Vite HMR)"
info "  Press Ctrl+C to stop."
echo ""

exec npx tauri dev
