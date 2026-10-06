---
status: ready
selected_shape: B
updated: 2026-10-06
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
| B1   | **Tables and schema** |
| B1.1 | `tables.py` defines each table: the request its row is computed from, when it applies, when it is unsure, and a code version |
| B1.2 | `schema.yaml` at the repo root is the data dictionary: each file in an entry, its fields, and the status vocabulary |
| B1.3 | Every state file is YAML, read and written with PyYAML; the repo is a uv project |
| B2   | **Entry directories** |
| B2.1 | One directory per post under `entries/`, named by post rkey |
| B2.2 | Commands find an entry by watchlist number or by rkey |
| B2.3 | The set of entries is the directory listing |
| B2.4 | `entries/` is committed to git |
| B3   | **Entry files** |
| B3.1 | `post.yaml`: the post's uri, cid and record as downloaded; its text, date and link are read from them |
| B3.2 | The parse (number, title, year, qualifier, raw title line, note) is computed from the post text on every read |
| B3.3 | `wikipedia.yaml`: chosen page and downloaded intro; the page link is built from the page title |
| B3.4 | `review.yaml`: the LLM's issue, suggestions and certainty; no issue means the row looks right |
| B3.5 | `override.yaml`: decisions by hand or by the LLM review: corrected fields, a pinned page, a dismissal and rejected values |
| B3.6 | `deleted.yaml`: an empty marker, present while the post is gone from the download |
| B4   | **Freshness** |
| B4.1 | Every stored stage file carries the `fp` of its table's code version and the exact request it made |
| B4.2 | A stage is done for an entry when its file exists and its `fp` matches the current request and version |
| B4.3 | Changing a stage's code means bumping its version, which redoes its rows |
| B4.4 | Corrected fields are applied over the computed ones when the entry is read; later stages read the corrected values |
| B4.5 | A pinned page is a stage input: Wikipedia fetches that page, and the entry shows the page it resolved to |
| B4.6 | Overrides stay until removed; outputs flag every override |
| B5   | **Writes** |
| B5.1 | Each file is written on its own through a temp file and rename, as soon as its row finishes, and only when its content changed |
| B5.2 | Outputs (`movies.csv` now, HTML later) are build artifacts rendered from the entries, leaving out deleted entries |
| B6   | **Status** |
| B6.1 | One status per post, from one shared vocabulary: `pending`, `needs_review`, `ok`, `deleted` |
| B6.2 | Status is computed from the entry's files whenever it is read: `pending` when a stage is missing or stale; `needs_review` when the last applicable table is unsure (the review once there is one, else the parse) and no dismissal holds; otherwise `ok` |
| B6.3 | A dismissal records the `fp` of the row it dismissed and lapses once that row changes |
| B6.4 | When a post is gone from the download, its entry is kept and `deleted.yaml` is written, making its status `deleted`; the marker is removed if the post comes back; stages skip deleted entries |
| B7   | **LLM resolution** |
| B7.1 | For each problem it finds, the review proposes a fix: the Wikipedia page, title or year |
| B7.2 | A proposed page is fetched by exact title, or found by search when that title doesn't exist; it is kept only when it is a single film from within a year of the row's year |
| B7.3 | Kept fixes are written to `override.yaml`; an existing key is replaced only when the LLM is certain; a value removed by hand is never set again |
| B7.4 | Only a person dismisses a flag |
| B7.5 | Review batches run a few at a time; once every batch is reviewed, each fresh flagged review with a suggestion is resolved, including flags left unfixed by earlier runs |
| B7.6 | Fixed rows are refetched and reviewed again in the same run, for up to two more rounds; rows still flagged stay `needs_review` |

---

## Data Model

Shape B is easiest to reason about as a small database. Each entry file name is a table, each
`entries/<rkey>/` directory is one row in every table it has a file for, and `rkey` is the primary
key everywhere. There is no database: the tables, views and predicates below describe what
`entries.py` and `tables.py` compute from the files.

