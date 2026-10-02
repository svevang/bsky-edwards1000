---
status: ready
selected_shape: B
updated: 2026-10-03
---

# Shape: Persisted State

## Problem Statement

The movie pipeline (see `../02-pipeline-architecture/pipeline-architecture.md`) keeps all of its
state in files: one JSON file per stage plus the final CSV, all committed to git. Each stage file
mixes computed results, freshness fingerprints and my hand corrections, so a fix can overwrite the
value it replaced or vanish when its input changes, and a row's story is spread across four files.
This shape moves state into one directory per post, described by a schema, with hand corrections
kept apart as overrides.

---

## Requirements

| ID  | Requirement | Priority |
|-----|-------------|----------|
| R0  | Every step's results are kept in a file I can open, read and diff | Must |
| R1  | Slow or paid work (Wikipedia, LLM) is never repeated for rows whose inputs are unchanged | Must |
| R2  | When an upstream value changes, only the affected downstream rows are redone | Must |
| R3  | A hand correction survives every rerun until I remove it, and is flagged in the output | Must |
| R4  | I can tell which values were corrected and what they replaced | Should |
| R5  | I can undo a correction and get the automated value back | Should |
| R6  | An interrupted run keeps most of its finished work | Must |
| R7  | A save never leaves a half-written file | Must |
| R8  | A row is identified the same way in every file | Must |
| R9  | I can refer to a film by its watchlist number | Should |
| R10 | An entry carries enough context to trace a bad value without opening upstream files | Should |
| R11 | I can see what changed between runs | Should |
| R12 | Later stages rerun without downloading again | Should |
| R13 | I can see which rows are stale without running a stage | Should |
| R14 | Every output (CSV now, HTML later) can be rebuilt from saved state without the network | Should |
| R15 | State is plain files in the repo, with no database or service to run | Should |
| R16 | When a post disappears, its entry is kept and marked deleted | Should |
| R17 | The LLM review fixes the problems it finds; I only see the rows it couldn't fix | Must |

---

## Shape B: Entry Directories with a Schema

| Part | Mechanism |
|------|-----------|
| B1   | **Schema** |
| B1.1 | `schema.yaml` at the repo root lists each file in an entry: the stage that writes it, its fields, and its fingerprint inputs; it also defines the status vocabulary |
| B1.2 | Stages, status and fix read fingerprint inputs from the schema |
| B1.3 | Every state file is YAML, read and written with PyYAML; the repo is a uv project |
| B2   | **Entry directories** |
| B2.1 | One directory per post under `entries/`, named by post rkey |
| B2.2 | The watchlist number lives in `parsed.yaml`; commands look entries up by it |
| B2.3 | The set of entries is the directory listing |
| B2.4 | `entries/` is committed to git |
| B3   | **Entry files** |
| B3.1 | `post.yaml`: the raw post as downloaded |
| B3.2 | `parsed.yaml`: number, title, year, qualifier, raw title line |
| B3.3 | `wikipedia.yaml`: chosen page, URL and downloaded intro |
| B3.4 | `review.yaml`: LLM verdict, issue and suggestions |
| B3.5 | `override.yaml`: corrections, by hand or by the LLM review, as keys and values; stage files keep the computed values beneath them |
| B3.6 | `status.yaml`: one line holding the post's status |
| B4   | **Freshness** |
| B4.1 | Every stage file carries the `fp` of the inputs it was computed from |
| B4.2 | A stage is done for an entry when its file exists and its `fp` matches the current inputs |
| B4.3 | Overrides are applied over the stage files when the entry is read; later stages read the overridden values |
| B4.4 | Overrides stay until removed; outputs flag every overridden key |
| B5   | **Writes** |
| B5.1 | Each file is written on its own through a temp file and rename, as soon as its row finishes |
| B5.2 | Outputs (`movies.csv` now, HTML later) are build artifacts rendered from the entries, leaving out deleted entries |
| B6   | **Status** |
| B6.1 | One status per post, from one shared vocabulary: `pending`, `needs_review`, `ok`, `deleted` |
| B6.2 | After each stage, the status is recomputed from the entry's files: `pending` when a stage is missing or stale, `needs_review` when a stage is unsure, otherwise `ok`; a fresh passing review, which sees the parse and Wikipedia warnings, clears them |
| B6.3 | When a post is gone from the download, its entry is kept and its status set to `deleted`; stages skip deleted entries |
| B7   | **LLM resolution** |
| B7.1 | For each problem it finds, the review proposes a fix: the Wikipedia page, title or year |
| B7.2 | A proposed page is fetched by exact title, or found by search when that title doesn't exist; it is kept only when it is a single film from within a year of the row's year |
| B7.3 | Kept fixes are written to `override.yaml`; an existing key is replaced only when the LLM is certain |
| B7.4 | The LLM never sets `review.ok` or `review.dismissed`; dismissing stays a hand decision |
| B7.5 | Fixed rows are refetched and reviewed again in the same run, for up to two more rounds; rows still flagged stay `needs_review` |

