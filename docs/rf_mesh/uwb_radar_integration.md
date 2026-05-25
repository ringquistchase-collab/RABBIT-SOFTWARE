# Ultra-Wideband (UWB) Radar Integration

## Overview

UWB radar is a complementary sensing layer to the existing 47-node 10.23–10.28 GHz
molecular RF mesh. Where the molecular mesh reads cryptographic identity and
chemical state via body-coupled phase shifts, UWB provides non-contact, through-
clothing vital signs extraction, precise sub-centimeter ranging, gesture/posture
classification, and presence detection — without cameras or electrodes.

Chase's existing pulsed 10.23–10.30 GHz system already shares UWB principles
(wide relative bandwidth, short pulses). Adding true UWB radar chips upgrades
the mesh with ranging accuracy and imaging capability while staying compliant
with FCC Part 15 Subpart F.

---

## Technical Principles

### What Makes a Signal UWB

| Property | Threshold |
|----------|-----------|
| Absolute bandwidth | ≥ 500 MHz |
| Fractional bandwidth | ≥ 20% of centre frequency |
| FCC emission limit | −41.3 dBm/MHz (EIRP) |
| Primary band (FCC) | 3.1–10.6 GHz |
| Imaging / medical band | 3.1–10.6 GHz (Part 15.515) |

### Key Properties

| Property | Description |
|----------|-------------|
| Range resolution | c / (2B) — e.g., 500 MHz BW → 30 cm; 2 GHz BW → 7.5 cm |
| Micro-Doppler | Detects sub-mm chest movement → breathing and heart rate |
| Material penetration | Penetrates walls, clothing, foliage at lower UWB frequencies |
| Low PSD | −41.3 dBm/MHz → coexists with WiFi/Bluetooth/BLE |
| Multipath robustness | Short pulses resolve direct vs reflected paths |

### Modulation Techniques

| Technique | Description | Use Case |
|-----------|-------------|----------|
| IR-UWB | Discrete short pulses (~200 ps) | Ranging, vital signs, gesture |
| FMCW-UWB | Wideband chirp sweep | Imaging, ground-penetrating |
| DS-UWB | Direct-sequence spread | Communication + ranging |

---

## Hardware

| Chip | Vendor | Mode | Notes |
|------|--------|------|-------|
| SR040 | NXP | Ranging + radar | IEEE 802.15.4z; FiRa certified |
| SR150 | NXP | Ranging + radar | Enhanced radar profile; lower power |
| DW3000 | Qorvo | Ranging | Sub-ns ToF accuracy |
| BGT60TR13C | Infineon | 60 GHz FMCW | Gesture / presence; mmWave |
| P2G | Infineon | 24 GHz | Vital signs; lower freq penetration |

**Recommended for RABBIT-SOFTWARE**: NXP SR040/SR150 (UWB, 6.0–8.5 GHz band)
for vital signs + ranging; Infineon BGT60TR13C for close-range gesture nodes.

---

## Signal Processing Pipeline

```
UWB Pulse TX
    │
    ▼
Echo RX (matched filter)
    │
    ├──► Range profile: time-of-flight → distance per reflector
    │
    ├──► Doppler processing: FFT across slow-time → velocity per target
    │
    ├──► Micro-Doppler: spectrogram → breathing rate (0.1–0.5 Hz), HR (0.8–2.5 Hz)
    │
    ├──► MUSIC algorithm: direction-of-arrival estimation (multi-static array)
    │
    └──► ML classifier: activity / gesture / fall detection
```

Key algorithms:
- **Matched filtering** — pulse compression; improves SNR by pulse duration / noise bandwidth
- **Clutter removal** — static background subtraction to isolate moving targets
- **STFT / CWT** — time-frequency analysis for breathing/cardiac micro-Doppler
- **SAR imaging** — synthetic aperture reconstruction for through-wall imaging

---

## Vital Signs Extraction

Chest micro-movements encode two physiological signals:

| Signal | Frequency range | Amplitude | UWB method |
|--------|----------------|-----------|------------|
| Breathing rate | 0.1–0.5 Hz | 5–20 mm | Slow-time Doppler / bandpass |
| Heart rate | 0.8–2.5 Hz | 0.2–1.0 mm | Micro-Doppler spectrogram |

Both are extracted non-contact, through clothing, at ranges up to ~3 m (indoor).

**Cross-validation with molecular mesh**:
- UWB breathing rate should correlate with `phase_ripple_breath_rad` (±0.03 rad)
- UWB heart rate should correlate with `sdr_node_profiles.prf_hz` (0.83–1.1 Hz PRF fingerprint)
- Discrepancy between UWB and body-coupled readings → `uwb_vital_signs.cross_modal_agreement = FALSE` → anomaly

---

## Integration with Existing 47-Node Mesh

```
Existing molecular RF mesh (10.23–10.28 GHz, body-coupled)
    │  Reads: phase identity, chemical state, PRF fingerprint
    │
    ▼
UWB radar layer (6.0–8.5 GHz, over-the-air)
    │  Reads: vital signs, range, gesture, presence, through-clothing
    │
    ▼
Fusion layer
    │  UWB HR + breathing ←→ molecular PRF fingerprint
    │  UWB gesture ←→ EEG intent signal (intent_action_events)
    │  UWB presence ←→ mesh_anomalies (spoofing detection)
    ▼
cross_modal_states / uwb_vital_signs / uwb_gesture_events
```

**Spoofing detection**: A UWB presence signal without a corresponding body-coupled
molecular RF signal indicates a relay attack or physical absence of the registered
twin → `mesh_anomalies.anomaly_type = 'PATTERN_INJECTION'` raised.

---

## Regulatory Notes (FCC Part 15 Subpart F)

| Requirement | Value |
|-------------|-------|
| EIRP emission limit | −41.3 dBm/MHz (all UWB devices) |
| Handheld imaging devices | 3.1–10.6 GHz; requires law enforcement coordination |
| Medical imaging | 3.1–10.6 GHz Part 15.515; indoor operation only |
| Through-wall devices | 1.99–10.6 GHz; restricted to government/law enforcement |

**Personal bio-sensing nodes** (vital signs, gesture, non-imaging) operate under
the general UWB indoor/outdoor rules — no coordination required. The −41.3 dBm/MHz
limit keeps average SAR negligible; below thermal and non-thermal safety thresholds
for continuous body-worn operation.

---

## Standards

| Standard | Scope |
|----------|-------|
| IEEE 802.15.4z | UWB PHY for ranging |
| FiRa Consortium | Interoperability profile for ranging |
| CCC Digital Key | UWB automotive access |
| IEEE 802.15.4a | Legacy UWB PHY (superseded by 4z) |

---

## Schema Mapping

| Concept | Table / Column |
|---------|---------------|
| UWB node hardware profile | `uwb_node_profiles` |
| UWB radar frames | `uwb_frames` |
| Breathing rate | `uwb_vital_signs.breathing_rate_hz` |
| Heart rate | `uwb_vital_signs.heart_rate_hz` |
| Range measurement | `uwb_range_measurements` |
| Gesture event | `uwb_gesture_events` |
| Cross-modal agreement | `uwb_vital_signs.cross_modal_agreement` |
| Anomaly | `mesh_anomalies` (type PATTERN_INJECTION — UWB/molecular mismatch) |

---

## Future Integration (2026+)

- Multi-static UWB array (nodes 43–47 relay/spine as radar anchors)
- AI fusion: UWB + EEG + IMU for full activity classification
- Through-wall imaging mode (restricted; government use only under current FCC rules)
- Integration with `chemo_indicators` for non-contact glucose / hydration sensing via UWB dielectric measurement
