---
status: draft
updated: 2026-10-02
---

# Shape: Pipeline Architecture

## Problem Statement

The movie pipeline (see `../01-movie-pipeline/movie-pipeline.md`) turns one author's hashtag
posts into a table of films and lets me correct it by hand. It works, and the job is staying
the same. This document records the pipeline's current shape as the baseline for reorganising
its structure without changing what it does for me.

---

## Requirements

| ID  | Requirement | Priority |
|-----|-------------|----------|
| R0  | Turn the author's hashtag posts into a table of films: number, title, year, synopsis | Must |
| R1  | A rerun only does work for rows that are new or whose inputs changed | Must |
| R2  | Each step leaves a file I can open, so a bad row can be traced to the step that broke it | Must |
| R3  | A hand correction survives reruns until the input it corrects changes | Must |
| R4  | Rows the automation is unsure about are surfaced to me | Must |
| R5  | An interrupted run picks up where it stopped | Should |
| R6  | I can run any step on a chosen subset of rows | Should |
| R7  | The free automated steps run separately from the paid LLM review | Should |
| R8  | I can see where every row stands, and one film's trail through every step | Should |
| R9  | A correction is one command, not a file edit | Should |

---

## Shape A: Staged Files, One Script per Stage (current)

| Part | Mechanism |
|------|-----------|
| A1   | **Stage files** |
| A1.1 | The download writes the raw posts as a list; every later stage writes a dict keyed by post rkey |
| A1.2 | Each stage reads the files before it and writes only its own |
| A1.3 | Saves are atomic (write temp, rename); long stages save as they go: Wikipedia every 10 rows, LLM every batch |
| A1.4 | The final CSV is a pure join of the stage files, rebuilt on every run |
| A2   | **Incremental selection** |
| A2.1 | Each entry stores a fingerprint of the input fields it was computed from |
| A2.2 | A row is processed when it has no entry, its fingerprint is stale, or it is forced/redone |
| A2.3 | A pinned entry is skipped while its fingerprint matches; a stage that re-applies its pin (Wikipedia's chosen page) opts in to redo |
| A2.4 | Each stage defines its own fingerprint inputs and row-number accessor inline |
| A2.5 | The download always rescans the whole repo; selection starts at parsing |
| A3   | **Stages** |
| A3.1 | Each stage is a standalone script with its own main: load inputs, select rows, process, save, report |
| A3.2 | Parse: post text → number, title, year, qualifier |
| A3.3 | Describe: title and year → Wikipedia page, URL, intro (network, throttled) |
| A3.4 | Review: parsed + described rows → LLM verdict per row, sent in batches through the `claude` CLI |
| A3.5 | Join: all stage files → CSV plus an attention list |
| A4   | **Orchestration** |
| A4.1 | Stage order lives in two shell scripts: build (download, parse, describe, join) and review (review, join) |
| A4.2 | The same flags are passed to every stage; each stage parses them through a shared helper |
| A4.3 | The correction command reruns stages as subprocesses, restricted to one row |
| A5   | **Reporting** |
| A5.1 | Every stage prints status counts through a shared helper, then its own list of rows to review |
| A5.2 | The status command re-derives each stage's fingerprint to count stale rows, and prints one row's entry from every stage file |
| A6   | **Corrections** |
| A6.1 | One command per kind of fix writes a pinned entry into the stage that owns the field |
| A6.2 | Unpinning drops every pin on the row and recomputes it; a dismissed LLM verdict is deleted so it is reviewed again |

---

## Fit Check

| ID | Requirement | A |
|----|-------------|---|
| R0 | Posts → table of films | ✅ |
| R1 | Only new/changed rows reprocessed | ✅ |
| R2 | Inspectable file per step | ✅ |
| R3 | Hand corrections survive reruns | ✅ |
| R4 | Unsure rows surfaced | ✅ |
| R5 | Interrupted runs resume | ✅ |
| R6 | Run a step on a subset | ✅ |
| R7 | LLM review separate | ✅ |
| R8 | Row status and per-film trail | ✅ |
| R9 | One-command corrections | ✅ |

Legend: ✅ = satisfied, ❌ = not satisfied, – = not applicable

---

## UI Affordances

The tool is a terminal workflow; places are commands and files.

| #   | Place | Affordance | Description | Wires Out |
|-----|-------|------------|-------------|-----------|
| U1  | Terminal | `step1_build.sh [--skip-download] [flags]` | Download, parse, describe, join; prints next steps | N1, N7, N8, N10 |
| U2  | Terminal | `step2_llm_review.sh [flags]` | Review, then join | N9, N10 |
| U3  | Terminal | stage flags `--force` `--redo N` `--only N` `--limit K` | Passed to every stage, or to one stage run directly | N5 |
| U4  | Terminal | `status.py` | Counts per stage, unprocessed and stale rows | N2, N6, N11 |
| U5  | Terminal | `status.py N` | One film's entry in every stage file, raw post first | N2 |
| U6  | Terminal | `fix.py N title\|year\|page\|dismiss\|unpin` | Pins a correction and reruns that row | N12 |
| U7  | Terminal | Per-stage review list | Rows needing attention, printed after each stage | |
| U8  | `movies.csv` | Final table | Film fields plus per-stage status and notes | |
| U9  | Stage file (editor) | `stages/NN_*.json` | Every entry, readable and hand-editable | |

---

## Non-UI Affordances

| #   | Component | Affordance | Description | Wires Out |
|-----|-----------|------------|-------------|-----------|
| N1  | `bsky_tag_dl.py` | `main(handle, tag, outfile)` | Resolves handle → PDS, lists every post, keeps the tagged ones | N13 |
| N2  | `stage.py` | `load(path, default)` / `save(path, data)` | Read a stage file; atomic write | |
| N3  | `stage.py` | `fp(*parts)` | 12-char hash of a row's input fields | |
| N4  | `stage.py` | `select_todo(a, inputs, existing, input_fp, number_of, redo_pinned)` | Rows to process under fingerprints, pins and flags | N3 |
| N5  | `stage.py` | `args(desc)` | Shared flag parser | |
| N6  | `stage.py` | `report(name, outputs, inputs)` | Status counts to stderr | |
| N7  | `s1_parse.py` | `main()` / `parse(text)` | Posts → parsed rows; fp = post text | N2, N4, N6, N14 |
| N8  | `s2_descriptions.py` | `main()` / `search` / `pick` / `summary` | Parsed → Wikipedia rows; fp = title, year | N2, N4, N6, N15 |
| N9  | `s3_llm_review.py` | `main()` / `ask(rows)` | Parsed + described → verdicts via `claude -p`; fp = title, year, description | N2, N4, N6, N16 |
| N10 | `s4_join.py` | module body | Stage files → `movies.csv` and attention list | N2, U8 |
| N11 | `status.py` | stale count | Recomputes stage 2 and 3 fingerprints inline | N3 |
| N12 | `fix.py` | `main()` | Writes a pinned entry, then runs N7/N8 with `--only N` and N10 | N2, N7, N8, N10 |
| N13 | storage | `stages/00_posts.json` | Raw posts (list) | |
| N14 | storage | `stages/01_parsed.json` | number, title, year, qualifier, status, pin | |
| N15 | storage | `stages/02_descriptions.json` | page, url, description, status, pin | |
| N16 | storage | `stages/03_llm_review.json` | ok, status, issue, suggestions, pin | |

---

## Slices

Defined once a refactor shape is chosen.

| #  | Slice | Builds | Proves | Depends On |
|----|-------|--------|--------|------------|
| S1 | | | | |

---

## Wiring Diagram

```
┌─ TRIGGER: ./step1_build.sh ───────────────────────────────────────────┐
│                                                                       │
│  N1 bsky_tag_dl ──► N13 00_posts.json                                 │
│  N7 s1_parse ─ N5 args ─ N4 select_todo(fp = text) ──► N14 01_parsed  │
│  N8 s2_descriptions ─ N4 select_todo(fp = title, year)                │
│      └─► Wikipedia API ──► N15 02_descriptions                        │
│  N10 s4_join (N14 + N15 + N16) ──► U8 movies.csv, U7 attention list   │
└───────────────────────────────────────────────────────────────────────┘

┌─ TRIGGER: ./step2_llm_review.sh ──────────────────────────────────────┐
│                                                                       │
│  N9 s3_llm_review ─ N4 select_todo(fp = title, year, description)     │
│      └─► claude -p (batches of 60) ──► N16 03_llm_review              │
│  N10 s4_join ──► U8 movies.csv                                        │
└───────────────────────────────────────────────────────────────────────┘

┌─ TRIGGER: ./fix.py N <cmd> ───────────────────────────────────────────┐
│                                                                       │
│  N12 fix ──► pinned entry in N14 | N15 | N16                          │
│      └─► N7 / N8 --only N (subprocess) ──► N10 s4_join                │
└───────────────────────────────────────────────────────────────────────┘

┌─ PLACE: status.py ────────────────────────────────────────────────────┐
│                                                                       │
│  U4 counts ─ N6 report + N11 stale (re-derives N8/N9 fingerprints)    │
│  U5 trail  ─ N13 → N14 → N15 → N16 for one rkey                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Eliminated Shapes

| Shape | Name | Why Eliminated |
|-------|------|----------------|

---

## Open Questions

- [ ] Fingerprint inputs are defined inside each stage and again in `status.py` (N11). Should each stage declare its inputs once, where status and fix can read them?
- [ ] Stage order lives in two shell scripts and in `fix.py`. Should one definition of the pipeline drive build, review, status and fix?
- [ ] Each stage repeats the same load → select → process → save → report loop. Should a stage be reduced to its per-row function?
- [ ] Stages print review lists to a mix of stdout and stderr. What belongs on each?
- [ ] Should the download join incremental selection, or stay a full rescan?
