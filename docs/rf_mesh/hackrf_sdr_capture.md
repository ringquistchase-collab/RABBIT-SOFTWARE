# HackRF SDR Capture & LTE Interference Side-Channel

## Overview

Two external RF phenomena confirm the body-coupled mesh from outside the system:

1. **HackRF SDR** — direct IQ capture of the 10.245 GHz body-coupled signal.
   Validates the PRF fingerprint (0.83 Hz spectral lines) and detects the 3rd
   harmonic at 30.735 GHz with an upconverter.

2. **LTE Band 2 harmonic leakage** — non-linear mixing product at 1935 MHz
   detected by cellular base stations. Pulsed interference signature allows
   multi-tower triangulation of HEAD_01 to ±10 m.

Both phenomena are logged, OPSEC-assessed, and tied to the mesh identity layer.

---

## 1. HackRF SDR Capture

### Capture Parameters

| Parameter | Value |
|-----------|-------|
| Hardware | HackRF One |
| Centre frequency | 10.245 GHz (requires upconverter block) |
| IQ sample rate | 10 MHz (Nyquist bandwidth ±5 MHz) |
| Bit depth | 8-bit IQ |
| Pulse envelope width | 1.2 ms |
| Pulse repetition frequency | 0.83 Hz |
| Inter-pulse period | ~1.205 s |

### Pulse Envelope

```
Amplitude
    │
    │     ┌────────┐                              ┌────────┐
    │     │ 1.2 ms │                              │ 1.2 ms │
    │     │        │                              │        │
────┼─────┘        └──────────────────────────────┘        └──────
    │
    0         1.205 s (PRF 0.83 Hz period)
```

A sharp 1.2 ms envelope at 0.83 Hz creates a **comb spectrum** in the frequency
domain: spectral lines spaced at ±0.83 Hz (and harmonics thereof: ±1.66, ±2.49 Hz…)
around the carrier at 10.245 GHz.

### Frequency Domain (IQ spectrum around 10.245 GHz)

```
Power (dBm)
    │
    │         ●                         ← carrier 10.245000 GHz
    │      ●     ●                      ← ±0.83 Hz PRF sidebands
    │   ●           ●                   ← ±1.66 Hz (2nd PRF harmonic)
    │●                 ●                ← ±2.49 Hz (3rd PRF harmonic)
    └──────────────────────────────── Frequency offset (Hz)
         -2.5  -1.7  -0.83  0  +0.83  +1.7  +2.5
```

This comb is the **PRF fingerprint** — identical to `sdr_node_profiles.prf_hz`
(0.83–1.1 Hz band per node). External HackRF capture validates the on-body PRF
without body coupling.

### 3rd Harmonic (30.735 GHz)

```
3 × 10.245 GHz = 30.735 GHz
```

Detectable with a 10.245 GHz → 30.735 GHz upconverter (×3 tripler). Presence of
the 3rd harmonic confirms the source is a coherent, high-spectral-purity oscillator
(not noise floor), consistent with AES-256-DNA-FH encrypted body-coupled RF.

3rd harmonic also carries:
- PRF comb at ±2.49 Hz (3 × 0.83 Hz) around 30.735 GHz
- Hop sequence is present in the tripled signal (DNA-FH structure preserved)
- Phase coherence preserved → `internal_reflection_events` geometry still readable

---

## 2. LTE Band 2 Harmonic Leakage (OPSEC Risk)

### Signal Path to 1935 MHz

| Step | Detail |
|------|--------|
| Source | Body-coupled RF at 10.245 GHz, pulsed 0.83 Hz |
| Non-linear element | Skin/tissue junction or nearby electronics |
| Mixing product | 10245 MHz − 8310 MHz LO = **1935 MHz** |
| LTE Band 2 downlink | 1930–1990 MHz |
| Adjacent channel | 1935 MHz — within Band 2 downlink |

### What the Base Station Sees

```
LTE Band 2 downlink receiver (base station, 1935 MHz)
    │
    │  Detects pulsed interference:
    │    • Pulse width: 1.2 ms
    │    • Repetition: 0.83 Hz
    │    • Power: elevated above noise floor (~−100 dBm at 50 m range)
    │    • Pattern: highly periodic → NOT thermal noise
    │
    ▼
Interference classification: PULSED_PERIODIC
    │
    ▼
Report to network SON (Self-Organizing Network) / RAN analytics
```

### Triangulation of HEAD_01

Three or more LTE base stations independently detect the same 1935 MHz pulsed
signature. Time-difference-of-arrival (TDoA) or received-signal-strength (RSS)
triangulation resolves HEAD_01's physical location:

```
BS_A ─────────────────────────────────────────────────────●
          d_A = c × t_A                                  HEAD_01
BS_B ─────────────────────────────────────────────────────●
          d_B = c × t_B              location accuracy: ±10 m

BS_C ─────────────────────────────────────────────────────●
          d_C = c × t_C
```

**Accuracy: ±10 m** — sufficient to identify building, floor (with height data),
and outdoor position within one city block.

### EID / eSIM Context

- **EID 8903...** — eSIM Identifier for the cellular device near HEAD_01.
  The eSIM is physically co-located with the mesh gateway device.
  LTE base station logs correlate EID with the pulsed interference event,
  linking the cellular identity to the physical mesh emission.

### OPSEC Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Physical location disclosure (±10 m) | **HIGH** | Pulse envelope randomization; jitter on 0.83 Hz PRF |
| EID ↔ mesh correlation | **HIGH** | Separate air-gapped cellular device from mesh gateway |
| 3rd harmonic (30.735 GHz) external detection | MEDIUM | Shielding on upconverter path |
| PRF fingerprint capture (HackRF) | MEDIUM | DNA-FH hop sequence prevents decoding without body coupling |

### PRF Jitter Mitigation

To defeat triangulation, add ±50 ms random jitter to the PRF:

```
prf_jitter_ms = random(−50, +50)
actual_prf_hz = 0.83 Hz + jitter_correction
```

This smears the 0.83 Hz spectral line into a broadened feature, raising the
noise floor for base station interference pattern classification.
Stored in `sdr_node_profiles.prf_jitter_ms`.

---

## Schema Mapping

| Concept | Table / Column |
|---------|---------------|
| HackRF capture session | `hackrf_captures` |
| PRF spectral lines | `prf_spectral_lines` |
| 3rd harmonic measurement | `harmonic_measurements` |
| LTE interference event | `lte_interference_events` |
| BS triangulation | `location_triangulations` |
| PRF jitter setting | `sdr_node_profiles.prf_jitter_ms` (added by this migration) |
| HEAD_01 location record | `location_triangulations.resolved_location` |
