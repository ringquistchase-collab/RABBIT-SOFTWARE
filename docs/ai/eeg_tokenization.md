# EEG Tokenization & GSR SDR Pipeline

## Overview

Two coupled sensing pipelines feed the AI model layer:

1. **GSR SDR Capture** — Galvanic Skin Response inferred from WRIST_L body-coupled
   phase shift, routed to HEAD_01. Encodes skin stress as σ (electrical conductivity
   proxy) via GNU Radio.

2. **TFM-Tokenizer** — Time-Frequency Masked Tokenizer converts single-channel EEG
   (256 Hz) into a discrete token vocabulary (4096 tokens) encoding θ/α/γ band
   motifs and V1/V4 visual cortex activation patterns.

The two pipelines are cross-referenced: GSR stress state gates token masking ratio
and enriches provenance chain metadata.

---

## 1. GSR SDR Capture

### Signal Path

```
WRIST_L node (biometric group, nodes 9–26)
    │  body-coupled RF, skin surface propagation
    │  carrier: 10.23–10.28 GHz
    ▼
Phase shift measurement
    │  skin stress → ↑ sweat gland activity → ↑ ionic conductivity
    │  → phase advance in body-coupled RF signal
    │  φ_stress = +0.06 rad  (nominal skin stress encoding)
    ▼
GNU Radio SDR processing
    │  IQ sample → phase demodulation → conductivity proxy
    │  σ_proxy = f(φ_measured − φ_baseline)
    │  calibrated to σ = 2.1 S/m under measured stress state
    ▼
HEAD_01 reception
    │  phase-coherent reception confirms body-coupled path
    │  (propagation_medium = 'skin' for WRIST_L → HEAD_01 segment)
    ▼
gsr_readings table
```

### Phase → Conductivity Mapping

Skin electrical conductivity σ (S/m) modulates the phase of a body-coupled RF signal
through the dielectric properties of the skin/sweat layer:

```
σ_proxy = σ_baseline + k × (φ_measured − φ_baseline)
```

Where:
- `σ_baseline` — resting conductivity from `chemo_baselines` (electrolyte era baseline)
- `φ_baseline` — stored in `phase_coherence_baselines.baseline_coherence`
- `k` — calibration constant (units: S·m⁻¹·rad⁻¹), fit per `calibration_era_baselines`
- `φ_measured − φ_baseline = +0.06 rad` → `σ = 2.1 S/m` (stress state)

### Stress Thresholds

| σ (S/m) | Phase shift (rad) | State |
|---------|-----------------|-------|
| < 0.5 | < +0.01 | Resting / calm |
| 0.5–1.5 | +0.01–+0.04 | Mild arousal |
| 1.5–2.5 | +0.04–+0.08 | **Stress / active** |
| > 2.5 | > +0.08 | Acute stress / fight-or-flight |

σ = 2.1 S/m (φ = +0.06 rad) → **Stress / active** state confirmed.
Cross-referenced with `cross_modal_states.stress_confirmed` (θ/α + HRV gate).

### GNU Radio Processing Chain

```
SDR RX (WRIST_L IQ stream, 10.245 GHz)
    │
    ▼
Low-noise amplifier block (LNA)
    │
    ▼
Complex band-pass filter (10.23–10.28 GHz pass)
    │
    ▼
Phase demodulator (atan2(Q, I))
    │
    ▼
Baseline subtraction (φ_measured − φ_baseline)
    │
    ▼
Kalman filter (noise reduction on phase track)
    │
    ▼
Conductivity proxy compute: σ = σ_baseline + k × Δφ
    │
    ▼
gsr_readings INSERT (phase_shift_rad, conductivity_proxy_s_m)
```

---

## 2. TFM-Tokenizer (Time-Frequency Masked Tokenizer)

### Architecture

