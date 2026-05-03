-- Edmonton Police Service Occurrences Database Schema for DuckDB
-- Source: Edmonton Police Service Community Safety Data Portal
-- Data spans 2023-present with police occurrence records
-- Categories: Disorder, Drugs, Non-Violent, Other, Traffic, Violent, Weapons

CREATE TABLE IF NOT EXISTS occurrences (
    id INTEGER PRIMARY KEY,
    occurrence_category VARCHAR,
    occurrence_group VARCHAR,
    occurrence_type VARCHAR,
    intersection VARCHAR,
    date_reported DATE,
    year INTEGER
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_occurrences_year ON occurrences(year);
CREATE INDEX IF NOT EXISTS idx_occurrences_category ON occurrences(occurrence_category);
CREATE INDEX IF NOT EXISTS idx_occurrences_group ON occurrences(occurrence_group);
CREATE INDEX IF NOT EXISTS idx_occurrences_type ON occurrences(occurrence_type);
CREATE INDEX IF NOT EXISTS idx_occurrences_intersection ON occurrences(intersection);
CREATE INDEX IF NOT EXISTS idx_occurrences_date_reported ON occurrences(date_reported);
