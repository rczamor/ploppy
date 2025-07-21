"""AI-powered search and analysis for NYC Campaign Finance data using available libraries."""

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.cluster import DBSCAN
import re
from typing import List, Dict, Tuple, Optional
from ..database.db_manager_v2 import NYCCFBDatabase
from ..database.code_mappings import parse_name, is_individual_name

# Import advanced NLP libraries
try:
    from gensim.models import Word2Vec, Doc2Vec
    from gensim.models.doc2vec import TaggedDocument
    import nltk
    from textblob import TextBlob
    ADVANCED_NLP = True
    
    # Download required NLTK data
    try:
        nltk.download('punkt', quiet=True)
        nltk.download('stopwords', quiet=True)
        nltk.download('wordnet', quiet=True)
        nltk.download('averaged_perceptron_tagger', quiet=True)
    except:
        pass
        
except ImportError:
    ADVANCED_NLP = False
    
from .ai_embeddings import AdvancedEmbeddings, SemanticSearchEngine
from .ai_time_series import ContributionForecaster
from .ai_entity_extraction import EntityExtractor
from .ai_fine_tuning import ModelFineTuner

# Try to import modern sentence-transformers
try:
    from .sentence_transformer_wrapper import sentence_transformer_wrapper
    MODERN_SEARCH_AVAILABLE = sentence_transformer_wrapper.available
except ImportError:
    MODERN_SEARCH_AVAILABLE = False

