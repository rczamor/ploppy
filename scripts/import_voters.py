#!/usr/bin/env python3
"""Import voter contacts from CSV file into the database."""

import pandas as pd
import os
import sys
from pathlib import Path
from datetime import datetime
import uuid
import psycopg2
from psycopg2.extras import execute_values
import re

DATABASE_URL = os.environ.get('DATABASE_URL')

def normalize_voter_name(first_name, last_name, middle_name=None, suffix=None):
    """Normalize voter name for matching."""
    parts = []
    if last_name:
        parts.append(str(last_name).upper().strip())
    if first_name:
        parts.append(str(first_name).upper().strip())
    if middle_name and pd.notna(middle_name):
        parts.append(str(middle_name).upper().strip())
    if suffix and pd.notna(suffix):
        parts.append(str(suffix).upper().strip())
    
    full_name = ' '.join(parts)
    # Remove extra spaces and non-alphanumeric characters
    full_name = re.sub(r'[^A-Z0-9\s]', '', full_name)
    full_name = re.sub(r'\s+', ' ', full_name).strip()
    return full_name

def normalize_address(address1, city, state, zip_code, unit=None, unit_number=None):
    """Normalize address for matching."""
    parts = []
    
    if address1 and pd.notna(address1):
        # Normalize street address
        addr = str(address1).upper().strip()
        # Replace common abbreviations
        addr = re.sub(r'\bST\b', 'STREET', addr)
        addr = re.sub(r'\bAVE\b', 'AVENUE', addr)
        addr = re.sub(r'\bRD\b', 'ROAD', addr)
        addr = re.sub(r'\bDR\b', 'DRIVE', addr)
        addr = re.sub(r'\bPL\b', 'PLACE', addr)
        addr = re.sub(r'\bBLVD\b', 'BOULEVARD', addr)
        addr = re.sub(r'\bLN\b', 'LANE', addr)
        addr = re.sub(r'\bCT\b', 'COURT', addr)
        addr = re.sub(r'\bE\b', 'EAST', addr)
        addr = re.sub(r'\bW\b', 'WEST', addr)
        addr = re.sub(r'\bN\b', 'NORTH', addr)
        addr = re.sub(r'\bS\b', 'SOUTH', addr)
        parts.append(addr)
    
    if unit and pd.notna(unit):
        parts.append(str(unit).upper().strip())
        if unit_number and pd.notna(unit_number):
            parts.append(str(unit_number).upper().strip())
    
    if city and pd.notna(city):
        parts.append(str(city).upper().strip())
    
    if state and pd.notna(state):
        parts.append(str(state).upper().strip())
    
    if zip_code and pd.notna(zip_code):
        # Only use first 5 digits of zip
        zip_str = str(zip_code).strip()[:5]
        if zip_str.isdigit():
            parts.append(zip_str)
    
    full_address = ' '.join(parts)
    # Remove extra spaces and non-alphanumeric characters
    full_address = re.sub(r'[^A-Z0-9\s]', '', full_address)
    full_address = re.sub(r'\s+', ' ', full_address).strip()
    return full_address

def parse_boolean(value):
    """Parse boolean values from the CSV."""
    if pd.isna(value):
        return None
    value_str = str(value).upper().strip()
    if value_str in ['TRUE', 'T', '1', 'YES', 'Y']:
        return True
    elif value_str in ['FALSE', 'F', '0', 'NO', 'N']:
        return False
    return None

