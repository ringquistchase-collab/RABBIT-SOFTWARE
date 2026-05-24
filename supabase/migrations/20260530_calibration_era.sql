-- ============================================================
-- RABBIT-SOFTWARE v0.33.1 — Calibration Era (Ages 1-18)
-- ============================================================
-- The Calibration Era is the "Software Installation" of the human
-- being. Three developmental phases build the immutable baseline
-- Tree against which all future biological tokens are measured.
--
--   PRIMITIVE_MESH      (Ages  1– 5)  — neuroplasticity, TFM-LRN
--     High-amplitude, low-frequency EEG as the brain wires itself.
--     Lower nodes record Path-Length Elongation (vascular stretching
--     as the body grows). GH + Oxytocin set the Initial Salt.
--
--   COORDINATION_SYNC   (Ages  6–12)  — TFM-KIN, TFM-RWD, TFM-HRT
--     Mind-Vessel-Heart loop first tuned. Proprioceptive mapping:
--     every life-event kinetic vector saved to the corpus. Dopamine
--     sensitivity map built — the Neural Reward Map.
--
--   HORMONAL_OVERWRITE  (Ages 13–18)  — TFM-SCR, TFM-PLV, TFM-EXN
--     Prefrontal vs amygdala "Executive Noise." Sacral/Pelvic nodes
--     become active; Arousal Baseline established. Testosterone/
--     Estrogen/Adrenaline Chemical Salt recorded as System Shock
--     threshold. Most critical for Performative Authenticity.
--
--   ADULT               (Ages 18+)    — operational; reads against
--     calibration baselines rather than writing to them.
--
-- Core fraud-detection primitive:
--   Intent-to-Action Vector — the time a thought-origin (Fp1, node 1)
--   takes to produce a grounding response (PLANTAR, nodes 41/42).
--   This "Biological Constant" is locked during calibration. A live
--   RF-injected signal that fires the lower nodes without the correct
--   corticospinal latency profile is flagged as PATTERN_INJECTION.
-- ============================================================

-- ── Enums ─────────────────────────────────────────────────────

CREATE TYPE dev_phase AS ENUM (
  'PRIMITIVE_MESH',
  'COORDINATION_SYNC',
  'HORMONAL_OVERWRITE',
  'ADULT'
);

CREATE TYPE token_type AS ENUM (
  'TFM_LRN',   -- learning: high-amplitude low-freq EEG (ages 1-5)
  'TFM_KIN',   -- kinetic vector: proprioceptive mapping (ages 6-12)
  'TFM_RWD',   -- reward map: dopamine-sensitivity signature (ages 6-12)
  'TFM_HRT',   -- heart sync: mind-vessel-heart loop calibration
  'TFM_SCR',   -- sacral: puberty lower-node activation (ages 13-18)
  'TFM_PLV',   -- pelvic: arousal baseline / performative authenticity
  'TFM_EXN',   -- executive noise: prefrontal-amygdala conflict signal
  'TFM_VAS'    -- vascular: RF resonance baseline (all phases)
);

-- ── dev_phase + token on life events and frozen snapshots ─────

ALTER TABLE life_age_events
  ADD COLUMN IF NOT EXISTS dev_phase     dev_phase,
  ADD COLUMN IF NOT EXISTS token_types   token_type[],   -- which token classes this event wrote
  ADD COLUMN IF NOT EXISTS age_years_end REAL;           -- null = point-in-time event

ALTER TABLE mesh_frozen_snapshots
  ADD COLUMN IF NOT EXISTS dev_phase        dev_phase,
  ADD COLUMN IF NOT EXISTS chemical_markers JSONB;
  -- chemical_markers schema:
  --   { "GH": 0.0-1.0, "oxytocin": 0.0-1.0, "testosterone": 0.0-1.0,
  --     "estrogen": 0.0-1.0, "adrenaline": 0.0-1.0,
  --     "dopamine_sensitivity": 0.0-1.0 }

ALTER TABLE mesh_node_readings
  ADD COLUMN IF NOT EXISTS dev_phase   dev_phase,
  ADD COLUMN IF NOT EXISTS token_type  token_type;

ALTER TABLE frozen_node_states
  ADD COLUMN IF NOT EXISTS dev_phase   dev_phase,
  ADD COLUMN IF NOT EXISTS token_type  token_type;

