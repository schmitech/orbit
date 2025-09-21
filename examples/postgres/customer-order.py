#!/usr/bin/env python3
"""
PostgreSQL test data management script for adapter testing.
Generates Canadian customer and order data using Faker.

Usage Examples:
    # Insert fresh data (adds to existing data)
    python customer-order.py --action insert --customers 100 --orders 500
    
    # Insert fresh data after cleaning existing data
    python customer-order.py --action insert --clean --customers 50 --orders 200
    
    # Query specific customer
    python customer-order.py --action query --customer-id 1
    
    # Query top customers by spending
    python customer-order.py --action query
    
    # Delete all data (requires confirmation)
    python customer-order.py --action delete --confirm
    
    # Completely recreate tables from scratch (requires confirmation)
    python customer-order.py --action recreate --confirm
    
    # Use custom database connection
    python customer-order.py --action insert --host localhost --port 5432 --database mydb --user myuser --password mypass

Actions:
    insert    - Insert customer and order data
    query     - Query existing data
    delete    - Delete all data from tables
    recreate  - Drop and recreate tables with full schema

Flags:
    --clean   - Clean existing data before inserting (for insert action)
    --confirm - Confirm destructive operations (delete, recreate)
"""

import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from faker import Faker
import random
from datetime import datetime, timedelta
import json
from decimal import Decimal
import os
from dotenv import load_dotenv, find_dotenv
import requests
import time
from typing import Optional, Dict, List

def reload_env_variables():
    """Reload environment variables from .env file"""
    env_file = find_dotenv()
    if env_file:
        load_dotenv(env_file, override=True)
        print(f"🔄 Reloaded environment variables from: {env_file}")
    else:
        print("⚠️  No .env file found")

# Initialize Faker with Western locales only (avoiding Asian characters)
# Initialize Faker with all necessary locales for realistic data generation
fake = Faker(['en_CA', 'en_US', 'en_GB', 'fr_FR', 'de_DE', 'es_ES', 'it_IT', 
               'ja_JP', 'en_AU', 'nl_NL', 'de_CH', 'fr_CH', 'it_CH', 'ko_KR'])

# Map countries to their primary Faker locale
COUNTRY_LOCALE_MAP = {
    'Canada': 'en_CA',
    'United States': 'en_US',
    'United Kingdom': 'en_GB',
    'Germany': 'de_DE',
    'France': 'fr_FR',
    'Italy': 'it_IT',
    'Spain': 'es_ES',
    'Japan': 'ja_JP',
    'Australia': 'en_AU',
    'Netherlands': 'nl_NL',
    'Switzerland': 'de_CH',  # Use German as default for Switzerland
    'South Korea': 'ko_KR'
}
# Set seed for reproducible results (optional)
# fake.seed_instance(12345)

# Geographic data for realistic addresses
CANADIAN_PROVINCES = {
    'AB': 'Alberta',
    'BC': 'British Columbia', 
    'MB': 'Manitoba',
    'NB': 'New Brunswick',
    'NL': 'Newfoundland and Labrador',
    'NS': 'Nova Scotia',
    'NT': 'Northwest Territories',
    'NU': 'Nunavut',
    'ON': 'Ontario',
    'PE': 'Prince Edward Island',
    'QC': 'Quebec',
    'SK': 'Saskatchewan',
    'YT': 'Yukon'
}

US_STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
    'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
    'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
    'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
    'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
    'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'
}

UK_COUNTIES = [
    'Bedfordshire', 'Berkshire', 'Bristol', 'Buckinghamshire', 'Cambridgeshire',
    'Cheshire', 'Cornwall', 'Cumbria', 'Derbyshire', 'Devon', 'Dorset', 'Durham',
    'East Sussex', 'Essex', 'Gloucestershire', 'Greater London', 'Greater Manchester',
    'Hampshire', 'Herefordshire', 'Hertfordshire', 'Isle of Wight', 'Kent', 'Lancashire',
    'Leicestershire', 'Lincolnshire', 'London', 'Merseyside', 'Norfolk', 'Northamptonshire',
    'Northumberland', 'Nottinghamshire', 'Oxfordshire', 'Rutland', 'Shropshire', 'Somerset',
    'South Yorkshire', 'Staffordshire', 'Suffolk', 'Surrey', 'Tyne and Wear', 'Warwickshire',
    'West Midlands', 'West Sussex', 'West Yorkshire', 'Wiltshire', 'Worcestershire'
]

GERMAN_STATES = [
    'Baden-Württemberg', 'Bayern', 'Berlin', 'Brandenburg', 'Bremen', 'Hamburg',
    'Hessen', 'Mecklenburg-Vorpommern', 'Niedersachsen', 'Nordrhein-Westfalen',
    'Rheinland-Pfalz', 'Saarland', 'Sachsen', 'Sachsen-Anhalt', 'Schleswig-Holstein', 'Thüringen'
]