def import_voters():
    """Main import function."""
    print(f"Starting VOTER import at {datetime.now()}")
    print("=" * 80)
    
    # Database connection
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    # Check existing voters
    cur.execute("SELECT COUNT(*) FROM voters")
    existing_count = cur.fetchone()[0]
    print(f"Existing voters: {existing_count:,}")
    
    # Load CSV file
    csv_path = Path(__file__).parent.parent / 'data' / 'Double Prime Kings County Reps.csv'
    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        return
    
    print(f"Loading voter CSV data from {csv_path}...")
    
    try:
        # Read CSV with proper encoding
        df = pd.read_csv(csv_path, encoding='utf-8', low_memory=False)
        print(f"Successfully loaded {len(df):,} records from CSV")
        
        # Process and insert records
        batch_size = 1000
        total_imported = 0
        duplicates = 0
        errors = 0
        
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            batch_records = []
            
            for _, row in batch.iterrows():
                try:
                    # Parse and normalize data
                    last_name = str(row['LastName']).strip() if pd.notna(row['LastName']) else None
                    first_name = str(row['FirstName']).strip() if pd.notna(row['FirstName']) else None
                    middle_name = str(row['MiddleName']).strip() if pd.notna(row['MiddleName']) else None
                    suffix_name = str(row['SuffixName']).strip() if pd.notna(row['SuffixName']) else None
                    
                    # Skip records without names
                    if not last_name and not first_name:
                        continue
                    
                    # Normalize name and address for matching
                    normalized_name = normalize_voter_name(first_name, last_name, middle_name, suffix_name)
                    
                    primary_address1 = str(row['PrimaryAddress1']).strip() if pd.notna(row['PrimaryAddress1']) else None
                    primary_city = str(row['PrimaryCity']).strip() if pd.notna(row['PrimaryCity']) else None
                    primary_state = str(row['PrimaryState']).strip() if pd.notna(row['PrimaryState']) else None
                    primary_zip = str(row['PrimaryZip']).strip() if pd.notna(row['PrimaryZip']) else None
                    primary_unit = str(row['PrimaryUnit']).strip() if pd.notna(row['PrimaryUnit']) else None
                    primary_unit_number = str(row['PrimaryUnitNumber']).strip() if pd.notna(row['PrimaryUnitNumber']) else None
                    
                    normalized_address = normalize_address(
                        primary_address1, primary_city, primary_state, primary_zip, 
                        primary_unit, primary_unit_number
                    )
                    
                    # Parse numeric fields
                    overall_frequency = None
                    if pd.notna(row['OverAllFrequency']):
                        try:
                            overall_frequency = int(row['OverAllFrequency'])
                        except (ValueError, TypeError):
                            overall_frequency = None
                    
                    # Parse boolean fields
                    moved = parse_boolean(row.get('Moved'))
                    landline_dnc = parse_boolean(row.get('LandlineDNC'))
                    mobile_dnc = parse_boolean(row.get('MobileDNC'))
                    
                    record = {
                        'id': str(uuid.uuid4()),
                        'last_name': last_name,
                        'first_name': first_name,
                        'middle_name': middle_name,
                        'suffix_name': suffix_name,
                        'primary_address1': primary_address1,
                        'primary_city': primary_city,
                        'primary_state': primary_state,
                        'primary_zip': primary_zip,
                        'primary_zip4': str(row['PrimaryZip4']).strip() if pd.notna(row['PrimaryZip4']) else None,
                        'primary_unit': primary_unit,
                        'primary_unit_number': primary_unit_number,
                        'gender': str(row['Gender']).strip() if pd.notna(row['Gender']) else None,
                        'observed_party': str(row['ObservedParty']).strip() if pd.notna(row['ObservedParty']) else None,
                        'official_party': str(row['OfficialParty']).strip() if pd.notna(row['OfficialParty']) else None,
                        'calculated_party': str(row['CalculatedParty']).strip() if pd.notna(row['CalculatedParty']) else None,
                        'household_party': str(row['HouseholdParty']).strip() if pd.notna(row['HouseholdParty']) else None,
                        'overall_frequency': overall_frequency,
                        'cd_name': str(row['CDName']).strip() if pd.notna(row['CDName']) else None,
                        'ld_name': str(row['LDName']).strip() if pd.notna(row['LDName']) else None,
                        'sd_name': str(row['SDName']).strip() if pd.notna(row['SDName']) else None,
                        'county_name': str(row['CountyName']).strip() if pd.notna(row['CountyName']) else None,
                        'precinct_number': str(row['PrecinctNumber']).strip() if pd.notna(row['PrecinctNumber']) else None,
                        'precinct_name': str(row['PrecinctName']).strip() if pd.notna(row['PrecinctName']) else None,
                        'voter_key': str(row['VoterKey']).strip() if pd.notna(row['VoterKey']) else None,
                        'hh_rec_id': str(row['HHRecId']).strip() if pd.notna(row['HHRecId']) else None,
                        'client_id': str(row['ClientId']).strip() if pd.notna(row['ClientId']) else None,
                        'state_voter_id': str(row['StateVoterId']).strip() if pd.notna(row['StateVoterId']) else None,
                        'hh_member_id': str(row['HHMemberId']).strip() if pd.notna(row['HHMemberId']) else None,
                        'hh_code': str(row['HHCode']).strip() if pd.notna(row['HHCode']) else None,
                        'rnc_reg_id': str(row['RNCRegId']).strip() if pd.notna(row['RNCRegId']) else None,
                        'moved': moved,
                        'landline': str(row['Landline']).strip() if pd.notna(row['Landline']) else None,
                        'mobile': str(row['Mobile']).strip() if pd.notna(row['Mobile']) else None,
                        'landline_trc': str(row['LandlineTRC']).strip() if pd.notna(row['LandlineTRC']) else None,
                        'landline_dnc': landline_dnc,
                        'mobile_trc': str(row['MobileTRC']).strip() if pd.notna(row['MobileTRC']) else None,
                        'mobile_dnc': mobile_dnc,
                        'normalized_name': normalized_name,
                        'normalized_address': normalized_address
                    }
                    
                    batch_records.append(record)
                    
                except Exception as e:
                    print(f"Error processing row {i + _}: {e}")
                    errors += 1
                    continue
            
            # Insert batch
            if batch_records:
                # Insert records individually with proper error handling
                for record in batch_records:
                    try:
                        cur.execute("""
                            INSERT INTO voters (
                                id, last_name, first_name, middle_name, suffix_name,
                                primary_address1, primary_city, primary_state, primary_zip, primary_zip4,
                                primary_unit, primary_unit_number, gender, observed_party, official_party,
                                calculated_party, household_party, overall_frequency, cd_name, ld_name,
                                sd_name, county_name, precinct_number, precinct_name, voter_key,
                                hh_rec_id, client_id, state_voter_id, hh_member_id, hh_code,
                                rnc_reg_id, moved, landline, mobile, landline_trc,
                                landline_dnc, mobile_trc, mobile_dnc, normalized_name, normalized_address
                            ) VALUES (
                                %(id)s, %(last_name)s, %(first_name)s, %(middle_name)s, %(suffix_name)s,
                                %(primary_address1)s, %(primary_city)s, %(primary_state)s, %(primary_zip)s, %(primary_zip4)s,
                                %(primary_unit)s, %(primary_unit_number)s, %(gender)s, %(observed_party)s, %(official_party)s,
                                %(calculated_party)s, %(household_party)s, %(overall_frequency)s, %(cd_name)s, %(ld_name)s,
                                %(sd_name)s, %(county_name)s, %(precinct_number)s, %(precinct_name)s, %(voter_key)s,
                                %(hh_rec_id)s, %(client_id)s, %(state_voter_id)s, %(hh_member_id)s, %(hh_code)s,
                                %(rnc_reg_id)s, %(moved)s, %(landline)s, %(mobile)s, %(landline_trc)s,
                                %(landline_dnc)s, %(mobile_trc)s, %(mobile_dnc)s, %(normalized_name)s, %(normalized_address)s
                            )
                            ON CONFLICT (state_voter_id) DO NOTHING
                        """, record)
                        
                        # Check if a row was inserted (not a duplicate)
                        if cur.rowcount > 0:
                            total_imported += 1
                        else:
                            duplicates += 1
                        
                        # Commit after each successful insert
                        conn.commit()
                        
                    except psycopg2.IntegrityError as e:
                        # Handle duplicates
                        conn.rollback()
                        duplicates += 1
                    except Exception as e:
                        # Handle other errors
                        conn.rollback()
                        print(f"Error inserting record (state_voter_id: {record.get('state_voter_id')}): {e}")
                        errors += 1
            
            # Progress update
            if (i + batch_size) % 5000 == 0:
                print(f"Processed {min(i + batch_size, len(df)):,} / {len(df):,} records...")
        
        print("\n" + "=" * 80)
        print(f"Import completed!")
        print(f"Total records processed: {len(df):,}")
        print(f"Successfully imported: {total_imported:,}")
        print(f"Duplicates skipped: {duplicates:,}")
        print(f"Errors: {errors:,}")
        
        # Final count
        cur.execute("SELECT COUNT(*) FROM voters")
        final_count = cur.fetchone()[0]
        print(f"Total voters in database: {final_count:,}")
        
        # Close connection
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error loading CSV: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import_voters()