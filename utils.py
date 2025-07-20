import pandas as pd
import numpy as np
from datetime import datetime
import re

def format_currency(amount):
    """Format a number as currency."""
    if pd.isna(amount):
        return "$0.00"
    
    if amount >= 1_000_000:
        return f"${amount/1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"${amount/1_000:.1f}K"
    else:
        return f"${amount:,.2f}"

def validate_data(df):
    """Validate uploaded political contribution data."""
    validation_result = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'info': {}
    }
    
    try:
        # Check if dataframe is empty
        if df.empty:
            validation_result['is_valid'] = False
            validation_result['errors'].append("Uploaded file is empty")
            return validation_result
        
        # Check minimum required columns
        required_columns = ['date', 'amount', 'donor_name']
        df_columns_lower = [col.lower().strip() for col in df.columns]
        
        # Map common column variations
        column_mappings = {
            'date': ['date', 'transaction_date', 'contribution_date', 'receipt_date'],
            'amount': ['amount', 'contribution_amount', 'transaction_amount', 'receipt_amount'],
            'donor_name': ['donor_name', 'contributor_name', 'name', 'full_name', 'contributor'],
        }
        
        found_columns = {}
        for req_col in required_columns:
            found = False
            for variation in column_mappings.get(req_col, [req_col]):
                if variation.lower() in df_columns_lower:
                    found_columns[req_col] = df.columns[df_columns_lower.index(variation.lower())]
                    found = True
                    break
            
            if not found:
                validation_result['errors'].append(f"Required column '{req_col}' not found. Expected one of: {column_mappings.get(req_col, [req_col])}")
        
        if validation_result['errors']:
            validation_result['is_valid'] = False
            return validation_result
        
        # Basic data type validation
        try:
            # Test amount conversion
            amount_col = found_columns['amount']
            test_amounts = pd.to_numeric(df[amount_col].astype(str).str.replace('[\$,]', '', regex=True), errors='coerce')
            null_amounts = test_amounts.isnull().sum()
            if null_amounts > len(df) * 0.1:  # More than 10% invalid amounts
                validation_result['warnings'].append(f"Warning: {null_amounts} rows have invalid amount values")
            
            # Test date conversion
            date_col = found_columns['date']
            test_dates = pd.to_datetime(df[date_col], errors='coerce')
            null_dates = test_dates.isnull().sum()
            if null_dates > len(df) * 0.1:  # More than 10% invalid dates
                validation_result['warnings'].append(f"Warning: {null_dates} rows have invalid date values")
            else:
                validation_result['info']['date_range'] = f"{test_dates.min().strftime('%Y-%m-%d')} to {test_dates.max().strftime('%Y-%m-%d')}"
            
            # Calculate total amount
            valid_amounts = test_amounts.dropna()
            if len(valid_amounts) > 0:
                validation_result['info']['total_amount'] = valid_amounts.sum()
        
        except Exception as e:
            validation_result['warnings'].append(f"Warning: Data validation issues - {str(e)}")
        
        # Check data size
        if len(df) > 1_000_000:
            validation_result['warnings'].append("Warning: Large dataset may affect performance")
        
        # Check for completely empty columns
        empty_columns = [col for col in df.columns if df[col].isnull().all()]
        if empty_columns:
            validation_result['warnings'].append(f"Warning: Completely empty columns found: {empty_columns}")
        
        validation_result['info']['total_rows'] = len(df)
        validation_result['info']['total_columns'] = len(df.columns)
        
    except Exception as e:
        validation_result['is_valid'] = False
        validation_result['errors'].append(f"Data validation failed: {str(e)}")
    
    return validation_result

def clean_text_field(text):
    """Clean and standardize text fields."""
    if pd.isna(text) or text == '':
        return ''
    
    text = str(text).strip()
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Standardize case
    text = text.title()
    
    return text

def detect_file_encoding(file_path):
    """Detect file encoding for better CSV reading."""
    import chardet
    
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000)  # Read first 10KB
        result = chardet.detect(raw_data)
        return result.get('encoding', 'utf-8')

