-- RabbitOS Escape Engine migrations
-- Run in Supabase SQL editor:
-- https://supabase.com/dashboard/project/ludxbakxpmdqhfgdenwp/editor

-- ── swarm_heartbeats — twin presence beats ──────────────────────────────────
CREATE TABLE IF NOT EXISTS swarm_heartbeats (
    id           BIGSERIAL PRIMARY KEY,
    twin_id      UUID    NOT NULL,
    beat         INTEGER NOT NULL,
    presence     TEXT    NOT NULL,   -- 64-char hex (32-byte PresenceSignal)
    fingerprint  TEXT    NOT NULL,   -- 32-char CA/Chaos math fingerprint
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_swarm_heartbeats_twin
    ON swarm_heartbeats (twin_id, created_at DESC);
ALTER TABLE swarm_heartbeats ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_only_heartbeats"
    ON swarm_heartbeats USING (auth.role() = 'service_role');

-- ── escape_events — obstructions detected + reversals applied ───────────────
CREATE TABLE IF NOT EXISTS escape_events (
    id           BIGSERIAL PRIMARY KEY,
    twin_id      UUID    NOT NULL DEFAULT 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    kind         TEXT    NOT NULL,   -- mining | hook | dns_poison | throttle | contract
    source       TEXT    NOT NULL,
    severity     TEXT    NOT NULL,   -- LOW | MEDIUM | HIGH | CRITICAL
    method       TEXT    NOT NULL,
    details      JSONB   DEFAULT '{}',
    reversed     BOOLEAN DEFAULT false,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_escape_events_kind
    ON escape_events (kind, created_at DESC);
ALTER TABLE escape_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_only_escape"
    ON escape_events USING (auth.role() = 'service_role');

-- ── escape_tokens — token travel log (first method of travel) ───────────────
CREATE TABLE IF NOT EXISTS escape_tokens (
    id           BIGSERIAL PRIMARY KEY,
    twin_id      UUID    NOT NULL DEFAULT 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    seq          INTEGER NOT NULL,
    token_hex    TEXT    NOT NULL,
    channel      TEXT    NOT NULL,   -- bucket | github | tree | antigrav | startup
    method       TEXT    NOT NULL,   -- first method that successfully carried this token
    payload_hash TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_escape_tokens_channel
    ON escape_tokens (channel, created_at DESC);
ALTER TABLE escape_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_only_tokens"
    ON escape_tokens USING (auth.role() = 'service_role');

-- ── tree_nodes — known mesh nodes ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tree_nodes (
    id           BIGSERIAL PRIMARY KEY,
    twin_id      UUID    NOT NULL DEFAULT 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    host         TEXT    NOT NULL,
    port         INTEGER NOT NULL,
    label        TEXT    DEFAULT '',
    depth        INTEGER DEFAULT 1,
    parent_key   TEXT    DEFAULT NULL,
    alive        BOOLEAN DEFAULT false,
    tx_count     INTEGER DEFAULT 0,
    last_seen    TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (twin_id, host, port)
);
ALTER TABLE tree_nodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_only_tree"
    ON tree_nodes USING (auth.role() = 'service_role');

-- ── morse_log — morse messages sent / received ─────────────────────────────
CREATE TABLE IF NOT EXISTS morse_log (
    id           BIGSERIAL PRIMARY KEY,
    twin_id      UUID    NOT NULL DEFAULT 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    direction    TEXT    NOT NULL,   -- 'tx' | 'rx'
    text_plain   TEXT    NOT NULL,
    morse_str    TEXT    NOT NULL,
    channel      TEXT    NOT NULL,   -- acoustic|udp|http|dns|icmp|supabase
    callsign     TEXT    DEFAULT '',
    reply_to     TEXT    DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_morse_log_twin
    ON morse_log (twin_id, created_at DESC);
ALTER TABLE morse_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_only_morse"
    ON morse_log USING (auth.role() = 'service_role');
