"""Typed access to the generated code artifact."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_ARTIFACT = Path(__file__).resolve().parent / "codes.json"

__all__ = ["load", "values", "label"]


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(_ARTIFACT.read_text(encoding="utf-8"))


def values(field: str) -> dict[str, str]:
    """The code->label mapping for a CFB column name, e.g. "OFFICECD"."""
    try:
        return dict(load()["fields"][field]["values"])
    except KeyError as exc:
        raise KeyError(f"no such field in codes.json: {field!r}") from exc


def label(field: str, code, default: str | None = None) -> str:
    """Look up one label. Codes are compared as strings, since CFB mixes types.

    A blank code is not the same as a missing one. CFB writes "Blank = Not
    Exempt", so EXEMPTCD genuinely documents the empty string as a code -- and
    the loader stores blank as NULL, on 2,123,656 of 2,123,892 rows. Resolving
    NULL to "Unknown" there would mislabel almost the whole table. So when a
    field documents "", NULL and whitespace resolve to it; otherwise they fall
    through to the default.
    """
    mapping = values(field)
    if code is None or (isinstance(code, str) and not code.strip()):
        if "" in mapping:
            return mapping[""]
        return default if default is not None else "Unknown"
    got = mapping.get(str(code).strip())
    if got is not None:
        return got
    return default if default is not None else f"Unknown ({code})"
