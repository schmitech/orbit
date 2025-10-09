# SQL Intent Template Generator Examples

This directory contains example SQL schemas and test queries for use with the SQL intent template generator. These examples demonstrate different domain patterns and help you get started with template generation.

## 🆕 Template Enrichment Resources

**NEW:** Enhanced resources for generating diverse, high-quality templates!

### Quick Links
- 📖 **[ENRICHMENT_GUIDE.md](ENRICHMENT_GUIDE.md)** - How to generate 20-25 specific templates instead of 2 generic ones
- 📊 **[BEFORE_AFTER_COMPARISON.md](BEFORE_AFTER_COMPARISON.md)** - Visual comparison showing 12x improvement
- ⚡ **[regenerate_contact_templates.sh](regenerate_contact_templates.sh)** - One-command template regeneration
- 🌱 **[contact_seed_templates.yaml](contact_seed_templates.yaml)** - 24 production-ready templates
- 📝 **[contact_test_queries_enriched.md](contact_test_queries_enriched.md)** - Categorized queries for better generation

### Quick Start: Get Better Templates Now!

```bash
# Option 1: Use 24 production-ready templates immediately (RECOMMENDED)
./regenerate_contact_templates.sh --use-seed

# Option 2: Auto-generate 20-25 diverse templates
./regenerate_contact_templates.sh --auto-only

# Option 3: Hybrid approach for best quality
./regenerate_contact_templates.sh --hybrid
```

**Result:** Go from 2 generic templates to 24 specific templates covering all major query patterns!

## Available Examples

### 1. Library Management System

A comprehensive library management system with books, authors, members, loans, and reviews.

**Files:**
- `library_management.sql` - Complete SQLite database schema with sample data
- `library_test_queries.md` - 195 test queries covering various search scenarios

**Schema Features:**
- 8 main tables (authors, categories, publishers, books, members, loans, reservations, reviews)
- 1 junction table (book_authors)
- 3 useful views for common queries
- Realistic sample data including classic books and authors
- Proper indexing and constraints
- SQLite-specific features like triggers for timestamps

**Test Queries Cover:**
- Book searches (by title, author, category, ISBN, etc.)
- Member searches (by name, email, membership type)
- Loan management (active, overdue, returned loans)
- Reservations and reviews
- Complex multi-criteria searches
- Statistical and administrative queries

**Usage:**
```bash
cd /path/to/orbit/utils/sql-intent-template
./generate_templates.sh \
    --schema examples/library_management.sql \
    --queries examples/library_test_queries.md \
    --config configs/library-config.yaml \
    --verbose
```

### 2. Customer-Order System

A simple e-commerce system with customers and orders for testing basic business queries.

**Files:**
- `customer-order.sql` - Simple customer-order database schema
- `customer-order_test_queries.md` - 200 test queries covering various business scenarios

**Schema Features:**
- Simple customer-order relationship
- Standard business entities (customers, orders)
- Common fields: email, phone, address, dates, amounts
- PostgreSQL-specific features (triggers, functions)
- Proper indexing and constraints

**Test Queries Cover:**
- Customer searches (by name, email, phone, location)
- Order searches (by customer, date, status, amount)
- Payment method queries
- Geographic analysis
- Customer analytics and behavior
- Order management and tracking
- Revenue and sales analysis

**Usage:**
```bash
cd /path/to/orbit/utils/sql-intent-template
./generate_templates.sh \
    --schema examples/customer-order.sql \
    --queries examples/customer-order_test_queries.md \
    --config configs/ecommerce-config.yaml \
    --verbose
```

### 3. Contact System

An ultra-simple schema with just one table for basic testing and validation of the template generator.

**Files:**
- `contact.sql` - Simple single-table schema with users (id, name, email, age, city)
- `contact_test_queries.md` - 150 basic test queries for quick testing

**Schema Features:**
- Single table with 5 basic columns
- Simple data types (INTEGER, TEXT, DATETIME)
- No foreign keys or complex relationships
- Perfect for "hello world" testing

**Test Queries Cover:**
- Basic user searches (by name, email, age, city)
- Simple filtering and sorting
- Count and statistics queries
- Basic existence checks
- Simple update operations

**Usage:**
```bash
cd /path/to/orbit/utils/sql-intent-template
./generate_templates.sh \
    --schema examples/contact.sql \
    --queries examples/contact_test_queries.md \
    --config configs/contact-config.yaml \
    --verbose
```

### 4. Classified Data Management System

A security-focused system for managing classified information with clearances, compartments, and audit logging.

**Files:**
- `classified-data.sql` - Complete database schema for classified data management
- `classified-data_test_queries.md` - 224 test queries covering various security scenarios

**Schema Features:**
- Security-focused with classification levels
- Complex access control and audit logging
- Specialized fields: clearance levels, compartments, PII flags
- Many-to-many relationships (users-compartments, items-compartments)
- Audit trail and compliance features

**Test Queries Cover:**
- Knowledge item searches (by classification, title, organization, compartment)
- User management (by clearance, citizenship, compartments)
- Access audit queries (by decision, user, time period)
- Organization and compartment queries
- Complex multi-criteria searches
- Security analysis and compliance queries
- Audit and reporting queries

**Usage:**
```bash
cd /path/to/orbit/utils/sql-intent-template
./generate_templates.sh \
    --schema examples/classified-data.sql \
    --queries examples/classified-data_test_queries.md \
    --config configs/classified-data-config.yaml \
    --verbose
```

## Quick Start with Examples

### 1. Test with Contact System (Recommended for Beginners)

```bash
# Start with the simplest possible example
./generate_templates.sh \
    --schema examples/contact.sql \
    --queries examples/contact_test_queries.md \
    --config configs/contact-config.yaml \
    --verbose

# Or use the quick script
./quick_generate.sh examples/contact.sql examples/contact_test_queries.md contact
```

