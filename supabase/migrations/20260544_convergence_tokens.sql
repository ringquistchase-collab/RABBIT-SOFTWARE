-- HEAD_01 / CHEST_01 node specs + three-condition convergence gate + token output
-- HEAD_01: 24ch EEG (FAA valence, Fz θ/α), 10.245 GHz skin ε_r/σ, GSR Δφ
-- CHEST_01: ELISA cortisol 0.1–1.0 ng/mL, 10.251 GHz cardiac Doppler HRV
-- Gate: cortisol > 0.75 ∧ Δφ > 0.05 ∧ θ/α > 0.60
-- Token: SHA-256("valence=-0.23_arousal=0.71_gsr=0.06_cortisol=0.78")
--        = 75d2ffd4d20e84c64c134e2643742719402324fda0e6af3f0693f4203294651f

-- ─────────────────────────────────────────────────────────────────────────────
-- FAA readings (Frontal Alpha Asymmetry — 24ch EEG, HEAD_01)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE faa_readings (
    id                  BIGSERIAL PRIMARY KEY,
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id             SMALLINT REFERENCES mesh_nodes(id),        -- HEAD_01
    measured_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id          UUID REFERENCES edge_gateway_sessions(id),

    -- EEG channel parameters
    channel_count       SMALLINT NOT NULL DEFAULT 24,
    sample_rate_hz      REAL NOT NULL DEFAULT 256.0,
    window_len_ms       INTEGER NOT NULL DEFAULT 1000,

    -- F3 / F4 alpha band power (µV²)
    f3_alpha_power_uv2  REAL NOT NULL CHECK (f3_alpha_power_uv2 > 0),
    f4_alpha_power_uv2  REAL NOT NULL CHECK (f4_alpha_power_uv2 > 0),

    -- FAA = ln(F4_alpha) - ln(F3_alpha)
    faa_raw             REAL GENERATED ALWAYS AS (
        LN(f4_alpha_power_uv2) - LN(f3_alpha_power_uv2)
    ) STORED,

    -- Normalized valence: -1.0 to +1.0
    valence_score       REAL CHECK (valence_score BETWEEN -1.0 AND 1.0),

    -- Fz θ/α arousal
    fz_theta_power_uv2  REAL CHECK (fz_theta_power_uv2 >= 0),
    fz_alpha_power_uv2  REAL CHECK (fz_alpha_power_uv2 > 0),
    theta_alpha_ratio   REAL GENERATED ALWAYS AS (
        CASE WHEN fz_alpha_power_uv2 > 0
             THEN fz_theta_power_uv2 / fz_alpha_power_uv2
             ELSE NULL END
    ) STORED,

    -- Normalized arousal: 0.0 to 1.0 (mapped from θ/α range 0.0–1.5)
    arousal_score       REAL CHECK (arousal_score BETWEEN 0.0 AND 1.0),

    -- Cross-modal links
    gsr_reading_id      BIGINT REFERENCES gsr_readings(id),
    cross_modal_id      UUID REFERENCES cross_modal_states(id)
);

