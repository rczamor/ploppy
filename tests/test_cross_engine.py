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
