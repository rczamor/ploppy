import pytest

from src.vocab.code_key import (
    KNOWN_REPAIRS,
    CodeKeyError,
    parse_enumeration,
    parse_key_csv,
)


def test_parse_enumeration_simple():
    assert parse_enumeration("0=Unknown; 1=Cash; 2=Check") == {
        "0": "Unknown",
        "1": "Cash",
        "2": "Check",
    }


def test_parse_enumeration_recovers_cfbs_missing_semicolon():
    # CFB's ADJTYPECD omits the separator between "Returned Check" and "2=Refund".
    assert parse_enumeration(
        "0=Unknown; 1=Returned Check 2=Refund; 5=Other", "ADJTYPECD"
    ) == {
        "0": "Unknown",
        "1": "Returned Check",
        "2": "Refund",
        "5": "Other",
    }


def test_missing_separator_raises_without_a_named_repair():
    """The repair is deliberately not a general heuristic. Unnamed, the defect is
    an error -- which is also what a NEW occurrence of it upstream looks like."""
    with pytest.raises(CodeKeyError, match="KNOWN_REPAIRS"):
        parse_enumeration("0=Unknown; 1=Returned Check 2=Refund; 5=Other")


def test_parse_enumeration_keeps_parenthetical_labels_intact():
    got = parse_enumeration(
        "1=Mayor; 11=Mayor Program A (EC2021 Only);IS=Independent Spender"
    )
    assert got == {
        "1": "Mayor",
        "11": "Mayor Program A (EC2021 Only)",
        "IS": "Independent Spender",
    }


def test_parse_enumeration_maps_blank_to_empty_string():
    got = parse_enumeration("C=Compliance Costs; U=Unknown; Blank = Not Exempt")
    assert got[""] == "Not Exempt"
    assert "Blank" not in got


def test_parse_enumeration_without_equals_returns_label_set():
    # CANCLASS has no code= form; the labels are the values.
    assert parse_enumeration(
        "Participant, Non-Participant, Limited Participant, Undetermined"
    ) == {
        "Participant": "Participant",
        "Non-Participant": "Non-Participant",
        "Limited Participant": "Limited Participant",
        "Undetermined": "Undetermined",
    }


def test_parse_enumeration_empty_when_no_enumeration():
    assert parse_enumeration("") == {}


def test_parse_key_csv_reads_every_column(repo_root):
    key = parse_key_csv(repo_root / "data" / "reference" / "Key-Contribution.csv")
    assert len(key) == 52, f"expected 52 columns, got {len(key)}"
    assert key["ELECTION"]["column"] == 1
    assert key["INT_C_CODE"]["column"] == 52
    assert key["AMNT"]["type"] == "Numeric"
    assert key["DATE"]["type"] == "Date"


@pytest.mark.parametrize(
    "field,code,label",
    [
        ("OFFICECD", "11", "Mayor Program A (EC2021 Only)"),
        ("OFFICECD", "55", "City Council Program A (EC2021 Only)"),
        ("SCHEDULE", "M", "Receipt Adjustments"),
        ("SCHEDULE", "D", "In-Kind Contributions"),
        ("C_CODE", "PCOMP", "Political Action Committee"),
        ("C_CODE", "PCOMC", "Candidate Committee"),
        ("PAY_METHOD", "4", "Credit Card"),
        ("PAY_METHOD", "5", "Money Order"),
        ("BOROUGHCD", "Z", "Outside New York City"),
        ("ADJTYPECD", "2", "Refund"),
    ],
)
def test_parse_key_csv_extracts_known_values(repo_root, field, code, label):
    key = parse_key_csv(repo_root / "data" / "reference" / "Key-Contribution.csv")
    assert key[field]["values"][code] == label


KEY_PATH = ("data", "reference", "Key-Contribution.csv")

EXPECTED_COUNTS = {
    "OFFICECD": 13, "CANCLASS": 4, "SCHEDULE": 10, "C_CODE": 13,
    "BOROUGHCD": 6, "PAY_METHOD": 6, "PURPOSECD": 24, "EXEMPTCD": 6,
    "ADJTYPECD": 4,
}

