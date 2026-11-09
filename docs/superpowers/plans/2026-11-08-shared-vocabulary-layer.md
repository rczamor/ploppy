# Shared Vocabulary Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the data's vocabulary correct and shared — CFB's own code key becomes the source of truth for every label, and one name-normalization definition generates both the Postgres function and the DuckDB macro, with a CI test proving they agree byte for byte.

**Architecture:** Two small packages under `src/vocab/`. `code_key.py` parses CFB's published `Key-Contribution.csv` into `codes.json`, a committed, diffable artifact; `code_mappings.py` is rewritten as a thin accessor over it, keeping its existing public API so no caller breaks. `normalize.py` holds the canonical Python definition of `name_norm`, and `sql_gen.py` emits a Postgres `IMMUTABLE` function and a DuckDB macro from that single definition. A golden-vector test asserts all three implementations produce identical output.

**Tech Stack:** Python 3.12+, pytest 9, psycopg 3.3, duckdb 2.0.0, PostgreSQL 14+ locally (PG16+ required later, not here), GitHub Actions.

**Environment — measured 2026-11-08, not assumed.** `python3` on PATH is 3.13.0 and has pytest but **neither duckdb nor psycopg**; the repo's uv-managed `.venv` (3.12.7) was empty. Both engines are now installed into `.venv`: pytest 9.2.0, duckdb 2.0.0, psycopg 3.3.8. Postgres is 14.13 (Homebrew), and the `ploppy` database already carries `unaccent 1.1`, `pg_trgm 1.6` and `fuzzystrmatch 1.1` — which is why `daitch_mokotoff` (1.2, PG16+) is out of scope here. **Every `python3` command below means `./.venv/bin/python3`.** Bare `python3` runs the suite with both engine legs skipping. An earlier draft of this line claimed psycopg was already installed; it was not.

**Scope:** This is plan 1 of several. It implements build-order steps 1 and 2 from `docs/superpowers/specs/2026-11-08-ploppy-research-tool-design.md` (committed `fbada2a`). It needs no Vercel project, no Neon database and no Blob store — everything runs on the laptop. Later plans cover: the identity schema, the ETL pipeline, rollup semantics, the Parquet build and publish, the public surface, the private console, and district attribution.

**Why this first — measured against the `ploppy` database, not asserted.** `src/database/code_mappings.py` mislabels office codes 11/44/55 as "Special Designation / District / Office" when CFB's key says they are the 2021 Program A offices. Under `election LIKE '2021%'` the six Program A codes (11/22/33/44/55/66) carry **437,059 rows and $49,779,237** — 92.5% of that cycle's contribution rows and 71.2% of its dollars — so three fabricated labels sit on top of nearly the whole cycle, hiding the only natural experiment in the dataset. Schedule M is Receipt Adjustments, not "Matchable Contributions": **39,336 of its 39,361 rows are negative**, summing to **-$24,468,945.56**, so anything aggregating M as contributions nets refunds into totals. Schedules `G` (54 rows) and `N` (771 rows) are in CFB's key *and* the data but absent from the module, and `X` (1,504 rows) is in neither — those get `Unknown Schedule (...)` today. And the two engines have no shared normalization at all, which is a zero-rows-not-an-error failure waiting to happen on every fact-to-dimension join.

---

## File Structure

| File | Responsibility |
|---|---|
| `pytest.ini` | Test config. Deliberately **not** `pyproject.toml` — that file is 90,942 bytes of unrelated `[tool.uv.sources]` and is rewritten in a later plan. |
| `data/reference/Key-Contribution.csv` | Vendored copy of CFB's published code key, so parsing is reproducible and testable offline. |
| `src/vocab/__init__.py` | Package marker. |
| `src/vocab/code_key.py` | Parses the key CSV into a structured dict. Knows about CFB's three enumeration formats and its missing-semicolon defect. Nothing else. |
| `src/vocab/codes.json` | Generated artifact, committed. The reviewable diff when CFB changes its key. |
| `src/vocab/normalize.py` | Canonical `name_norm` in Python, plus the accent-fold table derived from `unicodedata`. |
| `src/vocab/sql_gen.py` | Emits the Postgres function and the DuckDB macro from `normalize.py`. No logic of its own. |
| `src/vocab/generated/name_norm_pg.sql` | Generated. Postgres `IMMUTABLE` function. |
| `src/vocab/generated/name_norm_duckdb.sql` | Generated. DuckDB macros. |
| `src/database/code_mappings.py` | **Rewritten** as an accessor over `codes.json`. Public API preserved exactly. |
| `tests/conftest.py` | Shared fixtures: the parsed key, a DuckDB connection, an optional Postgres connection. |
| `tests/test_code_key.py` | Parser unit tests, including the defect cases. |
| `tests/test_code_mappings.py` | Regression tests pinning each documented mislabel as fixed. |
| `tests/test_normalize.py` | Python normalization unit tests. |
| `tests/test_cross_engine.py` | Golden-vector equality across Python, DuckDB and (when available) Postgres. |
| `.github/workflows/ci.yml` | Runs the suite on push. |

---

## Task 1: Test harness

**Files:**
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `src/vocab/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_normalize.py` with only an import, to prove the package is importable:

```python
def test_vocab_package_importable():
    import src.vocab  # noqa: F401
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.vocab'` (or a collection error, since `pytest.ini` does not exist yet).

- [ ] **Step 3: Create the config and the package**

`pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q -ra --strict-markers
markers =
    postgres: requires a local PostgreSQL with the ploppy database
```

`-ra` is not cosmetic: with bare `-q` a skipped test prints as `s` with no reason, so a run that skipped every cross-engine comparison looks identical to a run that passed.

Deliberately no `filterwarnings = error`: `src/utils/utils.py:65` has a known
`SyntaxWarning: invalid escape sequence '\$'`, and turning warnings into errors would fail
this plan's suite for a defect it does not own. Fixed in the pipeline plan.

`src/vocab/__init__.py`:

```python
"""Shared vocabulary: CFB code labels and the canonical name normalization."""
```

`tests/conftest.py`:

```python
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

#: When "1", a missing engine or an unreachable database is a FAILURE, not a skip.
#: The definition of done requires one run with this set: a cross-engine equality
#: suite that silently skips is worse than no suite, because it reports false
#: confidence. CI leaves it unset for the Postgres leg only.
STRICT_ENGINES = os.environ.get("PLOPPY_REQUIRE_ENGINES") == "1"

DEFAULT_DSN = "dbname=ploppy"


def _unavailable(reason: str) -> None:
    """Fail under PLOPPY_REQUIRE_ENGINES=1, otherwise skip. Always raises."""
    (pytest.fail if STRICT_ENGINES else pytest.skip)(reason, pytrace=False)


def _version(module_name: str) -> str:
    try:
        return __import__(module_name).__version__
    except Exception:
        return "not installed"


def pytest_report_header() -> list[str]:
    """Make the interpreter and the engines visible without an extra command.

    Bare `python3` here has pytest but neither engine, so without this header a
    run that skipped everything is indistinguishable from a run that passed.
    """
    return [
        f"interpreter: {sys.executable}",
        "engines: duckdb {}, psycopg {} (PLOPPY_REQUIRE_ENGINES={})".format(
            _version("duckdb"), _version("psycopg"), "1" if STRICT_ENGINES else "0"
        ),
    ]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def duckdb_conn():
    try:
        import duckdb
    except ImportError:
        _unavailable("duckdb is not installed")
    conn = duckdb.connect()
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pg_conn():
    """A connection to the local ploppy database.

    Optional in CI, required for local verification. An explicitly set
    PLOPPY_TEST_DSN means the caller intends Postgres to be used, so an
    unreachable server is a failure rather than a skip. autocommit avoids one
    bad vector aborting the transaction and cascading InFailedSqlTransaction
    into every later test on this session-scoped connection.
    """
    try:
        import psycopg
    except ImportError:
        _unavailable("psycopg is not installed")
    dsn = os.environ.get("PLOPPY_TEST_DSN") or ""
    explicit = bool(dsn)
    if not dsn:
        dsn = DEFAULT_DSN
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.OperationalError as exc:
        reason = f"no Postgres at {dsn!r}: {exc}"
        if explicit:
            pytest.fail(reason, pytrace=False)
        _unavailable(reason)
    yield conn
    conn.close()
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_normalize.py -v`
Expected: PASS, 1 test.

- [ ] **Step 5: Commit**

```bash
git add pytest.ini tests/conftest.py tests/test_normalize.py src/vocab/__init__.py .gitignore
git commit -m "test: add pytest harness and src/vocab package"
```

Note: the repo already has `test_everything.py` and `test_app.py` at the root. Both are print-based scripts, not pytest assertions, and `testpaths = tests` deliberately excludes them. Leave them alone; a later plan deletes them.

