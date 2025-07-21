"""Resume the interrupted data import."""

import pandas as pd
import sys
from datetime import datetime
from db_manager_v2 import NYCCFBDatabase
import time

def resume_import():
    """Resume importing CFB data from where it left off."""
    
    print(f"Resuming NYC CFB data import at {datetime.now()}")
    print("=" * 80)
    
    # Initialize database
    db = NYCCFBDatabase()
    
    # Connect to object storage
    if not db.connect_to_object_storage(''):
        print("Failed to connect to object storage")
        return False
    
    # Get current database stats
    print("\nCurrent database statistics:")
    stats = db.get_database_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Download CSV data
    csv_filename = 'CFB_20250718173623479.csv'
    print(f"\nDownloading {csv_filename} from object storage...")
    df = db.download_csv_to_dataframe(csv_filename)
    
    if df.empty:
        print("No data found in CSV file")
        return False
    
    print(f"\nTotal records in CSV: {len(df):,}")
    
    # Clean up column names
    df.columns = df.columns.str.strip()
    
    # Get already imported reference numbers
    print("\nChecking already imported records...")
    existing_refs = db.execute_query("""
        SELECT DISTINCT reference_number 
        FROM contributions 
        WHERE reference_number IS NOT NULL
    """)
    
    if not existing_refs.empty:
        imported_refs = set(existing_refs['reference_number'].tolist())
        print(f"Already imported: {len(imported_refs):,} unique reference numbers")
        
        # Filter out already imported records
        df_to_import = df[~df['REFNO'].isin(imported_refs)]
        print(f"Records remaining to import: {len(df_to_import):,}")
    else:
        df_to_import = df
        print(f"No previous imports found, importing all {len(df_to_import):,} records")
    
    if len(df_to_import) == 0:
        print("\nAll records have already been imported!")
        return True
    
    # Import data in batches
    batch_size = 1000
    total_batches = (len(df_to_import) + batch_size - 1) // batch_size
    
    print(f"\nImporting data in {total_batches} batches of {batch_size} records each...")
    print("This may take a while for 1.6M records...")
    
    total_imported = 0
    total_failed = 0
    start_time = time.time()
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(df_to_import))
        
        batch_df = df_to_import.iloc[start_idx:end_idx]
        
        # Import the batch
        results = db.import_contributions_batch(batch_df, batch_size)
        
        total_imported += results['successful_imports']
        total_failed += results['failed_imports']
        
        # Progress update
        if (batch_num + 1) % 10 == 0 or batch_num == 0:
            elapsed = time.time() - start_time
            rate = total_imported / elapsed if elapsed > 0 else 0
            eta = (len(df_to_import) - (end_idx)) / rate if rate > 0 else 0
            
            print(f"\nBatch {batch_num + 1}/{total_batches}:")
            print(f"  Progress: {end_idx:,}/{len(df_to_import):,} records")
            print(f"  Imported: {total_imported:,} | Failed: {total_failed:,}")
            print(f"  Rate: {rate:.0f} records/sec | ETA: {eta/60:.1f} minutes")
        
        # Add a small delay to avoid overwhelming the database
        if batch_num < total_batches - 1:
            time.sleep(0.1)
        
        # Stop after 100 batches for now (100,000 records) to test
        if batch_num >= 99:
            print("\nStopping after 100 batches for testing...")
            print("Run the script again to continue importing.")
            break
    
    # Get final database stats
    elapsed_total = time.time() - start_time
    print("\n" + "=" * 80)
    print("Import batch completed!")
    print(f"Time elapsed: {elapsed_total/60:.1f} minutes")
    print(f"Records processed: {min(end_idx, len(df_to_import)):,}")
    print(f"Successfully imported: {total_imported:,}")
    print(f"Failed imports: {total_failed:,}")
    print(f"Success rate: {(total_imported / (total_imported + total_failed) * 100):.1f}%")
    
    print("\nFinal database statistics:")
    final_stats = db.get_database_stats()
    for key, value in final_stats.items():
        print(f"  {key}: {value}")
    
    return True


if __name__ == "__main__":
    success = resume_import()
    
    if success:
        print("\nImport batch completed successfully!")
    else:
        print("\nImport batch failed!")
        sys.exit(1)