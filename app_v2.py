"""NYC Campaign Finance Board Data Explorer - Streamlit App."""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# Import custom modules
from db_manager_v2 import NYCCFBDatabase
from code_mappings import *
from utils import format_currency

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
    return NYCCFBDatabase()

# Load data from database
@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_database_stats():
    """Load database statistics."""
    db = init_database()
    return db.get_database_stats()

@st.cache_data(ttl=300)
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
    return db.execute_query(query.replace(':limit', str(limit)))

@st.cache_data(ttl=300)
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
    return db.execute_query(query.replace(':limit', str(limit)))

@st.cache_data(ttl=300)
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
    return db.execute_query(query.replace(':limit', str(limit)))

@st.cache_data(ttl=300)
def load_office_summary():
    """Load summary by office type."""
    db = init_database()
    query = """
        SELECT 
            r.office_name,
            COUNT(DISTINCT r.id) as num_candidates,
            COUNT(DISTINCT c.id) as num_contributions,
            SUM(c.amount) as total_raised,
            AVG(c.amount) as avg_contribution,
            MAX(c.amount) as max_contribution
        FROM contributions c
        JOIN recipients r ON c.recipient_id = r.id
        WHERE r.office_name IS NOT NULL
        GROUP BY r.office_name
        ORDER BY total_raised DESC
    """
    return db.execute_query(query)

# Main app
def main():
    st.title("🏛️ NYC Campaign Finance Board Data Explorer")
    st.markdown("Explore political contributions data from the NYC Campaign Finance Board")
    
    # Sidebar
    with st.sidebar:
        st.header("Navigation")
        page = st.selectbox(
            "Select Page",
            ["Overview", "Contributors", "Recipients", "Contributions", "Geographic Analysis", "Database Import"]
        )
        
        st.markdown("---")
        st.header("Database Status")
        stats = load_database_stats()
        
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
    
    # Page content
    if page == "Overview":
        show_overview_page()
    elif page == "Contributors":
        show_contributors_page()
    elif page == "Recipients":
        show_recipients_page()
    elif page == "Contributions":
        show_contributions_page()
    elif page == "Geographic Analysis":
        show_geographic_page()
    elif page == "Database Import":
        show_import_page()