FRENCH_REGIONS = [
    'Auvergne-Rhône-Alpes', 'Bourgogne-Franche-Comté', 'Bretagne', 'Centre-Val de Loire',
    'Corse', 'Grand Est', 'Hauts-de-France', 'Île-de-France', 'Normandie',
    'Nouvelle-Aquitaine', 'Occitanie', 'Pays de la Loire', 'Provence-Alpes-Côte d\'Azur'
]

class RealisticAddressGenerator:
    """Generates realistic addresses using OpenStreetMap Nominatim API"""
    
    def __init__(self):
        self.base_url = "https://nominatim.openstreetmap.org/search"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'OrbitCustomerOrderScript/1.0 (https://github.com/your-repo)'
        })
        self.cache = {}  # Simple cache to avoid repeated API calls
        self.rate_limit_delay = 1.0  # Respect rate limiting (1 request per second)
        
    def get_realistic_address(self, country: str) -> str:
        """Get a realistic address from OpenStreetMap for the given country"""
        cache_key = f"{country}_{random.randint(1, 100)}"  # Add randomness to avoid cache hits
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            address = self._fetch_from_nominatim(country)
            if address:
                self.cache[cache_key] = address
                # Only sleep for rate limiting if we're not in a batch operation
                if len(self.cache) < 50:  # Don't sleep if we have many cached addresses
                    time.sleep(self.rate_limit_delay)
                return address
        except Exception as e:
            print(f"⚠️  API call failed for {country}: {e}. Falling back to generated address.")
        
        # Fallback to generated address if API fails
        return self._generate_fallback_address(country)
    
    def _fetch_from_nominatim(self, country: str) -> Optional[str]:
        """Fetch a realistic address from OpenStreetMap Nominatim API"""
        
        # Country-specific search queries with proper city-state/province pairs
        search_queries = {
            'Canada': [
                'Toronto, Ontario, Canada',
                'Vancouver, British Columbia, Canada', 
                'Montreal, Quebec, Canada',
                'Calgary, Alberta, Canada',
                'Ottawa, Ontario, Canada',
                'Edmonton, Alberta, Canada',
                'Winnipeg, Manitoba, Canada',
                'Quebec City, Quebec, Canada',
                'Mississauga, Ontario, Canada',
                'Brampton, Ontario, Canada',
                'Hamilton, Ontario, Canada',
                'Surrey, British Columbia, Canada',
                'Burnaby, British Columbia, Canada',
                'Richmond, British Columbia, Canada'
            ],
            'United States': [
                'New York, NY, USA',
                'Los Angeles, CA, USA',
                'Chicago, IL, USA',
                'Houston, TX, USA',
                'Phoenix, AZ, USA',
                'Philadelphia, PA, USA',
                'San Antonio, TX, USA',
                'San Diego, CA, USA',
                'Dallas, TX, USA',
                'Austin, TX, USA',
                'Fort Worth, TX, USA',
                'Jacksonville, FL, USA',
                'Columbus, OH, USA',
                'Charlotte, NC, USA',
                'San Francisco, CA, USA'
            ],
            'United Kingdom': [
                'London, England, UK',
                'Manchester, England, UK',
                'Birmingham, England, UK',
                'Liverpool, England, UK',
                'Leeds, England, UK',
                'Sheffield, England, UK',
                'Bristol, England, UK',
                'Glasgow, Scotland, UK',
                'Edinburgh, Scotland, UK',
                'Cardiff, Wales, UK',
                'Belfast, Northern Ireland, UK',
                'Newcastle, England, UK',
                'Nottingham, England, UK',
                'Southampton, England, UK',
                'Oxford, England, UK'
            ],
            'Germany': [
                'Berlin, Germany',
                'Hamburg, Germany',
                'München, Germany',
                'Köln, Germany',
                'Frankfurt, Germany',
                'Stuttgart, Germany',
                'Düsseldorf, Germany',
                'Dortmund, Germany',
                'Essen, Germany',
                'Leipzig, Germany',
                'Bremen, Germany',
                'Dresden, Germany',
                'Hannover, Germany',
                'Nürnberg, Germany',
                'Duisburg, Germany'
            ],
            'France': [
                'Paris, France',
                'Marseille, France',
                'Lyon, France',
                'Toulouse, France',
                'Nice, France',
                'Nantes, France',
                'Strasbourg, France',
                'Montpellier, France',
                'Bordeaux, France',
                'Lille, France',
                'Rennes, France',
                'Reims, France',
                'Saint-Étienne, France',
                'Toulon, France',
                'Grenoble, France'
            ],
            'Italy': [
                'Rome, Lazio, Italy',
                'Milan, Lombardy, Italy',
                'Naples, Campania, Italy',
                'Turin, Piedmont, Italy',
                'Palermo, Sicily, Italy',
                'Genoa, Liguria, Italy',
                'Bologna, Emilia-Romagna, Italy',
                'Florence, Tuscany, Italy',
                'Bari, Apulia, Italy',
                'Catania, Sicily, Italy',
                'Venice, Veneto, Italy',
                'Verona, Veneto, Italy',
                'Messina, Sicily, Italy',
                'Padua, Veneto, Italy',
                'Trieste, Friuli-Venezia Giulia, Italy'
            ],
            'Spain': [
                'Madrid, Community of Madrid, Spain',
                'Barcelona, Catalonia, Spain',
                'Valencia, Valencian Community, Spain',
                'Seville, Andalusia, Spain',
                'Zaragoza, Aragon, Spain',
                'Málaga, Andalusia, Spain',
                'Murcia, Region of Murcia, Spain',
                'Palma, Balearic Islands, Spain',
                'Las Palmas, Canary Islands, Spain',
                'Bilbao, Basque Country, Spain',
                'Alicante, Valencian Community, Spain',
                'Córdoba, Andalusia, Spain',
                'Valladolid, Castile and León, Spain',
                'Vigo, Galicia, Spain',
                'Gijón, Asturias, Spain'
            ],
            'Japan': [
                'Tokyo, Tokyo, Japan',
                'Yokohama, Kanagawa, Japan',
                'Osaka, Osaka, Japan',
                'Nagoya, Aichi, Japan',
                'Sapporo, Hokkaido, Japan',
                'Fukuoka, Fukuoka, Japan',
                'Kobe, Hyogo, Japan',
                'Kyoto, Kyoto, Japan',
                'Kawasaki, Kanagawa, Japan',
                'Saitama, Saitama, Japan',
                'Hiroshima, Hiroshima, Japan',
                'Sendai, Miyagi, Japan',
                'Chiba, Chiba, Japan',
                'Kitakyushu, Fukuoka, Japan',
                'Sakai, Osaka, Japan'
            ],
            'Australia': [
                'Sydney, New South Wales, Australia',
                'Melbourne, Victoria, Australia',
                'Brisbane, Queensland, Australia',
                'Perth, Western Australia, Australia',
                'Adelaide, South Australia, Australia',
                'Gold Coast, Queensland, Australia',
                'Newcastle, New South Wales, Australia',
                'Canberra, Australian Capital Territory, Australia',
                'Sunshine Coast, Queensland, Australia',
                'Wollongong, New South Wales, Australia',
                'Hobart, Tasmania, Australia',
                'Geelong, Victoria, Australia',
                'Townsville, Queensland, Australia',
                'Cairns, Queensland, Australia',
                'Darwin, Northern Territory, Australia'
            ]
        }
        
        if country not in search_queries:
            # For other countries, use a generic search
            query = f"major city, {country}"
        else:
            query = random.choice(search_queries[country])
        
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1
        }
        
        try:
            response = self.session.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data and len(data) > 0:
                return self._format_nominatim_address(data[0], country)
            
        except requests.exceptions.Timeout:
            print(f"⏰ API timeout for {country}, using fallback address")
        except requests.exceptions.RequestException as e:
            print(f"🌐 API request failed for {country}: {e}, using fallback address")
        except Exception as e:
            print(f"❌ Unexpected error for {country}: {e}, using fallback address")
        
        return None
    
    def _format_nominatim_address(self, place_data: Dict, country: str) -> str:
        """Format the Nominatim response into a readable address"""
        address = place_data.get('address', {})
        display_name = place_data.get('display_name', '')
        
        # Validate that the result is actually from the requested country
        result_country = address.get('country', '').lower()
        
        # Check if the result country matches the requested country
        # OpenStreetMap often returns country names in native languages, which is correct
        if result_country:
            # Accept any result that contains the requested country name or is clearly from the right region
            # This handles cases like "deutschland" for Germany, "italia" for Italy, etc.
            country_lower = country.lower()
            result_lower = result_country.lower()
            
            # Direct match or partial match
            if (country_lower in result_lower or 
                result_lower in country_lower or
                # Handle common native language variants
                (country_lower == 'germany' and 'deutsch' in result_lower) or
                (country_lower == 'italy' and 'ital' in result_lower) or
                (country_lower == 'spain' and 'espa' in result_lower) or
                (country_lower == 'japan' and '日本' in result_lower) or
                (country_lower == 'south korea' and ('korea' in result_lower or '한국' in result_lower or '대한' in result_lower)) or
                (country_lower == 'netherlands' and ('neder' in result_lower or 'holland' in result_lower)) or
                (country_lower == 'switzerland' and ('schweiz' in result_lower or 'suisse' in result_lower or 'svizzera' in result_lower))):
                pass  # Valid match
            else:
                print(f"⚠️  API returned {result_country} for {country} request, using fallback")
                return None
        
        # Extract components
        house_number = address.get('house_number', '')
        road = address.get('road', '')
        city = address.get('city', address.get('town', address.get('village', '')))
        state = address.get('state', '')
        postcode = address.get('postcode', '')
        
        # Validate city is not from wrong country (common issue with Faker-style names)
        if city and any(foreign_word in city.lower() for foreign_word in ['strada', 'via', 'rue', 'straße', 'calle']):
            print(f"⚠️  City '{city}' appears to be from wrong country, using fallback")
            return None
        
        # Build street address
        if house_number and road:
            street_address = f"{house_number} {road}"
        elif road:
            street_address = f"{fake.building_number()} {road}"
        else:
            locale = COUNTRY_LOCALE_MAP.get(country, 'en_US') # Fallback to en_US
            street_address = fake[locale].street_address()
        
        # Format based on country
        if country == 'Canada':
            province = address.get('state', random.choice(list(CANADIAN_PROVINCES.keys())))
            return f"{street_address}, {city}, {province} {postcode}, Canada"
        elif country == 'United States':
            state_code = address.get('state', random.choice(list(US_STATES.keys())))
            return f"{street_address}, {city}, {state_code} {postcode}, USA"
        elif country == 'United Kingdom':
            county = address.get('county', random.choice(UK_COUNTIES))
            return f"{street_address}, {city}, {county}, {postcode}, United Kingdom"
        elif country == 'Germany':
            state = address.get('state', random.choice(GERMAN_STATES))
            return f"{street_address}, {postcode} {city}, {state}, Germany"
        elif country == 'France':
            region = address.get('state', random.choice(FRENCH_REGIONS))
            return f"{street_address}, {postcode} {city}, {region}, France"
        elif country == 'Italy':
            region = address.get('state', random.choice(['Lazio', 'Lombardy', 'Campania', 'Piedmont', 'Sicily']))
            return f"{street_address}, {city}, {region}, {postcode}, Italy"
        elif country == 'Spain':
            community = address.get('state', random.choice(['Community of Madrid', 'Catalonia', 'Valencian Community', 'Andalusia']))
            return f"{street_address}, {city}, {community}, {postcode}, Spain"
        elif country == 'Japan':
            prefecture = address.get('state', random.choice(['Tokyo', 'Kanagawa', 'Osaka', 'Aichi', 'Hokkaido']))
            return f"{street_address}, {city}, {prefecture}, {postcode}, Japan"
        elif country == 'Australia':
            state = address.get('state', random.choice(['New South Wales', 'Victoria', 'Queensland', 'Western Australia']))
            return f"{street_address}, {city}, {state}, {postcode}, Australia"
        else:
            return f"{street_address}, {city}, {postcode}, {country}"
    
    def _generate_fallback_address(self, country: str) -> str:
        """Generate a fallback address using the old method if API fails"""
        return generate_realistic_address(country)

