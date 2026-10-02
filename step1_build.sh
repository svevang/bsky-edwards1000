#!/usr/bin/env bash
# Step 1 (automated): download -> parse -> Wikipedia descriptions -> movies.csv.
# Every stage writes stages/NN_*.json and only processes new/changed rows, so you can
# stop after any stage, inspect, fix, and continue.
#
# Usage: ./step1_build.sh [--skip-download] [stage args...]
#   stage args (passed to every stage): --force | --redo N,N | --only N,N | --limit K
#   e.g. ./step1_build.sh --skip-download --redo 75      # redo one film end-to-end
#        ./step1_build.sh --skip-download --limit 20     # process 20 rows, then look
# Inspect: uv run python status.py        (counts per stage)
#          uv run python status.py 75     (full trail for film #75)
set -euo pipefail
cd "$(dirname "$0")"

HANDLE="${BSKY_HANDLE:-did:plc:uidrgvgtx2nbdb2mkhiacpus}"
TAG="Edwards1000SixtiesMovies"
hr() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

if [[ "${1:-}" == "--skip-download" ]]; then shift; hr "0: download skipped"
else hr "0: downloading #$TAG posts -> stages/00_posts.json"; uv run python bsky_tag_dl.py "$HANDLE" "$TAG" stages/00_posts.json; fi

hr "1: parse titles/years -> stages/01_parsed.json";        uv run python s1_parse.py "$@"
hr "2: Wikipedia descriptions -> stages/02_descriptions.json"; uv run python s2_descriptions.py "$@"
hr "4: join -> movies.csv";                                  uv run python s4_join.py

cat <<'TXT'

Check:  uv run python status.py              # counts per stage
        uv run python status.py <number>     # one film's trail through every stage
        column -s, -t < movies.csv | less -S
Fix:    ./fix.py <number> title "..." | year YYYY | page "Wikipedia Title" | unpin
        (pins the fix and reruns just that row; ./fix.py -h for details)
Next:   ./step2_llm_review.sh          # LLM pass over rows not yet reviewed
TXT