---

## Task 2: Vendor CFB's code key

CFB publishes the key at a stable URL, but a build that reaches the network to parse a label is a build that fails offline and changes meaning without a diff. Vendor it.

**Files:**
- Create: `data/reference/Key-Contribution.csv`
- Create: `data/reference/README.md`

- [ ] **Step 1: Download it**

```bash
mkdir -p data/reference
curl -sSL -o data/reference/Key-Contribution.csv \
  "https://www.nyccfb.info/DataLibrary/Key-Contribution.csv"
```

- [ ] **Step 2: Verify what arrived**

```bash
wc -c data/reference/Key-Contribution.csv
shasum -a 256 data/reference/Key-Contribution.csv
head -3 data/reference/Key-Contribution.csv
```

Expected: about 5,347 bytes; the first line begins `"NYC CAMPAIGN FINANCE BOARD SEARCHABLE DATABASE - KEY TO  CONTRIBUTION RESULTS REPORT`. If the byte count differs materially, CFB has revised the key — that is fine, but read the diff before continuing, because Task 4's assertions pin specific labels.

- [ ] **Step 3: Record provenance**

`data/reference/README.md`:

```markdown
# Reference data

## Key-Contribution.csv

NYC Campaign Finance Board's own key to the contribution export. The source of
truth for every code label in `src/vocab/codes.json`.

| | |
|---|---|
| Source | <https://www.nyccfb.info/DataLibrary/Key-Contribution.csv> |
| Retrieved | 2026-11-08 |

Committed deliberately rather than fetched at build time: a label that changes
without a diff is a silent change in meaning. Re-download it, re-run
`python3 -m src.vocab.code_key --write`, and read the diff.

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
  `splitlines()`. (An earlier draft of this plan claimed a BOM; verified absent —
  the first three bytes are `22 4e 59`.)
- Schedule `X` appears in the data (1,504 rows) but **not** in this key.
```

- [ ] **Step 4: Commit**

```bash
git add data/reference/Key-Contribution.csv data/reference/README.md
git commit -m "data: vendor CFB's published contribution code key"
```

---

## Task 3: Parse the code key

**Files:**
- Create: `src/vocab/code_key.py`
- Test: `tests/test_code_key.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_code_key.py`:

```python
import pytest

from src.vocab.code_key import parse_enumeration, parse_key_csv


def test_parse_enumeration_simple():
    assert parse_enumeration("0=Unknown; 1=Cash; 2=Check") == {
        "0": "Unknown",
        "1": "Cash",
        "2": "Check",
    }


def test_parse_enumeration_recovers_cfbs_missing_semicolon():
    # CFB's ADJTYPECD omits the separator between "Returned Check" and "2=Refund".
    assert parse_enumeration("0=Unknown; 1=Returned Check 2=Refund; 5=Other") == {
        "0": "Unknown",
        "1": "Returned Check",
        "2": "Refund",
        "5": "Other",
    }


def test_parse_enumeration_keeps_parenthetical_labels_intact():
    got = parse_enumeration(
        "1=Mayor; 11=Mayor Program A (EC2021 Only);IS=Independent Spender"
    )
    assert got == {
        "1": "Mayor",
        "11": "Mayor Program A (EC2021 Only)",
        "IS": "Independent Spender",
    }


def test_parse_enumeration_maps_blank_to_empty_string():
    got = parse_enumeration("C=Compliance Costs; U=Unknown; Blank = Not Exempt")
    assert got[""] == "Not Exempt"
    assert "Blank" not in got


def test_parse_enumeration_without_equals_returns_label_set():
    # CANCLASS has no code= form; the labels are the values.
    assert parse_enumeration(
        "Participant, Non-Participant, Limited Participant, Undetermined"
    ) == {
        "Participant": "Participant",
        "Non-Participant": "Non-Participant",
        "Limited Participant": "Limited Participant",
        "Undetermined": "Undetermined",
    }


def test_parse_enumeration_empty_when_no_enumeration():
    assert parse_enumeration("") == {}


def test_parse_key_csv_reads_every_column(repo_root):
    key = parse_key_csv(repo_root / "data" / "reference" / "Key-Contribution.csv")
    assert len(key) == 52, f"expected 52 columns, got {len(key)}"
    assert key["ELECTION"]["column"] == 1
    assert key["INT_C_CODE"]["column"] == 52
    assert key["AMNT"]["type"] == "Numeric"
    assert key["DATE"]["type"] == "Date"


@pytest.mark.parametrize(
    "field,code,label",
    [
        ("OFFICECD", "11", "Mayor Program A (EC2021 Only)"),
        ("OFFICECD", "55", "City Council Program A (EC2021 Only)"),
        ("SCHEDULE", "M", "Receipt Adjustments"),
        ("SCHEDULE", "D", "In-Kind Contributions"),
        ("C_CODE", "PCOMP", "Political Action Committee"),
        ("C_CODE", "PCOMC", "Candidate Committee"),
        ("PAY_METHOD", "4", "Credit Card"),
        ("PAY_METHOD", "5", "Money Order"),
        ("BOROUGHCD", "Z", "Outside New York City"),
        ("ADJTYPECD", "2", "Refund"),
    ],
)
def test_parse_key_csv_extracts_known_values(repo_root, field, code, label):
    key = parse_key_csv(repo_root / "data" / "reference" / "Key-Contribution.csv")
    assert key[field]["values"][code] == label
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_code_key.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.vocab.code_key'`.

- [ ] **Step 3: Write the parser**

> The code below is the parser as it actually landed, after review. An earlier draft
> recovered CFB's missing semicolon with a lookahead that treated any ` word=` as a new
> code. That heuristic and the defect are one mechanism and cannot be told apart: it
> fabricated a code from `B=Bar (see note: x=y)` and truncated `AB-1=Label` to
> `{'1': 'Label'}`, both silently. The repair is now named data keyed by field, the first
> `=` in a segment is the separator, and anything unexpected raises. Output is identical
> on all 52 fields; only the failure mode changed.

`src/vocab/code_key.py`:

```python
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
    """Build the codes.json payload: every field CFB documents, enumerated or not.

    All 52 fields are kept, with an empty ``values`` for the 43 that carry no
    enumeration. That is deliberate: codes.json is a diffable artifact, so keeping
    the free-text fields means a future re-download reveals when CFB *adds* an
    enumeration to a field that previously had none. Filtering would hide exactly
    the change worth noticing.
    """
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
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_code_key.py -v`
Expected: PASS, 17 tests (7 unit + 1 shape + 10 parametrized value checks).

- [ ] **Step 5: Commit**

```bash
git add src/vocab/code_key.py tests/test_code_key.py
git commit -m "feat: parse CFB's code key, handling its three enumeration formats"
```

---

## Task 4: Generate the committed codes artifact

**Files:**
- Create: `src/vocab/codes.json` (generated)
- Test: `tests/test_code_key.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_code_key.py`:

```python
def test_codes_json_is_in_sync_with_the_vendored_key(repo_root):
    """codes.json must be exactly what the parser produces. Regenerate with:

        python3 -m src.vocab.code_key --write
    """
    import json

    from src.vocab.code_key import build_codes

    expected = build_codes(repo_root / "data" / "reference" / "Key-Contribution.csv")
    actual = json.loads(
        (repo_root / "src" / "vocab" / "codes.json").read_text(encoding="utf-8")
    )
    assert actual == expected, "codes.json is stale; re-run the generator"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_code_key.py::test_codes_json_is_in_sync_with_the_vendored_key -v`
Expected: FAIL — `FileNotFoundError` on `src/vocab/codes.json`.

- [ ] **Step 3: Generate it**

```bash
python3 -m src.vocab.code_key --write
```

Expected output: `wrote .../src/vocab/codes.json (52 fields)`

- [ ] **Step 4: Run it to verify it passes, and read the artifact**

Run: `python3 -m pytest tests/test_code_key.py -v`
Expected: PASS, 18 tests.

Then eyeball the three fields this plan exists to fix:

```bash
python3 -I -c "
import json
d = json.load(open('src/vocab/codes.json'))['fields']
for f in ('OFFICECD','SCHEDULE','PAY_METHOD'):
    print(f, '->', d[f]['values'])
"
```

Expected: `OFFICECD` contains `'11': 'Mayor Program A (EC2021 Only)'` and `'55': 'City Council Program A (EC2021 Only)'`; `SCHEDULE` contains `'M': 'Receipt Adjustments'` and `'D': 'In-Kind Contributions'`; `PAY_METHOD` contains `'4': 'Credit Card'` and `'5': 'Money Order'`.

- [ ] **Step 5: Commit**

```bash
git add src/vocab/codes.json tests/test_code_key.py
git commit -m "feat: generate codes.json from CFB's key as a committed artifact"
```

---