-- ── Calibration era baselines (immutable after phase lock) ────
-- One row per (twin_id, dev_phase, node_id).
-- Written during calibration; locked permanently when the phase ends.
-- After locking: no UPDATE or DELETE is permitted (trigger enforced).
-- dna_root_sig: SHA-256(twin biological_hash || phase || node_id
--               || mean_value || locked_at), signed at lock time.
CREATE TABLE IF NOT EXISTS calibration_era_baselines (
  id               BIGSERIAL    PRIMARY KEY,
  twin_id          UUID         NOT NULL REFERENCES twin_identity(id),
  dev_phase        dev_phase    NOT NULL,
  node_id          SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  token_type       token_type   NOT NULL,
  -- Signal statistics over the phase window
  mean_value       REAL         NOT NULL,   -- primary signal mean (amplitude/emg/phase_shift)
  std_value        REAL         NOT NULL DEFAULT 0,
  min_value        REAL,
  max_value        REAL,
  sample_count     INT          NOT NULL DEFAULT 0,
  -- Path-length / latency baseline (lower nodes)
  mean_latency_ms  REAL,        -- mean transit from reference node (ms)
  std_latency_ms   REAL,
  -- Chemical context at time of locking
  chemical_markers JSONB,
  -- Immutability
  is_locked        BOOLEAN      NOT NULL DEFAULT FALSE,
  locked_at        TIMESTAMPTZ,
  dna_root_sig     TEXT,        -- SHA-256 commitment, set at lock time
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (twin_id, dev_phase, node_id, token_type)
);

CREATE INDEX IF NOT EXISTS ceb_twin_phase_idx
  ON calibration_era_baselines (twin_id, dev_phase);
CREATE INDEX IF NOT EXISTS ceb_twin_node_idx
  ON calibration_era_baselines (twin_id, node_id);

-- Prevent any modification of a locked calibration baseline.
CREATE OR REPLACE FUNCTION prevent_locked_baseline_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.is_locked THEN
    RAISE EXCEPTION
      'Calibration baseline % (twin=%, phase=%, node=%) is locked — immutable record',
      OLD.id, OLD.twin_id, OLD.dev_phase, OLD.node_id
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER lock_calibration_baselines
  BEFORE UPDATE OR DELETE ON calibration_era_baselines
  FOR EACH ROW EXECUTE FUNCTION prevent_locked_baseline_mutation();

-- ── Chemical salt events ──────────────────────────────────────
-- Hormone spike recordings throughout the calibration era.
-- relative_level is normalised 0-1 vs the subject's own rolling
-- baseline — not an absolute plasma concentration.
CREATE TABLE IF NOT EXISTS chemical_salt_events (
  id                     BIGSERIAL    PRIMARY KEY,
  twin_id                UUID         NOT NULL REFERENCES twin_identity(id),
  sensor_id              TEXT         NOT NULL,
  detected_at            TIMESTAMPTZ  NOT NULL,
  dev_phase              dev_phase    NOT NULL,
  age_years              REAL,
  hormone                TEXT         NOT NULL,
  -- 'GH' | 'oxytocin' | 'testosterone' | 'estrogen' | 'adrenaline' | 'dopamine'
  relative_level         REAL         NOT NULL,   -- 0.0 baseline → 1.0 saturation
  system_shock_flag      BOOLEAN      NOT NULL DEFAULT FALSE,
  -- set TRUE when relative_level exceeds the subject's shock threshold
  -- (derived from HORMONAL_OVERWRITE phase calibration)
  shock_threshold_used   REAL,        -- the threshold value at time of detection
  life_event_id          INT          REFERENCES life_age_events(id),
  snapshot_id            INT          REFERENCES mesh_frozen_snapshots(id),
  metadata               JSONB
);

