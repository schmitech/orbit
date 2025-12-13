# HR Management System

This directory contains a complete HR management system schema and templates, transformed from the simple contact database example.

## Overview

The HR system replaces the single flat `users` table with a proper relational database structure including:
- **Employees** - Employee information (name, email, hire date, status, etc.)
- **Departments** - Organizational units (Engineering, Sales, Marketing, etc.)
- **Positions** - Job titles/roles with salary ranges
- **Employee-Department Assignments** - Many-to-many relationship with history
- **Employee-Position Assignments** - Many-to-many relationship with salary and history

## Files

### Schema Files
- `hr_schema.sql` - Complete database schema with tables, relationships, indexes, and sample data
- `contact.sql` - Original simple contact schema (kept for reference)

### Configuration Files
- `hr-domain.yaml` - Domain configuration for HR system (entities, fields, relationships, semantic types)
- `contact-domain.yaml` - Original contact domain config (kept for reference)

### Template Files
- `hr-templates.yaml` - Comprehensive HR query templates (80+ templates)
- `hr_seed_templates.yaml` - Seed templates as reference/starting point
- `contact-templates.yaml` - Original contact templates (kept for reference)
- `contact_seed_templates.yaml` - Original seed templates (kept for reference)

### Data Generation
- `generate_hr_data.py` - Python script to generate realistic HR test data
- `generate_contact_data.py` - Original contact data generator (kept for reference)

### Test Queries
- `hr_test_queries.md` - 300+ natural language test queries for HR system
- `contact_test_queries.md` - Original contact test queries (kept for reference)

## Database Schema

### Tables

#### `departments`
- `id` (PRIMARY KEY)
- `name` (UNIQUE)
- `location`
- `budget`
- `manager_id` (FOREIGN KEY to employees)
- `created_at`

#### `positions`
- `id` (PRIMARY KEY)
- `title`
- `department_id` (FOREIGN KEY to departments)
- `min_salary`
- `max_salary`
- `description`
- `created_at`

#### `employees`
- `id` (PRIMARY KEY)
- `first_name`
- `last_name`
- `email` (UNIQUE)
- `phone`
- `birth_date`
- `hire_date`
- `termination_date`
- `status` (active, terminated, on_leave)
- `created_at`
- `updated_at`

#### `employee_departments`
- `id` (PRIMARY KEY)
- `employee_id` (FOREIGN KEY to employees)
- `department_id` (FOREIGN KEY to departments)
- `start_date`
- `end_date` (NULL = current assignment)
- `is_primary` (BOOLEAN)
- `created_at`

#### `employee_positions`
- `id` (PRIMARY KEY)
- `employee_id` (FOREIGN KEY to employees)
- `position_id` (FOREIGN KEY to positions)
- `start_date`
- `end_date` (NULL = current position)
- `salary`
- `is_primary` (BOOLEAN)
- `created_at`

### Relationships

- **Employees ↔ Departments**: Many-to-many (through `employee_departments`)
- **Employees ↔ Positions**: Many-to-many (through `employee_positions`)
- **Positions → Departments**: Many-to-one
- **Departments → Employees**: One-to-one (manager relationship)

## Quick Start

### 1. Create the Database

```bash
# Using the schema file
sqlite3 hr.db < hr_schema.sql

# Or generate with sample data
python generate_hr_data.py --employees 100 --output hr.db
```

### 2. Generate Test Data

```bash
# Generate 50 employees (default)
python generate_hr_data.py

# Generate 200 employees
python generate_hr_data.py --employees 200

# Clean existing data and generate fresh
python generate_hr_data.py --employees 100 --clean
```

### 3. Test Queries

```bash
# Using sqlite3
sqlite3 hr.db "SELECT * FROM employees LIMIT 5;"

# Example complex query
sqlite3 hr.db "
SELECT e.first_name, e.last_name, d.name as dept, p.title, ep.salary
FROM employees e
JOIN employee_departments ed ON e.id = ed.employee_id AND ed.end_date IS NULL
JOIN departments d ON ed.department_id = d.id
JOIN employee_positions ep ON e.id = ep.employee_id AND ep.end_date IS NULL
JOIN positions p ON ep.position_id = p.id
WHERE e.status = 'active'
LIMIT 10;
"
```

