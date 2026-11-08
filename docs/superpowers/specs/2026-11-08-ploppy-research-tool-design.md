# Ploppy — NYC/NYS donation research tool: design

**Date:** 2026-11-08
**Status:** awaiting review
**Supersedes:** `PRODUCT_PLAN.md` (committed `a290b4f`) in its entirety

---

## 0. What changed

Ploppy splits. The "doing business with" donor-intelligence product moves to **Blocade** and
is out of scope here. What remains is a personal, non-commercial tool to **visualize and
research ten years of New York City and New York State political donation data**
(2016-01-01 to present).

Everything in `PRODUCT_PLAN.md` about pay-to-play screening, pricing, buyers, counsel, E&O
and go-to-market is void. The data inventory and the defect list in that document remain
accurate except where corrected in §9 below.

One decision carries forward unchanged: **`data/Double Prime Kings County Reps.csv` stays.**
It is never an input, never a join, never in any deliverable. Nothing in this design touches
it.

---

## 1. Scope

### Hard requirement

Runs on **Vercel**. This is the only requirement stated by the owner.

### Agreed scope

| Question | Answer |
|---|---|
| Audience | Public aggregate views; person-level detail behind authentication |
| Budget ceiling | ~$50/month |
| Language | Whatever is best on merit |
| Research mode | Open-ended — arbitrary querying is the priority feature |

### Non-goals

Do not build these. Each duplicates something free and better-resourced:

- **Any ZIP / neighborhood / Council-district / Assembly-district choropleth of NYC
  donations.** The CFB × CUNY donor map already covers 2013, 2017, 2021 *and* 2025 across
  all four of those geographies. Verified directly.
- **NYC in-city donor share.** CFB publishes it in its own post-election report
  (2025: 244,401 individual contributions, $41.1M, 88.2% under $250, median $50).
- **Top-donor / top-recipient leaderboards with CSV export over NYSBOE.** That is
  Concourse's Campaign Finance Explorer line for line — 16,516,089 records, five time
  filters, CSV export, last updated 2026-03-10.
- **Plain contributor-name search over NYSBOE.** publicreporting.elections.ny.gov and
  Transparency USA.
- **Donor ideology scoring from scratch.** Import DIME v4.0 as a static reference layer
  with an explicit 2024 ceiling instead.

### Where the edge actually is

**Upkeep and resolution quality, not exclusivity.** Every free tool is frozen at 2024 —
followthemoney.org's own homepage says its state data is "current through the 2024 election
year" and that the site is unmaintained pending OpenSecrets integration; DIME v4.0 stops at
2024. The NYSBOE Socrata feed is current to today.

Do **not** claim cross-jurisdiction coverage is legally impossible elsewhere. Election Law
§ 14-105 merely eliminated duplicate filing, and FollowTheMoney already lists a separate
"New York — New York City" jurisdiction. The honest claim: *no official system queries both
halves, and no maintained tool resolves donors across them.*

---

## 2. Architecture

```
                        ┌─────────────────────────────────────────┐
   LAPTOP / CI          │  Socrata e9ss-239a · 7x2g-h32p          │
   (never Vercel)       │  CFB bulk exports · payments files      │
                        └────────────────┬────────────────────────┘
                                         │  acquire → conform → stage → gate
                                         ▼
                        ┌─────────────────────────────────────────┐
                        │  LOCAL POSTGRES (PG16+)                 │
                        │  staging + conformed fact tables        │
                        │  identity resolution + quarantine       │
                        └───────┬─────────────────────┬───────────┘
                     push only  │                     │  build artifacts
                  dims+rollups  ▼                     ▼
          ┌──────────────────────────┐   ┌────────────────────────────────┐
          │  NEON POSTGRES           │   │  VERCEL BLOB                   │
          │  name dimension + tiers  │   │  pub/   aggregate Parquet      │
          │  clusters + provenance   │   │  auth/  person-level Parquet   │
          │  rollups · pg_trgm GIN   │   │  (two stores, not two paths)   │
          │  daitch_mokotoff         │   └────────────────────────────────┘
          └──────────────┬───────────┘                  │
                         │                              │
                         └──────────┬───────────────────┘
                                    ▼
                   ┌────────────────────────────────────┐
                   │  ONE VERCEL PYTHON FUNCTION        │
                   │  FastAPI · psycopg · DuckDB        │
                   │  public pages ─ Blob only          │
                   │  private console ─ both engines    │
                   └────────────────────────────────────┘
```

