"""Monitor import progress."""

import time
from db_manager_v2 import NYCCFBDatabase

db = NYCCFBDatabase()

print("Monitoring import progress...")
print("Press Ctrl+C to stop\n")

last_count = 0
while True:
    try:
        stats = db.get_database_stats()
        current_count = stats.get('contributions_count', 0)
        
        if current_count > last_count:
            added = current_count - last_count
            print(f"[{time.strftime('%H:%M:%S')}] Total: {current_count:,} contributions (+{added:,})")
            print(f"          Contributors: {stats.get('contributors_count', 0):,}")
            print(f"          Recipients: {stats.get('recipients_count', 0):,}")
            last_count = current_count
        
        time.sleep(5)
        
    except KeyboardInterrupt:
        print("\nStopped monitoring.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(10)