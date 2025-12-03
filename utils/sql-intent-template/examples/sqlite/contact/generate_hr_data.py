#!/usr/bin/env python3
"""
HR Management System Sample Data Generator

DESCRIPTION:
    Generates realistic sample data for the HR management database schema using the
    Faker library. Creates a SQLite database with synthetic HR records including
    departments, positions, employees, and their relationships for testing the
    SQL Intent Template Generator.

    This script populates:
    - Departments table (Engineering, Sales, Marketing, HR, Finance, Operations)
    - Positions table (job titles with salary ranges)
    - Employees table (employee information with realistic turnover)
    - Employee-Department assignments (including cross-department and history)
    - Employee-Position assignments with salaries (including promotions)

    REALISTIC FEATURES:
    - Weighted department distribution (Engineering/Operations larger than HR)
    - Pyramid position structure (more junior roles than managers)
    - Tenure-based salary calculation (longer tenure = higher in range)
    - ~12% annual turnover rate with terminated employees
    - ~15% promotion rate for tenured employees
    - ~8% cross-department assignments
    - Canadian phone number format (XXX-XXX-XXXX)

USAGE:
    python generate_hr_data.py [--employees N] [--output FILE]

ARGUMENTS:
    --employees N    Number of employee records to generate (default: 50)
    --output FILE    Path to SQLite database file (default: hr.db)
    --clean          Drop existing tables before generating new data
    --turnover PCT   Annual turnover percentage (default: 12)
    --seed N         Random seed for reproducibility

EXAMPLES:
    # Generate 50 employees (default)
    python generate_hr_data.py

    # Generate 200 employees with reproducible results
    python generate_hr_data.py --employees 200 --seed 42

    # Generate to specific database file
    python generate_hr_data.py --output ./data/hr.db

    # Clean existing data and generate fresh with higher turnover
    python generate_hr_data.py --employees 100 --clean --turnover 20

OUTPUT:
    Creates a SQLite database with the following structure:
    - Database: hr.db (or specified path)
    - Tables: departments, positions, employees, employee_departments, employee_positions
    - Relationships: employees to departments, employees to positions

REQUIREMENTS:
    pip install faker

AUTHOR:
    SQL Intent Template Generator v1.0.0
"""

import sqlite3
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

try:
    from faker import Faker
except ImportError:
    print("❌ Error: Faker library is required")
    print("   Install with: pip install faker")
    sys.exit(1)


# Department definitions (Canadian cities) with realistic headcount weights
# Weight represents relative size - Engineering/Operations are typically larger
DEPARTMENTS = [
    {"name": "Engineering", "location": "Toronto", "budget": 5000000.00, "weight": 30},
    {"name": "Sales", "location": "Vancouver", "budget": 3000000.00, "weight": 20},
    {"name": "Marketing", "location": "Montreal", "budget": 2000000.00, "weight": 12},
    {"name": "Human Resources", "location": "Calgary", "budget": 1500000.00, "weight": 8},
    {"name": "Finance", "location": "Ottawa", "budget": 2500000.00, "weight": 10},
    {"name": "Operations", "location": "Edmonton", "budget": 4000000.00, "weight": 20},
]

