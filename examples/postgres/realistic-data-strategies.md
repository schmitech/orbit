# Realistic Data Generation Strategies for Business Analytics

This document outlines various randomization strategies to make the customer-order.py script generate more realistic business data for analytics purposes.

## 1. Temporal Patterns & Seasonality

### Business Hours Distribution
```python
def get_realistic_order_time():
    """Generate order timestamps with realistic business patterns"""
    # More orders during business hours (9 AM - 5 PM): 70% of orders
    # Evening orders (5 PM - 10 PM): 20% of orders  
    # Night/early morning (10 PM - 9 AM): 10% of orders
    
    # Weekend penalty: 30% fewer orders on weekends
    # Holiday effects: 50% spike during Black Friday, Christmas
    # Seasonal patterns: Summer dip, winter peak
```

### Seasonal Multipliers
- **Q1 (Jan-Mar)**: 0.9x (post-holiday dip)
- **Q2 (Apr-Jun)**: 1.0x (baseline)
- **Q3 (Jul-Sep)**: 0.8x (summer vacation dip)
- **Q4 (Oct-Dec)**: 1.3x (holiday shopping spike)

### Time Zone Effects
- Orders cluster around local business hours
- International orders follow destination time zones
- Peak ordering times: 10 AM - 2 PM and 7 PM - 9 PM

## 2. Customer Behavior Patterns

### Customer Segments
```python
def generate_customer_segments():
    """Create realistic customer behavior patterns"""
    segments = {
        'new_customers': {
            'percentage': 20,
            'order_frequency': '1-2 orders total',
            'avg_order_value': '$25-75',
            'characteristics': 'First-time buyers, price-sensitive'
        },
        'regular_customers': {
            'percentage': 60,
            'order_frequency': '2-10 orders over 24 months',
            'avg_order_value': '$50-150',
            'characteristics': 'Steady purchasers, brand loyal'
        },
        'vip_customers': {
            'percentage': 15,
            'order_frequency': '10+ orders over 24 months',
            'avg_order_value': '$200-500',
            'characteristics': 'High value, frequent buyers'
        },
        'inactive_customers': {
            'percentage': 5,
            'order_frequency': '1 order only',
            'avg_order_value': '$30-80',
            'characteristics': 'One-time buyers, price-driven'
        }
    }
```

### Customer Lifecycle Patterns
- **Onboarding**: New customers get welcome discounts
- **Retention**: Regular customers have higher repeat rates
- **Churn**: Inactive customers after 6+ months of no orders
- **Win-back**: Special offers for dormant customers

### Loyalty Program Effects
- 30% of customers are loyalty members
- Members have 25% higher order frequency
- Members have 15% higher average order value
- Members more likely to try new products

## 3. Order Value Distribution

### Power Law Distribution
```python
def get_realistic_order_value(customer_segment):
    """Generate order values using power law distribution"""
    # Small orders (60%): $10-$50
    # Medium orders (30%): $50-$200  
    # Large orders (8%): $200-$500
    # VIP orders (2%): $500-$2000
    
    # Use numpy.random.pareto() for realistic distribution
    # Apply customer segment multipliers
    # Add seasonal price variations
```

### Order Value Patterns
- **Bulk purchases**: 5% of orders are 3x+ average value
- **Seasonal pricing**: 10-20% price variations by season
- **Promotional effects**: 15% of orders have discounts
- **Currency effects**: International orders have exchange rate variations

### Product Category Value Ranges
- **Electronics**: $50-$2000 (high value, seasonal)
- **Clothing**: $20-$300 (moderate value, seasonal)
- **Home goods**: $30-$500 (steady value)
- **Books/Media**: $10-$100 (low value, steady)
- **Specialty items**: $100-$2000 (high value, low volume)

## 4. Product Categories & Order Complexity

### Product Category Distribution
```python
def generate_product_categories():
    """Realistic product category distribution"""
    categories = {
        'electronics': {
            'percentage': 30,
            'avg_value': '$150',
            'seasonality': 'High during holidays',
            'return_rate': 0.08
        },
        'clothing': {
            'percentage': 25,
            'avg_value': '$75',
            'seasonality': 'Strong seasonal patterns',
            'return_rate': 0.15
        },
        'home_goods': {
            'percentage': 20,
            'avg_value': '$100',
            'seasonality': 'Steady demand',
            'return_rate': 0.05
        },
        'books_media': {
            'percentage': 15,
            'avg_value': '$25',
            'seasonality': 'Low seasonal variation',
            'return_rate': 0.02
        },
        'specialty': {
            'percentage': 10,
            'avg_value': '$300',
            'seasonality': 'Event-driven',
            'return_rate': 0.12
        }
    }
```

### Order Complexity Patterns
- **Single item orders**: 60% of orders
- **Multi-item orders**: 35% of orders (2-5 items)
- **Bulk orders**: 5% of orders (6+ items)
- **Bundle purchases**: 10% of orders include bundles
- **Cross-selling**: 20% of orders include recommended items

## 5. Geographic & Demographic Realism

### Geographic Distribution Patterns
```python
def get_realistic_geographic_patterns():
    """Generate realistic geographic distribution"""
    # Urban vs rural: 70% urban, 30% rural
    # Income-based shipping preferences
    # Regional product preferences
    # Time zone effects on order timing
    
    # Metropolitan areas: Higher order frequency
    # Rural areas: Higher average order value (bulk buying)
    # International: Different payment preferences
```

### Regional Preferences
- **North America**: Credit cards (80%), PayPal (15%), Other (5%)
- **Europe**: Bank transfer (40%), Credit cards (35%), PayPal (25%)
- **Asia**: Digital wallets (60%), Credit cards (30%), Other (10%)

