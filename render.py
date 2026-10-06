#!/usr/bin/env python3
"""Render movies.csv from entries/: one row per entry that isn't deleted, overrides applied.
The `overrides` column lists the keys set by hand in override.yaml."""
import argparse
import csv
import io
import entries
from s2_descriptions import canonical

COLUMNS = ["number", "title", "canonical_title", "year", "qualifier", "description", "wikipedia", "status",
           "overrides", "parse_note", "desc_note", "llm_issue", "rkey", "url", "createdAt"]


def row(rk, v):
    p, w, r, post = (v.get(n) or {} for n in ("parsed", "wikipedia", "review", "post"))
    return {
        "number": p.get("number"), "title": p.get("title"), "canonical_title": canonical(w.get("page")),
        "year": p.get("year"), "qualifier": p.get("qualifier"),
        "description": w.get("description") or "", "wikipedia": w.get("url") or "",
        "status": entries.compute_status(v),
        "overrides": ", ".join(v["override"]),
        "parse_note": p.get("note", ""), "desc_note": w.get("note", ""),
        "llm_issue": r.get("issue", "") if r and not r.get("ok") else "",
        "rkey": rk, "url": post.get("url"), "createdAt": post.get("createdAt"),
    }


def render_csv(out="movies.csv"):
    rows = [row(rk, v) for rk, v in entries.live()]
    rows.sort(key=lambda r: (r["number"] is None, r["number"] or 0, r["createdAt"] or ""))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows(rows)
    entries.save_text(out, buf.getvalue())
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="movies.csv")
    a = p.parse_args()
    report(render_csv(a.out), a.out)


def report(rows, out="movies.csv"):
    attn = [r for r in rows if r["status"] == "needs_review"]
    pending = sum(r["status"] == "pending" for r in rows)
    print(f"{out}: {len(rows)} rows; {len(attn)} need attention")
    nums = [r["number"] for r in rows if r["number"]]
    if dups := sorted({n for n in nums if nums.count(n) > 1}):
        print(f"  duplicate numbers: {dups}")
    if gaps := sorted(set(range(1, max(nums, default=0) + 1)) - set(nums)):
        print(f"  missing numbers: {gaps}")
    for r in attn:
        why = [s for s in (r["parse_note"], r["desc_note"], r["llm_issue"]) if s]
        print(f"  #{r['number'] or '?':>3} {r['title'] or '':40} {' | '.join(why)}  rkey={r['rkey']}")
    if pending:
        print(f"  {pending} pending (a stage still has to run)")


if __name__ == "__main__":
    main()
