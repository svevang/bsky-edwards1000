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


def lookup(view, ref):
    file, field = ref.split(".", 1)
    return (view.get(file) or {}).get(field)


def fp(name, view):
    return stage.fp(*(lookup(view, ref) for ref in fp_inputs(name)))
