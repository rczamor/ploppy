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
│   │   ├── ai_search.py         # AI-powered search
│   │   ├── ai_embeddings.py     # Text embeddings
│   │   ├── ai_analyzer.py       # Data analysis
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