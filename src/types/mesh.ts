// 26+6-node biometric mesh + Digital Twin types
// mirrors: supabase/migrations/20260525_mesh_digital_twin.sql
//          supabase/migrations/20260526_vascular_nodes.sql

export type NodeModality = 'eeg' | 'biometric' | 'vascular' | 'kinetic' | 'relay'
export type PropagationMedium = 'air' | 'skin' | 'body_coupled'
export type EegBand      = 'delta' | 'theta' | 'alpha' | 'beta' | 'gamma'
export type LifeEventType =
  | 'BIRTH'
  | 'DEVELOPMENTAL_MILESTONE'
  | 'TRAUMA'
  | 'RECOVERY'
  | 'PEAK_STATE'
  | 'BASELINE_CALIBRATION'
  | 'USER_DEFINED'
export type AnomalyLevel = 'INFO' | 'WARNING' | 'CRITICAL'
export type AnomalyType  =
  | 'TOPOLOGY_SHIFT'
  | 'IDENTITY_DEVIATION'
  | 'PATTERN_INJECTION'
  | 'COHERENCE_BREAK'

export type VascState =
  | 'BASELINE'
  | 'VASODILATION'
  | 'VASOCONSTRICTION'
  | 'TACHYCARDIA'
  | 'BRADYCARDIA'
  | 'ARRHYTHMIA'

export type SnapshotAccessTier = 'LOW' | 'HIGH' | 'CRITICAL'

// ── Node IDs as branded type ─────────────────────────────────
export type NodeId = number & { __brand: 'NodeId' }

export const EEG_NODE_IDS:       NodeId[] = Array.from({ length: 19 }, (_, i) => (i + 1)  as NodeId)
export const BIOMETRIC_NODE_IDS: NodeId[] = Array.from({ length: 7 },  (_, i) => (i + 20) as NodeId)
export const VASCULAR_NODE_IDS:  NodeId[] = Array.from({ length: 6 },  (_, i) => (i + 27) as NodeId)
export const KINETIC_NODE_IDS:   NodeId[] = Array.from({ length: 10 }, (_, i) => (i + 33) as NodeId)
export const ALL_NODE_IDS:       NodeId[] = [...EEG_NODE_IDS, ...BIOMETRIC_NODE_IDS, ...VASCULAR_NODE_IDS, ...KINETIC_NODE_IDS, ...RELAY_NODE_IDS]

export const VASCULAR_NODE_CODES: Record<number, string> = {
  27: 'CAROT_L', 28: 'CAROT_R',
  29: 'RADIAL_L', 30: 'RADIAL_R',
  31: 'FEMORAL_L', 32: 'FEMORAL_R',
}

export const RELAY_NODE_IDS:   NodeId[] = Array.from({ length: 5 }, (_, i) => (i + 43) as NodeId)

export const RELAY_NODE_CODES: Record<number, string> = {
  43: 'SPINE_C7', 44: 'SPINE_T4', 45: 'SPINE_T10',
  46: 'SPINE_L2', 47: 'SKIN_REF',
}

export const KINETIC_NODE_CODES: Record<number, string> = {
  33: 'SACRUM_L',    34: 'SACRUM_R',
  35: 'FEM_NERVE_L', 36: 'FEM_NERVE_R',
  37: 'PATELLA_L',   38: 'PATELLA_R',
  39: 'ANKLE_L',     40: 'ANKLE_R',
  41: 'PLANTAR_L',   42: 'PLANTAR_R',
}

// ── DB row types ─────────────────────────────────────────────

export interface TwinIdentity {
  id:               string
  subject_name:     string
  subject_dob:      string          // ISO date
  biological_hash:  string | null
  is_sealed:        boolean
  created_at:       string
  sealed_at:        string | null
}

export interface MeshNode {
  id:           NodeId
  node_code:    string              // 'Fp1' | 'GSR' | …
  modality:     NodeModality
  lobe_region:  string | null
  x_pos:        number | null
  y_pos:        number | null
  z_pos:        number | null
  description:  string | null
}

