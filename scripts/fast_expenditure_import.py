#!/usr/bin/env python3
"""Fast expenditure import script for NYC Campaign Finance data with REFNO deduplication."""

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

def parse_date(date_str):
    """Parse date string to datetime."""
    if pd.isna(date_str) or not date_str:
        return None
    try:
        return pd.to_datetime(date_str, errors='coerce')
    except:
        return None

def main():
    print(f"\n{'='*80}")
    print(f"FAST EXPENDITURE IMPORT - Started at {datetime.now()}")
    print(f"{'='*80}\n")
    
    # Download CSV (the intermediaries file actually has expenditure data with REFNO)
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
    
    print(f"Loaded {len(df):,} expenditure records from CSV")
    
    # Filter records with REFNO
    df_with_refno = df[df['REFNO'].notna()].copy()
    print(f"Records with REFNO: {len(df_with_refno):,}")
    
    # Deduplicate by REFNO, keeping the first occurrence
    df_dedup = df_with_refno.drop_duplicates(subset=['REFNO'], keep='first')
    print(f"After deduplication: {len(df_dedup):,} unique REFNOs")
    print(f"Duplicates removed: {len(df_with_refno) - len(df_dedup):,}")
    
    if len(df_dedup) == 0:
        print("No records with REFNO to import!")
        return
    
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Check existing expenditures
        cur.execute("SELECT COUNT(*) FROM expenditures")
        existing_count = cur.fetchone()[0]
        print(f"Existing expenditures: {existing_count:,}")
        
        # Get existing REFNOs for deduplication
        cur.execute("SELECT reference_number FROM expenditures WHERE reference_number IS NOT NULL")
        existing_refnos = set(row[0] for row in cur.fetchall())
        print(f"Existing REFNOs: {len(existing_refnos):,}")
        
        # Filter out existing REFNOs
        df_new = df_dedup[~df_dedup['REFNO'].isin(existing_refnos)]
        print(f"New expenditures to import: {len(df_new):,}")
        
        if len(df_new) == 0:
            print("No new expenditures to import!")
            return
        
        # Process in batches
        batch_size = 5000
        total_batches = (len(df_new) + batch_size - 1) // batch_size
        
        expenditures_data = []
        total_amount = Decimal('0')
        imported_count = 0
        
        print(f"\nProcessing {total_batches} batches of up to {batch_size} records...")
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df_new))
            batch_df = df_new.iloc[start_idx:end_idx]
            
            for _, row in batch_df.iterrows():
                refno = clean_text(row.get('REFNO'))
                if not refno:
                    continue
                
                # Parse amount
                amount = Decimal(str(row.get('AMNT', 0))) if pd.notna(row.get('AMNT')) else Decimal('0')
                total_amount += amount
                
                # Map CSV columns to database columns
                expenditures_data.append((
                    str(uuid.uuid4()),  # id
                    refno,  # reference_number (UNIQUE)
                    None,  # election_id (will be linked later)
                    None,  # recipient_id (will be linked later)
                    int(row.get('FILING')) if pd.notna(row.get('FILING')) else None,  # filing_number
                    clean_text(row.get('SCHEDULE')),  # schedule
                    parse_date(row.get('INV_DATE')),  # invoice_date
                    parse_date(row.get('DATE')),  # payment_date
                    clean_text(row.get('NAME')),  # payee_name
                    clean_text(row.get('C_CODE')),  # payee_type
                    clean_text(row.get('ORG_IND')),  # organization_type
                    clean_text(row.get('CITY')),  # city
                    clean_text(row.get('STATE')),  # state
                    clean_text(row.get('ZIP')),  # zip
                    clean_text(row.get('PAY_METHOD')),  # payment_method
                    amount,  # amount
                    clean_text(row.get('PURPOSECD')),  # purpose_code
                    clean_text(row.get('PURPOSE')),  # purpose_description
                    clean_text(row.get('EXPLAIN')),  # explanation
                    clean_text(row.get('EXEMPTCD')),  # exemption_code
                    row.get('RR_IND') == 'Y' if pd.notna(row.get('RR_IND')) else False,  # is_reimbursement
                    row.get('SEG_IND') == 'Y' if pd.notna(row.get('SEG_IND')) else False,  # is_segregated
                    datetime.now(),  # created_at
                    datetime.now()  # updated_at
                ))
            
            # Insert batch
            if len(expenditures_data) >= batch_size or batch_num == total_batches - 1:
                if expenditures_data:
                    execute_values(cur, """
                        INSERT INTO expenditures 
                        (id, reference_number, election_id, recipient_id, filing_number,
                         schedule, invoice_date, payment_date, payee_name, payee_type,
                         organization_type, city, state, zip, payment_method,
                         amount, purpose_code, purpose_description, explanation,
                         exemption_code, is_reimbursement, is_segregated, created_at, updated_at)
                        VALUES %s
                        ON CONFLICT (reference_number) DO UPDATE SET
                            amount = EXCLUDED.amount,
                            payee_name = EXCLUDED.payee_name,
                            payment_date = EXCLUDED.payment_date,
                            updated_at = EXCLUDED.updated_at
                    """, expenditures_data, page_size=1000)
                    
                    imported_count += len(expenditures_data)
                    conn.commit()
                    print(f"  Batch {batch_num + 1}/{total_batches}: Imported {len(expenditures_data):,} expenditures (Total: {imported_count:,})")
                    expenditures_data = []
        
        # Get final statistics
        cur.execute("SELECT COUNT(*), SUM(amount) FROM expenditures")
        final_count, final_total = cur.fetchone()
        
        print(f"\n{'='*80}")
        print("IMPORT COMPLETE")
        print(f"{'='*80}")
        print(f"\nFinal Statistics:")
        print(f"  Total Expenditures: {final_count:,}")
        print(f"  Total Amount: ${final_total:,.2f}" if final_total else "  Total Amount: $0.00")
        print(f"  Newly Imported: {imported_count:,}")
        print(f"  Deduplicated (skipped): {len(df_dedup) - len(df_new):,}")
        
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