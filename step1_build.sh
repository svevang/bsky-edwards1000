#!/usr/bin/env bash
# Step 1 (automated): download -> Wikipedia descriptions -> movies.csv.
# Every stage writes one file per post under entries/<rkey>/ and only processes
# new/changed rows, so you can stop after any stage, inspect, fix, and continue.
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
else hr "0: downloading #$TAG posts -> entries/*/post.yaml"; uv run python s0_download.py "$HANDLE" "$TAG"; fi

hr "1: Wikipedia descriptions -> entries/*/wikipedia.yaml"; uv run python s2_descriptions.py "$@"
hr "2: render -> movies.csv";                               uv run python render.py

cat <<'TXT'

Check:  uv run python status.py              # counts by status
        uv run python status.py <number>     # one film's files, overrides and freshness
        column -s, -t < movies.csv | less -S
Fix:    ./fix.py <number> title "..." | year YYYY | page "Wikipedia Title" | unset [KEY ...]
        (sets an override and reruns just that row; ./fix.py -h for details)
Next:   ./step2_llm_review.sh          # LLM pass over rows not yet reviewed
TXT
