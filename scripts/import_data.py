"""Import NYC Campaign Finance Board data into the new database schema."""

import pandas as pd
import sys
from datetime import datetime
from db_manager_v2 import NYCCFBDatabase
import os

def import_cfb_data(bucket_id: str = '', csv_filename: str = 'CFB_20250718173623479.csv'):
    """Import CFB data into the new database schema."""
    
    print(f"Starting NYC CFB data import at {datetime.now()}")
    print("=" * 80)
    
    # Initialize database
    db = NYCCFBDatabase()
    
    # Connect to object storage
    if not db.connect_to_object_storage(bucket_id):
        print("Failed to connect to object storage")
        return False
    
    # Get initial database stats
    print("\nInitial database statistics:")
    stats = db.get_database_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Download CSV data
    print(f"\nDownloading {csv_filename} from object storage...")
    df = db.download_csv_to_dataframe(csv_filename)
    
    if df.empty:
        print("No data found in CSV file")
        return False
    
    print(f"\nLoaded {len(df)} contribution records")
    print(f"Columns: {', '.join(df.columns[:10])}...")
    
    # Show sample of data
    print("\nSample data (first 3 rows):")
    print(df[['NAME', 'RECIPNAME', 'AMNT', 'DATE']].head(3))
    
    # Clean up column names (remove any extra spaces)
    df.columns = df.columns.str.strip()
    
    # Import data in batches
    batch_size = 1000
    total_batches = (len(df) + batch_size - 1) // batch_size
    
    print(f"\nImporting data in {total_batches} batches of {batch_size} records each...")
    
    total_imported = 0
    total_failed = 0
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(df))
        
        batch_df = df.iloc[start_idx:end_idx]
        
        print(f"\nProcessing batch {batch_num + 1}/{total_batches} (rows {start_idx}-{end_idx})...")
        
        # Import the batch
        results = db.import_contributions_batch(batch_df, batch_size)
        
        total_imported += results['successful_imports']
        total_failed += results['failed_imports']
        
        print(f"  Imported: {results['successful_imports']}")
        print(f"  Failed: {results['failed_imports']}")
        
        if results['errors']:
            print(f"  Sample errors: {results['errors'][:3]}")
        
        # Show progress every 10 batches
        if (batch_num + 1) % 10 == 0:
            print(f"\nProgress: {total_imported} successfully imported, {total_failed} failed")
    
    # Get final database stats
    print("\n" + "=" * 80)
    print("Import completed!")
    print(f"Total records processed: {len(df)}")
    print(f"Successfully imported: {total_imported}")
    print(f"Failed imports: {total_failed}")
    print(f"Success rate: {(total_imported / len(df) * 100):.1f}%")
    
    print("\nFinal database statistics:")
    final_stats = db.get_database_stats()
    for key, value in final_stats.items():
        print(f"  {key}: {value}")
    
    # Show some sample imported data
    print("\nSample imported contributions:")
    sample_query = """
        SELECT 
            c.transaction_date,
            contrib.last_name || ', ' || contrib.first_name as contributor_name,
            contrib.contributor_type,
            r.office_name,
            r.last_name || ', ' || r.first_name as recipient_name,
            c.amount,
            c.payment_method_desc,
            l.borough_name
        FROM contributions c
        JOIN contributors contrib ON c.contributor_id = contrib.id
        JOIN recipients r ON c.recipient_id = r.id
        LEFT JOIN locations l ON c.location_id = l.id
        ORDER BY c.transaction_date DESC
        LIMIT 5
    """
    
    try:
        sample_df = db.execute_query(sample_query)
        print(sample_df.to_string(index=False))
    except Exception as e:
        print(f"Could not fetch sample data: {e}")
    
    return True


if __name__ == "__main__":
    # Get bucket ID from environment or command line
    bucket_id = os.environ.get('BUCKET_ID', '')
    if len(sys.argv) > 1:
        bucket_id = sys.argv[1]
    
    # Run import
    success = import_cfb_data(bucket_id)
    
    if success:
        print("\nData import completed successfully!")
        sys.exit(0)
    else:
        print("\nData import failed!")
        sys.exit(1)