// mesh-ingest: 32-node biometric mesh ingestion (26 EEG/biometric + 6 vascular)
//
// Two modes controlled by the optional `freeze` field:
//
//   Live ingest (default)
//     Writes mesh_node_readings + mesh_edge_weights.
//     Computes deviation_z against the latest sealed frozen snapshot.
//     Flags IDENTITY_DEVIATION / TOPOLOGY_SHIFT anomalies automatically.
//
//   Freeze mode  (include `freeze: { label, life_event_id }`)
//     Seals the batch into an immutable mesh_frozen_snapshots row using
//     the same SHA-256 chain pattern as audit_log.
//     Links the snapshot to a life_age_event if life_event_id is provided.
//
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

// ── Types ─────────────────────────────────────────────────────

type EegBand     = 'delta' | 'theta' | 'alpha' | 'beta' | 'gamma'
type AlertLevel  = 'INFO' | 'WARNING' | 'CRITICAL'
type AnomalyType = 'IDENTITY_DEVIATION' | 'TOPOLOGY_SHIFT' | 'PATTERN_INJECTION' | 'COHERENCE_BREAK'

interface NodeReading {
  node_id:           number                           // 1-32
  band_powers?:      Partial<Record<EegBand, number>> // EEG nodes
  amplitude_uv?:     number                           // EEG nodes
  phase_deg?:        number                           // EEG nodes
  raw_value?:        number                           // biometric nodes
  // Vascular nodes (27-32)
  phase_shift_rad?:  number                           // RF phase shift (rad)
  pulse_amplitude?:  number                           // pulsatile amplitude 0-1
  carrier_freq_ghz?: number                           // RF carrier (default 10.245)
  beat_interval_ms?: number                           // R-R interval (ms)
  vasc_state?:       string                           // VascState enum value
}

interface EdgeReading {
  node_a:        number
  node_b:        number
  coherence:     number     // 0-1
  phase_lag_ms?: number
}

interface FreezeParams {
  label:          string
  life_event_id:  number | null
}

interface MeshIngestRequest {
  twin_id:     string
  sensor_id:   string
  timestamp?:  string
  nodes:       NodeReading[]
  edges?:      EdgeReading[]
  freeze?:     FreezeParams
}

interface FrozenBaseline {
  node_id:        number
  mean_amplitude: number | null
  std_amplitude:  number | null
}

interface AnomalyInsert {
  twin_id:               string
  detected_at:           string
  anomaly_type:          AnomalyType
  affected_nodes:        number[]
  deviation_score:       number
  alert_level:           AlertLevel
  baseline_snapshot_id:  number | null
  metadata:              Record<string, unknown>
}

// ── Helpers ───────────────────────────────────────────────────

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

async function appendAudit(eventType: string, payload: Record<string, unknown>) {
  const payloadHash = await sha256(JSON.stringify(payload))
  const { data: last } = await supabase
    .from('audit_log').select('chain_hash').order('id', { ascending: false }).limit(1).maybeSingle()
  const prevHash  = last?.chain_hash ?? '0'.repeat(64)
  const chainHash = await sha256(prevHash + payloadHash)
  await supabase.from('audit_log').insert({
    event_type: eventType, payload, payload_hash: payloadHash, prev_hash: prevHash, chain_hash: chainHash,
  })
}

function dominantBand(powers: Partial<Record<EegBand, number>>): EegBand | null {
  const bands: EegBand[] = ['delta', 'theta', 'alpha', 'beta', 'gamma']
  let max = -Infinity, dom: EegBand | null = null
  for (const b of bands) {
    const v = powers[b] ?? 0
    if (v > max) { max = v; dom = b }
  }
  return dom
}

// ── Baseline lookup ───────────────────────────────────────────

