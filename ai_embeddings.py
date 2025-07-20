"""Advanced AI embeddings using available libraries."""

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation, NMF
from sklearn.manifold import TSNE
from sklearn.cluster import AgglomerativeClustering, SpectralClustering
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import normalize
import pickle
import os
from typing import List, Dict, Tuple, Optional
from db_manager_v2 import NYCCFBDatabase

class AdvancedEmbeddings:
    """Advanced text embeddings using matrix factorization and topic modeling."""
    
    def __init__(self):
        self.db = NYCCFBDatabase()
        self.tfidf_vectorizer = None
        self.count_vectorizer = None
        self.lda_model = None
        self.nmf_model = None
        self.embeddings = None
        self.documents = None
        
    def create_advanced_embeddings(self, texts: List[str], method: str = 'ensemble') -> np.ndarray:
        """Create advanced embeddings using various techniques."""
        
        # TF-IDF embeddings
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 3),
            min_df=2,
            sublinear_tf=True,
            use_idf=True
        )
        tfidf_embeddings = self.tfidf_vectorizer.fit_transform(texts)
        
        # Count vectorizer for LDA
        self.count_vectorizer = CountVectorizer(
            max_features=1000,
            ngram_range=(1, 2),
            min_df=2
        )
        count_vectors = self.count_vectorizer.fit_transform(texts)
        
        # Topic modeling embeddings
        if method in ['lda', 'ensemble']:
            self.lda_model = LatentDirichletAllocation(
                n_components=50,
                random_state=42,
                max_iter=10
            )
            lda_embeddings = self.lda_model.fit_transform(count_vectors)
        
        if method in ['nmf', 'ensemble']:
            self.nmf_model = NMF(
                n_components=50,
                random_state=42,
                init='nndsvd'
            )
            nmf_embeddings = self.nmf_model.fit_transform(tfidf_embeddings)
        
        # Combine embeddings
        if method == 'ensemble':
            # Normalize each embedding type
            tfidf_norm = normalize(tfidf_embeddings.toarray())
            lda_norm = normalize(lda_embeddings)
            nmf_norm = normalize(nmf_embeddings)
            
            # Concatenate
            combined = np.hstack([
                tfidf_norm[:, :200],  # Top 200 TF-IDF features
                lda_norm,             # 50 LDA topics
                nmf_norm              # 50 NMF topics
            ])
            return combined
        
        elif method == 'tfidf':
            return tfidf_embeddings.toarray()
        elif method == 'lda':
            return lda_embeddings
        elif method == 'nmf':
            return nmf_embeddings
        
    def build_contributor_embeddings(self):
        """Build embeddings for all contributors with enhanced features."""
        query = """
            SELECT 
                c.id,
                c.full_name,
                c.last_name,
                c.first_name,
                c.contributor_type,
                c.occupation,
                e.name as employer_name,
                STRING_AGG(DISTINCT l.city || ' ' || l.state, ' ') as locations,
                STRING_AGG(DISTINCT r.full_name, ' ') as recipients,
                COUNT(DISTINCT cont.id) as num_contributions,
                SUM(cont.amount) as total_amount,
                AVG(cont.amount) as avg_amount,
                MIN(cont.transaction_date) as first_contribution,
                MAX(cont.transaction_date) as last_contribution
            FROM contributors c
            LEFT JOIN employers e ON c.employer_id = e.id
            LEFT JOIN contributions cont ON c.id = cont.contributor_id
            LEFT JOIN locations l ON cont.location_id = l.id
            LEFT JOIN recipients r ON cont.recipient_id = r.id
            GROUP BY c.id, c.full_name, c.last_name, c.first_name, 
                     c.contributor_type, c.occupation, e.name
        """
        
        self.documents = self.db.execute_query(query)
        
        if self.documents.empty:
            return
        
        # Create rich text representations
        texts = []
        for _, row in self.documents.iterrows():
            # Create a rich text representation
            text_parts = [
                f"name:{row['full_name']}",
                f"type:{row['contributor_type']}",
                f"occupation:{row['occupation']}" if pd.notna(row['occupation']) else "",
                f"employer:{row['employer_name']}" if pd.notna(row['employer_name']) else "",
                f"locations:{row['locations']}" if pd.notna(row['locations']) else "",
                f"recipients:{row['recipients']}" if pd.notna(row['recipients']) else "",
                f"amount_range:{'high' if row['total_amount'] > 5000 else 'medium' if row['total_amount'] > 1000 else 'low'}",
                f"frequency:{'frequent' if row['num_contributions'] > 5 else 'occasional'}"
            ]
            texts.append(' '.join(filter(None, text_parts)))
        
        # Create embeddings
        self.embeddings = self.create_advanced_embeddings(texts, method='ensemble')
        
    def find_similar_entities(self, entity_id: str, top_k: int = 10, threshold: float = 0.7) -> pd.DataFrame:
        """Find similar entities using advanced similarity metrics."""
        if self.embeddings is None:
            self.build_contributor_embeddings()
        
        # Find entity index
        entity_idx = self.documents[self.documents['id'] == entity_id].index
        if len(entity_idx) == 0:
            return pd.DataFrame()
        
        idx = entity_idx[0]
        
        # Use multiple similarity metrics
        from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
        
        # Cosine similarity
        cos_sim = cosine_similarity(self.embeddings[idx:idx+1], self.embeddings).flatten()
        
        # Normalized euclidean distance
        eucl_dist = euclidean_distances(self.embeddings[idx:idx+1], self.embeddings).flatten()
        eucl_sim = 1 / (1 + eucl_dist)
        
        # Combined score
        combined_sim = 0.7 * cos_sim + 0.3 * eucl_sim
        
        # Get top results
        combined_sim[idx] = 0  # Exclude self
        top_indices = np.where(combined_sim > threshold)[0]
        top_indices = top_indices[combined_sim[top_indices].argsort()[::-1][:top_k]]
        
        results = self.documents.iloc[top_indices].copy()
        results['similarity_score'] = combined_sim[top_indices]
        results['similarity_type'] = results.apply(
            lambda row: self._determine_similarity_type(idx, row.name), axis=1
        )
        
        return results
    
    def _determine_similarity_type(self, idx1: int, idx2: int) -> str:
        """Determine what makes two entities similar."""
        doc1 = self.documents.iloc[idx1]
        doc2 = self.documents.iloc[idx2]
        
        similarities = []
        
        # Check various similarity factors
        if doc1['contributor_type'] == doc2['contributor_type']:
            similarities.append('same_type')
        
        if pd.notna(doc1['occupation']) and pd.notna(doc2['occupation']):
            if doc1['occupation'].lower() == doc2['occupation'].lower():
                similarities.append('same_occupation')
        
        if pd.notna(doc1['employer_name']) and pd.notna(doc2['employer_name']):
            if doc1['employer_name'].lower() == doc2['employer_name'].lower():
                similarities.append('same_employer')
        
        # Check contribution patterns
        amt_ratio = min(doc1['avg_amount'], doc2['avg_amount']) / max(doc1['avg_amount'], doc2['avg_amount'])
        if amt_ratio > 0.8:
            similarities.append('similar_amounts')
        
        return ', '.join(similarities) if similarities else 'pattern_based'
    
    def cluster_contributors(self, n_clusters: int = None) -> pd.DataFrame:
        """Cluster contributors using hierarchical clustering."""
        if self.embeddings is None:
            self.build_contributor_embeddings()
        
        # Determine optimal clusters if not specified
        if n_clusters is None:
            # Use elbow method
            from sklearn.metrics import silhouette_score
            scores = []
            for k in range(2, min(20, len(self.documents))):
                clustering = AgglomerativeClustering(n_clusters=k)
                labels = clustering.fit_predict(self.embeddings)
                score = silhouette_score(self.embeddings, labels)
                scores.append(score)
            
            n_clusters = scores.index(max(scores)) + 2
        
        # Perform clustering
        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            linkage='ward'
        )
        cluster_labels = clustering.fit_predict(self.embeddings)
        
        # Add cluster info to documents
        results = self.documents.copy()
        results['cluster'] = cluster_labels
        
        # Analyze clusters
        cluster_analysis = []
        for cluster_id in range(n_clusters):
            cluster_docs = results[results['cluster'] == cluster_id]
            
            analysis = {
                'cluster_id': cluster_id,
                'size': len(cluster_docs),
                'avg_contribution': cluster_docs['avg_amount'].mean(),
                'total_contributions': cluster_docs['total_amount'].sum(),
                'top_occupations': cluster_docs['occupation'].value_counts().head(3).to_dict(),
                'contributor_types': cluster_docs['contributor_type'].value_counts().to_dict()
            }
            cluster_analysis.append(analysis)
        
        return results, pd.DataFrame(cluster_analysis)
    
    def extract_key_phrases(self, n_phrases: int = 20) -> List[Tuple[str, float]]:
        """Extract key phrases using TF-IDF scores."""
        if self.tfidf_vectorizer is None:
            return []
        
        # Get feature names and scores
        feature_names = self.tfidf_vectorizer.get_feature_names_out()
        tfidf_scores = self.tfidf_vectorizer.idf_
        
        # Sort by IDF scores (lower IDF = more common = more important)
        sorted_indices = tfidf_scores.argsort()[:n_phrases]
        
        key_phrases = [(feature_names[i], tfidf_scores[i]) for i in sorted_indices]
        return key_phrases
    
    def get_topic_keywords(self, n_topics: int = 10, n_words: int = 10) -> Dict[int, List[str]]:
        """Extract topic keywords from LDA model."""
        if self.lda_model is None or self.count_vectorizer is None:
            return {}
        
        feature_names = self.count_vectorizer.get_feature_names_out()
        topics = {}
        
        for topic_idx in range(min(n_topics, self.lda_model.n_components)):
            top_words_idx = self.lda_model.components_[topic_idx].argsort()[-n_words:][::-1]
            top_words = [feature_names[i] for i in top_words_idx]
            topics[topic_idx] = top_words
        
        return topics


