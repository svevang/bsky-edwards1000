#!/usr/bin/env python3
"""Stage 4: join stages/01..03 -> movies.csv. Pure function of the stage files; always rebuilt."""
import csv
import re
import stage

parsed = stage.load(stage.PARSED)
descs = stage.load(stage.DESCRIPTIONS, default={})
reviews = stage.load(stage.LLM_REVIEW, default={})

def canonical(page):
    """Wikipedia page title minus its disambiguator: 'The Alamo (1960 film)' -> 'The Alamo'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", page) if page else ""


def llm_status(v):
    """A flag set "ok" by hand (or by fix.py dismiss) counts as dismissed, not flagged."""
    s = v.get("status", "missing")
    return "dismissed" if s == "flagged" and v.get("ok") else s


rows = []
for rk, p in parsed.items():
    d, v = descs.get(rk, {}), reviews.get(rk, {})
    rows.append({
        "number": p["number"], "title": p["title"], "canonical_title": canonical(d.get("page")),
        "year": p["year"], "qualifier": p["qualifier"],
        "description": d.get("description") or "", "wikipedia": d.get("url") or "",
        "parse_status": p["status"], "parse_note": p["note"],
        "desc_status": d.get("status", "missing"), "desc_note": d.get("note", ""),
        "llm_status": llm_status(v), "llm_issue": v.get("issue", ""),
        "rkey": rk, "url": p["url"], "createdAt": p["createdAt"],
    })
rows.sort(key=lambda r: (r["number"] is None, r["number"] or 0, r["createdAt"]))
with open(stage.FINAL, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

attn = [r for r in rows if r["parse_status"] == "needs_review" or r["desc_status"] in ("needs_review", "not_found", "missing")
        or r["llm_status"] == "flagged"]
print(f"{stage.FINAL}: {len(rows)} rows; {len(attn)} need attention")
for r in attn:
    why = [s for s in (r["parse_note"], r["desc_note"] if r["desc_status"] != "ok" else "",
                       r["desc_status"] if r["desc_status"] in ("missing", "not_found") else "", r["llm_issue"]) if s]
    print(f"  #{r['number']:>3} {r['title']:40} {' | '.join(why)}  rkey={r['rkey']}")