## Task 5: Rewrite code_mappings.py over the artifact

`src/database/code_mappings.py` is 220 lines, of which lines 7–93 are hand-typed dicts. Those get replaced by lookups into `codes.json`. Everything below them — `parse_election_cycle`, `parse_name`, `is_individual_name` — is unrelated string handling and stays untouched.

The public API that must not change: `OFFICE_CODES`, `CANDIDATE_CLASS`, `CONTRIBUTOR_CODES`, `BOROUGH_CODES`, `PAYMENT_METHODS`, `SCHEDULE_TYPES`, `ADJUSTMENT_TYPES`, `ELECTION_TYPES`, `PURPOSE_CODES`, `EXEMPT_CODES`, `get_office_name`, `get_candidate_class_desc`, `get_contributor_type`, `get_borough_name`, `get_payment_method`, `get_schedule_description`, `get_adjustment_type`, `parse_election_cycle`, `parse_name`, `is_individual_name`.

**Files:**
- Create: `src/vocab/codes.py`
- Modify: `src/database/code_mappings.py:1-93`
- Test: `tests/test_code_mappings.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_code_mappings.py`:

```python
"""Regression tests pinning each documented mislabel as fixed.

Every assertion here corresponds to a defect recorded in
docs/superpowers/specs/2026-11-08-ploppy-research-tool-design.md §9.
"""

import pytest

from src.database import code_mappings as cm


class TestOfficeCodesWereMislabelled:
    """11/44/55 were "Special Designation/District/Office". They are Program A."""

    @pytest.mark.parametrize("code", ["11", "22", "33", "44", "55", "66"])
    def test_program_a_codes_say_program_a(self, code):
        assert "Program A" in cm.get_office_name(code)

    def test_the_old_wrong_labels_are_gone(self):
        assert set(cm.OFFICE_CODES.values()).isdisjoint(
            {"Special Designation", "Special District", "Special Office"}
        )

    def test_base_offices_still_resolve(self):
        assert cm.get_office_name("1") == "Mayor"
        assert cm.get_office_name("5") == "City Council"
        assert cm.get_office_name("IS") == "Independent Spender"


class TestScheduleTypesWereMislabelled:
    def test_m_is_receipt_adjustments_not_matchable(self):
        assert cm.get_schedule_description("M") == "Receipt Adjustments"

    def test_d_is_in_kind_not_expenditures(self):
        assert cm.get_schedule_description("D") == "In-Kind Contributions"

    def test_abc_is_monetary_contributions(self):
        assert cm.get_schedule_description("ABC") == "Monetary Contributions"

    @pytest.mark.parametrize("code", ["G", "N"])
    def test_schedules_present_in_the_data_but_missing_from_the_old_map(self, code):
        """G (54 rows) and N (771 rows) are in CFB's key and in the data, but the
        hand-typed map omitted them, so they resolved to Unknown. Deriving from the
        key fixes these for free -- this test only pins that it stayed fixed."""
        label = cm.get_schedule_description(code)
        assert label and not label.startswith("Unknown")

    def test_schedule_x_is_honestly_unknown(self):
        """X has 1,504 rows in the data and appears nowhere in CFB's key. An honest
        Unknown is the correct answer; inventing a label would be worse than none."""
        assert cm.get_schedule_description("X") == "Unknown Schedule (X)"


class TestPaymentMethodsWereWrongAndPartlyInvented:
    def test_real_codes(self):
        assert cm.get_payment_method(1) == "Cash"
        assert cm.get_payment_method(2) == "Check"
        assert cm.get_payment_method(3) == "Other"
        assert cm.get_payment_method(4) == "Credit Card"
        assert cm.get_payment_method(5) == "Money Order"
        assert cm.get_payment_method(0) == "Unknown"

    @pytest.mark.parametrize("fabricated", [1253, 1530, 7686, 8012, 9253, 11, 15])
    def test_fabricated_codes_are_gone(self, fabricated):
        assert fabricated not in cm.PAYMENT_METHODS


class TestCandidateClassBridgesKeyLabelsToDataCodes:
    @pytest.mark.parametrize("code,label", [
        ("P", "Participant"),
        ("NP", "Non-Participant"),
        ("UN", "Undetermined"),
        ("L", "Limited Participant"),
    ])
    def test_data_abbreviations_resolve_to_the_keys_labels(self, code, label):
        """The export column carries P/NP/UN, not the key's full labels.
        P alone is 1,962,546 rows."""
        assert cm.get_candidate_class_desc(code) == label

    def test_the_keys_own_labels_are_not_the_keys(self):
        """Guards the regression directly: keying by label would look fine in
        isolation and return Unknown for every real row."""
        assert "Participant" not in cm.CANDIDATE_CLASS


class TestBlankIsACodeNotAMissingValue:
    def test_null_exemptcd_resolves_to_the_documented_blank_code(self):
        """CFB documents "" as a code meaning Not Exempt, and the loader stores
        blank as NULL on 2,123,656 of 2,123,892 rows. Treating NULL as Unknown
        would mislabel 99.99% of the column."""
        from src.vocab import codes as _c
        assert _c.label("EXEMPTCD", None) == "Not Exempt"
        assert _c.label("EXEMPTCD", "") == "Not Exempt"
        assert _c.label("EXEMPTCD", "   ") == "Not Exempt"

    def test_null_still_unknown_where_blank_is_not_a_documented_code(self):
        """SCHEDULE documents no blank, so NULL must not borrow one."""
        from src.vocab import codes as _c
        assert _c.label("SCHEDULE", None) == "Unknown"


class TestContributorCodes:
    def test_pcomp_is_a_pac(self):
        assert cm.get_contributor_type("PCOMP") == "Political Action Committee"

    def test_pcomc_is_a_candidate_committee(self):
        assert cm.get_contributor_type("PCOMC") == "Candidate Committee"

    def test_empo_is_a_labor_union_not_an_employee_organization(self):
        """8,695 rows. The old label was a plausible-sounding paraphrase, which is
        the kind of wrong that survives review because nothing looks broken."""
        assert cm.get_contributor_type("EMPO") == "Labor Union"

    @pytest.mark.parametrize("code", ["CAN", "FAM", "SPO", "PCOMZ"])
    def test_previously_missing_codes_are_present(self, code):
        """17,290 rows between them had no label at all."""
        assert code in cm.CONTRIBUTOR_CODES

    @pytest.mark.parametrize("code", ["PCOM", "TRST", "ORG"])
    def test_codes_cfb_does_not_document_stay_honestly_unknown(self, code):
        """PCOM (8,483 rows), TRST (14) and ORG (1) appear in the data but in
        neither CFB's key nor the old map. Deriving from the key cannot invent a
        label for them, and should not: an explicit Unknown is the correct answer,
        and these are the rows a later plan has to decide how to present."""
        assert code not in cm.CONTRIBUTOR_CODES
        assert cm.get_contributor_type(code) == "Unknown"


class TestAdjustmentTypes:
    def test_cfbs_missing_semicolon_did_not_swallow_refund(self):
        assert cm.get_adjustment_type(1) == "Returned Check"
        assert cm.get_adjustment_type(2) == "Refund"
        assert cm.get_adjustment_type(5) == "Other"


class TestBoroughCodesWereAlreadyCorrect:
    @pytest.mark.parametrize(
        "code,name",
        [("M", "Manhattan"), ("K", "Brooklyn"), ("Q", "Queens"),
         ("X", "Bronx"), ("S", "Staten Island")],
    )
    def test_boroughs(self, code, name):
        assert cm.get_borough_name(code) == name

    def test_z_is_outside_the_city(self):
        assert cm.get_borough_name("Z") == "Outside New York City"


class TestUnknownCodesDegradeGracefully:
    def test_unknown_office(self):
        assert cm.get_office_name("ZZZ") == "Unknown (ZZZ)"

    def test_none_payment_method(self):
        assert cm.get_payment_method(None) == "Unknown"


class TestUnrelatedHelpersSurvived:
    def test_parse_election_cycle(self):
        # parse_election_cycle is untouched by this plan and returns "General"
        # for a bare year, not "". Pinning what it does, not what I assumed.
        assert cm.parse_election_cycle("2021") == (2021, "General")

    def test_is_individual_name(self):
        assert cm.is_individual_name("SMITH, JOHN") is True
        assert cm.is_individual_name("ACME HOLDINGS LLC") is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_code_mappings.py -v`
Expected: FAIL — many. `get_office_name("11")` currently returns `"Special Designation"`; `get_schedule_description("M")` returns `"Matchable Contributions"`; `1253 in cm.PAYMENT_METHODS` is currently True.

- [ ] **Step 3: Write the accessor, then rewrite the dicts**

`src/vocab/codes.py`:

```python
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
```

