// corpus-builder — RabbitCorpusBuilder sync bridge
//
// Accepts the 60-second simulation corpus produced by RabbitCorpusBuilder
// and ingests it into Supabase. Runs all three interstitial methods inline:
//   Drift-Watch     → via ingest_corpus_frame() RPC
//   Ghost-Signal    → apply_ghost_filter() on cardiac/torso nodes
//   Twin-Sync Lock  → trigger_twin_sync_lock() on first SHOCK frame
//
// Two modes:
//   full   — ingest all frames (new session)
//   delta  — ingest only frames missing from an existing session (offline sync)
//   status — return session stats without writing
//
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

// ── Constants ─────────────────────────────────────────────────
const CRANIAL_NODES  = new Set([1, 2, 3, 4, 5, 6, 7, 8])
const CARDIAC_NODES  = new Set([9, 10, 11, 12, 13, 14, 15, 16]) // ghost filter targets
const DEFAULT_CARRIER_GHZ  = 10.245
const DEFAULT_NOISE_FLOOR  = 0.02  // rad — baseline RF noise floor
const DEFAULT_SHOCK_THRESH = 0.7   // raw intensity (0-1)

// ── Types ─────────────────────────────────────────────────────

type EegBand = 'delta' | 'theta' | 'alpha' | 'beta' | 'gamma'

interface NodeFrame {
  token:       string   // 8-char TFM hex token from generate_tfm_token()
  phase_shift: number   // -1.0 to 1.0 (raw signal value from Python sim)
  latency_ms:  number   // 1.2+ ms (1.2ms baseline + jitter)
}

interface CorpusFrame {
  timestamp:       number                      // 0-59 (seconds)
  intensity_level: number                      // 0.0-10.0
  state:           string                      // LOW_STRESS_ZEN | TRANSITION | HIGH_STRESS_SHOCK
  nodes:           Record<string, NodeFrame>   // "NODE_01" → NodeFrame
}

interface CorpusBuilderRequest {
  twin_id:              string
  sensor_id:            string
  mode:                 'full' | 'delta' | 'status'
  session_id?:          number         // required for delta mode
  corpus:               CorpusFrame[]
  carrier_hz?:          number         // default 10.245e9
  resolution_ms?:       number         // default 1.2
  noise_floor_rad?:     number         // default 0.02
  apply_ghost_filter?:  boolean        // default true
  shock_threshold?:     number         // raw 0-1, default 0.7
  auto_sync_lock?:      boolean        // default true
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
    event_type: eventType, payload, payload_hash: payloadHash,
    prev_hash: prevHash, chain_hash: chainHash,
  })
}

function parseNodeId(nodeKey: string): number {
  return parseInt(nodeKey.replace('NODE_', ''), 10)
}

// Map simulation intensity (0-1) to dominant EEG band.
// Mirrors the Python sim: freq = interp(intensity, [0,1], [8,40])
function classifyBand(intensityRaw: number): EegBand {
  const freq = 8 + intensityRaw * 32
  if (freq <= 4)  return 'delta'
  if (freq <= 8)  return 'theta'
  if (freq <= 13) return 'alpha'
  if (freq <= 30) return 'beta'
  return 'gamma'
}

// Build sparse band_powers from intensity + phase signal
function buildBandPowers(intensityRaw: number, phaseShift: number): Partial<Record<EegBand, number>> {
  const band = classifyBand(intensityRaw)
  const amplitude = Math.abs(phaseShift)
  const powers: Partial<Record<EegBand, number>> = { [band]: amplitude }
  // Distribute residual power across adjacent bands
  const bands: EegBand[] = ['delta', 'theta', 'alpha', 'beta', 'gamma']
  const idx = bands.indexOf(band)
  if (idx > 0)             powers[bands[idx - 1]] = amplitude * 0.3
  if (idx < bands.length - 1) powers[bands[idx + 1]] = amplitude * 0.2
  return powers
}

function normaliseState(state: string): string {
  const map: Record<string, string> = {
    LOW_STRESS_ZEN:    'LOW_STRESS_ZEN',
    TRANSITION:        'TRANSITION',
    HIGH_STRESS_SHOCK: 'HIGH_STRESS_SHOCK',
  }
  return map[state] ?? 'TRANSITION'
}

// ── Reading row builder ───────────────────────────────────────