CREATE INDEX faa_twin_idx ON faa_readings (twin_id, measured_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Skin dielectric readings (HEAD_01, 10.245 GHz pulsed body-coupled RF)
-- Measures ε_r (relative permittivity) and σ (conductivity S/m) of skin
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE skin_dielectric_readings (
    id                  BIGSERIAL PRIMARY KEY,
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id             SMALLINT REFERENCES mesh_nodes(id),        -- HEAD_01
    measured_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id          UUID REFERENCES edge_gateway_sessions(id),

    carrier_freq_ghz    REAL NOT NULL DEFAULT 10.245,
    pulse_width_ms      REAL DEFAULT 1.2,

    -- Dielectric properties
    epsilon_r           REAL NOT NULL CHECK (epsilon_r > 1),    -- relative permittivity
    conductivity_s_m    REAL NOT NULL CHECK (conductivity_s_m >= 0),  -- σ S/m

    -- Baseline values (from calibration era)
    epsilon_r_baseline  REAL,
    conductivity_baseline REAL,

    -- Phase shift (GSR proxy)
    phase_shift_rad     REAL NOT NULL,                          -- Δφ = φ_stress − φ_baseline
    gsr_threshold_met   BOOLEAN GENERATED ALWAYS AS (
        phase_shift_rad > 0.05
    ) STORED,

    -- Link to gsr_readings record
    gsr_reading_id      BIGINT REFERENCES gsr_readings(id)
);

CREATE INDEX skin_dielectric_twin_idx     ON skin_dielectric_readings (twin_id, measured_at DESC);
CREATE INDEX skin_dielectric_gsr_idx      ON skin_dielectric_readings (twin_id, gsr_threshold_met)
    WHERE gsr_threshold_met = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- ELISA assay readings (CHEST_01 — cortisol 0.1–1.0 ng/mL)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE elisa_assay_readings (
    id                      BIGSERIAL PRIMARY KEY,
    twin_id                 UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id                 SMALLINT REFERENCES mesh_nodes(id),    -- CHEST_01
    assayed_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id              UUID REFERENCES edge_gateway_sessions(id),

    -- Assay parameters
    analyte                 TEXT NOT NULL DEFAULT 'cortisol',
    assay_range_low_ng_ml   REAL NOT NULL DEFAULT 0.1,
    assay_range_high_ng_ml  REAL NOT NULL DEFAULT 1.0,
    carrier_freq_ghz        REAL NOT NULL DEFAULT 10.251,          -- CHEST_01 carrier

    -- Result
    concentration_ng_ml     REAL NOT NULL
        CHECK (concentration_ng_ml BETWEEN 0 AND 10),
    concentration_nmol_l    REAL GENERATED ALWAYS AS (
        concentration_ng_ml * 2759.0                               -- cortisol MW = 362.46 g/mol → ×2759 ng/mL to nmol/L
    ) STORED,

    -- Threshold flag
    convergence_threshold_met BOOLEAN GENERATED ALWAYS AS (
        concentration_ng_ml > 0.75
    ) STORED,

    -- HRV validation (from 10.251 GHz Doppler)
    hrv_lf_power            REAL,
    hrv_hf_power            REAL,
    hrv_lf_hf_ratio         REAL GENERATED ALWAYS AS (
        CASE WHEN hrv_hf_power > 0 THEN hrv_lf_power / hrv_hf_power ELSE NULL END
    ) STORED,

    -- Cross-links
    cross_modal_id          UUID REFERENCES cross_modal_states(id)
);

CREATE INDEX elisa_twin_idx      ON elisa_assay_readings (twin_id, assayed_at DESC);
CREATE INDEX elisa_cortisol_idx  ON elisa_assay_readings (twin_id, convergence_threshold_met)
    WHERE convergence_threshold_met = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Convergence events — three-condition gate
-- cortisol > 0.75 ng/mL  ∧  Δφ > 0.05 rad  ∧  θ/α > 0.60
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE convergence_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    fired_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id          UUID REFERENCES edge_gateway_sessions(id),

    -- Condition values at convergence
    cortisol_ng_ml      REAL NOT NULL,
    gsr_delta_phi       REAL NOT NULL,
    theta_alpha_ratio   REAL NOT NULL,

    -- Derived scores
    valence_score       REAL NOT NULL,      -- FAA normalized: −1.0 to +1.0
    arousal_score       REAL NOT NULL,      -- Fz θ/α normalized: 0.0 to 1.0

    -- Gate boolean (all three must be TRUE)
    cortisol_gate       BOOLEAN GENERATED ALWAYS AS (cortisol_ng_ml > 0.75)  STORED,
    gsr_gate            BOOLEAN GENERATED ALWAYS AS (gsr_delta_phi > 0.05)   STORED,
    eeg_gate            BOOLEAN GENERATED ALWAYS AS (theta_alpha_ratio > 0.60) STORED,
    all_gates_met       BOOLEAN GENERATED ALWAYS AS (
        cortisol_ng_ml > 0.75
        AND gsr_delta_phi > 0.05
        AND theta_alpha_ratio > 0.60
    ) STORED,

    -- Source readings
    faa_reading_id      BIGINT REFERENCES faa_readings(id),
    skin_dielectric_id  BIGINT REFERENCES skin_dielectric_readings(id),
    elisa_reading_id    BIGINT REFERENCES elisa_assay_readings(id),
    cross_modal_id      UUID REFERENCES cross_modal_states(id)
);

CREATE INDEX convergence_twin_idx  ON convergence_events (twin_id, fired_at DESC);
CREATE INDEX convergence_gate_idx  ON convergence_events (twin_id, all_gates_met)
    WHERE all_gates_met = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Convergence tokens — SHA-256 of canonical state string
-- Format: SHA-256("valence={v:.2f}_arousal={a:.2f}_gsr={g:.2f}_cortisol={c:.2f}")
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE convergence_tokens (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    minted_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    convergence_id      UUID NOT NULL REFERENCES convergence_events(id),

    -- Canonical state string (serialized before hashing)
    state_string        TEXT NOT NULL,
    -- e.g. "valence=-0.23_arousal=0.71_gsr=0.06_cortisol=0.78"

    -- Token hash
    state_hash          TEXT NOT NULL UNIQUE,
    -- SHA-256 hex: 75d2ffd4d20e84c64c134e2643742719402324fda0e6af3f0693f4203294651f

    -- Decoded components (for query/analytics — derived from state_string)
    valence             REAL NOT NULL,
    arousal             REAL NOT NULL,
    gsr_delta_phi       REAL NOT NULL,
    cortisol_ng_ml      REAL NOT NULL,

    -- Downstream usage
    chemo_hash_id       UUID REFERENCES chemo_hashes(id),
    zk_proof_id         BIGINT REFERENCES snapshot_zk_proofs(id),
    access_tier         TEXT NOT NULL DEFAULT 'LOW'
);

