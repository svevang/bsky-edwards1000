---
status: ready
selected_shape: A
updated: 2026-09-18
---

# Shape: Movie Pipeline

## Problem Statement

A Bluesky user is posting reviews of 1000 films from the 1960s under one hashtag. I want a
clean table of those films — number, title, year, and a synopsis — that I can rebuild as new
posts appear without redoing or re-checking work already done. Parsing is heuristic and
lookups are fuzzy, so I need to see where any row went wrong and correct it once.

---

## Requirements

| ID  | Requirement | Priority |
|-----|-------------|----------|
| R0  | Get title and year for every post carrying the hashtag | Must |
| R1  | Attach a synopsis to each film | Must |
| R2  | Re-running only processes new or changed posts | Must |
| R3  | Every step leaves an artifact I can inspect, so a bad row can be traced to the step that broke it | Must |
| R4  | I can correct a row by hand and the correction survives re-runs | Must |
| R5  | Rows the automation is unsure about are surfaced to me, not silently kept | Must |
| R6  | An LLM reviews the rows for errors the heuristics can't see | Should |
| R7  | The automated work runs to completion and stops for me to check before the LLM step | Should |
| R8  | I can run a step on a subset of rows to check its output before committing to all of them | Should |
| R9  | Titles normalized to canonical form (restore dropped "The", etc.) | Should |

---

## Shape A: Staged Files

| Part | Mechanism |
|------|-----------|
| A1   | **One artifact per stage** |
| A1.1 | Each stage reads the previous stage's file and writes its own; both are dicts keyed by post id |
| A1.2 | A stage's entry records a fingerprint of the inputs it was computed from; the stage skips entries whose fingerprint still matches |
| A1.3 | An entry marked pinned is a manual correction; it is kept unless its inputs change or it is explicitly redone |
| A1.4 | The final table is a pure join of the stage files, always rebuilt |
| A2   | **Parsing** |
| A2.1 | The post's `N/1000:` line gives the number; the next non-empty line is the title |
| A2.2 | The watchlist runs 100 films per year in order, so the number determines the year |
| A2.3 | Year suffixes and parenthetical qualifiers are split out of the title |
| A2.4 | A title that isn't all-caps, or a missing number line, marks the row for review |
| A3   | **Synopsis lookup** |
| A3.1 | Search Wikipedia for the title and year; take the intro paragraph of the best page |
| A3.2 | A page is trusted only if it is about a film, its title matches exactly, and its stated release year matches; otherwise the best guess is kept and marked for review |
| A3.3 | Throttling from Wikipedia is waited out, not failed |
| A3.4 | The chosen page's title, with its disambiguator removed, is the canonical title |
| A4   | **LLM review** |
| A4.1 | Rows are sent in batches to a model, which flags any where title, year and synopsis disagree or the title looks mangled |
| A4.2 | Runs through the user's existing Claude CLI login; no API key |
| A5   | **Operator control** |
| A5.1 | Two entry points: an automated build that stops with instructions, and the LLM review |
| A5.2 | Every stage accepts force, redo-by-number, and limit-count flags |
| A5.3 | A status command shows counts per stage and the full trail of one film through every stage |

---

## Fit Check

| ID | Requirement | Current | A | B |
|----|-------------|---------|---|---|
| R0 | Title and year per post | ❌ | ✅ | ✅ |
| R1 | Synopsis per film | ❌ | ✅ | ✅ |
| R2 | Only new/changed rows reprocessed | ❌ | ✅ | ❌ |
| R3 | Inspectable artifact per step | ❌ | ✅ | ❌ |
| R4 | Manual fixes survive re-runs | ❌ | ✅ | ✅ |
| R5 | Unsure rows surfaced | ❌ | ✅ | ✅ |
| R6 | LLM review | ❌ | ✅ | ❌ |
| R7 | Automated part stops before LLM step | ❌ | ✅ | – |
| R8 | Run a step on a subset | ❌ | ✅ | ❌ |
| R9 | Canonical titles | ❌ | ✅ | ❌ |

Legend: ✅ = satisfied, ❌ = not satisfied, – = not applicable

---

## UI Affordances

The tool is a terminal workflow; "places" are commands and files the operator opens.

| #  | Place | Affordance | Description | Wires Out |
|----|-------|------------|-------------|-----------|
| U1 | Terminal | `step1_build.sh [--skip-download] [flags]` | Runs download, parse, synopsis, join; prints flagged rows and what to do next | N1, N3, N5, N9 |
| U2 | Terminal | `step2_llm_review.sh [flags]` | Runs LLM review, then join; prints flagged rows | N8, N9 |
| U3 | Terminal | `status.py` | Counts per stage, unprocessed and stale rows | N2 |
| U4 | Terminal | `status.py <number>` | One film's entry in every stage file, raw post first | N2 |
| U5 | Stage file (editor) | `"pinned": true` on an entry | Marks a hand edit to keep: corrected title/year, a chosen Wikipedia `page`, or a dismissed LLM flag | N2 |
| U6 | `movies.csv` | Final table | number, title, canonical_title, year, qualifier, description, wikipedia, per-stage status/notes | |
| U7 | Any stage | `--force`, `--redo N,N`, `--limit K` | Redo all, redo named films, or process only K rows | N2 |

