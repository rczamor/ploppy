# Ploppy → product: plan

> **Superseded.** This plan describes the pay-to-play screening product, which moved to
> Blocade. Ploppy is now a research and visualization tool over NYC/NYS donation data.
> The current design is `docs/superpowers/specs/2026-11-08-ploppy-research-tool-design.md`,
> which supersedes this document in its entirety. Kept for the verified figures and the
> market analysis in it; do not build from it.

Produced from a 12-agent analysis (grounding → four competing strategies → three judging
lenses → synthesis → adversarial critique). Every number below is either verified against
the repo and live data sources, or explicitly marked as an assumption.

---

## 0. The voter file stays

**Decision recorded: `data/Double Prime Kings County Reps.csv` is never to be purged.**
I raised it twice, you've ruled, and that is the end of it. It stays in history and in
`origin/main`; no history rewrite, no force-push, and I won't raise it again.

Stated once so the plan describes the repo accurately: the file holds 7,287 named
Brooklyn residents with street addresses, 6,253 mobile numbers, 6,728 landlines,
`StateVoterId`, `RNCRegId`, do-not-call flags, gender and four party-affiliation fields.
It entered in `fa5d102`, an ancestor of all three remote branches, and the repo is public.

**The product consequence is narrow and unchanged either way: no voter-file column ever
enters a deliverable.** The screening product joins CFB contributions to the city's own
Doing Business Database and nothing else. Phone numbers, home addresses and party codes
are not inputs to it, so this file is not a product asset and its presence changes no
stage below. That refusal is what Stage 0 writes down.

Separate and still open: branch `claude/ny-elections-contributions-2016-3fb9d8` loads
6,182,834 NYSBOE rows into a schema carrying `flng_ent_add1/city/state/zip` and
`treas_add1/...`. That is a merge-or-leave call about a branch, not about this file (§7).

---

## 1. The legal picture (this reverses my earlier caution)

I flagged CFB terms as a likely constraint. Researched, with sources, that was wrong:

- **NYC Charter §1052** contains no reuse restriction and affirmatively requires a public
  database.
- **NY Election Law §14-108(4)** says filings "shall be open to public inspection", with
  no use limitation. No state analogue to the federal restriction exists.
- The **CFB Data Library** publishes complete bulk CSVs (2001–2025) with no terms of use
  and no licence; NYC OpenData declares none either.

NYC-only data is clear to build on commercially.

**The real trap is federal, and it is avoidable.** 52 U.S.C. §30111(a)(4) / 11 C.F.R.
§104.15 bar using data copied from **FEC** reports for solicitation or commercial
purposes. Second Circuit precedent (*FEC v. Political Contributions Data*, 943 F.2d 190)
is binding in NY and permissive — it let a for-profit sell compiled FEC contributor
reports — but the modern FEC is restrictive and deadlocked on exactly this fact pattern
in AO 2021-01. Note what the winning product in PCD did: **omitted contributor mailing
addresses and phone numbers**, and warned against solicitation use on every page.

So the rule is simple and cheap to hold: **never ingest FEC data**, and the restriction
never attaches.

One privacy wrinkle: CFB states publicly that it does not release contributor addresses,
yet the 2001–2005 files still carry street number/name/apartment on ~23,457 rows.
Dropping those at ingest costs nothing and avoids republishing what the agency says it
withholds.

---

## 2. What is actually there today

**The data is far richer than the app.** The public CFB set is 1,668,351 transaction-grain
rows across nine cycles (plus 108,590 off-year/special). `MATCHAMNT` is populated on 100%
of rows and non-zero on 61.9% — it is CFB's **own** determination of the matchable
portion, so the 8:1 match logic never has to be reimplemented. It reconciles end to end:
Mamdani 2025 shows $4,667,452 raised, $2,055,361 matchable base, $13,145,508 paid.

**The app answers none of it.** Verified:

- The headline natural-language search is a stub — `search_contributions()` takes `query`
  and never reads it. Every search returns the latest 100 rows by date.
- Party and Borough filters can never match: no import path writes `recipients.party` or
  `recipients.borough`.
- 11 of 12 AI buttons die inside `initialize()`; the committed launcher exports a
  SQLAlchemy DSN that psycopg2 rejects. (That one is mine — `.claude/run_local.sh:5`.)
- The pgvector search builds 6 SQL placeholders and passes 5, in the wrong order.
- The embedding model is fit on **20 hard-coded sentences**. Measured cosine similarity
  between four entirely different contributors: 1.000000. The "384-dim" vector is 292
  real dims plus 92 zeros.
