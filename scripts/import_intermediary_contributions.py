"""Import contributions with intermediary data."""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
import time
import uuid

DATABASE_URL = os.environ.get('DATABASE_URL')

class IntermediaryContributionsImporter:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self.conn.autocommit = False
        self.stats = {
            'total_contributions': 0,
            'total_intermediaries': 0,
            'start_time': time.time()
        }
    
    def normalize_name(self, name):
        """Fast name normalization."""
        if pd.isna(name) or not name:
            return "ANONYMOUS"
        return str(name).upper().strip()
    
    def import_data(self):
        """Import contributions with intermediary data."""
        print(f"\nStarting INTERMEDIARY CONTRIBUTIONS import at {datetime.now()}")
        print("=" * 80)
        
        cur = self.conn.cursor()
        
        # Load CSV
        print("\nLoading intermediary contributions CSV...")
        import sys
        sys.path.append('..')
        from src.database.db_manager_v2 import NYCCFBDatabase
        db = NYCCFBDatabase()
        db.connect_to_object_storage('')
        df = db.download_csv_to_dataframe('CFB_20250720195729674.csv')
        
        print(f"Total records: {len(df):,}")
        df.columns = df.columns.str.strip()
        
        # Filter to records with intermediaries
        df_with_intermediary = df[df['INTERMNAME'].notna()].copy()
        print(f"Records with intermediaries: {len(df_with_intermediary):,}")
        
        # Get existing intermediaries
        cur.execute("SELECT DISTINCT intermediary_number, full_name FROM intermediaries WHERE intermediary_number IS NOT NULL")
        existing_intermediaries = set((str(row[0]), row[1]) for row in cur.fetchall())
        print(f"Existing intermediaries: {len(existing_intermediaries):,}")
        
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
        
        # Cache lookups
        print("Loading caches...")
        cur.execute("SELECT normalized_name, id FROM contributors")
        contrib_cache = dict(cur.fetchall())
        
        cur.execute("SELECT recipid, id FROM recipients")
        recip_cache = dict(cur.fetchall())
        
        cur.execute("SELECT intermediary_number || '_' || full_name, id FROM intermediaries")
        interm_cache = dict(cur.fetchall())
        
        # Process intermediary records in batches
        batch_size = 10000
        total_batches = (len(df_with_intermediary) + batch_size - 1) // batch_size
        
        print(f"\nProcessing {total_batches} batches...")
        
        for batch_num in range(total_batches):
            batch_start = time.time()
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(df_with_intermediary))
            
            batch_df = df_with_intermediary.iloc[start_idx:end_idx].copy()
            
            # Prepare data
            batch_df['TRANS_DATE'] = pd.to_datetime(batch_df['DATE'], errors='coerce')
            batch_df['REFUND_DATE_PARSED'] = pd.to_datetime(batch_df['REFUNDDATE'], errors='coerce')
            batch_df['AMOUNT_NUM'] = pd.to_numeric(batch_df['AMNT'], errors='coerce').fillna(0)
            batch_df['MATCH_AMOUNT_NUM'] = pd.to_numeric(batch_df['MATCHAMNT'], errors='coerce').fillna(0)
            batch_df['PREV_AMOUNT_NUM'] = pd.to_numeric(batch_df['PREVAMNT'], errors='coerce').fillna(0)
            
            # Process intermediaries first
            new_intermediaries = []
            for _, row in batch_df[['INTERMNO', 'INTERMNAME', 'INTCITY', 'INTST', 'INTZIP', 
                                   'INTEMPNAME', 'INTOCCUPA']].drop_duplicates().iterrows():
                if pd.notna(row['INTERMNAME']):
                    interm_key = f"{row['INTERMNO']}_{row['INTERMNAME']}"
                    if interm_key not in interm_cache:
                        new_id = str(uuid.uuid4())
                        new_intermediaries.append((
                            new_id,
                            str(int(row['INTERMNO'])) if pd.notna(row['INTERMNO']) else None,
                            row['INTERMNAME'],
                            self.normalize_name(row['INTERMNAME']),
                            'Individual',
                            row['INTCITY'] if pd.notna(row['INTCITY']) else None,
                            row['INTST'] if pd.notna(row['INTST']) else None,
                            row['INTZIP'] if pd.notna(row['INTZIP']) else None,
                            row['INTEMPNAME'] if pd.notna(row['INTEMPNAME']) else None,
                            row['INTOCCUPA'] if pd.notna(row['INTOCCUPA']) else None
                        ))
                        interm_cache[interm_key] = new_id
            
            # Insert new intermediaries
            if new_intermediaries:
                # Insert intermediaries one by one to handle duplicates
                for interm in new_intermediaries:
                    cur.execute("""
                        INSERT INTO intermediaries (
                            id, intermediary_number, full_name, normalized_name, intermediary_type,
                            city, state, zip, employer_name, occupation
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, interm)
                self.stats['total_intermediaries'] += len(new_intermediaries)
            
            # Process contributors and recipients
            for _, row in batch_df.iterrows():
                # Get or create contributor
                norm_name = self.normalize_name(row['NAME'])
                if norm_name not in contrib_cache:
                    contrib_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO contributors (id, full_name, normalized_name, contributor_type, is_individual)
                        VALUES (%s, %s, %s, 'Individual', true)
                        ON CONFLICT DO NOTHING
                    """, (contrib_id, row['NAME'], norm_name))
                    contrib_cache[norm_name] = contrib_id
                
                # Get or create recipient
                if pd.notna(row['RECIPID']) and row['RECIPID'] not in recip_cache:
                    recip_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO recipients (id, recipid, full_name, normalized_name, recipient_type, is_individual)
                        VALUES (%s, %s, %s, %s, 'Candidate', true)
                        ON CONFLICT DO NOTHING
                    """, (recip_id, row['RECIPID'], row['RECIPNAME'], self.normalize_name(row['RECIPNAME'])))
                    recip_cache[row['RECIPID']] = recip_id
            
            # Prepare contributions with intermediary data
            contributions = []
            for _, row in batch_df.iterrows():
                if row['AMOUNT_NUM'] == 0 and pd.isna(row['TRANS_DATE']):
                    continue
                
                contrib_id = contrib_cache.get(self.normalize_name(row['NAME']))
                recip_id = recip_cache.get(row['RECIPID'])
                interm_id = None
                
                if pd.notna(row['INTERMNAME']):
                    interm_key = f"{row['INTERMNO']}_{row['INTERMNAME']}"
                    interm_id = interm_cache.get(interm_key)
                
                if contrib_id and recip_id:
                    contributions.append((
                        str(uuid.uuid4()),
                        row['REFNO'],
                        election_id,
                        contrib_id,
                        recip_id,
                        interm_id,
                        row['AMOUNT_NUM'],
                        row['MATCH_AMOUNT_NUM'],
                        row['PREV_AMOUNT_NUM'],
                        row['TRANS_DATE'] if pd.notna(row['TRANS_DATE']) else None,
                        row['REFUND_DATE_PARSED'] if pd.notna(row['REFUND_DATE_PARSED']) else None,
                        int(row['PAY_METHOD']) if pd.notna(row['PAY_METHOD']) else 1,
                        row['PURPOSECD'] if pd.notna(row['PURPOSECD']) else None,
                        row['EXEMPTCD'] if pd.notna(row['EXEMPTCD']) else None,
                        int(row['ADJTYPECD']) if pd.notna(row['ADJTYPECD']) else None
                    ))
            
            # Bulk insert
            if contributions:
                execute_values(cur, """
                    INSERT INTO contributions (
                        id, reference_number, election_id, contributor_id, recipient_id,
                        intermediary_id, amount, match_amount, previous_amount,
                        transaction_date, refund_date, payment_method,
                        purpose_code, exemption_code, adjustment_type_code
                    )
                    VALUES %s
                    ON CONFLICT (reference_number) DO UPDATE SET
                        intermediary_id = EXCLUDED.intermediary_id,
                        match_amount = EXCLUDED.match_amount,
                        previous_amount = EXCLUDED.previous_amount,
                        purpose_code = EXCLUDED.purpose_code,
                        exemption_code = EXCLUDED.exemption_code,
                        adjustment_type_code = EXCLUDED.adjustment_type_code,
                        refund_date = EXCLUDED.refund_date
                """, contributions, template="""(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""")
                
                self.conn.commit()
                self.stats['total_contributions'] += len(contributions)
            
            # Progress
            elapsed = time.time() - self.stats['start_time']
            rate = len(contributions) / (time.time() - batch_start) if batch_start > 0 else 0
            
            print(f"Batch {batch_num + 1}/{total_batches}: "
                  f"{len(contributions):,} contributions @ {rate:.0f}/sec | "
                  f"Total: {self.stats['total_contributions']:,}")
        
        # Final stats
        cur.execute("SELECT COUNT(*) FROM intermediaries")
        total_intermediaries = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM contributions WHERE intermediary_id IS NOT NULL")
        total_with_intermediary = cur.fetchone()[0]
        
        print("\n" + "=" * 80)
        print(f"INTERMEDIARY IMPORT COMPLETED!")
        print(f"New intermediaries: {self.stats['total_intermediaries']:,}")
        print(f"Total intermediaries: {total_intermediaries:,}")
        print(f"Contributions with intermediaries: {total_with_intermediary:,}")
        
        cur.close()
        self.conn.close()

if __name__ == "__main__":
    importer = IntermediaryContributionsImporter()
    importer.import_data()