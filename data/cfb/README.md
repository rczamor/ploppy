# NYC Campaign Finance Board exports + NYSBOE filer registry

Four bulk files, loaded as **staging tables** that mirror the exports column for
column. The repo's normalized schema is populated from these, so a reload never
has to re-parse 540 MB of CSV.

```bash
python3 scripts/load_cfb_filers.py --dbname ploppy \
    --contributions  ~/Downloads/CFB_<ts>.csv \
    --expenditures   ~/Downloads/CFB_<ts>.csv \
    --intermediaries ~/Downloads/CFB_<ts>.csv \
    --filers         ~/Downloads/ListOfFilers.csv
```

The loader refuses to start if a file's column count does not match the flag it
was passed under, since the three CFB exports are distinguishable only by their
headers (52 / 32 / 24 columns) and their filenames are just timestamps.

## Files

| Table | Source file | Rows | Columns | `sum(AMNT)` |
|---|---|---|---|---|
| `cfb_contributions` | `CFB_…140106946.csv` | 2,123,892 | 52 | $709,597,913.31 |
| `cfb_expenditures` | `CFB_…142252262.csv` | 669,276 | 32 | $1,120,064,358.68 |
| `cfb_intermediaries` | `CFB_…142254062.csv` | 7,260 | 24 | $54,069,104.12 |
| `nysboe_filers` | `ListOfFilers.csv` | 81,483 | 20 (+1) | — |

CSVs are **not** committed — they live in `~/Downloads` and are re-exportable.

## `REFNO` is not a transaction id

This is the single most important thing to know before querying or normalizing.

The repo's `public.contributions` carries `UNIQUE (refno)`. **The CFB data cannot
satisfy it.** `REFNO` is a filing *page* reference and repeats across candidates
and filings:

| | |
|---|---|
| Rows | 2,123,892 |
| Distinct `REFNO` | 204,266 |
| Rows sharing a `REFNO` | 2,033,177 (96%) |
| Worst offender | `P0001-01`, 4,490 times |

Loading this into a `UNIQUE(refno)` column would have silently discarded about
**90% of the file**. Even `(election, recipid, filing, schedule, refno)` still
collides 2,549 times, and `PAGENO`/`SEQUENCENO` cannot break the tie because they
are blank in every row of this export. Nothing short of the entire row is unique.

So the staging tables use a generated `id`, and the composite is indexed
**non-uniquely** (`cfb_contrib_txn_idx`). Any normalization step must choose a
dedup rule deliberately rather than leaning on a constraint.

## The two exports overlap — do not sum them

Schedules `D` and `X` appear in **both** the contributions and expenditures
exports, with identical row counts. Treat the pair as overlapping sets, not as
disjoint halves of a ledger.

| Schedule | In `cfb_contributions` | In `cfb_expenditures` |
|---|---|---|
| `ABC` contributions | 2,069,541 | — |
| `M` matchable | 39,361 | — |
| `F` expenditures | — | 636,606 |
| `D` | 12,661 | 12,661 |
| `X` | 1,504 | 1,504 |
| `N` | 771 | 12,144 |
| `L` | — | 5,860 |
| `G` | 54 | — |
| `H` / `Y` | — | 334 / 167 |

## Columns the export never fills

Kept so the tables mirror the files, but always blank — do not build on them:

- both: `PAGENO`, `SEQUENCENO`, `STRNO`, `STRNAME`, `APARTMENT`
- contributions also: `INTSTRNO`, `INTSTRNM`, `INTAPTNO`

Street address is therefore **unavailable** for contributors; only
city / state / zip / borough are populated.

## Intermediaries (bundlers)

`cfb_intermediaries` is the bundler registry for the contributions export:
**100% of the 131,905 `INTERMNAME` values in `cfb_contributions` resolve to a
name here.** It is *not* an aggregate of it — the amounts do not reconcile
(sampled keys came out $7,250 here vs $4,950 there), so it covers filings beyond
the contributions export's reach.

Note `INTERMNO` is filled on only 94,489 rows while `INTERMNAME` is filled on
131,905 — 37,416 rows name a bundler without numbering one, so join on the name,
not the number.

## `nysboe_filers` — the join NYSBOE data was missing

`data/nysboe/README.md` noted that filer names live in a separate table. This is
it, and coverage is complete: **all 13,707 distinct `filer_id`s in
`nysboe_contributions` resolve here**, out of 64,795 in the registry.

```sql
SELECT c.filer_id, f.name, f.status, sum(c.org_amt) AS raised
FROM   nysboe_contributions c
JOIN   nysboe_filers f ON f.filer_id = c.filer_id
GROUP  BY 1, 2, 3 ORDER BY raised DESC LIMIT 10;
```

**`filer_id` is not unique** — 81,483 rows over 64,795 ids, because a filer
recurs per candidate and election year. An unqualified join fans out and will
multiply contribution amounts. Qualify it, or aggregate the registry first.

## The CSV quoting defect

`ListOfFilers.csv` is not valid RFC 4180. **119 rows** contain quotes inside a
quoted field that are not doubled — overwhelmingly nicknames:

