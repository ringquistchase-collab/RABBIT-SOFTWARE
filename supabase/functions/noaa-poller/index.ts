// Scheduled via Supabase cron: every 15 minutes
// supabase/config.toml: [functions.noaa-poller] schedule = "*/15 * * * *"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)
const STATION = Deno.env.get('NOAA_STATION_ID') ?? 'KORD'

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

async function pollWeather() {
  const resp = await fetch(`https://api.weather.gov/stations/${STATION}/observations/latest`, {
    headers: { 'User-Agent': 'RabbitOS/1.0 (therealsickone.chase@gmail.com)' },
  })
  if (!resp.ok) { console.error('Weather fetch failed', resp.status); return }

  const { properties: p } = await resp.json()
  await supabase.from('sensor_readings').insert({
    sensor_id: `noaa_${STATION}`,
    sensor_type: 'noaa_weather',
    timestamp: p.timestamp ?? new Date().toISOString(),
    temperature_c: p.temperature?.value ?? null,
    humidity_pct: p.relativeHumidity?.value ?? null,
    pressure_hpa: p.barometricPressure?.value != null ? p.barometricPressure.value / 100 : null,
    metadata: {
      wind_speed_kmh: p.windSpeed?.value ?? null,
      wind_direction_deg: p.windDirection?.value ?? null,
      visibility_m: p.visibility?.value ?? null,
      station: STATION,
    },
  })
  await appendAudit('noaa_weather_poll', { station: STATION, ts: p.timestamp })
}

async function pollSpaceWeather() {
  const [kpRes, swRes] = await Promise.all([
    fetch('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json'),
    fetch('https://services.swpc.noaa.gov/products/solar-wind/plasma-1-minute.json'),
  ])

  if (kpRes.ok) {
    const kp: [string, string][] = await kpRes.json()
    const latest = kp[kp.length - 1]
    if (latest) {
      await supabase.from('sensor_readings').insert({
        sensor_id: 'noaa_kp_index',
        sensor_type: 'noaa_space',
        timestamp: new Date().toISOString(),
        kp_index: parseFloat(latest[1]),
        metadata: { source: 'NOAA_SWPC', raw: latest },
      })
    }
  }

  if (swRes.ok) {
    const sw: string[][] = await swRes.json()
    // Row 0 is headers; take last data row
    const latest = sw[sw.length - 1]
    if (latest && sw.length > 1) {
      await supabase.from('sensor_readings').insert({
        sensor_id: 'noaa_solar_wind',
        sensor_type: 'noaa_space',
        timestamp: new Date().toISOString(),
        solar_flux: parseFloat(latest[2]) || null, // proton density
        metadata: {
          source: 'NOAA_SWPC_SOLAR_WIND',
          speed_km_s: parseFloat(latest[1]) || null,
          temperature_k: parseFloat(latest[3]) || null,
        },
      })
    }
  }

  await appendAudit('noaa_space_poll', { ts: new Date().toISOString() })
}

Deno.serve(async () => {
  await Promise.all([pollWeather(), pollSpaceWeather()])
  return new Response(JSON.stringify({ ok: true, polled_at: new Date().toISOString() }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