export interface MeshTopologyEdge {
  id:           number
  node_a:       NodeId
  node_b:       NodeId
  edge_type:    'cortical_adjacent' | 'cortical_long_range' | 'cross_modal'
  base_weight:  number
  distance_cm:  number | null    // anatomical path length; set on vascular edges
}

export interface LifeAgeEvent {
  id:                number
  twin_id:           string
  event_type:        LifeEventType
  event_date:        string          // ISO date
  age_years:         number | null
  age_years_end:     number | null   // null = point-in-time event
  label:             string
  description:       string | null
  dev_phase:         DevPhase | null
  token_types:       TokenType[] | null
  access_tier:       SnapshotAccessTier
  is_sealed:         boolean
  mesh_snapshot_id:  number | null
  created_at:        string
  sealed_at:         string | null
}

export interface MeshFrozenSnapshot {
  id:               number
  twin_id:          string
  life_event_id:    number | null
  label:            string
  captured_at:      string
  node_count:       number
  snapshot_hash:    string | null
  prev_hash:        string | null
  chain_hash:       string | null
  is_sealed:        boolean
  sealed_at:        string | null
  access_tier:      SnapshotAccessTier
  dev_phase:        DevPhase | null
  chemical_markers: ChemicalMarkers | null
  metadata:         Record<string, unknown> | null
}

export interface SnapshotVaultRecord {
  id:                       number
  snapshot_id:              number
  twin_id:                  string
  disc_id:                  string
  vault_location_hash:      string | null
  sealed_at:                string
  destruction_requested_at: string | null
  destruction_confirmed_at: string | null
  destruction_witness:      string | null
  metadata:                 Record<string, unknown> | null
}

export interface SnapshotEphemeralKey {
  id:          number
  snapshot_id: number
  twin_id:     string
  key_hash:    string     // SHA-256(raw_key) — raw key never stored
  issued_at:   string
  expires_at:  string    // always issued_at + 24hr
  used_at:     string | null
  revoked_at:  string | null
  issued_to:   string | null
  sig_count:   number
}

export interface SnapshotThresholdSigner {
  id:           number
  snapshot_id:  number
  twin_id:      string
  signer_index: number   // 1-5
  signer_pub:   string   // Ed25519 public key, base64
  signer_label: string | null
  added_at:     string
  revoked_at:   string | null
}

export interface SnapshotZkProof {
  id:                number
  snapshot_id:       number
  twin_id:           string
  proof_system:      'groth16' | 'plonk' | 'stark'
  proof_hash:        string
  public_inputs:     Record<string, unknown>
  xrpl_tx_hash:      string | null
  xrpl_ledger_index: number | null
  block_gpt_verdict: string | null   // 'CLEAN' | 'ANOMALY' | 'PENDING'
  block_gpt_score:   number | null   // 0.0 normal → 1.0 anomalous
  verified_at:       string | null
  created_at:        string
}

export interface SnapshotAccessLog {
  id:                number
  snapshot_id:       number
  twin_id:           string
  access_tier:       SnapshotAccessTier
  requester_id:      string
  granted:           boolean
  denial_reason:     string | null
  ephemeral_key_id:  number | null
  xrpl_tx_hash:      string | null
  accessed_at:       string
}

export interface FrozenNodeState {
  id:               number
  snapshot_id:      number
  node_id:          NodeId
  // EEG
  delta_power:      number | null
  theta_power:      number | null
  alpha_power:      number | null
  beta_power:       number | null
  gamma_power:      number | null
  dominant_band:    EegBand | null
  mean_amplitude:   number | null
  std_amplitude:    number | null
  // Biometric
  biometric_value:  number | null
  biometric_unit:   string | null
  // Vascular
  phase_shift_rad:  number | null
  pulse_amplitude:  number | null
  beat_interval_ms: number | null
  vasc_state:       VascState | null
  // Kinetic
  emg_uv:               number | null
  reflex_latency_ms:    number | null
  motor_intent_score:   number | null
  ground_impedance_ohm: number | null
  // Adjacency coherence at snapshot time
  coherence_map:    Record<string, number> | null
}

