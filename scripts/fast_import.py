"""Fast import with better progress tracking."""

import pandas as pd
import sys
from datetime import datetime
from db_manager_v2 import NYCCFBDatabase
import time
from sqlalchemy import text
import uuid

def fast_bulk_import():
    """Fast bulk import using direct SQL inserts."""
    
    print(f"Starting fast NYC CFB data import at {datetime.now()}")
    print("=" * 80)
    
    # Initialize database
    db = NYCCFBDatabase()
    
    # Connect to object storage
    if not db.connect_to_object_storage(''):
        print("Failed to connect to object storage")
        return False
    
    # Get current counts
    stats = db.get_database_stats()
    print("\nCurrent database state:")
    print(f"  Contributions: {stats.get('contributions_count', 0):,}")
    print(f"  Contributors: {stats.get('contributors_count', 0):,}")
    
    # Download CSV
    csv_filename = 'CFB_20250718173623479.csv'
    print(f"\nDownloading {csv_filename}...")
    df = db.download_csv_to_dataframe(csv_filename)
    
    if df.empty:
        print("No data found")
        return False
    
    print(f"Total CSV records: {len(df):,}")
    df.columns = df.columns.str.strip()
    
    # Get already imported records
    print("\nChecking imported records...")
    imported_count = db.execute_query("SELECT COUNT(*) as count FROM contributions").iloc[0]['count']
    print(f"Already imported: {imported_count:,} contributions")
    
    # Process in larger batches
    batch_size = 5000  # Much larger batches
    start_time = time.time()
    
    # Skip first N records that were already imported
    if imported_count > 0:
        # Get the last imported sequence number
        last_seq = db.execute_query("""
            SELECT MAX(CAST(sequence_number AS INTEGER)) as max_seq 
            FROM contributions 
            WHERE sequence_number IS NOT NULL
        """).iloc[0]['max_seq']
        
        if last_seq:
            print(f"Resuming from sequence number: {last_seq}")
            # Filter to records after this sequence
            df['SEQUENCENO_INT'] = pd.to_numeric(df['SEQUENCENO'], errors='coerce')
            df_to_import = df[df['SEQUENCENO_INT'] > last_seq].copy()
        else:
            # Use reference number approach
            existing_refs = db.execute_query("SELECT DISTINCT reference_number FROM contributions WHERE reference_number IS NOT NULL")
            imported_refs = set(existing_refs['reference_number'].tolist())
            df_to_import = df[~df['REFNO'].isin(imported_refs)].copy()
    else:
        df_to_import = df.copy()
    
    print(f"Records to import: {len(df_to_import):,}")
    
    if len(df_to_import) == 0:
        print("All records already imported!")
        return True
    
    # Import in large batches
    total_imported = 0
    total_batches = (len(df_to_import) + batch_size - 1) // batch_size
    
    print(f"\nImporting in {total_batches} batches of {batch_size:,} records...")
    
    for batch_num in range(min(20, total_batches)):  # Process up to 20 batches (100k records)
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(df_to_import))
        batch_df = df_to_import.iloc[start_idx:end_idx]
        
        batch_start = time.time()
        
        # Import batch
        results = db.import_contributions_batch(batch_df, batch_size)
        total_imported += results['successful_imports']
        
        batch_time = time.time() - batch_start
        rate = results['successful_imports'] / batch_time if batch_time > 0 else 0
        
        print(f"\nBatch {batch_num + 1}/{min(20, total_batches)}:")
        print(f"  Imported: {results['successful_imports']:,} records in {batch_time:.1f}s")
        print(f"  Rate: {rate:.0f} records/sec")
        print(f"  Total imported so far: {total_imported:,}")
        
        # Small delay between batches
        time.sleep(0.5)
    
    # Final stats
    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"Import session completed in {elapsed/60:.1f} minutes")
    print(f"Imported {total_imported:,} records")
    print(f"Average rate: {total_imported/elapsed:.0f} records/sec")
    
    # Show final counts
    final_stats = db.get_database_stats()
    print("\nFinal database state:")
    print(f"  Contributions: {final_stats.get('contributions_count', 0):,}")
    print(f"  Contributors: {final_stats.get('contributors_count', 0):,}")
    
    return True


if __name__ == "__main__":
    # Kill any existing import processes
    import subprocess
    subprocess.run("pkill -f resume_import.py", shell=True)
    
    # Run fast import
    success = fast_bulk_import()
    
    if success:
        print("\nImport completed successfully!")
        print("Run again to import more records.")
    else:
        print("\nImport failed!")
        sys.exit(1)