function buildReadingRow(
  nodeId:    number,
  nf:        NodeFrame,
  frame:     CorpusFrame,
  twinId:    string,
  sensorId:  string,
  timestamp: string,
  sessionId: number,
): Record<string, unknown> {
  const intensityRaw = frame.intensity_level / 10
  const isCranial  = CRANIAL_NODES.has(nodeId)
  const isCardiac  = CARDIAC_NODES.has(nodeId)
  const simState   = normaliseState(frame.state)

  const base = {
    twin_id:            twinId,
    node_id:            nodeId,
    sensor_id:          sensorId,
    timestamp,
    reflex_latency_ms:  nf.latency_ms,
    corpus_session_id:  sessionId,
    intensity_level:    frame.intensity_level,
    sim_state:          simState,
    dev_phase:          'ADULT',
  }

  if (isCranial) {
    return {
      ...base,
      amplitude_uv:  nf.phase_shift * 100,   // scale normalised value to µV range
      band:          classifyBand(intensityRaw),
      band_powers:   buildBandPowers(intensityRaw, nf.phase_shift),
      token_type:    intensityRaw < 0.3 ? 'TFM_LRN'
                   : intensityRaw > 0.7 ? 'TFM_EXN'
                   :                      'TFM_KIN',
    }
  }

  if (isCardiac) {
    return {
      ...base,
      raw_value:       nf.phase_shift,
      phase_shift_rad: nf.phase_shift * 0.04,  // scale to rad range for 10.245 GHz
      beat_interval_ms: nf.latency_ms * 600,   // crude R-R proxy: latency → ms
      token_type: 'TFM_HRT',
    }
  }

  // Lower body / biometric nodes (17-26)
  return {
    ...base,
    raw_value:    nf.phase_shift,
    token_type:   intensityRaw > 0.7 ? 'TFM_SCR' : 'TFM_KIN',
  }
}

