# NYC Campaign Finance Board Analysis System

## Project Overview
This system analyzes NYC Campaign Finance Board (CFB) data, including political contributions, expenditures, intermediaries, and voter records. Features advanced AI capabilities including semantic search, anomaly detection, predictive analytics, and network analysis.

### AI Capabilities (August 23, 2025)
- **Anomaly Detection**: Identifies unusual contribution patterns
- **Semantic Search**: Natural language search across 10,000+ contributors
- **Network Analysis**: Maps contributor-recipient relationships
- **Predictive Analytics**: Forecasts future contributions and donor value
- **Enhanced Matching**: Finds household networks and relationships
- **NLP Features**: Sentiment analysis and entity extraction

## Optimized Pipeline Architecture (August 23, 2025)

### Streamlined Scripts (7 core scripts)
The pipeline has been optimized from 20+ redundant scripts to 7 focused, high-performance scripts:

1. **`fast_voter_import.py`** - Ultra-fast voter data import (1,280 records/second)
   - Imports voter CSV files with name/address normalization
   - Handles duplicate detection via voter_id
   - Currently loaded: 7,287 Kings County Republican voters

2. **`fast_contributor_import.py`** - High-speed contribution data import
   - Processes 2M+ contribution records efficiently
   - Preserves city/state/ZIP for geocoding
   - Handles $700M+ in contribution data

3. **`fast_expenditure_import.py`** - Optimized expenditure import
   - Imports campaign expenditure records
   - Links to recipients and election cycles
   - Processes refund dates and purpose codes

4. **`fast_intermediary_import.py`** - Intermediary contribution processing
   - Identifies and links intermediary relationships
   - Creates intermediary records with normalization
   - Links contributions to intermediaries

5. **`normalize_contributors.py`** - Name parsing and organization separation
   - Splits full names into first/middle/last components
   - Separates organizations (2,131) from individuals (577,737)
   - Calculates contribution totals per contributor

6. **`geocode_optimized.py`** - Deduplicating geocoding pipeline
   - Uses Census API with Nominatim backup
   - Caches geocoded addresses to minimize API calls
   - Processes voters, contributors, and organizations

7. **`fast_voter_matching.py`** - Geographic and name-based matching
   - Matches voters to contributors using coordinates
   - Calculates match confidence scores
   - Identifies exact address and proximity matches

### Database Schema
Enhanced schema with geographic capabilities:
- **voters** - 7,287 records with latitude/longitude
- **contributors** - Individual contributors with geocoding
- **organizations** - Separated organizational contributors
- **contributions** - 2M+ contribution records (import ongoing)
- **expenditures** - Campaign expenditure records
- **intermediaries** - Bundler/intermediary records
- **voter_contributor_matches** - Match results with confidence scores

### Key Technical Features
- **Performance**: Batch processing with 10,000+ record chunks
- **Geocoding**: Deduplication system (e.g., geocode "Brooklyn, NY 11218" once for 500+ records)
- **Matching**: Multi-factor scoring including name similarity, distance, and ZIP codes
- **Error Handling**: Transaction rollback and comprehensive error reporting
- **Storage**: Replit Object Storage integration for large CSV files

## Running the Pipeline

### Data Import Sequence
```bash
# 1. Import voters
python scripts/fast_voter_import.py

# 2. Import contributions (takes several hours for 2M records)
python scripts/fast_contributor_import.py

# 3. Import expenditures
python scripts/fast_expenditure_import.py

# 4. Import intermediary relationships
python scripts/fast_intermediary_import.py

# 5. Normalize contributor names and separate organizations
python scripts/normalize_contributors.py

# 6. Geocode all addresses
python scripts/geocode_optimized.py

# 7. Run voter-contributor matching
python scripts/fast_voter_matching.py
```

## Current Data Status
- **Voters**: 7,287 loaded (122 geocoded)
- **Contributors**: Being imported (64,720+ contributions loaded)
- **Total Contributions**: $24.3M+ loaded (targeting $700M)
- **Organizations**: 2,131 identified
- **Individual Contributors**: 577,737 identified

## Workflows
Active automated workflows:
- **Fast Voter Import** - Background voter data processing
- **Streamlit App** - Main web interface on port 5000

## Technical Stack
- **Database**: PostgreSQL with pg_trgm extension for fuzzy matching
- **Backend**: Python with psycopg2, pandas, SQLAlchemy
- **Frontend**: Streamlit web application
- **Geocoding**: US Census API with Nominatim fallback
- **Storage**: Replit Object Storage for large CSV files

## Performance Metrics
- Voter import: 1,280 records/second
- Contribution import: ~500 records/second
- Geocoding: ~10 addresses/second with caching
- Matching: Sub-second for exact matches, ~5 seconds for proximity matching

## Data Privacy Note
All voter and contributor data is handled in accordance with public records laws. The matching system is designed for legitimate political analysis and compliance purposes only.