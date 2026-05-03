-- Vancouver Police Department Crime Data Schema for DuckDB
-- Source: VPD GeoDASH Open Data
-- Data spans 2003-present (all neighbourhoods, all years)
-- Uses "All Offence / Founded" reporting method (not comparable to Statistics Canada UCR)

CREATE TABLE IF NOT EXISTS crime_data (
    id INTEGER PRIMARY KEY,
    crime_type VARCHAR,
    year INTEGER,
    month INTEGER,
    day INTEGER,
    hour INTEGER,
    minute INTEGER,
    hundred_block VARCHAR,
    neighbourhood VARCHAR,
    reported_date DATE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_crime_data_year ON crime_data(year);
CREATE INDEX IF NOT EXISTS idx_crime_data_crime_type ON crime_data(crime_type);
CREATE INDEX IF NOT EXISTS idx_crime_data_neighbourhood ON crime_data(neighbourhood);
CREATE INDEX IF NOT EXISTS idx_crime_data_hundred_block ON crime_data(hundred_block);
CREATE INDEX IF NOT EXISTS idx_crime_data_reported_date ON crime_data(reported_date);
CREATE INDEX IF NOT EXISTS idx_crime_data_hour ON crime_data(hour);
