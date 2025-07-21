"""NYC Campaign Finance Board recipient lookup functionality."""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from typing import Dict, Optional
import time

class CFBRecipientLookup:
    """Lookup recipient information from NYC CFB website."""
    
    def __init__(self):
        self.base_url = "https://www.nyccfb.info"
        self.search_url = f"{self.base_url}/FTMSearch/Home/FTMSearch"
        self.session = requests.Session()
        # Cache to avoid repeated lookups
        self.recipient_cache = {}
    
    def get_recipient_details_from_csv(self, recipid: str, recipients_df: pd.DataFrame) -> Optional[Dict]:
        """
        Get recipient details from a CFB recipients CSV file.
        
        The CFB Data Library provides separate CSV files with recipient details
        that can be downloaded and used for lookups.
        """
        if recipients_df is None or recipients_df.empty:
            return None
        
        # Look for recipient in dataframe
        recipient_row = recipients_df[recipients_df['RECIPID'] == recipid]
        
        if recipient_row.empty:
            return None
        
        row = recipient_row.iloc[0]
        
        # Extract available details
        details = {
            'recipid': recipid,
            'name': row.get('RECIPNAME', ''),
            'office': row.get('OFFICE', ''),
            'party': row.get('PARTY', ''),
            'district': row.get('DISTRICT', ''),
            'borough': row.get('BOROUGH', ''),
            'election_year': row.get('ELECTION_YEAR', ''),
            'participation_status': row.get('PARTICIPATION_STATUS', ''),
            'certification_date': row.get('CERTIFICATION_DATE', ''),
            'termination_date': row.get('TERMINATION_DATE', ''),
            'committee_name': row.get('COMMITTEE_NAME', ''),
            'treasurer': row.get('TREASURER', ''),
            'address': row.get('ADDRESS', ''),
            'phone': row.get('PHONE', ''),
            'email': row.get('EMAIL', ''),
            'website': row.get('WEBSITE', '')
        }
        
        # Clean up None values
        details = {k: v for k, v in details.items() if pd.notna(v) and v != ''}
        
        return details
    
    def scrape_recipient_page(self, recipid: str) -> Optional[Dict]:
        """
        Scrape recipient details from CFB website.
        
        Note: This is a fallback method. Always check robots.txt and 
        respect rate limits. Consider caching results.
        """
        # Check cache first
        if recipid in self.recipient_cache:
            return self.recipient_cache[recipid]
        
        try:
            # Construct candidate page URL (this is an example pattern)
            # The actual URL pattern would need to be determined from the CFB website
            candidate_url = f"{self.base_url}/follow-the-money/candidates/{recipid}"
            
            # Add delay to be respectful
            time.sleep(1)
            
            response = self.session.get(candidate_url, timeout=10)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Parse candidate details (these selectors would need to be updated based on actual HTML)
            details = {
                'recipid': recipid,
                'scraped': True
            }
            
            # Example parsing (would need actual selectors)
            name_elem = soup.find('h1', class_='candidate-name')
            if name_elem:
                details['name'] = name_elem.text.strip()
            
            office_elem = soup.find('span', class_='office')
            if office_elem:
                details['office'] = office_elem.text.strip()
            
            party_elem = soup.find('span', class_='party')
            if party_elem:
                details['party'] = party_elem.text.strip()
            
            # Cache the result
            self.recipient_cache[recipid] = details
            
            return details
            
        except Exception as e:
            print(f"Error scraping recipient {recipid}: {e}")
            return None
    
    def bulk_enrich_recipients(self, recipient_ids: list, recipients_csv_path: str = None) -> pd.DataFrame:
        """
        Enrich multiple recipients with additional details.
        
        Args:
            recipient_ids: List of recipient IDs to look up
            recipients_csv_path: Optional path to a CFB recipients CSV file
        
        Returns:
            DataFrame with enriched recipient information
        """
        results = []
        
        # Load recipients CSV if provided
        recipients_df = None
        if recipients_csv_path:
            try:
                recipients_df = pd.read_csv(recipients_csv_path)
                print(f"Loaded {len(recipients_df)} recipients from CSV")
            except Exception as e:
                print(f"Could not load recipients CSV: {e}")
        
        # Process each recipient
        for recipid in recipient_ids:
            details = {'recipid': recipid}
            
            # Try CSV lookup first
            if recipients_df is not None:
                csv_details = self.get_recipient_details_from_csv(recipid, recipients_df)
                if csv_details:
                    details.update(csv_details)
            
            # If no CSV data, try scraping (commented out by default)
            # if len(details) == 1:  # Only has recipid
            #     scraped_details = self.scrape_recipient_page(recipid)
            #     if scraped_details:
            #         details.update(scraped_details)
            
            results.append(details)
        
        return pd.DataFrame(results)


# Example usage for getting borough/district info
def get_recipient_district_info(office_code: str, details: Dict) -> Dict:
    """
    Extract district/borough information based on office type.
    """
    district_info = {}
    
    if office_code == '4':  # Borough President
        # Extract borough from office name or other fields
        borough = details.get('borough', '')
        if not borough and 'office' in details:
            # Try to extract from office name (e.g., "Borough President - Manhattan")
            office_name = details['office']
            for borough_name in ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island']:
                if borough_name in office_name:
                    borough = borough_name
                    break
        district_info['borough'] = borough
    
    elif office_code == '5':  # City Council
        # Extract district number
        district = details.get('district', '')
        if not district and 'office' in details:
            # Try to extract from office name (e.g., "City Council - District 1")
            match = re.search(r'District\s+(\d+)', details['office'])
            if match:
                district = int(match.group(1))
        district_info['district'] = district
    
    return district_info