---

## Fit Check

| ID  | Requirement | Current (A) | B |
|-----|-------------|-------------|---|
| R0  | Readable, diffable file per step | ✅ | ✅ |
| R1  | No repeated slow/paid work | ✅ | ✅ |
| R2  | Only affected downstream rows redone | ✅ | ✅ |
| R3  | Corrections persist until removed, flagged in output | ❌ | ✅ |
| R4  | Corrected values and what they replaced | ❌ | ✅ |
| R5  | Corrections can be undone | ✅ | ✅ |
| R6  | Interrupted runs keep finished work | ✅ | ✅ |
| R7  | No half-written files | ❌ | ✅ |
| R8  | Same row identity in every file | ✅ | ✅ |
| R9  | Rows addressable by watchlist number | ✅ | ✅ |
| R10 | Entries traceable without upstream files | ✅ | ✅ |
| R11 | Changes visible between runs | ✅ | ✅ |
| R12 | Rerun without redownloading | ✅ | ✅ |
| R13 | Stale rows visible without a run | ✅ | ✅ |
| R14 | Outputs rebuildable offline | ✅ | ✅ |
| R15 | Plain files, no service | ✅ | ✅ |
| R16 | Disappeared posts marked deleted | ❌ | ✅ |
| R17 | LLM review fixes what it finds | ❌ | ✅ |

Legend: ✅ = satisfied, ❌ = not satisfied, – = not applicable

R3 (A): a pin is replaced when its input changes (A5.5).

R4 (A): a parse fix keeps the replaced title or year only in `note` text; a page fix discards the previous page (A5.2, A5.3).

R16 (A): entries for a vanished post stay with no marker (A6.4).

R7 (A): the downloader and the join write `00_posts.json` and `movies.csv` in place (A6.3).

---

## UI Affordances

| #  | Place | Affordance | Description | Wires Out |
|----|-------|------------|-------------|-----------|
| U1 | Editor / git | `entries/<rkey>/*.yaml` | One post's files: post, parsed, wikipedia, review, override, status | |
| U2 | Editor / git | `schema.yaml` | Entry files, their fields, fingerprint inputs and the status vocabulary | |
| U3 | Terminal | `fix.py N title\|year\|page\|dismiss\|unset [key]` | Sets or removes an override, then reruns the stages it affects | N12 |
| U4 | Terminal | `status.py [N]` | Counts posts by status; with N, prints the entry's files and overrides | N3, N6, N14 |
| U5 | `movies.csv` | Output table | One row per post, with an `overrides` column listing overridden keys | |
| U6 | Terminal | `step1_build.sh` / `step2_llm_review.sh` + stage flags | Same entry points and flags as today | N7–N11 |

---

## Non-UI Affordances

