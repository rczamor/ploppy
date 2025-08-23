"""Modern embeddings using optimized TF-IDF and advanced techniques with available libraries."""

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD, NMF, LatentDirichletAllocation
from sklearn.preprocessing import normalize
from sklearn.metrics.pairwise import cosine_similarity
import pickle
import os
from typing import List, Dict, Tuple, Optional, Union
import hashlib
import json

class ModernEmbeddings:
    """Optimized embedding system using advanced TF-IDF and matrix factorization."""
    
    def __init__(self, cache_dir: str = 'embeddings_cache'):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # Optimized TF-IDF with n-grams
        self.tfidf = TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 3),
            min_df=2,
            max_df=0.95,
            sublinear_tf=True,
            use_idf=True,
            smooth_idf=True,
            strip_accents='unicode',
            analyzer='word',
            token_pattern=r'\b[a-zA-Z]+\b',
            lowercase=True
        )
        
        # Dimensionality reduction models
        self.svd = TruncatedSVD(n_components=300, random_state=42)
        self.nmf = NMF(n_components=100, random_state=42, init='nndsvd')
        
        # Storage
        self.documents = None
        self.embeddings = None
        self.document_ids = None
        
    def _cache_key(self, texts: List[str]) -> str:
        """Generate cache key for texts."""
        text_hash = hashlib.md5(''.join(sorted(texts)).encode()).hexdigest()
        return f"{self.cache_dir}/embeddings_{text_hash}.pkl"
    
    def create_embeddings(self, texts: List[str], ids: Optional[List[str]] = None, 
                         method: str = 'tfidf_svd') -> np.ndarray:
        """Create modern embeddings with multiple methods."""
        
        if not texts:
            return np.array([])
        
        # Check cache
        cache_file = self._cache_key(texts[:100])  # Use first 100 for cache key
        if os.path.exists(cache_file) and method == 'tfidf_svd':
            with open(cache_file, 'rb') as f:
                cached = pickle.load(f)
                if len(cached['embeddings']) == len(texts):
                    self.embeddings = cached['embeddings']
                    self.document_ids = cached['ids']
                    return self.embeddings
        
        # Generate embeddings based on method
        if method == 'tfidf':
            # Pure TF-IDF
            embeddings = self.tfidf.fit_transform(texts).toarray()
            
        elif method == 'tfidf_svd':
            # TF-IDF + SVD (similar to LSA)
            tfidf_matrix = self.tfidf.fit_transform(texts)
            embeddings = self.svd.fit_transform(tfidf_matrix)
            
        elif method == 'tfidf_nmf':
            # TF-IDF + NMF for non-negative embeddings
            tfidf_matrix = self.tfidf.fit_transform(texts)
            embeddings = self.nmf.fit_transform(tfidf_matrix)
            
        elif method == 'ensemble':
            # Combine multiple methods
            tfidf_matrix = self.tfidf.fit_transform(texts)
            
            # Get different representations
            svd_embeddings = self.svd.fit_transform(tfidf_matrix)
            nmf_embeddings = self.nmf.fit_transform(tfidf_matrix)
            
            # Normalize and combine
            svd_norm = normalize(svd_embeddings)
            nmf_norm = normalize(nmf_embeddings)
            tfidf_norm = normalize(tfidf_matrix[:, :500].toarray())  # Top 500 features
            
            embeddings = np.hstack([svd_norm, nmf_norm, tfidf_norm])
            
        else:
            raise ValueError(f"Unknown method: {method}")
        
        # Normalize final embeddings
        self.embeddings = normalize(embeddings)
        self.document_ids = ids if ids else list(range(len(texts)))
        self.documents = texts
        
        # Cache if using default method
        if method == 'tfidf_svd' and len(texts) > 10:
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'embeddings': self.embeddings,
                    'ids': self.document_ids
                }, f)
        
        return self.embeddings
    
    def semantic_search(self, query: str, top_k: int = 10, 
                       threshold: float = 0.0) -> List[Tuple[int, float, str]]:
        """Perform semantic search with similarity scores."""
        
        if self.embeddings is None or self.documents is None:
            return []
        
        # Transform query using the same method
        query_tfidf = self.tfidf.transform([query])
        query_embedding = self.svd.transform(query_tfidf)
        query_embedding = normalize(query_embedding)
        
        # Calculate similarities
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]
        
        # Get top results above threshold
        indices = np.where(similarities > threshold)[0]
        scores = similarities[indices]
        
        # Sort by score
        sorted_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in sorted_indices:
            real_idx = indices[idx]
            results.append((
                self.document_ids[real_idx],
                float(scores[idx]),
                self.documents[real_idx]
            ))
        
        return results
    
    def find_similar(self, doc_id: Union[int, str], top_k: int = 10) -> List[Tuple[int, float, str]]:
        """Find similar documents to a given document."""
        
        if self.embeddings is None or self.document_ids is None:
            return []
        
        # Find document index
        try:
            doc_idx = self.document_ids.index(doc_id)
        except ValueError:
            return []
        
        # Get embedding
        doc_embedding = self.embeddings[doc_idx].reshape(1, -1)
        
        # Calculate similarities
        similarities = cosine_similarity(doc_embedding, self.embeddings)[0]
        
        # Get top results (excluding self)
        sorted_indices = np.argsort(similarities)[::-1][1:top_k+1]
        
        results = []
        for idx in sorted_indices:
            results.append((
                self.document_ids[idx],
                float(similarities[idx]),
                self.documents[idx]
            ))
        
        return results
    
    def get_topics(self, n_topics: int = 10, n_words: int = 10) -> Dict[int, List[str]]:
        """Extract topics from the corpus using LDA."""
        
        if self.documents is None:
            return {}
        
        # Use CountVectorizer for LDA
        from sklearn.feature_extraction.text import CountVectorizer
        cv = CountVectorizer(max_features=1000, ngram_range=(1, 2))
        count_matrix = cv.fit_transform(self.documents)
        
        # Apply LDA
        lda = LatentDirichletAllocation(n_components=n_topics, random_state=42)
        lda.fit(count_matrix)
        
        # Get feature names
        feature_names = cv.get_feature_names_out()
        
        # Extract topics
        topics = {}
        for topic_idx, topic in enumerate(lda.components_):
            top_indices = np.argsort(topic)[::-1][:n_words]
            top_words = [feature_names[i] for i in top_indices]
            topics[topic_idx] = top_words
        
        return topics
    
    def save(self, filepath: str):
        """Save the embeddings model."""
        with open(filepath, 'wb') as f:
            pickle.dump({
                'tfidf': self.tfidf,
                'svd': self.svd,
                'nmf': self.nmf,
                'embeddings': self.embeddings,
                'documents': self.documents,
                'document_ids': self.document_ids
            }, f)
    
    def load(self, filepath: str):
        """Load a saved embeddings model."""
        with open(filepath, 'rb') as f:
            saved = pickle.load(f)
            self.tfidf = saved['tfidf']
            self.svd = saved['svd']
            self.nmf = saved['nmf']
            self.embeddings = saved['embeddings']
            self.documents = saved['documents']
            self.document_ids = saved['document_ids']