export interface MeshNodeReading {
  id:                    number
  twin_id:               string
  node_id:               NodeId
  sensor_id:             string
  timestamp:             string
  // EEG
  band:                  EegBand | null
  amplitude_uv:          number | null
  phase_deg:             number | null
  band_powers:           Partial<Record<EegBand, number>> | null
  // Biometric
  raw_value:             number | null
  // Vascular
  phase_shift_rad:       number | null   // RF phase shift from vessel wall displacement (rad)
  pulse_amplitude:       number | null   // pulsatile envelope amplitude (normalised 0-1)
  carrier_freq_ghz:      number | null   // RF carrier used (e.g. 10.245)
  beat_interval_ms:      number | null   // R-R interval at this node (ms)
  vasc_state:            VascState | null
  // Kinetic
  emg_uv:                number | null
  reflex_latency_ms:     number | null
  motor_intent_score:    number | null
  ground_impedance_ohm:  number | null
  // SDR / propagation
  prf_hz:                number | null   // pulse repetition frequency (0.83-1.1 Hz)
  bio_doppler_hz:        number | null   // bio-Doppler shift (Hz)
  path_loss_db:          number | null   // measured path loss (dB)
  propagation_medium:    PropagationMedium | null
  // Simulation
  ghost_filtered:        boolean | null
  corpus_session_id:     number | null
  intensity_level:       number | null
  sim_state:             SimulationState | null
  // Deviation
  baseline_snapshot_id:  number | null
  deviation_z:           number | null
}

export interface MeshEdgeWeight {
  id:            number
  twin_id:       string
  node_a:        NodeId
  node_b:        NodeId
  timestamp:     string
  coherence:     number    // 0-1
  phase_lag_ms:  number | null
}

export interface MeshAnomaly {
  id:                    number
  twin_id:               string
  detected_at:           string
  anomaly_type:          AnomalyType
  affected_nodes:        NodeId[]
  deviation_score:       number
  alert_level:           AnomalyLevel
  baseline_snapshot_id:  number | null
  resolved:              boolean
  resolved_at:           string | null
  metadata:              Record<string, unknown> | null
}

export interface VascularPulseEvent {
  id:                number
  twin_id:           string
  node_id:           NodeId
  sensor_id:         string
  detected_at:       string
  phase_shift_rad:   number
  pulse_amplitude:   number
  carrier_freq_ghz:  number
  ref_node_id:       NodeId | null   // null = this node is the proximal reference
  pwv_transit_ms:    number | null
  pwv_m_per_s:       number | null
  beat_seq:          number | null
  metadata:          Record<string, unknown> | null
}

export interface PwvResult {
  beat_count:       number
  mean_transit_ms:  number | null
  mean_pwv_m_per_s: number | null   // healthy resting range: 6–12 m/s
  distance_cm:      number | null
  node_a_code:      string
  node_b_code:      string
}

// ── RPC return type ──────────────────────────────────────────

export interface MeshDeviationRow {
  node_id:      NodeId
  node_code:    string
  modality:     NodeModality
  frozen_mean:  number | null
  live_mean:    number | null
  deviation_z:  number | null
  alert_level:  AnomalyLevel
}

export type DevPhase =
  | 'PRIMITIVE_MESH'       // ages 1-5:  neuroplasticity, TFM-LRN
  | 'COORDINATION_SYNC'    // ages 6-12: mind-vessel-heart tuning
  | 'HORMONAL_OVERWRITE'   // ages 13-18: puberty, TFM-SCR/PLV
  | 'ADULT'                // ages 18+:  operational

export type TokenType =
  | 'TFM_LRN'   // learning: high-amplitude low-freq EEG
  | 'TFM_KIN'   // kinetic vector: proprioceptive mapping
  | 'TFM_RWD'   // reward map: dopamine-sensitivity signature
  | 'TFM_HRT'   // heart sync: mind-vessel-heart calibration
  | 'TFM_SCR'   // sacral: puberty lower-node activation
  | 'TFM_PLV'   // pelvic: arousal baseline / performative authenticity
  | 'TFM_EXN'   // executive noise: prefrontal-amygdala conflict
  | 'TFM_VAS'   // vascular: RF resonance baseline

