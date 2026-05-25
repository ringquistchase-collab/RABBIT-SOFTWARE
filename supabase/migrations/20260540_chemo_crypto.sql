-- Chemo-Cryptographic Coupling (CCC)
-- Chemical indicators (hormones, neurotransmitters, electrolytes) inferred
-- from vascular phase shifts at 10.245 GHz, converted to cryptographic salt
-- that modifies the DNA Root Key to produce a chemo-hash for server template routing.

CREATE TYPE chemical_class  AS ENUM ('HORMONE', 'NEUROTRANSMITTER', 'ELECTROLYTE', 'METABOLITE');
CREATE TYPE ccc_output_type AS ENUM ('IMAGE', 'CODE', 'VECTOR', 'SUMMARY');

-- ─────────────────────────────────────────────────────────────────────────────
-- Research Baseline: per-twin reference ranges per developmental era
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE chemo_baselines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    chemical_name   TEXT NOT NULL,
    chemical_class  chemical_class NOT NULL,
    unit            TEXT NOT NULL,
    baseline_mean   REAL NOT NULL,
    baseline_stddev REAL NOT NULL CHECK (baseline_stddev > 0),
    age_years       SMALLINT,
    dev_phase       TEXT,                  -- PRIMITIVE_MESH | COORDINATION_SYNC | etc.
    carrier_freq_ghz REAL DEFAULT 10.245,  -- vascular Doppler carrier
    established_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (twin_id, chemical_name, dev_phase)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Chemical indicator readings
-- Inferred from vascular phase shifts (nodes 27–32) at 10.245 GHz
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE chemo_indicators (
    id               BIGSERIAL PRIMARY KEY,
    twin_id          UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id          SMALLINT REFERENCES mesh_nodes(id),
    sampled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    carrier_freq_ghz REAL NOT NULL DEFAULT 10.245,
    phase_shift_rad  REAL,                 -- measured phase shift encoding chemical state
    chemical_name    TEXT NOT NULL,
    chemical_class   chemical_class NOT NULL,
    unit             TEXT NOT NULL,
    value_raw        REAL NOT NULL,        -- inferred absolute value
    value_normalized REAL                  -- 0.0–1.0 relative to chemo_baselines
        CHECK (value_normalized IS NULL OR value_normalized BETWEEN 0 AND 1),
    deviation_sigma  REAL,                 -- std deviations from baseline_mean
    session_id       UUID REFERENCES edge_gateway_sessions(id)
);

