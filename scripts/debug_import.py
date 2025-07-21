"""Debug the import failure."""

from db_manager_v2 import NYCCFBDatabase
import pandas as pd
import traceback

db = NYCCFBDatabase()
db.connect_to_object_storage('')

# Get a sample record that should import
df = db.download_csv_to_dataframe('CFB_20250718173623479.csv')
df.columns = df.columns.str.strip()

# Get one record that hasn't been imported
existing_refs = db.execute_query('SELECT DISTINCT reference_number FROM contributions WHERE reference_number IS NOT NULL')
imported_refs = set(existing_refs['reference_number'].tolist())
new_df = df[~df['REFNO'].isin(imported_refs)]

if len(new_df) > 0:
    # Test with first record
    test_row = new_df.iloc[0]
    print("Testing import of single record:")
    print(f"REFNO: {test_row.get('REFNO')}")
    print(f"NAME: {test_row.get('NAME')}")
    print(f"RECIPNAME: {test_row.get('RECIPNAME')}")
    print(f"AMNT: {test_row.get('AMNT')}")
    print(f"DATE: {test_row.get('DATE')}")
    
    # Try to import with detailed error catching
    try:
        # Test each step of the import
        print("\n1. Testing get_or_create_election...")
        election_id = db.get_or_create_election(test_row.get('ELECTION', ''))
        print(f"   Election ID: {election_id}")
        
        print("\n2. Testing get_or_create_contributor...")
        contributor_id = db.get_or_create_contributor(test_row)
        print(f"   Contributor ID: {contributor_id}")
        
        print("\n3. Testing get_or_create_recipient...")
        recipient_id = db.get_or_create_recipient(test_row)
        print(f"   Recipient ID: {recipient_id}")
        
        if contributor_id and recipient_id:
            print("\n4. Testing full import_contribution_row...")
            success = db.import_contribution_row(test_row)
            print(f"   Import success: {success}")
        else:
            print("\nMissing required IDs - cannot import")
            
    except Exception as e:
        print(f"\nError during import test: {e}")
        traceback.print_exc()
        
    # Check what's in the required columns
    print("\n\nChecking data quality:")
    print(f"Columns in CSV: {list(df.columns[:20])}")
    print(f"\nNull counts for key columns:")
    for col in ['NAME', 'RECIPNAME', 'AMNT', 'DATE', 'ELECTION', 'REFNO']:
        if col in df.columns:
            null_count = df[col].isna().sum()
            print(f"  {col}: {null_count:,} nulls ({null_count/len(df)*100:.1f}%)")
else:
    print("All records already imported!")