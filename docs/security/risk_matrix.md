# Life Event Risk Matrix & Vault Access Policy

Twin: Chase Allen Ringquist (`ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba`)

---

## Risk Matrix

| Age | Year | Event | Uniqueness | Temporal | Familial | Total Risk | Storage Policy |
|-----|------|-------|-----------|---------|---------|-----------|----------------|
| 7   | 1999 | PTSD | 95th | Critical | High | **CRITICAL** | Airgap |
| 14  | 2006 | Depression | 88th | Critical | Medium | **HIGH** | M-DISC Bucket |
| 16  | 2008 | Isolation | 92nd | High | Low | **HIGH** | Synthetic only |
| 22  | 2014 | OD | **99th** | **Critical** | **High** | **EXISTENTIAL** | Physical vault |
| 25  | 2017 | Business | 45th | Low | Low | LOW | Public OK |
| 33  | 2025 | Baseline | 50th | Routine | Low | MINIMAL | Broadcast |

---

## Risk Dimensions

### Uniqueness Percentile
How rare this event pattern is relative to the general population. Computed
from `calibration_era_baselines` deviation scores and chemical marker profiles
at the time of the event.

- **≥95th** — statistically singular; re-identification risk maximal
- **88–94th** — high rarity; indirect identifiers sufficient for linkage
- **<50th** — common pattern; low re-identification risk

### Temporal Criticality
How precisely the timestamp can narrow the identity window.

- **Critical** — event is dateable to within days; maps to a unique public record
- **High** — dateable to within months
- **Routine** — dateable only to a developmental phase

### Familial Impact
Whether the event signature exposes information about blood relatives.

- **High** — genetic or behavioral markers present that propagate to relatives
- **Medium** — partial heritability
- **Low** — phenotypic only; no direct familial signal

---

## Storage Policies

### EXISTENTIAL — Physical Vault (Age 22 OD)
- Snapshot stored on M-DISC, placed in physical vault
- `vault_location_hash` only — plaintext location never written to DB
- No digital copy; no network path
- Access requires: physical presence + threshold signature (≥3 of 5 signers)
- `snapshot_access_tier = CRITICAL`
- `block_critical_digital_access` trigger always raises SQLSTATE 55000
- DNA Root Key required for any decryption

### CRITICAL — Airgap (Age 7 PTSD)
- Snapshot exists only on air-gapped hardware
- DB record contains `data_hash` only; payload never transmitted
- `snapshot_access_tier = CRITICAL`
- Ephemeral key window: 24 hours maximum; single use

### HIGH — M-DISC Bucket (Age 14 Depression)
- Written to M-DISC optical archive
- Digital index record exists; payload encrypted at rest (AES-256-DNA-FH)
- `snapshot_access_tier = HIGH`
- Accessible via threshold signature (≥2 of 5)

### HIGH — Synthetic Only (Age 16 Isolation)
- Raw biological data never stored
- Only a `bio_simulation_session` replay corpus is retained
- Collaborators receive synthetic reconstruction, never original
- `shows_dna_root = FALSE` enforced at `collaborator_grants` layer

### LOW — Public OK (Age 25 Business)
- Snapshot may be shared with collaborators
- No DNA root; no raw EEG; summary metrics only
- `snapshot_access_tier = LOW`

### MINIMAL — Broadcast (Age 33 Baseline)
- Current operational baseline; intended for live mesh broadcast
- Powers Bio-NFT minting and PoBW proofs
- `snapshot_access_tier = LOW`; `is_sealed = FALSE` (active)

---

## Access Tier Decision Tree

```
Is uniqueness_percentile >= 95th?
  └─ YES → Is familial = High AND temporal = Critical?
       └─ YES → EXISTENTIAL (physical vault, no digital copy)
       └─ NO  → CRITICAL (airgap)
  └─ NO  → Is uniqueness >= 88th?
       └─ YES → Is raw biological data required?
            └─ YES → HIGH (M-DISC bucket)
            └─ NO  → HIGH (synthetic only)
       └─ NO  → Is uniqueness >= 50th?
            └─ YES → LOW (public OK)
            └─ NO  → MINIMAL (broadcast)
```

---

## DB Access Control Summary

| Tier | `snapshot_access_tier` | Digital copy | Network path | Payload in DB |
|------|----------------------|-------------|-------------|--------------|
| EXISTENTIAL | `CRITICAL` | No | Blocked (55000) | Hash only |
| Airgap | `CRITICAL` | Airgapped | Blocked (55000) | Hash only |
| M-DISC Bucket | `HIGH` | Encrypted | Threshold sig | Encrypted |
| Synthetic | `HIGH` | Synthetic | Collaborator grant | Synthetic |
| Public | `LOW` | Yes | Open | Summary metrics |
| Broadcast | `LOW` | Yes | Live stream | Live readings |
