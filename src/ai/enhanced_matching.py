"""Enhanced matching algorithms for Phase 2."""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
# Using built-in string matching instead of jellyfish
import difflib
from datetime import datetime
import re

class EnhancedMatcher:
    """Advanced matching algorithms for voter-contributor relationships."""
    
    def __init__(self):
        self.match_cache = {}
        self.name_variations = {}
        
    def generate_name_variations(self, name: str) -> List[str]:
        """Generate possible variations of a name."""
        
        if not name:
            return []
        
        # Cache check
        if name in self.name_variations:
            return self.name_variations[name]
        
        variations = [name]
        name_parts = name.split()
        
        if len(name_parts) >= 2:
            # First Last
            variations.append(f"{name_parts[0]} {name_parts[-1]}")
            
            # Last, First
            variations.append(f"{name_parts[-1]}, {name_parts[0]}")
            
            # F. Last
            variations.append(f"{name_parts[0][0]}. {name_parts[-1]}")
            
            # First M. Last (if middle name exists)
            if len(name_parts) >= 3:
                variations.append(f"{name_parts[0]} {name_parts[1][0]}. {name_parts[-1]}")
            
            # Nicknames (common ones)
            nickname_map = {
                'Robert': ['Bob', 'Rob'],
                'William': ['Bill', 'Will'],
                'James': ['Jim', 'Jimmy'],
                'Michael': ['Mike'],
                'Richard': ['Dick', 'Rick'],
                'Joseph': ['Joe'],
                'Thomas': ['Tom'],
                'Charles': ['Chuck', 'Charlie'],
                'Christopher': ['Chris'],
                'Daniel': ['Dan', 'Danny'],
                'Matthew': ['Matt'],
                'Anthony': ['Tony'],
                'Elizabeth': ['Liz', 'Beth', 'Betty'],
                'Jennifer': ['Jen', 'Jenny'],
                'Patricia': ['Pat', 'Patty'],
                'Margaret': ['Peggy', 'Maggie'],
                'Katherine': ['Kate', 'Kathy', 'Katie']
            }
            
            first_name = name_parts[0]
            for full_name, nicknames in nickname_map.items():
                if first_name == full_name:
                    for nick in nicknames:
                        variations.append(f"{nick} {name_parts[-1]}")
                elif first_name in nicknames:
                    variations.append(f"{full_name} {name_parts[-1]}")
        
        # Remove duplicates
        variations = list(set(variations))
        
        # Cache result
        self.name_variations[name] = variations
        
        return variations
    
    def calculate_name_similarity(self, name1: str, name2: str, 
                                 use_variations: bool = True) -> float:
        """Calculate similarity between two names using multiple metrics."""
        
        if not name1 or not name2:
            return 0.0
        
        # Normalize names
        name1 = name1.upper().strip()
        name2 = name2.upper().strip()
        
        # Direct match
        if name1 == name2:
            return 1.0
        
        # Check variations
        if use_variations:
            variations1 = self.generate_name_variations(name1)
            variations2 = self.generate_name_variations(name2)
            
            for v1 in variations1:
                for v2 in variations2:
                    if v1.upper() == v2.upper():
                        return 0.95
        
        # Calculate various similarity metrics
        scores = []
        
        # Sequence matcher similarity (similar to Jaro-Winkler)
        sequence_score = difflib.SequenceMatcher(None, name1, name2).ratio()
        scores.append(sequence_score)
        
        # Character-based similarity
        common_chars = set(name1) & set(name2)
        if name1 and name2:
            char_score = len(common_chars) / max(len(set(name1)), len(set(name2)))
            scores.append(char_score)
        
        # Prefix similarity
        prefix_len = 0
        for i in range(min(len(name1), len(name2))):
            if name1[i] == name2[i]:
                prefix_len += 1
            else:
                break
        prefix_score = prefix_len / max(len(name1), len(name2)) if name1 and name2 else 0
        scores.append(prefix_score * 1.2)  # Weight prefix matches higher
        
        # Token-based similarity
        tokens1 = set(name1.split())
        tokens2 = set(name2.split())
        if tokens1 and tokens2:
            jaccard = len(tokens1.intersection(tokens2)) / len(tokens1.union(tokens2))
            scores.append(jaccard)
        
        # Return weighted average
        return np.mean(scores)
    
    def calculate_address_similarity(self, addr1: Dict, addr2: Dict) -> float:
        """Calculate similarity between two addresses."""
        
        score = 0.0
        weights = 0.0
        
        # ZIP code match (high weight)
        if addr1.get('zip') and addr2.get('zip'):
            if addr1['zip'][:5] == addr2['zip'][:5]:
                score += 0.4
            weights += 0.4
        
        # City match
        if addr1.get('city') and addr2.get('city'):
            city1 = addr1['city'].upper().strip()
            city2 = addr2['city'].upper().strip()
            if city1 == city2:
                score += 0.3
            elif difflib.SequenceMatcher(None, city1, city2).ratio() > 0.9:
                score += 0.2
            weights += 0.3
        
        # State match
        if addr1.get('state') and addr2.get('state'):
            if addr1['state'].upper() == addr2['state'].upper():
                score += 0.1
            weights += 0.1
        
        # Street address (if available)
        if addr1.get('street') and addr2.get('street'):
            street1 = self.normalize_street(addr1['street'])
            street2 = self.normalize_street(addr2['street'])
            if street1 == street2:
                score += 0.2
            elif difflib.SequenceMatcher(None, street1, street2).ratio() > 0.8:
                score += 0.1
            weights += 0.2
        
        # Normalize score
        if weights > 0:
            return score / weights
        else:
            return 0.0
    
    def normalize_street(self, street: str) -> str:
        """Normalize street address."""
        
        if not street:
            return ''
        
        street = street.upper().strip()
        
        # Replace common abbreviations
        replacements = {
            ' STREET': ' ST',
            ' AVENUE': ' AVE',
            ' ROAD': ' RD',
            ' BOULEVARD': ' BLVD',
            ' DRIVE': ' DR',
            ' PLACE': ' PL',
            ' COURT': ' CT',
            ' LANE': ' LN',
            ' NORTH ': ' N ',
            ' SOUTH ': ' S ',
            ' EAST ': ' E ',
            ' WEST ': ' W ',
            'APARTMENT': 'APT',
            'SUITE': 'STE'
        }
        
        for old, new in replacements.items():
            street = street.replace(old, new)
        
        # Remove extra spaces
        street = ' '.join(street.split())
        
        return street
    
    def calculate_geographic_distance(self, lat1: float, lon1: float, 
                                    lat2: float, lon2: float) -> float:
        """Calculate distance between two geographic points in meters."""
        
        if not all([lat1, lon1, lat2, lon2]):
            return float('inf')
        
        # Haversine formula
        R = 6371000  # Earth radius in meters
        
        lat1_rad = np.radians(lat1)
        lat2_rad = np.radians(lat2)
        delta_lat = np.radians(lat2 - lat1)
        delta_lon = np.radians(lon2 - lon1)
        
        a = (np.sin(delta_lat / 2) ** 2 + 
             np.cos(lat1_rad) * np.cos(lat2_rad) * 
             np.sin(delta_lon / 2) ** 2)
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
        
        return R * c
    
    def match_voter_contributor(self, voter: Dict, contributor: Dict) -> Dict:
        """Perform comprehensive matching between voter and contributor."""
        
        match_result = {
            'match_score': 0.0,
            'name_score': 0.0,
            'address_score': 0.0,
            'distance_meters': None,
            'confidence': 'none',
            'match_factors': []
        }
        
        # Name matching
        voter_name = voter.get('full_name', '')
        contributor_name = contributor.get('full_name', '')
        
        name_score = self.calculate_name_similarity(voter_name, contributor_name)
        match_result['name_score'] = name_score
        
        if name_score > 0.9:
            match_result['match_factors'].append('strong_name_match')
        elif name_score > 0.7:
            match_result['match_factors'].append('partial_name_match')
        
        # Address matching
        voter_addr = {
            'street': voter.get('address', ''),
            'city': voter.get('city', ''),
            'state': voter.get('state', 'NY'),
            'zip': voter.get('zip_code', '')
        }
        
        contributor_addr = {
            'street': contributor.get('address', ''),
            'city': contributor.get('city', ''),
            'state': contributor.get('state', ''),
            'zip': contributor.get('zip_code', '')
        }
        
        address_score = self.calculate_address_similarity(voter_addr, contributor_addr)
        match_result['address_score'] = address_score
        
        if address_score > 0.8:
            match_result['match_factors'].append('strong_address_match')
        elif address_score > 0.5:
            match_result['match_factors'].append('partial_address_match')
        
        # Geographic distance
        if all([voter.get('latitude'), voter.get('longitude'), 
                contributor.get('latitude'), contributor.get('longitude')]):
            distance = self.calculate_geographic_distance(
                voter['latitude'], voter['longitude'],
                contributor['latitude'], contributor['longitude']
            )
            match_result['distance_meters'] = distance
            
            if distance < 100:
                match_result['match_factors'].append('same_location')
            elif distance < 500:
                match_result['match_factors'].append('same_block')
            elif distance < 2000:
                match_result['match_factors'].append('same_neighborhood')
        
        # Calculate composite score
        weights = {
            'name': 0.5,
            'address': 0.3,
            'distance': 0.2
        }
        
        composite_score = (
            name_score * weights['name'] +
            address_score * weights['address']
        )
        
        # Adjust for distance if available
        if match_result['distance_meters'] is not None:
            if match_result['distance_meters'] < 100:
                distance_score = 1.0
            elif match_result['distance_meters'] < 1000:
                distance_score = 0.7
            elif match_result['distance_meters'] < 5000:
                distance_score = 0.3
            else:
                distance_score = 0.0
            
            composite_score = (
                name_score * weights['name'] +
                address_score * weights['address'] +
                distance_score * weights['distance']
            )
        
        match_result['match_score'] = composite_score
        
        # Determine confidence level
        if composite_score > 0.9:
            match_result['confidence'] = 'very_high'
        elif composite_score > 0.7:
            match_result['confidence'] = 'high'
        elif composite_score > 0.5:
            match_result['confidence'] = 'medium'
        elif composite_score > 0.3:
            match_result['confidence'] = 'low'
        else:
            match_result['confidence'] = 'none'
        
        return match_result
    
    def batch_match(self, voters: pd.DataFrame, contributors: pd.DataFrame,
                   threshold: float = 0.5) -> pd.DataFrame:
        """Perform batch matching between voters and contributors."""
        
        matches = []
        
        for _, voter in voters.iterrows():
            best_match = None
            best_score = 0
            
            for _, contributor in contributors.iterrows():
                result = self.match_voter_contributor(
                    voter.to_dict(),
                    contributor.to_dict()
                )
                
                if result['match_score'] > best_score:
                    best_score = result['match_score']
                    best_match = {
                        'voter_id': voter.get('id'),
                        'voter_name': voter.get('full_name'),
                        'contributor_id': contributor.get('id'),
                        'contributor_name': contributor.get('full_name'),
                        **result
                    }
            
            if best_match and best_score >= threshold:
                matches.append(best_match)
        
        return pd.DataFrame(matches)
    
    def find_household_connections(self, address_data: pd.DataFrame) -> List[Dict]:
        """Find potential household connections based on addresses."""
        
        connections = []
        
        # Group by normalized address
        if 'address' in address_data.columns:
            address_data['normalized_address'] = address_data['address'].apply(
                self.normalize_street
            )
            
            # Find addresses with multiple people
            grouped = address_data.groupby('normalized_address')
            
            for addr, group in grouped:
                if len(group) > 1 and addr:
                    connection = {
                        'address': addr,
                        'num_residents': len(group),
                        'residents': group['full_name'].tolist() if 'full_name' in group.columns else [],
                        'total_contributions': group['total_contributions'].sum() if 'total_contributions' in group.columns else 0
                    }
                    connections.append(connection)
        
        return connections


