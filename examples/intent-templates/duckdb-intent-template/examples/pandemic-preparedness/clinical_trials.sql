-- Clinical trials for vaccine/therapeutic candidates (synthetic demo data)
CREATE TABLE IF NOT EXISTS clinical_trials (
    trial_id INTEGER PRIMARY KEY,
    candidate_name VARCHAR NOT NULL,
    pathogen_target VARCHAR NOT NULL,
    trial_phase VARCHAR NOT NULL,
    sponsor_organization VARCHAR NOT NULL,
    facility_id INTEGER REFERENCES biomanufacturing_facilities(facility_id),
    start_date DATE NOT NULL,
    status VARCHAR NOT NULL,
    enrollment_count INTEGER NOT NULL,
    country VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trial_pathogen ON clinical_trials(pathogen_target);
CREATE INDEX IF NOT EXISTS idx_trial_phase ON clinical_trials(trial_phase);
CREATE INDEX IF NOT EXISTS idx_trial_status ON clinical_trials(status);
CREATE INDEX IF NOT EXISTS idx_trial_facility ON clinical_trials(facility_id);
