"""Unified AI module with modern optimized implementations."""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
import os
import sys

# Import our modern modules
from .modern_embeddings import ModernEmbeddings, OptimizedSemanticSearch
from .modern_clustering import ModernClustering, AnomalyDetector

# Database connection
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager_v2 import NYCCFBDatabase

class UnifiedAI:
    """Main AI interface for the NYC Campaign Finance system."""
    
    def __init__(self):
        self.db = NYCCFBDatabase()
        self.embeddings = ModernEmbeddings()
        self.search = OptimizedSemanticSearch()
        self.clustering = ModernClustering()
        self.anomaly_detector = AnomalyDetector()
        
        # Cache
        self.contributor_data = None
        self.contributor_embeddings = None
        
    def initialize(self):
        """Initialize AI system with database data."""
        print("Initializing AI system...")
        
        # Load contributor data
        self.contributor_data = self._load_contributor_data()
        
        if not self.contributor_data.empty:
            # Build search index
            self._build_search_index()
            print(f"✓ Initialized with {len(self.contributor_data):,} contributors")
        else:
            print("⚠ No contributor data found")
    
    def _load_contributor_data(self) -> pd.DataFrame:
        """Load contributor data from database."""
        query = """
            SELECT 
                c.id,
                c.full_name,
                c.first_name,
                c.last_name,
                c.contributor_type,
                c.occupation,
                c.city,
                c.state,
                c.zip_code,
                c.total_contributions,
                c.contribution_count,
                c.avg_contribution,
                c.created_at
            FROM contributors c
            WHERE c.full_name IS NOT NULL
            LIMIT 10000
        """
        
        try:
            return self.db.execute_query(query)
        except:
            # If contributors table doesn't exist or has different structure
            return pd.DataFrame()
    
    def _build_search_index(self):
        """Build search index for contributors."""
        if self.contributor_data.empty:
            return
        
        # Create text representations
        texts = []
        ids = []
        metadata = []
        
        for _, row in self.contributor_data.iterrows():
            # Build searchable text
            text_parts = [
                str(row['full_name']),
                str(row['occupation']) if pd.notna(row['occupation']) else '',
                str(row['city']) if pd.notna(row['city']) else '',
                str(row['state']) if pd.notna(row['state']) else '',
                f"total_contributions:{row['total_contributions']}" if pd.notna(row['total_contributions']) else ''
            ]
            
            text = ' '.join(filter(None, text_parts))
            texts.append(text)
            ids.append(str(row['id']))
            
            # Store metadata
            metadata.append({
                'name': row['full_name'],
                'type': row['contributor_type'],
                'city': row['city'],
                'state': row['state'],
                'total': row['total_contributions']
            })
        
        # Build embeddings and search index
        self.contributor_embeddings = self.embeddings.create_embeddings(texts, ids, method='tfidf_svd')
        self.search.build_index(texts, ids, metadata)
    
    def search_contributors(self, query: str, top_k: int = 10, 
                          filters: Optional[Dict] = None) -> pd.DataFrame:
        """Search contributors using semantic search."""
        
        if self.contributor_embeddings is None:
            self.initialize()
        
        # Perform search
        results = self.search.search(query, top_k, filters)
        
        # Enhance results with database data
        if not results.empty and not self.contributor_data.empty:
            results = results.merge(
                self.contributor_data[['id', 'full_name', 'contributor_type', 'total_contributions']],
                on='id',
                how='left'
            )
        
        return results
    
    def find_similar_contributors(self, contributor_id: str, top_k: int = 10) -> pd.DataFrame:
        """Find contributors similar to a given contributor."""
        
        if self.contributor_embeddings is None:
            self.initialize()
        
        # Find similar
        similar = self.embeddings.find_similar(contributor_id, top_k)
        
        # Convert to dataframe
        results = pd.DataFrame(similar, columns=['id', 'similarity', 'text'])
        
        # Enhance with database data
        if not results.empty and not self.contributor_data.empty:
            results = results.merge(
                self.contributor_data[['id', 'full_name', 'contributor_type', 'total_contributions']],
                on='id',
                how='left'
            )
        
        return results
    
    def cluster_contributors(self, method: str = 'auto') -> Dict:
        """Cluster contributors based on their characteristics."""
        
        if self.contributor_embeddings is None:
            self.initialize()
        
        if self.contributor_embeddings is None:
            return {}
        
        # Perform clustering
        if method == 'auto':
            results = self.clustering.auto_cluster(self.contributor_embeddings)
        else:
            labels = self.clustering.cluster_dbscan(self.contributor_embeddings)
            results = {
                'labels': labels,
                'n_clusters': len(set(labels)) - (1 if -1 in labels else 0),
                'stats': self.clustering.get_cluster_stats()
            }
        
        return results
    
    def detect_anomalous_contributions(self, limit: int = 100) -> pd.DataFrame:
        """Detect anomalous contribution patterns."""
        
        # Load contribution data
        query = """
            SELECT 
                c.id,
                c.refno,
                c.amount,
                c.date,
                cont.full_name as contributor_name,
                cont.total_contributions,
                cont.contribution_count,
                cont.avg_contribution
            FROM contributions c
            LEFT JOIN contributors cont ON c.contributor_id = cont.id
            WHERE c.amount IS NOT NULL
            ORDER BY c.amount DESC
            LIMIT 10000
        """
        
        try:
            contribution_data = self.db.execute_query(query)
        except:
            # Try simpler query if tables don't match
            query = """
                SELECT 
                    id,
                    amount,
                    date
                FROM contributions
                WHERE amount IS NOT NULL
                ORDER BY amount DESC
                LIMIT 10000
            """
            contribution_data = self.db.execute_query(query)
        
        if contribution_data.empty:
            return pd.DataFrame()
        
        # Prepare features for anomaly detection
        features = []
        if 'amount' in contribution_data.columns:
            features.append('amount')
        if 'contribution_count' in contribution_data.columns:
            features.append('contribution_count')
        if 'total_contributions' in contribution_data.columns:
            features.append('total_contributions')
        
        if not features:
            features = ['amount']
        
        # Detect anomalies
        anomalies = self.anomaly_detector.detect_anomalies(
            contribution_data,
            features,
            method='ensemble'
        )
        
        return anomalies.head(limit)
    
    def analyze_contribution_patterns(self) -> Dict:
        """Analyze overall contribution patterns."""
        
        # Load aggregated data
        query = """
            SELECT 
                DATE_TRUNC('month', date) as month,
                COUNT(*) as num_contributions,
                SUM(amount) as total_amount,
                AVG(amount) as avg_amount,
                STDDEV(amount) as std_amount
            FROM contributions
            WHERE date IS NOT NULL
            GROUP BY DATE_TRUNC('month', date)
            ORDER BY month
        """
        
        try:
            patterns = self.db.execute_query(query)
        except:
            # Fallback query
            patterns = pd.DataFrame()
        
        if patterns.empty:
            return {}
        
        # Calculate statistics
        analysis = {
            'total_contributions': int(patterns['num_contributions'].sum()),
            'total_amount': float(patterns['total_amount'].sum()),
            'avg_monthly_contributions': float(patterns['num_contributions'].mean()),
            'avg_monthly_amount': float(patterns['total_amount'].mean()),
            'peak_month': patterns.loc[patterns['total_amount'].idxmax(), 'month'] if not patterns.empty else None,
            'peak_amount': float(patterns['total_amount'].max()) if not patterns.empty else 0
        }
        
        # Detect trends
        if len(patterns) > 1:
            from scipy import stats
            x = np.arange(len(patterns))
            y = patterns['total_amount'].values
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            
            analysis['trend'] = 'increasing' if slope > 0 else 'decreasing'
            analysis['trend_strength'] = abs(r_value)
        
        return analysis
    
    def find_duplicate_contributors(self, threshold: float = 0.95) -> pd.DataFrame:
        """Find potential duplicate contributor records."""
        
        if self.contributor_embeddings is None:
            self.initialize()
        
        if self.contributor_embeddings is None:
            return pd.DataFrame()
        
        # Find duplicates
        duplicates = self.search.find_duplicates(threshold)
        
        # Convert to dataframe with details
        dup_data = []
        for id1, id2, score in duplicates:
            # Get contributor details
            contrib1 = self.contributor_data[self.contributor_data['id'] == id1].iloc[0] if not self.contributor_data.empty else {}
            contrib2 = self.contributor_data[self.contributor_data['id'] == id2].iloc[0] if not self.contributor_data.empty else {}
            
            dup_data.append({
                'id1': id1,
                'name1': contrib1.get('full_name', ''),
                'id2': id2,
                'name2': contrib2.get('full_name', ''),
                'similarity': score
            })
        
        return pd.DataFrame(dup_data)
    
    def get_ai_status(self) -> Dict:
        """Get status of AI system."""
        
        status = {
            'initialized': self.contributor_embeddings is not None,
            'contributors_indexed': len(self.contributor_data) if self.contributor_data is not None else 0,
            'embedding_dimensions': self.contributor_embeddings.shape[1] if self.contributor_embeddings is not None else 0,
            'available_features': [
                'semantic_search',
                'similarity_matching',
                'clustering',
                'anomaly_detection',
                'duplicate_detection',
                'pattern_analysis'
            ]
        }
        
        return status


# Convenience functions for direct use
def create_ai_system():
    """Create and initialize the AI system."""
    ai = UnifiedAI()
    ai.initialize()
    return ai

def search(query: str, top_k: int = 10):
    """Quick search function."""
    ai = create_ai_system()
    return ai.search_contributors(query, top_k)

def find_anomalies(limit: int = 50):
    """Quick anomaly detection."""
    ai = create_ai_system()
    return ai.detect_anomalous_contributions(limit)