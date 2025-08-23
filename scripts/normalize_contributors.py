#!/usr/bin/env python3
"""Normalize contributor data - separate organizations and parse individual names."""

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
import os
import re
from datetime import datetime
import uuid

DATABASE_URL = os.environ.get('DATABASE_URL')

def title_case(text):
    """Convert text to title case, handling special cases."""
    if not text or not isinstance(text, str):
        return text
    
    # Handle all caps or all lowercase
    text = text.strip()
    
    # Special cases for common name prefixes
    if text.upper() in ['MC', 'MAC', 'DE', 'LA', 'VAN', 'VON', 'DI', 'DA']:
        return text.capitalize()
    
    # Handle hyphenated names
    if '-' in text:
        parts = text.split('-')
        return '-'.join(p.title() for p in parts)
    
    # Handle apostrophes (O'Brien, D'Angelo)
    if "'" in text:
        parts = text.split("'")
        return "'".join(p.title() for p in parts)
    
    return text.title()

def parse_individual_name(full_name):
    """Parse individual full name into components."""
    if not full_name:
        return None, None, None
    
    # Clean the name
    full_name = full_name.strip()
    
    # Remove quotes and special characters at the beginning/end
    full_name = re.sub(r'^["\'"]+|["\'"]+$', '', full_name)
    
    # Check if it's in "LAST, FIRST [MIDDLE]" format
    if ',' in full_name:
        parts = full_name.split(',', 1)
        last_name = parts[0].strip()
        
        if len(parts) > 1:
            # Split first and middle names
            first_parts = parts[1].strip().split(None, 1)
            first_name = first_parts[0] if first_parts else ''
            middle_name = first_parts[1] if len(first_parts) > 1 else ''
            
            # Extract middle initial if middle name is longer
            middle_initial = middle_name[0] if middle_name else ''
        else:
            first_name = ''
            middle_initial = ''
    else:
        # Try to parse "FIRST [MIDDLE] LAST" format (less common in this dataset)
        parts = full_name.split()
        if len(parts) == 1:
            # Only one name, assume it's last name
            last_name = parts[0]
            first_name = ''
            middle_initial = ''
        elif len(parts) == 2:
            first_name = parts[0]
            last_name = parts[1]
            middle_initial = ''
        else:
            # 3 or more parts
            first_name = parts[0]
            last_name = parts[-1]
            # Everything in between is middle name(s)
            middle_parts = parts[1:-1]
            middle_initial = middle_parts[0][0] if middle_parts else ''
    
    # Apply title case
    last_name = title_case(last_name)
    first_name = title_case(first_name)
    middle_initial = middle_initial.upper() if middle_initial else ''
    
    return last_name, first_name, middle_initial

