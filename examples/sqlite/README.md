# Library Management System - SQLite Example

This directory contains a complete example of a library management system database schema and test queries for use with the SQL intent template generator.

## Files

- `library_management.sql` - Complete SQLite database schema with sample data
- `library_test_queries.md` - 195 test queries covering various search scenarios
- `test_template_generation.sh` - Script to test template generation
- `README.md` - This documentation file

## Database Schema

The library management system includes the following tables:

### Core Tables
- **authors** - Author information (name, biography, nationality, etc.)
- **categories** - Book categories (fiction, non-fiction, science fiction, etc.)
- **publishers** - Publisher information (name, address, contact details)
- **books** - Book information (title, ISBN, description, availability, etc.)
- **members** - Library member information (name, contact, membership type)
- **loans** - Book loan records (who borrowed what and when)
- **reservations** - Book reservation system
- **reviews** - Member book reviews and ratings

### Junction Tables
- **book_authors** - Many-to-many relationship between books and authors

### Views
- **book_summary** - Comprehensive book information with authors and categories
- **member_summary** - Member information with loan statistics
- **loan_summary** - Loan information with book and member details

## Sample Data

The schema includes realistic sample data:
- 8 books from classic literature and science
- 5 authors including George Orwell, J.K. Rowling, Isaac Asimov, etc.
- 5 publishers including major publishing houses
- 10 categories covering different genres
- 5 library members with different membership types
- Sample loans, reservations, and reviews

## Test Queries

The `library_test_queries.md` file contains 195 test queries covering:

### Book Queries (1-50)
- Search by title, author, category, publisher
- Search by ISBN, publication date, availability
- Search by price range, language

### Member Queries (51-71)
- Search by name, email, membership type
- Search by status, location

### Loan Queries (72-98)
- Search by status, member, book
- Search by date range, due date, fine amount

### Reservation Queries (99-111)
- Search by status, member, book, priority

### Review Queries (112-126)
- Search by rating, book, member, verification status

### Author Queries (127-138)
- Search by name, nationality, birth date

### Publisher Queries (139-148)
- Search by name, location, founded year

### Category Queries (149-155)
- Search by name, parent category

### Complex Queries (156-195)
- Multi-criteria searches
- Statistical queries
- Administrative queries
- Time-based analysis

## Usage

### 1. Generate Templates

To generate SQL intent templates using this schema:

```bash
cd /path/to/orbit/utils/sql-intent-template
./generate_templates.sh \
    --schema ../../examples/sqlite/library_management.sql \
    --queries ../../examples/sqlite/library_test_queries.md \
    --auto-config \
    --verbose
```

### 2. Use the Test Script

Run the provided test script:

```bash
cd /path/to/orbit/examples/sqlite
./test_template_generation.sh
```

### 3. Manual Testing

You can also test individual components:

```bash
# Test with specific configuration
./generate_templates.sh \
    --schema library_management.sql \
    --queries library_test_queries.md \
    --config configs/ecommerce-config.yaml \
    --limit 10

# Test with specific provider
./generate_templates.sh \
    --schema library_management.sql \
    --queries library_test_queries.md \
    --provider ollama \
    --auto-config
```

## Schema Features

### SQLite-Specific Features
- Uses `PRAGMA foreign_keys = ON` for referential integrity
- Includes `AUTOINCREMENT` for primary keys
- Uses `INTEGER` for boolean fields with CHECK constraints
- Includes triggers for `updated_at` timestamps

### Data Integrity
- Foreign key constraints
- CHECK constraints for enums
- UNIQUE constraints where appropriate
- Proper indexing for performance

### Sample Data
- Realistic book titles and authors
- Varied publication dates (19th century to modern)
- Different membership types and statuses
- Sample loans with different statuses
- Reviews with ratings and text

## Customization

You can easily customize this schema for your needs:

1. **Add more tables** - Add tables for magazines, DVDs, e-books, etc.
2. **Modify categories** - Add more specific categories or subcategories
3. **Extend member data** - Add more member attributes like preferences, reading history
4. **Add more queries** - Create additional test queries for your specific use cases
5. **Modify sample data** - Add more realistic data for your domain

## Integration with Orbit

This schema is designed to work seamlessly with the Orbit SQL intent template generator. The generated templates can be used with:

- Intent PostgreSQL retriever
- SQL RAG system
- Conversational AI applications
- Library management systems

The queries are designed to test various SQL patterns and intent recognition scenarios that are common in library management systems.