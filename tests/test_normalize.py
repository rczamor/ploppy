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
