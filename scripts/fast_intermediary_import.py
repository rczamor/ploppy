#!/usr/bin/env python3
"""Fast intermediary contributions import script for NYC Campaign Finance data."""

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
    print(f"FAST INTERMEDIARY IMPORT - Started at {datetime.now()}")
    print(f"{'='*80}\n")
    
    # Download CSV
    filename = 'CFB_intermediaries-2025-08-23.csv'
    
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
    
    # Filter for records with intermediaries
    df_with_intermediaries = df[df['INTERMNAME'].notna()]
    print(f"Records with intermediaries: {len(df_with_intermediaries):,}")
    
    if len(df_with_intermediaries) == 0:
        print("No intermediary records to import!")
        return
    
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Check existing intermediaries
        cur.execute("SELECT COUNT(*) FROM intermediaries")
        existing_count = cur.fetchone()[0]
        print(f"Existing intermediaries: {existing_count:,}")
        
        # Process intermediaries
        intermediaries_cache = {}
        contributions_data = []
        
        # Process in batches
        batch_size = 5000
        total_batches = (len(df_with_intermediaries) + batch_size - 1) // batch_size
        
        print(f"\nProcessing {total_batches} batches of {batch_size} records...")
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df_with_intermediaries))
            batch_df = df_with_intermediaries.iloc[start_idx:end_idx]
            
            for _, row in batch_df.iterrows():
                # Get or create intermediary
                interm_name = clean_text(row.get('INTERMNAME'))
                
                if interm_name and interm_name not in intermediaries_cache:
                    # Check if exists
                    cur.execute("""
                        SELECT id FROM intermediaries 
                        WHERE normalized_name = %s
                        LIMIT 1
                    """, (interm_name.upper(),))
                    
                    result = cur.fetchone()
                    if result:
                        intermediary_id = result[0]
                    else:
                        # Create new intermediary
                        intermediary_id = str(uuid.uuid4())
                        cur.execute("""
                            INSERT INTO intermediaries 
                            (id, full_name, normalized_name, intermediary_number,
                             street_number, street_name, apartment, city, state, zip_code,
                             employer_name, occupation, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            RETURNING id
                        """, (
                            intermediary_id,
                            interm_name,
                            interm_name.upper(),
                            clean_text(row.get('INTERMNO')),
                            clean_text(row.get('INTSTRNO')),
                            clean_text(row.get('INTSTRNM')),
                            clean_text(row.get('INTAPTNO')),
                            clean_text(row.get('INTCITY')),
                            clean_text(row.get('INTST')),
                            clean_text(row.get('INTZIP')),
                            clean_text(row.get('INTEMPNAME')),
                            clean_text(row.get('INTOCCUPA')),
                            datetime.now()
                        ))
                        
                        result = cur.fetchone()
                        if not result:
                            # Already exists (race condition)
                            cur.execute("""
                                SELECT id FROM intermediaries 
                                WHERE normalized_name = %s
                                LIMIT 1
                            """, (interm_name.upper(),))
                            result = cur.fetchone()
                            intermediary_id = result[0]
                    
                    intermediaries_cache[interm_name] = intermediary_id
                
                # Create contribution record with intermediary link
                amount = Decimal(str(row.get('AMNT', 0))) if pd.notna(row.get('AMNT')) else Decimal('0')
                
                # Parse date
                date_val = pd.to_datetime(row.get('DATE'), errors='coerce')
                if pd.isna(date_val):
                    date_val = None
                
                refno = clean_text(row.get('REFNO'))
                if not refno:  # Skip records without REFNO
                    continue
                    
                contributions_data.append((
                    refno,  # Use REFNO as unique identifier
                    intermediaries_cache.get(interm_name),  # intermediary_id
                    refno,  # refno
                    amount,  # amount
                    date_val,  # date
                    clean_text(row.get('NAME')),  # contributor name
                    clean_text(row.get('RECIPNAME')),  # recipient name
                    clean_text(row.get('CITY')),  # city
                    clean_text(row.get('STATE')),  # state
                    clean_text(row.get('ZIP')),  # zip
                    datetime.now(),  # created_at
                    datetime.now()  # updated_at
                ))
            
            # Insert batch of contributions with intermediary links
            if contributions_data and len(contributions_data) >= batch_size:
                execute_values(cur, """
                    INSERT INTO contributions 
                    (id, intermediary_id, refno, amount, date, str_name, occupation,
                     contributor_city, contributor_state, contributor_zip,
                     created_at, updated_at)
                    VALUES %s
                    ON CONFLICT (refno) DO UPDATE
                    SET intermediary_id = EXCLUDED.intermediary_id
                """, contributions_data, page_size=1000)
                
                conn.commit()
                print(f"  Batch {batch_num + 1}/{total_batches}: Processed {len(contributions_data):,} intermediary contributions")
                contributions_data = []
        
        # Insert remaining
        if contributions_data:
            execute_values(cur, """
                INSERT INTO contributions 
                (id, intermediary_id, refno, amount, date, str_name, occupation,
                 contributor_city, contributor_state, contributor_zip,
                 created_at, updated_at)
                VALUES %s
                ON CONFLICT (refno) DO UPDATE
                SET intermediary_id = EXCLUDED.intermediary_id
            """, contributions_data, page_size=1000)
            conn.commit()
            print(f"  Final batch: Processed {len(contributions_data):,} intermediary contributions")
        
        # Get final statistics
        cur.execute("SELECT COUNT(*) FROM intermediaries")
        intermediary_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM contributions WHERE intermediary_id IS NOT NULL")
        contrib_count = cur.fetchone()[0]
        
        print(f"\n{'='*80}")
        print("IMPORT COMPLETE")
        print(f"{'='*80}")
        print(f"\nFinal Statistics:")
        print(f"  Total Intermediaries: {intermediary_count:,}")
        print(f"  Contributions via Intermediaries: {contrib_count:,}")
        
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