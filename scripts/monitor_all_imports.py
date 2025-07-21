"""Monitor all ongoing imports."""

import psycopg2
import os
from datetime import datetime
import time

DATABASE_URL = os.environ.get('DATABASE_URL')

def monitor_imports():
    """Monitor import progress for all data types."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    print("Monitoring all imports...")
    print("Press Ctrl+C to stop\n")
    
    start_counts = {}
    
    # Get initial counts
    cur.execute("SELECT COUNT(*) FROM contributions")
    start_counts['contributions'] = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM expenditures")
    start_counts['expenditures'] = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM intermediaries")
    start_counts['intermediaries'] = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM contributions WHERE intermediary_id IS NOT NULL")
    start_counts['contrib_with_interm'] = cur.fetchone()[0]
    
    while True:
        try:
            # Get current counts
            cur.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM contributions) as contributions,
                    (SELECT COUNT(*) FROM expenditures) as expenditures,
                    (SELECT COUNT(*) FROM intermediaries) as intermediaries,
                    (SELECT COUNT(*) FROM contributions WHERE intermediary_id IS NOT NULL) as contrib_with_interm,
                    (SELECT COUNT(DISTINCT contributor_id) FROM contributions) as unique_contributors,
                    (SELECT COUNT(DISTINCT recipient_id) FROM contributions) as unique_recipients,
                    (SELECT SUM(amount) FROM contributions) as contrib_amount,
                    (SELECT SUM(amount) FROM expenditures) as expend_amount
            """)
            
            counts = cur.fetchone()
            
            # Clear screen and display
            os.system('clear' if os.name == 'posix' else 'cls')
            print(f"NYC Campaign Finance Data Import Monitor")
            print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            
            print(f"\nCONTRIBUTIONS:")
            print(f"  Total: {counts[0]:,} (+{counts[0] - start_counts['contributions']:,})")
            print(f"  With Intermediaries: {counts[3]:,} (+{counts[3] - start_counts['contrib_with_interm']:,})")
            print(f"  Amount: ${counts[6]:,.2f}" if counts[6] else "  Amount: $0.00")
            
            print(f"\nEXPENDITURES:")
            print(f"  Total: {counts[1]:,} (+{counts[1] - start_counts['expenditures']:,})")
            print(f"  Amount: ${counts[7]:,.2f}" if counts[7] else "  Amount: $0.00")
            
            print(f"\nINTERMEDIARIES:")
            print(f"  Total: {counts[2]:,} (+{counts[2] - start_counts['intermediaries']:,})")
            
            print(f"\nUNIQUE ENTITIES:")
            print(f"  Contributors: {counts[4]:,}")
            print(f"  Recipients: {counts[5]:,}")
            
            # Check progress files
            print(f"\nIMPORT PROGRESS:")
            try:
                with open('expenditures_import_progress.txt', 'r') as f:
                    lines = f.readlines()
                    for line in lines[2:5]:  # Skip header lines
                        print(f"  Expenditures: {line.strip()}")
            except:
                pass
            
            time.sleep(5)  # Update every 5 seconds
            
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    monitor_imports()