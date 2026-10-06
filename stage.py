"""Shared helpers for the pipeline stages.

Every stage reads entry views (entries/<rkey>/, overrides applied) and writes its own file
per entry as soon as the row finishes. Each stage file carries "fp": a fingerprint of the
stage's code version and the request it made (tables.py), so a stage only reprocesses rows
whose request or code changed.
Hand fixes live in override.yaml, which stages never write, so no rerun can clobber them.

Common CLI flags handled by `select`:
  --force            redo every row
  --redo N[,N...]    redo rows with these watchlist numbers or rkeys
  --only N[,N...]    consider only rows with these watchlist numbers or rkeys
  --limit K          process at most K rows this run (lets you check output early)
"""
import argparse
import sys
import entries
import tables


def args(desc):
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("--force", action="store_true")
    p.add_argument("--redo", default="", help="comma-separated watchlist numbers or rkeys")
    p.add_argument("--only", default="", help="comma-separated watchlist numbers or rkeys")
    p.add_argument("--limit", type=int, default=0)
    return p.parse_args()


def refs(csv):
    return {r.strip() for r in csv.split(",") if r.strip()}


def select(name, a):
    """rkeys whose stage file `name` is missing or stale, or asked for by --force/--redo.
    Skips deleted entries, entries the file doesn't apply to, and entries whose earlier
    stage files are missing or stale. --only/--redo match the rkey or the overridden parsed.number."""
    redo, only = refs(a.redo), refs(a.only)
    todo = []
    for rk, v in entries.live():
        if not ready(name, v):
            continue
        n = tables.lookup(v, "parsed.number")
        ids = {rk, str(n)}
        if (only and not ids & only) or not (a.force or ids & redo or not tables.fresh(name, v)):
            continue
        todo.append((n is None, n or 0, rk))
    todo = [rk for *_, rk in sorted(todo)]
    return todo[: a.limit] if a.limit else todo


def ready(name, v):
    """The entry has a post, stage file `name` applies to it, and every earlier table is fresh."""
    return tables.applies(name, v) and tables.all_fresh(v, before=name)


def finish(stage_name):
    """Print how many entries have each status."""
    counts, _ = entries.status_counts()
    print(f"{stage_name}: {sum(counts.values())} entries {counts}", file=sys.stderr)
