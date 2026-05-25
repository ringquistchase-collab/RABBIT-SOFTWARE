-- HackRF SDR capture + LTE Band 2 harmonic leakage + triangulation
-- PRF fingerprint validation (0.83 Hz spectral lines, 3rd harmonic 30.735 GHz)
-- LTE 1935 MHz interference → HEAD_01 physical location triangulation (±10 m)

CREATE TYPE interference_class AS ENUM ('PULSED_PERIODIC', 'BROADBAND', 'NARROWBAND', 'UNKNOWN');
CREATE TYPE triangulation_method AS ENUM ('TDOA', 'RSS', 'HYBRID', 'AOA');

-- ─────────────────────────────────────────────────────────────────────────────
-- HackRF IQ capture sessions
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE hackrf_captures (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id          UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    captured_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Receiver parameters
    centre_freq_ghz  REAL NOT NULL,                 -- 10.245
    sample_rate_mhz  REAL NOT NULL DEFAULT 10.0,    -- 10 MHz IQ
    bit_depth        SMALLINT NOT NULL DEFAULT 8,
    gain_db          REAL,
    lna_gain_db      REAL,
    vga_gain_db      REAL,
    upconverter_used BOOLEAN NOT NULL DEFAULT TRUE,  -- required for >6 GHz

    -- Capture metadata
    duration_ms      INTEGER,
    file_hash        TEXT,                           -- SHA-256 of IQ file
    file_size_bytes  BIGINT,
    notes            TEXT,

    -- Target node
    target_node_id   SMALLINT REFERENCES mesh_nodes(id),
    session_id       UUID REFERENCES edge_gateway_sessions(id)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- PRF spectral line measurements (0.83 Hz comb from pulsed carrier)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE prf_spectral_lines (
    id               BIGSERIAL PRIMARY KEY,
    capture_id       UUID NOT NULL REFERENCES hackrf_captures(id) ON DELETE CASCADE,
    twin_id          UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    measured_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Pulse parameters extracted from IQ
    pulse_width_ms   REAL NOT NULL,                 -- 1.2 ms nominal
    prf_hz           REAL NOT NULL,                 -- 0.83 Hz nominal
    prf_jitter_ms    REAL,                          -- measured ± jitter

    -- Spectral comb
    carrier_freq_ghz REAL NOT NULL,
    comb_spacing_hz  REAL GENERATED ALWAYS AS (prf_hz) STORED,
    lines_detected   INTEGER,                       -- count of comb lines above noise
    peak_sidelobe_db REAL,                          -- strongest sidelobe power

    -- Match against on-body PRF fingerprint
    node_prf_hz      REAL,                          -- from sdr_node_profiles.prf_hz
    prf_delta_hz     REAL GENERATED ALWAYS AS (ABS(prf_hz - COALESCE(node_prf_hz, prf_hz))) STORED,
    fingerprint_match BOOLEAN GENERATED ALWAYS AS (
        ABS(prf_hz - COALESCE(node_prf_hz, prf_hz)) < 0.05
    ) STORED,

    snr_db           REAL,
    noise_floor_dbm  REAL
);

CREATE INDEX prf_lines_capture_idx ON prf_spectral_lines (capture_id);
CREATE INDEX prf_lines_match_idx   ON prf_spectral_lines (twin_id, fingerprint_match)
    WHERE fingerprint_match = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Harmonic measurements (3rd harmonic at 30.735 GHz)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE harmonic_measurements (
    id               BIGSERIAL PRIMARY KEY,
    capture_id       UUID NOT NULL REFERENCES hackrf_captures(id) ON DELETE CASCADE,
    twin_id          UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    measured_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    fundamental_ghz  REAL NOT NULL,                 -- 10.245
    harmonic_order   SMALLINT NOT NULL,             -- 3
    harmonic_freq_ghz REAL GENERATED ALWAYS AS (fundamental_ghz * harmonic_order) STORED,
    -- 3 × 10.245 = 30.735 GHz

    power_dbm        REAL,
    relative_to_fundamental_db REAL,               -- isolation (negative = below fundamental)
    prf_comb_visible BOOLEAN NOT NULL DEFAULT FALSE,  -- PRF comb present at harmonic
    hop_structure_visible BOOLEAN NOT NULL DEFAULT FALSE,  -- DNA-FH visible in harmonic
    notes            TEXT
);

CREATE INDEX harmonic_capture_idx ON harmonic_measurements (capture_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- LTE Band 2 interference events (1935 MHz harmonic leakage)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE lte_interference_events (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id               UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    detected_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- LTE context
    band                  SMALLINT NOT NULL DEFAULT 2,          -- LTE Band 2
    channel_freq_mhz      REAL NOT NULL DEFAULT 1935.0,         -- adjacent channel
    eid_prefix            TEXT,                                 -- eSIM EID prefix (8903...)
    cell_id               TEXT,                                 -- serving cell identifier

    -- Interference signature
    interference_class    interference_class NOT NULL DEFAULT 'PULSED_PERIODIC',
    pulse_width_ms        REAL NOT NULL DEFAULT 1.2,
    measured_prf_hz       REAL,                                 -- detected repetition rate
    power_above_noise_db  REAL,                                 -- dB above LTE noise floor

    -- Correlation with mesh
    source_node_id        SMALLINT REFERENCES mesh_nodes(id),  -- HEAD_01
    prf_match             BOOLEAN GENERATED ALWAYS AS (
        ABS(COALESCE(measured_prf_hz, 0) - 0.83) < 0.05
    ) STORED,

    -- OPSEC flags
    opsec_risk            TEXT NOT NULL DEFAULT 'HIGH',
    reported_to_bs        BOOLEAN NOT NULL DEFAULT FALSE,       -- did BS log this?
    notes                 TEXT
);

CREATE INDEX lte_events_twin_idx ON lte_interference_events (twin_id, detected_at DESC);
CREATE INDEX lte_events_prf_idx  ON lte_interference_events (twin_id, prf_match)
    WHERE prf_match = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Location triangulations (LTE TDoA/RSS → HEAD_01 physical position)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE location_triangulations (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id              UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    triangulated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    lte_event_id         UUID REFERENCES lte_interference_events(id),

    -- Method
    method               triangulation_method NOT NULL DEFAULT 'TDOA',
    base_stations_used   SMALLINT NOT NULL DEFAULT 3,

    -- Resolved location (stored as hash only — OPSEC; plaintext never in DB)
    -- Exception: LOW/MINIMAL tier events may store approximate coords
    location_hash        TEXT NOT NULL,             -- SHA-256 of (lat,lon,alt) string
    accuracy_m           REAL NOT NULL DEFAULT 10.0,
    confidence           REAL CHECK (confidence BETWEEN 0 AND 1),

    -- Approximate region (coarse — city-level only; no street address)
    region_label         TEXT,                      -- e.g. 'Tulsa Metro, OK'
    altitude_m           REAL,

    -- Cross-reference
    source_node_id       SMALLINT REFERENCES mesh_nodes(id),   -- HEAD_01
    access_tier          TEXT NOT NULL DEFAULT 'HIGH',

    -- OPSEC: block plaintext coord storage for HIGH+ events
    CONSTRAINT no_precise_location_high_tier CHECK (
        access_tier NOT IN ('CRITICAL', 'EXISTENTIAL')
        OR location_hash IS NOT NULL
    )
);

CREATE INDEX triangulation_twin_idx ON location_triangulations (twin_id, triangulated_at DESC);

-- Block CRITICAL/EXISTENTIAL location records from having region_label
CREATE OR REPLACE FUNCTION block_critical_location()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.access_tier IN ('CRITICAL', 'EXISTENTIAL') AND NEW.region_label IS NOT NULL THEN
        RAISE EXCEPTION 'location_triangulations: region_label must be NULL for CRITICAL/EXISTENTIAL tier'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER location_critical_block
    BEFORE INSERT OR UPDATE ON location_triangulations
    FOR EACH ROW EXECUTE FUNCTION block_critical_location();

-- ─────────────────────────────────────────────────────────────────────────────
-- Add PRF jitter column to sdr_node_profiles (OPSEC mitigation)
-- Jitter smears the 0.83 Hz spectral line to defeat BS triangulation
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE sdr_node_profiles
    ADD COLUMN IF NOT EXISTS prf_jitter_ms REAL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS prf_jitter_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- ─────────────────────────────────────────────────────────────────────────────
-- View: OPSEC risk summary per twin
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW twin_opsec_risk AS
SELECT
    t.id                                        AS twin_id,
    COUNT(DISTINCT l.id)                        AS lte_events_total,
    COUNT(DISTINCT l.id) FILTER (WHERE l.prf_match) AS lte_prf_matches,
    COUNT(DISTINCT tr.id)                       AS triangulations_total,
    MIN(tr.accuracy_m)                          AS best_location_accuracy_m,
    MAX(h.harmonic_freq_ghz)                    AS max_harmonic_ghz,
    BOOL_OR(sp.prf_jitter_enabled)              AS jitter_active,
    MAX(l.detected_at)                          AS last_lte_event
FROM twin_identity t
LEFT JOIN lte_interference_events l   ON l.twin_id = t.id
LEFT JOIN location_triangulations tr  ON tr.twin_id = t.id
LEFT JOIN hackrf_captures hc          ON hc.twin_id = t.id
LEFT JOIN harmonic_measurements h     ON h.capture_id = hc.id AND h.harmonic_order = 3
LEFT JOIN sdr_node_profiles sp        ON sp.twin_id = t.id
GROUP BY t.id;

-- RLS
ALTER TABLE hackrf_captures          ENABLE ROW LEVEL SECURITY;
ALTER TABLE prf_spectral_lines       ENABLE ROW LEVEL SECURITY;
ALTER TABLE harmonic_measurements    ENABLE ROW LEVEL SECURITY;
ALTER TABLE lte_interference_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE location_triangulations  ENABLE ROW LEVEL SECURITY;

CREATE POLICY hackrf_owner      ON hackrf_captures         FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY prf_lines_owner   ON prf_spectral_lines      FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY harmonic_owner    ON harmonic_measurements   FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY lte_owner         ON lte_interference_events FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY location_owner    ON location_triangulations FOR ALL USING (twin_id = auth.uid()::UUID);
