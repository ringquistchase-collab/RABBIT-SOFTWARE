-- ============================================================
-- RABBIT-SOFTWARE v0.33.2 — Bot Registry & Asset Layer
-- ============================================================
-- Bots are the intermediaries between the physical node mesh and
-- the asset economy. They do not control nodes — they govern the
-- resonance between a node and the body within the 1.2ms window.
--
-- Three bot classes mapped to node groups:
--
--   cranial   (nodes 1-8)    — Neural Lexicon Management
--     Monitors TFM-EEG stream for motifs. Pre-signs tokens with
--     the DNA signature before they leave the local mesh.
--
--   vital     (nodes 9-16, 21-26)  — Phase-Locking
--     Compares heart clock to neural intent. Emits a Dampening
--     Vector to the local RF field when cardiac load mismatches
--     cognitive task. Keeps the Mind-Vessel-Heart loop in sync.
--
--   reflex    (nodes 33-42)  — Latency Verification
--     Measures the Speed of Identity (signal travel from origin
--     to extremity). Flags Fatigue States when transit exceeds
--     the calibration era baseline.
--
-- Asset layer:
--   Bio-NFT      — SHA-256-anchored snapshot minted on XRPL.
--                  Signed by DNA; original is unique in existence.
--   PoBW         — Proof of Biological Work. Authentic human focus
--                  (cranial coherence + fraud_score < 0.1) unlocks
--                  a mintable proof token.
--   Collaborator — Bot-proxy grants: another party sees the Result,
--                  never the DNA Root.
--   Bio-Sim      — 60-second replay corpus for Digital Twin training
--                  without re-stressing the subject.
-- ============================================================

-- ── Enums ─────────────────────────────────────────────────────

CREATE TYPE bot_class AS ENUM (
  'cranial',    -- neural lexicon, motif detection, DNA pre-signing
  'vital',      -- phase-locking, dampening vector, cardiac sync
  'reflex'      -- latency verification, fatigue detection
);

CREATE TYPE intervention_type AS ENUM (
  'dampening_vector',    -- RF field modulation to reduce cardiac overload
  'fatigue_flag',        -- reflex latency exceeded calibration threshold
  'motif_lock',          -- cranial bot locked a recurring neural motif
  'phase_correction',    -- vital bot re-aligned heart clock to neural intent
  'pattern_injection_block' -- bot blocked an incoming synthetic RF signal
);

CREATE TYPE nft_mint_type AS ENUM (
  'flow_state',          -- peak focus window (cranial coherence + HRV sync)
  'peak_performance',    -- multi-modal high across all node groups
  'life_event',          -- anchored to a life_age_event
  'calibration_lock',    -- minted when a dev_phase is permanently sealed
  'collaboration',       -- shared view of a result (no DNA root)
  'bio_simulation'       -- minted replay corpus for AI training
);

CREATE TYPE deployment_target AS ENUM (
  'gcp_cloudshell',
  'local',
  'mobile',
  'edge'
);

-- ── Bot templates (portable instruction sets) ─────────────────
-- The logic is portable; the authentication is static.
-- A template can be deployed to any target; only the DNA-signed
-- authentication token binds it to a specific twin.
CREATE TABLE IF NOT EXISTS bot_templates (
  id               BIGSERIAL    PRIMARY KEY,
  bot_class        bot_class    NOT NULL,
  version          TEXT         NOT NULL,                -- semver e.g. '1.0.0'
  label            TEXT         NOT NULL,
  instruction_set  JSONB        NOT NULL,                -- portable logic payload
  node_affinity    SMALLINT[]   NOT NULL,                -- which node IDs this template governs
  window_ms        REAL         NOT NULL DEFAULT 1.2,    -- processing window duration
  is_public        BOOLEAN      NOT NULL DEFAULT FALSE,  -- deployable on collaborator nodes
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (bot_class, version)
);