### Demographic Clustering
- **Age groups**: Different product preferences by age
- **Income levels**: Higher income = higher order values
- **Family size**: Larger families = bulk purchases
- **Urban density**: Urban areas = more frequent, smaller orders

## 6. Business Process Realism

### Order Status Progression
```python
def simulate_order_lifecycle():
    """Realistic order status progression"""
    # pending (5%) - payment processing
    # processing (15%) - being prepared
    # shipped (60%) - in transit
    # delivered (18%) - completed
    # cancelled (2%) - various reasons
    
    # Status transition times:
    # pending → processing: 1-4 hours
    # processing → shipped: 1-3 days
    # shipped → delivered: 2-7 days
```

### Return & Refund Patterns
- **Return rate**: 8% of orders are returned
- **Refund reasons**: Size (40%), Defective (25%), Changed mind (20%), Other (15%)
- **Return timing**: 70% within 30 days, 30% after 30 days
- **Refund processing**: 3-7 business days

### Payment Method Realism
```python
def get_payment_method_distribution():
    """Realistic payment method distribution by region"""
    payment_methods = {
        'credit_card': 0.60,  # Most common
        'debit_card': 0.20,   # Second most common
        'paypal': 0.12,       # Online preferred
        'bank_transfer': 0.05, # International
        'cash': 0.03          # Rare for online
    }
```

## 7. Data Quality & Anomalies

### Missing Data Patterns
```python
def add_data_quality_issues():
    """Add realistic data quality issues"""
    # Missing phone numbers: 5% of customers
    # Incomplete addresses: 3% of orders
    # Missing email domains: 1% of customers
    # Duplicate entries: 0.1% of orders
    
    # Data entry errors:
    # Typos in names: 2% of customers
    # Address formatting issues: 8% of orders
    # Phone number inconsistencies: 10% of customers
```

### Test Data Contamination
- **Test orders**: 0.5% of orders are test data
- **Development accounts**: 0.1% of customers are test accounts
- **QA orders**: 0.2% of orders are quality assurance tests
- **Demo data**: 0.1% of orders are demonstration purposes

## 8. Customer Communication Patterns

### Support Ticket Correlation
```python
def add_customer_interactions():
    """Add realistic customer interaction patterns"""
    # 15% of customers create support tickets
    # 5% of orders generate support tickets
    # Support ticket types:
    #   - Order status (40%)
    #   - Shipping issues (25%)
    #   - Product questions (20%)
    #   - Returns/refunds (15%)
```

### Communication Preferences
- **Email engagement**: 70% of customers engage with emails
- **SMS notifications**: 40% of customers opt for SMS
- **Push notifications**: 60% of mobile app users
- **Newsletter subscription**: 45% of customers

## 9. Financial & Payment Realism

### Payment Processing Patterns
```python
def add_financial_realism():
    """Add realistic financial patterns"""
    # Failed payment attempts: 3% of orders
    # Payment retry success: 60% on second attempt
    # Currency conversion: International orders
    # Tax calculation: Varies by region (5-15%)
    
    # Processing delays:
    # Credit cards: 1-3 days
    # Bank transfers: 3-7 days
    # PayPal: Instant to 1 day
```

### Financial Anomalies
- **Chargebacks**: 0.5% of orders
- **Refunds**: 8% of orders
- **Partial refunds**: 2% of orders
- **Payment disputes**: 0.2% of orders

## 10. Operational Patterns

### Warehouse & Shipping Effects
```python
def add_operational_realism():
    """Add realistic operational patterns"""
    # Warehouse location effects:
    #   - East Coast: 2-5 day shipping
    #   - West Coast: 3-6 day shipping
    #   - International: 7-14 day shipping
    
    # Peak season constraints:
    #   - Holiday rush: 2x normal volume
    #   - Backorder scenarios: 5% of orders
    #   - Out-of-stock: 3% of orders
```

### Seasonal Operational Patterns
- **Holiday shipping deadlines**: Cutoff dates for delivery
- **Weather delays**: 2% of orders affected by weather
- **Staff scheduling**: Reduced capacity on weekends
- **System maintenance**: 0.1% of orders affected

## Implementation Priority

### Phase 1: Core Realism
1. **Temporal patterns** (business hours, seasonality)
2. **Customer behavior patterns** (segments, lifecycle)
3. **Order value distribution** (power law, categories)

### Phase 2: Business Process
4. **Product categories** (realistic distribution)
5. **Order status progression** (lifecycle simulation)
6. **Payment method realism** (regional preferences)

### Phase 3: Advanced Features
7. **Geographic patterns** (urban/rural, demographics)
8. **Data quality issues** (missing data, errors)
9. **Customer interactions** (support, communication)
10. **Operational patterns** (shipping, constraints)

## Usage Examples

```python
# Generate data with specific patterns
python customer-order.py --action insert \
  --customers 1000 \
  --orders 5000 \
  --enable-seasonality \
  --customer-segments \
  --product-categories \
  --temporal-patterns

# Generate data for specific analytics scenarios
python customer-order.py --action insert \
  --analytics-scenario "holiday-shopping" \
  --timeframe "q4-2023" \
  --customer-density "urban"
```

## Analytics Benefits

These patterns enable realistic analysis of:
- **Customer lifetime value** by segment
- **Seasonal trend analysis** and forecasting
- **Geographic performance** metrics
- **Product category** profitability
- **Payment method** success rates
- **Operational efficiency** metrics
- **Customer churn** prediction
- **Inventory optimization** insights
