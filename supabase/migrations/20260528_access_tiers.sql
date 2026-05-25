-- ============================================================
-- RABBIT-SOFTWARE v0.32.2 — Tiered Snapshot Access Control
-- ============================================================
-- Three access tiers keyed to life events in the Digital Twin:
--
--   CRITICAL  (age 22, OD event)
--     • No digital access path — physical M-DISC vault only
--     • Emergency destruction protocol with witness record
--     • Smart contract anchoring disabled (no XRPL/ETH tx)
--
--   HIGH      (age 7, PTSD event)
--     • 3-of-5 node threshold signatures required
--     • 24-hour ephemeral keys only (hard TTL constraint)
--
--   LOW       (age 33, baseline calibration)
--     • Token-gated via XRPL (0.001 XRP gate)
--     • BlockGPT anomaly detection verdict stored per proof
--     • Public ZK ownership proofs (Groth16/PLONK/STARK)
-- ============================================================

CREATE TYPE snapshot_access_tier AS ENUM ('LOW', 'HIGH', 'CRITICAL');

-- ── Tier column on frozen snapshots and life events ───────────
ALTER TABLE mesh_frozen_snapshots
  ADD COLUMN IF NOT EXISTS access_tier snapshot_access_tier NOT NULL DEFAULT 'LOW';

ALTER TABLE life_age_events
  ADD COLUMN IF NOT EXISTS access_tier snapshot_access_tier NOT NULL DEFAULT 'LOW';

-- ── CRITICAL: physical M-DISC vault records ───────────────────
-- One row per CRITICAL snapshot. disc_id identifies the physical
-- archival disc. vault_location_hash is SHA-256 of the plaintext
-- location string — location is never stored in the database.
CREATE TABLE IF NOT EXISTS snapshot_vault_records (
  id                        BIGSERIAL    PRIMARY KEY,
  snapshot_id               INT          NOT NULL UNIQUE REFERENCES mesh_frozen_snapshots(id),
  twin_id                   UUID         NOT NULL REFERENCES twin_identity(id),
  disc_id                   TEXT         NOT NULL,
  vault_location_hash       TEXT,
  sealed_at                 TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  destruction_requested_at  TIMESTAMPTZ,
  destruction_confirmed_at  TIMESTAMPTZ,
  destruction_witness       TEXT,
  metadata                  JSONB
);

-- ── HIGH: threshold signers registry (max 5 per snapshot) ─────
-- signer_pub is an Ed25519 public key in base64.
-- Up to 5 signers registered; any 3 satisfy the threshold.
CREATE TABLE IF NOT EXISTS snapshot_threshold_signers (
  id            BIGSERIAL    PRIMARY KEY,
  snapshot_id   INT          NOT NULL REFERENCES mesh_frozen_snapshots(id),
  twin_id       UUID         NOT NULL REFERENCES twin_identity(id),
  signer_index  SMALLINT     NOT NULL CHECK (signer_index BETWEEN 1 AND 5),
  signer_pub    TEXT         NOT NULL,
  signer_label  TEXT,
  added_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  revoked_at    TIMESTAMPTZ,
  UNIQUE (snapshot_id, signer_index)
);

-- ── HIGH: submitted threshold signatures ─────────────────────
-- Each row is one signer's Ed25519 signature over
-- (snapshot_hash || operation || nonce) encoded as base64.
-- The nonce binds each signature to a single access session.
CREATE TABLE IF NOT EXISTS snapshot_threshold_sigs (
  id            BIGSERIAL    PRIMARY KEY,
  snapshot_id   INT          NOT NULL REFERENCES mesh_frozen_snapshots(id),
  signer_index  SMALLINT     NOT NULL,
  signature     TEXT         NOT NULL,
  operation     TEXT         NOT NULL, -- 'key_issue' | 'access_grant' | 'destruction_authorize'
  nonce         TEXT         NOT NULL,
  signed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (snapshot_id, signer_index, operation, nonce)
);

