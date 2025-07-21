"""Time series analysis for campaign finance data using available libraries."""

import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import PolynomialFeatures
from sklearn.metrics import mean_squared_error, r2_score
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')
from typing import Dict, List, Tuple, Optional
from ..database.db_manager_v2 import NYCCFBDatabase


class ContributionForecaster:
    """Time series forecasting for political contributions."""
    
    def __init__(self):
        self.db = NYCCFBDatabase()
        self.models = {}
        
    def prepare_time_series_data(self, entity_type: str = 'candidate', 
                                entity_id: Optional[int] = None,
                                frequency: str = 'D') -> pd.DataFrame:
        """Prepare time series data for analysis."""
        
        if entity_type == 'candidate':
            query = """
                SELECT 
                    DATE(con.date) as date,
                    r.id as entity_id,
                    r.last_name || ', ' || r.first_name as entity_name,
                    COUNT(con.id) as num_contributions,
                    SUM(con.amount) as total_amount,
                    AVG(con.amount) as avg_amount
                FROM contributions con
                JOIN recipients r ON con.recipient_id = r.id
                WHERE con.date IS NOT NULL
            """
            if entity_id:
                query += f" AND r.id = {entity_id}"
            query += " GROUP BY DATE(con.date), r.id, entity_name"
            
        else:  # election-wide
            query = """
                SELECT 
                    DATE(date) as date,
                    COUNT(id) as num_contributions,
                    SUM(amount) as total_amount,
                    AVG(amount) as avg_amount
                FROM contributions
                WHERE date IS NOT NULL
                GROUP BY DATE(date)
            """
        
        df = pd.read_sql(query, self.db.engine)
        df['date'] = pd.to_datetime(df['date'])
        
        # Resample to requested frequency
        if entity_type == 'candidate' and not entity_id:
            # Multiple entities - process each separately
            return df
        else:
            # Single entity or election-wide
            df = df.set_index('date')
            df = df.resample(frequency).agg({
                'num_contributions': 'sum',
                'total_amount': 'sum',
                'avg_amount': 'mean'
            }).fillna(0)
            
        return df
    
    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create time-based features for forecasting."""
        df = df.copy()
        
        # Time-based features
        df['day_of_week'] = df.index.dayofweek
        df['day_of_month'] = df.index.day
        df['month'] = df.index.month
        df['quarter'] = df.index.quarter
        df['day_of_year'] = df.index.dayofyear
        df['week_of_year'] = df.index.isocalendar().week
        
        # Lag features
        for lag in [1, 7, 14, 30]:
            df[f'lag_{lag}'] = df['total_amount'].shift(lag)
        
        # Rolling statistics
        for window in [7, 14, 30]:
            df[f'rolling_mean_{window}'] = df['total_amount'].rolling(window=window).mean()
            df[f'rolling_std_{window}'] = df['total_amount'].rolling(window=window).std()
            df[f'rolling_max_{window}'] = df['total_amount'].rolling(window=window).max()
            df[f'rolling_min_{window}'] = df['total_amount'].rolling(window=window).min()
        
        # Trend features
        df['days_since_start'] = (df.index - df.index[0]).days
        
        return df.dropna()
    
    def train_forecast_model(self, df: pd.DataFrame, target_col: str = 'total_amount',
                           test_size: int = 30) -> Dict:
        """Train a forecasting model using polynomial regression."""
        
        # Create features
        df_features = self.create_features(df)
        
        # Prepare train/test split
        train_df = df_features[:-test_size]
        test_df = df_features[-test_size:]
        
        # Select features
        feature_cols = [col for col in df_features.columns 
                       if col not in ['total_amount', 'num_contributions', 'avg_amount']]
        
        X_train = train_df[feature_cols]
        y_train = train_df[target_col]
        X_test = test_df[feature_cols]
        y_test = test_df[target_col]
        
        # Train polynomial regression model
        poly = PolynomialFeatures(degree=2, include_bias=False)
        X_train_poly = poly.fit_transform(X_train)
        X_test_poly = poly.transform(X_test)
        
        # Use Ridge regression to handle multicollinearity
        model = Ridge(alpha=1.0)
        model.fit(X_train_poly, y_train)
        
        # Make predictions
        train_pred = model.predict(X_train_poly)
        test_pred = model.predict(X_test_poly)
        
        # Calculate metrics
        train_rmse = np.sqrt(mean_squared_error(y_train, train_pred))
        test_rmse = np.sqrt(mean_squared_error(y_test, test_pred))
        train_r2 = r2_score(y_train, train_pred)
        test_r2 = r2_score(y_test, test_pred)
        
        return {
            'model': model,
            'poly': poly,
            'feature_cols': feature_cols,
            'train_rmse': train_rmse,
            'test_rmse': test_rmse,
            'train_r2': train_r2,
            'test_r2': test_r2,
            'test_predictions': test_pred,
            'test_dates': test_df.index,
            'test_actual': y_test.values
        }
    
    def forecast_future(self, df: pd.DataFrame, model_info: Dict, 
                       days_ahead: int = 30) -> pd.DataFrame:
        """Forecast future contributions."""
        
        # Get the last date
        last_date = df.index[-1]
        
        # Create future dates
        future_dates = pd.date_range(
            start=last_date + timedelta(days=1),
            periods=days_ahead,
            freq='D'
        )
        
        # Create future dataframe
        future_df = pd.DataFrame(index=future_dates)
        
        # Add time features
        future_df['day_of_week'] = future_df.index.dayofweek
        future_df['day_of_month'] = future_df.index.day
        future_df['month'] = future_df.index.month
        future_df['quarter'] = future_df.index.quarter
        future_df['day_of_year'] = future_df.index.dayofyear
        future_df['week_of_year'] = future_df.index.isocalendar().week
        future_df['days_since_start'] = (future_df.index - df.index[0]).days
        
        # For lag and rolling features, use the last known values
        last_values = df['total_amount'].iloc[-30:].values
        
        # Fill in lag features with last known values
        for lag in [1, 7, 14, 30]:
            if lag <= len(last_values):
                future_df[f'lag_{lag}'] = last_values[-lag]
            else:
                future_df[f'lag_{lag}'] = 0
        
        # Use last rolling statistics
        for window in [7, 14, 30]:
            if window <= len(last_values):
                future_df[f'rolling_mean_{window}'] = np.mean(last_values[-window:])
                future_df[f'rolling_std_{window}'] = np.std(last_values[-window:])
                future_df[f'rolling_max_{window}'] = np.max(last_values[-window:])
                future_df[f'rolling_min_{window}'] = np.min(last_values[-window:])
            else:
                future_df[f'rolling_mean_{window}'] = np.mean(last_values)
                future_df[f'rolling_std_{window}'] = np.std(last_values)
                future_df[f'rolling_max_{window}'] = np.max(last_values)
                future_df[f'rolling_min_{window}'] = np.min(last_values)
        
        # Make predictions
        X_future = future_df[model_info['feature_cols']]
        X_future_poly = model_info['poly'].transform(X_future)
        predictions = model_info['model'].predict(X_future_poly)
        
        # Create result dataframe
        forecast_df = pd.DataFrame({
            'date': future_dates,
            'forecast': predictions,
            'forecast_lower': predictions * 0.8,  # Simple confidence interval
            'forecast_upper': predictions * 1.2
        })
        
        return forecast_df
    
    def detect_seasonality(self, df: pd.DataFrame, target_col: str = 'total_amount') -> Dict:
        """Detect seasonal patterns in contributions."""
        
        # Daily seasonality (day of week)
        daily_pattern = df.groupby(df.index.dayofweek)[target_col].mean()
        
        # Monthly seasonality
        monthly_pattern = df.groupby(df.index.month)[target_col].mean()
        
        # Quarterly seasonality
        quarterly_pattern = df.groupby(df.index.quarter)[target_col].mean()
        
        # Calculate strength of seasonality (coefficient of variation)
        daily_cv = daily_pattern.std() / daily_pattern.mean()
        monthly_cv = monthly_pattern.std() / monthly_pattern.mean()
        quarterly_cv = quarterly_pattern.std() / quarterly_pattern.mean()
        
        return {
            'daily_pattern': daily_pattern.to_dict(),
            'monthly_pattern': monthly_pattern.to_dict(),
            'quarterly_pattern': quarterly_pattern.to_dict(),
            'daily_strength': daily_cv,
            'monthly_strength': monthly_cv,
            'quarterly_strength': quarterly_cv,
            'strongest_seasonality': max(
                [('daily', daily_cv), ('monthly', monthly_cv), ('quarterly', quarterly_cv)],
                key=lambda x: x[1]
            )[0]
        }
    
    def analyze_trends(self, df: pd.DataFrame, target_col: str = 'total_amount') -> Dict:
        """Analyze contribution trends over time."""
        
        # Simple linear trend
        X = np.arange(len(df)).reshape(-1, 1)
        y = df[target_col].values
        
        trend_model = LinearRegression()
        trend_model.fit(X, y)
        trend_line = trend_model.predict(X)
        
        # Calculate trend metrics
        slope = trend_model.coef_[0]
        r2 = r2_score(y, trend_line)
        
        # Detect change points (simple method using rolling statistics)
        window = min(30, len(df) // 4)
        rolling_mean = df[target_col].rolling(window=window).mean()
        rolling_std = df[target_col].rolling(window=window).std()
        
        # Z-score for detecting anomalies
        z_scores = np.abs((df[target_col] - rolling_mean) / rolling_std)
        change_points = df.index[z_scores > 3].tolist() if len(z_scores[z_scores > 3]) > 0 else []
        
        # Growth metrics
        if len(df) > 0:
            total_growth = (df[target_col].iloc[-1] - df[target_col].iloc[0]) / df[target_col].iloc[0] * 100
            avg_daily_growth = slope
            momentum = df[target_col].iloc[-7:].mean() / df[target_col].iloc[-30:-7].mean() - 1 if len(df) > 30 else 0
        else:
            total_growth = avg_daily_growth = momentum = 0
        
        return {
            'trend_slope': slope,
            'trend_r2': r2,
            'trend_direction': 'increasing' if slope > 0 else 'decreasing',
            'total_growth_pct': total_growth,
            'avg_daily_growth': avg_daily_growth,
            'momentum': momentum,
            'change_points': [str(cp) for cp in change_points[:5]],  # Top 5 change points
            'volatility': df[target_col].std() / df[target_col].mean() if df[target_col].mean() > 0 else 0
        }