-- ============================================================
-- RABBIT-SOFTWARE v0.33.0 — Lower Body Kinetic Node Extension
-- ============================================================
-- Extends the mesh with 10 kinetic/grounding nodes (IDs 33-42)
-- across three anatomical sub-groups:
--
--   33-34  Sacrum / Neural Trunk (L5-S1 junctions)
--            Monitor primary signal transit between upper CNS and
--            lower PNS — the "relay station" for spinal cord latency.
--
--   35-38  Femoral / Knee Junctions
--            Kinetic side of the femoral junction: motor nerve intent
--            and reflex arc timing. Co-located near vascular nodes
--            31-32 (FEMORAL_L/R) for cross-modal PWV + motor validation.
--            Patella nodes capture the patellar reflex arc.
--
--   39-42  Ankle / Plantar (Grounding Terminals)
--            Terminal vectors of the Digital Twin. Ground impedance
--            (foot-to-surface resistance) closes the circuit and
--            verifies the mesh is a complete mirror of the subject.
--
-- New modality: 'kinetic'
-- New columns on readings/frozen states: EMG, reflex latency, motor
--   intent score, and ground impedance.
-- New table: kinetic_gait_events (gait-cycle timing, parallel to
--   vascular_pulse_events for PWV).
-- ============================================================

ALTER TYPE node_modality ADD VALUE IF NOT EXISTS 'kinetic';
COMMIT;
BEGIN;

-- ── Kinetic nodes (33-42) ─────────────────────────────────────
INSERT INTO mesh_nodes (id, node_code, modality, lobe_region, x_pos, y_pos, z_pos, description) VALUES
-- Sacrum / Neural Trunk
(33, 'SACRUM_L',       'kinetic', 'sacrum',        -0.05, -0.85, -0.30, 'Left L5-S1 Sacral Neural Trunk'),
(34, 'SACRUM_R',       'kinetic', 'sacrum',         0.05, -0.85, -0.30, 'Right L5-S1 Sacral Neural Trunk'),
-- Femoral Nerve / Knee Junctions (kinetic, co-located near vascular 31-32)
(35, 'FEM_NERVE_L',    'kinetic', 'lower_limb',    -0.25, -1.00, -0.40, 'Left Femoral Nerve / Motor Junction'),
(36, 'FEM_NERVE_R',    'kinetic', 'lower_limb',     0.25, -1.00, -0.40, 'Right Femoral Nerve / Motor Junction'),
(37, 'PATELLA_L',      'kinetic', 'lower_limb',    -0.22, -1.30, -0.55, 'Left Patellar Reflex Node (Knee)'),
(38, 'PATELLA_R',      'kinetic', 'lower_limb',     0.22, -1.30, -0.55, 'Right Patellar Reflex Node (Knee)'),
-- Ankle / Plantar (Grounding Terminals)
(39, 'ANKLE_L',        'kinetic', 'lower_limb',    -0.18, -1.75, -0.70, 'Left Ankle / Achilles'),
(40, 'ANKLE_R',        'kinetic', 'lower_limb',     0.18, -1.75, -0.70, 'Right Ankle / Achilles'),
(41, 'PLANTAR_L',      'kinetic', 'lower_limb',    -0.18, -1.90, -0.80, 'Left Plantar / Foot Ground Terminal'),
(42, 'PLANTAR_R',      'kinetic', 'lower_limb',     0.18, -1.90, -0.80, 'Right Plantar / Foot Ground Terminal')
ON CONFLICT (id) DO NOTHING;

