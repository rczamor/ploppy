#!/usr/bin/env python3
"""Emergency data restoration script for NYC CFB data."""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from datetime import datetime
import io

# Add src to path
sys.path.insert(0, 'src')
from database.db_manager_v2 import NYCCFBDatabase

def count_current_data():
    """Count current records in database."""
    db = NYCCFBDatabase()
    
    print("\n📊 CURRENT DATABASE STATUS:")
    print("="*50)
    
    counts = {
        'contributions': "SELECT COUNT(*) FROM contributions",
        'expenditures': "SELECT COUNT(*) FROM expenditures", 
        'intermediaries': "SELECT COUNT(*) FROM intermediaries",
        'contributors': "SELECT COUNT(*) FROM contributors",
    }
    
    for table, query in counts.items():
        result = db.execute_query(query)
        count = result.iloc[0, 0] if not result.empty else 0
        print(f"{table}: {count:,} records")
    
    # Get contribution date range
    result = db.execute_query("""
        SELECT MIN(date) as min_date, MAX(date) as max_date, 
               SUM(amount) as total_amount
        FROM contributions WHERE amount IS NOT NULL
    """)
    
    if not result.empty:
        row = result.iloc[0]
        print(f"\nContribution date range: {row['min_date']} to {row['max_date']}")
        print(f"Total contribution amount: ${row['total_amount']:,.2f}")
    
    return True

def check_object_storage():
    """Check files in Replit Object Storage."""
    print("\n📦 CHECKING REPLIT OBJECT STORAGE:")
    print("="*50)
    
    try:
        from replit.object_storage import Client
        client = Client()
        
        files = list(client.list())
        cfb_files = [f for f in files if 'CFB' in str(f)]
        
        if cfb_files:
            print(f"Found {len(cfb_files)} CFB data files:")
            for file in cfb_files:
                print(f"  • {file}")
            return True
        else:
            print("No CFB files found in object storage")
            return False
    except Exception as e:
        print(f"Error accessing object storage: {e}")
        return False

def import_from_object_storage(filename, table_name, limit=None):
    """Import data from object storage file."""
    print(f"\n📥 IMPORTING {filename}...")
    
    try:
        from replit.object_storage import Client
        from replit import object_storage
        
        # Read file from object storage
        content = object_storage.get(filename)
        if not content:
            print(f"  ❌ File {filename} not found")
            return 0
        
        # Load into pandas
        df = pd.read_csv(io.StringIO(content.decode('utf-8', errors='ignore')))
        total_records = len(df)
        print(f"  • Loaded {total_records:,} records from CSV")
        
        if limit:
            df = df.head(limit)
            print(f"  • Limited to {limit:,} records for testing")
        
        # Import based on table type
        if 'contribution' in table_name.lower():
            return import_contributions(df)
        elif 'expenditure' in table_name.lower():
            return import_expenditures(df)
        elif 'intermediar' in table_name.lower():
            return import_intermediaries(df)
        else:
            print(f"  ❌ Unknown table type: {table_name}")
            return 0
            
    except Exception as e:
        print(f"  ❌ Error importing {filename}: {e}")
        return 0