class RelationshipAnalyzer:
    """Analyze relationships between entities."""
    
    def __init__(self):
        self.relationships = []
        
    def infer_relationships(self, data: pd.DataFrame) -> List[Dict]:
        """Infer relationships from data patterns."""
        
        relationships = []
        
        # Find family relationships (same last name, same address)
        if all(col in data.columns for col in ['last_name', 'address']):
            grouped = data.groupby(['last_name', 'address'])
            
            for (last_name, address), group in grouped:
                if len(group) > 1 and last_name and address:
                    relationships.append({
                        'type': 'potential_family',
                        'members': group['full_name'].tolist() if 'full_name' in group.columns else [],
                        'last_name': last_name,
                        'address': address,
                        'confidence': 0.8
                    })
        
        # Find business relationships (same employer)
        if 'employer' in data.columns:
            employer_groups = data.groupby('employer')
            
            for employer, group in employer_groups:
                if len(group) > 2 and employer and employer != 'SELF':
                    relationships.append({
                        'type': 'coworkers',
                        'employer': employer,
                        'members': group['full_name'].tolist()[:10] if 'full_name' in group.columns else [],
                        'num_employees': len(group),
                        'confidence': 0.9
                    })
        
        # Find geographic clusters
        if all(col in data.columns for col in ['latitude', 'longitude']):
            from sklearn.cluster import DBSCAN
            
            coords = data[['latitude', 'longitude']].dropna()
            if len(coords) > 10:
                # Cluster based on geographic proximity
                clustering = DBSCAN(eps=0.001, min_samples=3)  # ~100m radius
                coords['cluster'] = clustering.fit_predict(coords)
                
                for cluster_id in coords['cluster'].unique():
                    if cluster_id != -1:  # Ignore noise
                        cluster_members = data.iloc[coords[coords['cluster'] == cluster_id].index]
                        if len(cluster_members) > 2:
                            relationships.append({
                                'type': 'geographic_cluster',
                                'cluster_id': int(cluster_id),
                                'members': cluster_members['full_name'].tolist()[:10] if 'full_name' in cluster_members.columns else [],
                                'num_members': len(cluster_members),
                                'confidence': 0.6
                            })
        
        return relationships