-- ============================================================
-- RABBIT-SOFTWARE v0.33.3 — Simulation Corpus & Interstitial Methods
-- ============================================================
-- Supports the RabbitCorpusBuilder 60-second continuum simulation
-- (Deep Zen → System Shock) and the three interstitial methods that
-- operate between the state transitions.
--
-- State progression (intensity 0.0 → 1.0 over 60 seconds):
--   LOW_STRESS_ZEN    (0.0–0.3)  — alpha waves, 1.2ms latency baseline
--   TRANSITION        (0.3–0.7)  — "In-Between" corpus, leading indicators
--   HIGH_STRESS_SHOCK (0.7–1.0)  — beta/gamma dominance, Defeat Matrix
--
-- Three interstitial methods:
--
--   Drift-Watch      (Low → Mid)
--     Monitors the 1.2ms latency window. A drift to 1.3ms predicts
--     the subject entering TRANSITION before brainwaves confirm it.
--     This leading-indicator window is the most valuable predictive
--     signal in the corpus — the body signals state change before the
--     mind does.
--
--   Ghost-Signal Filter  (Mid → High)
--     Separates environmental RF noise from biological signal on the
--     10.245 GHz carrier. Ensures every stress-response token in the
--     HIGH_STRESS_SHOCK band is biological in origin, not injected.
--     SNR and noise-floor are stored per reading for audit.
--
--   Twin-Sync Lock   (High → Safe)
--     On SHOCK detection, hashes the last 5 seconds of bot-window
--     tokens into a composite hash and anchors it to the XRPL Ledger.
--     This creates an immutable timestamp of the "Defeat Matrix" event.
--     Also auto-creates a frozen snapshot and PoBW proof.
-- ============================================================

-- ── Simulation state enum ─────────────────────────────────────

CREATE TYPE simulation_state AS ENUM (
  'LOW_STRESS_ZEN',
  'TRANSITION',
  'HIGH_STRESS_SHOCK'
);

-- ── Corpus columns on mesh_node_readings ─────────────────────
-- NULL on all three columns = live (non-simulated) reading.

ALTER TABLE mesh_node_readings
  ADD COLUMN IF NOT EXISTS ghost_filtered    BOOLEAN,         -- TRUE = ghost filter was applied
  ADD COLUMN IF NOT EXISTS corpus_session_id BIGINT,          -- FK set after corpus_simulation_sessions exists
  ADD COLUMN IF NOT EXISTS intensity_level   REAL,            -- 0.0 (zen) → 1.0 (shock)
  ADD COLUMN IF NOT EXISTS sim_state         simulation_state; -- NULL for live data

-- ── Corpus simulation sessions ────────────────────────────────
-- One row per RabbitCorpusBuilder.simulate_continuum() call.
-- Tracks the full 60-second arc from start intensity to end intensity.
CREATE TABLE IF NOT EXISTS corpus_simulation_sessions (
  id                   BIGSERIAL         PRIMARY KEY,
  twin_id              UUID              NOT NULL REFERENCES twin_identity(id),
  sensor_id            TEXT              NOT NULL,
  started_at           TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
  duration_s           REAL              NOT NULL DEFAULT 60.0,
  node_count           SMALLINT          NOT NULL DEFAULT 26,
  resolution_ms        REAL              NOT NULL DEFAULT 1.2,
  carrier_hz           DOUBLE PRECISION  NOT NULL DEFAULT 10.245e9,
  intensity_start      REAL              NOT NULL DEFAULT 0.0,
  intensity_end        REAL              NOT NULL DEFAULT 1.0,
  -- Rolling counts updated as frames arrive
  frame_count          INT               NOT NULL DEFAULT 0,
  drift_event_count    INT               NOT NULL DEFAULT 0,
  ghost_filter_count   INT               NOT NULL DEFAULT 0,
  sync_lock_count      INT               NOT NULL DEFAULT 0,
  -- Final integrity hash = SHA-256(all frame hashes in order)
  session_hash         TEXT,
  status               TEXT              NOT NULL DEFAULT 'running',
  -- 'running' | 'completed' | 'locked'
  completed_at         TIMESTAMPTZ,
  snapshot_id          INT               REFERENCES mesh_frozen_snapshots(id),
  metadata             JSONB
);

CREATE INDEX IF NOT EXISTS css_twin_ts_idx ON corpus_simulation_sessions (twin_id, started_at DESC);

