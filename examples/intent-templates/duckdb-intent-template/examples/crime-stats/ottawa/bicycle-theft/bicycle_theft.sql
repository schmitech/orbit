-- Ottawa Police Bicycle Theft Database Schema for DuckDB
-- Source: Ottawa Police Community Safety Data Portal - Bicycle Theft
-- https://data.ottawapolice.ca/datasets/eff8a6410ec74136b5f611017e244a4e_0/about
-- Data spans 2018-2024 with ~13,995 bicycle-related property crime records
-- Includes theft, recovery, break & enter involving bicycles, and e-scooters
-- Optimized for analytical queries on bicycle theft patterns

CREATE TABLE IF NOT EXISTS bicycle_theft (
    id INTEGER PRIMARY KEY,
    incident_id INTEGER,
    year INTEGER,
    reported_date DATE,
    occurred_date DATE,
    weekday VARCHAR,
    offence_category VARCHAR,
    bicycle_style VARCHAR,
    bicycle_value INTEGER,
    bicycle_make VARCHAR,
    bicycle_model VARCHAR,
    bicycle_type VARCHAR,
    bicycle_frame VARCHAR,
    bicycle_colour VARCHAR,
    bicycle_speed INTEGER,
    neighbourhood VARCHAR,
    sector VARCHAR,
    division VARCHAR,
    census_tract VARCHAR,
    status VARCHAR,
    intersection VARCHAR,
    time_of_day VARCHAR,
    ward VARCHAR,
    councillor VARCHAR,
    reported_hour INTEGER,
    occurred_hour INTEGER,
    x DOUBLE,
    y DOUBLE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_year ON bicycle_theft(year);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_neighbourhood ON bicycle_theft(neighbourhood);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_division ON bicycle_theft(division);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_ward ON bicycle_theft(ward);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_offence_category ON bicycle_theft(offence_category);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_status ON bicycle_theft(status);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_bicycle_type ON bicycle_theft(bicycle_type);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_bicycle_style ON bicycle_theft(bicycle_style);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_time_of_day ON bicycle_theft(time_of_day);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_occurred_date ON bicycle_theft(occurred_date);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_weekday ON bicycle_theft(weekday);
