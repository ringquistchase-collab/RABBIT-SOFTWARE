-- Sensor ingest v2: API-key auth, blockchain hash, alerts
-- Replaces the previous sensor_readings schema with richer fields

-- ─────────────────────────────────────────────────────────────────────────────
-- sensors: one row per physical node (API key = auth token for ingest)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sensors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES twin_identity(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    api_key         TEXT NOT NULL UNIQUE,
    sensor_type     TEXT NOT NULL,              -- 'rf', 'eeg', 'uwb', 'gsr', etc.
    node_id         SMALLINT REFERENCES mesh_nodes(id),
    last_reading    TIMESTAMPTZ,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX sensors_user_idx ON sensors (user_id, active);
CREATE INDEX sensors_node_idx ON sensors (node_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- sensor_readings: ingest readings from mesh nodes via API key
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sensor_readings (
    id              BIGSERIAL PRIMARY KEY,
    sensor_id       UUID NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    value           REAL NOT NULL,
    unit            TEXT NOT NULL,
    signal_quality  REAL,
    frequency       REAL,                       -- Hz
    bandwidth       REAL,                       -- Hz
    signal_type     TEXT,
    raw_data        JSONB NOT NULL DEFAULT '{}',
    blockchain_hash TEXT,                       -- generateBlockchainHash output
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX sensor_readings_sensor_idx ON sensor_readings (sensor_id, created_at DESC);
CREATE INDEX sensor_readings_type_idx   ON sensor_readings (signal_type, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- sensor_alerts: triggered when ingest payload includes alert field
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TYPE alert_severity AS ENUM ('info', 'warning', 'critical');

CREATE TABLE IF NOT EXISTS sensor_alerts (
    id              BIGSERIAL PRIMARY KEY,
    sensor_id       UUID NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    reading_id      BIGINT REFERENCES sensor_readings(id),
    alert_type      TEXT NOT NULL,
    message         TEXT NOT NULL,
    severity        alert_severity NOT NULL DEFAULT 'info',
    blockchain_hash TEXT,
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX sensor_alerts_sensor_idx   ON sensor_alerts (sensor_id, created_at DESC);
CREATE INDEX sensor_alerts_sev_idx      ON sensor_alerts (severity, acknowledged)
    WHERE acknowledged = FALSE;

-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW: latest reading per sensor
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW sensor_latest AS
SELECT DISTINCT ON (r.sensor_id)
    r.sensor_id,
    s.name,
    s.sensor_type,
    s.node_id,
    r.value,
    r.unit,
    r.signal_quality,
    r.frequency,
    r.signal_type,
    r.blockchain_hash,
    r.created_at AS last_reading_at
FROM sensor_readings r
JOIN sensors s ON s.id = r.sensor_id
ORDER BY r.sensor_id, r.created_at DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: one sensor per key mesh node for Chase's twin
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO sensors (user_id, name, api_key, sensor_type, node_id) VALUES
(
    'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    'HEAD_01_EEG',
    encode(sha256('rabbitos_head01_eeg_seed'), 'hex'),
    'eeg', 1
),
(
    'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    'CHEST_01_HRV',
    encode(sha256('rabbitos_chest01_hrv_seed'), 'hex'),
    'hrv', 9
),
(
    'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    'WRIST_L_GSR',
    encode(sha256('rabbitos_wristl_gsr_seed'), 'hex'),
    'gsr', 20
),
(
    'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    'UWB_RADAR_01',
    encode(sha256('rabbitos_uwb01_seed'), 'hex'),
    'uwb', 27
);

-- RLS
ALTER TABLE sensors         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensor_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensor_alerts   ENABLE ROW LEVEL SECURITY;

CREATE POLICY sensors_owner         ON sensors         FOR ALL USING (user_id = auth.uid()::UUID);
CREATE POLICY sensor_readings_owner ON sensor_readings FOR ALL
    USING (sensor_id IN (SELECT id FROM sensors WHERE user_id = auth.uid()::UUID));
CREATE POLICY sensor_alerts_owner   ON sensor_alerts   FOR ALL
    USING (sensor_id IN (SELECT id FROM sensors WHERE user_id = auth.uid()::UUID));
