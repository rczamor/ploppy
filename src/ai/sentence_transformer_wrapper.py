"""Wrapper to use sentence-transformers via subprocess."""

import subprocess
import json
import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from db_manager_v2 import NYCCFBDatabase


class SentenceTransformerWrapper:
    """Use sentence-transformers through Python 3.10 subprocess."""
    
    def __init__(self):
        self.python_cmd = "python3.10"
        self.script = "./run_sentence_transformers.py"
        self.db = NYCCFBDatabase()
        self.available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """Check if sentence-transformers is available."""
        try:
            result = subprocess.run(
                [self.python_cmd, "-c", 
                 "import sys; sys.path.insert(0, '/home/runner/.pythonlibs/lib/python3.10/site-packages'); from sentence_transformers import SentenceTransformer; print('OK')"],
                capture_output=True, text=True
            )
            return result.returncode == 0 and "OK" in result.stdout
        except:
            return False
    
    def encode_texts(self, texts: List[str]) -> Optional[np.ndarray]:
        """Encode texts using sentence-transformers."""
        if not self.available:
            return None
        
        try:
            result = subprocess.run(
                [self.python_cmd, self.script, "encode", json.dumps(texts)],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if "embeddings" in data:
                    return np.array(data["embeddings"])
            return None
        except Exception as e:
            print(f"Error encoding texts: {e}")
            return None
    
    def calculate_similarity(self, text1: str, text2: str) -> Optional[float]:
        """Calculate semantic similarity between two texts."""
        if not self.available:
            return None
        
        try:
            result = subprocess.run(
                [self.python_cmd, self.script, "similarity", text1, text2],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("similarity")
            return None
        except:
            return None
    
    def semantic_search_contributors(self, query: str, top_k: int = 10) -> pd.DataFrame:
        """Search contributors using sentence-transformers."""
        if not self.available:
            return pd.DataFrame()
        
        # Get contributors
        query_sql = """
            SELECT 
                c.id,
                c.full_name,
                c.contributor_type,
                c.occupation,
                e.name as employer_name,
                l.city,
                l.state,
                SUM(cont.amount) as total_amount
            FROM contributors c
            LEFT JOIN employers e ON c.employer_id = e.id
            LEFT JOIN contributions cont ON c.id = cont.contributor_id
            LEFT JOIN locations l ON cont.location_id = l.id
            GROUP BY c.id, c.full_name, c.contributor_type, c.occupation, e.name, l.city, l.state
        """
        
        contributors = self.db.execute_query(query_sql)
        
        if contributors.empty:
            return pd.DataFrame()
        
        # Create text representations
        texts = []
        for _, row in contributors.iterrows():
            text = f"{row['full_name']} {row['contributor_type']}"
            if pd.notna(row['occupation']):
                text += f" {row['occupation']}"
            if pd.notna(row['employer_name']):
                text += f" {row['employer_name']}"
            if pd.notna(row['city']):
                text += f" {row['city']}"
            texts.append(text)
        
        # Encode query and texts
        query_embedding = self.encode_texts([query])
        if query_embedding is None:
            return pd.DataFrame()
        
        corpus_embeddings = self.encode_texts(texts)
        if corpus_embeddings is None:
            return pd.DataFrame()
        
        # Calculate similarities
        from sklearn.metrics.pairwise import cosine_similarity
        similarities = cosine_similarity(query_embedding, corpus_embeddings)[0]
        
        # Get top results
        top_indices = similarities.argsort()[-top_k:][::-1]
        
        results = contributors.iloc[top_indices].copy()
        results['similarity_score'] = similarities[top_indices]
        
        return results


# Global instance
sentence_transformer_wrapper = SentenceTransformerWrapper()