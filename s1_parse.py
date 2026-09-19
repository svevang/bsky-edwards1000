#!/usr/bin/env python3
"""Stage 1: stages/00_posts.json -> stages/01_parsed.json  (number, title, year per post)

Posts look like:
    #Edwards1000SixtiesMovies
    123/1000:
    THE TITLE
    <review...>
The watchlist is 100 films per year in order, so year = 1960 + (number-1)//100.

Each output entry keeps `raw_title_line` and `text_head` so a bad parse can be traced
back to its source without opening 00_posts.json.

Manual fixes: edit the entry in 01_parsed.json and set "pinned": true — it will survive
re-runs unless the post text itself changes (or you pass --redo N / --force).
"""
import re
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
    posts = {p["url"].rsplit("/", 1)[-1]: p for p in stage.load(stage.POSTS)}
    parsed = stage.load(stage.PARSED, default={})

    def in_fp(p): return stage.fp(p["text"])
    def num(p):
        m = NUM_RE.search(p["text"]); return int(m.group(1)) if m else None

    todo = stage.select_todo(a, posts, parsed, in_fp, num)
    for rk in todo:
        p = posts[rk]
        r = parse(p["text"])
        r.update(rkey=rk, url=p["url"], createdAt=p["createdAt"], fp=in_fp(p),
                 text_head=re.sub(r"\s+", " ", p["text"])[:160])
        parsed[rk] = r
    stage.save(stage.PARSED, parsed)

    print(f"parsed {len(todo)} new/changed of {len(posts)} posts", file=__import__("sys").stderr)
    stage.report("01_parsed", parsed, posts)
    nums = [r["number"] for r in parsed.values() if r["number"]]
    dups = sorted({n for n in nums if nums.count(n) > 1})
    gaps = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
    if dups: print(f"  duplicate numbers: {dups}")
    if gaps: print(f"  missing numbers: {gaps}")
    for r in sorted(parsed.values(), key=lambda r: r["number"] or 0):
        if r["status"] == "needs_review":
            print(f"  #{r['number']} {r['title']!r}: {r['note']}   raw={r['raw_title_line']!r}  rkey={r['rkey']}")


if __name__ == "__main__":
    main()
