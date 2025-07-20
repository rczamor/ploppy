"""Run data import with detailed logging."""

import sys
import os
from db_manager_v2 import NYCCFBDatabase
import pandas as pd

print("Starting data import investigation...")

# Initialize database
db = NYCCFBDatabase()

# Connect to object storage
print("\nConnecting to object storage...")
if not db.connect_to_object_storage(''):
    print("Failed to connect to object storage")
    sys.exit(1)

# Check available files
print("\nChecking available files...")
try:
    # Get the CSV file
    csv_filename = 'CFB_20250718173623479.csv'
    
    print(f"\nDownloading {csv_filename}...")
    df = db.download_csv_to_dataframe(csv_filename)
    
    print(f"\nCSV file statistics:")
    print(f"  Total rows: {len(df):,}")
    print(f"  Columns: {len(df.columns)}")
    print(f"  Memory usage: {df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")
    
    # Check for any filters that might limit data
    print("\nChecking data range:")
    if 'DATE' in df.columns:
        df['DATE_PARSED'] = pd.to_datetime(df['DATE'], errors='coerce')
        print(f"  Date range: {df['DATE_PARSED'].min()} to {df['DATE_PARSED'].max()}")
        print(f"  Records with valid dates: {df['DATE_PARSED'].notna().sum():,}")
    
    # Check current database state
    print("\nCurrent database state:")
    stats = db.get_database_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Check if import was interrupted
    print("\nChecking last imported record...")
    last_contrib = db.execute_query("""
        SELECT reference_number, sequence_number, transaction_date
        FROM contributions
        ORDER BY transaction_date DESC, sequence_number DESC NULLS LAST
        LIMIT 1
    """)
    
    if not last_contrib.empty:
        print(f"  Last contribution: {last_contrib.iloc[0].to_dict()}")
        
        # Check if this reference exists in CSV
        if 'REFNO' in df.columns:
            last_ref = last_contrib.iloc[0]['reference_number']
            matching_rows = df[df['REFNO'] == last_ref]
            print(f"  Matching rows in CSV for ref {last_ref}: {len(matching_rows)}")
    
    # Check for any batch limits
    print("\nChecking import method...")
    print(f"  Default batch size: 1000")
    
    # Test importing a small batch
    print("\nTesting small batch import (5 records)...")
    test_batch = df.head(5)
    
    # Skip already imported records
    existing_refs = db.execute_query("SELECT DISTINCT reference_number FROM contributions WHERE reference_number IS NOT NULL")
    if not existing_refs.empty:
        existing_ref_list = existing_refs['reference_number'].tolist()
        test_batch = df[~df['REFNO'].isin(existing_ref_list)].head(5)
    
    if len(test_batch) > 0:
        results = db.import_contributions_batch(test_batch, batch_size=5)
        print(f"  Test import results: {results}")
    else:
        print("  All test records already imported")
    
    # Check if there are more records to import
    print("\nChecking remaining records...")
    if 'REFNO' in df.columns:
        existing_refs = db.execute_query("SELECT DISTINCT reference_number FROM contributions WHERE reference_number IS NOT NULL")
        if not existing_refs.empty:
            imported_refs = set(existing_refs['reference_number'].tolist())
            csv_refs = set(df['REFNO'].dropna().tolist())
            remaining = csv_refs - imported_refs
            print(f"  Total CSV records: {len(df):,}")
            print(f"  Unique references in CSV: {len(csv_refs):,}")
            print(f"  Already imported references: {len(imported_refs):,}")
            print(f"  Remaining to import: {len(remaining):,}")
        else:
            print(f"  No imported references found, {len(df):,} records to import")
    
except Exception as e:
    print(f"\nError during investigation: {e}")
    import traceback
    traceback.print_exc()