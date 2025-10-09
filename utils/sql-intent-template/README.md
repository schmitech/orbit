# SQL Intent Template Generator

This tool automatically generates SQL templates for the Intent PostgreSQL retriever by analyzing natural language queries and database schemas using AI.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Shell Scripts](#shell-scripts)
3. [Configuration Files](#configuration-files)
4. [Schema-Specific Features](#schema-specific-features)
5. [Schema Adaptation Guide](#schema-adaptation-guide)
6. [Usage Examples](#usage-examples)
7. [Advanced Usage](#advanced-usage)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)
10. [Output Format](#output-format)

## Quick Start

### 1. Basic Usage

```bash
# Use the config selector to find the best configuration
python config_selector.py --schema your-schema.sql

# Generate templates with the recommended configuration
python template_generator.py \
    --schema your-schema.sql \
    --queries your-queries.md \
    --output generated-templates.yaml \
    --config configs/recommended-config.yaml
```

### 2. For Different Schema Types

#### Contact System (Recommended for Testing)
```bash
python template_generator.py \
    --schema examples/contact.sql \
    --queries examples/contact_test_queries.md \
    --output contact-templates.yaml \
    --config configs/contact-config.yaml
```

#### Classified Data Management System
```bash
python template_generator.py \
    --schema examples/classified-data.sql \
    --queries examples/classified-data_test_queries.md \
    --output classified-templates.yaml \
    --config configs/classified-data-config.yaml
```

#### Library Management System
```bash
python template_generator.py \
    --schema examples/library_management.sql \
    --queries examples/library_test_queries.md \
    --output library-templates.yaml \
    --config configs/library-config.yaml
```

#### Customer-Order System
```bash
python template_generator.py \
    --schema examples/customer-order.sql \
    --queries examples/customer-order_test_queries.md \
    --output customer-order-templates.yaml \
    --config configs/ecommerce-config.yaml
```

#### E-commerce System
```bash
python template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output ecommerce-templates.yaml \
    --config configs/ecommerce-config.yaml
```

#### Financial System
```bash
python template_generator.py \
    --schema financial-schema.sql \
    --queries financial-queries.md \
    --output financial-templates.yaml \
    --config configs/financial-config.yaml
```

## Shell Script

This directory contains a shell script to make it easy to run the template generator from the `sql-intent-template` directory.

### `generate_templates.sh` - Template Generation Script

A comprehensive script with all options and features.

**Usage:**
```bash
./generate_templates.sh [options]
```

**Examples:**
```bash
# Basic usage with specific configuration
./generate_templates.sh --schema database-schema.sql --queries test_queries.md --config configs/classified-data-config.yaml

# Contact example (recommended for testing)
./generate_templates.sh --schema examples/contact.sql --queries examples/contact_test_queries.md --config configs/contact-config.yaml

# Library management example
./generate_templates.sh --schema examples/library_management.sql --queries examples/library_test_queries.md --config configs/library-config.yaml

# Customer-order example
./generate_templates.sh --schema examples/customer-order.sql --queries examples/customer-order_test_queries.md --config configs/ecommerce-config.yaml

# E-commerce example
./generate_templates.sh --schema examples/postgres/customer-order.sql --queries examples/postgres/test/test_queries.md --config configs/ecommerce-config.yaml

# Test with limited queries
./generate_templates.sh --schema database-schema.sql --queries test_queries.md --config configs/contact-config.yaml --limit 10

# Verbose output
./generate_templates.sh --schema database-schema.sql --queries test_queries.md --config configs/contact-config.yaml --verbose
```

**Options:**
- `--schema FILE` - Path to SQL schema file (required)
- `--queries FILE` - Path to test queries markdown file (required)
- `--config FILE` - Path to configuration file (required)
- `--output FILE` - Path to output YAML file (optional, auto-generated if not provided)
- `--provider NAME` - Override inference provider (default: from config.yaml)
- `--limit NUMBER` - Limit number of queries to process
- `--verbose` - Enable verbose output
- `--help` - Show help message

### Quick Start

#### For Your Classified Data Schema
```bash
./generate_templates.sh --schema database-schema.sql --queries test_queries.md --config configs/classified-data-config.yaml
```

#### For Library Management Schema
```bash
./generate_templates.sh --schema examples/library_management.sql --queries examples/library_test_queries.md --config configs/library-config.yaml
```

#### For Customer-Order Schema
```bash
./generate_templates.sh --schema examples/customer-order.sql --queries examples/customer-order_test_queries.md --config configs/ecommerce-config.yaml
```

#### For E-commerce Schema
```bash
./generate_templates.sh --schema examples/postgres/customer-order.sql --queries examples/postgres/test/test_queries.md --config configs/ecommerce-config.yaml
```

#### For Custom Schema
```bash
./generate_templates.sh --schema your-schema.sql --queries your-queries.md --config configs/your-config.yaml
```

### Output Files

The script generates output files with timestamps:
- `database-schema_templates_20240115_143022.yaml`
- `customer-order_templates_20240115_143022.yaml`

### Provider Configuration

The script automatically reads the inference provider from your main Orbit configuration:

1. **Provider Setting**: The `inference_provider` setting in `../../config/config.yaml` determines which AI provider to use
2. **API Keys**: The corresponding API key from `../../config/inference.yaml` will be used automatically
3. **Override**: You can override the provider using the `--provider` flag if needed

**Example Configuration:**
```yaml
# In ../../config/config.yaml
general:
  inference_provider: "groq"  # or "ollama", "openai", "anthropic", etc.
```

**Required Environment Variables:**
- For Groq: `GROQ_API_KEY`
- For OpenAI: `OPENAI_API_KEY`
- For Anthropic: `ANTHROPIC_API_KEY`
- For Ollama: No API key needed (local)
- And so on based on your provider choice

### Prerequisites

Make sure you have:
1. Python 3 installed
2. Required Python packages: `pip install pyyaml`
3. The template generator files in the current directory
4. Your schema and query files
5. Main Orbit configuration file at `../../config/config.yaml`
6. Appropriate API keys set in environment variables (based on your `inference_provider` setting)

## Examples

The `examples/` directory contains sample SQL schemas and test queries to help you get started:

- `examples/contact.sql` - Ultra-simple single-table schema for basic testing
- `examples/contact_test_queries.md` - 150 basic test queries for quick validation
- `examples/library_management.sql` - Complete library management system with books, authors, members, loans, and reviews
- `examples/library_test_queries.md` - 195 test queries covering various library management scenarios
- `examples/customer-order.sql` - Simple e-commerce system with customers and orders
- `examples/customer-order_test_queries.md` - 200 test queries covering various business scenarios
- `examples/classified-data.sql` - Security-focused system for classified information management
- `examples/classified-data_test_queries.md` - 224 test queries covering various security scenarios

See [examples/README.md](examples/README.md) for detailed information about each example and how to use them.

## Configuration Files

### Available Configurations

- `configs/contact-config.yaml` - For ultra-simple single-table schemas
- `configs/classified-data-config.yaml` - For security/classified data systems
- `configs/ecommerce-config.yaml` - For e-commerce and customer-order systems  
- `configs/financial-config.yaml` - For financial and accounting systems
- `configs/library-config.yaml` - For library management systems
- `template_generator_config.yaml` - Default configuration (schema-agnostic)

### Configuration Selector

The `config_selector.py` script automatically analyzes your schema and suggests the best configuration:

```bash
# Analyze schema and get recommendations
python config_selector.py --schema your-schema.sql

# Generate custom configuration
python config_selector.py --schema your-schema.sql --output custom-config.yaml
```

## Schema-Specific Features

### Classified Data Management
- **Security-focused**: Higher similarity thresholds for stricter grouping
- **Classification awareness**: Handles clearance levels, compartments, and access control
- **Audit support**: Specialized patterns for access logging and compliance
- **PII handling**: Recognizes personally identifiable information flags

### E-commerce Systems
- **Business patterns**: Customer, order, and product queries
- **Standard fields**: Email, phone, address, payment information
- **Analytics support**: Sales reporting and customer analytics
- **Status tracking**: Order status, payment status, shipping status

### Financial Systems
- **Transaction focus**: Account balances, transaction history
- **Currency support**: Multi-currency and exchange rate handling
- **Compliance**: Tax calculations and regulatory reporting
- **Precision**: High accuracy requirements for financial calculations

## Schema Adaptation Guide

This guide explains how to configure `template_generator_config.yaml` to work effectively with different types of SQL schemas, from simple e-commerce databases to complex classified data management systems.

### Understanding the Current Configuration

The template generator uses several key configuration sections that can be adapted for different schemas:

1. **Schema Analysis** (`schema` section) - Identifies special column patterns
2. **Query Grouping** (`grouping` section) - Determines how similar queries are grouped
3. **Generation Settings** (`generation` section) - Controls template creation
4. **Validation Rules** (`validation` section) - Ensures template quality

### Schema-Specific Adaptations

#### 1. E-commerce/Customer-Order Schema

**Example Schema**: `examples/postgres/customer-order.sql`

**Key Characteristics**:
- Simple customer-order relationship
- Standard business entities (customers, orders, products)
- Common fields: email, phone, address, dates, amounts

**Configuration Adaptations**:

```yaml
# Schema analysis for e-commerce
schema:
  special_columns:
    email:
      pattern: ".*email.*"
      format: "email"
    phone:
      pattern: ".*phone.*"
      format: "phone"
    date:
      pattern: ".*(date|_at)$"
      format: "date"
    amount:
      pattern: ".*(amount|total|price|cost).*"
      format: "currency"
    status:
      pattern: ".*status.*"
      format: "enum"

# Query grouping for business queries
grouping:
  features:
    - intent
    - primary_entity
    - secondary_entity
    - aggregations
    - filters
  feature_weights:
    intent: 0.3
    primary_entity: 0.3
    secondary_entity: 0.2
    aggregations: 0.1
    filters: 0.1

# Generation categories for business domain
generation:
  categories:
    - customer_queries
    - order_queries
    - analytics_queries
    - payment_queries
    - status_queries
```

#### 2. Classified Data Management Schema

**Example Schema**: `utils/sql-intent-template/database-schema.sql`

**Key Characteristics**:
- Security-focused with classification levels
- Complex access control and audit logging
- Specialized fields: clearance levels, compartments, PII flags
- Many-to-many relationships (users-compartments, items-compartments)

**Configuration Adaptations**:

```yaml
# Schema analysis for classified data
schema:
  special_columns:
    classification:
      pattern: ".*classification.*"
      format: "enum"
    clearance:
      pattern: ".*clearance.*"
      format: "enum"
    compartments:
      pattern: ".*compartment.*"
      format: "enum"
    pii:
      pattern: ".*pii.*"
      format: "boolean"
    caveats:
      pattern: ".*caveat.*"
      format: "enum"
    declass_date:
      pattern: ".*declass.*"
      format: "date"
    retention:
      pattern: ".*retention.*"
      format: "date"
    audit_decision:
      pattern: ".*decision.*"
      format: "enum"

# Query grouping for security domain
grouping:
  features:
    - intent
    - primary_entity
    - classification_level
    - access_decision
    - time_range
    - compartment_access
  feature_weights:
    intent: 0.25
    primary_entity: 0.25
    classification_level: 0.2
    access_decision: 0.15
    time_range: 0.1
    compartment_access: 0.05

# Generation categories for security domain
generation:
  categories:
    - access_control_queries
    - audit_queries
    - classification_queries
    - compartment_queries
    - user_clearance_queries
    - retention_queries
```

#### 3. Financial/Accounting Schema

**Key Characteristics**:
- Transaction-based data
- Complex calculations and aggregations
- Regulatory compliance fields
- Time-series data

**Configuration Adaptations**:

```yaml
# Schema analysis for financial data
schema:
  special_columns:
    amount:
      pattern: ".*(amount|total|balance|value).*"
      format: "currency"
    transaction_date:
      pattern: ".*(transaction|posting|effective)_date.*"
      format: "date"
    account:
      pattern: ".*account.*"
      format: "string"
    currency:
      pattern: ".*currency.*"
      format: "enum"
    tax:
      pattern: ".*tax.*"
      format: "decimal"
    reference:
      pattern: ".*(reference|ref|id).*"
      format: "string"

# Query grouping for financial domain
grouping:
  features:
    - intent
    - primary_entity
    - calculation_type
    - time_period
    - account_type
    - aggregation_level
  feature_weights:
    intent: 0.2
    primary_entity: 0.2
    calculation_type: 0.2
    time_period: 0.2
    account_type: 0.1
    aggregation_level: 0.1

# Generation categories for financial domain
generation:
  categories:
    - transaction_queries
    - balance_queries
    - reporting_queries
    - reconciliation_queries
    - compliance_queries
    - audit_queries
```

### Advanced Configuration Strategies

#### 1. Multi-Domain Support

For schemas that span multiple domains, you can create domain-specific configurations:

```yaml
# Multi-domain configuration
generation:
  domains:
    ecommerce:
      categories:
        - customer_queries
        - order_queries
        - product_queries
      similarity_threshold: 0.8
    security:
      categories:
        - access_control_queries
        - audit_queries
        - classification_queries
      similarity_threshold: 0.9  # Stricter grouping for security
    analytics:
      categories:
        - reporting_queries
        - dashboard_queries
        - kpi_queries
      similarity_threshold: 0.7  # More permissive for analytics
```

#### 2. Dynamic Schema Detection

The template generator can automatically detect schema patterns:

```yaml
# Auto-detection configuration
schema:
  auto_detect_patterns: true
  detection_rules:
    - pattern: ".*_id$"
      type: "foreign_key"
    - pattern: ".*_at$"
      type: "timestamp"
    - pattern: ".*_date$"
      type: "date"
    - pattern: ".*_email$"
      type: "email"
    - pattern: ".*_phone$"
      type: "phone"
```

#### 3. Custom Validation Rules

Add schema-specific validation:

```yaml
# Custom validation for classified data
validation:
  custom_rules:
    - name: "classification_consistency"
      description: "Ensure classification levels are consistent"
      check: "template.sql_template contains classification checks"
    - name: "audit_trail_required"
      description: "Audit queries must include timestamp filters"
      check: "template.semantic_tags.action == 'audit' and 'time_range' in template.parameters"
```

### Best Practices for Schema Adaptation

#### 1. Start with Schema Analysis

1. **Identify Key Entities**: What are the main tables/entities in your schema?
2. **Map Relationships**: How are tables connected (foreign keys, many-to-many)?
3. **Categorize Fields**: What types of data do you have (dates, amounts, statuses, etc.)?
4. **Understand Business Logic**: What are the common query patterns?

#### 2. Configure Special Columns

```yaml
schema:
  special_columns:
    # Add patterns that match your schema's naming conventions
    your_field_type:
      pattern: ".*your_pattern.*"
      format: "your_format"
```

#### 3. Adjust Query Grouping

```yaml
grouping:
  features:
    # Add features that matter for your domain
    - intent
    - primary_entity
    - your_domain_specific_feature
  feature_weights:
    # Adjust weights based on what's most important for grouping
    intent: 0.3
    primary_entity: 0.3
    your_domain_specific_feature: 0.4
```

#### 4. Set Appropriate Categories

```yaml
generation:
  categories:
    # Create categories that match your business domain
    - your_domain_queries
    - your_analytics_queries
    - your_reporting_queries
```

## Usage Examples

This section provides practical examples of how to use the template generator with different types of SQL schemas.

### Example 1: Classified Data Management System

#### Schema: `examples/classified-data.sql`
This schema contains tables for managing classified information with security clearances, compartments, and access audit logging.

#### Step 1: Analyze the Schema
```bash
cd /Users/remsyschmilinsky/Downloads/orbit/utils/sql-intent-template
python config_selector.py --schema examples/classified-data.sql --verbose
```

**Expected Output:**
```
Schema Analysis Results:
Detected Domain: classified_data
Confidence Score: 15
Recommended Config: classified-data-config.yaml

All Domain Scores:
  classified_data: 15
  ecommerce: 2
  financial: 1
  inventory: 0
  hr: 0

Next Steps:
1. Use the recommended config: configs/classified-data-config.yaml
2. Or generate a custom config: python config_selector.py --schema database-schema.sql --output custom-config.yaml
3. Run template generator: python template_generator.py --schema database-schema.sql --config <config_file>
```

#### Step 2: Generate Templates
```bash
python template_generator.py \
    --schema examples/classified-data.sql \
    --queries examples/classified-data_test_queries.md \
    --output classified-templates.yaml \
    --config configs/classified-data-config.yaml \
    --provider ollama
```

#### Step 3: Review Generated Templates
The generated templates will include:
- Access control queries (user clearance validation)
- Audit queries (access logging and compliance)
- Classification queries (by security level)
- Compartment queries (need-to-know access)
- User management queries
- Retention queries (declassification dates)

### Example 2: Library Management System

#### Schema: `examples/library_management.sql`
This schema contains a complete library management system with books, authors, members, loans, and reviews.

#### Step 1: Analyze the Schema
```bash
python config_selector.py --schema examples/library_management.sql --verbose
```

**Expected Output:**
```
Schema Analysis Results:
Detected Domain: ecommerce
Confidence Score: 8
Recommended Config: ecommerce-config.yaml
```

#### Step 2: Generate Templates
```bash
python template_generator.py \
    --schema examples/library_management.sql \
    --queries examples/library_test_queries.md \
    --output library-templates.yaml \
    --config configs/library-config.yaml \
    --provider ollama
```

#### Step 3: Review Generated Templates
The generated templates will include:
- Book queries (find by title, author, category, ISBN)
- Member queries (find by name, email, membership type)
- Loan queries (active, overdue, returned loans)
- Reservation queries (pending, fulfilled, cancelled)
- Review queries (by rating, book, member)
- Complex multi-criteria searches

### Example 3: Customer-Order System

#### Schema: `examples/customer-order.sql`
This schema contains a simple e-commerce system with customers and orders.

#### Step 1: Analyze the Schema
```bash
python config_selector.py --schema examples/customer-order.sql --verbose
```

**Expected Output:**
```
Schema Analysis Results:
Detected Domain: ecommerce
Confidence Score: 8
Recommended Config: ecommerce-config.yaml
```

#### Step 2: Generate Templates
```bash
python template_generator.py \
    --schema examples/customer-order.sql \
    --queries examples/customer-order_test_queries.md \
    --output customer-order-templates.yaml \
    --config configs/ecommerce-config.yaml \
    --provider ollama
```

#### Step 3: Review Generated Templates
The generated templates will include:
- Customer queries (find by name, email, phone, location)
- Order queries (by customer, date, status, amount)
- Payment method queries (credit card, PayPal, etc.)
- Geographic analysis (orders by location)
- Customer analytics and behavior patterns
- Order management and tracking
- Revenue and sales analysis

### Example 4: E-commerce System

#### Schema: `examples/postgres/customer-order.sql`
This schema contains standard e-commerce tables for customers and orders.

#### Step 1: Analyze the Schema
```bash
python config_selector.py --schema examples/postgres/customer-order.sql --verbose
```

**Expected Output:**
```
Schema Analysis Results:
Detected Domain: ecommerce
Confidence Score: 8
Recommended Config: ecommerce-config.yaml
```

#### Step 2: Generate Templates
```bash
python template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output ecommerce-templates.yaml \
    --config configs/ecommerce-config.yaml \
    --provider ollama
```

#### Step 3: Review Generated Templates
The generated templates will include:
- Customer queries (find by name, email, location)
- Order queries (by customer, date, status)
- Analytics queries (sales totals, customer metrics)
- Payment queries (payment methods, amounts)
- Shipping queries (addresses, delivery status)

### Example 5: Custom Schema

#### Step 1: Create Custom Configuration
```bash
python config_selector.py \
    --schema your-custom-schema.sql \
    --output custom-config.yaml
```

#### Step 2: Customize the Configuration
Edit `custom-config.yaml` to add your domain-specific patterns:

```yaml
# Add your custom patterns
schema:
  special_columns:
    your_field_type:
      pattern: ".*your_pattern.*"
      format: "your_format"

# Add your categories
generation:
  categories:
    - your_domain_queries
    - your_analytics_queries
    - your_reporting_queries

# Adjust grouping for your domain
grouping:
  features:
    - intent
    - primary_entity
    - your_domain_feature
  feature_weights:
    intent: 0.3
    primary_entity: 0.3
    your_domain_feature: 0.4
```

#### Step 3: Generate Templates
```bash
python template_generator.py \
    --schema your-custom-schema.sql \
    --queries your-queries.md \
    --output custom-templates.yaml \
    --config custom-config.yaml \
    --provider ollama
```

### Example 6: Multi-Domain Schema

For schemas that span multiple domains, you can create a multi-domain configuration:

```yaml
# Multi-domain configuration
generation:
  domains:
    ecommerce:
      categories: [customer_queries, order_queries, product_queries]
      similarity_threshold: 0.8
    security:
      categories: [access_queries, audit_queries, compliance_queries]
      similarity_threshold: 0.9
    analytics:
      categories: [reporting_queries, dashboard_queries, kpi_queries]
      similarity_threshold: 0.7

# Use the appropriate domain based on query analysis
query_routing:
  ecommerce_keywords: [customer, order, product, payment]
  security_keywords: [access, audit, clearance, classification]
  analytics_keywords: [report, dashboard, kpi, metric]
```

### Example 7: Testing and Validation

#### Test with Limited Queries
```bash
python template_generator.py \
    --schema database-schema.sql \
    --queries test_queries.md \
    --output test-templates.yaml \
    --config configs/classified-data-config.yaml \
    --limit 5
```

#### Validate Generated Templates
```bash
# Check template quality
python -c "
import yaml
with open('test-templates.yaml', 'r') as f:
    data = yaml.safe_load(f)
    print(f'Generated {len(data[\"templates\"])} templates')
    for template in data['templates']:
        print(f'- {template[\"id\"]}: {template[\"description\"]}')
"
```

### Example 8: Production Workflow

#### 1. Development Phase
```bash
# Start with a small subset
python template_generator.py \
    --schema production-schema.sql \
    --queries dev-queries.md \
    --output dev-templates.yaml \
    --config configs/your-domain-config.yaml \
    --limit 10
```

#### 2. Testing Phase
```bash
# Test with more queries
python template_generator.py \
    --schema production-schema.sql \
    --queries test-queries.md \
    --output test-templates.yaml \
    --config configs/your-domain-config.yaml \
    --limit 50
```

#### 3. Production Phase
```bash
# Generate all templates
python template_generator.py \
    --schema production-schema.sql \
    --queries all-queries.md \
    --output production-templates.yaml \
    --config configs/your-domain-config.yaml
```

## Advanced Usage

### Multi-Domain Support
For schemas spanning multiple domains:

```yaml
generation:
  domains:
    ecommerce:
      categories: [customer_queries, order_queries]
      similarity_threshold: 0.8
    security:
      categories: [access_queries, audit_queries]
      similarity_threshold: 0.9
```

### Custom Validation Rules
Add domain-specific validation:

```yaml
validation:
  custom_rules:
    - name: "your_rule"
      description: "Your validation rule"
      check: "template.semantic_tags.your_field == 'expected_value'"
```

## Best Practices

### 1. Schema Preparation
- Ensure your schema file contains proper `CREATE TABLE` statements
- Include foreign key relationships
- Use descriptive column names
- Add comments for complex fields

### 2. Query Preparation
- Provide diverse, realistic queries
- Include edge cases and complex scenarios
- Use natural language that users would actually type
- Cover all major business use cases

### 3. Configuration Tuning
- Start with the recommended configuration for your domain
- Adjust `similarity_threshold` based on results:
  - Higher (0.9+) = fewer, more specific templates
  - Lower (0.7-) = more, broader templates
- Fine-tune `feature_weights` based on your domain priorities

### 4. Validation and Testing
- Always review generated templates before using in production
- Test templates with real queries
- Validate SQL syntax and parameter usage
- Check that templates cover your use cases

### 5. Start Small
- Test with `--limit` first
- Use domain configs: Choose the appropriate config for your schema type
- Validate output: Always review generated templates
- Iterate: Adjust configuration based on results
- Test thoroughly: Validate with real queries before production use

## Troubleshooting

### Common Issues

**Too Many Templates Generated**
- Increase `similarity_threshold` in configuration
- Adjust `feature_weights` to be more specific

**Too Few Templates Generated**
- Decrease `similarity_threshold` in configuration
- Add more diverse query examples

**Poor Template Quality**
- Check that your schema analysis patterns are correct
- Ensure query examples are representative
- Adjust validation rules

**Missing Domain Patterns**
- Add custom `special_columns` patterns
- Create domain-specific `categories`
- Adjust `feature_weights` for your domain

**Permission Denied**
```bash
chmod +x generate_templates.sh quick_generate.sh
```

**Python Not Found**
```bash
# Install Python 3
# On macOS: brew install python3
# On Ubuntu: sudo apt install python3
```

**Missing Dependencies**
```bash
pip install pyyaml
```

**File Not Found**
- Make sure you're running the script from the `sql-intent-template` directory
- Check that your schema and query files exist
- Use absolute paths if needed

### Debug Tips

1. Use `--verbose` flag for detailed logging
2. Test with `--limit` to process fewer queries first
3. Check generated templates for quality and completeness
4. Validate SQL syntax and parameter usage
5. Enable verbose logging to see how queries are analyzed
6. Check the generated templates for quality
7. Validate that SQL templates are syntactically correct
8. Ensure parameter names match between SQL and parameter definitions

### Debug Mode

Use the `--verbose` flag with the full script:
```bash
./generate_templates.sh --schema database-schema.sql --queries test_queries.md --config configs/contact-config.yaml --verbose
```

## Output Format

Generated templates follow this structure:

```yaml
generated_at: "2024-01-15T10:30:00"
generator_version: "1.0.0"
total_templates: 5
templates:
  - id: "find_customers_by_name"
    description: "Find customers by name or email"
    sql_template: |
      SELECT * FROM customers 
      WHERE name ILIKE %(name)s OR email ILIKE %(email)s
    parameters:
      - name: "name"
        type: "string"
        description: "Customer name to search for"
        required: true
      - name: "email"
        type: "string"
        description: "Customer email to search for"
        required: false
    nl_examples:
      - "Find customers named John"
      - "Show me customers with email containing @example.com"
    tags: ["find", "customer", "search"]
    semantic_tags:
      action: "find"
      primary_entity: "customer"
      secondary_entity: null
    version: "1.0.0"
    approved: false
    created_at: "2024-01-15T10:30:00"
    created_by: "template_generator"
```

## Common Patterns by Domain

### Classified Data Management
- Access control and clearance validation
- Audit logging and compliance reporting
- Classification level filtering
- Compartment-based access control
- Retention and declassification queries

### E-commerce
- Customer search and management
- Order processing and tracking
- Product catalog queries
- Sales analytics and reporting
- Payment and shipping information

### Financial Systems
- Transaction processing and history
- Account balance calculations
- Currency conversion and exchange rates
- Tax calculations and compliance
- Reconciliation and audit trails

### General Business
- Entity relationship queries
- Status tracking and updates
- Time-based filtering and reporting
- Aggregation and analytics
- Search and filtering operations

## Integration with Existing Workflow

You can integrate this script into your existing workflow:

```bash
# In your project's build script
cd utils/sql-intent-template
./generate_templates.sh --schema ../../database-schema.sql --queries ../../test_queries.md --config configs/classified-data-config.yaml

# In a CI/CD pipeline
cd utils/sql-intent-template
./generate_templates.sh --schema ../../database-schema.sql --queries ../../test_queries.md --config configs/contact-config.yaml --verbose
```

## Tips

1. **Test First**: Use `--limit` to test with fewer queries
2. **Choose Config**: Select the appropriate config for your schema type
3. **Check Output**: Always review generated templates
4. **Use Verbose**: Add `--verbose` for debugging

## Contributing

To add support for new schema types:

1. Create a new configuration file in `configs/`
2. Add domain patterns to `config_selector.py`
3. Update this README with examples
4. Test with real schemas and queries

## Support

For questions or issues:
1. Check the troubleshooting section above
2. Review the configuration examples
3. Test with the provided example schemas
4. Create an issue with your schema and configuration details