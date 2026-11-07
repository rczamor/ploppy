#!/usr/bin/env python3
"""Load NYC CFB exports and the NYSBOE filer registry into Postgres.

Creates the staging tables from scripts/cfb_schema.sql and
scripts/nysboe_filers_schema.sql, streams each CSV in with COPY, indexes them,
then verifies row counts and amount totals by re-reading the files -- not by
trusting the loader's own counters.

The four inputs are the CFB contributions / expenditures / intermediaries bulk
exports and NYSBOE's ListOfFilers.csv. Pass them with the flags below; nothing is
guessed from a directory listing, so a load is always explicit about its source.

ListOfFilers.csv is repaired first (see scripts/repair_listoffilers.py) because
one row's inner quotes are not RFC 4180 escaped, which makes COPY fail outright.
The repaired copy is written next to the original unless --repair-to says
otherwise; the source file is never modified.

Connection: explicit --dbname by default, so a stale DATABASE_URL in the
environment cannot silently redirect a 500 MB load. Credentials are never read
or printed by this script -- psql resolves them itself.

Usage:
    python3 scripts/load_cfb_filers.py \\
        --contributions ~/Downloads/CFB_<ts>.csv \\
        --expenditures  ~/Downloads/CFB_<ts>.csv \\
        --intermediaries ~/Downloads/CFB_<ts>.csv \\
        --filers        ~/Downloads/ListOfFilers.csv
"""

import argparse
import csv
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CFB_SCHEMA = os.path.join(HERE, "cfb_schema.sql")
FILER_SCHEMA = os.path.join(HERE, "nysboe_filers_schema.sql")
REPAIR = os.path.join(HERE, "repair_listoffilers.py")

USE_DATABASE_URL = False

# Columns that must become NULL rather than empty string / zero.
NULLABLE = {
    "cfb_contributions": ("date", "refunddate", "amnt", "matchamnt", "prevamnt",
                          "pay_method", "intermno", "adjtypecd", "filing"),
    "cfb_expenditures": ("inv_date", "date", "amnt", "filing"),
    "cfb_intermediaries": ("amnt",),
    "nysboe_filers": ("registration_date", "termination_date", "election_year",
                      "candidate_registration_date", "candidate_termination_date"),
}

# ListOfFilers.csv has spaces in its headers and one unnamed trailing field, so
# its mapping is explicit and positional. Order must match the file.
FILER_COLUMNS = [
    "filer_type", "compliance_type", "committee_type", "filer_id", "name",
    "office", "district", "county", "municipality", "address",
    "registration_date", "termination_date", "status", "candidate_name",
    "election_year", "candidate_office", "candidate_district", "purpose_type",
    "candidate_registration_date", "candidate_termination_date",
    "trailing_blank",
]
FILER_HEADER = [
    "Filer Type", "Compliance Type", "Committee Type", "Filer ID", "Name",
    "Office", "District", "County", "Municipality", "Address",
    "Registration Date", "Termination Date", "Status", "Candidate Name",
    "Election Year", "Candidate Office", "Candidate District", "Purpose Type",
    "Candidate Registration Date", "Candidate Termination Date",
]

INDEXES = {
    "cfb_contributions": [
        # the composite that WOULD be the natural key if it were unique; it is
        # not (2,549 collisions), so this is deliberately non-unique
        ("cfb_contrib_txn_idx", "(election, recipid, filing, schedule, refno)"),
        ("cfb_contrib_refno_idx", "(refno)"),
        ("cfb_contrib_recipid_idx", "(recipid)"),
        ("cfb_contrib_date_idx", "(date)"),
        ("cfb_contrib_election_idx", "(election)"),
        ("cfb_contrib_schedule_idx", "(schedule)"),
        ("cfb_contrib_amnt_idx", "(amnt)"),
        ("cfb_contrib_name_idx", "(lower(name))"),
        ("cfb_contrib_zip_idx", "(zip)"),
        ("cfb_contrib_empname_idx", "(lower(empname))"),
        ("cfb_contrib_intermname_idx", "(lower(intermname))"),
        # matched contributions are the point of the CFB program
        ("cfb_contrib_matched_idx", "(matchamnt) WHERE matchamnt > 0"),
    ],
    "cfb_expenditures": [
        ("cfb_exp_refno_idx", "(refno)"),
        ("cfb_exp_candid_idx", "(candid)"),
        ("cfb_exp_date_idx", "(date)"),
        ("cfb_exp_election_idx", "(election)"),
        ("cfb_exp_purposecd_idx", "(purposecd)"),
        ("cfb_exp_name_idx", "(lower(name))"),
        ("cfb_exp_amnt_idx", "(amnt)"),
    ],
    "cfb_intermediaries": [
        ("cfb_interm_name_idx", "(lower(name))"),
        ("cfb_interm_candid_idx", "(candid)"),
        ("cfb_interm_election_idx", "(election)"),
    ],
    "nysboe_filers": [
        ("nysboe_filers_filer_id_idx", "(filer_id)"),
        ("nysboe_filers_name_idx", "(lower(name))"),
        ("nysboe_filers_status_idx", "(status)"),
        ("nysboe_filers_cand_name_idx", "(lower(candidate_name))"),
        ("nysboe_filers_election_year_idx", "(election_year)"),
    ],
}