Now replace `src/database/code_mappings.py` lines 1–93 — everything from the module docstring through the end of `ELECTION_TYPES` — with the following. **Leave `parse_election_cycle`, `parse_name` and `is_individual_name` exactly as they are.**

```python
"""Code mappings for NYC Campaign Finance Board data.

Labels come from CFB's own published key via src/vocab/codes.json, not from
hand-typed dicts. Regenerate the artifact with:

    python3 -m src.vocab.code_key --write

The dicts below are kept as module-level names because existing callers import
them directly; they are now derived, not authored.
"""

import re

import pandas as pd

from src.vocab import codes as _codes

OFFICE_CODES = _codes.values("OFFICECD")
#: The one field where CFB's key and CFB's own export disagree. The key
#: documents CANCLASS as full labels ("Participant"), but the export column
#: contains abbreviations. Measured in cfb_contributions: P 1,962,546,
#: NP 134,526, UN 26,800. So this field needs an explicit bridge from the codes
#: the data uses to the labels the key publishes. Sourcing it straight from
#: codes.json would make get_candidate_class_desc("P") return
#: "Unknown Class (P)" for 92% of rows -- a regression, in a plan whose whole
#: point is getting labels right. Indexing (rather than .get) is deliberate:
#: if CFB renames a label, this raises at import instead of silently emptying.
_CANCLASS_ABBREVIATIONS = {
    "P": "Participant",
    "NP": "Non-Participant",
    "L": "Limited Participant",
    "UN": "Undetermined",
}
CANDIDATE_CLASS = {
    abbrev: _codes.values("CANCLASS")[label]
    for abbrev, label in _CANCLASS_ABBREVIATIONS.items()
}
CONTRIBUTOR_CODES = _codes.values("C_CODE")
BOROUGH_CODES = _codes.values("BOROUGHCD")
SCHEDULE_TYPES = _codes.values("SCHEDULE")
PURPOSE_CODES = _codes.values("PURPOSECD")
EXEMPT_CODES = _codes.values("EXEMPTCD")

# PAY_METHOD and ADJTYPECD are integers in the contributions export, so key the
# dicts by int while the artifact keys by string.
PAYMENT_METHODS = {
    int(k): v for k, v in _codes.values("PAY_METHOD").items() if k.isdigit()
}
ADJUSTMENT_TYPES = {
    int(k): v for k, v in _codes.values("ADJTYPECD").items() if k.isdigit()
}

# Not in CFB's key: the election-token suffixes. Derived from the loaded export,
# where the observed families are 2017/2017A/2017T, 2019/2019A/2019B/2019T,
# 2020A/2020B/2020C, 2021/2021A/2021B/2021C/2021T, 2023/2023T,
# 2025/2025A/2025B/2025T, 2026/2026A/2026T and 2029.
# NEVER cast an election token to an integer: '2025T' alone is 38,496 rows and
# $4.42M, so globbing or casting moves a 2025 headline by 15%.
# Deliberately UNCHANGED from the original. These values are persisted:
# db_manager_v2.py:79 writes them into elections.election_type, so editing this
# map silently rewrites the meaning of stored rows. A better mapping exists --
# the original sends suffixes B and C to "General" when they are special
# elections -- but replacing it is a data migration, not a label fix, and
# belongs with the pipeline plan. CFB's key has no field for these; they are
# election-token suffixes, not a published enumeration.
ELECTION_TYPES = {
    "T": "Transition",
    "A": "Special Election",
    "U": "Unknown Type",
}


def get_office_name(code: str) -> str:
    """Office sought. Codes 11/22/33/44/55/66 are the 2021 Program A offices."""
    return _codes.label("OFFICECD", code)


def get_candidate_class_desc(code: str) -> str:
    """Resolve the export's abbreviation (P/NP/L/UN), not the key's label.

    Going through _codes.label("CANCLASS", ...) would defeat the bridge above
    and return Unknown for the 1,962,546 rows that hold "P".
    """
    if code is None:
        return "Unknown"
    return CANDIDATE_CLASS.get(str(code).strip(), f"Unknown Class ({code})")


def get_contributor_type(code: str) -> str:
    return _codes.label("C_CODE", code)


def get_borough_name(code: str) -> str:
    return _codes.label("BOROUGHCD", code)


def get_payment_method(code) -> str:
    return _codes.label("PAY_METHOD", code)


def get_schedule_description(code: str) -> str:
    """Schedule. Note M is Receipt Adjustments (refunds, negative AMNT), not
    matchable contributions, and D is In-Kind, not expenditures. Schedule X
    appears in the data but not in CFB's key."""
    return _codes.label("SCHEDULE", code)


def get_adjustment_type(code) -> str:
    return _codes.label("ADJTYPECD", code)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_code_mappings.py -v`
Expected: PASS, 50 tests.

Then confirm nothing downstream broke — `src/database/db_manager_v2.py` imports `get_payment_method`, `get_adjustment_type` and `is_individual_name` from this module:

Run: `python3 -c "import src.database.db_manager_v2"`
Expected: no output, exit 0. (It needs `DATABASE_URL` only at instantiation, not import.)

- [ ] **Step 5: Commit**

```bash
git add src/vocab/codes.py src/database/code_mappings.py tests/test_code_mappings.py
git commit -m "fix: derive CFB code labels from the published key

Office codes 11/22/33/44/55/66 are the 2021 Program A offices, not "Special
Designation/District/Office" -- the mislabel hid the only natural experiment in
the dataset. Schedule M is Receipt Adjustments (refunds, negative AMNT), not
matchable contributions, so every aggregate built on the old map counted
\$24.47M of refunds as contributions. Schedule D is In-Kind, not expenditures.
PAY_METHOD 3/4/5 were Credit Card/Electronic Transfer/Other and are actually
Other/Credit Card/Money Order. Ten declared codes (11-15 and
1253/1530/7686/8012/9253) appear in none of the 2,123,865 rows despite a comment
claiming they were 'found in actual data', while three codes that do appear were
undeclared -- code 0 alone covers 135,005 rows. PCOMP is a Political Action Committee and PCOMC a Candidate
Committee; CAN, FAM, SPO and PCOMZ were missing entirely."
```

---

## Task 6: Prove the Program A experiment is now visible

The point of Task 5 was not tidiness. Verify the finding it unblocks.

**Files:**
- Test: `tests/test_program_ab.py`

- [ ] **Step 1: Write the failing test**

`tests/test_program_ab.py`:

```python
"""The 2021 Program A/B split is the only natural experiment in the data:
same city, same year, two match ratios and two contribution limits.

This test asserts the split is now *expressible*, not that any particular
average holds -- the spec records three different Program B averages
($576.52 / $620.33 / $606.25) under three different predicates, and fixing
that is a later plan's job. What must be true here is that the office codes
distinguish the two programs at all.
"""

import pytest

from src.database import code_mappings as cm

PROGRAM_A_CODES = {"11", "22", "33", "44", "55", "66"}


def test_program_a_codes_are_distinguishable_from_program_b():
    for code in PROGRAM_A_CODES:
        assert "Program A" in cm.get_office_name(code)
    for code in {"1", "2", "3", "4", "5", "6"}:
        assert "Program A" not in cm.get_office_name(code)


def test_independent_spender_is_neither_program():
    label = cm.get_office_name("IS")
    assert "Program A" not in label
    assert label == "Independent Spender"


@pytest.mark.postgres
def test_both_programs_have_2021_contributions(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT officecd, count(*), sum(amnt)
            FROM cfb_contributions
            WHERE election = '2021' AND schedule = 'ABC' AND amnt > 0
              AND officecd = ANY(%s)
            GROUP BY officecd ORDER BY officecd
            """,
            [sorted(PROGRAM_A_CODES)],
        )
        program_a = cur.fetchall()
    assert program_a, "no 2021 Program A rows found; check the office-code set"
    for officecd, rows, total in program_a:
        assert rows > 0 and total > 0
```

- [ ] **Step 2: Confirm it passes against the fix from Task 5**

This task is a **verification gate, not TDD** — the implementation it tests already landed in
Task 5, so the test is expected to pass immediately. That is the point: it pins the fix so a
future edit to `codes.json` cannot silently un-fix it.

Run: `python3 -m pytest tests/test_program_ab.py -v`
Expected: the two label tests PASS; the Postgres test PASSES locally or SKIPS without a
database.

- [ ] **Step 3: Verify it would have failed before the fix**

A regression test that cannot fail is worth nothing. Prove this one bites — against the
tree as it was *before* the label fix, without touching this worktree at all:

```bash
SCRATCH="$TMPDIR/task6-probe"; rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
git archive 472caed~1 | tar -x -C "$SCRATCH"      # the tree before the labels were fixed
cp tests/test_program_ab.py "$SCRATCH/tests/"      # ... plus the NEW test
ln -s "$PWD/.venv" "$SCRATCH/.venv"                # reuse this project's interpreter
(cd "$SCRATCH" && ./.venv/bin/python3 -m pytest tests/test_program_ab.py -v)
rm -rf "$SCRATCH"
```

