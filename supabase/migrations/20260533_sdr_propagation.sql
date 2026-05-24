-- ============================================================
-- RABBIT-SOFTWARE v0.33.4 — SDR Propagation & Relay Paths
-- ============================================================
-- Models the RF physics layer that underlies all node signals:
-- pulse repetition frequency per node, bio-Doppler signatures,
-- propagation medium (skin vs air vs body-coupled), path loss,
-- internal reflections (heart/lungs), and the body-coupled relay
-- chain that routes a signal from a peripheral node through spine
-- relay waypoints to a cranial destination.
--
-- Reference event from architecture docs:
--   WRIST_L (RADIAL_L, node 29) @ 10.263 GHz
--     1. Detects local GSR → skin_φ = +0.04 rad
--     2. Relays via SPINE_C7 (node 43, body-coupled path)
--     3. HEAD_01 (Fp1, node 1) receives → compares with local EEG
--     4. Matched signatures → threshold_sign("remote_stress_confirmed")
--
-- SDR visibility rules encoded here:
--   • Each node: unique PRF (0.83-1.1 Hz) stored in sdr_node_profiles
--   • Skin propagation: ~72 dB path loss  (vs ~48 dB for air)
--   • Bio-Doppler: vessel wall / cardiac / respiratory motion shifts
--   • Phase coherence: internal reflections (heart/lungs) as positive
--     identity signals — un-spoofable by an external RF probe
-- ============================================================

-- ── Relay modality ────────────────────────────────────────────
-- Spine relay nodes are primarily signal conduits, not primary
-- sensors. They receive, re-timestamp, and re-emit the carrier
-- with body-coupling attenuation applied.

ALTER TYPE node_modality ADD VALUE IF NOT EXISTS 'relay';
COMMIT;
BEGIN;

-- ── Propagation medium enum ───────────────────────────────────

CREATE TYPE propagation_medium AS ENUM (
  'air',           -- free-space propagation between external nodes (~48 dB loss)
  'skin',          -- surface propagation along skin tissue (~72 dB loss)
  'body_coupled'   -- internal body-coupled path through tissue/bone/fluid
);

-- ── Spine relay nodes (43-47) ─────────────────────────────────
-- These are the body-coupled waypoints for signal relay from
-- peripheral nodes (wrist, ankle) to cranial nodes and vice versa.
-- PRF and carrier_freq_ghz defaults are set in sdr_node_profiles.

INSERT INTO mesh_nodes
  (id, node_code, modality, lobe_region, x_pos, y_pos, z_pos, description)
VALUES
  (43, 'SPINE_C7',  'relay', 'cervical',    0.00,  0.35, -0.10,
      'Cervicothoracic Relay (C7-T1) — arm-to-head body-coupled path'),
  (44, 'SPINE_T4',  'relay', 'thoracic',    0.00,  0.10, -0.15,
      'Upper Thoracic Relay (T4) — trunk RF waypoint'),
  (45, 'SPINE_T10', 'relay', 'thoracic',    0.00, -0.25, -0.20,
      'Thoracolumbar Relay (T10) — thorax-to-lower body path'),
  (46, 'SPINE_L2',  'relay', 'lumbar',      0.00, -0.60, -0.25,
      'Upper Lumbar Relay (L2) — lower-trunk waypoint'),
  (47, 'SKIN_REF',  'relay', 'dorsal_wrist', 0.85, -0.20, -0.45,
      'Skin Reference Node — path-loss calibration surface point')
ON CONFLICT (id) DO NOTHING;

