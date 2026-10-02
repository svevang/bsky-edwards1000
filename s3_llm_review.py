#!/usr/bin/env python3
"""Stage 3: parsed.yaml + wikipedia.yaml -> review.yaml

Sends rows in batches to Claude (via the `claude` CLI) and asks it to flag rows whose
title, year and description disagree, or whose title looks mangled. Rows are only
re-reviewed when their title/year/description change; each batch is saved as it returns.
--limit K reviews just K rows so you can check the output early; --redo N re-asks about one row.

Manual: `./fix.py N dismiss "reason"` dismisses a flag with a review.ok override.
"""
import json
import subprocess
import sys
import entries
import schema
import stage

BATCH = 60

PROMPT = """You are checking a dataset of 1960s films parsed from social-media posts and joined to
Wikipedia intros. For each row below, decide whether it is CONSISTENT: the description is clearly
about a film with that title (allowing for missing "The", accents, alternate/foreign titles, and
minor punctuation), and the film's release year matches `year` (allow +/-1 for
festival-vs-general release; note it if it differs at all). Also flag titles that look mangled
(truncated, review text leaked in, wrong casing artifacts) or descriptions about a non-film
(album, play, person, franchise, remake from another decade).

Reply with ONLY a JSON array, no prose, of the problem rows:
[{"number": <int>, "issue": "<short reason>", "suggested_title": "<or null>", "suggested_year": <int or null>}]
Return [] if all rows are consistent.

Rows:
"""


def ask(rows):
    lines = [json.dumps({"number": int(r["number"]), "title": r["title"], "year": int(r["year"]),
                         "wikipedia_page": (r["url"] or "").rsplit("/", 1)[-1],
                         "description": (r["description"] or "")[:350]}, ensure_ascii=False) for r in rows]
    out = subprocess.run(["claude", "-p", "--output-format", "text"],
                         input=PROMPT + "\n".join(lines), capture_output=True, text=True, check=True).stdout
    start, end = out.find("["), out.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply:\n{out[:500]}")
    return json.loads(out[start:end + 1])


def main():
    a = stage.args(__doc__)
    todo = stage.select("review", a)
    views = {rk: entries.view(rk) for rk in todo}
    inputs = {rk: {"rkey": rk, **{k: v["parsed"][k] for k in ("number", "title", "year")},
                   **{k: v["wikipedia"].get(k) for k in ("url", "description")}} for rk, v in views.items()}
    print(f"{len(todo)} to review in batches of {BATCH}", file=sys.stderr)
    for i in range(0, len(todo), BATCH):
        batch = [inputs[rk] for rk in todo[i:i + BATCH]]
        print(f"  batch {i // BATCH + 1}/{-(-len(todo) // BATCH)} (#{batch[0]['number']}-#{batch[-1]['number']})...",
              file=sys.stderr, end=" ", flush=True)
        problems = {p["number"]: p for p in ask(batch)}
        for r in batch:
            p = problems.get(int(r["number"])) or {}
            entries.write(r["rkey"], "review", {"fp": schema.fp("review", views[r["rkey"]]), "ok": not p,
                                                **{k: p.get(k) for k in ("issue", "suggested_title", "suggested_year") if p}})
            entries.update_status(r["rkey"])
        print(f"{len(problems)} flagged", file=sys.stderr)
    stage.finish("review")

    flagged = sorted((v for rk in entries.list_entries() if entries.read(rk, "status") != "deleted"
                      and "review" in (v := entries.view(rk)) and schema.applies("review", v)
                      and schema.unsure("review", v)),
                     key=lambda v: v["parsed"]["number"] or 0)
    for v in flagged:
        r = v["review"]
        sug = ", ".join(f"{k.replace('suggested_', '')}={val!r}" for k in ("suggested_title", "suggested_year")
                        if (val := r.get(k)) not in (None, ""))
        print(f"  #{v['parsed']['number']:>3} {v['parsed']['title']:40} {r.get('issue')}" + (f"  -> {sug}" if sug else ""))


if __name__ == "__main__":
    main()
