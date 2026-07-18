-- ============================================================
-- RABBIT-SOFTWARE v0.32.1 — 26-Node Biometric Mesh + Digital Twin
-- ============================================================
-- Adds: twin_identity, mesh_nodes (26 seeded), mesh_topology (edges),
--       life_age_events, mesh_frozen_snapshots, frozen_node_states,
--       mesh_node_readings, mesh_edge_weights, mesh_anomalies
-- Frozen snapshots use the same SHA-256 chain pattern as audit_log.
-- ============================================================

-- ── Enums ────────────────────────────────────────────────────
CREATE TYPE node_modality    AS ENUM ('eeg', 'biometric');
CREATE TYPE eeg_band         AS ENUM ('delta', 'theta', 'alpha', 'beta', 'gamma');
CREATE TYPE life_event_type  AS ENUM (
  'BIRTH', 'DEVELOPMENTAL_MILESTONE', 'TRAUMA', 'RECOVERY',
  'PEAK_STATE', 'BASELINE_CALIBRATION', 'USER_DEFINED'
);
CREATE TYPE anomaly_level AS ENUM ('INFO', 'WARNING', 'CRITICAL');

-- ── 1. TWIN IDENTITY ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS twin_identity (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_name     TEXT         NOT NULL,
  subject_dob      DATE         NOT NULL,
  -- SHA-256(subject_name || subject_dob || first_frozen_snapshot.chain_hash)
  biological_hash  TEXT,
  is_sealed        BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  sealed_at        TIMESTAMPTZ
);

-- ── 2. MESH NODES (26 rows, static seed) ─────────────────────
CREATE TABLE IF NOT EXISTS mesh_nodes (
  id           SMALLINT      PRIMARY KEY,           -- 1-26
  node_code    TEXT          NOT NULL UNIQUE,        -- 'Fp1', 'GSR', …
  modality     node_modality NOT NULL,
  lobe_region  TEXT,                                 -- 'frontal' | 'temporal' | … | 'biometric'
  x_pos        REAL,                                 -- normalised sphere coords (−1 to 1)
  y_pos        REAL,
  z_pos        REAL,
  description  TEXT
);

INSERT INTO mesh_nodes (id, node_code, modality, lobe_region, x_pos, y_pos, z_pos, description) VALUES
-- EEG — 19 standard 10-20 positions
(1,  'Fp1',  'eeg', 'frontal',    -0.31,  0.87,  0.28, 'Frontal Polar Left'),
(2,  'Fp2',  'eeg', 'frontal',     0.31,  0.87,  0.28, 'Frontal Polar Right'),
(3,  'F7',   'eeg', 'frontal',    -0.72,  0.55,  0.09, 'Frontal Left'),
(4,  'F3',   'eeg', 'frontal',    -0.39,  0.67,  0.61, 'Frontal Left Central'),
(5,  'Fz',   'eeg', 'frontal',     0.00,  0.71,  0.71, 'Frontal Midline'),
(6,  'F4',   'eeg', 'frontal',     0.39,  0.67,  0.61, 'Frontal Right Central'),
(7,  'F8',   'eeg', 'frontal',     0.72,  0.55,  0.09, 'Frontal Right'),
(8,  'T3',   'eeg', 'temporal',   -0.95,  0.00,  0.00, 'Temporal Left'),
(9,  'C3',   'eeg', 'central',    -0.50,  0.00,  0.87, 'Central Left'),
(10, 'Cz',   'eeg', 'central',     0.00,  0.00,  1.00, 'Vertex / Central Midline'),
(11, 'C4',   'eeg', 'central',     0.50,  0.00,  0.87, 'Central Right'),
(12, 'T4',   'eeg', 'temporal',    0.95,  0.00,  0.00, 'Temporal Right'),
(13, 'T5',   'eeg', 'temporal',   -0.72, -0.55,  0.09, 'Posterior Temporal Left'),
(14, 'P3',   'eeg', 'parietal',   -0.39, -0.67,  0.61, 'Parietal Left'),
(15, 'Pz',   'eeg', 'parietal',    0.00, -0.71,  0.71, 'Parietal Midline'),
(16, 'P4',   'eeg', 'parietal',    0.39, -0.67,  0.61, 'Parietal Right'),
(17, 'T6',   'eeg', 'temporal',    0.72, -0.55,  0.09, 'Posterior Temporal Right'),
(18, 'O1',   'eeg', 'occipital',  -0.31, -0.87,  0.28, 'Occipital Left'),
(19, 'O2',   'eeg', 'occipital',   0.31, -0.87,  0.28, 'Occipital Right'),
-- Biometric — 7 peripheral nodes
(20, 'GSR',  'biometric', 'biometric',  0.00,  0.00, -1.00, 'Galvanic Skin Response'),
(21, 'HRV',  'biometric', 'biometric',  0.10,  0.00, -0.95, 'Heart Rate Variability'),
(22, 'TEMP', 'biometric', 'biometric', -0.10,  0.00, -0.95, 'Core Body Temperature'),
(23, 'SPO2', 'biometric', 'biometric',  0.00,  0.10, -0.95, 'Blood Oxygen Saturation'),
(24, 'RESP', 'biometric', 'biometric',  0.00, -0.10, -0.95, 'Respiration Rate'),
(25, 'ACC',  'biometric', 'biometric',  0.15,  0.10, -0.90, 'Accelerometer / Movement'),
(26, 'EOG',  'biometric', 'biometric', -0.15,  0.10, -0.90, 'Electrooculography / Eye Movement')
ON CONFLICT (id) DO NOTHING;

