"""The tables of an entry: what each is computed from, when it applies and when it is unsure.

An entry's view is a dict like {"post": ..., "parsed": ..., "wikipedia": ..., "review": ...,
"override": ...} (see entries.view). `parsed` is computed from the post on every read.
`wikipedia` and `review` are memos of network and LLM calls: each stored row carries `fp`, a
hash of the table's VERSION and the exact request that produced it, so a row is recomputed
only when what it would send, or the code that answers it, changes.

Bump a table's VERSION whenever you change code that changes its answers.
"""
import hashlib
import json

VERSION = {
    "parsed": 1,     # parse.py
    "wikipedia": 1,  # s2_descriptions.py: search, pick and fetch
    "review": 1,     # s3_llm_review.py: PROMPT and how replies become review rows
}
TABLES = ("parsed", "wikipedia", "review")  # pipeline order
STORED = ("wikipedia", "review")  # memos with a file and an fp

# Review suggestion -> the override key it sets.
FIXES = {"suggested_page": "pin.page", "suggested_title": "parsed.title", "suggested_year": "parsed.year"}


def lookup(v, ref):
    """A file.field reference in a view; None when the file or field is missing."""
    file, field = ref.split(".", 1)
    return (v.get(file) or {}).get(field)


def request(name, v):
    """What the table's row is computed from: the post text, the Wikipedia query, the LLM row."""
    p = v["parsed"]
    if name == "parsed":
        return v["post"]["text"]
    if name == "wikipedia":
        return {"title": p["title"], "year": p["year"], "page": v["override"].get("pin.page")}
    w = v["wikipedia"]
    r = {"number": int(p["number"]), "title": p["title"], "posted_title": p.get("raw_title_line"),
         "year": int(p["year"]), "wikipedia_page": w.get("page"),
         "description": (w.get("description") or "")[:350]}
    r.update({k: n for k, n in (("parse_note", p.get("note")), ("wikipedia_note", w.get("note"))) if n})
    fixes = {k: val for k, val in v["override"].items() if k in FIXES.values()}
    return {**r, "overrides": fixes} if fixes else r


def fp(name, v):
    payload = json.dumps([VERSION[name], request(name, v)], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def fresh(name, v):
    """The row exists and, for a stored table, was computed from the current request."""
    return name in v and (name not in STORED or v[name].get("fp") == fp(name, v))


def applies(name, v):
    """Every entry with a post is parsed; Wikipedia and the review need a watchlist number."""
    return "post" in v and (name == "parsed" or lookup(v, "parsed.number") is not None)


def unsure(name, v):
    row = v.get(name) or {}
    if name == "review":
        return not row.get("ok")
    cleared = applies("review", v) and fresh("review", v) and v["review"].get("ok")
    return bool(row.get("note")) and not cleared


def all_fresh(v, before=None):
    """Every applicable table (before `before`, when given) is fresh."""
    names = TABLES[:TABLES.index(before)] if before else TABLES
    return all(fresh(n, v) for n in names if applies(n, v))
