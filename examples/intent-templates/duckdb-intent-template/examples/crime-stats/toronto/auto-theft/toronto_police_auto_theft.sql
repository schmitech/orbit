-- Toronto Police Auto Theft Database Schema for DuckDB
-- Source: Toronto Police Service Public Safety Data Portal - Auto Theft Open Data
-- Data spans 2014-present with motor vehicle theft incident records
-- Optimized for analytical queries on auto theft patterns

-- Create auto_theft table
CREATE TABLE IF NOT EXISTS auto_theft (
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
CREATE INDEX IF NOT EXISTS idx_auto_theft_occ_year ON auto_theft(occ_year);
CREATE INDEX IF NOT EXISTS idx_auto_theft_report_year ON auto_theft(report_year);
CREATE INDEX IF NOT EXISTS idx_auto_theft_division ON auto_theft(division);
CREATE INDEX IF NOT EXISTS idx_auto_theft_neighbourhood_158 ON auto_theft(neighbourhood_158);
CREATE INDEX IF NOT EXISTS idx_auto_theft_neighbourhood_140 ON auto_theft(neighbourhood_140);
CREATE INDEX IF NOT EXISTS idx_auto_theft_premises_type ON auto_theft(premises_type);
CREATE INDEX IF NOT EXISTS idx_auto_theft_location_type ON auto_theft(location_type);
CREATE INDEX IF NOT EXISTS idx_auto_theft_occ_dow ON auto_theft(occ_dow);
CREATE INDEX IF NOT EXISTS idx_auto_theft_occ_hour ON auto_theft(occ_hour);
CREATE INDEX IF NOT EXISTS idx_auto_theft_occ_date ON auto_theft(occ_date);
CREATE INDEX IF NOT EXISTS idx_auto_theft_report_date ON auto_theft(report_date);
