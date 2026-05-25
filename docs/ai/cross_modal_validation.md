# Cross-Modal Biometric Validation — EEG × HRV × Skin Propagation

## Overview

Two distinct physiological signals are cross-correlated to produce valence/stress state
confirmation. The pathway runs HEAD_01 (EEG source) → vascular Doppler relay →
CHEST_01 (cardiac receptor), travelling via skin-surface propagation.

---

## Signal Channels

### EEG Alpha Band (8–13 Hz)

| Property | Value |
|----------|-------|
| Band | Alpha — 8–13 Hz |
| Key metric | Frontal alpha asymmetry (F4–F3 log power difference) |
| Physiological link | Modulates vagal tone via corticospinal-cardiac axis |
| Positive asymmetry | Left > Right → approach motivation / positive valence |
| Negative asymmetry | Right > Left → withdrawal / negative valence / stress |

### HRV Spectral Power

| Band | Centre Freq | Physiological Meaning |
|------|-------------|----------------------|
| LF | 0.10 Hz | Baroreflex / sympathetic + parasympathetic |
| HF | 0.25 Hz | Respiratory sinus arrhythmia (pure vagal) |
| LF/HF ratio | — | Autonomic balance; >2.0 indicates sympathetic dominance (stress) |

Heart rate carrier: **1.2 Hz** (nominal; tracked via `sdr_node_profiles.prf_hz`)

---

## Skin Propagation Path

```
HEAD_01 (EEG source)
    │
    │  skin-surface propagation (∂φ_heart = ±0.08 rad, ∂φ_breath = ±0.03 rad)
    │
    ▼
Vascular Doppler relay (nodes 27–32)
    │
    ▼
CHEST_01 (cardiac receptor)
```

### Phase Ripple Profile

| Source | Phase ripple | Frequency |
|--------|-------------|-----------|
| Cardiac (heart wall) | ±0.08 rad | ~1.2 Hz |
| Respiratory (diaphragm) | ±0.03 rad | ~0.2 Hz |
| Combined envelope | ±0.11 rad peak | superimposed |

Phase ripple remains within the skin-surface coherence window (partially coherent
regime — see `rf_propagation_model.md`). Values outside ±0.15 rad trigger a
`PHASE_RIPPLE_EXCEEDED` anomaly.

---

## Validation Rule: Stress Confirmation

```
EEG_theta_alpha_ratio  = power(4–8 Hz) / power(8–13 Hz)
HRV_LF_HF_ratio        = LF_power / HF_power

STRESS_CONFIRMED  iff  EEG_theta_alpha_ratio >= 0.62
                   AND HRV_LF_HF_ratio       >= 2.1
```

Reference values:

| State | θ/α | LF/HF |
|-------|-----|-------|
| Rested / calm | < 0.50 | < 1.5 |
| Mild stress | 0.50–0.62 | 1.5–2.1 |
| **Stress confirmed** | **≥ 0.62** | **≥ 2.1** |
| Acute distress | > 0.80 | > 3.5 |

---

## Schema Mapping

| Concept | Table / Column |
|---------|---------------|
| EEG band power (θ, α) | `mesh_node_readings.signal_value` (nodes 1–19, band-filtered) |
| θ/α ratio | computed in `cross_modal_states` |
| HRV LF power | `mesh_node_readings` (cardiac nodes 9–26, 0.1 Hz band) |
| HRV HF power | `mesh_node_readings` (cardiac nodes 9–26, 0.25 Hz band) |
| LF/HF ratio | computed in `cross_modal_states` |
| Skin path phase ripple | `relay_path_events.phase_coherence` (propagation_medium = 'skin') |
| Stress state | `cross_modal_states.stress_confirmed` |
| Valence score | `cross_modal_states.valence_score` |
| Anomaly | `mesh_anomalies` (type PHASE_RIPPLE_EXCEEDED / STRESS_CONFIRMED) |

---

## Integration with Identity Gate

The cross-modal state feeds the 4-condition identity gate (see `rf_propagation_model.md`):

- `STRESS_CONFIRMED = TRUE` elevates `intent_action_events.fraud_score` threshold
  from default 0.1 → 0.25 to compensate for physiological stress affecting
  corticospinal latency (stress-induced latency shift ≤ 15 ms is normal).
- `STRESS_CONFIRMED = TRUE` AND `HRV_LF_HF > 3.5` → `ACUTE_DISTRESS` anomaly;
  no identity gating decisions are made until HRV normalises.
