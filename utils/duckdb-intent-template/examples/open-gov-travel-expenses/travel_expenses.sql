-- Travel Expenses Database Schema for DuckDB
-- Government of Canada Proactive Disclosure - Travel Expenses
-- Source: https://open.canada.ca/data/en/dataset/009f9a49-c2d9-4d29-a6d4-1a228da335ce
-- Optimized for analytical queries on travel expense data

-- Create travel_expenses table
CREATE TABLE IF NOT EXISTS travel_expenses (
    ref_number VARCHAR PRIMARY KEY,
    disclosure_group VARCHAR,
    title_en VARCHAR,
    title_fr VARCHAR,
    name VARCHAR,
    purpose_en VARCHAR,
    purpose_fr VARCHAR,
    start_date DATE,
    end_date DATE,
    destination_en VARCHAR,
    destination_fr VARCHAR,
    destination_2_en VARCHAR,
    destination_2_fr VARCHAR,
    destination_other_en VARCHAR,
    destination_other_fr VARCHAR,
    airfare DECIMAL(10, 2),
    other_transport DECIMAL(10, 2),
    lodging DECIMAL(10, 2),
    meals DECIMAL(10, 2),
    other_expenses DECIMAL(10, 2),
    total DECIMAL(10, 2),
    additional_comments_en VARCHAR,
    additional_comments_fr VARCHAR,
    owner_org VARCHAR,
    owner_org_title VARCHAR
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_travel_start_date ON travel_expenses(start_date);
CREATE INDEX IF NOT EXISTS idx_travel_end_date ON travel_expenses(end_date);
CREATE INDEX IF NOT EXISTS idx_travel_name ON travel_expenses(name);
CREATE INDEX IF NOT EXISTS idx_travel_owner_org ON travel_expenses(owner_org);
CREATE INDEX IF NOT EXISTS idx_travel_total ON travel_expenses(total);
CREATE INDEX IF NOT EXISTS idx_travel_disclosure_group ON travel_expenses(disclosure_group);

