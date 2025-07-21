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
    print("Initializing database connection...")
    try:
        db = NYCCFBDatabase()
        print("Database connection successful!")
        return db
    except Exception as e:
        print(f"Database connection failed: {e}")
        st.error(f"Failed to connect to database: {e}")
        raise

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
    print("Starting main function...")
    st.title("🏛️ NYC Campaign Finance Board Data Explorer")
    st.markdown("Explore political contributions data from the NYC Campaign Finance Board")
    
    # Add a simple test to see if the app is rendering
    st.success("✅ App is loading successfully!")
    
    # Test if database connection works
    try:
        db = init_database()
        st.info("✅ Database connection established")
    except Exception as e:
        st.error(f"❌ Database connection failed: {e}")
        return
    
    print("App title displayed, checking import progress...")
    # Show import progress if available
    if os.path.exists('logs/import_progress.txt'):
        with open('logs/import_progress.txt', 'r') as f:
            progress_info = f.read()
        
        progress_container = st.container()
        with progress_container:
            with st.expander("📊 Background Import Progress", expanded=True):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.code(progress_info)
                with col2:
                    st.info("🔄 Import running in background")
                with col3:
                    if st.button("🔄 Refresh"):
                        st.rerun()
    
    # Sidebar
    with st.sidebar:
        st.header("Navigation")
        page = st.selectbox(
            "Select Page",
            ["Overview", "Contributors", "Recipients", "Contributions", "Geographic Analysis", "AI Analysis", "Natural Language Search", "Graph Network Analysis", "Database Import"]
        )
        
        st.markdown("---")
        st.header("Database Status")
        print("Loading database stats...")
        try:
            stats = load_database_stats()
            print(f"Database stats loaded: {stats}")
        except Exception as e:
            print(f"Error loading database stats: {e}")
            st.error("Failed to load database statistics")
            stats = {}
        
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
    elif page == "AI Analysis":
        show_ai_analysis_page()
    elif page == "Natural Language Search":
        show_natural_language_search_page()
    elif page == "Graph Network Analysis":
        show_graph_network_page()
    elif page == "Database Import":
        show_import_page()

def show_overview_page():
    """Show overview dashboard."""
    st.header("Campaign Finance Overview")
    
    # Load data
    try:
        office_summary = load_office_summary()
        print(f"Office summary type: {type(office_summary)}, empty: {office_summary.empty if hasattr(office_summary, 'empty') else 'N/A'}")
    except Exception as e:
        print(f"Error loading office summary: {e}")
        st.error(f"Error loading data: {e}")
        office_summary = pd.DataFrame()
    
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