async function getActiveBaseline(twinId: string): Promise<{
  snapshotId: number | null
  nodes: Map<number, FrozenBaseline>
}> {
  const { data: snap } = await supabase
    .from('mesh_frozen_snapshots')
    .select('id')
    .eq('twin_id', twinId)
    .eq('is_sealed', true)
    .order('captured_at', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (!snap) return { snapshotId: null, nodes: new Map() }

  const { data: states } = await supabase
    .from('frozen_node_states')
    .select('node_id, mean_amplitude, std_amplitude')
    .eq('snapshot_id', snap.id)

  const map = new Map<number, FrozenBaseline>()
  for (const s of (states ?? [])) map.set(s.node_id, s)

  return { snapshotId: snap.id, nodes: map }
}

function computeDeviationZ(liveVal: number, base: FrozenBaseline): number | null {
  if (base.mean_amplitude === null) return null
  const std = base.std_amplitude ?? 0
  return std === 0 ? 0 : (liveVal - base.mean_amplitude) / std
}

// ── Anomaly detection ─────────────────────────────────────────

// TOPOLOGY_SHIFT: 5+ nodes simultaneously deviate beyond critical threshold —
// suggests wholesale identity replacement rather than isolated sensor noise.
const CRITICAL_Z       = 3.0
const WARNING_Z        = 2.0
const TOPOLOGY_NODE_N  = 5

function detectAnomalies(
  twinId:     string,
  timestamp:  string,
  readings:   Array<{ node_id: number; deviation_z: number | null }>,
  snapshotId: number | null,
): AnomalyInsert[] {
  const anomalies: AnomalyInsert[] = []

  const critical = readings.filter(r => r.deviation_z !== null && Math.abs(r.deviation_z!) > CRITICAL_Z)
  const warning  = readings.filter(r => r.deviation_z !== null && Math.abs(r.deviation_z!) > WARNING_Z && Math.abs(r.deviation_z!) <= CRITICAL_Z)

  if (critical.length > 0) {
    anomalies.push({
      twin_id:              twinId,
      detected_at:          timestamp,
      anomaly_type:         critical.length >= TOPOLOGY_NODE_N ? 'TOPOLOGY_SHIFT' : 'IDENTITY_DEVIATION',
      affected_nodes:       critical.map(r => r.node_id),
      deviation_score:      Math.max(...critical.map(r => Math.abs(r.deviation_z!))),
      alert_level:          'CRITICAL',
      baseline_snapshot_id: snapshotId,
      metadata:             { nodes: critical, threshold: CRITICAL_Z },
    })
  }

  if (warning.length > 0) {
    anomalies.push({
      twin_id:              twinId,
      detected_at:          timestamp,
      anomaly_type:         'IDENTITY_DEVIATION',
      affected_nodes:       warning.map(r => r.node_id),
      deviation_score:      Math.max(...warning.map(r => Math.abs(r.deviation_z!))),
      alert_level:          'WARNING',
      baseline_snapshot_id: snapshotId,
      metadata:             { nodes: warning, threshold: WARNING_Z },
    })
  }

  return anomalies
}

// ── Freeze flow ───────────────────────────────────────────────

async function freezeSnapshot(
  twinId:    string,
  params:    FreezeParams,
  nodes:     NodeReading[],
  timestamp: string,
): Promise<number> {
  const { data: prev } = await supabase
    .from('mesh_frozen_snapshots')
    .select('chain_hash')
    .eq('twin_id', twinId)
    .order('captured_at', { ascending: false })
    .limit(1)
    .maybeSingle()

  const prevHash = prev?.chain_hash ?? '0'.repeat(64)

  const { data: snap, error: snapErr } = await supabase
    .from('mesh_frozen_snapshots')
    .insert({
      twin_id:       twinId,
      life_event_id: params.life_event_id,
      label:         params.label,
      captured_at:   timestamp,
      prev_hash:     prevHash,
    })
    .select('id')
    .single()

  if (snapErr || !snap) throw new Error(`snapshot insert failed: ${snapErr?.message}`)

  const stateRows = nodes.map(r => ({
    snapshot_id:      snap.id,
    node_id:          r.node_id,
    delta_power:      r.band_powers?.delta  ?? null,
    theta_power:      r.band_powers?.theta  ?? null,
    alpha_power:      r.band_powers?.alpha  ?? null,
    beta_power:       r.band_powers?.beta   ?? null,
    gamma_power:      r.band_powers?.gamma  ?? null,
    dominant_band:    r.band_powers ? dominantBand(r.band_powers) : null,
    mean_amplitude:   r.amplitude_uv ?? r.raw_value ?? r.phase_shift_rad ?? null,
    std_amplitude:    0,
    biometric_value:  r.raw_value         ?? null,
    biometric_unit:   null as string | null,
    coherence_map:    null as Record<string, number> | null,
    phase_shift_rad:  r.phase_shift_rad   ?? null,
    pulse_amplitude:  r.pulse_amplitude   ?? null,
    beat_interval_ms: r.beat_interval_ms  ?? null,
    vasc_state:       r.vasc_state        ?? null,
  }))

  const { error: stateErr } = await supabase.from('frozen_node_states').insert(stateRows)
  if (stateErr) throw new Error(`frozen_node_states insert failed: ${stateErr.message}`)

  // Deterministic hash over node states sorted by node_id
  const snapshotHash = await sha256(JSON.stringify(
    stateRows.slice().sort((a, b) => a.node_id - b.node_id)
  ))
  const chainHash = await sha256(prevHash + snapshotHash)

  const { error: sealErr } = await supabase
    .from('mesh_frozen_snapshots')
    .update({ snapshot_hash: snapshotHash, chain_hash: chainHash, is_sealed: true, sealed_at: timestamp })
    .eq('id', snap.id)

  if (sealErr) throw new Error(`snapshot seal failed: ${sealErr.message}`)

  if (params.life_event_id !== null) {
    await supabase
      .from('life_age_events')
      .update({ mesh_snapshot_id: snap.id, is_sealed: true, sealed_at: timestamp })
      .eq('id', params.life_event_id)
  }

  return snap.id
}

// ── Main ──────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: MeshIngestRequest
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const { twin_id, sensor_id, nodes, edges, freeze } = body

  if (!twin_id || !sensor_id || !Array.isArray(nodes) || nodes.length === 0) {
    return new Response(JSON.stringify({ error: 'Missing twin_id, sensor_id, or nodes' }), { status: 400 })
  }
  if (nodes.length > 32) {
    return new Response(JSON.stringify({ error: 'nodes array exceeds 32-node mesh limit' }), { status: 400 })
  }

  const timestamp = body.timestamp ?? new Date().toISOString()

  const { data: twin, error: twinErr } = await supabase
    .from('twin_identity')
    .select('id, is_sealed')
    .eq('id', twin_id)
    .maybeSingle()

  if (twinErr || !twin) {
    return new Response(JSON.stringify({ error: 'twin_id not found' }), { status: 404 })
  }
  if (twin.is_sealed) {
    return new Response(JSON.stringify({ error: 'Twin identity is sealed — no new data accepted' }), { status: 403 })
  }

  // ── Freeze ────────────────────────────────────────────────────
  if (freeze) {
    if (!freeze.label) {
      return new Response(JSON.stringify({ error: 'freeze.label is required' }), { status: 400 })
    }
    try {
      const snapshotId = await freezeSnapshot(twin_id, freeze, nodes, timestamp)
      await appendAudit('mesh_freeze', { twin_id, sensor_id, snapshot_id: snapshotId, label: freeze.label, timestamp })
      return new Response(JSON.stringify({ ok: true, mode: 'freeze', snapshot_id: snapshotId, timestamp }), {
        headers: { 'Content-Type': 'application/json' },
      })
    } catch (err) {
      return new Response(JSON.stringify({ error: (err as Error).message }), { status: 500 })
    }
  }

  // ── Live ingest ───────────────────────────────────────────────
  const { snapshotId, nodes: baseline } = await getActiveBaseline(twin_id)

  const readingRows = nodes.map(r => {
    const liveVal  = r.amplitude_uv ?? r.raw_value ?? r.phase_shift_rad ?? null
    const base     = baseline.get(r.node_id)
    const devZ     = (liveVal !== null && base) ? computeDeviationZ(liveVal, base) : null

    return {
      twin_id,
      node_id:              r.node_id,
      sensor_id,
      timestamp,
      band:                 r.band_powers ? dominantBand(r.band_powers) : null,
      amplitude_uv:         r.amplitude_uv      ?? null,
      phase_deg:            r.phase_deg          ?? null,
      band_powers:          r.band_powers        ?? null,
      raw_value:            r.raw_value          ?? null,
      phase_shift_rad:      r.phase_shift_rad    ?? null,
      pulse_amplitude:      r.pulse_amplitude    ?? null,
      carrier_freq_ghz:     r.carrier_freq_ghz   ?? null,
      beat_interval_ms:     r.beat_interval_ms   ?? null,
      vasc_state:           r.vasc_state         ?? null,
      baseline_snapshot_id: snapshotId,
      deviation_z:          devZ,
    }
  })

  const { error: readErr } = await supabase.from('mesh_node_readings').insert(readingRows)
  if (readErr) {
    return new Response(JSON.stringify({ error: `mesh_node_readings insert failed: ${readErr.message}` }), { status: 500 })
  }

  // Edge weights
  let edgesInserted = 0
  if (edges && edges.length > 0) {
    const edgeRows = edges.map(e => ({
      twin_id,
      node_a:       Math.min(e.node_a, e.node_b),
      node_b:       Math.max(e.node_a, e.node_b),
      timestamp,
      coherence:    e.coherence,
      phase_lag_ms: e.phase_lag_ms ?? null,
    }))
    const { error: edgeErr } = await supabase.from('mesh_edge_weights').insert(edgeRows)
    if (!edgeErr) edgesInserted = edgeRows.length
  }

  // Anomalies
  const deviationSummary = readingRows.map(r => ({ node_id: r.node_id, deviation_z: r.deviation_z }))
  const anomalies = snapshotId !== null
    ? detectAnomalies(twin_id, timestamp, deviationSummary, snapshotId)
    : []

  if (anomalies.length > 0) {
    await supabase.from('mesh_anomalies').insert(anomalies)
  }

  await appendAudit('mesh_ingest', {
    twin_id, sensor_id,
    node_count:        readingRows.length,
    edges_count:       edgesInserted,
    anomaly_count:     anomalies.length,
    baseline_snapshot: snapshotId,
    timestamp,
  })

  return new Response(JSON.stringify({
    ok:                true,
    mode:              'ingest',
    node_count:        readingRows.length,
    edges_inserted:    edgesInserted,
    anomalies:         anomalies.map(a => ({ type: a.anomaly_type, level: a.alert_level, nodes: a.affected_nodes, score: a.deviation_score })),
    baseline_snapshot: snapshotId,
    timestamp,
  }), { headers: { 'Content-Type': 'application/json' } })
})
