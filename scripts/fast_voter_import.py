#!/usr/bin/env python3
"""Fast bulk voter import - optimized for speed."""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
import sys
from datetime import datetime
import time
import uuid
import re
from pathlib import Path

DATABASE_URL = os.environ.get('DATABASE_URL')

def normalize_name_fast(first, last, middle=None):
    """Fast name normalization."""
    parts = []
    if last and pd.notna(last):
        parts.append(str(last).upper().strip())
    if first and pd.notna(first):
        parts.append(str(first).upper().strip())
    if middle and pd.notna(middle):
        parts.append(str(middle).upper().strip())
    
    full = ' '.join(parts)
    # Quick cleanup
    full = re.sub(r'[^A-Z0-9\s]', '', full)
    full = re.sub(r'\s+', ' ', full)
    return full.strip()

def normalize_address_fast(addr, city, state, zip_code):
    """Fast address normalization."""
    parts = []
    if addr and pd.notna(addr):
        parts.append(str(addr).upper().strip())
    if city and pd.notna(city):
        parts.append(str(city).upper().strip())
    if state and pd.notna(state):
        parts.append(str(state).upper().strip()[:2])
    if zip_code and pd.notna(zip_code):
        parts.append(str(zip_code).strip()[:5])
    
    full = ' '.join(parts)
    full = re.sub(r'[^A-Z0-9\s]', '', full)
    full = re.sub(r'\s+', ' ', full)
    return full.strip()