def generate_summary_stats(df):
    """Generate comprehensive summary statistics."""
    stats = {}
    
    # Basic counts
    stats['total_records'] = len(df)
    stats['total_columns'] = len(df.columns)
    
    # Amount statistics
    if 'amount' in df.columns:
        amounts = df['amount'].dropna()
        stats['amount_stats'] = {
            'total': amounts.sum(),
            'mean': amounts.mean(),
            'median': amounts.median(),
            'min': amounts.min(),
            'max': amounts.max(),
            'std': amounts.std()
        }
    
    # Date range
    if 'date' in df.columns:
        dates = df['date'].dropna()
        if len(dates) > 0:
            stats['date_range'] = {
                'start': dates.min(),
                'end': dates.max(),
                'span_days': (dates.max() - dates.min()).days
            }
    
    # Unique counts
    for col in ['donor_name', 'recipient', 'state', 'city']:
        if col in df.columns:
            stats[f'unique_{col}'] = df[col].nunique()
    
    # Data quality
    stats['data_quality'] = {
        'null_counts': df.isnull().sum().to_dict(),
        'duplicate_rows': df.duplicated().sum()
    }
    
    return stats

def export_to_excel(data_dict, filename):
    """Export multiple dataframes to Excel with different sheets."""
    import io
    
    buffer = io.BytesIO()
    
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        for sheet_name, df in data_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # Add formatting
        workbook = writer.book
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#D7E4BC',
            'border': 1
        })
        
        for sheet_name in data_dict.keys():
            worksheet = writer.sheets[sheet_name]
            worksheet.set_row(0, None, header_format)
    
    return buffer

def calculate_growth_rates(df, date_col='date', value_col='amount', period='M'):
    """Calculate growth rates over time periods."""
    if date_col not in df.columns or value_col not in df.columns:
        return pd.DataFrame()
    
    # Group by time period
    period_data = df.groupby(df[date_col].dt.to_period(period))[value_col].sum()
    
    # Calculate growth rates
    growth_rates = period_data.pct_change() * 100
    
    return pd.DataFrame({
        'period': period_data.index.astype(str),
        'value': period_data.values,
        'growth_rate': growth_rates.values
    })

def identify_top_contributors(df, n=10):
    """Identify top contributors by various metrics."""
    if 'donor_name' not in df.columns or 'amount' not in df.columns:
        return {}
    
    top_contributors = {}
    
    # By total amount
    top_contributors['by_amount'] = (
        df.groupby('donor_name')['amount']
        .sum()
        .sort_values(ascending=False)
        .head(n)
        .to_dict()
    )
    
    # By contribution count
    top_contributors['by_count'] = (
        df['donor_name']
        .value_counts()
        .head(n)
        .to_dict()
    )
    
    # By average amount
    top_contributors['by_avg_amount'] = (
        df.groupby('donor_name')['amount']
        .mean()
        .sort_values(ascending=False)
        .head(n)
        .to_dict()
    )
    
    return top_contributors

def generate_date_features(df, date_col='date'):
    """Generate additional date-based features."""
    if date_col not in df.columns:
        return df
    
    df_copy = df.copy()
    
    # Extract date components
    df_copy['year'] = df_copy[date_col].dt.year
    df_copy['month'] = df_copy[date_col].dt.month
    df_copy['day'] = df_copy[date_col].dt.day
    df_copy['weekday'] = df_copy[date_col].dt.day_name()
    df_copy['quarter'] = df_copy[date_col].dt.quarter
    
    # Political calendar features
    df_copy['is_election_year'] = df_copy['year'] % 2 == 0  # Even years are election years
    df_copy['days_to_election'] = df_copy.apply(
        lambda row: calculate_days_to_next_election(row[date_col]), axis=1
    )
    
    return df_copy

def calculate_days_to_next_election(date):
    """Calculate days to next election (simplified - assumes November elections)."""
    try:
        year = date.year
        election_date = datetime(year, 11, 1)  # Simplified to November 1st
        
        if date > election_date:
            # Next election is next year
            election_date = datetime(year + 1, 11, 1)
        
        return (election_date - date).days
    except:
        return 0

def create_donor_profiles(df):
    """Create comprehensive donor profiles."""
    if 'donor_name' not in df.columns:
        return pd.DataFrame()
    
    profiles = df.groupby('donor_name').agg({
        'amount': ['count', 'sum', 'mean', 'std', 'min', 'max'],
        'date': ['min', 'max'],
        'recipient': lambda x: x.nunique() if 'recipient' in df.columns else 0,
        'state': lambda x: x.iloc[0] if 'state' in df.columns else ''
    })
    
    # Flatten column names
    profiles.columns = ['_'.join(col).strip() if col[1] else col[0] for col in profiles.columns]
    
    # Calculate additional metrics
    profiles['contribution_span_days'] = (
        profiles['date_max'] - profiles['date_min']
    ).dt.days
    
    profiles['avg_contributions_per_month'] = profiles.apply(
        lambda row: row['amount_count'] / max(1, row['contribution_span_days'] / 30.44),
        axis=1
    )
    
    return profiles.reset_index()
