-- GSR SDR Capture + TFM-Tokenizer (EEG → discrete token vocabulary)
-- WRIST_L → HEAD_01 phase shift (φ=+0.06 rad → σ=2.1 S/m GSR proxy)
-- TFM-Tokenizer: STFT 1-50 Hz, masking p=0.15, 4096-token VQ-VAE codebook

-- ─────────────────────────────────────────────────────────────────────────────
-- GSR SDR readings (Galvanic Skin Response via body-coupled RF phase shift)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE gsr_readings (
    id                      BIGSERIAL PRIMARY KEY,
    twin_id                 UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    source_node_id          SMALLINT REFERENCES mesh_nodes(id),   -- WRIST_L
    dest_node_id            SMALLINT REFERENCES mesh_nodes(id),   -- HEAD_01
    sampled_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id              UUID REFERENCES edge_gateway_sessions(id),

    -- Phase measurement
    carrier_freq_ghz        REAL NOT NULL DEFAULT 10.245,
    phase_shift_rad         REAL NOT NULL,          -- φ measured − φ baseline
    phase_baseline_rad      REAL,                   -- φ from phase_coherence_baselines
    propagation_medium      TEXT NOT NULL DEFAULT 'skin',

    -- Conductivity proxy (GNU Radio derived)
    conductivity_proxy_s_m  REAL NOT NULL,          -- σ S/m; 2.1 = stress/active
    conductivity_baseline   REAL,                   -- resting σ from chemo_baselines
    conductivity_delta      REAL                    -- σ_measured − σ_baseline
        GENERATED ALWAYS AS (conductivity_proxy_s_m - COALESCE(conductivity_baseline, 0)) STORED,

    -- Derived stress state (σ thresholds)
    gsr_stress_label        TEXT GENERATED ALWAYS AS (
        CASE
            WHEN conductivity_proxy_s_m < 0.5  THEN 'CALM'
            WHEN conductivity_proxy_s_m < 1.5  THEN 'MILD_AROUSAL'
            WHEN conductivity_proxy_s_m < 2.5  THEN 'STRESS'
            ELSE                                     'ACUTE_STRESS'
        END
    ) STORED,

    -- GNU Radio processing metadata
    gnuradio_flowgraph      TEXT,                   -- flowgraph version/hash
    kalman_gain             REAL,                   -- Kalman filter gain used
    snr_db                  REAL,

    -- Cross-system links
    cross_modal_state_id    UUID REFERENCES cross_modal_states(id)
);

CREATE INDEX gsr_readings_twin_idx    ON gsr_readings (twin_id, sampled_at DESC);
CREATE INDEX gsr_readings_stress_idx  ON gsr_readings (twin_id, gsr_stress_label);

