#!/usr/bin/env python3
"""Where is every post in the pipeline?

  uv run python status.py       counts by status, computed now (hand edits to override.yaml show)
  uv run python status.py N     one film's trail: post, each stage file with its overrides, freshness
"""
import json
import sys
import entries
import schema
import stage


def short(value, n=200):
    s = repr(value)
    return s if len(s) <= n else s[:n] + "…"


def counts():
    live, out_of_date, overridden = {}, 0, 0
    for rk in entries.list_entries():
        stored, v = entries.read(rk, "status"), entries.view(rk)
        s = "deleted" if stored == "deleted" else entries.compute_status(v)
        live[s] = live.get(s, 0) + 1
        out_of_date += s != stored
        overridden += bool(v["override"])
    print(f"{sum(live.values())} entries: {live}")
    print(f"  {overridden} with overrides, {live.get('deleted', 0)} deleted")
    if out_of_date:
        print(f"  {out_of_date} stored statuses are out of date; any stage run refreshes them")


def trail(n):
    rk = entries.find(n)
    v, o = entries.view(rk), entries.read(rk, "override") or {}
    if "post" in v:
        print(f"#{n}  rkey={rk}  {v['post']['url']}")
        print(f"post:\n  {json.dumps(v['post']['text'][:300], ensure_ascii=False)}")
    else:
        print(f"#{n}  rkey={rk}\npost: (no post.yaml)")
    for name in schema.stage_files():
        raw = entries.read(rk, name)
        state = ("not applicable" if not schema.applies(name, v) else "missing" if raw is None
                 else "fresh" if stage.fresh(name, v) else "stale")
        print(f"{name}: ({state})")
        fields = [k for k in (raw or {}) if k != "fp"]
        fields += [k.split(".", 1)[1] for k in o if k.startswith(f"{name}.") and k.split(".", 1)[1] not in fields]
        for k in fields:
            key = f"{name}.{k}"
            computed = short(raw[k]) if k in (raw or {}) else "(none)"
            print(f"  {k}: {computed}" + (f" -> {short(o[key])}  (override)" if key in o else ""))
    print(f"status: {entries.compute_status(v)} (stored: {entries.read(rk, 'status')})")


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].isdigit():
        sys.exit(__doc__)
    trail(int(sys.argv[1])) if len(sys.argv) > 1 else counts()
