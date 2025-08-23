#!/usr/bin/env python3
"""Fast expenditure import script for NYC Campaign Finance data."""

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
    print(f"FAST EXPENDITURE IMPORT - Started at {datetime.now()}")
    print(f"{'='*80}\n")
    
    # Download CSV
    filename = 'CFB_20250720195643912.csv'
    
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
    
    print(f"Loaded {len(df):,} expenditure records from CSV")
    
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Check existing expenditures
        cur.execute("SELECT COUNT(*) FROM expenditures")
        existing_count = cur.fetchone()[0]
        print(f"Existing expenditures: {existing_count:,}")
        
        if existing_count >= len(df):
            print("All expenditures already imported!")
            return
        
        # Clear and reimport
        print("\nClearing existing expenditures for clean import...")
        cur.execute("TRUNCATE TABLE expenditures CASCADE")
        conn.commit()
        
        # Process in large batches
        batch_size = 10000
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        expenditures_data = []
        total_amount = Decimal('0')
        
        print(f"\nProcessing {total_batches} batches of {batch_size} records...")
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df))
            batch_df = df.iloc[start_idx:end_idx]
            
            for _, row in batch_df.iterrows():
                amount = Decimal(str(row.get('AMNT', 0))) if pd.notna(row.get('AMNT')) else Decimal('0')
                total_amount += amount
                
                # Parse date
                date_val = pd.to_datetime(row.get('DATE'), errors='coerce')
                if pd.isna(date_val):
                    date_val = None
                
                refund_date = pd.to_datetime(row.get('REFUNDDATE'), errors='coerce')
                if pd.isna(refund_date):
                    refund_date = None
                
                expenditures_data.append((
                    str(uuid.uuid4()),  # id
                    clean_text(row.get('REFNO')),  # reference_number
                    clean_text(row.get('PAYEENAME')),  # payee_name
                    clean_text(row.get('PURPOSECD')),  # purpose_code
                    clean_text(row.get('PURPOSEDESC')),  # purpose_description
                    date_val,  # expenditure_date
                    refund_date,  # refund_date
                    amount,  # amount
                    clean_text(row.get('RECIPID')),  # recipient_id
                    clean_text(row.get('RECIPNAME')),  # recipient_name
                    clean_text(row.get('ELECTION')),  # election_cycle
                    clean_text(row.get('CITY')),  # city
                    clean_text(row.get('STATE')),  # state
                    clean_text(row.get('ZIP')),  # zip_code
                    datetime.now(),  # created_at
                    datetime.now()  # updated_at
                ))
            
            # Insert batch
            if len(expenditures_data) >= batch_size:
                execute_values(cur, """
                    INSERT INTO expenditures 
                    (id, reference_number, payee_name, purpose_code, purpose_description,
                     expenditure_date, refund_date, amount, recipient_id, recipient_name,
                     election_cycle, city, state, zip_code, created_at, updated_at)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """, expenditures_data, page_size=1000)
                
                conn.commit()
                print(f"  Batch {batch_num + 1}/{total_batches}: Inserted {len(expenditures_data):,} expenditures")
                expenditures_data = []
        
        # Insert remaining
        if expenditures_data:
            execute_values(cur, """
                INSERT INTO expenditures 
                (id, reference_number, payee_name, purpose_code, purpose_description,
                 expenditure_date, refund_date, amount, recipient_id, recipient_name,
                 election_cycle, city, state, zip_code, created_at, updated_at)
                VALUES %s
                ON CONFLICT DO NOTHING
            """, expenditures_data, page_size=1000)
            conn.commit()
            print(f"  Final batch: Inserted {len(expenditures_data):,} expenditures")
        
        # Get final statistics
        cur.execute("SELECT COUNT(*), SUM(amount) FROM expenditures")
        final_count, final_total = cur.fetchone()
        
        print(f"\n{'='*80}")
        print("IMPORT COMPLETE")
        print(f"{'='*80}")
        print(f"\nFinal Statistics:")
        print(f"  Total Expenditures: {final_count:,}")
        print(f"  Total Amount: ${final_total:,.2f}")
        
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