### Tables

```
 BASE TABLES (facts; written only from outside: the download, a person, the LLM review)
 ┌──────────────────────────┐   ┌──────────────────────┐   ┌───────────────────────────────┐
 │ post                     │   │ deleted   (tombstone)│   │ override                      │
 │ rkey PK                  │   │ rkey PK              │   │ rkey PK                       │
 │ uri, cid, record         │   └──────────────────────┘   │ parsed.title, parsed.year     │
 └──────────────────────────┘                              │ pin.page                      │
                                                           │ dismissed {fp, reason}        │
                                                           │ rejected {key: [values]}      │
                                                           └───────────────────────────────┘

 MEMO TABLES (results of network/LLM calls; each row stores the hash of its request)
 ┌──────────────────────────┐   ┌───────────────────────────────┐
 │ wikipedia                │   │ review                        │
 │ rkey PK, fp              │   │ rkey PK, fp                   │
 │ page, description, note  │   │ issue, certain,               │
 └──────────────────────────┘   │ suggested_page/title/year     │
                                └───────────────────────────────┘
```

Base tables hold the real state. Wikipedia and the LLM don't answer the same way twice, so their
rows are memos keyed by the hash of their request (`fp`) and recomputed only when that hash
changes. Each table keeps one row per `rkey`, so changing an input and changing it back repeats
the call. The parse is deterministic and cheap, so it is a view, not a table.

### Views

```
 post_v   = post + text, createdAt (from record) + url (from uri)
 parsed   = parse(post_v.text)                                              (parse.py)
 X_v      = X with each 'X.field' override replacing that column            (entries.view)
 status   = CASE over freshness, unsure and dismissed, below                (entries.compute_status)
 movies   = SELECT … FROM post_v, parsed_v, wikipedia_v, review_v WHERE NOT deleted (render.py)
```

`X_v` starts from `X`: a correction only shows once its row exists. `pin.page`, `dismissed`
and `rejected` patch nothing; the code that needs them reads them.

### Freshness

One predicate covers every memo table: the stored hash matches the hash of the table's code
version and the request it would send now, built from the views.

```sql
fp(T)            :=  h(VERSION[T], request(T))
request(wikipedia) = (parsed_v.title, parsed_v.year, override['pin.page'])
request(review)    = the row sent to the LLM: number, title, posted title, year, page,
                     description, parse and page notes, and the overrides it may change
fresh(T)         :=  T.fp = fp(T)

applies(parsed)                      := post IS NOT NULL
applies(wikipedia) = applies(review) := parsed_v.number IS NOT NULL
```

Because `fp` is the hash of what is sent, the request and its hash can't drift apart. A code
change that changes answers bumps `VERSION[T]`, which makes every row of `T` stale.

Every memo row is in one of four states, and every stage moves rows the same way:

```
 NOT APPLICABLE ◀──▶ MISSING ──refresh──▶ FRESH ──request or version changes──▶ STALE ──refresh──▶ FRESH
```

A stage is `REFRESH <table> WHERE (missing OR stale) AND every earlier applicable table is fresh`
(`stage.select` and `stage.ready`), plus `--force`, `--redo` and `--only`.

### Status

```sql
CREATE VIEW status AS SELECT rkey, CASE
  WHEN rkey IN deleted                                   THEN 'deleted'
  WHEN post IS NULL OR NOT every applicable T is fresh   THEN 'pending'
  WHEN unsure(deciding) AND NOT dismissed                THEN 'needs_review'
  ELSE                                                        'ok'
END

deciding        := review if applies(review) else parsed
unsure(parsed)  := parsed_v.note  <> ''
unsure(review)  := review_v.issue IS NOT NULL
dismissed       := override['dismissed'].fp = fp(deciding)
```

The review is sent the parse and page notes, so once there is one its verdict replaces theirs.
A dismissal holds only for the row it dismissed.

### Writers

