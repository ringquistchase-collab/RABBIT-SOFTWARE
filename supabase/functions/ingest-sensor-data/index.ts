import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

type SensorType = 'rf' | 'weather' | 'eeg' | 'adsb' | 'noaa_weather' | 'noaa_space'

interface IngestPayload {
  sensor_id: string
  sensor_type: SensorType
  timestamp?: string
  data: Record<string, unknown>
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

async function appendAudit(eventType: string, payload: Record<string, unknown>) {
  const payloadHash = await sha256(JSON.stringify(payload))
  const { data: last } = await supabase
    .from('audit_log')
    .select('chain_hash')
    .order('id', { ascending: false })
    .limit(1)
    .maybeSingle()
  const prevHash = last?.chain_hash ?? '0'.repeat(64)
  const chainHash = await sha256(prevHash + payloadHash)
  await supabase.from('audit_log').insert({ event_type: eventType, payload, payload_hash: payloadHash, prev_hash: prevHash, chain_hash: chainHash })
}

function normalize(body: IngestPayload): Record<string, unknown> {
  const { sensor_id, sensor_type, data } = body
  const base: Record<string, unknown> = {
    sensor_id,
    sensor_type,
    timestamp: body.timestamp ?? new Date().toISOString(),
    metadata: data,
  }

  switch (sensor_type) {
    case 'rf':
    case 'adsb':
      return { ...base, frequency_mhz: data.frequency_mhz ?? null, power_dbm: data.power_dbm ?? null, signal_type: data.signal_type ?? sensor_type, bandwidth_mhz: data.bandwidth_mhz ?? null }
    case 'weather':
    case 'noaa_weather':
      return { ...base, temperature_c: data.temperature_c ?? null, humidity_pct: data.humidity_pct ?? null, pressure_hpa: data.pressure_hpa ?? null }
    case 'eeg':
      return { ...base, channel: data.channel ?? null, amplitude_uv: data.amplitude_uv ?? null, band: data.band ?? null }
    case 'noaa_space':
      return { ...base, kp_index: data.kp_index ?? null, solar_flux: data.solar_flux ?? null }
    default:
      return base
  }
}

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: IngestPayload
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  if (!body.sensor_id || !body.sensor_type || !body.data) {
    return new Response(JSON.stringify({ error: 'Missing sensor_id, sensor_type, or data' }), { status: 400 })
  }

  const reading = normalize(body)
  const { error } = await supabase.from('sensor_readings').insert(reading)
  if (error) return new Response(JSON.stringify({ error: error.message }), { status: 500 })

  await appendAudit('sensor_ingest', { sensor_id: body.sensor_id, sensor_type: body.sensor_type, timestamp: reading.timestamp })

  return new Response(JSON.stringify({ ok: true, timestamp: reading.timestamp }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
