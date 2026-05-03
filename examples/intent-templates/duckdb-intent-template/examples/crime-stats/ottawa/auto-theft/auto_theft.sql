-- Ottawa Police Auto Theft Database Schema for DuckDB
-- Source: Ottawa Police Community Safety Data Portal - Theft of Motor Vehicle
-- Data spans 2018-present with detailed vehicle theft incident records
-- Optimized for analytical queries on auto theft patterns

-- Create auto_theft table
CREATE TABLE IF NOT EXISTS auto_theft (
    id INTEGER PRIMARY KEY,
    vehicle_year INTEGER,
    vehicle_make VARCHAR,
    vehicle_model VARCHAR,
    vehicle_style VARCHAR,
    vehicle_colour VARCHAR,
    vehicle_value INTEGER,
    weekday VARCHAR,
    recovered VARCHAR,
    neighbourhood VARCHAR,
    ward VARCHAR,
    sector VARCHAR,
    reported_date DATE,
    occurred_date DATE,
    year INTEGER,
    intersection VARCHAR,
    division VARCHAR,
    census_tract VARCHAR,
    time_of_day VARCHAR,
    councillor VARCHAR,
    reported_hour INTEGER,
    occurred_hour INTEGER,
    x DOUBLE,
    y DOUBLE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_auto_theft_year ON auto_theft(year);
CREATE INDEX IF NOT EXISTS idx_auto_theft_vehicle_make ON auto_theft(vehicle_make);
CREATE INDEX IF NOT EXISTS idx_auto_theft_vehicle_style ON auto_theft(vehicle_style);
CREATE INDEX IF NOT EXISTS idx_auto_theft_neighbourhood ON auto_theft(neighbourhood);
CREATE INDEX IF NOT EXISTS idx_auto_theft_ward ON auto_theft(ward);
CREATE INDEX IF NOT EXISTS idx_auto_theft_division ON auto_theft(division);
CREATE INDEX IF NOT EXISTS idx_auto_theft_recovered ON auto_theft(recovered);
CREATE INDEX IF NOT EXISTS idx_auto_theft_time_of_day ON auto_theft(time_of_day);
CREATE INDEX IF NOT EXISTS idx_auto_theft_occurred_date ON auto_theft(occurred_date);
CREATE INDEX IF NOT EXISTS idx_auto_theft_reported_date ON auto_theft(reported_date);