```
   Bluesky API                         person (fix.py)
       │ s0: MERGE                            │ UPSERT / DELETE
       ▼                                      ▼
   ┌──────┐ ┌───────┐                  ┌──────────┐
   │ post │ │deleted│                  │ override │◀───────────────────────────┐
   └──┬───┘ └───────┘                  └────┬─────┘                            │
      │ text → parsed (view)                │ patches parsed_v; pin.page       │ s3 resolve():
      ▼                                     │ is a wikipedia input             │ INSERT certain,
   ┌────────┐      title,year      ┌────────▼──┐  s2   description,note ┌──────┴─┐ checked fixes
   │ parsed │─────────────────────▶│ wikipedia │──────────────────────▶ │ review │
   └────────┘   (Wikipedia API)    └───────────┘   (claude CLI)          └────────┘
      │ title, year, raw_title_line, note ──────────────────────────────────▲
```

| Table | Written by | Operation |
|-------|-----------|-----------|
| `post` | `s0_download.py` | Upsert each downloaded post when it differs |
| `deleted` | `s0_download.py` | Insert for posts gone from a non-empty download; delete when they return |
| `wikipedia` | `s2_descriptions.py`; `s2.refresh` for `fix.py` and `s3` | Refresh missing or stale rows |
| `review` | `s3_llm_review.py` | Refresh missing or stale rows, a few batches at a time |
| `override` | `fix.py`; `s3` for `parsed.title`, `parsed.year`, `pin.page` | Upsert or delete keys; `dismissed` and `rejected` only by hand |

### The review cycle

Every other edge flows one way. The one cycle is `review → override → wikipedia → review`, and
`ROUNDS` bounds it:

```
 round 0:  REFRESH review WHERE stale          ─┐
           fix_flagged(all live rows)           │  INSERT override → s2.refresh(fixed rows)
 round 1:  REFRESH review WHERE now stale       │  → the review row is now stale
           fix_flagged(those rows)              │
 round 2:  REFRESH review WHERE now stale      ─┘  stop; rows still flagged stay needs_review
```

`check()` guards the insert: a title or year needs the LLM to be certain; a page must exist (or be
found by search) and be about a single film from within a year; an existing override is replaced
only when the LLM is certain; a value in `rejected` is never set.

### Consequences

- **No transactions.** Each file is written atomically, but nothing spans two files: `s3` writes
  `override` and then refreshes `wikipedia`. A crash in between leaves `wikipedia` stale, which is
  `pending`, which the next run refreshes (`step2_llm_review.sh` runs `s2` first for this). Every
  crash point is a valid state, so the `fp` check does the job a transaction would (R6, R7).
- **Undo is a delete.** Removing a correction exposes the computed value underneath; nothing has
  to be recomputed unless the key was part of a request (R5). Removing a page, title or year
  also records it in `rejected`, so the review doesn't put it back.
- **A version bump costs a full rerun of that stage.** Bump only for changes that change answers.
  A refactor that leaves answers alone, or a stored-format change applied to existing rows by a
  migration, keeps the version.

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

R0 (B): the parse has no file of its own; `movies.csv` carries its number, title, year, qualifier and note, and `status.py N` shows the whole parse.

---

## UI Affordances

| #  | Place | Affordance | Description | Wires Out |
|----|-------|------------|-------------|-----------|
| U1 | Editor / git | `entries/<rkey>/*.yaml` | One post's files: post, wikipedia, review, override, and the deleted marker | |
| U2 | Editor / git | `schema.yaml` | Entry files, their fields and the status vocabulary | |
| U3 | Terminal | `fix.py N\|rkey title\|year\|page\|dismiss\|unset [key]` | Sets or removes an override, then refetches what it made stale; `unset` records the removed value as rejected | N12 |
| U4 | Terminal | `status.py [N\|rkey]` | Counts posts by status; with N, prints the entry's parse, files, overrides and freshness | N3, N6, N14 |
| U5 | `movies.csv` | Output table | One row per post, with an `overrides` column listing override keys | |
| U6 | Terminal | `step1_build.sh` / `step2_llm_review.sh` + stage flags | Download, describe, render; review; `--only`/`--redo` take numbers or rkeys | N7, N9–N11 |

