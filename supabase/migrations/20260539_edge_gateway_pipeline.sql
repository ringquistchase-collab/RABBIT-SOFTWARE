-- RabbitOS Edge Gateway: analog-to-digital biological ingestion pipeline
-- Covers: gateway sessions, per-packet telemetry, stage audit log, windowed summaries

CREATE TYPE transport_medium AS ENUM ('bluetooth_le', 'wifi', 'body_coupled_rf', 'wired');
CREATE TYPE pipeline_stage    AS ENUM ('TIMESTAMP', 'ENCRYPT', 'TELEMETRY', 'ANALYZE', 'ROUTE', 'SUMMARIZE', 'VISUALIZE', 'SHARE');
CREATE TYPE route_decision    AS ENUM ('BLOCK', 'AIRGAP', 'ENCRYPTED_STORE', 'DB_WRITE', 'LIVE_STREAM', 'BROADCAST');
CREATE TYPE summary_window    AS ENUM ('1s', '10s', '60s', '300s');

-- One row per gateway connection session (device powers on → off)
CREATE TABLE edge_gateway_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    session_start   TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_end     TIMESTAMPTZ,
    transport       transport_medium NOT NULL,
    device_label    TEXT,                          -- e.g. 'HEAD_01', 'CHEST_01'
    firmware_ver    TEXT,
    packets_rx      INTEGER NOT NULL DEFAULT 0,
    packets_dropped INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT session_times CHECK (session_end IS NULL OR session_end > session_start)
);

-- Per-node RF/BLE telemetry sampled at gateway receipt
CREATE TABLE edge_gateway_telemetry (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES edge_gateway_sessions(id) ON DELETE CASCADE,
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id         SMALLINT NOT NULL REFERENCES mesh_nodes(id),
    sampled_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    transport       transport_medium NOT NULL,
    rssi_dbm        REAL,              -- received signal strength
    snr_db          REAL,              -- signal-to-noise ratio
    packet_loss_pct REAL CHECK (packet_loss_pct BETWEEN 0 AND 100),
    latency_ms      REAL CHECK (latency_ms >= 0),
    propagation_med TEXT,              -- body_coupled | skin | air (mirrors mesh enum)
    phase_coherence REAL CHECK (phase_coherence BETWEEN 0 AND 1),
    hop_channel     SMALLINT           -- DNA-FH channel index
);

CREATE INDEX edge_telemetry_session_idx ON edge_gateway_telemetry (session_id, sampled_at DESC);
CREATE INDEX edge_telemetry_node_idx    ON edge_gateway_telemetry (twin_id, node_id, sampled_at DESC);

-- Per-packet stage audit — one row per packet per pipeline stage
CREATE TABLE ingestion_pipeline_log (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES edge_gateway_sessions(id) ON DELETE CASCADE,
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id         SMALLINT NOT NULL REFERENCES mesh_nodes(id),
    packet_seq      BIGINT NOT NULL,               -- monotonic seq from transport packet
    stage           pipeline_stage NOT NULL,
    entered_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_us     INTEGER,                       -- microseconds spent in stage

    -- TIMESTAMP stage
    utc_ns          BIGINT,                        -- nanosecond UTC on gateway receipt
    ntp_drift_ms    REAL,

    -- ENCRYPT stage
    encryption_alg  TEXT,                          -- e.g. 'AES-256-DNA-FH'
    sig_verified    BOOLEAN,                       -- Ed25519 signature valid

    -- TELEMETRY stage
    telemetry_id    BIGINT REFERENCES edge_gateway_telemetry(id),

    -- ANALYZE stage
    anomaly_raised  BOOLEAN NOT NULL DEFAULT FALSE,
    anomaly_type    TEXT,
    deviation_sigma REAL,

    -- ROUTE stage
    access_tier     TEXT,                          -- mirrors life_age_events.access_tier
    route_decision  route_decision,

    -- SUMMARIZE / VISUALIZE / SHARE — outcome flags
    summary_written   BOOLEAN NOT NULL DEFAULT FALSE,
    reading_written   BOOLEAN NOT NULL DEFAULT FALSE,
    share_dispatched  BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (session_id, node_id, packet_seq, stage)
);

