// Multi-modal physiological stress fusion
// Inputs: EEG band powers + HRV LF/HF + optional Doppler phase ripple
// Rule: θ/α ≥ 0.62 ∧ LF/HF ≥ 2.1 → STRESS_CONFIRMED
// LLM explanation: Claude if key present, Ollama/llama3 otherwise
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const ANTHROPIC_KEY = Deno.env.get('ANTHROPIC_API_KEY')
const OLLAMA_URL    = Deno.env.get('OLLAMA_URL') ?? 'http://localhost:11434'

// Thresholds from spec
const THETA_ALPHA_THRESHOLD = 0.62
const LF_HF_THRESHOLD       = 2.1
const GSR_WINDOW_MINUTES    = 60

// ─── types ───────────────────────────────────────────────────────────────────

type FusionState =
  | 'STRESS_CONFIRMED'
  | 'COGNITIVE_LOAD'
  | 'PHYSIOLOGICAL_AROUSAL'
  | 'BASELINE'

interface EEGInput  { theta_power: number; alpha_power: number }
interface HRVInput  { lf_power: number; hf_power: number }
interface DopplerInput { head_phase_rad: number; chest_phase_rad: number }

interface FusionRequest {
  sensor_id: string
  eeg:       EEGInput
  hrv:       HRVInput
  doppler?:  DopplerInput
  timestamp?: string
}

// ─── helpers ─────────────────────────────────────────────────────────────────

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

async function appendAudit(eventType: string, payload: Record<string, unknown>) {
  const payloadHash = await sha256(JSON.stringify(payload))
  const { data: last } = await supabase.from('audit_log').select('chain_hash').order('id', { ascending: false }).limit(1).maybeSingle()
  const prevHash  = last?.chain_hash ?? '0'.repeat(64)
  const chainHash = await sha256(prevHash + payloadHash)
  await supabase.from('audit_log').insert({ event_type: eventType, payload, payload_hash: payloadHash, prev_hash: prevHash, chain_hash: chainHash })
}

// ─── rolling GSR cross-validation (from eeg-processor) ──────────────────────

async function getGSRBaseline(sensorId: string): Promise<number | null> {
  const since = new Date(Date.now() - GSR_WINDOW_MINUTES * 60 * 1000).toISOString()
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

// ─── four-state classifier ────────────────────────────────────────────────────

function classify(thetaAlpha: number, lfHf: number): FusionState {
  const cognitiveStress  = thetaAlpha >= THETA_ALPHA_THRESHOLD
  const autonomicStress  = lfHf      >= LF_HF_THRESHOLD

  if (cognitiveStress && autonomicStress)  return 'STRESS_CONFIRMED'
  if (cognitiveStress && !autonomicStress) return 'COGNITIVE_LOAD'
  if (!cognitiveStress && autonomicStress) return 'PHYSIOLOGICAL_AROUSAL'
  return 'BASELINE'
}

// ─── Doppler phase validation ────────────────────────────────────────────────

function validateDoppler(doppler: DopplerInput): { cardiac_ok: boolean; respiratory_ok: boolean } {
  // Expected phase ripple: ±0.08 rad cardiac, ±0.03 rad respiratory
  // HEAD_01 → CHEST_01 propagation; deviation > 2x expected flags artifact
  const cardiacDev     = Math.abs(doppler.head_phase_rad - doppler.chest_phase_rad)
  const cardiac_ok     = cardiacDev <= 0.16   // 2× tolerance
  const respiratory_ok = doppler.chest_phase_rad <= 0.06
  return { cardiac_ok, respiratory_ok }
}

// ─── LLM explanation (Claude → Ollama/llama3 fallback) ──────────────────────

async function explain(state: FusionState, metrics: Record<string, unknown>): Promise<string> {
  const prompt = [
    `You are a physiological signal analyst. Summarize this biometric state in 2 sentences for a wellness dashboard.`,
    `State: ${state}`,
    `Metrics: theta/alpha=${metrics.theta_alpha_ratio}, LF/HF=${metrics.lf_hf_ratio}, GSR baseline=${metrics.gsr_baseline ?? 'unknown'}`,
    `Doppler valid: ${metrics.doppler_valid ?? 'not measured'}`,
    `Be factual and non-alarming. Do not mention thresholds or raw numbers.`,
  ].join('\n')

  // Try Claude first
  if (ANTHROPIC_KEY) {
    try {
      const r = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': ANTHROPIC_KEY, 'anthropic-version': '2023-06-01' },
        body: JSON.stringify({ model: 'claude-haiku-4-5-20251001', max_tokens: 120, messages: [{ role: 'user', content: prompt }] }),
      })
      const j = await r.json()
      if (j.content?.[0]?.text) return j.content[0].text
    } catch { /* fall through to Ollama */ }
  }

  // Fallback: Ollama / llama3 (no key required)
  try {
    const r = await fetch(`${OLLAMA_URL}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'llama3', prompt, stream: false }),
    })
    const j = await r.json()
    if (j.response) return j.response
  } catch { /* explanation unavailable */ }

  return `State: ${state}. LLM explanation unavailable — no API key and Ollama unreachable.`
}

// ─── main ────────────────────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: FusionRequest
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const { sensor_id, eeg, hrv, doppler } = body
  if (!sensor_id || !eeg || !hrv) {
    return new Response(JSON.stringify({ error: 'Missing sensor_id, eeg, or hrv' }), { status: 400 })
  }
  if (eeg.alpha_power === 0) {
    return new Response(JSON.stringify({ error: 'alpha_power cannot be zero' }), { status: 400 })
  }

  const timestamp      = body.timestamp ?? new Date().toISOString()
  const thetaAlpha     = eeg.theta_power / eeg.alpha_power
  const lfHf           = hrv.hf_power === 0 ? Infinity : hrv.lf_power / hrv.hf_power
  const state          = classify(thetaAlpha, lfHf)
  const gsrBaseline    = await getGSRBaseline(sensor_id)
  const dopplerResult  = doppler ? validateDoppler(doppler) : null

  const metrics = {
    theta_alpha_ratio: Math.round(thetaAlpha * 1000) / 1000,
    lf_hf_ratio:       Math.round(lfHf * 1000) / 1000,
    gsr_baseline:      gsrBaseline,
    doppler_valid:     dopplerResult
      ? dopplerResult.cardiac_ok && dopplerResult.respiratory_ok
      : null,
    doppler_detail:    dopplerResult,
  }

  // LLM explanation (non-blocking best-effort)
  const explanation = await explain(state, metrics)

  // Persist fused reading
  await supabase.from('sensor_readings').insert({
    sensor_id,
    sensor_type: 'eeg',
    timestamp,
    band: 'fusion',
    metadata: { state, ...metrics, explanation },
  })

  await appendAudit('bio_fusion', { sensor_id, state, ...metrics, timestamp })

  return new Response(JSON.stringify({
    state,
    metrics,
    explanation,
    timestamp,
    thresholds: { theta_alpha: THETA_ALPHA_THRESHOLD, lf_hf: LF_HF_THRESHOLD },
  }), { headers: { 'Content-Type': 'application/json' } })
})
