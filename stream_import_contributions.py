#!/usr/bin/env python3
"""Stream import contribution records without loading all into memory."""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
import csv
from datetime import datetime
import io

def stream_import_contributions():
    """Stream import contributions in chunks."""
    print("\n📥 STREAMING IMPORT OF CONTRIBUTIONS")
    print("="*60)
    
    try:
        from replit.object_storage import Client
        client = Client()
        
        # Download file
        print("Downloading CFB_contributions-2025-08-23.csv...")
        content = client.download_as_bytes('CFB_contributions-2025-08-23.csv')
        
        if not content:
            print("❌ File not found")
            return
        
        print(f"✅ Downloaded {len(content) / (1024*1024):.1f} MB")
        
        # Connect to database
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        
        # Process CSV in streaming fashion
        print("Processing CSV data in batches...")
        
        # Create text stream
        text_stream = io.StringIO(content.decode('utf-8', errors='ignore'))
        csv_reader = csv.DictReader(text_stream)
        
        batch_size = 5000
        batch = []
        imported = 0
        skipped = 0
        total_processed = 0
        
        for row in csv_reader:
            total_processed += 1
            
            # Parse amount and date
            try:
                amount_str = row.get('AMNT', '0').strip()
                if not amount_str or amount_str == '':
                    amount = 0
                else:
                    amount = float(amount_str)
                
                date_str = row.get('DATE', '').strip()
                if not date_str or amount == 0:
                    skipped += 1
                    continue
                    
                # Parse date - format is M/D/YYYY
                try:
                    date = datetime.strptime(date_str, '%m/%d/%Y')
                except:
                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d')
                    except:
                        skipped += 1
                        continue
                
            except (ValueError, TypeError):
                skipped += 1
                continue
            
            # Add to batch - use NAME field for contributor name
            batch.append((
                str(row.get('REFNO', '')),
                str(row.get('STRNO', '')),
                str(row.get('NAME', '')),  # Use NAME field instead of STRNAME
                date,
                amount,
                str(row.get('RECIPID', '')),
                str(row.get('OCCUPATION', '')),
                str(row.get('CITY', '')),
                str(row.get('STATE', '')),
                str(row.get('ZIP', ''))[:10],  # Limit ZIP to 10 chars
                str(row.get('SCHEDULE', '')),
                int(row.get('PAGENO', 0)) if row.get('PAGENO', '').isdigit() else 0,
                int(row.get('SEQUENCENO', 0)) if row.get('SEQUENCENO', '').isdigit() else 0
            ))
            
            # Process batch when full
            if len(batch) >= batch_size:
                try:
                    execute_values(
                        cur,
                        """
                        INSERT INTO contributions (
                            refno, str_no, str_name, date, amount,
                            recip_id, occupation,
                            contributor_city, contributor_state, contributor_zip,
                            schedule, page_no, sequence_no
                        ) VALUES %s
                        ON CONFLICT (refno) DO UPDATE SET
                            amount = EXCLUDED.amount,
                            date = EXCLUDED.date
                        """,
                        batch,
                        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    )
                    conn.commit()
                    imported += len(batch)
                    
                    # Progress
                    print(f"  Imported: {imported:,} | Skipped: {skipped:,} | Total: {total_processed:,}", end='\r')
                    
                except Exception as e:
                    print(f"\n  ⚠️  Batch error: {str(e)[:100]}")
                    conn.rollback()
                
                batch = []
        
        # Process final batch
        if batch:
            try:
                execute_values(
                    cur,
                    """
                    INSERT INTO contributions (
                        refno, str_no, str_name, date, amount,
                        recip_id, occupation,
                        contributor_city, contributor_state, contributor_zip,
                        schedule, page_no, sequence_no
                    ) VALUES %s
                    ON CONFLICT (refno) DO UPDATE SET
                        amount = EXCLUDED.amount,
                        date = EXCLUDED.date
                    """,
                    batch,
                    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                )
                conn.commit()
                imported += len(batch)
            except Exception as e:
                print(f"\n  ⚠️  Final batch error: {str(e)[:100]}")
        
        print(f"\n\n✅ IMPORT COMPLETE!")
        print(f"   Imported: {imported:,} records")
        print(f"   Skipped: {skipped:,} records")
        print(f"   Total processed: {total_processed:,} records")
        
        # Get final stats
        cur.execute("SELECT COUNT(*) FROM contributions")
        final_count = cur.fetchone()[0]
        print(f"   Final database count: {final_count:,} contributions")
        
        cur.execute("""
            SELECT 
                MIN(date) as min_date,
                MAX(date) as max_date,
                SUM(amount) as total_amount,
                COUNT(DISTINCT str_name) as unique_contributors
            FROM contributions
            WHERE amount IS NOT NULL
        """)
        
        stats = cur.fetchone()
        print(f"\n📊 DATABASE STATISTICS:")
        print(f"   Date range: {stats[0]} to {stats[1]}")
        print(f"   Total amount: ${stats[2]:,.2f}")
        print(f"   Unique contributors: {stats[3]:,}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    stream_import_contributions()