def show_overview_page():
    """Show overview dashboard."""
    st.header("Campaign Finance Overview")
    
    # Load data
    office_summary = load_office_summary()
    
    if not office_summary.empty:
        # Office type summary
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Total Raised by Office")
            fig = px.bar(
                office_summary,
                x='office_name',
                y='total_raised',
                title='Total Contributions by Office Type'
            )
            fig.update_layout(xaxis_title="Office", yaxis_title="Total Amount ($)")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("Number of Candidates by Office")
            fig = px.pie(
                office_summary,
                values='num_candidates',
                names='office_name',
                title='Distribution of Candidates'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Summary metrics
        st.subheader("Key Metrics")
        col1, col2, col3, col4 = st.columns(4)
        
        total_raised = office_summary['total_raised'].sum()
        total_contributions = office_summary['num_contributions'].sum()
        total_candidates = office_summary['num_candidates'].sum()
        avg_contribution = total_raised / total_contributions if total_contributions > 0 else 0
        
        with col1:
            st.metric("Total Raised", format_currency(total_raised))
        with col2:
            st.metric("Total Contributions", f"{total_contributions:,}")
        with col3:
            st.metric("Total Candidates", f"{total_candidates:,}")
        with col4:
            st.metric("Avg Contribution", format_currency(avg_contribution))
        
        # Detailed table
        st.subheader("Office Summary Details")
        display_df = office_summary.copy()
        display_df['total_raised'] = display_df['total_raised'].apply(format_currency)
        display_df['avg_contribution'] = display_df['avg_contribution'].apply(format_currency)
        display_df['max_contribution'] = display_df['max_contribution'].apply(format_currency)
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No data available. Please import contribution data first.")

def show_contributors_page():
    """Show contributors analysis."""
    st.header("Top Contributors Analysis")
    
    # Load data
    top_contributors = load_top_contributors(50)
    
    if not top_contributors.empty:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            contributor_types = ['All'] + top_contributors['contributor_type'].unique().tolist()
            selected_type = st.selectbox("Filter by Type", contributor_types)
        
        # Apply filters
        if selected_type != 'All':
            filtered_df = top_contributors[top_contributors['contributor_type'] == selected_type]
        else:
            filtered_df = top_contributors
        
        # Top contributors chart
        st.subheader("Top Contributors by Total Amount")
        fig = px.bar(
            filtered_df.head(20),
            x='total_amount',
            y='contributor_name',
            orientation='h',
            title='Top 20 Contributors'
        )
        fig.update_layout(height=600, yaxis_title="", xaxis_title="Total Contributions ($)")
        st.plotly_chart(fig, use_container_width=True)
        
        # Contributor metrics
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Contribution Patterns")
            scatter_df = filtered_df[filtered_df['num_contributions'] > 1]
            fig = px.scatter(
                scatter_df,
                x='num_contributions',
                y='avg_contribution',
                size='total_amount',
                hover_data=['contributor_name'],
                title='Contribution Frequency vs Average Amount'
            )
            fig.update_layout(
                xaxis_title="Number of Contributions",
                yaxis_title="Average Contribution ($)"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("Contributor Types")
            type_summary = filtered_df.groupby('contributor_type').agg({
                'total_amount': 'sum',
                'contributor_name': 'count'
            }).reset_index()
            type_summary.columns = ['Type', 'Total Amount', 'Count']
            
            fig = px.pie(
                type_summary,
                values='Total Amount',
                names='Type',
                title='Contributions by Contributor Type'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Detailed table
        st.subheader("Contributor Details")
        display_df = filtered_df.copy()
        display_df['total_amount'] = display_df['total_amount'].apply(format_currency)
        display_df['avg_contribution'] = display_df['avg_contribution'].apply(format_currency)
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No contributor data available. Please import contribution data first.")

def show_recipients_page():
    """Show recipients analysis."""
    st.header("Campaign Recipients Analysis")
    
    # Load data
    top_recipients = load_top_recipients(50)
    
    if not top_recipients.empty:
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            offices = ['All'] + top_recipients['office_name'].dropna().unique().tolist()
            selected_office = st.selectbox("Filter by Office", offices)
        with col2:
            parties = ['All'] + top_recipients['party'].dropna().unique().tolist()
            selected_party = st.selectbox("Filter by Party", parties)
        with col3:
            participation = ['All'] + top_recipients['canclass_description'].dropna().unique().tolist()
            selected_participation = st.selectbox("Filter by Participation", participation)
        
        # Apply filters
        filtered_df = top_recipients.copy()
        if selected_office != 'All':
            filtered_df = filtered_df[filtered_df['office_name'] == selected_office]
        if selected_party != 'All':
            filtered_df = filtered_df[filtered_df['party'] == selected_party]
        if selected_participation != 'All':
            filtered_df = filtered_df[filtered_df['canclass_description'] == selected_participation]
        
        # Top recipients chart
        st.subheader("Top Recipients by Total Raised")
        fig = px.bar(
            filtered_df.head(20),
            x='total_raised',
            y='recipient_name',
            color='office_name',
            orientation='h',
            title='Top 20 Campaign Recipients'
        )
        fig.update_layout(height=600, yaxis_title="", xaxis_title="Total Raised ($)")
        st.plotly_chart(fig, use_container_width=True)
        
        # Recipient metrics
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Fundraising Efficiency")
            scatter_df = filtered_df[filtered_df['num_contributors'] > 10]
            fig = px.scatter(
                scatter_df,
                x='num_contributors',
                y='avg_contribution',
                size='total_raised',
                color='office_name',
                hover_data=['recipient_name'],
                title='Number of Contributors vs Average Contribution'
            )
            fig.update_layout(
                xaxis_title="Number of Contributors",
                yaxis_title="Average Contribution ($)"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("Party Distribution")
            party_summary = filtered_df.groupby('party').agg({
                'total_raised': 'sum',
                'recipient_name': 'count'
            }).reset_index()
            party_summary.columns = ['Party', 'Total Raised', 'Count']
            
            fig = px.pie(
                party_summary,
                values='Total Raised',
                names='Party',
                title='Total Raised by Party'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Detailed table
        st.subheader("Recipient Details")
        display_df = filtered_df.copy()
        display_df['total_raised'] = display_df['total_raised'].apply(format_currency)
        display_df['avg_contribution'] = display_df['avg_contribution'].apply(format_currency)
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No recipient data available. Please import contribution data first.")

def show_contributions_page():
    """Show contributions analysis."""
    st.header("Contribution Patterns Analysis")
    
    # Load recent contributions
    recent_contributions = load_recent_contributions(5000)
    
    if not recent_contributions.empty:
        # Date range filter
        col1, col2 = st.columns(2)
        with col1:
            min_date = recent_contributions['transaction_date'].min()
            max_date = recent_contributions['transaction_date'].max()
            date_range = st.date_input(
                "Select Date Range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
        
        # Apply date filter
        if len(date_range) == 2:
            filtered_df = recent_contributions[
                (recent_contributions['transaction_date'] >= pd.to_datetime(date_range[0])) &
                (recent_contributions['transaction_date'] <= pd.to_datetime(date_range[1]))
            ]
        else:
            filtered_df = recent_contributions
        
        # Time series analysis
        st.subheader("Contributions Over Time")
        daily_contributions = filtered_df.groupby(
            filtered_df['transaction_date'].dt.date
        )['amount'].agg(['sum', 'count']).reset_index()
        daily_contributions.columns = ['Date', 'Total Amount', 'Count']
        
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Daily Total Amount', 'Daily Number of Contributions'),
            shared_xaxes=True
        )
        
        fig.add_trace(
            go.Scatter(x=daily_contributions['Date'], y=daily_contributions['Total Amount'], name='Amount'),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=daily_contributions['Date'], y=daily_contributions['Count'], name='Count'),
            row=2, col=1
        )
        
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)
        
        # Amount distribution
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Contribution Amount Distribution")
            fig = px.histogram(
                filtered_df[filtered_df['amount'] <= 5000],  # Focus on smaller contributions
                x='amount',
                nbins=50,
                title='Distribution of Contributions (Up to $5,000)'
            )
            fig.update_layout(xaxis_title="Amount ($)", yaxis_title="Count")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("Payment Methods")
            payment_summary = filtered_df['payment_method_desc'].value_counts()
            fig = px.pie(
                values=payment_summary.values,
                names=payment_summary.index,
                title='Contributions by Payment Method'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Recent contributions table
        st.subheader("Recent Contributions")
        display_df = filtered_df[['transaction_date', 'contributor_name', 'recipient_name', 
                                  'office_name', 'amount', 'payment_method_desc']].head(100)
        display_df['amount'] = display_df['amount'].apply(format_currency)
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No contribution data available. Please import contribution data first.")

def show_geographic_page():
    """Show geographic analysis."""
    st.header("Geographic Analysis")
    
    # Load data with geographic information
    db = init_database()
    query = """
        SELECT 
            l.city,
            l.state,
            l.borough_name,
            l.region,
            COUNT(DISTINCT c.id) as num_contributions,
            SUM(c.amount) as total_amount,
            COUNT(DISTINCT c.contributor_id) as num_contributors,
            AVG(c.amount) as avg_contribution
        FROM contributions c
        JOIN locations l ON c.location_id = l.id
        WHERE l.city IS NOT NULL AND l.state IS NOT NULL
        GROUP BY l.city, l.state, l.borough_name, l.region
        ORDER BY total_amount DESC
        LIMIT 100
    """
    
    geo_data = db.execute_query(query)
    
    if not geo_data.empty:
        # NYC vs Outside NYC
        st.subheader("NYC vs Outside NYC Contributions")
        region_summary = geo_data.groupby('region').agg({
            'total_amount': 'sum',
            'num_contributions': 'sum',
            'num_contributors': 'sum'
        }).reset_index()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            fig = px.pie(
                region_summary,
                values='total_amount',
                names='region',
                title='Total Amount by Region'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = px.pie(
                region_summary,
                values='num_contributions',
                names='region',
                title='Number of Contributions by Region'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col3:
            fig = px.pie(
                region_summary,
                values='num_contributors',
                names='region',
                title='Number of Contributors by Region'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Borough analysis (NYC only)
        st.subheader("NYC Borough Analysis")
        nyc_data = geo_data[geo_data['region'] == 'NYC']
        borough_summary = nyc_data.groupby('borough_name').agg({
            'total_amount': 'sum',
            'num_contributions': 'sum',
            'avg_contribution': 'mean'
        }).reset_index()
        
        if not borough_summary.empty:
            fig = px.bar(
                borough_summary,
                x='borough_name',
                y='total_amount',
                title='Total Contributions by NYC Borough'
            )
            fig.update_layout(xaxis_title="Borough", yaxis_title="Total Amount ($)")
            st.plotly_chart(fig, use_container_width=True)
        
        # Top cities
        st.subheader("Top Contributing Cities")
        top_cities = geo_data.nlargest(20, 'total_amount')
        
        fig = px.bar(
            top_cities,
            x='total_amount',
            y='city',
            orientation='h',
            color='state',
            title='Top 20 Cities by Total Contributions'
        )
        fig.update_layout(height=600, yaxis_title="", xaxis_title="Total Amount ($)")
        st.plotly_chart(fig, use_container_width=True)
        
        # State summary
        st.subheader("State Summary")
        state_summary = geo_data.groupby('state').agg({
            'total_amount': 'sum',
            'num_contributions': 'sum',
            'num_contributors': 'sum',
            'city': 'count'
        }).reset_index()
        state_summary.columns = ['State', 'Total Amount', 'Contributions', 'Contributors', 'Cities']
        state_summary = state_summary.sort_values('Total Amount', ascending=False)
        
        display_df = state_summary.copy()
        display_df['Total Amount'] = display_df['Total Amount'].apply(format_currency)
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No geographic data available. Please import contribution data first.")

def show_import_page():
    """Show data import page."""
    st.header("Database Import Management")
    
    db = init_database()
    stats = load_database_stats()
    
    # Current status
    st.subheader("Current Database Status")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Records", f"{stats.get('contributions_count', 0):,}")
    with col2:
        st.metric("Contributors", f"{stats.get('contributors_count', 0):,}")
    with col3:
        st.metric("Recipients", f"{stats.get('recipients_count', 0):,}")
    with col4:
        st.metric("Elections", f"{stats.get('elections_count', 0):,}")
    
    # Import controls
    st.subheader("Import Controls")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Check Object Storage"):
            with st.spinner("Checking object storage..."):
                try:
                    if db.connect_to_object_storage(''):
                        st.success("Connected to object storage successfully!")
                        # List files
                        from replit.object_storage import Client
                        client = Client()
                        files = client.list()
                        st.write("Available files:")
                        for file in files:
                            st.write(f"- {file}")
                    else:
                        st.error("Failed to connect to object storage")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    with col2:
        if st.button("View Recent Import Errors"):
            query = """
                SELECT DISTINCT 
                    created_at::date as import_date,
                    COUNT(*) as records_imported
                FROM contributions
                GROUP BY created_at::date
                ORDER BY import_date DESC
                LIMIT 10
            """
            try:
                recent_imports = db.execute_query(query)
                if not recent_imports.empty:
                    st.write("Recent import activity:")
                    st.dataframe(recent_imports)
                else:
                    st.info("No recent imports found")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    # Manual query interface
    st.subheader("Database Query Interface")
    
    query_text = st.text_area(
        "Enter SQL Query",
        value="SELECT * FROM contributions LIMIT 10",
        height=100
    )
    
    if st.button("Execute Query"):
        with st.spinner("Executing query..."):
            try:
                result = db.execute_query(query_text)
                st.success(f"Query returned {len(result)} rows")
                st.dataframe(result)
            except Exception as e:
                st.error(f"Query error: {str(e)}")
    
    # Data quality report
    st.subheader("Data Quality Report")
    
    if st.button("Generate Quality Report"):
        with st.spinner("Generating report..."):
            try:
                # Check for missing names
                query1 = """
                    SELECT 
                        'Contributors with missing names' as issue,
                        COUNT(*) as count
                    FROM contributors
                    WHERE full_name IS NULL OR full_name = ''
                    UNION ALL
                    SELECT 
                        'Recipients with missing names' as issue,
                        COUNT(*) as count
                    FROM recipients
                    WHERE full_name IS NULL OR full_name = ''
                    UNION ALL
                    SELECT 
                        'Contributions with zero amount' as issue,
                        COUNT(*) as count
                    FROM contributions
                    WHERE amount = 0
                    UNION ALL
                    SELECT 
                        'Contributions without dates' as issue,
                        COUNT(*) as count
                    FROM contributions
                    WHERE transaction_date IS NULL
                """
                
                quality_report = db.execute_query(query1)
                st.dataframe(quality_report)
                
            except Exception as e:
                st.error(f"Error generating report: {str(e)}")

if __name__ == "__main__":
    main()