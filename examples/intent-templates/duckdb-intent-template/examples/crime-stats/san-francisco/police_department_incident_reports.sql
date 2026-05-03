-- San Francisco Police Department Incident Reports (2018-Present)
-- Source: https://data.sfgov.org/Public-Safety/Police-Department-Incident-Reports-2018-to-Present/wg3w-h783/about_data
-- Data spans 2018-present, ~1M records
-- Covers all incident reports filed by SFPD officers and online

CREATE TABLE IF NOT EXISTS sf_incident_reports (
    row_id BIGINT PRIMARY KEY,
    incident_datetime VARCHAR,
    incident_date DATE,
    incident_time VARCHAR,
    incident_year INTEGER,
    incident_day_of_week VARCHAR,
    report_datetime VARCHAR,
    incident_id INTEGER,
    incident_number VARCHAR,
    cad_number VARCHAR,
    report_type_code VARCHAR,
    report_type_description VARCHAR,
    filed_online VARCHAR,
    incident_code VARCHAR,
    incident_category VARCHAR,
    incident_subcategory VARCHAR,
    incident_description VARCHAR,
    resolution VARCHAR,
    intersection VARCHAR,
    cnn VARCHAR,
    police_district VARCHAR,
    analysis_neighborhood VARCHAR,
    supervisor_district VARCHAR,
    supervisor_district_2012 VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    point VARCHAR,
    data_as_of VARCHAR,
    data_loaded_at VARCHAR
);

-- Indexes on commonly filtered columns
CREATE INDEX IF NOT EXISTS idx_sf_ir_incident_year ON sf_incident_reports(incident_year);
CREATE INDEX IF NOT EXISTS idx_sf_ir_incident_date ON sf_incident_reports(incident_date);
CREATE INDEX IF NOT EXISTS idx_sf_ir_incident_category ON sf_incident_reports(incident_category);
CREATE INDEX IF NOT EXISTS idx_sf_ir_incident_subcategory ON sf_incident_reports(incident_subcategory);
CREATE INDEX IF NOT EXISTS idx_sf_ir_resolution ON sf_incident_reports(resolution);
CREATE INDEX IF NOT EXISTS idx_sf_ir_police_district ON sf_incident_reports(police_district);
CREATE INDEX IF NOT EXISTS idx_sf_ir_analysis_neighborhood ON sf_incident_reports(analysis_neighborhood);
CREATE INDEX IF NOT EXISTS idx_sf_ir_supervisor_district ON sf_incident_reports(supervisor_district);
CREATE INDEX IF NOT EXISTS idx_sf_ir_incident_day_of_week ON sf_incident_reports(incident_day_of_week);
