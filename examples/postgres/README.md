# PostgreSQL Customer Order Test Data Generator

This script generates realistic customer and order data for testing PostgreSQL adapters and RAG systems.

## Features

### 🌍 Realistic Address Generation
The script now uses **OpenStreetMap Nominatim API** to generate highly realistic addresses:

- **Real street names and numbers** from actual geographic data
- **Authentic cities, states, and postal codes** that actually exist
- **Proper address formatting** for each country's standard
- **No more geographic mismatches** like "Miami, TX Canada"

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
- **Other countries**: Generic but realistic addresses

## Installation

1. Install dependencies:
```bash
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

### Address Generation Options
```bash
# Use OpenStreetMap API for realistic addresses (default)
python customer-order.py --action insert --use-api

# Disable API and use generated addresses only
python customer-order.py --action insert --no-api

# Customize batch size for better performance
python customer-order.py --action insert --batch-size 50
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

## Address Quality Examples

### Before (Generated)
- `123 Main St, Miami, TX Canada` ❌ (Geographic mismatch)

### After (API-Generated)
- `456 Oak Avenue, Toronto, ON M5V 3A8, Canada` ✅ (Real address)
- `789 Pine Street, Los Angeles, CA 90210, USA` ✅ (Real address)
- `321 High Road, London, Greater London, SW1A 1AA, UK` ✅ (Real address)

## API Details

### OpenStreetMap Nominatim
- **Free to use** - No API key required
- **Rate limited** - 1 request per second (automatically handled)
- **Fallback support** - Falls back to generated addresses if API fails
- **Caching** - Caches results to minimize API calls

### Fallback Behavior
If the API is unavailable or fails, the script automatically falls back to the previous address generation method, ensuring your script continues to work.

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

### Performance Tuning Options
```bash
# Use smaller batch size for better progress visibility
python customer-order.py --action insert --customers 100 --orders 1000 --batch-size 50

# Disable API for maximum speed (uses generated addresses)
python customer-order.py --action insert --customers 100 --orders 1000 --no-api

# Combine options for optimal performance
python customer-order.py --action insert --clean --customers 200 --orders 2000 --batch-size 100 --no-api
```

## Performance Notes

- **API calls**: Limited to 1 per second to respect rate limits
- **Caching**: Results are cached to minimize repeated API calls
- **Fallback**: Automatic fallback ensures script reliability
- **Batch processing**: Large datasets are processed efficiently

### 🚀 Performance Optimizations
- **Batch Inserts**: Uses `executemany` for faster database operations (configurable with `--batch-size`)
- **Address Pre-caching**: Pre-generates addresses for common countries to reduce API calls
- **Smart Rate Limiting**: Only applies delays when building initial cache
- **Real-time Progress**: Shows progress every 10 orders with detailed logging

### 📊 Progress Monitoring
- **Every 10 orders**: Real-time progress updates (overwrites same line)
- **Every 100 orders**: Major milestone updates
- **Address generation**: Shows progress during API calls
- **Batch completion**: Confirms each batch of orders inserted

## Troubleshooting

### API Issues
If you experience API timeouts or failures:
1. Check your internet connection
2. Use `--no-api` flag to disable API usage
3. The script will automatically fall back to generated addresses

### Database Issues
- Ensure PostgreSQL is running and accessible
- Check your `.env` file configuration
- Verify database permissions

## Expected Output

### 🌍 With API Enabled (Default)
```
🌍 Using OpenStreetMap API for realistic addresses
   (Use --no-api to disable API usage)
Inserting 100 customers with unique emails...
  Progress: 100/100 customers inserted
✓ Inserted 100 customers (after 100 attempts)
Inserting 1000 orders with international shipping addresses...
  Using batch size: 100
  Pre-generating addresses for common destinations...
  ✓ Address cache populated
    Generating addresses... 51/1000 orders...
    Generating addresses... 101/1000 orders...
  Progress: 100/1000 orders inserted
    Generating addresses... 151/1000 orders...
    Generating addresses... 201/1000 orders...
  Progress: 200/1000 orders inserted
...
✓ Inserted 1000 orders with international shipping
```

### 📍 With API Disabled (Maximum Speed)
```
📍 Using generated addresses (API disabled)
Inserting 100 customers with unique emails...
  Progress: 100/100 customers inserted
✓ Inserted 100 customers (after 100 attempts)
Inserting 1000 orders with international shipping addresses...
  Using batch size: 100
    10/1000 orders...
    20/1000 orders...
    30/1000 orders...
  Progress: 100/1000 orders inserted
...
✓ Inserted 1000 orders with international shipping
```

## Contributing

To add support for more countries:
1. Add country-specific search queries in `search_queries` dictionary
2. Add country-specific address formatting in `_format_nominatim_address`
3. Test with real data from that country
