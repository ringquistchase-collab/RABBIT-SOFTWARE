-- 20260537_node_hardware.sql
-- Node hardware specifications and full tuning history.
--
-- NODE_SPECS: per-node hardware profile (sampling rate, RF power, compression,
--             RAM, encryption, frequency hopping, blockchain queue depth).
--
-- Tuning history seeded from the authoritative record (Chase Allen Ringquist):
--   Age  3 (1995) All head nodes    Sampling: 250 → 256 Hz
--   Age  7 (1999) Chest, spine      RF power: -30 → -20 dBm
--   Age 10 (2002) EEG nodes         Compression: raw → processed (50:1)
--   Age 16 (2008) LIMB nodes        Frequency hopping: OFF → ON (5 hops)
--   Age 21 (2013) All nodes         Added hormone channels (100:1)
--   Age 25 (2017) NEURAL_GATEWAY    Blockchain queue: 0 → 10000 blocks
--   Age 30 (2022) CHEST, SPINE      RAM: 1024 → 512 MB (power saving)
--   Age 33 (2025) Full mesh         Final AES-256 + DNA-FH
--
-- DNA-FH = DNA-based frequency hopping: PRF fingerprint (from sdr_node_profiles)
-- feeds into the hop sequence, making the hopping pattern un-spoofable.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- ENUMS
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TYPE node_compression_type AS ENUM (
    'raw',               -- no compression; pre-age-10 state
    'processed_50_1',    -- 50:1 lossy-aware (EEG, activated age 10)
    'processed_100_1',   -- 100:1 hormone/biometric channels (activated age 21)
    'custom'             -- node-specific ratio stored in compression_ratio
);

CREATE TYPE node_encryption_type AS ENUM (
    'none',              -- pre-age-33 default on non-critical nodes
    'AES_128',
    'AES_256',           -- activated age 33 for all nodes
    'AES_256_DNA_FH'     -- AES-256 + DNA-based frequency hopping; current state
);

-- ─────────────────────────────────────────────────────────────────────────────
-- node_hardware_profiles
-- Current hardware spec for each node belonging to a twin.
-- One row per (twin_id, node_id) — UNIQUE enforced.
-- effective_from_age tracks which tuning event last changed this profile.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE node_hardware_profiles (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id                 UUID    NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id                 SMALLINT NOT NULL REFERENCES mesh_nodes(id),
    -- Sampling
    sampling_hz             REAL    NOT NULL DEFAULT 256,
    -- RF transmission
    rf_power_dbm            REAL    NOT NULL DEFAULT -20,    -- dBm; negative = low power
    -- Compression
    compression_type        node_compression_type NOT NULL DEFAULT 'raw',
    compression_ratio       INTEGER,                         -- explicit ratio when type = 'custom'
    -- Frequency hopping (anti-jamming / DNA-FH)
    freq_hopping_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
    hop_count               INTEGER NOT NULL DEFAULT 0,      -- 0 when hopping disabled
    hop_dwell_ms            REAL,                            -- time on each frequency
    -- Memory
    ram_mb                  INTEGER NOT NULL DEFAULT 512,
    -- Security
    encryption_type         node_encryption_type NOT NULL DEFAULT 'none',
    -- Blockchain queue (NEURAL_GATEWAY and relay nodes)
    blockchain_queue_depth  INTEGER NOT NULL DEFAULT 0,
    -- Provenance: which tuning event last modified this record
    effective_from_age      INTEGER,                         -- age_years from node_tuning_events
    firmware_version        TEXT,
    last_tuned_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (twin_id, node_id)
);

