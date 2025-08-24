#!/usr/bin/env python3
"""Import contribution records from Object Storage."""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from datetime import datetime
import io

# Add src to path
sys.path.insert(0, 'src')
from database.db_manager_v2 import NYCCFBDatabase

def import_contributions():
    """Import all contribution records from object storage."""
    print("\n📥 IMPORTING CONTRIBUTIONS FROM OBJECT STORAGE")
    print("="*60)
    
    try:
        from replit.object_storage import Client
        client = Client()
        
        # Download the file
        print("Downloading CFB_contributions-2025-08-23.csv...")
        content = client.download_as_bytes('CFB_contributions-2025-08-23.csv')
        
        if not content:
            print("❌ File not found in object storage")
            return
        
        print(f"✅ Downloaded {len(content) / (1024*1024):.1f} MB")
        
        # Load into pandas
        print("Loading CSV data...")
        df = pd.read_csv(io.StringIO(content.decode('utf-8', errors='ignore')))
        total_records = len(df)
        print(f"✅ Loaded {total_records:,} records from CSV")
        
        # Connect to database
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        
        # Process in batches
        batch_size = 10000
        imported = 0
        failed = 0
        
        print(f"\nImporting in batches of {batch_size:,}...")
        
        for start_idx in range(0, len(df), batch_size):
            end_idx = min(start_idx + batch_size, len(df))
            batch_df = df.iloc[start_idx:end_idx]
            
            # Clean and prepare data
            batch_df['amount'] = pd.to_numeric(batch_df.get('AMNT', 0), errors='coerce')
            batch_df['date'] = pd.to_datetime(batch_df.get('DATE'), errors='coerce')
            
            # Filter valid records
            valid_df = batch_df[batch_df['amount'].notna() & batch_df['date'].notna()]
            
            if len(valid_df) == 0:
                continue
            
            # Prepare records for insertion
            records = []
            for _, row in valid_df.iterrows():
                records.append((
                    str(row.get('REFNO', '')),
                    str(row.get('STRNO', '')),
                    str(row.get('STRNAME', '')),
                    row['date'],
                    float(row['amount']),
                    str(row.get('C_CODE', '')),
                    str(row.get('RECIPID', '')),
                    str(row.get('RECIPNAME', '')),
                    str(row.get('COMMITTEE', '')),
                    int(row.get('FILING', 0)) if pd.notna(row.get('FILING')) else 0,
                    str(row.get('SCHEDULE', '')),
                    int(row.get('PAGENO', 0)) if pd.notna(row.get('PAGENO')) else 0,
                    int(row.get('SEQUENCENO', 0)) if pd.notna(row.get('SEQUENCENO')) else 0,
                    str(row.get('OFFICE', '')),
                    str(row.get('PARTY', '')),
                    str(row.get('DISTRICT', '')),
                    str(row.get('OCCUPATION', '')),
                    str(row.get('EMPNAME', '')),
                    str(row.get('EMPSTRNO', '')),
                    str(row.get('EMPSTRNAME', '')),
                    str(row.get('EMPCITY', '')),
                    str(row.get('EMPSTATE', '')),
                    str(row.get('CITY', '')),
                    str(row.get('STATE', '')),
                    str(row.get('ZIP', '')),
                    str(row.get('BORO', '')),
                    str(row.get('WARD', '')),
                    str(row.get('PAY_METHOD', '')),
                    str(row.get('INTERMNO', '')),
                    str(row.get('INTERMNAME', '')),
                    str(row.get('INTSTRNO', '')),
                    str(row.get('INTSTRNM', '')),
                    str(row.get('INTAPTNO', '')),
                    str(row.get('INTCITY', '')),
                    str(row.get('INTST', '')),
                    str(row.get('INTZIP', '')),
                    str(row.get('INTEMPNAME', '')),
                    str(row.get('INTEMPSTNO', '')),
                    str(row.get('INTEMPSTNM', '')),
                    str(row.get('INTEMPCITY', '')),
                    str(row.get('INTEMPST', '')),
                    str(row.get('INTOCCUPA', '')),
                    str(row.get('PURPOSECD', '')),
                    str(row.get('EXEMPTCD', '')),
                    str(row.get('ADJTYPECD', '')),
                    str(row.get('RR_IND', '')),
                    str(row.get('SEG_IND', '')),
                    str(row.get('INT_C_CODE', ''))
                ))
            
            try:
                # Bulk insert with ON CONFLICT - using actual column names
                execute_values(
                    cur,
                    """
                    INSERT INTO contributions (
                        refno, str_no, str_name, date, amount,
                        recip_id, occupation, 
                        contributor_city, contributor_state, contributor_zip,
                        schedule, page_no, sequence_no
                    ) VALUES %s
                    ON CONFLICT (refno) DO UPDATE SET
                        amount = EXCLUDED.amount,
                        date = EXCLUDED.date,
                        str_name = EXCLUDED.str_name
                    """,
                    [(r[0], r[1], r[2], r[3], r[4], r[6], r[16], 
                      r[22], r[23], r[24], r[10], r[11], r[12]) for r in records],
                    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                )
                
                conn.commit()
                imported += len(records)
                
                # Progress update
                progress = (end_idx / total_records) * 100
                print(f"  Progress: {progress:.1f}% - Imported {imported:,} records", end='\r')
                
            except Exception as e:
                conn.rollback()
                failed += len(records)
                print(f"\n  ⚠️  Batch error: {str(e)[:100]}")
                continue
        
        print(f"\n\n✅ IMPORT COMPLETE!")
        print(f"   Total imported: {imported:,} records")
        if failed > 0:
            print(f"   Failed: {failed:,} records")
        
        # Final count
        cur.execute("SELECT COUNT(*) FROM contributions")
        final_count = cur.fetchone()[0]
        print(f"   Final database count: {final_count:,} contributions")
        
        # Get summary stats
        cur.execute("""
            SELECT 
                MIN(date) as min_date,
                MAX(date) as max_date,
                SUM(amount) as total_amount,
                COUNT(DISTINCT str_name) as unique_contributors
            FROM contributions
            WHERE amount IS NOT NULL
        """)
        
        stats = cur.fetchone()
        print(f"\n📊 DATABASE STATISTICS:")
        print(f"   Date range: {stats[0]} to {stats[1]}")
        print(f"   Total amount: ${stats[2]:,.2f}")
        print(f"   Unique contributors: {stats[3]:,}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import_contributions()