# Reference data

## Key-Contribution.csv

NYC Campaign Finance Board's own key to the contribution export. The source of
truth for every code label in `src/vocab/codes.json`.

| | |
|---|---|
| Source | <https://www.nyccfb.info/DataLibrary/Key-Contribution.csv> |
| Retrieved | 2026-11-08 |
| Last modified (upstream) | Tue, 23 Jul 2024 18:07:14 GMT |
| SHA-256 | `57a18a0024cb13dd607246e9b91d528f2e974b8482ebf4dd9d8910a5da99b216` |

Committed deliberately rather than fetched at build time: a label that changes
without a diff is a silent change in meaning. Re-download it, re-run
`./.venv/bin/python3 -m src.vocab.code_key --write`, and read the diff.

### Defects in the published file, handled by the parser

- `ADJTYPECD` reads `0=Unknown; 1=Returned Check 2=Refund; 5=Other`. The
  semicolon between `Returned Check` and `2=Refund` is missing, so splitting on
  `;` alone yields a value of `Returned Check 2=Refund`.
- `CANCLASS` enumerates comma-separated labels with no `code=` form at all:
  `[Participant, Non-Participant, Limited Participant, Undetermined]`.
- `EXEMPTCD` writes `Blank = Not Exempt`, with spaces around the equals sign, to
  mean the empty string.
- Four cells contain embedded newlines: row 0's title plus three later description
  cells (byte offsets 3298, 3405, 3517). The file is UTF-8 with **no**
  BOM — decoding with `utf-8-sig` is harmless but nothing is stripped, so no test
  should assert a BOM is removed. Line endings are mixed: 57 CRLF and 4 bare LF,
  so the file must be read with the `csv` module and `newline=''`, never with
  `splitlines()`.
- Schedule `X` appears in the data (1,504 rows) but **not** in this key.