---

## Non-UI Affordances

| #   | Component | Affordance | Description | Wires Out |
|-----|-----------|------------|-------------|-----------|
| N1  | tables | `VERSION` / `request(name, v)` / `OVERRIDES` | Per table: code version and the request its row is computed from; the override keys and their types | |
| N2  | entry store | `list_entries()` / `read` / `write` / `remove` | Directory listing; YAML read; atomic YAML write, skipped when unchanged | |
| N3  | entry store | `view(rk)` | Post with derived text, date and link; the parse; stage files with corrections applied; cached until the entry is written | N2, N8 |
| N4  | tables | `fp` / `fresh` / `applies` / `unsure` / `deciding` / `dismissed` | Freshness from `h(version, request)`; the status predicates | N1 |
| N5  | stages | `select(name, ...)` / `ready(name, v)` | Entries whose file is missing or stale and whose earlier tables are fresh; skips `deleted`; honors stage flags | N3, N4 |
| N6  | status | `compute_status(v)` / `status_counts()` | Status from the view; counts for every entry | N3, N4 |
| N7  | download | `s0_download.py` | Fetches the posts with `bsky_tag_dl.fetch`; writes `post.yaml` per post; writes and removes `deleted.yaml` | N2 |
| N8  | parse | `parse(text)` | Post text → number, title, year, qualifier, raw title line, note | |
| N9  | describe | `s2_descriptions.py` / `refresh(rks)` | Title, year and `pin.page` → `wikipedia.yaml`; `refresh` refetches only the given rows that are stale | N5, N2 |
| N10 | review | `s3_llm_review.py` | Request rows → `review.yaml`, batched through `claude -p`, a few batches at once; then N15 on flagged rows | N5, N2, N15 |
| N11 | render | `render_csv()` / `report()` | Entry views, except deleted ones → `movies.csv`; lists rows to review, duplicate and missing numbers | N3, N6, U5 |
| N12 | fix | `set_override` / `unset_override` | Edits `override.yaml`: corrections, `pin.page`, `dismissed` with the dismissed row's `fp`, `rejected` on unset | N2, N9, N11 |
| N13 | migration | `migrate.py` | One-off: `stages/*.json` → `entries/`; pins become overrides | N2 |
| N14 | entry store | `find(ref)` | rkey, or watchlist number → rkey; refuses a number two posts share | N3 |
| N15 | review | `fix_flagged(rows)` / `resolve(rk, v)` | Resolves each fresh flagged review with a suggestion: checks proposed pages, writes overrides; the caller refreshes and re-reviews fixed rows, up to two more rounds | N9, N12 |

---

## Slices

