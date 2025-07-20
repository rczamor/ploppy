# Political Contribution Data Analyzer

## Overview

This is an AI-powered application for analyzing NYC Campaign Finance Board political contribution data using a PostgreSQL graph database and open source language models. The system enables natural language queries on political contribution patterns, donor networks, and campaign finance relationships.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Database Architecture
- **Database**: PostgreSQL with graph database capabilities for political contribution relationships
- **Schema Design**: Normalized tables for Elections, Contributors, Recipients, Contributions, Employers, Intermediaries, Filings, and Locations
- **Name Parsing**: Automatic parsing of names into last, first, and middle initial fields
- **Code Mappings**: All NYC CFB codes (office, borough, candidate class, etc.) mapped to human-readable values for UI display

### Backend Architecture  
- **Modular Design**: Component-based architecture with separate modules for different functionalities
- **Data Source**: NYC Campaign Finance Board CSV data files from object storage
- **Language Models**: Open source models (Sentence Transformers, spaCy, FAISS) for classification and analysis
- **Natural Language Queries**: PostgreSQL graph queries for exploring donor networks and contribution patterns

## Key Components

### Data Processing (`data_processor.py`)
- **Purpose**: Handles data loading, cleaning, and preprocessing
- **Features**: 
  - Column name standardization with mapping for common variations
  - Data validation and cleaning
  - Derived feature generation
  - Handles null contributor names by creating "Anonymous Contributor" entries
- **Input**: Raw political contribution CSV data (1.6M records)
- **Output**: Cleaned and standardized DataFrame
- **Import Status**: Fixed null name handling issue, now importing successfully

### AI Analyzer (`ai_analyzer.py`)
- **Purpose**: AI-powered analysis using OpenAI GPT-4o
- **Features**:
  - Comprehensive data summarization
  - Pattern detection and insights generation
  - Anomaly detection
  - Recommendations generation
- **Model**: OpenAI GPT-4o (latest model as of May 2024)
- **Integration**: Uses environment variable for API key security

### AI Search (`ai_search.py`)
- **Purpose**: Advanced semantic search and analysis
- **Libraries**: Gensim (Word2Vec, Doc2Vec), NLTK, TextBlob, scikit-learn
- **Features**:
  - Semantic contributor search with query expansion
  - Duplicate detection using multiple similarity metrics
  - Natural language query processing
  - Advanced embeddings using ensemble methods
- **Fallback**: TF-IDF vectorization when advanced models unavailable

### AI Embeddings (`ai_embeddings.py`)
- **Purpose**: Advanced text embeddings and similarity analysis
- **Techniques**:
  - Ensemble embeddings (TF-IDF + LDA + NMF)
  - Topic modeling with Latent Dirichlet Allocation
  - Non-negative Matrix Factorization
  - Hierarchical clustering with optimal cluster detection
- **Features**:
  - Semantic search with nearest neighbors
  - Entity similarity analysis with type detection
  - Key phrase extraction
  - Topic keyword extraction

### ML Clustering (`ml_clustering.py`)
- **Purpose**: Machine learning-based donor segmentation
- **Algorithms**: K-means clustering, DBSCAN, Isolation Forest
- **Features**:
  - Donor behavior clustering
  - Feature engineering for donor profiles
  - Cluster statistical analysis
- **Preprocessing**: StandardScaler for feature normalization, PCA for dimensionality reduction

### Compliance Checker (`compliance_checker.py`)
- **Purpose**: Regulatory compliance validation
- **Features**:
  - Federal and state contribution limit checking
  - Data completeness validation
  - Duplicate detection
  - Date and amount validation
- **Limits**: Configurable federal and state-specific contribution limits

### Visualizations (`visualizations.py`)
- **Purpose**: Interactive data visualization creation
- **Library**: Plotly for interactive charts
- **Chart Types**: Time series, geographic maps, distribution charts, correlation matrices
- **Design**: Consistent color scheme and responsive layouts

### Utilities (`utils.py`)
- **Purpose**: Common utility functions
- **Features**:
  - Currency formatting with intelligent scaling (K/M notation)
  - Data validation with comprehensive error reporting
  - Column mapping for data standardization

## Data Flow

1. **Data Upload**: User uploads CSV file through Streamlit interface
2. **Validation**: Initial data validation using `validate_data()` function
3. **Processing**: Data cleaning and standardization via `DataProcessor`
4. **Analysis Pipeline**:
   - AI analysis for insights and patterns
   - ML clustering for donor segmentation
   - Compliance checking for regulatory validation
   - Visualization generation
5. **Results Display**: Interactive dashboard with multiple analysis views
6. **Session Persistence**: Results cached in Streamlit session state

## External Dependencies

### Core Libraries
- **Streamlit**: Web application framework
- **Pandas/NumPy**: Data manipulation and analysis
- **Plotly**: Interactive visualizations
- **Scikit-learn**: Machine learning algorithms

### AI/ML Services
- **OpenAI API**: GPT-4o model for advanced analysis
- **API Key Management**: Environment variable based configuration

### Data Processing
- **DateTime**: Date/time manipulation
- **Regular Expressions**: Data cleaning and validation
- **IO**: File handling utilities

## Deployment Strategy

### Environment Setup
- **Python Environment**: Requires Python with scientific computing stack
- **API Keys**: OpenAI API key must be set as environment variable `OPENAI_API_KEY`
- **Dependencies**: All dependencies managed through standard Python package managers

### Streamlit Configuration
- **Page Config**: Wide layout with expanded sidebar
- **Caching**: Resource caching for performance optimization
- **Session Management**: Stateful session handling for data persistence

### Security Considerations
- **API Key Security**: Environment variable based API key management
- **Data Privacy**: Client-side data processing, no persistent storage
- **Input Validation**: Comprehensive data validation before processing

### Scalability Features
- **Modular Architecture**: Easy to extend with new analysis modules
- **Caching Strategy**: Efficient resource utilization through Streamlit caching
- **Configurable Limits**: Adjustable compliance limits and analysis parameters

## Notable Design Decisions

### AI Model Choice
- **Decision**: Use OpenAI GPT-4o as the primary AI model
- **Rationale**: Latest and most capable model available as of May 2024
- **Constraint**: Explicitly configured not to change unless requested by user

### Modular Architecture
- **Decision**: Separate modules for each major functionality
- **Rationale**: Maintainability, testability, and extensibility
- **Benefits**: Easy to add new analysis types or modify existing ones

### Streamlit Framework
- **Decision**: Use Streamlit for the web interface
- **Rationale**: Rapid development for data science applications
- **Trade-offs**: Less customization flexibility but faster development

### No Database Dependency
- **Decision**: In-memory data processing without persistent storage
- **Rationale**: Simplicity and privacy - data stays with the user
- **Limitation**: Analysis must be re-run for each session