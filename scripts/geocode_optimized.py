#!/usr/bin/env python3
"""Optimized geocoding with deduplication and Nominatim backup."""

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import os
import requests
import time
from datetime import datetime
import json
from collections import defaultdict
import hashlib

DATABASE_URL = os.environ.get('DATABASE_URL')

# Census Geocoder endpoint
CENSUS_SINGLE_ADDRESS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# Nominatim endpoint (OpenStreetMap)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def create_geocode_cache_table():
    """Create a table to cache geocoded locations."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS geocode_cache (
                id SERIAL PRIMARY KEY,
                location_hash VARCHAR(64) UNIQUE,
                location_type VARCHAR(20),  -- 'full_address', 'city_state_zip', 'zip_only'
                full_address TEXT,
                city VARCHAR(255),
                state VARCHAR(2),
                zip_code VARCHAR(10),
                latitude DECIMAL(10, 8),
                longitude DECIMAL(11, 8),
                geocoder_used VARCHAR(20),  -- 'census', 'nominatim', 'failed'
                geocoded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                attempts INTEGER DEFAULT 1
            )
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_geocode_cache_hash 
            ON geocode_cache(location_hash)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_geocode_cache_zip 
            ON geocode_cache(zip_code)
        """)
        
        conn.commit()
        print("✓ Geocode cache table created/verified")
        
    except Exception as e:
        conn.rollback()
        print(f"Error creating cache table: {e}")
    finally:
        cur.close()
        conn.close()

def get_location_hash(location_type, **kwargs):
    """Generate a unique hash for a location."""
    if location_type == 'full_address':
        key = f"{kwargs.get('address', '')}|{kwargs.get('city', '')}|{kwargs.get('state', '')}|{kwargs.get('zip', '')}"
    elif location_type == 'city_state_zip':
        key = f"{kwargs.get('city', '')}|{kwargs.get('state', '')}|{kwargs.get('zip', '')}"
    elif location_type == 'zip_only':
        key = f"ZIP|{kwargs.get('zip', '')}"
    else:
        key = ""
    
    return hashlib.sha256(key.encode()).hexdigest()

