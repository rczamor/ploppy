#!/usr/bin/env python3
"""Add geographic fields to contributors, org_contributors, and voters tables."""

import psycopg2
import os
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL')

def add_geographic_fields():
    """Add city, state, zip, and geocoding fields to tables."""
    print(f"\n{'='*80}")
    print(f"ADDING GEOGRAPHIC FIELDS - Started at {datetime.now()}")
    print(f"{'='*80}")
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Step 1: Drop the locations table and its relationships
        print("\n1. Cleaning up old location structure...")
        
        # Drop foreign key constraints first
        cur.execute("""
            ALTER TABLE contributions 
            DROP CONSTRAINT IF EXISTS contributions_location_id_fkey
        """)
        
        cur.execute("""
            ALTER TABLE contributors 
            DROP CONSTRAINT IF EXISTS contributors_location_id_fkey
        """)
        
        # Drop the columns
        cur.execute("""
            ALTER TABLE contributions 
            DROP COLUMN IF EXISTS location_id
        """)
        
        cur.execute("""
            ALTER TABLE contributors 
            DROP COLUMN IF EXISTS location_id
        """)
        
        # Drop the locations table
        cur.execute("DROP TABLE IF EXISTS locations CASCADE")
        
        conn.commit()
        print("   ✓ Removed old location structure")
        
        # Step 2: Add geographic fields to contributors table
        print("\n2. Adding geographic fields to contributors table...")
        
        # Check which columns already exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'contributors'
            AND column_name IN ('city', 'state', 'zip_code', 'latitude', 'longitude', 'geocoded_at')
        """)
        existing_cols = {row[0] for row in cur.fetchall()}
        
        # Add missing columns
        columns_to_add = []
        if 'city' not in existing_cols:
            columns_to_add.append("ADD COLUMN city VARCHAR(255)")
        if 'state' not in existing_cols:
            columns_to_add.append("ADD COLUMN state VARCHAR(2)")
        if 'zip_code' not in existing_cols:
            columns_to_add.append("ADD COLUMN zip_code VARCHAR(10)")
        if 'latitude' not in existing_cols:
            columns_to_add.append("ADD COLUMN latitude DECIMAL(10, 8)")
        if 'longitude' not in existing_cols:
            columns_to_add.append("ADD COLUMN longitude DECIMAL(11, 8)")
        if 'geocoded_at' not in existing_cols:
            columns_to_add.append("ADD COLUMN geocoded_at TIMESTAMP")
        
        if columns_to_add:
            cur.execute(f"ALTER TABLE contributors {', '.join(columns_to_add)}")
            print(f"   ✓ Added {len(columns_to_add)} columns to contributors")
        else:
            print("   ✓ All columns already exist in contributors")
        
        # Create indexes for geographic fields
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_contributors_zip_code 
            ON contributors(zip_code)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_contributors_city_state 
            ON contributors(city, state)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_contributors_lat_lng 
            ON contributors(latitude, longitude)
        """)
        
        conn.commit()
        
        # Step 3: Add geographic fields to org_contributors table
        print("\n3. Adding geographic fields to org_contributors table...")
        
        # Check which columns already exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'org_contributors'
            AND column_name IN ('city', 'state', 'zip_code', 'latitude', 'longitude', 'geocoded_at')
        """)
        existing_cols = {row[0] for row in cur.fetchall()}
        
        # Add missing columns
        columns_to_add = []
        if 'city' not in existing_cols:
            columns_to_add.append("ADD COLUMN city VARCHAR(255)")
        if 'state' not in existing_cols:
            columns_to_add.append("ADD COLUMN state VARCHAR(2)")
        if 'zip_code' not in existing_cols:
            columns_to_add.append("ADD COLUMN zip_code VARCHAR(10)")
        if 'latitude' not in existing_cols:
            columns_to_add.append("ADD COLUMN latitude DECIMAL(10, 8)")
        if 'longitude' not in existing_cols:
            columns_to_add.append("ADD COLUMN longitude DECIMAL(11, 8)")
        if 'geocoded_at' not in existing_cols:
            columns_to_add.append("ADD COLUMN geocoded_at TIMESTAMP")
        
        if columns_to_add:
            cur.execute(f"ALTER TABLE org_contributors {', '.join(columns_to_add)}")
            print(f"   ✓ Added {len(columns_to_add)} columns to org_contributors")
        else:
            print("   ✓ All columns already exist in org_contributors")
        
        # Create indexes for geographic fields
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_org_contributors_zip_code 
            ON org_contributors(zip_code)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_org_contributors_city_state 
            ON org_contributors(city, state)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_org_contributors_lat_lng 
            ON org_contributors(latitude, longitude)
        """)
        
        conn.commit()
        
        # Step 4: Add geocoding fields to voters table
        print("\n4. Adding geocoding fields to voters table...")
        
        # Check which columns already exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'voters'
            AND column_name IN ('latitude', 'longitude', 'geocoded_at')
        """)
        existing_cols = {row[0] for row in cur.fetchall()}
        
        # Add missing columns
        columns_to_add = []
        if 'latitude' not in existing_cols:
            columns_to_add.append("ADD COLUMN latitude DECIMAL(10, 8)")
        if 'longitude' not in existing_cols:
            columns_to_add.append("ADD COLUMN longitude DECIMAL(11, 8)")
        if 'geocoded_at' not in existing_cols:
            columns_to_add.append("ADD COLUMN geocoded_at TIMESTAMP")
        
        if columns_to_add:
            cur.execute(f"ALTER TABLE voters {', '.join(columns_to_add)}")
            print(f"   ✓ Added {len(columns_to_add)} columns to voters")
        else:
            print("   ✓ All columns already exist in voters")
        
        # Create indexes for geocoding fields
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_voters_lat_lng 
            ON voters(latitude, longitude)
        """)
        
        conn.commit()
        
        # Step 5: Add geographic fields to contributions table for tracking
        print("\n5. Adding geographic fields to contributions table...")
        
        # Check which columns already exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'contributions'
            AND column_name IN ('contributor_city', 'contributor_state', 'contributor_zip')
        """)
        existing_cols = {row[0] for row in cur.fetchall()}
        
        # Add missing columns
        columns_to_add = []
        if 'contributor_city' not in existing_cols:
            columns_to_add.append("ADD COLUMN contributor_city VARCHAR(255)")
        if 'contributor_state' not in existing_cols:
            columns_to_add.append("ADD COLUMN contributor_state VARCHAR(2)")
        if 'contributor_zip' not in existing_cols:
            columns_to_add.append("ADD COLUMN contributor_zip VARCHAR(10)")
        
        if columns_to_add:
            cur.execute(f"ALTER TABLE contributions {', '.join(columns_to_add)}")
            print(f"   ✓ Added {len(columns_to_add)} columns to contributions")
        else:
            print("   ✓ All columns already exist in contributions")
        
        # Create indexes for geographic fields
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_contributions_zip 
            ON contributions(contributor_zip)
        """)
        
        conn.commit()
        
        print(f"\n{'='*80}")
        print("GEOGRAPHIC FIELDS ADDED SUCCESSFULLY")
        print(f"{'='*80}")
        
        # Show final statistics
        print("\nDatabase structure updated:")
        print("  ✓ contributors table: city, state, zip_code, latitude, longitude, geocoded_at")
        print("  ✓ org_contributors table: city, state, zip_code, latitude, longitude, geocoded_at")
        print("  ✓ voters table: latitude, longitude, geocoded_at")
        print("  ✓ contributions table: contributor_city, contributor_state, contributor_zip")
        print("\nReady for data import and geocoding!")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    add_geographic_fields()