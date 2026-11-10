"""Parse NYC CFB's published contribution code key into structured data.

The key is the source of truth for every code label in this project. It is
vendored at data/reference/Key-Contribution.csv; see that directory's README for
the defects in the published file that this module compensates for.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

__all__ = [
    "CodeKeyError",
    "KNOWN_REPAIRS",
    "parse_enumeration",
    "parse_key_csv",
    "build_codes",
    "main",
]

# A bracketed enumeration at the end of a description: "... : [a=b; c=d]"
_BRACKETED = re.compile(r"\[(?P<body>[^\[\]]*)\]\s*$")

class CodeKeyError(ValueError):
    """The published key did not parse as expected. Never silently absorbed."""


#: CFB publishes exactly one malformed enumeration. The repair is named here as
#: data rather than inferred by a general heuristic, because a lookahead that
#: treats " word=" as the start of a new code cannot distinguish this defect
#: from a legitimate label containing "=" -- "B=Bar (see note: x=y)" would
#: silently fabricate a code "x". Naming it means an upstream change raises
#: instead of being quietly absorbed: if CFB ever adds the missing semicolon,
#: test_known_repair_is_still_needed fails, which is the signal to delete this.
KNOWN_REPAIRS: dict[str, tuple[str, str]] = {
    "ADJTYPECD": ("1=Returned Check 2=Refund", "1=Returned Check; 2=Refund"),
}


def parse_enumeration(body: str, field: str | None = None) -> dict[str, str]:
    """Extract a code->label mapping from an enumeration body.

    Handles the three forms CFB actually publishes:
      "0=Unknown; 1=Cash"                -> {"0": "Unknown", "1": "Cash"}
      "Participant, Non-Participant"     -> label-as-code, no equals signs
      "Blank = Not Exempt"               -> "Blank" means the empty-string code

    The first "=" in a segment is the separator, so a label may contain "=".
    Anything that does not fit these forms raises CodeKeyError rather than
    returning a plausible-looking dict.
    """
    body = (body or "").strip()
    if not body:
        return {}

    repair = KNOWN_REPAIRS.get((field or "").upper())
    if repair and repair[0] in body:
        body = body.replace(*repair)

    segments = [s.strip() for s in body.split(";") if s.strip()]
    if not segments:
        return {}

    # Format 3: a comma-separated label list with no "=" anywhere.
    if not any("=" in s for s in segments):
        return {p.strip(): p.strip() for s in segments for p in s.split(",") if p.strip()}
    if not all("=" in s for s in segments):
        raise CodeKeyError(f"{field or '?'}: mixed coded and uncoded segments: {segments!r}")

    out: dict[str, str] = {}
    for seg in segments:
        code, label = seg.split("=", 1)
        code, label = code.strip(), label.strip().rstrip(",;").strip()
        if code.upper() == "BLANK":
            code = ""
        if not label:
            raise CodeKeyError(f"{field or '?'}: code {code!r} has an empty label")
        if "=" in label:
            raise CodeKeyError(
                f"{field or '?'}: label for {code!r} contains '=' ({label!r}); this is what "
                "CFB's missing-separator defect looks like -- add a KNOWN_REPAIRS entry"
            )
        if code and re.search(r"\s", code):
            raise CodeKeyError(f"{field or '?'}: code {code!r} contains whitespace")
        if code in out:
            raise CodeKeyError(f"{field or '?'}: duplicate code {code!r}")
        out[code] = label
    return out


def parse_key_csv(path: str | Path) -> dict[str, dict]:
    """Parse the key CSV into {FIELD_NAME: {column, type, description, values}}.

    Skips the preamble rows, keys on the column NAME, and attaches the parsed
    enumeration where the description carries one.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))

    header_at = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == "Column":
            header_at = i
            break
    if header_at is None:
        raise ValueError(f"{path}: no 'Column' header row found")

    key: dict[str, dict] = {}
    for row in rows[header_at + 1 :]:
        if len(row) < 4:
            continue
        col, type_, name, description = (c.strip() for c in row[:4])
        if not col.isdigit() or not name:
            continue
        match = _BRACKETED.search(description)
        if match:
            values = parse_enumeration(match.group("body"), name)
        elif "[" in description:
            raise CodeKeyError(
                f"{name}: description contains '[' but no parsable [...] list: {description!r}"
            )
        else:
            values = {}
        key[name] = {
            "column": int(col),
            "type": type_,
            "description": description,
            "values": values,
        }
    return key


def build_codes(path: str | Path) -> dict:
    """Build the codes.json payload: every field CFB documents, enumerated or not.

    All 52 fields are kept, with an empty ``values`` for the 43 that carry no
    enumeration. That is deliberate: codes.json is a diffable artifact, so
    keeping the free-text fields means a future re-download reveals when CFB
    *adds* an enumeration to a field that previously had none. Filtering would
    hide exactly the change worth noticing.
    """
    return {
        "source": "https://www.nyccfb.info/DataLibrary/Key-Contribution.csv",
        "fields": parse_key_csv(path),
    }


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--key",
        type=Path,
        default=repo_root / "data" / "reference" / "Key-Contribution.csv",
    )
    parser.add_argument(
        "--out", type=Path, default=Path(__file__).resolve().parent / "codes.json"
    )
    parser.add_argument(
        "--write", action="store_true", help="write the artifact instead of printing it"
    )
    args = parser.parse_args(argv)

    payload = build_codes(args.key)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.write:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(payload['fields'])} fields)")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