def show_graph_network_page():
    """Show graph network analysis page."""
    st.header("🔗 Graph Network Analysis")
    st.write("Explore political contribution networks using natural language queries")
    
    # Import graph modules
    try:
        from graph_nlp_query import GraphNLPQuery
        nlp_query = GraphNLPQuery()
    except Exception as e:
        st.error(f"Failed to load graph query system: {str(e)}")
        return
    
    # Query interface
    st.subheader("Natural Language Graph Queries")
    
    # Show example queries
    with st.expander("📝 Example Queries", expanded=True):
        examples = nlp_query.suggest_queries()
        cols = st.columns(2)
        for i, query in enumerate(examples):
            cols[i % 2].markdown(f"• {query}")
    
    # Query input
    user_query = st.text_input(
        "Enter your query:",
        placeholder="e.g., Show me the network of Bloomberg",
        help="Ask questions about contributor networks, money flows, influence patterns, etc."
    )
    
    if st.button("🔍 Search", type="primary") or user_query:
        if user_query:
            with st.spinner("Analyzing graph network..."):
                result = nlp_query.execute_query(user_query)
                
                if 'error' in result:
                    st.error(result['error'])
                else:
                    # Display results based on type
                    if 'type' in result and result['type'].startswith('top_'):
                        # Top queries results
                        st.subheader(f"Results: {result['type'].replace('_', ' ').title()}")
                        
                        if 'results' in result:
                            for i, item in enumerate(result['results'][:20], 1):
                                with st.container():
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.write(f"**{i}. {item['name']}**")
                                    with col2:
                                        if 'total_given' in item:
                                            st.metric("Total Given", f"${item['total_given']:,.0f}")
                                        elif 'total_received' in item:
                                            st.metric("Total Received", f"${item['total_received']:,.0f}")
                                        elif 'total_bundled' in item:
                                            st.metric("Total Bundled", f"${item['total_bundled']:,.0f}")
                    
                    elif 'patterns' in result:
                        # Pattern detection results
                        st.subheader("Detected Patterns")
                        
                        pattern_types = {}
                        for pattern in result['patterns']:
                            p_type = pattern['pattern_type']
                            if p_type not in pattern_types:
                                pattern_types[p_type] = []
                            pattern_types[p_type].append(pattern)
                        
                        for p_type, patterns in pattern_types.items():
                            st.write(f"**{p_type.replace('_', ' ').title()}** ({len(patterns)} found)")
                            
                            for pattern in patterns[:5]:
                                with st.expander(f"{pattern.get('contributor', pattern.get('bundler', pattern.get('recipient', 'Pattern')))}"):
                                    for key, value in pattern.items():
                                        if key != 'pattern_type':
                                            st.write(f"**{key.replace('_', ' ').title()}:** {value}")
                    
                    elif 'influence_metrics' in result:
                        # Influence analysis results
                        st.subheader(f"Influence Analysis: {result['entity']}")
                        
                        metrics = result['influence_metrics']
                        cols = st.columns(len(metrics))
                        for i, (key, value) in enumerate(metrics.items()):
                            with cols[i % len(cols)]:
                                if isinstance(value, (int, float)):
                                    if 'amount' in key or 'given' in key or 'received' in key or 'spent' in key:
                                        st.metric(key.replace('_', ' ').title(), f"${value:,.0f}")
                                    elif 'rate' in key:
                                        st.metric(key.replace('_', ' ').title(), f"{value:.1%}")
                                    else:
                                        st.metric(key.replace('_', ' ').title(), f"{value:,.0f}")
                        
                        if 'connected_entities' in result:
                            st.write("**Connected Entities:**")
                            for entity in result['connected_entities'][:10]:
                                st.write(f"• {entity['name']} - ${entity['amount']:,.0f} ({entity['transactions']} transactions)")
                    
                    elif 'nodes' in result and 'edges' in result:
                        # Network visualization results
                        st.subheader(f"Network: {result.get('center', {}).get('name', 'Entity')}")
                        
                        # Show stats if available
                        if 'stats' in result:
                            cols = st.columns(4)
                            for i, (key, value) in enumerate(result['stats'].items()):
                                with cols[i % 4]:
                                    if 'amount' in key:
                                        st.metric(key.replace('_', ' ').title(), f"${value:,.0f}")
                                    else:
                                        st.metric(key.replace('_', ' ').title(), f"{value:,}")
                        
                        # Show network info
                        st.write(f"**Network contains {len(result['nodes'])} nodes and {len(result['edges'])} connections**")
                        
                        # List nodes by type
                        node_types = {}
                        for node in result['nodes']:
                            n_type = node.get('type', 'unknown')
                            if n_type not in node_types:
                                node_types[n_type] = []
                            node_types[n_type].append(node)
                        
                        for n_type, nodes in node_types.items():
                            with st.expander(f"{n_type.title()}s ({len(nodes)})"):
                                for node in nodes[:20]:
                                    st.write(f"• **{node['name']}**")
                    
                    else:
                        # Generic results display
                        st.json(result)
    
    # Network statistics
    st.divider()
    st.subheader("📊 Network Statistics")
    
    try:
        from graph_analysis import PoliticalFinanceGraph
        with PoliticalFinanceGraph() as graph:
            stats = graph.get_network_statistics()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Contributors", f"{stats.get('num_contributors', 0):,}")
                st.metric("Active Contributors", f"{stats.get('active_contributors', 0):,}")
            with col2:
                st.metric("Total Recipients", f"{stats.get('num_recipients', 0):,}")
                st.metric("Active Recipients", f"{stats.get('active_recipients', 0):,}")
            with col3:
                st.metric("Total Intermediaries", f"{stats.get('num_intermediaries', 0):,}")
                st.metric("Active Intermediaries", f"{stats.get('active_intermediaries', 0):,}")
            
            col4, col5 = st.columns(2)
            with col4:
                st.metric("Contribution Edges", f"{stats.get('num_contributions', 0):,}")
                st.metric("Total Contributions", f"${stats.get('total_contributions', 0):,.0f}")
            with col5:
                st.metric("Expenditure Edges", f"{stats.get('num_expenditures', 0):,}")
                st.metric("Total Expenditures", f"${stats.get('total_expenditures', 0):,.0f}")
            
            if stats.get('avg_contributor_degree'):
                st.info(f"Average contributor connects to {stats['avg_contributor_degree']:.1f} recipients")
    
    except Exception as e:
        st.error(f"Failed to load network statistics: {str(e)}")

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