**Why hybrid.** Measured: a GIN trigram index over 946,403 distinct contributor names is
**35 MB** and answers a fuzzy match in **5.6 ms**; the same index over the 6.18M-row *fact*
table is 185–226 MB. Indexing distinct names rather than transactions is a ~5× reduction
because the trigram dictionary saturates. Meanwhile all 8.31M fact rows compress to
**251.93 MiB** of zstd Parquet, where a year filter costs 2.9 MB over 66 range requests and
a 344 KiB pre-aggregate answers every chart in 3 ms.

So: names and identity go where the index lives (Postgres); fact-grain analytics go where
scans are free (columnar Parquet on a CDN).

**Why Python.** Python went GA on Vercel on 2026-10-15. FastAPI is auto-detected, the whole
app compiles to one Function, and the `duckdb` wheel is 24.4 MB (the Node binding is 92 MB).
No language switch is forced on a 100%-Python repo.

**Why Streamlit is dead.** Vercel has no persistent process at any price. WebSockets went GA
2026-10-20, but a connection terminates at the function's max duration (300 s Hobby / 800 s
Pro) and reconnects land on an arbitrary instance with no shared memory. Any framework
holding session state in the server process loses it every few minutes. Dash is the one
Python dashboard framework that escapes this, because its callbacks are ordinary HTTP POSTs.

---

## 3. Arbitration: one owner per contract

Five component designs were produced independently and then cross-checked. The cross-check
found **nine blocking contradictions**, almost all at the seams. These are the rulings. Each
must be written down before anything is implemented against it.

### 3.1 One identity schema, one fact join key

Four incompatible designs existed. The ruling:

- **Grain:** observed-tuple, `(jurisdiction, name_norm, city, state, zip5, is_organization)`.
  Name-only grain cannot support the disambiguation facets the UI needs.
- **Normalization, blocking, tier materialization:** as designed in the identity component —
  those are the measured parts.
- **Fact join key:** the Parquet carries `identity_key_id` and `cluster_id` as `BIGINT`.
  Not a name string.
- **One tier vocabulary:** `name_only`, `name_zip`, `name_city_state_zip`, `unambiguous`.
  Integer tiers are mapped onto these, never published.
- The app layer **deletes its entire duplicate identity layer** and reads these tables.

**`entity_class` and `txn_kind` are two columns, not one.** All four fact-producing designs
wrote `CASE filing_sched_abbrev WHEN 'D' THEN 'in_kind'` into a column named `entity_class`.
Schedule D is a *transaction type*, not an entity class, and it is mixed: 75.3% of its 50,814
rows carry a last name and 22.4% an organization name. Ruling: `entity_class` ∈
{`individual_partnership`, `corporation`, `other`} derived from schedules A/B/C, and for D
derived from which name field is filled; `txn_kind` ∈ {`monetary`, `in_kind`} carries the
D-ness. This matters because the resolver's `a.kind = b.kind` guard is the only thing
preventing an organization being merged onto a person. Note also that 94,641 Schedule A rows
populate `flng_ent_name` — those are partnerships, so the name expression needs both the
organization and the person branch on both schedules.

### 3.2 One `name_norm`, generated from one source

The two engines disagreed, and the failure mode is **zero rows, not an error**: one design
kept the comma (`SMITH, JOHN A`), the other deleted it (`SMITH JOHN A`), and CFB's name
field is `LAST, FIRST MI` — so essentially every CFB row would have mismatched.

Ruling: punctuation runs collapse to a single space; ASCII-fold via `translate()`, **not
`unaccent`** (both `unaccent` signatures are `STABLE`, so illegal in an index expression);
U+FFFD is **deleted, not spaced** — measured, that keeps `similarity('JOSE MUOZ','JOSE
MUNOZ')` at 0.615, above the 0.6 threshold, which is what rescues the 161 damaged rows.