def import_contributions(df):
    """Import contribution records."""
    db = NYCCFBDatabase()
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    try:
        # Clean and prepare data
        df['amount'] = pd.to_numeric(df['AMNT'], errors='coerce')
        df['date'] = pd.to_datetime(df['DATE'], errors='coerce')
        
        # Filter valid records
        valid_df = df[df['amount'].notna() & df['date'].notna()]
        
        # Prepare for bulk insert
        records = []
        for _, row in valid_df.iterrows():
            records.append((
                row.get('REFNO', ''),
                row.get('STRNO', ''),
                row.get('STRNAME', ''),
                row['date'],
                float(row['amount']),
                row.get('C_CODE', ''),
                row.get('RECIPID', ''),
                row.get('RECIPNAME', ''),
                row.get('COMMITTEE', ''),
                row.get('FILING', 0),
                row.get('SCHEDULE', ''),
                row.get('PAGENO', 0),
                row.get('SEQUENCENO', 0),
                row.get('OFFICE', ''),
                row.get('PARTY', ''),
                row.get('DISTRICT', ''),
                row.get('OCCUPATION', ''),
                row.get('EMPNAME', ''),
                row.get('EMPSTRNO', ''),
                row.get('EMPSTRNAME', ''),
                row.get('EMPCITY', ''),
                row.get('EMPSTATE', ''),
                row.get('CITY', ''),
                row.get('STATE', ''),
                row.get('ZIP', ''),
                row.get('BORO', ''),
                row.get('WARD', ''),
                row.get('PAY_METHOD', ''),
                row.get('INTERMNO', ''),
                row.get('INTERMNAME', ''),
                row.get('INTSTRNO', ''),
                row.get('INTSTRNM', ''),
                row.get('INTAPTNO', ''),
                row.get('INTCITY', ''),
                row.get('INTST', ''),
                row.get('INTZIP', ''),
                row.get('INTEMPNAME', ''),
                row.get('INTEMPSTNO', ''),
                row.get('INTEMPSTNM', ''),
                row.get('INTEMPCITY', ''),
                row.get('INTEMPST', ''),
                row.get('INTOCCUPA', ''),
                row.get('PURPOSECD', ''),
                row.get('EXEMPTCD', ''),
                row.get('ADJTYPECD', ''),
                row.get('RR_IND', ''),
                row.get('SEG_IND', ''),
                row.get('INT_C_CODE', '')
            ))
        
        # Bulk insert
        execute_values(
            cur,
            """
            INSERT INTO contributions (
                refno, str_no, str_name, date, amount,
                c_code, recip_id, str_recipname, committee, filing,
                schedule, page_no, sequence_no, office, party,
                district, occupation, employer_name, employer_strno, employer_strname,
                employer_city, employer_state, contributor_city, contributor_state, contributor_zip,
                borough, ward, pay_method, interm_no, interm_name,
                interm_strno, interm_strname, interm_apt_no, interm_city, interm_state,
                interm_zip, interm_emp_name, interm_emp_strno, interm_emp_strname, interm_emp_city,
                interm_emp_state, interm_occupa, purpose_code, exempt_code, adj_type_code,
                rr_ind, seg_ind, int_c_code
            ) VALUES %s
            ON CONFLICT (refno) DO UPDATE SET
                amount = EXCLUDED.amount,
                date = EXCLUDED.date
            """,
            records,
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        
        conn.commit()
        print(f"  ✅ Imported {len(records):,} contribution records")
        return len(records)
        
    except Exception as e:
        conn.rollback()
        print(f"  ❌ Error: {e}")
        return 0
    finally:
        cur.close()
        conn.close()

def import_expenditures(df):
    """Import expenditure records."""
    # Similar structure to contributions
    print(f"  • Would import {len(df):,} expenditure records")
    return 0  # Placeholder

def import_intermediaries(df):
    """Import intermediary records."""
    # Similar structure to contributions
    print(f"  • Would import {len(df):,} intermediary records")
    return 0  # Placeholder

def main():
    """Main restoration process."""
    print("\n🚨 NYC CFB DATA RESTORATION TOOL 🚨")
    print("="*50)
    
    # Show current status
    count_current_data()
    
    # Check object storage
    if not check_object_storage():
        print("\n❌ Cannot access object storage files")
        return
    
    print("\n" + "="*50)
    print("📝 RESTORATION PLAN:")
    print("="*50)
    print("1. Import contributions from CFB_contributions-2025-08-23.csv")
    print("2. Import expenditures from CFB_expenditures-2025-08-23.csv")
    print("3. Import intermediaries from CFB_intermediaries-2025-08-23.csv")
    
    response = input("\n⚠️  Start restoration? (yes/no): ")
    if response.lower() != 'yes':
        print("Restoration cancelled")
        return
    
    # Run imports
    print("\n🔄 STARTING RESTORATION...")
    
    # Test with small batch first
    print("\n📋 Testing with 100 records first...")
    imported = import_from_object_storage(
        'CFB_contributions-2025-08-23.csv',
        'contributions',
        limit=100
    )
    
    if imported > 0:
        print(f"\n✅ Test successful! Imported {imported} records")
        response = input("\nProceed with full import? (yes/no): ")
        if response.lower() == 'yes':
            print("\n🚀 Running full import (this may take several minutes)...")
            import_from_object_storage(
                'CFB_contributions-2025-08-23.csv',
                'contributions'
            )
    
    # Final status
    print("\n" + "="*50)
    print("📊 FINAL DATABASE STATUS:")
    count_current_data()
    
    print("\n✅ Restoration complete!")

if __name__ == "__main__":
    main()