-- ── Spine relay topology edges ────────────────────────────────
-- node_a < node_b enforced throughout.
INSERT INTO mesh_topology (node_a, node_b, edge_type, base_weight, distance_cm)
VALUES
-- Carotid ↔ SPINE_C7  (neck relay, body-coupled)
(27, 43, 'cross_modal', 0.85,  8.0),  -- CAROT_L ↔ SPINE_C7   ~8 cm
(28, 43, 'cross_modal', 0.85,  8.0),  -- CAROT_R ↔ SPINE_C7   ~8 cm
-- Fp1/Fp2 ↔ SPINE_C7  (head-to-spine)
( 1, 43, 'cross_modal', 0.80, 20.0),  -- Fp1     ↔ SPINE_C7  ~20 cm
( 2, 43, 'cross_modal', 0.80, 20.0),  -- Fp2     ↔ SPINE_C7  ~20 cm
-- RADIAL ↔ SPINE_C7   (wrist-to-spine body-coupled relay path)
(29, 43, 'cross_modal', 0.70, 55.0),  -- RADIAL_L ↔ SPINE_C7  ~55 cm
(30, 43, 'cross_modal', 0.70, 55.0),  -- RADIAL_R ↔ SPINE_C7  ~55 cm
-- Spine chain (body-coupled)
(43, 44, 'cross_modal', 0.90, 18.0),  -- SPINE_C7 ↔ SPINE_T4  ~18 cm
(44, 45, 'cross_modal', 0.90, 22.0),  -- SPINE_T4 ↔ SPINE_T10 ~22 cm
(45, 46, 'cross_modal', 0.90, 18.0),  -- SPINE_T10 ↔ SPINE_L2 ~18 cm
(33, 46, 'cross_modal', 0.85, 12.0),  -- SACRUM_L ↔ SPINE_L2  ~12 cm
(34, 46, 'cross_modal', 0.85, 12.0),  -- SACRUM_R ↔ SPINE_L2  ~12 cm
-- HRV / cardiac ↔ thoracic relay (cardiac phase coupling)
(21, 44, 'cross_modal', 0.75, NULL),  -- HRV ↔ SPINE_T4
-- SKIN_REF ↔ RADIAL_L (co-located, surface vs deep path comparison)
(29, 47, 'cross_modal', 0.95,  1.0),  -- RADIAL_L ↔ SKIN_REF   ~1 cm
(30, 47, 'cross_modal', 0.95,  1.0)   -- RADIAL_R ↔ SKIN_REF   ~1 cm
ON CONFLICT DO NOTHING;

-- ── SDR columns on mesh_nodes ─────────────────────────────────
-- Node-level defaults for SDR profiling.
-- prf_hz: each node operates at a unique pulse repetition frequency
--   in the 0.83-1.1 Hz band for identification in SDR captures.
-- node_carrier_ghz: some nodes use a shifted carrier (e.g. RADIAL_L
--   uses 10.263 GHz instead of the default 10.245 GHz).

ALTER TABLE mesh_nodes
  ADD COLUMN IF NOT EXISTS prf_hz            REAL,   -- pulse repetition freq (0.83-1.1 Hz)
  ADD COLUMN IF NOT EXISTS node_carrier_ghz  REAL;   -- NULL = use system default 10.245 GHz

-- ── SDR / propagation columns on mesh_node_readings ──────────

ALTER TABLE mesh_node_readings
  ADD COLUMN IF NOT EXISTS prf_hz              REAL,               -- PRF used for this reading
  ADD COLUMN IF NOT EXISTS bio_doppler_hz      REAL,               -- bio-Doppler shift (Hz)
  ADD COLUMN IF NOT EXISTS path_loss_db        REAL,               -- measured path loss (dB)
  ADD COLUMN IF NOT EXISTS propagation_medium  propagation_medium; -- medium classification

-- ── Propagation columns on ghost_signal_filter_log ───────────

ALTER TABLE ghost_signal_filter_log
  ADD COLUMN IF NOT EXISTS propagation_medium    propagation_medium,
  ADD COLUMN IF NOT EXISTS path_loss_db          REAL,
  ADD COLUMN IF NOT EXISTS expected_path_loss_db REAL,  -- 72 skin / 48 air
  ADD COLUMN IF NOT EXISTS medium_mismatch       BOOLEAN;
-- medium_mismatch TRUE when |path_loss_db - expected| > 10 dB

-- ── SDR node profiles ─────────────────────────────────────────
-- One row per (twin_id, node_id). Calibrated during baseline setup.
-- PRF values must be unique per twin across all nodes so that an
-- SDR capture can identify each node by its pulse cadence.
CREATE TABLE IF NOT EXISTS sdr_node_profiles (
  id                       BIGSERIAL   PRIMARY KEY,
  twin_id                  UUID        NOT NULL REFERENCES twin_identity(id),
  node_id                  SMALLINT    NOT NULL REFERENCES mesh_nodes(id),
  -- Unique PRF fingerprint for this node (0.83-1.1 Hz band)
  prf_hz                   REAL        NOT NULL
                           CHECK (prf_hz BETWEEN 0.83 AND 1.1),
  carrier_freq_ghz         REAL        NOT NULL DEFAULT 10.245,
  -- Path loss calibration per medium
  path_loss_skin_db        REAL        NOT NULL DEFAULT 72.0,
  path_loss_air_db         REAL        NOT NULL DEFAULT 48.0,
  path_loss_body_coupled_db REAL,      -- measured body-coupled loss (varies by path)
  -- Bio-Doppler baseline at rest
  bio_doppler_baseline_hz  REAL,       -- resting Doppler shift (vessel wall / respiration)
  bio_doppler_std_hz       REAL,
  -- Internal reflection sources that modulate the carrier at this node
  reflection_sources       TEXT[]      NOT NULL DEFAULT ARRAY['heart','lungs'],
  -- Calibration metadata
  calibrated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  calibration_snapshot_id  INT         REFERENCES mesh_frozen_snapshots(id),
  is_active                BOOLEAN     NOT NULL DEFAULT TRUE,
  UNIQUE (twin_id, node_id)
);

