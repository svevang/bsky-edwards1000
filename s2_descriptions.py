#!/usr/bin/env python3
"""Stage 2: stages/01_parsed.json -> stages/02_descriptions.json  (Wikipedia intro per film)

One API call per film (search + intro extract). A candidate page is accepted when it's a
film, its title matches exactly (ignoring accents/leading article), and the stated release
year matches; otherwise the best guess is kept with status "needs_review".

Manual fixes: set "page": "Exact Wikipedia Title" and "pinned": true on the entry, then
re-run with --redo N to fetch that page. Rows are only refetched when title/year change.
"""
import json
import re
import sys
import stage
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "edwards1000-descriptions/1.0 (personal project)"}
API = "https://en.wikipedia.org/w/api.php"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def get(url, **params):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == 3:
                raise
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 0) or 0) or 15 * (attempt + 1)
                print(f"  429, sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
        except Exception:
            if attempt == 3:
                raise
        time.sleep(2 * (attempt + 1))


def norm(s):
    s = s.lower().replace("&", "and")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"^(the|a|an) ", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


def candidates(query, limit=5):
    """One API call: search + intro extract + url + disambiguation flag for each hit."""
    res = get(API, action="query", generator="search", gsrsearch=query, gsrlimit=limit,
              prop="extracts|info|pageprops", exintro=1, explaintext=1, exlimit=limit,
              inprop="url", ppprop="disambiguation", redirects=1, format="json")
    pages = (res or {}).get("query", {}).get("pages", {})
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        if "disambiguation" in p.get("pageprops", {}):
            continue
        out.append({"title": p["title"], "extract": (p.get("extract") or "").strip(),
                    "url": p.get("fullurl")})
    return out


def search(title, year):
    for q in (f'"{title}" {year} film', f"{title} {year} film", f"{title} film"):
        c = candidates(q)
        if c:
            return c
        time.sleep(0.5)
    return []


def summary(page):
    """Fetch one exact page (used for pinned entries)."""
    c = candidates(page, limit=1)
    return c[0] if c and c[0]["title"].lower() == page.lower() else None


def score_page(want, year, page, extract):
    """(is_film, title_ok, year_ok) for a candidate page."""
    lead = extract[:400].lower()
    is_film = bool(re.search(r"\b(film|movie)\b", lead))
    paren = re.search(r"\(([^)]*)\)\s*$", page)
    title_ok = norm(page) == want and (not paren or "film" in paren.group(1).lower())
    # "is a 1961 ... film" is the strongest signal; otherwise the year anywhere near the top
    stated = re.search(r"\bis a(?:n)? (19[5-7]\d)\b", lead)
    year_ok = (int(stated.group(1)) == int(year)) if stated else bool(re.search(rf"\b{year}\b", lead))
    return (is_film, title_ok, year_ok)


def pick(title, year, cands):
    """Prefer a candidate whose page title matches and whose summary mentions the year."""
    want = norm(title)
    ranked = []
    for s in cands:
        c, extract = s["title"], s["extract"]
        score = score_page(want, year, c, extract)
        ranked.append((score, c, s))
        if all(score):
            break
    if not ranked:
        return None, None, "no film page found"
    ranked.sort(key=lambda r: r[0], reverse=True)
    score, c, s = ranked[0]
    notes = []
    if not score[0]:
        notes.append("page may not be a film")
    if not score[1]:
        notes.append(f"title mismatch: {c!r}")
    if not score[2]:
        notes.append(f"{year} not mentioned")
    return c, s, "; ".join(notes)



def main():
    a = stage.args(__doc__)
    parsed = {rk: r for rk, r in stage.load(stage.PARSED).items() if r["number"]}
    descs = stage.load(stage.DESCRIPTIONS, default={})

    def in_fp(r): return stage.fp(r["title"], r["year"])
    def num(r): return r["number"]

    todo = stage.select_todo(a, parsed, descs, in_fp, num)
    print(f"{len(parsed)} rows, {len(todo)} to fetch", file=sys.stderr)
    for i, rk in enumerate(todo, 1):
        r = parsed[rk]
        title, year = r["title"], r["year"]
        pinned_page = (descs.get(rk) or {}).get("page") if (descs.get(rk) or {}).get("pinned") else None
        try:
            if pinned_page:
                s = summary(pinned_page)
                page, note = (pinned_page, "") if s else (None, f"pinned page {pinned_page!r} not found")
            else:
                page, s, note = pick(title, year, search(title, year))
        except Exception as e:
            print(f"  !! #{r['number']} {title}: {e}", file=sys.stderr)
            continue
        entry = {"number": r["number"], "title": title, "year": year, "fp": in_fp(r),
                 "page": page, "url": s["url"] if s else None,
                 "description": s["extract"] if s else None,
                 "status": "not_found" if not s else "pinned" if pinned_page else "needs_review" if note else "ok",
                 "note": note}
        if pinned_page:
            entry["pinned"] = True
        descs[rk] = entry
        mark = {"ok": " ", "pinned": "P", "needs_review": "?", "not_found": "X"}[entry["status"]]
        print(f"  [{mark}] {i}/{len(todo)} #{r['number']} {title} ({year}) -> {page}"
              + (f"  [{note}]" if note else ""), file=sys.stderr)
        if i % 10 == 0:
            stage.save(stage.DESCRIPTIONS, descs)
        time.sleep(1.0)
    stage.save(stage.DESCRIPTIONS, descs)

    stage.report("02_descriptions", descs, parsed)
    bad = [v for v in descs.values() if v["status"] in ("needs_review", "not_found")]
    if bad:
        print("review these (set \"page\" + \"pinned\": true, then --redo N):", file=sys.stderr)
        for v in sorted(bad, key=lambda v: v["number"]):
            print(f"  #{v['number']} {v['title']} -> {v['page']}: {v['note']}", file=sys.stderr)


if __name__ == "__main__":
    main()
