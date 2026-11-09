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

__all__ = ["parse_enumeration", "parse_key_csv", "build_codes", "main"]

# A bracketed enumeration at the end of a description: "... : [a=b; c=d]"
_BRACKETED = re.compile(r"\[(?P<body>[^\[\]]*)\]\s*$")

# One code=label pair. The lookahead stops the lazy label at the next "code=",
# which is what recovers CFB's missing semicolon in ADJTYPECD. It requires
# whitespace before the next code, so a parenthetical like "(EC2021 Only)"
# stays part of the label.
_PAIR = re.compile(r"([A-Za-z0-9]+)\s*=\s*(.*?)(?=\s+[A-Za-z0-9]+\s*=|$)")


def parse_enumeration(text: str) -> dict[str, str]:
    """Extract a code->label mapping from an enumeration body.

    Handles the three forms CFB actually publishes:
      "0=Unknown; 1=Cash"                     -> {"0": "Unknown", "1": "Cash"}
      "1=Returned Check 2=Refund"             -> both pairs, despite no separator
      "Participant, Non-Participant"          -> label-as-code, no equals signs
    "Blank" as a code means the empty string.
    """
    text = (text or "").strip()
    if not text:
        return {}

    out: dict[str, str] = {}
    for chunk in text.split(";"):
        for code, label in _PAIR.findall(chunk.strip()):
            label = label.strip().rstrip(",;").strip()
            if not label:
                continue
            key = "" if code.lower() == "blank" else code
            out[key] = label

    if out:
        return out

    # No "code=" anywhere: the labels themselves are the values.
    return {
        part.strip(): part.strip()
        for part in text.split(",")
        if part.strip()
    }


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
        body = ""
        match = _BRACKETED.search(description)
        if match:
            body = match.group("body")
        key[name] = {
            "column": int(col),
            "type": type_,
            "description": description,
            "values": parse_enumeration(body),
        }
    return key


def build_codes(path: str | Path) -> dict:
    """Build the codes.json payload: only the fields that carry enumerations."""
    key = parse_key_csv(path)
    return {
        "source": "https://www.nyccfb.info/DataLibrary/Key-Contribution.csv",
        "fields": {
            name: {
                "column": meta["column"],
                "type": meta["type"],
                "description": meta["description"],
                "values": meta["values"],
            }
            for name, meta in key.items()
        },
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
