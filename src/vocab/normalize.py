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


def translate_pairs(max_codepoint: int = 0x1EFF) -> tuple[str, str]:
    """Build the (from, to) argument pair for Postgres translate().

    Postgres has no NFD-strip primitive usable in an IMMUTABLE expression, so the
    fold is expressed as an explicit character list. Enumerating it from
    unicodedata here -- rather than typing it -- is what keeps the Postgres
    function, the DuckDB macro and this module from drifting apart.

    Covers Latin-1 Supplement through Latin Extended-B by default, which is every
    accented form observed in either jurisdiction's data. Characters that fold to
    more than one ASCII character (such as U+00C6 AE) cannot be expressed by
    translate() and are reported by sql_gen so they can be handled explicitly.
    """
    src: list[str] = []
    dst: list[str] = []
    for cp in range(0xC0, max_codepoint + 1):
        ch = chr(cp)
        folded = fold_ascii(ch)
        if len(folded) != 1 or folded == ch or not folded.isascii():
            continue
        src.append(ch)
        dst.append(folded)
    for ch in DELETE_CHARS:
        src.append(ch)  # no counterpart in dst: translate() deletes it
    # Combining marks must go too, or decomposed input diverges from DuckDB.
    # Python strips them via NFD, but translate() over precomposed characters
    # alone leaves them, and the [^A-Z0-9] step then
    # turns each one into a SPACE -- splitting the word. Measured:
    #   NFD "JOSE MUNOZ"     -> duckdb 'JOSE MUNOZ'     pg 'JOSE MUN OZ'
    #   NFD "Nguyen Thi Hoa" -> duckdb 'NGUYEN THI HOA' pg 'NGUYE N THI HOA'
    # Appending the range fixes both exactly. Precomposed input agreed already,
    # which is why a vector set that is entirely NFC would never catch this.
    for cp in range(0x0300, 0x0370):
        src.append(chr(cp))
    return "".join(src), "".join(dst)


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