-- ── 3. MESH TOPOLOGY (static edge catalogue) ─────────────────
-- edge_type: 'cortical_adjacent' | 'cortical_long_range' | 'cross_modal'
CREATE TABLE IF NOT EXISTS mesh_topology (
  id           SERIAL   PRIMARY KEY,
  node_a       SMALLINT NOT NULL REFERENCES mesh_nodes(id),
  node_b       SMALLINT NOT NULL REFERENCES mesh_nodes(id),
  edge_type    TEXT     NOT NULL,
  base_weight  REAL     NOT NULL DEFAULT 1.0,
  CHECK (node_a < node_b)
);

INSERT INTO mesh_topology (node_a, node_b, edge_type, base_weight) VALUES
-- Frontal adjacencies
(1,2,'cortical_adjacent',1.0),(1,3,'cortical_adjacent',0.9),(1,4,'cortical_adjacent',0.8),
(2,6,'cortical_adjacent',0.8),(2,7,'cortical_adjacent',0.9),
(3,4,'cortical_adjacent',1.0),(3,8,'cortical_adjacent',0.8),
(4,5,'cortical_adjacent',1.0),(4,9,'cortical_adjacent',0.7),
(5,6,'cortical_adjacent',1.0),(5,10,'cortical_adjacent',0.8),
(6,7,'cortical_adjacent',1.0),(6,11,'cortical_adjacent',0.7),
(7,12,'cortical_adjacent',0.8),
-- Temporal-central
(8,9,'cortical_adjacent',1.0),(8,13,'cortical_adjacent',0.9),
(9,10,'cortical_adjacent',1.0),(9,14,'cortical_adjacent',0.8),
(10,11,'cortical_adjacent',1.0),(10,15,'cortical_adjacent',0.8),
(11,12,'cortical_adjacent',1.0),(11,16,'cortical_adjacent',0.8),
(12,17,'cortical_adjacent',0.9),
-- Parietal-occipital
(13,14,'cortical_adjacent',0.9),(13,18,'cortical_adjacent',0.9),
(14,15,'cortical_adjacent',1.0),(14,18,'cortical_adjacent',0.7),
(15,16,'cortical_adjacent',1.0),(15,19,'cortical_adjacent',0.7),
(16,17,'cortical_adjacent',0.9),(16,19,'cortical_adjacent',0.7),
(17,19,'cortical_adjacent',0.9),
(18,19,'cortical_adjacent',1.0),
-- Long-range cortical (frontal–parietal / frontal–occipital networks)
(1,14,'cortical_long_range',0.5),(2,16,'cortical_long_range',0.5),
(5,15,'cortical_long_range',0.7),(4,9,'cortical_long_range',0.6),
(6,11,'cortical_long_range',0.6),
-- Cross-modal: biometric ↔ EEG hubs
(5,20,'cross_modal',0.6),(5,21,'cross_modal',0.5),
(10,20,'cross_modal',0.5),(10,24,'cross_modal',0.4),
(15,23,'cross_modal',0.4),
(8,26,'cross_modal',0.5),(12,26,'cross_modal',0.5),
-- Biometric inter-node
(20,21,'cross_modal',0.8),(20,22,'cross_modal',0.7),
(21,23,'cross_modal',0.8),(21,24,'cross_modal',0.7),
(22,23,'cross_modal',0.6),(24,25,'cross_modal',0.7),
(25,26,'cross_modal',0.5)
ON CONFLICT DO NOTHING;