| #   | Component | Affordance | Description | Wires Out |
|-----|-----------|------------|-------------|-----------|
| N1  | schema | `load_schema()` | Reads `schema.yaml`: files, fields, fingerprint inputs, status vocabulary | |
| N2  | entry store | `list_entries()` / `read(rk, file)` / `write(rk, file, data)` | Directory listing; YAML read; atomic YAML write | |
| N3  | entry store | `view(rk)` | Stage files merged, `override.yaml` applied over them; returns values plus overridden keys | N2 |
| N4  | schema | `fp(file, view)` | Fingerprint of a file's inputs, as listed in the schema | N1 |
| N5  | stages | `select_todo(file, ...)` | Entries whose file is missing or whose stored `fp` differs from N4; skips `deleted`; honors stage flags | N2, N3, N4 |
| N6  | status | `update_status(rk)` | Recomputes the one-line `status.yaml`: `deleted`, `pending`, `needs_review` or `ok` | N3, N4, N2 |
| N7  | download | `bsky_tag_dl.py` | Writes `post.yaml` per post; sets `deleted` on entries whose post is gone | N2, N6 |
| N8  | parse | `s1_parse.py` | `post.yaml` → `parsed.yaml` | N5, N2, N6 |
| N9  | describe | `s2_descriptions.py` | Title, year and any `wikipedia.page` override → `wikipedia.yaml` | N5, N2, N6 |
| N10 | review | `s3_llm_review.py` | Title, year, description → `review.yaml`, batched through `claude -p`; then N15 on flagged rows | N5, N2, N6, N15 |
| N11 | render | `render_csv()` | Entry views, except deleted ones → `movies.csv`, written atomically | N3, U5 |
| N12 | fix | `set_override(rk, key, value)` / `unset_override(rk, key)` | Edits `override.yaml`; keys are `file.field` (`parsed.title`, `wikipedia.page`, `review.ok`) | N2, N8–N11 |
| N13 | migration | `migrate.py` | One-off: `stages/*.json` → `entries/`; pins become overrides; computed values regenerated by rerunning parse | N2, N6, N8 |
| N14 | entry store | `find(number)` | Watchlist number → rkey via `parsed.yaml`; refuses duplicates | N3 |
| N15 | review | `resolve(rows)` | Asks for fixes, checks proposed pages, writes overrides, refetches and re-reviews; up to two more rounds | N9, N12 |

---

## Slices

| #   | Slice | Builds | Proves | Depends On |
|-----|-------|--------|--------|------------|
| S1  | **Schema and entry store** | N1, N2, N4, U2 | R7, R15 | |
| S1.1 | Write `schema.yaml` for the six entry files and the status vocabulary | U2, N1 | | |
| S1.2 | YAML read, atomic write, directory listing | N2 | R7 | |
| S1.3 | Fingerprints driven by the schema | N4 | | |
| S1.4 | Step scripts run stages through `uv run` | | | |
| S2  | **Entry view and status** | N3, N6, N14 | R4, R9 | |
| S2.1 | Merged view with overrides applied | N3 | R4 | |
| S2.2 | Status computation | N6 | | |
| S2.3 | Lookup by watchlist number | N14 | R9 | |
| S3  | **Migrate existing state** | N13, U1 | R0, R8, R10 | |
| S3.1 | Convert posts, parsed, wikipedia and review entries into `entries/` | N13 | R0, R8 | |
| S3.2 | Turn the 1 parse pin and 7 page pins into overrides; rerun parse to restore computed values | N13 | R4 | |
| S4  | **Render outputs from entries** | N11, U5 | R3, R14 | |
| S4.1 | `movies.csv` from entry views, matching today's file plus the `overrides` column | N11, U5 | R14 | |
| S5  | **Stages on entries** | N5, N7–N10, U6 | R1, R2, R6, R11, R12, R16 | |
| S5.1 | Selection from per-file `fp`, skipping deleted entries | N5 | R1, R2 | |
| S5.2 | Download writes `post.yaml` and marks vanished posts deleted | N7 | R12, R16 | |
| S5.3 | Parse, describe and review read views and write their own entry file per row | N8–N10 | R6 | |
| S6  | **Fix and status commands** | N12, U3, U4 | R3, R5, R13 | |
| S6.1 | `fix.py` sets and unsets overrides, then reruns affected stages | N12, U3 | R3, R5 | |
| S6.2 | `status.py` counts by status and prints one entry | U4 | R13 | |
| S7  | **Remove the stage files** | | | |
| S7.1 | Delete `stages/`, the JSON path constants in `stage.py`, and `s4_join.py` | | | |
| S8  | **LLM resolves what it flags** | N10, N15 | R17 | |
| S8.1 | Prompt asks for a page/title/year fix and a certainty for each flagged row | N15 | | |
| S8.2 | Check proposed pages, write overrides, refetch, re-review up to two more rounds | N15 | R17 | |

---

## Wiring Diagram