### 4. Generate SQL Templates

```bash
cd ../..
./generate_templates.sh \
  --schema examples/sqlite/contact/hr_schema.sql \
  --queries examples/sqlite/contact/hr_test_queries.md \
  --domain examples/sqlite/contact/hr-domain.yaml \
  --output hr-templates.yaml
```

## Template Categories

The HR templates cover:

1. **Basic Employee Queries**
   - List all employees
   - Search by name
   - Filter by status
   - Find by email

2. **Department Queries**
   - List departments
   - Find by name/location
   - Employees by department
   - Count by department

3. **Position Queries**
   - List positions
   - Filter by department
   - Salary range queries
   - Employees by position

4. **Relationship Queries**
   - Employees with departments
   - Employees with positions and salaries
   - Department rosters
   - Full employee profiles

5. **Aggregation Queries**
   - Count employees
   - Average salary
   - Average salary by department
   - Salary statistics

6. **Temporal Queries**
   - Recent hires
   - Employees by hire year
   - Tenure-based queries

7. **Complex Queries**
   - Multi-table joins
   - Multi-criteria filters
   - Full employee profiles
   - Department rosters

## Example Queries

### Natural Language → SQL

**Query**: "Show me employees in Engineering"
```sql
SELECT e.id, e.first_name, e.last_name, e.email, d.name as department_name, ed.start_date
FROM employees e
INNER JOIN employee_departments ed ON e.id = ed.employee_id
INNER JOIN departments d ON ed.department_id = d.id
WHERE d.name = 'Engineering' AND ed.end_date IS NULL
ORDER BY e.last_name, e.first_name
```

**Query**: "What's the average salary by department?"
```sql
SELECT d.name as department_name, AVG(ep.salary) as average_salary, COUNT(DISTINCT e.id) as employee_count
FROM departments d
INNER JOIN employee_departments ed ON d.id = ed.department_id AND ed.end_date IS NULL
INNER JOIN employees e ON ed.employee_id = e.id AND e.status = 'active'
INNER JOIN employee_positions ep ON e.id = ep.employee_id AND ep.end_date IS NULL
GROUP BY d.id, d.name
ORDER BY average_salary DESC
```

**Query**: "Show me Engineering department roster"
```sql
SELECT e.id, e.first_name, e.last_name, e.email, p.title as position_title, ep.salary, e.hire_date
FROM departments d
INNER JOIN employee_departments ed ON d.id = ed.department_id AND ed.end_date IS NULL
INNER JOIN employees e ON ed.employee_id = e.id AND e.status = 'active'
LEFT JOIN employee_positions ep ON e.id = ep.employee_id AND ep.end_date IS NULL AND ep.is_primary = 1
LEFT JOIN positions p ON ep.position_id = p.id
WHERE d.name = 'Engineering'
ORDER BY p.title, e.last_name, e.first_name
```

## Differences from Contact System

| Feature | Contact System | HR System |
|---------|---------------|-----------|
| **Tables** | 1 (users) | 5 (employees, departments, positions, employee_departments, employee_positions) |
| **Relationships** | None | Multiple (many-to-many, one-to-many) |
| **Complexity** | Simple flat structure | Relational with joins |
| **Use Cases** | Basic contact management | Full HR management |
| **Queries** | Simple filters | Complex multi-table queries |
| **Templates** | ~50 templates | 80+ templates |

## Requirements

- Python 3.6+
- Faker library: `pip install faker`
- SQLite3 (included with Python)

## Notes

- The original contact files are kept for reference
- All HR files use the `hr_` prefix to distinguish from contact files
- The schema supports historical tracking (end_date fields)
- Primary assignments are tracked via `is_primary` flags
- Foreign key constraints are enabled for data integrity

## Next Steps

1. Generate test data using `generate_hr_data.py`
2. Review and customize templates in `hr-templates.yaml`
3. Test queries using `hr_test_queries.md`
4. Integrate with SQL Intent Template Generator
5. Configure Intent adapter in Orbit server