def show_ai_analysis_page():
    """Show AI-powered analysis page."""
    st.header("🤖 AI-Powered Analysis")
    
    # Initialize analyzer
    analyzer = ContributionAnalyzer()
    
    # Analysis options
    analysis_type = st.selectbox(
        "Select Analysis Type",
        ["Contribution Patterns", "Donor Networks", "Duplicate Detection", "Semantic Search", 
         "Advanced Clustering", "Topic Analysis", "Time Series Forecasting", "Entity Extraction", 
         "Model Training & Fine-tuning"]
    )
    
    if analysis_type == "Contribution Patterns":
        st.subheader("ML-Based Contribution Pattern Analysis")
        
        if st.button("Analyze Patterns"):
            with st.spinner("Analyzing contribution patterns..."):
                patterns = analyzer.analyze_contribution_patterns()
                
                if patterns:
                    # Display metrics
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Contributions", f"{patterns['total_contributions']:,}")
                    with col2:
                        st.metric("Anomalous Contributions", f"{patterns['anomalous_contributions']:,}")
                    with col3:
                        st.metric("Anomaly Rate", f"{patterns['anomaly_percentage']:.1f}%")
                    with col4:
                        st.metric("Pattern Clusters", f"{patterns['num_clusters']:,}")
                    
                    # Contribution statistics
                    st.subheader("Contribution Statistics")
                    stats = patterns['contribution_stats']
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Mean Amount", format_currency(stats['mean_amount']))
                    with col2:
                        st.metric("Median Amount", format_currency(stats['median_amount']))
                    with col3:
                        st.metric("Std Deviation", format_currency(stats['std_amount']))
                    with col4:
                        st.metric("Total Amount", format_currency(stats['total_amount']))
                    
                    # Top anomalies
                    if patterns['top_anomalies']:
                        st.subheader("Top Anomalous Contributions")
                        anomaly_df = pd.DataFrame(patterns['top_anomalies'])
                        anomaly_df['amount'] = anomaly_df['amount'].apply(format_currency)
                        st.dataframe(anomaly_df)
                else:
                    st.warning("No patterns found in the data")
    
    elif analysis_type == "Donor Networks":
        st.subheader("Donor Network Analysis")
        
        if st.button("Analyze Networks"):
            with st.spinner("Analyzing donor networks..."):
                networks = analyzer.analyze_donor_networks()
                
                if not networks.empty:
                    st.write(f"Found {len(networks)} donor pairs with shared contribution patterns")
                    
                    # Display network connections
                    display_df = networks.copy()
                    display_df = display_df[['donor1_name', 'donor2_name', 'shared_recipients', 
                                           'donor1_type', 'donor2_type']]
                    st.dataframe(display_df)
                    
                    # Network visualization placeholder
                    st.info("Network visualization would show connections between donors who contribute to the same recipients")
                else:
                    st.info("No significant donor networks found in current data")
    
    elif analysis_type == "Duplicate Detection":
        st.subheader("Duplicate Contributor Detection")
        
        threshold = st.slider("Similarity Threshold", 0.7, 1.0, 0.85, 0.05)
        
        if st.button("Find Duplicates"):
            with st.spinner("Searching for duplicate contributors..."):
                analyzer.build_contributor_index()
                duplicates = analyzer.detect_duplicate_contributors(threshold)
                
                if duplicates:
                    st.write(f"Found {len(duplicates)} potential duplicate pairs")
                    
                    for i, dup in enumerate(duplicates[:10]):  # Show top 10
                        st.write(f"**Pair {i+1}** (Similarity: {dup['similarity']:.2%})")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("Contributor 1:")
                            st.write(f"- Name: {dup['contributor1']['full_name']}")
                            st.write(f"- Type: {dup['contributor1']['contributor_type']}")
                            st.write(f"- Total: {format_currency(dup['contributor1']['total_amount'])}")
                        
                        with col2:
                            st.write("Contributor 2:")
                            st.write(f"- Name: {dup['contributor2']['full_name']}")
                            st.write(f"- Type: {dup['contributor2']['contributor_type']}")
                            st.write(f"- Total: {format_currency(dup['contributor2']['total_amount'])}")
                        
                        st.markdown("---")
                else:
                    st.info("No duplicate contributors found at this threshold")
    
    elif analysis_type == "Semantic Search":
        st.subheader("Semantic Contributor Search")
        
        # Show which model is being used
        try:
            from ai_search import MODERN_SEARCH_AVAILABLE
            if MODERN_SEARCH_AVAILABLE:
                st.success("🚀 Using sentence-transformers (all-MiniLM-L6-v2) for modern semantic search")
            else:
                st.info("📊 Using ensemble embeddings (TF-IDF + LDA + NMF)")
        except:
            pass
        
        search_query = st.text_input("Search contributors by name, occupation, employer, or location")
        
        if search_query:
            with st.spinner("Searching..."):
                results = analyzer.semantic_search_contributors(search_query, top_k=20)
                
                if not results.empty:
                    st.write(f"Found {len(results)} matching contributors")
                    
                    # Check which columns are available
                    display_cols = []
                    for col in ['full_name', 'contributor_type', 'occupation', 
                               'employer_name', 'city', 'state', 'total_amount', 
                               'similarity_score']:
                        if col in results.columns:
                            display_cols.append(col)
                    
                    display_df = results[display_cols].copy()
                    
                    # Format currency columns
                    if 'total_amount' in display_df.columns:
                        display_df['total_amount'] = display_df['total_amount'].apply(
                            lambda x: format_currency(x) if pd.notna(x) else '$0'
                        )
                    
                    # Format similarity score
                    if 'similarity_score' in display_df.columns:
                        display_df['similarity_score'] = display_df['similarity_score'].apply(
                            lambda x: f"{x:.1%}"
                        )
                    
                    st.dataframe(display_df)
                else:
                    st.info("No matching contributors found")
        
        # Show available AI models
        st.sidebar.markdown("---")
        st.sidebar.subheader("Available AI Models")
        
        # Check for sentence-transformers
        try:
            import subprocess
            result = subprocess.run([
                "python3.10", "-c", 
                "import sys; sys.path.insert(0, '/home/runner/.pythonlibs/lib/python3.10/site-packages'); from sentence_transformers import SentenceTransformer; print('available')"
            ], capture_output=True, text=True)
            
            if result.returncode == 0 and "available" in result.stdout:
                st.sidebar.success("✓ Sentence-Transformers (Modern)")
                st.sidebar.info("Using all-MiniLM-L6-v2 model")
            else:
                st.sidebar.warning("⚠ Sentence-Transformers unavailable")
        except:
            pass
        
        # Always available models
        st.sidebar.success("✓ Gensim (Word2Vec, Doc2Vec)")
        st.sidebar.success("✓ Scikit-learn (TF-IDF, LDA, NMF)")
    
    elif analysis_type == "Advanced Clustering":
        st.subheader("Advanced Contributor Clustering")
        st.info("Using matrix factorization and topic modeling to group similar contributors")
        
        if st.button("Perform Advanced Clustering"):
            with st.spinner("Building advanced embeddings and clustering..."):
                try:
                    from ai_embeddings import AdvancedEmbeddings
                    embedder = AdvancedEmbeddings()
                    embedder.build_contributor_embeddings()
                    
                    if embedder.documents is not None and not embedder.documents.empty:
                        # Perform clustering
                        clustered_data, cluster_analysis = embedder.cluster_contributors()
                        
                        # Display cluster analysis
                        st.write("### Cluster Analysis")
                        for _, cluster in cluster_analysis.iterrows():
                            with st.expander(f"Cluster {int(cluster['cluster_id'])} ({int(cluster['size'])} contributors)"):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric("Average Contribution", format_currency(cluster['avg_contribution']))
                                    st.metric("Total Contributions", format_currency(cluster['total_contributions']))
                                with col2:
                                    st.write("**Contributor Types:**")
                                    for ctype, count in cluster['contributor_types'].items():
                                        st.write(f"- {ctype}: {count}")
                                
                                st.write("**Top Occupations:**")
                                for occ, count in cluster['top_occupations'].items():
                                    if pd.notna(occ):
                                        st.write(f"- {occ}: {count}")
                        
                        # Show sample contributors from each cluster
                        selected_cluster = st.selectbox(
                            "Select a cluster to view contributors:",
                            options=cluster_analysis['cluster_id'].tolist(),
                            format_func=lambda x: f"Cluster {x} ({len(clustered_data[clustered_data['cluster'] == x])} members)"
                        )
                        
                        cluster_members = clustered_data[clustered_data['cluster'] == selected_cluster]
                        st.write(f"### Sample Contributors from Cluster {selected_cluster}")
                        display_cols = ['full_name', 'contributor_type', 'occupation', 'total_amount', 'num_contributions']
                        display_df = cluster_members[display_cols].head(20).copy()
                        display_df['total_amount'] = display_df['total_amount'].apply(
                            lambda x: format_currency(x) if pd.notna(x) else '$0'
                        )
                        st.dataframe(display_df)
                    else:
                        st.warning("No contributor data available for clustering")
                        
                except Exception as e:
                    st.error(f"Error performing clustering: {str(e)}")
    
    elif analysis_type == "Topic Analysis":
        st.subheader("Contribution Topic Analysis")
        st.info("Extracting key themes and topics from contribution data")
        
        if st.button("Extract Topics"):
            with st.spinner("Analyzing topics..."):
                try:
                    from ai_embeddings import AdvancedEmbeddings
                    embedder = AdvancedEmbeddings()
                    embedder.build_contributor_embeddings()
                    
                    if embedder.lda_model is not None:
                        # Get topic keywords
                        topics = embedder.get_topic_keywords(n_topics=10, n_words=8)
                        
                        st.write("### Discovered Topics")
                        for topic_id, keywords in topics.items():
                            st.write(f"**Topic {topic_id + 1}:** {', '.join(keywords)}")
                        
                        # Get key phrases
                        key_phrases = embedder.extract_key_phrases(n_phrases=20)
                        
                        st.write("### Key Phrases in Dataset")
                        phrases_df = pd.DataFrame(key_phrases, columns=['Phrase', 'Importance'])
                        phrases_df['Importance'] = phrases_df['Importance'].apply(lambda x: f"{x:.3f}")
                        st.dataframe(phrases_df)
                        
                    else:
                        st.warning("Building topic model...")
                        
                except Exception as e:
                    st.error(f"Error analyzing topics: {str(e)}")
    
    elif analysis_type == "Time Series Forecasting":
        st.subheader("Contribution Time Series Forecasting")
        st.info("Predict future contribution patterns using machine learning")
        
        forecast_type = st.radio(
            "Forecast Type",
            ["Election-wide Trends", "Candidate-specific", "Custom Entity"]
        )
        
        if forecast_type == "Election-wide Trends":
            if st.button("Generate Forecast"):
                with st.spinner("Analyzing historical trends..."):
                    try:
                        # Prepare time series data
                        ts_data = analyzer.forecaster.prepare_time_series_data(
                            entity_type='election', frequency='D'
                        )
                        
                        if not ts_data.empty and len(ts_data) > 60:
                            # Analyze trends
                            trends = analyzer.forecaster.analyze_trends(ts_data)
                            
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Trend Direction", trends['trend_direction'].title())
                            with col2:
                                st.metric("Total Growth", f"{trends['total_growth_pct']:.1f}%")
                            with col3:
                                st.metric("Momentum", f"{trends['momentum']:.2%}")
                            with col4:
                                st.metric("Volatility", f"{trends['volatility']:.2%}")
                            
                            # Train forecast model
                            model_info = analyzer.forecaster.train_forecast_model(ts_data)
                            
                            st.write("### Model Performance")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("Training R²", f"{model_info['train_r2']:.3f}")
                            with col2:
                                st.metric("Test R²", f"{model_info['test_r2']:.3f}")
                            
                            # Generate forecast
                            forecast_days = st.slider("Days to Forecast", 7, 90, 30)
                            forecast = analyzer.forecaster.forecast_future(
                                ts_data, model_info, days_ahead=forecast_days
                            )
                            
                            # Plot results
                            import plotly.graph_objects as go
                            
                            fig = go.Figure()
                            
                            # Historical data
                            fig.add_trace(go.Scatter(
                                x=ts_data.index,
                                y=ts_data['total_amount'],
                                mode='lines',
                                name='Historical',
                                line=dict(color='blue')
                            ))
                            
                            # Forecast
                            fig.add_trace(go.Scatter(
                                x=forecast['date'],
                                y=forecast['forecast'],
                                mode='lines',
                                name='Forecast',
                                line=dict(color='red', dash='dash')
                            ))
                            
                            # Confidence intervals
                            fig.add_trace(go.Scatter(
                                x=forecast['date'],
                                y=forecast['forecast_upper'],
                                fill=None,
                                mode='lines',
                                line_color='rgba(255,0,0,0)',
                                showlegend=False
                            ))
                            
                            fig.add_trace(go.Scatter(
                                x=forecast['date'],
                                y=forecast['forecast_lower'],
                                fill='tonexty',
                                mode='lines',
                                line_color='rgba(255,0,0,0)',
                                name='Confidence Interval'
                            ))
                            
                            fig.update_layout(
                                title="Contribution Forecast",
                                xaxis_title="Date",
                                yaxis_title="Total Contributions ($)",
                                hovermode='x unified'
                            )
                            
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Seasonality analysis
                            seasonality = analyzer.forecaster.detect_seasonality(ts_data)
                            st.write("### Seasonality Analysis")
                            st.write(f"Strongest seasonality: **{seasonality['strongest_seasonality']}**")
                            
                        else:
                            st.warning("Not enough historical data for forecasting (need at least 60 days)")
                            
                    except Exception as e:
                        st.error(f"Error generating forecast: {str(e)}")
        
        elif forecast_type == "Candidate-specific":
            # Get list of candidates
            candidates = db_manager.get_all_recipients()
            if not candidates.empty:
                candidate_options = candidates.apply(
                    lambda x: f"{x['last_name']}, {x['first_name']} - {x['office_sought']}", 
                    axis=1
                ).tolist()
                
                selected_candidate = st.selectbox(
                    "Select Candidate",
                    options=range(len(candidates)),
                    format_func=lambda x: candidate_options[x]
                )
                
                if st.button("Generate Candidate Forecast"):
                    with st.spinner("Analyzing candidate contribution trends..."):
                        try:
                            candidate_id = candidates.iloc[selected_candidate]['id']
                            
                            # Prepare time series data
                            ts_data = analyzer.forecaster.prepare_time_series_data(
                                entity_type='candidate', 
                                entity_id=candidate_id,
                                frequency='D'
                            )
                            
                            if not ts_data.empty and len(ts_data) > 30:
                                # Train and forecast
                                model_info = analyzer.forecaster.train_forecast_model(ts_data)
                                forecast = analyzer.forecaster.forecast_future(
                                    ts_data, model_info, days_ahead=30
                                )
                                
                                # Display forecast summary
                                st.write("### 30-Day Forecast Summary")
                                total_forecast = forecast['forecast'].sum()
                                avg_daily = forecast['forecast'].mean()
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric("Expected Total (30 days)", format_currency(total_forecast))
                                with col2:
                                    st.metric("Average Daily", format_currency(avg_daily))
                                
                            else:
                                st.warning("Not enough data for this candidate")
                                
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
    
    elif analysis_type == "Entity Extraction":
        st.subheader("Entity Extraction & Analysis")
        st.info("Extract and analyze entities from contribution data")
        
        extraction_type = st.selectbox(
            "Extraction Type",
            ["Key Entities Overview", "Entity Search", "Entity Networks", "Text Analysis"]
        )
        
        if extraction_type == "Key Entities Overview":
            if st.button("Extract Key Entities"):
                with st.spinner("Extracting key entities..."):
                    try:
                        entities = analyzer.entity_extractor.extract_key_entities_from_dataset(limit=50)
                        
                        # Display top individuals
                        st.write("### Top Individual Contributors")
                        individuals_df = entities['top_individuals'][['full_name', 'occupation', 
                                                                     'employer', 'total_amount', 
                                                                     'num_recipients']].copy()
                        individuals_df['total_amount'] = individuals_df['total_amount'].apply(format_currency)
                        st.dataframe(individuals_df)
                        
                        # Display top organizations
                        st.write("### Top Organizational Contributors")
                        orgs_df = entities['top_organizations'][['full_name', 'contributor_type', 
                                                                'total_amount', 'num_recipients']].copy()
                        orgs_df['total_amount'] = orgs_df['total_amount'].apply(format_currency)
                        st.dataframe(orgs_df)
                        
                        # Display most connected
                        st.write("### Most Connected Contributors")
                        connected_df = entities['most_connected'][['full_name', 'num_recipients', 
                                                                  'total_amount']].head(20).copy()
                        connected_df['total_amount'] = connected_df['total_amount'].apply(format_currency)
                        st.dataframe(connected_df)
                        
                    except Exception as e:
                        st.error(f"Error extracting entities: {str(e)}")
        
        elif extraction_type == "Entity Search":
            entity_name = st.text_input("Enter entity name to search:")
            entity_type = st.radio("Entity Type", ["all", "contributor", "recipient"])
            
            if entity_name and st.button("Search Entity"):
                with st.spinner("Searching..."):
                    try:
                        results = analyzer.entity_extractor.find_related_entities(
                            entity_name, entity_type
                        )
                        
                        if not results.empty:
                            st.write(f"Found {len(results)} matching entities")
                            display_df = results.copy()
                            if 'total_amount' in display_df.columns:
                                display_df['total_amount'] = display_df['total_amount'].apply(format_currency)
                            st.dataframe(display_df)
                        else:
                            st.info("No matching entities found")
                            
                    except Exception as e:
                        st.error(f"Error searching entities: {str(e)}")
        
        elif extraction_type == "Entity Networks":
            network_type = st.radio("Network Type", ["contributor", "recipient"])
            min_connections = st.slider("Minimum Shared Connections", 1, 20, 5)
            
            if st.button("Build Network"):
                with st.spinner("Building entity network..."):
                    try:
                        network_data = analyzer.entity_extractor.create_entity_network(
                            entity_type=network_type,
                            min_connections=min_connections
                        )
                        
                        if network_data['num_connections'] > 0:
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Total Entities", network_data['num_entities'])
                            with col2:
                                st.metric("Total Connections", network_data['num_connections'])
                            with col3:
                                st.metric("Avg Connections", f"{network_data['avg_connections']:.1f}")
                            
                            st.write("### Most Connected Entities")
                            top_connected = pd.DataFrame(
                                list(network_data['top_connected'].items()),
                                columns=['Entity', 'Connections']
                            )
                            st.dataframe(top_connected)
                            
                            st.write("### Sample Network Connections")
                            st.dataframe(network_data['network'].head(20))
                        else:
                            st.info("No connections found with the specified criteria")
                            
                    except Exception as e:
                        st.error(f"Error building network: {str(e)}")
        
        elif extraction_type == "Text Analysis":
            sample_text = st.text_area(
                "Enter text to analyze:",
                placeholder="Paste contribution description, donor info, or any text to extract entities..."
            )
            
            if sample_text and st.button("Extract Entities"):
                try:
                    entities = analyzer.entity_extractor.extract_entities_from_text(sample_text)
                    
                    st.write("### Extracted Entities")
                    for entity_type, entity_list in entities.items():
                        if entity_list:
                            st.write(f"**{entity_type.title()}:** {', '.join(entity_list)}")
                    
                    # Classify if it looks like a contributor name
                    if any(word in sample_text.lower() for word in ['llc', 'inc', 'corp', 'pac']):
                        classification = analyzer.entity_extractor.classify_contributor_type(sample_text)
                        st.write(f"**Contributor Classification:** {classification}")
                        
                except Exception as e:
                    st.error(f"Error analyzing text: {str(e)}")
    
    elif analysis_type == "Model Training & Fine-tuning":
        st.subheader("Model Training & Fine-tuning")
        st.info("Train custom models for campaign finance analysis")
        
        training_option = st.selectbox(
            "Training Option",
            ["View Available Models", "Train New Models", "Test Predictions"]
        )
        
        if training_option == "View Available Models":
            try:
                model_info = analyzer.fine_tuner.get_model_info()
                
                st.write("### Available Models")
                for category, models in model_info.items():
                    if models:
                        st.write(f"**{category.title()}:**")
                        for model in models:
                            st.write(f"  • {model}")
                    else:
                        st.write(f"**{category.title()}:** No models trained yet")
                        
            except Exception as e:
                st.error(f"Error loading model info: {str(e)}")
        
        elif training_option == "Train New Models":
            if st.button("Train All Models"):
                with st.spinner("Training models... This may take a few minutes"):
                    try:
                        results = analyzer.fine_tuner.train_all_models()
                        
                        st.write("### Training Results")
                        for result in results:
                            if 'error' in result:
                                st.error(f"**{result['task']}**: {result['error']}")
                            else:
                                st.success(f"**{result['task']} ({result['model_type']})**")
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Train Score", f"{result['train_score']:.3f}")
                                with col2:
                                    st.metric("Test Score", f"{result['test_score']:.3f}")
                                with col3:
                                    st.metric("CV Score", f"{result['cv_mean']:.3f} ± {result['cv_std']:.3f}")
                                
                        st.info("Models saved to the models/ directory")
                        
                    except Exception as e:
                        st.error(f"Error training models: {str(e)}")
        
        elif training_option == "Test Predictions":
            task = st.selectbox(
                "Select Task",
                ["contributor_type_classification", "donation_size_prediction", "recipient_success_prediction"]
            )
            
            if task == "contributor_type_classification":
                test_name = st.text_input("Contributor Name", "Tech Solutions LLC")
                test_occupation = st.text_input("Occupation", "CEO")
                test_employer = st.text_input("Employer", "Technology Corporation")
                
                if st.button("Predict Contributor Type"):
                    try:
                        test_data = pd.DataFrame([{
                            'text': f"{test_name} {test_occupation} {test_employer}",
                            'num_contributions': 1,
                            'total_amount': 1000,
                            'avg_amount': 1000
                        }])
                        
                        prediction = analyzer.fine_tuner.predict(task, test_data)
                        st.write(f"**Predicted Type:** {prediction[0]}")
                        
                    except Exception as e:
                        st.error(f"Error making prediction: {str(e)}")