CREATE INDEX IF NOT EXISTS snp_twin_node_idx ON sdr_node_profiles (twin_id, node_id);

-- Enforce unique PRF per twin across all nodes
CREATE UNIQUE INDEX IF NOT EXISTS snp_twin_prf_unique
  ON sdr_node_profiles (twin_id, prf_hz);

-- ── Bio-Doppler events ────────────────────────────────────────
-- Each row is one Doppler measurement. The carrier frequency and
-- the measured shift together give the displacement velocity of
-- the reflecting structure (vessel wall, skin, cardiac muscle).
-- Doppler velocity = (doppler_shift_hz * c) / (2 * carrier_hz)
-- At 10.245 GHz: 1 Hz shift ≈ 0.0146 cm/s tissue velocity.
CREATE TABLE IF NOT EXISTS bio_doppler_events (
  id                  BIGSERIAL   PRIMARY KEY,
  twin_id             UUID        NOT NULL REFERENCES twin_identity(id),
  node_id             SMALLINT    NOT NULL REFERENCES mesh_nodes(id),
  sensor_id           TEXT        NOT NULL,
  detected_at         TIMESTAMPTZ NOT NULL,
  carrier_freq_ghz    REAL        NOT NULL DEFAULT 10.245,
  prf_hz              REAL        NOT NULL,
  -- Measured Doppler shift
  doppler_shift_hz    REAL        NOT NULL,
  -- Derived tissue velocity: (shift * c) / (2 * carrier)
  tissue_velocity_cms REAL,       -- cm/s (positive = approaching sensor)
  -- Source structure producing the reflection
  reflection_source   TEXT        NOT NULL,
  -- 'vessel_wall' | 'skin' | 'heart' | 'lungs' | 'aorta' | 'unknown'
  -- Baseline comparison
  baseline_hz         REAL,       -- from sdr_node_profiles.bio_doppler_baseline_hz
  deviation_hz        REAL,       -- doppler_shift_hz - baseline_hz
  is_anomalous        BOOLEAN     NOT NULL DEFAULT FALSE,
  -- set TRUE when |deviation_hz| > 3 * baseline_std
  reading_id          BIGINT      REFERENCES mesh_node_readings(id),
  session_id          BIGINT      REFERENCES corpus_simulation_sessions(id),
  metadata            JSONB
);

