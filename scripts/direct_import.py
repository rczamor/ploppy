"""Direct import - simple and fast."""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
import time
import uuid
import hashlib

DATABASE_URL = os.environ.get('DATABASE_URL')

def create_unique_key(row):
    """Create unique key for each contribution."""
    key = f"{row['REFNO']}_{row['NAME']}_{row['AMNT']}_{row['DATE']}"
    return hashlib.md5(key.encode()).hexdigest()

def direct_import():
    """Import all data directly without complex tracking."""
    print(f"\nStarting DIRECT import at {datetime.now()}")
    print("=" * 80)
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    # Get count
    cur.execute("SELECT COUNT(*) FROM contributions")
    start_count = cur.fetchone()[0]
    print(f"Starting with {start_count:,} contributions")
    
    # Target: 1,637,022 total records
    target = 1637022
    if start_count >= target:
        print("Already at target!")
        return
    
    # Load CSV
    print("\nLoading CSV data...")
    import sys
    sys.path.append('..')
    from src.database.db_manager_v2 import NYCCFBDatabase
    db = NYCCFBDatabase()
    db.connect_to_object_storage('')
    df = db.download_csv_to_dataframe('CFB_20250718173623479.csv')
    df.columns = df.columns.str.strip()
    
    print(f"Total CSV records: {len(df):,}")
    
    # Create unique keys
    print("Creating unique keys...")
    df['UNIQUE_KEY'] = df.apply(create_unique_key, axis=1)
    
    # Get existing keys
    print("Loading existing contribution keys...")
    cur.execute("""
        SELECT 
            MD5(CONCAT(reference_number, '_', 
                      COALESCE((SELECT full_name FROM contributors WHERE id = contributor_id), ''), '_',
                      COALESCE(amount::text, '0'), '_',
                      COALESCE(transaction_date::text, '')))
        FROM contributions
    """)
    existing_keys = set(row[0] for row in cur.fetchall())
    print(f"Found {len(existing_keys):,} existing contribution keys")
    
    # Filter to new records
    df_new = df[~df['UNIQUE_KEY'].isin(existing_keys)].copy()
    print(f"New records to import: {len(df_new):,}")
    
    if len(df_new) == 0:
        print("No new records!")
        return
    
    # Prepare data
    df_new['NAME'] = df_new['NAME'].fillna('Anonymous Contributor')
    df_new['RECIPNAME'] = df_new['RECIPNAME'].fillna('Unknown Recipient')
    df_new['TRANS_DATE'] = pd.to_datetime(df_new['DATE'], errors='coerce')
    df_new['AMOUNT_NUM'] = pd.to_numeric(df_new['AMNT'], errors='coerce').fillna(0)
    
    # Get default election
    cur.execute("SELECT id FROM elections LIMIT 1")
    election_id = cur.fetchone()
    if not election_id:
        election_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO elections (id, election_year, election_type)
            VALUES (%s, 2025, 'General')
        """, (election_id,))
    else:
        election_id = election_id[0]
    
    # Cache all contributors and recipients
    print("Loading contributor/recipient cache...")
    cur.execute("SELECT normalized_name, id FROM contributors")
    contrib_cache = dict(cur.fetchall())
    
    cur.execute("SELECT recipid, id FROM recipients")
    recip_cache = dict(cur.fetchall())
    
    # Process in batches
    batch_size = 25000
    total_batches = (len(df_new) + batch_size - 1) // batch_size
    total_imported = 0
    start_time = time.time()
    
    print(f"\nProcessing {total_batches} batches...")
    
    for batch_num in range(total_batches):
        batch_start = time.time()
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(df_new))
        
        batch_df = df_new.iloc[start_idx:end_idx]
        
        # Collect new contributors/recipients
        new_contribs = {}
        new_recips = {}
        
        for _, row in batch_df.iterrows():
            norm_name = str(row['NAME']).upper().strip()
            if norm_name not in contrib_cache and norm_name not in new_contribs:
                new_id = str(uuid.uuid4())
                new_contribs[norm_name] = (new_id, row['NAME'])
                contrib_cache[norm_name] = new_id
            
            if row['RECIPID'] not in recip_cache and row['RECIPID'] not in new_recips:
                new_id = str(uuid.uuid4())
                new_recips[row['RECIPID']] = (new_id, row['RECIPNAME'])
                recip_cache[row['RECIPID']] = new_id
        
        # Bulk insert new contributors
        if new_contribs:
            contrib_data = [(v[0], v[1], k, 'Individual', True) for k, v in new_contribs.items()]
            execute_values(cur, """
                INSERT INTO contributors (id, full_name, normalized_name, contributor_type, is_individual)
                VALUES %s
            """, contrib_data)
        
        # Bulk insert new recipients
        if new_recips:
            recip_data = [(v[0], k, v[1], str(v[1]).upper().strip(), 'Candidate', True) 
                         for k, v in new_recips.items()]
            execute_values(cur, """
                INSERT INTO recipients (id, recipid, full_name, normalized_name, recipient_type, is_individual)
                VALUES %s
            """, recip_data)
        
        # Prepare contributions
        contributions = []
        for _, row in batch_df.iterrows():
            if pd.isna(row['TRANS_DATE']) and row['AMOUNT_NUM'] == 0:
                continue
            
            norm_name = str(row['NAME']).upper().strip()
            trans_date = row['TRANS_DATE'] if pd.notna(row['TRANS_DATE']) else None
            
            contributions.append((
                str(uuid.uuid4()),
                row['REFNO'],
                election_id,
                contrib_cache[norm_name],
                recip_cache[row['RECIPID']],
                row['AMOUNT_NUM'],
                trans_date,
                1
            ))
        
        # Bulk insert
        if contributions:
            execute_values(cur, """
                INSERT INTO contributions (
                    id, reference_number, election_id, contributor_id, 
                    recipient_id, amount, transaction_date, payment_method
                )
                VALUES %s
            """, contributions, template="""(%s, %s, %s, %s, %s, %s, %s, %s)""")
            
            conn.commit()
            total_imported += len(contributions)
        
        # Progress
        batch_time = time.time() - batch_start
        elapsed = time.time() - start_time
        rate = len(contributions) / batch_time if batch_time > 0 else 0
        
        print(f"Batch {batch_num + 1}/{total_batches}: {len(contributions):,} records "
              f"@ {rate:.0f}/sec | Total: {total_imported:,} | {elapsed/60:.1f} min")
        
        # Save progress
        with open('import_progress.txt', 'w') as f:
            f.write(f"Direct Import Progress\n")
            f.write(f"====================\n")
            f.write(f"Imported: {total_imported:,} new records\n")
            f.write(f"Current total: {start_count + total_imported:,}\n")
            f.write(f"Target: {target:,}\n")
            f.write(f"Remaining: {target - (start_count + total_imported):,}\n")
            f.write(f"Progress: {(start_count + total_imported) / target * 100:.1f}%\n")
            f.write(f"Rate: {rate:.0f} records/sec\n")
    
    # Final stats
    cur.execute("SELECT COUNT(*) FROM contributions")
    final_count = cur.fetchone()[0]
    
    print("\n" + "=" * 80)
    print(f"IMPORT COMPLETED!")
    print(f"Imported: {total_imported:,} new records")
    print(f"Final count: {final_count:,} contributions")
    print(f"Progress: {final_count / target * 100:.1f}% of target")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    direct_import()