### 2. Test with Library Management System

```bash
# Navigate to the template generator directory
cd /path/to/orbit/utils/sql-intent-template

# Generate templates using auto-configuration
./generate_templates.sh \
    --schema examples/library_management.sql \
    --queries examples/library_test_queries.md \
    --auto-config \
    --verbose

# Or use the quick script
./quick_generate.sh examples/library_management.sql examples/library_test_queries.md library
```

### 2. Test with Customer-Order System

```bash
# Generate templates with e-commerce configuration
./generate_templates.sh \
    --schema examples/customer-order.sql \
    --queries examples/customer-order_test_queries.md \
    --config configs/ecommerce-config.yaml \
    --verbose

# Or use the quick script
./quick_generate.sh examples/customer-order.sql examples/customer-order_test_queries.md ecommerce
```

### 3. Test with Classified Data System

```bash
# Generate templates with security-focused configuration
./generate_templates.sh \
    --schema examples/classified-data.sql \
    --queries examples/classified-data_test_queries.md \
    --config configs/classified-data-config.yaml \
    --verbose

# Or use the quick script
./quick_generate.sh examples/classified-data.sql examples/classified-data_test_queries.md classified
```

### 4. Test with Limited Queries

```bash
# Test with just 10 queries first
./generate_templates.sh \
    --schema examples/library_management.sql \
    --queries examples/library_test_queries.md \
    --limit 10 \
    --auto-config
```

## Example Schema Details

### Library Management System

The library management system includes the following tables:

#### Core Tables
- **authors** - Author information (name, biography, nationality, etc.)
- **categories** - Book categories (fiction, non-fiction, science fiction, etc.)
- **publishers** - Publisher information (name, address, contact details)
- **books** - Book information (title, ISBN, description, availability, etc.)
- **members** - Library member information (name, contact, membership type)
- **loans** - Book loan records (who borrowed what and when)
- **reservations** - Book reservation system
- **reviews** - Member book reviews and ratings

#### Junction Tables
- **book_authors** - Many-to-many relationship between books and authors

#### Views
- **book_summary** - Comprehensive book information with authors and categories
- **member_summary** - Member information with loan statistics
- **loan_summary** - Loan information with book and member details

#### Sample Data
The schema includes realistic sample data:
- 8 books from classic literature and science
- 5 authors including George Orwell, J.K. Rowling, Isaac Asimov, etc.
- 5 publishers including major publishing houses
- 10 categories covering different genres
- 5 library members with different membership types
- Sample loans, reservations, and reviews

#### SQLite-Specific Features
- Uses `PRAGMA foreign_keys = ON` for referential integrity
- Includes `AUTOINCREMENT` for primary keys
- Uses `INTEGER` for boolean fields with CHECK constraints
- Includes triggers for `updated_at` timestamps

### Classified Data Management System

The classified data system includes:

#### Core Tables
- **knowledge_item** - Classified documents and information
- **users** - User accounts with clearance levels
- **access_audit** - Audit trail of access attempts
- **compartments** - Classification compartments
- **organizations** - Originating organizations

#### Key Features
- Security clearance levels (UNCLASSIFIED to TOP SECRET)
- Compartment-based access control
- PII (Personally Identifiable Information) flags
- Audit logging and compliance
- Declassification and retention dates

## Test Query Categories

### Library Management Queries (195 total)

1. **Book Queries (1-50)**
   - Search by title, author, category, publisher
   - Search by ISBN, publication date, availability
   - Search by price range, language

2. **Member Queries (51-71)**
   - Search by name, email, membership type
   - Search by status, location

3. **Loan Queries (72-98)**
   - Search by status, member, book
   - Search by date range, due date, fine amount

4. **Reservation Queries (99-111)**
   - Search by status, member, book, priority

5. **Review Queries (112-126)**
   - Search by rating, book, member, verification status

6. **Author Queries (127-138)**
   - Search by name, nationality, birth date

7. **Publisher Queries (139-148)**
   - Search by name, location, founded year

8. **Category Queries (149-155)**
   - Search by name, parent category

9. **Complex Queries (156-195)**
   - Multi-criteria searches
   - Statistical queries
   - Administrative queries
   - Time-based analysis

## Customization

You can easily customize these examples for your needs:

1. **Add more tables** - Extend the schemas with additional entities
2. **Modify categories** - Add more specific categories or subcategories
3. **Extend data** - Add more member attributes, book details, etc.
4. **Add more queries** - Create additional test queries for your specific use cases
5. **Modify sample data** - Add more realistic data for your domain

## Integration with Orbit

These schemas are designed to work seamlessly with the Orbit SQL intent template generator. The generated templates can be used with:

- Intent PostgreSQL retriever
- SQL RAG system
- Conversational AI applications
- Domain-specific applications

The queries are designed to test various SQL patterns and intent recognition scenarios that are common in different business domains.

## Troubleshooting

### Common Issues

**File Not Found**
- Make sure you're running commands from the `utils/sql-intent-template` directory
- Use relative paths: `examples/library_management.sql`

**Permission Denied**
```bash
chmod +x generate_templates.sh quick_generate.sh
```

**Python Dependencies**
```bash
pip install pyyaml
```

### Debug Tips

1. Start with `--limit 10` to test with fewer queries
2. Use `--verbose` for detailed output
3. Check that your schema files are valid SQL
4. Ensure query files follow the expected format

## Next Steps

1. **Try the Examples**: Start with the library management system
2. **Experiment**: Modify the schemas and queries
3. **Create Your Own**: Use these as templates for your domain
4. **Share**: Contribute new examples back to the project

For more detailed information about configuration and advanced usage, see the main [README.md](../README.md).
