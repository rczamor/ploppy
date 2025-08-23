#!/usr/bin/env python3
"""Ultra-fast unified contributor import script for NYC Campaign Finance data."""

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
import pandas as pd
import os
import re
import time
from datetime import datetime
from decimal import Decimal
import uuid
import hashlib

try:
    from replit.object_storage import Client
    client = Client()
    USE_OBJECT_STORAGE = True
except ImportError:
    USE_OBJECT_STORAGE = False
    print("Object storage not available, will look for local files")

DATABASE_URL = os.environ.get('DATABASE_URL')

# Organization type indicators
ORG_INDICATORS = {
    'c_codes': ['CORP', 'LLC', 'LLP', 'PART', 'OTHR', 'UNKN'],
    'suffixes': ['LLC', 'INC', 'CORP', 'LTD', 'LP', 'LLP', 'PLLC', 'PC', 'PA', 'ASSOC', 
                 'ASSOCIATES', 'COMPANY', 'CO', 'CORPORATION', 'INCORPORATED', 'LIMITED',
                 'PARTNERSHIP', 'GROUP', 'FOUNDATION', 'TRUST', 'FUND', 'UNION', 'COMMITTEE'],
    'keywords': ['UNION', 'LOCAL', 'DISTRICT', 'COUNCIL', 'COMMITTEE', 'PAC', 'ASSOCIATION',
                 'SOCIETY', 'INSTITUTE', 'CENTER', 'CLUB', 'LEAGUE', 'ALLIANCE', 'COALITION']
}

def is_organization(full_name, c_code):
    """Determine if a contributor is an organization."""
    if not full_name:
        return False
    
    # Check C_CODE first
    if c_code in ORG_INDICATORS['c_codes']:
        return True
    
    # Check for organization suffixes and keywords
    name_upper = full_name.upper()
    
    # Check suffixes
    for suffix in ORG_INDICATORS['suffixes']:
        if name_upper.endswith(' ' + suffix) or name_upper.endswith(' ' + suffix + '.'):
            return True
    
    # Check keywords
    for keyword in ORG_INDICATORS['keywords']:
        if keyword in name_upper:
            return True
    
    # Check for patterns like "# Local" or "District #"
    if re.search(r'(LOCAL|DISTRICT)\s*#?\d+', name_upper):
        return True
    
    return False

def parse_individual_name(full_name):
    """Parse individual full name into components."""
    if not full_name:
        return None, None, None
    
    # Clean the name
    full_name = full_name.strip()
    full_name = re.sub(r'^["\'"]+|["\'"]+$', '', full_name)
    
    # Check if it's in "LAST, FIRST [MIDDLE]" format
    if ',' in full_name:
        parts = full_name.split(',', 1)
        last_name = parts[0].strip()
        
        if len(parts) > 1:
            # Split first and middle names
            first_parts = parts[1].strip().split(None, 1)
            first_name = first_parts[0] if first_parts else ''
            middle_name = first_parts[1] if len(first_parts) > 1 else ''
            middle_initial = middle_name[0] if middle_name else ''
        else:
            first_name = ''
            middle_initial = ''
    else:
        # Try to parse "FIRST [MIDDLE] LAST" format
        parts = full_name.split()
        if len(parts) == 1:
            last_name = parts[0]
            first_name = ''
            middle_initial = ''
        elif len(parts) == 2:
            first_name = parts[0]
            last_name = parts[1]
            middle_initial = ''
        else:
            first_name = parts[0]
            last_name = parts[-1]
            middle_parts = parts[1:-1]
            middle_initial = middle_parts[0][0] if middle_parts else ''
    
    # Title case
    last_name = last_name.title() if last_name else ''
    first_name = first_name.title() if first_name else ''
    middle_initial = middle_initial.upper() if middle_initial else ''
    
    return last_name, first_name, middle_initial

def normalize_text(text):
    """Normalize text for comparison."""
    if pd.isna(text) or text is None:
        return ''
    return str(text).strip().upper()

