#!/usr/bin/env python3
"""Stage 2: parsed title and year -> wikipedia.yaml  (Wikipedia intro per film)

One API call per film (search + intro extract). A candidate page is accepted when it's a
film, its title matches exactly (ignoring accents/leading article), and the stated release
year matches; otherwise the best guess is kept with status "needs_review".

Bump tables.VERSION["wikipedia"] when you change how a page is searched for, picked or fetched.

Manual fixes: `./fix.py N page "Exact Wikipedia Title"` (or the LLM review) sets the
pin.page override; that exact page is then fetched, following redirects. Rows are
only refetched when title, year or that override change. Each row is saved as soon as it's
fetched; refresh(rks) refetches just the given rows that went stale, for fix.py and the review.
"""
import re
import sys
import time
from urllib.parse import quote
import entries
import stage
import tables
from bsky_tag_dl import get

UA = "edwards1000-descriptions/1.0 (personal project)"
API = "https://en.wikipedia.org/w/api.php"


def pages(**params):
    """One API query with intro extract and disambiguation flag; the real, non-disambiguation
    pages as {title, extract}, in search order."""
    res = get(API, ua=UA, action="query", prop="extracts|pageprops", exintro=1, explaintext=1,
              ppprop="disambiguation", redirects=1, format="json", **params)
    found = sorted((res or {}).get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    return [{"title": p["title"], "extract": (p.get("extract") or "").strip()}
            for p in found if not ("missing" in p or "invalid" in p or "disambiguation" in p.get("pageprops", {}))]


def page_url(page):
    return "https://en.wikipedia.org/wiki/" + quote(page.replace(" ", "_"), safe="()!:,*$;@=+/") if page else ""


def canonical(page):
    """Wikipedia page title minus its disambiguator: 'The Alamo (1960 film)' -> 'The Alamo'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", page) if page else ""


def norm(s):
    s = s.lower().replace("&", "and")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"^(the|a|an) ", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


def candidates(query, limit=5):
    """One API call: search + intro extract for each hit that isn't a disambiguation."""
    return pages(generator="search", gsrsearch=query, gsrlimit=limit, exlimit=limit)


def search(title, year):
    for q in (f'"{title}" {year} film', f"{title} {year} film", f"{title} film"):
        c = candidates(q)
        if c:
            return c
        time.sleep(0.5)
    return []


def summary(page):
    """Fetch one page by exact title, following redirects; None when missing or a disambiguation."""
    return next(iter(pages(titles=page)), None)


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


def year_ok(extract, year, slack=0):
    """The intro dates the film within `slack` years of `year`: "is a 1961 ... film" is the
    strongest signal; otherwise the year anywhere near the top."""
    lead = extract[:400].lower()
    stated = re.search(r"\bis a(?:n)? (19[5-7]\d)\b", lead)
    if stated:
        return abs(int(stated.group(1)) - int(year)) <= slack
    return any(re.search(rf"\b{int(year) + d}\b", lead) for d in range(-slack, slack + 1))


def score_page(want, year, page, extract):
    """(is_film, title_ok, year_ok) for a candidate page."""
    return (is_film(extract), norm(page) == want and film_title(page), year_ok(extract, year))


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
    notes = ("page may not be a film", f"title mismatch: {c!r}", f"{year} not mentioned")
    return c, s, "; ".join(n for ok, n in zip(score, notes) if not ok)


def describe(rk):
    """Fetch one entry's page and write its wikipedia.yaml; returns what was written."""
    v = entries.view(rk)
    q = tables.request("wikipedia", v)
    title, year, pinned_page = q["title"], q["year"], q["page"]
    if pinned_page:
        s = summary(pinned_page)
        page, note = (s["title"], "") if s else (None, f"pinned page {pinned_page!r} not found")
    else:
        page, s, note = pick(title, year, search(title, year))
    w = {"fp": tables.fp("wikipedia", v), "page": page, "description": s["extract"] if s else None, "note": note}
    entries.write(rk, "wikipedia", w)
    return w


def fetch(todo):
    """describe() each rkey, printing progress; returns the rkeys fetched."""
    done = []
    for i, rk in enumerate(todo, 1):
        v = entries.view(rk)
        r = v["parsed"]
        try:
            w = describe(rk)
        except Exception as e:
            print(f"  !! #{r['number']} {r['title']}: {e}", file=sys.stderr)
            continue
        done.append(rk)
        note = w["note"]
        mark = "X" if not w["page"] else "P" if "pin.page" in v["override"] else "?" if note else " "
        print(f"  [{mark}] {i}/{len(todo)} #{r['number']} {r['title']} ({r['year']}) -> {w['page']}"
              + (f"  [{note}]" if note else ""), file=sys.stderr)
        time.sleep(1.0)
    return done


def refresh(rks):
    """Refetch the pages of these rows that are ready and stale, e.g. after an override changed
    their title, year or pin; returns the rkeys fetched."""
    return fetch([rk for rk in rks
                  if stage.ready("wikipedia", v := entries.view(rk)) and not tables.fresh("wikipedia", v)])


def main():
    a = stage.args(__doc__)
    todo = stage.select("wikipedia", a)
    print(f"{len(todo)} to fetch", file=sys.stderr)
    fetch(todo)
    stage.finish("wikipedia")


if __name__ == "__main__":
    main()