# Position definitions with salary ranges and pyramid weights
# Level: 1=entry, 2=senior, 3=manager - weight determines distribution
POSITIONS = [
    # Engineering (pyramid: many engineers, few managers)
    {"title": "Software Engineer", "department": "Engineering", "min_salary": 80000, "max_salary": 150000, "level": 1, "weight": 50},
    {"title": "Senior Software Engineer", "department": "Engineering", "min_salary": 120000, "max_salary": 200000, "level": 2, "weight": 35},
    {"title": "Engineering Manager", "department": "Engineering", "min_salary": 150000, "max_salary": 250000, "level": 3, "weight": 10},
    {"title": "DevOps Engineer", "department": "Engineering", "min_salary": 90000, "max_salary": 160000, "level": 1, "weight": 25},
    # Sales
    {"title": "Sales Representative", "department": "Sales", "min_salary": 50000, "max_salary": 100000, "level": 1, "weight": 55},
    {"title": "Senior Sales Representative", "department": "Sales", "min_salary": 80000, "max_salary": 140000, "level": 2, "weight": 30},
    {"title": "Sales Manager", "department": "Sales", "min_salary": 100000, "max_salary": 180000, "level": 3, "weight": 15},
    # Marketing
    {"title": "Marketing Specialist", "department": "Marketing", "min_salary": 55000, "max_salary": 95000, "level": 1, "weight": 50},
    {"title": "Senior Marketing Specialist", "department": "Marketing", "min_salary": 75000, "max_salary": 120000, "level": 2, "weight": 35},
    {"title": "Marketing Manager", "department": "Marketing", "min_salary": 90000, "max_salary": 150000, "level": 3, "weight": 15},
    # HR
    {"title": "HR Coordinator", "department": "Human Resources", "min_salary": 45000, "max_salary": 75000, "level": 1, "weight": 45},
    {"title": "HR Specialist", "department": "Human Resources", "min_salary": 60000, "max_salary": 100000, "level": 2, "weight": 35},
    {"title": "HR Manager", "department": "Human Resources", "min_salary": 80000, "max_salary": 130000, "level": 3, "weight": 20},
    # Finance
    {"title": "Financial Analyst", "department": "Finance", "min_salary": 60000, "max_salary": 110000, "level": 1, "weight": 50},
    {"title": "Senior Financial Analyst", "department": "Finance", "min_salary": 85000, "max_salary": 140000, "level": 2, "weight": 35},
    {"title": "Finance Manager", "department": "Finance", "min_salary": 100000, "max_salary": 170000, "level": 3, "weight": 15},
    # Operations
    {"title": "Operations Coordinator", "department": "Operations", "min_salary": 50000, "max_salary": 90000, "level": 1, "weight": 50},
    {"title": "Operations Specialist", "department": "Operations", "min_salary": 70000, "max_salary": 120000, "level": 2, "weight": 35},
    {"title": "Operations Manager", "department": "Operations", "min_salary": 95000, "max_salary": 160000, "level": 3, "weight": 15},
]

# Promotion paths: from position -> to position
PROMOTION_PATHS = {
    "Software Engineer": "Senior Software Engineer",
    "Senior Software Engineer": "Engineering Manager",
    "DevOps Engineer": "Senior Software Engineer",
    "Sales Representative": "Senior Sales Representative",
    "Senior Sales Representative": "Sales Manager",
    "Marketing Specialist": "Senior Marketing Specialist",
    "Senior Marketing Specialist": "Marketing Manager",
    "HR Coordinator": "HR Specialist",
    "HR Specialist": "HR Manager",
    "Financial Analyst": "Senior Financial Analyst",
    "Senior Financial Analyst": "Finance Manager",
    "Operations Coordinator": "Operations Specialist",
    "Operations Specialist": "Operations Manager",
}


def weighted_choice(items: list, weight_key: str = "weight"):
    """Select an item based on weights"""
    weights = [item[weight_key] for item in items]
    return random.choices(items, weights=weights, k=1)[0]


def generate_canadian_phone() -> str:
    """Generate a realistic Canadian phone number (XXX-XXX-XXXX)"""
    # Canadian area codes
    area_codes = ['416', '647', '437', '905', '289',  # Toronto/GTA
                  '604', '778', '236',  # Vancouver
                  '514', '438', '450',  # Montreal
                  '403', '587', '825',  # Calgary
                  '613', '343',  # Ottawa
                  '780', '587']  # Edmonton
    area = random.choice(area_codes)
    exchange = random.randint(200, 999)
    subscriber = random.randint(1000, 9999)
    return f"{area}-{exchange}-{subscriber}"


def calculate_tenure_salary(pos: dict, hire_date: datetime, current_date: datetime,
                            allow_outliers: bool = True) -> int:
    """
    Calculate salary based on tenure within the position's range.
    Longer tenure = higher percentile in the salary range.

    Args:
        pos: Position dict with min_salary/max_salary
        hire_date: Employee hire date
        current_date: Current date for tenure calculation
        allow_outliers: If True, ~8% chance of salary outside the band

    Returns:
        Salary amount (may be outside min/max range if outlier)
    """
    min_sal = pos["min_salary"]
    max_sal = pos["max_salary"]
    salary_range = max_sal - min_sal

    # Calculate years of tenure
    tenure_days = (current_date - hire_date).days
    tenure_years = tenure_days / 365.0

    # Tenure factor: 0-5 years maps to 0-100% of range
    # With some randomness (+/- 15%)
    tenure_factor = min(tenure_years / 5.0, 1.0)  # Cap at 5 years
    noise = random.uniform(-0.15, 0.15)
    final_factor = max(0.0, min(1.0, tenure_factor + noise))

    # Calculate base salary
    salary = min_sal + (salary_range * final_factor)

    # ~8% chance of being an outlier (realistic: long-tenured above band, or underpaid)
    if allow_outliers and random.random() < 0.08:
        if tenure_years >= 4 and random.random() < 0.7:
            # Long-tenured employee above max (70% of outliers) - overdue for promotion
            overage_pct = random.uniform(0.02, 0.15)  # 2-15% above max
            salary = max_sal * (1 + overage_pct)
        else:
            # Underpaid employee below min (30% of outliers) - new hire or equity issue
            underage_pct = random.uniform(0.02, 0.10)  # 2-10% below min
            salary = min_sal * (1 - underage_pct)

    # Round to nearest 1000
    return round(salary / 1000) * 1000


