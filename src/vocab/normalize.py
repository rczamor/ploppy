"""The canonical definition of name normalization.

This module is the single source of truth. src/vocab/sql_gen.py generates the
Postgres function and the DuckDB macro FROM it, and tests/test_cross_engine.py
asserts all three agree byte for byte on GOLDEN_VECTORS. Change the rule here
and nowhere else, then regenerate and re-run the tests.

The rule, in order:
  1. Delete the characters that carry no information: U+FFFD REPLACEMENT
     CHARACTER and U+00AD SOFT HYPHEN. U+FFFD is DELETED rather than replaced
     with a space because 161 NYSBOE rows have it where an accented letter was,
     and deletion keeps similarity('JOSE MUOZ','JOSE MUNOZ') at 0.615 -- above
     the 0.6 trigram threshold -- where spacing gives 0.571 and loses the match.
  2. Fold accented Latin letters to ASCII by stripping combining marks.
  3. Upper-case.
  4. Replace every run of non-alphanumeric characters with a single space, so
     punctuation separates rather than vanishes: SMITH-JONES -> SMITH JONES,
     never SMITHJONES.
  5. Trim. An empty result is None.

Deliberately NOT used: Postgres's unaccent(). Both its signatures are declared
STABLE, not IMMUTABLE, so it cannot appear in an index expression, and the usual
IMMUTABLE wrapper asserts something about a dictionary file that ships with the
server package.
"""

from __future__ import annotations

import re
import sys
import unicodedata

__all__ = [
    "DELETE_CHARS",
    "EXPAND_FOLDS",
    "GOLDEN_VECTORS",
    "fold_ascii",
    "name_norm",
    "translate_pairs",
]

# Characters deleted outright, before any folding. All three are invisible or
# information-free: U+FFFD is a decoding casualty, U+00AD a soft hyphen, and
# U+034F a grapheme joiner. U+034F is here rather than left to the NFD step
# because it has combining CLASS 0 despite category Mn, so the
# `unicodedata.combining(c)` filter below does not remove it -- while the
# generated translate() table, which deletes all of U+0300..U+036F, does.
# That mismatch made 'A'+U+034F+'B' normalize to 'A B' in Python and 'AB' in
# SQL: a word split in half in one engine only.
DELETE_CHARS = "�­͏"

#: Characters whose uppercase is more than one character. Python's str.upper()
#: performs FULL case mapping and expands these; SQL upper() in both Postgres
#: and DuckDB performs SIMPLE case mapping and does not, after which the
#: [^A-Z0-9] step turns each into a space. That made Python the outlier:
#:     'Weiß, Hans' -> python 'WEISS HANS', postgres/duckdb 'WEI HANS'
#: Expanding explicitly here, rather than relying on upper()'s implicit
#: behaviour, is what lets the generated SQL reproduce it. Expanding is also the
#: better normalization: Weiß genuinely should match Weiss.
#: Enumerated from unicodedata over U+0020..U+1FFFF. The selection rule is not
#: "uppercases to pure ASCII" -- that missed U+0149 and U+1E9A, whose uppercase
#: is PARTLY ASCII -- but "Python's own normalization of it is more than one
#: character". The values for U+0149 and U+1E9A reproduce exactly what Python
#: already does with them: the non-ASCII half becomes a space. Characters whose
#: uppercase is multi-character but whose normalization is not (they expand to
#: Greek, Armenian and the like) become spaces in all three engines alike and
#: need no entry.
EXPAND_FOLDS = {
    "ß": "ss",
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
    "ŉ": " n",   # U+0149: upper() is U+02BC + N, so the apostrophe becomes a space
    "ẚ": "a ",   # U+1E9A: upper() is A + U+02BE, likewise
}

#: Single-character folds NFD cannot express. A stroke or bar is part of the
#: letter, not a combining mark, so NFD leaves these intact and the
#: [^A-Z0-9] step then turns each into a SPACE -- dropping the letter
#: outright. Measured before this map existed: "Lukasz" with U+0141
#: normalized to "UKASZ" in all three engines, so it could never match
#: "LUKASZ". Polish, Scandinavian, Croatian and Turkish surnames all hit this.
STROKE_FOLDS = {
    "Ł": "L", "ł": "l",   # L with stroke
    "Ø": "O", "ø": "o",   # O with stroke
    "Đ": "D", "đ": "d",   # D with stroke
    "Ħ": "H", "ħ": "h",   # H with stroke
    "Ŧ": "T", "ŧ": "t",   # T with stroke
    "ı": "i", "ȷ": "j",   # dotless i and j
    "Ɖ": "D", "Ƶ": "Z", "ƶ": "z",
}

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def fold_ascii(text: str) -> str:
    """Delete the no-information characters, fold strokes, strip combining marks."""
    for ch in DELETE_CHARS:
        text = text.replace(ch, "")
    for a, b in EXPAND_FOLDS.items():
        text = text.replace(a, b)
    text = "".join(STROKE_FOLDS.get(c, c) for c in text)
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def name_norm(text: str | None) -> str | None:
    """Normalize a contributor, committee or employer name. None if empty."""
    if text is None:
        return None
    folded = fold_ascii(str(text))
    collapsed = _NON_ALNUM.sub(" ", folded.upper()).strip()
    return collapsed or None


