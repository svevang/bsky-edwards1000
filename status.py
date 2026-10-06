#!/usr/bin/env python3
"""Where is every post in the pipeline?

  uv run python status.py       counts by status
  uv run python status.py N     one film's trail: post, each stage file with its overrides, freshness
                                (N is a watchlist number or an rkey)
"""
import json
import sys
import entries
import parse
import tables


def short(value, n=200):
    s = repr(value)
    return s if len(s) <= n else s[:n] + "…"


def counts():
    counts, overridden = entries.status_counts()
    print(f"{sum(counts.values())} entries: {counts}")
    print(f"  {overridden} with overrides, {counts.get('deleted', 0)} deleted")


def trail(ref):
    rk = entries.find(ref)
    v = entries.view(rk)
    o = v["override"]
    n = tables.lookup(v, "parsed.number") or "?"
    if "post" in v:
        print(f"#{n}  rkey={rk}  {v['post']['url']}")
        print(f"post:\n  {json.dumps(v['post']['text'][:300], ensure_ascii=False)}")
    else:
        print(f"#{n}  rkey={rk}\npost: (no post.yaml)")
    for name in tables.TABLES:
        if name == "parsed":
            raw = parse.parse(v["post"]["text"]) if "post" in v else None
            state = "computed" if raw else "no post"
        else:
            raw = entries.read(rk, name)
            state = ("not applicable" if not tables.applies(name, v) else "missing" if raw is None
                     else "fresh" if tables.fresh(name, v) else "stale")
        print(f"{name}: ({state})")
        fields = [k for k in (raw or {}) if k != "fp"]
        fields += [k.split(".", 1)[1] for k in o if k.startswith(f"{name}.") and k.split(".", 1)[1] not in fields]
        for k in fields:
            key = f"{name}.{k}"
            computed = short(raw[k]) if k in (raw or {}) else "(none)"
            print(f"  {k}: {computed}" + (f" -> {short(o[key])}  (override)" if key in o else ""))
    for k in o:
        if k.split(".", 1)[0] not in tables.TABLES:
            print(f"{k}: {short(o[k])}  (override)")
    if "dismissed" in o:
        print(f"  {'holds' if tables.dismissed(v) else 'lapsed: the row has changed since'}")
    print(f"status: {entries.compute_status(v)}")


if __name__ == "__main__":
    trail(sys.argv[1]) if len(sys.argv) > 1 else counts()
