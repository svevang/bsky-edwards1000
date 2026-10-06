"""Entry store: one directory per post under entries/, one YAML file per stage.

Files are named by stage without the extension ("post", "wikipedia", "review", "override");
schema.yaml describes them and tables.py holds their rules. An empty deleted.yaml marks a post gone from the
download. Status is never stored: compute_status(view) works it out from the files.
Every write goes through a temp file and os.replace, so a file is never half-written.

view(rk) is what stages, status and outputs read: the post, its parse (computed, never
stored) and the stage files, with override.yaml applied over them. The overridden keys are view["override"].keys().
"""
import os
import sys
import tempfile
import yaml
import tables
from parse import parse

ENTRIES = "entries"


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, s):
    if any(c in s for c in "\x85\u2028\u2029"):
        style = '"'  # other styles would load these back as plain line breaks
    else:
        style = "|" if "\n" in s else None  # PyYAML falls back to quoted when | can't hold s
    return dumper.represent_scalar("tag:yaml.org,2002:str", s, style=style)


_Dumper.add_representer(str, _str)


def path(rk, name):
    return os.path.join(ENTRIES, rk, f"{name}.yaml")


def list_entries():
    try:
        return sorted(d.name for d in os.scandir(ENTRIES) if d.is_dir() and not d.name.startswith("."))
    except FileNotFoundError:
        return []


def read(rk, name, default=None):
    try:
        with open(path(rk, name), encoding="utf-8") as f:
            return yaml.load(f, Loader=yaml.CSafeLoader)
    except FileNotFoundError:
        return default


def dump(data):
    return yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False,
                     default_flow_style=False, width=float("inf"))


def write(rk, name, data):
    save_text(path(rk, name), dump(data))


def save_text(p, text):
    """Write text to p through a temp file in the same directory and os.replace."""
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", prefix=f".{os.path.basename(p)}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.chmod(tmp, 0o644)  # mkstemp creates files 0600
        os.replace(tmp, p)
    except BaseException:
        os.unlink(tmp)
        raise


def view(rk):
    """{"post", stage files...: as read, absent when missing; "parsed": parse(post text);
    "override": override.yaml}. Each override table.field replaces that field, but only in a
    table that exists; other keys (pin.page, dismissed) are left to the code that reads them."""
    v = {n: d for n in ("post", *tables.STORED) if (d := read(rk, n)) is not None}
    if "post" in v:
        v["parsed"] = parse(v["post"]["text"])
    v["override"] = read(rk, "override") or {}
    for key, value in v["override"].items():
        file, _, field = key.partition(".")
        if file in tables.TABLES and file in v:
            v[file] = {**v[file], field: value}
    return v


def compute_status(v):
    if "post" not in v or not tables.all_fresh(v):
        return "pending"
    return "needs_review" if tables.flagged(v) else "ok"


def deleted(rk):
    return os.path.exists(path(rk, "deleted"))


def set_deleted(rk, gone):
    if gone:
        save_text(path(rk, "deleted"), "")
    elif deleted(rk):
        os.remove(path(rk, "deleted"))


def status_counts():
    """{status: number of entries}, plus how many entries have overrides."""
    counts, overridden = {}, 0
    for rk in list_entries():
        v = view(rk)
        s = "deleted" if deleted(rk) else compute_status(v)
        counts[s] = counts.get(s, 0) + 1
        overridden += bool(v["override"])
    return counts, overridden


def live():
    """(rkey, view) for every entry that isn't deleted."""
    return ((rk, view(rk)) for rk in list_entries() if not deleted(rk))


def find(number):
    """Watchlist number -> rkey, from parsed.number with overrides; deleted entries are skipped."""
    rks = [rk for rk, v in live() if tables.lookup(v, "parsed.number") == number]
    if len(rks) != 1:
        sys.exit(f"#{number}: {'not in entries' if not rks else f'{len(rks)} posts share this number: {rks}'}")
    return rks[0]


def set_override(rk, key, value):
    """Set one file.field override; the stage file keeps its computed value underneath."""
    write(rk, "override", {**(read(rk, "override") or {}), key: value})


def unset_override(rk, keys=None):
    """Remove these override keys (all when None); override.yaml is deleted once empty."""
    o = read(rk, "override") or {}
    o = {k: v for k, v in o.items() if keys is not None and k not in keys}
    if o:
        write(rk, "override", o)
    elif os.path.exists(path(rk, "override")):
        os.remove(path(rk, "override"))
