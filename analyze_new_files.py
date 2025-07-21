"""Analyze the new data files to understand their structure."""

from db_manager_v2 import NYCCFBDatabase
import pandas as pd

def analyze_file(filename):
    """Download and analyze a file from object storage."""
    print(f"\n{'='*80}")
    print(f"Analyzing: {filename}")
    print('='*80)
    
    try:
        # Use existing database class to download
        db = NYCCFBDatabase()
        db.connect_to_object_storage('')
        df = db.download_csv_to_dataframe(filename)
        
        print(f"Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
        print(f"\nColumns ({len(df.columns)}):")
        for col in df.columns:
            # Show column name, non-null count, and data type
            non_null = df[col].count()
            pct_filled = (non_null / len(df) * 100) if len(df) > 0 else 0
            print(f"  - {col.strip()}: {non_null:,}/{len(df):,} ({pct_filled:.1f}% filled) - {df[col].dtype}")
        
        # Show sample records
        print(f"\nFirst 3 records:")
        print(df.head(3).to_string(max_columns=5))
        
        # Check for key identifiers
        print(f"\nKey Statistics:")
        if 'REFNO' in df.columns:
            print(f"  - Unique REFNO: {df['REFNO'].nunique():,}")
        if 'RECIPID' in df.columns:
            print(f"  - Unique Recipients: {df['RECIPID'].nunique():,}")
        if 'NAME' in df.columns:
            print(f"  - Unique Names: {df['NAME'].nunique():,}")
        if 'AMNT' in df.columns:
            total_amt = pd.to_numeric(df['AMNT'], errors='coerce').sum()
            print(f"  - Total Amount: ${total_amt:,.2f}")
            
        # Detect file type based on columns
        if 'PAYEE_NAME' in df.columns or 'EXPENDITURE' in df.columns:
            print("\n✓ This appears to be an EXPENDITURES file")
        elif 'INTERMEDIARY' in df.columns or 'INTER_NAME' in df.columns:
            print("\n✓ This appears to be an INTERMEDIARY CONTRIBUTIONS file")
        else:
            print("\n✓ This appears to be a standard CONTRIBUTIONS file")
            
    except Exception as e:
        print(f"Error analyzing {filename}: {e}")

# Analyze each new file
new_files = [
    'CFB_20250720195444115.csv',
    'CFB_20250720195643912.csv', 
    'CFB_20250720195729674.csv'
]

for file in new_files:
    analyze_file(file)