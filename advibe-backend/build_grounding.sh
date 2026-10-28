#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 is required but was not found" >&2
    exit 1
fi

cd -- "$SCRIPT_DIR"

exec python3 build_grounding.py "$@"
