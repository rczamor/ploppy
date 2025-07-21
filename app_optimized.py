"""NYC Campaign Finance Board Data Explorer - Optimized Version."""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# Import custom modules
from src.database.db_manager_v2 import NYCCFBDatabase
from src.database.code_mappings import *
from src.utils.utils import format_currency
from src.ai.ai_search import ContributionAnalyzer, NaturalLanguageQueryProcessor

# Page configuration
st.set_page_config(
    page_title="NYC Campaign Finance Board Data Explorer",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database connection
@st.cache_resource
def init_database():
    """Initialize database connection."""
    try:
        db = NYCCFBDatabase()
        return db
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        raise

# Optimized database stats query
@st.cache_data(ttl=3600)
def load_database_stats():
    """Load database statistics."""
    db = init_database()
    return db.get_database_stats()

# Cache database stats in session state
def get_cached_stats():
    """Get cached database stats from session state."""
    if 'db_stats' not in st.session_state or st.session_state.get('stats_timestamp', 0) < datetime.now().timestamp() - 300:
        st.session_state.db_stats = load_database_stats()
        st.session_state.stats_timestamp = datetime.now().timestamp()
    return st.session_state.db_stats

# Data loading functions with proper data types
@st.cache_data(ttl=900)
def load_recent_contributions(limit=1000):
    """Load recent contributions from database."""
    db = init_database()
    query = """
        SELECT 
            c.transaction_date,
            c.amount,
            c.payment_method_desc,
            c.amount_category,
            contrib.last_name || CASE 
                WHEN contrib.first_name != '' THEN ', ' || contrib.first_name 
                ELSE '' 
            END as contributor_name,
            contrib.contributor_type,
            contrib.occupation,
            r.office_name,
            r.last_name || CASE 
                WHEN r.first_name != '' THEN ', ' || r.first_name 
                ELSE '' 
            END as recipient_name,
            r.canclass_description,
            r.party,
            l.city,
            l.state,
            l.borough_name,
            e.name as employer_name
        FROM contributions c
        JOIN contributors contrib ON c.contributor_id = contrib.id
        JOIN recipients r ON c.recipient_id = r.id
        LEFT JOIN locations l ON c.location_id = l.id
        LEFT JOIN employers e ON contrib.employer_id = e.id
        WHERE c.transaction_date IS NOT NULL
        ORDER BY c.transaction_date DESC
        LIMIT :limit
    """
    df = db.execute_query(query.replace(':limit', str(limit)))
    # Ensure numeric columns are properly typed
    if not df.empty:
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    return df

@st.cache_data(ttl=1800)
def load_top_contributors(limit=20):
    """Load top contributors by total amount."""
    db = init_database()
    query = """
        SELECT 
            contrib.last_name || CASE 
                WHEN contrib.first_name != '' THEN ', ' || contrib.first_name 
                ELSE '' 
            END as contributor_name,
            contrib.contributor_type,
            COUNT(DISTINCT c.id) as num_contributions,
            SUM(c.amount) as total_amount,
            COUNT(DISTINCT c.recipient_id) as num_recipients,
            AVG(c.amount) as avg_contribution
        FROM contributions c
        JOIN contributors contrib ON c.contributor_id = contrib.id
        GROUP BY contrib.id, contrib.last_name, contrib.first_name, contrib.contributor_type
        ORDER BY total_amount DESC
        LIMIT :limit
    """
    df = db.execute_query(query.replace(':limit', str(limit)))
    # Ensure numeric columns are properly typed
    if not df.empty:
        df['total_amount'] = pd.to_numeric(df['total_amount'], errors='coerce')
        df['num_contributions'] = pd.to_numeric(df['num_contributions'], errors='coerce')
        df['num_recipients'] = pd.to_numeric(df['num_recipients'], errors='coerce')
        df['avg_contribution'] = pd.to_numeric(df['avg_contribution'], errors='coerce')
    return df

@st.cache_data(ttl=1800)
def load_top_recipients(limit=20):
    """Load top recipients by total raised."""
    db = init_database()
    query = """
        SELECT 
            r.last_name || CASE 
                WHEN r.first_name != '' THEN ', ' || r.first_name 
                ELSE '' 
            END as recipient_name,
            r.office_name,
            r.canclass_description,
            r.party,
            COUNT(DISTINCT c.id) as num_contributions,
            SUM(c.amount) as total_raised,
            COUNT(DISTINCT c.contributor_id) as num_contributors,
            AVG(c.amount) as avg_contribution
        FROM contributions c
        JOIN recipients r ON c.recipient_id = r.id
        GROUP BY r.id, r.last_name, r.first_name, r.office_name, r.canclass_description, r.party
        ORDER BY total_raised DESC
        LIMIT :limit
    """
    df = db.execute_query(query.replace(':limit', str(limit)))
    # Ensure numeric columns are properly typed
    if not df.empty:
        df['total_raised'] = pd.to_numeric(df['total_raised'], errors='coerce')
        df['num_contributions'] = pd.to_numeric(df['num_contributions'], errors='coerce')
        df['num_contributors'] = pd.to_numeric(df['num_contributors'], errors='coerce')
        df['avg_contribution'] = pd.to_numeric(df['avg_contribution'], errors='coerce')
    return df

# Main app
def main():
    st.title("🏛️ NYC Campaign Finance Board Data Explorer")
    st.markdown("Explore political contributions data from the NYC Campaign Finance Board")
    
    # Initialize database connection only once
    try:
        if 'db_initialized' not in st.session_state:
            db = init_database()
            st.session_state.db_initialized = True
    except Exception as e:
        st.error(f"❌ Database connection failed: {e}")
        return
    
    # Sidebar with lazy loading
    with st.sidebar:
        st.header("Navigation")
        page = st.selectbox(
            "Select Page",
            ["Overview", "Contributors", "Recipients", "Contributions"]
        )
        
        # Only load stats if sidebar expander is opened
        with st.expander("Database Status", expanded=False):
            try:
                stats = get_cached_stats()
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Elections", f"{stats.get('elections_count', 0):,}")
                    st.metric("Contributors", f"{stats.get('contributors_count', 0):,}")
                    st.metric("Recipients", f"{stats.get('recipients_count', 0):,}")
                    st.metric("Contributions", f"{stats.get('contributions_count', 0):,}")
                with col2:
                    st.metric("Employers", f"{stats.get('employers_count', 0):,}")
                    st.metric("Locations", f"{stats.get('locations_count', 0):,}")
                    st.metric("Recent (30d)", f"{stats.get('recent_contributions', 0):,}")
            except Exception as e:
                st.error("Failed to load database statistics")
    
    # Page content
    if page == "Overview":
        show_overview_page()
    elif page == "Contributors":
        show_contributors_page()
    elif page == "Recipients":
        show_recipients_page()
    elif page == "Contributions":
        show_contributions_page()

def show_overview_page():
    """Show overview dashboard."""
    st.header("Campaign Finance Overview")
    st.info("Quick overview of the campaign finance data")
    
    # Simple metrics
    try:
        stats = get_cached_stats()
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Contributions", f"{stats.get('contributions_count', 0):,}")
        with col2:
            st.metric("Total Contributors", f"{stats.get('contributors_count', 0):,}")
        with col3:
            st.metric("Total Recipients", f"{stats.get('recipients_count', 0):,}")
        with col4:
            st.metric("Recent Activity (30d)", f"{stats.get('recent_contributions', 0):,}")
    except:
        st.error("Unable to load overview data")

def show_contributors_page():
    """Show contributors analysis."""
    st.header("Top Contributors Analysis")
    
    # Load data
    try:
        top_contributors = load_top_contributors(50)
        
        if not top_contributors.empty:
            # Top contributors chart
            st.subheader("Top Contributors by Total Amount")
            fig = px.bar(
                top_contributors.head(20),
                x='total_amount',
                y='contributor_name',
                orientation='h',
                title='Top 20 Contributors'
            )
            fig.update_layout(height=600, yaxis_title="", xaxis_title="Total Contributions ($)")
            st.plotly_chart(fig, use_container_width=True)
            
            # Detailed table
            st.subheader("Contributor Details")
            display_df = top_contributors.copy()
            display_df['total_amount'] = display_df['total_amount'].apply(format_currency)
            display_df['avg_contribution'] = display_df['avg_contribution'].apply(format_currency)
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("No contributor data available.")
    except Exception as e:
        st.error(f"Error loading contributor data: {e}")

def show_recipients_page():
    """Show recipients analysis."""
    st.header("Campaign Recipients Analysis")
    
    # Load data
    try:
        top_recipients = load_top_recipients(50)
        
        if not top_recipients.empty:
            # Top recipients chart
            st.subheader("Top Recipients by Total Raised")
            fig = px.bar(
                top_recipients.head(20),
                x='total_raised',
                y='recipient_name',
                color='office_name',
                orientation='h',
                title='Top 20 Campaign Recipients'
            )
            fig.update_layout(height=600, yaxis_title="", xaxis_title="Total Raised ($)")
            st.plotly_chart(fig, use_container_width=True)
            
            # Detailed table
            st.subheader("Recipient Details")
            display_df = top_recipients.copy()
            display_df['total_raised'] = display_df['total_raised'].apply(format_currency)
            display_df['avg_contribution'] = display_df['avg_contribution'].apply(format_currency)
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("No recipient data available.")
    except Exception as e:
        st.error(f"Error loading recipient data: {e}")

def show_contributions_page():
    """Show contributions analysis."""
    st.header("Recent Contributions")
    
    # Load recent contributions
    try:
        recent_contributions = load_recent_contributions(500)
        
        if not recent_contributions.empty:
            # Summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Displayed", f"{len(recent_contributions):,}")
            with col2:
                avg_amount = recent_contributions['amount'].mean()
                st.metric("Average Amount", format_currency(avg_amount))
            with col3:
                total_amount = recent_contributions['amount'].sum()
                st.metric("Total Amount", format_currency(total_amount))
            
            # Detailed table
            st.subheader("Recent Contribution Details")
            display_df = recent_contributions[['transaction_date', 'contributor_name', 'recipient_name', 'amount', 'city', 'state']].copy()
            display_df['amount'] = display_df['amount'].apply(format_currency)
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("No contribution data available.")
    except Exception as e:
        st.error(f"Error loading contribution data: {e}")

if __name__ == "__main__":
    main()