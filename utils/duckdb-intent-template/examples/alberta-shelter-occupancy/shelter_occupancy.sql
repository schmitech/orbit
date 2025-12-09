-- Alberta Emergency Shelter Occupancy Database Schema for DuckDB
-- Source: Government of Alberta Open Data - Emergency Shelter Occupancy
-- Data spans 2013-2025 with daily occupancy metrics for emergency shelters
-- Optimized for analytical queries on shelter utilization data

-- Create shelter_occupancy table
CREATE TABLE IF NOT EXISTS shelter_occupancy (
    id INTEGER PRIMARY KEY,
    date DATE,
    city VARCHAR,
    shelter_type VARCHAR,
    shelter_name VARCHAR,
    organization VARCHAR,
    shelter VARCHAR,
    capacity INTEGER,
    overnight INTEGER,
    daytime INTEGER,
    year INTEGER,
    month INTEGER
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_shelter_date ON shelter_occupancy(date);
CREATE INDEX IF NOT EXISTS idx_shelter_city ON shelter_occupancy(city);
CREATE INDEX IF NOT EXISTS idx_shelter_type ON shelter_occupancy(shelter_type);
CREATE INDEX IF NOT EXISTS idx_shelter_name ON shelter_occupancy(shelter_name);
CREATE INDEX IF NOT EXISTS idx_shelter_organization ON shelter_occupancy(organization);
CREATE INDEX IF NOT EXISTS idx_shelter_year ON shelter_occupancy(year);
CREATE INDEX IF NOT EXISTS idx_shelter_month ON shelter_occupancy(month);
CREATE INDEX IF NOT EXISTS idx_shelter_year_month ON shelter_occupancy(year, month);
