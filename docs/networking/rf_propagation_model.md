# RF Propagation Model — Body-Coupled vs Over-the-Air

## Overview

The 47-node biometric mesh operates across two physically distinct propagation
regimes. Correctly classifying a received signal into one of these regimes is
the foundation of biological identity verification — a body-coupled signal
carries a deterministic phase fingerprint that cannot be replicated by an
external transmitter.

---

## Propagation Regimes

### Body-Coupled (`body_coupled`)

Signal travels through biological tissue — skin, muscle, bone, and fluid —
rather than through free space.

| Property | Characteristic |
|----------|---------------|
| Internal reflectors | Heart wall, lung surface, rib cage, aorta, diaphragm |
| Phase relationship | **Fixed / coherent** — reflector geometry is constant |
| Interference pattern | Deterministic constructive/destructive pattern unique to anatomy |
| Amplitude stability | High — tissue path loss is consistent beat-to-beat |
| Multipath | Short, predictable; dominated by organ geometry |
| Carrier range | 10.23–10.28 GHz (molecular RF band) |
| Path loss reference | ~72 dB (skin-to-skin body-coupled path) |

The constructive/destructive interference pattern produced by the heart and
lung reflectors creates a **standing-wave signature** that is anatomically
unique and phase-locked to the cardiac cycle. This is what
`internal_reflection_events` and `phase_coherence_baselines` capture.

### Over-the-Air (`air`)

Signal travels through free space between transmitter and receiver with no
body-tissue path.

| Property | Characteristic |
|----------|---------------|
| External reflectors | Walls, furniture, moving objects, other people |
| Phase relationship | **Random / incoherent** — reflector geometry changes continuously |
| Interference pattern | Non-deterministic multipath scatter |
| Amplitude stability | Low — Rayleigh/Rician fading |
| Multipath | Long, unpredictable |
| Path loss reference | ~48 dB (line-of-sight air path) |

An over-the-air signal cannot reproduce the fixed phase constellation of a
body-coupled signal without physically passing through the same biological
tissue.

### Skin-Surface (`skin`)

Intermediate regime — surface wave propagation along the body boundary layer.
Phase relationships are partially coherent; used for short inter-node segments
(e.g. wrist to elbow).

---

## SDR IQ Analysis: Constellation Stability

The clearest way to distinguish the two regimes at the IQ level:

```
Body-coupled                     Over-the-air
─────────────────────────────    ─────────────────────────────
 Q │    ·                         Q │  · ·   ·
   │  ·   ·                         │    ·  ·  ·
   │    ·                           │  ·   ·  ·  ·
───┼────────── I               ───┼────────────── I
   │    ·                           │   ·    ·
   │  ·   ·                         │  ·  ·    ·
                                    │      ·  ·

 Stable cluster — tight σ        Random walk — wide σ
 phase-locked to heartbeat        no fixed attractor
```

**Body-coupled IQ signature:**
- Phase points cluster around fixed angles corresponding to dominant reflectors
- Cluster centroid oscillates at the cardiac PRF (~1 Hz), breathing rate (~0.2 Hz)
- `phase_coherence` → high (0.85–1.0 typical)
- `matched_baseline = TRUE` in `internal_reflection_events`

**Over-the-air IQ signature:**
- Phase points execute a random walk across the IQ plane
- No stable attractor; no periodic cluster motion
- `phase_coherence` → low (<0.5 typical for external signals)
- `matched_baseline = FALSE`

---

## Schema Mapping

| Concept | Table / Column |
|---------|---------------|
| Propagation regime | `propagation_medium` enum: `air \| skin \| body_coupled` |
| Per-node phase baseline | `phase_coherence_baselines.baseline_coherence` |
| Coherence threshold | `phase_coherence_baselines.match_threshold` (default 0.85) |
| Heartbeat reflector confirmation | `internal_reflection_events.matched_baseline` |
| Deviation from baseline | `internal_reflection_events.deviation_sigma` |
| Per-reading medium | `mesh_node_readings.propagation_medium` |
| Relay path coherence | `relay_path_events.phase_coherence` |
| Path loss by medium | `sdr_node_profiles.path_loss_skin_db` / `path_loss_air_db` |

---

## Identity Verification Logic

A received signal is accepted as **biologically authentic** only when ALL of:

1. `propagation_medium = 'body_coupled'`
2. `phase_coherence >= match_threshold` (≥ 0.85)
3. `internal_reflection_events.matched_baseline = TRUE`
   — heart, lung, and/or aorta reflection present at correct phase offsets
4. `intent_action_events.fraud_score < 0.1`
   — corticospinal latency within calibration-era bounds

Failing any condition raises a `PATTERN_INJECTION` anomaly
(`mesh_anomalies.anomaly_type`).

---

## Frequency Hopping Interaction

From age 16 (2008), limb nodes use DNA-based frequency hopping
(`AES_256_DNA_FH` from age 33). The hop sequence is derived from:

```
hop_seed = SHA-256(dna_root_hash XOR sdr.prf_hz)
```

Because `prf_hz` is the unique per-node pulse repetition frequency
(0.83–1.1 Hz band, body-coupled PRF fingerprint), the hop sequence is
inseparable from the biological signal. An external transmitter that does not
pass through the same tissue does not have access to the correct `prf_hz`
value and cannot reconstruct the hop sequence.

This is why the body-coupled path is the **only** medium through which the
node RF pattern can be correctly decoded: the encryption key is physically
embedded in the propagation path.
