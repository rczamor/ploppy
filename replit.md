# NYC Campaign Finance Board Analysis System

## Project Overview
This system analyzes NYC Campaign Finance Board (CFB) data, including political contributions, expenditures, and now voter contact records. It provides comprehensive analysis tools for understanding campaign finance patterns and matching voter records with contributor data.

## Recent Updates (August 23, 2025)

### Voter Data Integration
- **New Feature**: Voter-Contributor Matching System
  - Created `voters` table in database to store voter contact information
  - Imported voter data from Kings County Republican voter file
  - Built sophisticated matching algorithm to identify voters who are also campaign contributors
  - Implements fuzzy name matching and address verification
  - Calculates match probability scores based on multiple factors

### Database Schema
Added `voters` table with comprehensive fields:
- Personal information (name, gender)
- Address details (full address with normalization)
- Party affiliation data
- Contact information (phone numbers)
- Unique voter IDs for tracking
- Normalized fields for efficient matching

### Matching Capabilities
The system can now:
1. Match voter records with campaign contributor records
2. Calculate match probability based on:
   - Name similarity using fuzzy matching algorithms
   - Address matching with street-level precision
   - ZIP code verification
3. Identify voters who have made political contributions
4. Track contribution amounts and patterns by voter
5. Generate comprehensive reports on voter engagement in campaign finance

### Scripts Added
- `scripts/import_voters.py` - Imports voter data from CSV files
- `scripts/voter_contributor_matching.py` - Full matching analysis
- `scripts/quick_voter_match_demo.py` - Quick demonstration of capabilities

### Current Data Status
- Voters loaded: 3,000+ (import ongoing)
- Contributors in database: 579,921
- Contributions tracked: 1,931,534
- Expenditures: 56,566

## Running the Analysis

### Import Voter Data
```bash
python scripts/import_voters.py
```

### Run Matching Analysis
```bash
# Quick demo
python scripts/quick_voter_match_demo.py

# Full analysis
python scripts/voter_contributor_matching.py
```

## Workflows
The following automated workflows are configured:
- **Direct Import** - Imports contribution data
- **Import Expenditures** - Imports expenditure records
- **Import Intermediaries** - Processes intermediary contributions
- **Import Voters** - Imports voter contact records (background process)
- **Streamlit App** - Main web interface on port 5000

## Technical Architecture
- **Database**: PostgreSQL with full-text search and fuzzy matching extensions
- **Backend**: Python with psycopg2, pandas, SQLAlchemy
- **Frontend**: Streamlit web application
- **Matching Algorithm**: Uses pg_trgm extension for fuzzy text matching
- **Data Processing**: Batch processing with error handling and transaction management

## Key Features
1. **Data Import Pipeline**: Automated import from CFB data files and voter lists
2. **Name Normalization**: Standardizes names for accurate matching
3. **Address Normalization**: Standardizes addresses for geographic matching
4. **Probability Scoring**: Multi-factor matching with confidence scores
5. **Batch Processing**: Efficient processing of large datasets
6. **Error Handling**: Robust error handling with transaction rollback

## Future Enhancements
- Complete import of full voter dataset (7,287 records)
- Expand matching to include employment and occupation data
- Add geographic clustering analysis
- Create visualization dashboards for matched data
- Implement real-time matching for new contributions
- Add export functionality for matched results

## Data Privacy Note
All voter and contributor data is handled in accordance with public records laws. The matching system is designed for legitimate political analysis and compliance purposes only.