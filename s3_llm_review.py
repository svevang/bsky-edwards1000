#!/usr/bin/env python3
"""Stage 3: parsed title/year + wikipedia.yaml -> review.yaml, and override.yaml for what it fixes

Sends rows in batches to Claude (via the `claude` CLI) and asks it to flag rows whose
title, year and description disagree, or whose title looks mangled, and to propose a fix for
each: the right Wikipedia page, title or year, and whether it is certain. A proposed page is
fetched and kept only when it exists and its intro is about a single film; a title or year
only when certain; an existing override is replaced only when certain. Kept fixes go to
override.yaml, the row's page is refetched and the row reviewed again, for up to two more
rounds. Rows still flagged after that stay needs_review. Only a person dismisses a flag. Flagged rows from earlier runs whose suggestions weren't applied are
rechecked (Wikipedia only).

Rows are only re-reviewed when the row sent (tables.request) changes, or tables.VERSION["review"]
is bumped: bump it when you change PROMPT or how replies become review rows; each batch is saved as it
returns. --limit K reviews just K rows so you can check the output early; --redo N re-asks
about one row. These apply to the first round.

Manual: `./fix.py N dismiss "reason"` dismisses a flag until the row sent for review changes;
`./fix.py N unset KEY` drops a fix you don't want.
"""
import json
import re
import subprocess
import sys
import entries
import s2_descriptions as s2
import stage
import tables
from tables import FIXES

BATCH = 60
ROUNDS = 2  # extra review rounds for rows the review fixed
FIELDS = ("issue", *FIXES, "certain")

PROMPT = """You are checking a dataset of 1960s films parsed from social-media posts and joined to
Wikipedia intros. For each row below, decide whether it is CONSISTENT: the description is clearly
about a film with that title (allowing for missing "The", accents, alternate/foreign titles, and
minor punctuation), and the film's release year matches `year` (allow +/-1 for
festival-vs-general release; note it if it differs at all). Also flag titles that look mangled
(truncated, review text leaked in, wrong casing artifacts) or descriptions about a non-film
(album, play, person, franchise, remake from another decade).

`posted_title` is the title line exactly as posted. `overrides`, when present, are corrections
already made to the row (`pin.page`: the Wikipedia page to use; `parsed.title`, `parsed.year`); the
row already shows them.
`parse_note` and `wikipedia_note`, when present, are warnings from the automatic parse and page
match (e.g. "title mismatch"). Judge them: if the row is consistent anyway (an alternate or
foreign title, punctuation, a festival year), it is not a problem row and the warning is cleared.

For each problem row, propose a fix where you can:
- suggested_page: the exact title of the English Wikipedia article about this film, e.g.
  "Fun in Acapulco (film)", when the linked page is wrong or missing; otherwise null.
- suggested_title: only when the posted title itself is wrong (truncated, misspelled, missing
  punctuation). Never suggest one just to change case, or to swap the Wikipedia title in for an
  alternate or foreign title. Keep the post's ALL-CAPS style. Otherwise null.
- suggested_year: only when the film's year is actually wrong; otherwise null.
- certain: true only when you are sure every fix you suggest for the row is right. A title or
  year is only changed when you are certain, and replacing an existing correction in
  `overrides` requires you to be certain.

Reply with ONLY a JSON array, no prose, of the problem rows:
[{"number": <int>, "issue": "<short reason>", "suggested_page": "<or null>", "suggested_title": "<or null>",
  "suggested_year": <int or null>, "certain": <true or false>}]
Return [] if all rows are consistent.

Rows:
"""


def ask(rows):
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    out = subprocess.run(["claude", "-p", "--output-format", "text"],
                         input=PROMPT + "\n".join(lines), capture_output=True, text=True, check=True).stdout
    start, end = out.find("["), out.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply:\n{out[:500]}")
    return json.loads(out[start:end + 1])


def same(key, a, b):
    """Titles compare ignoring case; Wikipedia pages only ignore the first letter's case."""
    if key != "pin.page":
        return str(a).casefold() == str(b).casefold()
    a, b = (str(x).replace("_", " ").strip() for x in (a, b))
    return a[:1].upper() + a[1:] == b[:1].upper() + b[1:]


def found(page, year):
    """A proposed page that doesn't exist (e.g. "Fun in Acapulco (film)" for "Fun in Acapulco"):
    the first search hit with the same title that is a single film from around `year`."""
    want = bare(page)
    for c in s2.candidates(f'"{want}" {year} film'):
        if (bare(c["title"]) == want and s2.one_film(c["extract"]) and s2.film_title(c["title"])
                and near_year(c["extract"], year)):
            return c
    return None


def bare(page):
    """Page title without its trailing disambiguator, e.g. "Kid Galahad (1962 film)" -> "kid galahad"."""
    return s2.canonical(page).replace("_", " ").strip().casefold()


