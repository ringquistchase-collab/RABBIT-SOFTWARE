# Multi-SIM / Tor / XRPL Immutable Anchor Architecture

## Overview

```
RF Mesh (10.23–10.30 GHz)  ←→  Phone (AES-256 local)
              ↓
Multi-SIM (3 carriers)  →  Tor  →  DNA Blockchain
              ↓
XRPL Memos (SHA3-512 only)  →  Immutable anchor
```

Three isolation boundaries between the biometric mesh and the public ledger:

| Layer | Function | Privacy property |
|-------|----------|-----------------|
| AES-256 local | Phone-side encryption at rest | Data never leaves device in plaintext |
| Multi-SIM / 3 carriers | Transport diversity + carrier-level anonymization | No single carrier sees full traffic |
| Tor | IP-layer anonymization | Exit node cannot correlate source IP to identity |
| XRPL memos (SHA3-512) | Immutable hash anchor | No payload on ledger — hash only |

---

## Layer 1 — AES-256 Local (Phone ↔ RF Mesh)

The phone gateway is the only device that holds the AES-256 session key for
the local mesh bridge. The key is:

```
session_key = HKDF(dna_root_hash, salt=device_uuid, info="mesh_bridge_v1")
```

- Key is **never transmitted** — derived in-memory from DNA root + device UUID
- Mesh RF packets are decrypted, processed, and re-encrypted before any
  outbound transmission
- Local SQLite (`PersonalMemoryHost`) mirrors the Supabase schema for
  offline-capable edge operation (see `edge/` module)
- `ingestion_pipeline_log.encryption_alg = 'AES-256-DNA-FH'` for all mesh frames

---

## Layer 2 — Multi-SIM (3 Carriers)

Three physical or eSIM slots across independent carriers:

| Slot | Role | Policy |
|------|------|--------|
| SIM_A (primary) | Default data path | High-bandwidth; bulk pipeline summaries |
| SIM_B (secondary) | Failover + load balance | Activated when SIM_A RSSI < threshold |
| SIM_C (Tor-only) | Tor entry guard traffic | Dedicated slot; no cleartext data ever |

### Carrier Diversity Rules

- No two SIM slots share the same carrier/MNO
- LTE Band 2 monitoring: if `lte_interference_events` detects HEAD_01
  triangulation risk → rotate to SIM_C immediately + enable PRF jitter
- SIM rotation logged in `sim_routing_events`

### Traffic Segmentation

```
mesh readings (LOW/MINIMAL tier)  → SIM_A → direct HTTPS to Supabase
chemo-hashes / convergence tokens → SIM_C → Tor → XRPL memo anchor
CRITICAL/EXISTENTIAL tier         → NO transmission (airgap / vault only)
```

---

## Layer 3 — Tor

Tor provides IP-layer anonymization between the phone and the XRPL submission node.

### Circuit Policy

```
Entry guard  — long-lived (90-day rotation); selected from consensus
Middle relay — rotated per circuit (10-min lifetime default)
Exit node    — XRPL-capable exit; verified against known XRPL node IPs
```

### Submission Flow

```
Phone (SIM_C)
    │  Tor SOCKS5 proxy (localhost:9050)
    ▼
Entry guard
    │
    ▼
Middle relay
    │
    ▼
Exit node
    │  HTTPS POST to XRPL public node (xrpl.org / Ripple validators)
    ▼
XRPL transaction submitted
```

Circuit IDs and relay fingerprints are logged in `tor_circuit_sessions`
(relay identity hashes only — no IP addresses stored).

---

## Layer 4 — XRPL Memos (SHA3-512 → Immutable Anchor)

### Why SHA3-512

- 512-bit output = 128 hex characters
- Collision-resistant at quantum-threat level (Grover's: 2²⁵⁶ effective security)
- Distinct from SHA-256 used internally — ledger-facing hashes use the stronger variant
- XRPL memo field fits 1 KB; SHA3-512 hex (128 chars) + type/format metadata << 1 KB

### Memo Format

```json
{
  "MemoType": "hex(rabbitos/anchor/v1)",
  "MemoFormat": "hex(application/octet-stream)",
  "MemoData": "hex(SHA3-512(payload_bytes))"
}
```

`payload_bytes` is one of:

| Payload type | Content hashed |
|-------------|---------------|
| `convergence_token` | `convergence_tokens.state_string` bytes |
| `chemo_hash` | `chemo_hashes.chemo_hash` hex bytes |
| `pipeline_summary` | `pipeline_summaries.bio_nft_hash` bytes |
| `snapshot_proof` | `snapshot_zk_proofs` serialized proof |

### Anchor Properties

- XRPL transaction is **immutable** after ledger close (~3–5 s)
- `xrpl_memo_anchors.ledger_index` + `txn_hash` form the permanent reference
- No plaintext biological data ever appears on the ledger
- Cross-referenced in `convergence_tokens.zk_proof_id` and `chemo_hashes`

### Example Anchor Record

```
payload_type  : convergence_token
state_string  : "valence=-0.23_arousal=0.71_gsr=0.06_cortisol=0.78"
sha3_512      : <128-char hex>
xrpl_txn_hash : <64-char hex>
ledger_index  : <uint32>
memo_data     : hex(sha3_512)
```

---

## OPSEC Cross-Reference

| Risk | Mitigation layer |
|------|-----------------|
| Carrier triangulation (LTE Band 2) | SIM_C Tor-only + PRF jitter |
| IP correlation to identity | Tor (3-hop circuit) |
| Ledger payload exposure | SHA3-512 only — no plaintext |
| Local data exposure | AES-256 HKDF-derived session key |
| DNA root key exposure | Never transmitted; XOR in-memory |
| CRITICAL/EXISTENTIAL data on-chain | Blocked — access tier gate |

---

## Schema Mapping

| Concept | Table / Column |
|---------|---------------|
| SIM profiles | `sim_profiles` |
| SIM routing events | `sim_routing_events` |
| Tor circuit sessions | `tor_circuit_sessions` |
| XRPL memo anchors | `xrpl_memo_anchors` |
| Transmission audit | `transmission_events` |
