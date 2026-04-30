# PostgreSQL Customer Order Test Data Generator

This script generates realistic customer and order data for testing PostgreSQL adapters and RAG systems.

## Features

### 🌍 Realistic Address Generation
The script uses a localized address generation strategy powered by **Faker** and pre-defined geographic mappings to generate highly realistic addresses:

- **Real city-region consistency** ensures cities always match their respective provinces, states, or regions.
- **Authentic geographic data** using localized Faker providers for multiple countries.
- **Proper address formatting** tailored to each country's standard (e.g., European vs. North American formats).
- **High performance** with zero external API dependencies or rate-limiting issues.

### 📍 Supported Countries
- **Canada**: Real Canadian cities (Toronto, Vancouver, Montreal) with proper provinces
- **United States**: Real US cities (NYC, LA, Chicago) with proper state codes
- **United Kingdom**: Real UK cities (London, Manchester) with proper counties
- **Germany**: Real German cities (Berlin, Hamburg) with proper states
- **France**: Real French cities (Paris, Lyon) with proper regions
- **Italy**: Real Italian cities (Rome, Milan, Naples) with proper regions
- **Spain**: Real Spanish cities (Madrid, Barcelona, Valencia) with proper autonomous communities
- **Japan**: Real Japanese cities (Tokyo, Osaka, Kyoto) with proper prefectures
- **Australia**: Real Australian cities (Sydney, Melbourne, Brisbane) with proper states/territories
- **Other countries**: Generic but realistic localized addresses

## Installation

1. Install dependencies:
```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set up your `.env` file with database credentials (see `env.example`)

## Usage

### Basic Usage
```bash
# Insert 100 customers and 500 orders with realistic addresses
python customer-order.py --action insert --customers 100 --orders 500

# Insert data after cleaning existing data
python customer-order.py --action insert --clean --customers 50 --orders 200
```

### Advanced Options
```bash
# Customize batch size for better performance
python customer-order.py --action insert --batch-size 100

# Commit every 10 orders for more frequent database updates
python customer-order.py --action insert --commit-every 10
```

### Other Actions
```bash
# Query existing data
python customer-order.py --action query

# Query specific customer
python customer-order.py --action query --customer-id 1

# Delete all data (requires confirmation)
python customer-order.py --action delete --confirm

# Recreate tables from scratch (requires confirmation)
python customer-order.py --action recreate --confirm
```

## Address Quality

The generator ensures high-quality, geographically consistent addresses:
- `456 Oak Avenue, Toronto, ON M5V 3A8, Canada` ✅ (Real city/province match)
- `789 Pine Street, Los Angeles, CA 90210, USA` ✅ (Correct state code)
- `123 Straße, 10115 Berlin, Berlin, Germany` ✅ (Proper European formatting)

## Configuration

### Environment Variables
```bash
DATASOURCE_POSTGRES_HOST=localhost
DATASOURCE_POSTGRES_PORT=5432
DATASOURCE_POSTGRES_DATABASE=test_db
DATASOURCE_POSTGRES_USERNAME=postgres
DATASOURCE_POSTGRES_PASSWORD=postgres
DATASOURCE_POSTGRES_SSL_MODE=require
```

### Command Line Overrides
```bash
python customer-order.py --action insert --host localhost --port 5432 --database mydb --user myuser --password mypass
```

## Performance Notes

### 🚀 Performance Optimizations
- **Local Generation**: No network latency or API rate limits.
- **Batch Inserts**: Uses `executemany` for faster database operations (configurable with `--batch-size`).
- **Efficient Caching**: Uses internal mappings to ensure consistency without repeated computation.
- **Real-time Progress**: Shows progress during generation with detailed logging.

### 📊 Progress Monitoring
- **Every 50 orders**: Address generation progress updates.
- **Every 100 orders**: Major milestone updates.
- **Batch completion**: Confirms each batch of orders inserted and committed.

## Troubleshooting

### Database Issues
- Ensure PostgreSQL is running and accessible.
- Check your `.env` file configuration.
- Verify database permissions.

## Expected Output

```
📍 Using localized address generation (no external API dependencies)
Inserting 100 customers with international diversity and unique emails...
  Progress: 100/100 customers inserted
✓ Inserted 100 customers (after 100 attempts)
Inserting 500 orders with realistic patterns (seasonality, segments, etc.)...
    Generating addresses... 51/500 orders...
    Generating addresses... 101/500 orders...
    ✓ Committed batch at 100/500 orders
  Progress: 100/500 orders inserted and committed
...
✓ Test data inserted successfully!
```

## Contributing

To add support for more countries:
1. Update `COUNTRY_LOCALE_MAP` with the appropriate Faker locale.
2. Add city-region mappings to the `CITIES_BY_REGION` dictionary in `RealisticAddressGenerator`.
3. Implement any specific national formatting rules in `get_realistic_address`.
