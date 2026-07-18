// eeg-processor v2 — per-channel EEG → 26-node mesh
//
// Maps named EEG channels + biometric scalars to mesh node IDs,
// then forwards to mesh-ingest for deviation tracking and anomaly detection.
//
// Arousal classification (theta/alpha frontal ratio) is computed locally
// from incoming band powers — no extra DB query when rich data is present.
// Falls back to the rolling 60-min GSR baseline for legacy callers.
//
// Backward compat: still writes to sensor_readings so bio-fusion keeps working.
// twin_id is optional — omit it to skip mesh-ingest (legacy mode).
//
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const AROUSAL_THRESHOLD = 1.5   // gsr_phi ratio vs rolling baseline
const THETA_ALPHA_MIN   = 0.62  // frontal theta/alpha arousal threshold
const WINDOW_MINUTES    = 60

// ── Node code → ID map (mirrors mesh_nodes seed) ─────────────
const NODE_ID: Record<string, number> = {
  Fp1: 1,  Fp2: 2,  F7:  3,  F3:  4,  Fz:  5,
  F4:  6,  F8:  7,  T3:  8,  C3:  9,  Cz:  10,
  C4:  11, T4:  12, T5:  13, P3:  14, Pz:  15,
  P4:  16, T6:  17, O1:  18, O2:  19,
  GSR: 20, HRV: 21, TEMP: 22, SPO2: 23, RESP: 24, ACC: 25, EOG: 26,
}

// Frontal nodes whose theta/alpha ratio drives the arousal index
const FRONTAL = ['F3', 'Fz', 'F4']

// ── Types ─────────────────────────────────────────────────────

type EegBand  = 'delta' | 'theta' | 'alpha' | 'beta' | 'gamma'
type EegState = 'SENSING_CURRENT_AROUSAL_EVENT' | 'STATE_CURRENT_INTEGRATED'

type BiometricCode = 'GSR' | 'HRV' | 'TEMP' | 'SPO2' | 'RESP' | 'ACC' | 'EOG'

interface BandPowers { delta?: number; theta?: number; alpha?: number; beta?: number; gamma?: number }
interface ChannelReading { amplitude_uv?: number; phase_deg?: number; band_powers?: BandPowers }

interface EEGProcessRequest {
  sensor_id:      string
  twin_id?:       string       // required to activate mesh-ingest path
  timestamp?:     string
  // Rich per-channel format
  eeg_channels?:  Record<string, ChannelReading>              // key = node_code e.g. 'Fz'
  biometrics?:    Partial<Record<BiometricCode, number>>
  edges?:         Array<{ node_a: number; node_b: number; coherence: number; phase_lag_ms?: number }>
  freeze?:        { label: string; life_event_id: number | null }
  // Legacy format (backward compat)
  gsr_phi?:       number
  eeg_tokens?:    unknown
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

// Rolling 60-min GSR average — kept for legacy arousal path and bio-fusion cross-validation
async function getRollingGSRAverage(sensorId: string): Promise<number | null> {
  const since = new Date(Date.now() - WINDOW_MINUTES * 60 * 1000).toISOString()
  const { data } = await supabase
    .from('sensor_readings')
    .select('metadata')
    .eq('sensor_id', sensorId)
    .eq('sensor_type', 'eeg')
    .gte('timestamp', since)

  if (!data || data.length === 0) return null
  const vals = data
    .map((r: { metadata?: { gsr_phi?: unknown } }) => parseFloat(String(r.metadata?.gsr_phi ?? '')))
    .filter((v: number) => !isNaN(v))
  return vals.length === 0 ? null : vals.reduce((a: number, b: number) => a + b, 0) / vals.length
}

// ── Arousal classification ────────────────────────────────────

interface ArousalResult {
  state:            EegState
  baseline_source:  string
  theta_alpha?:     number | null
  dynamic_baseline: number | null
}

function classifyFromBandPowers(
  channels: Record<string, ChannelReading>,
): { theta_alpha: number | null } {
  // Average theta and alpha across frontal nodes that have band powers
  let thetaSum = 0, alphaSum = 0, n = 0
  for (const code of FRONTAL) {
    const bp = channels[code]?.band_powers
    if (bp?.theta !== undefined && bp?.alpha !== undefined && bp.alpha > 0) {
      thetaSum += bp.theta
      alphaSum += bp.alpha
      n++
    }
  }
  if (n === 0) return { theta_alpha: null }
  return { theta_alpha: thetaSum / alphaSum }
}

function classifyArousal(
  gsrPhi:          number | null,
  dynamicBaseline: number | null,
  thetaAlpha:      number | null,
): ArousalResult {
  // Prefer theta/alpha ratio when frontal band data is available
  if (thetaAlpha !== null) {
    return {
      state:            thetaAlpha >= THETA_ALPHA_MIN
                          ? 'SENSING_CURRENT_AROUSAL_EVENT'
                          : 'STATE_CURRENT_INTEGRATED',
      baseline_source:  'frontal_theta_alpha',
      theta_alpha:      thetaAlpha,
      dynamic_baseline: null,
    }
  }

  // Fall back to rolling GSR baseline
  if (gsrPhi === null || dynamicBaseline === null) {
    return {
      state:            'STATE_CURRENT_INTEGRATED',
      baseline_source:  'insufficient_history',
      dynamic_baseline: null,
    }
  }
  return {
    state:            gsrPhi > dynamicBaseline * AROUSAL_THRESHOLD
                        ? 'SENSING_CURRENT_AROUSAL_EVENT'
                        : 'STATE_CURRENT_INTEGRATED',
    baseline_source:  `rolling_${WINDOW_MINUTES}m`,
    dynamic_baseline: dynamicBaseline,
  }
}

// ── Build mesh-ingest node payload ────────────────────────────

interface MeshNode {
  node_id:       number
  band_powers?:  BandPowers
  amplitude_uv?: number
  phase_deg?:    number
  raw_value?:    number
}

function buildMeshNodes(
  channels:    Record<string, ChannelReading> | undefined,
  biometrics:  Partial<Record<BiometricCode, number>> | undefined,
  legacyGsr:   number | undefined,
): MeshNode[] {
  const nodes: MeshNode[] = []

  // EEG channels
  for (const [code, reading] of Object.entries(channels ?? {})) {
    const nodeId = NODE_ID[code]
    if (!nodeId) continue   // ignore unrecognised channel names
    nodes.push({
      node_id:      nodeId,
      amplitude_uv: reading.amplitude_uv,
      phase_deg:    reading.phase_deg,
      band_powers:  reading.band_powers,
    })
  }

  // Biometric scalars
  for (const [code, value] of Object.entries(biometrics ?? {})) {
    const nodeId = NODE_ID[code]
    if (!nodeId || value === undefined) continue
    nodes.push({ node_id: nodeId, raw_value: value })
  }

  // Legacy gsr_phi → GSR node (node 20) if not already present from biometrics
  if (legacyGsr !== undefined && !nodes.some(n => n.node_id === NODE_ID['GSR'])) {
    nodes.push({ node_id: NODE_ID['GSR'], raw_value: legacyGsr })
  }

  return nodes
}

// ── Main ──────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: EEGProcessRequest
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const { sensor_id, twin_id, eeg_channels, biometrics, edges, freeze, gsr_phi, eeg_tokens } = body

