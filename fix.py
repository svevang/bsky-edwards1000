#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml>=6.0.3"]
# ///
"""Hand-correct one film with an override, then rerun just what it affects.

  ./fix.py N title "THE V.I.P.s"          parsed.title    -> refetch description, rebuild csv
  ./fix.py N year 1964                    parsed.year     -> refetch description, rebuild csv
  ./fix.py N page "La Vérité (film)"      wikipedia.page  -> fetch that page, rebuild csv
  ./fix.py N dismiss "festival year"      review.ok (+ review.dismissed) -> rebuild csv
  ./fix.py N unset [KEY ...]              drop these overrides (all of N's when none given)

Overrides live in entries/<rkey>/override.yaml as file.field keys. Stage files keep their
computed values underneath and no stage rerun touches them, so a fix stays until unset. The
LLM review (./step2_llm_review.sh) also writes page, title and year fixes there; `unset`
drops one you don't want (it may propose it again on a later re-review).
"""
import argparse
import os
import sys
import entries
import render
import s2_descriptions as s2
import schema
import stage

KEYS = {"title": "parsed.title", "year": "parsed.year", "page": "wikipedia.page"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("number", type=int)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("title").add_argument("value")
    sub.add_parser("year").add_argument("value", type=int)
    sub.add_parser("page").add_argument("value")
    sub.add_parser("dismiss").add_argument("reason", nargs="?", default="")
    sub.add_parser("unset").add_argument("keys", nargs="*", metavar="KEY")
    a = p.parse_args()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    rk = entries.find(a.number)
    if a.cmd in KEYS:
        entries.set_override(rk, KEYS[a.cmd], a.value)
    elif a.cmd == "dismiss":
        if not entries.read(rk, "review"):
            sys.exit(f"#{a.number} has no LLM review yet")
        entries.set_override(rk, "review.ok", True)
        entries.set_override(rk, "review.dismissed", a.reason)
    elif a.cmd == "unset":
        current = entries.read(rk, "override") or {}
        if unknown := [k for k in a.keys if k not in current]:
            sys.exit(f"#{a.number} has no override {', '.join(unknown)}; current: {', '.join(current) or 'none'}")
        entries.unset_override(rk, a.keys or None)

    v = entries.view(rk)
    if a.cmd != "dismiss" and stage.ready("wikipedia", v) and not schema.fresh("wikipedia", v):
        print(f"refetching wikipedia -> {s2.describe(rk)['page']}")
        v = entries.view(rk)
    entries.update_status(rk)
    render.report(render.render_csv())
    shown = schema.lookup(v, "parsed.number") or a.number  # unset may have changed it
    if schema.applies("review", v) and not schema.fresh("review", v):
        print(f"\n#{shown} will be (re)reviewed on the next ./step2_llm_review.sh")
    print(f"uv run python status.py {shown}   # see the result")


if __name__ == "__main__":
    main()