FULL_ENUMERATIONS = {
    "SCHEDULE": {
        "ABC": "Monetary Contributions",
        "D": "In-Kind Contributions",
        "G": "Transfers In",
        "K": "Loans/Liabilities Forgiven",
        "M": "Receipt Adjustments",
        "N": "Outstanding Liabilities",
        "ICONT": "Monetary Contributions",
        "IEXPF": "In-Kind (Bill Paid)",
        "IDISC": "In-Kind (Vendor Discount)",
        "IREF": "Refund",
    },
    "PAY_METHOD": {
        "0": "Unknown", "1": "Cash", "2": "Check",
        "3": "Other", "4": "Credit Card", "5": "Money Order",
    },
    "BOROUGHCD": {
        "K": "Brooklyn", "M": "Manhattan", "Q": "Queens",
        "S": "Staten Island", "X": "Bronx", "Z": "Outside New York City",
    },
    "ADJTYPECD": {"0": "Unknown", "1": "Returned Check", "2": "Refund", "5": "Other"},
    "EXEMPTCD": {
        "C": "Compliance Costs",
        "E": "Previous Election Costs",
        "P": "Petition Challenges",
        "S": "Constituent Services",
        "U": "Unknown",
        "": "Not Exempt",
    },
}


@pytest.fixture(scope="session")
def real_key(repo_root):
    return parse_key_csv(repo_root.joinpath(*KEY_PATH))


def test_exactly_nine_fields_carry_enumerations(real_key):
    enumerated = {n for n, m in real_key.items() if m["values"]}
    assert enumerated == set(EXPECTED_COUNTS)


@pytest.mark.parametrize("field,count", sorted(EXPECTED_COUNTS.items()))
def test_each_enumerated_field_has_the_expected_number_of_codes(real_key, field, count):
    """Spot-checking one code per field would still pass if the parser dropped or
    merged the others. This is the cheap guard against a silent shrink."""
    assert len(real_key[field]["values"]) == count


@pytest.mark.parametrize("field,expected", sorted(FULL_ENUMERATIONS.items()))
def test_full_enumerations_are_pinned(real_key, field, expected):
    assert real_key[field]["values"] == expected


def test_schedule_abc_is_one_token_not_three(real_key):
    """ABC covers 2,069,541 of 2,123,865 contribution rows. Nothing pinned it, so
    a regression that split it into A, B and C would have passed the whole suite."""
    schedule = real_key["SCHEDULE"]["values"]
    assert "ABC" in schedule
    assert not {"A", "B", "C"} & set(schedule)


def test_exemptcd_blank_is_the_empty_string_in_the_real_file(real_key):
    """Previously asserted only against a hand-written string, never the file."""
    exempt = real_key["EXEMPTCD"]["values"]
    assert exempt[""] == "Not Exempt"
    assert "Blank" not in exempt


def test_canclass_is_label_as_code_in_the_real_file(real_key):
    canclass = real_key["CANCLASS"]["values"]
    assert canclass == {k: k for k in
                        ["Participant", "Non-Participant", "Limited Participant", "Undetermined"]}


def test_known_repair_is_still_needed(real_key):
    """If CFB adds the missing semicolon, this fails -- delete the KNOWN_REPAIRS
    entry when it does. A repair kept after the defect is fixed is a silent
    rewrite of correct upstream data."""
    description = real_key["ADJTYPECD"]["description"]
    assert KNOWN_REPAIRS["ADJTYPECD"][0] in description


@pytest.mark.parametrize("body,fragment", [
    ("A=x; A=y", "duplicate"),
    ("A=Alpha; B=", "empty label"),
    ("A=Foo; B=Bar (see note: x=y)", "KNOWN_REPAIRS"),
    ("Participant, Other; A=1", "mixed"),
])
def test_unparsable_bodies_raise_instead_of_guessing(body, fragment):
    with pytest.raises(CodeKeyError, match=fragment):
        parse_enumeration(body, "TEST")


def test_codes_with_hyphens_and_underscores_survive():
    """[A-Za-z0-9]+ silently truncated these to their tail. This file's own field
    names include RR-IND, SEG-IND and INT_C_CODE, so such codes are plausible."""
    assert parse_enumeration("AB-1=Label; C_2=Foo") == {"AB-1": "Label", "C_2": "Foo"}


def test_codes_json_is_in_sync_with_the_vendored_key(repo_root):
    """codes.json must be exactly what the parser produces. Regenerate with:

        ./.venv/bin/python3 -m src.vocab.code_key --write
    """
    import json

    from src.vocab.code_key import build_codes

    expected = build_codes(repo_root / "data" / "reference" / "Key-Contribution.csv")
    actual = json.loads(
        (repo_root / "src" / "vocab" / "codes.json").read_text(encoding="utf-8")
    )
    assert actual == expected, "codes.json is stale; re-run the generator"
