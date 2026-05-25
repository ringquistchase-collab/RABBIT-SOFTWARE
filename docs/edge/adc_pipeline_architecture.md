# Analog-to-Digital Biological Data Pipeline — RabbitOS Architecture

## Overview

All biological data originates as continuous analog signals from physical sensors.
The RabbitOS Edge Gateway converts, encrypts, routes, analyzes, and distributes
these signals across the mesh. This document defines every stage of that pipeline.

---

## Full Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│  PHYSICAL LAYER                                                     │
│                                                                     │
│  Heart Sensor   EEG Electrodes   Skin Galvanic   Vascular Doppler   │
│  (analog mV)    (analog µV)      (analog kΩ)     (analog Doppler)  │
└──────────┬──────────────┬──────────────┬──────────────┬────────────┘
           │              │              │              │
           ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ADC CONVERSION LAYER                                               │
│                                                                     │
│  • Sampling rate: node-class dependent (EEG 256 Hz, cardiac 1 kHz) │
│  • Resolution: 16–24 bit                                            │
│  • Anti-aliasing filter applied pre-digitization                    │
│  • Raw ADC counts → calibrated physical units (mV, µV, Hz)         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  TRANSPORT LAYER                                                    │
│                                                                     │
│  Bluetooth LE 5.2 (short-range nodes)                               │
│  WiFi 6 / WireGuard mesh (relay nodes 43–47)                        │
│  Body-coupled RF 10.23–10.28 GHz (intra-mesh, authenticated)       │
│                                                                     │
│  Packet format: [node_id | seq | adc_sample[] | raw_checksum]      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  RABBITOS EDGE GATEWAY                                              │
│                                                                     │
│  Stage 1 — TIMESTAMP                                                │
│    • UTC nanosecond timestamp attached on first gateway receipt     │
│    • Monotonic sequence number assigned per node per session        │
│    • NTP-synchronized; drift < 1 ms                                 │
│                                                                     │
│  Stage 2 — ENCRYPT                                                  │
│    • AES-256-DNA-FH applied: hop_seed = SHA-256(dna_root ⊕ prf_hz) │
│    • Ed25519 signature over [node_id + timestamp + payload_hash]    │
│    • Payload encrypted at rest before any DB write                  │
│                                                                     │
│  Stage 3 — TELEMETRY                                                │
│    • Node health: RSSI, SNR, packet loss rate written to            │
│      `edge_gateway_telemetry`                                       │
│    • Propagation medium classified (body_coupled / skin / air)      │
│    • Phase coherence score computed                                  │
│                                                                     │
│  Stage 4 — ANALYZE                                                  │
│    • Anomaly detection: deviation_sigma vs calibration baseline     │
│    • Cross-modal: EEG θ/α × HRV LF/HF → stress_confirmed           │
│    • Body-coupled identity gate: 4-condition check                  │
│    • EEG provenance hash appended to SHA-3 ledger                   │
│                                                                     │
│  Stage 5 — ROUTE                                                    │
│    • access_tier decision: EXISTENTIAL → block / CRITICAL → airgap │
│    • HIGH → encrypted M-DISC / synthetic only                       │
│    • LOW / MINIMAL → DB write + live stream                         │
│    • Anomalies → `mesh_anomalies` + optional alert                  │
│                                                                     │
│  Stage 6 — SUMMARIZE                                                │
│    • Windowed aggregates (1 s / 10 s / 60 s) written to            │
│      `pipeline_summaries`                                           │
│    • Bio-NFT snapshot hash computed for XRPL minting               │
│    • ZK proof generated for PoBW if snapshot_access_tier = LOW      │
│                                                                     │
│  Stage 7 — VISUALIZE                                                │
│    • Live mesh overlay pushed to `mesh_node_readings` real-time sub │
│    • OBS WebRTC stream updated (streaming/ module)                  │
│    • React dashboard receives Supabase real-time payload            │
│                                                                     │
│  Stage 8 — SHARE (authorized aggregates only)                       │
│    • `collaborator_grants` checked: shows_dna_root enforced FALSE   │
│    • Synthetic reconstruction served instead of raw biological data │
│    • Aggregate metrics only for LOW/MINIMAL tier events             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SUPABASE DATA LAYER                                                │
│                                                                     │
│  mesh_node_readings      — per-node per-sample digital readings     │
│  edge_gateway_sessions   — gateway session lifecycle                │
│  edge_gateway_telemetry  — RSSI, SNR, packet loss per node          │
│  pipeline_summaries      — windowed aggregates                      │
│  ingestion_pipeline_log  — per-packet stage audit trail             │
│  cross_modal_states      — EEG × HRV stress state                   │
│  mesh_anomalies          — anomaly events from any stage            │
│  snapshot_zk_proofs      — XRPL / PoBW proof records                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Stage Detail: ADC Conversion

| Node class | Sample rate | Bit depth | Physical unit | Calibration |
|------------|-------------|-----------|---------------|-------------|
| EEG (1–19) | 256 Hz | 24-bit | µV | `calibration_era_baselines` |
| Biometric (9–26) | 1000 Hz | 16-bit | mV / BPM | Per-era baseline |
| Vascular (27–32) | 500 Hz | 16-bit | cm/s (Doppler) | Per-era baseline |
| Kinetic (33–42) | 200 Hz | 16-bit | m/s² / rad/s | Per-era baseline |
| Relay/spine (43–47) | — | — | Relay only | n/a |

---

## Stage Detail: Transport Packets

```
Bluetooth LE / WiFi packet structure
┌────────┬────────┬──────────┬──────────────────────┬───────────┐
│node_id │seq_num │timestamp │adc_samples[]         │checksum   │
│2 bytes │4 bytes │8 bytes   │variable (16/24-bit)  │4 bytes    │
└────────┴────────┴──────────┴──────────────────────┴───────────┘

Body-coupled RF packet (10.23–10.28 GHz)
┌─────────────┬──────────────┬──────────────┬─────────────────────┐
│hop_channel  │phase_tag     │payload_enc   │ed25519_sig          │
│(DNA-FH seq) │(IQ snapshot) │(AES-256)     │64 bytes             │
└─────────────┴──────────────┴──────────────┴─────────────────────┘
```

---

## Stage Detail: Access Tier Routing

```
Incoming packet
    │
    ├─ access_tier = EXISTENTIAL → BLOCK (SQLSTATE 55000); log attempt only
    ├─ access_tier = CRITICAL    → airgap queue; no DB payload write
    ├─ access_tier = HIGH        → encrypt + M-DISC index write; synthetic for collaborators
    ├─ access_tier = LOW         → DB write; collaborator summary OK
    └─ access_tier = MINIMAL     → live stream + broadcast; Bio-NFT eligible
```

---

## Schema Mapping

| Pipeline stage | Table(s) |
|----------------|---------|
| Timestamp + sequence | `edge_gateway_sessions`, `ingestion_pipeline_log` |
| Encryption record | `ingestion_pipeline_log.encryption_alg`, `node_tuning_events` |
| Telemetry | `edge_gateway_telemetry` |
| Anomaly / analysis | `mesh_anomalies`, `cross_modal_states`, `internal_reflection_events` |
| Routing decision | `ingestion_pipeline_log.route_decision`, `life_age_events.access_tier` |
| Summaries | `pipeline_summaries` |
| Visualization | `mesh_node_readings` (real-time subscription) |
| Authorized share | `collaborator_grants`, `bio_simulation_session` |
