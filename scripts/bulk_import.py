"""Ultra-fast bulk import using direct SQL operations."""

import pandas as pd
from sqlalchemy import create_engine, text
import os
from datetime import datetime
import time
import uuid

DATABASE_URL = os.environ.get('DATABASE_URL')

def create_temp_tables(engine):
    """Create temporary staging tables for bulk operations."""
    with engine.connect() as conn:
        # Drop existing temp tables
        conn.execute(text("DROP TABLE IF EXISTS temp_contributors CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS temp_recipients CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS temp_contributions CASCADE"))
        
        # Create temp tables with simpler structure
        conn.execute(text("""
            CREATE TABLE temp_contributors (
                id UUID PRIMARY KEY,
                full_name TEXT,
                normalized_name TEXT,
                c_code VARCHAR(10)
            )
        """))
        
        conn.execute(text("""
            CREATE TABLE temp_recipients (
                id UUID PRIMARY KEY,
                recipid VARCHAR(50),
                full_name TEXT,
                normalized_name TEXT
            )
        """))
        
        conn.execute(text("""
            CREATE TABLE temp_contributions (
                reference_number VARCHAR(50),
                contributor_name TEXT,
                recipient_id VARCHAR(50),
                recipient_name TEXT,
                amount DECIMAL(12,2),
                transaction_date DATE,
                election_year INTEGER
            )
        """))
        conn.commit()

