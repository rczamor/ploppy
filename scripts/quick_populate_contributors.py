#!/usr/bin/env python3
"""Quick script to populate contributors from contributions."""

import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
import uuid

DATABASE_URL = os.environ.get('DATABASE_URL')

def main():
    print("Creating contributors from contributions...")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    try:
        # Get unique contributors from contributions
        cur.execute("""
            SELECT DISTINCT
                str_name,
                contributor_city,
                contributor_state,
                contributor_zip,
                occupation,
                COUNT(*) as contribution_count,
                SUM(amount) as total_contributions,
                AVG(amount) as avg_contribution
            FROM contributions
            WHERE str_name IS NOT NULL
            GROUP BY str_name, contributor_city, contributor_state, contributor_zip, occupation
            LIMIT 10000
        """)
        
        unique_contributors = cur.fetchall()
        print(f"Found {len(unique_contributors)} unique contributors")
        
        # Insert as contributors
        contributor_data = []
        for row in unique_contributors:
            name = row[0]
            
            # Parse name (simple split)
            name_parts = name.split(' ')
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
            else:
                first_name = ''
                last_name = name
            
            contributor_data.append((
                str(uuid.uuid4()),  # id
                name,  # full_name
                last_name,  # last_name
                first_name,  # first_name
                name.upper(),  # normalized_name
                'INDIVIDUAL',  # contributor_type
                row[1],  # city
                row[2],  # state
                row[3],  # zip_code
                row[4],  # occupation
                float(row[6]) if row[6] else 0,  # total_contributions
                int(row[5]),  # contribution_count
                float(row[7]) if row[7] else 0,  # avg_contribution
                datetime.now(),  # created_at
                datetime.now()  # updated_at
            ))
        
        # Insert contributors
        execute_values(cur, """
            INSERT INTO contributors 
            (id, full_name, last_name, first_name, normalized_name, contributor_type,
             city, state, zip_code, occupation, total_contributions, contribution_count,
             avg_contribution, created_at, updated_at)
            VALUES %s
            ON CONFLICT DO NOTHING
        """, contributor_data, page_size=1000)
        
        conn.commit()
        
        # Check results
        cur.execute("SELECT COUNT(*) FROM contributors")
        count = cur.fetchone()[0]
        print(f"✓ Created {count} contributors")
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()