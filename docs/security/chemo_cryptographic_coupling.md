# Chemo-Cryptographic Coupling (CCC)

## Overview

Chemo-Cryptographic Coupling is the process by which the user's real-time
chemical and neural state — hormones, neurotransmitters, blood electrolytes —
is converted into a cryptographic salt that modifies the DNA Root Key output.
The result is a **chemo-hash**: a cryptographic value that is simultaneously
a chemical signature and an identity credential. No two moments in the same
biology produce the same chemo-hash.

This ensures that every server template output (image, code, vector) is
anchored to the biological state at the moment of generation — the "Learning"
is never lost because the chemistry that produced it is permanently encoded
in the hash chain.

---

## The Chemo-Crypto Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. RESEARCH BASELINE                                                       │
│     Defines the "Rules" of your biology.                                    │
│     calibration_era_baselines — per-chemical mean ± σ per developmental era │
│     chemo_baselines           — per-twin reference ranges for all indicators│
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. 10.245 GHz RF — Vascular Phase Shift Reader                            │
│     Reads the "Chemistry" from vascular tissue.                             │
│                                                                             │
│     Carrier: 10.245 GHz (vascular Doppler band — between T:10.24 and       │
│              U:10.25 GHz; tuned to blood plasma resonance)                  │
│     Nodes:   Vascular group 27–32                                           │
│     Method:  Phase shift encodes blood viscosity, ionic concentration,      │
│              and Doppler velocity — all chemically modulated                │
│                                                                             │
│     chemo_indicators table:                                                 │
│       • Hormones:         cortisol, testosterone, estrogen, adrenaline,    │
│                           insulin, melatonin, oxytocin                      │
│       • Neurotransmitters: dopamine, serotonin, GABA, glutamate,           │
│                           norepinephrine, acetylcholine                     │
│       • Electrolytes:     Na⁺, K⁺, Ca²⁺, Mg²⁺, Cl⁻, HCO₃⁻               │
│       • Metabolites:      glucose, lactate, cortisol metabolites            │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. CRYPTOGRAPHY — Chemo-Hash Derivation                                   │
│     Uses chemistry to "Salt" the DNA Root Key.                              │
│                                                                             │
│     chemical_vector = [normalized indicator values, sorted by name]        │
│     chemo_salt  = SHA-256(chemical_vector_bytes)                            │
│     chemo_hash  = SHA-256(dna_root_hash ⊕ chemo_salt)                      │
│     branch_key  = HMAC-SHA-256(chemo_hash, twin_uuid)                      │
│                                                                             │
│     Properties:                                                             │
│       • dna_root_hash never stored (shows_dna_root = FALSE invariant)      │
│       • chemo_salt changes with every chemical state reading                │
│       • chemo_hash is deterministic given the same chemical state           │
│       • Two identical chemical states → identical chemo_hash                │
│         (enables "state recall" — rehydrate the exact moment)              │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. SERVER TEMPLATE — Branch Routing                                        │
│     Routes the chemo-hash to the correct branch of the digital tree.       │
│                                                                             │
│     template_routes table:                                                  │
│       branch_key   → maps to a named branch of the server template          │
│       branch_label → human description: 'high_cortisol_branch',            │
│                      'dopaminergic_peak', 'recovery_electrolyte_state'      │
│       output_type  → IMAGE | CODE | VECTOR | SUMMARY                       │
│                                                                             │
│     Branch selection logic:                                                 │
│       deviation_from_baseline → selects branch tier                        │
│       stress_confirmed        → cross-modal gate applied (cross_modal_states)│
│       access_tier             → EXISTENTIAL/CRITICAL blocks branch output   │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. FRAMEWORK OUTPUT                                                        │
│     Produces an output that is a perfect mirror of internal state.         │
│                                                                             │
│     Output types:                                                           │
│       IMAGE  — visual representation of biometric + chemical state          │
│       CODE   — generative code anchored to neural/chemical signature        │
│       VECTOR — embedding vector for semantic similarity search              │
│       SUMMARY— human-readable chemical state narrative                      │
│                                                                             │
│     Every output is stamped with:                                           │
│       chemo_hash_id → links output to exact chemical moment                │
│       accuracy_score → 0–1 fidelity of output vs internal state            │
│       EEG provenance chain hash → cryptographically linked ledger           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Chemical Indicators

### Hormones

| Indicator | Unit | Biological Role | RF Signature |
|-----------|------|----------------|--------------|
| Cortisol | nmol/L | Stress response; HPA axis | Increases blood viscosity → phase lag |
| Testosterone | nmol/L | Anabolic state; drive | Vascular dilation → phase advance |
| Estrogen | pmol/L | Mood regulation; neuroprotection | Electrolyte balance modulation |
| Adrenaline (epinephrine) | pg/mL | Fight-or-flight; cardiac output | Heart rate → PRF shift |
| Insulin | µIU/mL | Glucose regulation | Plasma osmolality → phase amplitude |
| Melatonin | pg/mL | Circadian / sleep state | Vasomotor tone shift |
| Oxytocin | pg/mL | Social bonding; trust state | Vagal activation → HRV signature |