def bulk_load_data():
    """Load data in bulk using PostgreSQL COPY command."""
    print(f"Starting ultra-fast bulk import at {datetime.now()}")
    print("=" * 80)
    
    engine = create_engine(DATABASE_URL)
    
    # Check current state
    with engine.connect() as conn:
        current_count = conn.execute(text("SELECT COUNT(*) FROM contributions")).scalar()
        print(f"Current contributions: {current_count:,}")
    
    # Load CSV
    print("\nLoading CSV data...")
    from db_manager_v2 import NYCCFBDatabase
    db = NYCCFBDatabase()
    db.connect_to_object_storage('')
    df = db.download_csv_to_dataframe('CFB_20250718173623479.csv')
    
    print(f"Total records in CSV: {len(df):,}")
    
    # Clean column names
    df.columns = df.columns.str.strip()
    
    # Prepare data
    print("\nPreparing data for bulk import...")
    
    # Handle null names
    df['NAME'] = df['NAME'].fillna('Anonymous Contributor')
    df['RECIPNAME'] = df['RECIPNAME'].fillna('Unknown Recipient')
    
    # Create normalized names
    df['CONTRIBUTOR_NORM'] = df['NAME'].str.upper().str.replace(r'[^A-Z0-9\s]', '', regex=True)
    df['RECIPIENT_NORM'] = df['RECIPNAME'].str.upper().str.replace(r'[^A-Z0-9\s]', '', regex=True)
    
    # Convert dates
    df['TRANS_DATE'] = pd.to_datetime(df['DATE'], errors='coerce')
    df['ELECTION_YEAR'] = pd.to_numeric(df['ELECTION'], errors='coerce')
    
    # Filter out already imported records
    if current_count > 0:
        print(f"\nChecking for already imported records...")
        with engine.connect() as conn:
            imported_refs = pd.read_sql_query(
                "SELECT DISTINCT reference_number FROM contributions", 
                conn
            )
            imported_set = set(imported_refs['reference_number'])
            df_new = df[~df['REFNO'].isin(imported_set)]
            print(f"New records to import: {len(df_new):,}")
    else:
        df_new = df
    
    if len(df_new) == 0:
        print("No new records to import!")
        return
    
    # Create temp tables
    create_temp_tables(engine)
    
    # Bulk insert into temp tables
    print("\nPerforming bulk insert...")
    start_time = time.time()
    
    # Insert unique contributors
    print("  - Extracting unique contributors...")
    contributors_df = df_new[['NAME', 'CONTRIBUTOR_NORM', 'C_CODE']].drop_duplicates(subset=['CONTRIBUTOR_NORM'])
    contributors_df['id'] = [str(uuid.uuid4()) for _ in range(len(contributors_df))]
    contributors_df.columns = ['full_name', 'normalized_name', 'c_code', 'id']
    
    print(f"    Found {len(contributors_df):,} unique contributors")
    contributors_df.to_sql('temp_contributors', engine, if_exists='append', index=False, method='multi')
    
    # Insert unique recipients
    print("  - Extracting unique recipients...")
    recipients_df = df_new[['RECIPID', 'RECIPNAME', 'RECIPIENT_NORM']].drop_duplicates(subset=['RECIPID'])
    recipients_df['id'] = [str(uuid.uuid4()) for _ in range(len(recipients_df))]
    recipients_df.columns = ['recipid', 'full_name', 'normalized_name', 'id']
    
    print(f"    Found {len(recipients_df):,} unique recipients")
    recipients_df.to_sql('temp_recipients', engine, if_exists='append', index=False, method='multi')
    
    # Prepare contributions for bulk insert
    print("  - Preparing contributions...")
    contributions_df = df_new[[
        'REFNO', 'NAME', 'RECIPID', 'RECIPNAME', 
        'AMNT', 'TRANS_DATE', 'ELECTION_YEAR'
    ]].copy()
    contributions_df.columns = [
        'reference_number', 'contributor_name', 'recipient_id', 
        'recipient_name', 'amount', 'transaction_date', 'election_year'
    ]
    
    # Insert in chunks
    chunk_size = 50000
    total_chunks = (len(contributions_df) + chunk_size - 1) // chunk_size
    
    print(f"  - Inserting {len(contributions_df):,} contributions in {total_chunks} chunks...")
    
    for i in range(min(10, total_chunks)):  # Process up to 10 chunks (500k records)
        chunk_start = i * chunk_size
        chunk_end = min((i + 1) * chunk_size, len(contributions_df))
        chunk = contributions_df.iloc[chunk_start:chunk_end]
        
        chunk.to_sql('temp_contributions', engine, if_exists='append', index=False, method='multi')
        print(f"    Chunk {i+1}/{min(10, total_chunks)} inserted ({chunk_end:,} records)")
    
    # Now do the final merge
    print("\nMerging data into main tables...")
    with engine.connect() as conn:
        # Merge contributors (skip duplicates without ON CONFLICT)
        conn.execute(text("""
            INSERT INTO contributors (id, full_name, normalized_name, c_code, contributor_type, is_individual)
            SELECT 
                tc.id, 
                tc.full_name, 
                tc.normalized_name, 
                tc.c_code,
                CASE 
                    WHEN tc.c_code = 'UNKN' THEN 'Unknown'
                    WHEN tc.c_code = 'CORP' THEN 'Corporation'
                    WHEN tc.c_code = 'IND' THEN 'Individual'
                    ELSE 'Other'
                END,
                tc.c_code = 'IND'
            FROM temp_contributors tc
            WHERE NOT EXISTS (
                SELECT 1 FROM contributors c 
                WHERE c.normalized_name = tc.normalized_name
            )
        """))
        
        # Merge recipients (skip duplicates without ON CONFLICT)
        conn.execute(text("""
            INSERT INTO recipients (id, recipid, full_name, normalized_name, recipient_type, is_individual)
            SELECT 
                tr.id,
                tr.recipid,
                tr.full_name,
                tr.normalized_name,
                'Candidate',
                true
            FROM temp_recipients tr
            WHERE NOT EXISTS (
                SELECT 1 FROM recipients r 
                WHERE r.recipid = tr.recipid
            )
        """))
        
        # Get default election
        election_id = conn.execute(text(
            "SELECT id FROM elections ORDER BY election_year DESC LIMIT 1"
        )).scalar()
        
        if not election_id:
            election_id = str(uuid.uuid4())
            conn.execute(text("""
                INSERT INTO elections (id, election_year, election_type)
                VALUES (:id, 2025, 'General')
            """), {'id': election_id})
        
        # Insert contributions with joins to get IDs
        print("  - Inserting contributions with proper foreign keys...")
        conn.execute(text(f"""
            INSERT INTO contributions (
                id, reference_number, election_id, contributor_id, recipient_id,
                amount, transaction_date, payment_method
            )
            SELECT 
                gen_random_uuid(),
                tc.reference_number,
                '{election_id}',
                COALESCE(c.id, (SELECT id FROM contributors WHERE full_name = 'Anonymous Contributor' LIMIT 1)),
                COALESCE(r.id, (SELECT id FROM recipients LIMIT 1)),
                tc.amount,
                tc.transaction_date,
                1
            FROM temp_contributions tc
            LEFT JOIN contributors c ON c.normalized_name = UPPER(REGEXP_REPLACE(tc.contributor_name, '[^A-Z0-9\\s]', '', 'g'))
            LEFT JOIN recipients r ON r.recipid = tc.recipient_id
            WHERE tc.amount IS NOT NULL
            AND tc.reference_number NOT IN (SELECT reference_number FROM contributions)
        """))
        
        conn.commit()
    
    # Clean up temp tables
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS temp_contributors CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS temp_recipients CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS temp_contributions CASCADE"))
        conn.commit()
    
    # Report results
    elapsed = time.time() - start_time
    with engine.connect() as conn:
        new_count = conn.execute(text("SELECT COUNT(*) FROM contributions")).scalar()
        imported = new_count - current_count
    
    print("\n" + "=" * 80)
    print(f"Bulk import completed in {elapsed:.1f} seconds")
    print(f"Imported {imported:,} new contributions")
    print(f"Rate: {imported/elapsed:.0f} records/second")
    print(f"Total contributions now: {new_count:,}")
    
    if new_count < len(df):
        print(f"\nRun again to import remaining {len(df) - new_count:,} records")

if __name__ == "__main__":
    bulk_load_data()