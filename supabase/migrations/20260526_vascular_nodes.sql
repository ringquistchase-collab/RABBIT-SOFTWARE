-- ============================================================
-- RABBIT-SOFTWARE v0.32.1 — RF Vascular Node Extension
-- ============================================================
-- Extends the mesh with 6 RF vascular junction nodes (IDs 27-32),
-- vascular-specific columns on mesh_node_readings + frozen_node_states,
-- and a vascular_pulse_events table for cross-node PWV calculation.
-- ============================================================

-- ── New enum values ───────────────────────────────────────────
ALTER TYPE node_modality ADD VALUE IF NOT EXISTS 'vascular';

CREATE TYPE vasc_state AS ENUM (
  'BASELINE',
  'VASODILATION',
  'VASOCONSTRICTION',
  'TACHYCARDIA',
  'BRADYCARDIA',
  'ARRHYTHMIA'
);

-- ── Vascular nodes (27-32) ────────────────────────────────────
-- Placed at major arterial junctions; co-located with existing nodes
-- for cross-modal validation (e.g. CAROT_L near T3 for EEG coherence).
INSERT INTO mesh_nodes (id, node_code, modality, lobe_region, x_pos, y_pos, z_pos, description) VALUES
(27, 'CAROT_L',  'vascular', 'cervical',    -0.15,  0.55, -0.05, 'Left Carotid Artery'),
(28, 'CAROT_R',  'vascular', 'cervical',     0.15,  0.55, -0.05, 'Right Carotid Artery'),
(29, 'RADIAL_L', 'vascular', 'upper_limb',  -0.85, -0.20, -0.45, 'Left Radial Artery / Wrist'),
(30, 'RADIAL_R', 'vascular', 'upper_limb',   0.85, -0.20, -0.45, 'Right Radial Artery / Wrist'),
(31, 'FEMORAL_L','vascular', 'lower_limb',  -0.25, -0.95, -0.60, 'Left Femoral Artery'),
(32, 'FEMORAL_R','vascular', 'lower_limb',   0.25, -0.95, -0.60, 'Right Femoral Artery')
ON CONFLICT (id) DO NOTHING;

-- ── Inter-node distance on topology (used for PWV = distance/transit_time) ──
ALTER TABLE mesh_topology
  ADD COLUMN IF NOT EXISTS distance_cm REAL;    -- anatomical path length between junctions

-- ── Vascular topology edges ───────────────────────────────────
-- distance_cm values are median anatomical estimates; calibrate per subject.
INSERT INTO mesh_topology (node_a, node_b, edge_type, base_weight, distance_cm) VALUES
-- Carotid ↔ temporal EEG (proximate placement)
(8,  27, 'cross_modal', 0.9,  NULL),   -- T3 ↔ CAROT_L
(12, 28, 'cross_modal', 0.9,  NULL),   -- T4 ↔ CAROT_R
-- Carotid ↔ HRV (central cardiac reference)
(21, 27, 'cross_modal', 0.8,  NULL),   -- HRV ↔ CAROT_L
(21, 28, 'cross_modal', 0.8,  NULL),   -- HRV ↔ CAROT_R
-- Bilateral carotid
(27, 28, 'cross_modal', 0.9,    6.0),  -- CAROT_L ↔ CAROT_R    ~6 cm
-- Central-to-peripheral (PWV measurement paths)
(27, 29, 'cross_modal', 0.7,   75.0),  -- CAROT_L ↔ RADIAL_L   ~75 cm
(28, 30, 'cross_modal', 0.7,   75.0),  -- CAROT_R ↔ RADIAL_R   ~75 cm
(27, 31, 'cross_modal', 0.7,   55.0),  -- CAROT_L ↔ FEMORAL_L  ~55 cm
(28, 32, 'cross_modal', 0.7,   55.0),  -- CAROT_R ↔ FEMORAL_R  ~55 cm
-- Peripheral bilateral
(29, 30, 'cross_modal', 0.7,   45.0),  -- RADIAL_L ↔ RADIAL_R  ~45 cm
(31, 32, 'cross_modal', 0.7,   30.0),  -- FEMORAL_L ↔ FEMORAL_R ~30 cm
-- Cross-limb paths (for systemic PWV index)
(29, 31, 'cross_modal', 0.5,   85.0),  -- RADIAL_L ↔ FEMORAL_L ~85 cm
(30, 32, 'cross_modal', 0.5,   85.0)   -- RADIAL_R ↔ FEMORAL_R ~85 cm
ON CONFLICT DO NOTHING;

-- ── Vascular columns on mesh_node_readings ───────────────────
ALTER TABLE mesh_node_readings
  ADD COLUMN IF NOT EXISTS phase_shift_rad  REAL,        -- RF phase shift from vessel wall displacement (rad)
  ADD COLUMN IF NOT EXISTS pulse_amplitude  REAL,        -- pulsatile envelope amplitude (normalised 0-1)
  ADD COLUMN IF NOT EXISTS carrier_freq_ghz REAL,        -- RF carrier used (e.g. 10.245)
  ADD COLUMN IF NOT EXISTS beat_interval_ms REAL,        -- R-R interval at this node (ms)
  ADD COLUMN IF NOT EXISTS vasc_state       vasc_state;  -- classifier output

