"""Database manager for NYC Campaign Finance Board political contribution data."""

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
from .code_mappings import *
import requests
import json

class NYCCFBDatabase:
    """Database manager for NYC Campaign Finance Board data with new schema."""
    
    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        print(f"Connecting to database...")
        try:
            self.engine = create_engine(self.database_url)
            # Test the connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database connection established successfully")
        except Exception as e:
            print(f"Failed to connect to database: {e}")
            raise
        self.storage_client = None
    
    def connect_to_object_storage(self, bucket_id: str = '') -> bool:
        """Connect to Replit Object Storage bucket."""
        try:
            if bucket_id:
                self.storage_client = ObjectStorageClient(bucket_id=bucket_id)
            else:
                self.storage_client = ObjectStorageClient()
            print(f"Connected to object storage bucket: {bucket_id}")
            return True
        except Exception as e:
            print(f"Failed to connect to bucket: {e}")
            return False
    
    def normalize_name(self, name: str) -> str:
        """Normalize names for better matching."""
        if pd.isna(name) or name == '':
            return ''
        
        # Convert to uppercase, remove extra spaces, punctuation
        normalized = str(name).upper().strip()
        normalized = re.sub(r'[^\w\s,]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Handle common variations
        normalized = normalized.replace(' JR', '').replace(' SR', '').replace(' III', '').replace(' II', '')
        normalized = normalized.replace('COMMITTEE', 'CMTE').replace('POLITICAL ACTION COMMITTEE', 'PAC')
        
        return normalized
    
    def get_or_create_election(self, election_cycle: str) -> str:
        """Get or create election record, return UUID."""
        try:
            with self.engine.connect() as conn:
                # Check if election exists
                result = conn.execute(text("""
                    SELECT id FROM elections WHERE election_cycle = :cycle
                """), {'cycle': election_cycle})
                
                election = result.fetchone()
                if election:
                    return str(election[0])
                
                # Parse election cycle
                year, election_type = parse_election_cycle(election_cycle)
                
                # Create new election
                election_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO elections (id, election_cycle, election_year, election_type)
                    VALUES (:id, :cycle, :year, :type)
                """), {
                    'id': election_id,
                    'cycle': election_cycle,
                    'year': year,
                    'type': election_type
                })
                conn.commit()
                return election_id
                
        except Exception as e:
            print(f"Error creating election: {e}")
            return str(uuid.uuid4())
    
    def get_or_create_employer(self, emp_name: str, emp_street_no: str = None, 
                               emp_street_name: str = None, emp_city: str = None, 
                               emp_state: str = None) -> Optional[str]:
        """Get or create employer record, return UUID."""
        if pd.isna(emp_name) or not emp_name:
            return None
        
        try:
            normalized_name = self.normalize_name(emp_name)
            
            with self.engine.connect() as conn:
                # Check if employer exists
                result = conn.execute(text("""
                    SELECT id FROM employers WHERE normalized_name = :name
                """), {'name': normalized_name})
                
                employer = result.fetchone()
                if employer:
                    return str(employer[0])
                
                # Create new employer
                employer_id = str(uuid.uuid4())
                
                # Determine employer type
                employer_type = 'Organization' if not is_individual_name(emp_name) else 'Individual Employer'
                
                conn.execute(text("""
                    INSERT INTO employers (id, name, normalized_name, street_number, 
                                         street_name, city, state, employer_type)
                    VALUES (:id, :name, :normalized_name, :street_no, :street_name, 
                            :city, :state, :employer_type)
                """), {
                    'id': employer_id,
                    'name': emp_name,
                    'normalized_name': normalized_name,
                    'street_no': str(emp_street_no) if pd.notna(emp_street_no) else None,
                    'street_name': str(emp_street_name) if pd.notna(emp_street_name) else None,
                    'city': str(emp_city).title() if pd.notna(emp_city) else None,
                    'state': str(emp_state).upper()[:2] if pd.notna(emp_state) else None,
                    'employer_type': employer_type
                })
                conn.commit()
                return employer_id
                
        except Exception as e:
            print(f"Error creating employer: {e}")
            return None
    
    def get_or_create_contributor(self, row: pd.Series) -> str:
        """Get or create contributor record from data row."""
        try:
            name = row.get('NAME', '')
            if pd.isna(name) or not name:
                # For null names, use "Anonymous" or skip based on amount
                amount = float(row.get('AMNT', 0)) if pd.notna(row.get('AMNT')) else 0
                if amount == 0:
                    return None  # Skip zero-amount anonymous contributions
                name = "Anonymous Contributor"
            
            normalized_name = self.normalize_name(name)
            
            with self.engine.connect() as conn:
                # Check if contributor exists
                result = conn.execute(text("""
                    SELECT id FROM contributors WHERE normalized_name = :name
                """), {'name': normalized_name})
                
                contributor = result.fetchone()
                if contributor:
                    return str(contributor[0])
                
                # Parse name
                name_parts = parse_name(name)
                
                # Get employer
                employer_id = self.get_or_create_employer(
                    row.get('EMPNAME'),
                    row.get('EMPSTRNO'),
                    row.get('EMPSTRNAME'),
                    row.get('EMPCITY'),
                    row.get('EMPSTATE')
                )
                
                # Determine contributor type
                c_code = row.get('C_CODE', 'UNKN')
                contributor_type = get_contributor_type(c_code)
                is_individual = is_individual_name(name, c_code)
                
                # Create new contributor
                contributor_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO contributors (id, full_name, last_name, first_name, 
                                            middle_initial, normalized_name, contributor_type,
                                            c_code, occupation, employer_id, is_individual)
                    VALUES (:id, :full_name, :last_name, :first_name, :middle_initial,
                            :normalized_name, :contributor_type, :c_code, :occupation,
                            :employer_id, :is_individual)
                """), {
                    'id': contributor_id,
                    'full_name': name,
                    'last_name': name_parts['last_name'],
                    'first_name': name_parts['first_name'],
                    'middle_initial': name_parts['middle_initial'],
                    'normalized_name': normalized_name,
                    'contributor_type': contributor_type,
                    'c_code': c_code,
                    'occupation': row.get('OCCUPATION'),
                    'employer_id': employer_id,
                    'is_individual': is_individual
                })
                conn.commit()
                return contributor_id
                
        except Exception as e:
            print(f"Error creating contributor: {e}")
            return None
    
    def get_or_create_recipient(self, row: pd.Series) -> str:
        """Get or create recipient record from data row."""
        try:
            recipid = str(row.get('RECIPID', ''))
            if not recipid:
                return None
            
            with self.engine.connect() as conn:
                # Check if recipient exists
                result = conn.execute(text("""
                    SELECT id FROM recipients WHERE recipid = :recipid
                """), {'recipid': recipid})
                
                recipient = result.fetchone()
                if recipient:
                    return str(recipient[0])
                
                # Parse recipient information
                recip_name = row.get('RECIPNAME', '')
                name_parts = parse_name(recip_name)
                normalized_name = self.normalize_name(recip_name)
                
                # Get office information
                office_code = str(row.get('OFFICECD', ''))
                office_name = get_office_name(office_code)
                
                # Get candidate class
                canclass = row.get('CANCLASS', 'UN')
                canclass_desc = get_candidate_class_desc(canclass)
                
                # Determine recipient type
                is_individual = is_individual_name(recip_name)
                recipient_type = 'Candidate' if is_individual else 'Committee'
                
                # Create new recipient
                recipient_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO recipients (id, recipid, full_name, last_name, first_name,
                                          middle_initial, normalized_name, recipient_type,
                                          office_code, office_name, canclass, canclass_description,
                                          committee_code, is_individual)
                    VALUES (:id, :recipid, :full_name, :last_name, :first_name,
                            :middle_initial, :normalized_name, :recipient_type,
                            :office_code, :office_name, :canclass, :canclass_desc,
                            :committee_code, :is_individual)
                """), {
                    'id': recipient_id,
                    'recipid': recipid,
                    'full_name': recip_name,
                    'last_name': name_parts['last_name'],
                    'first_name': name_parts['first_name'],
                    'middle_initial': name_parts['middle_initial'],
                    'normalized_name': normalized_name,
                    'recipient_type': recipient_type,
                    'office_code': office_code,
                    'office_name': office_name,
                    'canclass': canclass,
                    'canclass_desc': canclass_desc,
                    'committee_code': row.get('COMMITTEE'),
                    'is_individual': is_individual
                })
                conn.commit()
                return recipient_id
                
        except Exception as e:
            print(f"Error creating recipient: {e}")
            return None
    
    def get_or_create_location(self, row: pd.Series) -> Optional[str]:
        """Get or create location record from data row."""
        try:
            # Extract location fields
            city = str(row.get('CITY', '')).strip() if pd.notna(row.get('CITY')) else ''
            state = str(row.get('STATE', '')).strip()[:2] if pd.notna(row.get('STATE')) else ''
            
            # Skip if no location data
            if not city and not state:
                return None
            
            with self.engine.connect() as conn:
                # Build location key
                street_no = str(row.get('STRNO', '')) if pd.notna(row.get('STRNO')) else ''
                street_name = str(row.get('STRNAME', '')) if pd.notna(row.get('STRNAME')) else ''
                apartment = str(row.get('APARTMENT', '')) if pd.notna(row.get('APARTMENT')) else ''
                zip_code = str(row.get('ZIP', ''))[:5] if pd.notna(row.get('ZIP')) else ''
                borough_code = row.get('BOROUGHCD', '')
                
                # Check if location exists
                result = conn.execute(text("""
                    SELECT id FROM locations 
                    WHERE city = :city AND state = :state 
                    AND COALESCE(zip_code, '') = :zip
                    AND COALESCE(street_number, '') = :street_no
                    AND COALESCE(street_name, '') = :street_name
                """), {
                    'city': city,
                    'state': state,
                    'zip': zip_code,
                    'street_no': street_no,
                    'street_name': street_name
                })
                
                location = result.fetchone()
                if location:
                    return str(location[0])
                
                # Create new location
                location_id = str(uuid.uuid4())
                
                # Handle borough code - ensure it's a single character or None
                if pd.notna(borough_code) and str(borough_code) != 'nan' and len(str(borough_code)) == 1:
                    borough_code_clean = str(borough_code)
                else:
                    borough_code_clean = None
                    
                borough_name = get_borough_name(borough_code_clean) if borough_code_clean else None
                
                # Determine region
                region = 'NYC' if borough_code_clean in ['M', 'K', 'Q', 'X', 'S'] else 'Outside NYC'
                
                conn.execute(text("""
                    INSERT INTO locations (id, street_number, street_name, apartment,
                                         city, state, zip_code, borough_code, borough_name, region)
                    VALUES (:id, :street_no, :street_name, :apartment,
                            :city, :state, :zip_code, :borough_code, :borough_name, :region)
                """), {
                    'id': location_id,
                    'street_no': street_no if street_no else None,
                    'street_name': street_name if street_name else None,
                    'apartment': apartment if apartment else None,
                    'city': city.title(),
                    'state': state.upper(),
                    'zip_code': zip_code if zip_code else None,
                    'borough_code': borough_code_clean,
                    'borough_name': borough_name,
                    'region': region
                })
                conn.commit()
                return location_id
                
        except Exception as e:
            print(f"Error creating location: {e}")
            return None
    
    def get_or_create_intermediary(self, row: pd.Series) -> Optional[str]:
        """Get or create intermediary record if present."""
        try:
            interm_name = row.get('INTERMNAME')
            if pd.isna(interm_name) or not interm_name:
                return None
            
            normalized_name = self.normalize_name(interm_name)
            
            with self.engine.connect() as conn:
                # Check if intermediary exists
                result = conn.execute(text("""
                    SELECT id FROM intermediaries WHERE normalized_name = :name
                """), {'name': normalized_name})
                
                intermediary = result.fetchone()
                if intermediary:
                    return str(intermediary[0])
                
                # Parse name
                name_parts = parse_name(interm_name)
                
                # Get intermediary employer
                employer_id = self.get_or_create_employer(
                    row.get('INTEMPNAME'),
                    row.get('INTEMPSTNO'),
                    row.get('INTEMPSTNM'),
                    row.get('INTEMPCITY'),
                    row.get('INTEMPST')
                )
                
                # Create intermediary location
                int_location_data = pd.Series({
                    'STRNO': row.get('INTSTRNO'),
                    'STRNAME': row.get('INTSTRNM'),
                    'APARTMENT': row.get('INTAPTNO'),
                    'CITY': row.get('INTCITY'),
                    'STATE': row.get('INTST'),
                    'ZIP': row.get('INTZIP')
                })
                location_id = self.get_or_create_location(int_location_data)
                
                # Create new intermediary
                intermediary_id = str(uuid.uuid4())
                c_code = row.get('INT_C_CODE', 'IND')
                
                conn.execute(text("""
                    INSERT INTO intermediaries (id, intermediary_number, full_name,
                                              last_name, first_name, middle_initial,
                                              normalized_name, c_code, occupation,
                                              employer_id, location_id)
                    VALUES (:id, :number, :full_name, :last_name, :first_name,
                            :middle_initial, :normalized_name, :c_code, :occupation,
                            :employer_id, :location_id)
                """), {
                    'id': intermediary_id,
                    'number': str(row.get('INTERMNO', '')) if pd.notna(row.get('INTERMNO')) else None,
                    'full_name': interm_name,
                    'last_name': name_parts['last_name'],
                    'first_name': name_parts['first_name'],
                    'middle_initial': name_parts['middle_initial'],
                    'normalized_name': normalized_name,
                    'c_code': c_code,
                    'occupation': row.get('INTOCCUPA'),
                    'employer_id': employer_id,
                    'location_id': location_id
                })
                conn.commit()
                return intermediary_id
                
        except Exception as e:
            print(f"Error creating intermediary: {e}")
            return None
    
    def get_or_create_filing(self, row: pd.Series, election_id: str, recipient_id: str) -> str:
        """Get or create filing record."""
        try:
            with self.engine.connect() as conn:
                # Check if filing exists
                filing_raw = row.get('FILING', 0)
                try:
                    filing_num = int(filing_raw) if pd.notna(filing_raw) else 0
                except (ValueError, TypeError):
                    filing_num = 0  # Default for non-numeric values
                
                result = conn.execute(text("""
                    SELECT id FROM filings 
                    WHERE recipient_id = :recipient_id 
                    AND filing_number = :filing_num
                    AND election_id = :election_id
                """), {
                    'recipient_id': recipient_id,
                    'filing_num': filing_num,
                    'election_id': election_id
                })
                
                filing = result.fetchone()
                if filing:
                    return str(filing[0])
                
                # Create new filing
                filing_id = str(uuid.uuid4())
                schedule_type = row.get('SCHEDULE', '')
                schedule_desc = get_schedule_description(schedule_type)
                
                conn.execute(text("""
                    INSERT INTO filings (id, election_id, recipient_id, filing_number,
                                       schedule_type, schedule_description, page_number)
                    VALUES (:id, :election_id, :recipient_id, :filing_number,
                            :schedule_type, :schedule_desc, :page_number)
                """), {
                    'id': filing_id,
                    'election_id': election_id,
                    'recipient_id': recipient_id,
                    'filing_number': filing_num,
                    'schedule_type': schedule_type,
                    'schedule_desc': schedule_desc,
                    'page_number': int(row.get('PAGENO')) if pd.notna(row.get('PAGENO')) else None
                })
                conn.commit()
                return filing_id
                
        except Exception as e:
            print(f"Error creating filing: {e}")
            return str(uuid.uuid4())
    
    def import_contribution_row(self, row: pd.Series) -> bool:
        """Import a single contribution row."""
        try:
            # Get or create related entities
            election_id = self.get_or_create_election(row.get('ELECTION', ''))
            contributor_id = self.get_or_create_contributor(row)
            recipient_id = self.get_or_create_recipient(row)
            
            # Skip if missing key entities
            if not contributor_id or not recipient_id:
                return False
            
            location_id = self.get_or_create_location(row)
            intermediary_id = self.get_or_create_intermediary(row)
            filing_id = self.get_or_create_filing(row, election_id, recipient_id)
            
            # Parse dates
            trans_date = pd.to_datetime(row.get('DATE'), errors='coerce')
            refund_date = pd.to_datetime(row.get('REFUNDDATE'), errors='coerce')
            
            # Convert NaT to None for PostgreSQL
            trans_date = trans_date if pd.notna(trans_date) else None
            refund_date = refund_date if pd.notna(refund_date) else None
            
            # Get amounts
            amount = float(row.get('AMNT', 0)) if pd.notna(row.get('AMNT')) else 0
            match_amount = float(row.get('MATCHAMNT', 0)) if pd.notna(row.get('MATCHAMNT')) else 0
            prev_amount = float(row.get('PREVAMNT', 0)) if pd.notna(row.get('PREVAMNT')) else 0
            
            # Get payment method
            pay_method = int(row.get('PAY_METHOD')) if pd.notna(row.get('PAY_METHOD')) else None
            pay_method_desc = get_payment_method(pay_method) if pay_method else None
            
            # Get adjustment type
            adj_type = int(row.get('ADJTYPECD')) if pd.notna(row.get('ADJTYPECD')) else None
            adj_type_desc = get_adjustment_type(adj_type) if adj_type else None
            
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
                        id, contributor_id, recipient_id, intermediary_id, election_id,
                        filing_id, location_id, reference_number, sequence_number,
                        transaction_date, refund_date, amount, match_amount, previous_amount,
                        payment_method, payment_method_desc, purpose_code, exemption_code,
                        adjustment_type_code, adjustment_type_desc, registered_recipient,
                        segregated_account, amount_category, election_cycle, quarter,
                        month, day_of_year, weekday
                    ) VALUES (
                        :id, :contributor_id, :recipient_id, :intermediary_id, :election_id,
                        :filing_id, :location_id, :ref_no, :seq_no, :trans_date, :refund_date,
                        :amount, :match_amount, :prev_amount, :pay_method, :pay_method_desc,
                        :purpose_code, :exempt_code, :adj_type, :adj_type_desc, :registered,
                        :segregated, :amount_cat, :election_cycle, :quarter, :month,
                        :day_of_year, :weekday
                    )
                """), {
                    'id': contribution_id,
                    'contributor_id': contributor_id,
                    'recipient_id': recipient_id,
                    'intermediary_id': intermediary_id,
                    'election_id': election_id,
                    'filing_id': filing_id,
                    'location_id': location_id,
                    'ref_no': row.get('REFNO'),
                    'seq_no': int(row.get('SEQUENCENO')) if pd.notna(row.get('SEQUENCENO')) else None,
                    'trans_date': trans_date,
                    'refund_date': refund_date,
                    'amount': amount,
                    'match_amount': match_amount,
                    'prev_amount': prev_amount,
                    'pay_method': pay_method,
                    'pay_method_desc': pay_method_desc,
                    'purpose_code': row.get('PURPOSECD'),
                    'exempt_code': row.get('EXEMPTCD'),
                    'adj_type': adj_type,
                    'adj_type_desc': adj_type_desc,
                    'registered': row.get('RR_IND') == 'Y',
                    'segregated': row.get('SEG_IND') == 'Y',
                    'amount_cat': amount_category,
                    'election_cycle': row.get('ELECTION'),
                    'quarter': trans_date.quarter if trans_date else None,
                    'month': trans_date.month if trans_date else None,
                    'day_of_year': trans_date.dayofyear if trans_date else None,
                    'weekday': trans_date.weekday() if trans_date else None
                })
                conn.commit()
            
            return True
            
        except Exception as e:
            print(f"Error importing contribution: {e}")
            return False
    
    def import_contributions_batch(self, df: pd.DataFrame, batch_size: int = 500) -> Dict:
        """Import a batch of contributions."""
        results = {
            'total_rows': len(df),
            'successful_imports': 0,
            'failed_imports': 0,
            'errors': []
        }
        
        for idx, row in df.iterrows():
            try:
                if self.import_contribution_row(row):
                    results['successful_imports'] += 1
                else:
                    results['failed_imports'] += 1
            except Exception as e:
                results['failed_imports'] += 1
                if len(results['errors']) < 10:
                    results['errors'].append(f"Row {idx}: {str(e)}")
            
            # Progress update every 100 rows
            if (idx + 1) % 100 == 0:
                print(f"Processed {idx + 1}/{len(df)} rows...")
        
        return results
    
    def get_database_stats(self) -> Dict:
        """Get database statistics."""
        try:
            with self.engine.connect() as conn:
                stats = {}
                
                # Count tables
                tables = ['elections', 'contributors', 'recipients', 'contributions', 
                         'employers', 'intermediaries', 'filings', 'locations']
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
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute a query and return results as DataFrame."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                return df
        except Exception as e:
            raise Exception(f"Query failed: {str(e)}")
    
    def download_csv_to_dataframe(self, filename: str) -> pd.DataFrame:
        """Download CSV from object storage and return as DataFrame."""
        try:
            if not self.storage_client:
                raise Exception("Not connected to object storage")
            
            print(f"Downloading {filename} from object storage...")
            
            # Check if file exists
            if not self.storage_client.exists(filename):
                raise Exception(f"File {filename} not found in bucket")
            
            # Download file content as text
            csv_content = self.storage_client.download_as_text(filename)
            
            # Convert to DataFrame
            import io
            df = pd.read_csv(io.StringIO(csv_content), low_memory=False)
            print(f"Successfully loaded {len(df)} records from {filename}")
            
            return df
            
        except Exception as e:
            print(f"Error downloading {filename}: {e}")
            return pd.DataFrame()