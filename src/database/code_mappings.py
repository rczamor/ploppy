"""Code mappings for NYC Campaign Finance Board data.

Labels come from CFB's own published key via src/vocab/codes.json, not from
hand-typed dicts. Regenerate the artifact with:

    python3 -m src.vocab.code_key --write

The dicts below are kept as module-level names because existing callers import
them directly; they are now derived, not authored.
"""

import re

import pandas as pd

from src.vocab import codes as _codes

OFFICE_CODES = _codes.values("OFFICECD")
#: The one field where CFB's key and CFB's own export disagree. The key
#: documents CANCLASS as full labels ("Participant"), but the export column
#: contains abbreviations. Measured in cfb_contributions: P 1,962,546,
#: NP 134,526, UN 26,800. Sourcing it straight from codes.json would make
#: get_candidate_class_desc("P") return "Unknown Class (P)" for 92% of rows.
#:
#: What is and is not derived here: the abbreviation -> label PAIRING (P ->
#: Participant) is authored knowledge that nothing can check against CFB's key,
#: and in the artifact every CANCLASS key equals its value, so the lookup below
#: adds no information of its own. What the assertion guards is drift in the
#: label SET: a renamed, added or removed CFB class stops the import instead of
#: being silently ignored. It cannot catch a wrong pairing.
_CANCLASS_ABBREVIATIONS = {
    "P": "Participant",
    "NP": "Non-Participant",
    "L": "Limited Participant",
    "UN": "Undetermined",
}


def _check_canclass_bridge(published) -> None:
    published = set(published)
    if set(_CANCLASS_ABBREVIATIONS.values()) != published:
        raise ValueError(
            "CANCLASS drift: the bridge targets "
            f"{sorted(_CANCLASS_ABBREVIATIONS.values())} but CFB's key publishes "
            f"{sorted(published)}. Reconcile src/database/code_mappings.py "
            "with src/vocab/codes.json before continuing."
        )


_check_canclass_bridge(_codes.values("CANCLASS"))
CANDIDATE_CLASS = {
    abbrev: _codes.values("CANCLASS")[label]
    for abbrev, label in _CANCLASS_ABBREVIATIONS.items()
}
CONTRIBUTOR_CODES = _codes.values("C_CODE")
BOROUGH_CODES = _codes.values("BOROUGHCD")
SCHEDULE_TYPES = _codes.values("SCHEDULE")
PURPOSE_CODES = _codes.values("PURPOSECD")
EXEMPT_CODES = _codes.values("EXEMPTCD")

def _int_keyed(field: str) -> dict[int, str]:
    """Re-key a numeric field to ints, preserving the pre-existing dict shape.

    Strict on purpose. Filtering non-numeric codes would drop one silently, and
    str.isdigit() is not int()-safe -- '\u00b2'.isdigit() is True while
    int('\u00b2') raises. A new non-numeric code in a numeric field is a real
    upstream event and should stop the build, not vanish.
    """
    out: dict[int, str] = {}
    for code, label_text in _codes.values(field).items():
        try:
            key = int(code)
        except ValueError as exc:
            raise ValueError(
                f"{field}: code {code!r} is not numeric, but this field is re-keyed "
                f"to ints to preserve the pre-existing API shape"
            ) from exc
        if key in out:
            raise ValueError(f"{field}: codes {code!r} and another collapse to {key}")
        out[key] = label_text
    return out


# PAY_METHOD and ADJTYPECD are integers in the contributions export.
PAYMENT_METHODS = _int_keyed("PAY_METHOD")
ADJUSTMENT_TYPES = _int_keyed("ADJTYPECD")

# Not in CFB's key: these are election-token suffixes, not a published
# enumeration, so this stays a literal. parse_election_cycle stores its result in
# elections.election_type, so the values are left exactly as they were.
# NEVER cast an election token to an integer: '2025T' alone is 38,496 rows and
# $4.42M, so globbing or casting moves a 2025 headline by 15%.
ELECTION_TYPES = {
    'T': 'Transition',
    'A': 'Special Election',
    'U': 'Unknown Type'
}


def get_office_name(code: str) -> str:
    """Office sought. Codes 11/22/33/44/55/66 are the 2021 Program A offices."""
    return _codes.label("OFFICECD", code)


