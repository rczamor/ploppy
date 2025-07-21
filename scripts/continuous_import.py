"""Continuous import that processes all remaining data."""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
import time
import uuid

DATABASE_URL = os.environ.get('DATABASE_URL')

class ContinuousImporter:
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
            return "ANONYMOUS CONTRIBUTOR"
        return str(name).upper().strip()
    
    def import_all_remaining(self):
        """Import all remaining data in continuous batches."""
        print(f"\nStarting CONTINUOUS import at {datetime.now()}")
        print("=" * 80)
        
        # Get current count
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT reference_number) FROM contributions")
        existing_count = cur.fetchone()[0]
        print(f"Existing contributions: {existing_count:,}")
        
        # Load CSV
        print("\nLoading CSV data...")
        from db_manager_v2 import NYCCFBDatabase
        db = NYCCFBDatabase()
        db.connect_to_object_storage('')
        df = db.download_csv_to_dataframe('CFB_20250718173623479.csv')
        
        print(f"Total CSV records: {len(df):,}")
        df.columns = df.columns.str.strip()
        
        # Get all existing reference numbers in one query
        print("Loading existing reference numbers...")
        cur.execute("SELECT DISTINCT reference_number FROM contributions")
        existing_refs = set(row[0] for row in cur.fetchall())
        print(f"Found {len(existing_refs):,} existing references")
        
        # Filter to new records only
        df_new = df[~df['REFNO'].isin(existing_refs)]
        print(f"New records to import: {len(df_new):,}")
        
        if len(df_new) == 0:
            print("No new records to import!")
            return
        
        # Process in large batches
        batch_size = 50000
        total_batches = (len(df_new) + batch_size - 1) // batch_size
        
        print(f"\nProcessing {total_batches} batches of {batch_size:,} records...")
        
        # Get or create default election
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
        
        # Process ALL batches
        for batch_num in range(total_batches):
            batch_start = time.time()
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df_new))
            
            batch_df = df_new.iloc[start_idx:end_idx].copy()
            
            # Prepare batch data
            batch_df['NAME'] = batch_df['NAME'].fillna('Anonymous Contributor')
            batch_df['RECIPNAME'] = batch_df['RECIPNAME'].fillna('Unknown Recipient')
            batch_df['NORM_NAME'] = batch_df['NAME'].apply(self.normalize_name)
            batch_df['TRANS_DATE'] = pd.to_datetime(batch_df['DATE'], errors='coerce')
            batch_df['AMOUNT_NUM'] = pd.to_numeric(batch_df['AMNT'], errors='coerce').fillna(0)
            
            # Get all unique contributors/recipients for this batch
            contributor_map = {}
            recipient_map = {}
            
            # Bulk create contributors
            unique_contributors = batch_df[['NORM_NAME', 'NAME']].drop_duplicates('NORM_NAME')
            for _, row in unique_contributors.iterrows():
                cur.execute("""
                    SELECT id FROM contributors WHERE normalized_name = %s
                """, (row['NORM_NAME'],))
                result = cur.fetchone()
                if result:
                    contributor_map[row['NORM_NAME']] = result[0]
                else:
                    new_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO contributors (id, full_name, normalized_name, contributor_type, is_individual)
                        VALUES (%s, %s, %s, 'Individual', true)
                        ON CONFLICT DO NOTHING
                        RETURNING id
                    """, (new_id, row['NAME'], row['NORM_NAME']))
                    result = cur.fetchone()
                    contributor_map[row['NORM_NAME']] = result[0] if result else new_id
            
            # Bulk create recipients
            unique_recipients = batch_df[['RECIPID', 'RECIPNAME']].drop_duplicates('RECIPID')
            for _, row in unique_recipients.iterrows():
                cur.execute("""
                    SELECT id FROM recipients WHERE recipid = %s
                """, (row['RECIPID'],))
                result = cur.fetchone()
                if result:
                    recipient_map[row['RECIPID']] = result[0]
                else:
                    new_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO recipients (id, recipid, full_name, normalized_name, recipient_type, is_individual)
                        VALUES (%s, %s, %s, %s, 'Candidate', true)
                        ON CONFLICT DO NOTHING
                        RETURNING id
                    """, (new_id, row['RECIPID'], row['RECIPNAME'], self.normalize_name(row['RECIPNAME'])))
                    result = cur.fetchone()
                    recipient_map[row['RECIPID']] = result[0] if result else new_id
            
            # Prepare contributions for bulk insert
            contribution_data = []
            for _, row in batch_df.iterrows():
                if row['AMOUNT_NUM'] == 0 and pd.isna(row['TRANS_DATE']):
                    continue
                
                contrib_id = contributor_map.get(row['NORM_NAME'])
                recip_id = recipient_map.get(row['RECIPID'])
                
                if contrib_id and recip_id:
                    trans_date = row['TRANS_DATE'] if pd.notna(row['TRANS_DATE']) else None
                    contribution_data.append((
                        str(uuid.uuid4()),
                        row['REFNO'],
                        election_id,
                        contrib_id,
                        recip_id,
                        row['AMOUNT_NUM'],
                        trans_date,
                        1  # payment_method
                    ))
            
            # Bulk insert contributions
            if contribution_data:
                execute_values(cur, """
                    INSERT INTO contributions (
                        id, reference_number, election_id, contributor_id, recipient_id,
                        amount, transaction_date, payment_method
                    )
                    VALUES %s
                    ON CONFLICT (reference_number) DO NOTHING
                """, contribution_data, template="""(%s, %s, %s, %s, %s, %s, %s, %s)""")
                
                self.conn.commit()
                self.stats['total_processed'] += len(contribution_data)
            
            # Report progress
            batch_time = time.time() - batch_start
            elapsed = time.time() - self.stats['start_time']
            rate = len(contribution_data) / batch_time if batch_time > 0 else 0
            
            print(f"Batch {batch_num + 1}/{total_batches}: "
                  f"Imported {len(contribution_data):,} records in {batch_time:.1f}s "
                  f"({rate:.0f} rec/sec) | "
                  f"Total: {self.stats['total_processed']:,} | "
                  f"Elapsed: {elapsed/60:.1f} min")
            
            # Save progress
            with open('logs/import_progress.txt', 'w') as f:
                f.write(f"Continuous Import Progress\n")
                f.write(f"========================\n")
                f.write(f"Processed: {self.stats['total_processed']:,} new records\n")
                f.write(f"Batch: {batch_num + 1}/{total_batches}\n")
                f.write(f"Rate: {rate:.0f} records/sec\n")
                f.write(f"Elapsed: {elapsed/60:.1f} minutes\n")
                f.write(f"Updated: {datetime.now()}\n")
        
        # Final stats
        cur.execute("SELECT COUNT(*) FROM contributions")
        final_count = cur.fetchone()[0]
        
        print("\n" + "=" * 80)
        print(f"IMPORT COMPLETED!")
        print(f"Total imported: {self.stats['total_processed']:,} new records")
        print(f"Total time: {elapsed/60:.1f} minutes")
        print(f"Final contribution count: {final_count:,}")
        
        cur.close()
        self.conn.close()

if __name__ == "__main__":
    importer = ContinuousImporter()
    importer.import_all_remaining()