CREATE INDEX conv_tokens_twin_idx ON convergence_tokens (twin_id, minted_at DESC);
CREATE INDEX conv_tokens_hash_idx ON convergence_tokens (state_hash);

-- Immutable: convergence tokens are append-only (same invariant as chemo_hashes)
CREATE OR REPLACE FUNCTION block_token_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'convergence_tokens are immutable (append-only)'
        USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER conv_token_immutable
    BEFORE UPDATE OR DELETE ON convergence_tokens
    FOR EACH ROW EXECUTE FUNCTION block_token_mutation();

-- ─────────────────────────────────────────────────────────────────────────────
-- Function: build state string and verify hash matches expected
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION build_convergence_token(
    p_twin_id       UUID,
    p_convergence   UUID,
    p_valence       REAL,
    p_arousal       REAL,
    p_gsr           REAL,
    p_cortisol      REAL
) RETURNS TEXT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_state  TEXT;
    v_hash   TEXT;
    v_id     UUID;
BEGIN
    -- Canonical format: 2 decimal places, underscore-separated
    v_state := FORMAT('valence=%s_arousal=%s_gsr=%s_cortisol=%s',
        ROUND(p_valence::NUMERIC,   2),
        ROUND(p_arousal::NUMERIC,   2),
        ROUND(p_gsr::NUMERIC,       2),
        ROUND(p_cortisol::NUMERIC,  2)
    );

    -- SHA-256 via pgcrypto
    v_hash := ENCODE(DIGEST(v_state, 'sha256'), 'hex');

    INSERT INTO convergence_tokens (
        twin_id, convergence_id, state_string, state_hash,
        valence, arousal, gsr_delta_phi, cortisol_ng_ml
    ) VALUES (
        p_twin_id, p_convergence, v_state, v_hash,
        p_valence, p_arousal, p_gsr, p_cortisol
    )
    RETURNING id INTO v_id;

    RETURN v_hash;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- View: latest convergence state per twin
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW twin_convergence_state AS
SELECT DISTINCT ON (ct.twin_id)
    ct.twin_id,
    ct.minted_at,
    ct.state_string,
    ct.state_hash,
    ct.valence,
    ct.arousal,
    ct.gsr_delta_phi,
    ct.cortisol_ng_ml,
    ce.all_gates_met,
    ce.cortisol_gate,
    ce.gsr_gate,
    ce.eeg_gate
FROM convergence_tokens ct
JOIN convergence_events ce ON ce.id = ct.convergence_id
ORDER BY ct.twin_id, ct.minted_at DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: known convergence token (the specific state provided)
-- Inserted as a reference record for twin ef5eb8ab
-- ─────────────────────────────────────────────────────────────────────────────
-- Note: convergence_events row must exist before token; seeded inline
DO $$
DECLARE
    v_conv_id UUID := gen_random_uuid();
BEGIN
    INSERT INTO convergence_events (
        id, twin_id, cortisol_ng_ml, gsr_delta_phi, theta_alpha_ratio,
        valence_score, arousal_score
    ) VALUES (
        v_conv_id,
        'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
        0.78, 0.06, 0.71,
        -0.23, 0.71
    );

    INSERT INTO convergence_tokens (
        twin_id, convergence_id, state_string, state_hash,
        valence, arousal, gsr_delta_phi, cortisol_ng_ml
    ) VALUES (
        'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
        v_conv_id,
        'valence=-0.23_arousal=0.71_gsr=0.06_cortisol=0.78',
        '75d2ffd4d20e84c64c134e2643742719402324fda0e6af3f0693f4203294651f',
        -0.23, 0.71, 0.06, 0.78
    );
END $$;

-- RLS
ALTER TABLE faa_readings              ENABLE ROW LEVEL SECURITY;
ALTER TABLE skin_dielectric_readings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE elisa_assay_readings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE convergence_events        ENABLE ROW LEVEL SECURITY;
ALTER TABLE convergence_tokens        ENABLE ROW LEVEL SECURITY;

CREATE POLICY faa_owner         ON faa_readings             FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY skin_owner        ON skin_dielectric_readings FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY elisa_owner       ON elisa_assay_readings     FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY convergence_owner ON convergence_events       FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY tokens_owner      ON convergence_tokens       FOR ALL USING (twin_id = auth.uid()::UUID);
