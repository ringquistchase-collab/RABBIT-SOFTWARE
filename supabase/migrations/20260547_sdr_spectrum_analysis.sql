-- SDR Spectrum Analysis Schema
-- Tables: spectrum_recordings, spectrum_sessions, frequency_peaks
-- Connects to existing mesh_nodes, sdr_node_profiles, twin_identity

CREATE TYPE sdr_device_type AS ENUM ('hackrf', 'rtlsdr', 'airspy', 'mock');
CREATE TYPE peak_classification AS ENUM (
    'carrier', 'harmonic', 'prf_sideband', 'lte_leakage',
    'uwb_pulse', 'dna_resonance', 'noise_floor', 'unknown'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- spectrum_sessions: one session = one continuous SDR capture run
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE spectrum_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id         SMALLINT REFERENCES mesh_nodes(id),
    device_type     sdr_device_type NOT NULL DEFAULT 'hackrf',

    -- Capture parameters
    center_freq_mhz NUMERIC(14, 6) NOT NULL,
    sample_rate_mhz NUMERIC(10, 4) NOT NULL DEFAULT 10.0,
    gain_db         REAL DEFAULT 0.0,

    -- Timing
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    duration_ms     INTEGER GENERATED ALWAYS AS (
        CASE WHEN ended_at IS NOT NULL
             THEN EXTRACT(EPOCH FROM (ended_at - started_at))::INTEGER * 1000
             ELSE NULL END
    ) STORED,

    -- Integrity
    session_hash    TEXT,                           -- SHA3-256 of all recording hashes
    recording_count INTEGER NOT NULL DEFAULT 0,
    notes           TEXT,

    CONSTRAINT session_times CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX idx_sessions_user ON spectrum_sessions (user_id, started_at DESC);
CREATE INDEX idx_sessions_node ON spectrum_sessions (node_id, started_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- spectrum_recordings: one snapshot = one FFT frame at a point in time
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE spectrum_recordings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    session_id      UUID REFERENCES spectrum_sessions(id) ON DELETE SET NULL,
    node_id         SMALLINT REFERENCES mesh_nodes(id),

    -- Frequency parameters
    frequency_mhz   NUMERIC(14, 6) NOT NULL,        -- center frequency
    bandwidth_mhz   NUMERIC(10, 4) NOT NULL DEFAULT 10.0,
    sample_rate_mhz NUMERIC(10, 4) NOT NULL DEFAULT 10.0,
    fft_size        INTEGER NOT NULL DEFAULT 1024,

    -- Signal measurements
    power_dbm       REAL NOT NULL,
    noise_floor_dbm REAL,
    snr_db          REAL GENERATED ALWAYS AS (
        CASE WHEN noise_floor_dbm IS NOT NULL
             THEN power_dbm - noise_floor_dbm
             ELSE NULL END
    ) STORED,
    peak_count      INTEGER NOT NULL DEFAULT 0,

    -- IQ data reference (raw samples never stored inline)
    iq_data_hash    TEXT,                           -- SHA3-256(IQ samples) — not raw data
    iq_bucket_path  TEXT,                           -- Supabase Storage path if archived

    -- Spectrum array (binned power values, optional inline storage)
    spectrum_bins   JSONB,                          -- [{freq_mhz, power_dbm}, ...]

    -- Context
    access_tier     TEXT NOT NULL DEFAULT 'LOW',
    metadata        JSONB NOT NULL DEFAULT '{}',
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_recordings_user_timestamp ON spectrum_recordings (user_id, timestamp DESC);
CREATE INDEX idx_recordings_frequency      ON spectrum_recordings (frequency_mhz);
CREATE INDEX idx_recordings_session        ON spectrum_recordings (session_id, timestamp DESC);
CREATE INDEX idx_recordings_node           ON spectrum_recordings (node_id, timestamp DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- frequency_peaks: detected signal peaks within a recording
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE frequency_peaks (
    id              BIGSERIAL PRIMARY KEY,
    recording_id    UUID NOT NULL REFERENCES spectrum_recordings(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,

    -- Peak characteristics
    peak_freq_mhz   NUMERIC(14, 6) NOT NULL,
    peak_power_dbm  REAL NOT NULL,
    bandwidth_khz   REAL,                           -- 3 dB bandwidth
    snr_db          REAL,                           -- populated by ingest (peak_power_dbm - noise_floor_dbm)

    -- Classification
    peak_type       peak_classification NOT NULL DEFAULT 'unknown',

    -- Cross-reference to known frequencies in this project
    is_dna_resonance    BOOLEAN GENERATED ALWAYS AS (
        peak_freq_mhz BETWEEN 10229.0 AND 10271.0
    ) STORED,
    is_uwb_band         BOOLEAN GENERATED ALWAYS AS (
        peak_freq_mhz BETWEEN 6000.0 AND 8500.0
    ) STORED,
    is_lte_leakage      BOOLEAN GENERATED ALWAYS AS (
        ABS(peak_freq_mhz - 1935.0) < 5.0
    ) STORED,

    -- Harmonic relationship
    fundamental_peak_id BIGINT REFERENCES frequency_peaks(id),
    harmonic_order      SMALLINT,                   -- 2 = 2nd harmonic, 3 = 3rd, etc.

    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_peaks_recording   ON frequency_peaks (recording_id);
CREATE INDEX idx_peaks_user        ON frequency_peaks (user_id, detected_at DESC);
CREATE INDEX idx_peaks_freq        ON frequency_peaks (peak_freq_mhz);
CREATE INDEX idx_peaks_type        ON frequency_peaks (peak_type, detected_at DESC);
CREATE INDEX idx_peaks_dna         ON frequency_peaks (recording_id) WHERE is_dna_resonance = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW: live spectrum overview — latest recording per node with peak counts
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW spectrum_overview AS
SELECT DISTINCT ON (r.node_id)
    r.node_id,
    r.user_id,
    r.session_id,
    r.frequency_mhz,
    r.bandwidth_mhz,
    r.power_dbm,
    r.noise_floor_dbm,
    r.snr_db,
    r.peak_count,
    r.timestamp,
    r.access_tier,
    COUNT(p.id) FILTER (WHERE p.is_dna_resonance) AS dna_peaks,
    COUNT(p.id) FILTER (WHERE p.is_lte_leakage)   AS lte_peaks,
    COUNT(p.id) FILTER (WHERE p.is_uwb_band)       AS uwb_peaks
FROM spectrum_recordings r
LEFT JOIN frequency_peaks p ON p.recording_id = r.id
GROUP BY r.id, r.node_id, r.user_id, r.session_id, r.frequency_mhz,
         r.bandwidth_mhz, r.power_dbm, r.noise_floor_dbm, r.snr_db,
         r.peak_count, r.timestamp, r.access_tier
ORDER BY r.node_id, r.timestamp DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- FUNCTION: close session and compute integrity hash
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION close_spectrum_session(p_session_id UUID)
RETURNS TEXT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_hash  TEXT;
    v_count INTEGER;
BEGIN
    -- Aggregate all recording hashes in time order
    SELECT
        encode(sha256(string_agg(COALESCE(iq_data_hash, id::TEXT), ',' ORDER BY timestamp)), 'hex'),
        COUNT(*)
    INTO v_hash, v_count
    FROM spectrum_recordings
    WHERE session_id = p_session_id;

    UPDATE spectrum_sessions
    SET ended_at       = now(),
        session_hash   = v_hash,
        recording_count = v_count
    WHERE id = p_session_id;

    RETURN v_hash;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: one demo session + recording for HEAD_01 at 10.245 GHz
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_session_id UUID := gen_random_uuid();
    v_recording_id UUID := gen_random_uuid();
BEGIN
    INSERT INTO spectrum_sessions (id, user_id, node_id, device_type, center_freq_mhz, sample_rate_mhz)
    VALUES (v_session_id, 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 1, 'hackrf', 10245.0, 10.0);

    INSERT INTO spectrum_recordings (id, user_id, session_id, node_id, frequency_mhz, bandwidth_mhz,
                                     sample_rate_mhz, power_dbm, noise_floor_dbm, peak_count, access_tier)
    VALUES (v_recording_id, 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
            v_session_id, 1, 10245.0, 10.0, 10.0, -42.3, -87.5, 3, 'LOW');

    -- Seed peaks for this recording
    INSERT INTO frequency_peaks (recording_id, user_id, peak_freq_mhz, peak_power_dbm, bandwidth_khz, peak_type) VALUES
    (v_recording_id, 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 10245.000, -42.3, 0.83, 'dna_resonance'),
    (v_recording_id, 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 30735.000, -68.1, 2.49, 'harmonic'),
    (v_recording_id, 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',  1935.000, -71.4, 5.00, 'lte_leakage');
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RLS
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE spectrum_sessions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE spectrum_recordings ENABLE ROW LEVEL SECURITY;
ALTER TABLE frequency_peaks     ENABLE ROW LEVEL SECURITY;

CREATE POLICY spectrum_sessions_owner   ON spectrum_sessions   FOR ALL USING (user_id = auth.uid()::UUID);
CREATE POLICY spectrum_recordings_owner ON spectrum_recordings FOR ALL USING (user_id = auth.uid()::UUID);
CREATE POLICY frequency_peaks_owner     ON frequency_peaks     FOR ALL USING (user_id = auth.uid()::UUID);
