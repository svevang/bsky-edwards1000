#!/usr/bin/env python3
"""Stage 1: entries/*/post.yaml -> parsed.yaml  (number, title, year per post)

Posts look like:
    #Edwards1000SixtiesMovies
    123/1000:
    THE TITLE
    <review...>
The watchlist is 100 films per year in order, so year = 1960 + (number-1)//100.

parsed.yaml keeps `raw_title_line` so a bad parse can be traced; post.yaml sits beside it.
It always holds the automated values: hand fixes (`./fix.py N title "..."`) are overrides.
"""
import re
import sys
import entries
import schema
import stage

NUM_RE = re.compile(r"^\s*(\d+)\s*/\s*[12]000\s*:?\s*$", re.M)  # tolerate "200/2000" typo
YEAR_SUFFIX_RE = re.compile(r"^(.*?)\s*\(?(?:\b(19[5-7]\d)|'([5-7]\d))\)?\s*$")  # "... 1960" / "... '60"


def year_for(number):
    return 1960 + (number - 1) // 100


def parse(text):
    out = {"number": None, "title": None, "year": None, "qualifier": "",
           "raw_title_line": "", "status": "ok", "note": ""}
    m = NUM_RE.search(text)
    if not m:
        out.update(status="needs_review", note="no N/1000 line")
        return out
    out["number"] = int(m.group(1))
    out["year"] = year_for(out["number"])

    lines = [l.strip() for l in text[m.end():].split("\n") if l.strip()]
    if not lines:
        out.update(status="needs_review", note="no title line")
        return out
    out["raw_title_line"] = lines[0]
    title = re.sub(r"\b([A-Za-z])'\s+", r"\1'", lines[0])  # "L' ECLISSE" -> "L'ECLISSE"

    ym = YEAR_SUFFIX_RE.match(title)
    if ym and ym.group(1):
        title = ym.group(1).strip()
        yr = int(ym.group(2)) if ym.group(2) else 1900 + int(ym.group(3))
        out["qualifier"] = str(yr)
        if yr != out["year"]:
            out.update(status="needs_review", note=f"title says {yr}, position implies {out['year']}")

    qm = re.match(r"^(.*?)\s*\((.*)\)\s*$", title)  # "(1962 version)", "(aka ...)"
    if qm:
        title, out["qualifier"] = qm.group(1).strip(), qm.group(2).strip()

    if title.replace("Mc", "MC") != title.upper() or len(title) > 80:
        out.update(status="needs_review", note=out["note"] or "title line doesn't look like a title")
    out["title"] = title
    return out


def main():
    a = stage.args(__doc__)

    def num(v):  # overridden number once parsed, else the one in the post text
        if "parsed.number" in v["override"] or "parsed" in v:
            return v["override"].get("parsed.number", (v.get("parsed") or {}).get("number"))
        m = NUM_RE.search(v["post"]["text"]); return int(m.group(1)) if m else None

    todo = stage.select("parsed", a, num)
    fields = [k for k in schema.load_schema()["files"]["parsed"]["fields"] if k != "fp"]
    for rk in todo:
        v = entries.view(rk)
        r = parse(v["post"]["text"])
        entries.write(rk, "parsed", {"fp": schema.fp("parsed", v), **{k: r[k] for k in fields}})
        entries.update_status(rk)
    print(f"parsed {len(todo)} new/changed rows", file=sys.stderr)
    stage.finish("parsed")

    views = {rk: v for rk in entries.list_entries()
             if entries.read(rk, "status") != "deleted" and "parsed" in (v := entries.view(rk))}
    nums = [v["parsed"]["number"] for v in views.values() if v["parsed"]["number"]]
    dups = sorted({n for n in nums if nums.count(n) > 1})
    gaps = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
    if dups: print(f"  duplicate numbers: {dups}")
    if gaps: print(f"  missing numbers: {gaps}")
    for rk, v in sorted(views.items(), key=lambda kv: kv[1]["parsed"]["number"] or 0):
        r = v["parsed"]
        if schema.unsure("parsed", v):
            print(f"  #{r['number']} {r['title']!r}: {r['note']}   raw={r['raw_title_line']!r}  rkey={rk}")


if __name__ == "__main__":
    main()
