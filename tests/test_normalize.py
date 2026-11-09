import pytest

from src.vocab.normalize import GOLDEN_VECTORS, fold_ascii, name_norm


def test_vocab_package_importable():
    import src.vocab  # noqa: F401


@pytest.mark.parametrize("raw,expected", GOLDEN_VECTORS)
def test_golden_vectors(raw, expected):
    assert name_norm(raw) == expected


def test_punctuation_becomes_a_separator_not_nothing():
    # "SMITH-JONES" must not collapse to "SMITHJONES".
    assert name_norm("SMITH-JONES") == "SMITH JONES"


def test_cfb_last_comma_first_loses_the_comma():
    assert name_norm("SMITH, JOHN A") == "SMITH JOHN A"


def test_replacement_character_is_deleted_not_spaced():
    # Deleting U+FFFD keeps similarity('JOSE MUOZ','JOSE MUNOZ') at 0.615, above
    # the 0.6 trigram threshold. Spacing it gives 0.571 and loses the match.
    assert name_norm("JOSE MU�OZ") == "JOSE MUOZ"


def test_soft_hyphen_is_deleted():
    assert name_norm("SMITH­JONES") == "SMITHJONES"


def test_accents_fold_to_ascii():
    assert name_norm("Gutiérrez, José") == "GUTIERREZ JOSE"
    assert name_norm("Peña") == "PENA"
    assert name_norm("Łukasz") == "LUKASZ"


def test_empty_and_punctuation_only_are_none():
    assert name_norm("") is None
    assert name_norm("   ") is None
    assert name_norm("...") is None
    assert name_norm(None) is None


def test_fold_ascii_leaves_plain_text_alone():
    assert fold_ascii("PLAIN TEXT 123") == "PLAIN TEXT 123"


def test_golden_vectors_cover_the_hazard_classes():
    raws = [r for r, _ in GOLDEN_VECTORS]
    assert any("," in r for r in raws), "need a LAST, FIRST vector"
    assert any("�" in r for r in raws), "need a U+FFFD vector"
    assert any("'" in r for r in raws), "need an apostrophe vector"
    assert any("-" in r for r in raws), "need a hyphen vector"
    assert any("&" in r for r in raws), "need an ampersand vector"
    assert len(GOLDEN_VECTORS) >= 20


def test_every_multichar_uppercase_that_matters_is_expanded_explicitly():
    """The one step not generated from the shared table is upper(), and the
    engines disagree about it: Python does full case mapping, SQL does simple.
    So every character whose uppercase is multi-character AND whose Python
    normalization is more than one character must be expanded explicitly in
    EXPAND_FOLDS, or Python will diverge from both engines. Derived from
    unicodedata so a new one cannot be missed.

    An earlier version required the uppercase to be pure ASCII (isascii()),
    which hid U+0149 and U+1E9A: their uppercase is PARTLY ASCII (U+02BC + N,
    A + U+02BE), so they were skipped yet still diverged."""
    from src.vocab.normalize import EXPAND_FOLDS, name_norm

    # Probe inside a word so an expansion that yields a space is still visible:
    # a character that merely folds, or becomes a space, or is deleted, gives
    # "AxB" of length <= 3; only a real expansion makes it longer.
    needs_expanding = {
        chr(cp)
        for cp in range(0x20, 0x110000)
        if not 0xD800 <= cp <= 0xDFFF
        and len(name_norm("A" + chr(cp) + "B")) > 3
    }
    assert needs_expanding == set(EXPAND_FOLDS), (
        f"missing={sorted(needs_expanding - set(EXPAND_FOLDS))!r} "
        f"extra={sorted(set(EXPAND_FOLDS) - needs_expanding)!r}"
    )


def test_the_table_reproduces_python_across_the_whole_plane():
    """The golden vectors are the author's own choices, and a sweep found 820
    codepoints they missed. This asserts the actual claim -- that the generated
    table reproduces Python -- over every codepoint rather than a sample.

    Simulated in Python against the generated table rather than run through the
    engines, so it costs a second or two instead of minutes; test_cross_engine
    covers the engines themselves on the vectors.
    """
    import re

    from src.vocab.normalize import EXPAND_FOLDS, name_norm, translate_pairs

    src, dst = translate_pairs()
    mapping = {ord(a): b for a, b in zip(src, dst)}
    mapping.update({ord(c): None for c in src[len(dst):]})

    def as_sql_would(text: str) -> str | None:
        for a, b in EXPAND_FOLDS.items():
            text = text.replace(a, b)
        return re.sub(r"[^A-Z0-9]+", " ", text.translate(mapping).upper()).strip() or None

    divergences = [
        hex(cp)
        for cp in range(0x20, 0x110000)
        if not 0xD800 <= cp <= 0xDFFF
        and name_norm("A" + chr(cp) + "B") != as_sql_would("A" + chr(cp) + "B")
    ]
    assert not divergences, f"{len(divergences)} codepoints diverge: {divergences[:20]}"


def test_the_structural_rule_is_not_duplicated_by_hand():
    """Only the tables are generated; the regex and the trim/nullif wrapper are
    templates. Mutating _NON_ALNUM in Python left the whole suite green while
    Python and SQL disagreed, so assert the SQL carries the same class."""
    from src.vocab.normalize import _NON_ALNUM
    from src.vocab.sql_gen import duckdb_sql, postgres_sql

    for sql in (postgres_sql(), duckdb_sql()):
        assert _NON_ALNUM.pattern in sql, (
            f"generated SQL does not carry {_NON_ALNUM.pattern!r}; the Python rule and the "
            "SQL template have drifted"
        )