-- ── Vascular columns on frozen_node_states ───────────────────
ALTER TABLE frozen_node_states
  ADD COLUMN IF NOT EXISTS phase_shift_rad  REAL,
  ADD COLUMN IF NOT EXISTS pulse_amplitude  REAL,
  ADD COLUMN IF NOT EXISTS beat_interval_ms REAL,
  ADD COLUMN IF NOT EXISTS vasc_state       vasc_state;

-- ── Vascular pulse events (cross-node timing for PWV) ─────────
-- One row per detected pulse peak per node.
-- PWV between two nodes = distance_cm / pwv_transit_ms × 10  (→ m/s).
CREATE TABLE IF NOT EXISTS vascular_pulse_events (
  id                BIGSERIAL    PRIMARY KEY,
  twin_id           UUID         NOT NULL REFERENCES twin_identity(id),
  node_id           SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  sensor_id         TEXT         NOT NULL,
  detected_at       TIMESTAMPTZ  NOT NULL,
  -- RF measurement at pulse peak
  phase_shift_rad   REAL         NOT NULL,
  pulse_amplitude   REAL         NOT NULL,
  carrier_freq_ghz  REAL         NOT NULL DEFAULT 10.245,
  -- PWV relative to a proximal reference node (NULL = this is the reference)
  ref_node_id       SMALLINT     REFERENCES mesh_nodes(id),
  pwv_transit_ms    REAL,        -- time from ref_node to this node (ms)
  pwv_m_per_s       REAL,        -- = distance_cm / pwv_transit_ms × 10
  -- Sequence number within a single cardiac cycle across all nodes
  beat_seq          BIGINT,      -- monotonically increasing per twin per beat
  metadata          JSONB
);

CREATE INDEX IF NOT EXISTS vpe_twin_ts_idx   ON vascular_pulse_events (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS vpe_node_ts_idx   ON vascular_pulse_events (node_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS vpe_beat_seq_idx  ON vascular_pulse_events (twin_id, beat_seq);

-- ── RPC: get_pwv_between(twin_id, node_a, node_b, window_min) ─
-- Returns average pulse-wave velocity between two vascular nodes
-- over the most recent window_min minutes.
CREATE OR REPLACE FUNCTION get_pwv_between(
  p_twin_id   UUID,
  p_node_a    SMALLINT,   -- proximal node (e.g. CAROT_L = 27)
  p_node_b    SMALLINT,   -- distal node   (e.g. RADIAL_L = 29)
  p_window_min INT DEFAULT 5
)
RETURNS TABLE (
  beat_count      bigint,
  mean_transit_ms real,
  mean_pwv_m_per_s real,
  distance_cm     real,
  node_a_code     text,
  node_b_code     text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  v_distance_cm REAL;
BEGIN
  -- Look up the inter-node distance from mesh_topology
  SELECT t.distance_cm INTO v_distance_cm
  FROM   mesh_topology t
  WHERE  t.node_a = LEAST(p_node_a, p_node_b)
    AND  t.node_b = GREATEST(p_node_a, p_node_b)
  LIMIT 1;

  RETURN QUERY
  WITH ref_events AS (
    SELECT beat_seq, detected_at AS ref_at
    FROM   vascular_pulse_events
    WHERE  twin_id    = p_twin_id
      AND  node_id    = p_node_a
      AND  detected_at >= NOW() - (p_window_min || ' minutes')::INTERVAL
  ),
  distal_events AS (
    SELECT beat_seq, detected_at AS distal_at
    FROM   vascular_pulse_events
    WHERE  twin_id    = p_twin_id
      AND  node_id    = p_node_b
      AND  detected_at >= NOW() - (p_window_min || ' minutes')::INTERVAL
  ),
  paired AS (
    SELECT
      EXTRACT(EPOCH FROM (d.distal_at - r.ref_at)) * 1000.0 AS transit_ms
    FROM ref_events    r
    JOIN distal_events d USING (beat_seq)
    WHERE d.distal_at > r.ref_at   -- distal must arrive after proximal
  )
  SELECT
    COUNT(*)::bigint                                              AS beat_count,
    AVG(transit_ms)::real                                        AS mean_transit_ms,
    CASE WHEN AVG(transit_ms) > 0 AND v_distance_cm IS NOT NULL
         THEN (v_distance_cm / AVG(transit_ms) * 10.0)::real
         ELSE NULL
    END                                                          AS mean_pwv_m_per_s,
    v_distance_cm                                                AS distance_cm,
    (SELECT node_code FROM mesh_nodes WHERE id = p_node_a)       AS node_a_code,
    (SELECT node_code FROM mesh_nodes WHERE id = p_node_b)       AS node_b_code
  FROM paired;
END;
$$;