-- ── 4. LIFE AGE EVENTS ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS life_age_events (
  id                BIGSERIAL       PRIMARY KEY,
  twin_id           UUID            NOT NULL REFERENCES twin_identity(id),
  event_type        life_event_type NOT NULL,
  event_date        DATE            NOT NULL,
  age_years         REAL,           -- (event_date − subject_dob) / 365.25, set by trigger
  label             TEXT            NOT NULL,
  description       TEXT,
  is_sealed         BOOLEAN         NOT NULL DEFAULT FALSE,
  mesh_snapshot_id  BIGINT,         -- FK added after mesh_frozen_snapshots is created
  created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
  sealed_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS lae_twin_idx  ON life_age_events (twin_id);
CREATE INDEX IF NOT EXISTS lae_date_idx  ON life_age_events (event_date);
CREATE INDEX IF NOT EXISTS lae_type_idx  ON life_age_events (event_type);

-- ── 5. FROZEN MESH SNAPSHOTS ─────────────────────────────────
-- Same SHA-256 chain pattern as audit_log — prev_hash + snapshot_hash → chain_hash.
-- Once is_sealed = TRUE the row must not be updated (enforced by trigger below).
CREATE TABLE IF NOT EXISTS mesh_frozen_snapshots (
  id              BIGSERIAL    PRIMARY KEY,
  twin_id         UUID         NOT NULL REFERENCES twin_identity(id),
  life_event_id   BIGINT       REFERENCES life_age_events(id),
  label           TEXT         NOT NULL,
  captured_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  node_count      SMALLINT     NOT NULL DEFAULT 26,
  snapshot_hash   TEXT,        -- SHA-256 of all frozen_node_states for this snapshot
  prev_hash       TEXT,        -- chain_hash of previous snapshot ('0'*64 for first)
  chain_hash      TEXT,        -- SHA-256(prev_hash || snapshot_hash)
  is_sealed       BOOLEAN      NOT NULL DEFAULT FALSE,
  sealed_at       TIMESTAMPTZ,
  metadata        JSONB
);

CREATE INDEX IF NOT EXISTS mfs_twin_idx ON mesh_frozen_snapshots (twin_id);
CREATE INDEX IF NOT EXISTS mfs_ts_idx   ON mesh_frozen_snapshots (captured_at DESC);

-- Prevent mutations to sealed snapshots
CREATE OR REPLACE FUNCTION prevent_sealed_snapshot_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.is_sealed THEN
    RAISE EXCEPTION 'Cannot modify sealed snapshot id=%', OLD.id;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_no_mutate_sealed_snapshot
  BEFORE UPDATE ON mesh_frozen_snapshots
  FOR EACH ROW EXECUTE FUNCTION prevent_sealed_snapshot_mutation();

-- Back-link life_age_events → snapshots
ALTER TABLE life_age_events
  ADD CONSTRAINT fk_lae_snapshot
  FOREIGN KEY (mesh_snapshot_id) REFERENCES mesh_frozen_snapshots(id);

-- ── 6. FROZEN NODE STATES (26 rows per snapshot) ─────────────
CREATE TABLE IF NOT EXISTS frozen_node_states (
  id               BIGSERIAL    PRIMARY KEY,
  snapshot_id      BIGINT       NOT NULL REFERENCES mesh_frozen_snapshots(id),
  node_id          SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  -- EEG band power (µV²/Hz) — NULL for biometric nodes
  delta_power      REAL,
  theta_power      REAL,
  alpha_power      REAL,
  beta_power       REAL,
  gamma_power      REAL,
  dominant_band    eeg_band,
  mean_amplitude   REAL,        -- µV (EEG) or native unit (biometric)
  std_amplitude    REAL,
  -- Biometric scalar — NULL for EEG nodes
  biometric_value  REAL,
  biometric_unit   TEXT,        -- 'µS' | 'ms' | '°C' | '%' | 'bpm' | 'm/s²' | 'px'
  -- Per-node coherence to all adjacent nodes at snapshot time
  coherence_map    JSONB,       -- { "<node_id>": <0-1>, … }
  UNIQUE (snapshot_id, node_id)
);

CREATE INDEX IF NOT EXISTS fns_snapshot_idx ON frozen_node_states (snapshot_id);
CREATE INDEX IF NOT EXISTS fns_node_idx     ON frozen_node_states (node_id);

-- ── 7. LIVE MESH NODE READINGS (time-series) ─────────────────
-- Coexists with sensor_readings; mesh-aware ingest writes here.
CREATE TABLE IF NOT EXISTS mesh_node_readings (
  id                    BIGSERIAL    PRIMARY KEY,
  twin_id               UUID         NOT NULL REFERENCES twin_identity(id),
  node_id               SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  sensor_id             TEXT         NOT NULL,
  timestamp             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  -- EEG fields (NULL for biometric nodes)
  band                  eeg_band,
  amplitude_uv          REAL,
  phase_deg             REAL,
  band_powers           JSONB,       -- { delta, theta, alpha, beta, gamma }
  -- Biometric scalar (NULL for EEG nodes)
  raw_value             REAL,
  -- Deviation from baseline frozen snapshot
  baseline_snapshot_id  BIGINT       REFERENCES mesh_frozen_snapshots(id),
  deviation_z           REAL         -- (live − frozen_mean) / frozen_std
);

CREATE INDEX IF NOT EXISTS mnr_twin_ts_idx ON mesh_node_readings (twin_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS mnr_node_ts_idx ON mesh_node_readings (node_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS mnr_ts_idx      ON mesh_node_readings (timestamp DESC);

-- ── 8. LIVE EDGE WEIGHTS (coherence time-series) ─────────────
CREATE TABLE IF NOT EXISTS mesh_edge_weights (
  id            BIGSERIAL    PRIMARY KEY,
  twin_id       UUID         NOT NULL REFERENCES twin_identity(id),
  node_a        SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  node_b        SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  timestamp     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  coherence     REAL         NOT NULL CHECK (coherence BETWEEN 0 AND 1),
  phase_lag_ms  REAL,
  CHECK (node_a < node_b)
);

CREATE INDEX IF NOT EXISTS mew_twin_ts_idx ON mesh_edge_weights (twin_id, timestamp DESC);

-- ── 9. MESH ANOMALIES (anti-hijacking / identity deviation) ──
-- anomaly_type: 'TOPOLOGY_SHIFT' | 'IDENTITY_DEVIATION' | 'PATTERN_INJECTION' | 'COHERENCE_BREAK'
CREATE TABLE IF NOT EXISTS mesh_anomalies (
  id                    BIGSERIAL     PRIMARY KEY,
  twin_id               UUID          NOT NULL REFERENCES twin_identity(id),
  detected_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  anomaly_type          TEXT          NOT NULL,
  affected_nodes        SMALLINT[]    NOT NULL,
  deviation_score       REAL          NOT NULL,
  alert_level           anomaly_level NOT NULL DEFAULT 'WARNING',
  baseline_snapshot_id  BIGINT        REFERENCES mesh_frozen_snapshots(id),
  resolved              BOOLEAN       NOT NULL DEFAULT FALSE,
  resolved_at           TIMESTAMPTZ,
  metadata              JSONB
);

CREATE INDEX IF NOT EXISTS ma_twin_ts_idx    ON mesh_anomalies (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS ma_open_idx       ON mesh_anomalies (alert_level) WHERE NOT resolved;

-- ── RPC: get_mesh_deviation ───────────────────────────────────
-- Compares live readings (last N minutes) against a frozen snapshot.
-- Returns per-node z-score; consumer decides alert threshold.
CREATE OR REPLACE FUNCTION get_mesh_deviation(
  p_twin_id     UUID,
  p_snapshot_id BIGINT,
  p_window_min  INT DEFAULT 5
)
RETURNS TABLE (
  node_id       smallint,
  node_code     text,
  modality      node_modality,
  frozen_mean   real,
  live_mean     real,
  deviation_z   real,
  alert_level   text
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
  WITH frozen AS (
    SELECT fns.node_id,
           fns.mean_amplitude AS frozen_mean,
           fns.std_amplitude  AS frozen_std
    FROM   frozen_node_states fns
    WHERE  fns.snapshot_id = p_snapshot_id
  ),
  live AS (
    SELECT r.node_id,
           AVG(COALESCE(r.amplitude_uv, r.raw_value))::real AS live_mean
    FROM   mesh_node_readings r
    WHERE  r.twin_id   = p_twin_id
      AND  r.timestamp >= NOW() - (p_window_min || ' minutes')::INTERVAL
    GROUP  BY r.node_id
  )
  SELECT
    mn.id,
    mn.node_code,
    mn.modality,
    f.frozen_mean,
    l.live_mean,
    CASE WHEN COALESCE(f.frozen_std, 0) > 0
         THEN ((l.live_mean - f.frozen_mean) / f.frozen_std)::real
         ELSE 0.0
    END AS deviation_z,
    CASE
      WHEN ABS(COALESCE((l.live_mean - f.frozen_mean) / NULLIF(f.frozen_std,0), 0)) > 3.0 THEN 'CRITICAL'
      WHEN ABS(COALESCE((l.live_mean - f.frozen_mean) / NULLIF(f.frozen_std,0), 0)) > 2.0 THEN 'WARNING'
      ELSE 'INFO'
    END AS alert_level
  FROM  mesh_nodes mn
  LEFT  JOIN frozen f ON f.node_id = mn.id
  LEFT  JOIN live   l ON l.node_id = mn.id
  ORDER BY mn.id;
END;
$$;