Expected: FAILURES naming `Special Designation`, because at that commit `code_mappings.py`
still holds the hand-typed dicts. Then the same test against this worktree passes. New test
plus old code equals red; new test plus new code equals green. That is the proof.

Do **not** use `git stash` for this. Two reasons: the stash stack is shared across git
worktrees, so a bare `git stash pop` can take another session's work; and more simply, the
label fix is already committed, so there is nothing uncommitted to stash and the step would
silently prove nothing at all. Reconstructing the old tree read-only is both safer and a
stronger claim.

- [ ] **Step 4: Record what the data actually shows**

```bash
psql -d ploppy -c "
select case when officecd in ('11','22','33','44','55','66') then 'Program A' else 'Program B' end as program,
       count(*) as gifts,
       to_char(sum(amnt),'FM\$999,999,990') as total,
       to_char(avg(amnt),'FM\$9,990.00') as avg_gift,
       round(100.0*count(*) filter (where amnt <= 175)/count(*),1) as pct_gifts_under_175
from cfb_contributions
where election='2021' and schedule='ABC' and amnt>0
  and officecd in ('1','2','3','4','5','11','22','33','44','55')
group by 1 order by 1;"
```

Expected: two rows, with Program A showing a markedly lower average gift than Program B. Paste the actual output into the commit message — it is the first real finding this project produces.

- [ ] **Step 5: Commit**

```bash
git add tests/test_program_ab.py
git commit -m "test: pin the 2021 Program A/B split as expressible"
```

---

## Task 7: Canonical normalization in Python

**Files:**
- Create: `src/vocab/normalize.py`
- Test: `tests/test_normalize.py` (replace the placeholder from Task 1)

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_normalize.py` entirely:

```python
import pytest

from src.vocab.normalize import GOLDEN_VECTORS, fold_ascii, name_norm


def test_vocab_package_importable():
    import src.vocab  # noqa: F401


@pytest.mark.parametrize("raw,expected", GOLDEN_VECTORS)
def test_golden_vectors(raw, expected):
    assert name_norm(raw) == expected


def test_punctuation_becomes_a_separator_not_nothing():
    # "SMITH-JONES" must not collapse to "SMITHJONES".
    assert name_norm("SMITH-JONES") == "SMITH JONES"


def test_cfb_last_comma_first_loses_the_comma():
    assert name_norm("SMITH, JOHN A") == "SMITH JOHN A"


def test_replacement_character_is_deleted_not_spaced():
    # Deleting U+FFFD keeps similarity('JOSE MUOZ','JOSE MUNOZ') at 0.615, above
    # the 0.6 trigram threshold. Spacing it gives 0.571 and loses the match.
    assert name_norm("JOSE MU�OZ") == "JOSE MUOZ"


def test_soft_hyphen_is_deleted():
    assert name_norm("SMITH­JONES") == "SMITHJONES"


def test_accents_fold_to_ascii():
    assert name_norm("Gutiérrez, José") == "GUTIERREZ JOSE"
    assert name_norm("Peña") == "PENA"
    assert name_norm("Łukasz") == "LUKASZ"


def test_empty_and_punctuation_only_are_none():
    assert name_norm("") is None
    assert name_norm("   ") is None
    assert name_norm("...") is None
    assert name_norm(None) is None


def test_fold_ascii_leaves_plain_text_alone():
    assert fold_ascii("PLAIN TEXT 123") == "PLAIN TEXT 123"


def test_golden_vectors_cover_the_hazard_classes():
    raws = [r for r, _ in GOLDEN_VECTORS]
    assert any("," in r for r in raws), "need a LAST, FIRST vector"
    assert any("�" in r for r in raws), "need a U+FFFD vector"
    assert any("'" in r for r in raws), "need an apostrophe vector"
    assert any("-" in r for r in raws), "need a hyphen vector"
    assert any("&" in r for r in raws), "need an ampersand vector"
    assert len(GOLDEN_VECTORS) >= 20
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.vocab.normalize'`.

- [ ] **Step 3: Write the module**

`src/vocab/normalize.py`:

```python
"""The canonical definition of name normalization.

This module is the single source of truth. src/vocab/sql_gen.py generates the
Postgres function and the DuckDB macro FROM it, and tests/test_cross_engine.py
asserts all three agree byte for byte on GOLDEN_VECTORS. Change the rule here
and nowhere else, then regenerate and re-run the tests.

The rule, in order:
  1. Delete the characters that carry no information: U+FFFD REPLACEMENT
     CHARACTER and U+00AD SOFT HYPHEN. U+FFFD is DELETED rather than replaced
     with a space because 161 NYSBOE rows have it where an accented letter was,
     and deletion keeps similarity('JOSE MUOZ','JOSE MUNOZ') at 0.615 -- above
     the 0.6 trigram threshold -- where spacing gives 0.571 and loses the match.
  2. Fold accented Latin letters to ASCII by stripping combining marks.
  3. Upper-case.
  4. Replace every run of non-alphanumeric characters with a single space, so
     punctuation separates rather than vanishes: SMITH-JONES -> SMITH JONES,
     never SMITHJONES.
  5. Trim. An empty result is None.

Deliberately NOT used: Postgres's unaccent(). Both its signatures are declared
STABLE, not IMMUTABLE, so it cannot appear in an index expression, and the usual
IMMUTABLE wrapper asserts something about a dictionary file that ships with the
server package.
"""

from __future__ import annotations

import re
import sys
import unicodedata

__all__ = [
    "DELETE_CHARS",
    "GOLDEN_VECTORS",
    "fold_ascii",
    "name_norm",
    "translate_pairs",
]

# Characters deleted outright, before any folding.
DELETE_CHARS = "�­"

#: Single-character folds NFD cannot express. A stroke or bar is part of the
#: letter, not a combining mark, so NFD leaves these intact and the
#: [^A-Z0-9] step then turns each into a SPACE -- dropping the letter
#: outright. Measured before this map existed: "Lukasz" with U+0141
#: normalized to "UKASZ" in all three engines, so it could never match
#: "LUKASZ". Polish, Scandinavian, Croatian and Turkish surnames all hit this.
STROKE_FOLDS = {
    "Ł": "L", "ł": "l",   # L with stroke
    "Ø": "O", "ø": "o",   # O with stroke
    "Đ": "D", "đ": "d",   # D with stroke
    "Ħ": "H", "ħ": "h",   # H with stroke
    "Ŧ": "T", "ŧ": "t",   # T with stroke
    "ı": "i", "ȷ": "j",   # dotless i and j
    "Ɖ": "D", "Ƶ": "Z", "ƶ": "z",
}

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def fold_ascii(text: str) -> str:
    """Delete the no-information characters, fold strokes, strip combining marks."""
    for ch in DELETE_CHARS:
        text = text.replace(ch, "")
    text = "".join(STROKE_FOLDS.get(c, c) for c in text)
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def name_norm(text: str | None) -> str | None:
    """Normalize a contributor, committee or employer name. None if empty."""
    if text is None:
        return None
    folded = fold_ascii(str(text))
    collapsed = _NON_ALNUM.sub(" ", folded.upper()).strip()
    return collapsed or None


def translate_pairs(max_codepoint: int = 0x1EFF) -> tuple[str, str]:
    """Build the (from, to) argument pair for Postgres translate().

    Postgres has no NFD-strip primitive usable in an IMMUTABLE expression, so the
    fold is expressed as an explicit character list. Enumerating it from
    unicodedata here -- rather than typing it -- is what keeps the Postgres
    function, the DuckDB macro and this module from drifting apart.

    Covers Latin-1 Supplement through Latin Extended-B by default, which is every
    accented form observed in either jurisdiction's data. Characters that fold to
    more than one ASCII character (such as U+00C6 AE) cannot be expressed by
    translate() and are reported by sql_gen so they can be handled explicitly.
    """
    src: list[str] = []
    dst: list[str] = []
    for cp in range(0xC0, max_codepoint + 1):
        ch = chr(cp)
        folded = fold_ascii(ch)
        if len(folded) != 1 or folded == ch or not folded.isascii():
            continue
        src.append(ch)
        dst.append(folded)
    for ch in DELETE_CHARS:
        src.append(ch)  # no counterpart in dst: translate() deletes it
    # Combining marks must go too, or decomposed input diverges from DuckDB.
    # Python strips them via NFD, but translate() over precomposed characters
    # alone leaves them, and the [^A-Z0-9] step then
    # turns each one into a SPACE -- splitting the word. Measured:
    #   NFD "JOSE MUNOZ"     -> duckdb 'JOSE MUNOZ'     pg 'JOSE MUN OZ'
    #   NFD "Nguyen Thi Hoa" -> duckdb 'NGUYEN THI HOA' pg 'NGUYE N THI HOA'
    # Appending the range fixes both exactly. Precomposed input agreed already,
    # which is why a vector set that is entirely NFC would never catch this.
    for cp in range(0x0300, 0x0370):
        src.append(chr(cp))
    return "".join(src), "".join(dst)


# The contract. Every implementation must produce exactly these outputs.
# Each entry names a hazard rather than being arbitrary.
GOLDEN_VECTORS: list[tuple[str | None, str | None]] = [
    ("SMITH, JOHN A", "SMITH JOHN A"),            # CFB's LAST, FIRST MI
    ("Smith, John A.", "SMITH JOHN A"),           # mixed case + trailing period
    ("SMITH-JONES, MARY", "SMITH JONES MARY"),    # hyphen separates
    ("O'BRIEN, SEAN", "O BRIEN SEAN"),            # apostrophe separates
    ("GOLDMAN SACHS & CO.", "GOLDMAN SACHS CO"),  # ampersand
    ("SMITH & LAQUERCIA, LLP", "SMITH LAQUERCIA LLP"),   # firm, not a person
    ("SMITH & LAQUERCIA, P.C.", "SMITH LAQUERCIA P C"),  # initials split
    ("  multiple   spaces  ", "MULTIPLE SPACES"),  # whitespace runs collapse
    ("Gutiérrez, José", "GUTIERREZ JOSE"),         # Latin-1 accents
    ("Peña", "PENA"),
    ("Nuñez, María", "NUNEZ MARIA"),
    ("Łukasz", "LUKASZ"),                          # stroke, not a combining mark
    ("Nguyễn Thị Hoà", "NGUYEN THI HOA"),        # Latin Extended Additional
    ("JOSE\u0301 MUN\u0303OZ", "JOSE MUNOZ"),          # DECOMPOSED: the case that diverged
    ("Nguyễn", "NGUYEN"),                          # Vietnamese combining marks
    ("Trepinski�S", "TREPINSKIS"),            # U+FFFD deleted
    ("JOSE MU�OZ", "JOSE MUOZ"),              # the similarity case
    ("SMITH­JONES", "SMITHJONES"),            # soft hyphen deleted
    ("1199 SEIU", "1199 SEIU"),                    # digits survive
    ("FRIENDS OF JANE DOE 2025", "FRIENDS OF JANE DOE 2025"),
    ("...", None),                                 # punctuation only
    ("", None),
    ("   ", None),
    (None, None),
]


def main() -> int:
    for raw, expected in GOLDEN_VECTORS:
        got = name_norm(raw)
        flag = "ok " if got == expected else "BAD"
        print(f"{flag} {raw!r:34s} -> {got!r}")
        if got != expected:
            print(f"      expected {expected!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_normalize.py -v`
