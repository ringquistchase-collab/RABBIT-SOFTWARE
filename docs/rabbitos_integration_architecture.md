# RabbitOS Integration Architecture

RABBIT-SOFTWARE is a modular biometric mesh operating system. Each module is independently deployable and communicates through the shared Supabase data layer.

---

## Module Map

| Directory     | Domain                                | Key Interfaces |
|---------------|---------------------------------------|----------------|
| `core/`       | Digital twin lifecycle, mesh identity | `twin_identity`, `mesh_nodes`, `calibration_era_baselines` |
| `rf_mesh/`    | 47-node biometric RF mesh, SDR profiles, bio-Doppler | `sdr_node_profiles`, `relay_path_events` |
| `ai_models/`  | EEG classification, anomaly detection, LLM provenance | DeepSeek API, EEG provenance chain |
| `blockchain/` | XRPL Bio-NFT minting, PoBW proofs, ZK proofs | `snapshot_zk_proofs`, XRPL ledger |
| `security/`   | AES-256-DNA-FH, Ed25519 signing, OpenFHE homomorphic ops | `node_tuning_events`, vault records |
| `networking/` | P2P RF connections, WebRTC signalling, WireGuard mesh | `p2p_connections`, `p2p_handshakes` |
| `streaming/`  | OBS/WebRTC integrations, live mesh overlay | `mesh_node_readings`, live state |
| `gaming/`     | Telemetry overlays, biometric-driven game optimization | `kinetic_gait_events`, `intent_action_events` |
| `edge/`       | ARM + Android Termux runtimes, PersonalMemoryHost SQLite | `node_hardware_profiles` |
| `medical/`    | Research-grade signal provenance, HIPAA boundary layer | `bio_operation_log`, EEG provenance chain |
| `docs/`       | Architecture, security model, API references | — |
| `ui/`         | React/TypeScript dashboard, sensor views | `src/` components |

---

## Data Flow

```
Physical sensors / SDR hardware
        │
        ▼
   rf_mesh/  ──────────────────────────────────────────────────┐
  (acquire, filter, SDR profile)                               │
        │                                                       │
        ▼                                                       ▼
   core/  (digital twin, mesh topology)           ai_models/  (EEG provenance,
  (node readings, edge weights, anomalies)         DeepSeek analysis, ledger)
        │                                                       │
        ▼                                                       ▼
   Supabase DB  ←──────────── security/ ──────────────────────►
  (all tables,                (AES-256-DNA-FH,
   RLS policies,               Ed25519, vault)
   real-time subs)
        │
        ├──► blockchain/  (XRPL Bio-NFT, ZK proofs)
        ├──► networking/  (P2P RF, WebRTC)
        ├──► streaming/   (OBS overlay, live mesh)
        ├──► gaming/      (telemetry, biometric HID)
        ├──► edge/        (ARM / Termux mirror)
        └──► ui/          (React dashboard)
```

---

## RF Mesh Topology

- **47 nodes**: EEG (1–8 extended to 1–19), biometric (9–26), vascular (27–32), kinetic (33–42), relay/spine (43–47)
- **Carrier band**: 10.23–10.28 GHz (molecular RF formula)
- **Encryption**: AES-256-DNA-FH (age 33 / 2025 — current)
- **PRF fingerprint**: unique per node, 0.83–1.1 Hz band

## Security Invariants

- `shows_dna_root = FALSE` — DNA Root Key never exposed to collaborators
- `vault_location_hash` only — plaintext location never stored in DB
- CRITICAL tier: `block_critical_digital_access` trigger always raises SQLSTATE 55000
- CRISPR destructive edits require `approved_by_sig` matching locked `dna_root_sig`
- Applied `node_tuning_events` are immutable (trigger blocks UPDATE/DELETE)
- Node RF pattern is cryptographically un-clonable via DNA-FH

---

## Development Phases

| Phase | Age | Label | Status |
|-------|-----|-------|--------|
| 1 | 1–5 | `PRIMITIVE_MESH` | Seeded |
| 2 | 6–12 | `COORDINATION_SYNC` | Seeded |
| 3 | 13–18 | `HORMONAL_OVERWRITE` | Seeded |
| 4 | 18+ | `ADULT` | Active |

---

## Migration Index

| File | Domain |
|------|--------|
| `20260524001` | Audit log |
| `20260524002` | Typed sensors |
| `20260524003` | Vector embeddings |
| `20260525` | Digital twin + 47-node mesh |
| `20260526` | Vascular nodes (27–32) |
| `20260527` | Archives |
| `20260528` | Access tiers |
| `20260529` | Kinetic nodes (33–42) |
| `20260530` | Calibration era baselines |
| `20260531` | Bot registry |
| `20260532` | Simulation corpus |
| `20260533` | SDR propagation profiles |
| `20260534` | P2P RF interactions |
| `20260535` | Bio/RNA/DNA node integration |
| `20260536` | Bio operations + codon correction |
| `20260537` | Node hardware + tuning history |