```
"Committee To Elect Mary Eileen "Mel" Callan, R.N."
"Sysounthone Somboun "April""
```

A conforming parser ends the field at the inner quote, so the following comma
becomes a delimiter and **every later field shifts right by one** — dates land in
name columns, names in year columns. Postgres `COPY` rejects these rows outright;
Python's `csv` module silently mangles them, and the quote count stays even, so an
unbalanced-quote check sees nothing wrong. Only a *strict* parse reveals them.

`scripts/repair_listoffilers.py` fixes all 119 by **quote-run parity**: inside a
quoted field, a run of quotes followed by ordinary text must be even (literal
quotes, doubled), and a run followed by a delimiter must be odd (literals plus
the closer). Parity is what separates a genuinely quote-terminated value, encoded
with a run of 3, from the broken form's run of 2 — a naive "double anything not
already doubled" pass corrupts the first while still failing on the second.

The repair only touches rows that already fail a strict parse, keeps the rewrite
only if the field count then comes out right, re-checks the whole output
strictly, and **exits non-zero rather than dropping a row it cannot fix**. The
loader aborts on that, so a partial repair can never become a quiet partial load.
Your source file is never modified; the repaired copy is written elsewhere.

Two more quirks handled in passing:

- Every data row carries a **21st trailing empty field** the 20-column header
  does not name — hence `nysboe_filers.trailing_blank`, which is always NULL.
- All four files end with a **blank line**, which `COPY` reads as a row
  (`missing data for column …`). It cannot be fixed by filtering blank lines,
  because the contributions export has real newlines *inside* quoted fields, so
  the loader streams the file and withholds blank lines until a non-blank line
  proves they were interior.

## Dates

All date columns are `M/D/YYYY`. The loader sets `datestyle` to `ISO, MDY`
explicitly on every connection rather than trusting the server default — under
`DMY`, `4/16/1991` would parse as a different day or fail depending on the value.

A handful of dates fall outside 1970–2030 (24 in contributions `DATE`, 1 in
`REFUNDDATE`, 9 in expenditure `INV_DATE`, 3 in filer `Termination Date`). These
are filer typos, retained as filed.

## Type choices

`election`, `officecd`, `recipid`/`candid`, `district` stay **text**: `election`
carries suffixes (`2026A`, `2001T`), `officecd` includes `IS` for independent
spending, candidate ids are alphanumeric (`Y2`, `D4`), and 9–13% of filled
district values are non-numeric.

`pay_method` is `integer` on contributions but `text` on expenditures — the two
exports genuinely disagree, the latter carrying words like `Unknown`.

## Normalized layer

```bash
psql -d ploppy -f scripts/cfb_normalize.sql
```

Rebuilds the repo's normalized schema from the staging tables. Idempotent — it
truncates and repopulates, so a mapping can be fixed and re-run without touching
the CSVs. One transaction, about 4 minutes.

| Table | Rows |
|---|---|
| `contributions` | 2,123,892 — $709,597,913.31 |
| `expenditures` | 669,276 — $1,120,064,358.68 |
| `contributors` | 946,403 |
| `employers` | 341,156 |
| `locations` | 75,203 |
| `filings` | 24,335 |
| `intermediaries` | 6,116 |
| `recipients` | 2,023 |
| `elections` | 76 |

**Every row loaded** — both fact tables carry the full file, and their totals match
the staging tables and the CSVs to the cent.

### What it had to change

`contributions.refno` and `expenditures.reference_number` both carried UNIQUE
constraints that this data cannot satisfy (see above). Both are replaced with
non-unique indexes. Without that, the two inserts would have kept 204,266 and
62,308 rows instead of 2.1M and 669K.

### Foreign-key coverage

| FK | Resolved | Why not 100% |
|---|---|---|
| `recipient_id`, `election_id`, `filing_id` | 100% | — |
| `contributor_id` | 100% | — |
| `location_id` | 97.9% | rows with no city/state/zip at all |
| `employer_id` | 70.8% | `EMPNAME` blank on 619,203 rows |
| `intermediary_id` | 6.2% | only 131,905 rows name a bundler |

The shortfalls are **missing source data, not failed joins** — verified as a set
problem rather than by a row join (a row join on `refno` fans out and invents
failures): of 946,403 distinct contributor names, 340,609 employer names and
6,116 intermediary names in the staging data, **0 failed to resolve**.

### One caveat before you trust `contributors`

`contributors.normalized_name` is UNIQUE, so the dedup key is
`upper(trim(collapse whitespace))` on the name alone — the repo's own design.
Consequence: **every distinct person sharing a name collapses into one row.**
`SMITH, JOHN` in Brooklyn and in Buffalo are the same contributor, and
`total_contributions` / `contribution_count` on that row sum across all of them.
The 2,123,892 contributions rows still each point at their own as-filed values,
and `cfb_contributions` keeps every row exactly as exported.

Use `contributors` for name-level rollups. Use `cfb_contributions`, or
`contributions` joined to it, for anything per-person or per-transaction.
