import pandas as pd
import numpy as np
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

class MLClustering:
    """Machine learning clustering and analysis for donor segmentation."""
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=2)
    
    def perform_donor_clustering(self, df, n_clusters=5, features=None):
        """Perform donor clustering analysis."""
        if features is None:
            features = ['amount', 'frequency']
        
        try:
            # Prepare donor-level data
            donor_data = self._prepare_donor_features(df, features)
            
            # Perform clustering
            clustering_results = self._cluster_donors(donor_data, n_clusters)
            
            # Generate cluster descriptions
            cluster_descriptions = self._generate_cluster_descriptions(clustering_results)
            
            # Calculate cluster statistics
            cluster_stats = self._calculate_cluster_statistics(clustering_results)
            
            return {
                'clustered_data': clustering_results,
                'cluster_stats': cluster_stats,
                'segment_descriptions': cluster_descriptions,
                'n_clusters': n_clusters,
                'features_used': features
            }
            
        except Exception as e:
            raise Exception(f"Clustering analysis failed: {str(e)}")
    
    def _prepare_donor_features(self, df, features):
        """Prepare donor-level features for clustering."""
        # Aggregate by donor
        donor_agg = df.groupby('donor_name').agg({
            'amount': ['sum', 'mean', 'count', 'std'],
            'date': ['min', 'max']
        }).reset_index()
        
        # Flatten column names
        donor_agg.columns = [
            'donor_name', 'total_amount', 'avg_amount', 'contribution_count', 
            'amount_std', 'first_contribution', 'last_contribution'
        ]
        
        # Handle missing standard deviations (for single contributions)
        donor_agg['amount_std'] = donor_agg['amount_std'].fillna(0)
        
        # Calculate additional features
        donor_agg['contribution_span_days'] = (
            donor_agg['last_contribution'] - donor_agg['first_contribution']
        ).dt.days
        donor_agg['contribution_span_days'] = donor_agg['contribution_span_days'].fillna(0)
        
        # Calculate frequency (contributions per month)
        donor_agg['frequency_per_month'] = donor_agg.apply(
            lambda row: row['contribution_count'] / max(1, row['contribution_span_days'] / 30.44) 
            if row['contribution_span_days'] > 0 else row['contribution_count'], 
            axis=1
        )
        
        # Add geographic features if available
        if 'state' in df.columns:
            donor_states = df.groupby('donor_name')['state'].first().reset_index()
            donor_agg = donor_agg.merge(donor_states, on='donor_name', how='left')
        
        # Select features for clustering
        feature_columns = []
        
        if 'amount' in features:
            feature_columns.extend(['total_amount', 'avg_amount'])
        if 'frequency' in features:
            feature_columns.extend(['contribution_count', 'frequency_per_month'])
        if 'timing' in features:
            feature_columns.append('contribution_span_days')
        if 'geographic' in features and 'state' in donor_agg.columns:
            # Convert state to numeric (using state frequency as proxy)
            state_freq = df['state'].value_counts().to_dict()
            donor_agg['state_frequency'] = donor_agg['state'].map(state_freq)
            feature_columns.append('state_frequency')
        
        # Ensure we have valid features
        feature_columns = [col for col in feature_columns if col in donor_agg.columns]
        
        if not feature_columns:
            feature_columns = ['total_amount', 'contribution_count']
        
        return donor_agg[['donor_name'] + feature_columns]
    
    def _cluster_donors(self, donor_data, n_clusters):
        """Perform K-means clustering on donor data."""
        # Prepare features for clustering (exclude donor_name)
        feature_columns = [col for col in donor_data.columns if col != 'donor_name']
        X = donor_data[feature_columns].copy()
        
        # Handle any infinite or NaN values
        X = X.replace([np.inf, -np.inf], np.nan)
        X = X.fillna(X.median())
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Perform K-means clustering
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        clusters = kmeans.fit_predict(X_scaled)
        
        # Add cluster assignments to original data
        clustered_data = donor_data.copy()
        clustered_data['cluster'] = clusters
        
        # Add PCA coordinates for visualization
        X_pca = self.pca.fit_transform(X_scaled)
        clustered_data['pca_1'] = X_pca[:, 0]
        clustered_data['pca_2'] = X_pca[:, 1]
        
        return clustered_data
    
    def _generate_cluster_descriptions(self, clustered_data):
        """Generate human-readable descriptions for each cluster."""
        descriptions = {}
        
        for cluster_id in clustered_data['cluster'].unique():
            cluster_subset = clustered_data[clustered_data['cluster'] == cluster_id]
            
            # Calculate cluster characteristics
            avg_total = cluster_subset['total_amount'].mean()
            avg_count = cluster_subset['contribution_count'].mean()
            cluster_size = len(cluster_subset)
            
            # Generate description based on characteristics
            if avg_total > 1000 and avg_count > 5:
                desc = f"Major Donors (n={cluster_size}): High-value, frequent contributors"
            elif avg_total > 1000 and avg_count <= 5:
                desc = f"Large Donors (n={cluster_size}): High-value, infrequent contributors"
            elif avg_total <= 200 and avg_count > 10:
                desc = f"Grassroots Supporters (n={cluster_size}): Small, frequent contributions"
            elif avg_total <= 200 and avg_count <= 3:
                desc = f"Casual Supporters (n={cluster_size}): Small, infrequent contributions"
            else:
                desc = f"Regular Supporters (n={cluster_size}): Moderate contributors"
            
            descriptions[cluster_id] = desc
        
        return descriptions
    
    def _calculate_cluster_statistics(self, clustered_data):
        """Calculate statistics for each cluster."""
        stats = []
        
        for cluster_id in sorted(clustered_data['cluster'].unique()):
            cluster_subset = clustered_data[clustered_data['cluster'] == cluster_id]
            
            stat_row = {
                'Cluster': f'Cluster {cluster_id}',
                'Size': len(cluster_subset),
                'Avg Total Amount': f"${cluster_subset['total_amount'].mean():.2f}",
                'Avg Contribution Count': f"{cluster_subset['contribution_count'].mean():.1f}",
                'Total Cluster Value': f"${cluster_subset['total_amount'].sum():.2f}"
            }
            
            # Add frequency if available
            if 'frequency_per_month' in cluster_subset.columns:
                stat_row['Avg Frequency/Month'] = f"{cluster_subset['frequency_per_month'].mean():.2f}"
            
            stats.append(stat_row)
        
        return pd.DataFrame(stats)
    
    def detect_anomalies(self, df, contamination=0.1):
        """Detect anomalous contributions using Isolation Forest."""
        try:
            # Prepare features for anomaly detection
            feature_data = df[['amount']].copy()
            
            # Add time-based features
            if 'date' in df.columns:
                feature_data['day_of_year'] = df['date'].dt.dayofyear
                feature_data['hour'] = df['date'].dt.hour
            
            # Add donor frequency feature
            donor_counts = df['donor_name'].value_counts().to_dict()
            feature_data['donor_frequency'] = df['donor_name'].map(donor_counts)
            
            # Handle missing values
            feature_data = feature_data.fillna(feature_data.median())
            
            # Scale features
            X_scaled = self.scaler.fit_transform(feature_data)
            
            # Detect anomalies
            isolation_forest = IsolationForest(
                contamination=contamination, 
                random_state=42, 
                n_estimators=100
            )
            anomaly_labels = isolation_forest.fit_predict(X_scaled)
            
            # Get anomalous records
            anomaly_mask = anomaly_labels == -1
            anomalies = df[anomaly_mask].copy()
            anomalies['anomaly_score'] = isolation_forest.score_samples(X_scaled)[anomaly_mask]
            
            return anomalies.sort_values('anomaly_score')
            
        except Exception as e:
            raise Exception(f"Anomaly detection failed: {str(e)}")
    
    def visualize_clusters(self, clustering_results):
        """Create visualization of clustering results."""
        clustered_data = clustering_results['clustered_data']
        
        # Create scatter plot using PCA coordinates
        fig = px.scatter(
            clustered_data,
            x='pca_1',
            y='pca_2',
            color='cluster',
            hover_data=['donor_name', 'total_amount', 'contribution_count'],
            title='Donor Clustering Visualization (PCA)',
            labels={
                'pca_1': 'Principal Component 1',
                'pca_2': 'Principal Component 2',
                'cluster': 'Cluster'
            }
        )
        
        fig.update_layout(height=500)
        
        return fig
    
    def visualize_anomalies(self, df, anomalies):
        """Create visualization of detected anomalies."""
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Anomalies by Amount', 'Anomalies Over Time')
        )
        
        # Scatter plot: Amount vs Count
        fig.add_trace(
            go.Scatter(
                x=df['amount'],
                y=[1] * len(df),
                mode='markers',
                name='Normal',
                marker=dict(color='blue', opacity=0.6),
                showlegend=True
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=anomalies['amount'],
                y=[1] * len(anomalies),
                mode='markers',
                name='Anomalies',
                marker=dict(color='red', size=10),
                showlegend=True
            ),
            row=1, col=1
        )
        
        # Time series plot
        if 'date' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df['date'],
                    y=df['amount'],
                    mode='markers',
                    name='Normal',
                    marker=dict(color='blue', opacity=0.6),
                    showlegend=False
                ),
                row=1, col=2
            )
            
            fig.add_trace(
                go.Scatter(
                    x=anomalies['date'],
                    y=anomalies['amount'],
                    mode='markers',
                    name='Anomalies',
                    marker=dict(color='red', size=10),
                    showlegend=False
                ),
                row=1, col=2
            )
        
        fig.update_layout(
            height=500,
            title_text="Anomaly Detection Results"
        )
        
        return fig
