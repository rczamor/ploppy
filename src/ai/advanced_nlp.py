"""Advanced NLP capabilities for Phase 2 AI modernization."""

import pandas as pd
import numpy as np
from textblob import TextBlob
import nltk
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import LabelEncoder
from typing import List, Dict, Tuple, Optional
import re
from collections import Counter
from .simple_network import SimpleGraph, SimpleNetworkAnalyzer

# Download required NLTK data
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('maxent_ne_chunker', quiet=True)
    nltk.download('words', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)
except:
    pass

class AdvancedNLP:
    """Advanced NLP processing for contribution data."""
    
    def __init__(self):
        self.stop_words = set(nltk.corpus.stopwords.words('english'))
        self.entity_cache = {}
        
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities from text."""
        
        if not text:
            return {'persons': [], 'organizations': [], 'locations': []}
        
        # Cache check
        if text in self.entity_cache:
            return self.entity_cache[text]
        
        entities = {
            'persons': [],
            'organizations': [],
            'locations': []
        }
        
        # Simple pattern-based extraction
        # Person names (capitalized words)
        person_pattern = r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'
        persons = re.findall(person_pattern, text)
        entities['persons'] = list(set(persons))
        
        # Organizations (words ending in LLC, Inc, Corp, etc.)
        org_pattern = r'\b[\w\s]+(?:LLC|Inc|Corp|Corporation|Company|Group|Associates|Partners)\b'
        orgs = re.findall(org_pattern, text, re.IGNORECASE)
        entities['organizations'] = list(set(orgs))
        
        # Locations (common NYC locations)
        location_keywords = ['Brooklyn', 'Manhattan', 'Queens', 'Bronx', 'Staten Island', 
                           'New York', 'NYC', 'NY', 'Avenue', 'Street', 'Road', 'Plaza']
        for keyword in location_keywords:
            if keyword.lower() in text.lower():
                entities['locations'].append(keyword)
        
        # Cache result
        self.entity_cache[text] = entities
        
        return entities
    
    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """Analyze sentiment of text."""
        
        if not text:
            return {'polarity': 0.0, 'subjectivity': 0.0, 'sentiment': 'neutral'}
        
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity
        
        # Classify sentiment
        if polarity > 0.1:
            sentiment = 'positive'
        elif polarity < -0.1:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        return {
            'polarity': polarity,
            'subjectivity': subjectivity,
            'sentiment': sentiment
        }
    
    def extract_keywords(self, texts: List[str], top_n: int = 10) -> List[Tuple[str, float]]:
        """Extract top keywords from a collection of texts."""
        
        if not texts:
            return []
        
        # Combine all texts
        combined_text = ' '.join(texts)
        
        # Tokenize and filter
        words = nltk.word_tokenize(combined_text.lower())
        words = [w for w in words if w.isalnum() and w not in self.stop_words and len(w) > 2]
        
        # Count frequencies
        word_freq = Counter(words)
        
        # Calculate TF-IDF scores (simplified)
        total_words = len(words)
        keywords = []
        
        for word, freq in word_freq.most_common(top_n * 2):
            tf = freq / total_words
            # Simple IDF approximation
            idf = np.log(len(texts) / (1 + sum(1 for text in texts if word in text.lower())))
            score = tf * idf
            keywords.append((word, score))
        
        # Sort by score and return top N
        keywords.sort(key=lambda x: x[1], reverse=True)
        return keywords[:top_n]
    
    def categorize_occupation(self, occupation: str) -> str:
        """Categorize occupation into broader categories."""
        
        if not occupation:
            return 'Unknown'
        
        occupation_lower = occupation.lower()
        
        # Define categories and keywords
        categories = {
            'Legal': ['lawyer', 'attorney', 'counsel', 'legal', 'law firm', 'paralegal'],
            'Finance': ['banker', 'finance', 'investment', 'trader', 'analyst', 'accountant', 'cpa'],
            'Real Estate': ['real estate', 'realtor', 'property', 'developer', 'broker'],
            'Healthcare': ['doctor', 'physician', 'nurse', 'medical', 'hospital', 'health'],
            'Technology': ['software', 'engineer', 'developer', 'tech', 'it', 'programmer'],
            'Education': ['teacher', 'professor', 'educator', 'school', 'university'],
            'Government': ['government', 'public', 'city', 'state', 'federal', 'municipal'],
            'Business': ['ceo', 'president', 'manager', 'executive', 'director', 'owner'],
            'Retail': ['retail', 'store', 'shop', 'sales', 'merchant'],
            'Construction': ['construction', 'contractor', 'builder', 'architect'],
            'Retired': ['retired', 'retiree'],
            'Student': ['student'],
            'Unemployed': ['unemployed', 'not employed'],
            'Homemaker': ['homemaker', 'housewife', 'househusband']
        }
        
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in occupation_lower:
                    return category
        
        return 'Other'
    
    def analyze_contribution_purpose(self, purpose_code: str, description: str = None) -> Dict:
        """Analyze the purpose of a contribution."""
        
        analysis = {
            'category': 'Unknown',
            'subcategory': '',
            'keywords': [],
            'sentiment': 'neutral'
        }
        
        # Map purpose codes to categories
        purpose_map = {
            'campaign': ['CAMP', 'ELECT', 'PRIMARY', 'GENERAL'],
            'fundraising': ['FUND', 'EVENT', 'DINNER', 'GALA'],
            'advertising': ['AD', 'MEDIA', 'TV', 'RADIO', 'DIGITAL'],
            'consulting': ['CONSULT', 'STRATEGY', 'ADVICE'],
            'travel': ['TRAVEL', 'TRANSPORT', 'FLIGHT', 'HOTEL'],
            'staff': ['SALARY', 'PAYROLL', 'STAFF', 'WAGES'],
            'office': ['OFFICE', 'RENT', 'UTILITIES', 'SUPPLIES']
        }
        
        if purpose_code:
            code_upper = purpose_code.upper()
            for category, codes in purpose_map.items():
                if any(code in code_upper for code in codes):
                    analysis['category'] = category
                    break
        
        # Analyze description if provided
        if description:
            # Extract keywords
            keywords = re.findall(r'\b[A-Za-z]+\b', description)
            analysis['keywords'] = [k.lower() for k in keywords if len(k) > 3][:5]
            
            # Sentiment analysis
            sentiment = self.analyze_sentiment(description)
            analysis['sentiment'] = sentiment['sentiment']
        
        return analysis


class NetworkAnalyzer(SimpleNetworkAnalyzer):
    """Analyze networks and relationships in contribution data."""
    
    def __init__(self):
        super().__init__()
        
    def build_contributor_network(self, contributions: pd.DataFrame) -> SimpleGraph:
        """Build a network of contributors and recipients."""
        
        # Use parent class implementation
        return super().build_contributor_network(contributions)
    
    def find_influential_nodes(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Find most influential nodes in the network."""
        
        # Use simplified implementation from parent class
        return super().find_influential_nodes(top_n)
    
    def find_communities(self) -> Dict[int, List[str]]:
        """Find communities in the network."""
        
        # Use simplified implementation from parent class
        return super().find_communities()
    
    def calculate_network_metrics(self) -> Dict:
        """Calculate overall network metrics."""
        
        # Use simplified implementation from parent class
        return super().calculate_network_metrics()