-- ─────────────────────────────────────────────────────────────────────────────
-- EEG token vocabulary (4096-entry VQ-VAE codebook)
-- One row per discrete token; populated at model training time
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE eeg_token_vocab (
    token_id        INTEGER PRIMARY KEY CHECK (token_id BETWEEN 0 AND 4095),
    token_label     TEXT NOT NULL UNIQUE,   -- 'token_θ0.64', 'token_γ12.3', etc.
    band            TEXT NOT NULL,          -- 'delta','theta','alpha','beta','gamma'
    freq_low_hz     REAL NOT NULL,
    freq_high_hz    REAL NOT NULL,
    power_db        REAL,                   -- representative band power
    cortex_region   TEXT,                   -- 'V1','V2','V4','MT','frontal','temporal', NULL
    pattern_label   TEXT,                   -- 'edge','color','motion','orient', NULL
    codebook_vector JSONB,                  -- VQ centroid embedding (optional storage)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed core tokens (representative set — full 4096 populated by training pipeline)
INSERT INTO eeg_token_vocab (token_id, token_label, band, freq_low_hz, freq_high_hz, power_db, cortex_region, pattern_label) VALUES
(  0, 'token_δ0.5',        'delta', 0.5,  4.0,   0.5,  NULL,       NULL),
(  1, 'token_δ2.1',        'delta', 0.5,  4.0,   2.1,  NULL,       NULL),
( 64, 'token_θ0.64',       'theta', 4.0,  8.0,   0.64, NULL,       NULL),
( 65, 'token_θ3.2',        'theta', 4.0,  8.0,   3.2,  NULL,       NULL),
( 66, 'token_θ_frontal',   'theta', 4.0,  8.0,   1.8,  'frontal',  NULL),
(128, 'token_α8.7',        'alpha', 8.0,  13.0,  8.7,  NULL,       NULL),
(129, 'token_α_visual',    'alpha', 8.0,  13.0,  6.2,  'V1',       'idle'),
(192, 'token_β15.4',       'beta',  13.0, 30.0, 15.4,  NULL,       NULL),
(193, 'token_β_motor',     'beta',  13.0, 30.0, 18.1,  'frontal',  'motor'),
(256, 'token_γ12.3',       'gamma', 30.0, 50.0, 12.3,  NULL,       NULL),
(257, 'token_V1_edge',     'gamma', 30.0, 45.0, 22.1,  'V1',       'edge'),
(258, 'token_V1_orient',   'gamma', 30.0, 45.0, 19.8,  'V1',       'orient'),
(259, 'token_V4_color',    'gamma', 40.0, 50.0, 31.1,  'V4',       'color'),
(260, 'token_V4_form',     'gamma', 40.0, 50.0, 28.4,  'V4',       'form'),
(261, 'token_MT_motion',   'gamma', 20.0, 40.0, 24.7,  'MT',       'motion'),
(262, 'token_γ31.1_V4',   'gamma', 40.0, 50.0, 31.1,  'V4',       'color');

-- ─────────────────────────────────────────────────────────────────────────────
-- EEG token sequences (TFM-Tokenizer output)
-- One row per tokenization window
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE eeg_token_sequences (
    id               BIGSERIAL PRIMARY KEY,
    twin_id          UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id          SMALLINT REFERENCES mesh_nodes(id),
    tokenized_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id       UUID REFERENCES edge_gateway_sessions(id),

    -- Input parameters
    channel_idx      SMALLINT NOT NULL DEFAULT 0,
    sample_rate_hz   REAL NOT NULL DEFAULT 256.0,
    window_start_ms  BIGINT,                    -- epoch ms of window start
    window_len_ms    INTEGER NOT NULL DEFAULT 1000,

    -- STFT parameters
    stft_window_samples INTEGER DEFAULT 256,
    stft_hop_samples    INTEGER DEFAULT 64,
    freq_low_hz         REAL DEFAULT 1.0,
    freq_high_hz        REAL DEFAULT 50.0,

    -- Masking
    mask_ratio       REAL NOT NULL DEFAULT 0.15 CHECK (mask_ratio BETWEEN 0 AND 1),
    masked_patches   INTEGER,                   -- count of masked time-freq patches

    -- Token output
    tokens           JSONB NOT NULL,            -- array of token_id integers
    token_labels     JSONB,                     -- array of token_label strings
    token_count      INTEGER GENERATED ALWAYS AS (jsonb_array_length(tokens)) STORED,

    -- Dominant band / region
    dominant_band    TEXT,                      -- 'theta','alpha','gamma', etc.
    dominant_region  TEXT,                      -- 'V1','V4','frontal', etc.

    -- Provenance
    provenance_hash  TEXT,                      -- SHA-3 from eeg_provenance_chain
    gsr_reading_id   BIGINT REFERENCES gsr_readings(id),
    cross_modal_id   UUID REFERENCES cross_modal_states(id)
);

CREATE INDEX eeg_tokens_twin_idx    ON eeg_token_sequences (twin_id, tokenized_at DESC);
CREATE INDEX eeg_tokens_session_idx ON eeg_token_sequences (session_id, tokenized_at DESC);
CREATE INDEX eeg_tokens_region_idx  ON eeg_token_sequences (twin_id, dominant_region);

-- ─────────────────────────────────────────────────────────────────────────────
-- Visual cortex events (V1/V4 pattern detection from token stream)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE visual_cortex_events (
    id                  BIGSERIAL PRIMARY KEY,
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id             SMALLINT REFERENCES mesh_nodes(id),
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id          UUID REFERENCES edge_gateway_sessions(id),

    cortex_region       TEXT NOT NULL CHECK (cortex_region IN ('V1','V2','V3','V4','V5','MT')),
    pattern_type        TEXT NOT NULL,              -- 'edge','color','motion','orient','form'

    -- Source token sequence
    token_sequence_id   BIGINT REFERENCES eeg_token_sequences(id),
    dominant_token_id   INTEGER REFERENCES eeg_token_vocab(token_id),

    -- Signal metrics
    gamma_power_db      REAL,                       -- γ band power at detection
    gamma_freq_hz       REAL,                       -- peak γ frequency
    onset_latency_ms    REAL,                       -- ms from stimulus to token onset

    -- Cross-modal: correlate with UWB gesture and intent
    uwb_gesture_id      BIGINT REFERENCES uwb_gesture_events(id),
    intent_correlated   BOOLEAN DEFAULT FALSE,

    confidence          REAL CHECK (confidence BETWEEN 0 AND 1),
    duration_ms         INTEGER
);

CREATE INDEX visual_events_twin_idx   ON visual_cortex_events (twin_id, detected_at DESC);
CREATE INDEX visual_events_region_idx ON visual_cortex_events (twin_id, cortex_region, detected_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- View: live tokenizer state per twin
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW twin_tokenizer_state AS
SELECT DISTINCT ON (s.twin_id)
    s.twin_id,
    s.tokenized_at,
    s.token_count,
    s.dominant_band,
    s.dominant_region,
    s.mask_ratio,
    g.phase_shift_rad,
    g.conductivity_proxy_s_m,
    g.gsr_stress_label,
    v.cortex_region          AS latest_visual_region,
    v.pattern_type           AS latest_visual_pattern,
    v.gamma_power_db
FROM eeg_token_sequences s
LEFT JOIN gsr_readings g    ON g.id = s.gsr_reading_id
LEFT JOIN visual_cortex_events v ON v.token_sequence_id = s.id
ORDER BY s.twin_id, s.tokenized_at DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Function: dynamic mask ratio from current stress state
-- Call before each tokenization window
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION get_mask_ratio(p_twin_id UUID)
RETURNS REAL LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
DECLARE
    v_stress TEXT;
    v_gsr    TEXT;
BEGIN
    SELECT stress_level::TEXT INTO v_stress
    FROM cross_modal_states
    WHERE twin_id = p_twin_id
    ORDER BY evaluated_at DESC
    LIMIT 1;

    SELECT gsr_stress_label INTO v_gsr
    FROM gsr_readings
    WHERE twin_id = p_twin_id
    ORDER BY sampled_at DESC
    LIMIT 1;

    RETURN CASE
        WHEN v_stress = 'ACUTE_DISTRESS'             THEN 0.30
        WHEN v_stress = 'STRESS' OR v_gsr = 'STRESS' THEN 0.20
        WHEN v_gsr = 'ACUTE_STRESS'                  THEN 0.25
        ELSE                                               0.15
    END;
END;
$$;

-- RLS
ALTER TABLE gsr_readings          ENABLE ROW LEVEL SECURITY;
ALTER TABLE eeg_token_vocab       ENABLE ROW LEVEL SECURITY;
ALTER TABLE eeg_token_sequences   ENABLE ROW LEVEL SECURITY;
ALTER TABLE visual_cortex_events  ENABLE ROW LEVEL SECURITY;

CREATE POLICY gsr_owner        ON gsr_readings         FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY vocab_read       ON eeg_token_vocab      FOR SELECT USING (TRUE);
CREATE POLICY tokens_owner     ON eeg_token_sequences  FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY visual_owner     ON visual_cortex_events FOR ALL USING (twin_id = auth.uid()::UUID);
