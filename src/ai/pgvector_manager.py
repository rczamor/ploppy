"""PGVector integration for advanced vector search capabilities."""

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import numpy as np
import os
from typing import List, Dict, Tuple, Optional, Any
import json
import uuid
from datetime import datetime

class PGVectorManager:
    """Manages vector embeddings using PostgreSQL with pgvector extension."""
    
    def __init__(self):
        self.conn = None
        self.database_url = os.environ.get('DATABASE_URL')
        
    def connect(self):
        """Establish database connection."""
        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(self.database_url)
        return self.conn
    
    def store_embeddings(self, embeddings: List[Dict[str, Any]]) -> int:
        """Store embeddings in the database.
        
        Args:
            embeddings: List of dicts with keys:
                - entity_type: Type of entity ('contributor', 'contribution', etc.)
                - entity_id: ID of the entity
                - content: Text content that was embedded
                - embedding: Numpy array or list of floats
                - metadata: Optional dict of additional data
        
        Returns:
            Number of embeddings stored
        """
        conn = self.connect()
        cur = conn.cursor()
        
        try:
            # Prepare data for insertion
            insert_data = []
            for emb in embeddings:
                # Convert numpy array to list if needed
                vector = emb['embedding']
                if isinstance(vector, np.ndarray):
                    vector = vector.tolist()
                
                # Format vector for pgvector
                vector_str = '[' + ','.join(map(str, vector)) + ']'
                
                insert_data.append((
                    emb['entity_type'],
                    emb['entity_id'],
                    emb.get('content', ''),
                    vector_str,
                    json.dumps(emb.get('metadata', {}))
                ))
            
            # Bulk insert (without ON CONFLICT since we don't have unique constraint)
            execute_values(
                cur,
                """
                INSERT INTO embeddings (entity_type, entity_id, content, embedding, metadata)
                VALUES %s
                """,
                insert_data,
                template="(%s, %s, %s, %s::vector, %s::jsonb)"
            )
            
            conn.commit()
            return len(insert_data)
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
    
    def vector_search(self, query_embedding: np.ndarray, 
                     entity_type: Optional[str] = None,
                     top_k: int = 10,
                     threshold: float = 0.0) -> List[Dict]:
        """Search for similar vectors using cosine similarity.
        
        Args:
            query_embedding: Query vector
            entity_type: Filter by entity type
            top_k: Number of results to return
            threshold: Minimum similarity threshold
        
        Returns:
            List of similar entities with scores
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Convert to list and format for pgvector
            if isinstance(query_embedding, np.ndarray):
                query_embedding = query_embedding.tolist()
            vector_str = '[' + ','.join(map(str, query_embedding)) + ']'
            
            # Build query with optional entity type filter
            where_clause = ""
            params = [vector_str, top_k]
            
            if entity_type:
                where_clause = "WHERE entity_type = %s"
                params.insert(1, entity_type)
            
            if threshold > 0:
                similarity_clause = f"AND (1 - (embedding <=> %s::vector)) > %s"
                if where_clause:
                    where_clause += f" {similarity_clause}"
                else:
                    where_clause = f"WHERE {similarity_clause}"
                params.extend([vector_str, threshold])
            
            query = f"""
                SELECT 
                    id,
                    entity_type,
                    entity_id,
                    content,
                    metadata,
                    1 - (embedding <=> %s::vector) as similarity
                FROM embeddings
                {where_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            
            # Adjust params for the query
            if threshold > 0:
                final_params = [params[0]] + params[1:-2] + [params[0], params[-1]]
            elif entity_type:
                final_params = [params[0], params[1], params[0], params[2]]
            else:
                final_params = [params[0], params[0], params[1]]
            
            cur.execute(query, final_params)
            results = cur.fetchall()
            
            return [dict(r) for r in results]
            
        finally:
            cur.close()
    
    def hybrid_search(self, query_embedding: np.ndarray,
                     sql_filters: Dict[str, Any],
                     top_k: int = 10) -> List[Dict]:
        """Combine vector search with SQL filtering.
        
        Args:
            query_embedding: Query vector
            sql_filters: Dict of SQL conditions
            top_k: Number of results
        
        Returns:
            Filtered and ranked results
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Convert embedding
            if isinstance(query_embedding, np.ndarray):
                query_embedding = query_embedding.tolist()
            vector_str = '[' + ','.join(map(str, query_embedding)) + ']'
            
            # Build SQL conditions
            conditions = []
            params = [vector_str]
            
            for key, value in sql_filters.items():
                if key == 'metadata':
                    # Handle JSONB queries
                    for meta_key, meta_value in value.items():
                        conditions.append(f"metadata->>{meta_key} = %s")
                        params.append(meta_value)
                else:
                    conditions.append(f"{key} = %s")
                    params.append(value)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT 
                    id,
                    entity_type,
                    entity_id,
                    content,
                    metadata,
                    1 - (embedding <=> %s::vector) as similarity
                FROM embeddings
                WHERE {where_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            
            params.extend([vector_str, top_k])
            cur.execute(query, params)
            
            results = cur.fetchall()
            return [dict(r) for r in results]
            
        finally:
            cur.close()
    
    def get_nearest_neighbors(self, entity_id: str, 
                             entity_type: str,
                             k: int = 10) -> List[Dict]:
        """Find k nearest neighbors for a given entity.
        
        Args:
            entity_id: ID of the entity
            entity_type: Type of the entity
            k: Number of neighbors
        
        Returns:
            List of nearest neighbors
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get the entity's embedding
            cur.execute("""
                SELECT embedding 
                FROM embeddings 
                WHERE entity_id = %s AND entity_type = %s
            """, (entity_id, entity_type))
            
            result = cur.fetchone()
            if not result:
                return []
            
            # Find nearest neighbors
            cur.execute("""
                SELECT 
                    id,
                    entity_type,
                    entity_id,
                    content,
                    metadata,
                    1 - (embedding <=> %s) as similarity
                FROM embeddings
                WHERE entity_id != %s
                ORDER BY embedding <=> %s
                LIMIT %s
            """, (result['embedding'], entity_id, result['embedding'], k))
            
            results = cur.fetchall()
            return [dict(r) for r in results]
            
        finally:
            cur.close()
    
    def cluster_vectors(self, entity_type: Optional[str] = None,
                       min_cluster_size: int = 5) -> Dict[str, List[str]]:
        """Cluster vectors using density-based clustering.
        
        Args:
            entity_type: Optional filter by entity type
            min_cluster_size: Minimum cluster size
        
        Returns:
            Dict mapping cluster IDs to entity IDs
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get all embeddings
            where_clause = f"WHERE entity_type = '{entity_type}'" if entity_type else ""
            
            cur.execute(f"""
                SELECT entity_id, embedding
                FROM embeddings
                {where_clause}
            """)
            
            results = cur.fetchall()
            if len(results) < min_cluster_size:
                return {}
            
            # Extract embeddings and IDs
            entity_ids = [r['entity_id'] for r in results]
            embeddings = np.array([r['embedding'] for r in results])
            
            # Simple clustering using similarity threshold
            # (More sophisticated clustering would require DBSCAN or similar)
            clusters = {}
            visited = set()
            cluster_id = 0
            
            for i, entity_id in enumerate(entity_ids):
                if entity_id in visited:
                    continue
                
                # Find all points within similarity threshold
                cluster = [entity_id]
                visited.add(entity_id)
                
                for j, other_id in enumerate(entity_ids):
                    if i != j and other_id not in visited:
                        # Calculate cosine similarity
                        similarity = np.dot(embeddings[i], embeddings[j]) / (
                            np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
                        )
                        
                        if similarity > 0.8:  # Threshold
                            cluster.append(other_id)
                            visited.add(other_id)
                
                if len(cluster) >= min_cluster_size:
                    clusters[f"cluster_{cluster_id}"] = cluster
                    cluster_id += 1
            
            return clusters
            
        finally:
            cur.close()
    
    def update_embeddings_metadata(self, entity_id: str, 
                                  entity_type: str,
                                  metadata: Dict) -> bool:
        """Update metadata for an embedding.
        
        Args:
            entity_id: Entity ID
            entity_type: Entity type
            metadata: New metadata to merge
        
        Returns:
            Success status
        """
        conn = self.connect()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                UPDATE embeddings
                SET metadata = metadata || %s::jsonb,
                    updated_at = NOW()
                WHERE entity_id = %s AND entity_type = %s
            """, (json.dumps(metadata), entity_id, entity_type))
            
            conn.commit()
            return cur.rowcount > 0
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
    
    def delete_embeddings(self, entity_type: Optional[str] = None,
                         entity_ids: Optional[List[str]] = None) -> int:
        """Delete embeddings.
        
        Args:
            entity_type: Optional filter by type
            entity_ids: Optional list of specific IDs
        
        Returns:
            Number of deleted embeddings
        """
        conn = self.connect()
        cur = conn.cursor()
        
        try:
            conditions = []
            params = []
            
            if entity_type:
                conditions.append("entity_type = %s")
                params.append(entity_type)
            
            if entity_ids:
                conditions.append("entity_id = ANY(%s)")
                params.append(entity_ids)
            
            if not conditions:
                return 0  # Safety: don't delete everything
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                DELETE FROM embeddings
                WHERE {where_clause}
            """, params)
            
            conn.commit()
            return cur.rowcount
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
    
    def get_statistics(self) -> Dict:
        """Get statistics about stored embeddings."""
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Count by entity type
            cur.execute("""
                SELECT 
                    entity_type,
                    COUNT(*) as count,
                    AVG(CARDINALITY(embedding::real[])) as avg_dimensions
                FROM embeddings
                GROUP BY entity_type
            """)
            
            type_stats = {r['entity_type']: {
                'count': r['count'],
                'avg_dimensions': float(r['avg_dimensions']) if r['avg_dimensions'] else 0
            } for r in cur.fetchall()}
            
            # Total stats
            cur.execute("""
                SELECT 
                    COUNT(*) as total_embeddings,
                    COUNT(DISTINCT entity_type) as entity_types,
                    MIN(created_at) as oldest,
                    MAX(updated_at) as newest
                FROM embeddings
            """)
            
            total_stats = dict(cur.fetchone())
            
            return {
                'total': total_stats,
                'by_type': type_stats
            }
            
        finally:
            cur.close()