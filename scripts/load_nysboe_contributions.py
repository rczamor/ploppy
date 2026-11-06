#!/usr/bin/env python3
"""Load data/nysboe/*.csv into Postgres table nysboe_contributions.

Creates the table from scripts/nysboe_contributions_schema.sql, streams the CSV in
with COPY, adds analysis indexes, then verifies the loaded row count and amount
total against the CSV itself.

Connection: uses DATABASE_URL if set, otherwise libpq defaults with database
"ploppy" (override with --dbname). Credentials are never read or printed by this
script -- psql resolves them itself.

Usage:
    python3 scripts/load_nysboe_contributions.py
    python3 scripts/load_nysboe_contributions.py --dbname ploppy --include-null-dates
"""

import argparse
import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data", "nysboe")
MAIN_CSV = os.path.join(DATA_DIR, "contributions_2016_present.csv")
NULLDATE_CSV = os.path.join(DATA_DIR, "contributions_null_sched_date.csv")
SCHEMA_SQL = os.path.join(HERE, "nysboe_contributions_schema.sql")
TRGM_SQL = os.path.join(HERE, "nysboe_contributions_trgm.sql")
PHONETIC_SQL = os.path.join(HERE, "nysboe_contributions_phonetic.sql")
UNACCENT_SQL = os.path.join(HERE, "nysboe_contributions_unaccent.sql")
TABLE = "nysboe_contributions"

# Columns that must become NULL rather than empty string / zero.
TYPED_NULLABLE = ("org_date", "org_amt", "owed_amt", "election_year", "election_year_r")

INDEXES = [
    ("nysboe_contrib_filer_idx", "(filer_id)"),
    ("nysboe_contrib_sched_date_idx", "(sched_date)"),
    ("nysboe_contrib_sched_abbrev_idx", "(filing_sched_abbrev)"),
    ("nysboe_contrib_election_year_idx", "(election_year)"),
    ("nysboe_contrib_ent_name_idx", "(lower(flng_ent_name))"),
    ("nysboe_contrib_ent_last_idx", "(lower(flng_ent_last_name))"),
    ("nysboe_contrib_zip_idx", "(flng_ent_zip)"),
    ("nysboe_contrib_comm_name_idx", "(lower(cand_comm_name))"),
    ("nysboe_contrib_amt_idx", "(org_amt)"),
]


USE_DATABASE_URL = False


def psql(args=(), sql=None, dbname=None, capture=True):
    cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-qAt"]
    # Target is explicit by default so a stale DATABASE_URL in the environment
    # cannot silently redirect a 2.3 GB load somewhere unintended.
    if USE_DATABASE_URL and os.environ.get("DATABASE_URL"):
        cmd += ["-d", os.environ["DATABASE_URL"]]
    else:
        cmd += ["-d", dbname]
    if sql is not None:
        cmd += ["-c", sql]
    cmd += list(args)
    res = subprocess.run(cmd, capture_output=capture, text=True)
    if res.returncode != 0:
        sys.stderr.write((res.stderr or "") + "\n")
        raise SystemExit(f"psql failed ({res.returncode})")
    return (res.stdout or "").strip()


