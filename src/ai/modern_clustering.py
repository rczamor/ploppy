"""Modern clustering using DBSCAN with optimizations and UMAP-ready architecture."""

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, AgglomerativeClustering, SpectralClustering
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.metrics import silhouette_score, davies_bouldin_score
from typing import List, Dict, Tuple, Optional, Union
import warnings
warnings.filterwarnings('ignore')

class ModernClustering:
    """Advanced clustering with multiple algorithms and automatic optimization."""
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.labels = None
        self.embeddings = None
        self.reduced_embeddings = None
        
    def reduce_dimensions(self, embeddings: np.ndarray, n_components: int = 50, 
                         method: str = 'pca') -> np.ndarray:
        """Reduce dimensions for better clustering."""
        
        if embeddings.shape[1] <= n_components:
            return embeddings
        
        if method == 'pca':
            reducer = PCA(n_components=n_components, random_state=42)
        elif method == 'tsne':
            # T-SNE for visualization (2D/3D)
            reducer = TSNE(n_components=min(n_components, 3), random_state=42)
        else:
            # Default to PCA
            reducer = PCA(n_components=n_components, random_state=42)
        
        self.reduced_embeddings = reducer.fit_transform(embeddings)
        return self.reduced_embeddings
    
    def auto_cluster(self, embeddings: np.ndarray, 
                    min_clusters: int = 2, 
                    max_clusters: int = 20) -> Dict:
        """Automatically find optimal clustering using multiple methods."""
        
        # Standardize embeddings
        embeddings_scaled = self.scaler.fit_transform(embeddings)
        
        # Reduce dimensions if needed
        if embeddings.shape[1] > 50:
            embeddings_scaled = self.reduce_dimensions(embeddings_scaled, n_components=50)
        
        self.embeddings = embeddings_scaled
        
        results = {}
        best_score = -1
        best_method = None
        best_labels = None
        
        # Try DBSCAN with different parameters
        for eps in np.linspace(0.1, 2.0, 10):
            for min_samples in [3, 5, 10]:
                clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric='euclidean')
                labels = clusterer.fit_predict(embeddings_scaled)
                
                n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
                n_noise = list(labels).count(-1)
                
                if min_clusters <= n_clusters <= max_clusters:
                    # Calculate metrics
                    if n_clusters > 1:
                        try:
                            score = silhouette_score(embeddings_scaled, labels)
                            
                            results[f'dbscan_eps{eps:.2f}_ms{min_samples}'] = {
                                'labels': labels,
                                'n_clusters': n_clusters,
                                'n_noise': n_noise,
                                'silhouette': score,
                                'method': 'dbscan',
                                'params': {'eps': eps, 'min_samples': min_samples}
                            }
                            
                            if score > best_score:
                                best_score = score
                                best_method = f'dbscan_eps{eps:.2f}_ms{min_samples}'
                                best_labels = labels
                        except:
                            pass
        
        # Try Agglomerative Clustering
        for n_clusters in range(min_clusters, min(max_clusters, 20)):
            clusterer = AgglomerativeClustering(n_clusters=n_clusters)
            labels = clusterer.fit_predict(embeddings_scaled)
            
            try:
                score = silhouette_score(embeddings_scaled, labels)
                
                results[f'agglomerative_{n_clusters}'] = {
                    'labels': labels,
                    'n_clusters': n_clusters,
                    'n_noise': 0,
                    'silhouette': score,
                    'method': 'agglomerative',
                    'params': {'n_clusters': n_clusters}
                }
                
                if score > best_score:
                    best_score = score
                    best_method = f'agglomerative_{n_clusters}'
                    best_labels = labels
            except:
                pass
        
        # Store best results
        if best_labels is not None:
            self.labels = best_labels
            results['best'] = results[best_method]
            results['best']['method_name'] = best_method
        
        return results
    
    def cluster_dbscan(self, embeddings: np.ndarray, 
                       eps: float = 0.5, 
                       min_samples: int = 5,
                       standardize: bool = True) -> np.ndarray:
        """Perform DBSCAN clustering with optimizations."""
        
        # Standardize if requested
        if standardize:
            embeddings = self.scaler.fit_transform(embeddings)
        
        self.embeddings = embeddings
        
        # Apply DBSCAN
        clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric='euclidean', n_jobs=-1)
        self.labels = clusterer.fit_predict(embeddings)
        
        return self.labels
    
    def soft_clustering(self, embeddings: np.ndarray, n_clusters: int = 10) -> np.ndarray:
        """Perform soft clustering with membership probabilities."""
        
        from sklearn.mixture import GaussianMixture
        
        # Standardize
        embeddings_scaled = self.scaler.fit_transform(embeddings)
        
        # Reduce dimensions if needed
        if embeddings.shape[1] > 50:
            embeddings_scaled = self.reduce_dimensions(embeddings_scaled, n_components=50)
        
        # Apply Gaussian Mixture Model for soft clustering
        gmm = GaussianMixture(n_components=n_clusters, random_state=42)
        gmm.fit(embeddings_scaled)
        
        # Get probabilities
        probabilities = gmm.predict_proba(embeddings_scaled)
        
        # Hard labels
        self.labels = gmm.predict(embeddings_scaled)
        
        return probabilities
    
    def find_outliers(self, embeddings: np.ndarray, 
                     contamination: float = 0.1) -> np.ndarray:
        """Find outliers using multiple methods."""
        
        from sklearn.ensemble import IsolationForest
        from sklearn.neighbors import LocalOutlierFactor
        
        # Standardize
        embeddings_scaled = self.scaler.fit_transform(embeddings)
        
        # Isolation Forest
        iso_forest = IsolationForest(contamination=contamination, random_state=42)
        outliers_iso = iso_forest.fit_predict(embeddings_scaled)
        
        # Local Outlier Factor
        lof = LocalOutlierFactor(contamination=contamination)
        outliers_lof = lof.fit_predict(embeddings_scaled)
        
        # Combine results (outlier if both methods agree)
        outliers = np.where((outliers_iso == -1) & (outliers_lof == -1), -1, 1)
        
        return outliers
    
    def get_cluster_stats(self) -> pd.DataFrame:
        """Get statistics for each cluster."""
        
        if self.labels is None or self.embeddings is None:
            return pd.DataFrame()
        
        stats = []
        unique_labels = set(self.labels)
        
        for label in unique_labels:
            mask = self.labels == label
            cluster_points = self.embeddings[mask]
            
            if label == -1:
                cluster_type = 'Noise'
            else:
                cluster_type = f'Cluster {label}'
            
            stats.append({
                'cluster': cluster_type,
                'size': len(cluster_points),
                'percentage': len(cluster_points) / len(self.labels) * 100,
                'mean_distance': np.mean(np.linalg.norm(cluster_points - cluster_points.mean(axis=0), axis=1)) if len(cluster_points) > 0 else 0,
                'std_distance': np.std(np.linalg.norm(cluster_points - cluster_points.mean(axis=0), axis=1)) if len(cluster_points) > 0 else 0
            })
        
        return pd.DataFrame(stats).sort_values('size', ascending=False)
    
    def visualize_clusters_2d(self, embeddings: np.ndarray = None, 
                             labels: np.ndarray = None) -> Dict:
        """Prepare data for 2D cluster visualization."""
        
        if embeddings is None:
            embeddings = self.embeddings
        if labels is None:
            labels = self.labels
        
        if embeddings is None or labels is None:
            return {}
        
        # Reduce to 2D if needed
        if embeddings.shape[1] > 2:
            embeddings_2d = self.reduce_dimensions(embeddings, n_components=2, method='pca')
        else:
            embeddings_2d = embeddings
        
        # Prepare visualization data
        viz_data = {
            'x': embeddings_2d[:, 0].tolist(),
            'y': embeddings_2d[:, 1].tolist(),
            'labels': labels.tolist(),
            'colors': [f'C{label}' if label != -1 else 'gray' for label in labels]
        }
        
        return viz_data


