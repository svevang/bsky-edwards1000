#!/usr/bin/env bash
# Step 2 (LLM in the loop): Claude reads each row and flags title/year/description
# disagreements -> entries/*/review.yaml, then movies.csv is rebuilt with the flags.
# Uses the `claude` CLI (your login; no API key). Only rows not yet reviewed, or whose
# inputs changed, are sent.
#
# Usage: ./step2_llm_review.sh [--force | --redo N,N | --only N,N | --limit K]
set -euo pipefail
cd "$(dirname "$0")"
command -v claude >/dev/null || { echo "claude CLI not found"; exit 1; }

uv run python s3_llm_review.py "$@"
uv run python render.py

cat <<'TXT'

For each flagged row: uv run python status.py <number> to see its trail, then either
  - ./fix.py <number> title "..."   (or: year YYYY)
  - ./fix.py <number> page "Right Wikipedia Title"
  - ./fix.py <number> dismiss "why it's fine"
  (./fix.py <number> unset [KEY ...] undoes a fix)
then ./step2_llm_review.sh to re-review the rows you changed
TXT
