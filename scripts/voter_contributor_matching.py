#!/usr/bin/env python3
"""Match voter records with contributor records to find potential matches."""

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
import numpy as np
from difflib import SequenceMatcher
import re

DATABASE_URL = os.environ.get('DATABASE_URL')

class VoterContributorMatcher:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        
    def normalize_text(self, text):
        """Normalize text for comparison."""
        if pd.isna(text) or not text:
            return ""
        text = str(text).upper().strip()
        # Remove common punctuation and extra spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def calculate_name_similarity(self, voter_name, contributor_name):
        """Calculate similarity between two names."""
        if not voter_name or not contributor_name:
            return 0.0
        
        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, voter_name, contributor_name).ratio()
    
    def calculate_address_similarity(self, voter_addr, contributor_addr):
        """Calculate similarity between two addresses."""
        if not voter_addr or not contributor_addr:
            return 0.0
        
        # Extract numbers from addresses for comparison
        voter_nums = re.findall(r'\d+', voter_addr)
        contrib_nums = re.findall(r'\d+', contributor_addr)
        
        # Check if street numbers match
        number_match = 0.0
        if voter_nums and contrib_nums:
            if voter_nums[0] == contrib_nums[0]:
                number_match = 0.3  # 30% weight for matching street number
        
        # Check overall address similarity
        text_similarity = SequenceMatcher(None, voter_addr, contributor_addr).ratio() * 0.7
        
        return number_match + text_similarity
    
    def calculate_match_probability(self, name_sim, addr_sim, has_same_zip=False):
        """Calculate overall match probability."""
        # Weighted scoring
        name_weight = 0.6
        addr_weight = 0.3
        zip_weight = 0.1
        
        base_score = (name_sim * name_weight) + (addr_sim * addr_weight)
        
        if has_same_zip:
            base_score += zip_weight
        
        # Apply thresholds and confidence levels
        if name_sim >= 0.95 and addr_sim >= 0.8:
            # Very high confidence match
            return min(0.95, base_score * 1.1)
        elif name_sim >= 0.85 and addr_sim >= 0.6:
            # High confidence match
            return min(0.85, base_score)
        elif name_sim >= 0.7:
            # Medium confidence match
            return base_score * 0.9
        else:
            # Low confidence
            return base_score * 0.8
    
    def find_matches_for_voter(self, voter_id):
        """Find potential contributor matches for a specific voter."""
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Get voter info
        cur.execute("""
            SELECT 
                id, 
                normalized_name,
                normalized_address,
                last_name,
                first_name,
                middle_name,
                primary_zip,
                primary_address1,
                primary_city,
                primary_state
            FROM voters 
            WHERE id = %s
        """, (voter_id,))
        
        voter = cur.fetchone()
        if not voter:
            return []
        
        # Search for potential matches in contributors
        # First, try exact normalized name match
        cur.execute("""
            SELECT 
                c.id as contributor_id,
                c.full_name,
                c.normalized_name,
                c.last_name,
                c.first_name,
                c.middle_initial,
                l.street_number,
                l.street_name,
                l.city,
                l.state,
                l.zip_code,
                COUNT(DISTINCT cont.id) as contribution_count,
                SUM(cont.amount) as total_contributed,
                SIMILARITY(c.normalized_name, %s) as similarity_score
            FROM contributors c
            LEFT JOIN contributions cont ON c.id = cont.contributor_id
            LEFT JOIN locations l ON cont.location_id = l.id
            WHERE c.normalized_name = %s
               OR (c.last_name = %s AND c.first_name = %s)
               OR (SIMILARITY(c.normalized_name, %s) > 0.5)
            GROUP BY c.id, c.full_name, c.normalized_name, c.last_name, c.first_name, 
                     c.middle_initial, l.street_number, l.street_name, l.city, l.state, l.zip_code
            ORDER BY similarity_score DESC
            LIMIT 20
        """, (
            voter['normalized_name'],  # For SIMILARITY calculation
            voter['normalized_name'],  # For WHERE normalized_name = 
            voter['last_name'],        # For WHERE last_name =
            voter['first_name'],       # For WHERE first_name =
            voter['normalized_name']   # For WHERE SIMILARITY > 0.5
        ))
        
        potential_matches = cur.fetchall()
        
        matches = []
        for contributor in potential_matches:
            # Calculate name similarity
            name_sim = self.calculate_name_similarity(
                voter['normalized_name'],
                contributor['normalized_name']
            )
            
            # Build contributor address
            contrib_addr_parts = []
            if contributor['street_number']:
                contrib_addr_parts.append(str(contributor['street_number']))
            if contributor['street_name']:
                contrib_addr_parts.append(str(contributor['street_name']))
            if contributor['city']:
                contrib_addr_parts.append(str(contributor['city']))
            if contributor['state']:
                contrib_addr_parts.append(str(contributor['state']))
            
            contrib_addr = ' '.join(contrib_addr_parts)
            contrib_addr_normalized = self.normalize_text(contrib_addr)
            
            # Calculate address similarity
            addr_sim = self.calculate_address_similarity(
                voter['normalized_address'],
                contrib_addr_normalized
            )
            
            # Check zip code match
            has_same_zip = False
            if voter['primary_zip'] and contributor['zip_code']:
                has_same_zip = str(voter['primary_zip'])[:5] == str(contributor['zip_code'])[:5]
            
            # Calculate match probability
            match_prob = self.calculate_match_probability(name_sim, addr_sim, has_same_zip)
            
            # Only include matches above threshold
            if match_prob >= 0.3:  # 30% minimum threshold
                matches.append({
                    'voter_id': voter['id'],
                    'voter_name': f"{voter['first_name']} {voter['last_name']}",
                    'voter_address': voter['primary_address1'],
                    'contributor_id': contributor['contributor_id'],
                    'contributor_name': contributor['full_name'],
                    'contributor_address': contrib_addr,
                    'name_similarity': round(name_sim, 3),
                    'address_similarity': round(addr_sim, 3),
                    'match_probability': round(match_prob, 3),
                    'contribution_count': contributor['contribution_count'] or 0,
                    'total_contributed': float(contributor['total_contributed'] or 0),
                    'has_same_zip': has_same_zip
                })
        
        # Sort by match probability
        matches.sort(key=lambda x: x['match_probability'], reverse=True)
        
        cur.close()
        return matches
    
    def batch_match_voters(self, limit=100, min_probability=0.5):
        """Match multiple voters with contributors."""
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Get sample of voters
        cur.execute("""
            SELECT id, first_name, last_name, primary_address1
            FROM voters 
            WHERE official_party = 'Republican'
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit,))
        
        voters = cur.fetchall()
        
        all_matches = []
        for i, voter in enumerate(voters):
            if i % 10 == 0:
                print(f"Processing voter {i+1}/{len(voters)}...")
            
            matches = self.find_matches_for_voter(voter['id'])
            
            # Filter by minimum probability
            high_confidence_matches = [m for m in matches if m['match_probability'] >= min_probability]
            
            if high_confidence_matches:
                all_matches.extend(high_confidence_matches)
        
        cur.close()
        return all_matches
    
    def create_match_report(self, matches):
        """Create a summary report of matches."""
        if not matches:
            print("No matches found")
            return
        
        df = pd.DataFrame(matches)
        
        print("\n" + "=" * 80)
        print("VOTER-CONTRIBUTOR MATCHING REPORT")
        print("=" * 80)
        
        print(f"\nTotal matches found: {len(df)}")
        print(f"Unique voters matched: {df['voter_id'].nunique()}")
        print(f"Unique contributors matched: {df['contributor_id'].nunique()}")
        
        print("\nMatch Quality Distribution:")
        print("-" * 40)
        print(f"High confidence (>80%): {len(df[df['match_probability'] > 0.8])}")
        print(f"Medium confidence (60-80%): {len(df[(df['match_probability'] >= 0.6) & (df['match_probability'] <= 0.8)])}")
        print(f"Low confidence (30-60%): {len(df[df['match_probability'] < 0.6])}")
        
        print("\nTop 10 Matches:")
        print("-" * 40)
        top_matches = df.nlargest(10, 'match_probability')[
            ['voter_name', 'contributor_name', 'match_probability', 'total_contributed', 'contribution_count']
        ]
        
        for _, row in top_matches.iterrows():
            print(f"\n{row['voter_name']} <-> {row['contributor_name']}")
            print(f"  Match Probability: {row['match_probability']*100:.1f}%")
            print(f"  Total Contributed: ${row['total_contributed']:,.2f}")
            print(f"  Number of Contributions: {row['contribution_count']}")
        
        # Summary statistics
        if len(df) > 0:
            print("\n" + "=" * 80)
            print("FINANCIAL SUMMARY OF MATCHED VOTERS")
            print("=" * 80)
            
            total_amount = df.groupby('voter_id')['total_contributed'].first().sum()
            avg_amount = df.groupby('voter_id')['total_contributed'].first().mean()
            
            print(f"\nTotal amount contributed by matched voters: ${total_amount:,.2f}")
            print(f"Average contribution per matched voter: ${avg_amount:,.2f}")
            
            # Party affiliation insights
            print("\nContribution patterns for Republican voters:")
            print(f"  - {df['voter_id'].nunique()} voters have made political contributions")
            print(f"  - Average match confidence: {df['match_probability'].mean()*100:.1f}%")
        
        return df
    
    def close(self):
        """Close database connection."""
        self.conn.close()

def main():
    """Main execution function."""
    print("Starting Voter-Contributor Matching Analysis")
    print("=" * 80)
    
    matcher = VoterContributorMatcher()
    
    try:
        # First, ensure we have the similarity extension
        cur = matcher.conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        matcher.conn.commit()
        cur.close()
        
        # Run batch matching
        print("\nSearching for matches (this may take a few minutes)...")
        matches = matcher.batch_match_voters(limit=100, min_probability=0.5)
        
        # Create report
        df_report = matcher.create_match_report(matches)
        
        # Save results to CSV
        if matches:
            output_file = f"voter_contributor_matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df = pd.DataFrame(matches)
            df.to_csv(output_file, index=False)
            print(f"\nDetailed results saved to: {output_file}")
        
    except Exception as e:
        print(f"Error during matching: {e}")
        import traceback
        traceback.print_exc()
    finally:
        matcher.close()

if __name__ == "__main__":
    main()