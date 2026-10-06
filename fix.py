#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml>=6.0.3"]
# ///
"""Hand-correct one film with an override, then rerun just what it affects.
N is the film's watchlist number, or its rkey (for a post with no number, or a shared one).

  ./fix.py N title "THE V.I.P.s"          parsed.title    -> refetch description, rebuild csv
  ./fix.py N year 1964                    parsed.year     -> refetch description, rebuild csv
  ./fix.py N page "La Vérité (film)"      pin.page        -> fetch that page, rebuild csv
  ./fix.py N dismiss "festival year"      dismissed       -> rebuild csv
  ./fix.py N unset [KEY ...]              drop these overrides (all of N's when none given)
  ./fix.py N unset rejected               let the review propose values you removed again

Overrides live in entries/<rkey>/override.yaml. A file.field key replaces that field in the
entry's view; the stage file keeps its computed value underneath and no stage rerun touches
it, so a fix stays until unset. pin.page is an input instead: stage 2 fetches that page.
A dismissal records the fp of the row it dismissed (the review, or the parse for a post with
no watchlist number) and lapses once that row changes. The
LLM review (./step2_llm_review.sh) also writes page, title and year fixes there; `unset`
drops one you don't want and records its value under `rejected`, so the review won't set it again.
"""
import argparse
import os
import sys
import entries
import render
import s2_descriptions as s2
import tables
from tables import FIXES

KEYS = {"title": "parsed.title", "year": "parsed.year", "page": "pin.page"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ref", metavar="N", help="watchlist number or rkey")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("title").add_argument("value")
    sub.add_parser("year").add_argument("value", type=int)
    sub.add_parser("page").add_argument("value")
    sub.add_parser("dismiss").add_argument("reason", nargs="?", default="")
    sub.add_parser("unset").add_argument("keys", nargs="*", metavar="KEY")
    a = p.parse_args()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    rk = entries.find(a.ref)
    if a.cmd in KEYS:
        entries.set_override(rk, KEYS[a.cmd], a.value)
    elif a.cmd == "dismiss":
        v = entries.view(rk)
        if (s := entries.compute_status(v)) != "needs_review":
            sys.exit(f"{a.ref} is {s}; only a needs_review row can be dismissed")
        entries.set_override(rk, "dismissed", {"fp": tables.fp(tables.deciding(v), v), "reason": a.reason})
    elif a.cmd == "unset":
        current = entries.read(rk, "override") or {}
        if unknown := [k for k in a.keys if k not in current]:
            sys.exit(f"{a.ref} has no override {', '.join(unknown)}; current: {', '.join(current) or 'none'}")
        keys = a.keys or list(current)
        rejected = {} if "rejected" in keys else current.get("rejected", {})
        for k in keys:
            if k in FIXES.values() and current[k] not in rejected.get(k, []):
                rejected = {**rejected, k: [*rejected.get(k, []), current[k]]}
        entries.unset_override(rk, keys)
        if rejected:
            entries.set_override(rk, "rejected", rejected)

    s2.refresh([rk])
    v = entries.view(rk)
    render.report(render.render_csv())
    shown = tables.lookup(v, "parsed.number") or rk  # unset may have changed it
    if tables.applies("review", v) and not tables.fresh("review", v):
        print(f"\n#{shown} will be (re)reviewed on the next ./step2_llm_review.sh")
    print(f"uv run python status.py {shown}   # see the result")


if __name__ == "__main__":
    main()