def near_year(extract, year):
    """The intro dates the film within a year of `year` ("is a 1963 American film", or the year nearby)."""
    lead = extract[:400]
    stated = re.search(r"\b(?:is|was) an? (19\d\d)\b", lead)
    if stated:
        return abs(int(stated.group(1)) - int(year)) <= 1
    return any(re.search(rf"\b{y}\b", lead) for y in (year - 1, year, year + 1))


def check(key, new, cur, overrides, certain, year):
    """(why it is skipped, or None to apply; the value to write) for one suggested fix."""
    if key == "parsed.year":
        new = int(new)
    if same(key, new, cur):
        return "already current", new
    if key in overrides and not certain:
        return f"keeps override {overrides[key]!r}, not certain", new
    if key != "pin.page":
        return (None if certain else "not certain"), new
    s = s2.summary(new) or found(new, year)
    if not s:
        return "page missing or a disambiguation", new
    if not (s2.one_film(s["extract"]) and s2.film_title(s["title"])):
        return "page is not about a single film", s["title"]
    if not near_year(s["extract"], year):
        return f"page is not about a film from around {year}", s["title"]
    return ("already current" if same(key, s["title"], cur) else None), s["title"]


def resolve(rk, v):
    """Write the flagged row's kept fixes to override.yaml and refetch its page; returns the fixes."""
    r, n = v["review"], v["parsed"]["number"]
    applied = []
    for field, key in FIXES.items():
        new, cur = r.get(field), v["wikipedia"].get("page") if key == "pin.page" else tables.lookup(v, key)
        if new in (None, ""):
            continue
        try:
            why, new = check(key, new, cur, v["override"], r.get("certain") is True, v["parsed"]["year"])
        except Exception as e:
            why = f"check failed: {e}"
        print(f"    #{n} {key}: {cur!r} -> {new!r}: {why or 'applied'}", file=sys.stderr)
        if not why:
            entries.set_override(rk, key, new)
            applied.append(f"{key.split('.', 1)[1]}={new!r}")
    if applied:
        s2.describe(rk)
    return applied


def fix_flagged(pairs):
    """Resolve each (rkey, view) whose fresh review is flagged with a suggestion: this run's
    flags, and earlier runs' left unfixed (e.g. by an interrupted run). Returns {rkey: fixes}."""
    fixed = {}
    for rk, v in pairs:
        if not (stage.ready("review", v) and tables.fresh("review", v) and tables.flagged(v)
                and any(v["review"].get(k) not in (None, "") for k in FIXES)):
            continue
        try:
            if applied := resolve(rk, v):
                fixed[rk] = applied
        except Exception as e:
            print(f"  !! #{v['parsed']['number']} {v['parsed']['title']}: {e}", file=sys.stderr)
    return fixed


def review(todo):
    """Ask about rows in batches, saving each batch's review.yaml as it returns."""
    for i in range(0, len(todo), BATCH):
        views = {rk: entries.view(rk) for rk in todo[i:i + BATCH]}
        rows = {rk: tables.request("review", v) for rk, v in views.items()}
        batch = list(rows.values())
        print(f"  batch {i // BATCH + 1}/{-(-len(todo) // BATCH)} (#{batch[0]['number']}-#{batch[-1]['number']})...",
              file=sys.stderr, end=" ", flush=True)
        problems = {p["number"]: p for p in ask(batch)}
        for rk, r in rows.items():
            p = problems.get(r["number"]) or {}
            entries.write(rk, "review", {"fp": tables.fp("review", views[rk]), "ok": not p,
                                         **{k: p.get(k) for k in FIELDS if p}})
        print(f"{len(problems)} flagged", file=sys.stderr)


def main():
    a = stage.args(__doc__)
    todo = stage.select("review", a)
    print(f"{len(todo)} to review in batches of {BATCH}", file=sys.stderr)
    fixed = {}
    for rnd in range(ROUNDS + 1):
        if rnd:
            print(f"round {rnd + 1}: re-reviewing {len(todo)} fixed rows", file=sys.stderr)
        review(todo)
        if rnd == ROUNDS:
            break
        new = fix_flagged(entries.live() if rnd == 0 else ((rk, entries.view(rk)) for rk in todo))
        for rk, f in new.items():
            fixed.setdefault(rk, []).extend(f)
        todo = list(new)  # resolve() refetched each one's page, so it's ready for review
        if not todo:
            break
    stage.finish("review")

    if fixed:
        print("fixed by the review:")
    fixed_views = {rk: entries.view(rk) for rk in fixed}
    for rk, v in sorted(fixed_views.items(), key=lambda kv: (kv[1]["parsed"]["number"] or 0, kv[0])):
        n = v["parsed"]["number"] or 0
        print(f"  #{n:>3} {v['parsed']['title']:40} {', '.join(fixed[rk])}  -> {entries.compute_status(v)}")


if __name__ == "__main__":
    main()
