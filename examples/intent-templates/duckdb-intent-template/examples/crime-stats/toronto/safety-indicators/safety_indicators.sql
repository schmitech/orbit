-- Toronto Police Community Safety Indicators Database Schema for DuckDB
-- Source: Toronto Police Service Public Safety Data Portal - Community Safety Indicators / Major Crime Indicators Open Data
-- Report dates span 2014-2025 in this CSV, with occurrence years mostly 2013-2025 and sparse older legacy records
-- Includes selected CSI categories: Assault, Break and Enter, Auto Theft, Robbery, and Theft Over

CREATE TABLE IF NOT EXISTS safety_indicators (
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

CREATE INDEX IF NOT EXISTS idx_safety_indicators_report_year ON safety_indicators(report_year);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_occ_year ON safety_indicators(occ_year);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_division ON safety_indicators(division);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_csi_category ON safety_indicators(csi_category);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_offence ON safety_indicators(offence);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_premises_type ON safety_indicators(premises_type);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_location_type ON safety_indicators(location_type);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_neighbourhood_158 ON safety_indicators(neighbourhood_158);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_neighbourhood_140 ON safety_indicators(neighbourhood_140);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_occ_date ON safety_indicators(occ_date);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_report_date ON safety_indicators(report_date);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_occ_dow ON safety_indicators(occ_dow);
CREATE INDEX IF NOT EXISTS idx_safety_indicators_occ_hour ON safety_indicators(occ_hour);
