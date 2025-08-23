#!/usr/bin/env python3
"""Fast voter-contributor matching using geographic and name similarity."""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
from decimal import Decimal
import math

DATABASE_URL = os.environ.get('DATABASE_URL')

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate haversine distance between two points in miles."""
    if not all([lat1, lon1, lat2, lon2]):
        return None
    
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 3959  # Radius of Earth in miles
    
    return r * c

def main():
    print(f"\n{'='*80}")
    print(f"FAST VOTER-CONTRIBUTOR MATCHING - Started at {datetime.now()}")
    print(f"{'='*80}\n")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get counts
        cur.execute("SELECT COUNT(*) as count FROM voters WHERE latitude IS NOT NULL")
        geocoded_voters = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) as count FROM contributors WHERE latitude IS NOT NULL")
        geocoded_contributors = cur.fetchone()['count']
        
        print(f"Geocoded voters: {geocoded_voters:,}")
        print(f"Geocoded contributors: {geocoded_contributors:,}")
        
        if geocoded_voters == 0 or geocoded_contributors == 0:
            print("\nNeed geocoded data for matching! Run geocoding scripts first.")
            return
        
        # Create matches table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS voter_contributor_matches (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                voter_id VARCHAR(50) REFERENCES voters(voter_id),
                contributor_id UUID REFERENCES contributors(id),
                match_type VARCHAR(50),
                name_similarity FLOAT,
                distance_miles FLOAT,
                same_address BOOLEAN,
                same_zip BOOLEAN,
                confidence_score FLOAT,
                total_contributions DECIMAL(12,2),
                contribution_count INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Clear existing matches
        cur.execute("TRUNCATE TABLE voter_contributor_matches")
        conn.commit()
        
        print("\nPerforming geographic and name-based matching...")
        
        # Match by exact address first
        cur.execute("""
            INSERT INTO voter_contributor_matches 
            (voter_id, contributor_id, match_type, name_similarity, distance_miles, 
             same_address, same_zip, confidence_score, total_contributions, contribution_count)
            SELECT 
                v.voter_id,
                c.id as contributor_id,
                'exact_address' as match_type,
                similarity(
                    UPPER(v.first_name || ' ' || COALESCE(v.middle_name, '') || ' ' || v.last_name),
                    UPPER(c.first_name || ' ' || COALESCE(c.middle_name, '') || ' ' || c.last_name)
                ) as name_similarity,
                0 as distance_miles,
                true as same_address,
                true as same_zip,
                0.95 as confidence_score,
                c.total_contributions,
                c.contribution_count
            FROM voters v
            INNER JOIN contributors c ON 
                v.address = c.address 
                AND v.city = c.city
                AND v.zip = c.zip_code
                AND similarity(
                    UPPER(v.last_name),
                    UPPER(c.last_name)
                ) > 0.8
            WHERE v.latitude IS NOT NULL 
                AND c.latitude IS NOT NULL
        """)
        
        exact_matches = cur.rowcount
        print(f"  Exact address matches: {exact_matches:,}")
        
        # Match by proximity and name (within 0.5 miles)
        cur.execute("""
            INSERT INTO voter_contributor_matches 
            (voter_id, contributor_id, match_type, name_similarity, distance_miles, 
             same_address, same_zip, confidence_score, total_contributions, contribution_count)
            SELECT 
                v.voter_id,
                c.id as contributor_id,
                'proximity' as match_type,
                similarity(
                    UPPER(v.first_name || ' ' || COALESCE(v.middle_name, '') || ' ' || v.last_name),
                    UPPER(c.first_name || ' ' || COALESCE(c.middle_name, '') || ' ' || c.last_name)
                ) as name_similarity,
                SQRT(POWER((v.latitude - c.latitude) * 69.172, 2) + 
                     POWER((v.longitude - c.longitude) * 54.6, 2)) as distance_miles,
                false as same_address,
                (v.zip = c.zip_code) as same_zip,
                CASE 
                    WHEN v.zip = c.zip_code THEN 0.8
                    ELSE 0.6
                END as confidence_score,
                c.total_contributions,
                c.contribution_count
            FROM voters v
            CROSS JOIN contributors c
            WHERE v.latitude IS NOT NULL 
                AND c.latitude IS NOT NULL
                AND v.voter_id || c.id NOT IN (
                    SELECT voter_id || contributor_id 
                    FROM voter_contributor_matches
                )
                AND ABS(v.latitude - c.latitude) < 0.01  -- Rough filter
                AND ABS(v.longitude - c.longitude) < 0.01
                AND similarity(
                    UPPER(v.last_name),
                    UPPER(c.last_name)
                ) > 0.7
                AND SQRT(POWER((v.latitude - c.latitude) * 69.172, 2) + 
                         POWER((v.longitude - c.longitude) * 54.6, 2)) < 0.5
        """)
        
        proximity_matches = cur.rowcount
        print(f"  Proximity matches (< 0.5 mi): {proximity_matches:,}")
        
        # Get match statistics
        cur.execute("""
            SELECT 
                COUNT(DISTINCT voter_id) as matched_voters,
                COUNT(DISTINCT contributor_id) as matched_contributors,
                COUNT(*) as total_matches,
                SUM(total_contributions) as total_amount,
                SUM(contribution_count) as total_contributions
            FROM voter_contributor_matches
        """)
        
        stats = cur.fetchone()
        
        print(f"\n{'='*80}")
        print("MATCHING COMPLETE")
        print(f"{'='*80}")
        print(f"\nMatch Statistics:")
        print(f"  Unique voters matched: {stats['matched_voters']:,}")
        print(f"  Unique contributors matched: {stats['matched_contributors']:,}")
        print(f"  Total match pairs: {stats['total_matches']:,}")
        print(f"  Total contributions: {stats['total_contributions']:,.0f}" if stats['total_contributions'] else "  Total contributions: 0")
        print(f"  Total amount: ${stats['total_amount']:,.2f}" if stats['total_amount'] else "  Total amount: $0.00")
        
        # Show top matches
        print("\nTop 10 Matches by Contribution Amount:")
        cur.execute("""
            SELECT 
                v.first_name || ' ' || v.last_name as voter_name,
                c.first_name || ' ' || c.last_name as contributor_name,
                m.match_type,
                m.name_similarity,
                m.distance_miles,
                m.total_contributions,
                m.contribution_count
            FROM voter_contributor_matches m
            JOIN voters v ON m.voter_id = v.voter_id
            JOIN contributors c ON m.contributor_id = c.id
            ORDER BY m.total_contributions DESC NULLS LAST
            LIMIT 10
        """)
        
        for i, match in enumerate(cur.fetchall(), 1):
            print(f"\n  {i}. {match['voter_name']} ↔ {match['contributor_name']}")
            print(f"     Type: {match['match_type']}, Similarity: {match['name_similarity']:.2f}")
            print(f"     Distance: {match['distance_miles']:.2f} mi" if match['distance_miles'] else "     Distance: Same address")
            print(f"     Contributions: {match['contribution_count']:,} totaling ${match['total_contributions']:,.2f}" if match['total_contributions'] else "     Contributions: Unknown")
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()