def get_candidate_class_desc(code: str) -> str:
    """Resolve the export's abbreviation (P/NP/L/UN), not the key's label."""
    key = _codes._code_key(code)
    if key is None:
        return "Unknown"
    return CANDIDATE_CLASS.get(key, f"Unknown Class ({code})")


def get_contributor_type(code: str) -> str:
    return _codes.label("C_CODE", code, default="Unknown")


def get_borough_name(code: str) -> str:
    return _codes.label("BOROUGHCD", code)


def get_payment_method(code) -> str:
    return _codes.label("PAY_METHOD", code)


def get_schedule_description(code: str) -> str:
    """Schedule. Note M is Receipt Adjustments (refunds, negative AMNT), not
    matchable contributions, and D is In-Kind, not expenditures. Schedule X
    appears in the data but not in CFB's key."""
    return _codes.label("SCHEDULE", code, default=f"Unknown Schedule ({code})")


def get_adjustment_type(code) -> str:
    return _codes.label("ADJTYPECD", code)


def parse_election_cycle(election: str) -> tuple:
    """Parse election cycle string into year and type."""
    if not election:
        return None, None
    
    # Extract year (first 4 digits)
    year_match = re.match(r'(\d{4})', election)
    year = int(year_match.group(1)) if year_match else None
    
    # Extract type suffix if present
    election_type = 'General'
    if len(election) > 4:
        suffix = election[4:].upper()
        election_type = ELECTION_TYPES.get(suffix, 'General')
    
    return year, election_type

def parse_name(full_name: str) -> dict:
    """Parse a name in 'Last, First Middle' format."""
    if not full_name or pd.isna(full_name):
        return {
            'full_name': '',
            'last_name': '',
            'first_name': '',
            'middle_initial': ''
        }
    
    full_name = str(full_name).strip()
    
    # Check if it's an organization (no comma)
    if ',' not in full_name:
        return {
            'full_name': full_name,
            'last_name': full_name,
            'first_name': '',
            'middle_initial': ''
        }
    
    # Parse individual name
    parts = full_name.split(',', 1)
    last_name = parts[0].strip()
    
    if len(parts) > 1:
        # Parse first name and middle initial
        first_parts = parts[1].strip().split()
        first_name = first_parts[0] if first_parts else ''
        
        # Extract middle initial
        middle_initial = ''
        if len(first_parts) > 1:
            # Take the last part as potential middle initial
            potential_mi = first_parts[-1]
            if len(potential_mi) <= 2 and potential_mi.replace('.', '').isalpha():
                middle_initial = potential_mi.replace('.', '')
                # If we found a middle initial, reconstruct first name without it
                if len(first_parts) > 2:
                    first_name = ' '.join(first_parts[:-1])
            else:
                # No middle initial, full first name
                first_name = ' '.join(first_parts)
    else:
        first_name = ''
        middle_initial = ''
    
    return {
        'full_name': full_name,
        'last_name': last_name,
        'first_name': first_name,
        'middle_initial': middle_initial
    }

def is_individual_name(name: str, c_code: str = None) -> bool:
    """Determine if a name is an individual or organization."""
    if not name or pd.isna(name):
        return False
    
    name_upper = str(name).upper()
    
    # Check contributor code first
    if c_code and c_code in ['CORP', 'LLC', 'PART', 'EMPO', 'PCOMP', 'PCOMC']:
        return False
    
    # Organization indicators
    org_indicators = [
        'LLC', 'INC', 'CORP', 'COMMITTEE', 'PAC', 'ASSOCIATION',
        'UNION', 'FOUNDATION', 'TRUST', 'PARTNERSHIP', 'LTD', 'CO.',
        'COMPANY', 'GROUP', 'FUND', 'SOCIETY', 'LEAGUE', 'ALLIANCE',
        'COALITION', 'ORGANIZATION', 'INSTITUTE', 'CENTER', 'BOARD'
    ]
    
    if any(indicator in name_upper for indicator in org_indicators):
        return False
    
    # Individual indicators (has comma for Last, First format)
    if ',' in name:
        return True
    
    # Default to organization if no comma
    return False