-- ── Inter-node topology for kinetic group ─────────────────────
-- distance_cm values are median anatomical path-length estimates.
INSERT INTO mesh_topology (node_a, node_b, edge_type, base_weight, distance_cm) VALUES
-- Sacral trunk bilateral
(33, 34, 'cross_modal', 0.9,   3.0),   -- SACRUM_L ↔ SACRUM_R       ~3 cm
-- Sacrum → femoral nerve (spinal to peripheral)
(33, 35, 'cross_modal', 0.8,  30.0),   -- SACRUM_L ↔ FEM_NERVE_L    ~30 cm
(34, 36, 'cross_modal', 0.8,  30.0),   -- SACRUM_R ↔ FEM_NERVE_R    ~30 cm
-- Femoral nerve → patella (motor arc)
(35, 37, 'cross_modal', 0.85, 20.0),   -- FEM_NERVE_L ↔ PATELLA_L   ~20 cm
(36, 38, 'cross_modal', 0.85, 20.0),   -- FEM_NERVE_R ↔ PATELLA_R   ~20 cm
-- Patella → ankle (lower leg segment)
(37, 39, 'cross_modal', 0.75, 35.0),   -- PATELLA_L ↔ ANKLE_L       ~35 cm
(38, 40, 'cross_modal', 0.75, 35.0),   -- PATELLA_R ↔ ANKLE_R       ~35 cm
-- Ankle → plantar (grounding terminal)
(39, 41, 'cross_modal', 0.9,  12.0),   -- ANKLE_L ↔ PLANTAR_L       ~12 cm
(40, 42, 'cross_modal', 0.9,  12.0),   -- ANKLE_R ↔ PLANTAR_R       ~12 cm
-- Bilateral plantar (ground closure — completes the circuit)
(41, 42, 'cross_modal', 0.8,  20.0),   -- PLANTAR_L ↔ PLANTAR_R     ~20 cm
-- Cross-modal: sacrum ↔ femoral vascular (kinetic + vascular co-location)
-- node_a must be < node_b per mesh_topology check constraint
(31, 33, 'cross_modal', 0.7,  NULL),   -- FEMORAL_L (31) ↔ SACRUM_L (33)
(32, 34, 'cross_modal', 0.7,  NULL),   -- FEMORAL_R (32) ↔ SACRUM_R (34)
-- Cross-modal: femoral nerve ↔ femoral vascular (motor intent vs blood flow)
(31, 35, 'cross_modal', 0.75, NULL),   -- FEMORAL_L (31) ↔ FEM_NERVE_L (35)
(32, 36, 'cross_modal', 0.75, NULL),   -- FEMORAL_R (32) ↔ FEM_NERVE_R (36)
-- Cross-modal: sacrum ↔ HRV (autonomic coupling)
(21, 33, 'cross_modal', 0.6,  NULL),   -- HRV (21) ↔ SACRUM_L (33)
(21, 34, 'cross_modal', 0.6,  NULL),   -- HRV (21) ↔ SACRUM_R (34)
-- Full lower-chain path (sacrum-to-plantar, reflex arc length for CNS latency)
(33, 41, 'cross_modal', 0.5,  97.0),   -- SACRUM_L ↔ PLANTAR_L      ~97 cm
(34, 42, 'cross_modal', 0.5,  97.0)    -- SACRUM_R ↔ PLANTAR_R      ~97 cm
ON CONFLICT DO NOTHING;

-- ── Kinetic columns on mesh_node_readings ─────────────────────
ALTER TABLE mesh_node_readings
  ADD COLUMN IF NOT EXISTS emg_uv             REAL,   -- electromyography amplitude (µV)
  ADD COLUMN IF NOT EXISTS reflex_latency_ms  REAL,   -- reflex arc transit time (ms)
  ADD COLUMN IF NOT EXISTS motor_intent_score REAL,   -- normalised motor planning signal 0-1
  ADD COLUMN IF NOT EXISTS ground_impedance_ohm REAL; -- foot-to-surface impedance (Ω)

-- ── Kinetic columns on frozen_node_states ─────────────────────
ALTER TABLE frozen_node_states
  ADD COLUMN IF NOT EXISTS emg_uv             REAL,
  ADD COLUMN IF NOT EXISTS reflex_latency_ms  REAL,
  ADD COLUMN IF NOT EXISTS motor_intent_score REAL,
  ADD COLUMN IF NOT EXISTS ground_impedance_ohm REAL;

-- ── Gait cycle events (kinematic twin of vascular_pulse_events) ─
-- One row per detected gait event (heel-strike, toe-off, mid-stance)
-- per node per step. Reflex latency between nodes = neural conduction
-- speed = distance_cm / reflex_transit_ms × 10 (→ m/s).
CREATE TABLE IF NOT EXISTS kinetic_gait_events (
  id                    BIGSERIAL    PRIMARY KEY,
  twin_id               UUID         NOT NULL REFERENCES twin_identity(id),
  node_id               SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  sensor_id             TEXT         NOT NULL,
  detected_at           TIMESTAMPTZ  NOT NULL,
  -- Gait phase at detection
  gait_phase            TEXT         NOT NULL, -- 'heel_strike' | 'mid_stance' | 'toe_off' | 'swing'
  -- EMG signal at event
  emg_uv                REAL         NOT NULL,
  motor_intent_score    REAL,
  ground_impedance_ohm  REAL,        -- NULL for non-plantar nodes
  -- Reflex / neural conduction relative to sacral reference
  ref_node_id           SMALLINT     REFERENCES mesh_nodes(id), -- NULL = this is the sacral reference
  reflex_transit_ms     REAL,        -- elapsed time from sacral reference to this node (ms)
  neural_conduction_m_s REAL,        -- = distance_cm / reflex_transit_ms × 10  (healthy: 40-70 m/s)
  -- Step sequence (monotonically increasing per twin per step cycle)
  step_seq              BIGINT,
  laterality            TEXT,        -- 'left' | 'right' | 'bilateral'
  metadata              JSONB
);

