import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def duckdb_conn():
    duckdb = pytest.importorskip("duckdb")
    conn = duckdb.connect()
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pg_conn():
    """A connection to the local ploppy database, or skip.

    Postgres is optional for this plan: the Python and DuckDB implementations are
    the ones CI can always check. The Postgres leg runs locally and in any CI job
    that provides PLOPPY_TEST_DSN.
    """
    psycopg = pytest.importorskip("psycopg")
    dsn = os.environ.get("PLOPPY_TEST_DSN", "dbname=ploppy")
    try:
        conn = psycopg.connect(dsn)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no Postgres at {dsn!r}: {exc}")
    yield conn
    conn.close()
