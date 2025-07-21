# NYC Campaign Finance Board Data Explorer

## Project Overview
An advanced AI-powered platform for comprehensive NYC campaign finance data analysis, leveraging machine learning and big data techniques to provide deep insights into political contribution dynamics.

### Key Technologies
- **Frontend**: Streamlit for interactive web interface
- **Database**: PostgreSQL for large-scale data storage
- **Backend**: Python for advanced data processing
- **ORM**: SQLAlchemy for database interactions
- **Analytics**: Pandas and scikit-learn
- **AI Integration**: OpenAI for intelligent insights

## Project Structure
```
.
├── app_v2.py                    # Main Streamlit application
├── src/                         # Source code modules
│   ├── database/                # Database management
│   │   ├── db_manager_v2.py     # Database operations
│   │   ├── code_mappings.py     # Data mappings and utilities
│   │   └── schema_update.sql    # Database schema updates
│   ├── ai/                      # AI/ML modules
│   │   ├── ai_search.py         # AI-powered search and analysis
│   │   ├── ai_embeddings.py     # Advanced text embeddings
│   │   ├── ai_time_series.py    # Time series forecasting
│   │   ├── ai_entity_extraction.py # Entity extraction & NLP
│   │   ├── ai_fine_tuning.py    # Model training & fine-tuning
│   │   ├── ai_analyzer.py       # Data analysis
│   │   ├── sentence_transformer_wrapper.py # Sentence transformers integration
│   │   └── ai_sentence_transformers.py
│   └── utils/                   # Utility modules
│       ├── utils.py             # General utilities
│       ├── visualizations.py    # Data visualizations
│       ├── compliance_checker.py # Compliance checking
│       ├── data_processor.py    # Data processing
│       ├── ml_clustering.py     # ML clustering
│       └── graph_analysis.py    # Graph analysis
├── scripts/                     # Import and maintenance scripts
│   ├── direct_import.py         # Direct data import
│   ├── import_expenditures.py   # Expenditure import
│   ├── import_intermediary_contributions.py
│   └── monitor_all_imports.py   # Import monitoring
├── logs/                        # Log files
│   ├── import_progress.txt      # Import progress tracking
│   └── expenditures_import_progress.txt
└── archive/                     # Deprecated/old files

```

## Recent Changes (July 21, 2025)
- **Organized project structure**: Moved 35+ files into logical directories
- **Created module structure**: src/database, src/ai, src/utils for better organization
- **Cleaned up logs**: Moved active log files to logs/ directory, removed unused logs
- **Updated import paths**: Fixed all import statements to use new module structure
- **Archived old files**: Moved deprecated scripts to archive/ directory
- **Completed AI System Implementation**: Fully implemented all components from the AI system plan

## AI System Features (Completed July 21, 2025)
The comprehensive AI system for campaign finance analysis is now fully implemented with the following capabilities:

### 1. **Time Series Forecasting** (ai_time_series.py)
- Predict future contribution patterns using polynomial regression
- Analyze trends, seasonality, and growth metrics
- Support for election-wide and candidate-specific forecasts
- Visual forecasting with confidence intervals

### 2. **Entity Extraction & NLP** (ai_entity_extraction.py)
- Extract and classify entities from text using NLTK
- Identify contributors, organizations, PACs, and unions
- Build entity networks based on shared connections
- Standardize organization names and addresses

### 3. **Model Training & Fine-tuning** (ai_fine_tuning.py)
- Train custom models for campaign finance tasks:
  - Contributor type classification
  - Donation size prediction
  - Recipient success prediction
- Save and load trained models
- Model evaluation with cross-validation

### 4. **Advanced Embeddings** (ai_embeddings.py)
- TF-IDF, LDA, and NMF for text analysis
- Topic modeling and key phrase extraction
- Clustering and similarity search
- Ensemble embedding methods

### 5. **Semantic Search** (ai_search.py)
- Natural language query processing
- Advanced contributor search with ML
- Anomaly detection using Isolation Forest
- Duplicate donor detection
- Integration with all AI modules

### 6. **Natural Language Interface**
- Convert plain English questions to SQL queries
- Smart pattern matching for queries
- Support for complex analytical questions

### Model Storage Structure
```
models/
├── embeddings/      # Text embedding models
├── classification/  # Trained classifiers
├── clustering/      # Clustering models
└── analysis/        # Statistical models
```

### Available Analysis Types in UI
1. Contribution Patterns - ML-based pattern analysis
2. Donor Networks - Network analysis of contributors
3. Duplicate Detection - Find duplicate donors
4. Semantic Search - AI-powered search
5. Advanced Clustering - Group similar contributors
6. Topic Analysis - Extract themes from data
7. Time Series Forecasting - Predict future contributions
8. Entity Extraction - Extract and analyze entities
9. Model Training & Fine-tuning - Train custom models

### Technical Implementation
- Uses scikit-learn, NLTK, Gensim, and TextBlob
- No external API dependencies - fully self-contained
- Local model training and inference
- Privacy-focused with all data staying local
- Real-time analysis for datasets up to 1M records

## Database Schema
The application uses PostgreSQL with the following main tables:
- contributions - Political contributions data
- expenditures - Campaign expenditures
- contributors - Donor information
- recipients - Candidate/committee information
- intermediaries - Intermediary organizations
- locations - Geographic data
- employers - Employer information
- elections - Election cycle data

## Workflows
1. **Direct Import**: Imports contribution data from CSV files
2. **Import Expenditures**: Imports expenditure data
3. **Import Intermediaries**: Imports intermediary contribution data
4. **Streamlit App**: Main web application (port 5000)

## User Preferences
- Keep code well-organized in logical directories
- Maintain clean root directory structure
- Use descriptive file and directory names
- Document major architectural changes

## Development Guidelines
- Always use relative imports within src/ modules
- Keep logs in the logs/ directory
- Archive old/deprecated code instead of deleting
- Update this file when making structural changes