#!/usr/bin/env python3
"""Quick demo of voter-contributor matching capability."""

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from difflib import SequenceMatcher

DATABASE_URL = os.environ.get('DATABASE_URL')

def quick_match_demo():
    """Quick demonstration of matching capability."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("=" * 80)
    print("VOTER-CONTRIBUTOR MATCHING ANALYSIS DEMO")
    print("=" * 80)
    
    # Create similarity extension if needed
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    conn.commit()
    
    # Get some sample voters
    cur.execute("""
        SELECT 
            id, 
            first_name, 
            last_name, 
            normalized_name,
            primary_address1,
            primary_city,
            primary_zip
        FROM voters 
        WHERE official_party = 'Republican'
        LIMIT 10
    """)
    
    voters = cur.fetchall()
    print(f"\nAnalyzing {len(voters)} voter records...")
    
    matches_found = []
    
    for voter in voters:
        # Simple name-based matching
        cur.execute("""
            SELECT 
                c.id,
                c.full_name,
                c.normalized_name,
                COUNT(DISTINCT cont.id) as contribution_count,
                SUM(cont.amount) as total_amount
            FROM contributors c
            JOIN contributions cont ON c.id = cont.contributor_id
            WHERE c.normalized_name = %s
               OR (c.last_name = %s AND c.first_name = %s)
            GROUP BY c.id, c.full_name, c.normalized_name
            LIMIT 5
        """, (
            voter['normalized_name'],
            voter['last_name'],
            voter['first_name']
        ))
        
        contributor_matches = cur.fetchall()
        
        if contributor_matches:
            for contrib in contributor_matches:
                # Calculate simple similarity
                similarity = SequenceMatcher(None, 
                    voter['normalized_name'], 
                    contrib['normalized_name']
                ).ratio()
                
                if similarity > 0.7:  # 70% similarity threshold
                    matches_found.append({
                        'voter_name': f"{voter['first_name']} {voter['last_name']}",
                        'voter_address': voter['primary_address1'],
                        'contributor_name': contrib['full_name'],
                        'similarity_score': round(similarity * 100, 1),
                        'contributions': contrib['contribution_count'],
                        'total_amount': float(contrib['total_amount'] or 0)
                    })
    
    # Display results
    print("\n" + "=" * 80)
    print("MATCHING RESULTS")
    print("=" * 80)
    
    if matches_found:
        print(f"\nFound {len(matches_found)} potential matches:")
        print("-" * 40)
        
        for match in matches_found[:10]:  # Show top 10
            print(f"\nVoter: {match['voter_name']}")
            print(f"  Address: {match['voter_address']}")
            print(f"  Matched Contributor: {match['contributor_name']}")
            print(f"  Match Confidence: {match['similarity_score']}%")
            print(f"  Political Contributions: {match['contributions']} totaling ${match['total_amount']:,.2f}")
        
        # Summary statistics
        df = pd.DataFrame(matches_found)
        total_amount = df['total_amount'].sum()
        avg_confidence = df['similarity_score'].mean()
        
        print("\n" + "=" * 80)
        print("SUMMARY STATISTICS")
        print("=" * 80)
        print(f"Total matched voters: {len(df['voter_name'].unique())}")
        print(f"Total political contributions from matched voters: ${total_amount:,.2f}")
        print(f"Average match confidence: {avg_confidence:.1f}%")
        
    else:
        print("\nNo matches found in this sample.")
    
    # Show capability overview
    print("\n" + "=" * 80)
    print("MATCHING CAPABILITY OVERVIEW")
    print("=" * 80)
    print("""
This system can:
1. Match voter records with campaign contributor records
2. Calculate match probability based on:
   - Name similarity (fuzzy matching)
   - Address matching
   - ZIP code verification
3. Identify voters who have made political contributions
4. Track contribution amounts and patterns
5. Generate reports on voter engagement in campaign finance

Current Database Status:
    """)
    
    # Get counts
    cur.execute("SELECT COUNT(*) FROM voters")
    voter_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) FROM contributors")
    contributor_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) FROM contributions")
    contribution_count = cur.fetchone()['count']
    
    print(f"  - Voters loaded: {voter_count:,}")
    print(f"  - Contributors in database: {contributor_count:,}")
    print(f"  - Contributions tracked: {contribution_count:,}")
    
    print("""
To run a full analysis on all voters, use:
  python scripts/voter_contributor_matching.py
    """)
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    quick_match_demo()