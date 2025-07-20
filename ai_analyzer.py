import json
import os
import pandas as pd
import numpy as np
from datetime import datetime
import re
from collections import Counter

class AIAnalyzer:
    """AI-powered analysis of political contribution data using local models and statistical methods."""
    
    def __init__(self):
        # Using local statistical analysis and pattern detection instead of external APIs
        self.analysis_cache = {}
        self.pattern_keywords = {
            'large_donations': ['major', 'substantial', 'significant'],
            'frequent_donors': ['recurring', 'regular', 'repeated'],
            'geographic_concentration': ['concentrated', 'clustered', 'localized'],
            'temporal_patterns': ['seasonal', 'periodic', 'cyclical']
        }
    
    def analyze_contributions(self, df):
        """Perform comprehensive AI analysis of political contributions."""
        try:
            # Generate data summary for AI analysis
            data_summary = self._generate_data_summary(df)
            
            # Get AI insights
            insights = self._get_ai_insights(data_summary)
            
            # Detect anomalies
            anomalies = self._detect_pattern_anomalies(df)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(data_summary, anomalies)
            
            return {
                'summary': insights.get('summary', ''),
                'patterns': insights.get('patterns', []),
                'anomalies': anomalies,
                'recommendations': recommendations,
                'analysis_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            raise Exception(f"AI analysis failed: {str(e)}")
    
    def _generate_data_summary(self, df):
        """Generate a comprehensive summary of the data for AI analysis."""
        summary = {
            'total_contributions': len(df),
            'total_amount': float(df['amount'].sum()),
            'average_amount': float(df['amount'].mean()),
            'median_amount': float(df['amount'].median()),
            'date_range': {
                'start': df['date'].min().strftime('%Y-%m-%d'),
                'end': df['date'].max().strftime('%Y-%m-%d'),
                'span_days': (df['date'].max() - df['date'].min()).days
            },
            'unique_donors': int(df['donor_name'].nunique()),
            'unique_recipients': int(df['recipient'].nunique()) if 'recipient' in df.columns else 0,
            'top_recipients': df.groupby('recipient')['amount'].sum().sort_values(ascending=False).head(10).to_dict() if 'recipient' in df.columns else {},
            'top_states': df['state'].value_counts().head(10).to_dict() if 'state' in df.columns else {},
            'amount_distribution': {
                'small_contributions': len(df[df['amount'] <= 200]),
                'medium_contributions': len(df[(df['amount'] > 200) & (df['amount'] <= 1000)]),
                'large_contributions': len(df[df['amount'] > 1000])
            },
            'temporal_patterns': {
                'contributions_by_month': df.groupby(df['date'].dt.month)['amount'].sum().to_dict(),
                'contributions_by_quarter': df.groupby(df['date'].dt.quarter)['amount'].sum().to_dict(),
                'contributions_by_year': df.groupby(df['date'].dt.year)['amount'].sum().to_dict()
            },
            'donor_patterns': {
                'repeat_donors': len(df[df.duplicated(subset=['donor_name'], keep=False)]['donor_name'].unique()),
                'single_donors': len(df[~df.duplicated(subset=['donor_name'], keep=False)]['donor_name'].unique()),
                'top_donors': df.groupby('donor_name')['amount'].sum().sort_values(ascending=False).head(10).to_dict()
            }
        }
        
        return summary
    
    def _get_ai_insights(self, data_summary):
        """Generate insights using statistical analysis and pattern detection."""
        try:
            insights = {
                'summary': self._generate_statistical_summary(data_summary),
                'patterns': self._detect_statistical_patterns(data_summary)
            }
            return insights
            
        except Exception as e:
            return {
                'summary': f'Analysis unavailable: {str(e)}',
                'patterns': []
            }
    
    def _generate_statistical_summary(self, data_summary):
        """Generate a comprehensive statistical summary."""
        total_contributions = data_summary['total_contributions']
        total_amount = data_summary['total_amount']
        unique_donors = data_summary['unique_donors']
        unique_recipients = data_summary['unique_recipients']
        
        # Calculate key metrics
        avg_contribution = total_amount / total_contributions if total_contributions > 0 else 0
        donor_participation_rate = unique_donors / total_contributions if total_contributions > 0 else 0
        
        # Analyze contribution distribution
        amount_dist = data_summary['amount_distribution']
        small_pct = (amount_dist['small_contributions'] / total_contributions * 100) if total_contributions > 0 else 0
        large_pct = (amount_dist['large_contributions'] / total_contributions * 100) if total_contributions > 0 else 0
        
        summary = f"""
        Analysis of {total_contributions:,} political contributions totaling ${total_amount:,.2f}.
        
        Key Findings:
        • Average contribution: ${avg_contribution:.2f}
        • {unique_donors:,} unique donors contributing to {unique_recipients} recipients
        • {small_pct:.1f}% are small contributions ($200 or less)
        • {large_pct:.1f}% are large contributions (over $1,000)
        • Data spans {data_summary['date_range']['span_days']} days from {data_summary['date_range']['start']} to {data_summary['date_range']['end']}
        
        The contribution landscape shows {'high grassroots participation' if small_pct > 60 else 'significant large donor influence' if large_pct > 20 else 'mixed contribution patterns'}.
        """
        
        return summary.strip()
    
    def _detect_statistical_patterns(self, data_summary):
        """Detect patterns using statistical analysis."""
        patterns = []
        
        # Temporal patterns
        temporal_data = data_summary['temporal_patterns']
        if temporal_data:
            monthly_amounts = list(temporal_data['contributions_by_month'].values())
            quarterly_amounts = list(temporal_data['contributions_by_quarter'].values())
            
            if len(monthly_amounts) > 1:
                monthly_variation = np.std(monthly_amounts) / np.mean(monthly_amounts) if np.mean(monthly_amounts) > 0 else 0
                if monthly_variation > 0.5:
                    patterns.append("High monthly variation in contributions suggests seasonal or event-driven giving patterns")
                
            if len(quarterly_amounts) == 4:
                q4_amount = quarterly_amounts[3] if len(quarterly_amounts) > 3 else 0
                total_quarterly = sum(quarterly_amounts)
                if q4_amount > total_quarterly * 0.4:
                    patterns.append("Strong Q4 contribution surge indicates year-end fundraising focus")
        
        # Donor concentration analysis
        top_donors = data_summary['donor_patterns']['top_donors']
        total_amount = data_summary['total_amount']
        
        if top_donors and total_amount > 0:
            top_10_total = sum(list(top_donors.values())[:10])
            concentration_ratio = top_10_total / total_amount
            
            if concentration_ratio > 0.5:
                patterns.append(f"High donor concentration: Top 10 donors account for {concentration_ratio:.1%} of total contributions")
            elif concentration_ratio < 0.2:
                patterns.append("Broad-based fundraising with low donor concentration indicates grassroots support")
        
        # Geographic patterns
        top_states = data_summary['top_states']
        if top_states:
            state_counts = list(top_states.values())
            if len(state_counts) > 1:
                top_state_pct = state_counts[0] / sum(state_counts)
                if top_state_pct > 0.6:
                    top_state = list(top_states.keys())[0]
                    patterns.append(f"Geographic concentration: {top_state_pct:.1%} of contributions from {top_state}")
        
        # Repeat donor analysis
        repeat_donors = data_summary['donor_patterns']['repeat_donors']
        total_unique_donors = data_summary['unique_donors']
        
        if total_unique_donors > 0:
            repeat_rate = repeat_donors / total_unique_donors
            if repeat_rate > 0.3:
                patterns.append(f"Strong donor loyalty: {repeat_rate:.1%} of donors made multiple contributions")
            elif repeat_rate < 0.1:
                patterns.append("Low repeat donation rate suggests need for donor retention strategies")
        
        # Amount distribution patterns
        amount_dist = data_summary['amount_distribution']
        total_contribs = data_summary['total_contributions']
        
        if total_contribs > 0:
            small_ratio = amount_dist['small_contributions'] / total_contribs
            large_ratio = amount_dist['large_contributions'] / total_contribs
            
            if small_ratio > 0.7:
                patterns.append("Grassroots funding model with majority of small-dollar contributions")
            elif large_ratio > 0.3:
                patterns.append("Traditional fundraising model with significant large-dollar contributions")
        
        return patterns[:5]  # Return top 5 patterns
    
    def _detect_pattern_anomalies(self, df):
        """Detect unusual patterns in the contribution data."""
        anomalies = []
        
        try:
            # Check for unusual amount patterns
            amount_stats = df['amount'].describe()
            
            # Very large single contributions
            large_threshold = amount_stats['75%'] + 3 * (amount_stats['75%'] - amount_stats['25%'])
            large_contributions = df[df['amount'] > large_threshold]
            if len(large_contributions) > 0:
                anomalies.append(f"Found {len(large_contributions)} unusually large contributions (>${large_threshold:.2f}+)")
            
            # Round number bias
            round_amounts = df[df['amount'].apply(lambda x: x % 100 == 0 and x >= 100)]
            round_percentage = len(round_amounts) / len(df) * 100
            if round_percentage > 30:
                anomalies.append(f"High percentage ({round_percentage:.1f}%) of round-dollar contributions")
            
            # Temporal anomalies
            if 'date' in df.columns:
                monthly_counts = df.groupby(df['date'].dt.to_period('M')).size()
                monthly_mean = monthly_counts.mean()
                monthly_std = monthly_counts.std()
                
                # Check for months with unusually high activity
                high_activity_months = monthly_counts[monthly_counts > monthly_mean + 2 * monthly_std]
                if len(high_activity_months) > 0:
                    anomalies.append(f"Detected {len(high_activity_months)} months with unusually high contribution activity")
            
            # Duplicate donor patterns
            donor_counts = df['donor_name'].value_counts()
            frequent_donors = donor_counts[donor_counts > donor_counts.quantile(0.95)]
            if len(frequent_donors) > 0:
                anomalies.append(f"Found {len(frequent_donors)} donors with unusually high contribution frequency")
            
            # Geographic concentration
            if 'state' in df.columns:
                state_amounts = df.groupby('state')['amount'].sum()
                top_state_percentage = (state_amounts.max() / state_amounts.sum()) * 100
                if top_state_percentage > 50:
                    top_state = state_amounts.idxmax()
                    anomalies.append(f"High geographic concentration: {top_state_percentage:.1f}% of contributions from {top_state}")
            
        except Exception as e:
            anomalies.append(f"Anomaly detection error: {str(e)}")
        
        return anomalies
    
    def _generate_recommendations(self, data_summary, anomalies):
        """Generate evidence-based recommendations from statistical analysis."""
        try:
            recommendations = []
            
            # Data quality recommendations
            total_contributions = data_summary['total_contributions']
            if total_contributions < 100:
                recommendations.append("Consider collecting more data for robust statistical analysis")
            
            # Fundraising strategy recommendations
            amount_dist = data_summary['amount_distribution']
            small_ratio = amount_dist['small_contributions'] / total_contributions if total_contributions > 0 else 0
            large_ratio = amount_dist['large_contributions'] / total_contributions if total_contributions > 0 else 0
            
            if small_ratio > 0.8:
                recommendations.append("Strong grassroots base - consider implementing donor progression strategies to increase contribution amounts")
            elif large_ratio > 0.5:
                recommendations.append("High dependency on large donors - consider diversifying with small-dollar fundraising campaigns")
            
            # Geographic recommendations
            top_states = data_summary['top_states']
            if top_states:
                state_counts = list(top_states.values())
                if len(state_counts) > 1:
                    concentration = state_counts[0] / sum(state_counts)
                    if concentration > 0.7:
                        recommendations.append("Geographic concentration risk - expand fundraising to additional states and regions")
                    elif concentration < 0.3:
                        recommendations.append("Good geographic diversification - maintain broad outreach strategies")
            
            # Donor retention recommendations
            repeat_donors = data_summary['donor_patterns']['repeat_donors']
            total_unique = data_summary['unique_donors']
            if total_unique > 0:
                retention_rate = repeat_donors / total_unique
                if retention_rate < 0.2:
                    recommendations.append("Low donor retention - implement stewardship programs and regular donor communication")
                elif retention_rate > 0.4:
                    recommendations.append("Strong donor retention - leverage loyal donors for peer-to-peer fundraising")
            
            # Temporal recommendations
            temporal_data = data_summary.get('temporal_patterns', {})
            if temporal_data.get('contributions_by_quarter'):
                quarterly_amounts = list(temporal_data['contributions_by_quarter'].values())
                if len(quarterly_amounts) == 4:
                    q1_amount = quarterly_amounts[0]
                    total_amount = sum(quarterly_amounts)
                    if q1_amount < total_amount * 0.15:
                        recommendations.append("Low Q1 fundraising - implement early-year donor engagement strategies")
            
            # Anomaly-based recommendations
            if len(anomalies) > 5:
                recommendations.append("Multiple anomalies detected - conduct detailed compliance review and data validation")
            elif len(anomalies) > 0:
                recommendations.append("Some anomalies detected - review flagged contributions for compliance")
            
            # Compliance recommendations
            recommendations.append("Regular compliance monitoring recommended - implement automated limit checking")
            recommendations.append("Maintain comprehensive donor records and documentation for regulatory compliance")
            
            return recommendations[:5]  # Return top 5 recommendations
            
        except Exception as e:
            return [f"Unable to generate recommendations: {str(e)}"]
    
    def analyze_donor_behavior(self, df, donor_name):
        """Analyze specific donor's contribution behavior."""
        try:
            donor_data = df[df['donor_name'].str.contains(donor_name, case=False, na=False)]
            
            if len(donor_data) == 0:
                return {'error': 'Donor not found'}
            
            analysis = {
                'total_contributions': len(donor_data),
                'total_amount': float(donor_data['amount'].sum()),
                'average_amount': float(donor_data['amount'].mean()),
                'contribution_range': {
                    'min': float(donor_data['amount'].min()),
                    'max': float(donor_data['amount'].max())
                },
                'date_range': {
                    'first': donor_data['date'].min().strftime('%Y-%m-%d'),
                    'last': donor_data['date'].max().strftime('%Y-%m-%d')
                },
                'recipients': donor_data['recipient'].value_counts().to_dict() if 'recipient' in donor_data.columns else {},
                'temporal_pattern': donor_data.groupby(donor_data['date'].dt.month)['amount'].sum().to_dict()
            }
            
            return analysis
            
        except Exception as e:
            return {'error': f'Analysis failed: {str(e)}'}