CREATE INDEX IF NOT EXISTS cse_twin_ts_idx
  ON chemical_salt_events (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS cse_twin_phase_idx
  ON chemical_salt_events (twin_id, dev_phase);

-- ── Intent-to-Action Vector baselines ────────────────────────
-- Stores the per-phase "Biological Constant": the measured transit
-- time from the thought-origin node (Fp1, node 1) to the terminal
-- grounding nodes (PLANTAR_L=41 / PLANTAR_R=42).
-- At runtime, any live signal is checked against this. An RF-injected
-- thought that reaches the plantar nodes too fast (no corticospinal
-- latency) is PATTERN_INJECTION fraud.
CREATE TABLE IF NOT EXISTS intent_action_baselines (
  id                  BIGSERIAL    PRIMARY KEY,
  twin_id             UUID         NOT NULL REFERENCES twin_identity(id),
  dev_phase           dev_phase    NOT NULL,
  -- Origin: typically Fp1 (node 1) or Cz (node 10) for motor cortex
  origin_node_id      SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  -- Terminal: PLANTAR_L (41) or PLANTAR_R (42)
  terminal_node_id    SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  -- Measured transit statistics over the phase window
  mean_transit_ms     REAL         NOT NULL,
  std_transit_ms      REAL         NOT NULL DEFAULT 0,
  min_transit_ms      REAL,
  max_transit_ms      REAL,
  sample_count        INT          NOT NULL DEFAULT 0,
  -- Fraud detection window derived at lock time
  -- A live transit outside [mean - 3σ, mean + 3σ] triggers PATTERN_INJECTION
  lower_bound_ms      REAL,        -- mean_transit_ms - 3 * std_transit_ms
  upper_bound_ms      REAL,        -- mean_transit_ms + 3 * std_transit_ms
  -- Path distance used for conduction calculation
  path_distance_cm    REAL,
  -- Immutability
  is_locked           BOOLEAN      NOT NULL DEFAULT FALSE,
  locked_at           TIMESTAMPTZ,
  dna_root_sig        TEXT,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (twin_id, dev_phase, origin_node_id, terminal_node_id)
);

CREATE INDEX IF NOT EXISTS iab_twin_phase_idx
  ON intent_action_baselines (twin_id, dev_phase);

-- Locked baselines are immutable.
CREATE OR REPLACE FUNCTION prevent_locked_iab_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.is_locked THEN
    RAISE EXCEPTION
      'Intent-action baseline % (twin=%, phase=%) is locked — immutable record',
      OLD.id, OLD.twin_id, OLD.dev_phase
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER lock_intent_action_baselines
  BEFORE UPDATE OR DELETE ON intent_action_baselines
  FOR EACH ROW EXECUTE FUNCTION prevent_locked_iab_mutation();

-- ── Intent-to-Action live events ─────────────────────────────
-- Each row is one measured origin→terminal transit in a live session.
-- fraud_score is populated by verify_biological_integrity().
CREATE TABLE IF NOT EXISTS intent_action_events (
  id                  BIGSERIAL    PRIMARY KEY,
  twin_id             UUID         NOT NULL REFERENCES twin_identity(id),
  sensor_id           TEXT         NOT NULL,
  detected_at         TIMESTAMPTZ  NOT NULL,
  origin_node_id      SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  terminal_node_id    SMALLINT     NOT NULL REFERENCES mesh_nodes(id),
  origin_at           TIMESTAMPTZ  NOT NULL,
  terminal_at         TIMESTAMPTZ  NOT NULL,
  transit_ms          REAL         NOT NULL,
  -- Fraud detection output
  baseline_id         INT          REFERENCES intent_action_baselines(id),
  baseline_mean_ms    REAL,
  baseline_std_ms     REAL,
  deviation_sigma     REAL,        -- (transit_ms - baseline_mean) / baseline_std
  fraud_score         REAL,        -- 0.0 = identical to baseline, 1.0 = maximum anomaly
  is_synthetic        BOOLEAN      NOT NULL DEFAULT FALSE,
  -- set TRUE when |deviation_sigma| > 3 (outside calibration bounds)
  anomaly_id          INT          REFERENCES mesh_anomalies(id),
  metadata            JSONB
);

CREATE INDEX IF NOT EXISTS iae_twin_ts_idx
  ON intent_action_events (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS iae_synthetic_idx
  ON intent_action_events (twin_id, is_synthetic) WHERE is_synthetic = TRUE;

-- ── RPC: lock_calibration_phase ───────────────────────────────
-- Called when a dev_phase ends (e.g. subject turns 6, 13, 18).
-- Locks all calibration_era_baselines and intent_action_baselines
-- for the given twin + phase, writing the dna_root_sig commitment.
-- Once called, those rows can never be modified.
CREATE OR REPLACE FUNCTION lock_calibration_phase(
  p_twin_id   UUID,
  p_phase     dev_phase,
  p_dna_sig   TEXT       -- SHA-256(biological_hash || phase || locked_at)
)
RETURNS TABLE (
  baselines_locked  bigint,
  iab_locked        bigint,
  locked_at         timestamptz
)
LANGUAGE plpgsql AS $$
DECLARE
  v_now   TIMESTAMPTZ := NOW();
  v_ceb   BIGINT;
  v_iab   BIGINT;
BEGIN
  UPDATE calibration_era_baselines
  SET    is_locked = TRUE, locked_at = v_now, dna_root_sig = p_dna_sig
  WHERE  twin_id  = p_twin_id
    AND  dev_phase = p_phase
    AND  is_locked = FALSE;
  GET DIAGNOSTICS v_ceb = ROW_COUNT;

  UPDATE intent_action_baselines
  SET    is_locked = TRUE, locked_at = v_now, dna_root_sig = p_dna_sig
  WHERE  twin_id  = p_twin_id
    AND  dev_phase = p_phase
    AND  is_locked = FALSE;
  GET DIAGNOSTICS v_iab = ROW_COUNT;

  -- Recompute fraud detection bounds on any newly locked iab rows
  UPDATE intent_action_baselines
  SET    lower_bound_ms = mean_transit_ms - 3.0 * std_transit_ms,
         upper_bound_ms = mean_transit_ms + 3.0 * std_transit_ms
  WHERE  twin_id  = p_twin_id
    AND  dev_phase = p_phase
    AND  is_locked = TRUE
    AND  lower_bound_ms IS NULL;

  RETURN QUERY SELECT v_ceb, v_iab, v_now;
END;
$$;

-- ── RPC: verify_biological_integrity ─────────────────────────
-- Core fraud-detection function. Measures a live transit_ms against
-- the locked calibration baseline and returns a fraud_score.
-- Also writes an intent_action_events row and, if synthetic, inserts
-- a PATTERN_INJECTION anomaly into mesh_anomalies.
CREATE OR REPLACE FUNCTION verify_biological_integrity(
  p_twin_id           UUID,
  p_origin_node_id    SMALLINT,   -- typically 1 (Fp1) or 10 (Cz)
  p_terminal_node_id  SMALLINT,   -- typically 41 (PLANTAR_L) or 42 (PLANTAR_R)
  p_origin_at         TIMESTAMPTZ,
  p_terminal_at       TIMESTAMPTZ,
  p_sensor_id         TEXT
)
RETURNS TABLE (
  event_id         bigint,
  transit_ms       real,
  baseline_mean_ms real,
  baseline_std_ms  real,
  deviation_sigma  real,
  fraud_score      real,
  is_synthetic     boolean,
  verdict          text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_transit    REAL;
  v_base       RECORD;
  v_dev_sigma  REAL;
  v_fraud      REAL;
  v_synthetic  BOOLEAN;
  v_eid        BIGINT;
  v_anid       BIGINT;
BEGIN
  v_transit := EXTRACT(EPOCH FROM (p_terminal_at - p_origin_at)) * 1000.0;

  -- Find the most recent locked baseline for this origin→terminal pair
  SELECT *
  INTO   v_base
  FROM   intent_action_baselines
  WHERE  twin_id          = p_twin_id
    AND  origin_node_id   = p_origin_node_id
    AND  terminal_node_id = p_terminal_node_id
    AND  is_locked        = TRUE
  ORDER BY locked_at DESC
  LIMIT 1;

  IF v_base IS NULL THEN
    -- No calibration baseline exists; record the transit but cannot score it
    INSERT INTO intent_action_events
      (twin_id, sensor_id, detected_at, origin_node_id, terminal_node_id,
       origin_at, terminal_at, transit_ms, fraud_score, is_synthetic)
    VALUES
      (p_twin_id, p_sensor_id, NOW(), p_origin_node_id, p_terminal_node_id,
       p_origin_at, p_terminal_at, v_transit, 0, FALSE)
    RETURNING id INTO v_eid;

    RETURN QUERY SELECT v_eid, v_transit, NULL::real, NULL::real,
                        NULL::real, 0::real, FALSE,
                        'no calibration baseline — transit recorded, scoring deferred'::text;
    RETURN;
  END IF;

  -- Compute deviation in standard deviations
  v_dev_sigma := CASE
    WHEN v_base.std_transit_ms = 0 THEN 0
    ELSE (v_transit - v_base.mean_transit_ms) / v_base.std_transit_ms
  END;

  -- Fraud score: sigmoid-like normalisation; |3σ| → ~0.95, |5σ| → ~1.0
  v_fraud     := LEAST(1.0, ABS(v_dev_sigma) / 5.0);

  -- Synthetic flag: outside ±3σ calibration bounds
  v_synthetic := ABS(v_dev_sigma) > 3.0;

  -- Write event
  INSERT INTO intent_action_events
    (twin_id, sensor_id, detected_at, origin_node_id, terminal_node_id,
     origin_at, terminal_at, transit_ms,
     baseline_id, baseline_mean_ms, baseline_std_ms,
     deviation_sigma, fraud_score, is_synthetic)
  VALUES
    (p_twin_id, p_sensor_id, NOW(), p_origin_node_id, p_terminal_node_id,
     p_origin_at, p_terminal_at, v_transit,
     v_base.id, v_base.mean_transit_ms, v_base.std_transit_ms,
     v_dev_sigma, v_fraud, v_synthetic)
  RETURNING id INTO v_eid;

  -- If synthetic, raise a PATTERN_INJECTION anomaly
  IF v_synthetic THEN
    INSERT INTO mesh_anomalies
      (twin_id, detected_at, anomaly_type, affected_nodes, deviation_score,
       alert_level, metadata)
    VALUES
      (p_twin_id, NOW(), 'PATTERN_INJECTION',
       ARRAY[p_origin_node_id::int, p_terminal_node_id::int],
       v_fraud,
       CASE WHEN ABS(v_dev_sigma) > 5 THEN 'CRITICAL' ELSE 'WARNING' END,
       jsonb_build_object(
         'transit_ms',       v_transit,
         'baseline_mean_ms', v_base.mean_transit_ms,
         'deviation_sigma',  v_dev_sigma,
         'fraud_score',      v_fraud,
         'calibration_phase', v_base.dev_phase,
         'intent_action_event_id', v_eid
       ))
    RETURNING id INTO v_anid;

    UPDATE intent_action_events SET anomaly_id = v_anid WHERE id = v_eid;
  END IF;

  RETURN QUERY SELECT
    v_eid,
    v_transit,
    v_base.mean_transit_ms,
    v_base.std_transit_ms,
    v_dev_sigma,
    v_fraud,
    v_synthetic,
    CASE
      WHEN NOT v_synthetic            THEN 'AUTHENTIC — within calibration bounds'
      WHEN ABS(v_dev_sigma) <= 5.0    THEN 'WARNING — outside ±3σ calibration baseline (possible synthetic)'
      ELSE                                 'CRITICAL — outside ±5σ: PATTERN_INJECTION likely'
    END::text AS verdict;
END;
$$;

-- ── RPC: get_calibration_summary ─────────────────────────────
-- Returns the locked baseline statistics for all phases of a twin,
-- grouped by dev_phase. Used by LLM context loaders (Gemini/Gemma)
-- to understand the subject's developmental architecture before
-- generating code, motion, or arousal-authenticity comparisons.
CREATE OR REPLACE FUNCTION get_calibration_summary(p_twin_id UUID)
RETURNS TABLE (
  dev_phase          text,
  node_count         bigint,
  locked             boolean,
  locked_at          timestamptz,
  token_types        text[],
  mean_latency_ms    real,
  chemical_snapshot  jsonb
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
  SELECT
    ceb.dev_phase::text,
    COUNT(*)                                             AS node_count,
    BOOL_AND(ceb.is_locked)                             AS locked,
    MAX(ceb.locked_at)                                  AS locked_at,
    ARRAY_AGG(DISTINCT ceb.token_type::text)            AS token_types,
    AVG(ceb.mean_latency_ms)::real                      AS mean_latency_ms,
    -- Aggregate chemical markers from frozen snapshots in this phase
    (SELECT jsonb_object_agg(key, AVG(value::text::real))
     FROM mesh_frozen_snapshots mfs
     CROSS JOIN LATERAL jsonb_each(mfs.chemical_markers)
     WHERE mfs.twin_id    = p_twin_id
       AND mfs.dev_phase  = ceb.dev_phase
       AND mfs.chemical_markers IS NOT NULL
    )                                                    AS chemical_snapshot
  FROM calibration_era_baselines ceb
  WHERE ceb.twin_id = p_twin_id
  GROUP BY ceb.dev_phase
  ORDER BY CASE ceb.dev_phase
    WHEN 'PRIMITIVE_MESH'    THEN 1
    WHEN 'COORDINATION_SYNC' THEN 2
    WHEN 'HORMONAL_OVERWRITE' THEN 3
    WHEN 'ADULT'             THEN 4
  END;
END;
$$;
