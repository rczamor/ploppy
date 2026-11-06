# NY State Board of Elections — contribution records, 2016 to present

Every itemized **contribution** record the NYSBOE holds with a transaction date of
2016-01-01 or later.

Regenerate or resume with:

```bash
python3 scripts/download_nysboe_contributions.py
```

## Source

The bulk download UI at <https://publicreporting.elections.ny.gov/DownloadCampaignFinanceData/DownloadCampaignFinanceData>
serves per-year/per-period ZIPs (`2016gen.zip`, `2016jan.zip`, … plus `ALL_REPORTS.zip`)
from `cfapp.elections.ny.gov`. Both hosts sit behind a bot check that returns HTTP 403
to scripted clients, so they are not usable for an automated pull.

NYSBOE publishes the same itemized disclosure data — **identical 63-column record
layout** — through the state open data portal, which is the supported programmatic
path and what this download uses:

| | |
|---|---|
| Dataset | `e9ss-239a` — "Campaign Finance Disclosure Reports Data: Beginning 1999" |
| Landing page | <https://data.ny.gov/d/e9ss-239a> |
| API | `https://data.ny.gov/resource/e9ss-239a.csv` (Socrata SoQL) |
| Publisher | New York State Board of Elections |

## Files

| File | Contents |
|---|---|
| `contributions_2016_present.csv` | Contribution records with `sched_date >= 2016-01-01`. Ordered by `filing_trans_id`. |
| `contributions_null_sched_date.csv` | 169 contribution records (all years) whose `sched_date` is blank, so they cannot be placed in a year. Kept separate rather than dropped. |
| `manifest.json` | Source, filter, timestamp, row counts, and whether counts matched the server's own totals. |

CSVs are gitignored — they are ~2.3 GB and regenerable.

## What counts as a "contribution"

Filtered to the four contribution-receipt schedules:

| Schedule | Description | Rows (2016+) |
|---|---|---|
| A | Monetary Contributions Received From Ind. & Part. | 5,505,692 |
| B | Monetary Contributions Received From Corporation | 261,473 |
| C | Monetary Contributions Received From All Other | 364,687 |
| D | In-Kind (Non-Monetary) Contributions Received | 50,813 |
| | **Total** | **6,182,665** |

### Deliberately excluded

These are in the same source dataset but are not contributions received. Add the
abbreviation to `SCHEDULES` in the script if you want any of them:

`E` Other Receipts · `F` Expenditures/Payments · `G` Transfers In · `H` Transfers Out ·
`I` Loans Received · `J` Loan Repayments · `K` Liabilities/Loans Forgiven ·
`L` Expenditure Refunds · `M` Contributions Refunded · `N` Outstanding Liabilities/Loans ·
`O` LLCs/Partnership/Subcontractor · `P` Non-Campaign Housekeeping Receipts ·
`Q` Non-Campaign Housekeeping Expenses · `R` Expense Allocation Among Candidates ·
`S` Public Fund Receipts · `T` Qualified Expenditures · `U` Public Fund Repayment

`M` (Contributions Refunded) is the one most likely to matter: net it against A–D if
you need refund-adjusted totals.

## Caveats from the agency

- Reports are loaded exactly as filed. Misspellings, miscoded fields, and blanks are
  reproduced verbatim; amendments arrive as separate rows (`r_amend`).
- **Accented characters are corrupted at the source.** Every non-ASCII character in
  the dataset (161 rows) is U+FFFD REPLACEMENT CHARACTER — the original letter is
  gone, not merely transliterated. Confirmed against the live API. See the accent
  folding section below.
- Some `sched_date` values are filer typos and fall in the future (up to 2039). They
  are retained — they are real records with bad dates. Filter on `sched_date` if a
  clean window matters.
- NYC municipal campaigns (Mayor, Council, Public Advocate, Comptroller, Borough
  President) **from 2020 onward** file with the NYC Campaign Finance Board, not
  NYSBOE, so they are absent here. That data is the NYC CFB set this repo already
  handles.
- Filer names live in a separate filer table (`commcand.csv` in the UI, or dataset
  `7x2g-h32p` on the portal); join on `filer_id`. `cand_comm_name` is denormalized
  into these rows already.
