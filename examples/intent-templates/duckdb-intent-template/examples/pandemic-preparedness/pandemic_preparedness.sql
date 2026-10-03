-- Canadian Pandemic Preparedness Demo Database for DuckDB
-- Synthetic data illustrating biomanufacturing capacity and clinical trial
-- readiness, built for a demo with the Canadian Pandemic Preparedness Hub
-- (CP2H, University of Ottawa / McMaster University). All data is synthetic.
--
-- Reference copy only: the loader reads biomanufacturing_facilities.sql and
-- clinical_trials.sql separately (see README.md), since csv_to_duckdb.py
-- expects one CREATE TABLE per schema file.

-- Biomanufacturing facilities: vaccine/therapeutic production capacity
CREATE TABLE IF NOT EXISTS biomanufacturing_facilities (
    facility_id INTEGER PRIMARY KEY,
    facility_name VARCHAR NOT NULL,
    organization VARCHAR NOT NULL,
    province VARCHAR(2) NOT NULL,
    city VARCHAR NOT NULL,
    facility_type VARCHAR NOT NULL,          -- vaccine, viral_vector, cell_therapy, antibody, mRNA
    capacity_liters INTEGER NOT NULL,
    status VARCHAR NOT NULL,                 -- operational, under_construction, planned
    gmp_certified BOOLEAN NOT NULL,
    commissioned_year INTEGER,
    partner_network VARCHAR                  -- CP2H, BioCanRx, Canadian Immunization Research Network, independent
);

CREATE INDEX IF NOT EXISTS idx_fac_province ON biomanufacturing_facilities(province);
CREATE INDEX IF NOT EXISTS idx_fac_type ON biomanufacturing_facilities(facility_type);
CREATE INDEX IF NOT EXISTS idx_fac_status ON biomanufacturing_facilities(status);
CREATE INDEX IF NOT EXISTS idx_fac_gmp ON biomanufacturing_facilities(gmp_certified);
CREATE INDEX IF NOT EXISTS idx_fac_partner ON biomanufacturing_facilities(partner_network);

-- Clinical trials for vaccine/therapeutic candidates
CREATE TABLE IF NOT EXISTS clinical_trials (
    trial_id INTEGER PRIMARY KEY,
    candidate_name VARCHAR NOT NULL,
    pathogen_target VARCHAR NOT NULL,        -- influenza, coronavirus, RSV, mpox, norovirus, H5N1 avian influenza
    trial_phase VARCHAR NOT NULL,            -- Preclinical, Phase I, Phase II, Phase III, Approved
    sponsor_organization VARCHAR NOT NULL,
    facility_id INTEGER REFERENCES biomanufacturing_facilities(facility_id),
    start_date DATE NOT NULL,
    status VARCHAR NOT NULL,                 -- active, completed, paused, terminated
    enrollment_count INTEGER NOT NULL,
    country VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trial_pathogen ON clinical_trials(pathogen_target);
CREATE INDEX IF NOT EXISTS idx_trial_phase ON clinical_trials(trial_phase);
CREATE INDEX IF NOT EXISTS idx_trial_status ON clinical_trials(status);
CREATE INDEX IF NOT EXISTS idx_trial_facility ON clinical_trials(facility_id);
