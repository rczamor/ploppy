"""Graph analysis module for NYC Campaign Finance data.

This module implements graph database capabilities on top of PostgreSQL,
enabling network analysis of political contributions, expenditures, and intermediary relationships.
"""

import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Set
import os
from datetime import datetime
import json

DATABASE_URL = os.environ.get('DATABASE_URL')

class PoliticalFinanceGraph:
    """Graph analysis for political finance networks."""
    
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self.conn.autocommit = True
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()
    
    def create_graph_views(self):
        """Create materialized views for graph traversal."""
        cur = self.conn.cursor()
        
        # Contributor-Recipient edges with intermediaries
        cur.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS graph_contribution_edges AS
            SELECT 
                c.contributor_id as source_id,
                'contributor' as source_type,
                c.recipient_id as target_id,
                'recipient' as target_type,
                c.amount as weight,
                c.transaction_date as edge_date,
                c.intermediary_id,
                CASE 
                    WHEN c.intermediary_id IS NOT NULL THEN 'intermediated'
                    ELSE 'direct'
                END as edge_type
            FROM contributions c
            WHERE c.amount > 0
        """)
        
        # Recipient-Payee edges from expenditures
        cur.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS graph_expenditure_edges AS
            SELECT 
                e.recipient_id as source_id,
                'recipient' as source_type,
                e.payee_name as target_id,
                'payee' as target_type,
                e.amount as weight,
                e.payment_date as edge_date,
                e.purpose_code,
                'expenditure' as edge_type
            FROM expenditures e
            WHERE e.amount > 0
        """)
        
        # Intermediary connections
        cur.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS graph_intermediary_edges AS
            SELECT DISTINCT
                c.contributor_id as source_id,
                'contributor' as source_type,
                c.intermediary_id as target_id,
                'intermediary' as target_type,
                COUNT(*) as weight,
                MIN(c.transaction_date) as first_date,
                MAX(c.transaction_date) as last_date,
                SUM(c.amount) as total_amount
            FROM contributions c
            WHERE c.intermediary_id IS NOT NULL
            GROUP BY c.contributor_id, c.intermediary_id
        """)
        
        # Create indexes for performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_contrib_edges_source ON graph_contribution_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_contrib_edges_target ON graph_contribution_edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_expend_edges_source ON graph_expenditure_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_interm_edges_source ON graph_intermediary_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_interm_edges_target ON graph_intermediary_edges(target_id);
        """)
        
        self.conn.commit()
        print("Graph views created successfully")
    
    def refresh_graph_views(self):
        """Refresh materialized views with latest data."""
        cur = self.conn.cursor()
        cur.execute("REFRESH MATERIALIZED VIEW graph_contribution_edges")
        cur.execute("REFRESH MATERIALIZED VIEW graph_expenditure_edges")
        cur.execute("REFRESH MATERIALIZED VIEW graph_intermediary_edges")
        print("Graph views refreshed")
    
    def find_contributor_network(self, contributor_name: str, depth: int = 2) -> Dict:
        """Find network of contributors connected through shared recipients."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Find contributor ID
        cur.execute("""
            SELECT id, full_name, normalized_name 
            FROM contributors 
            WHERE normalized_name ILIKE %s OR full_name ILIKE %s
            LIMIT 1
        """, (f'%{contributor_name}%', f'%{contributor_name}%'))
        
        contributor = cur.fetchone()
        if not contributor:
            return {"error": "Contributor not found"}
        
        network = {
            "center": {
                "id": contributor['id'],
                "name": contributor['full_name'],
                "type": "contributor"
            },
            "nodes": [],
            "edges": []
        }
        
        # Get direct recipients
        cur.execute("""
            SELECT DISTINCT
                r.id, r.full_name, r.recipid,
                COUNT(*) as num_contributions,
                SUM(c.amount) as total_amount,
                AVG(c.amount) as avg_amount
            FROM contributions c
            JOIN recipients r ON c.recipient_id = r.id
            WHERE c.contributor_id = %s
            GROUP BY r.id, r.full_name, r.recipid
        """, (contributor['id'],))
        
        recipients = cur.fetchall()
        for recip in recipients:
            network['nodes'].append({
                "id": recip['id'],
                "name": recip['full_name'],
                "type": "recipient",
                "total_received": float(recip['total_amount'])
            })
            network['edges'].append({
                "source": contributor['id'],
                "target": recip['id'],
                "weight": float(recip['total_amount']),
                "count": recip['num_contributions']
            })
        
        if depth >= 2:
            # Find co-contributors (those who gave to same recipients)
            recipient_ids = [r['id'] for r in recipients]
            if recipient_ids:
                cur.execute("""
                    WITH co_contributors AS (
                        SELECT 
                            c2.contributor_id,
                            COUNT(DISTINCT c2.recipient_id) as shared_recipients,
                            SUM(c2.amount) as total_amount
                        FROM contributions c1
                        JOIN contributions c2 ON c1.recipient_id = c2.recipient_id
                        WHERE c1.contributor_id = %s 
                            AND c2.contributor_id != %s
                            AND c1.recipient_id = ANY(%s)
                        GROUP BY c2.contributor_id
                        HAVING COUNT(DISTINCT c2.recipient_id) >= 2
                    )
                    SELECT 
                        cc.*,
                        contrib.full_name,
                        contrib.contributor_type
                    FROM co_contributors cc
                    JOIN contributors contrib ON cc.contributor_id = contrib.id
                    ORDER BY shared_recipients DESC
                    LIMIT 20
                """, (contributor['id'], contributor['id'], recipient_ids))
                
                co_contributors = cur.fetchall()
                for co_contrib in co_contributors:
                    network['nodes'].append({
                        "id": co_contrib['contributor_id'],
                        "name": co_contrib['full_name'],
                        "type": "co-contributor",
                        "shared_recipients": co_contrib['shared_recipients']
                    })
        
        return network
    
    def find_intermediary_network(self, intermediary_name: str) -> Dict:
        """Find network of contributions flowing through an intermediary."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Find intermediary
        cur.execute("""
            SELECT id, full_name, normalized_name
            FROM intermediaries
            WHERE normalized_name ILIKE %s OR full_name ILIKE %s
            LIMIT 1
        """, (f'%{intermediary_name}%', f'%{intermediary_name}%'))
        
        intermediary = cur.fetchone()
        if not intermediary:
            return {"error": "Intermediary not found"}
        
        network = {
            "center": {
                "id": intermediary['id'],
                "name": intermediary['full_name'],
                "type": "intermediary"
            },
            "nodes": [],
            "edges": [],
            "stats": {}
        }
        
        # Get all contributions through this intermediary
        cur.execute("""
            SELECT 
                c.contributor_id,
                c.recipient_id,
                contrib.full_name as contributor_name,
                r.full_name as recipient_name,
                COUNT(*) as num_contributions,
                SUM(c.amount) as total_amount,
                MIN(c.transaction_date) as first_date,
                MAX(c.transaction_date) as last_date
            FROM contributions c
            JOIN contributors contrib ON c.contributor_id = contrib.id
            JOIN recipients r ON c.recipient_id = r.id
            WHERE c.intermediary_id = %s
            GROUP BY c.contributor_id, c.recipient_id, contrib.full_name, r.full_name
        """, (intermediary['id'],))
        
        flows = cur.fetchall()
        
        contributors = {}
        recipients = {}
        total_amount = 0
        
        for flow in flows:
            # Add contributor node
            if flow['contributor_id'] not in contributors:
                contributors[flow['contributor_id']] = {
                    "id": flow['contributor_id'],
                    "name": flow['contributor_name'],
                    "type": "contributor",
                    "total_given": 0
                }
            contributors[flow['contributor_id']]['total_given'] += float(flow['total_amount'])
            
            # Add recipient node
            if flow['recipient_id'] not in recipients:
                recipients[flow['recipient_id']] = {
                    "id": flow['recipient_id'],
                    "name": flow['recipient_name'],
                    "type": "recipient",
                    "total_received": 0
                }
            recipients[flow['recipient_id']]['total_received'] += float(flow['total_amount'])
            
            # Add edges
            network['edges'].append({
                "source": flow['contributor_id'],
                "target": intermediary['id'],
                "weight": float(flow['total_amount']),
                "type": "contribution_to_intermediary"
            })
            network['edges'].append({
                "source": intermediary['id'],
                "target": flow['recipient_id'],
                "weight": float(flow['total_amount']),
                "type": "intermediary_to_recipient"
            })
            
            total_amount += float(flow['total_amount'])
        
        network['nodes'].extend(contributors.values())
        network['nodes'].extend(recipients.values())
        
        network['stats'] = {
            "total_amount": total_amount,
            "num_contributors": len(contributors),
            "num_recipients": len(recipients),
            "num_transactions": sum(f['num_contributions'] for f in flows)
        }
        
        return network
    
    def find_money_flow_path(self, start_entity: str, end_entity: str, max_hops: int = 3) -> List[Dict]:
        """Find paths showing how money flows between entities."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # This would use recursive CTEs for path finding
        # Simplified version showing direct paths
        paths = []
        
        # Check direct contribution path
        cur.execute("""
            SELECT 
                contrib.full_name as contributor,
                r.full_name as recipient,
                SUM(c.amount) as total_amount,
                COUNT(*) as num_transactions,
                STRING_AGG(DISTINCT i.full_name, ', ') as intermediaries
            FROM contributions c
            JOIN contributors contrib ON c.contributor_id = contrib.id
            JOIN recipients r ON c.recipient_id = r.id
            LEFT JOIN intermediaries i ON c.intermediary_id = i.id
            WHERE contrib.full_name ILIKE %s AND r.full_name ILIKE %s
            GROUP BY contrib.full_name, r.full_name
        """, (f'%{start_entity}%', f'%{end_entity}%'))
        
        direct_paths = cur.fetchall()
        for path in direct_paths:
            paths.append({
                "path_type": "direct_contribution",
                "hops": 1,
                "entities": [path['contributor'], path['recipient']],
                "total_amount": float(path['total_amount']),
                "num_transactions": path['num_transactions'],
                "intermediaries": path['intermediaries']
            })
        
        return paths
    
    def analyze_influence_network(self, entity_name: str, entity_type: str = 'auto') -> Dict:
        """Analyze influence network of an entity (contributor, recipient, or intermediary)."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        analysis = {
            "entity": entity_name,
            "type": entity_type,
            "influence_metrics": {},
            "connected_entities": []
        }
        
        # Auto-detect entity type if needed
        if entity_type == 'auto':
            # Check contributors
            cur.execute("SELECT COUNT(*) FROM contributors WHERE full_name ILIKE %s", (f'%{entity_name}%',))
            if cur.fetchone()[0] > 0:
                entity_type = 'contributor'
            else:
                cur.execute("SELECT COUNT(*) FROM recipients WHERE full_name ILIKE %s", (f'%{entity_name}%',))
                if cur.fetchone()[0] > 0:
                    entity_type = 'recipient'
                else:
                    cur.execute("SELECT COUNT(*) FROM intermediaries WHERE full_name ILIKE %s", (f'%{entity_name}%',))
                    if cur.fetchone()[0] > 0:
                        entity_type = 'intermediary'
        
        analysis['type'] = entity_type
        
        if entity_type == 'contributor':
            # Contributor influence metrics
            cur.execute("""
                WITH contrib_stats AS (
                    SELECT 
                        c.id,
                        c.full_name,
                        COUNT(DISTINCT contrib.recipient_id) as num_recipients,
                        COUNT(DISTINCT contrib.intermediary_id) as num_intermediaries,
                        SUM(contrib.amount) as total_given,
                        AVG(contrib.amount) as avg_contribution,
                        COUNT(*) as num_contributions
                    FROM contributors c
                    JOIN contributions contrib ON c.id = contrib.contributor_id
                    WHERE c.full_name ILIKE %s
                    GROUP BY c.id, c.full_name
                )
                SELECT * FROM contrib_stats
            """, (f'%{entity_name}%',))
            
            stats = cur.fetchone()
            if stats:
                analysis['influence_metrics'] = {
                    "total_given": float(stats['total_given']),
                    "num_recipients": stats['num_recipients'],
                    "num_intermediaries": stats['num_intermediaries'],
                    "avg_contribution": float(stats['avg_contribution']),
                    "num_contributions": stats['num_contributions']
                }
                
                # Get top recipients
                cur.execute("""
                    SELECT 
                        r.full_name,
                        SUM(c.amount) as total_amount,
                        COUNT(*) as num_contributions
                    FROM contributions c
                    JOIN recipients r ON c.recipient_id = r.id
                    WHERE c.contributor_id = (
                        SELECT id FROM contributors WHERE full_name ILIKE %s LIMIT 1
                    )
                    GROUP BY r.full_name
                    ORDER BY total_amount DESC
                    LIMIT 10
                """, (f'%{entity_name}%',))
                
                analysis['connected_entities'] = [
                    {
                        "name": row['full_name'],
                        "relationship": "gave_to",
                        "amount": float(row['total_amount']),
                        "transactions": row['num_contributions']
                    }
                    for row in cur.fetchall()
                ]
        
        elif entity_type == 'recipient':
            # Recipient influence metrics
            cur.execute("""
                WITH recip_stats AS (
                    SELECT 
                        r.id,
                        r.full_name,
                        COUNT(DISTINCT c.contributor_id) as num_contributors,
                        COUNT(DISTINCT c.intermediary_id) as num_intermediaries,
                        SUM(c.amount) as total_received,
                        AVG(c.amount) as avg_contribution,
                        COUNT(*) as num_contributions,
                        SUM(e.amount) as total_spent,
                        COUNT(DISTINCT e.payee_name) as num_payees
                    FROM recipients r
                    LEFT JOIN contributions c ON r.id = c.recipient_id
                    LEFT JOIN expenditures e ON r.id = e.recipient_id
                    WHERE r.full_name ILIKE %s
                    GROUP BY r.id, r.full_name
                )
                SELECT * FROM recip_stats
            """, (f'%{entity_name}%',))
            
            stats = cur.fetchone()
            if stats:
                analysis['influence_metrics'] = {
                    "total_received": float(stats['total_received']) if stats['total_received'] else 0,
                    "total_spent": float(stats['total_spent']) if stats['total_spent'] else 0,
                    "num_contributors": stats['num_contributors'],
                    "num_intermediaries": stats['num_intermediaries'],
                    "num_payees": stats['num_payees'],
                    "avg_contribution": float(stats['avg_contribution']) if stats['avg_contribution'] else 0,
                    "burn_rate": float(stats['total_spent']) / float(stats['total_received']) if stats['total_received'] else 0
                }
        
        return analysis
    
    def detect_contribution_patterns(self, min_amount: float = 1000) -> List[Dict]:
        """Detect interesting contribution patterns in the network."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        patterns = []
        
        # Pattern 1: Coordinated giving (multiple contributors giving similar amounts on same day)
        cur.execute("""
            WITH same_day_contributions AS (
                SELECT 
                    transaction_date,
                    recipient_id,
                    amount,
                    COUNT(DISTINCT contributor_id) as num_contributors,
                    STRING_AGG(DISTINCT contrib.full_name, ', ' ORDER BY contrib.full_name) as contributors,
                    r.full_name as recipient_name
                FROM contributions c
                JOIN contributors contrib ON c.contributor_id = contrib.id
                JOIN recipients r ON c.recipient_id = r.id
                WHERE c.amount >= %s
                    AND c.transaction_date IS NOT NULL
                GROUP BY transaction_date, recipient_id, amount, r.full_name
                HAVING COUNT(DISTINCT contributor_id) >= 3
            )
            SELECT * FROM same_day_contributions
            ORDER BY num_contributors DESC
            LIMIT 20
        """, (min_amount,))
        
        coordinated = cur.fetchall()
        for pattern in coordinated:
            patterns.append({
                "pattern_type": "coordinated_giving",
                "date": pattern['transaction_date'].strftime('%Y-%m-%d') if pattern['transaction_date'] else 'Unknown',
                "recipient": pattern['recipient_name'],
                "amount": float(pattern['amount']),
                "num_contributors": pattern['num_contributors'],
                "contributors": pattern['contributors'][:200] + '...' if len(pattern['contributors']) > 200 else pattern['contributors']
            })
        
        # Pattern 2: Max-out networks (contributors who max out to multiple candidates)
        cur.execute("""
            WITH max_contributions AS (
                SELECT 
                    contributor_id,
                    COUNT(DISTINCT recipient_id) as num_recipients,
                    SUM(amount) as total_given,
                    contrib.full_name as contributor_name
                FROM contributions c
                JOIN contributors contrib ON c.contributor_id = contrib.id
                WHERE c.amount >= 2750  -- Common max contribution limit
                GROUP BY contributor_id, contrib.full_name
                HAVING COUNT(DISTINCT recipient_id) >= 3
            )
            SELECT * FROM max_contributions
            ORDER BY num_recipients DESC
            LIMIT 20
        """)
        
        max_out = cur.fetchall()
        for pattern in max_out:
            patterns.append({
                "pattern_type": "max_out_network",
                "contributor": pattern['contributor_name'],
                "num_recipients": pattern['num_recipients'],
                "total_given": float(pattern['total_given'])
            })
        
        # Pattern 3: Bundler effectiveness
        cur.execute("""
            WITH bundler_stats AS (
                SELECT 
                    i.id,
                    i.full_name as bundler_name,
                    COUNT(DISTINCT c.contributor_id) as num_contributors,
                    COUNT(DISTINCT c.recipient_id) as num_recipients,
                    SUM(c.amount) as total_bundled,
                    AVG(c.amount) as avg_contribution
                FROM intermediaries i
                JOIN contributions c ON i.id = c.intermediary_id
                GROUP BY i.id, i.full_name
                HAVING SUM(c.amount) >= %s
            )
            SELECT * FROM bundler_stats
            ORDER BY total_bundled DESC
            LIMIT 20
        """, (min_amount * 10,))
        
        bundlers = cur.fetchall()
        for pattern in bundlers:
            patterns.append({
                "pattern_type": "power_bundler",
                "bundler": pattern['bundler_name'],
                "num_contributors": pattern['num_contributors'],
                "num_recipients": pattern['num_recipients'],
                "total_bundled": float(pattern['total_bundled']),
                "avg_contribution": float(pattern['avg_contribution'])
            })
        
        return patterns
    
    def get_network_statistics(self) -> Dict:
        """Get overall network statistics."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        stats = {}
        
        # Basic counts
        cur.execute("""
            SELECT 
                (SELECT COUNT(*) FROM contributors) as num_contributors,
                (SELECT COUNT(*) FROM recipients) as num_recipients,
                (SELECT COUNT(*) FROM intermediaries) as num_intermediaries,
                (SELECT COUNT(*) FROM contributions) as num_contributions,
                (SELECT COUNT(*) FROM expenditures) as num_expenditures,
                (SELECT SUM(amount) FROM contributions) as total_contributions,
                (SELECT SUM(amount) FROM expenditures) as total_expenditures
        """)
        
        basic_stats = cur.fetchone()
        stats.update(dict(basic_stats))
        
        # Network density metrics
        cur.execute("""
            WITH network_metrics AS (
                SELECT 
                    COUNT(DISTINCT contributor_id) as active_contributors,
                    COUNT(DISTINCT recipient_id) as active_recipients,
                    COUNT(DISTINCT intermediary_id) as active_intermediaries
                FROM contributions
                WHERE amount > 0
            )
            SELECT * FROM network_metrics
        """)
        
        network_stats = cur.fetchone()
        stats.update(dict(network_stats))
        
        # Calculate network density
        if stats['active_contributors'] and stats['active_recipients']:
            possible_edges = stats['active_contributors'] * stats['active_recipients']
            actual_edges = stats['num_contributions']
            stats['contribution_network_density'] = actual_edges / possible_edges if possible_edges > 0 else 0
        
        # Average degree (connections per node)
        cur.execute("""
            WITH contributor_degrees AS (
                SELECT 
                    contributor_id,
                    COUNT(DISTINCT recipient_id) as out_degree
                FROM contributions
                GROUP BY contributor_id
            )
            SELECT 
                AVG(out_degree) as avg_contributor_degree,
                MAX(out_degree) as max_contributor_degree
            FROM contributor_degrees
        """)
        
        degree_stats = cur.fetchone()
        stats.update(dict(degree_stats))
        
        return stats

