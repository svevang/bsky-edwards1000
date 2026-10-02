#!/usr/bin/env python3
"""Hand-correct one film, pin the correction, and rerun just the stages it affects.

  ./fix.py N title "THE V.I.P.s"          01_parsed: fix the title   -> refetch description, rebuild csv
  ./fix.py N year 1964                    01_parsed: fix the year    -> refetch description, rebuild csv
  ./fix.py N page "La Vérité (film)"      02_descriptions: use this Wikipedia page -> fetch it, rebuild csv
  ./fix.py N dismiss "festival year"      03_llm_review: dismiss the LLM flag -> rebuild csv
  ./fix.py N unpin                        drop every pin on N and recompute it

Pinned entries survive reruns (even --force/--redo) until their own inputs change.
"""
import argparse
import os
import subprocess
import sys
import stage


def run(*cmd):
    subprocess.run([sys.executable, *cmd], check=True)


def rkey_for(parsed, n):
    rks = [rk for rk, r in parsed.items() if r["number"] == n]
    if len(rks) != 1:
        sys.exit(f"#{n}: {'not in 01_parsed' if not rks else f'{len(rks)} posts share this number: {rks}'}")
    return rks[0]


def pin_parsed(parsed, rk, field, value):
    r = parsed[rk]
    note = f"manual: {field} was {r[field]!r}"
    r.update({field: value, "status": "pinned", "pinned": True,
              "note": note if not r.get("pinned") else f"{r['note']}; {note}"})
    stage.save(stage.PARSED, parsed)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("number", type=int)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("title").add_argument("value")
    sub.add_parser("year").add_argument("value", type=int)
    sub.add_parser("page").add_argument("value")
    sub.add_parser("dismiss").add_argument("reason", nargs="?", default="")
    sub.add_parser("unpin")
    a = p.parse_args()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    n = str(a.number)
    parsed = stage.load(stage.PARSED)
    rk = rkey_for(parsed, a.number)
    descs = stage.load(stage.DESCRIPTIONS, default={})
    reviews = stage.load(stage.LLM_REVIEW, default={})

    if a.cmd in ("title", "year"):
        pin_parsed(parsed, rk, a.cmd, a.value)
        run("s2_descriptions.py", "--only", n)  # title/year are s2's input, so it refetches
    elif a.cmd == "page":
        descs.setdefault(rk, {}).update(page=a.value, pinned=True)
        stage.save(stage.DESCRIPTIONS, descs)
        run("s2_descriptions.py", "--only", n, "--redo", n)
    elif a.cmd == "dismiss":
        v = reviews.get(rk)
        if not v:
            sys.exit(f"#{a.number} has no LLM review yet")
        v.update(ok=True, status="dismissed", pinned=True, dismissed=a.reason)
        stage.save(stage.LLM_REVIEW, reviews)
    elif a.cmd == "unpin":
        parsed[rk].pop("pinned", None)
        stage.save(stage.PARSED, parsed)
        if rk in descs:
            descs[rk].pop("pinned", None)
            stage.save(stage.DESCRIPTIONS, descs)
        if reviews.get(rk, {}).get("pinned"):
            del reviews[rk]  # re-reviewed on the next ./step2_llm_review.sh
            stage.save(stage.LLM_REVIEW, reviews)
        run("s1_parse.py", "--only", n, "--redo", n)
        run("s2_descriptions.py", "--only", n, "--redo", n)

    run("s4_join.py")
    r, d = stage.load(stage.PARSED)[rk], stage.load(stage.DESCRIPTIONS, default={}).get(rk, {})
    v = stage.load(stage.LLM_REVIEW, default={}).get(rk)
    if not v or v["fp"] != stage.fp(r["title"], r["year"], d.get("description")):  # same fp as s3
        print(f"\n#{a.number} will be (re)reviewed on the next ./step2_llm_review.sh")
    print(f"python3 status.py {a.number}   # see the result")


if __name__ == "__main__":
    main()