Ship it as **one Python module plus a golden-vector fixture** that generates both the
Postgres `IMMUTABLE` function and the DuckDB macro, with a CI test asserting byte-identical
output on every vector: accented names, the U+FFFD rows, `O'BRIEN`, `SMITH-JONES`,
`LAST, FIRST MI`, `GOLDMAN SACHS & CO.`.

### 3.3 One id-stability rule

Surrogate ids were being reassigned by every rebuild while the API exposed them in URLs and
the frontend cached them. Ruling: **upsert on the natural key**, never `TRUNCATE` + `COPY`;
mint `cluster_id` from its own sequence, not from `min(name_id)`; merges flow to the lower
id; record them in `cluster_merge`; retired ids stay resolvable. The stability gate needs a
`person_cluster_prev` snapshot that no step currently captures — add it, and add a test
asserting the gate fails when it should.

### 3.4 One role vocabulary for "what counts as a dollar"

This is a user-visible setting, and the measured spread across presets is **$24,468,945.56
on identical data** — which is the whole point of exposing it. Three failures were found:

- A stored predicate `adjtypecd IN (1,2,4)` against a `text` column is a type error in
  Postgres and succeeds via implicit cast in DuckDB. Rewrite every predicate in the dialect
  intersection with explicit casts, or type the column `smallint`.
- The DuckDB pre-aggregate hard-coded `0` for three roles on the NYS side, so two of four
  presets silently returned the same number as a third.
- The Parquet rollups carried four differently-named measures and could not serve the
  presets at all.

Ruling: the rollup component owns the role vocabulary and publishes it as a fixed column
list; Parquet emits exactly those names. **`NULL` means "this role does not exist in this
jurisdiction"; `0` means "measured zero"** — a basis touching an absent role returns `NULL`
plus a named note. A cross-engine equality test (Postgres total = DuckDB total, to the cent,
per jurisdiction × basis) **gates the publish**.

Schedule N is a **stock**, not a flow: it lives in a separate file with the column named
`balance_amt`, never `amount`. Keeping stocks and flows in one file under one column name
defeats the guard downstream of Postgres.

### 3.5 One `build_id`

Five version schemes existed and three components hard-coded `DATE '2026-11-08'` — a footgun
that fires on the second build. Ruling: one token, `date + sha256(watermark, source
digests)`, used as the Blob path prefix, a column on every rollup row, the asset query
string, and a field every API response echoes. Nothing hard-codes a date; the plausibility
upper bound is a parameter bound to the run's as-of, with a grace window.

---

## 4. Settled by spike

Run locally against DuckDB 2.0.0 on 2026-11-08. Two independent designs had made **opposite
first-hand claims**; both were partly wrong.

| Question | Answer |
|---|---|
| `LOAD httpfs` by bare name with autoload disabled | Works **only where the extension is already cached**. Vercel's filesystem is read-only, so it must be `LOAD '<abs path>'` from a vendored, sha256-pinned file. |
| `http_timeout` / `http_keep_alive` / `http_retries` | **Absent in 2.0.0.** DuckDB raises on an unknown `SET`, so a module setting them throws on first use. |
| `disabled_filesystems='LocalFileSystem'` as console hardening | **Unusable.** It blocks httpfs reads *even when httpfs is already loaded from an absolute path* — `PermissionException: File system LocalFileSystem has been disabled`. It does correctly block local reads, but you cannot have both. |
| `lock_configuration=true` | Works; correctly refuses later changes to `disabled_filesystems`. |

**Consequence:** the console's filesystem sandbox as designed does not exist. The replacement
is a **parser-level gate**, which was verified to be sound and needs no filesystem hardening:

1. `json_serialize_sql(user_sql)` → reject if `error == true`. That one check eliminates DDL,
   `COPY TO`, `ATTACH`, `INSTALL`/`LOAD` and multi-statement in a single move; all of them
   return `{"error": true, "error_message": "Only SELECT statements can be serialized to
   json!"}`.
