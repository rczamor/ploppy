import pandas as pd
import numpy as np
from datetime import datetime
import re

class DataProcessor:
    """Handles data loading, cleaning, and preprocessing for political contribution data."""
    
    def __init__(self):
        self.column_mappings = {
            # Common column name variations
            'date': ['date', 'transaction_date', 'contribution_date', 'receipt_date'],
            'amount': ['amount', 'contribution_amount', 'transaction_amount', 'receipt_amount'],
            'donor_name': ['donor_name', 'contributor_name', 'name', 'full_name', 'contributor'],
            'recipient': ['recipient', 'candidate', 'committee', 'recipient_name', 'committee_name'],
            'city': ['city', 'contributor_city', 'donor_city'],
            'state': ['state', 'contributor_state', 'donor_state'],
            'zip': ['zip', 'zipcode', 'postal_code', 'contributor_zip', 'donor_zip'],
            'occupation': ['occupation', 'contributor_occupation', 'donor_occupation'],
            'employer': ['employer', 'contributor_employer', 'donor_employer']
        }
    
    def process_data(self, df):
        """Process and clean the raw political contribution data."""
        try:
            # Create a copy to avoid modifying original data
            processed_df = df.copy()
            
            # Standardize column names
            processed_df = self._standardize_columns(processed_df)
            
            # Clean and validate data
            processed_df = self._clean_data(processed_df)
            
            # Add derived features
            processed_df = self._add_derived_features(processed_df)
            
            return processed_df
            
        except Exception as e:
            raise Exception(f"Data processing failed: {str(e)}")
    
    def _standardize_columns(self, df):
        """Standardize column names based on common variations."""
        df_columns_lower = [col.lower().strip() for col in df.columns]
        column_map = {}
        
        for standard_name, variations in self.column_mappings.items():
            for variation in variations:
                if variation.lower() in df_columns_lower:
                    original_col = df.columns[df_columns_lower.index(variation.lower())]
                    column_map[original_col] = standard_name
                    break
        
        df = df.rename(columns=column_map)
        
        # Ensure required columns exist
        required_columns = ['date', 'amount', 'donor_name']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        return df
    
    def _clean_data(self, df):
        """Clean and validate the data."""
        # Clean amount column
        if 'amount' in df.columns:
            # Remove currency symbols and convert to float
            df['amount'] = df['amount'].astype(str).str.replace('[\$,]', '', regex=True)
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            
            # Remove negative amounts and extremely large amounts
            df = df[df['amount'] > 0]
            df = df[df['amount'] <= 1000000]  # Cap at $1M
        
        # Clean date column
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            # Remove records with invalid dates
            df = df[df['date'].notna()]
            
            # Remove future dates
            df = df[df['date'] <= datetime.now()]
        
        # Clean text columns
        text_columns = ['donor_name', 'recipient', 'city', 'state', 'occupation', 'employer']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.title()
                # Remove rows with missing donor names or recipients
                if col in ['donor_name', 'recipient']:
                    df = df[df[col].notna() & (df[col] != 'Nan') & (df[col] != '')]
        
        # Clean ZIP codes
        if 'zip' in df.columns:
            df['zip'] = df['zip'].astype(str).str.extract('(\d{5})')[0]
        
        # Standardize state codes
        if 'state' in df.columns:
            df['state'] = df['state'].str.upper().str.slice(0, 2)
        
        # Remove duplicates
        df = df.drop_duplicates()
        
        return df
    
    def _add_derived_features(self, df):
        """Add derived features for analysis."""
        # Add time-based features
        if 'date' in df.columns:
            df['year'] = df['date'].dt.year
            df['month'] = df['date'].dt.month
            df['quarter'] = df['date'].dt.quarter
            df['day_of_year'] = df['date'].dt.dayofyear
            df['weekday'] = df['date'].dt.day_name()
            
            # Election cycle feature (assuming 2-year cycles)
            df['election_cycle'] = ((df['year'] - 1) // 2) * 2 + 1
        
        # Add amount categories
        if 'amount' in df.columns:
            df['amount_category'] = pd.cut(
                df['amount'],
                bins=[0, 50, 200, 1000, 5000, float('inf')],
                labels=['Small ($0-$50)', 'Medium ($51-$200)', 'Large ($201-$1K)', 
                       'Major ($1K-$5K)', 'Maximum ($5K+)'],
                include_lowest=True
            )
        
        # Add donor type based on patterns
        if 'donor_name' in df.columns:
            df['donor_type'] = df['donor_name'].apply(self._classify_donor_type)
        
        # Add geographic region
        if 'state' in df.columns:
            df['region'] = df['state'].map(self._get_region_mapping())
        
        return df
    
    def _classify_donor_type(self, donor_name):
        """Classify donor type based on name patterns."""
        if pd.isna(donor_name) or donor_name == '':
            return 'Unknown'
        
        donor_name = str(donor_name).upper()
        
        # Check for organizational indicators
        org_indicators = ['LLC', 'INC', 'CORP', 'COMMITTEE', 'PAC', 'ASSOCIATION', 
                         'UNION', 'FOUNDATION', 'TRUST', 'PARTNERSHIP']
        
        if any(indicator in donor_name for indicator in org_indicators):
            return 'Organization'
        
        # Check for individual patterns (has comma, suggesting Last, First format)
        if ',' in donor_name:
            return 'Individual'
        
        # Default to individual for single names
        return 'Individual'
    
    def _get_region_mapping(self):
        """Map states to geographic regions."""
        return {
            # Northeast
            'ME': 'Northeast', 'NH': 'Northeast', 'VT': 'Northeast', 'MA': 'Northeast',
            'RI': 'Northeast', 'CT': 'Northeast', 'NY': 'Northeast', 'NJ': 'Northeast',
            'PA': 'Northeast',
            
            # Southeast
            'DE': 'Southeast', 'MD': 'Southeast', 'DC': 'Southeast', 'VA': 'Southeast',
            'WV': 'Southeast', 'KY': 'Southeast', 'TN': 'Southeast', 'NC': 'Southeast',
            'SC': 'Southeast', 'GA': 'Southeast', 'FL': 'Southeast', 'AL': 'Southeast',
            'MS': 'Southeast', 'AR': 'Southeast', 'LA': 'Southeast',
            
            # Midwest
            'OH': 'Midwest', 'MI': 'Midwest', 'IN': 'Midwest', 'WI': 'Midwest',
            'IL': 'Midwest', 'MN': 'Midwest', 'IA': 'Midwest', 'MO': 'Midwest',
            'ND': 'Midwest', 'SD': 'Midwest', 'NE': 'Midwest', 'KS': 'Midwest',
            
            # Southwest
            'OK': 'Southwest', 'TX': 'Southwest', 'AZ': 'Southwest', 'NM': 'Southwest',
            
            # West
            'MT': 'West', 'WY': 'West', 'CO': 'West', 'UT': 'West', 'ID': 'West',
            'WA': 'West', 'OR': 'West', 'NV': 'West', 'CA': 'West', 'AK': 'West',
            'HI': 'West'
        }
    
    def get_data_summary(self, df):
        """Generate a comprehensive data summary."""
        summary = {
            'total_records': len(df),
            'total_amount': df['amount'].sum(),
            'date_range': {
                'start': df['date'].min(),
                'end': df['date'].max()
            },
            'unique_donors': df['donor_name'].nunique(),
            'unique_recipients': df['recipient'].nunique() if 'recipient' in df.columns else 0,
            'amount_stats': df['amount'].describe().to_dict(),
            'top_states': df['state'].value_counts().head(10).to_dict() if 'state' in df.columns else {},
            'data_quality': {
                'completeness': (1 - df.isnull().sum() / len(df)).to_dict(),
                'duplicates': df.duplicated().sum()
            }
        }
        
        return summary