def normalize_contributors():
    """Main normalization function."""
    print(f"\n{'='*80}")
    print(f"CONTRIBUTOR DATA NORMALIZATION - Started at {datetime.now()}")
    print(f"{'='*80}")
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        # Step 1: Create org_contributors table
        print("\n1. Creating org_contributors table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS org_contributors (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                full_name VARCHAR(500),
                normalized_name VARCHAR(500),
                organization_type VARCHAR(100),
                c_code VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for efficient lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_org_contributors_normalized_name 
            ON org_contributors(normalized_name)
        """)
        
        conn.commit()
        print("   ✓ Table created")
        
        # Step 2: Add location_id to contributors if not exists
        print("\n2. Adding location_id to contributors table...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'contributors' 
            AND column_name = 'location_id'
        """)
        
        if not cur.fetchone():
            cur.execute("""
                ALTER TABLE contributors 
                ADD COLUMN location_id UUID REFERENCES locations(id)
            """)
            cur.execute("""
                CREATE INDEX idx_contributors_location_id 
                ON contributors(location_id)
            """)
            conn.commit()
            print("   ✓ location_id column added")
        else:
            print("   ✓ location_id column already exists")
        
        # Step 3: Move organizations to org_contributors table
        print("\n3. Moving organizations to org_contributors table...")
        
        # Get organizations that aren't already in org_contributors
        cur.execute("""
            SELECT id, full_name, normalized_name, contributor_type, c_code
            FROM contributors
            WHERE is_individual = false
        """)
        
        orgs = cur.fetchall()
        print(f"   Found {len(orgs):,} organizations to move")
        
        if orgs:
            # Prepare data for bulk insert
            org_records = []
            org_id_mapping = {}  # Old ID -> New ID mapping
            
            for org in orgs:
                new_id = str(uuid.uuid4())
                org_id_mapping[org[0]] = new_id
                org_records.append((
                    new_id,
                    org[1],  # full_name
                    org[2],  # normalized_name
                    org[3],  # contributor_type -> organization_type
                    org[4]   # c_code
                ))
            
            # Bulk insert organizations
            execute_values(cur, """
                INSERT INTO org_contributors (id, full_name, normalized_name, organization_type, c_code)
                VALUES %s
                ON CONFLICT (id) DO NOTHING
            """, org_records, page_size=1000)
            
            print(f"   ✓ Inserted {len(org_records):,} organizations")
            
            # Update contributions to point to org_contributors
            print("   Updating contribution references...")
            
            # Create a temporary mapping table
            cur.execute("""
                CREATE TEMP TABLE org_id_mapping (
                    old_id UUID,
                    new_id UUID
                )
            """)
            
            # Insert mappings
            mapping_records = [(old_id, new_id) for old_id, new_id in org_id_mapping.items()]
            execute_values(cur, """
                INSERT INTO org_id_mapping (old_id, new_id)
                VALUES %s
            """, mapping_records)
            
            # Add org_contributor_id column to contributions if not exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'contributions' 
                AND column_name = 'org_contributor_id'
            """)
            
            if not cur.fetchone():
                cur.execute("""
                    ALTER TABLE contributions 
                    ADD COLUMN org_contributor_id UUID REFERENCES org_contributors(id)
                """)
                cur.execute("""
                    CREATE INDEX idx_contributions_org_contributor_id 
                    ON contributions(org_contributor_id)
                """)
            
            # Update contributions to use org_contributor_id for organizations
            cur.execute("""
                UPDATE contributions c
                SET org_contributor_id = m.new_id,
                    contributor_id = NULL
                FROM org_id_mapping m
                WHERE c.contributor_id = m.old_id
            """)
            
            affected = cur.rowcount
            print(f"   ✓ Updated {affected:,} contribution records")
            
            # Delete organizations from contributors table
            cur.execute("""
                DELETE FROM contributors
                WHERE is_individual = false
            """)
            
            deleted = cur.rowcount
            print(f"   ✓ Removed {deleted:,} organizations from contributors table")
            
            conn.commit()
        
        # Step 4: Parse and update individual contributor names
        print("\n4. Parsing individual contributor names...")
        
        # Get all individuals with unparsed names
        cur.execute("""
            SELECT id, full_name
            FROM contributors
            WHERE is_individual = true
            AND (first_name IS NULL OR first_name = '' 
                 OR last_name IS NULL OR last_name = '')
            ORDER BY id
        """)
        
        individuals = cur.fetchall()
        print(f"   Found {len(individuals):,} individuals to parse")
        
        if individuals:
            # Prepare updates
            updates = []
            batch_size = 5000
            
            for i, (contrib_id, full_name) in enumerate(individuals):
                last_name, first_name, middle_initial = parse_individual_name(full_name)
                
                if last_name or first_name:  # Only update if we got something
                    updates.append((
                        last_name or '',
                        first_name or '',
                        middle_initial or '',
                        contrib_id
                    ))
                
                # Process in batches
                if len(updates) >= batch_size or i == len(individuals) - 1:
                    if updates:
                        execute_values(cur, """
                            UPDATE contributors AS c
                            SET last_name = v.last_name,
                                first_name = v.first_name,
                                middle_initial = v.middle_initial
                            FROM (VALUES %s) AS v(last_name, first_name, middle_initial, id)
                            WHERE c.id = v.id::uuid
                        """, updates, page_size=1000)
                        
                        print(f"   Processed {i+1:,}/{len(individuals):,} names...")
                        updates = []
            
            conn.commit()
            print(f"   ✓ Updated {len(individuals):,} individual names")
        
        # Step 5: Update location relationships for contributors
        print("\n5. Updating contributor location relationships...")
        
        # Link contributors to their most common contribution location
        cur.execute("""
            WITH contributor_locations AS (
                SELECT 
                    contributor_id,
                    location_id,
                    COUNT(*) as location_count,
                    ROW_NUMBER() OVER (PARTITION BY contributor_id ORDER BY COUNT(*) DESC) as rn
                FROM contributions
                WHERE contributor_id IS NOT NULL
                AND location_id IS NOT NULL
                GROUP BY contributor_id, location_id
            )
            UPDATE contributors c
            SET location_id = cl.location_id
            FROM contributor_locations cl
            WHERE c.id = cl.contributor_id
            AND cl.rn = 1
            AND c.location_id IS NULL
        """)
        
        updated = cur.rowcount
        print(f"   ✓ Updated {updated:,} contributor locations")
        
        conn.commit()
        
        # Final statistics
        print(f"\n{'='*80}")
        print("NORMALIZATION COMPLETE")
        print(f"{'='*80}")
        
        # Get final counts
        cur.execute("SELECT COUNT(*) FROM contributors WHERE is_individual = true")
        individual_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM org_contributors")
        org_count = cur.fetchone()[0]
        
        cur.execute("""
            SELECT COUNT(*) FROM contributors 
            WHERE is_individual = true 
            AND first_name IS NOT NULL 
            AND first_name != ''
        """)
        parsed_count = cur.fetchone()[0]
        
        print(f"\nFinal Statistics:")
        print(f"  Individual contributors: {individual_count:,}")
        print(f"  Organization contributors: {org_count:,}")
        print(f"  Individuals with parsed names: {parsed_count:,}")
        print(f"  Parse rate: {(parsed_count/individual_count*100):.1f}%")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    normalize_contributors()