-- 20260534_p2p_interactions.sql
-- Person-to-person RF node interaction system
--
-- Core invariant: for every share event, BOTH parties own their own row
-- (UNIQUE(share_id, twin_id) in p2p_interactions enforces this at DB level)
--
-- Topology: connections are stored as ordered pairs (twin_id_a < twin_id_b),
-- mirroring the mesh_topology CHECK (node_a < node_b) convention.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- ENUMS
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TYPE p2p_connection_state AS ENUM ('pending', 'active', 'revoked');
CREATE TYPE p2p_interaction_role  AS ENUM ('sent', 'received');
CREATE TYPE p2p_group_role        AS ENUM ('initiator', 'participant');

-- ─────────────────────────────────────────────────────────────────────────────
-- p2p_connections
-- One row per unordered pair of twins.  Enforced ordered by CHECK (twin_id_a < twin_id_b).
-- freq_delta_ghz is a generated column; the range CHECK (< 0.05 GHz) mirrors
-- persons_in_range() from the Python class.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE p2p_connections (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id_a           UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    twin_id_b           UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    state               p2p_connection_state NOT NULL DEFAULT 'pending',
    -- RF carrier frequencies captured at handshake time (from sdr_node_profiles)
    freq_a_ghz          REAL,
    freq_b_ghz          REAL,
    freq_delta_ghz      REAL GENERATED ALWAYS AS (ABS(freq_a_ghz - freq_b_ghz)) STORED,
    -- Explicit consent timestamps for each party
    consent_a_at        TIMESTAMPTZ,
    consent_b_at        TIMESTAMPTZ,
    -- Revocation
    revoked_by          UUID REFERENCES twin_identity(id),
    revoked_at          TIMESTAMPTZ,
    revocation_reason   TEXT,
    -- Lifecycle
    initiated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at        TIMESTAMPTZ,
    CONSTRAINT p2p_connections_ordered    CHECK (twin_id_a < twin_id_b),
    CONSTRAINT p2p_connections_no_self    CHECK (twin_id_a != twin_id_b),
    CONSTRAINT p2p_connections_unique     UNIQUE (twin_id_a, twin_id_b),
    -- Belt-and-suspenders: RPC also validates range before inserting
    CONSTRAINT p2p_connections_rf_range   CHECK (
        freq_delta_ghz IS NULL OR freq_delta_ghz < 0.05
    )
);

CREATE INDEX p2p_conn_a_idx     ON p2p_connections (twin_id_a);
CREATE INDEX p2p_conn_b_idx     ON p2p_connections (twin_id_b);
CREATE INDEX p2p_conn_state_idx ON p2p_connections (state);

