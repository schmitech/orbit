-- Electric Vehicle Population Database Schema for DuckDB
-- Washington State DOL Electric Vehicle Registration Data
-- Optimized for analytical queries on BEV and PHEV registrations

-- Create main electric vehicles table
CREATE TABLE IF NOT EXISTS electric_vehicles (
    id INTEGER PRIMARY KEY,
    vin_prefix VARCHAR(10) NOT NULL,           -- First 10 characters of VIN
    county VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(2) NOT NULL DEFAULT 'WA',
    postal_code VARCHAR(10),
    model_year INTEGER NOT NULL,
    make VARCHAR(50) NOT NULL,                  -- Manufacturer (Tesla, Nissan, etc.)
    model VARCHAR(100) NOT NULL,                -- Model name (Model 3, Leaf, etc.)
    ev_type VARCHAR(50) NOT NULL,               -- Battery Electric Vehicle (BEV) or Plug-in Hybrid (PHEV)
    cafv_eligibility VARCHAR(100),              -- Clean Alternative Fuel Vehicle eligibility
    electric_range INTEGER DEFAULT 0,           -- Electric range in miles
    legislative_district INTEGER,               -- State legislative district
    dol_vehicle_id BIGINT UNIQUE,               -- DOL unique identifier
    vehicle_location VARCHAR(100),              -- POINT coordinates
    longitude DOUBLE,                           -- Extracted longitude
    latitude DOUBLE,                            -- Extracted latitude
    electric_utility VARCHAR(200),              -- Electric utility provider(s)
    census_tract BIGINT,                        -- 2020 Census tract
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_ev_county ON electric_vehicles(county);
CREATE INDEX IF NOT EXISTS idx_ev_city ON electric_vehicles(city);
CREATE INDEX IF NOT EXISTS idx_ev_postal_code ON electric_vehicles(postal_code);
CREATE INDEX IF NOT EXISTS idx_ev_model_year ON electric_vehicles(model_year);
CREATE INDEX IF NOT EXISTS idx_ev_make ON electric_vehicles(make);
CREATE INDEX IF NOT EXISTS idx_ev_model ON electric_vehicles(model);
CREATE INDEX IF NOT EXISTS idx_ev_type ON electric_vehicles(ev_type);
CREATE INDEX IF NOT EXISTS idx_ev_cafv ON electric_vehicles(cafv_eligibility);
CREATE INDEX IF NOT EXISTS idx_ev_range ON electric_vehicles(electric_range);
CREATE INDEX IF NOT EXISTS idx_ev_district ON electric_vehicles(legislative_district);
CREATE INDEX IF NOT EXISTS idx_ev_utility ON electric_vehicles(electric_utility);

-- Useful views for common analyses

-- View: EV Summary by County
CREATE VIEW IF NOT EXISTS ev_by_county AS
SELECT
    county,
    COUNT(*) as total_vehicles,
    COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev_count,
    COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev_count,
    ROUND(100.0 * COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) / COUNT(*), 2) as bev_percentage,
    AVG(CASE WHEN electric_range > 0 THEN electric_range END) as avg_range,
    COUNT(DISTINCT make) as unique_makes,
    COUNT(DISTINCT model) as unique_models
FROM electric_vehicles
GROUP BY county;

-- View: EV Summary by Make
CREATE VIEW IF NOT EXISTS ev_by_make AS
SELECT
    make,
    COUNT(*) as total_vehicles,
    COUNT(DISTINCT model) as model_count,
    AVG(model_year) as avg_model_year,
    AVG(CASE WHEN electric_range > 0 THEN electric_range END) as avg_range,
    COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev_count,
    COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev_count
FROM electric_vehicles
GROUP BY make;

-- View: EV Adoption Trends by Year
CREATE VIEW IF NOT EXISTS ev_adoption_trends AS
SELECT
    model_year,
    COUNT(*) as total_vehicles,
    COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev_count,
    COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev_count,
    AVG(CASE WHEN electric_range > 0 THEN electric_range END) as avg_range,
    COUNT(DISTINCT make) as unique_makes
FROM electric_vehicles
GROUP BY model_year
ORDER BY model_year;

-- View: Legislative District Analysis
CREATE VIEW IF NOT EXISTS ev_by_district AS
SELECT
    legislative_district,
    COUNT(*) as total_vehicles,
    COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev_count,
    COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev_count,
    COUNT(DISTINCT county) as counties_covered,
    AVG(CASE WHEN electric_range > 0 THEN electric_range END) as avg_range
FROM electric_vehicles
WHERE legislative_district IS NOT NULL
GROUP BY legislative_district;

-- View: Electric Utility Coverage
CREATE VIEW IF NOT EXISTS ev_by_utility AS
SELECT
    electric_utility,
    COUNT(*) as total_vehicles,
    COUNT(DISTINCT county) as counties_served,
    COUNT(DISTINCT city) as cities_served,
    AVG(CASE WHEN electric_range > 0 THEN electric_range END) as avg_range
FROM electric_vehicles
WHERE electric_utility IS NOT NULL
GROUP BY electric_utility;

-- View: CAFV Eligibility Summary
CREATE VIEW IF NOT EXISTS cafv_eligibility_summary AS
SELECT
    cafv_eligibility,
    COUNT(*) as vehicle_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage,
    AVG(CASE WHEN electric_range > 0 THEN electric_range END) as avg_range
FROM electric_vehicles
GROUP BY cafv_eligibility;
