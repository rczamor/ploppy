"""Entity extraction for campaign finance data using NLTK and regex."""

import re
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Set
import nltk
from collections import Counter, defaultdict
from ..database.db_manager_v2 import NYCCFBDatabase
from ..database.code_mappings import parse_name, is_individual_name

# Download required NLTK data
try:
    nltk.download('punkt', quiet=True)
    nltk.download('maxent_ne_chunker', quiet=True)
    nltk.download('words', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)
    nltk.download('stopwords', quiet=True)
except:
    pass


class EntityExtractor:
    """Extract and standardize entities from campaign finance text data."""
    
    def __init__(self):
        self.db = NYCCFBDatabase()
        self.stopwords = set(nltk.corpus.stopwords.words('english'))
        
        # Common patterns for campaign finance data
        self.patterns = {
            'corporation': re.compile(r'\b(?:LLC|INC|CORP|LTD|LP|PLLC|PC|PA|CO|COMPANY|CORPORATION|INCORPORATED)\b', re.I),
            'pac': re.compile(r'\b(?:PAC|COMMITTEE|FUND|FRIENDS OF|CITIZENS FOR|PEOPLE FOR)\b', re.I),
            'union': re.compile(r'\b(?:UNION|LOCAL \d+|WORKERS|EMPLOYEES|ASSOCIATION)\b', re.I),
            'money': re.compile(r'\$[\d,]+(?:\.\d{2})?|\b\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:dollars?|USD)\b', re.I),
            'date': re.compile(r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})\b', re.I),
            'address': re.compile(r'\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Ln|Lane|Dr|Drive|Ct|Court|Pl|Place)\b', re.I),
            'zip': re.compile(r'\b\d{5}(?:-\d{4})?\b'),
            'phone': re.compile(r'\b(?:\d{3}[-.]?\d{3}[-.]?\d{4}|\(\d{3}\)\s*\d{3}[-.]?\d{4})\b'),
            'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        }
        
        # Entity type classifiers
        self.entity_keywords = {
            'business': ['llc', 'inc', 'corp', 'company', 'partners', 'group', 'associates', 'enterprises'],
            'political': ['committee', 'pac', 'campaign', 'friends of', 'citizens for', 'voters for'],
            'union': ['union', 'local', 'workers', 'employees', 'federation', 'association'],
            'nonprofit': ['foundation', 'charity', 'institute', '501c', 'nonprofit', 'society'],
            'government': ['city', 'state', 'federal', 'department', 'agency', 'commission']
        }
    
    def extract_entities_from_text(self, text: str) -> Dict[str, List[str]]:
        """Extract various entity types from text."""
        entities = defaultdict(list)
        
        # Extract using patterns
        for entity_type, pattern in self.patterns.items():
            matches = pattern.findall(text)
            entities[entity_type].extend(matches)
        
        # Extract names using NLTK
        try:
            tokens = nltk.word_tokenize(text)
            pos_tags = nltk.pos_tag(tokens)
            
            # Extract named entities
            chunks = nltk.ne_chunk(pos_tags, binary=False)
            
            for chunk in chunks:
                if hasattr(chunk, 'label'):
                    entity_text = ' '.join([c[0] for c in chunk])
                    if chunk.label() == 'PERSON':
                        entities['person'].append(entity_text)
                    elif chunk.label() == 'ORGANIZATION':
                        entities['organization'].append(entity_text)
                    elif chunk.label() == 'GPE':  # Geo-political entity
                        entities['location'].append(entity_text)
        except:
            pass
        
        # Remove duplicates
        for key in entities:
            entities[key] = list(set(entities[key]))
        
        return dict(entities)
    
    def classify_contributor_type(self, name: str, occupation: Optional[str] = None,
                                employer: Optional[str] = None) -> str:
        """Classify a contributor as individual, business, PAC, etc."""
        
        name_lower = name.lower() if name else ''
        occupation_lower = occupation.lower() if occupation else ''
        employer_lower = employer.lower() if employer else ''
        
        combined_text = f"{name_lower} {occupation_lower} {employer_lower}"
        
        # Check for corporation indicators
        if self.patterns['corporation'].search(name):
            return 'CORPORATION'
        
        # Check for PAC indicators
        if self.patterns['pac'].search(name):
            return 'PAC'
        
        # Check for union indicators
        if self.patterns['union'].search(combined_text):
            return 'UNION'
        
        # Check entity keywords
        entity_scores = {}
        for entity_type, keywords in self.entity_keywords.items():
            score = sum(1 for keyword in keywords if keyword in combined_text)
            if score > 0:
                entity_scores[entity_type] = score
        
        if entity_scores:
            return max(entity_scores, key=entity_scores.get).upper()
        
        # Check if it's an individual name
        if is_individual_name(name):
            return 'INDIVIDUAL'
        
        # Default to organization if unclear
        return 'ORGANIZATION'
    
    def standardize_organization_name(self, name: str) -> str:
        """Standardize organization names for better matching."""
        if not name:
            return ''
        
        # Convert to uppercase
        name = name.upper().strip()
        
        # Standardize common abbreviations
        replacements = {
            ' INCORPORATED': ' INC',
            ' CORPORATION': ' CORP',
            ' LIMITED': ' LTD',
            ' COMPANY': ' CO',
            ' AND ': ' & ',
            ' POLITICAL ACTION COMMITTEE': ' PAC',
            'THE ': '',  # Remove leading "THE"
        }
        
        for old, new in replacements.items():
            name = name.replace(old, new)
        
        # Remove extra spaces
        name = ' '.join(name.split())
        
        return name
    
    def extract_address_components(self, address: str) -> Dict[str, str]:
        """Extract components from an address string."""
        components = {
            'street': '',
            'city': '',
            'state': '',
            'zip': ''
        }
        
        if not address:
            return components
        
        # Extract ZIP code
        zip_match = self.patterns['zip'].search(address)
        if zip_match:
            components['zip'] = zip_match.group()
            address = address.replace(zip_match.group(), '').strip()
        
        # Extract state (2-letter abbreviation)
        state_match = re.search(r'\b([A-Z]{2})\b', address)
        if state_match:
            components['state'] = state_match.group(1)
            address = address.replace(state_match.group(), '').strip()
        
        # Split remaining into street and city
        # Assume last comma-separated part is city
        parts = [p.strip() for p in address.split(',')]
        if len(parts) >= 2:
            components['street'] = parts[0]
            components['city'] = parts[-1].strip()
        else:
            # Try to identify city by common patterns
            city_match = re.search(r'\b(?:New York|Brooklyn|Manhattan|Queens|Bronx|Staten Island)\b', address, re.I)
            if city_match:
                components['city'] = city_match.group()
                components['street'] = address.replace(city_match.group(), '').strip(' ,')
            else:
                components['street'] = address
        
        return components
    
    def find_related_entities(self, entity_name: str, entity_type: str = 'all') -> pd.DataFrame:
        """Find entities related to a given entity."""
        
        standardized_name = self.standardize_organization_name(entity_name)
        
        # Build query based on entity type
        if entity_type == 'contributor':
            query = f"""
                SELECT DISTINCT
                    c.id,
                    c.full_name as name,
                    c.contributor_type,
                    COUNT(DISTINCT cont.id) as num_contributions,
                    SUM(cont.amount) as total_amount,
                    STRING_AGG(DISTINCT r.last_name || ', ' || r.first_name, '; ') as recipients
                FROM contributors c
                JOIN contributions cont ON c.id = cont.contributor_id
                JOIN recipients r ON cont.recipient_id = r.id
                WHERE UPPER(c.full_name) LIKE '%{standardized_name}%'
                GROUP BY c.id, c.full_name, c.contributor_type
                ORDER BY total_amount DESC
            """
        elif entity_type == 'recipient':
            query = f"""
                SELECT DISTINCT
                    r.id,
                    r.last_name || ', ' || r.first_name as name,
                    r.office_sought,
                    COUNT(DISTINCT cont.id) as num_contributions,
                    SUM(cont.amount) as total_amount
                FROM recipients r
                JOIN contributions cont ON r.id = cont.recipient_id
                WHERE UPPER(r.last_name || ', ' || r.first_name) LIKE '%{standardized_name}%'
                GROUP BY r.id, name, r.office_sought
                ORDER BY total_amount DESC
            """
        else:  # Search all
            query = f"""
                SELECT * FROM (
                    SELECT 
                        'contributor' as entity_type,
                        c.id,
                        c.full_name as name,
                        COUNT(DISTINCT cont.id) as num_contributions,
                        SUM(cont.amount) as total_amount
                    FROM contributors c
                    JOIN contributions cont ON c.id = cont.contributor_id
                    WHERE UPPER(c.full_name) LIKE '%{standardized_name}%'
                    GROUP BY c.id, c.full_name
                    
                    UNION ALL
                    
                    SELECT 
                        'recipient' as entity_type,
                        r.id,
                        r.last_name || ', ' || r.first_name as name,
                        COUNT(DISTINCT cont.id) as num_contributions,
                        SUM(cont.amount) as total_amount
                    FROM recipients r
                    JOIN contributions cont ON r.id = cont.recipient_id
                    WHERE UPPER(r.last_name || ', ' || r.first_name) LIKE '%{standardized_name}%'
                    GROUP BY r.id, name
                ) combined
                ORDER BY total_amount DESC
            """
        
        return pd.read_sql(query, self.db.engine)
    
    def extract_key_entities_from_dataset(self, limit: int = 100) -> Dict[str, pd.DataFrame]:
        """Extract and rank key entities from the entire dataset."""
        
        results = {}
        
        # Top individual contributors
        individual_query = """
            SELECT 
                c.id,
                c.full_name,
                c.occupation,
                e.name as employer,
                COUNT(DISTINCT cont.id) as num_contributions,
                SUM(cont.amount) as total_amount,
                COUNT(DISTINCT cont.recipient_id) as num_recipients
            FROM contributors c
            JOIN contributions cont ON c.id = cont.contributor_id
            LEFT JOIN employers e ON c.employer_id = e.id
            WHERE c.contributor_type = 'I'
            GROUP BY c.id, c.full_name, c.occupation, e.name
            ORDER BY total_amount DESC
            LIMIT %s
        """
        results['top_individuals'] = pd.read_sql(individual_query % limit, self.db.engine)
        
        # Top organizational contributors
        org_query = """
            SELECT 
                c.id,
                c.full_name,
                c.contributor_type,
                COUNT(DISTINCT cont.id) as num_contributions,
                SUM(cont.amount) as total_amount,
                COUNT(DISTINCT cont.recipient_id) as num_recipients
            FROM contributors c
            JOIN contributions cont ON c.id = cont.contributor_id
            WHERE c.contributor_type != 'I'
            GROUP BY c.id, c.full_name, c.contributor_type
            ORDER BY total_amount DESC
            LIMIT %s
        """
        results['top_organizations'] = pd.read_sql(org_query % limit, self.db.engine)
        
        # Most connected entities (contribute to many candidates)
        connected_query = """
            SELECT 
                c.id,
                c.full_name,
                c.contributor_type,
                COUNT(DISTINCT cont.recipient_id) as num_recipients,
                COUNT(DISTINCT cont.id) as num_contributions,
                SUM(cont.amount) as total_amount,
                STRING_AGG(DISTINCT r.last_name || ', ' || r.first_name, '; ' 
                          ORDER BY r.last_name || ', ' || r.first_name) as recipients_sample
            FROM contributors c
            JOIN contributions cont ON c.id = cont.contributor_id
            JOIN recipients r ON cont.recipient_id = r.id
            GROUP BY c.id, c.full_name, c.contributor_type
            HAVING COUNT(DISTINCT cont.recipient_id) > 5
            ORDER BY num_recipients DESC
            LIMIT %s
        """
        results['most_connected'] = pd.read_sql(connected_query % limit, self.db.engine)
        
        return results
    
    def create_entity_network(self, entity_type: str = 'contributor', min_connections: int = 5) -> Dict:
        """Create a network of entities based on shared connections."""
        
        if entity_type == 'contributor':
            # Network of contributors who donate to same candidates
            query = """
                WITH contributor_pairs AS (
                    SELECT 
                        c1.contributor_id as contributor1_id,
                        c2.contributor_id as contributor2_id,
                        COUNT(DISTINCT c1.recipient_id) as shared_recipients
                    FROM contributions c1
                    JOIN contributions c2 ON c1.recipient_id = c2.recipient_id
                    WHERE c1.contributor_id < c2.contributor_id
                    GROUP BY c1.contributor_id, c2.contributor_id
                    HAVING COUNT(DISTINCT c1.recipient_id) >= %s
                )
                SELECT 
                    con1.full_name as entity1,
                    con2.full_name as entity2,
                    cp.shared_recipients,
                    con1.contributor_type as type1,
                    con2.contributor_type as type2
                FROM contributor_pairs cp
                JOIN contributors con1 ON cp.contributor1_id = con1.id
                JOIN contributors con2 ON cp.contributor2_id = con2.id
                ORDER BY shared_recipients DESC
                LIMIT 1000
            """
        else:  # recipient network
            # Network of candidates who receive from same contributors
            query = """
                WITH recipient_pairs AS (
                    SELECT 
                        c1.recipient_id as recipient1_id,
                        c2.recipient_id as recipient2_id,
                        COUNT(DISTINCT c1.contributor_id) as shared_contributors
                    FROM contributions c1
                    JOIN contributions c2 ON c1.contributor_id = c2.contributor_id
                    WHERE c1.recipient_id < c2.recipient_id
                    GROUP BY c1.recipient_id, c2.recipient_id
                    HAVING COUNT(DISTINCT c1.contributor_id) >= %s
                )
                SELECT 
                    r1.last_name || ', ' || r1.first_name as entity1,
                    r2.last_name || ', ' || r2.first_name as entity2,
                    rp.shared_contributors,
                    r1.office_sought as office1,
                    r2.office_sought as office2
                FROM recipient_pairs rp
                JOIN recipients r1 ON rp.recipient1_id = r1.id
                JOIN recipients r2 ON rp.recipient2_id = r2.id
                ORDER BY shared_contributors DESC
                LIMIT 1000
            """
        
        network_df = pd.read_sql(query % min_connections, self.db.engine)
        
        # Calculate network statistics
        if not network_df.empty:
            entities = set(network_df['entity1'].unique()) | set(network_df['entity2'].unique())
            
            # Calculate degree (number of connections) for each entity
            degree = Counter()
            for _, row in network_df.iterrows():
                degree[row['entity1']] += 1
                degree[row['entity2']] += 1
            
            return {
                'network': network_df,
                'num_entities': len(entities),
                'num_connections': len(network_df),
                'top_connected': dict(degree.most_common(20)),
                'avg_connections': sum(degree.values()) / len(degree) if degree else 0
            }
        
        return {
            'network': pd.DataFrame(),
            'num_entities': 0,
            'num_connections': 0,
            'top_connected': {},
            'avg_connections': 0
        }