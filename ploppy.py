"""
🐷 Ploppy - NYC Campaign Finance Explorer
A fun, engaging way to explore NYC political contributions!
Named after the pig from The Simpsons Movie
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import time

# Import custom modules
from src.database.db_manager_v2 import NYCCFBDatabase
from src.database.code_mappings import *
from src.utils.utils import format_currency
from src.ai.ai_search import ContributionAnalyzer, NaturalLanguageQueryProcessor

# Page configuration with pig theme
st.set_page_config(
    page_title="Ploppy - NYC Campaign Finance Explorer",
    page_icon="🐷",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for a beautiful, playful design
st.markdown("""
<style>
    /* Main theme colors - pink/purple pig theme */
    :root {
        --ploppy-pink: #FF69B4;
        --ploppy-purple: #DDA0DD;
        --ploppy-light: #FFE4E1;
        --ploppy-dark: #8B4789;
        --ploppy-accent: #FF1493;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Custom fonts and general styling */
    .stApp {
        background: linear-gradient(135deg, #FFF5F7 0%, #FFE0EC 100%);
    }
    
    /* Main title styling */
    .ploppy-title {
        font-size: 3.5rem;
        font-weight: 800;
        background: linear-gradient(45deg, var(--ploppy-pink), var(--ploppy-purple));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0;
        font-family: 'Comic Sans MS', cursive;
    }
    
    .ploppy-subtitle {
        text-align: center;
        color: var(--ploppy-dark);
        font-size: 1.2rem;
        margin-top: -10px;
        margin-bottom: 2rem;
    }
    
    /* Search bar styling */
    .search-container {
        background: white;
        border-radius: 50px;
        padding: 1rem;
        box-shadow: 0 8px 32px rgba(255, 105, 180, 0.1);
        margin-bottom: 2rem;
    }
    
    /* Metric cards */
    .metric-card {
        background: white;
        border-radius: 20px;
        padding: 1.5rem;
        box-shadow: 0 4px 20px rgba(255, 105, 180, 0.1);
        transition: transform 0.2s;
        border: 2px solid transparent;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        border-color: var(--ploppy-pink);
        box-shadow: 0 8px 30px rgba(255, 105, 180, 0.2);
    }
    
    /* Data table styling */
    .dataframe {
        border-radius: 15px !important;
        overflow: hidden;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
    }
    
    .dataframe thead {
        background: var(--ploppy-pink) !important;
        color: white !important;
    }
    
    .dataframe tbody tr:hover {
        background: var(--ploppy-light) !important;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(45deg, var(--ploppy-pink), var(--ploppy-purple));
        color: white;
        border: none;
        border-radius: 25px;
        padding: 0.5rem 2rem;
        font-weight: 600;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 20px rgba(255, 105, 180, 0.4);
    }
    
    /* Filter sidebar */
    .css-1d391kg {
        background: white;
        border-radius: 0 20px 20px 0;
        box-shadow: 5px 0 20px rgba(0, 0, 0, 0.05);
    }
    
    /* Loading animation */
    .ploppy-loader {
        text-align: center;
        font-size: 3rem;
        animation: bounce 1s infinite;
    }
    
    @keyframes bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-20px); }
    }
    
    /* Fun tooltip */
    .tooltip {
        position: relative;
        display: inline-block;
        cursor: help;
    }
    
    .tooltip .tooltiptext {
        visibility: hidden;
        background-color: var(--ploppy-dark);
        color: white;
        text-align: center;
        border-radius: 10px;
        padding: 5px 10px;
        position: absolute;
        z-index: 1;
        bottom: 125%;
        left: 50%;
        margin-left: -60px;
        opacity: 0;
        transition: opacity 0.3s;
    }
    
    .tooltip:hover .tooltiptext {
        visibility: visible;
        opacity: 1;
    }
