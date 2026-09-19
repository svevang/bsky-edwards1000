#!/usr/bin/env bash
# Step 2 (LLM in the loop): Claude reads each row and flags title/year/description
# disagreements -> stages/03_llm_review.json, then movies.csv is rebuilt with the flags.
# Uses the `claude` CLI (your login; no API key). Only rows not yet reviewed, or whose
# inputs changed, are sent.
#
# Usage: ./step2_llm_review.sh [--force | --redo N,N | --limit K]
set -euo pipefail
cd "$(dirname "$0")"
command -v claude >/dev/null || { echo "claude CLI not found"; exit 1; }

python3 s3_llm_review.py "$@"
python3 s4_join.py

cat <<'TXT'

For each flagged row: python3 status.py <number> to see its trail, then either
  - fix title/year in stages/01_parsed.json (set "pinned": true), or
  - pin the right Wikipedia "page" in stages/02_descriptions.json ("pinned": true), or
  - dismiss: set "ok": true, "pinned": true in stages/03_llm_review.json
then ./step1_build.sh --skip-download --redo <number> && ./step2_llm_review.sh
TXT