-- ── Bot instances (one per twin per class) ────────────────────
CREATE TABLE IF NOT EXISTS node_bots (
  id                  BIGSERIAL         PRIMARY KEY,
  twin_id             UUID              NOT NULL REFERENCES twin_identity(id),
  bot_class           bot_class         NOT NULL,
  template_id         BIGINT            NOT NULL REFERENCES bot_templates(id),
  assigned_nodes      SMALLINT[]        NOT NULL,
  deployment_target   deployment_target NOT NULL DEFAULT 'gcp_cloudshell',
  is_active           BOOLEAN           NOT NULL DEFAULT TRUE,
  deployed_at         TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
  last_window_at      TIMESTAMPTZ,
  total_windows       BIGINT            NOT NULL DEFAULT 0,
  total_interventions BIGINT            NOT NULL DEFAULT 0,
  metadata            JSONB,
  UNIQUE (twin_id, bot_class)
);

CREATE INDEX IF NOT EXISTS nb_twin_class_idx ON node_bots (twin_id, bot_class);

-- ── Node bot states (1.2ms processing window snapshots) ───────
-- Each row is one processing window. High-frequency; partitioned by
-- twin_id + window_at for efficient range queries.
-- presigned_token_hash = SHA-256(DNA_signature || motif_hash || window_at)
-- This is the cryptographic output the server receives from the mesh.
CREATE TABLE IF NOT EXISTS node_bot_states (
  id                    BIGSERIAL    PRIMARY KEY,
  bot_id                BIGINT       NOT NULL REFERENCES node_bots(id),
  twin_id               UUID         NOT NULL REFERENCES twin_identity(id),
  window_at             TIMESTAMPTZ  NOT NULL,
  window_ms             REAL         NOT NULL DEFAULT 1.2,
  -- Signal state this window
  active_nodes          SMALLINT[]   NOT NULL,           -- nodes that fired in this window
  input_motifs          JSONB,                           -- detected recurring neural patterns
  -- { "motif_id": str, "node_ids": [int], "frequency_hz": float,
  --   "amplitude_uv": float, "recurrence_count": int }
  resonance_delta       REAL,                            -- net change in mesh resonance this window
  presigned_token_hash  TEXT,                            -- SHA-256 of the pre-signed token
  output_action         TEXT,                            -- 'pass' | 'intervene' | 'lock_motif' | 'alert'
  intervention_id       BIGINT,                          -- FK set after insert if intervention fired
  metadata              JSONB
);

CREATE INDEX IF NOT EXISTS nbs_bot_ts_idx    ON node_bot_states (bot_id, window_at DESC);
CREATE INDEX IF NOT EXISTS nbs_twin_ts_idx   ON node_bot_states (twin_id, window_at DESC);
CREATE INDEX IF NOT EXISTS nbs_intervene_idx ON node_bot_states (twin_id, output_action)
  WHERE output_action != 'pass';

