-- Ultra-Wideband (UWB) Radar Integration
-- Non-contact vital signs, ranging, gesture, and presence detection
-- Complements the 10.23–10.28 GHz molecular RF mesh with through-clothing sensing

CREATE TYPE uwb_modulation  AS ENUM ('IR_UWB', 'FMCW_UWB', 'DS_UWB');
CREATE TYPE uwb_band         AS ENUM ('low_3100_5000', 'high_6000_8500', 'full_3100_10600');
CREATE TYPE uwb_output_class AS ENUM ('VITAL_SIGNS', 'RANGE', 'GESTURE', 'PRESENCE', 'IMAGING');
CREATE TYPE gesture_label    AS ENUM (
    'BREATH_NORMAL', 'BREATH_DEEP', 'BREATH_APNEA',
    'HAND_WAVE', 'HAND_PUSH', 'HAND_SWIPE',
    'POSTURE_STANDING', 'POSTURE_SITTING', 'POSTURE_LYING',
    'FALL_DETECTED', 'ABSENT', 'PRESENCE_CONFIRMED'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- UWB node hardware profiles
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE uwb_node_profiles (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id          UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id          SMALLINT REFERENCES mesh_nodes(id),   -- NULL = standalone UWB node
    chip_vendor      TEXT NOT NULL,                         -- 'NXP', 'Qorvo', 'Infineon'
    chip_model       TEXT NOT NULL,                         -- 'SR040', 'SR150', 'DW3000'
    modulation       uwb_modulation NOT NULL DEFAULT 'IR_UWB',
    band             uwb_band NOT NULL DEFAULT 'high_6000_8500',
    centre_freq_ghz  REAL NOT NULL,                         -- e.g. 7.25
    bandwidth_mhz    REAL NOT NULL CHECK (bandwidth_mhz >= 500),
    pulse_width_ps   REAL,                                  -- pulse width in picoseconds
    max_eirp_dbm_mhz REAL NOT NULL DEFAULT -41.3,           -- FCC Part 15 limit
    max_range_m      REAL,
    firmware_ver     TEXT,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX uwb_profiles_twin_idx ON uwb_node_profiles (twin_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- UWB radar frames (raw range profiles, one per TX pulse burst)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE uwb_frames (
    id               BIGSERIAL PRIMARY KEY,
    uwb_node_id      UUID NOT NULL REFERENCES uwb_node_profiles(id) ON DELETE CASCADE,
    twin_id          UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    captured_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id       UUID REFERENCES edge_gateway_sessions(id),

    -- Signal parameters
    pulse_rep_freq_hz REAL,                 -- pulse repetition frequency
    integration_ms    INTEGER DEFAULT 20,   -- slow-time integration window
    snr_db            REAL,
    clutter_removed   BOOLEAN NOT NULL DEFAULT TRUE,

    -- Extracted range profile (JSONB array of [range_m, amplitude] pairs)
    range_profile     JSONB,

    -- Primary detected target
    target_range_m    REAL,                 -- distance to primary reflector
    target_rcs_dbsm   REAL,                 -- radar cross section estimate
    tof_ns            REAL                  -- time-of-flight in nanoseconds
);

CREATE INDEX uwb_frames_node_idx ON uwb_frames (uwb_node_id, captured_at DESC);
CREATE INDEX uwb_frames_twin_idx ON uwb_frames (twin_id, captured_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Vital signs extracted from UWB micro-Doppler
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE uwb_vital_signs (
    id                    BIGSERIAL PRIMARY KEY,
    uwb_node_id           UUID NOT NULL REFERENCES uwb_node_profiles(id) ON DELETE CASCADE,
    twin_id               UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    measured_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    frame_id              BIGINT REFERENCES uwb_frames(id),
    session_id            UUID REFERENCES edge_gateway_sessions(id),

    -- Breathing
    breathing_rate_hz     REAL CHECK (breathing_rate_hz BETWEEN 0.05 AND 1.0),
    breathing_amplitude_mm REAL CHECK (breathing_amplitude_mm >= 0),
    breathing_regularity  REAL CHECK (breathing_regularity BETWEEN 0 AND 1),

    -- Heart rate (micro-Doppler)
    heart_rate_hz         REAL CHECK (heart_rate_hz BETWEEN 0.5 AND 4.0),
    heart_amplitude_mm    REAL CHECK (heart_amplitude_mm >= 0),

    -- Cross-modal validation vs molecular mesh
    cross_modal_agreement BOOLEAN,          -- TRUE if UWB HR ≈ sdr prf_hz
    prf_delta_hz          REAL,             -- |uwb_heart_rate - molecular_prf|
    breath_phase_delta_rad REAL,            -- |uwb_breath - phase_ripple_breath|

    -- Quality
    confidence            REAL CHECK (confidence BETWEEN 0 AND 1),
    range_to_subject_m    REAL
);

CREATE INDEX uwb_vitals_twin_idx ON uwb_vital_signs (twin_id, measured_at DESC);

-- Anomaly trigger: UWB/molecular heart rate mismatch > 0.3 Hz
CREATE OR REPLACE FUNCTION check_uwb_crossmodal_anomaly()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.prf_delta_hz IS NOT NULL AND ABS(NEW.prf_delta_hz) > 0.3 THEN
        INSERT INTO mesh_anomalies (twin_id, anomaly_type, details, detected_at)
        VALUES (
            NEW.twin_id,
            'PATTERN_INJECTION',
            jsonb_build_object(
                'sub_type',       'UWB_MOLECULAR_HR_MISMATCH',
                'uwb_hr_hz',      NEW.heart_rate_hz,
                'prf_delta_hz',   NEW.prf_delta_hz,
                'uwb_vital_id',   NEW.id
            ),
            NEW.measured_at
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER uwb_crossmodal_check
    AFTER INSERT ON uwb_vital_signs
    FOR EACH ROW EXECUTE FUNCTION check_uwb_crossmodal_anomaly();

-- ─────────────────────────────────────────────────────────────────────────────
-- Precise range measurements (ToF ranging mode)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE uwb_range_measurements (
    id              BIGSERIAL PRIMARY KEY,
    uwb_node_id     UUID NOT NULL REFERENCES uwb_node_profiles(id) ON DELETE CASCADE,
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    measured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    frame_id        BIGINT REFERENCES uwb_frames(id),

    -- ToF ranging
    range_m         REAL NOT NULL CHECK (range_m >= 0),
    range_error_m   REAL,                   -- ±uncertainty
    tof_ns          REAL NOT NULL,
    los_confirmed   BOOLEAN,                -- line-of-sight vs NLOS

    -- Anchor geometry (for multi-static positioning)
    anchor_node_id  UUID REFERENCES uwb_node_profiles(id),
    azimuth_deg     REAL,
    elevation_deg   REAL
);

CREATE INDEX uwb_range_twin_idx ON uwb_range_measurements (twin_id, measured_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Gesture and posture events (ML classifier output)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE uwb_gesture_events (
    id              BIGSERIAL PRIMARY KEY,
    uwb_node_id     UUID NOT NULL REFERENCES uwb_node_profiles(id) ON DELETE CASCADE,
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    frame_id        BIGINT REFERENCES uwb_frames(id),
    session_id      UUID REFERENCES edge_gateway_sessions(id),

    gesture         gesture_label NOT NULL,
    confidence      REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    duration_ms     INTEGER,

    -- Cross-modal: compare with EEG intent
    intent_event_id BIGINT,                -- FK to intent_action_events if it exists
    eeg_correlated  BOOLEAN,

    -- Anomaly: ABSENT with molecular mesh still transmitting = spoofing
    spoof_risk      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX uwb_gesture_twin_idx ON uwb_gesture_events (twin_id, detected_at DESC);

-- Spoofing detection: presence=ABSENT but molecular mesh active
CREATE OR REPLACE FUNCTION check_uwb_presence_spoof()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.gesture = 'ABSENT' AND NEW.spoof_risk = TRUE THEN
        INSERT INTO mesh_anomalies (twin_id, anomaly_type, details, detected_at)
        VALUES (
            NEW.twin_id,
            'PATTERN_INJECTION',
            jsonb_build_object(
                'sub_type',       'UWB_PRESENCE_SPOOF',
                'gesture',        'ABSENT',
                'gesture_id',     NEW.id
            ),
            NEW.detected_at
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER uwb_spoof_check
    AFTER INSERT ON uwb_gesture_events
    FOR EACH ROW EXECUTE FUNCTION check_uwb_presence_spoof();

-- ─────────────────────────────────────────────────────────────────────────────
-- View: live UWB state per twin
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW twin_uwb_state AS
SELECT
    v.twin_id,
    v.measured_at,
    v.breathing_rate_hz,
    v.heart_rate_hz,
    v.cross_modal_agreement,
    v.prf_delta_hz,
    v.confidence       AS vitals_confidence,
    g.gesture          AS latest_gesture,
    g.confidence       AS gesture_confidence,
    g.spoof_risk,
    p.chip_model,
    p.centre_freq_ghz,
    p.bandwidth_mhz
FROM (
    SELECT DISTINCT ON (twin_id) *
    FROM uwb_vital_signs
    ORDER BY twin_id, measured_at DESC
) v
LEFT JOIN (
    SELECT DISTINCT ON (twin_id) *
    FROM uwb_gesture_events
    ORDER BY twin_id, detected_at DESC
) g ON g.twin_id = v.twin_id
LEFT JOIN uwb_node_profiles p ON p.id = v.uwb_node_id;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: UWB node profile for Chase (NXP SR150, high band)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO uwb_node_profiles
    (twin_id, chip_vendor, chip_model, modulation, band,
     centre_freq_ghz, bandwidth_mhz, pulse_width_ps, max_range_m)
VALUES
    ('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
     'NXP', 'SR150', 'IR_UWB', 'high_6000_8500',
     7.25, 1500.0, 200.0, 10.0);

-- RLS
ALTER TABLE uwb_node_profiles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE uwb_frames             ENABLE ROW LEVEL SECURITY;
ALTER TABLE uwb_vital_signs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE uwb_range_measurements ENABLE ROW LEVEL SECURITY;
ALTER TABLE uwb_gesture_events     ENABLE ROW LEVEL SECURITY;

CREATE POLICY uwb_profiles_owner  ON uwb_node_profiles      FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY uwb_frames_owner    ON uwb_frames             FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY uwb_vitals_owner    ON uwb_vital_signs        FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY uwb_range_owner     ON uwb_range_measurements FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY uwb_gesture_owner   ON uwb_gesture_events     FOR ALL USING (twin_id = auth.uid()::UUID);
