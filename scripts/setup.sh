#!/usr/bin/env bash
# scripts/setup.sh — One-time setup for the Second project on macOS.
# Safe to run multiple times (idempotent).
set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Colour

info()    { echo -e "${BLUE}[info]${NC}  $*"; }
ok()      { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }
section() { echo -e "\n${BOLD}=== $* ===${NC}"; }

# ---------------------------------------------------------------------------
# Resolve project root (directory that contains package.json)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
info "Project root: $PROJECT_ROOT"

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------
section "Checking prerequisites"

# --- Xcode Command Line Tools ---
if xcode-select -p &>/dev/null; then
    ok "Xcode Command Line Tools installed at $(xcode-select -p)"
else
    warn "Xcode Command Line Tools not found. Installing..."
    echo "  This may require sudo and will open a system dialog."
    xcode-select --install 2>/dev/null || true
    echo ""
    echo "  After the installation finishes, re-run this script."
    exit 1
fi

# --- Homebrew ---
if command -v brew &>/dev/null; then
    ok "Homebrew found: $(brew --prefix)"
else
    fail "Homebrew is not installed. Install it from https://brew.sh"
fi

# --- Node.js ---
MINIMUM_NODE=18
if command -v node &>/dev/null; then
    NODE_VERSION=$(node -v | sed 's/^v//' | cut -d. -f1)
    if [ "$NODE_VERSION" -ge "$MINIMUM_NODE" ]; then
        ok "Node.js $(node -v)"
    else
        fail "Node.js >= $MINIMUM_NODE required, found $(node -v). Run: brew install node"
    fi
else
    fail "Node.js is not installed. Run: brew install node"
fi

# --- npm ---
if command -v npm &>/dev/null; then
    ok "npm $(npm -v)"
else
    fail "npm is not installed (comes with Node). Run: brew install node"
fi

# --- Rust (via rustup) ---
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if command -v rustup &>/dev/null; then
    ok "rustup found: $(rustup --version 2>/dev/null | head -1)"
else
    warn "Rust is not installed. Installing via rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
    source "$HOME/.cargo/env"
    ok "Rust installed: $(rustc --version)"
fi

if command -v cargo &>/dev/null; then
    ok "cargo $(cargo --version | awk '{print $2}')"
else
    fail "cargo not found on PATH. Ensure \$HOME/.cargo/bin is in your PATH."
fi

if command -v rustc &>/dev/null; then
    ok "rustc $(rustc --version | awk '{print $2}')"
else
    fail "rustc not found on PATH."
fi

# Make sure we have the correct host target (arm or x86)
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    TARGET="aarch64-apple-darwin"
else
    TARGET="x86_64-apple-darwin"
fi
if rustup target list --installed | grep -q "$TARGET"; then
    ok "Rust target $TARGET installed"
else
    info "Adding Rust target $TARGET..."
    rustup target add "$TARGET"
    ok "Rust target $TARGET added"
fi

# --- Python ---
MINIMUM_PYTHON_MINOR=11
PYTHON_CMD=""

# Prefer python3.13 from Homebrew
if command -v python3.13 &>/dev/null; then
    PYTHON_CMD="python3.13"
elif command -v python3.12 &>/dev/null; then
    PYTHON_CMD="python3.12"
elif command -v python3.11 &>/dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &>/dev/null; then
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [ "$PY_MINOR" -ge "$MINIMUM_PYTHON_MINOR" ]; then
        PYTHON_CMD="python3"
    fi
fi

if [ -n "$PYTHON_CMD" ]; then
    PY_VERSION=$($PYTHON_CMD --version 2>&1)
    ok "Python: $PY_VERSION (using $PYTHON_CMD)"
else
    fail "Python >= 3.$MINIMUM_PYTHON_MINOR not found. Run: brew install python@3.13"
fi

# ---------------------------------------------------------------------------
# 2. Install project dependencies
# ---------------------------------------------------------------------------
section "Installing project dependencies"

# --- npm ---
info "Installing Node dependencies..."
npm install
ok "npm install complete"

# --- Tauri CLI ---
if npx tauri --version &>/dev/null; then
    ok "Tauri CLI $(npx tauri --version)"
else
    info "Installing @tauri-apps/cli..."
    npm install --save-dev @tauri-apps/cli
    ok "Tauri CLI installed"
fi

# --- Python virtualenv ---
VENV_DIR="$PROJECT_ROOT/backend/.venv"
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    VENV_PY_VERSION=$("$VENV_DIR/bin/python" --version 2>&1)
    ok "Python venv exists: $VENV_PY_VERSION ($VENV_DIR)"
else
    info "Creating Python venv at $VENV_DIR using $PYTHON_CMD..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    ok "Python venv created"
fi

# --- Python deps ---
info "Installing Python dependencies from backend/requirements.txt..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip --quiet
"$VENV_DIR/bin/python" -m pip install -r "$PROJECT_ROOT/backend/requirements.txt" --quiet
ok "Python dependencies installed"

# ---------------------------------------------------------------------------
# 3. Verify everything
# ---------------------------------------------------------------------------
section "Running verification checks"

ERRORS=0

# --- cargo check ---
info "Running cargo check in src-tauri/..."
if (cd "$PROJECT_ROOT/src-tauri" && cargo check 2>&1); then
    ok "cargo check passed"
else
    warn "cargo check failed"
    ERRORS=$((ERRORS + 1))
fi

# --- cargo test ---
info "Running cargo test in src-tauri/..."
if (cd "$PROJECT_ROOT/src-tauri" && cargo test 2>&1); then
    ok "cargo test passed"
else
    warn "cargo test failed"
    ERRORS=$((ERRORS + 1))
fi

# --- svelte-check ---
info "Running svelte-check..."
if npx svelte-check --tsconfig "$PROJECT_ROOT/tsconfig.json" 2>&1; then
    ok "svelte-check passed"
else
    warn "svelte-check had warnings or errors (non-fatal)"
    # Don't count as error since svelte-check can be noisy with warnings
fi

# --- Python tests ---
info "Running Python tests..."
if "$VENV_DIR/bin/python" -m pytest "$PROJECT_ROOT/backend/tests/" -v 2>&1; then
    ok "Python tests passed"
else
    warn "Python tests failed"
    ERRORS=$((ERRORS + 1))
fi

# ---------------------------------------------------------------------------
# 4. Summary
# ---------------------------------------------------------------------------
section "Setup complete"

if [ "$ERRORS" -gt 0 ]; then
    warn "$ERRORS verification step(s) had issues. Check the output above."
    echo ""
    echo -e "  The project is set up, but some checks failed."
    echo -e "  You can still start development — see the warnings above."
else
    ok "All checks passed!"
fi

echo ""
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo "  Start the dev server (Tauri + Vite hot-reload):"
echo "    ./scripts/dev.sh"
echo ""
echo "  Build a release .app bundle:"
echo "    npm run tauri build"
echo ""
echo "  Run all linters and tests:"
echo "    ./scripts/check.sh"
echo ""
echo "  Activate the Python venv for backend work:"
echo "    source backend/.venv/bin/activate"
echo ""
