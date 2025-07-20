"""Code mappings for NYC Campaign Finance Board data."""

import pandas as pd
import re

# Office codes mapping
OFFICE_CODES = {
    '1': 'Mayor',
    '2': 'Public Advocate',
    '3': 'Comptroller',
    '4': 'Borough President',
    '5': 'City Council Member',
    '6': 'Unknown/Other',
    '11': 'Special Designation',
    '44': 'Special District',
    '55': 'Special Office',
    'IS': 'Independent Spending'
}

# Candidate class mapping
CANDIDATE_CLASS = {
    'P': 'Participating',
    'NP': 'Non-participating',
    'UN': 'Unknown',
    'L': 'Limited Participation',
    'E': 'Exempt'
}

# Contributor type codes
CONTRIBUTOR_CODES = {
    'IND': 'Individual',
    'CORP': 'Corporation',
    'LLC': 'Limited Liability Company',
    'PART': 'Partnership',
    'EMPO': 'Employee Organization/Union',
    'PCOMP': 'Political Committee',
    'PCOMC': 'Political Committee (Other)',
    'OTHR': 'Other',
    'UNKN': 'Unknown'
}

# Borough codes
BOROUGH_CODES = {
    'M': 'Manhattan',
    'K': 'Brooklyn',
    'Q': 'Queens',
    'X': 'Bronx',
    'S': 'Staten Island',
    'Z': 'Outside NYC'
}

# Payment method codes
PAYMENT_METHODS = {
    1: 'Cash',
    2: 'Check',
    3: 'Credit Card',
    4: 'Electronic Transfer',
    5: 'Other'
}

# Schedule types
SCHEDULE_TYPES = {
    'ABC': 'Contributions',
    'D': 'Expenditures',
    'M': 'Matchable Contributions',
    'ICONT': 'In-Kind Contributions'
}

# Adjustment type codes
ADJUSTMENT_TYPES = {
    1: 'Addition',
    2: 'Deletion',
    3: 'Modification'
}

# Election type suffixes
ELECTION_TYPES = {
    'T': 'Transition',
    'A': 'Special Election',
    'U': 'Unknown Type'
}

def get_office_name(code: str) -> str:
    """Get office name from code."""
    return OFFICE_CODES.get(str(code), f'Unknown Office ({code})')

def get_candidate_class_desc(code: str) -> str:
    """Get candidate class description from code."""
    return CANDIDATE_CLASS.get(code, f'Unknown Class ({code})')

def get_contributor_type(code: str) -> str:
    """Get contributor type from code."""
    return CONTRIBUTOR_CODES.get(code, 'Unknown Type')

def get_borough_name(code: str) -> str:
    """Get borough name from code."""
    return BOROUGH_CODES.get(code, 'Unknown Borough')

def get_payment_method(code: int) -> str:
    """Get payment method from code."""
    return PAYMENT_METHODS.get(code, 'Unknown Method')

def get_schedule_description(code: str) -> str:
    """Get schedule description from code."""
    return SCHEDULE_TYPES.get(code, f'Unknown Schedule ({code})')

def get_adjustment_type(code: int) -> str:
    """Get adjustment type from code."""
    return ADJUSTMENT_TYPES.get(code, 'Unknown Adjustment')

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