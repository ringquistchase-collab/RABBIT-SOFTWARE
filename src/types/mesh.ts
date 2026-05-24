// 26-node biometric mesh + Digital Twin types
// mirrors: supabase/migrations/20260525_mesh_digital_twin.sql

export type NodeModality = 'eeg' | 'biometric'
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

// ── Node IDs 1-26 as branded type ───────────────────────────
export type NodeId = number & { __brand: 'NodeId' }

export const EEG_NODE_IDS: NodeId[]        = Array.from({ length: 19 }, (_, i) => (i + 1) as NodeId)
export const BIOMETRIC_NODE_IDS: NodeId[]  = Array.from({ length: 7 },  (_, i) => (i + 20) as NodeId)
export const ALL_NODE_IDS: NodeId[]        = [...EEG_NODE_IDS, ...BIOMETRIC_NODE_IDS]

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
  // Adjacency coherence at snapshot time
  coherence_map:    Record<string, number> | null   // { "3": 0.82, "7": 0.71, … }
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
  twin:        TwinIdentity
  nodes:       MeshNode[]
  edges:       MeshTopologyEdge[]
  readings:    MeshNodeReading[]       // latest per node
  edgeWeights: MeshEdgeWeight[]        // latest per edge
  deviation:   MeshDeviationRow[]      // vs. active frozen snapshot
  anomalies:   MeshAnomaly[]           // unresolved
}
