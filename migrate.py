#!/usr/bin/env python3
"""One-off: stages/*.json -> entries/<rkey>/*.yaml

Parse is rerun so parsed.yaml holds the automated values; hand corrections become
override.yaml keys: parse pins -> parsed.<field>, page pins -> wikipedia.page, dismissed
reviews -> review.ok (+ review.dismissed). Hand-accepted description notes are kept as notes.
Stage files are only written for rows the old stage produced. A row whose old fp was already
stale keeps that fp, so the new stages redo it. Refuses to touch an existing entries/
unless --force, which rebuilds it from scratch.
"""
import argparse
import shutil
import sys
import entries
import schema
import stage
from s1_parse import parse

PARSE_FIELDS = ("number", "title", "year", "qualifier", "raw_title_line")


def fields(name, row):
    """The schema's fields for this file, in schema order, that the row has (fp excluded)."""
    return {k: row[k] for k in schema.load_schema()["files"][name]["fields"] if k != "fp" and k in row}


def build(rk, post, old, d, v, problems):
    """All files for one entry, in memory."""
    files = {"post": fields("post", post)}
    override = files["override"] = {}
    if not old:
        return files
    new = parse(post["text"])
    if old.get("pinned"):
        override.update({f"parsed.{k}": old[k] for k in PARSE_FIELDS if old[k] != new[k]})
    elif any(old[k] != new[k] for k in (*PARSE_FIELDS, "note")):
        problems.append(f"#{old['number']} {rk}: parse differs from 01_parsed")
    files["parsed"] = {"fp": schema.fp("parsed", {"post": post}), **fields("parsed", new)}

    if d:
        w = fields("wikipedia", d)
        if d.get("pinned"):
            override["wikipedia.page"] = d["page"]
        if d["status"] == "not_found":
            w.update(page=None, note=d["note"] or "no film page found")
        elif d["note"]:  # status set ok by hand over a note: keep the automated note
            w["note"] = d["note"].removeprefix("accepted: ")
        files["wikipedia"] = w
    if v:
        files["review"] = {k: x for k, x in fields("review", v).items() if k != "dismissed"}
        if v.get("ok") and v.get("status") in ("dismissed", "flagged"):
            files["review"]["ok"] = False  # the LLM's verdict; the dismissal is an override
            override["review.ok"] = True
            if v.get("dismissed"):
                override["review.dismissed"] = v["dismissed"]

    # fp: new recipe on the overridden view when the old fp was current, else keep the old one
    title, year = old["title"], old["year"]
    for name, row, old_fp in (("wikipedia", d, d and stage.fp(title, year)),
                              ("review", v, v and d and stage.fp(title, year, d.get("description")))):
        if row:
            fresh = row["fp"] == old_fp
            fp = schema.fp(name, entries.overlay(files)) if fresh else row["fp"]
            files[name] = {"fp": fp, **files[name]}
            if not fresh:
                problems.append(f"#{old['number']} {rk}: {name} was stale; kept old fp")
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    if entries.list_entries() and not a.force:
        sys.exit(f"{entries.ENTRIES}/ already has entries; --force rebuilds it from scratch")

    posts = {p["url"].rsplit("/", 1)[-1]: p for p in stage.load(stage.POSTS)}
    parsed = stage.load(stage.PARSED)
    descs = stage.load(stage.DESCRIPTIONS, default={})
    reviews = stage.load(stage.LLM_REVIEW, default={})
    for name, data in (("01_parsed", parsed), ("02_descriptions", descs), ("03_llm_review", reviews)):
        if extra := set(data) - set(posts):
            sys.exit(f"{name} has rows with no post: {sorted(extra)}")
    if extra := (set(descs) | set(reviews)) - set(parsed):
        sys.exit(f"descriptions/reviews have rows with no parse: {sorted(extra)}")

    problems = []
    plan = {rk: build(rk, post, parsed.get(rk), descs.get(rk), reviews.get(rk), problems)
            for rk, post in posts.items()}

    shutil.rmtree(entries.ENTRIES, ignore_errors=True)
    overrides, statuses = {}, {}
    for rk, files in plan.items():
        for name, data in files.items():
            if data:
                entries.write(rk, name, data)
        for k in files["override"]:
            overrides[k] = overrides.get(k, 0) + 1
        s = entries.update_status(rk)
        statuses[s] = statuses.get(s, 0) + 1

    print(f"{len(plan)} entries written to {entries.ENTRIES}/")
    print(f"overrides: {overrides}")
    print(f"status: {statuses}")
    for line in problems:
        print(f"  !! {line}")


if __name__ == "__main__":
    main()
