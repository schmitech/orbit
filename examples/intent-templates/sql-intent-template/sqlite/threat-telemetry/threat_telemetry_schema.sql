-- Sensor/Threat Telemetry Database Schema
-- Simulated perimeter/ISR sensor network: sensors report detections,
-- and detections above a severity threshold raise alerts.

PRAGMA foreign_keys = ON;

-- ============================================================================
-- SENSORS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,                -- radar, perimeter, drone, acoustic
    location_name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    status TEXT DEFAULT 'online'       -- online, offline, degraded
);

-- ============================================================================
-- DETECTIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS detections (
    detection_id TEXT PRIMARY KEY,
    sensor_id TEXT NOT NULL,
    detected_at DATETIME NOT NULL,
    object_type TEXT NOT NULL,         -- aircraft, vehicle, person, unknown
    confidence REAL NOT NULL,          -- 0.0 - 1.0
    severity TEXT NOT NULL,            -- low, medium, high, critical
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    notes TEXT,
    FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id)
);

-- ============================================================================
-- ALERTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    detection_id TEXT NOT NULL,
    raised_at DATETIME NOT NULL,
    status TEXT DEFAULT 'open',        -- open, acknowledged, resolved
    assigned_to TEXT,
    FOREIGN KEY (detection_id) REFERENCES detections(detection_id)
);

-- ============================================================================
-- INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_detections_sensor ON detections(sensor_id);
CREATE INDEX IF NOT EXISTS idx_detections_detected_at ON detections(detected_at);
CREATE INDEX IF NOT EXISTS idx_detections_severity ON detections(severity);
CREATE INDEX IF NOT EXISTS idx_detections_object_type ON detections(object_type);
CREATE INDEX IF NOT EXISTS idx_alerts_detection ON alerts(detection_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_assigned_to ON alerts(assigned_to);