CREATE INDEX chemo_indicators_twin_idx ON chemo_indicators (twin_id, sampled_at DESC);
CREATE INDEX chemo_indicators_chemical_idx ON chemo_indicators (twin_id, chemical_name, sampled_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Chemo-hash: chemical state → cryptographic salt → DNA root key derivation
-- Formula:
--   chemo_salt = SHA-256(chemical_vector_json_bytes)
--   chemo_hash = SHA-256(dna_root_hash XOR chemo_salt)   [computed in-memory only]
--   branch_key = HMAC-SHA-256(chemo_hash, twin_uuid)
-- dna_root_hash is NEVER stored (shows_dna_root = FALSE invariant)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE chemo_hashes (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id              UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    computed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Chemical vector snapshot used in derivation (sorted by chemical_name)
    indicator_vector     JSONB NOT NULL,

    -- Cryptographic outputs
    chemo_salt           TEXT NOT NULL,     -- hex: SHA-256(indicator_vector bytes)
    chemo_hash           TEXT NOT NULL,     -- hex: SHA-256(dna_root XOR chemo_salt)
    branch_key           TEXT NOT NULL,     -- hex: HMAC-SHA-256(chemo_hash, twin_uuid)

    -- RF parameters used for this reading
    carrier_freq_ghz     REAL NOT NULL DEFAULT 10.245,
    phase_window_ms      INTEGER NOT NULL DEFAULT 1000,   -- integration window

    -- Cross-system links
    eeg_provenance_hash  TEXT,              -- SHA-3 from eeg_provenance_chain ledger
    session_id           UUID REFERENCES edge_gateway_sessions(id),
    stress_state_id      UUID REFERENCES cross_modal_states(id),

    -- Access control
    access_tier          TEXT NOT NULL DEFAULT 'LOW',
    is_sealed            BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX chemo_hashes_twin_idx    ON chemo_hashes (twin_id, computed_at DESC);
CREATE INDEX chemo_hashes_branch_idx  ON chemo_hashes (twin_id, branch_key);
CREATE INDEX chemo_hashes_sealed_idx  ON chemo_hashes (twin_id, is_sealed)
    WHERE is_sealed = FALSE;

-- Immutability: chemo-hash chain is append-only
CREATE OR REPLACE FUNCTION block_chemo_hash_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'chemo_hashes records are immutable (append-only chain)'
        USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER chemo_hash_immutable
    BEFORE UPDATE OR DELETE ON chemo_hashes
    FOR EACH ROW EXECUTE FUNCTION block_chemo_hash_mutation();

-- Block CRITICAL/EXISTENTIAL tier chemo-hash digital access
CREATE OR REPLACE FUNCTION block_critical_chemo_access()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.access_tier IN ('CRITICAL', 'EXISTENTIAL') THEN
        RAISE EXCEPTION 'chemo_hashes: CRITICAL/EXISTENTIAL tier digital access blocked'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER chemo_critical_access_block
    BEFORE INSERT ON chemo_hashes
    FOR EACH ROW EXECUTE FUNCTION block_critical_chemo_access();

-- ─────────────────────────────────────────────────────────────────────────────
-- Server template branch routing
-- chemo-hash → branch of digital twin tree → framework output
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE template_routes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    chemo_hash_id   UUID NOT NULL REFERENCES chemo_hashes(id),
    routed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Branch selection
    branch_key      TEXT NOT NULL,
    branch_label    TEXT,                  -- e.g. 'high_cortisol_branch', 'dopaminergic_peak'
    branch_depth    SMALLINT DEFAULT 1,    -- depth in digital twin tree (1 = root branch)

    -- Framework output
    output_type     ccc_output_type NOT NULL,
    output_ref      TEXT,                  -- URI / hash of output artifact
    output_bytes    INTEGER,               -- size of output
    accuracy_score  REAL CHECK (accuracy_score BETWEEN 0 AND 1),

    -- Chemical state context at routing time
    dominant_chemical  TEXT,              -- highest-deviation indicator
    dominant_deviation REAL,              -- deviation_sigma of dominant chemical
    stress_confirmed   BOOLEAN NOT NULL DEFAULT FALSE,

    -- Provenance
    zk_proof_id     BIGINT REFERENCES snapshot_zk_proofs(id)
);

CREATE INDEX template_routes_twin_idx      ON template_routes (twin_id, routed_at DESC);
CREATE INDEX template_routes_branch_idx    ON template_routes (twin_id, branch_key);
CREATE INDEX template_routes_output_idx    ON template_routes (twin_id, output_type, routed_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- View: current chemical state per twin (latest reading per indicator)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW twin_chemo_state AS
SELECT DISTINCT ON (twin_id, chemical_name)
    twin_id,
    chemical_name,
    chemical_class,
    unit,
    value_raw,
    value_normalized,
    deviation_sigma,
    phase_shift_rad,
    carrier_freq_ghz,
    sampled_at
FROM chemo_indicators
ORDER BY twin_id, chemical_name, sampled_at DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Function: compute chemical vector and insert chemo-hash record
-- (dna_root_hash XOR performed by caller in secure enclave;
--  this function records the result only)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION record_chemo_hash(
    p_twin_id            UUID,
    p_indicator_vector   JSONB,
    p_chemo_salt         TEXT,
    p_chemo_hash         TEXT,
    p_branch_key         TEXT,
    p_access_tier        TEXT DEFAULT 'LOW',
    p_session_id         UUID DEFAULT NULL,
    p_eeg_provenance     TEXT DEFAULT NULL,
    p_stress_state_id    UUID DEFAULT NULL
) RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO chemo_hashes (
        twin_id, indicator_vector, chemo_salt, chemo_hash,
        branch_key, access_tier, session_id,
        eeg_provenance_hash, stress_state_id
    ) VALUES (
        p_twin_id, p_indicator_vector, p_chemo_salt, p_chemo_hash,
        p_branch_key, p_access_tier, p_session_id,
        p_eeg_provenance, p_stress_state_id
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: reference baselines for Chase Allen Ringquist (age 33 — current era)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO chemo_baselines
    (twin_id, chemical_name, chemical_class, unit, baseline_mean, baseline_stddev, age_years, dev_phase)
VALUES
-- Hormones
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'cortisol',       'HORMONE',          'nmol/L',  450.0,  120.0, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'testosterone',   'HORMONE',          'nmol/L',   16.5,    4.5, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'adrenaline',     'HORMONE',          'pg/mL',    60.0,   20.0, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'insulin',        'HORMONE',          'µIU/mL',    8.0,    3.0, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'melatonin',      'HORMONE',          'pg/mL',    25.0,   10.0, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'oxytocin',       'HORMONE',          'pg/mL',    18.0,    6.0, 33, 'ADULT'),
-- Neurotransmitters
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'dopamine',       'NEUROTRANSMITTER', 'ng/mL',     0.12,   0.04, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'serotonin',      'NEUROTRANSMITTER', 'ng/mL',   180.0,   40.0, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'gaba',           'NEUROTRANSMITTER', 'µmol/L',    2.0,    0.5, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'glutamate',      'NEUROTRANSMITTER', 'µmol/L',   60.0,   15.0, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'norepinephrine', 'NEUROTRANSMITTER', 'pg/mL',   280.0,   80.0, 33, 'ADULT'),
-- Electrolytes
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'sodium',         'ELECTROLYTE',      'mEq/L',   140.0,    2.5, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'potassium',      'ELECTROLYTE',      'mEq/L',     4.2,    0.4, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'calcium',        'ELECTROLYTE',      'mg/dL',     9.5,    0.5, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'magnesium',      'ELECTROLYTE',      'mg/dL',     2.0,    0.2, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'chloride',       'ELECTROLYTE',      'mEq/L',   102.0,    2.0, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'bicarbonate',    'ELECTROLYTE',      'mEq/L',    25.0,    2.0, 33, 'ADULT'),
-- Metabolites
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'glucose',        'METABOLITE',       'mg/dL',    90.0,   10.0, 33, 'ADULT'),
('ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 'lactate',        'METABOLITE',       'mmol/L',    1.0,    0.3, 33, 'ADULT');

-- RLS
ALTER TABLE chemo_baselines  ENABLE ROW LEVEL SECURITY;
ALTER TABLE chemo_indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE chemo_hashes     ENABLE ROW LEVEL SECURITY;
ALTER TABLE template_routes  ENABLE ROW LEVEL SECURITY;

CREATE POLICY chemo_baselines_owner  ON chemo_baselines  FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY chemo_indicators_owner ON chemo_indicators FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY chemo_hashes_owner     ON chemo_hashes     FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY template_routes_owner  ON template_routes  FOR ALL USING (twin_id = auth.uid()::UUID);