def geocode_with_census(address):
    """Try geocoding with Census API."""
    try:
        params = {
            'address': address,
            'benchmark': 'Public_AR_Current',
            'format': 'json'
        }
        
        response = requests.get(CENSUS_SINGLE_ADDRESS, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('result', {}).get('addressMatches'):
                match = data['result']['addressMatches'][0]
                coords = match['coordinates']
                return coords['y'], coords['x'], 'census'
    except Exception as e:
        print(f"   Census API error: {e}")
    
    return None, None, None

def geocode_with_nominatim(address, city=None, state=None, zip_code=None):
    """Try geocoding with Nominatim (OpenStreetMap)."""
    try:
        # Build query
        if city and state and zip_code:
            # Structured query for better results
            params = {
                'q': address,
                'city': city,
                'state': state,
                'postalcode': zip_code,
                'countrycodes': 'us',
                'format': 'json',
                'limit': 1
            }
        else:
            # Free-form query
            params = {
                'q': f"{address}, USA",
                'format': 'json',
                'limit': 1
            }
        
        # Add user agent (required by Nominatim)
        headers = {
            'User-Agent': 'NYC Campaign Finance Analyzer/1.0'
        }
        
        response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                result = data[0]
                return float(result['lat']), float(result['lon']), 'nominatim'
    except Exception as e:
        print(f"   Nominatim API error: {e}")
    
    return None, None, None

def geocode_location(location_type, **kwargs):
    """Geocode a location using Census first, then Nominatim as backup."""
    lat, lng, geocoder = None, None, None
    
    if location_type == 'full_address':
        address = kwargs.get('address', '')
        # Try Census first
        lat, lng, geocoder = geocode_with_census(address)
        
        # If failed, try Nominatim
        if not lat:
            time.sleep(1)  # Nominatim rate limit
            lat, lng, geocoder = geocode_with_nominatim(
                address,
                kwargs.get('city'),
                kwargs.get('state'),
                kwargs.get('zip')
            )
    
    elif location_type == 'city_state_zip':
        city = kwargs.get('city', '')
        state = kwargs.get('state', '')
        zip_code = kwargs.get('zip', '')
        
        # Build address for geocoding
        address = f"{city}, {state} {zip_code}"
        
        # Try Census first
        lat, lng, geocoder = geocode_with_census(address)
        
        # If failed, try Nominatim
        if not lat:
            time.sleep(1)  # Nominatim rate limit
            lat, lng, geocoder = geocode_with_nominatim(
                address, city, state, zip_code
            )
    
    elif location_type == 'zip_only':
        zip_code = kwargs.get('zip', '')
        address = f"USA {zip_code}"
        
        # Try Census first
        lat, lng, geocoder = geocode_with_census(address)
        
        # If failed, try Nominatim
        if not lat:
            time.sleep(1)
            lat, lng, geocoder = geocode_with_nominatim(address)
    
    return lat, lng, geocoder or 'failed'

def collect_unique_locations():
    """Collect all unique locations from voters, contributors, and org_contributors."""
    print("\n1. Collecting unique locations...")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    locations = {}
    location_to_records = defaultdict(lambda: {'voters': [], 'contributors': [], 'org_contributors': []})
    
    try:
        # Collect voter addresses
        print("   Collecting voter addresses...")
        cur.execute("""
            SELECT id, primary_address1, primary_city, primary_state, primary_zip
            FROM voters
            WHERE geocoded_at IS NULL
            AND primary_address1 IS NOT NULL
            AND primary_city IS NOT NULL
            AND primary_state IS NOT NULL
            AND primary_zip IS NOT NULL
        """)
        
        for voter in cur.fetchall():
            address = f"{voter['primary_address1']}, {voter['primary_city']}, {voter['primary_state']} {voter['primary_zip']}"
            location_hash = get_location_hash(
                'full_address',
                address=address,
                city=voter['primary_city'],
                state=voter['primary_state'],
                zip=voter['primary_zip']
            )
            
            if location_hash not in locations:
                locations[location_hash] = {
                    'type': 'full_address',
                    'address': address,
                    'city': voter['primary_city'],
                    'state': voter['primary_state'],
                    'zip': voter['primary_zip']
                }
            
            location_to_records[location_hash]['voters'].append(voter['id'])
        
        print(f"      Found {len(location_to_records)} unique voter addresses")
        
        # Collect contributor city/state/zip
        print("   Collecting contributor locations...")
        cur.execute("""
            SELECT id, city, state, zip_code
            FROM contributors
            WHERE geocoded_at IS NULL
            AND city IS NOT NULL
            AND state IS NOT NULL
            AND zip_code IS NOT NULL
        """)
        
        for contrib in cur.fetchall():
            location_hash = get_location_hash(
                'city_state_zip',
                city=contrib['city'],
                state=contrib['state'],
                zip=contrib['zip_code']
            )
            
            if location_hash not in locations:
                locations[location_hash] = {
                    'type': 'city_state_zip',
                    'address': f"{contrib['city']}, {contrib['state']} {contrib['zip_code']}",
                    'city': contrib['city'],
                    'state': contrib['state'],
                    'zip': contrib['zip_code']
                }
            
            location_to_records[location_hash]['contributors'].append(contrib['id'])
        
        contributor_locations = len([k for k in location_to_records if location_to_records[k]['contributors']])
        print(f"      Found {contributor_locations} unique contributor locations")
        
        # Collect org contributor city/state/zip
        print("   Collecting organization locations...")
        cur.execute("""
            SELECT id, city, state, zip_code
            FROM org_contributors
            WHERE geocoded_at IS NULL
            AND city IS NOT NULL
            AND state IS NOT NULL
            AND zip_code IS NOT NULL
        """)
        
        for org in cur.fetchall():
            location_hash = get_location_hash(
                'city_state_zip',
                city=org['city'],
                state=org['state'],
                zip=org['zip_code']
            )
            
            if location_hash not in locations:
                locations[location_hash] = {
                    'type': 'city_state_zip',
                    'address': f"{org['city']}, {org['state']} {org['zip_code']}",
                    'city': org['city'],
                    'state': org['state'],
                    'zip': org['zip_code']
                }
            
            location_to_records[location_hash]['org_contributors'].append(org['id'])
        
        org_locations = len([k for k in location_to_records if location_to_records[k]['org_contributors']])
        print(f"      Found {org_locations} unique organization locations")
        
        print(f"\n   Total unique locations to geocode: {len(locations)}")
        
        # Count total records that will be updated
        total_records = sum(
            len(records['voters']) + len(records['contributors']) + len(records['org_contributors'])
            for records in location_to_records.values()
        )
        print(f"   Total records to update: {total_records}")
        
        return locations, location_to_records
        
    except Exception as e:
        print(f"Error collecting locations: {e}")
        import traceback
        traceback.print_exc()
        return {}, {}
    finally:
        cur.close()
        conn.close()

def geocode_unique_locations(locations, limit=100):
    """Geocode unique locations and cache results."""
    print(f"\n2. Geocoding {min(limit, len(locations))} unique locations...")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    geocoded_count = 0
    failed_count = 0
    
    try:
        for i, (location_hash, location_info) in enumerate(list(locations.items())[:limit]):
            # Check if already in cache
            cur.execute("""
                SELECT latitude, longitude, geocoder_used
                FROM geocode_cache
                WHERE location_hash = %s
            """, (location_hash,))
            
            cached = cur.fetchone()
            
            if cached and cached[0] is not None:
                print(f"   {i+1}/{min(limit, len(locations))}: Using cached result for {location_info['zip']}")
                continue
            
            # Geocode the location
            print(f"   {i+1}/{min(limit, len(locations))}: Geocoding {location_info['address'][:50]}...")
            
            lat, lng, geocoder = geocode_location(
                location_info['type'],
                address=location_info['address'],
                city=location_info.get('city'),
                state=location_info.get('state'),
                zip=location_info.get('zip')
            )
            
            # Save to cache
            cur.execute("""
                INSERT INTO geocode_cache 
                (location_hash, location_type, full_address, city, state, zip_code, 
                 latitude, longitude, geocoder_used)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (location_hash) 
                DO UPDATE SET 
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    geocoder_used = EXCLUDED.geocoder_used,
                    attempts = geocode_cache.attempts + 1
            """, (
                location_hash,
                location_info['type'],
                location_info['address'],
                location_info.get('city'),
                location_info.get('state'),
                location_info.get('zip'),
                lat, lng, geocoder
            ))
            
            if lat and lng:
                geocoded_count += 1
                print(f"      ✓ Success using {geocoder}: {lat:.6f}, {lng:.6f}")
            else:
                failed_count += 1
                print(f"      ✗ Failed to geocode")
            
            conn.commit()
            
            # Rate limiting
            if geocoder == 'census':
                time.sleep(0.5)  # Census allows ~2 req/sec
            else:
                time.sleep(1.2)  # Nominatim requires 1 req/sec
        
        print(f"\n   Geocoding results:")
        print(f"   ✓ Successfully geocoded: {geocoded_count}")
        print(f"   ✗ Failed: {failed_count}")
        
    except Exception as e:
        conn.rollback()
        print(f"Error during geocoding: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

def update_records_from_cache(location_to_records):
    """Update voter, contributor, and org records from geocode cache."""
    print("\n3. Updating records from geocode cache...")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    try:
        voters_updated = 0
        contributors_updated = 0
        orgs_updated = 0
        
        # Get all cached geocodes
        cur.execute("""
            SELECT location_hash, latitude, longitude
            FROM geocode_cache
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """)
        
        cache = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        
        for location_hash, records in location_to_records.items():
            if location_hash in cache:
                lat, lng = cache[location_hash]
                
                # Update voters
                if records['voters']:
                    cur.execute("""
                        UPDATE voters
                        SET latitude = %s, longitude = %s, geocoded_at = %s
                        WHERE id = ANY(%s::uuid[])
                    """, (lat, lng, datetime.now(), records['voters']))
                    voters_updated += len(records['voters'])
                
                # Update contributors
                if records['contributors']:
                    cur.execute("""
                        UPDATE contributors
                        SET latitude = %s, longitude = %s, geocoded_at = %s
                        WHERE id = ANY(%s::uuid[])
                    """, (lat, lng, datetime.now(), records['contributors']))
                    contributors_updated += len(records['contributors'])
                
                # Update org_contributors
                if records['org_contributors']:
                    cur.execute("""
                        UPDATE org_contributors
                        SET latitude = %s, longitude = %s, geocoded_at = %s
                        WHERE id = ANY(%s::uuid[])
                    """, (lat, lng, datetime.now(), records['org_contributors']))
                    orgs_updated += len(records['org_contributors'])
        
        conn.commit()
        
        print(f"\n   Update results:")
        print(f"   ✓ Voters updated: {voters_updated}")
        print(f"   ✓ Contributors updated: {contributors_updated}")
        print(f"   ✓ Organizations updated: {orgs_updated}")
        print(f"   ✓ Total records updated: {voters_updated + contributors_updated + orgs_updated}")
        
    except Exception as e:
        conn.rollback()
        print(f"Error updating records: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

def show_statistics():
    """Show geocoding statistics."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    try:
        print(f"\n{'='*80}")
        print("GEOCODING STATISTICS")
        print(f"{'='*80}")
        
        # Cache statistics
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) as geocoded,
                COUNT(CASE WHEN geocoder_used = 'census' THEN 1 END) as census_success,
                COUNT(CASE WHEN geocoder_used = 'nominatim' THEN 1 END) as nominatim_success,
                COUNT(CASE WHEN geocoder_used = 'failed' THEN 1 END) as failed
            FROM geocode_cache
        """)
        
        cache_stats = cur.fetchone()
        print(f"\nCache Statistics:")
        print(f"  Total cached locations: {cache_stats[0]}")
        print(f"  Successfully geocoded: {cache_stats[1]}")
        print(f"  Via Census API: {cache_stats[2]}")
        print(f"  Via Nominatim: {cache_stats[3]}")
        print(f"  Failed: {cache_stats[4]}")
        
        # Record statistics
        cur.execute("""
            SELECT 
                'Voters' as type,
                COUNT(*) as total,
                COUNT(geocoded_at) as geocoded
            FROM voters
            UNION ALL
            SELECT 
                'Contributors' as type,
                COUNT(*) as total,
                COUNT(geocoded_at) as geocoded
            FROM contributors
            UNION ALL
            SELECT 
                'Organizations' as type,
                COUNT(*) as total,
                COUNT(geocoded_at) as geocoded
            FROM org_contributors
        """)
        
        print(f"\nRecord Statistics:")
        for row in cur.fetchall():
            pct = (row[2] / row[1] * 100) if row[1] > 0 else 0
            print(f"  {row[0]}: {row[2]:,}/{row[1]:,} geocoded ({pct:.1f}%)")
        
    except Exception as e:
        print(f"Error getting statistics: {e}")
    finally:
        cur.close()
        conn.close()

def main():
    """Main geocoding pipeline."""
    print(f"\n{'='*80}")
    print(f"OPTIMIZED GEOCODING PIPELINE - Started at {datetime.now()}")
    print(f"{'='*80}")
    
    # Create cache table if needed
    create_geocode_cache_table()
    
    # Collect unique locations
    locations, location_to_records = collect_unique_locations()
    
    if not locations:
        print("\nNo locations to geocode!")
        return
    
    # Geocode unique locations (limited batch for testing)
    geocode_unique_locations(locations, limit=50)
    
    # Update all records from cache
    update_records_from_cache(location_to_records)
    
    # Show statistics
    show_statistics()
    
    print(f"\n{'='*80}")
    print("GEOCODING PIPELINE COMPLETE")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()