class ContributionAnalyzer:
    """AI-powered analysis for political contributions using advanced NLP."""
    
    def __init__(self):
        self.db = NYCCFBDatabase()
        self.vectorizer = None
        self.contributor_embeddings = None
        self.contributor_data = None
        self.scaler = StandardScaler()
        self.word2vec_model = None
        self.doc2vec_model = None
        self.advanced_embeddings = AdvancedEmbeddings() if ADVANCED_NLP else None
        self.semantic_engine = SemanticSearchEngine() if ADVANCED_NLP else None
        self.forecaster = ContributionForecaster()
        self.entity_extractor = EntityExtractor()
        self.fine_tuner = ModelFineTuner()
        
    def build_contributor_index(self):
        """Build searchable index of contributors using advanced embeddings."""
        query = """
            SELECT 
                c.id,
                c.full_name,
                c.last_name,
                c.first_name,
                c.contributor_type,
                c.occupation,
                e.name as employer_name,
                l.city,
                l.state,
                COUNT(DISTINCT cont.id) as num_contributions,
                SUM(cont.amount) as total_amount,
                AVG(cont.amount) as avg_amount
            FROM contributors c
            LEFT JOIN employers e ON c.employer_id = e.id
            LEFT JOIN contributions cont ON c.id = cont.contributor_id
            LEFT JOIN locations l ON cont.location_id = l.id
            GROUP BY c.id, c.full_name, c.last_name, c.first_name, 
                     c.contributor_type, c.occupation, e.name, l.city, l.state
        """
        
        self.contributor_data = self.db.execute_query(query)
        
        if self.contributor_data.empty:
            return
        
        # Create searchable text for each contributor
        search_texts = []
        for _, row in self.contributor_data.iterrows():
            text_parts = [
                str(row['full_name']),
                str(row['occupation']) if pd.notna(row['occupation']) else '',
                str(row['employer_name']) if pd.notna(row['employer_name']) else '',
                str(row['city']) if pd.notna(row['city']) else '',
                str(row['state']) if pd.notna(row['state']) else '',
                str(row['contributor_type'])
            ]
            search_texts.append(' '.join(filter(None, text_parts)))
        
        if ADVANCED_NLP and self.advanced_embeddings:
            # Use advanced embeddings
            self.advanced_embeddings.build_contributor_embeddings()
            if self.semantic_engine:
                self.semantic_engine.build_search_index()
            
            # Also build Word2Vec model for additional capabilities
            if len(search_texts) > 10:
                tokenized_texts = [text.lower().split() for text in search_texts]
                self.word2vec_model = Word2Vec(
                    sentences=tokenized_texts,
                    vector_size=100,
                    window=5,
                    min_count=1,
                    workers=4,
                    epochs=10
                )
                
                # Build Doc2Vec model
                tagged_docs = [TaggedDocument(doc.lower().split(), [i]) 
                              for i, doc in enumerate(search_texts)]
                self.doc2vec_model = Doc2Vec(
                    documents=tagged_docs,
                    vector_size=100,
                    window=5,
                    min_count=1,
                    workers=4,
                    epochs=10
                )
        
        # Always create TF-IDF as fallback
        self.vectorizer = TfidfVectorizer(max_features=1000, ngram_range=(1, 3))
        self.contributor_embeddings = self.vectorizer.fit_transform(search_texts)
    
    def semantic_search_contributors(self, query: str, top_k: int = 10) -> pd.DataFrame:
        """Search contributors using advanced semantic similarity."""
        # Try sentence-transformers first
        if MODERN_SEARCH_AVAILABLE:
            try:
                results = sentence_transformer_wrapper.semantic_search_contributors(query, top_k)
                if not results.empty:
                    return results
            except Exception as e:
                print(f"Sentence-transformers search failed: {e}")
        
        # Then try advanced embeddings
        if self.contributor_data is None or self.contributor_data.empty:
            self.build_contributor_index()
        
        if self.contributor_data.empty:
            return pd.DataFrame()
        
        # Use advanced search if available
        if ADVANCED_NLP and self.semantic_engine:
            results = self.semantic_engine.search(query, top_k)
            if not results.empty:
                return results
        
        # Fallback to TF-IDF
        if self.vectorizer is None or self.contributor_embeddings is None:
            self.build_contributor_index()
            
        # Enhance query with TextBlob if available
        enhanced_query = query
        if ADVANCED_NLP:
            try:
                blob = TextBlob(query)
                # Add synonyms and related words
                words = []
                for word in blob.words:
                    words.append(word)
                    # Add lemmatized form
                    words.append(word.lemmatize())
                enhanced_query = ' '.join(words)
            except:
                pass
        
        # Vectorize query
        query_vector = self.vectorizer.transform([enhanced_query])
        
        # Calculate similarities
        similarities = cosine_similarity(query_vector, self.contributor_embeddings).flatten()
        
        # Get top results
        top_indices = similarities.argsort()[-top_k:][::-1]
        
        results = self.contributor_data.iloc[top_indices].copy()
        results['similarity_score'] = similarities[top_indices]
        
        return results
    
    def find_similar_contributors(self, contributor_id: str, top_k: int = 10) -> pd.DataFrame:
        """Find contributors similar to a given contributor."""
        if self.contributor_embeddings is None:
            self.build_contributor_index()
        
        # Find the contributor index
        contributor_idx = self.contributor_data[self.contributor_data['id'] == contributor_id].index
        
        if len(contributor_idx) == 0:
            return pd.DataFrame()
        
        idx = contributor_idx[0]
        
        # Calculate similarities
        contributor_vector = self.contributor_embeddings[idx]
        similarities = cosine_similarity(contributor_vector, self.contributor_embeddings).flatten()
        
        # Exclude self and get top results
        similarities[idx] = 0
        top_indices = similarities.argsort()[-top_k:][::-1]
        
        results = self.contributor_data.iloc[top_indices].copy()
        results['similarity_score'] = similarities[top_indices]
        
        return results
    
    def detect_duplicate_contributors(self, threshold: float = 0.85) -> List[Dict]:
        """Detect potential duplicate contributors using similarity."""
        if self.contributor_embeddings is None:
            self.build_contributor_index()
        
        duplicates = []
        n_contributors = len(self.contributor_data)
        
        # Calculate pairwise similarities
        for i in range(n_contributors):
            for j in range(i + 1, n_contributors):
                similarity = cosine_similarity(
                    self.contributor_embeddings[i],
                    self.contributor_embeddings[j]
                )[0, 0]
                
                if similarity > threshold:
                    duplicates.append({
                        'contributor1': self.contributor_data.iloc[i].to_dict(),
                        'contributor2': self.contributor_data.iloc[j].to_dict(),
                        'similarity': similarity
                    })
        
        return duplicates
    
    def analyze_contribution_patterns(self) -> Dict:
        """Analyze contribution patterns using ML techniques."""
        query = """
            SELECT 
                c.contributor_id,
                c.amount,
                c.transaction_date,
                c.payment_method_desc,
                r.office_name,
                r.party,
                l.state,
                l.borough_name,
                EXTRACT(DOW FROM c.transaction_date) as day_of_week,
                EXTRACT(HOUR FROM c.transaction_date) as hour_of_day
            FROM contributions c
            JOIN recipients r ON c.recipient_id = r.id
            LEFT JOIN locations l ON c.location_id = l.id
            WHERE c.transaction_date IS NOT NULL
        """
        
        data = self.db.execute_query(query)
        
        if data.empty:
            return {}
        
        # Prepare features for anomaly detection
        features = []
        for _, row in data.iterrows():
            features.append([
                float(row['amount']),
                float(row['day_of_week']) if pd.notna(row['day_of_week']) else 0,
                float(row['hour_of_day']) if pd.notna(row['hour_of_day']) else 12
            ])
        
        features = np.array(features)
        
        # Anomaly detection
        iso_forest = IsolationForest(contamination=0.05, random_state=42)
        anomalies = iso_forest.fit_predict(self.scaler.fit_transform(features))
        
        # Clustering patterns
        dbscan = DBSCAN(eps=0.5, min_samples=5)
        clusters = dbscan.fit_predict(self.scaler.transform(features))
        
        # Analyze results
        anomaly_indices = np.where(anomalies == -1)[0]
        anomalous_contributions = data.iloc[anomaly_indices]
        
        # Pattern summary
        patterns = {
            'total_contributions': len(data),
            'anomalous_contributions': len(anomaly_indices),
            'anomaly_percentage': (len(anomaly_indices) / len(data)) * 100,
            'num_clusters': len(set(clusters)) - (1 if -1 in clusters else 0),
            'top_anomalies': anomalous_contributions.nlargest(10, 'amount')[
                ['contributor_id', 'amount', 'transaction_date', 'office_name']
            ].to_dict('records'),
            'contribution_stats': {
                'mean_amount': float(data['amount'].mean()),
                'median_amount': float(data['amount'].median()),
                'std_amount': float(data['amount'].std()),
                'total_amount': float(data['amount'].sum())
            }
        }
        
        return patterns
    
    def analyze_donor_networks(self) -> pd.DataFrame:
        """Analyze donor networks and relationships."""
        query = """
            WITH donor_pairs AS (
                SELECT 
                    c1.contributor_id as donor1_id,
                    c2.contributor_id as donor2_id,
                    COUNT(DISTINCT c1.recipient_id) as shared_recipients
                FROM contributions c1
                JOIN contributions c2 ON c1.recipient_id = c2.recipient_id 
                    AND c1.contributor_id < c2.contributor_id
                GROUP BY c1.contributor_id, c2.contributor_id
                HAVING COUNT(DISTINCT c1.recipient_id) > 2
            )
            SELECT 
                dp.donor1_id,
                dp.donor2_id,
                dp.shared_recipients,
                contrib1.full_name as donor1_name,
                contrib2.full_name as donor2_name,
                contrib1.contributor_type as donor1_type,
                contrib2.contributor_type as donor2_type
            FROM donor_pairs dp
            JOIN contributors contrib1 ON dp.donor1_id = contrib1.id
            JOIN contributors contrib2 ON dp.donor2_id = contrib2.id
            ORDER BY shared_recipients DESC
            LIMIT 50
        """
        
        return self.db.execute_query(query)
    
    def predict_contribution_likelihood(self, contributor_features: Dict) -> float:
        """Predict likelihood of future contributions based on patterns."""
        # This is a simplified version using statistical analysis
        # In a full implementation, this would use trained ML models
        
        query = """
            SELECT 
                AVG(CASE WHEN num_contributions > 1 THEN 1 ELSE 0 END) as repeat_rate,
                AVG(total_amount) as avg_total,
                AVG(num_recipients) as avg_recipients
            FROM (
                SELECT 
                    contributor_id,
                    COUNT(*) as num_contributions,
                    SUM(amount) as total_amount,
                    COUNT(DISTINCT recipient_id) as num_recipients
                FROM contributions
                GROUP BY contributor_id
            ) contrib_stats
        """
        
        stats = self.db.execute_query(query)
        
        if stats.empty:
            return 0.5
        
        # Simple scoring based on contributor features
        base_likelihood = float(stats.iloc[0]['repeat_rate'])
        
        # Adjust based on features
        if contributor_features.get('previous_contributions', 0) > 1:
            base_likelihood *= 1.5
        
        if contributor_features.get('contributor_type') == 'Individual':
            base_likelihood *= 0.9
        else:
            base_likelihood *= 1.1
        
        return min(base_likelihood, 1.0)


