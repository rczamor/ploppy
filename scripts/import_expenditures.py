"""Import expenditures data from CFB file."""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
import time
import uuid

DATABASE_URL = os.environ.get('DATABASE_URL')

class ExpendituresImporter:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self.conn.autocommit = False
        self.stats = {
            'total_processed': 0,
            'start_time': time.time()
        }
    
    def normalize_name(self, name):
        """Fast name normalization."""
        if pd.isna(name) or not name:
            return "UNKNOWN"
        return str(name).upper().strip()
    
    def import_expenditures(self):
        """Import expenditures data."""
        print(f"\nStarting EXPENDITURES import at {datetime.now()}")
        print("=" * 80)
        
        cur = self.conn.cursor()
        
        # Check existing count
        cur.execute("SELECT COUNT(*) FROM expenditures")
        existing_count = cur.fetchone()[0]
        print(f"Existing expenditures: {existing_count:,}")
        
        # Load CSV
        print("\nLoading expenditures CSV data...")
        import sys
        sys.path.append('..')
        from src.database.db_manager_v2 import NYCCFBDatabase
        db = NYCCFBDatabase()
        db.connect_to_object_storage('')
        df = db.download_csv_to_dataframe('CFB_20250720195643912.csv')
        
        print(f"Total expenditure records: {len(df):,}")
        df.columns = df.columns.str.strip()
        
        # Get existing reference numbers
        if existing_count > 0:
            cur.execute("SELECT DISTINCT reference_number FROM expenditures")
            existing_refs = set(row[0] for row in cur.fetchall())
            df_new = df[~df['REFNO'].isin(existing_refs)]
            print(f"New records to import: {len(df_new):,}")
        else:
            df_new = df
            print(f"Importing all {len(df_new):,} records")
        
        if len(df_new) == 0:
            print("No new expenditures to import!")
            return
        
        # Get default election
        cur.execute("SELECT id FROM elections ORDER BY election_year DESC LIMIT 1")
        election_id = cur.fetchone()
        if not election_id:
            election_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO elections (id, election_year, election_type)
                VALUES (%s, 2025, 'General')
            """, (election_id,))
            self.conn.commit()
        else:
            election_id = election_id[0]
        
        # Cache recipients
        print("Loading recipient cache...")
        cur.execute("SELECT COALESCE(recipid, full_name), id FROM recipients")
        recip_cache = dict(cur.fetchall())
        
        # Process in batches
        batch_size = 10000
        total_batches = (len(df_new) + batch_size - 1) // batch_size
        
        print(f"\nProcessing {total_batches} batches...")
        
        for batch_num in range(total_batches):
            batch_start = time.time()
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df_new))
            
            batch_df = df_new.iloc[start_idx:end_idx].copy()
            
            # Prepare batch data
            batch_df['PAYMENT_DATE'] = pd.to_datetime(batch_df['DATE'], errors='coerce')
            batch_df['INVOICE_DATE'] = pd.to_datetime(batch_df['INV_DATE'], errors='coerce')
            batch_df['AMOUNT_NUM'] = pd.to_numeric(batch_df['AMNT'], errors='coerce').fillna(0)
            
            # Get or create recipients
            for _, row in batch_df[['CANDID', 'CANDLAST', 'CANDFIRST']].drop_duplicates().iterrows():
                if pd.notna(row['CANDID']) and row['CANDID'] not in recip_cache:
                    full_name = f"{row['CANDLAST']}, {row['CANDFIRST']}"
                    new_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO recipients (id, recipid, full_name, normalized_name, recipient_type, is_individual)
                        VALUES (%s, %s, %s, %s, 'Candidate', true)
                        ON CONFLICT DO NOTHING
                    """, (new_id, row['CANDID'], full_name, self.normalize_name(full_name)))
                    recip_cache[row['CANDID']] = new_id
            
            # Prepare expenditures
            expenditures = []
            for _, row in batch_df.iterrows():
                recip_id = recip_cache.get(row['CANDID']) if pd.notna(row['CANDID']) else None
                if not recip_id:
                    continue
                
                is_reimb = str(row.get('RR_IND', 'N')).upper() == 'Y'
                is_seg = str(row.get('SEG_IND', 'N')).upper() == 'Y'
                
                expenditures.append((
                    str(uuid.uuid4()),
                    row['REFNO'],
                    election_id,
                    recip_id,
                    int(row['FILING']) if pd.notna(row['FILING']) else None,
                    row['SCHEDULE'] if pd.notna(row['SCHEDULE']) else None,
                    row['INVOICE_DATE'] if pd.notna(row['INVOICE_DATE']) else None,
                    row['PAYMENT_DATE'] if pd.notna(row['PAYMENT_DATE']) else None,
                    row['NAME'] if pd.notna(row['NAME']) else 'Unknown Payee',
                    row['C_CODE'] if pd.notna(row['C_CODE']) else None,
                    row['ORG_IND'] if pd.notna(row['ORG_IND']) else None,
                    row['CITY'] if pd.notna(row['CITY']) else None,
                    row['STATE'] if pd.notna(row['STATE']) else None,
                    row['ZIP'] if pd.notna(row['ZIP']) else None,
                    row['PAY_METHOD'] if pd.notna(row['PAY_METHOD']) else None,
                    row['AMOUNT_NUM'],
                    row['PURPOSECD'] if pd.notna(row['PURPOSECD']) else None,
                    row['PURPOSE'] if pd.notna(row['PURPOSE']) else None,
                    row['EXPLAIN'] if pd.notna(row['EXPLAIN']) else None,
                    row['EXEMPTCD'] if pd.notna(row['EXEMPTCD']) else None,
                    is_reimb,
                    is_seg
                ))
            
            # Bulk insert
            if expenditures:
                execute_values(cur, """
                    INSERT INTO expenditures (
                        id, reference_number, election_id, recipient_id, filing_number, schedule,
                        invoice_date, payment_date, payee_name, payee_type, organization_type,
                        city, state, zip, payment_method, amount, purpose_code,
                        purpose_description, explanation, exemption_code,
                        is_reimbursement, is_segregated
                    )
                    VALUES %s
                    ON CONFLICT (reference_number) DO NOTHING
                """, expenditures, template="""(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""")
                
                self.conn.commit()
                self.stats['total_processed'] += len(expenditures)
            
            # Progress
            batch_time = time.time() - batch_start
            elapsed = time.time() - self.stats['start_time']
            rate = len(expenditures) / batch_time if batch_time > 0 else 0
            
            print(f"Batch {batch_num + 1}/{total_batches}: "
                  f"Imported {len(expenditures):,} records @ {rate:.0f}/sec | "
                  f"Total: {self.stats['total_processed']:,}")
            
            # Save progress
            with open('expenditures_import_progress.txt', 'w') as f:
                f.write(f"Expenditures Import Progress\n")
                f.write(f"=========================\n")
                f.write(f"Imported: {self.stats['total_processed']:,} records\n")
                f.write(f"Progress: {(batch_num + 1) / total_batches * 100:.1f}%\n")
                f.write(f"Rate: {rate:.0f} records/sec\n")
                f.write(f"Elapsed: {elapsed/60:.1f} minutes\n")
        
        # Final stats
        cur.execute("SELECT COUNT(*) FROM expenditures")
        final_count = cur.fetchone()[0]
        
        cur.execute("SELECT SUM(amount) FROM expenditures")
        total_amount = cur.fetchone()[0] or 0
        
        print("\n" + "=" * 80)
        print(f"EXPENDITURES IMPORT COMPLETED!")
        print(f"Imported: {self.stats['total_processed']:,} new records")
        print(f"Total expenditures: {final_count:,}")
        print(f"Total amount: ${total_amount:,.2f}")
        
        cur.close()
        self.conn.close()

if __name__ == "__main__":
    importer = ExpendituresImporter()
    importer.import_expenditures()