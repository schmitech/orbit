-- Toronto Police Break and Enter Database Schema for DuckDB
-- Source: Toronto Police Service Public Safety Data Portal - Break and Enter Open Data
-- https://data.tps.ca/datasets/TorontoPS::break-and-enter-open-data/about
-- Data spans 2014-2025 with ~83,129 break and enter occurrence records
-- Includes B&E, B&E with intent, B&E out, unlawfully in dwelling-house
-- Optimized for analytical queries on break and enter patterns

CREATE TABLE IF NOT EXISTS break_and_enter (
    id INTEGER PRIMARY KEY,
    event_unique_id VARCHAR,
    report_date DATE,
    occ_date DATE,
    report_year INTEGER,
    report_month VARCHAR,
    report_day INTEGER,
    report_doy INTEGER,
    report_dow VARCHAR,
    report_hour INTEGER,
    occ_year INTEGER,
    occ_month VARCHAR,
    occ_day INTEGER,
    occ_doy INTEGER,
    occ_dow VARCHAR,
    occ_hour INTEGER,
    division VARCHAR,
    location_type VARCHAR,
    premises_type VARCHAR,
    ucr_code INTEGER,
    ucr_ext INTEGER,
    offence VARCHAR,
    csi_category VARCHAR,
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
CREATE INDEX IF NOT EXISTS idx_break_and_enter_occ_year ON break_and_enter(occ_year);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_report_year ON break_and_enter(report_year);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_division ON break_and_enter(division);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_neighbourhood_158 ON break_and_enter(neighbourhood_158);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_neighbourhood_140 ON break_and_enter(neighbourhood_140);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_premises_type ON break_and_enter(premises_type);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_location_type ON break_and_enter(location_type);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_offence ON break_and_enter(offence);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_ucr_ext ON break_and_enter(ucr_ext);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_occ_dow ON break_and_enter(occ_dow);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_occ_hour ON break_and_enter(occ_hour);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_occ_date ON break_and_enter(occ_date);
CREATE INDEX IF NOT EXISTS idx_break_and_enter_csi_category ON break_and_enter(csi_category);