export interface ChemicalMarkers {
  GH?:                   number   // growth hormone 0-1
  oxytocin?:             number
  testosterone?:         number
  estrogen?:             number
  adrenaline?:           number
  dopamine_sensitivity?: number
}

export type SimulationState = 'LOW_STRESS_ZEN' | 'TRANSITION' | 'HIGH_STRESS_SHOCK'

export interface SdrNodeProfile {
  id:                         number
  twin_id:                    string
  node_id:                    NodeId
  prf_hz:                     number   // unique per twin, 0.83-1.1 Hz
  carrier_freq_ghz:           number
  path_loss_skin_db:          number   // ~72 dB
  path_loss_air_db:           number   // ~48 dB
  path_loss_body_coupled_db:  number | null
  bio_doppler_baseline_hz:    number | null
  bio_doppler_std_hz:         number | null
  reflection_sources:         string[]
  calibrated_at:              string
  is_active:                  boolean
}

export interface BioDopplerEvent {
  id:                  number
  twin_id:             string
  node_id:             NodeId
  sensor_id:           string
  detected_at:         string
  carrier_freq_ghz:    number
  prf_hz:              number
  doppler_shift_hz:    number
  tissue_velocity_cms: number | null    // cm/s
  reflection_source:   string          // 'vessel_wall' | 'skin' | 'heart' | 'lungs' | 'aorta'
  baseline_hz:         number | null
  deviation_hz:        number | null
  is_anomalous:        boolean
  reading_id:          number | null
  session_id:          number | null
  metadata:            Record<string, unknown> | null
}

export interface RelayPathEvent {
  id:                       number
  twin_id:                  string
  sensor_id:                string
  detected_at:              string
  source_node_id:           NodeId
  relay_node_id:            NodeId | null
  destination_node_id:      NodeId
  propagation_path:         NodeId[]
  source_phase_rad:         number
  relay_phase_rad:          number | null
  destination_phase_rad:    number
  source_to_relay_loss_db:  number | null
  relay_to_dest_loss_db:    number | null
  total_path_loss_db:       number | null
  source_medium:            PropagationMedium | null
  relay_medium:             PropagationMedium | null
  carrier_freq_ghz:         number
  prf_hz:                   number | null
  phase_coherence:          number           // 0.0-1.0
  match_threshold:          number           // default 0.85
  signature_matched:        boolean
  operation:                string | null    // e.g. 'remote_stress_confirmed'
  threshold_sig_id:         number | null
  heart_reflection_present: boolean
  lung_reflection_present:  boolean
  path_loss_anomaly:        boolean
  session_id:               number | null
  metadata:                 Record<string, unknown> | null
}

export interface InternalReflectionEvent {
  id:                      number
  twin_id:                 string
  node_id:                 NodeId
  sensor_id:               string
  detected_at:             string
  carrier_freq_ghz:        number
  reflection_source:       string   // 'heart' | 'lungs' | 'aorta' | 'diaphragm'
  phase_modulation_rad:    number
  modulation_freq_hz:      number | null
  baseline_modulation_rad: number | null
  baseline_std_rad:        number | null
  deviation_sigma:         number | null
  matched_baseline:        boolean   // TRUE = confirmed in-body origin
  reading_id:              number | null
}

export interface PhaseCoherenceBaseline {
  id:                 number
  twin_id:            string
  node_a_id:          NodeId
  node_b_id:          NodeId
  medium:             PropagationMedium
  baseline_coherence: number
  std_coherence:      number
  match_threshold:    number
  reflection_sources: string[]
  is_locked:          boolean
  locked_at:          string | null
  calibrated_at:      string
}

export type GaitPhase = 'heel_strike' | 'mid_stance' | 'toe_off' | 'swing'

