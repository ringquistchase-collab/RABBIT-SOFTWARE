-- Multi-SIM / Tor / XRPL immutable anchor pipeline
-- RF Mesh ←→ Phone (AES-256) → Multi-SIM (3 carriers) → Tor → XRPL SHA3-512 memo

CREATE TYPE sim_role      AS ENUM ('PRIMARY', 'SECONDARY', 'TOR_ONLY');
CREATE TYPE sim_transport AS ENUM ('LTE', 'LTE_ADVANCED', '5G_NSA', '5G_SA', 'HSPA');
CREATE TYPE anchor_payload_type AS ENUM (
    'convergence_token', 'chemo_hash', 'pipeline_summary',
    'snapshot_proof', 'eeg_provenance', 'custom'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- SIM profiles (up to 3 per device)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE sim_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    slot            SMALLINT NOT NULL CHECK (slot BETWEEN 1 AND 3),
    role            sim_role NOT NULL,

    -- Carrier identification (no PII — carrier code only)
    carrier_mno     TEXT NOT NULL,          -- e.g. 'AT&T', 'T-Mobile', 'Verizon'
    iccid_hash      TEXT NOT NULL,          -- SHA-256(ICCID) — never store raw ICCID
    eid_hash        TEXT,                   -- SHA-256(EID) for eSIM

    -- RF parameters
    lte_band        SMALLINT,               -- primary LTE band (e.g. 2, 4, 12)
    transport       sim_transport NOT NULL DEFAULT 'LTE',
    rssi_threshold_dbm REAL DEFAULT -95.0,  -- failover trigger below this RSSI

    -- Policy flags
    tor_only        BOOLEAN NOT NULL DEFAULT FALSE,   -- SIM_C: never cleartext
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (twin_id, slot),
    UNIQUE (twin_id, role)
);

CREATE INDEX sim_profiles_twin_idx ON sim_profiles (twin_id, active);

-- ─────────────────────────────────────────────────────────────────────────────
-- SIM routing events (which SIM was used, why rotated)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE sim_routing_events (
    id              BIGSERIAL PRIMARY KEY,
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    sim_id          UUID NOT NULL REFERENCES sim_profiles(id),
    routed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    reason          TEXT,                   -- 'triangulation_risk', 'failover', 'scheduled'
    rssi_dbm        REAL,
    lte_event_id    UUID REFERENCES lte_interference_events(id),
    prior_sim_id    UUID REFERENCES sim_profiles(id),
    session_id      UUID REFERENCES edge_gateway_sessions(id)
);

CREATE INDEX sim_routing_twin_idx ON sim_routing_events (twin_id, routed_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Tor circuit sessions
-- Relay identity hashes only — no IP addresses ever stored
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE tor_circuit_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    sim_id              UUID REFERENCES sim_profiles(id),
    opened_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at           TIMESTAMPTZ,
    circuit_id          TEXT NOT NULL,      -- Tor internal circuit identifier (opaque)

    -- Relay fingerprints (SHA-1 hashes from Tor consensus — public, not private)
    guard_fingerprint   TEXT,               -- entry guard relay fingerprint
    middle_fingerprint  TEXT,               -- middle relay fingerprint
    exit_fingerprint    TEXT,               -- exit relay fingerprint

    -- Usage
    bytes_sent          BIGINT DEFAULT 0,
    bytes_recv          BIGINT DEFAULT 0,
    txns_submitted      INTEGER DEFAULT 0,  -- XRPL transactions sent via this circuit

    -- Status
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    teardown_reason     TEXT,               -- 'timeout', 'rotation', 'error'

    CONSTRAINT circuit_times CHECK (closed_at IS NULL OR closed_at > opened_at)
);

CREATE INDEX tor_circuits_twin_idx   ON tor_circuit_sessions (twin_id, opened_at DESC);
CREATE INDEX tor_circuits_active_idx ON tor_circuit_sessions (twin_id, is_active)
    WHERE is_active = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- XRPL memo anchors (SHA3-512 only — no plaintext on ledger)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE xrpl_memo_anchors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    anchored_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    tor_circuit_id      UUID REFERENCES tor_circuit_sessions(id),
    sim_id              UUID REFERENCES sim_profiles(id),

    -- XRPL transaction
    xrpl_txn_hash       TEXT NOT NULL UNIQUE,   -- 64-char hex
    xrpl_ledger_index   BIGINT NOT NULL,
    xrpl_account_hash   TEXT NOT NULL,           -- SHA-256(xrpl_account) — never raw address
    xrpl_fee_drops      BIGINT DEFAULT 12,       -- XRP drops

    -- Memo fields (as they appear on ledger)
    memo_type_hex       TEXT NOT NULL,           -- hex("rabbitos/anchor/v1")
    memo_format_hex     TEXT NOT NULL DEFAULT encode('application/octet-stream'::bytea, 'hex'),
    memo_data_hex       TEXT NOT NULL,           -- hex(SHA3-512(payload_bytes)) — 128 hex chars

    -- Payload metadata (local reference only — not on ledger)
    payload_type        anchor_payload_type NOT NULL,
    sha3_512_hash       TEXT NOT NULL             -- 128-char hex; must match memo_data_hex
        CHECK (LENGTH(sha3_512_hash) = 128),

    -- Source records
    convergence_token_id  UUID REFERENCES convergence_tokens(id),
    chemo_hash_id         UUID REFERENCES chemo_hashes(id),
    pipeline_summary_id   UUID REFERENCES pipeline_summaries(id),

    -- Access control
    access_tier         TEXT NOT NULL DEFAULT 'LOW',

    CONSTRAINT memo_hash_matches CHECK (memo_data_hex = encode(sha3_512_hash::bytea, 'hex')
        OR memo_data_hex = sha3_512_hash)
);