</style>
""", unsafe_allow_html=True)

# Initialize database connection
@st.cache_resource
def init_database():
    """Initialize database connection."""
    try:
        db = NYCCFBDatabase()
        return db
    except Exception as e:
        st.error(f"Oink! Database connection failed: {e}")
        raise

# Initialize AI components
@st.cache_resource
def init_ai_components():
    """Initialize AI search components."""
    try:
        analyzer = ContributionAnalyzer()
        query_processor = NaturalLanguageQueryProcessor()
        return analyzer, query_processor
    except Exception as e:
        st.warning("AI features unavailable - but Ploppy still works great! 🐷")
        return None, None

# Cache key stats
@st.cache_data(ttl=300)
def get_key_stats():
    """Get key statistics for display."""
    db = init_database()
    stats = db.get_database_stats()
    
    # Calculate some fun stats
    query_recent = """
        SELECT 
            COUNT(*) as today_count,
            SUM(amount) as today_amount
        FROM contributions
        WHERE transaction_date >= CURRENT_DATE - INTERVAL '1 day'
    """
    recent = db.execute_query(query_recent)
    
    # Ensure no None values in the return dictionary
    total_amount_result = db.execute_query("SELECT SUM(amount) FROM contributions")
    total_amount = total_amount_result.iloc[0, 0] if not total_amount_result.empty else 0
    total_amount = total_amount if total_amount is not None else 0
    
    today_count = 0
    today_amount = 0
    if not recent.empty:
        today_count = recent['today_count'].iloc[0]
        today_amount = recent['today_amount'].iloc[0]
        # Handle None values
        today_count = today_count if today_count is not None else 0
        today_amount = today_amount if today_amount is not None else 0
    
    return {
        'total_contributions': stats.get('contributions_count', 0),
        'total_amount': total_amount,
        'unique_contributors': stats.get('contributors_count', 0),
        'today_contributions': today_count,
        'today_amount': today_amount
    }

# Main search function
@st.cache_data(ttl=60)
def search_contributions(query=None, filters=None, limit=100, offset=0):
    """Search contributions with natural language or filters."""
    db = init_database()
    
    # Base query
    base_query = """
        SELECT 
            c.id,
            c.transaction_date,
            c.amount,
            c.payment_method_desc as payment_method,
            contrib.last_name || CASE 
                WHEN contrib.first_name != '' THEN ', ' || contrib.first_name 
                ELSE '' 
            END as contributor,
            contrib.contributor_type,
            r.last_name || CASE 
                WHEN r.first_name != '' THEN ', ' || r.first_name 
                ELSE '' 
            END as recipient,
            r.office_name as office,
            r.party,
            l.city,
            l.state,
            l.borough_name as borough,
            e.name as employer
        FROM contributions c
        JOIN contributors contrib ON c.contributor_id = contrib.id
        JOIN recipients r ON c.recipient_id = r.id
        LEFT JOIN locations l ON c.location_id = l.id
        LEFT JOIN employers e ON contrib.employer_id = e.id
        WHERE 1=1
    """
    
    # Apply filters
    conditions = []
    
    if filters:
        if filters.get('date_from'):
            conditions.append(f"c.transaction_date >= '{filters['date_from']}'")
        if filters.get('date_to'):
            conditions.append(f"c.transaction_date <= '{filters['date_to']}'")
        if filters.get('min_amount'):
            conditions.append(f"c.amount >= {filters['min_amount']}")
        if filters.get('max_amount'):
            conditions.append(f"c.amount <= {filters['max_amount']}")
        if filters.get('party'):
            conditions.append(f"r.party = '{filters['party']}'")
        if filters.get('borough'):
            conditions.append(f"l.borough_name = '{filters['borough']}'")
        if filters.get('office'):
            conditions.append(f"r.office_name = '{filters['office']}'")
    
    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    
    # Add ordering and limit
    base_query += f" ORDER BY c.transaction_date DESC LIMIT {limit} OFFSET {offset}"
    
    return db.execute_query(base_query)

# Dynamic chart functions
def create_amount_distribution_chart(df):
    """Create amount distribution chart."""
    if df.empty:
        return None
    
    # Create bins for amounts
    bins = [0, 10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float('inf')]
    labels = ['$0-10', '$10-50', '$50-100', '$100-250', '$250-500', 
              '$500-1k', '$1k-2.5k', '$2.5k-5k', '$5k-10k', '$10k+']
    
    df['amount_range'] = pd.cut(df['amount'], bins=bins, labels=labels)
    amount_dist = df['amount_range'].value_counts().sort_index()
    
    fig = go.Figure(data=[
        go.Bar(
            x=amount_dist.index,
            y=amount_dist.values,
            marker_color='hotpink',
            marker_line_color='darkmagenta',
            marker_line_width=2,
            text=amount_dist.values,
            textposition='outside'
        )
    ])
    
    fig.update_layout(
        title='Contribution Amount Distribution',
        xaxis_title='Amount Range',
        yaxis_title='Number of Contributions',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=14),
        margin=dict(t=40, b=40, l=40, r=40),
        height=300
    )
    
    return fig

def create_timeline_chart(df):
    """Create timeline chart of contributions."""
    if df.empty:
        return None
    
    # Group by date
    daily = df.groupby(df['transaction_date'].dt.date).agg({
        'amount': ['sum', 'count']
    }).reset_index()
    daily.columns = ['date', 'total_amount', 'count']
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=('Daily Contribution Amount', 'Daily Contribution Count')
    )
    
    # Amount chart
    fig.add_trace(
        go.Scatter(
            x=daily['date'],
            y=daily['total_amount'],
            mode='lines+markers',
            name='Amount',
            line=dict(color='hotpink', width=3),
            marker=dict(size=8),
            fill='tozeroy',
            fillcolor='rgba(255,105,180,0.2)'
        ),
        row=1, col=1
    )
    
    # Count chart
    fig.add_trace(
        go.Bar(
            x=daily['date'],
            y=daily['count'],
            name='Count',
            marker_color='plum'
        ),
        row=2, col=1
    )
    
    fig.update_layout(
        height=400,
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=40, b=40, l=40, r=40)
    )
    
    return fig

def create_party_chart(df):
    """Create party distribution chart."""
    if df.empty:
        return None
    
    party_stats = df.groupby('party').agg({
        'amount': ['sum', 'count', 'mean']
    }).reset_index()
    party_stats.columns = ['party', 'total_amount', 'count', 'avg_amount']
    party_stats = party_stats.sort_values('total_amount', ascending=True)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=party_stats['party'],
        x=party_stats['total_amount'],
        orientation='h',
        marker_color=['#FF69B4', '#DDA0DD', '#FFB6C1', '#FF1493', '#DB7093'],
        text=[f"${x:,.0f}" for x in party_stats['total_amount']],
        textposition='outside'
    ))
    
    fig.update_layout(
        title='Total Contributions by Party',
        xaxis_title='Total Amount ($)',
        yaxis_title='',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        height=300,
        margin=dict(t=40, b=40, l=100, r=40)
    )
    
    return fig

def create_top_contributors_chart(df):
    """Create top contributors chart."""
    if df.empty:
        return None
    
    top_contributors = df.groupby('contributor')['amount'].sum().sort_values(ascending=False).head(10)
    
    fig = go.Figure(data=[
        go.Bar(
            y=top_contributors.index,
            x=top_contributors.values,
            orientation='h',
            marker=dict(
                color=top_contributors.values,
                colorscale='Purples',
                showscale=False
            ),
            text=[f"${x:,.0f}" for x in top_contributors.values],
            textposition='outside'
        )
    ])
    
    fig.update_layout(
        title='Top 10 Contributors',
        xaxis_title='Total Contributions ($)',
        yaxis_title='',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        height=400,
        margin=dict(t=40, b=40, l=200, r=40)
    )
    
    return fig

# Main app function
def main():
    # Header with playful title
    st.markdown('<h1 class="ploppy-title">🐷 Ploppy</h1>', unsafe_allow_html=True)
    st.markdown('<p class="ploppy-subtitle">Your friendly NYC Campaign Finance Explorer</p>', unsafe_allow_html=True)
    
    # Initialize session state
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 0
    if 'filters' not in st.session_state:
        st.session_state.filters = {}
    
    # Get key stats
    try:
        stats = get_key_stats()
    except:
        stats = {
            'total_contributions': 0,
            'total_amount': 0,
            'unique_contributors': 0,
            'today_contributions': 0,
            'today_amount': 0
        }
    
    # Display key metrics in a fun way
    st.markdown("### 📊 Quick Stats")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric(
            "Total Contributions", 
            f"{stats.get('total_contributions', 0):,}",
            delta=f"+{stats.get('today_contributions', 0)} today"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric(
            "Total Amount", 
            f"${stats.get('total_amount', 0) or 0:,.0f}",
            delta=f"+${stats.get('today_amount', 0) or 0:,.0f} today"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric(
            "Unique Contributors", 
            f"{stats.get('unique_contributors', 0):,}"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        avg_contribution = (stats.get('total_amount', 0) or 0) / max(stats.get('total_contributions', 1), 1)
        st.metric(
            "Average Contribution", 
            f"${avg_contribution:,.0f}"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col5:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric(
            "Data Freshness", 
            "Live 🟢"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Search and Filter Section
    st.markdown("### 🔍 Search Contributions")
    
    # Natural Language Search Bar
    search_col1, search_col2 = st.columns([5, 1])
    with search_col1:
        search_query = st.text_input(
            "Ask Ploppy anything about NYC campaign contributions!",
            placeholder="e.g., 'Show me the biggest donors to mayoral campaigns' or 'What contributions came from Brooklyn in 2024?'",
            key="nl_search"
        )
    
    with search_col2:
        search_button = st.button("🔍 Search", type="primary", use_container_width=True)
    
    # Expandable filters
    with st.expander("🎚️ Advanced Filters", expanded=False):
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        
        with filter_col1:
            date_from = st.date_input("From Date", value=None, key="date_from")
            date_to = st.date_input("To Date", value=None, key="date_to")
        
        with filter_col2:
            min_amount = st.number_input("Min Amount ($)", min_value=0, value=None, key="min_amount")
            max_amount = st.number_input("Max Amount ($)", min_value=0, value=None, key="max_amount")
        
        with filter_col3:
            parties = ["All", "Democratic", "Republican", "Independent", "Other"]
            selected_party = st.selectbox("Party", parties, key="party_filter")
            
            boroughs = ["All", "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"]
            selected_borough = st.selectbox("Borough", boroughs, key="borough_filter")
        
        with filter_col4:
            offices = ["All", "Mayor", "City Council", "Comptroller", "Public Advocate", "Borough President"]
            selected_office = st.selectbox("Office", offices, key="office_filter")
            
            apply_filters = st.button("Apply Filters", use_container_width=True)
    
    # Build filters dict
    if search_button or apply_filters:
        filters = {}
        if date_from:
            filters['date_from'] = date_from
        if date_to:
            filters['date_to'] = date_to
        if min_amount:
            filters['min_amount'] = min_amount
        if max_amount:
            filters['max_amount'] = max_amount
        if selected_party != "All":
            filters['party'] = selected_party
        if selected_borough != "All":
            filters['borough'] = selected_borough
        if selected_office != "All":
            filters['office'] = selected_office
        
        st.session_state.filters = filters
        st.session_state.current_page = 0
        
        # Perform search
        with st.spinner("🐷 Ploppy is searching..."):
            time.sleep(0.5)  # Small delay for effect
            results = search_contributions(
                query=search_query if search_query else None,
                filters=filters,
                limit=100,
                offset=0
            )
            st.session_state.search_results = results
    
    # Display results
    if st.session_state.search_results is not None:
        df = st.session_state.search_results
        
        if not df.empty:
            st.markdown(f"### 📋 Found {len(df):,} Contributions")
            
            # Dynamic visualizations
            viz_col1, viz_col2 = st.columns(2)
            
            with viz_col1:
                amount_chart = create_amount_distribution_chart(df)
                if amount_chart:
                    st.plotly_chart(amount_chart, use_container_width=True)
                
                party_chart = create_party_chart(df)
                if party_chart:
                    st.plotly_chart(party_chart, use_container_width=True)
            
            with viz_col2:
                timeline_chart = create_timeline_chart(df)
                if timeline_chart:
                    st.plotly_chart(timeline_chart, use_container_width=True)
            
            # Top contributors
            st.markdown("### 🏆 Top Contributors")
            top_chart = create_top_contributors_chart(df)
            if top_chart:
                st.plotly_chart(top_chart, use_container_width=True)
            
            # Data table
            st.markdown("### 📊 Contribution Details")
            
            # Format the dataframe for display
            display_df = df.copy()
            display_df['amount'] = display_df['amount'].apply(lambda x: f"${x:,.2f}")
            display_df['transaction_date'] = pd.to_datetime(display_df['transaction_date']).dt.strftime('%Y-%m-%d')
            
            # Select columns to display
            display_columns = ['transaction_date', 'contributor', 'recipient', 'amount', 
                             'office', 'party', 'borough', 'payment_method']
            
            # Display with custom styling
            st.dataframe(
                display_df[display_columns],
                use_container_width=True,
                height=600,
                column_config={
                    "transaction_date": st.column_config.TextColumn("Date"),
                    "contributor": st.column_config.TextColumn("Contributor"),
                    "recipient": st.column_config.TextColumn("Recipient"),
                    "amount": st.column_config.TextColumn("Amount"),
                    "office": st.column_config.TextColumn("Office"),
                    "party": st.column_config.TextColumn("Party"),
                    "borough": st.column_config.TextColumn("Borough"),
                    "payment_method": st.column_config.TextColumn("Payment")
                }
            )
            
            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv,
                file_name=f"ploppy_contributions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            # Fun empty state
            st.markdown("""
            <div style='text-align: center; padding: 3rem;'>
                <h1 style='font-size: 5rem;'>🐷</h1>
                <h3 style='color: var(--ploppy-pink);'>Oink! No contributions found.</h3>
                <p>Try adjusting your search or filters to find what you're looking for!</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        # Welcome state
        st.markdown("""
        <div style='text-align: center; padding: 2rem; background: white; border-radius: 20px; margin: 2rem 0;'>
            <h2 style='color: var(--ploppy-pink);'>Welcome to Ploppy! 🐷</h2>
            <p style='font-size: 1.2rem; color: #666;'>
                I'm your friendly guide to NYC campaign finance data.<br>
                Ask me anything or use the filters to explore contributions!
            </p>
            <br>
            <h4>Try these example searches:</h4>
            <ul style='text-align: left; display: inline-block;'>
                <li>"Show me the biggest donations from Brooklyn"</li>
                <li>"What contributions went to mayoral candidates?"</li>
                <li>"Find donations over $1000 from Manhattan"</li>
                <li>"Who contributed to City Council races?"</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    # Footer
    st.markdown("""
    <div style='text-align: center; margin-top: 3rem; padding: 2rem; color: #999;'>
        <p>Made with 💖 by Ploppy | Data from NYC Campaign Finance Board</p>
        <p style='font-size: 0.8rem;'>Named after Spider-Pig from The Simpsons Movie 🕷️🐷</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()