def show_natural_language_search_page():
    """Show natural language query interface."""
    st.header("🔍 Natural Language Search")
    st.markdown("Ask questions about the campaign finance data in plain English")
    
    # Initialize query processor
    nlp = NaturalLanguageQueryProcessor()
    
    # Example queries
    st.subheader("Example Queries")
    example_queries = [
        "Show all contributors who gave to Adams",
        "Top 10 contributors by total amount",
        "Contributors from Brooklyn",
        "Find all mayoral candidates",
        "Show contributions from John Smith"
    ]
    
    col1, col2, col3 = st.columns(3)
    for i, query in enumerate(example_queries):
        if i % 3 == 0:
            col = col1
        elif i % 3 == 1:
            col = col2
        else:
            col = col3
        
        with col:
            if st.button(query, key=f"example_{i}"):
                st.session_state.nl_query = query
    
    # Query input
    query = st.text_area(
        "Enter your question:",
        value=st.session_state.get('nl_query', ''),
        height=100,
        placeholder="e.g., Show me all contributors from Manhattan who gave more than $1000"
    )
    
    if st.button("Search", type="primary") or query:
        if query:
            with st.spinner("Processing query..."):
                try:
                    sql, results = nlp.process_query(query)
                    
                    # Show SQL query (collapsible)
                    with st.expander("View Generated SQL"):
                        st.code(sql, language='sql')
                    
                    # Show results
                    if not results.empty:
                        st.success(f"Found {len(results)} results")
                        
                        # Format currency columns if present
                        for col in results.columns:
                            if 'amount' in col.lower() and results[col].dtype in ['float64', 'int64']:
                                results[col] = results[col].apply(
                                    lambda x: format_currency(x) if pd.notna(x) else ''
                                )
                        
                        st.dataframe(results, use_container_width=True)
                        
                        # Download option
                        csv = results.to_csv(index=False)
                        st.download_button(
                            label="Download Results as CSV",
                            data=csv,
                            file_name=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("No results found for your query")
                        
                except Exception as e:
                    st.error(f"Error processing query: {str(e)}")
                    st.info("Try rephrasing your question or use one of the example queries")
        
        # Check if advanced NLP is available
        try:
            from ai_search import ADVANCED_NLP
            if ADVANCED_NLP:
                st.success("✓ Advanced NLP models (Gensim, NLTK, TextBlob) are active")
            else:
                st.warning("Basic search mode - Advanced NLP libraries not available")
        except:
            pass
    
    # Advanced search tips
    with st.expander("Search Tips"):
        st.markdown("""
        **Supported Query Types:**
        - Find contributors to a specific candidate: "Show contributors who gave to [candidate name]"
        - Top contributors: "Top [number] contributors by amount"
        - Geographic searches: "Contributors from [city/state/borough]"
        - Office-based searches: "Show all [office] candidates"
        - Donor searches: "Show contributions from [donor name]"
        
        **Tips:**
        - Use partial names for flexible matching
        - Specify numbers for "top" queries
        - Include location names for geographic filtering
        - Office names: Mayor, Public Advocate, Comptroller, Borough President, City Council
        """)

if __name__ == "__main__":
    main()