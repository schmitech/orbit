-- Classified Data Management System Database Schema
-- This schema supports a classified data management system with knowledge items and access audit logging

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Create knowledge_item table
CREATE TABLE IF NOT EXISTS knowledge_item (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    classification TEXT NOT NULL CHECK (classification IN (
        'UNCLASSIFIED', 'PROTECTED A', 'PROTECTED B', 'PROTECTED C',
        'CONFIDENTIAL', 'SECRET', 'TOP SECRET', 'NATO SECRET'
    )),
    caveats TEXT,
    compartments TEXT,
    rel_to TEXT,
    pii_present INTEGER NOT NULL DEFAULT 0 CHECK (pii_present IN (0, 1)),
    originator_org TEXT,
    source_uri TEXT,
    source_hash TEXT UNIQUE,
    declass_on DATE,
    retention_until DATE,
    last_reviewed DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create access_audit table
CREATE TABLE IF NOT EXISTS access_audit (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    subject_clearance TEXT NOT NULL CHECK (subject_clearance IN (
        'UNCLASSIFIED', 'PROTECTED A', 'PROTECTED B', 'PROTECTED C',
        'CONFIDENTIAL', 'SECRET', 'TOP SECRET', 'NATO SECRET'
    )),
    subject_attrs_json TEXT,
    decision TEXT NOT NULL CHECK (decision IN ('ALLOW', 'REDACT', 'DENY')),
    redaction_rules TEXT,
    query_text TEXT NOT NULL,
    reason TEXT,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES knowledge_item (item_id) ON DELETE CASCADE
);

-- Create users table for user management
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    clearance_level TEXT NOT NULL CHECK (clearance_level IN (
        'UNCLASSIFIED', 'PROTECTED A', 'PROTECTED B', 'PROTECTED C',
        'CONFIDENTIAL', 'SECRET', 'TOP SECRET', 'NATO SECRET'
    )),
    citizenship TEXT NOT NULL,
    need_to_know TEXT, -- JSON array of compartments/projects
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create compartments table for classification compartments
CREATE TABLE IF NOT EXISTS compartments (
    compartment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    classification_level TEXT NOT NULL CHECK (classification_level IN (
        'UNCLASSIFIED', 'PROTECTED A', 'PROTECTED B', 'PROTECTED C',
        'CONFIDENTIAL', 'SECRET', 'TOP SECRET', 'NATO SECRET'
    )),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create organizations table
CREATE TABLE IF NOT EXISTS organizations (
    org_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    country TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create knowledge_item_compartments junction table (many-to-many)
CREATE TABLE IF NOT EXISTS knowledge_item_compartments (
    item_id INTEGER NOT NULL,
    compartment_id INTEGER NOT NULL,
    PRIMARY KEY (item_id, compartment_id),
    FOREIGN KEY (item_id) REFERENCES knowledge_item (item_id) ON DELETE CASCADE,
    FOREIGN KEY (compartment_id) REFERENCES compartments (compartment_id) ON DELETE CASCADE
);

-- Create user_compartments junction table (many-to-many)
CREATE TABLE IF NOT EXISTS user_compartments (
    user_id TEXT NOT NULL,
    compartment_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, compartment_id),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (compartment_id) REFERENCES compartments (compartment_id) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_knowledge_item_classification ON knowledge_item (classification);
CREATE INDEX IF NOT EXISTS idx_knowledge_item_originator ON knowledge_item (originator_org);
CREATE INDEX IF NOT EXISTS idx_knowledge_item_created_at ON knowledge_item (created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_item_source_hash ON knowledge_item (source_hash);

CREATE INDEX IF NOT EXISTS idx_access_audit_user_id ON access_audit (user_id);
CREATE INDEX IF NOT EXISTS idx_access_audit_item_id ON access_audit (item_id);
CREATE INDEX IF NOT EXISTS idx_access_audit_decision ON access_audit (decision);
CREATE INDEX IF NOT EXISTS idx_access_audit_ts ON access_audit (ts);

CREATE INDEX IF NOT EXISTS idx_users_clearance ON users (clearance_level);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Create triggers for updated_at timestamps
CREATE TRIGGER IF NOT EXISTS update_knowledge_item_timestamp 
    AFTER UPDATE ON knowledge_item
    FOR EACH ROW
    BEGIN
        UPDATE knowledge_item SET updated_at = CURRENT_TIMESTAMP WHERE item_id = NEW.item_id;
    END;

CREATE TRIGGER IF NOT EXISTS update_users_timestamp 
    AFTER UPDATE ON users
    FOR EACH ROW
    BEGIN
        UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE user_id = NEW.user_id;
    END;

-- Insert default data
INSERT OR IGNORE INTO organizations (name, code, description, country) VALUES
    ('Department of Defense', 'DEPT_DEFENSE', 'United States Department of Defense', 'USA'),
    ('Intelligence Agency', 'INTEL_AGENCY', 'Intelligence Agency', 'USA'),
    ('Cyber Command', 'CYBER_COMMAND', 'Cyber Command', 'USA'),
    ('Security Bureau', 'SECURITY_BUREAU', 'Security Bureau', 'USA'),
    ('Homeland Protection', 'HOMELAND_PROTECTION', 'Homeland Protection', 'USA'),
    ('Canadian Intelligence', 'CANADIAN_INTEL', 'Canadian Intelligence', 'CAN'),
    ('Cyber Defense', 'CYBER_DEFENSE', 'Cyber Defense', 'CAN'),
    ('Government Communications', 'GOVT_COMMS', 'Government Communications', 'GBR'),
    ('Domestic Security', 'DOMESTIC_SECURITY', 'Domestic Security', 'GBR'),
    ('Foreign Intelligence', 'FOREIGN_INTEL', 'Foreign Intelligence', 'GBR');

INSERT OR IGNORE INTO compartments (name, description, classification_level) VALUES
    ('COMPARTMENT_A', 'High-level compartment for sensitive operations', 'TOP SECRET'),
    ('COMPARTMENT_B', 'Medium-level compartment for classified projects', 'SECRET'),
    ('COMPARTMENT_C', 'Low-level compartment for protected information', 'CONFIDENTIAL'),
    ('PROJECT_X', 'Special project compartment', 'SECRET'),
    ('PROJECT_Y', 'Another special project compartment', 'TOP SECRET'),
    ('OP_HUSKY', 'Operation Husky compartment', 'SECRET'),
    ('OP_THUNDER', 'Operation Thunder compartment', 'TOP SECRET'),
    ('INTEL_ANALYSIS', 'Intelligence analysis compartment', 'CONFIDENTIAL'),
    ('CYBER_OPS', 'Cybersecurity operations compartment', 'SECRET'),
    ('COUNTER_TERROR', 'Ainti-fraud operations compartment', 'TOP SECRET');

-- Insert sample users
INSERT OR IGNORE INTO users (user_id, username, email, clearance_level, citizenship, need_to_know, is_active) VALUES
    ('john.doe@example.com', 'john.doe', 'john.doe@example.com', 'SECRET', 'USA', '["OP HUSKY", "PROJECT_X"]', 1),
    ('jane.smith@example.com', 'jane.smith', 'jane.smith@example.com', 'CONFIDENTIAL', 'USA', '["INTEL_ANALYSIS"]', 1),
    ('bob.wilson@example.com', 'bob.wilson', 'bob.wilson@example.com', 'TOP SECRET', 'USA', '["OP_THUNDER", "COUNTER_TERROR"]', 1),
    ('alice.johnson@example.com', 'alice.johnson', 'alice.johnson@example.com', 'SECRET', 'CAN', '["PROJECT_Y", "CYBER_OPS"]', 1),
    ('charlie.brown@example.com', 'charlie.brown', 'charlie.brown@example.com', 'CONFIDENTIAL', 'GBR', '["INTEL_ANALYSIS"]', 1);

-- Insert user compartment assignments
INSERT OR IGNORE INTO user_compartments (user_id, compartment_id) VALUES
    ('john.doe@example.com', 6), -- OP_HUSKY
    ('john.doe@example.com', 4), -- PROJECT_X
    ('jane.smith@example.com', 8), -- INTEL_ANALYSIS
    ('bob.wilson@example.com', 7), -- OP_THUNDER
    ('bob.wilson@example.com', 10), -- COUNTER_TERROR
    ('alice.johnson@example.com', 5), -- PROJECT_Y
    ('alice.johnson@example.com', 9), -- CYBER_OPS
    ('charlie.brown@example.com', 8); -- INTEL_ANALYSIS

-- Insert sample knowledge items
INSERT OR IGNORE INTO knowledge_item (title, content, classification, caveats, compartments, rel_to, pii_present, originator_org, source_uri, source_hash, declass_on, retention_until, last_reviewed) VALUES
    ('Operation Husky Intelligence Report', 'Detailed intelligence report on Operation Husky including threat assessments, target analysis, and operational recommendations. This document contains sensitive information about ongoing operations and should be handled with extreme care.', 'SECRET', 'NOFORN', 'OP_HUSKY', 'USA,CAN', 0, 'DEPT_DEFENSE', 'https://intel.example.com/op-husky-report.pdf', 'sha256:abc123def456', '2030-12-31', '2035-12-31', '2024-01-15'),
    ('Project X Technical Specifications', 'Technical specifications and implementation details for Project X. Contains proprietary technology information and system architecture details that are critical to national security.', 'TOP SECRET', 'ORCON', 'PROJECT_X', 'USA', 0, 'CYBER_COMMAND', 'https://tech.example.com/project-x-specs.pdf', 'sha256:def456ghi789', '2040-12-31', '2045-12-31', '2024-01-10'),
    ('Ainti-fraud Threat Assessment', 'Comprehensive threat assessment report covering current terrorist activities, threat levels, and recommended countermeasures. Contains information about ongoing investigations.', 'TOP SECRET', 'NOFORN,ORCON', 'COUNTER_TERROR', 'USA,GBR,CAN', 1, 'SECURITY_BUREAU', 'https://ct.example.com/threat-assessment.pdf', 'sha256:ghi789jkl012', '2025-12-31', '2030-12-31', '2024-01-20'),
    ('Intelligence Analysis Summary', 'Monthly intelligence analysis summary covering global security trends, emerging threats, and strategic recommendations. Contains unclassified and confidential information.', 'CONFIDENTIAL', NULL, 'INTEL_ANALYSIS', 'USA,CAN,GBR', 0, 'INTEL_AGENCY', 'https://analysis.example.com/monthly-summary.pdf', 'sha256:jkl012mno345', '2025-06-30', '2026-06-30', '2024-01-05'),
    ('Cybersecurity Operations Manual', 'Detailed manual for cybersecurity operations including protocols, procedures, and best practices. Contains sensitive information about defensive capabilities.', 'SECRET', 'ORCON', 'CYBER_OPS', 'USA,CAN', 0, 'CYBER_COMMAND', 'https://cyber.example.com/ops-manual.pdf', 'sha256:mno345pqr678', '2030-12-31', '2035-12-31', '2024-01-12');

-- Insert sample access audit entries
INSERT OR IGNORE INTO access_audit (item_id, user_id, subject_clearance, subject_attrs_json, decision, query_text, reason, ts) VALUES
    (1, 'john.doe@example.com', 'SECRET', '{"citizenship":"USA","need_to_know":["OP HUSKY"]}', 'ALLOW', 'search for operation husky documents', 'User has appropriate clearance and need-to-know', '2024-01-15 10:30:00'),
    (2, 'jane.smith@example.com', 'CONFIDENTIAL', '{"citizenship":"USA","need_to_know":["INTEL_ANALYSIS"]}', 'DENY', 'search for project x technical details', 'Insufficient clearance level for TOP SECRET document', '2024-01-15 11:15:00'),
    (3, 'bob.wilson@example.com', 'TOP SECRET', '{"citizenship":"USA","need_to_know":["OP_THUNDER","COUNTER_TERROR"]}', 'ALLOW', 'search for Ainti-fraud reports', 'User has appropriate clearance and need-to-know', '2024-01-15 14:20:00'),
    (4, 'alice.johnson@example.com', 'SECRET', '{"citizenship":"CAN","need_to_know":["PROJECT_Y","CYBER_OPS"]}', 'REDACT', 'search for intelligence analysis', 'Document contains information outside user compartment', '2024-01-15 15:45:00'),
    (5, 'charlie.brown@example.com', 'CONFIDENTIAL', '{"citizenship":"GBR","need_to_know":["INTEL_ANALYSIS"]}', 'ALLOW', 'search for cybersecurity information', 'User has appropriate clearance for document', '2024-01-15 16:30:00');

-- Create views for common queries
CREATE VIEW IF NOT EXISTS knowledge_item_summary AS
SELECT 
    ki.item_id,
    ki.title,
    ki.classification,
    ki.caveats,
    ki.compartments,
    ki.pii_present,
    ki.originator_org,
    o.name as org_name,
    ki.created_at,
    ki.updated_at
FROM knowledge_item ki
LEFT JOIN organizations o ON ki.originator_org = o.code;

CREATE VIEW IF NOT EXISTS access_audit_summary AS
SELECT 
    aa.event_id,
    aa.item_id,
    ki.title as item_title,
    aa.user_id,
    u.username,
    aa.subject_clearance,
    aa.decision,
    aa.query_text,
    aa.reason,
    aa.ts
FROM access_audit aa
LEFT JOIN knowledge_item ki ON aa.item_id = ki.item_id
LEFT JOIN users u ON aa.user_id = u.user_id;

-- Create a function to check user access to knowledge items
-- This would be implemented in the application layer, but the schema supports it