# Initialize the address generator
address_generator = RealisticAddressGenerator()

def generate_realistic_address(country):
    """
    Generate a realistic-looking address for a given country using pre-defined
    city-state/province mappings and locale-specific data.
    """
    CITIES_BY_REGION = {
        'Canada': {
            'ON': ['Toronto', 'Ottawa', 'Mississauga', 'Brampton', 'Hamilton'],
            'BC': ['Vancouver', 'Surrey', 'Burnaby', 'Richmond'],
            'AB': ['Calgary', 'Edmonton', 'Red Deer'],
            'QC': ['Montreal', 'Quebec City', 'Laval', 'Gatineau'],
            'MB': ['Winnipeg'], 'NS': ['Halifax'], 'SK': ['Saskatoon', 'Regina']
        },
        'United States': {
            'CA': ['Los Angeles', 'San Francisco', 'San Diego', 'San Jose'],
            'NY': ['New York', 'Buffalo', 'Rochester', 'Syracuse'],
            'TX': ['Houston', 'Dallas', 'Austin', 'San Antonio'],
            'FL': ['Miami', 'Orlando', 'Tampa', 'Jacksonville'],
            'IL': ['Chicago'], 'AZ': ['Phoenix'], 'PA': ['Philadelphia']
        },
        'United Kingdom': {
            'England': ['London', 'Manchester', 'Birmingham', 'Liverpool', 'Leeds', 'Bristol'],
            'Scotland': ['Glasgow', 'Edinburgh'],
            'Wales': ['Cardiff', 'Swansea'],
            'Northern Ireland': ['Belfast']
        },
        'Germany': {
            'Baden-Württemberg': ['Stuttgart', 'Karlsruhe', 'Mannheim'],
            'Bayern': ['Munich', 'Nuremberg', 'Augsburg'],
            'Berlin': ['Berlin'], 'Hamburg': ['Hamburg'],
            'Hessen': ['Frankfurt', 'Wiesbaden'],
            'Nordrhein-Westfalen': ['Cologne', 'Düsseldorf', 'Dortmund', 'Essen'],
            'Sachsen': ['Leipzig', 'Dresden']
        },
        'France': {
            'Île-de-France': ['Paris'],
            'Provence-Alpes-Côte d\'Azur': ['Marseille', 'Nice'],
            'Auvergne-Rhône-Alpes': ['Lyon'],
            'Occitanie': ['Toulouse', 'Montpellier'],
            'Hauts-de-France': ['Lille'],
            'Nouvelle-Aquitaine': ['Bordeaux']
        },
        'Italy': {
            'Lazio': ['Rome'], 'Lombardy': ['Milan'], 'Campania': ['Naples'],
            'Piedmont': ['Turin'], 'Sicily': ['Palermo', 'Catania'],
            'Emilia-Romagna': ['Bologna'], 'Tuscany': ['Florence']
        },
        'Spain': {
            'Community of Madrid': ['Madrid'], 'Catalonia': ['Barcelona'],
            'Valencian Community': ['Valencia'], 'Andalusia': ['Seville', 'Málaga']
        },
        'Japan': {
            'Tokyo': ['Tokyo'], 'Kanagawa': ['Yokohama', 'Kawasaki'],
            'Osaka': ['Osaka', 'Sakai'], 'Aichi': ['Nagoya'], 'Hokkaido': ['Sapporo']
        },
        'Australia': {
            'New South Wales': ['Sydney'], 'Victoria': ['Melbourne'],
            'Queensland': ['Brisbane', 'Gold Coast'], 'Western Australia': ['Perth'],
            'South Australia': ['Adelaide'], 'Australian Capital Territory': ['Canberra']
        },
        'Netherlands': {
            'North Holland': ['Amsterdam'], 'South Holland': ['Rotterdam', 'The Hague'],
            'Utrecht': ['Utrecht'], 'North Brabant': ['Eindhoven']
        },
        'Switzerland': {
            'Zürich': ['Zurich'], 'Geneva': ['Geneva'], 'Basel-Stadt': ['Basel'],
            'Bern': ['Bern'], 'Vaud': ['Lausanne']
        },
        'South Korea': {
            'Seoul': ['Seoul'], 'Busan': ['Busan'], 'Incheon': ['Incheon']
        }
    }

    locale = COUNTRY_LOCALE_MAP.get(country)
    faker_instance = fake[locale] if locale else fake['en_US']  # Fallback to en_US

    street_address = faker_instance.street_address()
    postal_code = faker_instance.postcode()

    if country in CITIES_BY_REGION:
        regions = CITIES_BY_REGION[country]
        region_name = random.choice(list(regions.keys()))
        city = random.choice(regions[region_name])

        if country == 'Canada':
            return f"{street_address}, {city}, {region_name} {postal_code}, Canada"
        elif country == 'United States':
            return f"{street_address}, {city}, {region_name} {postal_code}, USA"
        elif country in ['Germany', 'France', 'Italy', 'Spain']:
            return f"{street_address}, {postal_code} {city}, {region_name}, {country}"
        else:
            return f"{street_address}, {city}, {region_name}, {postal_code}, {country}"
    else:
        # Generic fallback for countries without detailed data
        city = faker_instance.city()
        return f"{street_address}, {city}, {postal_code}, {country}"

