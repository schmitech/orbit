-- Toronto Police Robbery Occurrences
-- Source: Toronto Police Service Public Safety Data Portal
-- Data spans 2014 - 2025

CREATE TABLE IF NOT EXISTS robbery (
    id INTEGER PRIMARY KEY,
    event_unique_id VARCHAR,
    report_date TIMESTAMP,
    occ_date TIMESTAMP,
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

-- Create indexes on commonly filtered columns
CREATE INDEX IF NOT EXISTS idx_robbery_occ_year ON robbery(occ_year);
CREATE INDEX IF NOT EXISTS idx_robbery_division ON robbery(division);
CREATE INDEX IF NOT EXISTS idx_robbery_neighbourhood_158 ON robbery(neighbourhood_158);
CREATE INDEX IF NOT EXISTS idx_robbery_offence ON robbery(offence);
CREATE INDEX IF NOT EXISTS idx_robbery_premises_type ON robbery(premises_type);