def fast_voter_import(csv_file=None):
    """Ultra-fast bulk import of voter data."""
    start_time = time.time()
    print(f"\n{'='*80}")
    print(f"FAST VOTER IMPORT - Started at {datetime.now()}")
    print(f"{'='*80}")
    
    # Get CSV file
    if csv_file:
        csv_path = Path(csv_file)
    else:
        # Default to the file in data directory
        csv_path = Path('data/Double Prime Kings County Reps.csv')
    
    if not csv_path.exists():
        print(f"ERROR: CSV file not found at {csv_path}")
        print("\nUsage: python scripts/fast_voter_import.py [path/to/voter_file.csv]")
        print("Default: data/Double Prime Kings County Reps.csv")
        return
    
    print(f"Loading CSV from: {csv_path}")
    
    # Database connection
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Get current count
        cur.execute("SELECT COUNT(*) FROM voters")
        start_count = cur.fetchone()[0]
        print(f"Current voters in database: {start_count:,}")
        
        # Load CSV
        df = pd.read_csv(csv_path, encoding='utf-8', low_memory=False)
        print(f"CSV records loaded: {len(df):,}")
        
        # Get existing voter IDs to avoid duplicates
        cur.execute("SELECT state_voter_id FROM voters WHERE state_voter_id IS NOT NULL")
        existing_ids = set(row[0] for row in cur.fetchall())
        print(f"Existing voter IDs: {len(existing_ids):,}")
        
        # Filter to new records only
        df['StateVoterId'] = df['StateVoterId'].astype(str)
        df_new = df[~df['StateVoterId'].isin(existing_ids)].copy()
        print(f"New records to import: {len(df_new):,}")
        
        if len(df_new) == 0:
            print("No new records to import!")
            return
        
        # Prepare data with vectorized operations
        print("Preparing data...")
        
        # Generate UUIDs for all records
        df_new['id'] = [str(uuid.uuid4()) for _ in range(len(df_new))]
        
        # Normalize names and addresses in bulk
        df_new['normalized_name'] = df_new.apply(
            lambda r: normalize_name_fast(r['FirstName'], r['LastName'], r.get('MiddleName')), 
            axis=1
        )
        
        df_new['normalized_address'] = df_new.apply(
            lambda r: normalize_address_fast(
                r.get('PrimaryAddress1'), 
                r.get('PrimaryCity'), 
                r.get('PrimaryState'), 
                r.get('PrimaryZip')
            ), 
            axis=1
        )
        
        # Convert boolean fields
        bool_fields = ['Moved', 'LandlineDNC', 'MobileDNC']
        for field in bool_fields:
            if field in df_new.columns:
                df_new[field] = df_new[field].map({
                    'TRUE': True, 'FALSE': False, 
                    'T': True, 'F': False,
                    '1': True, '0': False,
                    True: True, False: False
                })
                # Replace NaN with None for proper NULL handling
                df_new[field] = df_new[field].where(pd.notna(df_new[field]), None)
        
        # Convert numeric fields
        if 'OverAllFrequency' in df_new.columns:
            df_new['OverAllFrequency'] = pd.to_numeric(df_new['OverAllFrequency'], errors='coerce')
        
        # Prepare records for bulk insert
        print("Preparing bulk insert...")
        records = []
        
        for _, row in df_new.iterrows():
            record = (
                row['id'],
                row.get('LastName'),
                row.get('FirstName'),
                row.get('MiddleName'),
                row.get('SuffixName'),
                row.get('PrimaryAddress1'),
                row.get('PrimaryCity'),
                row.get('PrimaryState'),
                str(row.get('PrimaryZip'))[:10] if pd.notna(row.get('PrimaryZip')) else None,
                str(row.get('PrimaryZip4'))[:10] if pd.notna(row.get('PrimaryZip4')) else None,
                row.get('PrimaryUnit'),
                row.get('PrimaryUnitNumber'),
                row.get('Gender'),
                row.get('ObservedParty'),
                row.get('OfficialParty'),
                row.get('CalculatedParty'),
                row.get('HouseholdParty'),
                int(row['OverAllFrequency']) if pd.notna(row.get('OverAllFrequency')) else None,
                row.get('CDName'),
                row.get('LDName'),
                row.get('SDName'),
                row.get('CountyName'),
                row.get('PrecinctNumber'),
                row.get('PrecinctName'),
                row.get('VoterKey'),
                row.get('HHRecId'),
                row.get('ClientId'),
                row.get('StateVoterId'),
                row.get('HHMemberId'),
                row.get('HHCode'),
                row.get('RNCRegId'),
                row.get('Moved'),
                row.get('Landline'),
                row.get('Mobile'),
                row.get('LandlineTRC'),
                row.get('LandlineDNC'),
                row.get('MobileTRC'),
                row.get('MobileDNC'),
                row['normalized_name'],
                row['normalized_address']
            )
            records.append(record)
        
        # Bulk insert using execute_values
        batch_size = 5000
        total_batches = (len(records) + batch_size - 1) // batch_size
        
        print(f"\nInserting {len(records):,} records in {total_batches} batches...")
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            batch_num = i // batch_size + 1
            
            execute_values(cur, """
                INSERT INTO voters (
                    id, last_name, first_name, middle_name, suffix_name,
                    primary_address1, primary_city, primary_state, primary_zip, primary_zip4,
                    primary_unit, primary_unit_number, gender, observed_party, official_party,
                    calculated_party, household_party, overall_frequency, cd_name, ld_name,
                    sd_name, county_name, precinct_number, precinct_name, voter_key,
                    hh_rec_id, client_id, state_voter_id, hh_member_id, hh_code,
                    rnc_reg_id, moved, landline, mobile, landline_trc,
                    landline_dnc, mobile_trc, mobile_dnc, normalized_name, normalized_address
                ) VALUES %s
                ON CONFLICT (state_voter_id) DO NOTHING
            """, batch, page_size=1000)
            
            # Progress update
            if batch_num % 2 == 0 or batch_num == total_batches:
                elapsed = time.time() - start_time
                rate = (i + len(batch)) / elapsed
                remaining = (len(records) - (i + len(batch))) / rate if rate > 0 else 0
                print(f"  Batch {batch_num}/{total_batches}: {i+len(batch):,}/{len(records):,} records "
                      f"({rate:.0f} rec/sec, {remaining:.0f}s remaining)")
        
        # Commit all changes
        conn.commit()
        
        # Get final count
        cur.execute("SELECT COUNT(*) FROM voters")
        final_count = cur.fetchone()[0]
        
        # Summary
        elapsed_time = time.time() - start_time
        imported = final_count - start_count
        
        print(f"\n{'='*80}")
        print(f"IMPORT COMPLETED SUCCESSFULLY")
        print(f"{'='*80}")
        print(f"Time taken: {elapsed_time:.1f} seconds")
        print(f"Records imported: {imported:,}")
        print(f"Import rate: {imported/elapsed_time:.0f} records/second")
        print(f"Total voters in database: {final_count:,}")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    # Accept CSV file path from command line
    csv_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print("Fast Voter Import Script")
        print("\nUsage:")
        print("  python scripts/fast_voter_import.py [csv_file_path]")
        print("\nExamples:")
        print("  python scripts/fast_voter_import.py")
        print("  python scripts/fast_voter_import.py data/voters.csv")
        print("  python scripts/fast_voter_import.py /path/to/voter_file.csv")
        print("\nDefault file: data/Double Prime Kings County Reps.csv")
        sys.exit(0)
    
    fast_voter_import(csv_file)