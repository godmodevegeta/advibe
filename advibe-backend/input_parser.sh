#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
Usage: input_parser.sh -p "free-text brand brief"

Extract structured seed signals from a brand brief using user_input.py.

Options:
  -p PROMPT   Brand brief to parse (required; quote multi-word prompts)
  -h          Show this help message

When references are sparse, the parser infers culturally coherent seeds and
1-2 mainstream competitors automatically.

Examples:
  ./input_parser.sh -p "Canned Ceremonial Matcha Energy drink brand called Chaen. Similar vibe to Chamberlain Coffee and Erewhon. Target city: New York, NY. Compare against Red Bull."
  ./input_parser.sh -p "Canned Ceremonial Matcha Energy drink brand called Chaen. Similar vibe to Chamberlain Coffee and Erewhon. Target city: New York, NY."
  ./input_parser.sh -p "I own Jungsik in NYC, I want an ad for a new line of makgeolli we're launching, it's high luxury."
  ./input_parser.sh -p "Sustainable streetwear label for Berlin, inspired by Patagonia."
EOF
}

prompt=""
while getopts ":p:h" opt; do
    case "$opt" in
        p)
            prompt="$OPTARG"
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

python3 - "$prompt" <<'PY'
import sys
from pprint import pprint

from user_input import SeedExtractionError, extract_seed_signals

try:
    result = extract_seed_signals(sys.argv[1])
except SeedExtractionError as exc:
    print(f"error: {exc}", file=sys.stderr)
    raise SystemExit(1)

pprint(result, sort_dicts=False)
PY