Expected: PASS, 31 tests (22 golden vectors + 9 behaviour tests).

- [ ] **Step 5: Commit**

```bash
git add src/vocab/normalize.py tests/test_normalize.py
git commit -m "feat: canonical name normalization with golden vectors"
```

---

## Task 8: Generate the Postgres function and DuckDB macro

**Files:**
- Create: `src/vocab/sql_gen.py`
- Create: `src/vocab/generated/name_norm_pg.sql` (generated)
- Create: `src/vocab/generated/name_norm_duckdb.sql` (generated)

- [ ] **Step 1: Write the failing test**

Create `tests/test_sql_gen.py`:

```python
from src.vocab.sql_gen import duckdb_sql, postgres_sql


def test_postgres_sql_is_immutable_and_names_the_function():
    sql = postgres_sql()
    assert "CREATE OR REPLACE FUNCTION vocab.name_norm" in sql
    assert "IMMUTABLE" in sql
    assert "unaccent" not in sql.lower(), "unaccent is STABLE; must not be used"


def test_duckdb_sql_defines_the_macro():
    sql = duckdb_sql()
    assert "CREATE OR REPLACE MACRO name_norm" in sql


def test_duckdb_macro_actually_deletes_what_it_claims(duckdb_conn):
    """A string-presence assertion cannot catch the defect this guards. The
    escaped form '[\\xFFFD\\x00AD]' is accepted by DuckDB without error and is a
    class of the LETTERS A, D and F -- it turned 'ADAM FOX' into 'M OX' and left
    U+FFFD in place. So execute the generated SQL and check behaviour."""
    from src.vocab.sql_gen import duckdb_sql

    duckdb_conn.execute(duckdb_sql())
    row = duckdb_conn.execute(
        "select name_norm(?), name_norm(?), name_norm(?)",
        ["ADAM FOX", "DAVID", "JOSE\ufffd MUNOZ"],
    ).fetchone()
    assert row[0] == "ADAM FOX", "the delete class is eating letters"
    assert row[1] == "DAVID", "the delete class is eating letters"
    assert row[2] == "JOSE MUNOZ", "U+FFFD was not deleted"


def test_generated_files_are_in_sync(repo_root):
    """Regenerate with: python3 -m src.vocab.sql_gen --write"""
    gen = repo_root / "src" / "vocab" / "generated"
    assert (gen / "name_norm_pg.sql").read_text(encoding="utf-8") == postgres_sql()
    assert (gen / "name_norm_duckdb.sql").read_text(encoding="utf-8") == duckdb_sql()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_sql_gen.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.vocab.sql_gen'`.

- [ ] **Step 3: Write the generator**

`src/vocab/sql_gen.py`:

```python
"""Emit the Postgres function and DuckDB macro from src/vocab/normalize.py.

Neither engine's SQL is authored by hand. The whole point is that there is one
definition of name_norm and two generated bindings to it, so a change cannot
land in one engine and not the other. tests/test_cross_engine.py proves the
bindings agree with the Python original on every golden vector.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.vocab.normalize import DELETE_CHARS, translate_pairs

__all__ = ["duckdb_sql", "postgres_sql", "main"]

_HEADER = (
    "-- GENERATED by src/vocab/sql_gen.py from src/vocab/normalize.py.\n"
    "-- Do not edit. Regenerate with: python3 -m src.vocab.sql_gen --write\n"
)


def _duckdb_literal(text: str) -> str:
    """A DuckDB string literal carrying the real codepoints.

    DuckDB has no `U&'...'` literal -- it parses the leading `U` as a column
    name and raises BinderException -- and no `\\uXXXX` escape in a plain
    string either. So the characters are embedded directly in the UTF-8 file,
    with `'` doubled. This is the same rule as the delete class: always embed
    the real codepoint, never an escape that looks like one.
    """
    return "'" + text.replace("'", "''") + "'"


def _pg_literal(text: str) -> str:
    """A Postgres string literal, with non-ASCII written as U&'...' escapes so the
    file stays ASCII and cannot be corrupted by an editor or a locale."""
    parts: list[str] = []
    for ch in text:
        if ch.isascii() and ch.isprintable() and ch != "'":
            parts.append(ch)
        else:
            parts.append(f"\\{ord(ch):04X}")
    return "U&'" + "".join(parts) + "'"


def postgres_sql() -> str:
    src, dst = translate_pairs()
    return f"""{_HEADER}
CREATE SCHEMA IF NOT EXISTS vocab;