def csv_header(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return next(csv.reader(fh))


def csv_stats(path):
    """Row count and org_amt sum, computed straight from the file."""
    csv.field_size_limit(10**9)
    n = 0
    total = 0.0
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n += 1
            if row["org_amt"]:
                total += float(row["org_amt"])
    return n, total


def copy_csv(path, cols, dbname):
    """Stream one CSV into the table via psql \\copy."""
    collist = ", ".join(cols)
    force_null = ", ".join(c for c in TYPED_NULLABLE if c in cols)
    stmt = (
        f"\\copy {TABLE} ({collist}) FROM '{path}' "
        f"WITH (FORMAT csv, HEADER true, FORCE_NULL ({force_null}))"
    )
    print(f"  COPY {os.path.basename(path)} ...", flush=True)
    psql(["-c", stmt], dbname=dbname, capture=True)


def main():
    global USE_DATABASE_URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbname", default="ploppy")
    ap.add_argument(
        "--use-database-url",
        action="store_true",
        help="connect via $DATABASE_URL instead of --dbname",
    )
    ap.add_argument(
        "--with-trgm",
        action="store_true",
        help="also build the GIN trigram indexes from nysboe_contributions_trgm.sql",
    )
    ap.add_argument(
        "--with-phonetic",
        action="store_true",
        help="also build the dmetaphone/soundex indexes from "
             "nysboe_contributions_phonetic.sql",
    )
    ap.add_argument(
        "--with-unaccent",
        action="store_true",
        help="also install unaccent and the immutable_unaccent() wrapper from "
             "nysboe_contributions_unaccent.sql (adds no index -- this table has "
             "no real accents left to fold; see that file)",
    )
    ap.add_argument(
        "--include-null-dates",
        action="store_true",
        help="also load the 169 records whose sched_date is blank (they fail the "
             "NOT NULL constraint, so this relaxes it first)",
    )
    args = ap.parse_args()
    USE_DATABASE_URL = args.use_database_url

    if not os.path.exists(MAIN_CSV):
        raise SystemExit(f"missing {MAIN_CSV} -- run scripts/download_nysboe_contributions.py first")

    print("creating table ...", flush=True)
    psql(["-f", SCHEMA_SQL], dbname=args.dbname)

    cols = csv_header(MAIN_CSV)
    print(f"csv has {len(cols)} columns", flush=True)

    print("loading ...", flush=True)
    copy_csv(MAIN_CSV, cols, args.dbname)

    if args.include_null_dates and os.path.exists(NULLDATE_CSV):
        psql(sql=f"ALTER TABLE {TABLE} ALTER COLUMN sched_date DROP NOT NULL;", dbname=args.dbname)
        copy_csv(NULLDATE_CSV, csv_header(NULLDATE_CSV), args.dbname)

    print("indexing ...", flush=True)
    for name, expr in INDEXES:
        print(f"  {name}", flush=True)
        psql(sql=f"CREATE INDEX {name} ON {TABLE} {expr};", dbname=args.dbname)

    if args.with_trgm:
        print("building trigram indexes (needs pg_trgm; several minutes) ...", flush=True)
        psql(["-f", TRGM_SQL], dbname=args.dbname)

    if args.with_phonetic:
        print("building phonetic indexes (needs fuzzystrmatch) ...", flush=True)
        psql(["-f", PHONETIC_SQL], dbname=args.dbname)

    if args.with_unaccent:
        print("installing unaccent + immutable wrapper ...", flush=True)
        psql(["-f", UNACCENT_SQL], dbname=args.dbname)

    print("analyzing ...", flush=True)
    psql(sql=f"VACUUM ANALYZE {TABLE};", dbname=args.dbname)

    # verify against the file, not against our own load counter
    print("verifying ...", flush=True)
    db_rows = int(psql(sql=f"SELECT count(*) FROM {TABLE};", dbname=args.dbname))
    db_total = psql(sql=f"SELECT coalesce(sum(org_amt),0)::text FROM {TABLE};", dbname=args.dbname)
    file_rows, file_total = csv_stats(MAIN_CSV)
    if args.include_null_dates and os.path.exists(NULLDATE_CSV):
        n2, t2 = csv_stats(NULLDATE_CSV)
        file_rows += n2
        file_total += t2

    ok_rows = db_rows == file_rows
    ok_amt = abs(float(db_total) - file_total) < 0.01
    print(f"  rows   db={db_rows:,}  csv={file_rows:,}  {'OK' if ok_rows else 'MISMATCH'}")
    print(f"  org_amt db=${float(db_total):,.2f}  csv=${file_total:,.2f}  {'OK' if ok_amt else 'MISMATCH'}")

    size = psql(sql=f"SELECT pg_size_pretty(pg_total_relation_size('{TABLE}'));", dbname=args.dbname)
    print(f"  table size (incl. indexes): {size}")

    if not (ok_rows and ok_amt):
        return 1
    print("load verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
