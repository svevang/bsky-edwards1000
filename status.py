#!/usr/bin/env python3
"""Where is every row in the pipeline? `uv run python status.py [N]` shows one row's full trail."""
import json
import sys
import stage

posts = {p["url"].rsplit("/", 1)[-1]: p for p in stage.load(stage.POSTS, default=[])}
files = [("01_parsed", stage.load(stage.PARSED, default={})),
         ("02_descriptions", stage.load(stage.DESCRIPTIONS, default={})),
         ("03_llm_review", stage.load(stage.LLM_REVIEW, default={}))]

if len(sys.argv) > 1:  # trail for one watchlist number
    n = int(sys.argv[1])
    rk = next((rk for rk, r in files[0][1].items() if r["number"] == n), None)
    if not rk:
        sys.exit(f"#{n} not in 01_parsed")
    print(f"00_posts:\n  {json.dumps(posts[rk]['text'][:300], ensure_ascii=False)}")
    for name, data in files:
        e = data.get(rk)
        print(f"{name}:" + ("\n  " + json.dumps({k: v for k, v in e.items() if k not in ('text_head', 'fp')},
                                                ensure_ascii=False, indent=2).replace("\n", "\n  ") if e else "  (not yet)"))
    sys.exit()

print(f"00_posts: {len(posts)}")
for name, data in files:
    stage.report(name, data, posts)
    missing = len(posts) - len(data)
    stale = sum(1 for rk in data if rk in posts and files[0][1].get(rk) and name != "01_parsed"
                and data[rk].get("fp") != (stage.fp(files[0][1][rk]["title"], files[0][1][rk]["year"]) if name == "02_descriptions"
                                           else stage.fp(files[0][1][rk]["title"], files[0][1][rk]["year"], files[1][1].get(rk, {}).get("description"))))
    if stale:
        print(f"  {stale} rows have stale inputs (will be redone on next run)")
