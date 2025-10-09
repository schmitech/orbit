# Creating Seed Templates for Your Schema

This guide shows you how to create high-quality seed template files for any database schema.

## Quick Start

```bash
# 1. Create enriched queries
cp examples/contact_test_queries_enriched.md examples/your-schema_test_queries_enriched.md
# Edit to match your schema

# 2. Generate seed templates
./create_seed_templates.sh your-schema

# 3. Review and refine the output
# 4. Test with your adapter
```

---

## Step-by-Step Process

### Step 1: Organize Your Test Queries

Create an enriched query file with clear categories:

**File:** `examples/your-schema_test_queries_enriched.md`

```markdown
# Your Schema - Enriched Test Queries

## Category 1: Basic List All
<!-- Intent: list, Entity: main_entity, Filter: none -->

Show me all items
List all records
Get all entries

---

## Category 2: Search by Primary Field
<!-- Intent: search, Entity: main_entity, Filter: field_name (exact) -->

Find item by ID
Get record with ID 123
Show me item #456

---

## Category 3: Filter by Status
<!-- Intent: filter, Entity: main_entity, Filter: status (exact) -->

Show active items
Find pending records
Get completed entries

---

## Category 4: Date Range Filter
<!-- Intent: filter, Entity: main_entity, Filter: date (range) -->

Show items from last week
Find records created this month
Get entries from 2024

---

## Category 5: Count Total
<!-- Intent: count, Entity: main_entity, Aggregation: COUNT(*) -->

How many items do we have?
Count all records
What's the total?

---

... (continue with 15-25 categories)
```

### Step 2: Run the Generator

```bash
./create_seed_templates.sh your-schema --provider ollama_cloud
```

This will:
1. Use AI to analyze your queries
2. Generate SQL templates
3. Create parameter definitions
4. Add natural language examples

### Step 3: Review Generated Templates

The script outputs to `/tmp/your-schema-auto-generated.yaml`

**What to check:**

#### ✅ SQL Quality
```yaml
# BAD - Missing important fields
sql_template: SELECT * FROM users

# GOOD - Specific columns, proper ordering
sql_template: |
  SELECT id, name, email, created_at
  FROM users
  ORDER BY created_at DESC
  LIMIT ? OFFSET ?
```

#### ✅ Parameter Defaults
```yaml
# BAD - Null defaults cause errors
parameters:
  - name: limit
    type: integer
    default: null

# GOOD - Actual values
parameters:
  - name: limit
    type: integer
    default: 100
```

#### ✅ Descriptions
```yaml
# BAD - Too generic
description: Get users

# GOOD - Specific and clear
description: Search users by partial name match (case-insensitive) with pagination
```

#### ✅ Natural Language Examples
```yaml
# BAD - Too few or repetitive
nl_examples:
  - "Find users"
  - "Get users"

# GOOD - Diverse and specific
nl_examples:
  - "Find users named John"
  - "Show me users with Smith in their name"
  - "Search for Alice Brown"
  - "Get all users named Wilson"
```

#### ✅ Tags
```yaml
# BAD - Missing or too generic
tags: [search]

# GOOD - Specific and useful
tags: [search, name, partial_match, text_filter, user]
```

### Step 4: Common Refinements

#### Add Indexes (PostgreSQL)
```yaml
# Before
sql_template: |
  SELECT * FROM orders WHERE customer_id = ?

# After - hint at index usage
sql_template: |
  SELECT order_id, customer_id, order_date, total
  FROM orders
  WHERE customer_id = ?  -- Uses idx_orders_customer_id
  ORDER BY order_date DESC
```

#### Optimize Aggregations
```yaml
# Before
sql_template: SELECT COUNT(*) FROM users WHERE active = 1

# After - more efficient
sql_template: |
  SELECT COUNT(*) as active_users
  FROM users
  WHERE active = 1
  -- Consider materialized view for large tables
```

#### Add Safety Limits
```yaml
# Before - no protection
sql_template: SELECT * FROM logs

# After - add LIMIT
sql_template: |
  SELECT timestamp, level, message
  FROM logs
  ORDER BY timestamp DESC
  LIMIT ? OFFSET ?
```

### Step 5: Save as Seed Templates

Once refined:

```bash
cp /tmp/your-schema-auto-generated.yaml \
   examples/your-schema_seed_templates.yaml
```

---

## Category Planning Guide

### For E-commerce Schemas

1. **Product Queries**
   - List all products
   - Search by name/SKU
   - Filter by category
   - Filter by price range
   - Filter by availability

2. **Customer Queries**
   - Search by name/email
   - Filter by location
   - Filter by membership tier
   - Recent customers

3. **Order Queries**
   - Search by order ID
   - Filter by status
   - Filter by date range
   - Filter by customer
   - Calculate totals

4. **Analytics Queries**
   - Revenue by period
   - Top products
   - Customer lifetime value
   - Sales trends

### For Security/Classified Schemas

1. **Access Control**
   - Filter by classification level
   - Filter by clearance required
   - Filter by compartment

2. **Audit Queries**
   - Access attempts by user
   - Access by date range
   - Failed access attempts

3. **Document Queries**
   - Search by title/content
   - Filter by organization
   - Filter by classification
   - Expiring documents

4. **Compliance Queries**
   - Items needing review
   - Overdue for declassification
   - PII-containing items

### For Content/Library Schemas

1. **Search Queries**
   - By title/author
   - By ISBN/identifier
   - By category/genre
   - Full-text search

2. **Availability**
   - Available items
   - Checked out items
   - Reserved items
   - Overdue items

