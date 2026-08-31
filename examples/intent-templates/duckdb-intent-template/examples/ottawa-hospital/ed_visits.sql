-- Ottawa Hospital ED Visits Database Schema for DuckDB
-- Source: City of Ottawa Open Data - ED Visits to Ottawa Hospitals
-- Tracks weekly emergency department visits by age group and respiratory causes
-- Optimized for analytical queries on ED visit patterns

-- Create ed_visits table
CREATE TABLE IF NOT EXISTS ed_visits (
    id INTEGER PRIMARY KEY,
    epi_week DATE,
    epi_year INTEGER,
    epi_week_num INTEGER,
    age_category VARCHAR,
    all_causes_visits INTEGER,
    respiratory_visits INTEGER,
    respiratory_pct DECIMAL(5,2)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_ed_visits_epi_week ON ed_visits(epi_week);
CREATE INDEX IF NOT EXISTS idx_ed_visits_epi_year ON ed_visits(epi_year);
CREATE INDEX IF NOT EXISTS idx_ed_visits_age_category ON ed_visits(age_category);
CREATE INDEX IF NOT EXISTS idx_ed_visits_epi_week_num ON ed_visits(epi_week_num);