def psql(args=(), sql=None, dbname=None, capture=True):
    cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-qAt"]
    if USE_DATABASE_URL and os.environ.get("DATABASE_URL"):
        cmd += ["-d", os.environ["DATABASE_URL"]]
    else:
        cmd += ["-d", dbname]
    # The CFB exports write dates as M/D/YYYY. Do not rely on the server's
    # DateStyle happening to be MDY -- under DMY, 4/16/1991 would silently
    # become 16 April or fail depending on the value.
    cmd += ["-c", "SET datestyle TO 'ISO, MDY'"]
    if sql is not None:
        cmd += ["-c", sql]
    cmd += list(args)
    res = subprocess.run(cmd, capture_output=capture, text=True)
    if res.returncode != 0:
        sys.stderr.write((res.stderr or "") + "\n")
        raise SystemExit(f"psql failed ({res.returncode})")
    return (res.stdout or "").strip()


def csv_header(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return next(csv.reader(fh))


def csv_stats(path, amount_col="AMNT"):
    """Row count and amount sum, computed straight from the file."""
    csv.field_size_limit(10**9)
    n = 0
    total = 0.0
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rdr = csv.DictReader(fh)
        has_amt = amount_col in (rdr.fieldnames or [])
        for row in rdr:
            n += 1
            if has_amt and row.get(amount_col):
                try:
                    total += float(row[amount_col])
                except ValueError:
                    pass
    return n, total


def stream_without_trailing_blanks(path, out):
    """Copy the file to `out`, dropping only blank lines at end of file.

    Every one of these exports ends with a blank line, which COPY reads as a row
    with one empty field ('missing data for column ...'). It cannot be fixed by
    filtering all blank lines: the contributions export has newlines INSIDE
    quoted fields, so a blank line can be real data. Blank lines are therefore
    held back and emitted only once a non-blank line proves they were interior.
    """
    pending = []
    dropped = 0
    with open(path, "rb") as fh:
        for line in fh:
            if line.strip() == b"":
                pending.append(line)
                continue
            for p in pending:
                out.write(p)
            pending = []
            out.write(line)
    dropped = len(pending)
    return dropped


def copy_csv(path, table, cols, dbname):
    collist = ", ".join(f'"{c}"' for c in cols)
    force = [c for c in NULLABLE.get(table, ()) if c in cols]
    opts = "FORMAT csv, HEADER true"
    if force:
        opts += f", FORCE_NULL ({', '.join(chr(34) + c + chr(34) for c in force)})"
    stmt = f"COPY {table} ({collist}) FROM STDIN WITH ({opts})"
    size = os.path.getsize(path) / 1e6
    print(f"  COPY {os.path.basename(path)} ({size:,.0f} MB) -> {table}", flush=True)

    cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-qAt"]
    if USE_DATABASE_URL and os.environ.get("DATABASE_URL"):
        cmd += ["-d", os.environ["DATABASE_URL"]]
    else:
        cmd += ["-d", dbname]
    cmd += ["-c", "SET datestyle TO 'ISO, MDY'", "-c", stmt]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        dropped = stream_without_trailing_blanks(path, proc.stdin)
        proc.stdin.close()
    except BrokenPipeError:
        dropped = 0
    err = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        sys.stderr.write(err + "\n")
        raise SystemExit(f"COPY into {table} failed")
    if dropped:
        print(f"    (dropped {dropped} blank line(s) at end of file)", flush=True)


def load_cfb_file(path, table, dbname):
    """CFB headers lowercase straight onto the staging column names."""
    hdr = csv_header(path)
    cols = [c.strip().lower() for c in hdr]
    copy_csv(path, table, cols, dbname)
    return len(cols)


def load_filers(path, dbname, repair_to=None):
    hdr = csv_header(path)
    if [h.strip() for h in hdr] != FILER_HEADER:
        raise SystemExit(
            "ListOfFilers.csv header does not match the expected 20 columns.\n"
            f"  got     : {hdr}\n  expected: {FILER_HEADER}"
        )
    if repair_to is None:
        repair_to = os.path.join(tempfile.gettempdir(), "ListOfFilers_repaired.csv")
    print(f"  repairing -> {repair_to}", flush=True)
    res = subprocess.run([sys.executable, REPAIR, path, repair_to], text=True)
    if res.returncode != 0:
        raise SystemExit(
            "repair_listoffilers.py could not fix every malformed row; "
            "COPY would reject them. Fix or exclude them before loading."
        )
    copy_csv(repair_to, "nysboe_filers", FILER_COLUMNS, dbname)
    return repair_to


def build_indexes(table, dbname):
    for name, expr in INDEXES.get(table, []):
        print(f"    {name}", flush=True)
        psql(sql=f"CREATE INDEX {name} ON {table} {expr};", dbname=dbname)


def verify(table, path, dbname, amount_col="AMNT"):
    db_rows = int(psql(sql=f"SELECT count(*) FROM {table};", dbname=dbname))
    file_rows, file_total = csv_stats(path, amount_col)
    ok_rows = db_rows == file_rows
    print(f"  {table}")
    print(f"    rows  db={db_rows:,}  csv={file_rows:,}  "
          f"{'OK' if ok_rows else 'MISMATCH'}")

    # nysboe_filers carries no amount column, so there is no total to reconcile.
    has_amnt = psql(
        sql=f"SELECT count(*) FROM information_schema.columns "
            f"WHERE table_name = '{table}' AND column_name = 'amnt';",
        dbname=dbname,
    ) == "1"
    if not has_amnt:
        print("    amnt  (no amount column on this table -- row count only)")
        return ok_rows

    db_total = psql(sql=f"SELECT coalesce(sum(amnt),0)::text FROM {table};",
                    dbname=dbname)
    ok_amt = abs(float(db_total) - file_total) < 0.01
    print(f"    amnt  db=${float(db_total):,.2f}  csv=${file_total:,.2f}  "
          f"{'OK' if ok_amt else 'MISMATCH'}")
    return ok_rows and ok_amt


def main():
    global USE_DATABASE_URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbname", default="ploppy")
    ap.add_argument("--use-database-url", action="store_true",
                    help="connect via $DATABASE_URL instead of --dbname")
    ap.add_argument("--contributions", help="CFB contributions export (52 cols)")
    ap.add_argument("--expenditures", help="CFB expenditures export (32 cols)")
    ap.add_argument("--intermediaries", help="CFB intermediaries export (24 cols)")
    ap.add_argument("--filers", help="NYSBOE ListOfFilers.csv (20 cols)")
    ap.add_argument("--repair-to", help="where to write the repaired filers CSV")
    ap.add_argument("--skip-indexes", action="store_true")
    args = ap.parse_args()
    USE_DATABASE_URL = args.use_database_url

    cfb = [(args.contributions, "cfb_contributions", 52),
           (args.expenditures, "cfb_expenditures", 32),
           (args.intermediaries, "cfb_intermediaries", 24)]
    if not any(p for p, _, _ in cfb) and not args.filers:
        raise SystemExit("nothing to do -- pass at least one input file")

    for path, table, want in cfb:
        if path and not os.path.exists(path):
            raise SystemExit(f"missing {path}")
        if path:
            n = len(csv_header(path))
            if n != want:
                raise SystemExit(
                    f"{os.path.basename(path)} has {n} columns; {table} expects "
                    f"{want}. Did the --contributions / --expenditures / "
                    f"--intermediaries flags get crossed?"
                )
    if args.filers and not os.path.exists(args.filers):
        raise SystemExit(f"missing {args.filers}")

    if any(p for p, _, _ in cfb):
        print("creating CFB staging tables ...", flush=True)
        psql(["-f", CFB_SCHEMA], dbname=args.dbname)
    if args.filers:
        print("creating nysboe_filers ...", flush=True)
        psql(["-f", FILER_SCHEMA], dbname=args.dbname)

    print("loading ...", flush=True)
    loaded = []
    for path, table, _ in cfb:
        if path:
            load_cfb_file(path, table, args.dbname)
            loaded.append((table, path))
    repaired = None
    if args.filers:
        repaired = load_filers(args.filers, args.dbname, args.repair_to)
        loaded.append(("nysboe_filers", repaired))

    if not args.skip_indexes:
        print("indexing ...", flush=True)
        for table, _ in loaded:
            print(f"  {table}", flush=True)
            build_indexes(table, args.dbname)

    print("analyzing ...", flush=True)
    for table, _ in loaded:
        psql(sql=f"VACUUM ANALYZE {table};", dbname=args.dbname)

    print("verifying against the files ...", flush=True)
    ok = all(verify(table, path, args.dbname) for table, path in loaded)

    for table, _ in loaded:
        size = psql(sql=f"SELECT pg_size_pretty(pg_total_relation_size('{table}'));",
                    dbname=args.dbname)
        print(f"  {table} size (incl. indexes): {size}")

    if not ok:
        return 1
    print("load verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
