"""Fine-tuning capabilities for campaign finance models."""

import pandas as pd
import numpy as np
import pickle
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder
from typing import Dict, List, Tuple, Optional, Any
import json
from datetime import datetime
from ..database.db_manager_v2 import NYCCFBDatabase


class ModelFineTuner:
    """Fine-tune models for campaign finance specific tasks."""
    
    def __init__(self, model_dir: str = 'models'):
        self.db = NYCCFBDatabase()
        self.model_dir = model_dir
        self.models = {}
        self.vectorizers = {}
        self.encoders = {}
        
        # Create model directories
        for subdir in ['classification', 'embeddings', 'clustering', 'analysis']:
            os.makedirs(os.path.join(model_dir, subdir), exist_ok=True)
    
    def prepare_training_data(self, task: str) -> Tuple[pd.DataFrame, List[str], str]:
        """Prepare training data for different tasks."""
        
        if task == 'contributor_type_classification':
            # Classify contributors as Individual, Corporation, PAC, etc.
            query = """
                SELECT 
                    c.id,
                    c.full_name,
                    c.occupation,
                    e.name as employer_name,
                    c.contributor_type,
                    COUNT(cont.id) as num_contributions,
                    SUM(cont.amount) as total_amount,
                    AVG(cont.amount) as avg_amount
                FROM contributors c
                LEFT JOIN employers e ON c.employer_id = e.id
                JOIN contributions cont ON c.id = cont.contributor_id
                WHERE c.contributor_type IS NOT NULL
                GROUP BY c.id, c.full_name, c.occupation, e.name, c.contributor_type
            """
            df = pd.read_sql(query, self.db.engine)
            
            # Create text features
            df['text'] = df.apply(lambda x: f"{x['full_name']} {x['occupation'] or ''} {x['employer_name'] or ''}", axis=1)
            feature_cols = ['text', 'num_contributions', 'total_amount', 'avg_amount']
            target_col = 'contributor_type'
            
        elif task == 'donation_size_prediction':
            # Predict if a donation will be large or small
            query = """
                SELECT 
                    c.full_name as contributor_name,
                    c.occupation,
                    c.contributor_type,
                    r.last_name || ', ' || r.first_name as recipient_name,
                    r.office_sought,
                    cont.amount,
                    CASE 
                        WHEN cont.amount > 1000 THEN 'large'
                        WHEN cont.amount > 250 THEN 'medium'
                        ELSE 'small'
                    END as donation_size
                FROM contributions cont
                JOIN contributors c ON cont.contributor_id = c.id
                JOIN recipients r ON cont.recipient_id = r.id
                WHERE cont.amount > 0
                LIMIT 50000
            """
            df = pd.read_sql(query, self.db.engine)
            
            # Create features
            df['text'] = df.apply(lambda x: f"{x['contributor_name']} {x['occupation'] or ''} to {x['recipient_name']} for {x['office_sought']}", axis=1)
            feature_cols = ['text', 'contributor_type']
            target_col = 'donation_size'
            
        elif task == 'recipient_success_prediction':
            # Predict if a candidate will be successful based on contribution patterns
            query = """
                WITH recipient_stats AS (
                    SELECT 
                        r.id,
                        r.last_name || ', ' || r.first_name as name,
                        r.office_sought,
                        COUNT(DISTINCT cont.contributor_id) as num_contributors,
                        COUNT(cont.id) as num_contributions,
                        SUM(cont.amount) as total_raised,
                        AVG(cont.amount) as avg_contribution,
                        MAX(cont.amount) as max_contribution,
                        STDDEV(cont.amount) as contribution_stddev
                    FROM recipients r
                    JOIN contributions cont ON r.id = cont.recipient_id
                    GROUP BY r.id, name, r.office_sought
                )
                SELECT 
                    *,
                    CASE 
                        WHEN total_raised > (SELECT AVG(total_raised) FROM recipient_stats) THEN 'high_performer'
                        ELSE 'low_performer'
                    END as performance
                FROM recipient_stats
            """
            df = pd.read_sql(query, self.db.engine)
            
            # Create features
            df['text'] = df.apply(lambda x: f"{x['name']} running for {x['office_sought']}", axis=1)
            feature_cols = ['text', 'num_contributors', 'num_contributions', 'total_raised', 
                          'avg_contribution', 'max_contribution', 'contribution_stddev']
            target_col = 'performance'
            
        else:
            raise ValueError(f"Unknown task: {task}")
        
        return df, feature_cols, target_col
    
    def train_classification_model(self, task: str, model_type: str = 'logistic') -> Dict:
        """Train a classification model for a specific task."""
        
        # Prepare data
        df, feature_cols, target_col = self.prepare_training_data(task)
        
        # Separate text and numeric features
        text_features = [col for col in feature_cols if col == 'text']
        numeric_features = [col for col in feature_cols if col != 'text']
        
        # Prepare features
        X_text = None
        if text_features:
            # Vectorize text
            vectorizer = TfidfVectorizer(max_features=1000, ngram_range=(1, 2))
            X_text = vectorizer.fit_transform(df['text'].fillna(''))
            self.vectorizers[task] = vectorizer
        
        X_numeric = None
        if numeric_features:
            X_numeric = df[numeric_features].fillna(0).values
        
        # Combine features
        if X_text is not None and X_numeric is not None:
            X = np.hstack([X_text.toarray(), X_numeric])
        elif X_text is not None:
            X = X_text
        else:
            X = X_numeric
        
        # Encode target
        encoder = LabelEncoder()
        y = encoder.fit_transform(df[target_col])
        self.encoders[task] = encoder
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Train model
        if model_type == 'logistic':
            model = LogisticRegression(max_iter=1000, random_state=42)
        elif model_type == 'random_forest':
            model = RandomForestClassifier(n_estimators=100, random_state=42)
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        model.fit(X_train, y_train)
        
        # Evaluate
        train_score = model.score(X_train, y_train)
        test_score = model.score(X_test, y_test)
        
        # Cross-validation
        cv_scores = cross_val_score(model, X, y, cv=5)
        
        # Predictions for detailed metrics
        y_pred = model.predict(X_test)
        
        # Store model
        self.models[task] = model
        
        # Save model
        model_path = os.path.join(self.model_dir, 'classification', f'{task}_{model_type}.pkl')
        with open(model_path, 'wb') as f:
            pickle.dump({
                'model': model,
                'vectorizer': self.vectorizers.get(task),
                'encoder': encoder,
                'feature_cols': feature_cols,
                'task': task,
                'trained_at': datetime.now().isoformat()
            }, f)
        
        return {
            'task': task,
            'model_type': model_type,
            'train_score': train_score,
            'test_score': test_score,
            'cv_scores': cv_scores.tolist(),
            'cv_mean': cv_scores.mean(),
            'cv_std': cv_scores.std(),
            'num_samples': len(df),
            'num_features': X.shape[1],
            'classes': encoder.classes_.tolist(),
            'classification_report': classification_report(y_test, y_pred, 
                                                         target_names=encoder.classes_),
            'model_path': model_path
        }
    
    def fine_tune_embeddings(self, texts: List[str], labels: List[str], 
                           embedding_type: str = 'tfidf') -> Dict:
        """Fine-tune embeddings for domain-specific similarity."""
        
        if embedding_type == 'tfidf':
            # Create specialized TF-IDF for political contribution data
            vectorizer = TfidfVectorizer(
                max_features=2000,
                ngram_range=(1, 3),
                min_df=2,
                sublinear_tf=True,
                use_idf=True,
                # Add domain-specific vocabulary
                vocabulary=None  # Could add political terms here
            )
            
            embeddings = vectorizer.fit_transform(texts)
            
            # Save the fine-tuned vectorizer
            model_path = os.path.join(self.model_dir, 'embeddings', f'fine_tuned_{embedding_type}.pkl')
            with open(model_path, 'wb') as f:
                pickle.dump({
                    'vectorizer': vectorizer,
                    'embedding_type': embedding_type,
                    'num_texts': len(texts),
                    'vocab_size': len(vectorizer.vocabulary_),
                    'trained_at': datetime.now().isoformat()
                }, f)
            
            return {
                'embedding_type': embedding_type,
                'num_texts': len(texts),
                'embedding_dim': embeddings.shape[1],
                'vocab_size': len(vectorizer.vocabulary_),
                'model_path': model_path
            }
        
        else:
            raise ValueError(f"Unknown embedding type: {embedding_type}")
    
    def load_model(self, task: str, model_type: Optional[str] = None) -> Dict:
        """Load a saved model."""
        
        if model_type:
            model_path = os.path.join(self.model_dir, 'classification', f'{task}_{model_type}.pkl')
        else:
            # Find any model for this task
            import glob
            pattern = os.path.join(self.model_dir, 'classification', f'{task}_*.pkl')
            files = glob.glob(pattern)
            if not files:
                raise FileNotFoundError(f"No model found for task: {task}")
            model_path = files[0]
        
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)
        
        return model_data
    
    def predict(self, task: str, data: pd.DataFrame) -> np.ndarray:
        """Make predictions using a trained model."""
        
        # Load model
        model_data = self.load_model(task)
        model = model_data['model']
        vectorizer = model_data.get('vectorizer')
        encoder = model_data['encoder']
        feature_cols = model_data['feature_cols']
        
        # Prepare features same way as training
        text_features = [col for col in feature_cols if col == 'text']
        numeric_features = [col for col in feature_cols if col != 'text']
        
        X_text = None
        if text_features and vectorizer:
            X_text = vectorizer.transform(data['text'].fillna(''))
        
        X_numeric = None
        if numeric_features:
            X_numeric = data[numeric_features].fillna(0).values
        
        # Combine features
        if X_text is not None and X_numeric is not None:
            X = np.hstack([X_text.toarray(), X_numeric])
        elif X_text is not None:
            X = X_text
        else:
            X = X_numeric
        
        # Predict
        y_pred = model.predict(X)
        
        # Decode predictions
        predictions = encoder.inverse_transform(y_pred)
        
        return predictions
    
    def get_model_info(self) -> Dict[str, List[str]]:
        """Get information about all available models."""
        
        info = {
            'classification': [],
            'embeddings': [],
            'clustering': [],
            'analysis': []
        }
        
        for category in info.keys():
            category_dir = os.path.join(self.model_dir, category)
            if os.path.exists(category_dir):
                for file in os.listdir(category_dir):
                    if file.endswith('.pkl'):
                        info[category].append(file.replace('.pkl', ''))
        
        return info
    
    def train_all_models(self) -> List[Dict]:
        """Train all available models."""
        
        results = []
        
        # Classification tasks
        tasks = [
            ('contributor_type_classification', 'logistic'),
            ('contributor_type_classification', 'random_forest'),
            ('donation_size_prediction', 'logistic'),
            ('recipient_success_prediction', 'random_forest')
        ]
        
        for task, model_type in tasks:
            try:
                result = self.train_classification_model(task, model_type)
                results.append(result)
                print(f"✓ Trained {task} with {model_type}: {result['test_score']:.3f}")
            except Exception as e:
                print(f"✗ Failed to train {task} with {model_type}: {str(e)}")
                results.append({
                    'task': task,
                    'model_type': model_type,
                    'error': str(e)
                })
        
        return results