| #   | Slice | Builds | Proves | Depends On |
|-----|-------|--------|--------|------------|
| S1  | **Schema and entry store** | N1, N2, N4, U2 | R7, R15 | |
| S1.1 | Write `schema.yaml` for the entry files and the status vocabulary | U2, N1 | | |
| S1.2 | YAML read, atomic write, directory listing | N2 | R7 | |
| S1.3 | Fingerprints of each stage's inputs | N4 | | |
| S1.4 | Step scripts run stages through `uv run` | | | |
| S2  | **Entry view and status** | N3, N6, N14 | R4, R9 | |
| S2.1 | Merged view with overrides applied | N3 | R4 | |
| S2.2 | Status computation | N6 | | |
| S2.3 | Lookup by watchlist number | N14 | R9 | |
| S3  | **Migrate existing state** | N13, U1 | R0, R8, R10 | |
| S3.1 | Convert posts, parsed, wikipedia and review entries into `entries/` | N13 | R0, R8 | |
| S3.2 | Turn the 1 parse pin and 7 page pins into overrides | N13 | R4 | |
| S4  | **Render outputs from entries** | N11, U5 | R3, R14 | |
| S4.1 | `movies.csv` from entry views, matching today's file plus the `overrides` column | N11, U5 | R14 | |
| S5  | **Stages on entries** | N5, N7–N10, U6 | R1, R2, R6, R11, R12, R16 | |
| S5.1 | Selection from per-file `fp`, skipping deleted entries | N5 | R1, R2 | |
| S5.2 | Download writes `post.yaml` and marks vanished posts deleted | N7 | R12, R16 | |
| S5.3 | Stages read views and write their own entry file per row | N8–N10 | R6 | |
| S6  | **Fix and status commands** | N12, U3, U4 | R3, R5, R13 | |
| S6.1 | `fix.py` sets and unsets overrides, then reruns affected stages | N12, U3 | R3, R5 | |
| S6.2 | `status.py` counts by status and prints one entry | U4 | R13 | |
| S7  | **Remove the stage files** | | | |
| S7.1 | Delete `stages/`, the JSON path constants in `stage.py`, and `s4_join.py` | | | |
| S8  | **LLM resolves what it flags** | N10, N15 | R17 | |
| S8.1 | Prompt asks for a page/title/year fix and a certainty for each flagged row | N15 | | |
| S8.2 | Check proposed pages, write overrides, refetch, re-review up to two more rounds | N15 | R17 | |
| S9  | **Simplify the data model** | N1, N3, N4, N8, N9, N12, N14 | R1, R2, R5, R9 | |
| S9.1 | Compute the parse on read; delete `parsed.yaml` | N3, N8 | | |
| S9.2 | Split `pin.page` from corrections that patch the view | N3, N9 | | |
| S9.3 | `tables.py`: `fp = h(version, request)`; restamp stored rows | N1, N4 | R1, R2 | |
| S9.4 | Status from the deciding table; dismissals carry the dismissed row's `fp`; `unset` records rejected values | N4, N12, N15 | R5 | |
| S9.5 | Derive post text, date and links; drop `review.ok` | N3 | | |
| S9.6 | Find entries by rkey or number | N14, U3, U4 | R9 | |
| S9.7 | One refresh helper; view cache; unchanged writes skipped; parallel review batches | N2, N3, N9, N10 | R1 | |

---

## Wiring Diagram

```
┌─ TRIGGER: ./step1_build.sh, ./step2_llm_review.sh ─────────────────────────┐
│                                                                            │
│  N7 download ──► N2 write post.yaml; deleted.yaml for gone posts           │
│  N9 describe ─ N5 select(N4 fp) ─ N3 view ──► N2 write wikipedia.yaml      │
│  N10 review  ─ N5 select(N4 fp) ─ N3 view ──► N2 write review.yaml         │
│      └─► N15 fix flagged ──► N12 override ──► N9 refresh ──► N10 again     │
│  N11 render  ─ N3 view (not deleted) + N6 status ──► U5 movies.csv         │
│            N3 view = post + N8 parse + stage files + overrides             │
│            N1 versions and requests feed N4                                │
└────────────────────────────────────────────────────────────────────────────┘

┌─ TRIGGER: ./fix.py N|rkey <cmd> ───────────────────────────────────────────┐
│                                                                            │
│  N14 find(ref) ──► N12 set/unset/dismiss ──► N2 write override.yaml        │
│      └─► N9 refresh if wikipedia went stale ──► N11 render                 │
└────────────────────────────────────────────────────────────────────────────┘

┌─ PLACE: status.py ─────────────────────────────────────────────────────────┐
│                                                                            │
│  U4 counts  ─ N6 status_counts()                                           │
│  U4 N|rkey  ─ N14 find(ref) ─ N3 view (parse, files, overrides)            │
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

- [ ] Should the parse also be written to a file (without an `fp`) so parse changes show in git
  diffs beyond the columns `movies.csv` carries (R0)?
