"""Run full NYC CFB data import with progress monitoring."""

import pandas as pd
import sys
from datetime import datetime
from db_manager_v2 import NYCCFBDatabase
import os
import time

def run_full_import():
    """Run the full data import with better error handling."""
    
    print(f"Starting FULL NYC CFB data import at {datetime.now()}")
    print("=" * 80)
    print("This will import approximately 1.6 million records...")
    print("Expected duration: 30-60 minutes")
    print("=" * 80)
    
    # Initialize database
    db = NYCCFBDatabase()
    
    # Connect to object storage
    if not db.connect_to_object_storage(''):
        print("Failed to connect to object storage")
        return False
    
    # Download CSV data
    print("\nDownloading CFB_20250718173623479.csv from object storage...")
    df = db.download_csv_to_dataframe('CFB_20250718173623479.csv')
    
    if df.empty:
        print("No data found in CSV file")
        return False
    
    print(f"\nLoaded {len(df):,} contribution records")
    
    # Clean up column names
    df.columns = df.columns.str.strip()
    
    # Import data in larger batches for efficiency
    batch_size = 5000  # Larger batches for faster import
    total_batches = (len(df) + batch_size - 1) // batch_size
    
    print(f"\nImporting data in {total_batches} batches of {batch_size:,} records each...")
    
    total_imported = 0
    total_failed = 0
    start_time = time.time()
    
    # Process all batches
    for batch_num in range(total_batches):
        batch_start = time.time()
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(df))
        
        batch_df = df.iloc[start_idx:end_idx]
        
        print(f"\nBatch {batch_num + 1}/{total_batches} (rows {start_idx:,}-{end_idx:,})...", end='', flush=True)
        
        # Import the batch
        results = db.import_contributions_batch(batch_df, batch_size)
        
        total_imported += results['successful_imports']
        total_failed += results['failed_imports']
        
        batch_time = time.time() - batch_start
        records_per_sec = results['successful_imports'] / batch_time if batch_time > 0 else 0
        
        print(f" Done! ({results['successful_imports']:,} imported, {results['failed_imports']:,} failed) - {records_per_sec:.0f} rec/sec")
        
        # Progress update every 20 batches
        if (batch_num + 1) % 20 == 0:
            elapsed = time.time() - start_time
            avg_speed = total_imported / elapsed if elapsed > 0 else 0
            remaining_records = len(df) - (batch_num + 1) * batch_size
            eta_seconds = remaining_records / avg_speed if avg_speed > 0 else 0
            eta_minutes = eta_seconds / 60
            
            print(f"\n--- Progress Report ---")
            print(f"Total imported: {total_imported:,} ({(total_imported/len(df)*100):.1f}%)")
            print(f"Total failed: {total_failed:,}")
            print(f"Average speed: {avg_speed:.0f} records/second")
            print(f"ETA: {eta_minutes:.1f} minutes")
            print(f"---")
    
    # Final summary
    total_time = time.time() - start_time
    print("\n" + "=" * 80)
    print("IMPORT COMPLETED!")
    print(f"Total time: {total_time/60:.1f} minutes")
    print(f"Total records processed: {len(df):,}")
    print(f"Successfully imported: {total_imported:,}")
    print(f"Failed imports: {total_failed:,}")
    print(f"Success rate: {(total_imported / len(df) * 100):.1f}%")
    print(f"Average speed: {total_imported / total_time:.0f} records/second")
    
    # Get final database stats
    print("\nFinal database statistics:")
    final_stats = db.get_database_stats()
    for key, value in final_stats.items():
        if value > 0:
            print(f"  {key}: {value:,}")
    
    # Show sample of imported data
    print("\nSample of imported contributions:")
    sample_query = """
        SELECT 
            c.transaction_date,
            contrib.last_name || ', ' || contrib.first_name as contributor_name,
            r.office_name,
            r.last_name || ', ' || r.first_name as recipient_name,
            c.amount,
            l.borough_name,
            l.state
        FROM contributions c
        JOIN contributors contrib ON c.contributor_id = contrib.id
        JOIN recipients r ON c.recipient_id = r.id
        LEFT JOIN locations l ON c.location_id = l.id
        WHERE c.transaction_date IS NOT NULL
        ORDER BY c.amount DESC
        LIMIT 10
    """
    
    try:
        sample_df = db.execute_query(sample_query)
        print(sample_df.to_string(index=False))
    except Exception as e:
        print(f"Could not fetch sample data: {e}")
    
    return True


if __name__ == "__main__":
    success = run_full_import()
    
    if success:
        print("\n✅ Data import completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Data import failed!")
        sys.exit(1)