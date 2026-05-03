-- Winnipeg Police Crime Statistics (UCR)
-- Source: City of Winnipeg Open Data
-- Data spans 2017 to current (5-year + monthly lag)

CREATE TABLE IF NOT EXISTS winnipeg_crime_ucr (
    id INTEGER PRIMARY KEY,
    year INTEGER,
    month INTEGER,
    neighbourhood VARCHAR,
    community VARCHAR,
    count_stats INTEGER,
    crime_type VARCHAR,
    offence VARCHAR
);

-- Create indexes on commonly filtered columns
CREATE INDEX IF NOT EXISTS idx_winnipeg_crime_ucr_year ON winnipeg_crime_ucr(year);
CREATE INDEX IF NOT EXISTS idx_winnipeg_crime_ucr_month ON winnipeg_crime_ucr(month);
CREATE INDEX IF NOT EXISTS idx_winnipeg_crime_ucr_crime_type ON winnipeg_crime_ucr(crime_type);
CREATE INDEX IF NOT EXISTS idx_winnipeg_crime_ucr_offence ON winnipeg_crime_ucr(offence);
CREATE INDEX IF NOT EXISTS idx_winnipeg_crime_ucr_neighbourhood ON winnipeg_crime_ucr(neighbourhood);
CREATE INDEX IF NOT EXISTS idx_winnipeg_crime_ucr_community ON winnipeg_crime_ucr(community);
