// Ports OpenNeuralSystem from gsr_sdr/ai/fusionroute_open.py
// Rolling 60-min adaptive baseline — no frozen historical comparison
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const AROUSAL_THRESHOLD = 1.5
const WINDOW_MINUTES    = 60

type EEGState = 'SENSING_CURRENT_AROUSAL_EVENT' | 'STATE_CURRENT_INTEGRATED'

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

async function appendAudit(eventType: string, payload: Record<string, unknown>) {
  const payloadHash = await sha256(JSON.stringify(payload))
  const { data: last } = await supabase.from('audit_log').select('chain_hash').order('id', { ascending: false }).limit(1).maybeSingle()
  const prevHash = last?.chain_hash ?? '0'.repeat(64)
  const chainHash = await sha256(prevHash + payloadHash)
  await supabase.from('audit_log').insert({ event_type: eventType, payload, payload_hash: payloadHash, prev_hash: prevHash, chain_hash: chainHash })
}

async function getRollingAverage(sensorId: string): Promise<number | null> {
  const since = new Date(Date.now() - WINDOW_MINUTES * 60 * 1000).toISOString()
  const { data, error } = await supabase
    .from('sensor_readings')
    .select('metadata')
    .eq('sensor_id', sensorId)
    .eq('sensor_type', 'eeg')
    .gte('timestamp', since)

  if (error || !data || data.length === 0) return null

  const values = data
    .map((r: { metadata?: { gsr_phi?: unknown } }) => parseFloat(String(r.metadata?.gsr_phi ?? '')))
    .filter((v: number) => !isNaN(v))

  return values.length === 0 ? null : values.reduce((a: number, b: number) => a + b, 0) / values.length
}

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: { sensor_id: string; eeg_tokens?: unknown; gsr_phi: number }
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const { sensor_id, eeg_tokens, gsr_phi } = body
  if (!sensor_id || gsr_phi === undefined) {
    return new Response(JSON.stringify({ error: 'Missing sensor_id or gsr_phi' }), { status: 400 })
  }

  const timestamp = new Date().toISOString()

  // Persist raw EEG+GSR reading
  await supabase.from('sensor_readings').insert({
    sensor_id,
    sensor_type: 'eeg',
    timestamp,
    metadata: { eeg_tokens: eeg_tokens ?? null, gsr_phi },
  })

  // Compute rolling baseline from last 60 minutes
  const dynamicBaseline = await getRollingAverage(sensor_id)

  let state: EEGState
  let baseline_source: string

  if (dynamicBaseline === null) {
    // Not enough history — no arousal flag on first reading
    state = 'STATE_CURRENT_INTEGRATED'
    baseline_source = 'insufficient_history'
  } else {
    state = gsr_phi > dynamicBaseline * AROUSAL_THRESHOLD
      ? 'SENSING_CURRENT_AROUSAL_EVENT'
      : 'STATE_CURRENT_INTEGRATED'
    baseline_source = `rolling_${WINDOW_MINUTES}m`
  }

  await appendAudit('eeg_process', { sensor_id, state, gsr_phi, dynamic_baseline: dynamicBaseline, timestamp })

  return new Response(JSON.stringify({
    state,
    gsr_phi,
    dynamic_baseline: dynamicBaseline,
    baseline_source,
    window_minutes: WINDOW_MINUTES,
    timestamp,
  }), { headers: { 'Content-Type': 'application/json' } })
})
