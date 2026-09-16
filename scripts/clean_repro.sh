#!/bin/bash
# Clean-room reproduction: fresh clone -> build -> full verification.
# Usage: scripts/clean_repro.sh [/tmp/rg-repro]
set -euo pipefail
DEST="${1:-/tmp/rg-repro}"
REPO="$(git rev-parse --show-toplevel)"
REV="$(git rev-parse HEAD)"
rm -rf "$DEST"
git clone -q "$REPO" "$DEST"
cd "$DEST"
git checkout -q "$REV"
cp .env.example .env
export RG_QUIET=1
uv sync --extra dev
uv run ruff check .
uv run pytest -q
uv run python evals/runner/run.py --tiers 1
uv run python evals/judges/judges.py
uv run python scripts/quality_gates.py
echo "CLEAN REPRO PASS @ $REV"
