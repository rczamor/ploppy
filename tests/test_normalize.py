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


def test_delete_chars_and_the_translate_table_agree():
    """Every character Python deletes must also be deleted by the generated
    table, and vice versa. U+034F broke this: category Mn but combining class
    0, so the NFD filter kept it while translate() removed it. Comparing the
    two sets directly catches the next one without needing a vector for it."""
    import unicodedata

    from src.vocab.normalize import DELETE_CHARS, translate_pairs

    src, dst = translate_pairs()
    deleted_by_table = set(src[len(dst):])
    deleted_by_python = set(DELETE_CHARS) | {
        c for c in src if unicodedata.combining(c)
    }
    assert deleted_by_table == deleted_by_python, (
        "python and the generated table disagree about which characters vanish: "
        f"table-only={sorted(deleted_by_table - deleted_by_python)!r} "
        f"python-only={sorted(deleted_by_python - deleted_by_table)!r}"
    )


def test_every_multichar_uppercase_that_matters_is_expanded_explicitly():
    """The one step not generated from the shared table is upper(), and the
    engines disagree about it: Python does full case mapping, SQL does simple.
    So every character whose uppercase is multi-character AND lands in [A-Z]
    must be expanded explicitly in EXPAND_FOLDS, or Python will diverge from
    both engines. Derived from unicodedata so a new one cannot be missed."""
    import unicodedata

    from src.vocab.normalize import EXPAND_FOLDS

    needs_expanding = {
        chr(cp)
        for cp in range(0x20, 0x20000)
        if len(chr(cp).upper()) > 1
        and chr(cp).upper().isascii()
        and chr(cp).upper().isalpha()
    }
    assert needs_expanding == set(EXPAND_FOLDS), (
        f"missing={sorted(needs_expanding - set(EXPAND_FOLDS))!r} "
        f"extra={sorted(set(EXPAND_FOLDS) - needs_expanding)!r}"
    )