CREATE INDEX IF NOT EXISTS kge_twin_ts_idx   ON kinetic_gait_events (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS kge_node_ts_idx   ON kinetic_gait_events (node_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS kge_step_seq_idx  ON kinetic_gait_events (twin_id, step_seq);

-- ── Spinal relay latency table ────────────────────────────────
-- Records the measured upper-to-lower CNS transit at the sacral
-- trunk — the core diagnostic for spinal cord integrity over time.
CREATE TABLE IF NOT EXISTS spinal_relay_events (
  id                  BIGSERIAL    PRIMARY KEY,
  twin_id             UUID         NOT NULL REFERENCES twin_identity(id),
  sensor_id           TEXT         NOT NULL,
  detected_at         TIMESTAMPTZ  NOT NULL,
  -- Upper reference: last EEG motor cortex event (Cz = node 10)
  motor_cortex_at     TIMESTAMPTZ  NOT NULL,
  -- Lower arrival: sacral trunk detection
  sacrum_l_at         TIMESTAMPTZ,
  sacrum_r_at         TIMESTAMPTZ,
  -- Computed transit
  left_transit_ms     REAL,        -- sacrum_l_at − motor_cortex_at in ms
  right_transit_ms    REAL,
  mean_transit_ms     REAL,        -- (left + right) / 2
  -- Distance: Cz (vertex) to L5/S1 sacrum ≈ 65 cm typical adult
  spinal_distance_cm  REAL         NOT NULL DEFAULT 65.0,
  -- Neural conduction = distance / transit (healthy corticospinal: 55-75 m/s)
  conduction_m_s      REAL,
  metadata            JSONB
);

CREATE INDEX IF NOT EXISTS sre_twin_ts_idx ON spinal_relay_events (twin_id, detected_at DESC);

-- ── RPC: get_neural_conduction(twin_id, node_a, node_b, window_min) ──
-- Returns average neural conduction velocity between two kinetic nodes
-- (or from sacrum to any peripheral node) over the most recent window.
-- Pattern mirrors get_pwv_between for the kinetic domain.
CREATE OR REPLACE FUNCTION get_neural_conduction(
  p_twin_id     UUID,
  p_node_a      SMALLINT,   -- proximal node (e.g. SACRUM_L = 33)
  p_node_b      SMALLINT,   -- distal node   (e.g. PLANTAR_L = 41)
  p_window_min  INT DEFAULT 5
)
RETURNS TABLE (
  step_count          bigint,
  mean_transit_ms     real,
  mean_conduction_m_s real,
  distance_cm         real,
  node_a_code         text,
  node_b_code         text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  v_distance_cm REAL;
BEGIN
  SELECT t.distance_cm INTO v_distance_cm
  FROM   mesh_topology t
  WHERE  t.node_a = LEAST(p_node_a, p_node_b)
    AND  t.node_b = GREATEST(p_node_a, p_node_b)
  LIMIT 1;

  RETURN QUERY
  WITH ref_events AS (
    SELECT step_seq, detected_at AS ref_at
    FROM   kinetic_gait_events
    WHERE  twin_id   = p_twin_id
      AND  node_id   = p_node_a
      AND  ref_node_id IS NULL          -- this node is the proximal reference
      AND  detected_at >= NOW() - (p_window_min || ' minutes')::INTERVAL
  ),
  distal_events AS (
    SELECT step_seq, detected_at AS distal_at
    FROM   kinetic_gait_events
    WHERE  twin_id   = p_twin_id
      AND  node_id   = p_node_b
      AND  detected_at >= NOW() - (p_window_min || ' minutes')::INTERVAL
  ),
  paired AS (
    SELECT
      EXTRACT(EPOCH FROM (d.distal_at - r.ref_at)) * 1000.0 AS transit_ms
    FROM ref_events    r
    JOIN distal_events d USING (step_seq)
    WHERE d.distal_at > r.ref_at
  )
  SELECT
    COUNT(*)::bigint                                              AS step_count,
    AVG(transit_ms)::real                                        AS mean_transit_ms,
    CASE WHEN AVG(transit_ms) > 0 AND v_distance_cm IS NOT NULL
         THEN (v_distance_cm / AVG(transit_ms) * 10.0)::real
         ELSE NULL
    END                                                          AS mean_conduction_m_s,
    v_distance_cm                                                AS distance_cm,
    (SELECT node_code FROM mesh_nodes WHERE id = p_node_a)       AS node_a_code,
    (SELECT node_code FROM mesh_nodes WHERE id = p_node_b)       AS node_b_code
  FROM paired;
END;
$$;
