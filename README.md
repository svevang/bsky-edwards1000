# Edwards 1000 Sixties Movies

[Edward the Movie Buff](https://bsky.app/profile/midgetmoxie.bsky.social)
(`did:plc:uidrgvgtx2nbdb2mkhiacpus`) is posting 1000 must-watch films from the 1960s on Bluesky,
one per post, tagged
[#Edwards1000SixtiesMovies](https://bsky.app/hashtag/Edwards1000SixtiesMovies). This repo
downloads those posts, reads each film's number, title and year, matches it to its Wikipedia
article, checks the match, and writes the result to [`movies.csv`](movies.csv).

## Run it

Needs [uv](https://docs.astral.sh/uv/). The review step also needs the `claude` CLI.

```sh
./step1_build.sh          # download posts, fetch Wikipedia intros, render movies.csv
./step2_llm_review.sh     # LLM review: flags and fixes mismatches, re-renders movies.csv
uv run python status.py   # how many posts are ok, pending or need review
```

Each step only redoes rows whose inputs changed. To correct a row by hand, use
`./fix.py <number|rkey> title|year|page|dismiss|unset ...`; see `./fix.py -h`.

## Layout

- `entries/<rkey>/`: one directory per post, holding the post, its Wikipedia match, its review
  and any hand corrections. `schema.yaml` describes the files.
- `tables.py`, `entries.py`: the persisted state and its rules.
- `s0_download.py`, `s2_descriptions.py`, `s3_llm_review.py`: the pipeline stages.
- `docs/shaping/`: design notes.
