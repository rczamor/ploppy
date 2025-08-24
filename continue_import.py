#!/usr/bin/env python3
"""Continue importing contributions from where we left off."""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
import csv
from datetime import datetime
import io

def continue_import():
    """Continue importing remaining contributions."""
    print("\n📥 CONTINUING CONTRIBUTION IMPORT")
    print("="*60)
    
    try:
        from replit.object_storage import Client
        client = Client()
        
        # Connect to database
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        
        # Get existing refnos to skip
        print("Checking existing records...")
        cur.execute("SELECT refno FROM contributions")
        existing_refnos = set(row[0] for row in cur.fetchall())
        print(f"✅ Found {len(existing_refnos):,} existing records to skip")
        
        # Download file
        print("\nDownloading CFB_contributions-2025-08-23.csv...")
        content = client.download_as_bytes('CFB_contributions-2025-08-23.csv')
        
        if not content:
            print("❌ File not found")
            return
        
        print(f"✅ Downloaded {len(content) / (1024*1024):.1f} MB")
        
        # Process CSV
        print("\nProcessing remaining records...")
        text_stream = io.StringIO(content.decode('utf-8', errors='ignore'))
        csv_reader = csv.DictReader(text_stream)
        
        batch_size = 2000
        batch = []
        imported = 0
        skipped = 0
        already_exists = 0
        total_processed = 0
        
        for row in csv_reader:
            total_processed += 1
            
            # Skip if already exists
            refno = str(row.get('REFNO', ''))
            if refno in existing_refnos:
                already_exists += 1
                continue
            
            # Parse amount and date
            try:
                amount_str = row.get('AMNT', '0').strip()
                if not amount_str or amount_str == '':
                    skipped += 1
                    continue
                amount = float(amount_str)
                
                if amount == 0:
                    skipped += 1
                    continue
                
                date_str = row.get('DATE', '').strip()
                if not date_str:
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
                
                if not refno:
                    skipped += 1
                    continue
                
                batch.append((
                    refno,
                    str(row.get('STRNO', '')),
                    str(row.get('NAME', '')),
                    date,
                    amount,
                    str(row.get('RECIPID', '')),
                    str(row.get('OCCUPATION', '')),
                    str(row.get('CITY', '')),
                    str(row.get('STATE', '')),
                    str(row.get('ZIP', ''))[:10],
                    str(row.get('SCHEDULE', '')),
                    int(row.get('PAGENO', 0)) if row.get('PAGENO', '').isdigit() else 0,
                    int(row.get('SEQUENCENO', 0)) if row.get('SEQUENCENO', '').isdigit() else 0
                ))
                
            except (ValueError, TypeError):
                skipped += 1
                continue
            
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
                        """,
                        batch,
                        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    )
                    conn.commit()
                    imported += len(batch)
                    
                    # Progress
                    print(f"  New: {imported:,} | Existing: {already_exists:,} | Skipped: {skipped:,} | Total: {total_processed:,}", end='\r')
                    
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
                    """,
                    batch,
                    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                )
                conn.commit()
                imported += len(batch)
            except Exception as e:
                print(f"\n  ⚠️  Final batch error: {str(e)[:100]}")
        
        print(f"\n\n✅ IMPORT COMPLETE!")
        print(f"   Newly imported: {imported:,} records")
        print(f"   Already existed: {already_exists:,} records")
        print(f"   Skipped (no amount/date): {skipped:,} records")
        print(f"   Total processed: {total_processed:,} records")
        
        # Get final stats
        cur.execute("SELECT COUNT(*) FROM contributions")
        final_count = cur.fetchone()[0]
        print(f"\n📊 FINAL DATABASE COUNT: {final_count:,} contributions")
        
        cur.execute("""
            SELECT 
                MIN(date) as min_date,
                MAX(date) as max_date,
                SUM(amount) as total_amount,
                COUNT(DISTINCT str_name) as unique_contributors,
                AVG(amount) as avg_amount
            FROM contributions
            WHERE amount IS NOT NULL
        """)
        
        stats = cur.fetchone()
        print(f"\n📊 DATABASE STATISTICS:")
        print(f"   Date range: {stats[0]} to {stats[1]}")
        print(f"   Total amount: ${stats[2]:,.2f}")
        print(f"   Unique contributors: {stats[3]:,}")
        print(f"   Average contribution: ${stats[4]:,.2f}")
        
        # Show year breakdown
        cur.execute("""
            SELECT 
                EXTRACT(YEAR FROM date) as year,
                COUNT(*) as count,
                SUM(amount) as total
            FROM contributions
            WHERE date IS NOT NULL
            GROUP BY year
            ORDER BY year DESC
            LIMIT 10
        """)
        
        print(f"\n📅 TOP 10 YEARS BY CONTRIBUTIONS:")
        for row in cur.fetchall():
            print(f"   {int(row[0])}: {row[1]:,} contributions, ${row[2]:,.2f}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    continue_import()