class ContributionPredictor:
    """Predictive modeling for contributions."""
    
    def __init__(self):
        self.models = {}
        self.encoders = {}
        
    def prepare_features(self, data: pd.DataFrame) -> np.ndarray:
        """Prepare features for modeling."""
        
        features = []
        
        # Numeric features
        if 'amount' in data.columns:
            features.append(data['amount'].fillna(0).values.reshape(-1, 1))
        
        # Time features
        if 'date' in data.columns:
            dates = pd.to_datetime(data['date'], errors='coerce')
            features.append(dates.dt.month.fillna(0).values.reshape(-1, 1))
            features.append(dates.dt.dayofweek.fillna(0).values.reshape(-1, 1))
        
        # Categorical features
        for col in ['contributor_type', 'state', 'occupation_category']:
            if col in data.columns:
                if col not in self.encoders:
                    self.encoders[col] = LabelEncoder()
                    encoded = self.encoders[col].fit_transform(data[col].fillna('Unknown'))
                else:
                    encoded = self.encoders[col].transform(data[col].fillna('Unknown'))
                features.append(encoded.reshape(-1, 1))
        
        if features:
            return np.hstack(features)
        else:
            return np.array([])
    
    def predict_contribution_amount(self, contributor_data: Dict) -> float:
        """Predict likely contribution amount for a contributor."""
        
        # Simple heuristic-based prediction
        base_amount = 500
        
        # Adjust based on occupation
        occupation = contributor_data.get('occupation', '').lower()
        if any(word in occupation for word in ['ceo', 'president', 'executive']):
            base_amount *= 5
        elif any(word in occupation for word in ['lawyer', 'attorney', 'doctor']):
            base_amount *= 3
        elif any(word in occupation for word in ['retired', 'student']):
            base_amount *= 0.5
        
        # Adjust based on location
        location = contributor_data.get('city', '').lower()
        if 'manhattan' in location:
            base_amount *= 1.5
        elif 'brooklyn' in location:
            base_amount *= 1.2
        
        # Add some randomness
        base_amount *= np.random.uniform(0.8, 1.2)
        
        return min(max(base_amount, 25), 5000)  # Cap between $25 and $5000
    
    def predict_contributor_segment(self, contributor_data: Dict) -> str:
        """Predict contributor segment."""
        
        # Simple rule-based segmentation
        amount = contributor_data.get('total_contributions', 0)
        count = contributor_data.get('contribution_count', 1)
        
        if amount > 10000:
            return 'Major Donor'
        elif amount > 2500:
            return 'Large Donor'
        elif count > 5:
            return 'Frequent Donor'
        elif amount > 500:
            return 'Regular Donor'
        else:
            return 'Small Donor'
    
    def forecast_contributions(self, historical_data: pd.DataFrame, periods: int = 3) -> pd.DataFrame:
        """Forecast future contributions."""
        
        if historical_data.empty or 'date' not in historical_data.columns:
            return pd.DataFrame()
        
        # Group by month
        historical_data['date'] = pd.to_datetime(historical_data['date'])
        monthly = historical_data.groupby(pd.Grouper(key='date', freq='M')).agg({
            'amount': 'sum',
            'id': 'count'
        }).rename(columns={'id': 'count'})
        
        if len(monthly) < 2:
            return pd.DataFrame()
        
        # Simple moving average forecast
        window = min(3, len(monthly))
        forecast = []
        
        for i in range(periods):
            # Use last 'window' months for prediction
            recent_avg_amount = monthly['amount'].iloc[-window:].mean()
            recent_avg_count = monthly['count'].iloc[-window:].mean()
            
            # Add trend component
            if len(monthly) > 1:
                trend_amount = (monthly['amount'].iloc[-1] - monthly['amount'].iloc[-2]) * 0.5
                trend_count = (monthly['count'].iloc[-1] - monthly['count'].iloc[-2]) * 0.5
            else:
                trend_amount = 0
                trend_count = 0
            
            forecast.append({
                'month': monthly.index[-1] + pd.DateOffset(months=i+1),
                'predicted_amount': max(0, recent_avg_amount + trend_amount),
                'predicted_count': max(0, int(recent_avg_count + trend_count))
            })
        
        return pd.DataFrame(forecast)