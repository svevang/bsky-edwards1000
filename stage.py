"""Shared helpers for the pipeline stages.

Every stage reads entry views (entries/<rkey>/, overrides applied) and writes its own file
per entry as soon as the row finishes. Each stage file carries "fp": a fingerprint of the
inputs schema.yaml lists for it, so a stage only reprocesses rows whose inputs changed.
Hand fixes live in override.yaml, which stages never write, so no rerun can clobber them.

Common CLI flags handled by `select`:
  --force            redo every row
  --redo N[,N...]    redo rows with these watchlist numbers
  --only N[,N...]    consider only rows with these watchlist numbers
  --limit K          process at most K rows this run (lets you check output early)
"""
import argparse
import hashlib
import sys
import entries
import schema


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


def select(name, a, number_of=None):
    """rkeys whose stage file `name` is missing or stale, or asked for by --force/--redo.
    Skips deleted entries, entries the file doesn't apply to, and entries whose earlier
    stage files are missing or stale. number_of(view) gives the watchlist number for
    --only/--redo; by default the overridden parsed.number."""
    number_of = number_of or (lambda v: (v.get("parsed") or {}).get("number"))
    redo, only = numbers(a.redo), numbers(a.only)
    earlier = schema.stage_files()[:schema.stage_files().index(name)]
    todo = []
    for rk in entries.list_entries():
        if entries.read(rk, "status") == "deleted":
            continue
        v = entries.view(rk)
        n = number_of(v) if "post" in v else None
        if "post" not in v or not schema.applies(name, v) or (only and n not in only):
            continue
        if any(schema.applies(e, v) and not fresh(e, v) for e in earlier):
            continue
        if not fresh(name, v) or a.force or n in redo:
            todo.append((n is None, n or 0, rk))
    todo = [rk for *_, rk in sorted(todo)]
    return todo[: a.limit] if a.limit else todo


def fresh(name, view):
    return name in view and view[name].get("fp") == schema.fp(name, view)


def finish(stage_name):
    """Recompute every entry's status (it depends on all stages) and print the counts."""
    counts = {}
    for rk in entries.list_entries():
        s = entries.update_status(rk)
        counts[s] = counts.get(s, 0) + 1
    print(f"{stage_name}: {sum(counts.values())} entries {counts}", file=sys.stderr)