-- Accent folding as an explicit character list, enumerated from Python's
-- unicodedata. translate() deletes characters that appear in the first argument
-- with no counterpart in the second, which is how U+FFFD and U+00AD are removed.
CREATE OR REPLACE FUNCTION vocab.fold_ascii(src text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $$
  SELECT translate(src, {_pg_literal(src)}, {_pg_literal(dst)});
$$;

CREATE OR REPLACE FUNCTION vocab.name_norm(src text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT nullif(btrim(regexp_replace(
           upper(vocab.fold_ascii(src)), '[^A-Z0-9]+', ' ', 'g')), '');
$$;
"""


def duckdb_sql() -> str:
    """Emit the DuckDB macros from the SAME translate table as Postgres.

    Deliberately NOT strip_accents(). DuckDB has translate(), so both engines can
    be driven by one table generated from one Python definition -- which makes
    them agree by construction instead of by coincidence. The earlier design used
    strip_accents() here and translate() there, and the two folds differ on 1,519
    codepoints. Precomposed input happened to agree, which is why an all-NFC
    vector set never caught it; decomposed input did not. Measured then:

        NFD "JOSE MUNOZ"     -> duckdb 'JOSE MUNOZ'     postgres 'JOSE MUN OZ'
        NFD "Nguyen Thi Hoa" -> duckdb 'NGUYEN THI HOA' postgres 'NGUYE N THI HOA'

    A spurious space inside a surname is worse than a missing fold: it silently
    splits one name into two tokens on every join. With one shared table all 19
    golden vectors agree in Python, Postgres and DuckDB, decomposed cases
    included.
    """
    src, dst = translate_pairs()
    return f"""{_HEADER}
CREATE OR REPLACE MACRO fold_ascii(s) AS
  translate(s, {_pg_literal(src)}, {_pg_literal(dst)});

CREATE OR REPLACE MACRO name_norm(s) AS
  nullif(trim(regexp_replace(upper(fold_ascii(s)), '[^A-Z0-9]+', ' ', 'g')), '');
"""


def main(argv: list[str] | None = None) -> int:
    out_dir = Path(__file__).resolve().parent / "generated"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=out_dir)
    args = parser.parse_args(argv)

    targets = {
        "name_norm_pg.sql": postgres_sql(),
        "name_norm_duckdb.sql": duckdb_sql(),
    }
    if args.write:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for name, text in targets.items():
            (args.out_dir / name).write_text(text, encoding="utf-8")
            print(f"wrote {args.out_dir / name}")
    else:
        for name, text in targets.items():
            print(f"--- {name} ---")
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate, then run the test**

```bash
python3 -m src.vocab.sql_gen --write
python3 -m pytest tests/test_sql_gen.py -v
```

Expected: two `wrote ...` lines, then PASS, 3 tests.sql
```

- [ ] **Step 5: Commit**

```bash
git add src/vocab/sql_gen.py src/vocab/generated/ tests/test_sql_gen.py
git commit -m "feat: generate the Postgres function and DuckDB macro from one source"
```

---

## Task 9: Cross-engine equality test

This is the test the whole plan exists to make possible. Two engines disagreeing on whether `SMITH, JOHN A` keeps its comma is a **zero-rows-not-an-error** failure on every fact-to-dimension join.

**Files:**
- Test: `tests/test_cross_engine.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cross_engine.py`:

```python
"""Assert Python, DuckDB and Postgres normalize names identically.

The failure this prevents: one engine writing SMITH, JOHN A and the other
SMITH JOHN A, so every join between the Parquet fact rows and the Postgres
name dimension returns nothing -- silently, with no error anywhere.
"""

from pathlib import Path

import pytest

from src.vocab.normalize import GOLDEN_VECTORS, name_norm

GENERATED = Path(__file__).resolve().parents[1] / "src" / "vocab" / "generated"
VECTORS = [(raw, expected) for raw, expected in GOLDEN_VECTORS if raw is not None]


@pytest.fixture(scope="module")
def duckdb_with_macros(duckdb_conn):
    duckdb_conn.execute((GENERATED / "name_norm_duckdb.sql").read_text(encoding="utf-8"))
    return duckdb_conn


@pytest.fixture(scope="module")
def pg_with_functions(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute((GENERATED / "name_norm_pg.sql").read_text(encoding="utf-8"))
    pg_conn.commit()
    return pg_conn


@pytest.mark.parametrize("raw,expected", VECTORS)
def test_duckdb_matches_python(duckdb_with_macros, raw, expected):
    got = duckdb_with_macros.execute("SELECT name_norm(?)", [raw]).fetchone()[0]
    assert got == expected, f"duckdb({raw!r}) = {got!r}, python = {expected!r}"


@pytest.mark.postgres
@pytest.mark.parametrize("raw,expected", VECTORS)
def test_postgres_matches_python(pg_with_functions, raw, expected):
    with pg_with_functions.cursor() as cur:
        cur.execute("SELECT vocab.name_norm(%s)", [raw])
        got = cur.fetchone()[0]
    assert got == expected, f"postgres({raw!r}) = {got!r}, python = {expected!r}"


@pytest.mark.postgres
def test_all_three_agree_on_every_vector(pg_with_functions, duckdb_with_macros):
    """One assertion over the whole set, so a failure reports every divergence
    at once rather than one parametrized case at a time."""
    divergences = []
    for raw, _ in VECTORS:
        py = name_norm(raw)
        duck = duckdb_with_macros.execute("SELECT name_norm(?)", [raw]).fetchone()[0]
        with pg_with_functions.cursor() as cur:
            cur.execute("SELECT vocab.name_norm(%s)", [raw])
            pg = cur.fetchone()[0]
        if not (py == duck == pg):
            divergences.append((raw, py, duck, pg))
    assert not divergences, "python/duckdb/postgres disagree:\n" + "\n".join(
        f"  {raw!r}: py={py!r} duck={duck!r} pg={pg!r}"
        for raw, py, duck, pg in divergences
    )


@pytest.mark.postgres
def test_the_replacement_character_rule_earns_its_keep(pg_with_functions):
    """Deleting U+FFFD rather than spacing it is what keeps the damaged NYSBOE
    rows matchable. Assert the trigram similarity actually clears 0.6."""
    with pg_with_functions.cursor() as cur:
        cur.execute("SELECT similarity('JOSE MUOZ', 'JOSE MUNOZ')")
        deleted = cur.fetchone()[0]
        cur.execute("SELECT similarity('JOSE MU OZ', 'JOSE MUNOZ')")
        spaced = cur.fetchone()[0]
    assert deleted > 0.6 > spaced, (
        f"deleting U+FFFD gives {deleted}, spacing gives {spaced}; "
        "the rule in normalize.py depends on deleted > 0.6 > spaced"
    )
```

- [ ] **Step 2: Run it to verify the DuckDB leg fails first, then passes**

Run: `python3 -m pytest tests/test_cross_engine.py -v`

Expected: the DuckDB legs PASS (Task 8 generated a working macro). The Postgres legs PASS locally, or SKIP if no local database.

If any vector diverges, both engines now run the *same* generated `translate()` table, so the cause is not a fold mismatch — it is a codepoint outside the table altogether. Fix by widening `max_codepoint` in `translate_pairs()` (or adding a `STROKE_FOLDS` entry if NFD cannot express the fold), regenerating, and re-running — **not** by deleting the vector. A vector deleted to make a suite green is a name that will silently fail to join in production.

Note: `test_the_replacement_character_rule_earns_its_keep` needs `pg_trgm`. If it errors with `function similarity(text, text) does not exist`, run `psql -d ploppy -c "CREATE EXTENSION IF NOT EXISTS pg_trgm"` first.

- [ ] **Step 3: Verify both engines really ran**

Run: `python3 -m pytest tests/test_cross_engine.py -v -m postgres`
Expected: the Postgres-marked tests run and pass. If they all SKIP, the Postgres leg is not being exercised and the test is giving false confidence — set `PLOPPY_TEST_DSN` and re-run.

- [ ] **Step 4: Confirm the full suite is green**

Run: `python3 -m pytest -v`
Expected: all tests pass. The count should be about **206** with Postgres available
(44 code_key + 74 code_mappings + 3 program_ab + 34 normalize + 4 sql_gen + 50 cross_engine).
Treat these counts as a sanity check, not a contract: a number materially below them means
tests were skipped or not collected, which is precisely what `-ra` and
`PLOPPY_REQUIRE_ENGINES=1` exist to make visible.
A materially lower number means tests are being skipped or a module failed to collect — read
the summary line rather than trusting the green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cross_engine.py
git commit -m "test: assert Python, DuckDB and Postgres normalize names identically

The failure this prevents is silent: one engine emitting SMITH, JOHN A and the
other SMITH JOHN A makes every fact-to-dimension join return zero rows with no
error. Both engines run the same generated translate() table, so they agree by
construction rather than coincidence -- but equality is still asserted per
vector, because construction is a claim and the test is the evidence."
```

---

## Task 10: CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: ploppy
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      PLOPPY_TEST_DSN: "host=localhost port=5432 user=postgres password=postgres dbname=ploppy"
      # Without this a failed pip install would skip every cross-engine test and
      # still report green -- the exact false confidence this switch exists to
      # prevent. Under it, a missing engine is a failure, not a skip.
      PLOPPY_REQUIRE_ENGINES: "1"

    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-python@v6
        with:
          python-version: "3.13"

      - name: Install test dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest==9.2.0 duckdb==2.0.0 psycopg[binary]==3.3.8 pandas

      - name: Create extensions
        run: |
          PGPASSWORD=postgres psql -h localhost -U postgres -d ploppy \
            -c "CREATE EXTENSION IF NOT EXISTS pg_trgm"

      - name: Verify the generated artifacts are in sync
        run: |
          python -m src.vocab.code_key --write
          python -m src.vocab.sql_gen --write
          git diff --exit-code -- src/vocab/codes.json src/vocab/generated/

      - name: Run tests
        run: python -m pytest -v
```

The Python version differs from local on purpose (CI 3.13, local 3.12.7), and that is safe
for the generated artifacts: the `translate()` table is derived from `unicodedata`, and it
comes out byte-identical under Unicode 13.0, 15.0 and 15.1 — same 504 folds, 115 deletes,
same digest. Checked across Python 3.9.6, 3.12.7 and 3.13.0 rather than assumed, because if
it did vary, `git diff --exit-code` would fail CI on a correctly generated file and the
cause would be invisible.

Two things that workflow does deliberately. It **regenerates and diffs** the artifacts, so a hand-edited `codes.json` or `name_norm_pg.sql` fails the build rather than silently diverging from its source. And it stands up a real Postgres, because the cross-engine test is worthless if the Postgres leg skips — on PG17, `fuzzystrmatch` would also give `daitch_mokotoff`, which a later plan needs.

`tests/test_program_ab.py`'s data-backed test SKIPS in CI, but only because it guards on
`to_regclass('public.cfb_contributions')` being non-NULL. An earlier draft of this plan
claimed it would skip on its own; it would not — it was marked `postgres` with no in-body
guard, so against CI's empty service database it FAILED with `UndefinedTable`. Verified by
running the suite against a scratch empty database: `1 failed, 205 passed`. The guard draws
the right line: a missing **engine** is a failure, because the engine is part of what we
ship, while missing **data** is a skip, because the data is not in the repo. `-ra` in
`addopts` prints the reason, so the skip is visible rather than silent.
- [ ] **Step 2: Verify the workflow is valid YAML**

```bash
python3 -I -c "
import sys
try:
    import yaml
except ImportError:
    sys.exit('pip install pyyaml to validate locally, or push and read the Actions log')
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print('jobs:', list(d['jobs']))
print('steps:', len(d['jobs']['test']['steps']))
"
```

Expected: `jobs: ['test']` and `steps: 6`.

- [ ] **Step 3: Run the same checks locally that CI runs**

```bash
python3 -m src.vocab.code_key --write
python3 -m src.vocab.sql_gen --write
git diff --exit-code -- src/vocab/codes.json src/vocab/generated/
python3 -m pytest -v
```

Expected: no diff, all tests pass. If `git diff --exit-code` fails here, a generated file was edited by hand — discard the edit and change its source instead.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run the suite with a real Postgres and diff generated artifacts"
```

- [ ] **Step 5: Push and confirm CI is green**

```bash
git push -u origin claude/application-startup-a6fde1
```

Then read the Actions log. A red build here is a real failure, not flake — most likely a codepoint outside the generated `translate()` table that the local run did not exercise, or a generated file committed stale (which `git diff --exit-code` catches).

---

## The one step not generated

Every part of the fold is generated from one table, with one exception: **`upper()` is
applied independently by each engine**, and the three do not agree about it. Python's
`str.upper()` performs *full* case mapping (one-to-many); SQL `upper()` in both Postgres and
DuckDB performs *simple* case mapping. Measured before the fix:

```
'Weiß, Hans'  ->  python 'WEISS HANS'   postgres 'WEI HANS'   duckdb 'WEI HANS'
'Oﬃce, Jane'  ->  python 'OFICE JANE'   postgres 'O CE JANE'  duckdb 'O CE JANE'
```

Note the shape: Postgres and DuckDB agreed with each other and **Python was the outlier**,
the reverse of every other divergence in this plan. `Weiß` is a real surname, and a name
that normalizes two ways is a join that silently returns nothing — exactly the failure this
plan exists to prevent, surviving in the one place the generator did not reach.

The fix enumerates the affected characters from `unicodedata` rather than guessing: of the
102 codepoints in U+0020..U+1FFFF whose uppercase is multi-character, exactly **8** expand to
ASCII letters (`ß` and the ff/fi/fl/ffi/ffl/st ligatures). Those are expanded explicitly in
`EXPAND_FOLDS` and reproduced in both dialects by a generated `replace()` chain. The other 94
expand to non-ASCII and become spaces in all three engines alike, so they need no entry. A
test re-derives that set from `unicodedata`, so a future Unicode addition fails loudly
instead of silently diverging.

Expanding is also the better normalization, not merely the consistent one: `Weiß` genuinely
should match `Weiss`.

## Definition of done

- [ ] `PLOPPY_REQUIRE_ENGINES=1 ./.venv/bin/python3 -m pytest -v` passes locally. Under that
  variable a missing engine or an unreachable database is a **failure**, not a skip, so a green
  run proves the duckdb and Postgres legs actually ran. The report header prints the interpreter
  and both engine versions.
- [ ] `git diff --exit-code -- src/vocab/codes.json src/vocab/generated/` is clean after regenerating.
- [ ] `src/database/code_mappings.py` contains no hand-typed code dict.
- [ ] `get_office_name("11")` returns a label containing "Program A".
- [ ] `get_schedule_description("M")` returns "Receipt Adjustments".
- [ ] `1253 not in PAYMENT_METHODS`.
- [ ] `python3 -c "import src.database.db_manager_v2"` exits 0.
- [ ] CI is green on the branch.

## What this plan does not do

Named here so the next plan does not have to rediscover them:

- **Does not touch `pyproject.toml`.** It is 90,942 bytes, named `repl-nix-workspace`, and pins hundreds of unused packages to a pytorch-cpu index. Rewriting it belongs with the app plan, where the Vercel bundle budget makes it matter.
- **Does not delete `test_everything.py` or `test_app.py`.** Both are print-based scripts; `testpaths = tests` excludes them.
- **Does not fix the Program A/B *numbers*.** The spec records three different Program B averages under three different predicates. Choosing and publishing one predicate belongs with the rollup-semantics plan, which owns measure definitions.
- **Does not load the codes into Postgres.** Nothing needs a SQL join on labels yet. The rollup plan adds `code_set`/`code_value` tables fed from the same artifact.
- **Does not address `data_dictionary.md`,** which is wrong on the same points as the old dicts were. It is documentation, not code, and the pipeline plan rewrites it from `codes.json`.
- **Does not fix `is_individual_name`.** It classifies a name as an organization if the
  name *contains* any of `INC`, `PAC`, `CO.`, `GROUP` and similar as a plain substring, so
  every person named **Vincent** (`V-INC-ent`), **Princess** (`Pr-INC-ess`) or **DePace**
  (`De-PAC-e`) is called an organization. Measured against the contributors table:
  **4,690 of 885,629** names that CFB itself codes `c_code='IND'` are misclassified, or
  0.53%. Left untouched because this plan froze those three functions byte-identical and
  because changing the classification changes behaviour the app already depends on. The
  real fix is word-boundary matching plus trusting `c_code` first, and it belongs with the
  identity plan, which owns entity classification.
- **Does not fix the loader's falsy-zero guards.** `src/database/db_manager_v2.py:517`
  reads `get_payment_method(pay_method) if pay_method else None`, and `pay_method = 0`
  is falsy, so **135,005 rows** are stored as NULL rather than "Unknown". Line 521 has
  the same shape for `adjtypecd = 0`, and line 331 for a blank `boroughcd`. Correcting
  the labels does not help a caller that never asks. This belongs with the ETL pipeline
  plan, which owns the loader; recorded here with the measured count so it is not
  rediscovered. Note the fix is `is not None`, not a truthiness test.
- **Does not fold multi-character ligatures *in the translate table*.** `translate()` is
  strictly 1:1, so Æ→AE and Œ→OE cannot be expressed there; all three engines turn them
  into a space consistently, so cross-engine equality holds and the fold is simply lossy.
  The eight characters whose *uppercase* is multi-character and ASCII (ß and the f/st
  ligatures) are a different matter and ARE handled, via `EXPAND_FOLDS` and a generated
  `replace()` chain — because there Python and SQL actively disagreed rather than merely
  being lossy together. See § the `upper()` asymmetry below.
- **Does not correct `ELECTION_TYPES`.** The original map sends election-token
  suffixes `B` and `C` to "General" when they are special elections, and `parse_election_cycle`
  persists the result into `elections.election_type` (`db_manager_v2.py:79`). Fixing the map
  therefore changes the meaning of already-stored rows, which is a migration rather than a
  label fix. Left exactly as found; the pipeline plan owns it.
- **Does not clean the literal string `'None'`.** `canclass` holds the four-character
  string `'None'` on 20 rows -- a Python `None` stringified at load time rather than a
  NULL. Harmless at this scale and invisible to label lookup (it resolves to Unknown),
  but it means the loader stringifies before writing, so other columns may carry the
  same artifact. The pipeline plan owns it.
- **Does not re-load `exemptcd`.** The column is NULL on 2,123,656 of 2,123,892 rows and
  `''` on none, so CFB's documented blank code was flattened to NULL at load time. This
  plan's accessor resolves NULL to the documented code, which is the right read-side
  behaviour; whether to store `''` instead is the pipeline plan's call.
- **Does not add `daitch_mokotoff`.** It needs `fuzzystrmatch` 1.2, i.e. PG16+, and the laptop is PG14.13. The local upgrade is a prerequisite for the identity plan, not this one.
