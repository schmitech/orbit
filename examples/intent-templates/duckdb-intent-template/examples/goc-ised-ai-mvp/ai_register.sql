-- Government of Canada AI Register (MVP) Database Schema for DuckDB
-- Source: Innovation, Science and Economic Development Canada (ISED)
-- Government of Canada Artificial Intelligence Register (Minimum Viable Product)
-- Tracks AI systems deployed across federal government institutions
-- Bilingual content: English (_en) and French (_fr) fields

-- Create ai_register table
CREATE TABLE IF NOT EXISTS ai_register (
    ai_register_id VARCHAR PRIMARY KEY,
    name_ai_system_en VARCHAR,
    name_ai_system_fr VARCHAR,
    government_organization VARCHAR,
    description_ai_system_en VARCHAR,
    description_ai_system_fr VARCHAR,
    ai_system_primary_users_en VARCHAR,
    ai_system_primary_users_fr VARCHAR,
    developed_by_en VARCHAR,
    developed_by_fr VARCHAR,
    vendor_information VARCHAR,
    ai_system_status_en VARCHAR,
    ai_system_status_fr VARCHAR,
    status_date INTEGER,
    ai_system_capabilities_en VARCHAR,
    ai_system_capabilities_fr VARCHAR,
    data_sources_en VARCHAR,
    data_sources_fr VARCHAR,
    involves_personal_information VARCHAR,
    personal_information_banks_en VARCHAR,
    personal_information_banks_fr VARCHAR,
    notification_ai VARCHAR,
    ai_system_results_en VARCHAR,
    ai_system_results_fr VARCHAR
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_ai_register_org ON ai_register(government_organization);
CREATE INDEX IF NOT EXISTS idx_ai_register_status_en ON ai_register(ai_system_status_en);
CREATE INDEX IF NOT EXISTS idx_ai_register_developed_by ON ai_register(developed_by_en);
CREATE INDEX IF NOT EXISTS idx_ai_register_status_date ON ai_register(status_date);
CREATE INDEX IF NOT EXISTS idx_ai_register_personal_info ON ai_register(involves_personal_information);
CREATE INDEX IF NOT EXISTS idx_ai_register_notification ON ai_register(notification_ai);
CREATE INDEX IF NOT EXISTS idx_ai_register_vendor ON ai_register(vendor_information);

