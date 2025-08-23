#!/usr/bin/env python3
"""Simple direct contributor import - focusing on speed and completeness."""

import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import os
from datetime import datetime
from decimal import Decimal
import uuid

try:
    from replit.object_storage import Client
    client = Client()
    USE_OBJECT_STORAGE = True
except ImportError:
    USE_OBJECT_STORAGE = False

DATABASE_URL = os.environ.get('DATABASE_URL')

def clean_text(text):
    """Clean and normalize text."""
    if pd.isna(text) or text is None:
        return None
    text = str(text).strip()
    return text if text else None

def main():
    print(f"\n{'='*80}")
    print(f"SIMPLE CONTRIBUTOR IMPORT - Started at {datetime.now()}")
    print(f"{'='*80}\n")
    
    # Download CSV
    filename = 'CFB_contributions-2025-08-23.csv'
    
    if USE_OBJECT_STORAGE:
        print(f"Downloading {filename} from object storage...")
        data = client.download_as_text(filename)
        temp_file = f'/tmp/{filename}'
        with open(temp_file, 'w') as f:
            f.write(data)
        df = pd.read_csv(temp_file, low_memory=False)
        os.remove(temp_file)
    else:
        df = pd.read_csv(f'data/{filename}', low_memory=False)
    
    print(f"Loaded {len(df):,} records from CSV")
    
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Clear existing data for clean import
        print("\nClearing existing contributions...")
        cur.execute("TRUNCATE TABLE contributions CASCADE")
        cur.execute("DELETE FROM contributors WHERE is_individual = true")
        cur.execute("DELETE FROM org_contributors")
        cur.execute("TRUNCATE TABLE recipients CASCADE")
        cur.execute("TRUNCATE TABLE employers CASCADE")
        cur.execute("TRUNCATE TABLE elections CASCADE")
        conn.commit()
        print("  ✓ Cleared existing data")
        
        # Process in large batches for speed
        batch_size = 10000
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        contributions_data = []
        total_amount = Decimal('0')
        
        print(f"\nProcessing {total_batches} batches of {batch_size} records...")
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df))
            batch_df = df.iloc[start_idx:end_idx]
            
            for _, row in batch_df.iterrows():
                # Simple direct insert - don't worry about relationships for now
                amount = Decimal(str(row.get('AMNT', 0))) if pd.notna(row.get('AMNT')) else Decimal('0')
                total_amount += amount
                
                # Parse date, handling NaT/None properly
                date_val = pd.to_datetime(row.get('DATE'), errors='coerce')
                if pd.isna(date_val):
                    date_val = None
                
                contributions_data.append((
                    str(uuid.uuid4()),  # id
                    clean_text(row.get('REFNO')),  # refno
                    amount,  # amount
                    date_val,  # date
                    clean_text(row.get('NAME')),  # contributor name (store in str_name temporarily)
                    clean_text(row.get('RECIPNAME')),  # recipient name (store in occupation temporarily) 
                    clean_text(row.get('CITY')),  # contributor_city
                    clean_text(row.get('STATE')),  # contributor_state
                    clean_text(row.get('ZIP')),  # contributor_zip
                    datetime.now(),  # created_at
                    datetime.now()  # updated_at
                ))
            
            # Insert batch
            if len(contributions_data) >= batch_size:
                execute_values(cur, """
                    INSERT INTO contributions 
                    (id, refno, amount, date, str_name, occupation,
                     contributor_city, contributor_state, contributor_zip,
                     created_at, updated_at)
                    VALUES %s
                    ON CONFLICT (refno) DO NOTHING
                """, contributions_data, page_size=1000)
                
                conn.commit()
                inserted = cur.rowcount
                print(f"  Batch {batch_num + 1}/{total_batches}: Inserted {inserted:,} contributions")
                contributions_data = []
        
        # Insert remaining
        if contributions_data:
            execute_values(cur, """
                INSERT INTO contributions 
                (id, refno, amount, date, str_name, occupation,
                 contributor_city, contributor_state, contributor_zip,
                 created_at, updated_at)
                VALUES %s
                ON CONFLICT (refno) DO NOTHING
            """, contributions_data, page_size=1000)
            conn.commit()
            print(f"  Final batch: Inserted {cur.rowcount:,} contributions")
        
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
        
        if final_count > 2000000:
            print("\n✓ Import successful! Data loaded.")
            print("\nNext steps:")
            print("  1. Run contributor normalization to parse names")
            print("  2. Run geocoding for all records")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()