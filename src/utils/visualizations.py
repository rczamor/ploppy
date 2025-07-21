import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

class Visualizations:
    """Create interactive visualizations for political contribution data."""
    
    def __init__(self):
        # Color scheme for consistent visualizations
        self.colors = {
            'primary': '#1f77b4',
            'secondary': '#ff7f0e',
            'success': '#2ca02c',
            'danger': '#d62728',
            'warning': '#ff7f0e',
            'info': '#17a2b8',
            'purple': '#9467bd',
            'brown': '#8c564b',
            'pink': '#e377c2',
            'gray': '#7f7f7f'
        }
    
    def create_time_series_chart(self, df):
        """Create time series visualization of contributions over time."""
        # Aggregate contributions by month
        monthly_data = df.groupby(df['date'].dt.to_period('M')).agg({
            'amount': 'sum',
            'donor_name': 'count'
        }).reset_index()
        monthly_data['date'] = monthly_data['date'].dt.to_timestamp()
        
        # Create subplot with secondary y-axis
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Add contribution amount line
        fig.add_trace(
            go.Scatter(
                x=monthly_data['date'],
                y=monthly_data['amount'],
                mode='lines+markers',
                name='Total Amount',
                line=dict(color=self.colors['primary'], width=3),
                hovertemplate='<b>%{x|%B %Y}</b><br>Amount: $%{y:,.0f}<extra></extra>'
            ),
            secondary_y=False,
        )
        
        # Add contribution count line
        fig.add_trace(
            go.Scatter(
                x=monthly_data['date'],
                y=monthly_data['donor_name'],
                mode='lines+markers',
                name='Number of Contributions',
                line=dict(color=self.colors['secondary'], width=2),
                hovertemplate='<b>%{x|%B %Y}</b><br>Count: %{y}<extra></extra>'
            ),
            secondary_y=True,
        )
        
        # Update axes labels
        fig.update_xaxes(title_text="Date")
        fig.update_yaxes(title_text="Contribution Amount ($)", secondary_y=False)
        fig.update_yaxes(title_text="Number of Contributions", secondary_y=True)
        
        fig.update_layout(
            title="Contribution Trends Over Time",
            hovermode='x unified',
            height=500
        )
        
        return fig
    
    def create_geographic_map(self, df):
        """Create geographic distribution map of contributions."""
        if 'state' not in df.columns:
            # Create a placeholder chart
            fig = go.Figure()
            fig.add_annotation(
                text="Geographic data not available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16)
            )
            return fig
        
        # Aggregate by state
        state_data = df.groupby('state').agg({
            'amount': 'sum',
            'donor_name': 'count'
        }).reset_index()
        
        # Create choropleth map
        fig = go.Figure(data=go.Choropleth(
            locations=state_data['state'],
            z=state_data['amount'],
            locationmode='USA-states',
            colorscale='Blues',
            text=state_data['state'],
            hovertemplate='<b>%{text}</b><br>Amount: $%{z:,.0f}<br>Count: %{customdata}<extra></extra>',
            customdata=state_data['donor_name']
        ))
        
        fig.update_layout(
            title_text='Geographic Distribution of Contributions',
            geo_scope='usa',
            height=500
        )
        
        return fig
    
    def create_amount_distribution(self, df):
        """Create distribution visualization of contribution amounts."""
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Amount Distribution', 'Amount Categories'),
            specs=[[{"type": "histogram"}, {"type": "bar"}]]
        )
        
        # Histogram of amounts
        fig.add_trace(
            go.Histogram(
                x=df['amount'],
                nbinsx=50,
                name='Distribution',
                marker_color=self.colors['primary'],
                opacity=0.7
            ),
            row=1, col=1
        )
        
        # Category counts
        if 'amount_category' in df.columns:
            category_counts = df['amount_category'].value_counts()
            fig.add_trace(
                go.Bar(
                    x=category_counts.index,
                    y=category_counts.values,
                    name='Categories',
                    marker_color=self.colors['secondary'],
                    text=category_counts.values,
                    textposition='outside'
                ),
                row=1, col=2
            )
        
        fig.update_layout(
            height=500,
            showlegend=False,
            title_text="Contribution Amount Analysis"
        )
        
        return fig
    
    def create_top_contributors_chart(self, df):
        """Create chart of top contributors by total amount."""
        top_contributors = df.groupby('donor_name')['amount'].sum().sort_values(ascending=False).head(15)
        
        fig = go.Figure(data=[
            go.Bar(
                x=top_contributors.values,
                y=top_contributors.index,
                orientation='h',
                marker_color=self.colors['success'],
                text=[f'${x:,.0f}' for x in top_contributors.values],
                textposition='outside',
                hovertemplate='<b>%{y}</b><br>Total: $%{x:,.0f}<extra></extra>'
            )
        ])
        
        fig.update_layout(
            title="Top 15 Contributors by Total Amount",
            xaxis_title="Total Contribution Amount ($)",
            yaxis_title="Contributor",
            height=500,
            yaxis={'categoryorder': 'total ascending'}
        )
        
        return fig
    
    def create_top_recipients_chart(self, df):
        """Create chart of top recipients by total amount."""
        if 'recipient' not in df.columns:
            fig = go.Figure()
            fig.add_annotation(
                text="Recipient data not available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16)
            )
            return fig
        
        top_recipients = df.groupby('recipient')['amount'].sum().sort_values(ascending=False).head(15)
        
        fig = go.Figure(data=[
            go.Bar(
                x=top_recipients.values,
                y=top_recipients.index,
                orientation='h',
                marker_color=self.colors['info'],
                text=[f'${x:,.0f}' for x in top_recipients.values],
                textposition='outside',
                hovertemplate='<b>%{y}</b><br>Total: $%{x:,.0f}<extra></extra>'
            )
        ])
        
        fig.update_layout(
            title="Top 15 Recipients by Total Amount",
            xaxis_title="Total Received Amount ($)",
            yaxis_title="Recipient",
            height=500,
            yaxis={'categoryorder': 'total ascending'}
        )
        
        return fig
    
    def create_contribution_patterns(self, df):
        """Create visualization of contribution patterns by day of week and hour."""
        # Create day of week and hour patterns
        df_with_time = df.copy()
        df_with_time['day_of_week'] = df_with_time['date'].dt.day_name()
        df_with_time['hour'] = df_with_time['date'].dt.hour
        
        # Day of week pattern
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_pattern = df_with_time.groupby('day_of_week')['amount'].agg(['count', 'sum']).reindex(day_order)
        
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Contributions by Day of Week', 'Average Amount by Day'),
            specs=[[{"type": "bar"}], [{"type": "bar"}]]
        )
        
        # Count by day
        fig.add_trace(
            go.Bar(
                x=day_pattern.index,
                y=day_pattern['count'],
                name='Count',
                marker_color=self.colors['purple'],
                text=day_pattern['count'],
                textposition='outside'
            ),
            row=1, col=1
        )
        
        # Average amount by day
        avg_by_day = day_pattern['sum'] / day_pattern['count']
        fig.add_trace(
            go.Bar(
                x=avg_by_day.index,
                y=avg_by_day.values,
                name='Average Amount',
                marker_color=self.colors['brown'],
                text=[f'${x:.0f}' for x in avg_by_day.values],
                textposition='outside'
            ),
            row=2, col=1
        )
        
        fig.update_layout(
            height=600,
            showlegend=False,
            title_text="Contribution Patterns Analysis"
        )
        
        return fig
    
    def create_seasonal_trends(self, df):
        """Create seasonal trends visualization."""
        df_seasonal = df.copy()
        df_seasonal['month'] = df_seasonal['date'].dt.month
        df_seasonal['quarter'] = df_seasonal['date'].dt.quarter
        
        # Monthly trends
        monthly_trends = df_seasonal.groupby('month')['amount'].agg(['count', 'sum', 'mean'])
        
        # Quarterly trends  
        quarterly_trends = df_seasonal.groupby('quarter')['amount'].agg(['count', 'sum', 'mean'])
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Monthly Contribution Count', 'Monthly Total Amount', 
                          'Quarterly Contribution Count', 'Quarterly Total Amount'),
            specs=[[{"type": "scatter"}, {"type": "scatter"}], 
                   [{"type": "bar"}, {"type": "bar"}]]
        )
        
        # Monthly count
        fig.add_trace(
            go.Scatter(
                x=monthly_trends.index,
                y=monthly_trends['count'],
                mode='lines+markers',
                name='Monthly Count',
                line=dict(color=self.colors['primary'], width=3),
                marker=dict(size=8)
            ),
            row=1, col=1
        )
        
        # Monthly amount
        fig.add_trace(
            go.Scatter(
                x=monthly_trends.index,
                y=monthly_trends['sum'],
                mode='lines+markers',
                name='Monthly Amount',
                line=dict(color=self.colors['secondary'], width=3),
                marker=dict(size=8)
            ),
            row=1, col=2
        )
        
        # Quarterly count
        fig.add_trace(
            go.Bar(
                x=['Q1', 'Q2', 'Q3', 'Q4'],
                y=quarterly_trends['count'],
                name='Quarterly Count',
                marker_color=self.colors['success']
            ),
            row=2, col=1
        )
        
        # Quarterly amount
        fig.add_trace(
            go.Bar(
                x=['Q1', 'Q2', 'Q3', 'Q4'],
                y=quarterly_trends['sum'],
                name='Quarterly Amount',
                marker_color=self.colors['info']
            ),
            row=2, col=2
        )
        
        fig.update_layout(
            height=600,
            showlegend=False,
            title_text="Seasonal Contribution Trends"
        )
        
        return fig
    
    def create_donor_segment_visualization(self, clustering_results):
        """Create visualization for donor segmentation results."""
        cluster_data = clustering_results['clustered_data']
        
        fig = px.scatter(
            cluster_data,
            x='total_amount',
            y='contribution_count',
            color='cluster',
            size='avg_amount',
            hover_data=['donor_name'],
            title='Donor Segmentation Analysis',
            labels={
                'total_amount': 'Total Contribution Amount ($)',
                'contribution_count': 'Number of Contributions',
                'cluster': 'Donor Segment'
            }
        )
        
        fig.update_layout(height=500)
        
        return fig
