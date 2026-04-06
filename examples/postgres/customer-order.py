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
from typing import Optional, Dict, List
from env_utils import get_postgres_config, print_postgres_config

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
    """Generates realistic addresses using Faker locales with consistent city/region mapping"""
    
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

    def __init__(self):
        # Cache results to maintain consistency for repeated lookups
        self.cache = {}

    def get_realistic_address(self, country: str) -> str:
        """
        Get a realistic address using Faker for the given country,
        ensuring correct regional formatting and city-state consistency.
        """
        locale = COUNTRY_LOCALE_MAP.get(country, 'en_US')
        f = fake[locale]

        # Use our city-region mappings if available for higher realism
        if country in self.CITIES_BY_REGION:
            regions = self.CITIES_BY_REGION[country]
            region_name = random.choice(list(regions.keys()))
            city = random.choice(regions[region_name])
            
            # Generate common components
            street = f.street_address()
            postcode = f.postcode()

            # Format based on national conventions
            if country == 'Canada':
                return f"{street}, {city}, {region_name} {postcode}, Canada"
            elif country == 'United States':
                return f"{street}, {city}, {region_name} {postcode}, USA"
            elif country == 'United Kingdom':
                return f"{street}, {city}, {region_name}, {postcode}, United Kingdom"
            elif country in ['Germany', 'France', 'Italy', 'Spain']:
                # Many European countries use [Street, Postcode City, Region, Country]
                return f"{street}, {postcode} {city}, {region_name}, {country}"
            elif country == 'Japan':
                # Japan: [Prefecture, City, Street, Postcode] or reversed for Western style
                # We'll stick to a Western-friendly "Street, City, Prefecture, Postcode, Japan"
                return f"{street}, {city}, {region_name}, {postcode}, Japan"
            else:
                return f"{street}, {city}, {region_name}, {postcode}, {country}"
        else:
            # Fallback to standard Faker address with formatting cleanup
            full_address = f.address().replace('\n', ', ')
            if country not in full_address:
                full_address = f"{full_address}, {country}"
            return full_address

# Initialize the address generator
address_generator = RealisticAddressGenerator()

def generate_realistic_address(country):
    """Fallback function for backward compatibility"""
    return address_generator.get_realistic_address(country)

def get_connection():
    """Create and return a database connection."""
    config = get_postgres_config()
    print_postgres_config(config)
    return psycopg2.connect(**config)