class SemanticSearchEngine:
    """Enhanced semantic search using advanced embeddings."""
    
    def __init__(self):
        self.embeddings_model = AdvancedEmbeddings()
        self.index = None
        
    def build_search_index(self):
        """Build search index with nearest neighbors."""
        self.embeddings_model.build_contributor_embeddings()
        
        if self.embeddings_model.embeddings is not None:
            # Build nearest neighbors index
            self.index = NearestNeighbors(
                n_neighbors=20,
                metric='cosine',
                algorithm='ball_tree'
            )
            self.index.fit(self.embeddings_model.embeddings)
    
    def search(self, query: str, top_k: int = 10) -> pd.DataFrame:
        """Perform semantic search with query expansion."""
        if self.index is None:
            self.build_search_index()
        
        # Create query embedding
        query_embedding = self.embeddings_model.create_advanced_embeddings(
            [query], 
            method='ensemble'
        )
        
        # Find nearest neighbors
        distances, indices = self.index.kneighbors(query_embedding, n_neighbors=top_k)
        
        # Get results
        results = self.embeddings_model.documents.iloc[indices[0]].copy()
        results['relevance_score'] = 1 - distances[0]
        
        return results
    
    def save_index(self, path: str = 'search_index.pkl'):
        """Save search index to disk."""
        with open(path, 'wb') as f:
            pickle.dump({
                'embeddings': self.embeddings_model.embeddings,
                'documents': self.embeddings_model.documents,
                'vectorizers': {
                    'tfidf': self.embeddings_model.tfidf_vectorizer,
                    'count': self.embeddings_model.count_vectorizer
                },
                'models': {
                    'lda': self.embeddings_model.lda_model,
                    'nmf': self.embeddings_model.nmf_model
                }
            }, f)
    
    def load_index(self, path: str = 'search_index.pkl'):
        """Load search index from disk."""
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.embeddings_model.embeddings = data['embeddings']
                self.embeddings_model.documents = data['documents']
                self.embeddings_model.tfidf_vectorizer = data['vectorizers']['tfidf']
                self.embeddings_model.count_vectorizer = data['vectorizers']['count']
                self.embeddings_model.lda_model = data['models']['lda']
                self.embeddings_model.nmf_model = data['models']['nmf']
                
                # Rebuild neighbor index
                if self.embeddings_model.embeddings is not None:
                    self.index = NearestNeighbors(
                        n_neighbors=20,
                        metric='cosine',
                        algorithm='ball_tree'
                    )
                    self.index.fit(self.embeddings_model.embeddings)