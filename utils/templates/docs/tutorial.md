# SQL Intent Template Generator - Complete Tutorial

**A step-by-step guide to creating natural language SQL query templates for Orbit**

This tutorial walks you through the complete process of setting up SQL Intent templates using a simple contact database as an example. By the end, you'll be able to query your database using natural language like "Show me all users from New York".

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Understanding the Workflow](#understanding-the-workflow)
3. [Step 1: Prepare Your Database Schema](#step-1-prepare-your-database-schema)
4. [Step 2: Create Test Queries](#step-2-create-test-queries)
5. [Step 3: Generate SQL Templates](#step-3-generate-sql-templates)
6. [Step 4: Generate Sample Data](#step-4-generate-sample-data)
7. [Step 5: Configure the Intent Adapter](#step-5-configure-the-intent-adapter)
8. [Step 6: Start Orbit and Test](#step-6-start-orbit-and-test)
9. [Validation and Troubleshooting](#validation-and-troubleshooting)
10. [Next Steps](#next-steps)

---

## Prerequisites

Before starting, ensure you have:

### Software Requirements
- Python 3.12+ installed
- Orbit installed
- Virtual environment activated
- Required Python packages installed

### Environment Setup

```bash
# Navigate to Orbit root directory
cd /path/to/orbit

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate     # On Windows

# Install required packages
pip install pyyaml anthropic openai faker
```

### API Keys Configuration

Create or update `../../.env` with:

```bash
# For OpenAI (recommended for production)
OPENAI_API_KEY=sk-your-key-here

# For Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-your-key-here

# For Ollama Cloud
OLLAMA_CLOUD_API_KEY=your-key-here
```

### Verify Configuration

Check that your `config/config.yaml` has a valid `inference_provider`:

```yaml
inference_provider: "ollama_cloud"  # or "openai" or "anthropic"
```

---

## Understanding the Workflow

The SQL Intent Template Generator follows this workflow:

```
1. Database Schema (SQL)
   ↓
2. Test Queries (Markdown) ← You write natural language questions
   ↓
3. Template Generator (AI-powered) ← Analyzes and creates templates
   ↓
4. Generated Files:
   - Domain Configuration (YAML) ← Entities, fields, relationships
   - SQL Templates (YAML) ← Parameterized queries with examples
   ↓
5. Orbit Intent Adapter ← Loads templates into vector store
   ↓
6. Natural Language Queries ← Users ask questions in plain English
   ↓
7. SQL Results ← Intent adapter matches query and executes SQL
```

---

## Step 1: Prepare Your Database Schema

Navigate to the template generator directory:

```bash
cd utils/sql-intent-template
```

### 1.1 Review the Contact Schema

The contact schema is already provided at `examples/contact.sql`:

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    age INTEGER,
    city TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

This is a simple single-table schema perfect for learning.

### 1.2 For Your Own Database

If you want to use your own database schema:

1. Export your database schema to a `.sql` file
2. Ensure it includes `CREATE TABLE` statements
3. Place it in `examples/` directory
4. Use it in the commands below by replacing `examples/contact.sql`

**Supported SQL Dialects:**
- SQLite
- PostgreSQL
- MySQL / MariaDB
- Oracle
- SQL Server

---

## Step 2: Create Test Queries

Test queries are natural language questions you want users to be able to ask. The AI uses these to learn patterns and generate SQL templates.

### 2.1 Option A: Use the Template Generator (Recommended)

Generate a starter template from your schema:

```bash
python create_query_template.py \
  --schema examples/contact.sql \
  --output my_contact_queries.md
```

**Output:** Creates `my_contact_queries.md` with organized sections and placeholder queries.

**Next:** Open the file and fill in real queries based on your use case.

### 2.2 Option B: Use the Existing Example

The contact example already has queries at `examples/contact_test_queries.md`:

```bash
cat examples/contact_test_queries.md
```

**Sample queries from the file:**

```markdown
## Basic User Search
1. "Show me all users"
2. "Find all users"
3. "List all users"
4. "Get all users"
5. "Display all users"

## Search by Name
1. "Find users with name John"
2. "Show me users named Sarah"
3. "Get users by name Michael"
...
```

### 2.3 Query Format Guidelines

**Format Requirements:**
- Numbered queries: `1. "Your question here"`
- Each query in quotes
- Natural language (how users actually ask)
- Variety is key (different phrasings, different use cases)

**Quality Tips:**
- ✅ **Be natural:** "Show me users from New York"
- ❌ **Avoid SQL-like:** "SELECT users WHERE city = 'New York'"
- ✅ **Be specific:** Use real values like "John", "New York", "age 30"
- ❌ **Avoid placeholders:** Don't use "NAME", "CITY", "VALUE"
- ✅ **Vary phrasing:** Same intent, different words
- ✅ **Include edge cases:** "How many users?", "Are there any users over 100?"

**Recommended Query Count:**
- Minimum: 20 queries per table
- Good: 50-100 queries
- Best: 100+ queries

More queries = better template quality and coverage!

---

## Step 3: Generate SQL Templates

Now use the AI-powered generator to create SQL templates from your queries.

### 3.1 Quick Start with the Example Script

The easiest way to get started:

```bash
./run_contact_example.sh
```

This runs the complete generation process and creates:
- `contact-example-output.yaml` - SQL templates
- `contact-example-domain.yaml` - Domain configuration

### 3.2 Manual Generation with Full Control

For more control over the process:

```bash
./generate_templates.sh \
  --schema examples/contact.sql \
  --queries examples/contact_test_queries.md \
  --output contact-templates.yaml \
  --domain configs/contact-config.yaml \
  --generate-domain \
  --domain-name "Contact Management" \
  --domain-type general \
  --domain-output contact-domain.yaml
```

**What each flag does:**

| Flag | Purpose | Example Value |
|------|---------|---------------|
| `--schema` | SQL schema file | `examples/contact.sql` |
| `--queries` | Natural language queries | `examples/contact_test_queries.md` |
| `--output` | Where to save SQL templates | `contact-templates.yaml` |
| `--domain` | Domain config for SQL dialect | `configs/contact-config.yaml` |
| `--generate-domain` | Auto-generate domain config | (flag only) |
| `--domain-name` | Name for your domain | `"Contact Management"` |
| `--domain-type` | Domain category | `general` or `specialized` |
| `--domain-output` | Where to save domain config | `contact-domain.yaml` |

**Optional flags:**

| Flag | Purpose | Default |
|------|---------|---------|
| `--limit N` | Process only first N queries | All queries |
| `--resume` | Resume from previous run | Start fresh |
| `--batch-size N` | Queries per batch | 10 |
| `--skip-validation` | Skip output validation | Validate |

### 3.3 What Gets Generated

The generator creates two files:

#### Domain Configuration (`contact-domain.yaml`)

Defines your database structure:

```yaml
domain_name: Contact Management
domain_type: general

entities:
  users:
    name: users
    entity_type: primary
    table_name: users
    primary_key: id
    display_name_field: name
    searchable_fields: [name, email, city]

fields:
  users:
    id:
      data_type: integer
      semantic_type: identifier
      filterable: true
    name:
      data_type: string
      searchable: true
      semantic_type: null
    email:
      data_type: string
      searchable: true
      semantic_type: email_address
    # ... more fields

semantic_types:
  email_address:
    patterns: [email, mail, contact]
  date_value:
    patterns: [date, created, time]
  identifier:
    patterns: [id, identifier, key]

vocabulary:
  action_verbs:
    find: [show, list, get, find, display, retrieve]
    filter: [filter, only, where, with]
    count: [count, how many, number of, total]
```

#### SQL Template Library (`contact-templates.yaml`)

Contains parameterized SQL queries with examples:

```yaml
templates:
  - id: "users_basic_search"
    description: "Basic user search and listing"
    sql_template: |
      SELECT id, name, email, age, city, created_at
      FROM users
      ORDER BY created_at DESC
      LIMIT ?
    parameters:
      - name: limit
        type: integer
        required: false
        default_value: 10
    examples:
      - "Show me all users"
      - "List all users"
      - "Find all users"
    semantic_tags:
      - users
      - basic_search
      - list_all

  - id: "users_by_city"
    description: "Search users by city"
    sql_template: |
      SELECT id, name, email, age, city, created_at
      FROM users
      WHERE city = ?
      ORDER BY name ASC
    parameters:
      - name: city
        type: string
        required: true
    examples:
      - "Find users from New York"
      - "Show me users in Chicago"
      - "List users from Los Angeles"
    semantic_tags:
      - users
      - city_search
      - location_filter
```

### 3.4 Monitor Generation Progress

During generation, you'll see:

```
📋 Parsing schema: examples/contact.sql
✅ Found 1 tables: users

📖 Loading test queries: examples/contact_test_queries.md
✅ Loaded 150 queries

🤖 Generating templates...
   Processing batch 1/15...
   Processing batch 2/15...
   ...

✅ Generated 8 templates

💾 Saving templates to: contact-templates.yaml
💾 Saving domain config to: contact-domain.yaml

✅ Generation complete!
```

**Typical generation time:**
- 50 queries: 30-60 seconds
- 150 queries: 2-4 minutes
- 500+ queries: 5-10 minutes

---

## Step 4: Generate Sample Data

Generate realistic test data for your contact database.

### 4.1 Navigate to Examples Directory

```bash
cd examples/sqlite
```

### 4.2 Install Faker Library

```bash
pip install faker
```

### 4.3 Generate Data

**Default (100 records):**

```bash
python generate_contact_data.py
```

**Custom number of records:**

```bash
python generate_contact_data.py --records 1000
```

**Custom output path:**

```bash
python generate_contact_data.py \
  --records 500 \
  --output /path/to/contact.db
```

**Clean existing data:**

```bash
python generate_contact_data.py --records 1000 --clean
```

### 4.4 Verify Data

**View sample records:**

```bash
sqlite3 contact.db "SELECT * FROM users LIMIT 5;"
```

**Check record count:**

```bash
sqlite3 contact.db "SELECT COUNT(*) FROM users;"
```

**Sample output:**

```
📊 Sample Data:
----------------------------------------------------------------------------------------------------
ID    Name                 Email                          Age   City                 Created
----------------------------------------------------------------------------------------------------
1     John Smith           jsmith@example.com             34    New York            2024-03-15 10:23:45
2     Sarah Johnson        sarahj@example.com             28    Los Angeles         2024-05-22 14:32:11
3     Michael Brown        mbrown@example.com             45    Chicago             2024-07-08 09:15:22
4     Emily Davis          edavis@example.com             31    Houston             2024-08-19 16:47:33
5     David Wilson         dwilson@example.com            39    Phoenix             2024-09-30 11:28:54

📈 Database Statistics:
   Total Users: 1000
   Unique Cities: 40
   Age Range: 18 - 80 (avg: 49.3)

   Top 5 Cities:
      New York: 67 users
      Los Angeles: 54 users
      Chicago: 48 users
      Houston: 42 users
      Phoenix: 38 users
```

### 4.5 Return to Template Directory

```bash
cd ../..  # Back to utils/sql-intent-template
```

---

## Step 5: Configure the Intent Adapter

Deploy your generated templates to Orbit.

### 5.1 Copy Templates to Config Directory

```bash
# Create contact directory if it doesn't exist
mkdir -p ../../config/sql_intent_templates/examples/contact

# Copy domain configuration
cp contact-domain.yaml \
   ../../config/sql_intent_templates/examples/contact/

# Copy SQL templates
cp contact-templates.yaml \
   ../../config/sql_intent_templates/examples/contact/
```

### 5.2 Configure Database Connection

Edit `../../config/datasources.yaml`:

```yaml
datasources:
  sqlite:
    type: "sqlite"
    path: "utils/sql-intent-template/examples/sqlite/contact.db"
    check_same_thread: false
```

**Note:** Adjust the path based on where you generated the database.

### 5.3 Enable the Contact Adapter

The adapter is already configured in `../../config/adapters.yaml`. Verify it's enabled:

```yaml
- name: "intent-sql-sqlite-contact"
  enabled: true  # Make sure this is true
  type: "retriever"
  datasource: "sqlite"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentSQLiteRetriever"
  inference_provider: "ollama_cloud"
  model: "gpt-oss:20b"
  embedding_provider: "ollama"
  config:
    domain_config_path: "config/sql_intent_templates/examples/contact/contact-domain.yaml"
    template_library_path:
      - "config/sql_intent_templates/examples/contact/contact-templates.yaml"
    template_collection_name: "contact_intent_templates"
    store_name: "chroma"
    confidence_threshold: 0.4
    max_templates: 5
    return_results: 10
    reload_templates_on_start: false
    force_reload_templates: false
```

**Important Settings:**

| Setting | Purpose | Recommended Value |
|---------|---------|-------------------|
| `enabled` | Enable/disable adapter | `true` |
| `confidence_threshold` | Minimum match confidence | `0.4` (adjust based on results) |
| `max_templates` | Templates to consider | `5` |
| `return_results` | Max results to return | `10` |
| `reload_templates_on_start` | Reload on every start | `false` (set `true` when testing) |
| `force_reload_templates` | Force reload even if cached | `false` (set `true` to clear cache) |

### 5.4 Configure System Prompt (Optional)

For better response quality, configure a system prompt that defines the assistant's personality and behavior:

```yaml
- name: "intent-sql-sqlite-contact"
  enabled: true
  config:
    # ... other config ...
    system_prompt_path: "examples/prompts/contact-assistant-prompt.txt"
```

The contact assistant prompt provides:
- Privacy-conscious data handling
- Bilingual support (English/French)
- Consistent formatting for ages, locations, emails
- Statistical analysis capabilities
- Natural, conversational responses

See `examples/prompts/README.md` for more information on system prompts.

### 5.5 For First-Time Setup or Template Changes

If you're running for the first time or have updated templates:

```yaml
reload_templates_on_start: true   # Load templates on startup
force_reload_templates: true      # Clear cache and reload
```

After successful loading, change back to `false` for better performance.

---

## Step 6: Start Orbit and Test

Now it's time to test your natural language SQL queries!

### 6.1 Navigate to Orbit Root

```bash
cd ../..  # From utils/sql-intent-template to orbit root
```

### 6.2 Start Orbit Server

```bash
# With default settings
python -m server.app

# With specific port
python -m server.app --port 8080

# With debug mode
python -m server.app --debug
```

### 6.3 Monitor Startup Logs

Watch for template loading confirmation:

```
INFO: Starting Orbit server...
INFO: Loading Intent adapter: intent-sql-sqlite-contact
INFO: Loading domain config: config/sql_intent_templates/examples/contact/contact-domain.yaml
INFO: Loading template library: config/sql_intent_templates/examples/contact/contact-templates.yaml
INFO: Loaded 8 templates into collection: contact_intent_templates
INFO: Intent adapter ready
INFO: Server started on http://localhost:8000
```

**If you see errors, see [Troubleshooting](#validation-and-troubleshooting) section.**

### 6.4 Test Natural Language Queries

#### Using Web Chat Interface

1. Open browser: `http://localhost:8000`
2. Select adapter: `intent-sql-sqlite-contact`
3. Type natural language queries

#### Using API

**Basic user search:**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me all users",
    "adapter": "intent-sql-sqlite-contact"
  }'
```

**Search by city:**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Find users from New York",
    "adapter": "intent-sql-sqlite-contact"
  }'
```

**Count queries:**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How many users do we have?",
    "adapter": "intent-sql-sqlite-contact"
  }'
```

**Age filters:**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me users over 30 years old",
    "adapter": "intent-sql-sqlite-contact"
  }'
```

**Recent users:**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "List users created in the last month",
    "adapter": "intent-sql-sqlite-contact"
  }'
```

### 6.5 Understanding Results

**Successful response:**

```json
{
  "response": "Found 45 users:\n\n1. John Smith (jsmith@example.com) - New York, Age 34\n2. Sarah Johnson (sarahj@example.com) - New York, Age 28\n...",
  "metadata": {
    "adapter": "intent-sql-sqlite-contact",
    "matched_template": "users_by_city",
    "confidence": 0.87,
    "sql_executed": "SELECT id, name, email, age, city FROM users WHERE city = ? ORDER BY name",
    "parameters": {"city": "New York"},
    "execution_time_ms": 23
  }
}
```

**Low confidence warning:**

```json
{
  "response": "I'm not confident I understood your query correctly. Did you mean to ask about users?",
  "metadata": {
    "confidence": 0.32,
    "threshold": 0.40,
    "suggestion": "Try rephrasing or adding more details"
  }
}
```

### 6.6 Example Test Queries

Try these queries to test different capabilities:

**Basic Listing:**
- "Show me all users"
- "List all contacts"
- "Display everyone in the database"

**Filtering by City:**
- "Find users from Chicago"
- "Who lives in Los Angeles?"
- "Show me all people in New York"

**Filtering by Age:**
- "Find users over 40"
- "Show me young users under 25"
- "List people between 30 and 50 years old"

**Email Searches:**
- "Find user with email john@example.com"
- "Who has the email address sarah@example.com?"

**Counting:**
- "How many users do we have?"
- "Count all contacts"
- "Total number of users"

**Time-based:**
- "Show me recent users"
- "Who was created this week?"
- "List users from last month"

**Combinations:**
- "Find young users from New York"
- "Show me recent contacts over 30"
- "Count users in Chicago"

---

## Validation and Troubleshooting

### Pre-Deployment Validation

Before deploying templates, validate them:

#### 1. Structure Validation

```bash
cd utils/sql-intent-template

python validate_output.py \
  contact-domain.yaml \
  contact-templates.yaml
```

**Expected output:**

```
✅ Domain configuration is valid
✅ Template library is valid
✅ All required fields present
✅ Parameter definitions correct
✅ Semantic types configured properly
```

#### 2. Compare with Reference

```bash
python compare_structures.py \
  contact-domain.yaml \
  contact-templates.yaml \
  ../../config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml \
  ../../config/sql_intent_templates/examples/customer-orders/postgres_customer_orders.yaml
```

#### 3. Test Adapter Loading

```bash
cd ../..  # Back to orbit root

python utils/sql-intent-template/test_adapter_loading.py \
  config/sql_intent_templates/examples/contact/contact-domain.yaml \
  config/sql_intent_templates/examples/contact/contact-templates.yaml
```

**Expected output:**

```
✅ IntentAdapter imported successfully
✅ Domain config loaded: Contact Management
✅ Template library loaded: 8 templates
✅ Entities accessible: users
✅ Fields accessible: 6 fields
✅ Templates retrievable by ID
✅ All validation tests passed!
```

### Common Issues and Solutions

#### Issue 1: Templates Not Loading

**Symptoms:**
```
ERROR: Failed to load templates from contact-templates.yaml
```

**Solutions:**

1. **Check file paths:**
   ```bash
   ls -la config/sql_intent_templates/examples/contact/
   ```

2. **Validate YAML syntax:**
   ```bash
   python -c "import yaml; yaml.safe_load(open('config/sql_intent_templates/examples/contact/contact-templates.yaml'))"
   ```

3. **Force reload templates:**
   ```yaml
   # In config/adapters.yaml
   reload_templates_on_start: true
   force_reload_templates: true
   ```

4. **Clear vector store cache:**
   ```bash
   rm -rf chroma_storage/contact_intent_templates/
   ```

#### Issue 2: Low Confidence Scores

**Symptoms:**
```
Query returned confidence 0.25 (below threshold 0.40)
```

**Solutions:**

1. **Lower confidence threshold temporarily:**
   ```yaml
   confidence_threshold: 0.3  # Was 0.4
   ```

2. **Add more example queries** to templates:
   ```yaml
   examples:
     - "Show me all users"
     - "List all users"  # Add more variations
     - "Display all users"
     - "Get all users"
   ```

3. **Add more test queries** and regenerate templates

4. **Check if query matches any template:**
   - Look at template semantic_tags
   - Ensure vocabulary includes relevant synonyms

#### Issue 3: Wrong SQL Dialect

**Symptoms:**
```
SQL syntax error: unrecognized token "?"
```

**Solutions:**

1. **Check database type matches adapter:**
   - SQLite adapter → SQLite placeholders (`?`)
   - PostgreSQL adapter → PostgreSQL placeholders (`%(name)s`)

2. **Verify dialect in domain config:**
   ```yaml
   # In configs/contact-config.yaml
   dialect: sqlite  # or postgres, mysql, etc.
   ```

3. **Regenerate templates with correct dialect:**
   ```bash
   ./generate_templates.sh \
     --schema examples/contact.sql \
     --queries examples/contact_test_queries.md \
     --domain configs/postgres-config.yaml  # Use correct config
     --output contact-templates.yaml
   ```

#### Issue 4: Database Connection Failed

**Symptoms:**
```
ERROR: Unable to connect to database: contact.db
```

**Solutions:**

1. **Check database path in datasources.yaml:**
   ```yaml
   sqlite:
     path: "utils/sql-intent-template/examples/sqlite/contact.db"
   ```

2. **Verify database exists:**
   ```bash
   ls -la utils/sql-intent-template/examples/sqlite/contact.db
   ```

3. **Check file permissions:**
   ```bash
   chmod 644 utils/sql-intent-template/examples/sqlite/contact.db
   ```

4. **Test database directly:**
   ```bash
   sqlite3 utils/sql-intent-template/examples/sqlite/contact.db "SELECT COUNT(*) FROM users;"
   ```

#### Issue 5: Missing API Keys

**Symptoms:**
```
ERROR: OPENAI_API_KEY not found in environment
```

**Solutions:**

1. **Check .env file exists:**
   ```bash
   ls -la .env
   ```

2. **Verify API key is set:**
   ```bash
   grep OPENAI_API_KEY .env
   ```

3. **Restart server** after adding keys

4. **Export manually for testing:**
   ```bash
   export OPENAI_API_KEY=sk-your-key-here
   python -m server.app
   ```

#### Issue 6: Import Errors

**Symptoms:**
```
ModuleNotFoundError: No module named 'yaml'
```

**Solutions:**

1. **Install missing packages:**
   ```bash
   pip install pyyaml anthropic openai faker
   ```

2. **Verify virtual environment:**
   ```bash
   which python  # Should point to venv
   pip list | grep yaml
   ```

3. **Reinstall requirements:**
   ```bash
   pip install -r requirements.txt
   ```

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
# Set environment variable
export ORBIT_DEBUG=true

# Or in config.yaml
debug: true
log_level: DEBUG
```

This provides detailed logs:
- Template matching process
- SQL query construction
- Parameter extraction
- Confidence score calculation

---

## Next Steps

### Expand Your Templates

Now that you have a working system, enhance it:

#### 1. Add More Queries

The more training queries, the better:

```bash
# Open your queries file
vim examples/contact_test_queries.md

# Add 50-100 more varied queries
# Then regenerate templates
./generate_templates.sh \
  --schema examples/contact.sql \
  --queries examples/contact_test_queries.md \
  --output contact-templates.yaml \
  --domain configs/contact-config.yaml
```

#### 2. Create Additional Templates

Add specialized templates manually:

```yaml
# In contact-templates.yaml
- id: "users_by_email_domain"
  description: "Find users by email domain"
  sql_template: |
    SELECT id, name, email, city
    FROM users
    WHERE email LIKE '%' || ? || '%'
    ORDER BY name
  parameters:
    - name: domain
      type: string
      required: true
  examples:
    - "Find all gmail users"
    - "Show me everyone with yahoo email"
    - "List users with company email"
  semantic_tags:
    - users
    - email_search
    - domain_filter
```

#### 3. Add Business Intelligence Templates

Create analytical queries:

```yaml
- id: "user_distribution_by_city"
  description: "Analyze user distribution across cities"
  sql_template: |
    SELECT
      city,
      COUNT(*) as user_count,
      AVG(age) as avg_age,
      MIN(created_at) as first_user,
      MAX(created_at) as latest_user
    FROM users
    GROUP BY city
    ORDER BY user_count DESC
    LIMIT ?
  parameters:
    - name: limit
      type: integer
      default_value: 10
  examples:
    - "Show me user distribution by city"
    - "Which cities have the most users?"
    - "Analyze users by location"
  semantic_tags:
    - analytics
    - distribution
    - city_analysis
```

### Apply to Your Own Database

Ready to use your own database?

#### 1. Export Your Schema

**For PostgreSQL:**
```bash
pg_dump -s -d your_database > my_schema.sql
```

**For MySQL:**
```bash
mysqldump --no-data your_database > my_schema.sql
```

**For SQLite:**
```bash
sqlite3 your_database.db .schema > my_schema.sql
```

#### 2. Create Domain-Specific Configuration

Copy and modify a config template:

```bash
cp configs/contact-config.yaml configs/my-database-config.yaml

# Edit dialect and settings
vim configs/my-database-config.yaml
```

#### 3. Write Domain-Specific Queries

Create queries based on YOUR use cases:

```bash
# Generate template
python create_query_template.py \
  --schema my_schema.sql \
  --output my_queries.md \
  --domain "My Business Domain"

# Fill in actual queries
vim my_queries.md
```

#### 4. Generate Templates

```bash
./generate_templates.sh \
  --schema my_schema.sql \
  --queries my_queries.md \
  --domain configs/my-database-config.yaml \
  --output my-templates.yaml \
  --generate-domain \
  --domain-name "My Business Domain" \
  --domain-output my-domain.yaml
```

### Advanced Features

#### Multi-Table Relationships

Add relationship definitions to domain config:

```yaml
relationships:
  - name: "user_orders"
    type: "one_to_many"
    from_entity: "users"
    to_entity: "orders"
    join_condition: "users.id = orders.user_id"

  - name: "order_items"
    type: "one_to_many"
    from_entity: "orders"
    to_entity: "order_items"
    join_condition: "orders.id = order_items.order_id"
```

#### Custom Semantic Types

Define domain-specific semantic types:

```yaml
semantic_types:
  customer_status:
    description: "Customer account status"
    patterns: [active, inactive, suspended, premium]

  product_category:
    description: "Product category classification"
    patterns: [electronics, clothing, books, food]

  order_priority:
    description: "Order priority level"
    patterns: [urgent, high, normal, low]
```

#### Template Variations

Create template variations for different result formats:

```yaml
# Detailed view
- id: "users_detailed"
  sql_template: "SELECT * FROM users WHERE city = ?"

# Summary view
- id: "users_summary"
  sql_template: "SELECT name, email FROM users WHERE city = ?"

# Count only
- id: "users_count"
  sql_template: "SELECT COUNT(*) FROM users WHERE city = ?"
```

### Performance Optimization

#### 1. Index Your Database

Add indexes for common filters:

```sql
CREATE INDEX idx_users_city ON users(city);
CREATE INDEX idx_users_created_at ON users(created_at);
CREATE INDEX idx_users_email ON users(email);
```

#### 2. Optimize Template Collection

```yaml
# In adapter config
max_templates: 3  # Reduce for faster matching
confidence_threshold: 0.5  # Increase for more precise matches
```

#### 3. Use Connection Pooling

For production PostgreSQL/MySQL:

```yaml
config:
  use_connection_pool: true
  pool_size: 10
  connection_timeout: 30
```

#### 4. Cache Results

```yaml
config:
  cache_ttl: 1800  # Cache results for 30 minutes
```

### Monitoring and Analytics

Track template usage and performance:

```yaml
config:
  enable_query_monitoring: true
  query_timeout: 5000
```

Check logs for:
- Most frequently matched templates
- Low confidence queries
- Slow-performing SQL queries
- Failed parameter extractions

### Share Your Templates

Contribute back to the community:

1. **Document your domain** in the template file
2. **Include diverse examples** (50+ queries minimum)
3. **Test thoroughly** with various phrasings
4. **Submit examples** to the Orbit repository

---

## Summary Checklist

Before going to production, verify:

- [ ] Schema file is complete and accurate
- [ ] 50+ diverse test queries written
- [ ] Templates generated successfully
- [ ] Domain configuration validated
- [ ] Templates validated against schema
- [ ] Sample data generated and verified
- [ ] Database connection configured
- [ ] Adapter enabled in config
- [ ] Orbit server starts without errors
- [ ] Templates load successfully
- [ ] Test queries return expected results
- [ ] Confidence scores are reasonable (>0.4)
- [ ] Performance is acceptable
- [ ] Error handling works correctly
- [ ] Documentation is complete

---

## Additional Resources

### Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Complete feature documentation |
| `TUTORIAL.md` | This guide |
| `VALIDATION_TOOLS.md` | Validation workflow guide |
| `VALIDATION_REPORT.md` | Compatibility test results |
| `SQL_DIALECT_GUIDE.md` | SQL dialect reference |
| `SCRIPTS_DOCUMENTATION.md` | Script documentation index |

### Example Files

| File | Purpose |
|------|---------|
| `examples/contact.sql` | Simple single-table schema |
| `examples/contact_test_queries.md` | 150 example queries |
| `examples/sqlite/contact.db` | Generated sample database |
| `examples/prompts/contact-assistant-prompt.txt` | System prompt for contact assistant |
| `configs/contact-config.yaml` | SQLite configuration |

### Script Reference

| Script | Purpose |
|--------|---------|
| `generate_templates.sh` | Main template generator |
| `run_contact_example.sh` | Quick start example |
| `create_query_template.py` | Query file generator |
| `validate_output.py` | Structure validator |
| `compare_structures.py` | Reference comparison |
| `test_adapter_loading.py` | Adapter loading test |
| `examples/sqlite/generate_contact_data.py` | Sample data generator |

### Help Commands

```bash
# Script help
./generate_templates.sh --help
python create_query_template.py --help
python validate_output.py
python generate_contact_data.py --help

# View documentation
head -187 generate_templates.sh
head -101 run_contact_example.sh
python -c "import validate_output; print(validate_output.__doc__)"
```

---

## Getting Help

### Check Logs

```bash
# Server logs
tail -f logs/orbit.log

# Template loading logs
grep "Intent adapter" logs/orbit.log

# Query matching logs
grep "confidence" logs/orbit.log
```

### Community Support

- **Issues:** https://github.com/anthropics/orbit/issues
- **Discussions:** https://github.com/anthropics/orbit/discussions
- **Documentation:** See `docs/` directory

### Debug Tips

1. **Start simple** - Use contact example first
2. **Validate early** - Run validation scripts before deploying
3. **Test incrementally** - Test one feature at a time
4. **Check examples** - Compare with working examples
5. **Read logs** - Error messages are descriptive
6. **Adjust confidence** - Lower threshold while testing
7. **Force reload** - Clear cache when updating templates

---

**Congratulations!** You now have a fully functional natural language SQL query system. Users can ask questions in plain English and get accurate results from your database.

**Happy querying!** 🎉