CREATE INDEX xrpl_anchors_twin_idx    ON xrpl_memo_anchors (twin_id, anchored_at DESC);
CREATE INDEX xrpl_anchors_ledger_idx  ON xrpl_memo_anchors (xrpl_ledger_index);
CREATE INDEX xrpl_anchors_payload_idx ON xrpl_memo_anchors (twin_id, payload_type);

-- Block CRITICAL/EXISTENTIAL anchors from being created
CREATE OR REPLACE FUNCTION block_critical_anchor()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.access_tier IN ('CRITICAL', 'EXISTENTIAL') THEN
        RAISE EXCEPTION 'xrpl_memo_anchors: CRITICAL/EXISTENTIAL tier cannot be anchored on public ledger'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER xrpl_anchor_tier_block
    BEFORE INSERT ON xrpl_memo_anchors
    FOR EACH ROW EXECUTE FUNCTION block_critical_anchor();

-- Immutable: anchors cannot be modified after ledger close
CREATE OR REPLACE FUNCTION block_anchor_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'xrpl_memo_anchors are immutable after ledger close'
        USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER xrpl_anchor_immutable
    BEFORE UPDATE OR DELETE ON xrpl_memo_anchors
    FOR EACH ROW EXECUTE FUNCTION block_anchor_mutation();

-- ─────────────────────────────────────────────────────────────────────────────
-- Full transmission pipeline audit
-- Traces one payload from mesh → AES256 → SIM → Tor → XRPL
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE transmission_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    initiated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,

    -- Pipeline stages
    mesh_session_id     UUID REFERENCES edge_gateway_sessions(id),
    aes_key_id          TEXT,               -- HKDF key identifier (not the key itself)
    sim_id              UUID REFERENCES sim_profiles(id),
    tor_circuit_id      UUID REFERENCES tor_circuit_sessions(id),
    anchor_id           UUID REFERENCES xrpl_memo_anchors(id),

    -- Payload reference
    payload_type        anchor_payload_type NOT NULL,
    payload_hash        TEXT NOT NULL,      -- SHA3-512 hex of transmitted payload
    bytes_total         INTEGER,

    -- Outcome
    success             BOOLEAN NOT NULL DEFAULT FALSE,
    error_stage         TEXT,               -- 'mesh','aes','sim','tor','xrpl', NULL
    error_detail        TEXT,

    latency_ms          INTEGER GENERATED ALWAYS AS (
        CASE WHEN completed_at IS NOT NULL
             THEN EXTRACT(EPOCH FROM (completed_at - initiated_at))::INTEGER * 1000
             ELSE NULL END
    ) STORED
);

CREATE INDEX transmission_twin_idx    ON transmission_events (twin_id, initiated_at DESC);
CREATE INDEX transmission_success_idx ON transmission_events (twin_id, success);

-- ─────────────────────────────────────────────────────────────────────────────
-- View: anchor chain integrity — latest anchor per payload type per twin
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW twin_anchor_chain AS
SELECT DISTINCT ON (a.twin_id, a.payload_type)
    a.twin_id,
    a.payload_type,
    a.anchored_at,
    a.xrpl_txn_hash,
    a.xrpl_ledger_index,
    a.sha3_512_hash,
    a.access_tier,
    t.success             AS last_transmission_ok,
    tc.guard_fingerprint,
    sp.carrier_mno,
    sp.role               AS sim_role
FROM xrpl_memo_anchors a
LEFT JOIN transmission_events t  ON t.anchor_id = a.id
LEFT JOIN tor_circuit_sessions tc ON tc.id = a.tor_circuit_id
LEFT JOIN sim_profiles sp        ON sp.id = a.sim_id
ORDER BY a.twin_id, a.payload_type, a.anchored_at DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: SIM profiles for Chase (3 slots)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO sim_profiles (twin_id, slot, role, carrier_mno, iccid_hash, lte_band, transport, tor_only) VALUES
(
    'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 1, 'PRIMARY',
    'AT&T',
    'ce39240160c3d89b6cdc2643fbd53a8aaf216131c357e4301682c161478a2114',
    2, 'LTE', FALSE
),
(
    'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 2, 'SECONDARY',
    'T-Mobile',
    '33574d5d80a2cd5de94f618eccf434377bbe38b4566f4ed21f98e941546757a3',
    4, 'LTE_ADVANCED', FALSE
),
(
    'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba', 3, 'TOR_ONLY',
    'Verizon',
    '2209446530f390fce0ae7eae8ef80d0eea6fae82307794a9b9c7d7bb216d1c4f',
    12, 'LTE', TRUE
);

-- RLS
ALTER TABLE sim_profiles         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sim_routing_events   ENABLE ROW LEVEL SECURITY;
ALTER TABLE tor_circuit_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE xrpl_memo_anchors    ENABLE ROW LEVEL SECURITY;
ALTER TABLE transmission_events  ENABLE ROW LEVEL SECURITY;

CREATE POLICY sim_owner          ON sim_profiles         FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY sim_routing_owner  ON sim_routing_events   FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY tor_owner          ON tor_circuit_sessions FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY anchor_owner       ON xrpl_memo_anchors    FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY transmission_owner ON transmission_events  FOR ALL USING (twin_id = auth.uid()::UUID);
