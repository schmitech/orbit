-- HR Management System Database Schema
-- Multi-table relational schema for HR management
-- Replaces simple contact table with proper HR structure

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- ============================================================================
-- DEPARTMENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    location TEXT,
    budget DECIMAL(10, 2),
    manager_id INTEGER,  -- References employees.id (self-referential)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (manager_id) REFERENCES employees(id)
);

-- ============================================================================
-- POSITIONS TABLE (Job Titles/Roles)
-- ============================================================================
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    department_id INTEGER,
    min_salary DECIMAL(10, 2),
    max_salary DECIMAL(10, 2),
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

-- ============================================================================
-- EMPLOYEES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    birth_date DATE,
    hire_date DATE NOT NULL,
    termination_date DATE,
    status TEXT DEFAULT 'active',  -- active, terminated, on_leave
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- EMPLOYEE-DEPARTMENT ASSIGNMENTS (with history)
-- ============================================================================
CREATE TABLE IF NOT EXISTS employee_departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    department_id INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,  -- NULL means current assignment
    is_primary BOOLEAN DEFAULT 1,  -- Primary department assignment
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

-- ============================================================================
-- EMPLOYEE-POSITION ASSIGNMENTS (with history and salary)
-- ============================================================================
CREATE TABLE IF NOT EXISTS employee_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    position_id INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,  -- NULL means current position
    salary DECIMAL(10, 2),
    is_primary BOOLEAN DEFAULT 1,  -- Primary position
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (position_id) REFERENCES positions(id)
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_employees_email ON employees(email);
CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(status);
CREATE INDEX IF NOT EXISTS idx_employees_hire_date ON employees(hire_date);
CREATE INDEX IF NOT EXISTS idx_employee_departments_employee ON employee_departments(employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_departments_department ON employee_departments(department_id);
CREATE INDEX IF NOT EXISTS idx_employee_positions_employee ON employee_positions(employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_positions_position ON employee_positions(position_id);
CREATE INDEX IF NOT EXISTS idx_positions_department ON positions(department_id);

-- ============================================================================
-- SAMPLE DATA
-- ============================================================================

-- Insert Departments
INSERT OR IGNORE INTO departments (id, name, location, budget) VALUES
    (1, 'Engineering', 'San Francisco', 5000000.00),
    (2, 'Sales', 'New York', 3000000.00),
    (3, 'Marketing', 'Los Angeles', 2000000.00),
    (4, 'Human Resources', 'Chicago', 1500000.00),
    (5, 'Finance', 'Boston', 2500000.00),
    (6, 'Operations', 'Seattle', 4000000.00);

-- Insert Positions
INSERT OR IGNORE INTO positions (id, title, department_id, min_salary, max_salary, description) VALUES
    (1, 'Software Engineer', 1, 80000, 150000, 'Develops software applications'),
    (2, 'Senior Software Engineer', 1, 120000, 200000, 'Senior software development role'),
    (3, 'Engineering Manager', 1, 150000, 250000, 'Manages engineering team'),
    (4, 'Sales Representative', 2, 50000, 100000, 'Sells company products'),
    (5, 'Sales Manager', 2, 100000, 180000, 'Manages sales team'),
    (6, 'Marketing Specialist', 3, 55000, 95000, 'Marketing campaigns and strategy'),
    (7, 'Marketing Manager', 3, 90000, 150000, 'Manages marketing team'),
    (8, 'HR Coordinator', 4, 45000, 75000, 'HR administrative tasks'),
    (9, 'HR Manager', 4, 80000, 130000, 'Manages HR department'),
    (10, 'Financial Analyst', 5, 60000, 110000, 'Financial analysis and reporting'),
    (11, 'Finance Manager', 5, 100000, 170000, 'Manages finance department'),
    (12, 'Operations Coordinator', 6, 50000, 90000, 'Operations support'),
    (13, 'Operations Manager', 6, 95000, 160000, 'Manages operations team');

-- Insert Employees
INSERT OR IGNORE INTO employees (id, first_name, last_name, email, phone, birth_date, hire_date, status) VALUES
    (1, 'John', 'Doe', 'john.doe@company.com', '555-0101', '1990-05-15', '2020-01-15', 'active'),
    (2, 'Jane', 'Smith', 'jane.smith@company.com', '555-0102', '1988-03-22', '2019-06-10', 'active'),
    (3, 'Bob', 'Johnson', 'bob.johnson@company.com', '555-0103', '1985-11-08', '2018-03-20', 'active'),
    (4, 'Alice', 'Brown', 'alice.brown@company.com', '555-0104', '1992-07-30', '2021-02-01', 'active'),
    (5, 'Charlie', 'Wilson', 'charlie.wilson@company.com', '555-0105', '1987-12-14', '2019-09-05', 'active'),
    (6, 'Diana', 'Prince', 'diana.prince@company.com', '555-0106', '1991-09-18', '2020-11-12', 'active'),
    (7, 'Eve', 'Adams', 'eve.adams@company.com', '555-0107', '1989-04-25', '2021-05-20', 'active'),
    (8, 'Frank', 'Miller', 'frank.miller@company.com', '555-0108', '1986-08-03', '2018-08-15', 'active'),
    (9, 'Grace', 'Davis', 'grace.davis@company.com', '555-0109', '1993-01-10', '2022-01-10', 'active'),
    (10, 'Henry', 'Garcia', 'henry.garcia@company.com', '555-0110', '1984-06-28', '2017-12-01', 'active');

-- Insert Employee-Department Assignments
INSERT OR IGNORE INTO employee_departments (employee_id, department_id, start_date, is_primary) VALUES
    (1, 1, '2020-01-15', 1),  -- John - Engineering
    (2, 2, '2019-06-10', 1),  -- Jane - Sales
    (3, 1, '2018-03-20', 1),  -- Bob - Engineering
    (4, 3, '2021-02-01', 1),  -- Alice - Marketing
    (5, 4, '2019-09-05', 1),  -- Charlie - HR
    (6, 5, '2020-11-12', 1),  -- Diana - Finance
    (7, 6, '2021-05-20', 1),  -- Eve - Operations
    (8, 1, '2018-08-15', 1),  -- Frank - Engineering
    (9, 2, '2022-01-10', 1),  -- Grace - Sales
    (10, 5, '2017-12-01', 1); -- Henry - Finance

-- Insert Employee-Position Assignments
INSERT OR IGNORE INTO employee_positions (employee_id, position_id, start_date, salary, is_primary) VALUES
    (1, 1, '2020-01-15', 95000, 1),   -- John - Software Engineer
    (2, 4, '2019-06-10', 75000, 1),   -- Jane - Sales Representative
    (3, 3, '2018-03-20', 180000, 1),  -- Bob - Engineering Manager
    (4, 6, '2021-02-01', 70000, 1),   -- Alice - Marketing Specialist
    (5, 8, '2019-09-05', 60000, 1),   -- Charlie - HR Coordinator
    (6, 10, '2020-11-12', 85000, 1),  -- Diana - Financial Analyst
    (7, 12, '2021-05-20', 65000, 1),  -- Eve - Operations Coordinator
    (8, 2, '2018-08-15', 140000, 1),  -- Frank - Senior Software Engineer
    (9, 4, '2022-01-10', 60000, 1),   -- Grace - Sales Representative
    (10, 11, '2017-12-01', 150000, 1); -- Henry - Finance Manager