-- Back-fill FK on mesh_node_readings now that the table exists
ALTER TABLE mesh_node_readings
  ADD CONSTRAINT fk_corpus_session
  FOREIGN KEY (corpus_session_id) REFERENCES corpus_simulation_sessions(id);

-- ── Corpus simulation frames (one per second of the 60s window) ─
-- Stores the full per-node snapshot for each second. The Python
-- simulation produces one frame per second; each frame contains
-- all 26 nodes' token, phase_shift, and latency_ms values.
CREATE TABLE IF NOT EXISTS corpus_simulation_frames (
  id               BIGSERIAL         PRIMARY KEY,
  session_id       BIGINT            NOT NULL REFERENCES corpus_simulation_sessions(id),
  twin_id          UUID              NOT NULL REFERENCES twin_identity(id),
  timestamp_s      SMALLINT          NOT NULL,   -- 0-59 (second within the 60s window)
  intensity_level  REAL              NOT NULL,   -- 0.0-10.0 (the * 10 rounded value)
  sim_state        simulation_state  NOT NULL,
  -- Full node payload as produced by RabbitCorpusBuilder
  node_snapshot    JSONB             NOT NULL,
  -- { "NODE_01": { "token": "A7B2D9F1", "phase_shift": 0.0, "latency_ms": 1.2 }, ... }
  -- Per-frame aggregate metrics
  avg_latency_ms   REAL,
  avg_phase_shift  REAL,
  dominant_token   TEXT,            -- most frequent token prefix this frame
  -- Integrity
  frame_hash       TEXT             NOT NULL,   -- SHA-256(session_id || timestamp_s || node_snapshot)
  UNIQUE (session_id, timestamp_s)
);

CREATE INDEX IF NOT EXISTS csf_session_ts_idx  ON corpus_simulation_frames (session_id, timestamp_s);
CREATE INDEX IF NOT EXISTS csf_state_idx       ON corpus_simulation_frames (session_id, sim_state);
CREATE INDEX IF NOT EXISTS csf_intensity_idx   ON corpus_simulation_frames (session_id, intensity_level);

-- ── Method 1: Drift-Watch events (Low → Mid leading indicator) ─
-- Fired when reflex_latency_ms crosses above the drift threshold
-- before EEG band powers have confirmed a state change.
-- This is the most predictive signal: the body shows TRANSITION
-- before the mind does. lead_time_ms records how far ahead the
-- latency drift was relative to the band-power confirmation.
CREATE TABLE IF NOT EXISTS drift_watch_events (
  id                         BIGSERIAL   PRIMARY KEY,
  twin_id                    UUID        NOT NULL REFERENCES twin_identity(id),
  session_id                 BIGINT      REFERENCES corpus_simulation_sessions(id),
  sensor_id                  TEXT        NOT NULL,
  detected_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- Which kinetic node triggered the drift
  node_id                    SMALLINT    NOT NULL REFERENCES mesh_nodes(id),
  -- Latency values
  baseline_latency_ms        REAL        NOT NULL DEFAULT 1.2,
  observed_latency_ms        REAL        NOT NULL,
  drift_ratio                REAL        NOT NULL,  -- observed / baseline
  drift_threshold_ms         REAL        NOT NULL DEFAULT 1.3,
  -- Band powers at detection (to confirm bands have NOT yet changed)
  band_powers_at_detection   JSONB,
  -- Predicted transition
  predicted_state            simulation_state NOT NULL,
  predicted_intensity        REAL,
  -- Confirmation (filled in when band powers later confirm the prediction)
  confirmed_at               TIMESTAMPTZ,
  confirmed_state            simulation_state,
  lead_time_ms               REAL,        -- confirmed_at - detected_at in ms
  -- A negative lead_time would mean the prediction was wrong (body lagged mind)
  prediction_correct         BOOLEAN,
  frame_id                   BIGINT      REFERENCES corpus_simulation_frames(id)
);