CREATE INDEX pipeline_log_session_idx ON ingestion_pipeline_log (session_id, entered_at DESC);
CREATE INDEX pipeline_log_anomaly_idx ON ingestion_pipeline_log (twin_id, anomaly_raised)
    WHERE anomaly_raised = TRUE;

-- Windowed aggregate summaries (Stage 6 — SUMMARIZE)
CREATE TABLE pipeline_summaries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twin_id         UUID NOT NULL REFERENCES twin_identity(id) ON DELETE CASCADE,
    node_id         SMALLINT REFERENCES mesh_nodes(id),  -- NULL = all-node aggregate
    agg_window      summary_window NOT NULL,
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,

    packets_total   INTEGER NOT NULL DEFAULT 0,
    packets_anomaly INTEGER NOT NULL DEFAULT 0,
    avg_rssi_dbm    REAL,
    avg_snr_db      REAL,
    avg_latency_ms  REAL,
    avg_phase_coh   REAL,

    -- Bio-signal aggregates
    mean_signal     REAL,
    stddev_signal   REAL,
    peak_signal     REAL,

    -- NFT / PoBW eligibility
    bio_nft_hash    TEXT,              -- SHA-256 of window payload; NULL if tier > LOW
    zk_proof_id     BIGINT REFERENCES snapshot_zk_proofs(id),

    UNIQUE (twin_id, node_id, agg_window, window_start)
);

CREATE INDEX pipeline_summaries_twin_idx ON pipeline_summaries (twin_id, agg_window, window_start DESC);

-- View: live gateway health per twin (latest telemetry per node)
CREATE OR REPLACE VIEW live_gateway_health AS
SELECT DISTINCT ON (t.twin_id, t.node_id)
    t.twin_id,
    t.node_id,
    t.sampled_at,
    t.transport,
    t.rssi_dbm,
    t.snr_db,
    t.packet_loss_pct,
    t.latency_ms,
    t.phase_coherence,
    s.device_label,
    s.is_active
FROM edge_gateway_telemetry t
JOIN edge_gateway_sessions s ON s.id = t.session_id
ORDER BY t.twin_id, t.node_id, t.sampled_at DESC;

-- Function: open a new gateway session
CREATE OR REPLACE FUNCTION open_gateway_session(
    p_twin_id    UUID,
    p_transport  transport_medium,
    p_device     TEXT DEFAULT NULL,
    p_firmware   TEXT DEFAULT NULL
) RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO edge_gateway_sessions (twin_id, transport, device_label, firmware_ver)
    VALUES (p_twin_id, p_transport, p_device, p_firmware)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- Function: close a gateway session and tally packets
CREATE OR REPLACE FUNCTION close_gateway_session(
    p_session_id UUID
) RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE edge_gateway_sessions
    SET session_end = now(),
        is_active   = FALSE,
        packets_rx  = (
            SELECT COUNT(DISTINCT packet_seq)
            FROM ingestion_pipeline_log
            WHERE session_id = p_session_id AND stage = 'TIMESTAMP'
        ),
        packets_dropped = (
            SELECT COALESCE(SUM((packet_loss_pct / 100.0 * packets_rx)::INTEGER), 0)
            FROM edge_gateway_telemetry et
            JOIN edge_gateway_sessions es ON es.id = et.session_id
            WHERE et.session_id = p_session_id
        )
    WHERE id = p_session_id;
END;
$$;

-- RLS
ALTER TABLE edge_gateway_sessions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge_gateway_telemetry  ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_pipeline_log  ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_summaries      ENABLE ROW LEVEL SECURITY;

CREATE POLICY gw_sessions_owner   ON edge_gateway_sessions   FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY gw_telemetry_owner  ON edge_gateway_telemetry  FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY pipeline_log_owner  ON ingestion_pipeline_log  FOR ALL USING (twin_id = auth.uid()::UUID);
CREATE POLICY summaries_owner     ON pipeline_summaries       FOR ALL USING (twin_id = auth.uid()::UUID);