class AnomalyDetector:
    """Advanced anomaly detection for contribution data."""
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.anomaly_scores = None
        
    def detect_anomalies(self, data: pd.DataFrame, 
                        features: List[str],
                        method: str = 'ensemble') -> pd.DataFrame:
        """Detect anomalies in contribution data."""
        
        # Extract features
        X = data[features].fillna(0).values
        X_scaled = self.scaler.fit_transform(X)
        
        anomaly_scores = np.zeros(len(X))
        
        if method in ['isolation', 'ensemble']:
            # Isolation Forest
            from sklearn.ensemble import IsolationForest
            iso = IsolationForest(contamination=0.1, random_state=42)
            iso.fit(X_scaled)  # Fit the model first
            iso_scores = iso.decision_function(X_scaled)
            anomaly_scores += (1 - iso_scores) / 2  # Normalize to 0-1
        
        if method in ['lof', 'ensemble']:
            # Local Outlier Factor
            from sklearn.neighbors import LocalOutlierFactor
            lof = LocalOutlierFactor(contamination=0.1)
            lof_labels = lof.fit_predict(X_scaled)
            lof_scores = -lof.negative_outlier_factor_
            anomaly_scores += (lof_scores - lof_scores.min()) / (lof_scores.max() - lof_scores.min())
        
        if method in ['svm', 'ensemble']:
            # One-class SVM
            from sklearn.svm import OneClassSVM
            svm = OneClassSVM(gamma='auto', nu=0.1)
            svm.fit(X_scaled)
            svm_scores = -svm.decision_function(X_scaled)
            anomaly_scores += (svm_scores - svm_scores.min()) / (svm_scores.max() - svm_scores.min())
        
        # Average scores if ensemble
        if method == 'ensemble':
            anomaly_scores /= 3
        
        # Add to dataframe
        result = data.copy()
        result['anomaly_score'] = anomaly_scores
        result['is_anomaly'] = anomaly_scores > np.percentile(anomaly_scores, 90)
        
        self.anomaly_scores = anomaly_scores
        
        return result.sort_values('anomaly_score', ascending=False)
    
    def explain_anomaly(self, data_point: pd.Series, 
                       features: List[str],
                       reference_data: pd.DataFrame) -> Dict:
        """Explain why a data point is anomalous."""
        
        explanation = {}
        
        for feature in features:
            if feature in data_point:
                value = data_point[feature]
                
                # Calculate statistics
                mean = reference_data[feature].mean()
                std = reference_data[feature].std()
                percentile = (reference_data[feature] <= value).mean() * 100
                
                # Calculate z-score
                z_score = abs((value - mean) / std) if std > 0 else 0
                
                if z_score > 2:
                    explanation[feature] = {
                        'value': value,
                        'mean': mean,
                        'std': std,
                        'z_score': z_score,
                        'percentile': percentile,
                        'anomalous': True,
                        'reason': f'Value is {z_score:.1f} standard deviations from mean'
                    }
        
        return explanation