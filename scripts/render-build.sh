#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python -m pip install -r advibe-backend/requirements.txt
npm --prefix advibe-frontend ci
npm --prefix advibe-frontend run build
test -f advibe-frontend/dist/index.html