export interface KineticGaitEvent {
  id:                    number
  twin_id:               string
  node_id:               NodeId
  sensor_id:             string
  detected_at:           string
  gait_phase:            GaitPhase
  emg_uv:                number
  motor_intent_score:    number | null
  ground_impedance_ohm:  number | null
  ref_node_id:           NodeId | null    // null = this node is the sacral reference
  reflex_transit_ms:     number | null
  neural_conduction_m_s: number | null   // healthy range: 40-70 m/s (corticospinal 55-75)
  step_seq:              number | null
  laterality:            'left' | 'right' | 'bilateral' | null
  metadata:              Record<string, unknown> | null
}

export interface SpinalRelayEvent {
  id:                  number
  twin_id:             string
  sensor_id:           string
  detected_at:         string
  motor_cortex_at:     string             // Cz (node 10) motor cortex timestamp
  sacrum_l_at:         string | null
  sacrum_r_at:         string | null
  left_transit_ms:     number | null
  right_transit_ms:    number | null
  mean_transit_ms:     number | null
  spinal_distance_cm:  number             // default 65 cm Cz→L5/S1
  conduction_m_s:      number | null      // healthy corticospinal: 55-75 m/s
  metadata:            Record<string, unknown> | null
}

export interface CalibrationEraBaseline {
  id:               number
  twin_id:          string
  dev_phase:        DevPhase
  node_id:          NodeId
  token_type:       TokenType
  mean_value:       number
  std_value:        number
  min_value:        number | null
  max_value:        number | null
  sample_count:     number
  mean_latency_ms:  number | null
  std_latency_ms:   number | null
  chemical_markers: ChemicalMarkers | null
  is_locked:        boolean
  locked_at:        string | null
  dna_root_sig:     string | null
  created_at:       string
}

export interface IntentActionBaseline {
  id:                 number
  twin_id:            string
  dev_phase:          DevPhase
  origin_node_id:     NodeId     // Fp1 (1) or Cz (10)
  terminal_node_id:   NodeId     // PLANTAR_L (41) or PLANTAR_R (42)
  mean_transit_ms:    number     // the "Biological Constant"
  std_transit_ms:     number
  min_transit_ms:     number | null
  max_transit_ms:     number | null
  sample_count:       number
  lower_bound_ms:     number | null  // mean - 3σ
  upper_bound_ms:     number | null  // mean + 3σ
  path_distance_cm:   number | null
  is_locked:          boolean
  locked_at:          string | null
  dna_root_sig:       string | null
  created_at:         string
}

export interface IntentActionEvent {
  id:                 number
  twin_id:            string
  sensor_id:          string
  detected_at:        string
  origin_node_id:     NodeId
  terminal_node_id:   NodeId
  origin_at:          string
  terminal_at:        string
  transit_ms:         number
  baseline_id:        number | null
  baseline_mean_ms:   number | null
  baseline_std_ms:    number | null
  deviation_sigma:    number | null
  fraud_score:        number | null    // 0.0 authentic → 1.0 synthetic
  is_synthetic:       boolean
  anomaly_id:         number | null
  metadata:           Record<string, unknown> | null
}

export interface ChemicalSaltEvent {
  id:                   number
  twin_id:              string
  sensor_id:            string
  detected_at:          string
  dev_phase:            DevPhase
  age_years:            number | null
  hormone:              string
  relative_level:       number
  system_shock_flag:    boolean
  shock_threshold_used: number | null
  life_event_id:        number | null
  snapshot_id:          number | null
  metadata:             Record<string, unknown> | null
}

export interface BiologicalIntegrityResult {
  event_id:         number
  transit_ms:       number
  baseline_mean_ms: number | null
  baseline_std_ms:  number | null
  deviation_sigma:  number | null
  fraud_score:      number          // 0.0 authentic → 1.0 synthetic
  is_synthetic:     boolean
  verdict:          string
}

export interface CalibrationSummaryRow {
  dev_phase:         DevPhase
  node_count:        number
  locked:            boolean
  locked_at:         string | null
  token_types:       TokenType[]
  mean_latency_ms:   number | null
  chemical_snapshot: ChemicalMarkers | null
}

export interface NeuralConductionResult {
  step_count:           number
  mean_transit_ms:      number | null
  mean_conduction_m_s:  number | null    // 40-70 m/s peripheral; 55-75 m/s corticospinal
  distance_cm:          number | null
  node_a_code:          string
  node_b_code:          string
}