2. Walk the resulting AST and reject any `function_name` in a table-function denylist
   (`read_csv`, `read_parquet`, `read_json`, `glob`, `parquet_scan`, `read_text`,
   `read_blob`, …). Verified: these remain visible through subqueries **and** CTEs.
3. Reject any `table_name` outside an allowlist of pre-created views.

Pin all three behaviours in a test file that runs on every DuckDB version bump.

### Still open — need infrastructure that does not exist yet

- **Can DuckDB range-read a private Vercel Blob?** Vercel's private-storage docs document
  exactly one read path (`get_blob()` returning a whole body/stream, served with
  `Cache-Control: private, no-cache`) and document **no range-addressable URL and no HTTP
  206**. An `Authorization`-bearing request is also never CDN-cached, so every range would be
  an origin hit. This is a **privacy decision disguised as a performance question**: if
  ranges do not work, the options are a function-authored range proxy, a weaker posture with
  unguessable public paths, or a smaller authenticated surface. Nobody may assume it works.
- **Do psycopg protocol-level prepared statements survive Neon's pooler?** Two designs set
  `prepare_threshold=5` and `prepare_threshold=None` on the same endpoint. The failure is an
  intermittent `prepared statement does not exist` under concurrency. One answer, pinned in
  one shared pool module, with one `statement_timeout` for the whole deployment — PgBouncer
  may key server pools on the options string and fragment the pool.

---

## 5. The Postgres budget, honestly

The hybrid does **not** fit 450 MB at the grain the design requires.

| Layer | Size |
|---|---|
| Identity at observed-tuple grain (~1.57M rows) | ~502 MB |
| Rollups (`recipient_phase` ~600k + `recipient_cycle_band` ~250k) | ~185 MB |
| Dimensions and control tables | ~50 MB |
| **One generation** | **~737 MB** |
| With one retired generation retained by the schema swap | **~1.44 GB** |

Three components each built a GIN trigram index over the same contributor names: **~162 MB
specified where ~54 MB is needed**, anchored to the measured 35 MB / 946,403 names.

Measured directly: the unified name dimension across both jurisdictions is **1,996,692
distinct normalized names** (681,866 CFB-only, 1,059,673 NYSBOE-only, **255,153 on both
sides**) at **224 MB** total with heap, PK and trigram index, answering a fuzzy query in
**4.75 ms**.

**Ruling: stop contorting the design to fit a free tier.** Neon Launch has no base fee and
storage is $0.35/GB-month, so a ~740 MB layer is about **$0.26/month of storage** — the bill
is entirely compute. With an autoscaling minimum of 2 CU and 5-minute autosuspend it lands
near **$15/month**, comfortably inside the approved $50.

Keeping Postgres small was never really about money; it was about Neon's Local File Cache not
surviving autosuspend, which makes the first queries of every session slow. A ~740 MB layer
still fits the 6 GB cache at 2 CU, so the actual goal is met without the cuts that cost
capability.

Do still make these cuts, because they remove duplication rather than capability:

- The app layer deletes its duplicate identity tables and reads the real ones (~275 MB).
- `recipient_phase` moves to Parquet — it serves the private console only (~110 MB).
- The two-generation schema swap becomes a `generation` column plus a partial index.

---

## 6. Privacy posture

**The leak to fix before anything is ever uploaded.** The publish script uploaded every file
with `access: "public"` and `addRandomSuffix: false`, including `search/name_sorted.parquet`
(~8M person-level gift rows), `donor_spine`, `bundler_nyc` and `employer_sector_nyc`. A
`private/` path prefix **is not an access control**. Publishing once is irreversible.

Ruling:

- **Two Blob stores**, not two path prefixes. Rename the prefixes `pub/` and `auth/` so a
  path never implies an access mode it does not have.
- The publish script reads each file's tier from `layout.json` and passes
  `access="private"` for anything not under `pub/`.
- Extend the existing banned-column preflight to a **banned-tier check** that refuses to
  `put` a private-tier file into the public store.
