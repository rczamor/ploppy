"""Modern AI-powered search using sentence-transformers."""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
import os
import sys

# Add the Python 3.10 site-packages to path
sys.path.insert(0, '/home/runner/.pythonlibs/lib/python3.10/site-packages')

try:
    from sentence_transformers import SentenceTransformer, util
    import torch
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not available")

from db_manager_v2 import NYCCFBDatabase
from sklearn.metrics.pairwise import cosine_similarity
import pickle


class ModernSemanticSearch:
    """State-of-the-art semantic search using sentence-transformers."""
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """Initialize with a pre-trained sentence transformer model.
        
        Popular models:
        - 'all-MiniLM-L6-v2': Fast and good quality (default)
        - 'all-mpnet-base-v2': Best quality
        - 'multi-qa-MiniLM-L6-cos-v1': Optimized for semantic search
        """
        self.db = NYCCFBDatabase()
        self.model = None
        self.embeddings = None
        self.documents = None
        self.model_name = model_name
        
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                print(f"Loading sentence transformer model: {model_name}")
                self.model = SentenceTransformer(model_name)
                print("✓ Model loaded successfully")
            except Exception as e:
                print(f"Error loading model: {e}")
                SENTENCE_TRANSFORMERS_AVAILABLE = False
    
    def encode_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Encode texts into embeddings using sentence-transformers."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE or self.model is None:
            raise ValueError("Sentence transformers not available")
        
        # Convert texts to embeddings
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True
        )
        
        return embeddings
    
    def build_contributor_index(self):
        """Build semantic index for all contributors."""
        query = """
            SELECT 
                c.id,
                c.full_name,
                c.last_name,
                c.first_name,
                c.contributor_type,
                c.occupation,
                e.name as employer_name,
                STRING_AGG(DISTINCT l.city || ', ' || l.state, '; ') as locations,
                STRING_AGG(DISTINCT r.full_name, '; ') as recipients,
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
            print("No contributor data found")
            return
        
        # Create rich text representations for encoding
        texts = []
        for _, row in self.documents.iterrows():
            # Build comprehensive text representation
            text_parts = [
                f"Name: {row['full_name']}",
                f"Type: {row['contributor_type']}",
            ]
            
            if pd.notna(row['occupation']) and row['occupation']:
                text_parts.append(f"Occupation: {row['occupation']}")
            
            if pd.notna(row['employer_name']) and row['employer_name']:
                text_parts.append(f"Employer: {row['employer_name']}")
            
            if pd.notna(row['locations']) and row['locations']:
                text_parts.append(f"Locations: {row['locations']}")
            
            if pd.notna(row['recipients']) and row['recipients']:
                text_parts.append(f"Donated to: {row['recipients']}")
            
            # Add contribution patterns
            text_parts.append(f"Total donated: ${row['total_amount']:,.2f}")
            text_parts.append(f"Number of contributions: {row['num_contributions']}")
            
            texts.append(" | ".join(text_parts))
        
        print(f"Encoding {len(texts)} contributors...")
        self.embeddings = self.encode_texts(texts)
        print(f"✓ Created embeddings with shape: {self.embeddings.shape}")
    
    def semantic_search(self, query: str, top_k: int = 10, threshold: float = 0.0) -> pd.DataFrame:
        """Perform semantic search on contributors."""
        if self.embeddings is None:
            self.build_contributor_index()
        
        if self.documents.empty:
            return pd.DataFrame()
        
        # Encode query
        query_embedding = self.model.encode(query, convert_to_numpy=True)
        
        # Calculate cosine similarities
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            # Use sentence-transformers util for efficiency
            cos_scores = util.cos_sim(query_embedding, self.embeddings)[0]
            cos_scores = cos_scores.cpu().numpy()
        else:
            # Fallback to sklearn
            cos_scores = cosine_similarity([query_embedding], self.embeddings)[0]
        
        # Get top results
        top_indices = np.argsort(cos_scores)[::-1][:top_k]
        
        # Filter by threshold
        top_indices = [idx for idx in top_indices if cos_scores[idx] > threshold]
        
        if not top_indices:
            return pd.DataFrame()
        
        # Build results
        results = self.documents.iloc[top_indices].copy()
        results['similarity_score'] = [cos_scores[idx] for idx in top_indices]
        
        return results
    
    def find_similar_contributors(self, contributor_id: str, top_k: int = 10) -> pd.DataFrame:
        """Find contributors similar to a given contributor."""
        if self.embeddings is None:
            self.build_contributor_index()
        
        # Find contributor index
        contributor_idx = self.documents[self.documents['id'] == contributor_id].index
        
        if len(contributor_idx) == 0:
            return pd.DataFrame()
        
        idx = contributor_idx[0]
        
        # Calculate similarities to all other contributors
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            cos_scores = util.cos_sim(self.embeddings[idx], self.embeddings)[0]
            cos_scores = cos_scores.cpu().numpy()
        else:
            cos_scores = cosine_similarity([self.embeddings[idx]], self.embeddings)[0]
        
        # Exclude self and get top results
        cos_scores[idx] = -1
        top_indices = np.argsort(cos_scores)[::-1][:top_k]
        
        results = self.documents.iloc[top_indices].copy()
        results['similarity_score'] = [cos_scores[idx] for idx in top_indices]
        
        return results
    
    def detect_duplicates(self, threshold: float = 0.9) -> List[Dict]:
        """Detect potential duplicate contributors using semantic similarity."""
        if self.embeddings is None:
            self.build_contributor_index()
        
        duplicates = []
        n_contributors = len(self.documents)
        
        # Calculate pairwise similarities efficiently
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            # Use sentence-transformers for batch processing
            similarities = util.cos_sim(self.embeddings, self.embeddings)
            
            # Find pairs above threshold
            for i in range(n_contributors):
                for j in range(i + 1, n_contributors):
                    if similarities[i][j] > threshold:
                        duplicates.append({
                            'contributor1': self.documents.iloc[i].to_dict(),
                            'contributor2': self.documents.iloc[j].to_dict(),
                            'similarity': float(similarities[i][j])
                        })
        
        return duplicates
    
    def save_index(self, path: str = 'contributor_index.pkl'):
        """Save the search index to disk."""
        with open(path, 'wb') as f:
            pickle.dump({
                'embeddings': self.embeddings,
                'documents': self.documents,
                'model_name': self.model_name
            }, f)
        print(f"✓ Index saved to {path}")
    
    def load_index(self, path: str = 'contributor_index.pkl'):
        """Load search index from disk."""
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.embeddings = data['embeddings']
                self.documents = data['documents']
                
                # Load model if needed
                if self.model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
                    self.model = SentenceTransformer(data.get('model_name', 'all-MiniLM-L6-v2'))
            print(f"✓ Index loaded from {path}")
            return True
        return False


class SmartQueryProcessor:
    """Process natural language queries with semantic understanding."""
    
    def __init__(self):
        self.db = NYCCFBDatabase()
        self.search_engine = ModernSemanticSearch()
    
    def process_query(self, query: str) -> Tuple[str, pd.DataFrame]:
        """Process natural language query with semantic understanding."""
        query_lower = query.lower()
        
        # Semantic intent detection
        if any(word in query_lower for word in ['similar', 'like', 'related']):
            # Find similar contributors
            return self._handle_similarity_query(query)
        
        elif any(word in query_lower for word in ['duplicate', 'same', 'multiple']):
            # Find duplicates
            return self._handle_duplicate_query(query)
        
        elif any(word in query_lower for word in ['top', 'most', 'highest', 'biggest']):
            # Top contributors query
            return self._handle_top_contributors_query(query)
        
        else:
            # General semantic search
            return self._handle_semantic_search(query)
    
    def _handle_semantic_search(self, query: str) -> Tuple[str, pd.DataFrame]:
        """Handle general semantic search queries."""
        results = self.search_engine.semantic_search(query, top_k=20)
        
        if results.empty:
            return "No semantic search performed", pd.DataFrame()
        
        # Format results
        display_cols = ['full_name', 'contributor_type', 'occupation', 
                       'employer_name', 'total_amount', 'num_contributions', 
                       'similarity_score']
        
        display_results = results[display_cols].copy()
        display_results['similarity_score'] = display_results['similarity_score'].apply(
            lambda x: f"{x:.2%}"
        )
        
        explanation = f"Semantic search for: '{query}'"
        return explanation, display_results
    
    def _handle_similarity_query(self, query: str) -> Tuple[str, pd.DataFrame]:
        """Handle queries about similar contributors."""
        # Extract contributor name from query
        import re
        pattern = r'similar to (.+?)(?:\?|$)'
        match = re.search(pattern, query, re.I)
        
        if match:
            name = match.group(1).strip()
            # Find the contributor
            contrib_query = f"SELECT id FROM contributors WHERE LOWER(full_name) LIKE LOWER('%{name}%') LIMIT 1"
            result = self.db.execute_query(contrib_query)
            
            if not result.empty:
                contributor_id = result.iloc[0]['id']
                similar = self.search_engine.find_similar_contributors(contributor_id)
                
                if not similar.empty:
                    display_cols = ['full_name', 'contributor_type', 'occupation', 
                                   'total_amount', 'similarity_score']
                    display_results = similar[display_cols].copy()
                    display_results['similarity_score'] = display_results['similarity_score'].apply(
                        lambda x: f"{x:.2%}"
                    )
                    
                    explanation = f"Contributors similar to {name}"
                    return explanation, display_results
        
        return "Could not find similar contributors", pd.DataFrame()
    
    def _handle_duplicate_query(self, query: str) -> Tuple[str, pd.DataFrame]:
        """Handle duplicate detection queries."""
        duplicates = self.search_engine.detect_duplicates(threshold=0.85)
        
        if duplicates:
            # Format results
            dup_data = []
            for dup in duplicates[:20]:  # Show top 20
                dup_data.append({
                    'Contributor 1': dup['contributor1']['full_name'],
                    'Type 1': dup['contributor1']['contributor_type'],
                    'Contributor 2': dup['contributor2']['full_name'],
                    'Type 2': dup['contributor2']['contributor_type'],
                    'Similarity': f"{dup['similarity']:.2%}"
                })
            
            return "Potential duplicate contributors", pd.DataFrame(dup_data)
        
        return "No duplicate contributors found", pd.DataFrame()
    
    def _handle_top_contributors_query(self, query: str) -> Tuple[str, pd.DataFrame]:
        """Handle top contributors queries with semantic understanding."""
        # Extract number if specified
        import re
        num_match = re.search(r'top (\d+)', query, re.I)
        limit = int(num_match.group(1)) if num_match else 20
        
        sql = f"""
            SELECT 
                c.full_name,
                c.contributor_type,
                c.occupation,
                e.name as employer_name,
                COUNT(DISTINCT cont.id) as num_contributions,
                SUM(cont.amount) as total_amount,
                AVG(cont.amount) as avg_amount
            FROM contributors c
            LEFT JOIN employers e ON c.employer_id = e.id
            LEFT JOIN contributions cont ON c.id = cont.contributor_id
            GROUP BY c.id, c.full_name, c.contributor_type, c.occupation, e.name
            ORDER BY total_amount DESC
            LIMIT {limit}
        """
        
        results = self.db.execute_query(sql)
        return f"Top {limit} contributors by total amount", results