class NaturalLanguageQueryProcessor:
    """Process natural language queries on political contribution data."""
    
    def __init__(self):
        self.db = NYCCFBDatabase()
        self.query_patterns = self._build_query_patterns()
    
    def _build_query_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """Build regex patterns for common query types."""
        return [
            (re.compile(r'(show|find|get|list)\s+(?:all\s+)?contributors?\s+(?:who\s+)?(?:gave|donated|contributed)\s+to\s+(\w+(?:\s+\w+)*)', re.I),
             'contributors_to_recipient'),
            (re.compile(r'(show|find|get|list)\s+(?:all\s+)?contributions?\s+from\s+(\w+(?:\s+\w+)*)', re.I),
             'contributions_from_donor'),
            (re.compile(r'top\s+(\d+)?\s*contributors?\s+(?:by\s+)?(?:total\s+)?amount', re.I),
             'top_contributors'),
            (re.compile(r'(?:total\s+)?(?:contributions?|raised)\s+(?:for|by)\s+(\w+(?:\s+\w+)*)', re.I),
             'total_for_recipient'),
            (re.compile(r'contributors?\s+from\s+(\w+(?:\s+\w+)*)', re.I),
             'contributors_from_location'),
            (re.compile(r'(show|find|get|list)\s+(?:all\s+)?(\w+)\s+(?:office|race)\s+candidates?', re.I),
             'candidates_by_office')
        ]
    
    def process_query(self, natural_query: str) -> Tuple[str, pd.DataFrame]:
        """Process a natural language query and return SQL + results."""
        natural_query = natural_query.strip()
        
        # Try to match query patterns
        for pattern, query_type in self.query_patterns:
            match = pattern.match(natural_query)
            if match:
                return self._handle_query_type(query_type, match, natural_query)
        
        # Default fallback
        return self._handle_general_search(natural_query)
    
    def _handle_query_type(self, query_type: str, match: re.Match, original_query: str) -> Tuple[str, pd.DataFrame]:
        """Handle specific query types."""
        if query_type == 'contributors_to_recipient':
            recipient_name = match.group(2)
            sql = f"""
                SELECT 
                    contrib.full_name as contributor_name,
                    contrib.contributor_type,
                    c.amount,
                    c.transaction_date,
                    l.city,
                    l.state
                FROM contributions c
                JOIN contributors contrib ON c.contributor_id = contrib.id
                JOIN recipients r ON c.recipient_id = r.id
                LEFT JOIN locations l ON c.location_id = l.id
                WHERE LOWER(r.full_name) LIKE LOWER('%{recipient_name}%')
                ORDER BY c.amount DESC
            """
            
        elif query_type == 'top_contributors':
            limit = match.group(1) or '20'
            sql = f"""
                SELECT 
                    contrib.full_name as contributor_name,
                    contrib.contributor_type,
                    COUNT(*) as num_contributions,
                    SUM(c.amount) as total_amount,
                    AVG(c.amount) as avg_amount
                FROM contributions c
                JOIN contributors contrib ON c.contributor_id = contrib.id
                GROUP BY contrib.id, contrib.full_name, contrib.contributor_type
                ORDER BY total_amount DESC
                LIMIT {limit}
            """
            
        elif query_type == 'contributors_from_location':
            location = match.group(1)
            sql = f"""
                SELECT DISTINCT
                    contrib.full_name as contributor_name,
                    contrib.contributor_type,
                    l.city,
                    l.state,
                    COUNT(*) as num_contributions,
                    SUM(c.amount) as total_amount
                FROM contributions c
                JOIN contributors contrib ON c.contributor_id = contrib.id
                LEFT JOIN locations l ON c.location_id = l.id
                WHERE LOWER(l.city) LIKE LOWER('%{location}%')
                   OR LOWER(l.state) LIKE LOWER('%{location}%')
                   OR LOWER(l.borough_name) LIKE LOWER('%{location}%')
                GROUP BY contrib.id, contrib.full_name, contrib.contributor_type, l.city, l.state
                ORDER BY total_amount DESC
            """
            
        else:
            sql = "SELECT 'Query type not implemented' as message"
        
        # Execute query
        try:
            results = self.db.execute_query(sql)
            return sql, results
        except Exception as e:
            return sql, pd.DataFrame({'error': [str(e)]})
    
    def _handle_general_search(self, query: str) -> Tuple[str, pd.DataFrame]:
        """Handle general search queries."""
        # Extract potential search terms
        search_terms = query.lower().split()
        
        sql = f"""
            SELECT 
                'Contributor' as type,
                full_name as name,
                contributor_type as subtype,
                NULL as amount
            FROM contributors
            WHERE LOWER(full_name) LIKE '%{search_terms[0]}%'
            UNION ALL
            SELECT 
                'Recipient' as type,
                full_name as name,
                office_name as subtype,
                NULL as amount
            FROM recipients
            WHERE LOWER(full_name) LIKE '%{search_terms[0]}%'
            LIMIT 20
        """
        
        try:
            results = self.db.execute_query(sql)
            return sql, results
        except Exception as e:
            return sql, pd.DataFrame({'error': [str(e)]})