// ── Bio/RNA/DNA types (20260535_bio_rna_integration) ──────────

// ── Bio operations types (20260536_bio_operations) ────────────

export type BioEffectDuration =
  | 'hours'           // RNA interference, acute mRNA pulse
  | 'hours_days'      // protein expression, transient translation
  | 'weeks_months'    // epigenetic modulation (methylation)
  | 'permanent'       // genetic injection, CRISPR edit, DNA data storage

export type BioOperationType =
  | 'genetic_injection'
  | 'protein_expression'
  | 'crispr_programming'
  | 'rna_interference'
  | 'epigenetic_modulation'
  | 'dna_data_storage'

export type NodeEffectType =
  | 'permanent_programming'  // genetic injection, CRISPR knockin
  | 'temporary_modulation'   // mRNA protein expression
  | 'node_rewiring'          // CRISPR guide RNA + Cas9
  | 'node_silencing'         // siRNA interference
  | 'sensitivity_change'     // epigenetic methylation
  | 'memory_storage'         // DNA data encoding

export interface GeneticInjectionRecord {
  id:                       number
  twin_id:                  string
  molecule_id:              number
  delivery_method:          string    // 'viral_vector' | 'nanoparticle' | 'electroporation' | 'liposome'
  vector_type:              string | null  // 'AAV' | 'lentiviral' | 'adenoviral' | 'retroviral' | 'LNP'
  target_node_id:           NodeId | null
  target_tissue:            string | null
  target_gene:              string | null
  integration_site:         string | null
  node_effect:              NodeEffectType
  effect_duration:          BioEffectDuration
  expression_confirmed:     boolean
  expression_confirmed_at:  string | null
  expression_level:         number | null
  approved_by_sig:          string | null
  approved_at:              string | null
  administered_at:          string
}

export interface BioOperationLogEntry {
  id:                 number
  twin_id:            string
  operation_type:     BioOperationType
  operation_ref_id:   number
  molecule_id:        number | null
  target_node_id:     NodeId | null
  node_effect:        NodeEffectType
  effect_duration:    BioEffectDuration
  freq_before_ghz:    number | null
  freq_after_ghz:     number | null
  freq_delta_ghz:     number | null    // generated: freq_after - freq_before
  notes:              string | null
  performed_at:       string
}

export interface BioOperationsSummaryRow {
  twin_id:              string
  operation_type:       BioOperationType
  total_operations:     number
  permanent_ops:        number
  weeks_months_ops:     number
  hours_days_ops:       number
  hours_ops:            number
  avg_freq_delta_ghz:   number | null
  last_performed_at:    string | null
}

// ── Bio/RNA/DNA types (20260535_bio_rna_integration) ──────────

export type BioMoleculeType =
  | 'DNA'
  | 'mRNA'
  | 'tRNA'
  | 'guide_rna'
  | 'siRNA'

export type CrisprEditType =
  | 'knockout'
  | 'knockin'
  | 'base_edit'
  | 'activation'
  | 'silencing'

export type EpigeneticMarkType =
  | 'methylation'
  | 'acetylation'
  | 'phosphorylation'
  | 'deacetylation'

export interface CodonRfOffset {
  codon:          string          // e.g. 'ATG', 'AUG'
  amino_acid:     string | null
  is_start_codon: boolean
  is_stop_codon:  boolean
  rf_offset_ghz:  number
}

export interface BioMoleculeRecord {
  id:                   number
  twin_id:              string
  linked_node_id:       NodeId | null
  molecule_type:        BioMoleculeType
  nucleotide_sequence:  string
  sequence_length_bp:   number          // generated
  computed_freq_ghz:    number | null   // set by trigger: formula f_RF
  source_region:        string | null
  gene_symbol:          string | null
  chromosome:           string | null
  dna_root_sig:         string | null
  is_locked:            boolean
  locked_at:            string | null
  registered_at:        string
}

