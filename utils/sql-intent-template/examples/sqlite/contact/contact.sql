-- Contact Database Schema
-- Ultra-simple schema for testing SQL intent template generation
-- Just one table with basic columns

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Create a simple users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    age INTEGER,
    city TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample data
INSERT OR IGNORE INTO users (name, email, age, city) VALUES
    ('John Doe', 'john@example.com', 25, 'Ottawa'),
    ('Jane Smith', 'jane@example.com', 30, 'Toronto'),
    ('Bob Johnson', 'bob@example.com', 35, 'Calgary'),
    ('Alice Brown', 'alice@example.com', 28, 'Montreal'),
    ('Charlie Wilson', 'charlie@example.com', 32, 'Edmonton'),
    ('Diana Prince', 'diana@example.com', 27, 'Vancouver'),
    ('Eve Adams', 'eve@example.com', 33, 'Winnipeg'),
    ('Frank Miller', 'frank@example.com', 29, 'Edmonton');