- Pre-July-1999 reports are not in the database at all (paper records held by the
  State Archives).

## Postgres

Loaded into the local `ploppy` database as table **`nysboe_contributions`**:

```bash
python3 scripts/load_nysboe_contributions.py --dbname ploppy --include-null-dates
```

| | |
|---|---|
| Rows | 6,182,834 (6,182,665 dated + 169 undated) |
| Size | 2,576 MB including indexes |
| `sum(org_amt)` | $2,667,284,009.05 — matches the CSV to the cent |
| Distinct filers | 13,707 |
| Distinct contributor names | 230,879 |

Kept as **its own table, not merged into `contributions`** (the NYC CFB table):
different filing authority, different column set, and a disjoint
`filing_trans_id` space. Merging would mean discarding NYSBOE-only fields or
inventing nulls on both sides. Build a view if you need unified reporting.

Types: `filing_trans_id` is the primary key (`bigint`), `filer_id` `bigint`,
`sched_date`/`org_date` `date`, `org_amt`/`owed_amt` `numeric(16,2)`, the
`r_*` flags stay `text` because blank is distinct from `N` as filed. Everything
else is `text`. All 6.18M rows parsed cleanly — no type coercion failures.

Re-running the loader **drops and recreates** the table.

### Indexes

Btree (10, ~620 MB): `filing_trans_id` (pk), `filer_id`, `sched_date`,
`filing_sched_abbrev`, `election_year`, `org_amt`, `flng_ent_zip`, and `lower()`
on `flng_ent_name`, `flng_ent_last_name`, `cand_comm_name`.

GIN trigram (4, 585 MB) for fuzzy name matching, via `pg_trgm` 1.6:

```bash
psql -d ploppy -f scripts/nysboe_contributions_trgm.sql
```

| Index | Column |
|---|---|
| `nysboe_contrib_ent_name_trgm` | `flng_ent_name` — organizations |
| `nysboe_contrib_ent_last_trgm` | `flng_ent_last_name` — individuals |
| `nysboe_contrib_ent_fullname_trgm` | `coalesce(first,'')‖' '‖coalesce(last,'')` |
| `nysboe_contrib_comm_name_trgm` | `cand_comm_name` — recipient committees |

Contributor identity splits by type: organizations populate `flng_ent_name`
(715,688 rows), individuals populate `flng_ent_first_name` / `flng_ent_last_name`
(~5.23M rows). Both paths are indexed, plus the combined full-name expression that
matches how `scripts/fast_voter_matching.py` joins voters to contributors.

`pg_trgm` folds case internally, so these index raw columns — no `lower()`
wrapper — and they serve `ILIKE '%…%'`, `similarity()` and `%` alike.

**Set the similarity threshold before fuzzy queries.** The 0.3 default is far too
loose at this row count — `% 'Jon Smith'` matched 170,026 rows in 1.9 s. At 0.6 the
same shape of query returns 16,281 rows in 104 ms:

```sql
SET pg_trgm.similarity_threshold = 0.6;
```

Selective `ILIKE` is index-backed and fast (`%Hochul%` 38 ms, `%1199 SEIU%` 10 ms).
A broad pattern like `%friends of%` matches ~900K rows, and the planner correctly
falls back to a parallel seq scan (~630 ms) — that is the right plan, not a missing
index.

### Phonetic + edit distance (`fuzzystrmatch` 1.1)

```bash
psql -d ploppy -f scripts/nysboe_contributions_phonetic.sql
```

| Index | Expression | Size |
|---|---|---|
| `nysboe_contrib_last_dmetaphone_idx` | `dmetaphone(flng_ent_last_name)` | 42 MB |
| `nysboe_contrib_last_soundex_idx` | `soundex(flng_ent_last_name)` | 42 MB |

**`levenshtein()` has no operator class, so it can never be index-driven.** Run it
against an already-narrowed candidate set, never across the table. The working
pattern is *block, then rank* — block on the phonetic index, rank the survivors by
edit distance (97 ms over 6.18M rows):

