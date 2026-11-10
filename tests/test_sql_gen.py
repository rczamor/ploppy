from src.vocab.sql_gen import duckdb_sql, postgres_sql


def test_postgres_sql_is_immutable_and_names_the_function():
    sql = postgres_sql()
    assert "CREATE OR REPLACE FUNCTION vocab.name_norm" in sql
    assert "IMMUTABLE" in sql
    assert "unaccent" not in sql.lower(), "unaccent is STABLE; must not be used"


def test_duckdb_sql_defines_the_macro():
    sql = duckdb_sql()
    assert "CREATE OR REPLACE MACRO name_norm" in sql


def test_duckdb_macro_actually_deletes_what_it_claims(duckdb_conn):
    """A string-presence assertion cannot catch the defect this guards. The
    escaped form '[\\xFFFD\\x00AD]' is accepted by DuckDB without error and is a
    class of the LETTERS A, D and F -- it turned 'ADAM FOX' into 'M OX' and left
    U+FFFD in place. So execute the generated SQL and check behaviour."""
    from src.vocab.sql_gen import duckdb_sql

    duckdb_conn.execute(duckdb_sql())
    row = duckdb_conn.execute(
        "select name_norm(?), name_norm(?), name_norm(?)",
        ["ADAM FOX", "DAVID", "JOSE\ufffd MUNOZ"],
    ).fetchone()
    assert row[0] == "ADAM FOX", "the delete class is eating letters"
    assert row[1] == "DAVID", "the delete class is eating letters"
    assert row[2] == "JOSE MUNOZ", "U+FFFD was not deleted"


def test_generated_files_are_in_sync(repo_root):
    """Regenerate with: python3 -m src.vocab.sql_gen --write"""
    gen = repo_root / "src" / "vocab" / "generated"
    assert (gen / "name_norm_pg.sql").read_text(encoding="utf-8") == postgres_sql()
    assert (gen / "name_norm_duckdb.sql").read_text(encoding="utf-8") == duckdb_sql()
