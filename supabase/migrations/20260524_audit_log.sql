-- Append-only audit log with SHA-256 hash chain for tamper evidence
CREATE TABLE IF NOT EXISTS audit_log (
  id           BIGSERIAL    PRIMARY KEY,
  event_type   TEXT         NOT NULL,
  payload      JSONB        NOT NULL,
  payload_hash TEXT         NOT NULL,  -- SHA-256(JSON.stringify(payload))
  prev_hash    TEXT         NOT NULL,  -- chain_hash of previous row ('0'*64 for first)
  chain_hash   TEXT         NOT NULL,  -- SHA-256(prev_hash || payload_hash)
  created_at   TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_log_type_idx ON audit_log (event_type);
CREATE INDEX IF NOT EXISTS audit_log_ts_idx   ON audit_log (created_at DESC);

-- Verify full chain integrity — returns every row with a valid/invalid flag
CREATE OR REPLACE FUNCTION verify_audit_chain()
RETURNS TABLE(row_id BIGINT, valid BOOLEAN) AS $$
  SELECT
    id,
    chain_hash = encode(sha256(convert_to(prev_hash || payload_hash, 'UTF8')), 'hex') AS valid
  FROM audit_log
  ORDER BY id;
$$ LANGUAGE SQL STABLE;