def insert_customers(conn, count=100):
    """Insert fake customer data with unique emails and random IDs."""
    cursor = conn.cursor()
    customers = []
    inserted_count = 0
    attempts = 0
    max_attempts = count * 10  # Prevent infinite loops
    used_customer_ids = set()  # Track used customer IDs to ensure uniqueness
    
    # Countries for customer diversity
    customer_countries = [
        ('Canada', 0.5), ('United States', 0.3), ('United Kingdom', 0.1), 
        ('Germany', 0.05), ('France', 0.05)
    ]
    countries = [c[0] for c in customer_countries]
    country_weights = [c[1] for c in customer_countries]

    print(f"Inserting {count} customers with international diversity and unique emails...")
    
    while inserted_count < count and attempts < max_attempts:
        attempts += 1
        
        # Select country and locale
        country = random.choices(countries, weights=country_weights)[0]
        locale = COUNTRY_LOCALE_MAP.get(country, 'en_US')
        f = fake[locale]

        # Generate unique email using timestamp and random components
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = fake.random_number(digits=4)
        unique_email = f"{f.user_name()}{timestamp}{random_suffix}@{f.domain_name()}"
        
        # Generate a unique random customer ID (6-8 digits)
        customer_id = None
        while True:
            candidate_id = random.randint(100000, 99999999)
            if candidate_id not in used_customer_ids:
                customer_id = candidate_id
                used_customer_ids.add(customer_id)
                break
        
        # Realistic data quality issues: 5% missing phone numbers
        phone = f.phone_number()[:20] if random.random() > 0.05 else None
        
        # Address parts
        address = f.street_address()
        city = f.city()

        customer = (
            customer_id,
            f.name(),
            unique_email,
            phone,
            address,
            city,
            country
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
            conn.rollback()
            if "customers_email_key" in str(e) or "customers_pkey" in str(e):
                continue
            else:
                raise e
    
    conn.commit()
    print(f"✓ Inserted {inserted_count} customers (after {attempts} attempts)")
    return customers


class RealisticOrderGenerator:
    """Generates realistic order data based on business logic and strategies."""

    # Customer Segments
    SEGMENTS = {
        'VIP': {'weight': 0.10, 'freq_mult': 5.0, 'value_range': (200, 1000)},
        'REGULAR': {'weight': 0.50, 'freq_mult': 1.0, 'value_range': (50, 200)},
        'NEW': {'weight': 0.30, 'freq_mult': 0.2, 'value_range': (20, 80)},
        'INACTIVE': {'weight': 0.10, 'freq_mult': 0.05, 'value_range': (10, 50)}
    }

    # Seasonality (Month 1-12)
    # Q1: 0.8, Q2: 1.0, Q3: 0.9, Q4: 1.5
    SEASONAL_MULTIPLIERS = {
        1: 0.8, 2: 0.8, 3: 0.9,
        4: 1.0, 5: 1.0, 6: 1.0,
        7: 0.9, 8: 0.9, 9: 1.1, # Back to school
        10: 1.2, 11: 1.6, 12: 1.8 # Holiday
    }

    # Payment Methods by Region
    PAYMENT_PREFS = {
        'United States': {'credit_card': 0.6, 'paypal': 0.2, 'debit_card': 0.15, 'other': 0.05},
        'Canada': {'credit_card': 0.5, 'debit_card': 0.3, 'paypal': 0.15, 'other': 0.05},
        'Germany': {'bank_transfer': 0.4, 'paypal': 0.3, 'credit_card': 0.25, 'other': 0.05},
        'United Kingdom': {'credit_card': 0.5, 'debit_card': 0.3, 'paypal': 0.15, 'other': 0.05},
        'Japan': {'credit_card': 0.4, 'cash': 0.2, 'digital_wallet': 0.3, 'other': 0.1},
        'default': {'credit_card': 0.5, 'paypal': 0.3, 'debit_card': 0.1, 'other': 0.1}
    }

    def __init__(self, customer_ids):
        self.customer_ids = customer_ids
        self.customer_segments = {}
        self._assign_segments()
        # Pre-calculate selection weights for performance
        self._selection_weights = [self.SEGMENTS[self.customer_segments[cid]]['freq_mult'] for cid in self.customer_ids]

    def _assign_segments(self):
        """Assign segments to customers randomly based on weights."""
        segments = list(self.SEGMENTS.keys())
        weights = [self.SEGMENTS[s]['weight'] for s in segments]
        # Use random.choices for bulk assignment if possible, but strict iteration is safer for dict population
        for cid in self.customer_ids:
            self.customer_segments[cid] = random.choices(segments, weights=weights, k=1)[0]

    def get_customer_for_order(self):
        """Select a customer based on their segment's frequency multiplier."""
        return random.choices(self.customer_ids, weights=self._selection_weights, k=1)[0]

    def get_order_date(self):
        """Generate a realistic order date respecting seasonality and business hours."""
        # Try to find a date that matches seasonal weights
        for _ in range(10): 
            days_ago = random.randint(0, 730)
            candidate_date = datetime.now() - timedelta(days=days_ago)
            month = candidate_date.month
            weight = self.SEASONAL_MULTIPLIERS.get(month, 1.0)
            
            # Weekend penalty: 30% fewer orders on weekends (Sat=5, Sun=6)
            if candidate_date.weekday() >= 5:
                weight *= 0.7
                
            if random.random() < (weight / 2.0):
                # Now randomize the time based on business hours
                # 9 AM - 5 PM: 70%
                # 5 PM - 10 PM: 20%
                # 10 PM - 9 AM: 10%
                r = random.random()
                if r < 0.70:
                    hour = random.randint(9, 16)
                elif r < 0.90:
                    hour = random.randint(17, 21)
                else:
                    hour = random.choice(list(range(0, 9)) + list(range(22, 24)))
                
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                return candidate_date.replace(hour=hour, minute=minute, second=second)
                
        # Fallback
        return datetime.now() - timedelta(days=random.randint(0, 730))

    def get_order_total(self, customer_id):
        """Generate order total based on customer segment and power law."""
        segment = self.customer_segments.get(customer_id, 'REGULAR')
        min_val, max_val = self.SEGMENTS[segment]['value_range']
        
        # Power law distribution (Pareto)
        # alpha=3 gives a nice long tail
        val = (random.paretovariate(3) - 1) * (max_val - min_val) + min_val
        
        # Add noise and bounds
        val = val * random.uniform(0.8, 1.2)
        val = max(5.0, min(val, 5000.0))
            
        return round(val, 2)

    def get_status(self, order_date):
        """Determine status based on how old the order is."""
        days_old = (datetime.now().date() - order_date.date()).days
        
        if days_old > 7:
            return random.choices(['delivered', 'returned', 'cancelled'], weights=[0.90, 0.08, 0.02])[0]
        elif days_old > 3:
            return random.choices(['shipped', 'delivered'], weights=[0.3, 0.7])[0]
        elif days_old > 1:
            return random.choices(['processing', 'shipped'], weights=[0.4, 0.6])[0]
        else:
            return random.choices(['pending', 'processing'], weights=[0.3, 0.7])[0]

    def get_payment_method(self, country):
        """Get payment method based on country preferences."""
        prefs = self.PAYMENT_PREFS.get(country, self.PAYMENT_PREFS['default'])
        methods = list(prefs.keys())
        weights = list(prefs.values())
        return random.choices(methods, weights=weights)[0]


def insert_orders(conn, customer_ids, count=500, batch_size=100, commit_every=100):
    """Insert fake order data with realistic patterns."""
    if not customer_ids:
        print("⚠️  No customer IDs provided. Skipping order insertion.")
        return

    cursor = conn.cursor()
    
    print(f"Inserting {count} orders with realistic patterns (seasonality, segments, etc.)...")
    
    # Initialize generator with business logic
    generator = RealisticOrderGenerator(customer_ids)
    
    # Shipping destinations with weights
    shipping_destinations = [
        ('Canada', 0.35), ('United States', 0.25), ('United Kingdom', 0.1),
        ('Germany', 0.08), ('France', 0.06), ('Italy', 0.04),
        ('Spain', 0.03), ('Japan', 0.03), ('Australia', 0.03),
        ('South Korea', 0.01), ('Netherlands', 0.01), ('Switzerland', 0.01)
    ]
    dest_names = [d[0] for d in shipping_destinations]
    dest_weights = [d[1] for d in shipping_destinations]
    
    orders_batch = []
    used_order_ids = set()
    
    for i in range(count):
        # 1. Select Customer (weighted by segment)
        customer_id = generator.get_customer_for_order()
        
        # 2. Date (weighted by seasonality)
        order_date = generator.get_order_date()
        
        # 3. Total (weighted by segment & power law)
        total = generator.get_order_total(customer_id)
        
        # 4. Shipping Address & Country
        destination = random.choices(dest_names, weights=dest_weights)[0]
        
        if i % 50 == 0:
            print(f"    Generating addresses... {i + 1}/{count} orders...", end="\r")
        shipping_address = address_generator.get_realistic_address(destination)
        
        # 5. Payment Method (weighted by region)
        payment_method = generator.get_payment_method(destination)
        
        # 6. Status (weighted by age)
        status = generator.get_status(order_date)
        
        # 7. Unique ID
        while True:
            order_id = random.randint(10000000, 999999999)
            if order_id not in used_order_ids:
                used_order_ids.add(order_id)
                break
        
        order = (
            order_id,
            customer_id,
            order_date.date(),
            total,
            status,
            shipping_address,
            payment_method,
            order_date  # created_at matches order_date
        )
        
        orders_batch.append(order)
        
        # Batch insert
        if len(orders_batch) >= batch_size or i == count - 1:
            cursor.executemany("""
                INSERT INTO orders (id, customer_id, order_date, total, status, 
                                  shipping_address, payment_method, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, orders_batch)
            
            if (i + 1) % commit_every == 0 or i == count - 1:
                conn.commit()
                print(f"    ✓ Committed batch at {i + 1}/{count} orders")
            
            orders_batch = []
            
            if (i + 1) % 100 == 0:
                print(f"  Progress: {i + 1}/{count} orders inserted and committed")

    print(f"✓ Inserted {count} orders with realistic business patterns")


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
            
            print("📍 Using localized address generation (no external API dependencies)")
            
            # Insert customers first
            customer_ids = insert_customers(conn, args.customers)
            # Then insert orders
            insert_orders(conn, customer_ids, args.orders, 
                         batch_size=args.batch_size, commit_every=args.commit_every)
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