"""Entry store: one directory per post under entries/, one YAML file per stage.

Files are named by stage without the extension ("post", "parsed", "wikipedia", "review",
"override", "status"); schema.yaml describes them. status.yaml is one bare line.
Every write goes through a temp file and os.replace, so a file is never half-written.

view(rk) is what stages, status and outputs read: the stage files with override.yaml
applied over them. The overridden keys are view["override"].keys().
"""
import os
import sys
import tempfile
import yaml
import schema

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
            return yaml.safe_load(f)
    except FileNotFoundError:
        return default


def dump(data):
    return yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False,
                     default_flow_style=False, width=float("inf"))


def write(rk, name, data):
    save_text(path(rk, name), f"{data}\n" if name == "status" else dump(data))


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
    """{"post", stage files...: as read, absent when missing; "override": override.yaml}.
    Each override file.field replaces that field, but only in a stage file that exists."""
    files = {n: d for n in ("post", *schema.stage_files()) if (d := read(rk, n)) is not None}
    return overlay({**files, "override": read(rk, "override") or {}})


def overlay(files):
    """Apply files["override"] over copies of the other files, as view() does."""
    v = {**files, "override": files.get("override") or {}}
    for key, value in v["override"].items():
        file, field = key.split(".", 1)
        if file in v and file != "override":
            v[file] = {**v[file], field: value}
    return v


def compute_status(v):
    if "post" not in v:
        return "pending"
    names = [n for n in schema.stage_files() if schema.applies(n, v)]
    if any(n not in v or v[n].get("fp") != schema.fp(n, v) for n in names):
        return "pending"
    return "needs_review" if any(schema.unsure(n, v) for n in names) else "ok"


def update_status(rk):
    """Recompute status.yaml from the entry's view; deleted stays deleted. Writes only on change."""
    old = read(rk, "status")
    if old == "deleted":
        return old
    new = compute_status(view(rk))
    if new != old:
        write(rk, "status", new)
    return new


def find(number):
    """Watchlist number -> rkey, from parsed.number with overrides; deleted entries are skipped."""
    rks = [rk for rk in list_entries() if read(rk, "status") != "deleted"
           and (view(rk).get("parsed") or {}).get("number") == number]
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