class OptimizedSemanticSearch:
    """Fast semantic search using optimized algorithms."""
    
    def __init__(self):
        self.embeddings_model = ModernEmbeddings()
        self.index = None
        
    def build_index(self, texts: List[str], ids: List[str], 
                   metadata: Optional[List[Dict]] = None):
        """Build search index from texts."""
        
        # Create embeddings
        embeddings = self.embeddings_model.create_embeddings(texts, ids, method='tfidf_svd')
        
        # Store metadata
        self.metadata = metadata if metadata else [{}] * len(texts)
        
        # Build approximate nearest neighbor index for fast search
        # Store normalized embeddings for cosine similarity via dot product
        from sklearn.preprocessing import normalize
        self.normalized_embeddings = normalize(embeddings)
        self.index = None  # Will use direct cosine similarity for now
        
        return embeddings
    
    def search(self, query: str, top_k: int = 10, 
              filters: Optional[Dict] = None) -> pd.DataFrame:
        """Fast semantic search with optional filtering."""
        
        results = self.embeddings_model.semantic_search(query, top_k * 2)  # Get extra for filtering
        
        # Apply filters if provided
        if filters and self.metadata:
            filtered_results = []
            for doc_id, score, text in results:
                idx = self.embeddings_model.document_ids.index(doc_id)
                doc_metadata = self.metadata[idx]
                
                # Check all filters
                match = True
                for key, value in filters.items():
                    if key in doc_metadata and doc_metadata[key] != value:
                        match = False
                        break
                
                if match:
                    filtered_results.append({
                        'id': doc_id,
                        'score': score,
                        'text': text[:200],  # Preview
                        **doc_metadata
                    })
                
                if len(filtered_results) >= top_k:
                    break
            
            return pd.DataFrame(filtered_results)
        
        # No filtering
        return pd.DataFrame([
            {
                'id': doc_id,
                'score': score,
                'text': text[:200]
            }
            for doc_id, score, text in results[:top_k]
        ])
    
    def find_duplicates(self, threshold: float = 0.9) -> List[Tuple[str, str, float]]:
        """Find potential duplicate documents."""
        
        if self.embeddings_model.embeddings is None:
            return []
        
        # Calculate all pairwise similarities
        similarities = cosine_similarity(self.embeddings_model.embeddings)
        
        # Find high similarity pairs
        duplicates = []
        n_docs = len(self.embeddings_model.embeddings)
        
        for i in range(n_docs):
            for j in range(i + 1, n_docs):
                if similarities[i, j] > threshold:
                    duplicates.append((
                        self.embeddings_model.document_ids[i],
                        self.embeddings_model.document_ids[j],
                        float(similarities[i, j])
                    ))
        
        return sorted(duplicates, key=lambda x: x[2], reverse=True)