- Drop NYSBOE's `flng_ent_add1` (contributor street address) from everything published; keep
  city, state and ZIP. CFB's street fields are already always blank.
- Every public route reads **only** Blob artifacts and opens zero Postgres connections.
  Committee and organization search moves behind authentication or ships as a small
  pre-built public search artifact (the committee dimension is 64,801 rows; the CFB recipient
  dimension 2,023). That also removes the only unauthenticated route that can wake an
  autosuspended compute.
- A `robots.txt` goes in the public store. Vercel provides none, and blob URLs are indexable
  once linked.

---

## 7. The five builds

| # | Build | Status |
|---|---|---|
| 1 | **2021 NYC Program A vs Program B matching-ratio experiment** | Unblocked by the code-mappings fix |
| 2 | **Matching-funds leverage** — public dollars per private dollar | Needs the three small payments files |
| 3 | **Cross-jurisdiction donor identity**, shipped as a confidence range | Needs §3.1 and calibration |
| 4 | **NYS in- vs out-of-district money** | **Blocked** — needs a ZIP→district crosswalk that does not exist |
| 5 | **NYC employer / industry sectors** | NYC-only, permanently |

Build 1 is the only genuine natural experiment in the data: same city, same year, two match
ratios and two contribution limits. It is invisible today because `code_mappings.py` labels
office codes 11/44/55 "Special Designation / District / Office" when those are the Program A
offices. Six lines of a dict.

Build 2 must not use `MATCHAMNT` — that is CFB's determination of the *matchable* amount, not
money paid. Leverage needs the separate payments files, where the join is exact
(`Payments.CANDID = cfb_contributions.recipid` on `ELECTION`).

Build 5 is permanently NYC-only: NYSBOE's contributor employer and occupation fields are
filled on **0 of 6,182,834 rows** — verified directly. `treas_occupation`/`treas_employer`
describe the treasurer.

---

## 8. Build order

0. **Three spikes** — private-Blob ranges, psycopg prepares through the pooler, and
   (done) the DuckDB console gate. Three designs branch on these answers.
1. **Code mappings as data** — parse CFB's own `Key-Contribution.csv` into `code_set` /
   `code_value` and delete the hand-typed dicts. Depends on nothing; blocks build 1.
2. **One normalization module** with golden vectors generating both engines' implementations,
   plus the CI byte-equality test.
3. **The merged identity schema**, built and sized on the local Postgres first, on **PG16+**
   so `daitch_mokotoff` exists (the laptop is currently 14.13 with fuzzystrmatch 1.1, so the
   local upgrade is a prerequisite, not a cleanup).
4. **Pipeline acquire / conform / stage / quarantine** with the gates wired.
5. **Rollup semantics frozen as a contract** — it dictates which schedules reach which file
   under which column name, and retrofitting that means rewriting every artifact.
6. **Parquet build and publish**, one path scheme, one version token, both tiers, privacy
   preflight extended to the tier check. Publishing before that check exists is the one
   irreversible mistake available.
7. **Cross-engine basis equality test** and the reported-not-asserted gates against CFB's own
   published files — the first point where a number can be checked against an independent
   source.
8. **Public surface** — reads only Blob artifacts, every figure carrying the `build_id`, with
   a response-size guard as shared middleware.
9. **Private console** — single module-level DuckDB connection, the parser gate pinned in
   tests, httpfs scoped to the two Blob hosts, keyset cursors and streaming everywhere. Last
   and alone, because it is the only surface that can leak person-level data.
10. The five builds, with #4 behind the ZIP crosswalk.

---

## 9. Numbers not to trust, including three of mine

- **`nysboe_contributions` is 3,244 MB**, not the 2,576 MB in `data/nysboe/README.md`
  (1,954 MB heap + 1,290 MB indexes). I repeated the stale figure before measuring it.
- **`r_in_district` is non-NULL on only 9.18% of in-window rows, covering 2.11% of dollars.**
  I described it as a usable native flag. `in_district = (r_in_district = 'Y')` appears in
  three designs and turns NULL — 97.9% of dollars — into "out of district", which would
  publish as a finding. It must be three-valued everywhere: `in_district`, `out_district`,
  `unknown_geo`. The flag is a validation sample, not a data source.