def translate_pairs() -> tuple[str, str]:
    """Build the (from, to) argument pair for translate(), derived from Python.

    The rule is not a codepoint range -- an earlier version walked
    U+00C0..U+01EFF and deleted only U+0300..U+036F, and a full-plane sweep
    found 820 codepoints where Python and the two SQL engines disagreed. The
    rule is: every codepoint whose Python normalization is a single ASCII
    character must be folded to it, and every codepoint Python's fold erases
    must be deleted. Derived here rather than enumerated, so the table cannot
    fall behind the definition it is supposed to mirror.

    ASCII a-z are folded here too, which is what makes the generated SQL
    locale-independent. SQL upper() is not: this cluster is lc_ctype=C, where
    upper('stra\u00dfe') leaves the eszett alone, and under a glibc tr_TR cluster
    upper('i') is 'I' with a dot above -- non-ASCII, so it would become a
    space. translate() runs before upper(), so folding a-z first leaves upper()
    nothing locale-specific to do, and the IMMUTABLE declaration becomes
    honest rather than merely asserted.
    """
    folds: dict[str, str] = {c: c.upper() for c in "abcdefghijklmnopqrstuvwxyz"}
    deletes: list[str] = []
    for cp in range(0xA0, 0x110000):
        if 0xD800 <= cp <= 0xDFFF:          # surrogates are not characters
            continue
        ch = chr(cp)
        if fold_ascii(ch) == "":
            deletes.append(ch)
            continue
        norm = name_norm(ch)
        if norm is not None and len(norm) == 1 and norm.isascii() and norm.isalnum():
            folds[ch] = norm
    src = "".join(folds) + "".join(deletes)
    dst = "".join(folds.values())
    return src, dst


# The contract. Every implementation must produce exactly these outputs.
# Each entry names a hazard rather than being arbitrary.
GOLDEN_VECTORS: list[tuple[str | None, str | None]] = [
    ("SMITH, JOHN A", "SMITH JOHN A"),            # CFB's LAST, FIRST MI
    ("Smith, John A.", "SMITH JOHN A"),           # mixed case + trailing period
    ("SMITH-JONES, MARY", "SMITH JONES MARY"),    # hyphen separates
    ("O'BRIEN, SEAN", "O BRIEN SEAN"),            # apostrophe separates
    ("GOLDMAN SACHS & CO.", "GOLDMAN SACHS CO"),  # ampersand
    ("SMITH & LAQUERCIA, LLP", "SMITH LAQUERCIA LLP"),   # firm, not a person
    ("SMITH & LAQUERCIA, P.C.", "SMITH LAQUERCIA P C"),  # initials split
    ("  multiple   spaces  ", "MULTIPLE SPACES"),  # whitespace runs collapse
    ("Gutiérrez, José", "GUTIERREZ JOSE"),         # Latin-1 accents
    ("Peña", "PENA"),
    ("Nuñez, María", "NUNEZ MARIA"),
    ("Łukasz", "LUKASZ"),                          # stroke, not a combining mark
    ("Nguyễn Thị Hoà", "NGUYEN THI HOA"),        # Latin Extended Additional
    ("JOSE\u0301 MUN\u0303OZ", "JOSE MUNOZ"),          # DECOMPOSED: the case that diverged
    ("Nguyễn", "NGUYEN"),                          # Vietnamese combining marks
    ("Trepinski�S", "TREPINSKIS"),            # U+FFFD deleted
    ("JOSE MU�OZ", "JOSE MUOZ"),              # the similarity case
    ("SMITH­JONES", "SMITHJONES"),            # soft hyphen deleted
    ("A\u034fB", "AB"),                         # U+034F: combining class 0, so NFD alone misses it
    ("Wei\u00df, Hans", "WEISS HANS"),        # str.upper() expands \u00df; SQL upper() does not
    ("Stra\u00dfe 1 LLC", "STRASSE 1 LLC"),
    ("O\ufb03ce, Jane", "OFFICE JANE"),       # U+FB03 ffi ligature
    ("1199 SEIU", "1199 SEIU"),                    # digits survive
    ("FRIENDS OF JANE DOE 2025", "FRIENDS OF JANE DOE 2025"),
    ("...", None),                                 # punctuation only
    ("", None),
    ("   ", None),
    (None, None),
]


def main() -> int:
    for raw, expected in GOLDEN_VECTORS:
        got = name_norm(raw)
        flag = "ok " if got == expected else "BAD"
        print(f"{flag} {raw!r:34s} -> {got!r}")
        if got != expected:
            print(f"      expected {expected!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