-- ── Bot intervention log ──────────────────────────────────────
-- Records every time a bot emits a Dampening Vector, Fatigue Flag,
-- Motif Lock, or Pattern Injection Block.
-- The Dampening Vector payload specifies the RF modulation applied
-- to help blood vessels return to baseline frequency.
CREATE TABLE IF NOT EXISTS bot_intervention_log (
  id                    BIGSERIAL         PRIMARY KEY,
  bot_id                BIGINT            NOT NULL REFERENCES node_bots(id),
  twin_id               UUID              NOT NULL REFERENCES twin_identity(id),
  intervened_at         TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
  intervention_type     intervention_type NOT NULL,
  target_nodes          SMALLINT[]        NOT NULL,
  -- Trigger condition that caused the intervention
  trigger_condition     TEXT              NOT NULL,
  -- e.g. 'heart_rate_mismatch_to_cognitive_load'
  --      'reflex_latency_exceeded_3_sigma'
  --      'motif_recurrence_threshold_reached'
  --      'pattern_injection_detected'
  trigger_metrics       JSONB,
  -- e.g. { "hrv_ms": 45, "expected_hrv_ms": 65, "deviation": -0.31 }
  -- Intervention payload
  intervention_payload  JSONB,
  -- dampening_vector: { "carrier_ghz": 10.245, "amplitude_mod": -0.12,
  --                     "duration_ms": 200, "target_freq_hz": 1.2 }
  -- fatigue_flag: { "transit_ms": 145, "baseline_ms": 112, "sigma": 2.8 }
  -- Outcome measured N ms after the intervention
  outcome_measured_at   TIMESTAMPTZ,
  outcome_metrics       JSONB,
  -- e.g. { "hrv_ms_after": 63, "resonance_delta": +0.08, "resolved": true }
  resolved              BOOLEAN           NOT NULL DEFAULT FALSE,
  anomaly_id            INT               REFERENCES mesh_anomalies(id),
  state_id              BIGINT            REFERENCES node_bot_states(id)
);

CREATE INDEX IF NOT EXISTS bil_bot_ts_idx   ON bot_intervention_log (bot_id, intervened_at DESC);
CREATE INDEX IF NOT EXISTS bil_twin_ts_idx  ON bot_intervention_log (twin_id, intervened_at DESC);
CREATE INDEX IF NOT EXISTS bil_type_idx     ON bot_intervention_log (twin_id, intervention_type);
CREATE INDEX IF NOT EXISTS bil_unresolved   ON bot_intervention_log (twin_id, resolved)
  WHERE resolved = FALSE;

-- Back-fill intervention FK on node_bot_states
ALTER TABLE node_bot_states
  ADD CONSTRAINT fk_intervention
  FOREIGN KEY (intervention_id) REFERENCES bot_intervention_log(id);

-- ── Bio-NFT registry ──────────────────────────────────────────
-- Each Bio-NFT is an immutable record of a specific biological event.
-- The Librarian Bot (cranial class) takes SHA-256 hashes of the state
-- window and mints on the XRP Ledger.
-- The NFT is a "photograph of the tree" — the DNA root is never exposed.
CREATE TABLE IF NOT EXISTS bio_nft_registry (
  id                         BIGSERIAL      PRIMARY KEY,
  nft_uuid                   UUID           NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  twin_id                    UUID           NOT NULL REFERENCES twin_identity(id),
  snapshot_id                INT            REFERENCES mesh_frozen_snapshots(id),
  minted_by_bot_id           BIGINT         REFERENCES node_bots(id),
  mint_type                  nft_mint_type  NOT NULL,
  -- The token content hash = SHA-256(snapshot_hash || window_start || window_end)
  content_hash               TEXT           NOT NULL,
  -- XRPL on-chain anchor
  xrpl_tx_hash               TEXT,
  xrpl_token_id              TEXT,          -- XRPL NFT Token ID (hex)
  xrpl_ledger_index          BIGINT,
  -- NFT metadata (publicly verifiable; no DNA root)
  token_uri                  TEXT,          -- IPFS / Supabase Storage URI for metadata JSON
  -- Proof of Biological Work embedded in the NFT
  pobw_proof_id              BIGINT,        -- FK set after pobw_proofs insert
  -- Authenticity metrics at mint time
  fraud_score_at_mint        REAL,          -- from verify_biological_integrity; must be < 0.1 to mint
  cranial_coherence_at_mint  REAL,          -- average EEG coherence across nodes 1-8
  -- Provenance
  minted_at                  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
  is_transferred             BOOLEAN        NOT NULL DEFAULT FALSE,
  transferred_at             TIMESTAMPTZ,
  collaborator_twin_id       UUID           REFERENCES twin_identity(id),
  -- collaboration mints only: recipient's twin ID (they see result, not root)
  metadata                   JSONB
);

