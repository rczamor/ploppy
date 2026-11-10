"""Typed access to the generated code artifact."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

_ARTIFACT = Path(__file__).resolve().parent / "codes.json"

__all__ = ["load", "values", "label"]


@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(_ARTIFACT.read_text(encoding="utf-8"))


def load() -> dict:
    """The whole artifact, as a deep copy so callers cannot mutate the cache
    that label() and values() read from."""
    return copy.deepcopy(_load())


def values(field: str) -> dict[str, str]:
    """The code->label mapping for a CFB column name, e.g. "OFFICECD"."""
    try:
        return dict(_load()["fields"][field]["values"])
    except KeyError as exc:
        raise KeyError(f"no such field in codes.json: {field!r}") from exc


def _code_key(code) -> str | None:
    """Normalise a code to its artifact key, or None if it is missing.

    pandas promotes an integer column to float as soon as one value is NULL, so
    pay_method 1 arrives as 1.0 and must still find '1'. NaN and pd.NA are
    missing values, not codes, and must take the blank-code branch -- otherwise
    a NaN on EXEMPTCD returns "Unknown (nan)" instead of the documented
    "Not Exempt".
    """
    if code is None:
        return None
    if isinstance(code, float):
        if code != code:                      # NaN, without importing pandas
            return None
        if code.is_integer():
            return str(int(code))
    text = str(code).strip()
    if text in ("", "nan", "<NA>", "None", "NaT"):
        return None
    return text


def label(field: str, code, default: str | None = None) -> str:
    """Look up one label. Codes are compared as strings, since CFB mixes types.

    A blank code is not the same as a missing one. CFB writes "Blank = Not
    Exempt", so EXEMPTCD genuinely documents the empty string as a code -- and
    the loader stores blank as NULL, on 2,123,656 of 2,123,892 rows. Resolving
    NULL to "Unknown" there would mislabel almost the whole table.

    What comes back, by input (``default`` is the optional argument):

    ============================  ============================================
    input                         result
    ============================  ============================================
    None / NaN / pd.NA / blank    the label of the documented "" code if the
                                  field has one; else ``default`` if given;
                                  else "Unknown"
    code in the field             its label (1.0 is treated as 1)
    code absent from the field    ``default`` if given; else "Unknown (<code>)"
    ============================  ============================================

    Callers that pass ``default`` get it verbatim for missing AND absent codes,
    so a wrapper's default decides what its callers see for both.
    """
    mapping = values(field)
    key = _code_key(code)
    if key is None:
        if "" in mapping:
            return mapping[""]
        return default if default is not None else "Unknown"
    got = mapping.get(key)
    if got is not None:
        return got
    return default if default is not None else f"Unknown ({code})"
