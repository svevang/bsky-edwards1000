"""schema.yaml: the files in an entry, their fingerprint inputs and the status vocabulary.

Fingerprint inputs are file.field references looked up in an entry's view, a dict like
{"parsed": {...}, "wikipedia": {...}, "override": {"wikipedia.page": ...}}. The reference
splits at the first dot, so "override.wikipedia.page" reads key "wikipedia.page" of the
override file. Missing files or fields count as None.
"""
import functools
import os
import yaml
import stage

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.yaml")


@functools.cache
def load_schema():
    with open(SCHEMA, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fp_inputs(name):
    return load_schema()["files"][name].get("fp", [])


def stage_files():
    """Files a stage writes, in pipeline order: the ones with fingerprint inputs."""
    return [n for n, f in load_schema()["files"].items() if "fp" in f]


def lookup(view, ref):
    file, field = ref.split(".", 1)
    return (view.get(file) or {}).get(field)


def fp(name, view):
    return stage.fp(*(lookup(view, ref) for ref in fp_inputs(name)))


def applies(name, view):
    req = load_schema()["files"][name].get("requires")
    return not req or bool(lookup(view, req))


def unsure(name, view):
    check = load_schema()["files"][name].get("unsure")
    if not check:
        return False
    negate = check.startswith("not ")
    value = bool((view.get(name) or {}).get(check.removeprefix("not ")))
    return value != negate
