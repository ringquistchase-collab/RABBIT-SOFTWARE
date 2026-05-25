# Node Specifications — HEAD_01 & CHEST_01

## HEAD_01 — EEG + Skin RF

### EEG Layer (24-channel)

| Parameter | Value |
|-----------|-------|
| Channels | 24 (extended 10–20 system) |
| Sample rate | 256 Hz |
| Key electrodes | F3, F4 (FAA valence), Fz (θ/α arousal), O1, O2 (V1/V4) |

#### FAA Valence (Frontal Alpha Asymmetry)

```
FAA = ln(P_F4_α) − ln(P_F3_α)

valence = normalize(FAA, range=[−2.0, +2.0])

valence > 0  → positive affect / approach motivation  (F4 > F3 alpha)
valence < 0  → negative affect / withdrawal           (F3 > F4 alpha)
valence = −0.23 → mild withdrawal / negative valence
```

#### Fz θ/α Arousal

```
theta_power = bandpower(Fz, 4–8 Hz)
alpha_power = bandpower(Fz, 8–13 Hz)
theta_alpha_ratio = theta_power / alpha_power

arousal = normalize(theta_alpha_ratio, range=[0.0, 1.5])

arousal = 0.71 → elevated arousal (raw θ/α ≈ 0.62–0.80)
```

Threshold for convergence gate: `theta_alpha_ratio > 0.60`

---

### RF Layer (10.245 GHz — Skin Dielectric)

| Parameter | Value |
|-----------|-------|
| Carrier | 10.245 GHz (vascular Doppler band) |
| Mode | Pulsed body-coupled RF |
| Measured properties | ε_r (relative permittivity), σ (electrical conductivity S/m) |

#### Skin Dielectric Properties

At 10.245 GHz, skin dielectric properties are:

| State | ε_r (typical) | σ (S/m) | Δφ (rad) |
|-------|--------------|---------|----------|
| Dry/resting | 35–40 | 1.0–1.5 | 0.00–0.02 |
| Mild arousal | 40–45 | 1.5–2.0 | 0.02–0.05 |
| **Stress** | **45–55** | **2.0–2.5** | **> 0.05** |
| Acute stress | > 55 | > 2.5 | > 0.08 |

ε_r increases with sweat gland activation → ionic conductivity ↑ → phase advance.

#### GSR Proxy (Phase Threshold)

```
Δφ = φ_stress − φ_baseline

Δφ > 0.05 rad  → stress threshold crossed
Δφ = 0.06 rad  → current measured state (stress confirmed)
```

---

## CHEST_01 — Cardiac + Hormone

### ELISA Cortisol Assay

| Parameter | Value |
|-----------|-------|
| Method | ELISA (Enzyme-Linked Immunosorbent Assay) |
| Range | 0.1–1.0 ng/mL |
| Threshold | **> 0.75 ng/mL** → convergence gate met |
| Current value | 0.78 ng/mL (stress-elevated; normal waking = 0.2–0.4 ng/mL) |

Cortisol 0.78 ng/mL maps to ~215 nmol/L — below the CRITICAL tier cortisol
spike (>900 nmol/L at age 7/22) but confirming active HPA axis stress response.

### RF Layer (10.251 GHz — Cardiac Doppler)

| Parameter | Value |
|-----------|-------|
| Carrier | 10.251 GHz (U nucleotide band + 0.001 GHz codon offset) |
| Mode | Continuous-wave Doppler |
| Target | Aortic / ventricular wall motion |
| Output | Beat-to-beat RR intervals → HRV |

10.251 GHz differs from HEAD_01's 10.245 GHz — each node encodes a distinct
molecular RF signature. CHEST_01's carrier is in the U (uracil) band (10.25 GHz
base) with a +1 MHz codon offset encoding the cardiac-specific nucleotide context.

#### HRV Validation

CHEST_01 Doppler provides:
- RR intervals → time-domain HRV (SDNN, RMSSD)
- LF (0.10 Hz) and HF (0.25 Hz) power → LF/HF ratio
- Cross-validates `cross_modal_states.hrv_lf_hf_ratio`

---

## Three-Condition Convergence Gate

```sql
CONVERGENCE_MET  iff
    cortisol_ng_ml    > 0.75          (CHEST_01 ELISA)
  AND gsr_delta_phi   > 0.05          (HEAD_01 skin RF Δφ)
  AND theta_alpha_ratio > 0.60        (HEAD_01 EEG Fz)
```

All three conditions independently confirmed → `convergence_events` record inserted.

---

## Convergence Token Output

When the gate fires, a canonical state string is serialized and hashed:

```
state_string = f"valence={valence:.2f}_arousal={arousal:.2f}_gsr={gsr:.2f}_cortisol={cortisol:.2f}"
token        = SHA-256(state_string.encode('utf-8'))
```

### Current State Token

```
Input  : "valence=-0.23_arousal=0.71_gsr=0.06_cortisol=0.78"
SHA-256: 75d2ffd4d20e84c64c134e2643742719402324fda0e6af3f0693f4203294651f
```

Interpretation:
- `valence = −0.23` — mild negative affect; F3 alpha > F4 alpha
- `arousal = 0.71` — elevated arousal; θ/α ≈ 0.71 at Fz
- `gsr = 0.06` — Δφ 0.06 rad; stress threshold exceeded
- `cortisol = 0.78` — 0.78 ng/mL; HPA axis active

This token is stored in `convergence_tokens.state_hash` and optionally feeds
the chemo-crypto pipeline as the `chemo_salt` input (`chemo_hashes` table).

---

## Node Cross-Reference

| Node | Carrier | Primary sensing | Convergence role |
|------|---------|----------------|-----------------|
| HEAD_01 | 10.245 GHz | 24ch EEG (FAA, Fz θ/α), skin ε_r/σ, GSR Δφ | Δφ > 0.05 AND θ/α > 0.60 |
| CHEST_01 | 10.251 GHz | Cardiac Doppler (HRV), ELISA cortisol | cortisol > 0.75 ng/mL |

---

## Schema Mapping

| Concept | Table / Column |
|---------|---------------|
| FAA valence | `faa_readings.valence_score` |
| Fz θ/α arousal | `faa_readings.arousal_score`, `cross_modal_states.theta_alpha_ratio` |
| Skin ε_r | `skin_dielectric_readings.epsilon_r` |
| Skin σ | `skin_dielectric_readings.conductivity_s_m` |
| GSR Δφ | `gsr_readings.phase_shift_rad` |
| ELISA cortisol | `elisa_assay_readings.concentration_ng_ml` |
| CHEST_01 HRV | `cross_modal_states.hrv_lf_hf_ratio` |
| Convergence gate | `convergence_events` |
| Convergence token | `convergence_tokens.state_hash` |
