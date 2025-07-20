#!/usr/bin/env python3
"""Script to import political contribution data from object storage to PostgreSQL."""

import pandas as pd
import io
from db_manager import PoliticalContributionDB
import sys

def main():
    # Create database instance
    db = PoliticalContributionDB()
    
    # Connect to object storage
    print("Connecting to object storage...")
    if not db.connect_to_object_storage(''):
        print("Failed to connect to object storage")
        return
    
    filename = 'CFB_20250718173623479.csv'
    print(f"\nProcessing file: {filename}")
    
    # Download file content
    try:
        print("Downloading file content...")
        csv_content = db.storage_client.download_as_text(filename)
        
        # Read only necessary columns to save memory
        columns_needed = ['NAME', 'RECIPNAME', 'AMNT', 'DATE', 'CITY', 'STATE', 'ZIP', 
                          'OCCUPATION', 'EMPNAME', 'ELECTION', 'OFFICECD', 'CANCLASS']
        
        # Process in chunks
        chunk_size = 25000
        total_imported = 0
        total_failed = 0
        
        print(f"\nProcessing data in chunks of {chunk_size} records...")
        
        # Create StringIO object for chunk reading
        csv_buffer = io.StringIO(csv_content)
        
        for i, chunk in enumerate(pd.read_csv(csv_buffer, 
                                            usecols=columns_needed, 
                                            chunksize=chunk_size,
                                            low_memory=False)):
            
            print(f"\n--- Chunk {i+1} ({len(chunk)} records) ---")
            
            # Map columns
            mapped_chunk = db.map_cfb_columns(chunk)
            
            # Filter valid records
            valid_chunk = mapped_chunk[
                mapped_chunk['donor_name'].notna() & 
                mapped_chunk['recipient'].notna() & 
                (mapped_chunk['amount'] > 0)
            ]
            
            if len(valid_chunk) > 0:
                print(f"Valid records: {len(valid_chunk)}")
                
                # Import this chunk
                result = db.import_contributions_from_dataframe(valid_chunk, batch_size=500)
                total_imported += result['successful_imports']
                total_failed += result['failed_imports']
                
                print(f"Imported: {result['successful_imports']}, Failed: {result['failed_imports']}")
                
                # Show progress
                if total_imported % 10000 == 0:
                    stats = db.get_database_stats()
                    print(f"\nProgress - Total imported: {total_imported}")
                    print(f"Database totals: Donors: {stats['donors_count']}, Recipients: {stats['recipients_count']}")
            
            # Limit to first 200k records for initial import
            if total_imported >= 200000:
                print("\nReached 200,000 record limit for initial import")
                break
        
        print(f"\n{'='*50}")
        print(f"Import Complete!")
        print(f"Total records imported: {total_imported}")
        print(f"Total records failed: {total_failed}")
        
        # Final database statistics
        stats = db.get_database_stats()
        print("\nFinal Database Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # Show sample data
        print("\nSample contributions:")
        sample_query = '''
            SELECT 
                d.name as donor, 
                d.donor_type,
                r.name as recipient, 
                r.recipient_type,
                c.amount, 
                c.transaction_date,
                l.city || ', ' || l.state as location
            FROM contributions c
            JOIN donors d ON c.donor_id = d.id
            JOIN recipients r ON c.recipient_id = r.id
            JOIN locations l ON c.location_id = l.id
            ORDER BY c.amount DESC
            LIMIT 10
        '''
        sample_data = db.execute_graph_query(sample_query)
        print(sample_data.to_string())
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()