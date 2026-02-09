#!/usr/bin/env bash
set -euo pipefail

echo "=== Python checks ==="
cd backend
ruff check .
ruff format --check .
python -m pytest tests/ -v
cd ..

echo "=== Rust checks ==="
cd src-tauri
source "$HOME/.cargo/env" 2>/dev/null || true
cargo fmt --check
cargo clippy -- -D warnings
cargo test
cd ..

echo "=== Frontend checks ==="
npm run build

echo "=== All checks passed ==="
