"""Import using sequence numbers to track progress."""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
import time
import uuid

DATABASE_URL = os.environ.get('DATABASE_URL')

def import_by_sequence():
    """Import data using sequence numbers for accurate tracking."""
    print(f"\nStarting SEQUENCE-BASED import at {datetime.now()}")
    print("=" * 80)
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    # Get highest sequence number in database
    cur.execute("""
        SELECT MAX(CAST(sequence_number AS BIGINT)) 
        FROM contributions 
        WHERE sequence_number IS NOT NULL
    """)
    max_seq = cur.fetchone()[0] or 0
    print(f"Highest sequence in database: {max_seq:,}")
    
    # Load CSV
    print("\nLoading CSV data...")
    from db_manager_v2 import NYCCFBDatabase
    db = NYCCFBDatabase()
    db.connect_to_object_storage('')
    df = db.download_csv_to_dataframe('CFB_20250718173623479.csv')
    df.columns = df.columns.str.strip()
    
    print(f"Total CSV records: {len(df):,}")
    
    # Convert sequence numbers to integers
    df['SEQ_INT'] = pd.to_numeric(df['SEQUENCENO'], errors='coerce')
    
    # Filter to records after max sequence
    df_new = df[df['SEQ_INT'] > max_seq].copy()
    print(f"Records with sequence > {max_seq}: {len(df_new):,}")
    
    if len(df_new) == 0:
        print("No new records to import!")
        return
    
    # Sort by sequence for orderly import
    df_new = df_new.sort_values('SEQ_INT')
    
    # Prepare data
    df_new['NAME'] = df_new['NAME'].fillna('Anonymous Contributor')
    df_new['RECIPNAME'] = df_new['RECIPNAME'].fillna('Unknown Recipient')
    df_new['TRANS_DATE'] = pd.to_datetime(df_new['DATE'], errors='coerce')
    df_new['AMOUNT_NUM'] = pd.to_numeric(df_new['AMNT'], errors='coerce').fillna(0)
    
    # Get default election
    cur.execute("SELECT id FROM elections ORDER BY election_year DESC LIMIT 1")
    election_id = cur.fetchone()
    if not election_id:
        election_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO elections (id, election_year, election_type)
            VALUES (%s, 2025, 'General')
        """, (election_id,))
        conn.commit()
    else:
        election_id = election_id[0]
    
    # Process in batches
    batch_size = 10000
    total_batches = (len(df_new) + batch_size - 1) // batch_size
    total_imported = 0
    start_time = time.time()
    
    print(f"\nProcessing {total_batches} batches of up to {batch_size:,} records...")
    
    for batch_num in range(total_batches):
        batch_start = time.time()
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(df_new))
        
        batch_df = df_new.iloc[start_idx:end_idx]
        
        # Get or create contributors/recipients for batch
        contributions = []
        
        for _, row in batch_df.iterrows():
            # Skip invalid records
            if pd.isna(row['TRANS_DATE']) and row['AMOUNT_NUM'] == 0:
                continue
            
            # Get contributor
            norm_name = str(row['NAME']).upper().strip()
            cur.execute("SELECT id FROM contributors WHERE normalized_name = %s", (norm_name,))
            contrib_id = cur.fetchone()
            if not contrib_id:
                contrib_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO contributors (id, full_name, normalized_name, contributor_type, is_individual)
                    VALUES (%s, %s, %s, 'Individual', true)
                """, (contrib_id, row['NAME'], norm_name))
            else:
                contrib_id = contrib_id[0]
            
            # Get recipient
            cur.execute("SELECT id FROM recipients WHERE recipid = %s", (row['RECIPID'],))
            recip_id = cur.fetchone()
            if not recip_id:
                recip_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO recipients (id, recipid, full_name, normalized_name, recipient_type, is_individual)
                    VALUES (%s, %s, %s, %s, 'Candidate', true)
                """, (recip_id, row['RECIPID'], row['RECIPNAME'], str(row['RECIPNAME']).upper().strip()))
            else:
                recip_id = recip_id[0]
            
            # Add contribution
            trans_date = row['TRANS_DATE'] if pd.notna(row['TRANS_DATE']) else None
            contributions.append((
                str(uuid.uuid4()),
                row['REFNO'],
                int(row['SEQ_INT']),
                election_id,
                contrib_id,
                recip_id,
                row['AMOUNT_NUM'],
                trans_date,
                1  # payment_method
            ))
        
        # Bulk insert contributions
        if contributions:
            execute_values(cur, """
                INSERT INTO contributions (
                    id, reference_number, sequence_number, election_id, 
                    contributor_id, recipient_id, amount, transaction_date, payment_method
                )
                VALUES %s
            """, contributions, template="""(%s, %s, %s, %s, %s, %s, %s, %s, %s)""")
            
            conn.commit()
            total_imported += len(contributions)
        
        # Report progress
        batch_time = time.time() - batch_start
        elapsed = time.time() - start_time
        rate = len(contributions) / batch_time if batch_time > 0 else 0
        
        print(f"Batch {batch_num + 1}/{total_batches}: "
              f"Imported {len(contributions):,} records in {batch_time:.1f}s "
              f"({rate:.0f} rec/sec) | Total: {total_imported:,}")
        
        # Save progress
        with open('import_progress.txt', 'w') as f:
            f.write(f"Sequence-Based Import\n")
            f.write(f"===================\n")
            f.write(f"Imported: {total_imported:,} records\n")
            f.write(f"Batch: {batch_num + 1}/{total_batches}\n")
            f.write(f"Max sequence: {batch_df['SEQ_INT'].max():,}\n")
            f.write(f"Rate: {rate:.0f} records/sec\n")
            f.write(f"Elapsed: {elapsed/60:.1f} minutes\n")
    
    # Final stats
    cur.execute("SELECT COUNT(*) FROM contributions")
    final_count = cur.fetchone()[0]
    
    print("\n" + "=" * 80)
    print(f"IMPORT COMPLETED!")
    print(f"Imported: {total_imported:,} new records")
    print(f"Total time: {elapsed/60:.1f} minutes")
    print(f"Final count: {final_count:,} contributions")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    import_by_sequence()