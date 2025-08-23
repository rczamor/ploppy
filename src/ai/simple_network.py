"""Simple network analysis implementation without external dependencies."""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict, Counter

class SimpleGraph:
    """Simple graph implementation for network analysis."""
    
    def __init__(self):
        self.nodes = set()
        self.edges = defaultdict(dict)
        self.node_attributes = {}
        
    def clear(self):
        """Clear the graph."""
        self.nodes.clear()
        self.edges.clear()
        self.node_attributes.clear()
        
    def add_node(self, node, **attributes):
        """Add a node to the graph."""
        self.nodes.add(node)
        if attributes:
            self.node_attributes[node] = attributes
            
    def add_edge(self, node1, node2, **attributes):
        """Add an edge between two nodes."""
        self.add_node(node1)
        self.add_node(node2)
        self.edges[node1][node2] = attributes
        self.edges[node2][node1] = attributes  # Undirected graph
        
    def has_node(self, node):
        """Check if node exists."""
        return node in self.nodes
        
    def has_edge(self, node1, node2):
        """Check if edge exists."""
        return node1 in self.edges and node2 in self.edges[node1]
        
    def neighbors(self, node):
        """Get neighbors of a node."""
        return list(self.edges.get(node, {}).keys())
        
    def degree(self, node=None):
        """Get degree of a node or all nodes."""
        if node is not None:
            return len(self.edges.get(node, {}))
        return {n: len(self.edges.get(n, {})) for n in self.nodes}
        
    def number_of_nodes(self):
        """Get number of nodes."""
        return len(self.nodes)
        
    def number_of_edges(self):
        """Get number of edges."""
        return sum(len(edges) for edges in self.edges.values()) // 2
        
    def __getitem__(self, node):
        """Get edges for a node."""
        return self.edges.get(node, {})


class SimpleNetworkAnalyzer:
    """Simple network analysis without NetworkX."""
    
    def __init__(self):
        self.graph = SimpleGraph()
        
    def build_contributor_network(self, contributions: pd.DataFrame) -> SimpleGraph:
        """Build a network of contributors and recipients."""
        
        self.graph.clear()
        
        # Add nodes for contributors and recipients
        for _, row in contributions.iterrows():
            contributor = row.get('contributor_name', '') or row.get('str_name', '')
            recipient = row.get('recipient_name', '') or row.get('candidate_name', '')
            
            if contributor and recipient:
                # Add nodes
                if not self.graph.has_node(contributor):
                    self.graph.add_node(contributor, node_type='contributor')
                if not self.graph.has_node(recipient):
                    self.graph.add_node(recipient, node_type='recipient')
                
                # Add or update edge
                if self.graph.has_edge(contributor, recipient):
                    self.graph[contributor][recipient]['weight'] = \
                        self.graph[contributor][recipient].get('weight', 0) + row.get('amount', 0)
                    self.graph[contributor][recipient]['count'] = \
                        self.graph[contributor][recipient].get('count', 0) + 1
                else:
                    self.graph.add_edge(contributor, recipient, 
                                      weight=row.get('amount', 0),
                                      count=1)
        
        return self.graph
    
    def find_influential_nodes(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Find most influential nodes based on degree centrality."""
        
        if not self.graph.nodes:
            return []
        
        # Calculate degree centrality
        degrees = self.graph.degree()
        max_degree = max(degrees.values()) if degrees else 1
        
        # Normalize to 0-1
        centrality = {node: deg / max_degree for node, deg in degrees.items()}
        
        # Sort and return top N
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        return sorted_nodes[:top_n]
    
    def find_communities(self) -> Dict[int, List[str]]:
        """Find communities using simple connected components."""
        
        if not self.graph.nodes:
            return {}
        
        # Find connected components using BFS
        visited = set()
        communities = {}
        community_id = 0
        
        for node in self.graph.nodes:
            if node not in visited:
                # BFS from this node
                queue = [node]
                community = []
                
                while queue:
                    current = queue.pop(0)
                    if current not in visited:
                        visited.add(current)
                        community.append(current)
                        
                        # Add neighbors to queue
                        for neighbor in self.graph.neighbors(current):
                            if neighbor not in visited:
                                queue.append(neighbor)
                
                if community:
                    communities[community_id] = community
                    community_id += 1
        
        return communities
    
    def calculate_network_metrics(self) -> Dict:
        """Calculate overall network metrics."""
        
        if not self.graph.nodes:
            return {}
        
        num_nodes = self.graph.number_of_nodes()
        num_edges = self.graph.number_of_edges()
        
        # Calculate density
        max_edges = num_nodes * (num_nodes - 1) / 2
        density = num_edges / max_edges if max_edges > 0 else 0
        
        # Calculate average degree
        degrees = self.graph.degree()
        avg_degree = sum(degrees.values()) / num_nodes if num_nodes > 0 else 0
        
        # Count connected components
        communities = self.find_communities()
        
        metrics = {
            'num_nodes': num_nodes,
            'num_edges': num_edges,
            'density': density,
            'avg_degree': avg_degree,
            'num_connected_components': len(communities),
            'largest_component_size': max(len(c) for c in communities.values()) if communities else 0
        }
        
        # Calculate clustering coefficient (simplified)
        clustering_coeffs = []
        for node in self.graph.nodes:
            neighbors = self.graph.neighbors(node)
            if len(neighbors) >= 2:
                # Count edges between neighbors
                neighbor_edges = 0
                for i, n1 in enumerate(neighbors):
                    for n2 in neighbors[i+1:]:
                        if self.graph.has_edge(n1, n2):
                            neighbor_edges += 1
                
                # Calculate clustering coefficient
                max_neighbor_edges = len(neighbors) * (len(neighbors) - 1) / 2
                if max_neighbor_edges > 0:
                    clustering_coeffs.append(neighbor_edges / max_neighbor_edges)
        
        metrics['avg_clustering'] = np.mean(clustering_coeffs) if clustering_coeffs else 0
        
        return metrics