- "Build Knowledge Graph" targets a `knowledge_graph` table no DDL creates.
- "Analyze Networks" returns `{}` and renders nothing at all — no error, no message.
- "Predict Value" always returns 'Small Donor' plus a random number.
- The feasible import path loads **9 of 54 source fields**, writes no foreign keys, and
  stores the contributor's name in `contributions.str_name` (a street-name column) and
  the recipient's name in `contributions.occupation`.
- `scripts/fast_contributor_import.py` aborts on its own first transaction: it does
  `DELETE FROM org_contributors` at step 2, and that table is first created at step 5 by
  a different script.
- `src/database/code_mappings.py` mislabels the 2021 cycle — the largest — so its Mayor
  and Council contributions read as "Special Designation".

Genuinely working: the monthly-trend regression, and an sklearn anomaly ensemble (though
it runs 1-D on a sample pre-filtered to the 10,000 largest contributions, so it can only
ever return "the biggest donations").

---

## 3. Recommendation

**Sell a batch pay-to-play screening report to organizations already named in NYC's
Doing Business Database. Give away a reconciled public record as the credibility proof.**

NYC's Local Law 34 lowers contribution limits for people tied to city business and makes
their contributions unmatchable. Coverage reaches principal officers, 10%+ owners, senior
managers and registered lobbyists. The city publishes the covered population itself:
**10,787 entities, 60,545 people, 3,094 lobbyist-coded**, refreshed monthly. CFB also
publishes its own cross-reference of DB-covered contributions (`fbkk-n4e3`, 22,294 rows),
which is free labelled ground truth for an entity-resolution evaluation.

Scoring across the three judging lenses (market / feasibility / legal-ethical):

| Strategy | Market | Feasibility | Legal | Total | Fatal flaws |
|---|---|---|---|---|---|
| **Pay-to-play screen** | 7 | 7 | 4 | **18** | none non-survivable |
| Journalist research tool | 3 | 6 | 8 | 17 | diff feature unvalidatable until ~2028 |
| Campaign-side pre-filing check | 6 | 5 | 5 | 16 | depends on C-SMART export nobody has verified |
| Free civic explorer | 2 | 8 | 3 | 13 | monetisation is grants; no funder identified |

It wins not on score but on being the only one with **zero non-survivable flaws** — and
on one structural fact: its buyer has a **continuous** statutory filing duty, not an
election-indexed one.

**That matters because of timing, which is the hardest finding here.** NYC municipal
elections are odd-year. November 2025 just passed. The next primary is **June 2029**.
The 2026 midterms are over. Any product whose demand is election-indexed has no buyer
until 2029. This one does not.

Its weakest lens is defensibility (4/10) for two reasons, both cheap to fix: the product
cannot by itself distinguish a lawful covered-persons screen from an employer surveilling
staff political activity (fix: attestation, scope bound to the organisation's own filed
DB Data Form, cadence caps, audit logging, published correction path), and open-releasing
a resolved identity layer while forbidding redistribution is incoherent (fix: publish
aggregates, methodology and measured error rates; withhold the resolved identity table).

---

## 4. Architecture

**Hybrid, with Streamlit demoted to an internal reconciliation console and never put in
front of a non-developer.**

- Pipeline: **DuckDB + Parquet**, build-time, single file, no server. 1.7M rows is small.
- Product surface: a **CLI emitting PDF + CSV**. The buyer wants a document for a
  compliance file, not a dashboard to explore — and an exploratory dashboard is exactly
  what CFB already ships free, with a CUNY donor map launched January 2025.
- Public surface: flat HTML from Python + Jinja on GitHub Pages. No new toolchain; there
  is no `package.json` and no JavaScript in this repo.
- Postgres and a web app are **not built** until a repeat-demand trigger fires.

The f-string SQL and `db_manager_v2.execute_query` are not fixed — they are deleted along
with the code paths that use them.

---

## 5. Stages

I have reordered these against the raw synthesis, because the critic found a structural
flaw: the demand test originally sat 14 weeks out, behind engineering it does not need,
with no schedule kill criterion — in a repo where `replit.md` records five prior import
attempts reaching 64,720 of ~2M rows.

| # | Stage | Time | Exit criterion |
|---|---|---|---|
| **0** | Refusals policy in writing | 2 d | `POLICY.md` on main: no FEC ingest, no voter-file column in any deliverable, no pre-2006 contributor street addresses |
| **0.5** | **Hand-built demand test** | 1 wk | 3 firms screened **by hand** off the free CFB portal, report written in a doc, money asked for |
| 1 | Reconciled ingest, CI as the gate | 5 wk | CI asserts internal consistency exactly, and reports delta vs CFB's published aggregates |
| 2 | Entity resolution + DBD join | 6 wk | recall ≥0.90 at precision ≥0.95 against `fbkk-n4e3` — **after** a one-day probe of its grain |
| 3 | Paid pilot, no UI | 3 wk | 3 of 10 approached organisations invoiced; CFB written answer + counsel + E&O on file first |
| 4 | Public reconciliation pages | 3 wk | site builds from CI; build fails rather than publishing drifted figures |
| 5 | Self-serve + monitoring | 6 wk | **blocked** until two distinct organisations have each paid for a *second* run |
| 6 | Freshness (conditional) | 4 wk | either a permitted machine-readable path, or a published "blocked" note and no freshness claims |