def get_or_create_entity(cur, table, fields, values, return_field='id'):
    """Get or create an entity in the database."""
    # Build the WHERE clause for checking existence
    where_clauses = []
    where_values = []
    for field, value in zip(fields, values):
        if value is None or (isinstance(value, str) and value == ''):
            where_clauses.append(f"({field} IS NULL OR {field} = '')")
        else:
            where_clauses.append(f"{field} = %s")
            where_values.append(value)
    
    # Try to find existing record
    select_query = f"""
        SELECT {return_field} FROM {table} 
        WHERE {' AND '.join(where_clauses)}
        LIMIT 1
    """
    cur.execute(select_query, where_values)
    result = cur.fetchone()
    
    if result:
        return result[0]
    
    # Create new record
    field_names = ', '.join(fields)
    placeholders = ', '.join(['%s'] * len(values))
    insert_query = f"""
        INSERT INTO {table} ({field_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
        RETURNING {return_field}
    """
    cur.execute(insert_query, values)
    result = cur.fetchone()
    
    if result:
        return result[0]
    
    # If insert failed due to race condition, try select again
    cur.execute(select_query, where_values)
    result = cur.fetchone()
    return result[0] if result else None

def import_contributions():
    """Main import function."""
    print(f"\n{'='*80}")
    print(f"FAST CONTRIBUTOR IMPORT - Started at {datetime.now()}")
    print(f"{'='*80}\n")
    
    # Download and load CSV
    filename = 'CFB_contributions-2025-08-23.csv'
    
    if USE_OBJECT_STORAGE:
        print(f"Downloading {filename} from object storage...")
        try:
            data = client.download_as_text(filename)
            # Save to temp file for pandas
            temp_file = f'/tmp/{filename}'
            with open(temp_file, 'w') as f:
                f.write(data)
            df = pd.read_csv(temp_file, low_memory=False)
            os.remove(temp_file)
        except Exception as e:
            print(f"Error downloading from object storage: {e}")
            print("Trying local file...")
            df = pd.read_csv(f'data/{filename}', low_memory=False)
    else:
        print(f"Loading {filename} from local data directory...")
        df = pd.read_csv(f'data/{filename}', low_memory=False)
    
    print(f"Loaded {len(df):,} records from CSV")
    
    # All records in this file are contributions
    print(f"Processing {len(df):,} contribution records")
    
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Get existing REFNOs to avoid duplicates
        print("\nChecking for existing contributions...")
        cur.execute("SELECT DISTINCT refno FROM contributions WHERE refno IS NOT NULL")
        existing_refnos = {row[0] for row in cur.fetchall()}
        print(f"Found {len(existing_refnos):,} existing contributions")
        
        # Filter out existing contributions
        df['REFNO_STR'] = df['REFNO'].astype(str)
        df = df[~df['REFNO_STR'].isin(existing_refnos)]
        print(f"New contributions to import: {len(df):,}")
        
        if len(df) == 0:
            print("No new contributions to import!")
            return
        
        # Prepare batch processing
        batch_size = 5000
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        # Track entities for caching
        elections_cache = {}
        recipients_cache = {}
        employers_cache = {}
        contributors_cache = {}
        org_contributors_cache = {}
        
        contributions_to_insert = []
        total_amount = Decimal('0')
        
        print(f"\nProcessing {total_batches} batches of {batch_size} records...")
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df))
            batch_df = df.iloc[start_idx:end_idx]
            
            for _, row in batch_df.iterrows():
                # Parse election
                election_key = normalize_text(row.get('ELECTION'))
                if election_key and election_key not in elections_cache:
                    election_id = get_or_create_entity(
                        cur, 'elections',
                        ['election_cycle'],
                        [election_key]
                    )
                    elections_cache[election_key] = election_id
                election_id = elections_cache.get(election_key)
                
                # Parse recipient
                recipient_key = normalize_text(row.get('RECIPNAME'))
                recip_id_value = str(row.get('RECIPID', ''))
                if recipient_key and recipient_key not in recipients_cache:
                    recipient_id = get_or_create_entity(
                        cur, 'recipients',
                        ['full_name', 'recipid'],
                        [recipient_key, recip_id_value if recip_id_value else '0']
                    )
                    recipients_cache[recipient_key] = recipient_id
                recipient_id = recipients_cache.get(recipient_key)
                
                # Parse employer
                employer_key = normalize_text(row.get('EMPNAME'))
                if employer_key and employer_key not in employers_cache:
                    employer_id = get_or_create_entity(
                        cur, 'employers',
                        ['name'],
                        [employer_key]
                    )
                    employers_cache[employer_key] = employer_id
                employer_id = employers_cache.get(employer_key)
                
                # Parse contributor - use NAME if available, otherwise use EMPNAME
                contrib_name = normalize_text(row.get('NAME'))
                if not contrib_name:
                    contrib_name = normalize_text(row.get('EMPNAME'))
                c_code = normalize_text(row.get('C_CODE'))
                
                # Extract location info
                city = normalize_text(row.get('CITY'))
                state = normalize_text(row.get('STATE'))
                zip_code = str(row.get('ZIP', ''))[:10] if pd.notna(row.get('ZIP')) else ''
                
                if contrib_name:
                    # Determine if organization or individual
                    is_org = is_organization(contrib_name, c_code)
                    
                    if is_org:
                        # Handle as organization
                        cache_key = f"{contrib_name}|{city}|{state}|{zip_code}"
                        if cache_key not in org_contributors_cache:
                            # Check if exists in database
                            cur.execute("""
                                SELECT id FROM org_contributors 
                                WHERE normalized_name = %s
                                LIMIT 1
                            """, (contrib_name,))
                            result = cur.fetchone()
                            
                            if result:
                                org_id = result[0]
                                # Update location if not set
                                cur.execute("""
                                    UPDATE org_contributors
                                    SET city = COALESCE(city, %s),
                                        state = COALESCE(state, %s),
                                        zip_code = COALESCE(zip_code, %s)
                                    WHERE id = %s AND city IS NULL
                                """, (city, state, zip_code, org_id))
                            else:
                                # Create new org
                                org_id = str(uuid.uuid4())
                                cur.execute("""
                                    INSERT INTO org_contributors 
                                    (id, full_name, normalized_name, organization_type, c_code, 
                                     city, state, zip_code)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                    ON CONFLICT DO NOTHING
                                    RETURNING id
                                """, (org_id, contrib_name, contrib_name, 
                                      row.get('RECIPTYPE'), c_code, city, state, zip_code))
                                
                                result = cur.fetchone()
                                if not result:
                                    # Race condition, get existing
                                    cur.execute("""
                                        SELECT id FROM org_contributors 
                                        WHERE normalized_name = %s
                                        LIMIT 1
                                    """, (contrib_name,))
                                    result = cur.fetchone()
                                    org_id = result[0]
                            
                            org_contributors_cache[cache_key] = org_id
                        
                        org_contributor_id = org_contributors_cache[cache_key]
                        contributor_id = None
                    else:
                        # Handle as individual
                        cache_key = f"{contrib_name}|{city}|{state}|{zip_code}"
                        if cache_key not in contributors_cache:
                            # Parse name
                            last_name, first_name, middle_initial = parse_individual_name(contrib_name)
                            
                            # Check if exists in database
                            cur.execute("""
                                SELECT id FROM contributors 
                                WHERE normalized_name = %s
                                AND is_individual = true
                                LIMIT 1
                            """, (contrib_name,))
                            result = cur.fetchone()
                            
                            if result:
                                contrib_id = result[0]
                                # Update parsed name and location if not set
                                cur.execute("""
                                    UPDATE contributors
                                    SET first_name = COALESCE(first_name, %s),
                                        last_name = COALESCE(last_name, %s),
                                        middle_initial = COALESCE(middle_initial, %s),
                                        city = COALESCE(city, %s),
                                        state = COALESCE(state, %s),
                                        zip_code = COALESCE(zip_code, %s)
                                    WHERE id = %s AND (first_name IS NULL OR city IS NULL)
                                """, (first_name, last_name, middle_initial, 
                                      city, state, zip_code, contrib_id))
                            else:
                                # Create new contributor
                                contrib_id = str(uuid.uuid4())
                                cur.execute("""
                                    INSERT INTO contributors 
                                    (id, full_name, normalized_name, first_name, last_name, 
                                     middle_initial, is_individual, contributor_type, c_code,
                                     city, state, zip_code)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    ON CONFLICT DO NOTHING
                                    RETURNING id
                                """, (contrib_id, contrib_name, contrib_name, first_name, 
                                      last_name, middle_initial, True, 'Individual', c_code,
                                      city, state, zip_code))
                                
                                result = cur.fetchone()
                                if not result:
                                    # Race condition, get existing
                                    cur.execute("""
                                        SELECT id FROM contributors 
                                        WHERE normalized_name = %s
                                        AND is_individual = true
                                        LIMIT 1
                                    """, (contrib_name,))
                                    result = cur.fetchone()
                                    contrib_id = result[0]
                            
                            contributors_cache[cache_key] = contrib_id
                        
                        contributor_id = contributors_cache[cache_key]
                        org_contributor_id = None
                else:
                    contributor_id = None
                    org_contributor_id = None
                
                # Prepare contribution record
                amount = Decimal(str(row.get('AMNT', 0)))
                total_amount += amount
                
                contributions_to_insert.append((
                    str(uuid.uuid4()),  # id
                    contributor_id,
                    org_contributor_id,
                    election_id,
                    recipient_id,
                    employer_id,
                    amount,
                    pd.to_datetime(row.get('DATE'), errors='coerce'),
                    row.get('OCCUPATION'),
                    row.get('RECIPID'),
                    row.get('STRNO'),
                    row.get('STRNAME'),
                    city,  # contributor_city
                    state,  # contributor_state
                    zip_code,  # contributor_zip
                    row.get('BOROUGHCD'),
                    row.get('REFNO'),
                    row.get('SCHEDULE'),
                    row.get('PAGENO'),
                    row.get('SEQUENCENO'),
                    datetime.now(),  # created_at
                    datetime.now()   # updated_at
                ))
            
            # Insert batch of contributions
            if contributions_to_insert and len(contributions_to_insert) >= batch_size:
                execute_values(cur, """
                    INSERT INTO contributions 
                    (id, contributor_id, org_contributor_id, election_id, recipient_id, 
                     employer_id, amount, date, occupation, recip_id, str_no, str_name,
                     contributor_city, contributor_state, contributor_zip,
                     borough_code, refno, schedule, page_no, sequence_no, 
                     created_at, updated_at)
                    VALUES %s
                    ON CONFLICT (refno) DO NOTHING
                """, contributions_to_insert, page_size=1000)
                
                conn.commit()
                print(f"  Batch {batch_num + 1}/{total_batches}: Inserted {len(contributions_to_insert):,} contributions")
                contributions_to_insert = []
        
        # Insert remaining contributions
        if contributions_to_insert:
            execute_values(cur, """
                INSERT INTO contributions 
                (id, contributor_id, org_contributor_id, election_id, recipient_id, 
                 employer_id, amount, date, occupation, recip_id, str_no, str_name,
                 contributor_city, contributor_state, contributor_zip,
                 borough_code, refno, schedule, page_no, sequence_no, 
                 created_at, updated_at)
                VALUES %s
                ON CONFLICT (refno) DO NOTHING
            """, contributions_to_insert, page_size=1000)
            
            conn.commit()
            print(f"  Final batch: Inserted {len(contributions_to_insert):,} contributions")
        
        # Get final statistics
        cur.execute("SELECT COUNT(*), SUM(amount) FROM contributions")
        final_count, final_total = cur.fetchone()
        
        print(f"\n{'='*80}")
        print("IMPORT COMPLETE")
        print(f"{'='*80}")
        print(f"\nFinal Statistics:")
        print(f"  Total Records: {final_count:,}")
        print(f"  Total Contributions: ${final_total:,.2f}")
        print(f"\nTarget:")
        print(f"  Total Records: 2,043,325")
        print(f"  Total Contributions: $700,074,925.40")
        
        # Entity counts
        cur.execute("SELECT COUNT(*) FROM contributors WHERE is_individual = true")
        individual_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM org_contributors")
        org_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM elections")
        election_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM recipients")
        recipient_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM employers")
        employer_count = cur.fetchone()[0]
        
        print(f"\nEntity Counts:")
        print(f"  Individual Contributors: {individual_count:,}")
        print(f"  Organization Contributors: {org_count:,}")
        print(f"  Elections: {election_count:,}")
        print(f"  Recipients: {recipient_count:,}")
        print(f"  Employers: {employer_count:,}")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    import_contributions()