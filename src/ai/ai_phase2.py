"""Phase 2 AI Integration - Advanced capabilities."""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
import sys
import os

# Import Phase 1 modules
from .ai_unified import UnifiedAI
from .modern_embeddings import ModernEmbeddings, OptimizedSemanticSearch
from .modern_clustering import ModernClustering, AnomalyDetector

# Import Phase 2 modules
from .advanced_nlp import AdvancedNLP, NetworkAnalyzer, ContributionPredictor
from .enhanced_matching import EnhancedMatcher, RelationshipAnalyzer

# Database connection
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager_v2 import NYCCFBDatabase

class Phase2AI:
    """Advanced AI system with Phase 2 capabilities."""
    
    def __init__(self):
        # Phase 1 components
        self.base_ai = UnifiedAI()
        
        # Phase 2 components
        self.nlp = AdvancedNLP()
        self.network = NetworkAnalyzer()
        self.predictor = ContributionPredictor()
        self.matcher = EnhancedMatcher()
        self.relationship_analyzer = RelationshipAnalyzer()
        
        # Database
        self.db = NYCCFBDatabase()
        
        # Cache
        self.data_cache = {}
        
    def initialize(self):
        """Initialize all AI components."""
        print("Initializing Phase 2 AI system...")
        
        # Initialize base system
        self.base_ai.initialize()
        
        # Load additional data for Phase 2
        self._load_phase2_data()
        
        print("✓ Phase 2 AI system initialized")
    
    def _load_phase2_data(self):
        """Load additional data needed for Phase 2."""
        
        # Load contribution data with more details
        query = """
            SELECT 
                c.*,
                cont.full_name as contributor_name,
                cont.occupation,
                cont.city,
                cont.state,
                cont.latitude,
                cont.longitude
            FROM contributions c
            LEFT JOIN contributors cont ON c.contributor_id = cont.id
            LIMIT 5000
        """
        
        try:
            self.data_cache['contributions'] = self.db.execute_query(query)
        except:
            self.data_cache['contributions'] = pd.DataFrame()
    
    # ========== Advanced NLP Features ==========
    
    def analyze_text_sentiment(self, text: str) -> Dict:
        """Analyze sentiment of any text."""
        return self.nlp.analyze_sentiment(text)
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities from text."""
        return self.nlp.extract_entities(text)
    
    def categorize_occupations(self, df: pd.DataFrame) -> pd.DataFrame:
        """Categorize occupations in a dataframe."""
        
        if 'occupation' in df.columns:
            df['occupation_category'] = df['occupation'].apply(
                self.nlp.categorize_occupation
            )
        
        return df
    
    def analyze_contribution_purposes(self, limit: int = 100) -> pd.DataFrame:
        """Analyze purposes of contributions."""
        
        query = """
            SELECT 
                purpose_code,
                description,
                COUNT(*) as count,
                SUM(amount) as total_amount,
                AVG(amount) as avg_amount
            FROM expenditures
            WHERE purpose_code IS NOT NULL
            GROUP BY purpose_code, description
            ORDER BY total_amount DESC
            LIMIT %s
        """
        
        try:
            purposes = self.db.execute_query(query, (limit,))
            
            # Analyze each purpose
            analyses = []
            for _, row in purposes.iterrows():
                analysis = self.nlp.analyze_contribution_purpose(
                    row.get('purpose_code'),
                    row.get('description')
                )
                analyses.append({
                    **row.to_dict(),
                    **analysis
                })
            
            return pd.DataFrame(analyses)
        except:
            return pd.DataFrame()
    
    # ========== Network Analysis Features ==========
    
    def build_contribution_network(self) -> Dict:
        """Build and analyze contribution network."""
        
        if 'contributions' not in self.data_cache or self.data_cache['contributions'].empty:
            return {}
        
        # Build network
        graph = self.network.build_contributor_network(self.data_cache['contributions'])
        
        # Get metrics
        metrics = self.network.calculate_network_metrics()
        
        # Find influential nodes
        influential = self.network.find_influential_nodes(top_n=10)
        
        # Find communities
        communities = self.network.find_communities()
        
        return {
            'metrics': metrics,
            'influential_nodes': influential,
            'num_communities': len(communities),
            'largest_community_size': max(len(c) for c in communities.values()) if communities else 0
        }
    
    def find_influence_networks(self, contributor_name: str) -> Dict:
        """Find influence network around a specific contributor."""
        
        if not self.network.graph.has_node(contributor_name):
            return {'error': 'Contributor not found in network'}
        
        # Get neighbors
        neighbors = list(self.network.graph.neighbors(contributor_name))
        
        # Calculate influence metrics
        degree = self.network.graph.degree(contributor_name)
        
        # Get connected contributions
        total_influence = sum(
            self.network.graph[contributor_name][neighbor].get('weight', 0)
            for neighbor in neighbors
        )
        
        return {
            'contributor': contributor_name,
            'direct_connections': len(neighbors),
            'degree': degree,
            'total_influence_amount': total_influence,
            'top_connections': neighbors[:10]
        }
    
    # ========== Predictive Features ==========
    
    def predict_future_contributions(self, periods: int = 3) -> pd.DataFrame:
        """Predict future contribution patterns."""
        
        if 'contributions' in self.data_cache:
            return self.predictor.forecast_contributions(
                self.data_cache['contributions'],
                periods
            )
        return pd.DataFrame()
    
    def predict_contributor_value(self, contributor_data: Dict) -> Dict:
        """Predict lifetime value and segment of a contributor."""
        
        predicted_amount = self.predictor.predict_contribution_amount(contributor_data)
        segment = self.predictor.predict_contributor_segment(contributor_data)
        
        return {
            'predicted_next_contribution': predicted_amount,
            'contributor_segment': segment,
            'lifetime_value_estimate': predicted_amount * 3  # Simple estimate
        }
    
    # ========== Enhanced Matching Features ==========
    
    def match_voter_to_contributor(self, voter_data: Dict) -> List[Dict]:
        """Find potential contributor matches for a voter."""
        
        # Get contributors to match against
        query = """
            SELECT * FROM contributors 
            WHERE city = %s OR zip_code = %s
            LIMIT 100
        """
        
        try:
            candidates = self.db.execute_query(
                query, 
                (voter_data.get('city', ''), voter_data.get('zip_code', ''))
            )
            
            matches = []
            for _, contributor in candidates.iterrows():
                result = self.matcher.match_voter_contributor(
                    voter_data,
                    contributor.to_dict()
                )
                
                if result['match_score'] > 0.3:
                    matches.append({
                        'contributor_id': contributor['id'],
                        'contributor_name': contributor['full_name'],
                        **result
                    })
            
            # Sort by match score
            matches.sort(key=lambda x: x['match_score'], reverse=True)
            return matches[:10]
            
        except:
            return []
    
    def find_household_networks(self) -> List[Dict]:
        """Find household-based contribution networks."""
        
        query = """
            SELECT 
                full_name,
                address,
                city,
                zip_code,
                total_contributions
            FROM contributors
            WHERE address IS NOT NULL
            AND city IS NOT NULL
            LIMIT 1000
        """
        
        try:
            data = self.db.execute_query(query)
            return self.matcher.find_household_connections(data)
        except:
            return []
    
    def analyze_relationships(self) -> List[Dict]:
        """Analyze relationships between contributors."""
        
        query = """
            SELECT 
                full_name,
                last_name,
                address,
                employer,
                latitude,
                longitude
            FROM contributors
            WHERE full_name IS NOT NULL
            LIMIT 1000
        """
        
        try:
            data = self.db.execute_query(query)
            return self.relationship_analyzer.infer_relationships(data)
        except:
            return []
    
    # ========== Intelligent Insights ==========
    
    def generate_insights(self) -> Dict:
        """Generate intelligent insights from the data."""
        
        insights = {
            'key_findings': [],
            'recommendations': [],
            'alerts': []
        }
        
        # Analyze contribution patterns
        try:
            patterns = self.base_ai.analyze_contribution_patterns()
            
            if patterns:
                if patterns.get('trend') == 'increasing':
                    insights['key_findings'].append(
                        f"Contributions are trending upward with {patterns.get('trend_strength', 0):.1%} correlation"
                    )
                
                if patterns.get('peak_amount', 0) > 1000000:
                    insights['alerts'].append(
                        f"Peak monthly contributions reached ${patterns['peak_amount']:,.0f}"
                    )
        except:
            pass
        
        # Network insights
        try:
            network_data = self.build_contribution_network()
            
            if network_data.get('metrics'):
                metrics = network_data['metrics']
                
                if metrics.get('density', 0) < 0.1:
                    insights['key_findings'].append(
                        "Contribution network is sparse - most contributors are not connected"
                    )
                
                if metrics.get('num_connected_components', 0) > 10:
                    insights['key_findings'].append(
                        f"Found {metrics['num_connected_components']} separate contribution networks"
                    )
        except:
            pass
        
        # Anomaly insights
        try:
            anomalies = self.base_ai.detect_anomalous_contributions(limit=5)
            
            if not anomalies.empty:
                max_anomaly = anomalies.iloc[0]['amount'] if 'amount' in anomalies.columns else 0
                if max_anomaly > 100000:
                    insights['alerts'].append(
                        f"Detected unusually large contribution: ${max_anomaly:,.0f}"
                    )
        except:
            pass
        
        # Generate recommendations
        if insights['key_findings']:
            insights['recommendations'].append(
                "Review identified patterns for compliance and reporting requirements"
            )
        
        if insights['alerts']:
            insights['recommendations'].append(
                "Investigate flagged transactions for potential issues"
            )
        
        return insights
    
    def get_phase2_status(self) -> Dict:
        """Get status of Phase 2 AI capabilities."""
        
        return {
            'phase': 2,
            'capabilities': {
                'nlp': {
                    'sentiment_analysis': True,
                    'entity_extraction': True,
                    'occupation_categorization': True,
                    'keyword_extraction': True
                },
                'network_analysis': {
                    'contribution_networks': True,
                    'influence_mapping': True,
                    'community_detection': True
                },
                'predictive': {
                    'contribution_forecasting': True,
                    'donor_segmentation': True,
                    'value_prediction': True
                },
                'matching': {
                    'enhanced_voter_matching': True,
                    'household_detection': True,
                    'relationship_inference': True,
                    'name_variations': True,
                    'phonetic_matching': True
                },
                'insights': {
                    'automated_insights': True,
                    'trend_detection': True,
                    'anomaly_alerts': True,
                    'recommendations': True
                }
            },
            'data_loaded': {
                'contributions': len(self.data_cache.get('contributions', [])),
                'network_nodes': self.network.graph.number_of_nodes(),
                'network_edges': self.network.graph.number_of_edges()
            }
        }


# Convenience function for creating Phase 2 AI
def create_phase2_ai():
    """Create and initialize Phase 2 AI system."""
    ai = Phase2AI()
    ai.initialize()
    return ai