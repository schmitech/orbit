# SQL Dialect Configuration Guide

## Overview

The template generator automatically adapts to different SQL databases. Simply specify your database type in the config file, and the tool handles all the dialect-specific details.

## Supported Databases

| Database | Config Value | Parameter Placeholder | Notes |
|----------|-------------|----------------------|-------|
| **SQLite** | `sqlite` | `?` | Default for simple/embedded databases |
| **PostgreSQL** | `postgres` | `%(name)s` | Enterprise features, RETURNING clause |
| **MySQL** | `mysql` | `%s` | Popular open-source database |
| **MariaDB** | `mariadb` | `%s` | MySQL fork with additional features |
| **Oracle** | `oracle` | `:param_name` | Enterprise database |
| **SQL Server** | `sqlserver` | `?` | Microsoft T-SQL |

## Configuration

Just add this to your config file (e.g., `configs/my-config.yaml`):

```yaml
sql_dialect:
  type: sqlite  # Change to: postgres, mysql, mariadb, oracle, sqlserver
```

**That's it!** The generator automatically handles:
- Correct parameter placeholder style
- Database-specific SQL syntax
- Pagination methods (LIMIT/OFFSET, ROWNUM, etc.)
- String concatenation operators
- Date formatting functions
- Boolean value representation
- Auto-increment column syntax

## Examples

### SQLite Example
```yaml
sql_dialect:
  type: sqlite
```
Generated SQL uses:
- `?` placeholders
- `LIMIT` and `OFFSET`
- `||` for string concat
- `strftime()` for dates
- `0/1` for booleans

### PostgreSQL Example
```yaml
sql_dialect:
  type: postgres
```
Generated SQL uses:
- `%(name)s` placeholders
- `LIMIT` and `OFFSET`
- `||` for string concat
- `TO_CHAR()` for dates
- `true/false` for booleans
- `RETURNING` clause support

### MySQL Example
```yaml
sql_dialect:
  type: mysql
```
Generated SQL uses:
- `%s` placeholders
- `LIMIT` and `OFFSET`
- `CONCAT()` for strings
- `DATE_FORMAT()` for dates
- `0/1` for booleans
- Backticks for identifiers

### Oracle Example
```yaml
sql_dialect:
  type: oracle
```
Generated SQL uses:
- `:param_name` placeholders
- `ROWNUM` or `ROW_NUMBER()` for pagination
- `||` for string concat
- `TO_CHAR()` for dates
- `SEQUENCE` for auto-increment

### SQL Server Example
```yaml
sql_dialect:
  type: sqlserver
```
Generated SQL uses:
- `?` placeholders
- `OFFSET`/`FETCH NEXT` for pagination
- `+` for string concat
- `FORMAT()` for dates
- `OUTPUT` clause instead of RETURNING

## Quick Start Examples

### For SQLite (embedded apps, testing)
```bash
./generate_templates.sh \
  --schema examples/contact.sql \
  --queries examples/contact_test_queries.md \
  --output contact-templates.yaml \
  --domain configs/contact-config.yaml  # Set type: sqlite
```

### For PostgreSQL (production web apps)
```bash
# Just change sql_dialect.type to 'postgres' in your config file
./generate_templates.sh \
  --schema examples/ecommerce.sql \
  --queries examples/ecommerce_queries.md \
  --output ecommerce-templates.yaml \
  --domain configs/ecommerce-config.yaml  # Set type: postgres
```

### For MySQL (legacy systems)
```bash
# Just change sql_dialect.type to 'mysql' in your config file
./generate_templates.sh \
  --schema examples/legacy.sql \
  --queries examples/legacy_queries.md \
  --output legacy-templates.yaml \
  --domain configs/legacy-config.yaml  # Set type: mysql
```

## Switching Databases

To switch from one database to another:

1. Open your config file (e.g., `configs/my-config.yaml`)
2. Change `sql_dialect.type` to your target database
3. Re-run the template generator
4. New templates will use the correct syntax automatically!

```yaml
# Before
sql_dialect:
  type: sqlite

# After
sql_dialect:
  type: postgres
```

No other changes needed!

## Default Behavior

If no `sql_dialect` is specified, the generator defaults to **PostgreSQL** syntax, as it's the most feature-complete open-source database.

## Best Practices

1. **Match your production database**: Set the dialect to match your actual database system
2. **Test templates**: Always test generated templates against your target database
3. **Review for edge cases**: Some database-specific features may require manual adjustment
4. **Keep it simple**: The generator handles common patterns well; complex queries may need customization

## Troubleshooting

**Q: My database isn't listed**
A: Use the closest equivalent (e.g., use `mysql` for Aurora MySQL, `postgres` for Aurora PostgreSQL)

**Q: Generated SQL doesn't work on my database**
A: Check your database version. Some features require specific versions (e.g., MySQL 8.0+ for CTEs)

**Q: Can I customize the dialect settings?**
A: The built-in settings cover most use cases. If you need custom settings, the dialect configurations are in `template_generator.py:100-221`

## Technical Details

All dialect configurations are maintained in `SQL_DIALECTS` dictionary in `template_generator.py`. Each dialect includes:

- Parameter style (qmark, named, format, pyformat)
- Feature support flags (CTEs, window functions, RETURNING, etc.)
- Database-specific functions
- Syntax preferences
- Generation instructions for AI

This ensures consistency and makes it easy to add new dialects in the future.
