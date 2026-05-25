-- Cross-modal biometric validation: EEG × HRV → stress/valence state
-- EEG alpha asymmetry (8-13 Hz) x HRV LF/HF (0.1/0.25 Hz) x skin propagation path

CREATE TYPE stress_state AS ENUM (
    'CALM',           -- theta/alpha < 0.50, LF/HF < 1.5
    'MILD_STRESS',    -- 0.50-0.62 / 1.5-2.1
    'STRESS',         -- theta/alpha >= 0.62 AND LF/HF >= 2.1
    'ACUTE_DISTRESS'  -- theta/alpha > 0.80 OR LF/HF > 3.5
);

-- One row per twin per evaluation window
CREATE TABLE cross_modal_states (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- EEG spectral ratios (nodes 1-19)
    theta_power         REAL NOT NULL CHECK (theta_power >= 0),   -- 4-8 Hz band µV²
    alpha_power         REAL NOT NULL CHECK (alpha_power > 0),    -- 8-13 Hz band µV²
    theta_alpha_ratio   REAL GENERATED ALWAYS AS (theta_power / alpha_power) STORED,

    -- Frontal alpha asymmetry (F4 log power - F3 log power)
    frontal_alpha_asymmetry REAL,   -- positive = approach, negative = withdrawal

    -- HRV spectral power (cardiac nodes 9-26)
    hrv_lf_power        REAL NOT NULL CHECK (hrv_lf_power >= 0),  -- 0.10 Hz band ms²
    hrv_hf_power        REAL NOT NULL CHECK (hrv_hf_power > 0),   -- 0.25 Hz band ms²
    hrv_lf_hf_ratio     REAL GENERATED ALWAYS AS (hrv_lf_power / hrv_hf_power) STORED,

    -- Skin propagation phase ripple (HEAD_01 → vascular relay → CHEST_01)
    phase_ripple_heart_rad  REAL,   -- ±0.08 rad nominal
    phase_ripple_breath_rad REAL,   -- ±0.03 rad nominal

    -- Derived state
    stress_confirmed    BOOLEAN GENERATED ALWAYS AS (
        (theta_power / alpha_power) >= 0.62
        AND (hrv_lf_power / hrv_hf_power) >= 2.1
    ) STORED,

    valence_score       REAL,       -- -1.0 (negative) to +1.0 (positive); NULL until computed
    stress_level        stress_state NOT NULL DEFAULT 'CALM',

    -- Identity gate adjustment
    fraud_score_threshold_override REAL
        GENERATED ALWAYS AS (
            CASE
                -- Stress raises latency tolerance; acute distress = no gate
                WHEN (hrv_lf_power / hrv_hf_power) > 3.5
                     OR (theta_power / alpha_power) > 0.80  THEN NULL
                WHEN (theta_power / alpha_power) >= 0.62
                     AND (hrv_lf_power / hrv_hf_power) >= 2.1 THEN 0.25
                ELSE 0.1
            END
        ) STORED,

    -- Source reading references (mesh_node_readings.id and relay_path_events.id are BIGINT)
    eeg_reading_id      BIGINT REFERENCES mesh_node_readings(id),
    hrv_reading_id      BIGINT REFERENCES mesh_node_readings(id),
    relay_path_id       BIGINT REFERENCES relay_path_events(id)
);

CREATE INDEX cross_modal_states_twin_idx ON cross_modal_states (twin_id, evaluated_at DESC);
CREATE INDEX cross_modal_states_stress_idx ON cross_modal_states (twin_id, stress_confirmed)
    WHERE stress_confirmed = TRUE;

-- Anomaly trigger: phase ripple exceeded OR acute distress
CREATE OR REPLACE FUNCTION check_cross_modal_anomalies()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_ripple_combined REAL;
BEGIN
    v_ripple_combined := COALESCE(ABS(NEW.phase_ripple_heart_rad), 0)
                       + COALESCE(ABS(NEW.phase_ripple_breath_rad), 0);

    IF v_ripple_combined > 0.15 THEN
        INSERT INTO mesh_anomalies (twin_id, anomaly_type, details, detected_at)
        VALUES (
            NEW.twin_id,
            'PATTERN_INJECTION',
            jsonb_build_object(
                'sub_type',         'PHASE_RIPPLE_EXCEEDED',
                'ripple_combined',  v_ripple_combined,
                'threshold',        0.15,
                'cross_modal_id',   NEW.id
            ),
            NEW.evaluated_at
        );
    END IF;

    IF NEW.stress_level = 'ACUTE_DISTRESS' THEN
        INSERT INTO mesh_anomalies (twin_id, anomaly_type, details, detected_at)
        VALUES (
            NEW.twin_id,
            'PATTERN_INJECTION',
            jsonb_build_object(
                'sub_type',          'ACUTE_DISTRESS',
                'theta_alpha_ratio', NEW.theta_alpha_ratio,
                'hrv_lf_hf',         NEW.hrv_lf_hf_ratio,
                'cross_modal_id',    NEW.id
            ),
            NEW.evaluated_at
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER cross_modal_anomaly_check
    AFTER INSERT ON cross_modal_states
    FOR EACH ROW EXECUTE FUNCTION check_cross_modal_anomalies();

-- View: latest stress state per twin
CREATE OR REPLACE VIEW twin_stress_status AS
SELECT DISTINCT ON (twin_id)
    twin_id,
    evaluated_at,
    ROUND(theta_alpha_ratio::NUMERIC, 3)  AS theta_alpha_ratio,
    ROUND(hrv_lf_hf_ratio::NUMERIC, 3)   AS hrv_lf_hf_ratio,
    frontal_alpha_asymmetry,
    stress_confirmed,
    stress_level,
    valence_score,
    fraud_score_threshold_override
FROM cross_modal_states
ORDER BY twin_id, evaluated_at DESC;

-- RLS
ALTER TABLE cross_modal_states ENABLE ROW LEVEL SECURITY;

CREATE POLICY cross_modal_owner
    ON cross_modal_states FOR ALL
    USING (twin_id = auth.uid()::UUID);