```sql
SELECT flng_ent_last_name,
       levenshtein(lower(flng_ent_last_name), 'smyth') AS edits,
       count(*)
FROM   nysboe_contributions
WHERE  dmetaphone(flng_ent_last_name) = dmetaphone('Smyth')      -- indexed block
  AND  levenshtein_less_equal(lower(flng_ent_last_name), 'smyth', 2) <= 2
GROUP  BY 1, 2
ORDER  BY edits;
```

Use `levenshtein_less_equal(a, b, max)` rather than `levenshtein(a,b) <= max`: it
aborts once the bound is exceeded instead of computing the full matrix.

That query returns `Smyth` (0 edits), then `Smith`, `Smythe`, `Smth` and the
case variants at 1 edit — 31,303 contributions clustered across spellings.

**Prefer `dmetaphone` over `soundex` for blocking.** Soundex is coarser: `Smith`,
`Smyth` *and* `Schmidt` all collapse to `S530`, while dmetaphone keeps Smith/Smyth
together as `SM0` and separates Schmidt as `XMT`. Soundex is the higher-recall
fallback when dmetaphone blocks find nothing.

Scope: surnames only. Both functions encode a single word, so they are not
meaningful on multi-word organization or committee names — use the trigram indexes
for those. The two families are complementary: trigrams catch transpositions, extra
tokens and substring hits; phonetics catch spellings that *sound* alike but share
few trigrams (`Nguyen`/`Nguyn`, `Schmidt`/`Schmitt`).

Edge cases are safe — no errors on `NULL`, `''`, numeric strings, apostrophes,
hyphens, or accents (`dmetaphone('José')` → `JS`).

### Accent folding (`unaccent` 1.1)

```bash
psql -d ploppy -f scripts/nysboe_contributions_unaccent.sql
```

Installed, with an `immutable_unaccent(text)` wrapper. **No index** — and that is
the finding, not an omission: `unaccent()` changes **0 of 6,182,834 rows**.

All 161 rows with non-ASCII characters hold **U+FFFD REPLACEMENT CHARACTER**, not
accents — upstream mojibake. `Trepinski�S`, `Gutif�Rrez`,
`Quif�Ones`. Verified against the live Socrata API for
`filing_trans_id = 7058108`, which returns the same corrupted bytes, so this is
NYSBOE's data, not a download artifact. The original characters are
unrecoverable. A column-side index would be ~500 MB that can never change a
result.

| Column | Rows non-ASCII | …of which U+FFFD |
|---|---|---|
| `flng_ent_name` | 95 | 95 |
| `flng_ent_last_name` | 68 | 68 |
| `flng_ent_add1` | 29 | 29 |
| `flng_ent_first_name` | 25 | 25 |
| `flng_ent_city` | 6 | 6 |
| `cand_comm_name` | 0 | — |

**Fold the query input, not the column.** That is where the value is: a name
pasted from a system that *does* keep accents will not equal the plain-ASCII
spelling NYSBOE stores. Folding the literal costs one function call and needs no
index, so the existing `lower()` btrees still serve it:

```sql
SELECT * FROM nysboe_contributions
WHERE  lower(flng_ent_last_name) = lower(unaccent('Gutierrez'));  -- accented input
```

| Accented input | Folds to | Rows matched (folded → raw) |
|---|---|---|
| `José` | `Jose` | 10,604 → 0 |
| `Peña` | `Pena` | 1,280 → 0 |
| `Gutiérrez` | `Gutierrez` | 1,021 → 0 |
| `Nuñez` | `Nunez` | 729 → 0 |

**Both `unaccent()` overloads are `STABLE`, not `IMMUTABLE`** — the dictionary is
read from a file on disk — so a direct index on `unaccent(col)` is rejected with
`ERROR: functions in index expression must be marked IMMUTABLE`. That is why
`immutable_unaccent(text)` exists: it pins the dictionary explicitly and asserts
immutability. The assertion is a promise, not a fact — if `unaccent.rules` ever
changes, every index built on it is silently stale and needs a `REINDEX`. Use
`USING gin (immutable_unaccent(col) gin_trgm_ops)` on a table that holds real
accents.

## Pagination

Keyset pagination on `filing_trans_id` (verified unique and non-null across the
6,182,665 matching rows) in 50,000-row pages, rather than `$offset`, so the run is
resumable via `download_state.json` and immune to deep-offset drift.