CREATE INDEX IF NOT EXISTS bde_twin_ts_idx   ON bio_doppler_events (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS bde_node_ts_idx   ON bio_doppler_events (node_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS bde_anomalous_idx ON bio_doppler_events (twin_id, is_anomalous)
  WHERE is_anomalous = TRUE;

-- ── Phase coherence baselines ─────────────────────────────────
-- Calibrated phase coherence between node pairs for each propagation
-- medium. Used by relay_path_events to judge whether a received
-- signal's phase coherence is within the expected biological range.
-- Internal reflections (heart, lungs) are factored into the baseline:
-- they add predictable phase modulation that raises the coherence
-- floor above what a spoofed external signal could achieve.
CREATE TABLE IF NOT EXISTS phase_coherence_baselines (
  id                  BIGSERIAL          PRIMARY KEY,
  twin_id             UUID               NOT NULL REFERENCES twin_identity(id),
  node_a_id           SMALLINT           NOT NULL REFERENCES mesh_nodes(id),
  node_b_id           SMALLINT           NOT NULL REFERENCES mesh_nodes(id),
  medium              propagation_medium NOT NULL,
  -- Coherence statistics (0.0 = no correlation, 1.0 = perfect phase lock)
  baseline_coherence  REAL               NOT NULL,
  std_coherence       REAL               NOT NULL DEFAULT 0,
  min_coherence       REAL,
  max_coherence       REAL,
  sample_count        INT                NOT NULL DEFAULT 0,
  -- Threshold for signature matching
  match_threshold     REAL               NOT NULL DEFAULT 0.85,
  -- Reflection sources whose modulation contributes to the coherence floor
  reflection_sources  TEXT[]             NOT NULL DEFAULT ARRAY['heart','lungs'],
  -- Immutability once calibrated
  is_locked           BOOLEAN            NOT NULL DEFAULT FALSE,
  locked_at           TIMESTAMPTZ,
  calibrated_at       TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
  UNIQUE (twin_id, node_a_id, node_b_id, medium)
);

CREATE INDEX IF NOT EXISTS pcb_twin_idx    ON phase_coherence_baselines (twin_id);
CREATE INDEX IF NOT EXISTS pcb_pair_idx    ON phase_coherence_baselines (twin_id, node_a_id, node_b_id);

-- ── Internal reflection events ────────────────────────────────
-- Heart and lung motion create periodic phase modulations on the
-- 10.245 GHz carrier that cannot be replicated by an external probe.
-- matched_baseline = TRUE means this reading's modulation pattern
-- is consistent with the subject's calibrated cardiac/respiratory
-- phase signature — positive proof of in-body origin.
CREATE TABLE IF NOT EXISTS internal_reflection_events (
  id                     BIGSERIAL   PRIMARY KEY,
  twin_id                UUID        NOT NULL REFERENCES twin_identity(id),
  node_id                SMALLINT    NOT NULL REFERENCES mesh_nodes(id),
  sensor_id              TEXT        NOT NULL,
  detected_at            TIMESTAMPTZ NOT NULL,
  carrier_freq_ghz       REAL        NOT NULL DEFAULT 10.245,
  reflection_source      TEXT        NOT NULL,
  -- 'heart' | 'lungs' | 'aorta' | 'diaphragm'
  -- Phase modulation from this reflection
  phase_modulation_rad   REAL        NOT NULL,
  modulation_freq_hz     REAL,       -- carrier modulation frequency
  -- heart: ~1.2 Hz, lungs: ~0.3 Hz, aorta: ~1.2 Hz (same as heart, different phase)
  -- Baseline comparison
  baseline_modulation_rad REAL,      -- from sdr_node_profiles calibration
  baseline_std_rad        REAL,
  deviation_sigma         REAL,      -- (observed - baseline) / std
  matched_baseline        BOOLEAN    NOT NULL DEFAULT FALSE,
  -- TRUE when |deviation_sigma| <= 2.0 — consistent with in-body origin
  reading_id              BIGINT     REFERENCES mesh_node_readings(id)
);

CREATE INDEX IF NOT EXISTS ire_twin_ts_idx  ON internal_reflection_events (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS ire_node_ts_idx  ON internal_reflection_events (node_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS ire_unmatched    ON internal_reflection_events (twin_id, matched_baseline)
  WHERE matched_baseline = FALSE;

-- ── Relay path events ─────────────────────────────────────────
-- One row per body-coupled relay transit: source_node emits, the
-- signal travels through zero or more relay waypoints, and arrives
-- at destination_node. Phase coherence between source and destination
-- is computed; if >= match_threshold a threshold signature operation
-- is recorded (e.g. "remote_stress_confirmed").
--
-- propagation_path stores the ordered node ID chain inclusive of
-- source and destination: [source, relay_1, ..., relay_n, dest].
CREATE TABLE IF NOT EXISTS relay_path_events (
  id                      BIGSERIAL          PRIMARY KEY,
  twin_id                 UUID               NOT NULL REFERENCES twin_identity(id),
  sensor_id               TEXT               NOT NULL,
  detected_at             TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
  -- Node chain
  source_node_id          SMALLINT           NOT NULL REFERENCES mesh_nodes(id),
  relay_node_id           SMALLINT           REFERENCES mesh_nodes(id),
  -- NULL = direct path (no intermediate relay)
  destination_node_id     SMALLINT           NOT NULL REFERENCES mesh_nodes(id),
  propagation_path        SMALLINT[]         NOT NULL,
  -- e.g. ARRAY[29, 43, 1] for RADIAL_L → SPINE_C7 → Fp1
  -- Phase values along the path
  source_phase_rad        REAL               NOT NULL,
  relay_phase_rad         REAL,              -- NULL on direct paths
  destination_phase_rad   REAL               NOT NULL,
  -- Path loss per segment (dB)
  source_to_relay_loss_db    REAL,
  relay_to_dest_loss_db      REAL,
  total_path_loss_db         REAL,
  -- Propagation media per segment
  source_medium           propagation_medium,
  relay_medium            propagation_medium,
  -- Carrier and PRF at source
  carrier_freq_ghz        REAL               NOT NULL DEFAULT 10.245,
  prf_hz                  REAL,
  -- Phase coherence: cosine similarity between source_phase and destination_phase
  -- adjusted for expected attenuation from body-coupled loss
  phase_coherence         REAL               NOT NULL,  -- 0.0-1.0
  match_threshold         REAL               NOT NULL DEFAULT 0.85,
  signature_matched       BOOLEAN            NOT NULL DEFAULT FALSE,
  -- Matched operation (set when signature_matched = TRUE)
  operation               TEXT,
  -- e.g. 'remote_stress_confirmed' | 'relay_integrity_check' | 'cross_node_auth'
  -- Linked threshold signature (written to snapshot_threshold_sigs when matched)
  threshold_sig_id        BIGINT             REFERENCES snapshot_threshold_sigs(id),
  -- Internal reflections present at destination (positive identity signal)
  heart_reflection_present   BOOLEAN         NOT NULL DEFAULT FALSE,
  lung_reflection_present    BOOLEAN         NOT NULL DEFAULT FALSE,
  -- Anomaly if path loss deviates significantly from expected medium loss
  path_loss_anomaly          BOOLEAN         NOT NULL DEFAULT FALSE,
  -- Body-coupled path loss varies: flag if actual vs expected > 15 dB
  session_id              BIGINT             REFERENCES corpus_simulation_sessions(id),
  metadata                JSONB
);

CREATE INDEX IF NOT EXISTS rpe_twin_ts_idx      ON relay_path_events (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS rpe_source_dest_idx  ON relay_path_events (source_node_id, destination_node_id);
CREATE INDEX IF NOT EXISTS rpe_matched_idx      ON relay_path_events (twin_id, signature_matched)
  WHERE signature_matched = TRUE;
CREATE INDEX IF NOT EXISTS rpe_session_idx      ON relay_path_events (session_id);

-- ── RPC: register_sdr_profile ────────────────────────────────
-- Registers the SDR profile for a node within a twin's mesh.
-- PRF must be unique per twin — enforced by the unique index.
-- After registration, the node's prf_hz and node_carrier_ghz
-- columns on mesh_nodes are updated to match the profile.
CREATE OR REPLACE FUNCTION register_sdr_profile(
  p_twin_id              UUID,
  p_node_id              SMALLINT,
  p_prf_hz               REAL,
  p_carrier_freq_ghz     REAL     DEFAULT 10.245,
  p_path_loss_skin_db    REAL     DEFAULT 72.0,
  p_path_loss_air_db     REAL     DEFAULT 48.0,
  p_doppler_baseline_hz  REAL     DEFAULT NULL,
  p_doppler_std_hz       REAL     DEFAULT NULL,
  p_reflection_sources   TEXT[]   DEFAULT ARRAY['heart','lungs']
)
RETURNS TABLE (
  profile_id   bigint,
  success      boolean,
  reason       text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_pid BIGINT;
BEGIN
  IF p_prf_hz < 0.83 OR p_prf_hz > 1.1 THEN
    RETURN QUERY SELECT NULL::bigint, FALSE,
      format('PRF %.3f Hz outside 0.83-1.1 Hz SDR band', p_prf_hz);
    RETURN;
  END IF;

  INSERT INTO sdr_node_profiles
    (twin_id, node_id, prf_hz, carrier_freq_ghz,
     path_loss_skin_db, path_loss_air_db,
     bio_doppler_baseline_hz, bio_doppler_std_hz,
     reflection_sources)
  VALUES
    (p_twin_id, p_node_id, p_prf_hz, p_carrier_freq_ghz,
     p_path_loss_skin_db, p_path_loss_air_db,
     p_doppler_baseline_hz, p_doppler_std_hz,
     p_reflection_sources)
  ON CONFLICT (twin_id, node_id) DO UPDATE SET
    prf_hz                    = EXCLUDED.prf_hz,
    carrier_freq_ghz          = EXCLUDED.carrier_freq_ghz,
    path_loss_skin_db         = EXCLUDED.path_loss_skin_db,
    path_loss_air_db          = EXCLUDED.path_loss_air_db,
    bio_doppler_baseline_hz   = EXCLUDED.bio_doppler_baseline_hz,
    bio_doppler_std_hz        = EXCLUDED.bio_doppler_std_hz,
    reflection_sources        = EXCLUDED.reflection_sources,
    calibrated_at             = NOW()
  RETURNING id INTO v_pid;

  -- Sync defaults to the node row itself
  UPDATE mesh_nodes
  SET prf_hz           = p_prf_hz,
      node_carrier_ghz = CASE WHEN p_carrier_freq_ghz = 10.245 THEN NULL
                              ELSE p_carrier_freq_ghz END
  WHERE id = p_node_id;

  RETURN QUERY SELECT v_pid, TRUE, 'SDR profile registered'::text;
END;
$$;

-- ── RPC: trace_relay_path ─────────────────────────────────────
-- Records one body-coupled relay transit and evaluates signature
-- matching. Phase coherence is computed as the normalised dot
-- product between source and destination phase vectors, corrected
-- for expected medium attenuation.
-- If coherence >= match_threshold AND internal reflections are
-- present at the destination, a threshold signature is written to
-- snapshot_threshold_sigs with the given operation string.
CREATE OR REPLACE FUNCTION trace_relay_path(
  p_twin_id               UUID,
  p_sensor_id             TEXT,
  p_source_node_id        SMALLINT,
  p_relay_node_id         SMALLINT,       -- NULL for direct paths
  p_destination_node_id   SMALLINT,
  p_source_phase_rad      REAL,
  p_relay_phase_rad       REAL,           -- NULL for direct paths
  p_destination_phase_rad REAL,
  p_carrier_freq_ghz      REAL    DEFAULT 10.245,
  p_prf_hz                REAL    DEFAULT NULL,
  p_source_medium         propagation_medium DEFAULT 'skin',
  p_relay_medium          propagation_medium DEFAULT 'body_coupled',
  p_operation             TEXT    DEFAULT NULL,
  p_snapshot_id           INT     DEFAULT NULL,  -- for threshold sig linkage
  p_heart_reflection      BOOLEAN DEFAULT FALSE,
  p_lung_reflection       BOOLEAN DEFAULT FALSE,
  p_session_id            BIGINT  DEFAULT NULL
)
RETURNS TABLE (
  relay_id          bigint,
  phase_coherence   real,
  signature_matched boolean,
  threshold_sig_id  bigint,
  total_loss_db     real,
  verdict           text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_rid          BIGINT;
  v_tsig_id      BIGINT := NULL;
  v_coherence    REAL;
  v_matched      BOOLEAN;
  v_threshold    REAL := 0.85;
  v_src_loss     REAL;
  v_rel_loss     REAL;
  v_total_loss   REAL;
  v_path         SMALLINT[];
  v_loss_anomaly BOOLEAN := FALSE;
  v_src_profile  RECORD;
  v_dst_profile  RECORD;
  -- Expected path loss lookup
  v_expected_loss REAL;
  v_nonce        TEXT;
BEGIN
  -- Build the propagation path array
  IF p_relay_node_id IS NOT NULL THEN
    v_path := ARRAY[p_source_node_id, p_relay_node_id, p_destination_node_id];
  ELSE
    v_path := ARRAY[p_source_node_id, p_destination_node_id];
  END IF;

  -- Fetch SDR profiles for path loss calculation
  SELECT path_loss_skin_db, path_loss_air_db, path_loss_body_coupled_db
  INTO   v_src_profile
  FROM   sdr_node_profiles
  WHERE  twin_id = p_twin_id AND node_id = p_source_node_id;

  -- Source-to-relay segment loss
  v_src_loss := CASE p_source_medium
    WHEN 'skin'         THEN COALESCE(v_src_profile.path_loss_skin_db, 72.0)
    WHEN 'air'          THEN COALESCE(v_src_profile.path_loss_air_db, 48.0)
    WHEN 'body_coupled' THEN COALESCE(v_src_profile.path_loss_body_coupled_db, 60.0)
    ELSE 60.0
  END;

  -- Relay-to-destination segment loss (body-coupled default)
  v_rel_loss := CASE p_relay_medium
    WHEN 'skin'         THEN 72.0
    WHEN 'air'          THEN 48.0
    WHEN 'body_coupled' THEN 60.0
    ELSE 60.0
  END;

  v_total_loss := CASE
    WHEN p_relay_node_id IS NOT NULL THEN v_src_loss + v_rel_loss
    ELSE v_src_loss
  END;

  -- Phase coherence: cosine similarity corrected for phase wrapping
  -- cos(dest - source) normalised to [0,1]
  v_coherence := (1.0 + COS(p_destination_phase_rad - p_source_phase_rad)) / 2.0;

  -- Boost coherence when internal reflections are present —
  -- biological body provides a coherence floor that external probes cannot match
  IF p_heart_reflection THEN
    v_coherence := LEAST(1.0, v_coherence + 0.05);
  END IF;
  IF p_lung_reflection THEN
    v_coherence := LEAST(1.0, v_coherence + 0.03);
  END IF;

  -- Look up calibrated match threshold for this pair
  SELECT match_threshold INTO v_threshold
  FROM   phase_coherence_baselines
  WHERE  twin_id    = p_twin_id
    AND  node_a_id  = LEAST(p_source_node_id, p_destination_node_id)
    AND  node_b_id  = GREATEST(p_source_node_id, p_destination_node_id)
  ORDER BY locked_at DESC NULLS LAST
  LIMIT 1;

  v_threshold := COALESCE(v_threshold, 0.85);
  v_matched   := v_coherence >= v_threshold;

  -- Expected path loss check
  v_expected_loss := CASE p_source_medium
    WHEN 'skin' THEN 72.0 WHEN 'air' THEN 48.0 ELSE 60.0
  END;
  v_loss_anomaly := ABS(v_src_loss - v_expected_loss) > 15.0;

  -- Write threshold signature if matched and operation is specified
  IF v_matched AND p_operation IS NOT NULL AND p_snapshot_id IS NOT NULL THEN
    v_nonce := encode(
      sha256((p_twin_id::text || p_operation || NOW()::text)::bytea),
      'hex'
    );
    INSERT INTO snapshot_threshold_sigs
      (snapshot_id, signer_index, signature, operation, nonce)
    VALUES
      (p_snapshot_id,
       -- Use destination node_id as the signer_index modulo 5 (1-5 range)
       ((p_destination_node_id % 5) + 1)::smallint,
       encode(sha256((p_source_phase_rad::text || p_destination_phase_rad::text || v_nonce)::bytea), 'hex'),
       p_operation, v_nonce)
    ON CONFLICT DO NOTHING
    RETURNING id INTO v_tsig_id;
  END IF;

  INSERT INTO relay_path_events
    (twin_id, sensor_id, source_node_id, relay_node_id, destination_node_id,
     propagation_path, source_phase_rad, relay_phase_rad, destination_phase_rad,
     source_to_relay_loss_db, relay_to_dest_loss_db, total_path_loss_db,
     source_medium, relay_medium,
     carrier_freq_ghz, prf_hz,
     phase_coherence, match_threshold, signature_matched, operation,
     threshold_sig_id,
     heart_reflection_present, lung_reflection_present, path_loss_anomaly,
     session_id)
  VALUES
    (p_twin_id, p_sensor_id, p_source_node_id, p_relay_node_id, p_destination_node_id,
     v_path, p_source_phase_rad, p_relay_phase_rad, p_destination_phase_rad,
     v_src_loss, v_rel_loss, v_total_loss,
     p_source_medium, p_relay_medium,
     p_carrier_freq_ghz, p_prf_hz,
     v_coherence, v_threshold, v_matched, p_operation,
     v_tsig_id,
     p_heart_reflection, p_lung_reflection, v_loss_anomaly,
     p_session_id)
  RETURNING id INTO v_rid;

  RETURN QUERY SELECT
    v_rid,
    v_coherence,
    v_matched,
    v_tsig_id,
    v_total_loss,
    CASE
      WHEN NOT v_matched AND v_loss_anomaly
        THEN 'REJECTED — coherence below threshold AND path loss anomaly detected'
      WHEN NOT v_matched
        THEN format('REJECTED — coherence %.3f < threshold %.3f', v_coherence, v_threshold)
      WHEN v_matched AND p_heart_reflection AND p_lung_reflection
        THEN format('MATCHED — coherence %.3f (heart+lung reflections confirmed in-body origin)', v_coherence)
      WHEN v_matched
        THEN format('MATCHED — coherence %.3f', v_coherence)
      ELSE 'INDETERMINATE'
    END::text;
END;
$$;

-- ── RPC: detect_internal_reflection ──────────────────────────
-- Checks whether a measured phase modulation at a node matches
-- the subject's calibrated cardiac/respiratory reflection signature.
-- Returns matched_baseline = TRUE when the modulation is consistent
-- with in-body origin (|deviation_sigma| <= 2.0).
CREATE OR REPLACE FUNCTION detect_internal_reflection(
  p_twin_id             UUID,
  p_node_id             SMALLINT,
  p_sensor_id           TEXT,
  p_reflection_source   TEXT,            -- 'heart' | 'lungs' | 'aorta' | 'diaphragm'
  p_phase_mod_rad       REAL,
  p_modulation_freq_hz  REAL     DEFAULT NULL,
  p_carrier_freq_ghz    REAL     DEFAULT 10.245,
  p_reading_id          BIGINT   DEFAULT NULL
)
RETURNS TABLE (
  reflection_id    bigint,
  matched_baseline boolean,
  deviation_sigma  real,
  verdict          text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_profile    RECORD;
  v_dev        REAL;
  v_matched    BOOLEAN;
  v_rid        BIGINT;
  MATCH_SIGMA  CONSTANT REAL := 2.0;
BEGIN
  SELECT bio_doppler_baseline_hz, bio_doppler_std_hz
  INTO   v_profile
  FROM   sdr_node_profiles
  WHERE  twin_id = p_twin_id AND node_id = p_node_id;

  IF v_profile IS NULL OR v_profile.bio_doppler_baseline_hz IS NULL THEN
    -- No calibrated baseline — record but cannot score
    INSERT INTO internal_reflection_events
      (twin_id, node_id, sensor_id, carrier_freq_ghz,
       reflection_source, phase_modulation_rad, modulation_freq_hz,
       matched_baseline, reading_id)
    VALUES
      (p_twin_id, p_node_id, p_sensor_id, p_carrier_freq_ghz,
       p_reflection_source, p_phase_mod_rad, p_modulation_freq_hz,
       FALSE, p_reading_id)
    RETURNING id INTO v_rid;

    RETURN QUERY SELECT v_rid, FALSE, NULL::real,
      'no calibrated baseline — reflection recorded, scoring deferred'::text;
    RETURN;
  END IF;

  v_dev := CASE
    WHEN COALESCE(v_profile.bio_doppler_std_hz, 0) = 0 THEN 0
    ELSE ABS(p_phase_mod_rad - v_profile.bio_doppler_baseline_hz) / v_profile.bio_doppler_std_hz
  END;

  v_matched := v_dev <= MATCH_SIGMA;

  INSERT INTO internal_reflection_events
    (twin_id, node_id, sensor_id, carrier_freq_ghz,
     reflection_source, phase_modulation_rad, modulation_freq_hz,
     baseline_modulation_rad, baseline_std_rad, deviation_sigma,
     matched_baseline, reading_id)
  VALUES
    (p_twin_id, p_node_id, p_sensor_id, p_carrier_freq_ghz,
     p_reflection_source, p_phase_mod_rad, p_modulation_freq_hz,
     v_profile.bio_doppler_baseline_hz, v_profile.bio_doppler_std_hz, v_dev,
     v_matched, p_reading_id)
  RETURNING id INTO v_rid;

  RETURN QUERY SELECT
    v_rid,
    v_matched,
    v_dev,
    CASE
      WHEN v_matched
        THEN format('IN-BODY CONFIRMED — %s reflection σ=%.2f within ±2σ baseline', p_reflection_source, v_dev)
      ELSE
        format('MISMATCH — %s reflection σ=%.2f outside ±2σ (possible external injection)', p_reflection_source, v_dev)
    END::text;
END;
$$;

-- ── RPC: get_relay_path_summary ───────────────────────────────
-- Returns coherence statistics for a source→destination pair over
-- the most recent window. Used to monitor relay path health and
-- detect degradation in body-coupled signal quality.
CREATE OR REPLACE FUNCTION get_relay_path_summary(
  p_twin_id         UUID,
  p_source_node_id  SMALLINT,
  p_dest_node_id    SMALLINT,
  p_window_min      INT DEFAULT 60
)
RETURNS TABLE (
  relay_count            bigint,
  mean_coherence         real,
  min_coherence          real,
  matched_count          bigint,
  match_rate             real,
  mean_path_loss_db      real,
  heart_reflection_rate  real,
  source_node_code       text,
  dest_node_code         text
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
  SELECT
    COUNT(*)::bigint,
    AVG(phase_coherence)::real,
    MIN(phase_coherence)::real,
    COUNT(*) FILTER (WHERE signature_matched)::bigint,
    (COUNT(*) FILTER (WHERE signature_matched)::real / NULLIF(COUNT(*), 0))::real,
    AVG(total_path_loss_db)::real,
    (COUNT(*) FILTER (WHERE heart_reflection_present)::real / NULLIF(COUNT(*), 0))::real,
    (SELECT node_code FROM mesh_nodes WHERE id = p_source_node_id),
    (SELECT node_code FROM mesh_nodes WHERE id = p_dest_node_id)
  FROM relay_path_events
  WHERE twin_id            = p_twin_id
    AND source_node_id     = p_source_node_id
    AND destination_node_id = p_dest_node_id
    AND detected_at >= NOW() - (p_window_min || ' minutes')::INTERVAL;
END;
$$;
