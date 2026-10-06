"""Shared helpers for the pipeline stages.

Every stage reads entry views (entries/<rkey>/, overrides applied) and writes its own file
per entry as soon as the row finishes. Each stage file carries "fp": a fingerprint of the
stage's code version and the request it made (tables.py), so a stage only reprocesses rows
whose request or code changed.
Hand fixes live in override.yaml, which stages never write, so no rerun can clobber them.

Common CLI flags handled by `select`:
  --force            redo every row
  --redo N[,N...]    redo rows with these watchlist numbers
  --only N[,N...]    consider only rows with these watchlist numbers
  --limit K          process at most K rows this run (lets you check output early)
"""
import argparse
import sys
import entries
import tables


def args(desc):
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("--force", action="store_true")
    p.add_argument("--redo", default="", help="comma-separated watchlist numbers")
    p.add_argument("--only", default="", help="comma-separated watchlist numbers")
    p.add_argument("--limit", type=int, default=0)
    return p.parse_args()


def numbers(csv):
    return {int(n) for n in csv.split(",") if n.strip()}


def select(name, a):
    """rkeys whose stage file `name` is missing or stale, or asked for by --force/--redo.
    Skips deleted entries, entries the file doesn't apply to, and entries whose earlier
    stage files are missing or stale. --only/--redo match the overridden parsed.number."""
    redo, only = numbers(a.redo), numbers(a.only)
    todo = []
    for rk, v in entries.live():
        if not ready(name, v):
            continue
        n = tables.lookup(v, "parsed.number")
        if (only and n not in only) or not (a.force or n in redo or not tables.fresh(name, v)):
            continue
        todo.append((n is None, n or 0, rk))
    todo = [rk for *_, rk in sorted(todo)]
    return todo[: a.limit] if a.limit else todo


def ready(name, v):
    """The entry has a post, stage file `name` applies to it, and every earlier table is fresh."""
    return tables.applies(name, v) and tables.all_fresh(v, before=name)


def finish(stage_name):
    """Print how many entries have each status."""
    counts = {}
    for rk in entries.list_entries():
        s = entries.status(rk)
        counts[s] = counts.get(s, 0) + 1
    print(f"{stage_name}: {sum(counts.values())} entries {counts}", file=sys.stderr)