  if (!sensor_id) {
    return new Response(JSON.stringify({ error: 'Missing sensor_id' }), { status: 400 })
  }
  const hasRichData   = !!(eeg_channels || biometrics)
  const hasLegacyData = gsr_phi !== undefined
  if (!hasRichData && !hasLegacyData) {
    return new Response(JSON.stringify({ error: 'Provide eeg_channels/biometrics or legacy gsr_phi' }), { status: 400 })
  }

  const timestamp = body.timestamp ?? new Date().toISOString()

  // ── Arousal classification ──────────────────────────────────
  const { theta_alpha } = eeg_channels
    ? classifyFromBandPowers(eeg_channels)
    : { theta_alpha: null }

  // Only query rolling baseline when we need it (no frontal band data)
  const dynamicBaseline = theta_alpha === null ? await getRollingGSRAverage(sensor_id) : null
  const arousal = classifyArousal(gsr_phi ?? null, dynamicBaseline, theta_alpha ?? null)

  // ── Persist to sensor_readings (bio-fusion reads from here) ──
  await supabase.from('sensor_readings').insert({
    sensor_id,
    sensor_type: 'eeg',
    timestamp,
    metadata: {
      eeg_tokens:       eeg_tokens          ?? null,
      gsr_phi:          gsr_phi             ?? null,
      eeg_channels:     eeg_channels        ?? null,
      biometrics:       biometrics          ?? null,
      state:            arousal.state,
      theta_alpha:      arousal.theta_alpha ?? null,
      dynamic_baseline: arousal.dynamic_baseline,
    },
  })

  // ── Mesh-ingest (skipped when twin_id is absent) ──────────────
  let meshResult: Record<string, unknown> | null = null

  if (twin_id) {
    const meshNodes = buildMeshNodes(eeg_channels, biometrics, gsr_phi)

    if (meshNodes.length === 0) {
      return new Response(JSON.stringify({ error: 'No recognisable node codes in eeg_channels or biometrics' }), { status: 400 })
    }

    const { data, error: meshErr } = await supabase.functions.invoke('mesh-ingest', {
      body: {
        twin_id,
        sensor_id,
        timestamp,
        nodes:  meshNodes,
        edges:  edges  ?? undefined,
        freeze: freeze ?? undefined,
      },
    })

    if (meshErr) {
      // Non-fatal: log and continue — arousal state is still valid
      console.error('mesh-ingest error:', meshErr)
    } else {
      meshResult = data as Record<string, unknown>
    }
  }

  await appendAudit('eeg_process', {
    sensor_id,
    twin_id:          twin_id          ?? null,
    state:            arousal.state,
    baseline_source:  arousal.baseline_source,
    theta_alpha:      arousal.theta_alpha   ?? null,
    dynamic_baseline: arousal.dynamic_baseline,
    node_count:       meshResult?.node_count ?? null,
    anomaly_count:    meshResult?.anomalies  ? (meshResult.anomalies as unknown[]).length : null,
    timestamp,
  })

  return new Response(JSON.stringify({
    state:            arousal.state,
    baseline_source:  arousal.baseline_source,
    theta_alpha:      arousal.theta_alpha   ?? null,
    dynamic_baseline: arousal.dynamic_baseline,
    window_minutes:   WINDOW_MINUTES,
    mesh:             meshResult,
    timestamp,
  }), { headers: { 'Content-Type': 'application/json' } })
})
