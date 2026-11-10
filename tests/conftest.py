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
