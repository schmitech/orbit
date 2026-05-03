-- Toronto Police Bicycle Theft Database Schema for DuckDB
-- Source: Toronto Police Service Public Safety Data Portal - Bicycle Thefts Open Data
-- https://data.tps.ca/datasets/TorontoPS::bicycle-thefts-open-data/about
-- Data spans 2014-2025 with ~39,848 bicycle-related occurrence records
-- Includes theft, B&E, property found/recovered, and e-bike theft
-- Optimized for analytical queries on bicycle theft patterns

CREATE TABLE IF NOT EXISTS bicycle_theft (
    id INTEGER PRIMARY KEY,
    event_unique_id VARCHAR,
    primary_offence VARCHAR,
    occ_date DATE,
    occ_year INTEGER,
    occ_month VARCHAR,
    occ_dow VARCHAR,
    occ_day INTEGER,
    occ_doy INTEGER,
    occ_hour INTEGER,
    report_date DATE,
    report_year INTEGER,
    report_month VARCHAR,
    report_dow VARCHAR,
    report_day INTEGER,
    report_doy INTEGER,
    report_hour INTEGER,
    division VARCHAR,
    location_type VARCHAR,
    premises_type VARCHAR,
    bike_make VARCHAR,
    bike_model VARCHAR,
    bike_type VARCHAR,
    bike_speed INTEGER,
    bike_colour VARCHAR,
    bike_cost INTEGER,
    status VARCHAR,
    hood_158 VARCHAR,
    neighbourhood_158 VARCHAR,
    hood_140 VARCHAR,
    neighbourhood_140 VARCHAR,
    long_wgs84 DOUBLE,
    lat_wgs84 DOUBLE,
    x DOUBLE,
    y DOUBLE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_occ_year ON bicycle_theft(occ_year);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_report_year ON bicycle_theft(report_year);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_division ON bicycle_theft(division);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_neighbourhood_158 ON bicycle_theft(neighbourhood_158);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_neighbourhood_140 ON bicycle_theft(neighbourhood_140);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_premises_type ON bicycle_theft(premises_type);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_location_type ON bicycle_theft(location_type);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_primary_offence ON bicycle_theft(primary_offence);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_bike_type ON bicycle_theft(bike_type);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_status ON bicycle_theft(status);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_occ_dow ON bicycle_theft(occ_dow);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_occ_hour ON bicycle_theft(occ_hour);
CREATE INDEX IF NOT EXISTS idx_bicycle_theft_occ_date ON bicycle_theft(occ_date);