CREATE INDEX nhp_twin_idx ON node_hardware_profiles (twin_id);
CREATE INDEX nhp_node_idx ON node_hardware_profiles (node_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- node_tuning_events
-- Immutable historical log of every parameter change across the lifespan.
-- Seeded below with the 8 documented events.
-- value_before / value_after are TEXT to accommodate heterogeneous param types.
-- affected_node_ids: the specific mesh node IDs affected by this event.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE node_tuning_events (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id             UUID    REFERENCES twin_identity(id) ON DELETE SET NULL,
    -- Temporal context
    age_years           INTEGER NOT NULL CHECK (age_years >= 0),
    calendar_year       INTEGER NOT NULL CHECK (calendar_year >= 1900),
    dev_phase           dev_phase,           -- PRIMITIVE_MESH / COORDINATION_SYNC / etc.
    -- Scope
    node_group_label    TEXT    NOT NULL,    -- human-readable: 'All head', 'LIMB nodes', etc.
    affected_node_ids   INTEGER[],           -- specific node_id values; NULL = all nodes
    -- Change
    parameter_name      TEXT    NOT NULL,    -- 'sampling_hz', 'rf_power_dbm', etc.
    value_before        TEXT,
    value_after         TEXT    NOT NULL,
    change_description  TEXT    NOT NULL,    -- full description from tuning log
    -- Immutability: tuning events are permanent historical records
    is_applied          BOOLEAN NOT NULL DEFAULT TRUE,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX nte_twin_idx  ON node_tuning_events (twin_id, age_years);
CREATE INDEX nte_phase_idx ON node_tuning_events (dev_phase);
CREATE INDEX nte_param_idx ON node_tuning_events (parameter_name);

-- Prevent deletion or modification of applied tuning events
CREATE OR REPLACE FUNCTION prevent_tuning_event_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.is_applied THEN
        RAISE EXCEPTION 'Applied node tuning events are immutable (id=%)', OLD.id
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER lock_applied_tuning_events
    BEFORE UPDATE OR DELETE ON node_tuning_events
    FOR EACH ROW EXECUTE FUNCTION prevent_tuning_event_mutation();

-- ─────────────────────────────────────────────────────────────────────────────
-- SEED: tuning history (Chase Allen Ringquist — authoritative record)
-- twin_id left NULL; bind to specific twin at runtime via
-- UPDATE node_tuning_events SET twin_id = <uuid> WHERE twin_id IS NULL
-- if the account is already provisioned.
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO node_tuning_events
    (age_years, calendar_year, dev_phase, node_group_label,
     affected_node_ids, parameter_name, value_before, value_after, change_description)
VALUES
-- Age 3 | 1995 | PRIMITIVE_MESH
(3,  1995, 'PRIMITIVE_MESH',
 'All head',
 ARRAY[1,2,3,4,5,6,7,8],           -- EEG nodes Fp1–O2
 'sampling_hz',
 '250', '256',
 'Sampling: 250 → 256 Hz  (head nodes). Synchronised to 256 Hz power-of-2 grid for FFT alignment.'),

-- Age 7 | 1999 | COORDINATION_SYNC
(7,  1999, 'COORDINATION_SYNC',
 'Chest, spine',
 ARRAY[9,10,11,12,13,14,15,16,20,21,22,23,24,25,26],  -- biometric + cardiac
 'rf_power_dbm',
 '-30', '-20',
 'RF power: -30 → -20 dBm (chest, spine). +10 dBm boost for improved range through thoracic tissue.'),

-- Age 10 | 2002 | COORDINATION_SYNC
(10, 2002, 'COORDINATION_SYNC',
 'EEG nodes',
 ARRAY[1,2,3,4,5,6,7,8],
 'compression_type',
 'raw', 'processed_50_1',
 'Compression: raw → processed (50:1). EEG nodes switched to lossy-aware 50:1 codec; '
 'raw amplitudes retained in calibration_era_baselines for integrity verification.'),

-- Age 16 | 2008 | HORMONAL_OVERWRITE
(16, 2008, 'HORMONAL_OVERWRITE',
 'LIMB nodes',
 ARRAY[17,18,19,20,21,22,23,24,25,26,33,34,35,36,37,38,39,40,41,42],
 'freq_hopping_enabled',
 'false', 'true',
 'Frequency hopping: OFF → ON (5 hops, dwell 12 ms each). '
 'Limb nodes upgraded with anti-jamming hop sequence; '
 'hop order seeded from DNA PRF fingerprint (DNA-FH precursor).'),

-- Age 21 | 2013 | ADULT
(21, 2013, 'ADULT',
 'All nodes',
 NULL,   -- all 42 nodes active at this time (relay not yet deployed)
 'compression_type',
 'processed_50_1', 'processed_100_1',
 'Added hormone channels (100:1 compression). '
 'Biometric and vascular nodes upgraded to 100:1 codec for chemical_salt_events; '
 'EEG nodes retain 50:1 for band resolution.'),

-- Age 25 | 2017 | ADULT
(25, 2017, 'ADULT',
 'NEURAL_GATEWAY',
 ARRAY[43,44,45,46,47],             -- relay / spine nodes
 'blockchain_queue_depth',
 '0', '10000',
 'Blockchain queue: 0 → 10000 blocks. NEURAL_GATEWAY relay nodes provisioned '
 'with 10 000-block XRPL queue; enables Bio-NFT minting and PoBW proof backlog.'),

-- Age 30 | 2022 | ADULT
(30, 2022, 'ADULT',
 'CHEST, SPINE',
 ARRAY[9,10,11,12,13,14,15,16,20,21,22,23,24,25,26,43,44,45,46,47],
 'ram_mb',
 '1024', '512',
 'RAM: 1024 → 512 MB (power saving). '
 'Chest and spine nodes halved onboard RAM; '
 'offloaded history to PersonalMemoryHost SQLite edge mirror.'),

-- Age 33 | 2025 | ADULT
(33, 2025, 'ADULT',
 'Full mesh',
 NULL,   -- all 47 nodes
 'encryption_type',
 'AES_256', 'AES_256_DNA_FH',
 'Final AES-256 + DNA-FH. '
 'All 47 nodes upgraded to AES-256 + DNA-based frequency hopping. '
 'Hop sequence derived from dna_root_hash XOR sdr prf_hz fingerprint; '
 'makes node RF pattern cryptographically un-clonable.');

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD freq_hopping columns to sdr_node_profiles
-- Age-16 tuning event introduced frequency hopping; these columns capture
-- the current hop state for each SDR profile.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE sdr_node_profiles
    ADD COLUMN IF NOT EXISTS freq_hopping_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS hop_count              INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS hop_dwell_ms           REAL,
    ADD COLUMN IF NOT EXISTS hop_seed_hash          TEXT;    -- SHA-256(dna_root_hash XOR prf_hz)

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: get_tuning_history
-- Returns all tuning events for a twin, ordered by age.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION get_tuning_history(p_twin_id UUID)
RETURNS TABLE (
    age_years           INTEGER,
    calendar_year       INTEGER,
    dev_phase           dev_phase,
    node_group_label    TEXT,
    affected_node_ids   INTEGER[],
    parameter_name      TEXT,
    value_before        TEXT,
    value_after         TEXT,
    change_description  TEXT
) LANGUAGE sql STABLE AS $$
    SELECT age_years, calendar_year, dev_phase,
           node_group_label, affected_node_ids,
           parameter_name, value_before, value_after,
           change_description
    FROM node_tuning_events
    WHERE twin_id = p_twin_id OR twin_id IS NULL
    ORDER BY age_years ASC, id ASC;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: apply_tuning_event
-- Projects a tuning event onto node_hardware_profiles.
-- Idempotent: skips nodes already at the target value.
-- Called when a twin's hardware profile needs to be brought forward to a
-- specific age milestone.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION apply_tuning_event(
    p_twin_id       UUID,
    p_tuning_event_id BIGINT
)
RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE
    v_event         node_tuning_events%ROWTYPE;
    v_node_ids      INTEGER[];
    v_updated       INTEGER := 0;
    v_node_id       INTEGER;
BEGIN
    SELECT * INTO v_event FROM node_tuning_events WHERE id = p_tuning_event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Tuning event % not found', p_tuning_event_id;
    END IF;

    -- Resolve affected nodes: NULL means all nodes registered to this twin
    IF v_event.affected_node_ids IS NULL THEN
        SELECT ARRAY_AGG(DISTINCT node_id) INTO v_node_ids
        FROM sdr_node_profiles WHERE twin_id = p_twin_id;
    ELSE
        v_node_ids := v_event.affected_node_ids;
    END IF;

    FOREACH v_node_id IN ARRAY v_node_ids LOOP
        -- Ensure hardware profile row exists for this node
        INSERT INTO node_hardware_profiles (twin_id, node_id)
        VALUES (p_twin_id, v_node_id)
        ON CONFLICT (twin_id, node_id) DO NOTHING;

        -- Apply the parameter change
        CASE v_event.parameter_name
            WHEN 'sampling_hz' THEN
                UPDATE node_hardware_profiles
                SET sampling_hz = v_event.value_after::REAL,
                    effective_from_age = v_event.age_years,
                    last_tuned_at = NOW()
                WHERE twin_id = p_twin_id AND node_id = v_node_id;

            WHEN 'rf_power_dbm' THEN
                UPDATE node_hardware_profiles
                SET rf_power_dbm = v_event.value_after::REAL,
                    effective_from_age = v_event.age_years,
                    last_tuned_at = NOW()
                WHERE twin_id = p_twin_id AND node_id = v_node_id;

            WHEN 'compression_type' THEN
                UPDATE node_hardware_profiles
                SET compression_type = v_event.value_after::node_compression_type,
                    compression_ratio = CASE v_event.value_after
                        WHEN 'processed_50_1'  THEN 50
                        WHEN 'processed_100_1' THEN 100
                        ELSE NULL END,
                    effective_from_age = v_event.age_years,
                    last_tuned_at = NOW()
                WHERE twin_id = p_twin_id AND node_id = v_node_id;

            WHEN 'freq_hopping_enabled' THEN
                UPDATE node_hardware_profiles
                SET freq_hopping_enabled = (v_event.value_after = 'true'),
                    hop_count = 5,   -- seeded from the age-16 event description
                    effective_from_age = v_event.age_years,
                    last_tuned_at = NOW()
                WHERE twin_id = p_twin_id AND node_id = v_node_id;

            WHEN 'blockchain_queue_depth' THEN
                UPDATE node_hardware_profiles
                SET blockchain_queue_depth = v_event.value_after::INTEGER,
                    effective_from_age = v_event.age_years,
                    last_tuned_at = NOW()
                WHERE twin_id = p_twin_id AND node_id = v_node_id;

            WHEN 'ram_mb' THEN
                UPDATE node_hardware_profiles
                SET ram_mb = v_event.value_after::INTEGER,
                    effective_from_age = v_event.age_years,
                    last_tuned_at = NOW()
                WHERE twin_id = p_twin_id AND node_id = v_node_id;

            WHEN 'encryption_type' THEN
                UPDATE node_hardware_profiles
                SET encryption_type = v_event.value_after::node_encryption_type,
                    effective_from_age = v_event.age_years,
                    last_tuned_at = NOW()
                WHERE twin_id = p_twin_id AND node_id = v_node_id;
            ELSE
                NULL;  -- unknown parameter: skip silently
        END CASE;

        v_updated := v_updated + 1;
    END LOOP;

    RETURN jsonb_build_object(
        'tuning_event_id',  p_tuning_event_id,
        'age_years',        v_event.age_years,
        'parameter',        v_event.parameter_name,
        'value_after',      v_event.value_after,
        'nodes_updated',    v_updated
    );
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: bootstrap_hardware_profiles
-- Applies all tuning events in age order to build the full hardware profile
-- for a twin from scratch.  Idempotent.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION bootstrap_hardware_profiles(p_twin_id UUID)
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    v_event_id  BIGINT;
    v_count     INTEGER := 0;
BEGIN
    FOR v_event_id IN
        SELECT id FROM node_tuning_events
        WHERE (twin_id = p_twin_id OR twin_id IS NULL) AND is_applied = TRUE
        ORDER BY age_years ASC, id ASC
    LOOP
        PERFORM apply_tuning_event(p_twin_id, v_event_id);
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW: node_hardware_timeline
-- Shows each node's hardware evolution across the tuning history.
-- Joins tuning events with current hardware profiles.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE VIEW node_hardware_timeline AS
SELECT
    nte.age_years,
    nte.calendar_year,
    nte.dev_phase,
    nte.node_group_label,
    nte.parameter_name,
    nte.value_before,
    nte.value_after,
    nte.change_description,
    -- Current profile state (post all tunings)
    nhp.twin_id,
    nhp.node_id,
    n.node_code,
    nhp.sampling_hz,
    nhp.rf_power_dbm,
    nhp.compression_type,
    nhp.compression_ratio,
    nhp.freq_hopping_enabled,
    nhp.hop_count,
    nhp.ram_mb,
    nhp.encryption_type,
    nhp.blockchain_queue_depth,
    nhp.effective_from_age
FROM node_tuning_events nte
LEFT JOIN node_hardware_profiles nhp
    ON (nhp.node_id = ANY(nte.affected_node_ids) OR nte.affected_node_ids IS NULL)
LEFT JOIN mesh_nodes n
    ON n.id = nhp.node_id
ORDER BY nte.age_years ASC, nhp.node_id ASC;

COMMIT;