def create_database(db_path: str, clean: bool = False):
    """Create database and schema"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")

    # Drop tables if clean mode
    if clean:
        cursor.execute("DROP TABLE IF EXISTS employee_positions")
        cursor.execute("DROP TABLE IF EXISTS employee_departments")
        cursor.execute("DROP TABLE IF EXISTS employees")
        cursor.execute("DROP TABLE IF EXISTS positions")
        cursor.execute("DROP TABLE IF EXISTS departments")
        print("🧹 Cleaned existing data")

    # Create departments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            location TEXT,
            budget DECIMAL(10, 2),
            manager_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (manager_id) REFERENCES employees(id)
        )
    """)

    # Create positions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            department_id INTEGER,
            min_salary DECIMAL(10, 2),
            max_salary DECIMAL(10, 2),
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        )
    """)

    # Create employees table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            birth_date DATE,
            hire_date DATE NOT NULL,
            termination_date DATE,
            status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create employee_departments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employee_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE,
            is_primary BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id),
            FOREIGN KEY (department_id) REFERENCES departments(id)
        )
    """)

    # Create employee_positions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employee_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            position_id INTEGER NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE,
            salary DECIMAL(10, 2),
            is_primary BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id),
            FOREIGN KEY (position_id) REFERENCES positions(id)
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_employees_email ON employees(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_employees_hire_date ON employees(hire_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_employee_departments_employee ON employee_departments(employee_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_employee_departments_department ON employee_departments(department_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_employee_positions_employee ON employee_positions(employee_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_employee_positions_position ON employee_positions(position_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_department ON positions(department_id)")

    conn.commit()
    return conn


def insert_departments(conn: sqlite3.Connection) -> dict:
    """Insert departments and return mapping of name to id"""
    cursor = conn.cursor()
    dept_map = {}

    for dept in DEPARTMENTS:
        cursor.execute("""
            INSERT OR IGNORE INTO departments (name, location, budget)
            VALUES (?, ?, ?)
        """, (dept["name"], dept["location"], dept["budget"]))
        dept_id = cursor.lastrowid
        if dept_id == 0:
            # Already exists, get the ID
            cursor.execute("SELECT id FROM departments WHERE name = ?", (dept["name"],))
            dept_id = cursor.fetchone()[0]
        dept_map[dept["name"]] = dept_id

    conn.commit()
    return dept_map


def insert_positions(conn: sqlite3.Connection, dept_map: dict) -> dict:
    """Insert positions and return mapping of title to id"""
    cursor = conn.cursor()
    pos_map = {}

    for pos in POSITIONS:
        dept_id = dept_map.get(pos["department"])
        if not dept_id:
            continue

        cursor.execute("""
            INSERT OR IGNORE INTO positions (title, department_id, min_salary, max_salary, description)
            VALUES (?, ?, ?, ?, ?)
        """, (
            pos["title"],
            dept_id,
            pos["min_salary"],
            pos["max_salary"],
            f"Position: {pos['title']}"
        ))
        pos_id = cursor.lastrowid
        if pos_id == 0:
            cursor.execute("SELECT id FROM positions WHERE title = ? AND department_id = ?", 
                          (pos["title"], dept_id))
            pos_id = cursor.fetchone()[0]
        pos_map[pos["title"]] = pos_id

    conn.commit()
    return pos_map


def generate_employees(count: int, turnover_pct: float = 12.0) -> list:
    """
    Generate fake employee records with realistic turnover.

    Args:
        count: Number of employees to generate
        turnover_pct: Annual turnover percentage (default 12%)

    Returns:
        List of employee dictionaries
    """
    fake = Faker('en_CA')  # Use Canadian locale
    employees = []
    current_date = datetime.now()

    # Generate records with varied hire dates (last 7 years for more history)
    start_date = current_date - timedelta(days=2555)  # 7 years

    for _ in range(count):
        # Generate realistic hire date
        days_offset = random.randint(0, 2555)
        hire_date = start_date + timedelta(days=days_offset)

        # Generate birth date (age 22-65)
        age = random.randint(22, 65)
        birth_date = current_date - timedelta(days=age * 365 + random.randint(0, 365))

        # Determine if employee is terminated based on turnover rate
        # Probability increases with tenure (longer-tenured have had more chances to leave)
        tenure_years = (current_date - hire_date).days / 365.0

        # Cumulative probability of leaving: 1 - (1 - annual_rate)^years
        annual_rate = turnover_pct / 100.0
        cumulative_turnover_prob = 1 - ((1 - annual_rate) ** tenure_years)

        is_terminated = random.random() < cumulative_turnover_prob

        if is_terminated:
            # Termination happened sometime between hire and now
            # Weighted toward more recent (people who left long ago wouldn't be in recent data)
            days_employed = random.randint(90, int((current_date - hire_date).days))
            termination_date = hire_date + timedelta(days=days_employed)
            status = 'terminated'
        else:
            termination_date = None
            status = 'active'

        # Small chance of being on leave (2% of active employees)
        if status == 'active' and random.random() < 0.02:
            status = 'on_leave'

        employee = {
            'first_name': fake.first_name(),
            'last_name': fake.last_name(),
            'email': fake.email(),
            'phone': generate_canadian_phone(),
            'birth_date': birth_date.strftime('%Y-%m-%d'),
            'hire_date': hire_date.strftime('%Y-%m-%d'),
            'termination_date': termination_date.strftime('%Y-%m-%d') if termination_date else None,
            'status': status
        }
        employees.append(employee)

    return employees


def insert_employees(conn: sqlite3.Connection, employees: list) -> tuple:
    """Insert employee records into database"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    employee_records = []  # Store full record for later processing

    for employee in employees:
        try:
            cursor.execute("""
                INSERT INTO employees (first_name, last_name, email, phone, birth_date, hire_date, termination_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                employee['first_name'],
                employee['last_name'],
                employee['email'],
                employee['phone'],
                employee['birth_date'],
                employee['hire_date'],
                employee['termination_date'],
                employee['status']
            ))
            emp_id = cursor.lastrowid
            employee_records.append({
                'id': emp_id,
                'hire_date': employee['hire_date'],
                'termination_date': employee['termination_date'],
                'status': employee['status']
            })
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
            continue

    conn.commit()
    return inserted, skipped, employee_records


def assign_employees_to_departments(conn: sqlite3.Connection, employee_records: list, dept_map: dict,
                                    cross_dept_rate: float = 0.08):
    """
    Assign employees to departments using weighted distribution.

    Args:
        conn: Database connection
        employee_records: List of employee record dicts with id, hire_date, etc.
        dept_map: Mapping of department name to ID
        cross_dept_rate: Percentage of employees with cross-department assignments (default 8%)
    """
    cursor = conn.cursor()
    current_date = datetime.now()

    # Track assignments for return
    assignments = {}

    for emp_rec in employee_records:
        emp_id = emp_rec['id']
        hire_date = emp_rec['hire_date']
        termination_date = emp_rec.get('termination_date')

        # Select primary department using weighted choice
        primary_dept = weighted_choice(DEPARTMENTS)
        dept_id = dept_map[primary_dept["name"]]

        # Determine end_date for terminated employees
        end_date = termination_date if termination_date else None

        cursor.execute("""
            INSERT INTO employee_departments (employee_id, department_id, start_date, end_date, is_primary)
            VALUES (?, ?, ?, ?, 1)
        """, (emp_id, dept_id, hire_date, end_date))

        assignments[emp_id] = {
            'primary_dept': primary_dept["name"],
            'hire_date': hire_date,
            'termination_date': termination_date
        }

        # Cross-department assignment for some active employees with 2+ years tenure
        if emp_rec['status'] == 'active' and random.random() < cross_dept_rate:
            hire_dt = datetime.strptime(hire_date, '%Y-%m-%d')
            tenure_years = (current_date - hire_dt).days / 365.0

            if tenure_years >= 2:
                # Assign to a secondary department (different from primary)
                other_depts = [d for d in DEPARTMENTS if d["name"] != primary_dept["name"]]
                secondary_dept = weighted_choice(other_depts)
                secondary_dept_id = dept_map[secondary_dept["name"]]

                # Secondary assignment started 6-18 months ago
                secondary_start = current_date - timedelta(days=random.randint(180, 540))
                if secondary_start > hire_dt:
                    cursor.execute("""
                        INSERT INTO employee_departments (employee_id, department_id, start_date, end_date, is_primary)
                        VALUES (?, ?, ?, NULL, 0)
                    """, (emp_id, secondary_dept_id, secondary_start.strftime('%Y-%m-%d')))

    conn.commit()
    return assignments


def assign_employees_to_positions(conn: sqlite3.Connection, employee_records: list, pos_map: dict,
                                   dept_assignments: dict, promotion_rate: float = 0.15):
    """
    Assign employees to positions with weighted distribution, tenure-based salaries,
    and promotion history.

    Args:
        conn: Database connection
        employee_records: List of employee record dicts
        pos_map: Mapping of position title to ID
        dept_assignments: Dict mapping employee_id to their department info
        promotion_rate: Annual probability of promotion for eligible employees (default 15%)
    """
    cursor = conn.cursor()
    current_date = datetime.now()

    # Group positions by department
    positions_by_dept = {}
    for pos in POSITIONS:
        dept_name = pos["department"]
        if dept_name not in positions_by_dept:
            positions_by_dept[dept_name] = []
        positions_by_dept[dept_name].append(pos)

    promotions_count = 0

    for emp_rec in employee_records:
        emp_id = emp_rec['id']
        hire_date_str = emp_rec['hire_date']
        termination_date = emp_rec.get('termination_date')
        hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d')

        # Get department assignment
        dept_info = dept_assignments.get(emp_id)
        if not dept_info:
            continue

        dept_name = dept_info['primary_dept']
        available_positions = positions_by_dept.get(dept_name, [])
        if not available_positions:
            continue

        # Calculate tenure
        end_date = datetime.strptime(termination_date, '%Y-%m-%d') if termination_date else current_date
        tenure_years = (end_date - hire_date).days / 365.0

        # Determine if employee got promoted (only for 2+ year tenure)
        # Entry-level employees with good tenure may have been promoted
        was_promoted = False
        if tenure_years >= 2:
            # Cumulative promotion probability
            years_eligible = tenure_years - 1.5  # Eligible after 1.5 years
            cumulative_promo_prob = 1 - ((1 - promotion_rate) ** years_eligible)
            was_promoted = random.random() < cumulative_promo_prob

        if was_promoted:
            # Start with entry-level position, then promote
            entry_positions = [p for p in available_positions if p["level"] == 1]
            if not entry_positions:
                entry_positions = available_positions

            initial_pos = weighted_choice(entry_positions)
            initial_pos_id = pos_map.get(initial_pos["title"])

            if initial_pos_id:
                # Calculate initial salary (lower end since they were junior)
                initial_salary = calculate_tenure_salary(
                    initial_pos,
                    hire_date,
                    hire_date + timedelta(days=int(tenure_years * 365 * 0.4))  # ~40% through tenure
                )

                # Promotion happened after 1.5-3 years
                promo_delay_days = random.randint(540, 1095)
                promo_date = hire_date + timedelta(days=promo_delay_days)

                if promo_date < end_date:
                    # Insert initial position (now ended)
                    cursor.execute("""
                        INSERT INTO employee_positions (employee_id, position_id, start_date, end_date, salary, is_primary)
                        VALUES (?, ?, ?, ?, ?, 0)
                    """, (emp_id, initial_pos_id, hire_date_str, promo_date.strftime('%Y-%m-%d'), initial_salary))

                    # Get promoted position
                    new_title = PROMOTION_PATHS.get(initial_pos["title"])
                    new_pos = next((p for p in POSITIONS if p["title"] == new_title), None)

                    if new_pos:
                        new_pos_id = pos_map.get(new_pos["title"])
                        if new_pos_id:
                            # Calculate current salary in new role
                            new_salary = calculate_tenure_salary(new_pos, promo_date, end_date)

                            # Insert current position
                            pos_end_date = termination_date if termination_date else None
                            cursor.execute("""
                                INSERT INTO employee_positions (employee_id, position_id, start_date, end_date, salary, is_primary)
                                VALUES (?, ?, ?, ?, ?, 1)
                            """, (emp_id, new_pos_id, promo_date.strftime('%Y-%m-%d'), pos_end_date, new_salary))
                            promotions_count += 1
                            continue

        # No promotion - assign directly using weighted choice
        pos = weighted_choice(available_positions)
        pos_id = pos_map.get(pos["title"])
        if not pos_id:
            continue

        # Calculate tenure-based salary
        salary = calculate_tenure_salary(pos, hire_date, end_date)

        # Determine end_date for position
        pos_end_date = termination_date if termination_date else None

        cursor.execute("""
            INSERT INTO employee_positions (employee_id, position_id, start_date, end_date, salary, is_primary)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (emp_id, pos_id, hire_date_str, pos_end_date, salary))

    conn.commit()
    return promotions_count


def print_sample_data(conn: sqlite3.Connection, limit: int = 5):
    """Print sample records from database"""
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT e.id, e.first_name, e.last_name, e.email, d.name as dept, p.title as position, ep.salary
        FROM employees e
        LEFT JOIN employee_departments ed ON e.id = ed.employee_id AND ed.is_primary = 1
        LEFT JOIN departments d ON ed.department_id = d.id
        LEFT JOIN employee_positions ep ON e.id = ep.employee_id AND ep.is_primary = 1
        LEFT JOIN positions p ON ep.position_id = p.id
        ORDER BY e.id
        LIMIT {limit}
    """)

    rows = cursor.fetchall()

    print("\n📊 Sample Data:")
    print("-" * 120)
    print(f"{'ID':<5} {'Name':<25} {'Email':<30} {'Dept':<20} {'Position':<25} {'Salary':<10}")
    print("-" * 120)

    for row in rows:
        name = f"{row[1]} {row[2]}"
        print(f"{row[0]:<5} {name:<25} {row[3]:<30} {row[4] or 'N/A':<20} {row[5] or 'N/A':<25} {row[6] or 'N/A':<10}")

    print("-" * 120)


def get_database_stats(conn: sqlite3.Connection):
    """Get and display database statistics"""
    cursor = conn.cursor()

    # Total employees
    cursor.execute("SELECT COUNT(*) FROM employees WHERE status = 'active'")
    total_employees = cursor.fetchone()[0]

    # Departments
    cursor.execute("SELECT COUNT(*) FROM departments")
    total_departments = cursor.fetchone()[0]

    # Positions
    cursor.execute("SELECT COUNT(*) FROM positions")
    total_positions = cursor.fetchone()[0]

    # Average salary
    cursor.execute("""
        SELECT AVG(ep.salary)
        FROM employee_positions ep
        JOIN employees e ON ep.employee_id = e.id
        WHERE ep.end_date IS NULL AND e.status = 'active'
    """)
    avg_salary = cursor.fetchone()[0]

    # Employees by department
    cursor.execute("""
        SELECT d.name, COUNT(DISTINCT e.id) as count
        FROM departments d
        LEFT JOIN employee_departments ed ON d.id = ed.department_id AND ed.end_date IS NULL
        LEFT JOIN employees e ON ed.employee_id = e.id AND e.status = 'active'
        GROUP BY d.id, d.name
        ORDER BY count DESC
    """)
    dept_counts = cursor.fetchall()

    print("\n📈 Database Statistics:")
    print(f"   Total Employees: {total_employees}")
    print(f"   Total Departments: {total_departments}")
    print(f"   Total Positions: {total_positions}")
    print(f"   Average Salary: ${avg_salary:,.2f}" if avg_salary else "   Average Salary: N/A")
    print(f"\n   Employees by Department:")
    for dept_name, count in dept_counts:
        print(f"      {dept_name}: {count} employees")


def main():
    parser = argparse.ArgumentParser(
        description='Generate sample HR data using Faker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_hr_data.py --employees 100
  python generate_hr_data.py --output hr.db --clean
  python generate_hr_data.py --employees 200 --seed 42
  python generate_hr_data.py --employees 500 --turnover 15 --clean
        """
    )

    parser.add_argument(
        '--employees',
        type=int,
        default=50,
        help='Number of employee records to generate (default: 50)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='hr.db',
        help='Path to SQLite database file (default: hr.db)'
    )

    parser.add_argument(
        '--clean',
        action='store_true',
        help='Drop existing tables before generating new data'
    )

    parser.add_argument(
        '--turnover',
        type=float,
        default=12.0,
        help='Annual turnover percentage (default: 12)'
    )

    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Random seed for reproducibility'
    )

    args = parser.parse_args()

    # Set random seed if provided
    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    # Validate employees
    if args.employees < 1:
        print("❌ Error: --employees must be at least 1")
        return 1

    if args.turnover < 0 or args.turnover > 100:
        print("❌ Error: --turnover must be between 0 and 100")
        return 1

    if args.employees > 10000:
        print("⚠️  Warning: Generating more than 10,000 employees may take a while")
        response = input("   Continue? (y/n): ")
        if response.lower() != 'y':
            print("   Cancelled")
            return 0

    print("=" * 60)
    print("  HR Management System Data Generator")
    print("=" * 60)
    print(f"📝 Configuration:")
    print(f"   Employees: {args.employees}")
    print(f"   Output: {args.output}")
    print(f"   Clean mode: {'Yes' if args.clean else 'No'}")
    print(f"   Turnover rate: {args.turnover}%")
    print(f"   Random seed: {args.seed if args.seed else 'None (random)'}")
    print()

    # Create database
    print("🔨 Creating database schema...")
    conn = create_database(args.output, clean=args.clean)

    # Insert departments
    print("🏢 Inserting departments...")
    dept_map = insert_departments(conn)
    print(f"   ✅ Inserted {len(dept_map)} departments")

    # Insert positions
    print("💼 Inserting positions...")
    pos_map = insert_positions(conn, dept_map)
    print(f"   ✅ Inserted {len(pos_map)} positions")

    # Generate employees
    print(f"👥 Generating {args.employees} employees (turnover: {args.turnover}%)...")
    employees = generate_employees(args.employees, turnover_pct=args.turnover)

    # Count status distribution
    active_count = sum(1 for e in employees if e['status'] == 'active')
    terminated_count = sum(1 for e in employees if e['status'] == 'terminated')
    on_leave_count = sum(1 for e in employees if e['status'] == 'on_leave')

    # Insert employees
    print("💾 Inserting employees...")
    inserted, skipped, employee_records = insert_employees(conn, employees)
    print(f"   ✅ Inserted {inserted} employees")
    print(f"      Active: {active_count}, Terminated: {terminated_count}, On Leave: {on_leave_count}")
    if skipped > 0:
        print(f"   ⚠️  Skipped {skipped} duplicates")

    # Assign departments (with cross-department support)
    print("🔗 Assigning employees to departments...")
    dept_assignments = assign_employees_to_departments(conn, employee_records, dept_map)
    print(f"   ✅ Assigned {len(dept_assignments)} employees to departments")

    # Count cross-department assignments
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(DISTINCT employee_id)
        FROM employee_departments
        WHERE is_primary = 0 AND end_date IS NULL
    """)
    cross_dept_count = cursor.fetchone()[0]
    if cross_dept_count > 0:
        print(f"      Cross-department: {cross_dept_count} employees")

    # Assign positions (with promotions)
    print("💼 Assigning employees to positions...")
    promotions_count = assign_employees_to_positions(conn, employee_records, pos_map, dept_assignments)
    print(f"   ✅ Assigned {len(employee_records)} employees to positions")
    if promotions_count > 0:
        print(f"      Promotions: {promotions_count} employees have position history")

    # Show sample data
    print_sample_data(conn, limit=10)

    # Show statistics
    get_database_stats(conn)

    # Close connection
    conn.close()

    print(f"\n✅ Database created successfully: {args.output}")
    print(f"\n💡 Next steps:")
    print(f"   1. Test queries with sqlite3:")
    print(f"      sqlite3 {args.output} 'SELECT * FROM employees LIMIT 5;'")
    print(f"\n   2. Generate SQL templates:")
    print(f"      cd ../..")
    print(f"      ./generate_templates.sh \\")
    print(f"        --schema examples/sqlite/contact/hr_schema.sql \\")
    print(f"        --queries examples/sqlite/contact/hr_test_queries.md \\")
    print(f"        --domain examples/sqlite/contact/hr-domain.yaml \\")
    print(f"        --output hr-templates.yaml")

    return 0


if __name__ == '__main__':
    sys.exit(main())