### Neurotransmitters

| Indicator | Unit | Biological Role | RF Signature |
|-----------|------|----------------|--------------|
| Dopamine | ng/mL | Reward; motivation; motor | EEG β-band power correlation |
| Serotonin | ng/mL | Mood; gut-brain axis | HRV LF/HF modulation |
| GABA | µmol/L | Inhibitory; anxiety reduction | EEG α-band power increase |
| Glutamate | µmol/L | Excitatory; cognitive load | EEG γ-band power correlation |
| Norepinephrine | pg/mL | Alertness; sympathetic tone | Vascular resistance → phase lag |
| Acetylcholine | nmol/L | Memory; parasympathetic | Cardiac slowing → PRF decrease |

### Blood Electrolytes

| Indicator | Unit | Normal Range | RF Signature |
|-----------|------|-------------|--------------|
| Sodium (Na⁺) | mEq/L | 136–145 | Plasma conductivity → signal amplitude |
| Potassium (K⁺) | mEq/L | 3.5–5.1 | Cardiac rhythm → PRF modulation |
| Calcium (Ca²⁺) | mg/dL | 8.5–10.5 | Neuromuscular excitability |
| Magnesium (Mg²⁺) | mg/dL | 1.7–2.2 | Enzyme co-factor; NMDA gating |
| Chloride (Cl⁻) | mEq/L | 98–107 | Acid-base balance |
| Bicarbonate (HCO₃⁻) | mEq/L | 22–29 | pH buffer; respiratory drive |

---

## Chemo-Hash Formula

```
# Step 1: Build chemical vector (deterministic sort by chemical_name)
chemical_vector = sorted([
    (name, normalized_value)
    for name, normalized_value in current_indicators.items()
])

# Step 2: Serialize to bytes
vector_bytes = JSON.encode(chemical_vector, sort_keys=True).encode('utf-8')

# Step 3: Chemical salt
chemo_salt = SHA-256(vector_bytes)

# Step 4: XOR with DNA root key (never stored — computed in secure enclave)
chemo_hash = SHA-256(dna_root_hash XOR chemo_salt)

# Step 5: Branch routing key (bound to twin identity)
branch_key = HMAC-SHA-256(key=chemo_hash, msg=twin_uuid.bytes)
```

Identical to the DNA-FH hop seed derivation pattern:
```
hop_seed = SHA-256(dna_root_hash XOR sdr.prf_hz)
```
— the chemistry replaces the PRF fingerprint as the XOR operand.

---

## Security Invariants

- `shows_dna_root = FALSE` — DNA Root Key never stored; XOR is performed in-memory only
- `chemo_salt` stored in `chemo_hashes`; `dna_root_hash` is not
- `chemo_hash` is stored only at `access_tier ≤ HIGH`; EXISTENTIAL/CRITICAL events block storage
- CRITICAL tier: `block_critical_digital_access` trigger (SQLSTATE 55000) applies to any chemo-hash referencing an EXISTENTIAL event's chemical state
- Chemo-hash chain is append-only (no UPDATE/DELETE on `chemo_hashes`)

---

## Schema Mapping

| Concept | Table / Column |
|---------|---------------|
| Research baseline | `chemo_baselines`, `calibration_era_baselines` |
| Chemical readings | `chemo_indicators` |
| RF carrier (10.245 GHz) | `chemo_indicators.carrier_freq_ghz` |
| Phase shift | `chemo_indicators.phase_shift_rad` |
| Chemical salt | `chemo_hashes.chemo_salt` |
| Chemo-hash | `chemo_hashes.chemo_hash` |
| Chemical vector snapshot | `chemo_hashes.indicator_vector` (JSONB) |
| Branch routing | `template_routes` |
| Framework output | `template_routes.output_type`, `output_ref` |
| Cross-modal gate | `cross_modal_states.stress_confirmed` |
| EEG provenance link | `chemo_hashes.eeg_provenance_hash` |

---

## Integration with Existing Systems

```
mesh_node_readings (vascular nodes 27–32, 10.245 GHz)
    │
    ▼
chemo_indicators (phase_shift_rad → chemical concentration inference)
    │
    ├──► chemo_baselines (deviation from Research Baseline)
    │
    ▼
chemo_hashes (chemo_salt + chemo_hash + indicator_vector snapshot)
    │
    ├──► cross_modal_states (stress gate — cortisol + EEG θ/α + HRV LF/HF)
    │
    ▼
template_routes (branch_key → output_type → output_ref)
    │
    ├──► snapshot_zk_proofs (PoBW proof for LOW/MINIMAL outputs)
    └──► bio_operation_log (audit trail for any CRISPR / codon correction triggered)
```