**Stage 0.5 is the most important change.** You can hand-build one firm's screen from the
free CFB portal in a day. Doing that first surfaces the most likely and most informative
negative answer — *"our outside counsel already does this"* — before eleven weeks of
engineering, not after.

Other corrections folded in from the critique:

- **Split the Stage 1 gate.** Internal consistency (loader totals = raw staging totals,
  exact) catches loader bugs and needs no external truth. External agreement against CFB's
  published aggregates is *reported*, not asserted at 0.02% tolerance — otherwise a
  Data-Library-vs-Socrata discrepancy is indistinguishable from a bug in your loader.
- **Probe `fbkk-n4e3` before building the matcher.** If it enumerates only CFB-identified
  positives, precision is not computable from it and the Stage 2 gate is meaningless as
  written. One day, before six weeks.
- **Name the store once.** DuckDB + Parquet is the system of record through Stage 4.
  Stage 2's Postgres DDL notes are migration notes for Stage 5, not work items.
- **E&O and counsel gate the first *invoice*,** not the first self-serve customer.
  Stage 3's manual reports are the highest-liability moment in the plan.
- **Redact the cold-outreach artifact.** Mailing a named private individual's
  contribution history to their employer, unsolicited, is the exact failure mode this
  plan identifies as most likely to become the story. Pitch with role labels
  ("a C-suite officer"), name-level only after the firm asks and attests.
- **Fix the deletion list.** `db_manager_v2.py`, `code_mappings.py`,
  `normalize_contributors.py` and the three `fast_*_import.py` scripts are declared dead
  in prose but survive every stage. Delete them explicitly, or the per-row importer and
  the injectable query helper stay on main through Stage 6.
- **One critique finding was wrong, and I had relayed it.** The critic claimed
  `ploppy.py` imports the deleted `src.ai.ai_phase3` and `src.utils.utils`. Both modules
  exist and all four of its local imports resolve — verified by importing them. `ploppy.py`
  is not broken. The live decision is still whether to keep it: rewrite it to ~200 lines as
  the reconciliation console (its one genuinely working pattern is `@st.cache_data` over SQL
  into a DataFrame into Plotly), or drop Streamlit from the architecture entirely.

---

## 6. Numbers to treat as assumptions, not findings

The critic caught these being asserted with more confidence than the research supports:

- "Ten to thirty consultant shops and a few dozen exposed firms" — appears in no
  grounding report. It is the sole basis for the $30–60K/yr ceiling.
- "$3,000–12,000/yr per organisation" — extrapolated from **nonprofit fundraising**
  prospect-research tools (iWave $4,150–4,500, Kindsight $5,800), a different buyer with
  a different budget. Every actual pay-to-play vendor is quote-only.
- "~2,000 candidate-election pages" — no grounding report gives a candidate-election count.
- "2,043,325 contributions" — this is a hardcoded string in a `print()` statement in
  `scripts/fast_contributor_import.py`, not a sourced figure. The published data is
  1,668,351. Explain the gap or record it as unresolved.
- That the DBD list is a **prospect** list — the counts are correct; that these
  organisations will buy is the hypothesis Stage 0.5 exists to test.

---

## 7. Decisions only you can make

1. Publish the resolved donor identity table, or withhold it? (Recommendation: withhold.
   Publishing hands anyone the exact asset needed to build the prospecting product this
   plan refuses, under terms enforceable only against paying customers.)
2. Budget ceiling for NY election-law counsel and E&O before first revenue — and will you
   hold the no-invoice-until-written-CFB-answer gate if a buyer wants to pay in month three?
3. Is a $30–60K/yr solo business an acceptable outcome? If not, decide now: Stages 5–6 are
   only worth building if it is. Stages 0–4 are worth doing regardless.
4. Merge, quarantine or delete the NYSBOE branch.
5. The name. "Ploppy" cannot front a compliance product sold to a general counsel. Decide
   before Stage 4 publishes anything.
6. **Will you personally do the Stage 0.5 and Stage 3 outreach?** Stages 1–2 are twelve
   weeks of genuinely interesting engineering that produce no revenue signal. If nobody
   makes the calls, the plan fails silently.