# Database configuration from environment variables
def get_db_config():
    """Get database configuration from environment variables and construct connection string."""
    # Reload environment variables to get latest values
    reload_env_variables()
    
    # Get individual environment variables
    host = os.getenv('DATASOURCE_POSTGRES_HOST', 'localhost')
    port = int(os.getenv('DATASOURCE_POSTGRES_PORT', '5432'))
    database = os.getenv('DATASOURCE_POSTGRES_DATABASE', 'test_db')
    user = os.getenv('DATASOURCE_POSTGRES_USERNAME', 'postgres')
    password = os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'postgres')
    sslmode = os.getenv('DATASOURCE_POSTGRES_SSL_MODE', 'require')
    
    # Construct connection string dynamically
    connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    print(f"🔗 Using connection string: postgresql://{user}:{'*' * len(password)}@{host}:{port}/{database}")
    print(f"🔒 SSL Mode: {sslmode}")
    
    return {
        'host': host,
        'port': port,
        'database': database,
        'user': user,
        'password': password,
        'sslmode': sslmode
    }


def get_connection():
    """Create and return a database connection."""
    # Get fresh configuration each time
    config = get_db_config()
    return psycopg2.connect(**config)


def insert_customers(conn, count=100):
    """Insert fake customer data with unique emails and random IDs."""
    cursor = conn.cursor()
    customers = []
    inserted_count = 0
    attempts = 0
    max_attempts = count * 10  # Prevent infinite loops
    used_customer_ids = set()  # Track used customer IDs to ensure uniqueness
    
    print(f"Inserting {count} customers with unique emails and random IDs...")
    
    while inserted_count < count and attempts < max_attempts:
        attempts += 1
        
        # Generate unique email using timestamp and random components
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = fake.random_number(digits=4)
        unique_email = f"{fake.user_name()}{timestamp}{random_suffix}@{fake.domain_name()}"
        
        # Generate a unique random customer ID (6-8 digits, fits in INTEGER range)
        customer_id_attempts = 0
        customer_id = None
        
        while customer_id_attempts < 1000:
            candidate_id = random.randint(100000, 99999999)  # 6-8 digits, fits in INTEGER
            if candidate_id not in used_customer_ids:
                customer_id = candidate_id
                used_customer_ids.add(customer_id)
                break
            customer_id_attempts += 1
        
        if customer_id is None:
            # Fallback: use timestamp-based ID if we can't find a unique random one
            customer_id = int(datetime.now().timestamp() * 100) % 100000000  # 8 digits max
            used_customer_ids.add(customer_id)
        
        customer = (
            customer_id,  # Random customer ID
            fake.name(),
            unique_email,
            fake['en_CA'].phone_number()[:20],
            fake['en_CA'].street_address(),
            fake['en_CA'].city(),
            "Canada"  # Ensure Canadian data
        )
        
        try:
            cursor.execute("""
                INSERT INTO customers (id, name, email, phone, address, city, country)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, customer)
            
            customers.append(customer_id)
            inserted_count += 1
            
            if inserted_count % 100 == 0:
                print(f"  Progress: {inserted_count}/{count} customers inserted")
                
        except psycopg2.IntegrityError as e:
            if "customers_email_key" in str(e) or "customers_pkey" in str(e):
                # Email or ID already exists, continue to next attempt
                continue
            else:
                # Other integrity error, re-raise
                raise e
    
    conn.commit()
    print(f"✓ Inserted {inserted_count} customers (after {attempts} attempts)")
    
    if inserted_count < count:
        print(f"⚠️  Could only insert {inserted_count} customers due to email/ID conflicts")
    
    return customers


def insert_orders(conn, customer_ids, count=500, use_api=True, batch_size=100, commit_every=100, force_fallback=False):
    """Insert fake order data with international shipping addresses."""
    cursor = conn.cursor()
    
    print(f"Inserting {count} orders with international shipping addresses...")
    print(f"  Data will be spread across the last 24 months for better historical analytics")
    print(f"  Using batch size: {batch_size}")
    print(f"  Committing every: {commit_every} orders")
    
    # Payment methods
    payment_methods = ['credit_card', 'debit_card', 'paypal', 'bank_transfer', 'cash']
    statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
    
    # International shipping destinations with weights (more likely to ship to certain countries)
    shipping_destinations = [
        ('Canada', '0.35'),     # 35% - Canadian customers
        ('United States', '0.25'),  # 25% - US shipping
        ('United Kingdom', '0.1'),  # 10% - UK shipping
        ('Germany', '0.08'),    # 8% - German shipping
        ('France', '0.06'),     # 6% - French shipping
        ('Italy', '0.04'),      # 4% - Italian shipping
        ('Spain', '0.03'),      # 3% - Spanish shipping
        ('Japan', '0.03'),      # 3% - Japanese shipping
        ('Australia', '0.03'),  # 3% - Australian shipping
        ('South Korea', '0.01'), # 1% - Korean shipping
        ('Netherlands', '0.01'), # 1% - Dutch shipping
        ('Switzerland', '0.01')  # 1% - Swiss shipping
    ]
    
    # Pre-generate some addresses to speed up the process
    if use_api:
        print("  Pre-generating addresses for common destinations...")
        common_destinations = ['Canada', 'United States', 'United Kingdom', 'Germany', 'France', 'Italy', 'Spain', 'Japan', 'Australia']
        for dest in common_destinations:
            address_generator.get_realistic_address(dest)
        print("  ✓ Address cache populated")
    
    orders_batch = []
    used_order_ids = set()  # Track used order IDs to ensure uniqueness
    
    for i in range(count):
        # Random date within the last 24 months for better historical analytics data
        days_ago = random.randint(0, 730)  # Random days within last 24 months (730 days)
        order_date = datetime.now() - timedelta(days=days_ago)
        
        # Random total between $10 and $1000
        total = round(random.uniform(10.0, 1000.0), 2)
        
        # Select shipping destination based on weights
        destination = random.choices(
            [dest[0] for dest in shipping_destinations],
            weights=[float(dest[1]) for dest in shipping_destinations]
        )[0]
        
        # Generate realistic international shipping address
        if not use_api or force_fallback:
            shipping_address = generate_realistic_address(destination)
        else:
            if i % 50 == 0:  # Show progress every 50 orders
                print(f"    Generating addresses... {i + 1}/{count} orders...", end="\r")
            shipping_address = address_generator.get_realistic_address(destination)
        
        # Generate a unique random order ID (8-9 digits, fits in INTEGER range)
        max_attempts = 1000  # Prevent infinite loops
        attempts = 0
        order_id = None
        
        while attempts < max_attempts:
            candidate_id = random.randint(10000000, 999999999)  # 8-9 digits, fits in INTEGER
            if candidate_id not in used_order_ids:
                order_id = candidate_id
                used_order_ids.add(order_id)
                break
            attempts += 1
        
        if order_id is None:
            # Fallback: use timestamp-based ID if we can't find a unique random one
            order_id = int(datetime.now().timestamp() * 1000) % 1000000000  # 9 digits max
            used_order_ids.add(order_id)
        
        order = (
            order_id,  # Random order ID
            random.choice(customer_ids),
            order_date.date(),
            total,
            random.choice(statuses),
            shipping_address,
            random.choice(payment_methods),
            order_date  # created_at
        )
        
        orders_batch.append(order)
        
        # Insert batch when it reaches the batch size or at the end
        if len(orders_batch) >= batch_size or i == count - 1:
            # Use executemany for batch insert
            cursor.executemany("""
                INSERT INTO orders (id, customer_id, order_date, total, status, 
                                  shipping_address, payment_method, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, orders_batch)
            
            # Commit based on commit frequency
            if (i + 1) % commit_every == 0 or i == count - 1:
                conn.commit()
                print(f"    ✓ Committed batch at {i + 1}/{count} orders")
            
            # Clear the batch
            orders_batch = []
            
            # Progress updates
            if (i + 1) % 100 == 0:
                print(f"  Progress: {i + 1}/{count} orders inserted and committed")
            elif (i + 1) % 10 == 0:
                print(f"    {i + 1}/{count} orders inserted...", end="\r")
    
    print(f"✓ Inserted {count} orders with international shipping")


def query_recent_activity(conn, customer_id):
    """Query recent customer activity (matching the retriever query)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT c.name, o.order_date, o.total, o.created_at
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        WHERE o.created_at >= NOW() - INTERVAL '24 months'
        AND c.id = %s
        ORDER BY o.created_at DESC
        LIMIT 20
    """
    
    cursor.execute(query, (customer_id,))
    results = cursor.fetchall()
    
    return results


def query_customer_summary(conn, customer_id=None):
    """Query customer summary with order statistics."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if customer_id:
        query = """
            SELECT 
                c.id,
                c.name,
                c.email,
                COUNT(o.id) as total_orders,
                COALESCE(SUM(o.total), 0) as total_spent,
                COALESCE(AVG(o.total), 0) as avg_order_value,
                MAX(o.order_date) as last_order_date
            FROM customers c
            LEFT JOIN orders o ON c.id = o.customer_id
            WHERE c.id = %s
            GROUP BY c.id, c.name, c.email
        """
        cursor.execute(query, (customer_id,))
    else:
        query = """
            SELECT 
                c.id,
                c.name,
                c.email,
                COUNT(o.id) as total_orders,
                COALESCE(SUM(o.total), 0) as total_spent,
                COALESCE(AVG(o.total), 0) as avg_order_value,
                MAX(o.order_date) as last_order_date
            FROM customers c
            LEFT JOIN orders o ON c.id = o.customer_id
            GROUP BY c.id, c.name, c.email
            ORDER BY total_spent DESC
            LIMIT 10
        """
        cursor.execute(query)
    
    results = cursor.fetchall()
    return results


def delete_all_data(conn):
    """Delete all data from tables."""
    cursor = conn.cursor()
    
    print("Deleting all data...")
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM customers")
    
    conn.commit()
    print("✓ All data deleted")


def drop_and_recreate_tables(conn):
    """Drop and recreate tables for fresh start."""
    cursor = conn.cursor()
    
    print("Dropping and recreating tables...")
    
    # Drop tables if they exist
    cursor.execute("DROP TABLE IF EXISTS orders CASCADE")
    cursor.execute("DROP TABLE IF EXISTS customers CASCADE")
    
    # Recreate customers table
    cursor.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            phone VARCHAR(20),
            address TEXT,
            city VARCHAR(100),
            country VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Recreate orders table
    cursor.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            order_date DATE NOT NULL,
            total DECIMAL(10, 2) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            shipping_address TEXT,
            payment_method VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)
    
    # Create indexes for better performance
    cursor.execute("CREATE INDEX idx_orders_customer_id ON orders(customer_id)")
    cursor.execute("CREATE INDEX idx_orders_created_at ON orders(created_at)")
    cursor.execute("CREATE INDEX idx_orders_order_date ON orders(order_date)")
    
    # Create update trigger for updated_at
    cursor.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql'
    """)
    
    cursor.execute("""
        CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    
    cursor.execute("""
        CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    
    conn.commit()
    print("✓ Tables dropped and recreated with full schema")


def print_results(results, title="Query Results"):
    """Pretty print query results."""
    print(f"\n{title}")
    print("-" * 80)
    
    if not results:
        print("No results found.")
        return
    
    # Convert Decimal to float for JSON serialization
    for result in results:
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = float(value)
    
    print(json.dumps(results, indent=2, default=str, ensure_ascii=False))
    print(f"\nTotal records: {len(results)}")


def main():
    parser = argparse.ArgumentParser(description='PostgreSQL test data management')
    parser.add_argument('--action', choices=['insert', 'query', 'delete', 'recreate'], 
                       required=True, help='Action to perform')
    parser.add_argument('--customers', type=int, default=100, 
                       help='Number of customers to insert')
    parser.add_argument('--orders', type=int, default=500, 
                       help='Number of orders to insert')
    parser.add_argument('--customer-id', type=int, 
                       help='Customer ID for querying')
    parser.add_argument('--confirm', action='store_true', 
                       help='Confirm deletion')
    parser.add_argument('--clean', action='store_true',
                       help='Clean existing data before inserting (for insert action)')
    parser.add_argument('--host', 
                       help='Database host (defaults to DATASOURCE_POSTGRES_HOST env var)')
    parser.add_argument('--port', type=int, 
                       help='Database port (defaults to DATASOURCE_POSTGRES_PORT env var)')
    parser.add_argument('--database', 
                       help='Database name (defaults to DATASOURCE_POSTGRES_DATABASE env var)')
    parser.add_argument('--user', 
                       help='Database user (defaults to DATASOURCE_POSTGRES_USERNAME env var)')
    parser.add_argument('--password', 
                       help='Database password (defaults to DATASOURCE_POSTGRES_PASSWORD env var)')
    parser.add_argument('--use-api', action='store_true', default=True,
                       help='Use OpenStreetMap API for realistic addresses (default: True)')
    parser.add_argument('--no-api', action='store_true',
                       help='Disable API usage and use generated addresses only')
    parser.add_argument('--force-fallback', action='store_true',
                       help='Force use of fallback address generation (bypasses API completely)')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Batch size for database inserts (default: 100)')
    parser.add_argument('--commit-every', type=int, default=100,
                       help='Commit every N orders (default: 100, use 1 for real-time commits)')
    
    args = parser.parse_args()
    
    # Set environment variables from command line args if provided
    if args.host:
        os.environ['DATASOURCE_POSTGRES_HOST'] = args.host
    if args.port:
        os.environ['DATASOURCE_POSTGRES_PORT'] = str(args.port)
    if args.database:
        os.environ['DATASOURCE_POSTGRES_DATABASE'] = args.database
    if args.user:
        os.environ['DATASOURCE_POSTGRES_USERNAME'] = args.user
    if args.password:
        os.environ['DATASOURCE_POSTGRES_PASSWORD'] = args.password
    
    try:
        conn = get_connection()
        
        if args.action == 'insert':
            # Clean existing data if --clean flag is provided
            if args.clean:
                print("🧹 Cleaning existing data before insert...")
                delete_all_data(conn)
            
            # Show address generation method
            if args.no_api:
                print("📍 Using generated addresses (API disabled)")
            else:
                print("🌍 Using OpenStreetMap API for realistic addresses")
                print("   (Use --no-api to disable API usage)")
            
            # Insert customers first
            customer_ids = insert_customers(conn, args.customers)
            # Then insert orders
            insert_orders(conn, customer_ids, args.orders, use_api=not args.no_api, 
                         batch_size=args.batch_size, commit_every=args.commit_every, 
                         force_fallback=args.force_fallback)
            print(f"\n✓ Test data inserted successfully!")
            
        elif args.action == 'query':
            if args.customer_id:
                # Query recent activity for specific customer
                results = query_recent_activity(conn, args.customer_id)
                print_results(results, f"Recent Activity for Customer {args.customer_id}")
                
                # Also show customer summary
                summary = query_customer_summary(conn, args.customer_id)
                print_results(summary, f"\nCustomer Summary for ID {args.customer_id}")
            else:
                # Show top customers
                results = query_customer_summary(conn)
                print_results(results, "Top Customers by Total Spent")
                
        elif args.action == 'delete':
            if args.confirm:
                delete_all_data(conn)
            else:
                print("⚠️  Use --confirm flag to delete all data")
                
        elif args.action == 'recreate':
            if args.confirm:
                drop_and_recreate_tables(conn)
            else:
                print("⚠️  Use --confirm flag to drop and recreate tables")
                
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        exit(1)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()