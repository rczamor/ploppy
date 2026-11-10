#!/usr/bin/env python3
"""Download every NY State Board of Elections contribution record from 2016 onward.

Source: data.ny.gov dataset e9ss-239a, "Campaign Finance Disclosure Reports Data:
Beginning 1999" -- the NYSBOE itemized disclosure data published by the agency via
Socrata. Same record layout as the Bulk Download ZIPs on
publicreporting.elections.ny.gov (those are served behind a bot-check that blocks
scripted clients; the Socrata endpoint is the supported programmatic path).

Contribution schedules pulled:
  A  Monetary Contributions Received From Ind. & Part.
  B  Monetary Contributions Received From Corporation
  C  Monetary Contributions Received From All Other
  D  In-Kind (Non-Monetary) Contributions Received

Pagination is keyset-based on filing_trans_id (unique, non-null), so the run is
resumable and immune to deep-offset drift.
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DATASET = "e9ss-239a"
BASE = f"https://data.ny.gov/resource/{DATASET}.csv"
SCHEDULES = ("A", "B", "C", "D")
START_DATE = "2016-01-01T00:00:00"
PAGE = 50_000
MAX_RETRIES = 6

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nysboe")
DATA_CSV = os.path.join(OUT_DIR, "contributions_2016_present.csv")
NULLDATE_CSV = os.path.join(OUT_DIR, "contributions_null_sched_date.csv")
STATE_JSON = os.path.join(OUT_DIR, "download_state.json")
MANIFEST_JSON = os.path.join(OUT_DIR, "manifest.json")

SCHED_LIST = ",".join(f"'{s}'" for s in SCHEDULES)
WHERE_DATED = (
    f"sched_date >= '{START_DATE}' AND filing_sched_abbrev in({SCHED_LIST})"
)
WHERE_NULLDATE = f"sched_date IS NULL AND filing_sched_abbrev in({SCHED_LIST})"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch(params):
    """GET the Socrata CSV endpoint with retry/backoff. Returns decoded text."""
    url = BASE + "?" + urllib.parse.urlencode(params)
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/csv"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            code = getattr(exc, "code", None)
            if attempt == MAX_RETRIES:
                raise
            log(f"  request failed ({code or exc}); retry {attempt}/{MAX_RETRIES - 1} in {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, 60)


def count_rows(where):
    url = (
        f"https://data.ny.gov/resource/{DATASET}.json?"
        + urllib.parse.urlencode({"$select": "count(1) as n", "$where": where})
    )
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                return int(json.load(resp)[0]["n"])
        except Exception:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)


def load_state():
    if os.path.exists(STATE_JSON):
        with open(STATE_JSON) as fh:
            return json.load(fh)
    return {"last_id": 0, "rows": 0, "pages": 0}


def save_state(state):
    tmp = STATE_JSON + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE_JSON)


def split_header(text):
    """Return (header_line, body_text) from a CSV response."""
    nl = text.find("\n")
    if nl == -1:
        return text.strip(), ""
    return text[:nl].rstrip("\r"), text[nl + 1:]


def last_id_of(body, header):
    """Parse the final filing_trans_id out of a CSV body chunk."""
    reader = csv.DictReader([header] + body.splitlines())
    last = None
    n = 0
    for row in reader:
        n += 1
        last = row.get("filing_trans_id")
    return (int(last) if last else None), n


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    log("counting expected rows ...")
    expected = count_rows(WHERE_DATED)
    expected_null = count_rows(WHERE_NULLDATE)
    log(f"expected: {expected:,} dated contribution rows (2016+), {expected_null:,} with null sched_date")

    state = load_state()
    if state["last_id"]:
        log(f"resuming after filing_trans_id={state['last_id']:,} ({state['rows']:,} rows already written)")

    mode = "a" if state["last_id"] else "w"
    header = None
    with open(DATA_CSV, mode, encoding="utf-8", newline="") as out:
        while True:
            params = {
                "$where": f"{WHERE_DATED} AND filing_trans_id > {state['last_id']}",
                "$order": "filing_trans_id",
                "$limit": PAGE,
            }
            text = fetch(params)
            hdr, body = split_header(text)
            header = header or hdr
            if not body.strip():
                log("no more rows")
                break

            if state["rows"] == 0 and mode == "w":
                out.write(hdr + "\n")
            out.write(body if body.endswith("\n") else body + "\n")
            out.flush()

            new_last, got = last_id_of(body, hdr)
            if not got or new_last is None or new_last <= state["last_id"]:
                log(f"pagination stalled at id={state['last_id']}; stopping")
                break

            state["last_id"] = new_last
            state["rows"] += got
            state["pages"] += 1
            save_state(state)
            pct = 100.0 * state["rows"] / expected if expected else 0
            log(f"page {state['pages']:>4}  +{got:>6,}  total {state['rows']:>10,} / {expected:,} ({pct:5.1f}%)  last_id={new_last}")

            if got < PAGE:
                log("final partial page received")
                break

    log("fetching null-sched_date contribution rows ...")
    text = fetch({"$where": WHERE_NULLDATE, "$order": "filing_trans_id", "$limit": PAGE})
    with open(NULLDATE_CSV, "w", encoding="utf-8", newline="") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    null_rows = max(0, sum(1 for _ in open(NULLDATE_CSV, encoding="utf-8")) - 1)

    manifest = {
        "source_dataset": f"https://data.ny.gov/d/{DATASET}",
        "source_api": BASE,
        "publisher": "New York State Board of Elections (via data.ny.gov)",
        "equivalent_ui": "https://publicreporting.elections.ny.gov/DownloadCampaignFinanceData/DownloadCampaignFinanceData",
        "downloaded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "filter": {"sched_date_from": START_DATE[:10], "filing_sched_abbrev": list(SCHEDULES)},
        "schedule_meanings": {
            "A": "Monetary Contributions Received From Ind. & Part.",
            "B": "Monetary Contributions Received From Corporation",
            "C": "Monetary Contributions Received From All Other",
            "D": "In-Kind (Non-Monetary) Contributions Received",
        },
        "files": {
            os.path.basename(DATA_CSV): {"rows": state["rows"], "expected": expected},
            os.path.basename(NULLDATE_CSV): {"rows": null_rows, "expected": expected_null},
        },
        "pagination": {"key": "filing_trans_id", "page_size": PAGE, "pages": state["pages"]},
        "complete": state["rows"] == expected and null_rows == expected_null,
    }
    with open(MANIFEST_JSON, "w") as fh:
        json.dump(manifest, fh, indent=2)

    log(f"wrote {state['rows']:,} dated rows (expected {expected:,}) -> {DATA_CSV}")
    log(f"wrote {null_rows:,} null-date rows (expected {expected_null:,}) -> {NULLDATE_CSV}")
    if not manifest["complete"]:
        log("WARNING: row counts do not match expected totals")
        return 1
    log("row counts match expected totals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
