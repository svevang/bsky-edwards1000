#!/usr/bin/env python3
"""Stage 2: parsed.yaml -> wikipedia.yaml  (Wikipedia intro per film)

One API call per film (search + intro extract). A candidate page is accepted when it's a
film, its title matches exactly (ignoring accents/leading article), and the stated release
year matches; otherwise the best guess is kept with status "needs_review".

Manual fixes: `./fix.py N page "Exact Wikipedia Title"` (or the LLM review) sets the
wikipedia.page override; that exact page is then fetched, following redirects. Rows are
only refetched when title, year or that override change. Each row is saved as soon as it's
fetched; describe(rk) does one row and is also used by the review stage.
"""
import json
import re
import sys
import entries
import schema
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
    """Fetch one page by exact title, following redirects; None when missing or a disambiguation."""
    res = get(API, action="query", titles=page, redirects=1, prop="extracts|info|pageprops",
              exintro=1, explaintext=1, inprop="url", ppprop="disambiguation", format="json")
    for p in (res or {}).get("query", {}).get("pages", {}).values():
        if "missing" in p or "invalid" in p or "disambiguation" in p.get("pageprops", {}):
            return None
        return {"title": p["title"], "extract": (p.get("extract") or "").strip(), "url": p.get("fullurl")}
    return None


def is_film(extract):
    return bool(re.search(r"\b(film|movie)\b", extract[:400].lower()))


def film_title(page):
    """False when the page's disambiguator names something else, e.g. "(soundtrack)", "(film series)"."""
    paren = re.search(r"\(([^)]*)\)\s*$", page)
    if not paren:
        return True
    disambiguator = paren.group(1).lower()
    return "film" in disambiguator and "series" not in disambiguator


NOT_ONE_FILM = "series|director|actor|actress|producer|franchise|studio|festival|score|soundtrack|composer|critic"
GENRES = "comedy|drama|thriller|docudrama|melodrama|western|musical|documentary"
LINK_WORDS = {"from", "for", "by", "of", "in", "on", "to", "the", "with", "about", "featuring", "song", "album",
              "single", "soundtrack", "novel", "character", "series", "franchise", "television", "tv", "stage", "play"}


def one_film(extract):
    """True when the intro's first "X is a ..." makes X a single film: "is a 1963 American musical
    film", "is a 1960 romantic comedy starring", "is the second of four Miss Marple films"; not
    "a film series", "an American film director" or "a song from the 1961 film"."""
    m = re.search(r"\b(?:is|was) (an?|the) ", extract[:400])
    if not m:
        return False
    rest = extract[m.end():400]
    if m.group(1) == "the":
        return bool(re.match(r"\w+ of (?:\S+\s+){1,4}?films\b", rest))
    head = re.match(rf"((?:\S+\s+){{0,12}}?)(?:(?:film|movie)\b(?!\s+(?:{NOT_ONE_FILM}))|(?:{GENRES})"
                    rf"(?=\s+(?:directed|starring|written|produced|about|based|released)\b|[,.(]))", rest, re.I)
    return bool(head) and not LINK_WORDS & {w.lower() for w in re.findall(r"[\w'-]+", head.group(1))}


def score_page(want, year, page, extract):
    """(is_film, title_ok, year_ok) for a candidate page."""
    lead = extract[:400].lower()
    title_ok = norm(page) == want and film_title(page)
    # "is a 1961 ... film" is the strongest signal; otherwise the year anywhere near the top
    stated = re.search(r"\bis a(?:n)? (19[5-7]\d)\b", lead)
    year_ok = (int(stated.group(1)) == int(year)) if stated else bool(re.search(rf"\b{year}\b", lead))
    return (is_film(extract), title_ok, year_ok)


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


def describe(rk):
    """Fetch one entry's page and write its wikipedia.yaml and status; returns what was written."""
    v = entries.view(rk)
    title, year = v["parsed"]["title"], v["parsed"]["year"]
    pinned_page = v["override"].get("wikipedia.page")
    if pinned_page:
        s = summary(pinned_page)
        page, note = (s["title"], "") if s else (None, f"pinned page {pinned_page!r} not found")
    else:
        page, s, note = pick(title, year, search(title, year))
    w = {"fp": schema.fp("wikipedia", v), "page": page, "url": s["url"] if s else None,
         "description": s["extract"] if s else None, "note": note}
    entries.write(rk, "wikipedia", w)
    entries.update_status(rk)
    return w


def main():
    a = stage.args(__doc__)
    todo = stage.select("wikipedia", a)
    print(f"{len(todo)} to fetch", file=sys.stderr)
    for i, rk in enumerate(todo, 1):
        v = entries.view(rk)
        r = v["parsed"]
        try:
            w = describe(rk)
        except Exception as e:
            print(f"  !! #{r['number']} {r['title']}: {e}", file=sys.stderr)
            continue
        note = w["note"]
        mark = "X" if not w["page"] else "P" if "wikipedia.page" in v["override"] else "?" if note else " "
        print(f"  [{mark}] {i}/{len(todo)} #{r['number']} {r['title']} ({r['year']}) -> {w['page']}"
              + (f"  [{note}]" if note else ""), file=sys.stderr)
        time.sleep(1.0)
    stage.finish("wikipedia")

    bad = [v for rk in entries.list_entries() if entries.read(rk, "status") != "deleted"
           and "wikipedia" in (v := entries.view(rk)) and schema.applies("wikipedia", v)
           and schema.unsure("wikipedia", v)]
    if bad:
        print("review these (./fix.py N page \"Wikipedia Title\", or ./fix.py N title/year):", file=sys.stderr)
        for v in sorted(bad, key=lambda v: v["parsed"]["number"] or 0):
            print(f"  #{v['parsed']['number']} {v['parsed']['title']} -> {v['wikipedia']['page']}: "
                  f"{v['wikipedia']['note']}", file=sys.stderr)


if __name__ == "__main__":
    main()
