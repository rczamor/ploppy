"""Super-fast background import using PostgreSQL COPY and bulk operations."""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
import time
import uuid
from io import StringIO
import threading
import queue

DATABASE_URL = os.environ.get('DATABASE_URL')

class SuperFastImporter:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self.conn.autocommit = False
        self.processed_refs = set()
        self.contributor_cache = {}
        self.recipient_cache = {}
        self.stats = {
            'total_processed': 0,
            'start_time': time.time(),
            'last_update': time.time()
        }
    
    def get_existing_data(self):
        """Cache existing data to avoid duplicates."""
        print("Loading existing data...")
        cur = self.conn.cursor()
        
        # Get existing contributions
        cur.execute("SELECT reference_number FROM contributions")
        self.processed_refs = set(row[0] for row in cur.fetchall())
        print(f"Found {len(self.processed_refs):,} existing contributions")
        
        # Cache contributors
        cur.execute("SELECT normalized_name, id FROM contributors")
        self.contributor_cache = {row[0]: row[1] for row in cur.fetchall()}
        print(f"Cached {len(self.contributor_cache):,} contributors")
        
        # Cache recipients
        cur.execute("SELECT recipid, id FROM recipients")
        self.recipient_cache = {row[0]: row[1] for row in cur.fetchall()}
        print(f"Cached {len(self.recipient_cache):,} recipients")
        
        cur.close()
    
    def normalize_name(self, name):
        """Fast name normalization."""
        if pd.isna(name) or not name:
            return "ANONYMOUS CONTRIBUTOR"
        return str(name).upper().strip()
    
    def process_batch(self, df_batch):
        """Process a batch of contributions super fast."""
        cur = self.conn.cursor()
        
        # Filter out already processed
        df_new = df_batch[~df_batch['REFNO'].isin(self.processed_refs)]
        if len(df_new) == 0:
            return 0
        
        # Prepare data (use .loc to avoid warnings)
        df_new = df_new.copy()  # Create explicit copy
        df_new.loc[:, 'NAME'] = df_new['NAME'].fillna('Anonymous Contributor')
        df_new.loc[:, 'RECIPNAME'] = df_new['RECIPNAME'].fillna('Unknown Recipient')
        df_new.loc[:, 'NORM_NAME'] = df_new['NAME'].apply(self.normalize_name)
        df_new.loc[:, 'TRANS_DATE'] = pd.to_datetime(df_new['DATE'], errors='coerce')
        df_new.loc[:, 'AMOUNT_NUM'] = pd.to_numeric(df_new['AMNT'], errors='coerce').fillna(0)
        
        # Get unique contributors not in cache
        new_contributors = df_new[['NORM_NAME', 'NAME', 'C_CODE']].drop_duplicates('NORM_NAME')
        new_contributors = new_contributors[~new_contributors['NORM_NAME'].isin(self.contributor_cache)]
        
        if len(new_contributors) > 0:
            # Bulk insert new contributors
            contributor_data = []
            for _, row in new_contributors.iterrows():
                contrib_id = str(uuid.uuid4())
                self.contributor_cache[row['NORM_NAME']] = contrib_id
                contributor_data.append((
                    contrib_id,
                    row['NAME'],
                    row['NORM_NAME'],
                    row['C_CODE'] or 'UNKN',
                    'Individual' if row['C_CODE'] == 'IND' else 'Other',
                    row['C_CODE'] == 'IND'
                ))
            
            execute_values(cur, """
                INSERT INTO contributors (id, full_name, normalized_name, c_code, contributor_type, is_individual)
                VALUES %s
            """, contributor_data)
        
        # Get unique recipients not in cache
        new_recipients = df_new[['RECIPID', 'RECIPNAME']].drop_duplicates('RECIPID')
        new_recipients = new_recipients[~new_recipients['RECIPID'].isin(self.recipient_cache)]
        
        if len(new_recipients) > 0:
            # Bulk insert new recipients
            recipient_data = []
            for _, row in new_recipients.iterrows():
                recip_id = str(uuid.uuid4())
                self.recipient_cache[row['RECIPID']] = recip_id
                recipient_data.append((
                    recip_id,
                    row['RECIPID'],
                    row['RECIPNAME'],
                    self.normalize_name(row['RECIPNAME']),
                    'Candidate',
                    True
                ))
            
            execute_values(cur, """
                INSERT INTO recipients (id, recipid, full_name, normalized_name, recipient_type, is_individual)
                VALUES %s
            """, recipient_data)
        
        # Get default election
        cur.execute("SELECT id FROM elections ORDER BY election_year DESC LIMIT 1")
        election_id = cur.fetchone()
        if not election_id:
            election_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO elections (id, election_year, election_type)
                VALUES (%s, 2025, 'General')
            """, (election_id,))
        else:
            election_id = election_id[0]
        
        # Prepare contributions for bulk insert
        contribution_data = []
        for _, row in df_new.iterrows():
            if row['AMOUNT_NUM'] == 0 and pd.isna(row['TRANS_DATE']):
                continue  # Skip invalid records
                
            contrib_id = self.contributor_cache.get(row['NORM_NAME'])
            recip_id = self.recipient_cache.get(row['RECIPID'])
            
            if contrib_id and recip_id:
                # Handle date properly
                trans_date = row['TRANS_DATE'] if pd.notna(row['TRANS_DATE']) else None
                
                contribution_data.append((
                    str(uuid.uuid4()),
                    row['REFNO'],
                    election_id,
                    contrib_id,
                    recip_id,
                    row['AMOUNT_NUM'],
                    trans_date,
                    1,  # payment_method
                    int(row.get('SEQUENCENO')) if pd.notna(row.get('SEQUENCENO')) and str(row.get('SEQUENCENO')).isdigit() else None
                ))
        
        # Bulk insert contributions
        if contribution_data:
            execute_values(cur, """
                INSERT INTO contributions (
                    id, reference_number, election_id, contributor_id, recipient_id,
                    amount, transaction_date, payment_method, sequence_number
                )
                VALUES %s
            """, contribution_data, template="""(%s, %s, %s, %s, %s, %s, %s, %s, %s)""")
            
            # Update processed refs
            for data in contribution_data:
                self.processed_refs.add(data[1])
        
        # Commit the batch
        self.conn.commit()
        
        cur.close()
        return len(contribution_data)
    
    def import_all_data(self):
        """Import all data in super-fast mode."""
        print(f"\nStarting SUPER-FAST import at {datetime.now()}")
        print("=" * 80)
        
        # Load existing data
        self.get_existing_data()
        
        # Load CSV
        print("\nLoading CSV data...")
        from db_manager_v2 import NYCCFBDatabase
        db = NYCCFBDatabase()
        db.connect_to_object_storage('')
        df = db.download_csv_to_dataframe('CFB_20250718173623479.csv')
        
        if df.empty:
            print("No data found")
            return
        
        print(f"Total CSV records: {len(df):,}")
        df.columns = df.columns.str.strip()
        
        # Process in large batches
        batch_size = 25000  # Very large batches
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        print(f"\nProcessing {total_batches} batches of {batch_size:,} records...")
        print("This will run continuously until complete.\n")
        
        for batch_num in range(total_batches):
            batch_start = time.time()
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df))
            
            batch_df = df.iloc[start_idx:end_idx]
            imported = self.process_batch(batch_df)
            
            self.stats['total_processed'] += imported
            batch_time = time.time() - batch_start
            
            if imported > 0:
                rate = imported / batch_time if batch_time > 0 else 0
                elapsed = time.time() - self.stats['start_time']
                
                print(f"Batch {batch_num + 1}/{total_batches}: "
                      f"Imported {imported:,} records in {batch_time:.1f}s "
                      f"({rate:.0f} rec/sec) | "
                      f"Total: {self.stats['total_processed']:,} | "
                      f"Elapsed: {elapsed/60:.1f} min")
                
                # Save progress every 10 batches
                if batch_num % 10 == 0:
                    with open('import_progress.txt', 'w') as f:
                        f.write(f"Processed: {self.stats['total_processed']:,}\n")
                        f.write(f"Batch: {batch_num + 1}/{total_batches}\n")
                        f.write(f"Rate: {rate:.0f} records/sec\n")
                        f.write(f"Updated: {datetime.now()}\n")
        
        # Final stats
        elapsed = time.time() - self.stats['start_time']
        print("\n" + "=" * 80)
        print(f"IMPORT COMPLETED!")
        print(f"Total imported: {self.stats['total_processed']:,} records")
        print(f"Total time: {elapsed/60:.1f} minutes")
        print(f"Average rate: {self.stats['total_processed']/elapsed:.0f} records/second")
        
        # Final database stats
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM contributions")
        total_contributions = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM contributors")
        total_contributors = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM recipients")
        total_recipients = cur.fetchone()[0]
        
        print(f"\nFinal database state:")
        print(f"  Total contributions: {total_contributions:,}")
        print(f"  Total contributors: {total_contributors:,}")
        print(f"  Total recipients: {total_recipients:,}")
        
        cur.close()
        self.conn.close()

if __name__ == "__main__":
    importer = SuperFastImporter()
    importer.import_all_data()