export interface RnaTranslationEvent {
  id:                     number
  twin_id:                string
  template_molecule_id:   number
  trna_carrier_ids:       number[] | null
  product_name:           string
  product_function:       string | null
  codon_sequence:         string[] | null
  translation_efficiency: number          // 0.0–1.0
  ribosomal_site:         string | null
  target_node_id:         NodeId | null
  expression_delta:       number | null
  effect_duration:        BioEffectDuration
  node_effect:            NodeEffectType
  detected_at:            string
}

export interface RnaInterferenceLog {
  id:                     number
  twin_id:                string
  sirna_molecule_id:      number
  target_molecule_id:     number
  silencing_efficiency:   number   // 0.0–1.0
  off_target_score:       number
  target_node_id:         NodeId | null
  node_signal_suppression: number | null
  estimated_duration_h:   number | null
  effect_duration:        BioEffectDuration
  node_effect:            NodeEffectType
  applied_at:             string
  expires_at:             string | null
}

export interface CrisprGuideRecord {
  id:                 number
  twin_id:            string
  guide_molecule_id:  number
  cas9_molecule_id:   number | null   // bio_molecule_registry ID for Cas9-like nuclease
  nuclease_type:      string          // 'Cas9-like' | 'dCas9' | 'Cas12a' | 'Cas13'
  edit_type:          CrisprEditType
  target_sequence:    string
  pam_site:           string
  target_gene:        string | null
  target_chromosome:  string | null
  on_target_score:    number
  off_target_score:   number
  effect_duration:    BioEffectDuration
  node_effect:        NodeEffectType
  approved_by_sig:    string | null
  approved_at:        string | null
  executed_at:        string | null
  execution_outcome:  string | null
  designed_at:        string
}

export interface EpigeneticNodeState {
  id:                   number
  twin_id:              string
  node_id:              NodeId
  mark_type:            EpigeneticMarkType
  mark_level:           number          // 0.0–1.0
  expression_modifier:  number          // -1.0 (silenced) → +1.0 (fully activated)
  source_molecule_id:   number | null
  life_event_id:        number | null
  dev_phase:            string | null
  is_reversible:        boolean
  is_heritable:         boolean
  recorded_at:          string
  expires_at:           string | null
}

export interface DnaStorageRecord {
  id:                   number
  twin_id:              string
  storage_molecule_id:  number | null
  data_label:           string
  data_hash:            string
  encoded_sequence:     string
  data_size_bp:         number          // generated
  data_payload_jsonb:   Record<string, unknown> | null
  error_correction:     string
  retrieval_count:      number
  last_retrieved_at:    string | null
  stored_at:            string
}

export interface MolecularRfSpectrumRow {
  molecule_id:         number
  molecule_type:       BioMoleculeType
  gene_symbol:         string | null
  linked_node_id:      NodeId | null
  nucleotide_sequence: string
  sequence_length_bp:  number
  computed_freq_ghz:   number
  is_locked:           boolean
}

export interface BioNodeState {
  node_id:           NodeId
  molecules:         Pick<BioMoleculeRecord, 'id' | 'molecule_type' | 'gene_symbol' | 'computed_freq_ghz' | 'is_locked'>[] | null
  active_silencing:  Pick<RnaInterferenceLog, 'id' | 'silencing_efficiency' | 'node_signal_suppression' | 'expires_at'>[] | null
  epigenetic_marks:  Pick<EpigeneticNodeState, 'mark_type' | 'mark_level' | 'expression_modifier' | 'is_reversible' | 'is_heritable'>[] | null
  crispr_guides:     { guide_id: number; edit_type: CrisprEditType; target_gene: string | null; on_target: number; approved: boolean; executed: boolean }[] | null
}

export interface MolecularNodeMapRow {
  twin_id:                string
  node_id:                NodeId
  node_code:              string
  modality:               NodeModality
  molecule_id:            number
  molecule_type:          BioMoleculeType
  gene_symbol:            string | null
  source_region:          string | null
  chromosome:             string | null
  computed_freq_ghz:      number
  sequence_length_bp:     number
  is_locked:              boolean
  sdr_carrier_ghz:        number | null
  freq_alignment_delta:   number | null   // |molecular_freq - sdr_carrier_ghz|
}