-- ─────────────────────────────────────────────────────────────────────────────
-- p2p_handshakes
-- Individual handshake events.  Multiple handshakes may occur over the
-- lifetime of one connection (e.g. re-authentication after reconnect).
-- handshake_id mirrors the SHA3-256[:16] generated in Python accept_handshake().
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE p2p_handshakes (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    handshake_id        TEXT NOT NULL UNIQUE,
    connection_id       BIGINT NOT NULL REFERENCES p2p_connections(id) ON DELETE CASCADE,
    initiator_twin_id   UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    responder_twin_id   UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    signal_strength     REAL CHECK (signal_strength BETWEEN 0.0 AND 1.0),
    initiator_signature TEXT,   -- MD5(handshake_id || initiator_id)[:16]
    responder_signature TEXT,
    duration_sec        REAL NOT NULL DEFAULT 0,
    successful          BOOLEAN NOT NULL DEFAULT FALSE,
    handshake_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX p2p_hs_conn_idx       ON p2p_handshakes (connection_id);
CREATE INDEX p2p_hs_initiator_idx  ON p2p_handshakes (initiator_twin_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- p2p_interactions
-- The core "both parties own their copy" table.
-- For every share event, record_p2p_share() inserts EXACTLY TWO rows:
--   (share_id, source_twin_id, role='sent')
--   (share_id, target_twin_id, role='received')
-- UNIQUE(share_id, twin_id) is the DB-level invariant.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE p2p_interactions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    share_id            TEXT NOT NULL,
    twin_id             UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    peer_twin_id        UUID NOT NULL REFERENCES twin_identity(id),
    handshake_id        TEXT NOT NULL REFERENCES p2p_handshakes(handshake_id),
    role                p2p_interaction_role NOT NULL,
    data_type           TEXT NOT NULL,
    data_hash           TEXT NOT NULL,           -- SHA3-256 of compressed payload
    payload             JSONB,                   -- optional; may be NULL for privacy
    group_session_id    BIGINT,                  -- set when part of a group session
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (share_id, twin_id)                   -- one copy per person per share
);

CREATE INDEX p2p_int_twin_idx ON p2p_interactions (twin_id,      recorded_at DESC);
CREATE INDEX p2p_int_peer_idx ON p2p_interactions (twin_id,      peer_twin_id, recorded_at DESC);
CREATE INDEX p2p_int_share_idx ON p2p_interactions (share_id);
CREATE INDEX p2p_int_type_idx  ON p2p_interactions (twin_id,     data_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- p2p_shared_memories
-- Enriched, named memories promoted from received interactions.
-- Maps to the Python shared_memories table + access_count tracking.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE p2p_shared_memories (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    memory_id           TEXT NOT NULL UNIQUE,
    owner_twin_id       UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    source_twin_id      UUID NOT NULL REFERENCES twin_identity(id),
    interaction_id      BIGINT REFERENCES p2p_interactions(id),
    memory_type         TEXT NOT NULL,           -- 'experience', 'knowledge', 'emotion', etc.
    memory_data         JSONB,
    access_count        INTEGER NOT NULL DEFAULT 0,
    last_accessed_at    TIMESTAMPTZ,
    shared_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX p2p_mem_owner_idx  ON p2p_shared_memories (owner_twin_id);
CREATE INDEX p2p_mem_source_idx ON p2p_shared_memories (source_twin_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- p2p_group_sessions + p2p_group_participants
-- Maps to simulate_group_interaction().  Participants are registered with a
-- role (initiator vs participant) and every interaction inside a session
-- carries group_session_id.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE p2p_group_sessions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_session_id    TEXT NOT NULL UNIQUE,    -- MD5(topic || timestamp)[:8]
    topic               TEXT NOT NULL,
    duration_s          INTEGER,
    interaction_count   INTEGER NOT NULL DEFAULT 0,
    handshake_count     INTEGER NOT NULL DEFAULT 0,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ
);

CREATE TABLE p2p_group_participants (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  BIGINT NOT NULL REFERENCES p2p_group_sessions(id) ON DELETE CASCADE,
    twin_id     UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    role        p2p_group_role NOT NULL DEFAULT 'participant',
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, twin_id)
);

CREATE INDEX p2p_gp_session_idx ON p2p_group_participants (session_id);
CREATE INDEX p2p_gp_twin_idx    ON p2p_group_participants (twin_id);

-- FK from p2p_interactions to group sessions (added after both tables exist)
ALTER TABLE p2p_interactions
    ADD CONSTRAINT p2p_interactions_group_fk
    FOREIGN KEY (group_session_id) REFERENCES p2p_group_sessions(id);

-- ─────────────────────────────────────────────────────────────────────────────
-- TRIGGER: block interactions on revoked or non-existent connections
-- Fires on every INSERT into p2p_interactions, including both rows
-- inserted by record_p2p_share().
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION enforce_active_p2p_connection()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_a     UUID;
    v_b     UUID;
    v_state p2p_connection_state;
BEGIN
    v_a := LEAST(NEW.twin_id, NEW.peer_twin_id);
    v_b := GREATEST(NEW.twin_id, NEW.peer_twin_id);

    SELECT state INTO v_state
    FROM p2p_connections
    WHERE twin_id_a = v_a AND twin_id_b = v_b;

    IF v_state IS NULL THEN
        RAISE EXCEPTION 'No p2p connection exists between % and %',
            NEW.twin_id, NEW.peer_twin_id
            USING ERRCODE = '55000';
    END IF;

    IF v_state != 'active' THEN
        RAISE EXCEPTION 'p2p connection is not active (state: %)', v_state
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER check_p2p_connection_before_interaction
    BEFORE INSERT ON p2p_interactions
    FOR EACH ROW EXECUTE FUNCTION enforce_active_p2p_connection();

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: establish_p2p_handshake
-- Creates or re-activates a connection between two twins and records the
-- handshake event.  RF range check mirrors persons_in_range() (< 0.05 GHz).
-- Looks up carrier frequencies from sdr_node_profiles (lowest node_id per twin).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION establish_p2p_handshake(
    p_twin_id_a         UUID,
    p_twin_id_b         UUID,
    p_signal_strength   REAL DEFAULT 0.85
)
RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE
    v_a             UUID  := LEAST(p_twin_id_a, p_twin_id_b);
    v_b             UUID  := GREATEST(p_twin_id_a, p_twin_id_b);
    v_freq_a        REAL;
    v_freq_b        REAL;
    v_conn_id       BIGINT;
    v_handshake_id  TEXT;
    v_init_sig      TEXT;
    v_resp_sig      TEXT;
BEGIN
    IF p_twin_id_a = p_twin_id_b THEN
        RAISE EXCEPTION 'Cannot handshake with self' USING ERRCODE = '22023';
    END IF;

    -- Carrier frequency: use lowest node_id profile for each twin as anchor
    SELECT carrier_freq_ghz INTO v_freq_a
    FROM sdr_node_profiles
    WHERE twin_id = p_twin_id_a
    ORDER BY node_id ASC LIMIT 1;

    SELECT carrier_freq_ghz INTO v_freq_b
    FROM sdr_node_profiles
    WHERE twin_id = p_twin_id_b
    ORDER BY node_id ASC LIMIT 1;

    -- RF range gate: 50 MHz = 0.05 GHz
    IF v_freq_a IS NOT NULL AND v_freq_b IS NOT NULL THEN
        IF ABS(v_freq_a - v_freq_b) >= 0.05 THEN
            RETURN jsonb_build_object(
                'success',     FALSE,
                'reason',      'Out of RF range',
                'freq_a',      v_freq_a,
                'freq_b',      v_freq_b,
                'freq_delta',  ABS(v_freq_a - v_freq_b)
            );
        END IF;
    END IF;

    -- Upsert connection: re-activation resets revocation fields
    INSERT INTO p2p_connections (
        twin_id_a, twin_id_b, state,
        freq_a_ghz, freq_b_ghz,
        consent_a_at, consent_b_at, activated_at
    ) VALUES (
        v_a, v_b, 'active',
        -- freq_a_ghz maps to twin_id_a (the "smaller" UUID, v_a)
        CASE WHEN p_twin_id_a < p_twin_id_b THEN v_freq_a ELSE v_freq_b END,
        CASE WHEN p_twin_id_a < p_twin_id_b THEN v_freq_b ELSE v_freq_a END,
        NOW(), NOW(), NOW()
    )
    ON CONFLICT (twin_id_a, twin_id_b) DO UPDATE
        SET state         = 'active',
            consent_a_at  = COALESCE(p2p_connections.consent_a_at, NOW()),
            consent_b_at  = COALESCE(p2p_connections.consent_b_at, NOW()),
            activated_at  = COALESCE(p2p_connections.activated_at, NOW()),
            revoked_at    = NULL,
            revoked_by    = NULL,
            revocation_reason = NULL
    RETURNING id INTO v_conn_id;

    -- Generate handshake ID and per-party signatures
    v_handshake_id := encode(
        sha256((p_twin_id_a::TEXT || p_twin_id_b::TEXT || extract(epoch FROM NOW())::TEXT)::bytea),
        'hex'
    );
    v_init_sig := LEFT(encode(sha256((v_handshake_id || p_twin_id_a::TEXT)::bytea), 'hex'), 16);
    v_resp_sig := LEFT(encode(sha256((v_handshake_id || p_twin_id_b::TEXT)::bytea), 'hex'), 16);

    INSERT INTO p2p_handshakes (
        handshake_id, connection_id,
        initiator_twin_id, responder_twin_id,
        signal_strength,
        initiator_signature, responder_signature,
        successful
    ) VALUES (
        v_handshake_id, v_conn_id,
        p_twin_id_a, p_twin_id_b,
        p_signal_strength,
        v_init_sig, v_resp_sig,
        TRUE
    );

    RETURN jsonb_build_object(
        'success',       TRUE,
        'handshake_id',  v_handshake_id,
        'connection_id', v_conn_id,
        'freq_a',        v_freq_a,
        'freq_b',        v_freq_b
    );
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: record_p2p_share
-- Atomically inserts two rows into p2p_interactions:
--   (share_id, source_twin_id, role='sent')
--   (share_id, target_twin_id, role='received')
-- The trigger enforce_active_p2p_connection fires for each row.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION record_p2p_share(
    p_share_id          TEXT,
    p_source_twin_id    UUID,
    p_target_twin_id    UUID,
    p_handshake_id      TEXT,
    p_data_type         TEXT,
    p_data_hash         TEXT,
    p_payload           JSONB    DEFAULT NULL,
    p_group_session_id  BIGINT   DEFAULT NULL
)
RETURNS JSONB LANGUAGE plpgsql AS $$
BEGIN
    -- Source's copy
    INSERT INTO p2p_interactions (
        share_id, twin_id, peer_twin_id, handshake_id,
        role, data_type, data_hash, payload, group_session_id
    ) VALUES (
        p_share_id, p_source_twin_id, p_target_twin_id, p_handshake_id,
        'sent', p_data_type, p_data_hash, p_payload, p_group_session_id
    );

    -- Target's copy
    INSERT INTO p2p_interactions (
        share_id, twin_id, peer_twin_id, handshake_id,
        role, data_type, data_hash, payload, group_session_id
    ) VALUES (
        p_share_id, p_target_twin_id, p_source_twin_id, p_handshake_id,
        'received', p_data_type, p_data_hash, p_payload, p_group_session_id
    );

    RETURN jsonb_build_object(
        'success',       TRUE,
        'share_id',      p_share_id,
        'copies_written', 2
    );
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: revoke_p2p_connection
-- Either party can revoke.  Prevents all future record_p2p_share() calls.
-- Existing interaction rows are preserved (each party keeps their history).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION revoke_p2p_connection(
    p_revoking_twin_id  UUID,
    p_peer_twin_id      UUID,
    p_reason            TEXT DEFAULT NULL
)
RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE
    v_a     UUID    := LEAST(p_revoking_twin_id, p_peer_twin_id);
    v_b     UUID    := GREATEST(p_revoking_twin_id, p_peer_twin_id);
    v_rows  INTEGER;
BEGIN
    UPDATE p2p_connections
    SET state             = 'revoked',
        revoked_by        = p_revoking_twin_id,
        revoked_at        = NOW(),
        revocation_reason = p_reason
    WHERE twin_id_a = v_a AND twin_id_b = v_b
      AND state = 'active';

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows = 0 THEN
        RETURN jsonb_build_object('success', FALSE, 'reason', 'No active connection found');
    END IF;

    RETURN jsonb_build_object(
        'success',    TRUE,
        'revoked_by', p_revoking_twin_id,
        'revoked_at', NOW()
    );
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: get_p2p_summary  (mirrors PersonNodeNetwork.get_connection_summary)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION get_p2p_summary(p_twin_id UUID)
RETURNS JSONB LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_object(
        'twin_id',              p_twin_id,
        'active_connections',   COUNT(*) FILTER (WHERE c.state = 'active'),
        'total_connections',    COUNT(*),
        'unique_peers',         COUNT(*),
        'total_interactions',   (
            SELECT COUNT(*) FROM p2p_interactions
            WHERE twin_id = p_twin_id
        ),
        'sent_count',           (
            SELECT COUNT(*) FROM p2p_interactions
            WHERE twin_id = p_twin_id AND role = 'sent'
        ),
        'received_count',       (
            SELECT COUNT(*) FROM p2p_interactions
            WHERE twin_id = p_twin_id AND role = 'received'
        ),
        'handshakes_completed', (
            SELECT COUNT(*) FROM p2p_handshakes
            WHERE (initiator_twin_id = p_twin_id OR responder_twin_id = p_twin_id)
              AND successful = TRUE
        ),
        'group_sessions',       (
            SELECT COUNT(DISTINCT session_id) FROM p2p_group_participants
            WHERE twin_id = p_twin_id
        )
    )
    FROM p2p_connections c
    WHERE c.twin_id_a = p_twin_id OR c.twin_id_b = p_twin_id;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: begin_p2p_group_session / complete_p2p_group_session
-- Maps to MultiPersonInteractionController.simulate_group_interaction()
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION begin_p2p_group_session(
    p_topic             TEXT,
    p_group_session_id  TEXT,
    p_participant_ids   UUID[],
    p_duration_s        INTEGER DEFAULT NULL
)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    v_session_id BIGINT;
    v_twin_id    UUID;
    v_role       p2p_group_role;
BEGIN
    INSERT INTO p2p_group_sessions (group_session_id, topic, duration_s)
    VALUES (p_group_session_id, p_topic, p_duration_s)
    RETURNING id INTO v_session_id;

    FOREACH v_twin_id IN ARRAY p_participant_ids LOOP
        v_role := CASE WHEN v_twin_id = p_participant_ids[1]
                       THEN 'initiator'::p2p_group_role
                       ELSE 'participant'::p2p_group_role
                  END;
        INSERT INTO p2p_group_participants (session_id, twin_id, role)
        VALUES (v_session_id, v_twin_id, v_role);
    END LOOP;

    RETURN v_session_id;
END;
$$;

CREATE OR REPLACE FUNCTION complete_p2p_group_session(
    p_session_id        BIGINT,
    p_interaction_count INTEGER,
    p_handshake_count   INTEGER
)
RETURNS VOID LANGUAGE sql AS $$
    UPDATE p2p_group_sessions
    SET ended_at          = NOW(),
        interaction_count = p_interaction_count,
        handshake_count   = p_handshake_count
    WHERE id = p_session_id;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW: p2p_connection_matrix
-- Mirrors the ASCII interaction matrix from visualize_interaction_network().
-- Each row = one connection pair with per-side interaction counts.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE VIEW p2p_connection_matrix AS
SELECT
    c.twin_id_a,
    c.twin_id_b,
    c.state,
    c.freq_a_ghz,
    c.freq_b_ghz,
    c.freq_delta_ghz,
    c.activated_at,
    c.revoked_at,
    COUNT(i.id) FILTER (WHERE i.twin_id = c.twin_id_a)  AS interactions_a,
    COUNT(i.id) FILTER (WHERE i.twin_id = c.twin_id_b)  AS interactions_b,
    MAX(i.recorded_at)                                   AS last_interaction_at
FROM p2p_connections c
LEFT JOIN p2p_interactions i
    ON  (i.twin_id = c.twin_id_a OR  i.twin_id = c.twin_id_b)
    AND (i.peer_twin_id = c.twin_id_a OR i.peer_twin_id = c.twin_id_b)
GROUP BY c.id, c.twin_id_a, c.twin_id_b, c.state,
         c.freq_a_ghz, c.freq_b_ghz, c.freq_delta_ghz,
         c.activated_at, c.revoked_at;

COMMIT;