3. **User Queries**
   - Active members
   - Borrowing history
   - Fines/holds

4. **Statistics**
   - Most popular items
   - Circulation stats
   - Member activity

---

## Best Practices

### 1. Template Naming

**Use descriptive IDs:**
```yaml
# Good
- id: search_products_by_name_partial
- id: filter_orders_by_status_and_date
- id: count_active_users_by_region

# Bad
- id: query1
- id: search
- id: get_data
```

### 2. Parameter Design

**Make it user-friendly:**
```yaml
# Good - clear names and descriptions
parameters:
  - name: min_price
    type: decimal
    description: Minimum price in USD (inclusive)
    required: false
    default: 0.00
  - name: max_price
    type: decimal
    description: Maximum price in USD (inclusive)
    required: false
    default: 999999.99

# Bad - unclear
parameters:
  - name: p1
    type: decimal
    required: true
  - name: p2
    type: decimal
    required: true
```

### 3. SQL Optimization

**Think about performance:**
```yaml
# Good - specific columns, proper indexes
sql_template: |
  SELECT p.product_id, p.name, p.price, c.category_name
  FROM products p
  INNER JOIN categories c ON p.category_id = c.category_id
  WHERE p.category_id = ?
    AND p.price BETWEEN ? AND ?
    AND p.in_stock = 1
  ORDER BY p.price ASC
  LIMIT ? OFFSET ?

# Bad - SELECT *, no indexes considered
sql_template: |
  SELECT * FROM products
  WHERE category_id = ? AND price >= ? AND price <= ?
```

### 4. Template Coverage

**Aim for comprehensive coverage:**

| Query Type | Example Templates | Count |
|------------|-------------------|-------|
| Basic List | List all X | 1 |
| Search | By name, ID, email, etc. | 3-5 |
| Filter Single Field | By status, type, category | 3-5 |
| Filter Range | By date, price, age | 2-3 |
| Filter Multi-Field | City + age, status + date | 2-4 |
| Count/Aggregate | Total, by group, statistics | 3-5 |
| Sort | By different fields | 2-3 |
| Top N | Oldest, newest, highest, etc. | 2-3 |
| Existence Checks | Does X exist? | 1-2 |
| **Total** | | **20-30** |

---

## Testing Your Seed Templates

### 1. Syntax Validation

```bash
# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('examples/your-schema_seed_templates.yaml'))"
```

### 2. SQL Validation

Run each SQL template against your database:

```sql
-- Test with actual parameters
SELECT id, name, email, age, city, created_at
FROM users
WHERE name LIKE '%' || 'John' || '%'
ORDER BY name
LIMIT 100 OFFSET 0;
```

### 3. Integration Testing

```bash
# 1. Copy to config
cp examples/your-schema_seed_templates.yaml \
   config/sql_intent_templates/examples/your-schema/

# 2. Update adapter config to reload
# Set: reload_templates_on_start: true

# 3. Restart ORBIT and test
python main.py

# 4. Test queries via API
curl -X POST http://localhost:8718/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-key" \
  -d '{"message": "Find users named John", "adapters": ["your-adapter"]}'
```

---

## Examples

### Minimal Seed Template (5 templates)

Good for very simple schemas:

1. List all records
2. Search by primary field
3. Filter by status
4. Count total
5. Recent items

### Standard Seed Template (15-20 templates)

Good for typical business schemas:

1. Basic list (1)
2. Search operations (3-4)
3. Single-field filters (3-4)
4. Range filters (2-3)
5. Aggregations (3-4)
6. Sorting (2-3)
7. Existence checks (1-2)

### Comprehensive Seed Template (25-30 templates)

Good for complex schemas:

- All standard templates plus:
- Multi-field filters (3-4)
- Complex aggregations (2-3)
- Top N queries (2-3)
- Advanced search (2-3)
- Analytics queries (2-3)

---

## Common Issues

### Issue: Too Few Templates Generated

**Cause:** Queries too similar or high similarity threshold

**Fix:**
1. Add more diverse query categories
2. Lower similarity threshold in config
3. Make queries more specific

### Issue: Templates Too Generic

**Cause:** Queries not specific enough

**Fix:**
1. Add more parameters to queries
2. Specify exact field names
3. Include examples with actual values

### Issue: Parameter Binding Errors

**Cause:** Null defaults or wrong parameter types

**Fix:**
1. Check all `default: null` → replace with actual values
2. Verify parameter types match SQL
3. Test with actual parameter values

---

## Quick Reference: Schema → Seed Templates

```bash
# 1. Prepare
cp examples/contact_test_queries_enriched.md \
   examples/your-schema_test_queries_enriched.md

# Edit categories to match your schema (15-25 categories)

# 2. Generate
./create_seed_templates.sh your-schema

# 3. Review (opens in editor)
# Check: SQL, parameters, descriptions, examples

# 4. Save
cp /tmp/your-schema-auto-generated.yaml \
   examples/your-schema_seed_templates.yaml

# 5. Deploy
cp examples/your-schema_seed_templates.yaml \
   config/sql_intent_templates/examples/your-schema/templates.yaml

# 6. Test
python main.py
# Run test queries
```

---

## See Also

- [ENRICHMENT_GUIDE.md](examples/ENRICHMENT_GUIDE.md) - Template enrichment strategies
- [BEFORE_AFTER_COMPARISON.md](examples/BEFORE_AFTER_COMPARISON.md) - Quality comparison
- [contact_seed_templates.yaml](examples/contact_seed_templates.yaml) - Reference example
- [template_generator.py](template_generator.py) - Generator source code
