"""Entry store: one directory per post under entries/, one YAML file per stage.

Files are named by stage without the extension ("post", "parsed", "wikipedia", "review",
"override", "status"); schema.yaml describes them. status.yaml is one bare line.
Every write goes through a temp file and os.replace, so a file is never half-written.
"""
import os
import tempfile
import yaml

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
    p = path(rk, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{data}\n" if name == "status" else dump(data))
        os.chmod(tmp, 0o644)  # mkstemp creates files 0600
        os.replace(tmp, p)
    except BaseException:
        os.unlink(tmp)
        raise
