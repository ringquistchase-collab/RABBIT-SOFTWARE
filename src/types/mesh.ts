// 26+6-node biometric mesh + Digital Twin types
// mirrors: supabase/migrations/20260525_mesh_digital_twin.sql
//          supabase/migrations/20260526_vascular_nodes.sql

export type NodeModality = 'eeg' | 'biometric' | 'vascular'
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

// ── Node IDs as branded type ─────────────────────────────────
export type NodeId = number & { __brand: 'NodeId' }

export const EEG_NODE_IDS:       NodeId[] = Array.from({ length: 19 }, (_, i) => (i + 1)  as NodeId)
export const BIOMETRIC_NODE_IDS: NodeId[] = Array.from({ length: 7 },  (_, i) => (i + 20) as NodeId)
export const VASCULAR_NODE_IDS:  NodeId[] = Array.from({ length: 6 },  (_, i) => (i + 27) as NodeId)
export const ALL_NODE_IDS:       NodeId[] = [...EEG_NODE_IDS, ...BIOMETRIC_NODE_IDS, ...VASCULAR_NODE_IDS]

export const VASCULAR_NODE_CODES: Record<number, string> = {
  27: 'CAROT_L', 28: 'CAROT_R',
  29: 'RADIAL_L', 30: 'RADIAL_R',
  31: 'FEMORAL_L', 32: 'FEMORAL_R',
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
  label:             string
  description:       string | null
  is_sealed:         boolean
  mesh_snapshot_id:  number | null
  created_at:        string
  sealed_at:         string | null
}

export interface MeshFrozenSnapshot {
  id:             number
  twin_id:        string
  life_event_id:  number | null
  label:          string
  captured_at:    string
  node_count:     number
  snapshot_hash:  string | null
  prev_hash:      string | null
  chain_hash:     string | null
  is_sealed:      boolean
  sealed_at:      string | null
  metadata:       Record<string, unknown> | null
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

// ── Composite: full mesh state for UI ────────────────────────

export interface LiveMeshState {
  twin:           TwinIdentity
  nodes:          MeshNode[]
  edges:          MeshTopologyEdge[]
  readings:       MeshNodeReading[]       // latest per node
  edgeWeights:    MeshEdgeWeight[]        // latest per edge
  deviation:      MeshDeviationRow[]      // vs. active frozen snapshot
  anomalies:      MeshAnomaly[]           // unresolved
  vascularEvents: VascularPulseEvent[]    // latest cardiac cycle across vascular nodes
}