# Helper functions for common graph queries
def find_shortest_path(start_entity: str, end_entity: str):
    """Find shortest path between two entities in the contribution network."""
    with PoliticalFinanceGraph() as graph:
        return graph.find_money_flow_path(start_entity, end_entity)

def get_entity_influence(entity_name: str):
    """Get influence metrics for an entity."""
    with PoliticalFinanceGraph() as graph:
        return graph.analyze_influence_network(entity_name)

def detect_patterns(min_amount: float = 1000):
    """Detect contribution patterns."""
    with PoliticalFinanceGraph() as graph:
        return graph.detect_contribution_patterns(min_amount)

if __name__ == "__main__":
    # Create/refresh graph views
    with PoliticalFinanceGraph() as graph:
        print("Creating graph views...")
        graph.create_graph_views()
        print("\nRefreshing graph data...")
        graph.refresh_graph_views()
        print("\nGraph database ready!")
        
        # Get network statistics
        stats = graph.get_network_statistics()
        print("\nNetwork Statistics:")
        print(f"  Contributors: {stats.get('num_contributors', 0):,}")
        print(f"  Recipients: {stats.get('num_recipients', 0):,}")
        print(f"  Intermediaries: {stats.get('num_intermediaries', 0):,}")
        print(f"  Total Contributions: ${stats.get('total_contributions', 0):,.2f}")
        print(f"  Total Expenditures: ${stats.get('total_expenditures', 0):,.2f}")