// ── P2P interaction types (20260534_p2p_interactions) ─────────

export type P2pConnectionState = 'pending' | 'active' | 'revoked'
export type P2pInteractionRole = 'sent' | 'received'
export type P2pGroupRole       = 'initiator' | 'participant'

export interface P2pConnection {
  id:                 number
  twin_id_a:          string
  twin_id_b:          string
  state:              P2pConnectionState
  freq_a_ghz:         number | null
  freq_b_ghz:         number | null
  freq_delta_ghz:     number | null     // generated; < 0.05 required
  consent_a_at:       string | null
  consent_b_at:       string | null
  revoked_by:         string | null
  revoked_at:         string | null
  revocation_reason:  string | null
  initiated_at:       string
  activated_at:       string | null
}

export interface P2pHandshake {
  id:                   number
  handshake_id:         string
  connection_id:        number
  initiator_twin_id:    string
  responder_twin_id:    string
  signal_strength:      number | null   // 0.0–1.0
  initiator_signature:  string | null
  responder_signature:  string | null
  duration_sec:         number
  successful:           boolean
  handshake_at:         string
}

export interface P2pInteraction {
  id:               number
  share_id:         string             // links the two copies (sent + received)
  twin_id:          string             // owner of this copy
  peer_twin_id:     string
  handshake_id:     string
  role:             P2pInteractionRole
  data_type:        string
  data_hash:        string
  payload:          Record<string, unknown> | null
  group_session_id: number | null
  recorded_at:      string
}

export interface P2pSharedMemory {
  id:               number
  memory_id:        string
  owner_twin_id:    string
  source_twin_id:   string
  interaction_id:   number | null
  memory_type:      string
  memory_data:      Record<string, unknown> | null
  access_count:     number
  last_accessed_at: string | null
  shared_at:        string
}

export interface P2pGroupSession {
  id:                 number
  group_session_id:   string
  topic:              string
  duration_s:         number | null
  interaction_count:  number
  handshake_count:    number
  started_at:         string
  ended_at:           string | null
}

export interface P2pGroupParticipant {
  id:         number
  session_id: number
  twin_id:    string
  role:       P2pGroupRole
  joined_at:  string
}

export interface P2pSummary {
  twin_id:              string
  active_connections:   number
  total_connections:    number
  unique_peers:         number
  total_interactions:   number
  sent_count:           number
  received_count:       number
  handshakes_completed: number
  group_sessions:       number
}

export interface P2pConnectionMatrixRow {
  twin_id_a:           string
  twin_id_b:           string
  state:               P2pConnectionState
  freq_a_ghz:          number | null
  freq_b_ghz:          number | null
  freq_delta_ghz:      number | null
  activated_at:        string | null
  revoked_at:          string | null
  interactions_a:      number
  interactions_b:      number
  last_interaction_at: string | null
}

// ── Composite: full mesh state for UI ────────────────────────

export interface LiveMeshState {
  twin:           TwinIdentity
  nodes:          MeshNode[]
  edges:          MeshTopologyEdge[]
  readings:       MeshNodeReading[]       // latest per node
  edgeWeights:    MeshEdgeWeight[]        // latest per edge
  deviation:      MeshDeviationRow[]      // vs. active frozen snapshot
  anomalies:           MeshAnomaly[]              // unresolved
  vascularEvents:      VascularPulseEvent[]       // latest cardiac cycle across vascular nodes
  gaitEvents:          KineticGaitEvent[]         // latest step cycle across kinetic nodes
  spinalRelay:         SpinalRelayEvent[]         // latest Cz→sacrum conduction measurements
  intentActionEvents:  IntentActionEvent[]        // latest Fp1→plantar integrity checks
  calibrationSummary:  CalibrationSummaryRow[]    // per-phase baseline overview
  p2pConnections:      P2pConnectionMatrixRow[]   // peer-to-peer interaction matrix
  p2pSummary:          P2pSummary | null          // this twin's interaction stats
  molecularSpectrum:   MolecularRfSpectrumRow[]   // DNA/RNA → GHz spectrum
  bioNodeStates:       BioNodeState[]             // per-node biological state
}
