import pytest

from src.vocab.code_key import parse_enumeration, parse_key_csv


def test_parse_enumeration_simple():
    assert parse_enumeration("0=Unknown; 1=Cash; 2=Check") == {
        "0": "Unknown",
        "1": "Cash",
        "2": "Check",
    }


def test_parse_enumeration_recovers_cfbs_missing_semicolon():
    # CFB's ADJTYPECD omits the separator between "Returned Check" and "2=Refund".
    assert parse_enumeration("0=Unknown; 1=Returned Check 2=Refund; 5=Other") == {
        "0": "Unknown",
        "1": "Returned Check",
        "2": "Refund",
        "5": "Other",
    }


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
