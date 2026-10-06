"""Parse a post's text into its watchlist number, title and year.

Posts look like:
    #Edwards1000SixtiesMovies
    123/1000:
    THE TITLE
    <review...>
The watchlist is 100 films per year in order, so year = 1960 + (number-1)//100.

parse() is cheap and deterministic, so nothing stores its result: entries.view() calls it
on every read, and hand fixes (`./fix.py N title "..."`) are overrides applied over it.
`raw_title_line` is kept so a bad parse can be traced.
"""
import re

NUM_RE = re.compile(r"^\s*(\d+)\s*/\s*[12]000\s*:?\s*$", re.M)  # tolerate "200/2000" typo
YEAR_SUFFIX_RE = re.compile(r"^(.*?)\s*\(?(?:\b(19[5-7]\d)|'([5-7]\d))\)?\s*$")  # "... 1960" / "... '60"


def year_for(number):
    return 1960 + (number - 1) // 100


def parse(text):
    out = {"number": None, "title": None, "year": None, "qualifier": "",
           "raw_title_line": "", "note": ""}
    m = NUM_RE.search(text)
    if not m:
        out.update(note="no N/1000 line")
        return out
    out["number"] = int(m.group(1))
    out["year"] = year_for(out["number"])

    lines = [l.strip() for l in text[m.end():].split("\n") if l.strip()]
    if not lines:
        out.update(note="no title line")
        return out
    out["raw_title_line"] = lines[0]
    title = re.sub(r"\b([A-Za-z])'\s+", r"\1'", lines[0])  # "L' ECLISSE" -> "L'ECLISSE"

    ym = YEAR_SUFFIX_RE.match(title)
    if ym and ym.group(1):
        title = ym.group(1).strip()
        yr = int(ym.group(2)) if ym.group(2) else 1900 + int(ym.group(3))
        out["qualifier"] = str(yr)
        if yr != out["year"]:
            out["note"] = f"title says {yr}, position implies {out['year']}"

    qm = re.match(r"^(.*?)\s*\((.*)\)\s*$", title)  # "(1962 version)", "(aka ...)"
    if qm:
        title, out["qualifier"] = qm.group(1).strip(), qm.group(2).strip()

    if title.replace("Mc", "MC") != title.upper() or len(title) > 80:
        out["note"] = out["note"] or "title line doesn't look like a title"
    out["title"] = title
    return out
