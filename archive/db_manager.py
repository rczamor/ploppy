import pandas as pd
import psycopg2
import os
from sqlalchemy import create_engine, text
import uuid
from datetime import datetime
import numpy as np
import re
from typing import Dict, List, Optional, Tuple
from replit.object_storage import Client as ObjectStorageClient

class PoliticalContributionDB:
    """Database manager for political contribution graph database."""
    
    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        self.engine = create_engine(self.database_url)
        self.storage_client = None
    
    def load_csv_data(self, csv_path: str) -> pd.DataFrame:
        """Load and validate CSV data."""
        try:
            df = pd.read_csv(csv_path)
            print(f"Loaded {len(df)} records from {csv_path}")
            return df
        except Exception as e:
            raise Exception(f"Failed to load CSV: {str(e)}")
    
    def normalize_name(self, name: str) -> str:
        """Normalize names for better matching."""
        if pd.isna(name) or name == '':
            return ''
        
        # Convert to uppercase, remove extra spaces, punctuation
        normalized = str(name).upper().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Handle common variations
        normalized = normalized.replace(' JR', '').replace(' SR', '').replace(' III', '').replace(' II', '')
        normalized = normalized.replace('COMMITTEE', 'CMTE').replace('POLITICAL ACTION COMMITTEE', 'PAC')
        
        return normalized
    
    def detect_donor_type(self, name: str) -> str:
        """Classify donor type based on name patterns."""
        if pd.isna(name) or name == '':
            return 'unknown'
        
        name_upper = str(name).upper()
        
        # Organization indicators
        org_indicators = ['LLC', 'INC', 'CORP', 'COMMITTEE', 'PAC', 'ASSOCIATION', 
                         'UNION', 'FOUNDATION', 'TRUST', 'PARTNERSHIP', 'LTD', 'CO']
        
        if any(indicator in name_upper for indicator in org_indicators):
            return 'organization'
        
        # Committee/PAC indicators
        if 'COMMITTEE' in name_upper or 'PAC' in name_upper:
            return 'committee'
        
        # Check for individual patterns (comma suggests Last, First format)
        if ',' in name:
            return 'individual'
        
        # Default to individual for simple names
        return 'individual'
    
    def get_or_create_location(self, city: str, state: str, zip_code: str = None) -> str:
        """Get or create location record, return UUID."""
        try:
            # Normalize location data
            city = str(city).title().strip() if pd.notna(city) else ''
            state = str(state).upper().strip()[:2] if pd.notna(state) else ''
            zip_code = str(zip_code)[:5] if pd.notna(zip_code) else ''
            
            # Map states to regions
            region_map = {
                'Northeast': ['ME', 'NH', 'VT', 'MA', 'RI', 'CT', 'NY', 'NJ', 'PA'],
                'Southeast': ['DE', 'MD', 'DC', 'VA', 'WV', 'KY', 'TN', 'NC', 'SC', 'GA', 'FL', 'AL', 'MS', 'AR', 'LA'],
                'Midwest': ['OH', 'MI', 'IN', 'WI', 'IL', 'MN', 'IA', 'MO', 'ND', 'SD', 'NE', 'KS'],
                'Southwest': ['OK', 'TX', 'AZ', 'NM'],
                'West': ['MT', 'WY', 'CO', 'UT', 'ID', 'WA', 'OR', 'NV', 'CA', 'AK', 'HI']
            }
            
            region = 'Unknown'
            for region_name, states in region_map.items():
                if state in states:
                    region = region_name
                    break
            
            with self.engine.connect() as conn:
                # Check if location exists
                result = conn.execute(text("""
                    SELECT id FROM locations 
                    WHERE city = :city AND state = :state AND zip_code = :zip_code
                """), {'city': city, 'state': state, 'zip_code': zip_code})
                
                location = result.fetchone()
                if location:
                    return str(location[0])
                
                # Create new location
                location_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO locations (id, city, state, zip_code, region)
                    VALUES (:id, :city, :state, :zip_code, :region)
                """), {
                    'id': location_id,
                    'city': city,
                    'state': state,
                    'zip_code': zip_code,
                    'region': region
                })
                conn.commit()
                return location_id
                
        except Exception as e:
            print(f"Error creating location: {e}")
            return str(uuid.uuid4())  # Return a default UUID if failed
    
    def get_or_create_donor(self, name: str, occupation: str = None, employer: str = None) -> str:
        """Get or create donor record, return UUID."""
        try:
            normalized_name = self.normalize_name(name)
            donor_type = self.detect_donor_type(name)
            
            with self.engine.connect() as conn:
                # Check if donor exists
                result = conn.execute(text("""
                    SELECT id FROM donors WHERE normalized_name = :normalized_name
                """), {'normalized_name': normalized_name})
                
                donor = result.fetchone()
                if donor:
                    return str(donor[0])
                
                # Create new donor
                donor_id = str(uuid.uuid4())
                
                # Parse individual names
                first_name, last_name = '', ''
                if donor_type == 'individual' and ',' in name:
                    parts = name.split(',', 1)
                    last_name = parts[0].strip()
                    first_name = parts[1].strip() if len(parts) > 1 else ''
                
                conn.execute(text("""
                    INSERT INTO donors (id, name, normalized_name, donor_type, first_name, last_name, occupation, employer)
                    VALUES (:id, :name, :normalized_name, :donor_type, :first_name, :last_name, :occupation, :employer)
                """), {
                    'id': donor_id,
                    'name': name,
                    'normalized_name': normalized_name,
                    'donor_type': donor_type,
                    'first_name': first_name,
                    'last_name': last_name,
                    'occupation': occupation,
                    'employer': employer
                })
                conn.commit()
                return donor_id
                
        except Exception as e:
            print(f"Error creating donor: {e}")
            return str(uuid.uuid4())
    
    def get_or_create_recipient(self, name: str, office: str = None, party: str = None, election_year: int = None) -> str:
        """Get or create recipient record, return UUID."""
        try:
            normalized_name = self.normalize_name(name)
            
            # Detect recipient type
            recipient_type = 'candidate'  # Default
            name_upper = str(name).upper()
            if 'COMMITTEE' in name_upper or 'PAC' in name_upper:
                recipient_type = 'committee'
            elif 'PARTY' in name_upper:
                recipient_type = 'party'
            
            with self.engine.connect() as conn:
                # Check if recipient exists
                result = conn.execute(text("""
                    SELECT id FROM recipients WHERE normalized_name = :normalized_name
                """), {'normalized_name': normalized_name})
                
                recipient = result.fetchone()
                if recipient:
                    return str(recipient[0])
                
                # Create new recipient
                recipient_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO recipients (id, name, normalized_name, recipient_type, office, party, election_year)
                    VALUES (:id, :name, :normalized_name, :recipient_type, :office, :party, :election_year)
                """), {
                    'id': recipient_id,
                    'name': name,
                    'normalized_name': normalized_name,
                    'recipient_type': recipient_type,
                    'office': office,
                    'party': party,
                    'election_year': election_year
                })
                conn.commit()
                return recipient_id
                
        except Exception as e:
            print(f"Error creating recipient: {e}")
            return str(uuid.uuid4())
    
    def map_cfb_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map CFB (Campaign Finance Board) columns to standard format."""
        # Create a mapped DataFrame with standardized column names
        mapped_df = pd.DataFrame()
        
        # Map donor information
        mapped_df['donor_name'] = df['NAME']
        mapped_df['occupation'] = df['OCCUPATION']
        mapped_df['employer'] = df['EMPNAME']
        
        # Map recipient information
        mapped_df['recipient'] = df['RECIPNAME']
        mapped_df['office'] = df['OFFICECD']
        mapped_df['party'] = df['CANCLASS']  # Using candidate class as party proxy
        
        # Map contribution details
        mapped_df['amount'] = df['AMNT']
        mapped_df['date'] = df['DATE']
        
        # Map location information
        mapped_df['city'] = df['CITY']
        mapped_df['state'] = df['STATE']
        mapped_df['zip'] = df['ZIP']
        
        # Additional fields
        mapped_df['election_year'] = df['ELECTION']
        mapped_df['payment_method'] = df['PAY_METHOD']
        mapped_df['match_amount'] = df['MATCHAMNT']
        
        return mapped_df
    
    def import_contributions_from_dataframe(self, df: pd.DataFrame, batch_size: int = 1000) -> Dict:
        """Import political contribution data from DataFrame into graph database."""
        try:
            results = {
                'total_rows': len(df),
                'successful_imports': 0,
                'failed_imports': 0,
                'errors': []
            }
            
            print(f"Starting import of {len(df)} contributions...")
            
            # Process in batches
            for batch_start in range(0, len(df), batch_size):
                batch_end = min(batch_start + batch_size, len(df))
                batch_df = df.iloc[batch_start:batch_end]
                
                print(f"Processing batch {batch_start//batch_size + 1}: rows {batch_start}-{batch_end}")
                
                for idx, row in batch_df.iterrows():
                    try:
                        # Extract and validate core fields
                        donor_name = row.get('donor_name', row.get('contributor_name', ''))
                        recipient_name = row.get('recipient', row.get('candidate', ''))
                        amount = float(row.get('amount', 0))
                        transaction_date = pd.to_datetime(row.get('date', row.get('transaction_date', '')))
                        
                        if not donor_name or not recipient_name or amount <= 0:
                            results['failed_imports'] += 1
                            continue
                        
                        # Get or create related entities
                        donor_id = self.get_or_create_donor(
                            donor_name,
                            row.get('occupation', ''),
                            row.get('employer', '')
                        )
                        
                        recipient_id = self.get_or_create_recipient(
                            recipient_name,
                            row.get('office', ''),
                            row.get('party', ''),
                            transaction_date.year if pd.notna(transaction_date) else None
                        )
                        
                        location_id = self.get_or_create_location(
                            row.get('city', ''),
                            row.get('state', ''),
                            row.get('zip', '')
                        )
                        
                        # Calculate derived features
                        election_cycle = ((transaction_date.year - 1) // 2) * 2 + 1 if pd.notna(transaction_date) else None
                        
                        # Determine amount category
                        if amount <= 50:
                            amount_category = 'small'
                        elif amount <= 200:
                            amount_category = 'medium'
                        elif amount <= 1000:
                            amount_category = 'large'
                        else:
                            amount_category = 'major'
                        
                        # Insert contribution
                        with self.engine.connect() as conn:
                            contribution_id = str(uuid.uuid4())
                            conn.execute(text("""
                                INSERT INTO contributions (
                                    id, donor_id, recipient_id, location_id, amount, transaction_date,
                                    amount_category, election_cycle, quarter, month, day_of_year, weekday
                                ) VALUES (
                                    :id, :donor_id, :recipient_id, :location_id, :amount, :transaction_date,
                                    :amount_category, :election_cycle, :quarter, :month, :day_of_year, :weekday
                                )
                            """), {
                                'id': contribution_id,
                                'donor_id': donor_id,
                                'recipient_id': recipient_id,
                                'location_id': location_id,
                                'amount': amount,
                                'transaction_date': transaction_date,
                                'amount_category': amount_category,
                                'election_cycle': election_cycle,
                                'quarter': transaction_date.quarter if pd.notna(transaction_date) else None,
                                'month': transaction_date.month if pd.notna(transaction_date) else None,
                                'day_of_year': transaction_date.dayofyear if pd.notna(transaction_date) else None,
                                'weekday': transaction_date.weekday() if pd.notna(transaction_date) else None
                            })
                            conn.commit()
                        
                        results['successful_imports'] += 1
                        
                    except Exception as e:
                        results['failed_imports'] += 1
                        results['errors'].append(f"Row {idx}: {str(e)}")
                        if len(results['errors']) < 10:  # Limit error collection
                            print(f"Error processing row {idx}: {e}")
            
            print(f"Import completed: {results['successful_imports']} successful, {results['failed_imports']} failed")
            return results
            
        except Exception as e:
            raise Exception(f"Import failed: {str(e)}")
    
    def execute_graph_query(self, query: str) -> pd.DataFrame:
        """Execute a graph query and return results."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                return df
        except Exception as e:
            raise Exception(f"Query failed: {str(e)}")
    
    def get_database_stats(self) -> Dict:
        """Get database statistics."""
        try:
            with self.engine.connect() as conn:
                stats = {}
                
                # Count tables
                tables = ['donors', 'recipients', 'contributions', 'locations']
                for table in tables:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    stats[f'{table}_count'] = result.fetchone()[0]
                
                # Get recent activity
                result = conn.execute(text("""
                    SELECT COUNT(*) as recent_contributions
                    FROM contributions 
                    WHERE transaction_date >= CURRENT_DATE - INTERVAL '30 days'
                """))
                stats['recent_contributions'] = result.fetchone()[0]
                
                return stats
        except Exception as e:
            return {'error': str(e)}
    
    def connect_to_object_storage(self, bucket_id: str = 'data_files') -> bool:
        """Connect to Replit Object Storage bucket."""
        try:
            self.storage_client = ObjectStorageClient(bucket_id=bucket_id)
            print(f"Connected to object storage bucket: {bucket_id}")
            return True
        except Exception as e:
            print(f"Failed to connect to bucket {bucket_id}: {e}")
            # Try without bucket_id (default bucket)
            try:
                self.storage_client = ObjectStorageClient()
                print("Connected to default object storage bucket")
                return True
            except Exception as e2:
                print(f"Failed to connect to default bucket: {e2}")
                return False
    
    def list_bucket_files(self, prefix: str = "", file_extension: str = ".csv") -> List[str]:
        """List files in the object storage bucket."""
        try:
            if not self.storage_client:
                if not self.connect_to_object_storage():
                    return []
            
            all_objects = list(self.storage_client.list(prefix=prefix))
            
            # Extract file names from objects
            all_files = [obj.name if hasattr(obj, 'name') else str(obj) for obj in all_objects]
            
            # Filter by extension if specified
            if file_extension:
                files = [f for f in all_files if f.lower().endswith(file_extension.lower())]
            else:
                files = all_files
            
            print(f"Found {len(files)} files with extension '{file_extension}'")
            return files
        except Exception as e:
            print(f"Error listing files: {e}")
            return []
    
    def download_and_import_csv(self, filename: str, batch_size: int = 1000) -> Dict:
        """Download CSV from object storage and import to database."""
        try:
            if not self.storage_client:
                if not self.connect_to_object_storage():
                    raise Exception("Could not connect to object storage")
            
            print(f"Downloading {filename} from object storage...")
            
            # Check if file exists
            if not self.storage_client.exists(filename):
                raise Exception(f"File {filename} not found in bucket")
            
            # Download file content as text
            csv_content = self.storage_client.download_as_text(filename)
            
            # Convert to DataFrame
            import io
            df = pd.read_csv(io.StringIO(csv_content))
            print(f"Successfully loaded {len(df)} records from {filename}")
            
            # Import to database
            return self.import_contributions_from_dataframe(df, batch_size)
            
        except Exception as e:
            print(f"Error downloading/importing {filename}: {e}")
            return {
                'total_rows': 0,
                'successful_imports': 0,
                'failed_imports': 0,
                'errors': [str(e)]
            }
    
    def download_csv_to_dataframe(self, filename: str) -> pd.DataFrame:
        """Download CSV from object storage and return as DataFrame."""
        try:
            if not self.storage_client:
                if not self.connect_to_object_storage():
                    raise Exception("Could not connect to object storage")
            
            print(f"Downloading {filename} from object storage...")
            
            # Check if file exists
            if not self.storage_client.exists(filename):
                raise Exception(f"File {filename} not found in bucket")
            
            # Download file content as text
            csv_content = self.storage_client.download_as_text(filename)
            
            # Convert to DataFrame
            import io
            df = pd.read_csv(io.StringIO(csv_content))
            print(f"Successfully loaded {len(df)} records from {filename}")
            
            return df
            
        except Exception as e:
            print(f"Error downloading {filename}: {e}")
            return pd.DataFrame()