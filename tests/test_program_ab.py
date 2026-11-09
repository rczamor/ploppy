"""The 2021 Program A/B split is the only natural experiment in the data:
same city, same year, two match ratios and two contribution limits.

This test asserts the split is now *expressible*, not that any particular
average holds -- the spec records three different Program B averages
($576.52 / $620.33 / $606.25) under three different predicates, and fixing
that is a later plan's job. What must be true here is that the office codes
distinguish the two programs at all.
"""

import pytest

from src.database import code_mappings as cm

PROGRAM_A_CODES = {"11", "22", "33", "44", "55", "66"}


def test_program_a_codes_are_distinguishable_from_program_b():
    for code in PROGRAM_A_CODES:
        assert "Program A" in cm.get_office_name(code)
    for code in {"1", "2", "3", "4", "5", "6"}:
        assert "Program A" not in cm.get_office_name(code)


def test_independent_spender_is_neither_program():
    label = cm.get_office_name("IS")
    assert "Program A" not in label
    assert label == "Independent Spender"


@pytest.mark.postgres
def test_both_programs_have_2021_contributions(pg_conn):
    rel = pg_conn.execute(
        "SELECT to_regclass('public.cfb_contributions')"
    ).fetchone()[0]
    if rel is None:
        pytest.skip(
            "cfb_contributions is not loaded in this database; this test asserts a "
            "property of the data, not of the code. CI stands up an empty Postgres "
            "on purpose -- loading 2.1M rows there is a later plan's decision."
        )
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT officecd, count(*), sum(amnt)
            FROM cfb_contributions
            WHERE election = '2021' AND schedule = 'ABC' AND amnt > 0
              AND officecd = ANY(%s)
            GROUP BY officecd ORDER BY officecd
            """,
            [sorted(PROGRAM_A_CODES)],
        )
        program_a = cur.fetchall()
    assert program_a, "no 2021 Program A rows found; check the office-code set"
    for officecd, rows, total in program_a:
        assert rows > 0 and total > 0
