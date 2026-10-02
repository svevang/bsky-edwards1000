"""Shared helpers for the pipeline stages.

Every stage reads the previous stage's file and writes its own, both JSON dicts keyed
by post rkey. Each output entry carries "fp": a fingerprint of the input fields it was
computed from, so a stage only reprocesses rows whose input changed. Manual edits to a
stage file (pins, overrides) are preserved because they set "pinned": true.

Common CLI flags handled by `select_todo`:
  --force            redo every row
  --redo N[,N...]    redo rows with these watchlist numbers
  --only N[,N...]    consider only rows with these watchlist numbers
  --limit K          process at most K rows this run (lets you check output early)

Pinned entries are skipped even under --force/--redo while their input is unchanged, so a
hand fix can't be clobbered by a rerun. A stage that re-applies the pin itself (s2 fetching a
pinned "page") passes redo_pinned=True so --redo N reaches it. `fix.py` sets and clears pins.
"""
import argparse
import hashlib
import json
import os
import sys

STAGES = "stages"
POSTS = f"{STAGES}/00_posts.json"
PARSED = f"{STAGES}/01_parsed.json"
DESCRIPTIONS = f"{STAGES}/02_descriptions.json"
LLM_REVIEW = f"{STAGES}/03_llm_review.json"
FINAL = "movies.csv"


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        if default is None:
            sys.exit(f"{path} not found — run the previous stage first")
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def fp(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def args(desc):
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("--force", action="store_true")
    p.add_argument("--redo", default="", help="comma-separated watchlist numbers")
    p.add_argument("--only", default="", help="comma-separated watchlist numbers")
    p.add_argument("--limit", type=int, default=0)
    return p.parse_args()


def numbers(csv):
    return {int(n) for n in csv.split(",") if n.strip()}


def select_todo(a, inputs, existing, input_fp, number_of, redo_pinned=False):
    """inputs: {rkey: input row}; existing: {rkey: previous output}.
    Returns rkeys to (re)process, honoring --force/--redo/--only/--limit and pins."""
    redo, only = numbers(a.redo), numbers(a.only)
    todo = []
    for rk, row in inputs.items():
        n = number_of(row)
        if only and n not in only:
            continue
        prev = existing.get(rk)
        changed = not prev or prev.get("fp") != input_fp(row)
        if prev and prev.get("pinned") and not changed and not (redo_pinned and n in redo):
            continue  # pinned and input unchanged
        if changed or a.force or n in redo:
            todo.append(rk)
    todo.sort(key=lambda rk: number_of(inputs[rk]) or 10**6)
    return todo[: a.limit] if a.limit else todo


def report(stage_name, outputs, inputs=None):
    counts = {}
    for v in outputs.values():
        counts[v.get("status", "?")] = counts.get(v.get("status", "?"), 0) + 1
    extra = f", {len(inputs) - len(outputs)} not yet processed" if inputs is not None and len(inputs) > len(outputs) else ""
    print(f"{stage_name}: {len(outputs)} rows {counts}{extra}", file=sys.stderr)
