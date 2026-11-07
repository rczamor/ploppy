#!/usr/bin/env python3
"""Repair unescaped inner quotes in NYSBOE ListOfFilers.csv.

The export writes names like

    "Committee To Elect Mary Eileen "Mel" Callan, R.N."

where the inner quotes are NOT doubled per RFC 4180. A conforming parser ends the
field at the second quote, so the comma inside "Callan, R.N." becomes a delimiter
and every later field shifts right by one. Postgres COPY rejects the row outright
("extra data after last expected column"); Python's csv module silently mangles
it instead. The quote count stays even, so an unbalanced-quote check does not
catch it either.

The repair walks each field with a small state machine rather than a regex: a
regex that doubles "inner" quotes cannot tell a field-opening quote at the start
of a line from a stray one, and doubling that opening quote produces input that
Python's lenient parser still accepts while Postgres rejects it. Inside a quoted
field, a quote is left alone when it is already doubled or when it closes the
field (next character is a delimiter or end of line); anything else is doubled.

Only lines that are already malformed are touched, the rewrite is kept only if it
then parses strictly to the expected field count, and anything unfixable is
reported rather than dropped. The source file is never modified.

This is line-based, which is safe for this export because it has no newlines
inside quoted fields -- asserted at run time, not assumed.

Usage:
    python3 scripts/repair_listoffilers.py IN.csv OUT.csv
"""

import csv
import io
import sys


def strict_fields(line):
    """Field count under strict parsing, or -1 if the line is malformed."""
    try:
        rows = list(csv.reader(io.StringIO(line), strict=True))
    except csv.Error:
        return -1
    if len(rows) != 1:          # an embedded newline split it
        return -1
    return len(rows[0])


def escape_inner_quotes(line):
    """Fix unescaped quotes inside quoted fields, by quote-run parity.

    Inside a quoted field, look at each maximal run of k quote characters and at
    what follows it. Valid RFC 4180 input has a specific parity, and restoring
    that parity is enough to repair every defect this export produces:

      * run followed by ordinary text -- the run is purely literal content, so k
        must be EVEN (each literal quote doubled). 'Eileen "Mel' has k=1, so it
        gains one.
      * run followed by a delimiter or end of line -- the run is some literal
        quotes plus the one that closes the field, so k must be ODD. The name
        Somboun "April" is exported with a run of 2 there, so it gains one and
        the value survives intact.

    Parity is what disambiguates the hard case. A value that genuinely ends in a
    quote is correctly encoded with a run of 3 before the delimiter (one doubled
    literal, then the closer): already odd, so it is left alone. The broken form
    has a run of 2. Without this parity rule the two are indistinguishable, which
    is why a naive pass that doubles any quote not already doubled corrupts valid
    rows while still failing on these.
    """
    out = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == '"':
            out.append('"')                 # the field's opening quote
            i += 1
            while i < n:
                ch = line[i]
                if ch != '"':
                    out.append(ch)
                    i += 1
                    continue
                # measure the whole run of quotes
                j = i
                while j < n and line[j] == '"':
                    j += 1
                k = j - i
                after = line[j] if j < n else ""
                terminating = after in ("", ",", "\r", "\n")
                if terminating:
                    k_fixed = k if k % 2 == 1 else k + 1
                    out.append('"' * k_fixed)
                    i = j
                    break
                k_fixed = k if k % 2 == 0 else k + 1
                out.append('"' * k_fixed)
                i = j
            continue
        # --- unquoted field: copy through to the delimiter
        while i < n and line[i] != ",":
            out.append(line[i])
            i += 1
        if i < n:
            out.append(",")
            i += 1
    return "".join(out)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, newline="", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()

    lines = raw.splitlines(keepends=True)
    header = lines[0]
    want = strict_fields(header)
    # Every data row in this export carries one extra trailing empty field.
    data_want = want + 1

    # Line-based repair is only valid if no record spans multiple lines.
    with open(src, newline="", encoding="utf-8", errors="replace") as fh:
        parsed = sum(1 for _ in csv.reader(fh)) - 1
    if parsed != len(lines) - 1:
        raise SystemExit(
            f"{src} has records spanning multiple lines "
            f"({parsed:,} records over {len(lines) - 1:,} lines); "
            "this line-based repair would corrupt them."
        )

    repaired = unfixable = 0
    out = [header]
    for i, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        if strict_fields(line) == data_want:
            out.append(line)
            continue
        fixed = escape_inner_quotes(line)
        if strict_fields(fixed) == data_want:
            repaired += 1
            print(f"  repaired line {i}: {line.rstrip()[:110]}")
            out.append(fixed)
        else:
            unfixable += 1
            print(f"  COULD NOT FIX line {i} "
                  f"(strict parse gives {strict_fields(line)} fields, "
                  f"want {data_want}): {line.rstrip()[:110]}", file=sys.stderr)
            out.append(line)

    with open(dst, "w", newline="", encoding="utf-8") as fh:
        fh.writelines(out)

    # Re-read the result strictly: the repair is not trusted on its own word.
    bad = [i for i, l in enumerate(out[1:], start=2)
           if l.strip() and strict_fields(l) != data_want]
    print(f"header fields {want} (+1 trailing = {data_want} per row)")
    print(f"rows in  : {len(lines) - 1:,}")
    print(f"rows out : {len(out) - 1:,}")
    print(f"repaired : {repaired}")
    print(f"unfixable: {unfixable}")
    print(f"strict re-check of output: "
          f"{'all rows OK' if not bad else f'{len(bad)} still bad: {bad[:5]}'}")
    return 1 if (unfixable or bad) else 0


if __name__ == "__main__":
    sys.exit(main())
