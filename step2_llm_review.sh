#!/usr/bin/env bash
# Step 2 (LLM in the loop): Claude reads each row and flags title/year/description
# disagreements -> entries/*/review.yaml, and fixes what it can: a checked Wikipedia page,
# or a title/year it is certain of, goes to entries/*/override.yaml; those rows are refetched
# and reviewed again (up to two more rounds). Then movies.csv is rebuilt with the flags.
# Uses the `claude` CLI (your login; no API key). Only rows not yet reviewed, or whose
# inputs changed, are sent.
#
# Usage: ./step2_llm_review.sh [--force | --redo N,N | --only N,N | --limit K]   (N: number or rkey)
set -euo pipefail
cd "$(dirname "$0")"
command -v claude >/dev/null || { echo "claude CLI not found"; exit 1; }

uv run python s2_descriptions.py  # catch-up: refetch pages a fix left stale; a no-op otherwise
uv run python s3_llm_review.py "$@"
uv run python render.py

cat <<'TXT'

Fixes the review made are listed above and in the `overrides` column; ./fix.py <N|rkey> unset KEY
undoes one. For each row still flagged: uv run python status.py <N|rkey> to see its trail, then either
  - ./fix.py <N|rkey> title "..."   (or: year YYYY)
  - ./fix.py <N|rkey> page "Right Wikipedia Title"
  - ./fix.py <N|rkey> dismiss "why it's fine"
  (./fix.py <N|rkey> unset [KEY ...] undoes a fix)
then ./step2_llm_review.sh to re-review the rows you changed
TXT