```
┌─ TRIGGER: ./step1_build.sh, ./step2_llm_review.sh ─────────────────────────┐
│                                                                            │
│  N7 download ──► N2 write post.yaml ──► N6 status (deleted if post gone)   │
│  N8 parse    ─ N5 select(N4 fp) ─ N3 view ──► N2 write parsed.yaml ─► N6   │
│  N9 describe ─ N5 select(N4 fp) ─ N3 view ──► N2 write wikipedia.yaml ─► N6│
│  N10 review  ─ N5 select(N4 fp) ─ N3 view ──► N2 write review.yaml ─► N6   │
│  N11 render  ─ N3 view (not deleted) ──► U5 movies.csv                     │
│                          N1 schema.yaml feeds N4 and N6                    │
└────────────────────────────────────────────────────────────────────────────┘

┌─ TRIGGER: ./fix.py N <cmd> ────────────────────────────────────────────────┐
│                                                                            │
│  N14 find(N) ──► N12 set/unset ──► N2 write override.yaml                  │
│      └─► N8–N10 --only N ──► N6 status ──► N11 render                      │
└────────────────────────────────────────────────────────────────────────────┘

┌─ PLACE: status.py ─────────────────────────────────────────────────────────┐
│                                                                            │
│  U4 counts ─ N2 read status.yaml for every entry                           │
│  U4 N      ─ N14 find(N) ─ N3 view (files + overrides)                     │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Eliminated Shapes

| Shape | Name | Why Eliminated |
|-------|------|----------------|
| A | Per-Stage JSON Files with Inline Pins (current) | Pins overwrite computed values and vanish when inputs change; writes can leave half-written files; vanished posts go unmarked (fit check R3, R4, R7, R16). Kept below as the migration source. |

### Shape A: Per-Stage JSON Files with Inline Pins (current)

| Part | Mechanism |
|------|-----------|
| A1   | **Layout** |
| A1.1 | One file per stage under `stages/`, numbered in pipeline order; the final table is `movies.csv` at the repo root |
| A1.2 | Stage files are pretty-printed UTF-8 JSON; all state files are committed to git |
| A2   | **Identity** |
| A2.1 | The post rkey (last segment of the post URL) keys every stage dict |
| A2.2 | The raw posts file is a list; readers derive the rkey from each post's URL |
| A2.3 | The watchlist number is a field on each entry; commands look rows up by number and refuse when two rows share one |
| A3   | **Entries** |
| A3.1 | Each entry holds the stage's computed fields plus bookkeeping: `fp`, `status`, `note`, optional `pinned` |
| A3.2 | Downstream entries copy `number`, `title` and `year` from upstream for readability |
| A3.3 | Each stage has its own status vocabulary: parse `ok` `needs_review` `pinned`; describe `ok` `needs_review` `not_found` `pinned`; review `ok` `flagged` `dismissed` |
| A4   | **Freshness** |
| A4.1 | `fp` is a 12-character SHA-1 of the input fields the entry was computed from |
| A4.2 | Inputs per stage: parse = post text; describe = title, year; review = title, year, description |
| A4.3 | The fingerprint recipe lives in each stage and is recomputed independently by the status and fix commands |
| A5   | **Hand corrections (pins)** |
| A5.1 | A pin is stored inside the computed entry: `pinned: true` plus the corrected value |
| A5.2 | Parse pins overwrite `title` or `year` in place; the previous value is kept only in the `note` text |
| A5.3 | Describe pins store the chosen `page`; the stage refetches its description from that page |
| A5.4 | Review dismissals set `ok: true`, `status: dismissed` and a `dismissed` reason; the join also reads a hand-set `ok: true` on a flagged entry as dismissed |
| A5.5 | When a pinned entry's input fingerprint changes, the stage recomputes the row and the pin is replaced |
| A6   | **Writes** |
| A6.1 | Every save rewrites the whole file through a temp file and rename |
| A6.2 | Long stages checkpoint as they go: describe every 10 rows, review every batch; parse saves once at the end |
| A6.3 | The downloader overwrites the posts file directly; the join writes the CSV directly |
| A6.4 | Entries are only added or replaced; a post that disappears from the download keeps its downstream entries |
| A6.5 | Writers take no lock; the fix command saves its pin, then runs stages that reload and save the same files |
| A7   | **Derived output** |
| A7.1 | `movies.csv` is a pure join of the stage files, rebuilt on every run and committed alongside them |

---

## Open Questions

