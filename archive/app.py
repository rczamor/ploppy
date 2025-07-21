import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io

# Import custom modules
from data_processor import DataProcessor
from ai_analyzer import AIAnalyzer
from visualizations import Visualizations
from ml_clustering import MLClustering
from compliance_checker import ComplianceChecker
from utils import format_currency, validate_data

# Page configuration
st.set_page_config(
    page_title="Political Contribution Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'data' not in st.session_state:
    st.session_state.data = None
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'ai_insights' not in st.session_state:
    st.session_state.ai_insights = None

# Initialize components
@st.cache_resource
def initialize_components():
    return {
        'data_processor': DataProcessor(),
        'ai_analyzer': AIAnalyzer(),
        'visualizations': Visualizations(),
        'ml_clustering': MLClustering(),
        'compliance_checker': ComplianceChecker()
    }

components = initialize_components()

# Main title and description
st.title("🏛️ Political Contribution Data Analyzer")
st.markdown("""
This AI-powered application provides comprehensive analysis of political contribution data with 
machine learning insights, interactive visualizations, and compliance checking.
""")

# Sidebar for file upload and basic controls
with st.sidebar:
    st.header("📁 Data Upload")
    
    uploaded_file = st.file_uploader(
        "Upload Political Contribution Data",
        type=['csv', 'xlsx', 'xls'],
        help="Upload CSV or Excel files containing political contribution data"
    )
    
    if uploaded_file is not None:
        try:
            with st.spinner("Processing uploaded file..."):
                # Load and process data
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                # Validate and process data
                validation_result = validate_data(df)
                if validation_result['is_valid']:
                    st.session_state.data = df
                    st.session_state.processed_data = components['data_processor'].process_data(df)
                    st.success(f"✅ Successfully loaded {len(df):,} records")
                    
                    # Show data overview
                    st.subheader("📋 Data Overview")
                    st.write(f"**Rows:** {len(df):,}")
                    st.write(f"**Columns:** {len(df.columns)}")
                    st.write(f"**Date Range:** {validation_result.get('date_range', 'N/A')}")
                    st.write(f"**Total Amount:** {format_currency(validation_result.get('total_amount', 0))}")
                else:
                    st.error("❌ Data validation failed:")
                    for error in validation_result['errors']:
                        st.error(f"• {error}")
        
        except Exception as e:
            st.error(f"Error loading file: {str(e)}")

# Main content area
if st.session_state.data is not None:
    # Create tabs for different analyses
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview", "🤖 AI Insights", "📈 Visualizations", 
        "🎯 ML Analysis", "⚖️ Compliance", "📤 Export"
    ])
    
    with tab1:
        st.header("📊 Data Overview & Summary Statistics")
        
        df = st.session_state.processed_data
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Contributions", f"{len(df):,}")
        with col2:
            st.metric("Total Amount", format_currency(df['amount'].sum()))
        with col3:
            st.metric("Unique Donors", f"{df['donor_name'].nunique():,}")
        with col4:
            st.metric("Unique Recipients", f"{df['recipient'].nunique():,}")
        
        # Data filtering
        st.subheader("🔍 Data Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            date_range = st.date_input(
                "Date Range",
                value=(df['date'].min(), df['date'].max()),
                min_value=df['date'].min(),
                max_value=df['date'].max()
            )
        
        with col2:
            amount_range = st.slider(
                "Contribution Amount Range",
                min_value=float(df['amount'].min()),
                max_value=float(df['amount'].max()),
                value=(float(df['amount'].min()), float(df['amount'].max())),
                format="$%.2f"
            )
        
        with col3:
            states = st.multiselect(
                "Select States",
                options=sorted(df['state'].unique()),
                default=[]
            )
        
        # Apply filters
        filtered_df = df.copy()
        if len(date_range) == 2:
            filtered_df = filtered_df[
                (filtered_df['date'] >= pd.to_datetime(date_range[0])) &
                (filtered_df['date'] <= pd.to_datetime(date_range[1]))
            ]
        
        filtered_df = filtered_df[
            (filtered_df['amount'] >= amount_range[0]) &
            (filtered_df['amount'] <= amount_range[1])
        ]
        
        if states:
            filtered_df = filtered_df[filtered_df['state'].isin(states)]
        
        # Display filtered data
        st.subheader(f"📋 Filtered Data ({len(filtered_df):,} records)")
        st.dataframe(
            filtered_df.head(1000),
            use_container_width=True,
            height=400
        )
        
        # Quick statistics
        if len(filtered_df) > 0:
            st.subheader("📈 Quick Statistics")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Top 10 Recipients by Amount**")
                top_recipients = filtered_df.groupby('recipient')['amount'].sum().sort_values(ascending=False).head(10)
                st.dataframe(top_recipients.reset_index())
            
            with col2:
                st.write("**Top 10 States by Amount**")
                top_states = filtered_df.groupby('state')['amount'].sum().sort_values(ascending=False).head(10)
                st.dataframe(top_states.reset_index())
    
    with tab2:
        st.header("🤖 AI-Powered Insights")
        
        if st.button("🔍 Generate AI Analysis", type="primary"):
            with st.spinner("Analyzing data with AI... This may take a moment."):
                try:
                    insights = components['ai_analyzer'].analyze_contributions(
                        st.session_state.processed_data
                    )
                    st.session_state.ai_insights = insights
                except Exception as e:
                    st.error(f"AI analysis failed: {str(e)}")
        
        if st.session_state.ai_insights:
            insights = st.session_state.ai_insights
            
            # Display insights
            st.subheader("📝 Key Findings")
            st.write(insights.get('summary', 'No summary available'))
            
            st.subheader("🎯 Pattern Analysis")
            patterns = insights.get('patterns', [])
            for i, pattern in enumerate(patterns, 1):
                st.write(f"**{i}.** {pattern}")
            
            st.subheader("🚨 Anomalies Detected")
            anomalies = insights.get('anomalies', [])
            if anomalies:
                for anomaly in anomalies:
                    st.warning(f"⚠️ {anomaly}")
            else:
                st.info("No significant anomalies detected in the data.")
            
            st.subheader("💡 Recommendations")
            recommendations = insights.get('recommendations', [])
            for i, rec in enumerate(recommendations, 1):
                st.success(f"**{i}.** {rec}")
        else:
            st.info("Click 'Generate AI Analysis' to get AI-powered insights about your data.")
    
    with tab3:
        st.header("📈 Interactive Visualizations")
        
        df = st.session_state.processed_data
        vis = components['visualizations']
        
        # Chart selection
        chart_type = st.selectbox(
            "Select Visualization Type",
            [
                "Time Series Analysis",
                "Geographic Distribution",
                "Amount Distribution",
                "Top Contributors/Recipients",
                "Contribution Patterns",
                "Seasonal Trends"
            ]
        )
        
        try:
            if chart_type == "Time Series Analysis":
                fig = vis.create_time_series_chart(df)
                st.plotly_chart(fig, use_container_width=True)
                
            elif chart_type == "Geographic Distribution":
                fig = vis.create_geographic_map(df)
                st.plotly_chart(fig, use_container_width=True)
                
            elif chart_type == "Amount Distribution":
                fig = vis.create_amount_distribution(df)
                st.plotly_chart(fig, use_container_width=True)
                
            elif chart_type == "Top Contributors/Recipients":
                col1, col2 = st.columns(2)
                with col1:
                    fig_contributors = vis.create_top_contributors_chart(df)
                    st.plotly_chart(fig_contributors, use_container_width=True)
                with col2:
                    fig_recipients = vis.create_top_recipients_chart(df)
                    st.plotly_chart(fig_recipients, use_container_width=True)
                    
            elif chart_type == "Contribution Patterns":
                fig = vis.create_contribution_patterns(df)
                st.plotly_chart(fig, use_container_width=True)
                
            elif chart_type == "Seasonal Trends":
                fig = vis.create_seasonal_trends(df)
                st.plotly_chart(fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error creating visualization: {str(e)}")
    
    with tab4:
        st.header("🎯 Machine Learning Analysis")
        
        ml = components['ml_clustering']
        
        st.subheader("👥 Donor Clustering Analysis")
        
        # Clustering parameters
        col1, col2 = st.columns(2)
        with col1:
            n_clusters = st.slider("Number of Clusters", min_value=2, max_value=10, value=5)
        with col2:
            clustering_features = st.multiselect(
                "Features for Clustering",
                ["amount", "frequency", "timing", "geographic"],
                default=["amount", "frequency"]
            )
        
        if st.button("🔍 Perform Clustering Analysis", type="primary"):
            with st.spinner("Running machine learning analysis..."):
                try:
                    clustering_results = ml.perform_donor_clustering(
                        st.session_state.processed_data,
                        n_clusters=n_clusters,
                        features=clustering_features
                    )
                    
                    # Display clustering results
                    st.subheader("📊 Clustering Results")
                    
                    # Cluster visualization
                    fig = ml.visualize_clusters(clustering_results)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Cluster statistics
                    st.subheader("📈 Cluster Statistics")
                    cluster_stats = clustering_results['cluster_stats']
                    st.dataframe(cluster_stats, use_container_width=True)
                    
                    # Donor segments
                    st.subheader("👥 Donor Segments")
                    for cluster_id, description in clustering_results['segment_descriptions'].items():
                        st.write(f"**Cluster {cluster_id}:** {description}")
                    
                except Exception as e:
                    st.error(f"Clustering analysis failed: {str(e)}")
        
        # Anomaly Detection
        st.subheader("🚨 Anomaly Detection")
        
        if st.button("🔍 Detect Anomalies", type="secondary"):
            with st.spinner("Detecting anomalies..."):
                try:
                    anomalies = ml.detect_anomalies(st.session_state.processed_data)
                    
                    if len(anomalies) > 0:
                        st.warning(f"Found {len(anomalies)} potential anomalies:")
                        st.dataframe(anomalies.head(100), use_container_width=True)
                        
                        # Anomaly visualization
                        fig = ml.visualize_anomalies(
                            st.session_state.processed_data, 
                            anomalies
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.success("No significant anomalies detected!")
                        
                except Exception as e:
                    st.error(f"Anomaly detection failed: {str(e)}")
    
    with tab5:
        st.header("⚖️ Compliance Analysis")
        
        compliance = components['compliance_checker']
        
        if st.button("🔍 Run Compliance Check", type="primary"):
            with st.spinner("Checking compliance..."):
                try:
                    compliance_results = compliance.check_compliance(
                        st.session_state.processed_data
                    )
                    
                    # Overall compliance score
                    score = compliance_results['overall_score']
                    if score >= 0.9:
                        st.success(f"✅ Excellent Compliance Score: {score:.1%}")
                    elif score >= 0.7:
                        st.warning(f"⚠️ Good Compliance Score: {score:.1%}")
                    else:
                        st.error(f"❌ Poor Compliance Score: {score:.1%}")
                    
                    # Detailed compliance checks
                    st.subheader("📋 Compliance Check Details")
                    
                    checks = compliance_results['checks']
                    for check_name, check_result in checks.items():
                        if check_result['passed']:
                            st.success(f"✅ {check_name}: {check_result['message']}")
                        else:
                            st.error(f"❌ {check_name}: {check_result['message']}")
                            if 'violations' in check_result:
                                st.dataframe(
                                    check_result['violations'].head(10),
                                    use_container_width=True
                                )
                    
                    # Recommendations
                    if compliance_results['recommendations']:
                        st.subheader("💡 Compliance Recommendations")
                        for rec in compliance_results['recommendations']:
                            st.info(f"💡 {rec}")
                    
                except Exception as e:
                    st.error(f"Compliance check failed: {str(e)}")
    
    with tab6:
        st.header("📤 Export Analysis Results")
        
        df = st.session_state.processed_data
        
        st.subheader("📊 Export Options")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Export filtered data
            st.write("**Export Processed Data**")
            
            if st.button("📄 Download CSV", type="secondary"):
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV File",
                    data=csv,
                    file_name=f"political_contributions_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            if st.button("📊 Download Excel", type="secondary"):
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, sheet_name='Contributions', index=False)
                    
                    # Add summary statistics
                    summary_stats = df.describe()
                    summary_stats.to_excel(writer, sheet_name='Summary_Stats')
                
                st.download_button(
                    label="Download Excel File",
                    data=buffer.getvalue(),
                    file_name=f"political_contributions_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        with col2:
            # Export analysis results
            st.write("**Export Analysis Results**")
            
            if st.session_state.ai_insights and st.button("🤖 Download AI Insights", type="secondary"):
                insights_text = f"""
Political Contribution Analysis Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SUMMARY:
{st.session_state.ai_insights.get('summary', 'N/A')}

KEY PATTERNS:
{chr(10).join([f"• {p}" for p in st.session_state.ai_insights.get('patterns', [])])}

ANOMALIES:
{chr(10).join([f"• {a}" for a in st.session_state.ai_insights.get('anomalies', [])])}

RECOMMENDATIONS:
{chr(10).join([f"• {r}" for r in st.session_state.ai_insights.get('recommendations', [])])}
                """
                
                st.download_button(
                    label="Download AI Insights Report",
                    data=insights_text,
                    file_name=f"ai_insights_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
        
        # Export summary
        st.subheader("📋 Analysis Summary")
        st.write(f"**Dataset:** {len(df):,} contribution records")
        st.write(f"**Total Amount:** {format_currency(df['amount'].sum())}")
        st.write(f"**Date Range:** {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
        st.write(f"**Unique Donors:** {df['donor_name'].nunique():,}")
        st.write(f"**Unique Recipients:** {df['recipient'].nunique():,}")

else:
    # Welcome screen when no data is loaded
    st.info("👆 Please upload a political contribution dataset using the sidebar to begin analysis.")
    
    st.subheader("📋 Expected Data Format")
    st.write("""
    Your data should include the following columns (column names may vary):
    - **Date:** Transaction date
    - **Amount:** Contribution amount
    - **Donor Name:** Name of the contributor
    - **Recipient:** Name of the recipient (candidate/committee)
    - **City:** Donor city
    - **State:** Donor state
    - **ZIP:** Donor ZIP code
    - **Occupation:** Donor occupation (optional)
    - **Employer:** Donor employer (optional)
    """)
    
    st.subheader("🔧 Features")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("""
        **Data Analysis:**
        - ✅ Automated data cleaning and validation
        - ✅ Statistical summaries and insights
        - ✅ Time-series trend analysis
        - ✅ Geographic distribution mapping
        - ✅ Donor behavior analysis
        """)
    
    with col2:
        st.write("""
        **Advanced Features:**
        - ✅ AI-powered pattern detection
        - ✅ Machine learning clustering
        - ✅ Anomaly detection
        - ✅ Compliance checking
        - ✅ Interactive visualizations
        """)

# Footer
st.markdown("---")
st.markdown(
    "🏛️ **Political Contribution Analyzer** - AI-powered data analysis for political transparency"
)
