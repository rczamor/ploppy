#!/usr/bin/env python3
"""Geocode voter and contributor addresses using Census Geocoder API."""

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import os
import requests
import time
from datetime import datetime
import json

DATABASE_URL = os.environ.get('DATABASE_URL')

# Census Geocoder endpoints
CENSUS_SINGLE_ADDRESS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
CENSUS_BATCH = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"

def geocode_single_address(address):
    """Geocode a single address using Census API."""
    try:
        params = {
            'address': address,
            'benchmark': 'Public_AR_Current',
            'format': 'json'
        }
        
        response = requests.get(CENSUS_SINGLE_ADDRESS, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data['result']['addressMatches']:
                match = data['result']['addressMatches'][0]
                coords = match['coordinates']
                return coords['y'], coords['x']  # lat, lng
        
        return None, None
    except Exception as e:
        print(f"   Error geocoding {address}: {e}")
        return None, None

def geocode_city_state_zip(city, state, zip_code):
    """Geocode using just city, state, and zip."""
    # For city/state/zip, we'll use the center of the ZIP code
    # Census geocoder needs a more complete address, so we'll construct one
    address = f"{city}, {state} {zip_code}"
    return geocode_single_address(address)

def geocode_voters():
    """Geocode voter addresses."""
    print(f"\n{'='*80}")
    print(f"GEOCODING VOTERS - Started at {datetime.now()}")
    print(f"{'='*80}")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get voters without geocoding
        cur.execute("""
            SELECT id, voter_key, first_name, last_name, middle_name,
                   primary_address1, primary_city, primary_state, primary_zip,
                   primary_unit, primary_unit_number
            FROM voters
            WHERE geocoded_at IS NULL
            ORDER BY id
            LIMIT 100
        """)
        
        voters = cur.fetchall()
        print(f"Found {len(voters)} voters to geocode (processing first 100)")
        
        geocoded_count = 0
        failed_count = 0
        
        for i, voter in enumerate(voters):
            # Construct full address
            address_parts = []
            if voter['primary_address1']:
                address_parts.append(voter['primary_address1'])
            
            # Add unit/apartment if present
            if voter['primary_unit'] and voter['primary_unit_number']:
                address_parts.append(f"{voter['primary_unit']} {voter['primary_unit_number']}")
            
            street_address = ' '.join(address_parts)
            full_address = f"{street_address}, {voter['primary_city']}, {voter['primary_state']} {voter['primary_zip']}"
            
            # Geocode the address
            lat, lng = geocode_single_address(full_address)
            
            if lat and lng:
                # Update voter with coordinates
                cur.execute("""
                    UPDATE voters
                    SET latitude = %s, longitude = %s, geocoded_at = %s
                    WHERE id = %s
                """, (lat, lng, datetime.now(), voter['id']))
                geocoded_count += 1
                print(f"   ✓ Geocoded voter {i+1}/{len(voters)}: {voter['first_name']} {voter['last_name']}")
            else:
                failed_count += 1
                print(f"   ✗ Failed to geocode voter {i+1}/{len(voters)}: {full_address}")
            
            # Rate limiting - Census API allows about 1 request per second
            time.sleep(1)
            
            # Commit every 10 records
            if (i + 1) % 10 == 0:
                conn.commit()
                print(f"   Committed {i+1} records...")
        
        conn.commit()
        
        print(f"\nVoter Geocoding Results:")
        print(f"  ✓ Successfully geocoded: {geocoded_count}")
        print(f"  ✗ Failed to geocode: {failed_count}")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

def geocode_contributors():
    """Geocode contributor city/state/zip locations."""
    print(f"\n{'='*80}")
    print(f"GEOCODING CONTRIBUTORS - Started at {datetime.now()}")
    print(f"{'='*80}")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get unique city/state/zip combinations from contributors
        cur.execute("""
            SELECT DISTINCT city, state, zip_code
            FROM contributors
            WHERE city IS NOT NULL 
            AND state IS NOT NULL 
            AND zip_code IS NOT NULL
            AND geocoded_at IS NULL
            ORDER BY zip_code
            LIMIT 50
        """)
        
        locations = cur.fetchall()
        print(f"Found {len(locations)} unique contributor locations to geocode (processing first 50)")
        
        geocoded_count = 0
        failed_count = 0
        
        for i, loc in enumerate(locations):
            # Geocode the location
            lat, lng = geocode_city_state_zip(loc['city'], loc['state'], loc['zip_code'])
            
            if lat and lng:
                # Update all contributors with this city/state/zip
                cur.execute("""
                    UPDATE contributors
                    SET latitude = %s, longitude = %s, geocoded_at = %s
                    WHERE city = %s AND state = %s AND zip_code = %s
                    AND geocoded_at IS NULL
                """, (lat, lng, datetime.now(), loc['city'], loc['state'], loc['zip_code']))
                
                updated = cur.rowcount
                geocoded_count += updated
                print(f"   ✓ Geocoded location {i+1}/{len(locations)}: {loc['city']}, {loc['state']} {loc['zip_code']} ({updated} contributors)")
            else:
                failed_count += 1
                print(f"   ✗ Failed to geocode: {loc['city']}, {loc['state']} {loc['zip_code']}")
            
            # Rate limiting
            time.sleep(1)
            
            # Commit every 10 locations
            if (i + 1) % 10 == 0:
                conn.commit()
                print(f"   Committed {i+1} locations...")
        
        conn.commit()
        
        print(f"\nContributor Geocoding Results:")
        print(f"  ✓ Successfully geocoded: {geocoded_count} contributors")
        print(f"  ✗ Failed locations: {failed_count}")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

def geocode_org_contributors():
    """Geocode organization contributor locations."""
    print(f"\n{'='*80}")
    print(f"GEOCODING ORGANIZATION CONTRIBUTORS - Started at {datetime.now()}")
    print(f"{'='*80}")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get unique city/state/zip combinations from org_contributors
        cur.execute("""
            SELECT DISTINCT city, state, zip_code
            FROM org_contributors
            WHERE city IS NOT NULL 
            AND state IS NOT NULL 
            AND zip_code IS NOT NULL
            AND geocoded_at IS NULL
            ORDER BY zip_code
            LIMIT 50
        """)
        
        locations = cur.fetchall()
        print(f"Found {len(locations)} unique organization locations to geocode (processing first 50)")
        
        geocoded_count = 0
        failed_count = 0
        
        for i, loc in enumerate(locations):
            # Geocode the location
            lat, lng = geocode_city_state_zip(loc['city'], loc['state'], loc['zip_code'])
            
            if lat and lng:
                # Update all orgs with this city/state/zip
                cur.execute("""
                    UPDATE org_contributors
                    SET latitude = %s, longitude = %s, geocoded_at = %s
                    WHERE city = %s AND state = %s AND zip_code = %s
                    AND geocoded_at IS NULL
                """, (lat, lng, datetime.now(), loc['city'], loc['state'], loc['zip_code']))
                
                updated = cur.rowcount
                geocoded_count += updated
                print(f"   ✓ Geocoded location {i+1}/{len(locations)}: {loc['city']}, {loc['state']} {loc['zip_code']} ({updated} organizations)")
            else:
                failed_count += 1
                print(f"   ✗ Failed to geocode: {loc['city']}, {loc['state']} {loc['zip_code']}")
            
            # Rate limiting
            time.sleep(1)
            
            # Commit every 10 locations
            if (i + 1) % 10 == 0:
                conn.commit()
                print(f"   Committed {i+1} locations...")
        
        conn.commit()
        
        print(f"\nOrganization Geocoding Results:")
        print(f"  ✓ Successfully geocoded: {geocoded_count} organizations")
        print(f"  ✗ Failed locations: {failed_count}")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

def main():
    """Main geocoding function."""
    print("\nStarting geocoding process...")
    print("Note: This is rate-limited to comply with Census API guidelines")
    print("Processing small batches as demonstration\n")
    
    # Geocode voters first (they have full addresses)
    geocode_voters()
    
    # Then geocode contributors (city/state/zip only)
    # Note: This will only work after you've imported contributor data with city/state/zip
    # geocode_contributors()
    # geocode_org_contributors()
    
    print(f"\n{'='*80}")
    print("GEOCODING COMPLETE")
    print(f"{'='*80}")
    print("\nNote: Full geocoding will take time due to rate limits.")
    print("Run this script periodically to process more records.")

if __name__ == "__main__":
    main()