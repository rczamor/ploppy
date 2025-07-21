"""Natural Language Query interface for the political finance graph database."""

import re
from typing import Dict, List, Any, Optional
from graph_analysis import PoliticalFinanceGraph
import json

class GraphNLPQuery:
    """Translate natural language queries to graph database operations."""
    
    def __init__(self):
        self.graph = PoliticalFinanceGraph()
        
        # Query patterns mapping
        self.patterns = {
            'contributor_network': [
                r"(?:show|find|get)(?: me)?(?: the)? (?:network|connections|recipients) (?:of|for) (.+)",
                r"who (?:did|does) (.+) (?:give|donate|contribute) to",
                r"(.+?)(?:'s|s)? (?:contributions|donations|giving)",
            ],
            'intermediary_network': [
                r"(?:show|find|get)(?: me)?(?: the)? (?:bundler|intermediary) (?:network|connections) (?:of|for) (.+)",
                r"who (?:bundled|raised) (?:money|funds|contributions) (?:through|via|using) (.+)",
                r"(.+?)(?:'s|s)? bundling (?:network|activity)",
            ],
            'influence_analysis': [
                r"(?:analyze|show|what is)(?: the)? influence (?:of|for) (.+)",
                r"how (?:influential|important|connected) is (.+)",
                r"(.+?)(?:'s|s)? (?:influence|impact|reach)",
            ],
            'money_flow': [
                r"(?:show|trace|find)(?: the)? (?:money|funds|contributions) (?:flow|path) (?:from|between) (.+) (?:to|and) (.+)",
                r"how (?:did|does) money (?:flow|get|move) from (.+) to (.+)",
                r"(?:connection|path|link) between (.+) and (.+)",
            ],
            'pattern_detection': [
                r"(?:find|show|detect)(?: me)?(?: any)? (?:patterns|trends|anomalies)",
                r"(?:coordinated|suspicious|interesting) (?:giving|contributions|patterns)",
                r"who (?:gives|contributes) together",
            ],
            'top_queries': [
                r"(?:top|biggest|largest) (\d+)? ?(?:contributors|donors|givers)(?: to (.+))?",
                r"(?:top|biggest|largest) (\d+)? ?(?:recipients|candidates|committees)",
                r"(?:top|biggest|largest) (\d+)? ?(?:bundlers|intermediaries)",
            ]
        }
    
    def parse_query(self, query: str) -> Dict[str, Any]:
        """Parse natural language query and determine intent."""
        query_lower = query.lower().strip()
        
        # Check each pattern category
        for intent, patterns in self.patterns.items():
            for pattern in patterns:
                match = re.search(pattern, query_lower)
                if match:
                    return {
                        'intent': intent,
                        'entities': match.groups(),
                        'original_query': query
                    }
        
        # Default to keyword search
        return {
            'intent': 'keyword_search',
            'entities': [query],
            'original_query': query
        }
    
    def execute_query(self, query: str) -> Dict[str, Any]:
        """Execute natural language query and return results."""
        parsed = self.parse_query(query)
        intent = parsed['intent']
        entities = parsed['entities']
        
        try:
            if intent == 'contributor_network':
                entity_name = entities[0] if entities else query
                return self.graph.find_contributor_network(entity_name, depth=2)
            
            elif intent == 'intermediary_network':
                entity_name = entities[0] if entities else query
                return self.graph.find_intermediary_network(entity_name)
            
            elif intent == 'influence_analysis':
                entity_name = entities[0] if entities else query
                return self.graph.analyze_influence_network(entity_name)
            
            elif intent == 'money_flow':
                if len(entities) >= 2:
                    return {
                        'paths': self.graph.find_money_flow_path(entities[0], entities[1])
                    }
                else:
                    return {'error': 'Please specify both start and end entities'}
            
            elif intent == 'pattern_detection':
                return {
                    'patterns': self.graph.detect_contribution_patterns()
                }
            
            elif intent == 'top_queries':
                return self._handle_top_queries(entities, query_lower)
            
            else:
                return self._handle_keyword_search(query)
                
        except Exception as e:
            return {
                'error': f'Query execution failed: {str(e)}',
                'parsed_query': parsed
            }
    
    def _handle_top_queries(self, entities: tuple, query: str) -> Dict[str, Any]:
        """Handle top N queries."""
        # Extract limit
        limit = 10
        if entities and entities[0] and entities[0].isdigit():
            limit = int(entities[0])
        
        cur = self.graph.conn.cursor()
        
        if 'contributor' in query or 'donor' in query:
            # Check if looking for contributors to specific recipient
            if len(entities) > 1 and entities[1]:
                recipient_name = entities[1]
                cur.execute("""
                    SELECT 
                        contrib.full_name,
                        contrib.contributor_type,
                        SUM(c.amount) as total_given,
                        COUNT(*) as num_contributions
                    FROM contributions c
                    JOIN contributors contrib ON c.contributor_id = contrib.id
                    JOIN recipients r ON c.recipient_id = r.id
                    WHERE r.full_name ILIKE %s
                    GROUP BY contrib.id, contrib.full_name, contrib.contributor_type
                    ORDER BY total_given DESC
                    LIMIT %s
                """, (f'%{recipient_name}%', limit))
            else:
                # Top contributors overall
                cur.execute("""
                    SELECT 
                        contrib.full_name,
                        contrib.contributor_type,
                        SUM(c.amount) as total_given,
                        COUNT(DISTINCT c.recipient_id) as num_recipients
                    FROM contributions c
                    JOIN contributors contrib ON c.contributor_id = contrib.id
                    GROUP BY contrib.id, contrib.full_name, contrib.contributor_type
                    ORDER BY total_given DESC
                    LIMIT %s
                """, (limit,))
            
            results = cur.fetchall()
            return {
                'type': 'top_contributors',
                'limit': limit,
                'results': [
                    {
                        'name': r[0],
                        'type': r[1],
                        'total_given': float(r[2]),
                        'num_recipients': r[3] if len(r) > 3 else None,
                        'num_contributions': r[3] if len(r) == 4 else None
                    }
                    for r in results
                ]
            }
        
        elif 'recipient' in query or 'candidate' in query:
            cur.execute("""
                SELECT 
                    r.full_name,
                    r.recipient_type,
                    SUM(c.amount) as total_received,
                    COUNT(DISTINCT c.contributor_id) as num_contributors
                FROM contributions c
                JOIN recipients r ON c.recipient_id = r.id
                GROUP BY r.id, r.full_name, r.recipient_type
                ORDER BY total_received DESC
                LIMIT %s
            """, (limit,))
            
            results = cur.fetchall()
            return {
                'type': 'top_recipients',
                'limit': limit,
                'results': [
                    {
                        'name': r[0],
                        'type': r[1],
                        'total_received': float(r[2]),
                        'num_contributors': r[3]
                    }
                    for r in results
                ]
            }
        
        elif 'bundler' in query or 'intermediar' in query:
            cur.execute("""
                SELECT 
                    i.full_name,
                    COUNT(DISTINCT c.contributor_id) as num_contributors,
                    COUNT(DISTINCT c.recipient_id) as num_recipients,
                    SUM(c.amount) as total_bundled
                FROM intermediaries i
                JOIN contributions c ON i.id = c.intermediary_id
                GROUP BY i.id, i.full_name
                ORDER BY total_bundled DESC
                LIMIT %s
            """, (limit,))
            
            results = cur.fetchall()
            return {
                'type': 'top_bundlers',
                'limit': limit,
                'results': [
                    {
                        'name': r[0],
                        'num_contributors': r[1],
                        'num_recipients': r[2],
                        'total_bundled': float(r[3])
                    }
                    for r in results
                ]
            }
        
        return {'error': 'Could not determine query type'}
    
    def _handle_keyword_search(self, query: str) -> Dict[str, Any]:
        """Handle general keyword search across entities."""
        cur = self.graph.conn.cursor()
        results = {
            'query': query,
            'results': {
                'contributors': [],
                'recipients': [],
                'intermediaries': []
            }
        }
        
        # Search contributors
        cur.execute("""
            SELECT 
                id, full_name, contributor_type,
                (SELECT SUM(amount) FROM contributions WHERE contributor_id = contributors.id) as total_given
            FROM contributors
            WHERE full_name ILIKE %s
            LIMIT 10
        """, (f'%{query}%',))
        
        for row in cur.fetchall():
            results['results']['contributors'].append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'total_given': float(row[3]) if row[3] else 0
            })
        
        # Search recipients
        cur.execute("""
            SELECT 
                id, full_name, recipient_type,
                (SELECT SUM(amount) FROM contributions WHERE recipient_id = recipients.id) as total_received
            FROM recipients
            WHERE full_name ILIKE %s
            LIMIT 10
        """, (f'%{query}%',))
        
        for row in cur.fetchall():
            results['results']['recipients'].append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'total_received': float(row[3]) if row[3] else 0
            })
        
        # Search intermediaries
        cur.execute("""
            SELECT 
                id, full_name,
                (SELECT COUNT(DISTINCT contributor_id) FROM contributions WHERE intermediary_id = intermediaries.id) as num_contributors,
                (SELECT SUM(amount) FROM contributions WHERE intermediary_id = intermediaries.id) as total_bundled
            FROM intermediaries
            WHERE full_name ILIKE %s
            LIMIT 10
        """, (f'%{query}%',))
        
        for row in cur.fetchall():
            results['results']['intermediaries'].append({
                'id': row[0],
                'name': row[1],
                'num_contributors': row[2] or 0,
                'total_bundled': float(row[3]) if row[3] else 0
            })
        
        return results
    
    def suggest_queries(self) -> List[str]:
        """Suggest example queries users can try."""
        return [
            "Show me the network of Bloomberg",
            "Who are the top 10 contributors?",
            "Find patterns in contributions",
            "Show influence of Real Estate Board",
            "Who did Eric Adams receive money from?",
            "Show bundler network of [intermediary name]",
            "Trace money flow from unions to Eric Adams",
            "Who gives together?",
            "Top recipients by total raised",
            "Analyze influence of Hotel Trades Council"
        ]

# Example usage
if __name__ == "__main__":
    nlp = GraphNLPQuery()
    
    print("Political Finance Graph - Natural Language Query Interface")
    print("=" * 60)
    print("\nExample queries:")
    for q in nlp.suggest_queries()[:5]:
        print(f"  - {q}")
    
    print("\n" + "=" * 60)
    
    # Test some queries
    test_queries = [
        "Top 5 contributors",
        "Show network of Bloomberg",
        "Find patterns"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        result = nlp.execute_query(query)
        if 'error' in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Result type: {result.get('type', 'network_data')}")
            if 'results' in result and isinstance(result['results'], list):
                print(f"Found {len(result['results'])} results")