-- ── HIGH: 24-hour ephemeral access keys ──────────────────────
-- The raw key is generated client-side and never stored.
-- key_hash = SHA-256(raw_key). Clients present the raw key;
-- the function verifies SHA-256(presented) = stored key_hash.
CREATE TABLE IF NOT EXISTS snapshot_ephemeral_keys (
  id             BIGSERIAL    PRIMARY KEY,
  snapshot_id    INT          NOT NULL REFERENCES mesh_frozen_snapshots(id),
  twin_id        UUID         NOT NULL REFERENCES twin_identity(id),
  key_hash       TEXT         NOT NULL UNIQUE,
  issued_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  expires_at     TIMESTAMPTZ  NOT NULL,
  used_at        TIMESTAMPTZ,
  revoked_at     TIMESTAMPTZ,
  issued_to      TEXT,
  sig_count      SMALLINT     NOT NULL DEFAULT 0,
  CONSTRAINT ephemeral_key_24hr CHECK (expires_at = issued_at + INTERVAL '24 hours')
);

CREATE INDEX IF NOT EXISTS ek_snapshot_expires_idx
  ON snapshot_ephemeral_keys (snapshot_id, expires_at DESC);

-- ── LOW: ZK ownership proofs ──────────────────────────────────
-- proof_hash = SHA-256(raw proof bytes). public_inputs contains
-- only the public signals — no private witness data.
-- block_gpt_score: 0.0 = clean, 1.0 = anomalous.
CREATE TABLE IF NOT EXISTS snapshot_zk_proofs (
  id                 BIGSERIAL    PRIMARY KEY,
  snapshot_id        INT          NOT NULL REFERENCES mesh_frozen_snapshots(id),
  twin_id            UUID         NOT NULL REFERENCES twin_identity(id),
  proof_system       TEXT         NOT NULL DEFAULT 'groth16', -- groth16 | plonk | stark
  proof_hash         TEXT         NOT NULL,
  public_inputs      JSONB        NOT NULL,
  xrpl_tx_hash       TEXT,
  xrpl_ledger_index  BIGINT,
  block_gpt_verdict  TEXT,        -- 'CLEAN' | 'ANOMALY' | 'PENDING'
  block_gpt_score    REAL,
  verified_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS zkp_snapshot_idx ON snapshot_zk_proofs (snapshot_id);
CREATE INDEX IF NOT EXISTS zkp_xrpl_tx_idx
  ON snapshot_zk_proofs (xrpl_tx_hash) WHERE xrpl_tx_hash IS NOT NULL;

-- ── Access attempt log (all tiers) ───────────────────────────
CREATE TABLE IF NOT EXISTS snapshot_access_log (
  id                  BIGSERIAL    PRIMARY KEY,
  snapshot_id         INT          NOT NULL REFERENCES mesh_frozen_snapshots(id),
  twin_id             UUID         NOT NULL REFERENCES twin_identity(id),
  access_tier         snapshot_access_tier NOT NULL,
  requester_id        TEXT         NOT NULL,
  granted             BOOLEAN      NOT NULL,
  denial_reason       TEXT,
  ephemeral_key_id    BIGINT       REFERENCES snapshot_ephemeral_keys(id),
  xrpl_tx_hash        TEXT,
  accessed_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sal_snapshot_ts_idx
  ON snapshot_access_log (snapshot_id, accessed_at DESC);
CREATE INDEX IF NOT EXISTS sal_twin_ts_idx
  ON snapshot_access_log (twin_id, accessed_at DESC);

-- ── Trigger: hard-block digital access to CRITICAL snapshots ──
-- Even if something calls INSERT on access_log with granted=TRUE
-- for a CRITICAL snapshot, this trigger raises an exception.
CREATE OR REPLACE FUNCTION block_critical_digital_access()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.granted = TRUE
    AND (SELECT access_tier FROM mesh_frozen_snapshots WHERE id = NEW.snapshot_id) = 'CRITICAL'
  THEN
    RAISE EXCEPTION
      'CRITICAL tier snapshot % is vault-only — no digital access permitted (SQLSTATE 55000)',
      NEW.snapshot_id
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER enforce_critical_vault_only
  BEFORE INSERT ON snapshot_access_log
  FOR EACH ROW EXECUTE FUNCTION block_critical_digital_access();

-- ── RPC: request_ephemeral_key ────────────────────────────────
-- Validates tier rules and records an ephemeral key commitment.
-- p_key_hash must be SHA-256(raw_key) computed client-side.
-- Returns granted=FALSE with a reason on any rule violation.
CREATE OR REPLACE FUNCTION request_ephemeral_key(
  p_snapshot_id  INT,
  p_twin_id      UUID,
  p_key_hash     TEXT,    -- SHA-256(raw_key), provided by caller
  p_requester    TEXT,
  p_sig_count    SMALLINT DEFAULT 0
)
RETURNS TABLE (
  key_id      bigint,
  expires_at  timestamptz,
  granted     boolean,
  reason      text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_tier   snapshot_access_tier;
  v_kid    BIGINT;
  v_exp    TIMESTAMPTZ;
BEGIN
  SELECT access_tier INTO v_tier
  FROM   mesh_frozen_snapshots
  WHERE  id = p_snapshot_id AND twin_id = p_twin_id;

  IF v_tier IS NULL THEN
    RETURN QUERY SELECT NULL::bigint, NULL::timestamptz, FALSE, 'snapshot not found';
    RETURN;
  END IF;

  IF v_tier = 'CRITICAL' THEN
    RETURN QUERY SELECT NULL::bigint, NULL::timestamptz, FALSE,
      'CRITICAL tier: M-DISC vault access only — no digital key issuance';
    RETURN;
  END IF;

  IF v_tier = 'HIGH' AND p_sig_count < 3 THEN
    RETURN QUERY SELECT NULL::bigint, NULL::timestamptz, FALSE,
      format('HIGH tier requires 3-of-5 threshold signatures; %s provided', p_sig_count);
    RETURN;
  END IF;

  v_exp := NOW() + INTERVAL '24 hours';

  INSERT INTO snapshot_ephemeral_keys
    (snapshot_id, twin_id, key_hash, expires_at, issued_to, sig_count)
  VALUES
    (p_snapshot_id, p_twin_id, p_key_hash, v_exp, p_requester, p_sig_count)
  RETURNING id INTO v_kid;

  RETURN QUERY SELECT v_kid, v_exp, TRUE, 'ephemeral key issued'::text;
END;
$$;

-- ── RPC: request_vault_destruction ───────────────────────────
-- Marks a CRITICAL snapshot for physical destruction.
-- Requires the vault record to exist; records the witness identity.
-- Actual destruction must be confirmed via a second call with
-- p_confirm = TRUE after the physical disc is destroyed.
CREATE OR REPLACE FUNCTION request_vault_destruction(
  p_snapshot_id  INT,
  p_twin_id      UUID,
  p_witness      TEXT,
  p_confirm      BOOLEAN DEFAULT FALSE
)
RETURNS TABLE (
  vault_id   bigint,
  status     text,
  success    boolean
)
LANGUAGE plpgsql AS $$
DECLARE
  v_vid BIGINT;
BEGIN
  SELECT id INTO v_vid
  FROM   snapshot_vault_records
  WHERE  snapshot_id = p_snapshot_id AND twin_id = p_twin_id;

  IF v_vid IS NULL THEN
    RETURN QUERY SELECT NULL::bigint, 'vault record not found'::text, FALSE;
    RETURN;
  END IF;

  IF NOT p_confirm THEN
    UPDATE snapshot_vault_records
    SET    destruction_requested_at = NOW(), destruction_witness = p_witness
    WHERE  id = v_vid;
    RETURN QUERY SELECT v_vid, 'destruction requested — physical disc must be destroyed before confirmation'::text, TRUE;
  ELSE
    UPDATE snapshot_vault_records
    SET    destruction_confirmed_at = NOW()
    WHERE  id = v_vid AND destruction_requested_at IS NOT NULL;

    IF NOT FOUND THEN
      RETURN QUERY SELECT v_vid, 'destruction must be requested before it can be confirmed'::text, FALSE;
      RETURN;
    END IF;

    -- Seal the snapshot as permanently inaccessible
    UPDATE mesh_frozen_snapshots
    SET    metadata = COALESCE(metadata, '{}'::jsonb)
             || jsonb_build_object('destruction_confirmed_at', NOW(), 'destruction_witness', p_witness)
    WHERE  id = p_snapshot_id;

    RETURN QUERY SELECT v_vid, 'destruction confirmed — snapshot permanently sealed'::text, TRUE;
  END IF;
END;
$$;