// ── Main ──────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: CorpusBuilderRequest
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const {
    twin_id, sensor_id, mode, corpus,
    noise_floor_rad   = DEFAULT_NOISE_FLOOR,
    shock_threshold   = DEFAULT_SHOCK_THRESH,
    apply_ghost_filter: doGhost = true,
    auto_sync_lock    = true,
  } = body

  if (!twin_id || !sensor_id) {
    return new Response(JSON.stringify({ error: 'Missing twin_id or sensor_id' }), { status: 400 })
  }

  // ── Status mode ───────────────────────────────────────────
  if (mode === 'status') {
    const sid = body.session_id
    if (!sid) return new Response(JSON.stringify({ error: 'session_id required for status mode' }), { status: 400 })
    const { data: sess } = await supabase
      .from('corpus_simulation_sessions')
      .select('*, corpus_simulation_frames(count)')
      .eq('id', sid).eq('twin_id', twin_id).maybeSingle()
    return new Response(JSON.stringify({ ok: true, session: sess }), { headers: { 'Content-Type': 'application/json' } })
  }

  if (!Array.isArray(corpus) || corpus.length === 0) {
    return new Response(JSON.stringify({ error: 'corpus array required' }), { status: 400 })
  }

  // ── Validate twin ─────────────────────────────────────────
  const { data: twin } = await supabase
    .from('twin_identity').select('id, is_sealed').eq('id', twin_id).maybeSingle()
  if (!twin)       return new Response(JSON.stringify({ error: 'twin_id not found' }), { status: 404 })
  if (twin.is_sealed) return new Response(JSON.stringify({ error: 'Twin is sealed' }), { status: 403 })

  // ── Delta: find existing frame timestamps ─────────────────
  const existingTimestamps = new Set<number>()
  let sessionId: number

  if (mode === 'delta') {
    if (!body.session_id) {
      return new Response(JSON.stringify({ error: 'session_id required for delta mode' }), { status: 400 })
    }
    sessionId = body.session_id
    const { data: existing } = await supabase
      .from('corpus_simulation_frames')
      .select('timestamp_s')
      .eq('session_id', sessionId)
    for (const row of existing ?? []) existingTimestamps.add(row.timestamp_s)
  } else {
    // Full mode: begin new session
    const { data: sessRows } = await supabase.rpc('begin_corpus_session', {
      p_twin_id:       twin_id,
      p_sensor_id:     sensor_id,
      p_duration_s:    corpus.length,
      p_node_count:    Object.keys(corpus[0]?.nodes ?? {}).length,
      p_resolution_ms: body.resolution_ms ?? 1.2,
      p_carrier_hz:    body.carrier_hz ?? 10.245e9,
    })
    sessionId = Array.isArray(sessRows) ? sessRows[0].session_id : sessRows.session_id
  }

  // ── Look up cranial bot ────────────────────────────────────
  const { data: botRow } = await supabase
    .from('node_bots')
    .select('id')
    .eq('twin_id', twin_id)
    .eq('bot_class', 'cranial')
    .eq('is_active', true)
    .maybeSingle()
  const cranialBotId: number | null = botRow?.id ?? null

  // ── Process frames ────────────────────────────────────────
  let framesIngested    = 0
  let framesSkipped     = 0
  let readingsWritten   = 0
  let driftEvents       = 0
  let ghostFilterEvents = 0
  let syncLockEvents    = 0
  let botWindowsWritten = 0
  let syncLockFired     = false

  for (const frame of corpus) {
    const timestampS = frame.timestamp as number

    // Skip frames already in DB (delta mode)
    if (existingTimestamps.has(timestampS)) {
      framesSkipped++
      continue
    }

    const intensityRaw = frame.intensity_level / 10  // back to 0-1
    const isoTimestamp = new Date(Date.now() - (corpus.length - timestampS) * 1000).toISOString()

    // ── 1. Ingest frame via RPC (Drift-Watch integrated) ────
    const { data: frameRows } = await supabase.rpc('ingest_corpus_frame', {
      p_session_id:    sessionId,
      p_twin_id:       twin_id,
      p_timestamp_s:   timestampS,
      p_intensity_raw: intensityRaw,
      p_node_snapshot: frame.nodes as unknown,
    })
    const frameResult = Array.isArray(frameRows) ? frameRows[0] : frameRows
    if (frameResult?.drift_detected) driftEvents++
    framesIngested++

    // ── 2. Build and insert mesh_node_readings (batch) ──────
    const readingRows: Record<string, unknown>[] = []
    for (const [nodeKey, nf] of Object.entries(frame.nodes)) {
      const nodeId = parseNodeId(nodeKey)
      if (nodeId < 1 || nodeId > 26) continue  // corpus only covers 1-26
      readingRows.push(buildReadingRow(nodeId, nf, frame, twin_id, sensor_id, isoTimestamp, sessionId))
    }

    const { data: insertedReadings } = await supabase
      .from('mesh_node_readings')
      .insert(readingRows)
      .select('id, node_id')

    readingsWritten += insertedReadings?.length ?? 0

    // ── 3. Ghost-Signal Filter on cardiac/torso nodes ───────
    if (doGhost && insertedReadings) {
      for (const row of insertedReadings) {
        if (!CARDIAC_NODES.has(row.node_id)) continue
        const nf = frame.nodes[`NODE_${String(row.node_id).padStart(2, '0')}`]
        if (!nf) continue

        await supabase.rpc('apply_ghost_filter', {
          p_twin_id:           twin_id,
          p_session_id:        sessionId,
          p_node_id:           row.node_id,
          p_reading_id:        row.id,
          p_raw_phase_shift:   nf.phase_shift * 0.04,   // scaled to rad
          p_noise_floor_rad:   noise_floor_rad,
          p_carrier_freq_ghz:  DEFAULT_CARRIER_GHZ,
          p_filter_method:     'adaptive_threshold',
        })
        ghostFilterEvents++
      }
    }

    // ── 4. Cranial bot windows ───────────────────────────────
    if (cranialBotId !== null) {
      const cranialNodeIds: number[] = []
      const cranialTokens: string[]  = []
      let   phaseSum = 0

      for (const [nodeKey, nf] of Object.entries(frame.nodes)) {
        const nodeId = parseNodeId(nodeKey)
        if (!CRANIAL_NODES.has(nodeId)) continue
        cranialNodeIds.push(nodeId)
        cranialTokens.push(nf.token)
        phaseSum += nf.phase_shift
      }

      if (cranialNodeIds.length > 0) {
        const compositeToken = cranialTokens.join('')
        const presignedHash  = await sha256(compositeToken + isoTimestamp)

        await supabase.rpc('record_bot_window', {
          p_bot_id:           cranialBotId,
          p_twin_id:          twin_id,
          p_window_at:        isoTimestamp,
          p_active_nodes:     cranialNodeIds,
          p_motifs:           { tokens: cranialTokens, frame_timestamp_s: timestampS },
          p_resonance_delta:  phaseSum / cranialNodeIds.length,
          p_presigned_hash:   presignedHash,
          p_action:           'pass',
        })
        botWindowsWritten++
      }
    }

    // ── 5. Twin-Sync Lock on first SHOCK frame ───────────────
    if (auto_sync_lock && !syncLockFired && intensityRaw > shock_threshold) {
      const { data: lockRows } = await supabase.rpc('trigger_twin_sync_lock', {
        p_twin_id:    twin_id,
        p_session_id: sessionId,
        p_sensor_id:  sensor_id,
        p_intensity:  intensityRaw,
        p_window_end: isoTimestamp,
      })
      const lockResult = Array.isArray(lockRows) ? lockRows[0] : lockRows
      if (lockResult?.success) {
        syncLockEvents++
        syncLockFired = true   // only fire once per session
      }
    }
  }

  // ── Complete session (full mode only) ─────────────────────
  let sessionHash: string | null = null
  if (mode === 'full') {
    const { data: completeRows } = await supabase.rpc('complete_corpus_session', {
      p_session_id: sessionId,
      p_twin_id:    twin_id,
    })
    const cr = Array.isArray(completeRows) ? completeRows[0] : completeRows
    sessionHash = cr?.session_hash ?? null
  }

  await appendAudit('corpus_build', {
    twin_id, sensor_id, mode, session_id: sessionId,
    frames_ingested: framesIngested,
    frames_skipped:  framesSkipped,
    readings_written: readingsWritten,
    drift_events:     driftEvents,
    ghost_filter_events: ghostFilterEvents,
    sync_lock_events: syncLockEvents,
    bot_windows_written: botWindowsWritten,
    session_hash: sessionHash,
  })

  return new Response(JSON.stringify({
    ok:                  true,
    mode,
    session_id:          sessionId,
    session_hash:        sessionHash,
    frames_ingested:     framesIngested,
    frames_skipped:      framesSkipped,
    readings_written:    readingsWritten,
    drift_events:        driftEvents,
    ghost_filter_events: ghostFilterEvents,
    sync_lock_events:    syncLockEvents,
    bot_windows_written: botWindowsWritten,
    timestamp:           new Date().toISOString(),
  }), { headers: { 'Content-Type': 'application/json' } })
})