- **The 2021 Program B figures are contested.** Average gift computed three ways: $576.52
  (the figure I quoted), $620.33, $606.25. Small-dollar share: 6.3%, 5.84%, 7.4%. Program A
  agrees closely ($117.01–$123.91). The predicates differ on schedule set, `c_code` set,
  office codes, band boundary and refund treatment. One owner computes it once, publishes the
  predicate beside the number, and reconciles against CFB's own Financial Analysis file as a
  gate.
- **NYSBOE in-window distinct contributor names: ~1.39M**, not the 230,879 in the branch
  README. My own measurement gives ~1.31M; the difference is normalization.
- **The function bundle ceiling is contested** — 250 MB uncompressed per Vercel's limitations
  page versus 500 MB for Python. A measured app bundle of 112.4 MB fits either way, but the
  headroom is possibly half what was assumed. Settle it before proposing pyarrow (55 MB),
  pandas or a plotting library.
- **The NYSBOE small-dollar swing could not be reproduced.** 17.4%→34.8% was claimed;
  7.07%→24.94% by filing period was measured. Band cut, schedule set, itemization treatment
  and denominator all differ.
- **Every NYSBOE total needs an as-of date.** The live dataset drifted $503,115.89 during a
  single research pass.
- **`filing_trans_id` stability across Socrata publishes is untested.** The entire incremental
  refresh rests on it. Until it is verified, the only provably correct refresh is a full
  reload.

---

## 10. Known gaps with no owner

- A **ZIP5 → Assembly/Senate district crosswalk**, with a documented apportionment rule for
  straddling ZIPs or an explicit "ambiguous" bucket. Build 4 has no data path without it.
- A **per-(cycle, schedule) source-of-record rule for CFB.** Schedules D, X and N overlap
  between the contributions and expenditures exports; once both are loaded, D and X double-
  count with nothing catching it.
- **The CFB recipient dimension** (2,023 rows). Four designs reference it; none builds it.
  Builds 1 and 2 both need candidate names and corrected office labels.
- **One owner for NYSBOE office/district resolution** — two designs for the same 3,360-pair
  fan-out, and `office_desc` is filled on 0.35% of in-window rows, so without the registry
  join every NYS office figure is NULL.
- **Labelled ground truth for identity precision and recall** — roughly 300 hand-adjudicated
  pairs, or CFB's own Doing Business cross-reference (`fbkk-n4e3`, ~22,294 rows) as free
  labels. Without it, the published confidence range is asserted, not calibrated.
- **A Blob operation counter.** Three components each worried about Hobby's 10,000 simple
  operations per month and each assumed it owned the whole allowance. None implements a
  counter or a degradation path.
- **Scoping DuckDB's httpfs to the two known Blob hosts.** The parser gate controls statement
  type, not what a `SELECT` reads, so a leaked session cookie yields arbitrary outbound HTTP
  from the function. DuckDB secrets take a `SCOPE`, so this is doable.
- **OIDC token refresh** for a query that outlives the token after a 200 header has gone out.
- **An independent-expenditure lower-bound label.** `committee_type_desc` is NULL on 56.6% of
  the registry, so the 382 IE committees are a floor, not a count.
- **Supply-chain pinning for the vendored DuckDB extension**, and SRI hashes for the two CDN
  scripts.
- **Cold-start measurement for the whole function** on Vercel — the dominant first-request
  cost on both surfaces, and unmeasured.

---

## 11. Repo hygiene before first deploy

`pyproject.toml` is 90,942 bytes, still named `repl-nix-workspace`, declares
`requires-python = ">=3.10"`, disagrees with `requirements.txt`, and carries a
`[tool.uv.sources]` block pinning hundreds of never-imported packages to a pytorch-cpu index.
Python functions bundle every reachable file with **no tree-shaking**. Write a minimal
`pyproject.toml` for the app service, set `.python-version`, and add `excludeFiles` globs for
tests, `scripts/`, `data/` and `attached_assets/`.
