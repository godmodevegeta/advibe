#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
Usage: resolve_signals.sh [-j] -p "free-text brand brief"

Extract seed signals from a brief, then resolve them into Qloo entity IDs and
tag URNs. You may also pass a JSON object matching the extract_seed_signals()
schema to skip extraction and resolve it directly.

Options:
  -p INPUT     Brand brief, or a JSON signals object (required; quote it)
  -j, --json   Print the resolved result as JSON instead of Python pprint
  -h           Show this help message

Examples:
  ./resolve_signals.sh -p "Build an Austin, Texas campaign for 'Humo Santo', our new artisanal Espadín mezcal made for tech founders, poker nights, and vinyl lounges. Think the vibe of Casamigos meets Soho House and Khruangbin, going head-to-head against Don Julio."
  ./resolve_signals.sh -j -p "Build an Austin, Texas campaign for 'Humo Santo'" > resolved.json
  ./resolve_signals.sh --json -p "Build an Austin, Texas campaign for 'Humo Santo'" > resolved.json
  ./resolve_signals.sh -p '{"brand_name": "Humo Santo", "seed_brands": ["Casamigos", "Soho House", "Khruangbin"], "competitor_brands": ["Don Julio"], "seed_tags": ["mezcal", "artisanal mezcal", "espadín", "tech founders", "poker nights", "vinyl lounges"], "location": "Austin, Texas", "location_query": "Austin, TX"}'
EOF
}

# getopts does not support long options. Normalize --json to -j.
normalized=()
for arg in "$@"; do
    if [[ "$arg" == "--json" ]]; then
        normalized+=("-j")
    else
        normalized+=("$arg")
    fi
done
set -- "${normalized[@]}"

prompt=""
json_mode=0
while getopts ":p:hj" opt; do
    case "$opt" in
        p)
            prompt="$OPTARG"
            ;;
        j)
            json_mode=1
            ;;
        h)
            usage
            exit 0
            ;;
        :)
            echo "error: option -$OPTARG requires an argument" >&2
            usage >&2
            exit 2
            ;;
        \?)
            echo "error: unknown option -$OPTARG" >&2
            usage >&2
            exit 2
            ;;
    esac
done
shift $((OPTIND - 1))

if (( $# > 0 )); then
    echo "error: unexpected argument(s): $*" >&2
    usage >&2
    exit 2
fi

if [[ -z "$prompt" ]]; then
    echo "error: -p requires a non-empty prompt" >&2
    usage >&2
    exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 is required but was not found" >&2
    exit 1
fi

cd -- "$SCRIPT_DIR"

python3 - "$prompt" "$json_mode" <<'PY'
import json
import sys
from pprint import pprint

from resolve_signals import (
    QlooResolutionError,
    ResolutionJudgeError,
    load_qloo_api_key,
    resolve_signals,
)
from user_input import SeedExtractionError, extract_seed_signals

raw = sys.argv[1]
json_mode = sys.argv[2] == "1"
try:
    parsed = json.loads(raw)
except json.JSONDecodeError:
    parsed = None

try:
    if isinstance(parsed, dict):
        extracted = parsed
    else:
        extracted = extract_seed_signals(raw)
    result = resolve_signals(extracted, load_qloo_api_key())
except (SeedExtractionError, QlooResolutionError, ResolutionJudgeError) as exc:
    print(f"error: {exc}", file=sys.stderr)
    raise SystemExit(1)

if json_mode:
    print(json.dumps(result, indent=2, ensure_ascii=False))
else:
    pprint(result, sort_dicts=False)
PY
