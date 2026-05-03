-- Ottawa Police Criminal Offences Database Schema for DuckDB
-- Source: Ottawa Police Community Safety Data Portal - Criminal Offences
-- Data spans 2018-present with detailed criminal offence incident records
-- Optimized for analytical queries on crime patterns

-- Create criminal_offences table
CREATE TABLE IF NOT EXISTS criminal_offences (
    id INTEGER PRIMARY KEY,
    year INTEGER,
    reported_date DATE,
    reported_hour INTEGER,
    occurred_date DATE,
    occurred_hour INTEGER,
    weekday VARCHAR,
    offence_summary VARCHAR,
    offence_category VARCHAR,
    neighbourhood VARCHAR,
    sector VARCHAR,
    division VARCHAR,
    census_tract VARCHAR,
    time_of_day VARCHAR,
    ward VARCHAR,
    councillor VARCHAR,
    intersection VARCHAR,
    x DOUBLE,
    y DOUBLE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_criminal_offences_year ON criminal_offences(year);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_offence_summary ON criminal_offences(offence_summary);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_offence_category ON criminal_offences(offence_category);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_neighbourhood ON criminal_offences(neighbourhood);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_ward ON criminal_offences(ward);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_division ON criminal_offences(division);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_sector ON criminal_offences(sector);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_time_of_day ON criminal_offences(time_of_day);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_occurred_date ON criminal_offences(occurred_date);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_reported_date ON criminal_offences(reported_date);
CREATE INDEX IF NOT EXISTS idx_criminal_offences_weekday ON criminal_offences(weekday);