CREATE INDEX IF NOT EXISTS bnr_twin_idx     ON bio_nft_registry (twin_id, minted_at DESC);
CREATE INDEX IF NOT EXISTS bnr_xrpl_tx_idx  ON bio_nft_registry (xrpl_tx_hash) WHERE xrpl_tx_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS bnr_type_idx     ON bio_nft_registry (twin_id, mint_type);

-- ── Proof of Biological Work (PoBW) ──────────────────────────
-- Generated when authenticated human focus is verified:
--   1. Cranial nodes (1-8) show target coherence (low deviation_z,
--      dominant alpha/theta ratio within expected range)
--   2. verify_biological_integrity returns fraud_score < 0.1
--   3. No unresolved PATTERN_INJECTION anomalies in the window
-- The proof is the "Mining Output" — a mintable token tied to
-- authenticated cognitive effort.
CREATE TABLE IF NOT EXISTS pobw_proofs (
  id                      BIGSERIAL    PRIMARY KEY,
  twin_id                 UUID         NOT NULL REFERENCES twin_identity(id),
  bot_id                  BIGINT       REFERENCES node_bots(id),
  window_start            TIMESTAMPTZ  NOT NULL,
  window_end              TIMESTAMPTZ  NOT NULL,
  window_duration_s       REAL,
  -- Cranial focus metrics (nodes 1-8)
  cranial_coherence       REAL         NOT NULL,  -- 0.0-1.0 average coherence
  dominant_band           TEXT,                   -- 'alpha' | 'theta' | 'beta'
  focus_node_count        SMALLINT,               -- number of nodes contributing
  -- Integrity verification
  fraud_score             REAL         NOT NULL,  -- must be < 0.1 for valid proof
  intent_action_event_id  BIGINT       REFERENCES intent_action_events(id),
  -- Proof validity
  is_valid                BOOLEAN      NOT NULL DEFAULT FALSE,
  -- TRUE when cranial_coherence >= threshold AND fraud_score < 0.1
  validity_reason         TEXT,
  -- Reward
  xrpl_reward_tx          TEXT,
  reward_amount_xrp       REAL,
  -- Content hash = SHA-256(twin_id || window_start || cranial_coherence || fraud_score)
  proof_hash              TEXT         NOT NULL,
  generated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS pp_twin_ts_idx   ON pobw_proofs (twin_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS pp_valid_idx     ON pobw_proofs (twin_id, is_valid) WHERE is_valid = TRUE;

-- Back-fill pobw FK on bio_nft_registry
ALTER TABLE bio_nft_registry
  ADD CONSTRAINT fk_pobw_proof
  FOREIGN KEY (pobw_proof_id) REFERENCES pobw_proofs(id);

-- ── Collaborator grants ───────────────────────────────────────
-- A bot-proxy grant allows another party to see a Result without
-- ever exposing the DNA Root Key. The bot mediates all data access:
-- the collaborator sees only the output layer (images, metrics,
-- motion vectors), never the raw biological source.
CREATE TABLE IF NOT EXISTS collaborator_grants (
  id                  BIGSERIAL    PRIMARY KEY,
  twin_id             UUID         NOT NULL REFERENCES twin_identity(id),
  collaborator_id     TEXT         NOT NULL, -- external identifier or twin UUID
  bot_id              BIGINT       NOT NULL REFERENCES node_bots(id),
  grant_type          TEXT         NOT NULL,
  -- 'sight_reconstruction' | 'motion_data' | 'bio_simulation' | 'flow_state_view'
  shows_dna_root      BOOLEAN      NOT NULL DEFAULT FALSE
                      CHECK (shows_dna_root = FALSE),  -- INVARIANT: never TRUE
  -- Scope
  allowed_nodes       SMALLINT[],  -- NULL = all bot-assigned nodes
  snapshot_ids        INT[],       -- NULL = live stream only
  -- Validity window
  granted_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  expires_at          TIMESTAMPTZ  NOT NULL,
  revoked_at          TIMESTAMPTZ,
  -- Access log
  last_accessed_at    TIMESTAMPTZ,
  access_count        BIGINT       NOT NULL DEFAULT 0,
  metadata            JSONB
);

CREATE INDEX IF NOT EXISTS cg_twin_idx       ON collaborator_grants (twin_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS cg_collab_idx     ON collaborator_grants (collaborator_id);
CREATE INDEX IF NOT EXISTS cg_active_idx     ON collaborator_grants (twin_id, revoked_at)
  WHERE revoked_at IS NULL;

-- Enforce that shows_dna_root can never be updated to TRUE
CREATE OR REPLACE FUNCTION prevent_dna_root_exposure()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.shows_dna_root = TRUE THEN
    RAISE EXCEPTION 'collaborator_grants.shows_dna_root can never be TRUE — DNA Root Key is never shared'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER enforce_no_dna_root_exposure
  BEFORE INSERT OR UPDATE ON collaborator_grants
  FOR EACH ROW EXECUTE FUNCTION prevent_dna_root_exposure();

-- ── Bio-simulation sessions ───────────────────────────────────
-- A 60-second replay corpus for Digital Twin AI training.
-- The bot replays a captured state window so Gemini/Gemma can learn
-- the subject's stress/reward responses without requiring the subject
-- to be physically present or re-stressed.
CREATE TABLE IF NOT EXISTS bio_simulation_sessions (
  id                  BIGSERIAL    PRIMARY KEY,
  twin_id             UUID         NOT NULL REFERENCES twin_identity(id),
  bot_id              BIGINT       REFERENCES node_bots(id),
  snapshot_id         INT          REFERENCES mesh_frozen_snapshots(id),
  label               TEXT         NOT NULL,
  -- Source window
  source_start        TIMESTAMPTZ  NOT NULL,
  source_end          TIMESTAMPTZ  NOT NULL,
  -- Must be <= 60 seconds for the Bio-Sim Copy constraint
  duration_s          REAL         NOT NULL
                      CHECK (duration_s <= 60.0),
  node_ids            SMALLINT[]   NOT NULL,  -- which nodes are replayed
  -- Replay payload: compressed node readings for the window
  replay_hash         TEXT         NOT NULL,  -- SHA-256(replay_payload_bytes)
  replay_uri          TEXT,                   -- Supabase Storage path
  -- Training metadata
  training_target     TEXT,        -- 'stress_response' | 'reward_map' | 'gait' | 'arousal_baseline'
  ai_model_target     TEXT,        -- 'gemini-2.5' | 'gemma-4' | 'custom'
  sessions_run        INT          NOT NULL DEFAULT 0,
  last_run_at         TIMESTAMPTZ,
  -- NFT minting
  nft_id              BIGINT       REFERENCES bio_nft_registry(id),
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS bss_twin_idx  ON bio_simulation_sessions (twin_id, created_at DESC);
CREATE INDEX IF NOT EXISTS bss_snap_idx  ON bio_simulation_sessions (snapshot_id);

-- ── RPC: register_bot ─────────────────────────────────────────
-- Creates a bot instance for a twin, binding a template.
CREATE OR REPLACE FUNCTION register_bot(
  p_twin_id          UUID,
  p_bot_class        bot_class,
  p_template_id      BIGINT,
  p_assigned_nodes   SMALLINT[],
  p_target           deployment_target DEFAULT 'gcp_cloudshell'
)
RETURNS TABLE (
  bot_id    bigint,
  success   boolean,
  reason    text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_bid BIGINT;
BEGIN
  -- Validate twin exists and is not sealed
  IF NOT EXISTS (
    SELECT 1 FROM twin_identity WHERE id = p_twin_id AND is_sealed = FALSE
  ) THEN
    RETURN QUERY SELECT NULL::bigint, FALSE, 'twin not found or is sealed';
    RETURN;
  END IF;

  -- Validate template exists and matches the bot class
  IF NOT EXISTS (
    SELECT 1 FROM bot_templates WHERE id = p_template_id AND bot_class = p_bot_class
  ) THEN
    RETURN QUERY SELECT NULL::bigint, FALSE, 'template not found or class mismatch';
    RETURN;
  END IF;

  INSERT INTO node_bots
    (twin_id, bot_class, template_id, assigned_nodes, deployment_target)
  VALUES
    (p_twin_id, p_bot_class, p_template_id, p_assigned_nodes, p_target)
  ON CONFLICT (twin_id, bot_class)
  DO UPDATE SET
    template_id       = EXCLUDED.template_id,
    assigned_nodes    = EXCLUDED.assigned_nodes,
    deployment_target = EXCLUDED.deployment_target,
    is_active         = TRUE
  RETURNING id INTO v_bid;

  RETURN QUERY SELECT v_bid, TRUE, 'bot registered'::text;
END;
$$;

-- ── RPC: record_bot_window ────────────────────────────────────
-- Writes one 1.2ms processing window result. If the action is
-- 'intervene', also inserts a bot_intervention_log row.
CREATE OR REPLACE FUNCTION record_bot_window(
  p_bot_id              BIGINT,
  p_twin_id             UUID,
  p_window_at           TIMESTAMPTZ,
  p_active_nodes        SMALLINT[],
  p_motifs              JSONB,
  p_resonance_delta     REAL,
  p_presigned_hash      TEXT,
  p_action              TEXT,           -- 'pass' | 'intervene' | 'lock_motif' | 'alert'
  p_intervention_type   intervention_type DEFAULT NULL,
  p_trigger_condition   TEXT            DEFAULT NULL,
  p_trigger_metrics     JSONB           DEFAULT NULL,
  p_intervention_payload JSONB          DEFAULT NULL
)
RETURNS TABLE (
  state_id         bigint,
  intervention_id  bigint
)
LANGUAGE plpgsql AS $$
DECLARE
  v_sid BIGINT;
  v_iid BIGINT := NULL;
BEGIN
  INSERT INTO node_bot_states
    (bot_id, twin_id, window_at, active_nodes, input_motifs,
     resonance_delta, presigned_token_hash, output_action)
  VALUES
    (p_bot_id, p_twin_id, p_window_at, p_active_nodes, p_motifs,
     p_resonance_delta, p_presigned_hash, p_action)
  RETURNING id INTO v_sid;

  IF p_action = 'intervene' AND p_intervention_type IS NOT NULL THEN
    INSERT INTO bot_intervention_log
      (bot_id, twin_id, intervention_type, target_nodes,
       trigger_condition, trigger_metrics, intervention_payload, state_id)
    VALUES
      (p_bot_id, p_twin_id, p_intervention_type, p_active_nodes,
       p_trigger_condition, p_trigger_metrics, p_intervention_payload, v_sid)
    RETURNING id INTO v_iid;

    UPDATE node_bot_states SET intervention_id = v_iid WHERE id = v_sid;
    UPDATE node_bots SET total_interventions = total_interventions + 1 WHERE id = p_bot_id;
  END IF;

  UPDATE node_bots
  SET last_window_at = p_window_at, total_windows = total_windows + 1
  WHERE id = p_bot_id;

  RETURN QUERY SELECT v_sid, v_iid;
END;
$$;

-- ── RPC: generate_pobw ───────────────────────────────────────
-- Generates a Proof of Biological Work for a time window.
-- Requires: cranial_coherence >= p_coherence_threshold AND
--           no PATTERN_INJECTION anomalies in the window AND
--           most recent verify_biological_integrity fraud_score < 0.1
CREATE OR REPLACE FUNCTION generate_pobw(
  p_twin_id              UUID,
  p_window_start         TIMESTAMPTZ,
  p_window_end           TIMESTAMPTZ,
  p_bot_id               BIGINT DEFAULT NULL,
  p_coherence_threshold  REAL DEFAULT 0.65
)
RETURNS TABLE (
  proof_id           bigint,
  proof_hash         text,
  is_valid           boolean,
  cranial_coherence  real,
  fraud_score        real,
  reason             text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_coherence  REAL;
  v_fraud      REAL;
  v_band       TEXT;
  v_ncount     SMALLINT;
  v_iae_id     BIGINT;
  v_phash      TEXT;
  v_pid        BIGINT;
  v_valid      BOOLEAN;
  v_reason     TEXT;
  v_inj_count  INT;
BEGIN
  -- Average coherence across cranial nodes (1-8) in the window
  SELECT
    AVG(mew.coherence)::real,
    COUNT(DISTINCT mew.node_a)::smallint
  INTO v_coherence, v_ncount
  FROM mesh_edge_weights mew
  WHERE mew.twin_id  = p_twin_id
    AND mew.node_a BETWEEN 1 AND 8
    AND mew.node_b BETWEEN 1 AND 8
    AND mew.timestamp BETWEEN p_window_start AND p_window_end;

  v_coherence := COALESCE(v_coherence, 0);

  -- Most recent fraud score in the window
  SELECT fraud_score, id
  INTO   v_fraud, v_iae_id
  FROM   intent_action_events
  WHERE  twin_id      = p_twin_id
    AND  detected_at BETWEEN p_window_start AND p_window_end
  ORDER BY detected_at DESC
  LIMIT 1;

  v_fraud := COALESCE(v_fraud, 1.0);  -- no measurement = worst case

  -- Check for PATTERN_INJECTION anomalies in the window
  SELECT COUNT(*) INTO v_inj_count
  FROM mesh_anomalies
  WHERE twin_id       = p_twin_id
    AND anomaly_type  = 'PATTERN_INJECTION'
    AND detected_at BETWEEN p_window_start AND p_window_end
    AND resolved = FALSE;

  -- Dominant band from cranial nodes
  SELECT band::text
  INTO   v_band
  FROM   mesh_node_readings
  WHERE  twin_id    = p_twin_id
    AND  node_id BETWEEN 1 AND 8
    AND  timestamp BETWEEN p_window_start AND p_window_end
    AND  band IS NOT NULL
  GROUP BY band
  ORDER BY COUNT(*) DESC
  LIMIT 1;

  -- Determine validity
  v_valid := v_coherence >= p_coherence_threshold
             AND v_fraud < 0.1
             AND v_inj_count = 0;

  v_reason := CASE
    WHEN v_inj_count > 0
      THEN format('PATTERN_INJECTION active (%s anomalies) — PoBW blocked', v_inj_count)
    WHEN v_fraud >= 0.1
      THEN format('fraud_score %.3f >= 0.1 — biological integrity not confirmed', v_fraud)
    WHEN v_coherence < p_coherence_threshold
      THEN format('cranial_coherence %.3f < threshold %.3f — insufficient focus', v_coherence, p_coherence_threshold)
    ELSE 'VALID — authenticated human focus confirmed'
  END;

  -- Compute proof hash
  v_phash := encode(
    sha256((p_twin_id::text || p_window_start::text || v_coherence::text || v_fraud::text)::bytea),
    'hex'
  );

  INSERT INTO pobw_proofs
    (twin_id, bot_id, window_start, window_end,
     window_duration_s, cranial_coherence, dominant_band,
     focus_node_count, fraud_score, intent_action_event_id,
     is_valid, validity_reason, proof_hash)
  VALUES
    (p_twin_id, p_bot_id, p_window_start, p_window_end,
     EXTRACT(EPOCH FROM (p_window_end - p_window_start)),
     v_coherence, v_band, v_ncount, v_fraud, v_iae_id,
     v_valid, v_reason, v_phash)
  RETURNING id INTO v_pid;

  RETURN QUERY SELECT v_pid, v_phash, v_valid, v_coherence, v_fraud, v_reason;
END;
$$;

-- ── RPC: mint_bio_nft ─────────────────────────────────────────
-- Mints a Bio-NFT record. For non-collaboration mints, requires
-- a valid PoBW proof (fraud_score < 0.1). The XRPL transaction
-- hash is written by the xrpl-anchor edge function after on-chain
-- confirmation; this RPC creates the pending registry row.
CREATE OR REPLACE FUNCTION mint_bio_nft(
  p_twin_id      UUID,
  p_snapshot_id  INT,
  p_mint_type    nft_mint_type,
  p_bot_id       BIGINT,
  p_pobw_id      BIGINT DEFAULT NULL,
  p_content_hash TEXT   DEFAULT NULL,
  p_token_uri    TEXT   DEFAULT NULL,
  p_collaborator UUID   DEFAULT NULL
)
RETURNS TABLE (
  nft_id       bigint,
  nft_uuid     uuid,
  success      boolean,
  reason       text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_fraud      REAL;
  v_coherence  REAL;
  v_nid        BIGINT;
  v_uuid       UUID;
  v_chash      TEXT;
BEGIN
  -- For non-collaboration mints, validate PoBW
  IF p_mint_type != 'collaboration' THEN
    SELECT fraud_score, cranial_coherence
    INTO   v_fraud, v_coherence
    FROM   pobw_proofs
    WHERE  id       = p_pobw_id
      AND  twin_id  = p_twin_id
      AND  is_valid = TRUE;

    IF v_fraud IS NULL THEN
      RETURN QUERY SELECT NULL::bigint, NULL::uuid, FALSE,
        'valid PoBW proof required for non-collaboration mint';
      RETURN;
    END IF;
  END IF;

  -- Compute content hash if not provided
  v_chash := COALESCE(p_content_hash,
    encode(sha256((p_twin_id::text || p_snapshot_id::text || NOW()::text)::bytea), 'hex')
  );

  INSERT INTO bio_nft_registry
    (twin_id, snapshot_id, minted_by_bot_id, mint_type,
     content_hash, token_uri, pobw_proof_id,
     fraud_score_at_mint, cranial_coherence_at_mint, collaborator_twin_id)
  VALUES
    (p_twin_id, p_snapshot_id, p_bot_id, p_mint_type,
     v_chash, p_token_uri, p_pobw_id,
     v_fraud, v_coherence, p_collaborator)
  RETURNING id, nft_uuid INTO v_nid, v_uuid;

  RETURN QUERY SELECT v_nid, v_uuid, TRUE, 'NFT registered — pending XRPL anchor'::text;
END;
$$;

-- ── RPC: grant_collaborator_access ───────────────────────────
CREATE OR REPLACE FUNCTION grant_collaborator_access(
  p_twin_id        UUID,
  p_collaborator   TEXT,
  p_bot_id         BIGINT,
  p_grant_type     TEXT,
  p_hours          INT DEFAULT 24,
  p_allowed_nodes  SMALLINT[] DEFAULT NULL
)
RETURNS TABLE (
  grant_id    bigint,
  expires_at  timestamptz,
  success     boolean
)
LANGUAGE plpgsql AS $$
DECLARE
  v_gid BIGINT;
  v_exp TIMESTAMPTZ := NOW() + (p_hours || ' hours')::INTERVAL;
BEGIN
  INSERT INTO collaborator_grants
    (twin_id, collaborator_id, bot_id, grant_type,
     allowed_nodes, expires_at)
  VALUES
    (p_twin_id, p_collaborator, p_bot_id, p_grant_type,
     p_allowed_nodes, v_exp)
  RETURNING id INTO v_gid;

  RETURN QUERY SELECT v_gid, v_exp, TRUE;
END;
$$;