CREATE INDEX IF NOT EXISTS dwe_twin_ts_idx    ON drift_watch_events (twin_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS dwe_session_idx    ON drift_watch_events (session_id);
CREATE INDEX IF NOT EXISTS dwe_unconfirmed    ON drift_watch_events (twin_id, confirmed_at)
  WHERE confirmed_at IS NULL;

-- ── Method 2: Ghost-Signal Filter log (Mid → High) ────────────
-- Records the result of filtering environmental RF noise from the
-- 10.245 GHz carrier on each vascular/kinetic reading.
-- is_biological = TRUE means the signal passed the filter and is
-- accepted as an authentic biological response.
-- Readings that fail the filter have ghost_filtered = TRUE on the
-- corresponding mesh_node_readings row.
CREATE TABLE IF NOT EXISTS ghost_signal_filter_log (
  id                  BIGSERIAL   PRIMARY KEY,
  twin_id             UUID        NOT NULL REFERENCES twin_identity(id),
  session_id          BIGINT      REFERENCES corpus_simulation_sessions(id),
  node_id             SMALLINT    NOT NULL REFERENCES mesh_nodes(id),
  reading_id          BIGINT      REFERENCES mesh_node_readings(id),
  filtered_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  carrier_freq_ghz    REAL        NOT NULL DEFAULT 10.245,
  -- Raw (unfiltered) signal
  raw_phase_shift_rad REAL        NOT NULL,
  -- Filter output
  filtered_phase_shift_rad REAL,  -- NULL if fully rejected as noise
  noise_floor_rad     REAL        NOT NULL,   -- estimated environmental noise amplitude
  snr_db              REAL,                   -- 10 * log10(signal / noise)
  filter_method       TEXT        NOT NULL DEFAULT 'adaptive_threshold',
  -- 'adaptive_threshold' | 'spectral_subtraction' | 'kalman'
  is_biological       BOOLEAN     NOT NULL,   -- TRUE = passed filter, biological in origin
  rejection_reason    TEXT,                   -- set when is_biological = FALSE
  -- 'snr_below_threshold' | 'freq_mismatch' | 'amplitude_ceiling' | 'correlation_fail'
  intensity_at_filter REAL,                   -- simulation intensity when filter ran
  sim_state           simulation_state
);

CREATE INDEX IF NOT EXISTS gsfl_twin_ts_idx   ON ghost_signal_filter_log (twin_id, filtered_at DESC);
CREATE INDEX IF NOT EXISTS gsfl_session_idx   ON ghost_signal_filter_log (session_id);
CREATE INDEX IF NOT EXISTS gsfl_rejected_idx  ON ghost_signal_filter_log (twin_id, is_biological)
  WHERE is_biological = FALSE;

-- ── Method 3: Twin-Sync Lock events (High → Safe) ─────────────
-- Triggered when intensity crosses the shock threshold (> 0.7).
-- Hashes the last 5 seconds of node_bot_states presigned_token_hash
-- values into a composite hash and submits for XRPL anchoring.
-- Also auto-creates a frozen snapshot and PoBW proof so the event
-- becomes a permanent verifiable record in the Digital Twin corpus.
CREATE TABLE IF NOT EXISTS twin_sync_lock_events (
  id                    BIGSERIAL   PRIMARY KEY,
  twin_id               UUID        NOT NULL REFERENCES twin_identity(id),
  session_id            BIGINT      REFERENCES corpus_simulation_sessions(id),
  sensor_id             TEXT        NOT NULL,
  triggered_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- The 5-second window that was hashed
  lock_window_start     TIMESTAMPTZ NOT NULL,  -- triggered_at - 5s
  lock_window_end       TIMESTAMPTZ NOT NULL,  -- triggered_at
  intensity_at_trigger  REAL        NOT NULL,  -- must be > 0.7
  sim_state_at_trigger  simulation_state NOT NULL DEFAULT 'HIGH_STRESS_SHOCK',
  -- Token hash array from node_bot_states in the window
  token_hashes          TEXT[]      NOT NULL,  -- presigned_token_hash values, ordered by window_at
  token_count           INT         NOT NULL,
  -- Composite hash = SHA-256(token_hashes[0] || token_hashes[1] || ... sorted by window_at)
  composite_hash        TEXT        NOT NULL,
  -- XRPL anchor (written by xrpl-anchor edge function after on-chain confirmation)
  xrpl_tx_hash          TEXT,
  xrpl_ledger_index     BIGINT,
  -- Auto-created linked records
  snapshot_id           INT         REFERENCES mesh_frozen_snapshots(id),
  pobw_id               BIGINT      REFERENCES pobw_proofs(id),
  nft_id                BIGINT      REFERENCES bio_nft_registry(id),
  -- Status
  anchor_status         TEXT        NOT NULL DEFAULT 'pending',
  -- 'pending' | 'anchored' | 'failed'
  anchored_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS tsle_twin_ts_idx    ON twin_sync_lock_events (twin_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS tsle_session_idx    ON twin_sync_lock_events (session_id);
CREATE INDEX IF NOT EXISTS tsle_pending_idx    ON twin_sync_lock_events (anchor_status)
  WHERE anchor_status = 'pending';
CREATE INDEX IF NOT EXISTS tsle_xrpl_tx_idx    ON twin_sync_lock_events (xrpl_tx_hash)
  WHERE xrpl_tx_hash IS NOT NULL;

-- ── RPC: begin_corpus_session ─────────────────────────────────
-- Opens a new simulation session. Returns the session_id that the
-- corpus-builder edge function attaches to every frame it ingests.
CREATE OR REPLACE FUNCTION begin_corpus_session(
  p_twin_id       UUID,
  p_sensor_id     TEXT,
  p_duration_s    REAL     DEFAULT 60.0,
  p_node_count    SMALLINT DEFAULT 26,
  p_resolution_ms REAL     DEFAULT 1.2,
  p_carrier_hz    DOUBLE PRECISION DEFAULT 10.245e9
)
RETURNS TABLE (session_id bigint, started_at timestamptz)
LANGUAGE plpgsql AS $$
DECLARE
  v_sid BIGINT;
  v_now TIMESTAMPTZ := NOW();
BEGIN
  INSERT INTO corpus_simulation_sessions
    (twin_id, sensor_id, started_at, duration_s, node_count, resolution_ms, carrier_hz)
  VALUES
    (p_twin_id, p_sensor_id, v_now, p_duration_s, p_node_count, p_resolution_ms, p_carrier_hz)
  RETURNING id INTO v_sid;

  RETURN QUERY SELECT v_sid, v_now;
END;
$$;

-- ── RPC: ingest_corpus_frame ──────────────────────────────────
-- Ingests one second-level frame from RabbitCorpusBuilder output.
-- Computes sim_state from intensity, stores the frame, and runs
-- the Drift-Watch check on latency values in the node snapshot.
-- Returns the frame_id and whether a drift event was detected.
CREATE OR REPLACE FUNCTION ingest_corpus_frame(
  p_session_id    BIGINT,
  p_twin_id       UUID,
  p_timestamp_s   SMALLINT,         -- 0-59
  p_intensity_raw REAL,             -- 0.0-1.0 (from sec/seconds in the Python sim)
  p_node_snapshot JSONB             -- { "NODE_01": { token, phase_shift, latency_ms }, ... }
)
RETURNS TABLE (
  frame_id         bigint,
  sim_state        simulation_state,
  drift_detected   boolean,
  drift_event_id   bigint,
  avg_latency_ms   real,
  avg_phase_shift  real
)
LANGUAGE plpgsql AS $$
DECLARE
  v_state     simulation_state;
  v_fid       BIGINT;
  v_fhash     TEXT;
  v_avg_lat   REAL;
  v_avg_phase REAL;
  v_drift     BOOLEAN := FALSE;
  v_deid      BIGINT;
  v_node_key  TEXT;
  v_node_val  JSONB;
  v_lat       REAL;
  v_phase     REAL;
  v_lat_sum   REAL := 0;
  v_phase_sum REAL := 0;
  v_n         INT  := 0;
  v_intensity REAL := p_intensity_raw * 10.0;  -- scale to 0-10 display range
  DRIFT_THRESHOLD_MS CONSTANT REAL := 1.3;
  BASELINE_LATENCY_MS CONSTANT REAL := 1.2;
BEGIN
  -- Classify simulation state from raw intensity (0.0-1.0)
  v_state := CASE
    WHEN p_intensity_raw < 0.3 THEN 'LOW_STRESS_ZEN'::simulation_state
    WHEN p_intensity_raw > 0.7 THEN 'HIGH_STRESS_SHOCK'::simulation_state
    ELSE 'TRANSITION'::simulation_state
  END;

  -- Aggregate metrics across nodes
  FOR v_node_key, v_node_val IN SELECT * FROM jsonb_each(p_node_snapshot)
  LOOP
    v_lat   := (v_node_val->>'latency_ms')::real;
    v_phase := (v_node_val->>'phase_shift')::real;
    IF v_lat IS NOT NULL THEN
      v_lat_sum   := v_lat_sum + v_lat;
      v_phase_sum := v_phase_sum + COALESCE(v_phase, 0);
      v_n := v_n + 1;
    END IF;
  END LOOP;

  v_avg_lat   := CASE WHEN v_n > 0 THEN v_lat_sum / v_n   ELSE NULL END;
  v_avg_phase := CASE WHEN v_n > 0 THEN v_phase_sum / v_n ELSE NULL END;

  -- Compute frame hash
  v_fhash := encode(
    sha256((p_session_id::text || p_timestamp_s::text || p_node_snapshot::text)::bytea),
    'hex'
  );

  INSERT INTO corpus_simulation_frames
    (session_id, twin_id, timestamp_s, intensity_level, sim_state,
     node_snapshot, avg_latency_ms, avg_phase_shift, frame_hash)
  VALUES
    (p_session_id, p_twin_id, p_timestamp_s, v_intensity, v_state,
     p_node_snapshot, v_avg_lat, v_avg_phase, v_fhash)
  RETURNING id INTO v_fid;

  -- Drift-Watch: fire when avg latency crosses threshold while state is still LOW/TRANSITION
  IF v_avg_lat IS NOT NULL
     AND v_avg_lat >= DRIFT_THRESHOLD_MS
     AND v_state != 'HIGH_STRESS_SHOCK'
  THEN
    -- Only fire if no unconfirmed drift event already open for this session
    IF NOT EXISTS (
      SELECT 1 FROM drift_watch_events
      WHERE session_id = p_session_id AND confirmed_at IS NULL
    ) THEN
      INSERT INTO drift_watch_events
        (twin_id, session_id, sensor_id, node_id,
         baseline_latency_ms, observed_latency_ms, drift_ratio,
         drift_threshold_ms, band_powers_at_detection,
         predicted_state, predicted_intensity, frame_id)
      VALUES
        (p_twin_id, p_session_id, 'corpus_builder',
         -- Use the first kinetic node (SACRUM_L = 33) as the representative node
         33,
         BASELINE_LATENCY_MS, v_avg_lat, v_avg_lat / BASELINE_LATENCY_MS,
         DRIFT_THRESHOLD_MS, NULL,
         'TRANSITION'::simulation_state, p_intensity_raw + 0.1, v_fid)
      RETURNING id INTO v_deid;

      v_drift := TRUE;
      UPDATE corpus_simulation_sessions
      SET drift_event_count = drift_event_count + 1
      WHERE id = p_session_id;
    END IF;
  END IF;

  -- Confirm any open Drift-Watch predictions that match the new state
  IF v_state = 'TRANSITION' OR v_state = 'HIGH_STRESS_SHOCK' THEN
    UPDATE drift_watch_events
    SET    confirmed_at     = NOW(),
           confirmed_state  = v_state,
           lead_time_ms     = EXTRACT(EPOCH FROM (NOW() - detected_at)) * 1000.0,
           prediction_correct = (predicted_state = v_state)
    WHERE  session_id   = p_session_id
      AND  confirmed_at IS NULL
      AND  predicted_state = v_state;
  END IF;

  -- Update frame counter on session
  UPDATE corpus_simulation_sessions
  SET frame_count = frame_count + 1
  WHERE id = p_session_id;

  RETURN QUERY SELECT v_fid, v_state, v_drift, v_deid, v_avg_lat, v_avg_phase;
END;
$$;

-- ── RPC: apply_ghost_filter ───────────────────────────────────
-- Evaluates whether a raw phase_shift reading on the 10.245 GHz
-- carrier is biological or environmental noise.
-- Uses an adaptive SNR threshold: signals with SNR < 6 dB are
-- rejected as environmental. This threshold holds for the carrier
-- frequency at typical indoor RF conditions.
-- Returns the filtered value and updates the reading's ghost_filtered flag.
CREATE OR REPLACE FUNCTION apply_ghost_filter(
  p_twin_id            UUID,
  p_session_id         BIGINT,
  p_node_id            SMALLINT,
  p_reading_id         BIGINT,
  p_raw_phase_shift    REAL,
  p_noise_floor_rad    REAL,
  p_carrier_freq_ghz   REAL DEFAULT 10.245,
  p_filter_method      TEXT DEFAULT 'adaptive_threshold'
)
RETURNS TABLE (
  filter_id              bigint,
  filtered_phase_shift   real,
  snr_db                 real,
  is_biological          boolean,
  rejection_reason       text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_snr        REAL;
  v_filtered   REAL;
  v_is_bio     BOOLEAN;
  v_reason     TEXT := NULL;
  v_fid        BIGINT;
  SNR_THRESHOLD_DB CONSTANT REAL := 6.0;
BEGIN
  -- SNR = 20 * log10(|signal| / noise_floor), floored to avoid -inf
  v_snr := CASE
    WHEN p_noise_floor_rad <= 0 THEN 60.0   -- perfect signal if no noise
    WHEN ABS(p_raw_phase_shift) <= 0 THEN -60.0
    ELSE 20.0 * LOG(ABS(p_raw_phase_shift) / p_noise_floor_rad)
  END;

  -- Determine if biological
  IF v_snr >= SNR_THRESHOLD_DB THEN
    v_is_bio   := TRUE;
    v_filtered := p_raw_phase_shift - SIGN(p_raw_phase_shift) * p_noise_floor_rad;
    -- Simple noise subtraction; a real Kalman pass would iterate
  ELSE
    v_is_bio   := FALSE;
    v_filtered := NULL;
    v_reason   := CASE
      WHEN v_snr < -20.0   THEN 'amplitude_ceiling'
      WHEN v_snr < 0        THEN 'snr_below_threshold'
      ELSE                       'correlation_fail'
    END;
  END IF;

  INSERT INTO ghost_signal_filter_log
    (twin_id, session_id, node_id, reading_id,
     carrier_freq_ghz, raw_phase_shift_rad, filtered_phase_shift_rad,
     noise_floor_rad, snr_db, filter_method, is_biological, rejection_reason)
  VALUES
    (p_twin_id, p_session_id, p_node_id, p_reading_id,
     p_carrier_freq_ghz, p_raw_phase_shift, v_filtered,
     p_noise_floor_rad, v_snr, p_filter_method, v_is_bio, v_reason)
  RETURNING id INTO v_fid;

  -- Mark the source reading as ghost-filtered
  UPDATE mesh_node_readings
  SET ghost_filtered = NOT v_is_bio
  WHERE id = p_reading_id;

  UPDATE corpus_simulation_sessions
  SET ghost_filter_count = ghost_filter_count + 1
  WHERE id = p_session_id;

  RETURN QUERY SELECT v_fid, v_filtered, v_snr, v_is_bio, v_reason;
END;
$$;

-- ── RPC: trigger_twin_sync_lock ───────────────────────────────
-- Fires when intensity crosses the shock threshold (> 0.7).
-- Collects the last 5 seconds of presigned_token_hash values from
-- node_bot_states, builds a composite hash, and creates the full
-- chain: sync_lock_event → frozen_snapshot → pobw_proof → bio_nft
-- (all pending XRPL anchor confirmation).
CREATE OR REPLACE FUNCTION trigger_twin_sync_lock(
  p_twin_id              UUID,
  p_session_id           BIGINT,
  p_sensor_id            TEXT,
  p_intensity            REAL,    -- must be > 0.7
  p_window_end           TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (
  lock_id          bigint,
  composite_hash   text,
  token_count      int,
  snapshot_id      int,
  pobw_id          bigint,
  nft_id           bigint,
  success          boolean,
  reason           text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_window_start  TIMESTAMPTZ := p_window_end - INTERVAL '5 seconds';
  v_tokens        TEXT[];
  v_composite     TEXT;
  v_lid           BIGINT;
  v_snap_id       INT;
  v_pobw_id       BIGINT;
  v_nft_id        BIGINT;
  v_snap_hash     TEXT;
  v_prev_hash     TEXT;
  v_chain_hash    TEXT;
  v_pobw_hash     TEXT;
  v_bot_id        BIGINT;
BEGIN
  IF p_intensity <= 0.7 THEN
    RETURN QUERY SELECT NULL::bigint, NULL::text, 0, NULL::int,
                        NULL::bigint, NULL::bigint, FALSE,
                        format('intensity %.2f <= 0.7 — shock threshold not reached', p_intensity);
    RETURN;
  END IF;

  -- Prevent duplicate locks within 5 seconds for the same session
  IF EXISTS (
    SELECT 1 FROM twin_sync_lock_events
    WHERE session_id  = p_session_id
      AND triggered_at > p_window_end - INTERVAL '5 seconds'
  ) THEN
    RETURN QUERY SELECT NULL::bigint, NULL::text, 0, NULL::int,
                        NULL::bigint, NULL::bigint, FALSE,
                        'duplicate lock suppressed — previous lock within 5s window';
    RETURN;
  END IF;

  -- Collect token hashes from node_bot_states for the last 5 seconds
  SELECT ARRAY_AGG(presigned_token_hash ORDER BY window_at)
  INTO   v_tokens
  FROM   node_bot_states
  WHERE  twin_id     = p_twin_id
    AND  window_at BETWEEN v_window_start AND p_window_end
    AND  presigned_token_hash IS NOT NULL;

  IF v_tokens IS NULL OR array_length(v_tokens, 1) = 0 THEN
    -- Fall back to corpus frame tokens if no bot windows are present
    SELECT ARRAY_AGG(frame_hash ORDER BY timestamp_s)
    INTO   v_tokens
    FROM   corpus_simulation_frames
    WHERE  session_id = p_session_id
      AND  timestamp_s BETWEEN
             EXTRACT(EPOCH FROM (p_window_end - v_window_start))::int - 5
             AND EXTRACT(EPOCH FROM (p_window_end - v_window_start))::int;
  END IF;

  v_tokens := COALESCE(v_tokens, ARRAY['no_tokens_in_window']);

  -- Composite hash = SHA-256(concatenation of all tokens in order)
  v_composite := encode(
    sha256(array_to_string(v_tokens, '')::bytea),
    'hex'
  );

  -- Look up the cranial bot for this twin
  SELECT id INTO v_bot_id
  FROM node_bots
  WHERE twin_id = p_twin_id AND bot_class = 'cranial' AND is_active = TRUE
  LIMIT 1;

  -- Create frozen snapshot for the shock window
  SELECT chain_hash INTO v_prev_hash
  FROM   mesh_frozen_snapshots
  WHERE  twin_id = p_twin_id
  ORDER BY captured_at DESC
  LIMIT 1;

  v_prev_hash := COALESCE(v_prev_hash, REPEAT('0', 64));

  v_snap_hash  := encode(sha256(v_composite::bytea), 'hex');
  v_chain_hash := encode(sha256((v_prev_hash || v_snap_hash)::bytea), 'hex');

  INSERT INTO mesh_frozen_snapshots
    (twin_id, label, captured_at, node_count,
     snapshot_hash, prev_hash, chain_hash,
     is_sealed, sealed_at,
     access_tier, dev_phase,
     metadata)
  VALUES
    (p_twin_id,
     format('twin_sync_lock | intensity=%.2f | session=%s', p_intensity, p_session_id),
     p_window_end, 26,
     v_snap_hash, v_prev_hash, v_chain_hash,
     TRUE, p_window_end,
     'LOW',
     'ADULT',
     jsonb_build_object(
       'trigger', 'twin_sync_lock',
       'intensity', p_intensity,
       'sim_state', 'HIGH_STRESS_SHOCK',
       'composite_hash', v_composite,
       'token_count', array_length(v_tokens, 1)
     ))
  RETURNING id INTO v_snap_id;

  -- Generate PoBW proof for the shock window
  v_pobw_hash := encode(
    sha256((p_twin_id::text || p_window_end::text || v_composite)::bytea),
    'hex'
  );

  INSERT INTO pobw_proofs
    (twin_id, bot_id, window_start, window_end, window_duration_s,
     cranial_coherence, fraud_score,
     is_valid, validity_reason, proof_hash)
  VALUES
    (p_twin_id, v_bot_id, v_window_start, p_window_end, 5.0,
     0.0,   -- coherence is zero at shock — this is a distress proof, not focus proof
     0.0,   -- fraud_score = 0 because the shock was biologically triggered
     TRUE, 'twin_sync_lock: HIGH_STRESS_SHOCK event anchored', v_pobw_hash)
  RETURNING id INTO v_pobw_id;

  -- Mint Bio-NFT (pending XRPL anchor)
  INSERT INTO bio_nft_registry
    (twin_id, snapshot_id, minted_by_bot_id, mint_type,
     content_hash, pobw_proof_id,
     fraud_score_at_mint, cranial_coherence_at_mint,
     metadata)
  VALUES
    (p_twin_id, v_snap_id, v_bot_id, 'life_event',
     v_composite, v_pobw_id,
     0.0, 0.0,
     jsonb_build_object(
       'trigger', 'twin_sync_lock',
       'intensity', p_intensity,
       'composite_hash', v_composite,
       'session_id', p_session_id
     ))
  RETURNING id INTO v_nft_id;

  -- Create the sync lock event record
  INSERT INTO twin_sync_lock_events
    (twin_id, session_id, sensor_id, triggered_at,
     lock_window_start, lock_window_end, intensity_at_trigger,
     token_hashes, token_count, composite_hash,
     snapshot_id, pobw_id, nft_id)
  VALUES
    (p_twin_id, p_session_id, p_sensor_id, p_window_end,
     v_window_start, p_window_end, p_intensity,
     v_tokens, array_length(v_tokens, 1), v_composite,
     v_snap_id, v_pobw_id, v_nft_id)
  RETURNING id INTO v_lid;

  -- Update session counters
  UPDATE corpus_simulation_sessions
  SET sync_lock_count = sync_lock_count + 1,
      snapshot_id     = v_snap_id
  WHERE id = p_session_id;

  RETURN QUERY SELECT
    v_lid, v_composite, array_length(v_tokens, 1),
    v_snap_id, v_pobw_id, v_nft_id, TRUE,
    'twin_sync_lock committed — pending XRPL anchor'::text;
END;
$$;

-- ── RPC: complete_corpus_session ──────────────────────────────
-- Seals a simulation session once all frames have been ingested.
-- Computes the final session_hash by chaining all frame_hash values,
-- marks the session complete, and records the completion time.
CREATE OR REPLACE FUNCTION complete_corpus_session(
  p_session_id  BIGINT,
  p_twin_id     UUID
)
RETURNS TABLE (
  session_id    bigint,
  session_hash  text,
  frame_count   int,
  status        text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_chain_input TEXT;
  v_hash        TEXT;
  v_fcount      INT;
BEGIN
  -- Build session hash by concatenating all frame hashes in order
  SELECT
    string_agg(frame_hash, '' ORDER BY timestamp_s),
    COUNT(*)::int
  INTO v_chain_input, v_fcount
  FROM corpus_simulation_frames
  WHERE session_id = p_session_id;

  v_hash := encode(sha256(COALESCE(v_chain_input, '')::bytea), 'hex');

  UPDATE corpus_simulation_sessions
  SET status       = 'completed',
      session_hash  = v_hash,
      completed_at  = NOW(),
      frame_count   = v_fcount
  WHERE id = p_session_id AND twin_id = p_twin_id;

  RETURN QUERY SELECT p_session_id, v_hash, v_fcount, 'completed'::text;
END;
$$;

-- ── View: corpus_session_summary ─────────────────────────────
-- Quick dashboard for any simulation session.
CREATE OR REPLACE VIEW corpus_session_summary AS
SELECT
  css.id                                        AS session_id,
  css.twin_id,
  css.started_at,
  css.duration_s,
  css.frame_count,
  css.drift_event_count,
  css.ghost_filter_count,
  css.sync_lock_count,
  css.status,
  css.session_hash,
  -- State distribution
  COUNT(csf.id) FILTER (WHERE csf.sim_state = 'LOW_STRESS_ZEN')    AS frames_low,
  COUNT(csf.id) FILTER (WHERE csf.sim_state = 'TRANSITION')         AS frames_transition,
  COUNT(csf.id) FILTER (WHERE csf.sim_state = 'HIGH_STRESS_SHOCK')  AS frames_shock,
  -- Latency arc
  MIN(csf.avg_latency_ms)                       AS min_latency_ms,
  MAX(csf.avg_latency_ms)                       AS max_latency_ms,
  AVG(csf.avg_latency_ms)::real                 AS mean_latency_ms,
  -- Phase shift arc
  MIN(csf.avg_phase_shift)                      AS min_phase_shift,
  MAX(csf.avg_phase_shift)                      AS max_phase_shift
FROM corpus_simulation_sessions css
LEFT JOIN corpus_simulation_frames csf ON csf.session_id = css.id
GROUP BY css.id;