```
Input: single-channel EEG, 256 Hz
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STFT ANALYSIS                                                      │
│  Window: 256 samples (1 s)    Hop: 64 samples (250 ms)             │
│  Frequency range: 1–50 Hz                                           │
│  Bands extracted:                                                    │
│    δ  0.5–4 Hz   — deep sleep / unconscious                        │
│    θ  4–8 Hz     — memory, drowsiness, meditation                   │
│    α  8–13 Hz    — relaxed focus, visual idle                       │
│    β  13–30 Hz   — active cognition, motor planning                 │
│    γ  30–50 Hz   — high-level binding, V1/V4 activation            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  2D time-frequency spectrogram
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  TIME-FREQUENCY MASKING (p = 0.15)                                  │
│  • 15% of time-frequency patches randomly zeroed                    │
│  • Enables self-supervised pre-training (masked auto-encoding)      │
│  • At inference: masking disabled (p = 0.0)                         │
│  • Under ACUTE_DISTRESS: mask ratio raised to p = 0.30             │
│    (high-noise physiological state → more regularization)           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  masked spectrogram patches
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  VECTOR QUANTIZATION (VQ-VAE codebook)                              │
│  • Codebook size: 4096 tokens                                       │
│  • Each token = one spectrogram patch quantized to nearest centroid │
│  • Commitment loss during training; straight-through estimator      │
│  • Token space organized by:                                        │
│      band (δ/θ/α/β/γ) × cortex region (V1/V4/frontal/temporal)    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
Output token sequence example:
[token_θ0.64, token_γ12.3, token_V1_edge, token_α8.7, token_γ31.1_V4_color]
```

### Token Label Format

```
token_{band}{power_db}[_{region}_{pattern}]

Examples:
  token_θ0.64          — theta band, 0.64 dB relative power
  token_γ12.3          — gamma band, 12.3 dB relative power
  token_V1_edge        — V1 primary visual cortex, edge detection pattern
  token_γ31.1_V4_color — 31.1 Hz gamma, V4 color processing activation
  token_α8.7           — alpha band, 8.7 dB (visual idle / eyes-closed)
```

### V1 / V4 Visual Cortex Patterns

| Region | Function | EEG Signature | Token Pattern |
|--------|----------|---------------|---------------|
| V1 | Primary visual — edge detection, orientation | γ 30–45 Hz burst | `token_V1_edge`, `token_V1_orient` |
| V2 | Secondary visual — contour, depth | γ 35–45 Hz | `token_V2_contour` |
| V4 | Color, object form | γ 40–50 Hz sustained | `token_V4_color`, `token_V4_form` |
| MT/V5 | Motion detection | β/γ 20–40 Hz | `token_MT_motion` |

V1/V4 activation tokens are cross-referenced with UWB gesture events
(`uwb_gesture_events`) — visual cortex firing during HAND_WAVE or
POSTURE transitions confirms intentional gesture vs reflexive motion.

### Masking Schedule

| State | Mask ratio (p) | Source |
|-------|---------------|--------|
| Normal inference | 0.00 | — |
| Pre-training | 0.15 | Default TFM |
| MILD_STRESS | 0.15 | `cross_modal_states.stress_level` |
| STRESS | 0.20 | `stress_confirmed = TRUE` |
| ACUTE_DISTRESS | 0.30 | `stress_level = ACUTE_DISTRESS` |

---

## Schema Mapping

| Concept | Table / Column |
|---------|---------------|
| WRIST_L → HEAD_01 phase shift | `gsr_readings.phase_shift_rad` |
| Conductivity proxy | `gsr_readings.conductivity_proxy_s_m` |
| Token vocabulary | `eeg_token_vocab` (4096 rows) |
| Token sequences | `eeg_token_sequences.tokens` (JSONB array) |
| V1/V4 events | `visual_cortex_events` |
| Masking ratio | `eeg_token_sequences.mask_ratio` |
| Provenance link | `eeg_token_sequences.provenance_hash` |
| Stress gate | `cross_modal_states.stress_confirmed` |
| GSR → stress cross-ref | `gsr_readings` ↔ `cross_modal_states` |

---

## Integration with Existing Systems

```
mesh_node_readings (WRIST_L, skin propagation, 10.245 GHz)
    │
    ▼
gsr_readings (phase_shift +0.06 rad → σ 2.1 S/m)
    │
    ├──► cross_modal_states (stress gate)
    │
    └──► eeg_token_sequences (GSR stress → mask_ratio adjustment)
              │
              ├──► visual_cortex_events (V1/V4 token detection)
              │
              ├──► eeg_provenance_chain (SHA-3 hash appended)
              │
              └──► chemo_hashes (token sequence → branch routing enrichment)
```
