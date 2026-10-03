-- Biomanufacturing facilities: vaccine/therapeutic production capacity (synthetic demo data)
CREATE TABLE IF NOT EXISTS biomanufacturing_facilities (
    facility_id INTEGER PRIMARY KEY,
    facility_name VARCHAR NOT NULL,
    organization VARCHAR NOT NULL,
    province VARCHAR(2) NOT NULL,
    city VARCHAR NOT NULL,
    facility_type VARCHAR NOT NULL,
    capacity_liters INTEGER NOT NULL,
    status VARCHAR NOT NULL,
    gmp_certified BOOLEAN NOT NULL,
    commissioned_year INTEGER,
    partner_network VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_fac_province ON biomanufacturing_facilities(province);
CREATE INDEX IF NOT EXISTS idx_fac_type ON biomanufacturing_facilities(facility_type);
CREATE INDEX IF NOT EXISTS idx_fac_status ON biomanufacturing_facilities(status);
CREATE INDEX IF NOT EXISTS idx_fac_gmp ON biomanufacturing_facilities(gmp_certified);
CREATE INDEX IF NOT EXISTS idx_fac_partner ON biomanufacturing_facilities(partner_network);