---

## Non-UI Affordances

| #  | Component | Affordance | Description | Wires Out |
|----|-----------|------------|-------------|-----------|
| N1 | `bsky_tag_dl.py` | `main()` | Walks the user's repo, keeps posts with the tag, writes `stages/00_posts.json` | |
| N2 | `stage.py` | `load / save / fp / args / select_todo / report` | Shared stage contract: file paths, fingerprinting, flag parsing, todo selection honoring pins | |
| N3 | `s1_parse.py` | `parse(text)` | Number, title, year, qualifier, status, note, plus raw title line for provenance | N2 |
| N4 | `stages/01_parsed.json` | entry per post | Output of N3 | |
| N5 | `s2_descriptions.py` | `search / candidates / score_page / pick / summary` | One Wikipedia API call per film; scores candidates; honors pinned page | N2 |
| N6 | `s2_descriptions.py` | `get()` with 429 backoff | Sleeps for Retry-After instead of failing | |
| N7 | `stages/02_descriptions.json` | entry per film | page, url, description, status, note | |
| N8 | `s3_llm_review.py` | `ask(rows)` | Batches rows into a prompt to `claude -p`; parses JSON list of problems | N2 |
| N9 | `s4_join.py` | join | Merges 01/02/03 into `movies.csv`; derives canonical_title from the Wikipedia page title; lists rows needing attention | N2 |
| N10 | `stages/03_llm_review.json` | entry per film | ok/flagged, issue, suggested title/year | |

---

## Slices

| #    | Slice | Builds | Proves | Depends On |
|------|-------|--------|--------|------------|
| S1   | **Title and year table** | N1, N3, N9 | R0, R5 | – |
| S1.1 | Parse number/title/year from posts | N3 | R0 | |
| S1.2 | Flag non-title-looking lines and missing numbers | N3 | R5 | |
| S2   | **Synopses** | N5, N6, N7 | R1, R5 | S1 |
| S2.1 | Wikipedia search and scoring | N5 | R1 | |
| S2.2 | Rate-limit backoff | N6 | | |
| S3   | **Staged artifacts** | N2, N4, N7, U5, U7 | R2, R3, R4, R8 | S2 |
| S3.1 | Fingerprint-based skip, pins, force/redo/limit | N2 | R2, R4, R8 | |
| S3.2 | Status and per-film trail | U3, U4 | R3 | |
| S4   | **LLM review** | N8, N10, U2 | R6, R7 | S3 |
| S4.1 | Segment the wrappers: build stops, review is separate | U1, U2 | R7 | |
| S5   | **Canonical titles** | N9 | R9 | S2 |

---

## Wiring Diagram

```
┌─ TRIGGER: ./step1_build.sh ──────────────────────────────────────────────┐
│                                                                          │
│  N1 bsky_tag_dl.py ──► stages/00_posts.json                              │
│      └─► N3 s1_parse.py ─ N2 select_todo ──► N4 stages/01_parsed.json    │
│              └─► N5 s2_descriptions.py ─ N2 select_todo                  │
│                      └─► N6 get() (Wikipedia) ──► N7 02_descriptions.json│
│                              └─► N9 s4_join.py ──► U6 movies.csv         │
│                                      └─► prints flagged rows, next steps │
└──────────────────────────────────────────────────────────────────────────┘

┌─ TRIGGER: ./step2_llm_review.sh ─────────────────────────────────────────┐
│                                                                          │
│  N8 s3_llm_review.py ─ N2 select_todo(01 + 02)                           │
│      └─► claude -p ──► N10 stages/03_llm_review.json                     │
│              └─► N9 s4_join.py ──► U6 movies.csv                         │
└──────────────────────────────────────────────────────────────────────────┘

┌─ PLACE: operator fixing a row ───────────────────────────────────────────┐
│                                                                          │
│  U4 status.py <n> (trail)                                                │
│      └─► U5 edit stage file, "pinned": true                              │
│              └─► U7 --redo n ──► N2 select_todo honors pin ──► U6        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Eliminated Shapes

| Shape | Name | Why Eliminated |
|-------|------|----------------|
| B | Single script | One parser that also joined descriptions into the CSV and was run twice per build. No stage boundaries: nothing to inspect between steps, and every run re-derived everything. |
| C | TMDB lookup | Richer metadata, but needs an API key and gives nothing Wikipedia doesn't already: the page title is the canonical title and the intro is the synopsis. |

---

## Open Questions

- [ ] Year is the author's placement (100 per year), not the release date; *Dead Ringer* (#360) is 1963 by position, 1964 on Wikipedia. Keep source order or trust lookup?
- [ ] Posts #106 and #204 are absent from the download (deleted or untagged). Leave the gaps, or fill from another source?
- [ ] Should LLM-suggested fixes be applied automatically as pins, or always by hand?
