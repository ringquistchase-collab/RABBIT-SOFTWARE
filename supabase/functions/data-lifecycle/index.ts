// Moves sensor_readings older than HOT_TIER_DAYS to GCS as partitioned JSONL
// Scheduled daily — keeps Supabase lean, archive stays queryable (BigQuery etc.)
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const HOT_DAYS  = parseInt(Deno.env.get('HOT_TIER_DAYS') ?? '7')
const GCS_BUCKET = Deno.env.get('GCS_BUCKET') ?? 'rabbitos-archive'
const BATCH_SIZE = 500

// ─── GCS auth (service account JWT → access token) ──────────────────────────

function pemToDer(pem: string): ArrayBuffer {
  const b64 = pem.replace(/-----[^-]+-----/g, '').replace(/\s/g, '')
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes.buffer
}

function b64url(buf: ArrayBuffer | string): string {
  const b64 = typeof buf === 'string'
    ? btoa(buf)
    : btoa(String.fromCharCode(...new Uint8Array(buf)))
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
}

async function getGCSToken(): Promise<string> {
  const sa = JSON.parse(Deno.env.get('GCS_SERVICE_ACCOUNT_JSON')!)
  const now = Math.floor(Date.now() / 1000)

  const header  = b64url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const payload = b64url(JSON.stringify({
    iss:   sa.client_email,
    scope: 'https://www.googleapis.com/auth/devstorage.read_write',
    aud:   'https://oauth2.googleapis.com/token',
    iat:   now,
    exp:   now + 3600,
  }))

  const unsigned  = `${header}.${payload}`
  const cryptoKey = await crypto.subtle.importKey(
    'pkcs8', pemToDer(sa.private_key),
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false, ['sign'],
  )
  const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', cryptoKey, new TextEncoder().encode(unsigned))
  const jwt = `${unsigned}.${b64url(sig)}`

  const r = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${jwt}`,
  })
  const { access_token, error } = await r.json()
  if (!access_token) throw new Error(`GCS auth failed: ${error}`)
  return access_token
}

// ─── GCS upload ──────────────────────────────────────────────────────────────

async function uploadToGCS(token: string, path: string, jsonl: string): Promise<number> {
  const body   = new TextEncoder().encode(jsonl)
  const url    = `https://storage.googleapis.com/upload/storage/v1/b/${GCS_BUCKET}/o?uploadType=media&name=${encodeURIComponent(path)}`
  const r = await fetch(url, {
    method:  'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/x-ndjson' },
    body,
  })
  if (!r.ok) throw new Error(`GCS upload failed: ${r.status} ${await r.text()}`)
  return body.byteLength
}

// ─── sha256 + audit ──────────────────────────────────────────────────────────

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

// ─── lifecycle logic ─────────────────────────────────────────────────────────

interface SensorRow { id: string; [k: string]: unknown }

async function archiveBatch(
  token: string,
  sensorType: string,
  date: string, // YYYY-MM-DD
): Promise<{ skipped: boolean; rows: number; bytes: number }> {

  // Skip if already archived
  const { data: existing } = await supabase
    .from('sensor_reading_archives')
    .select('id')
    .eq('sensor_type', sensorType)
    .eq('date', date)
    .maybeSingle()
  if (existing) return { skipped: true, rows: 0, bytes: 0 }

  // Fetch all rows for this (type, date) in pages
  const allRows: SensorRow[] = []
  let from = 0
  while (true) {
    const { data, error } = await supabase
      .from('sensor_readings')
      .select('*')
      .eq('sensor_type', sensorType)
      .gte('timestamp', `${date}T00:00:00Z`)
      .lt( 'timestamp', `${date}T23:59:59.999Z`)
      .range(from, from + BATCH_SIZE - 1)
      .order('timestamp', { ascending: true })

    if (error) throw new Error(error.message)
    if (!data || data.length === 0) break
    allRows.push(...(data as SensorRow[]))
    if (data.length < BATCH_SIZE) break
    from += BATCH_SIZE
  }

  if (allRows.length === 0) return { skipped: true, rows: 0, bytes: 0 }

  // GCS path: year=YYYY/month=MM/day=DD/sensor_type.jsonl  (BigQuery-compatible partitioning)
  const [year, month, day] = date.split('-')
  const gcsPath = `sensor_readings/year=${year}/month=${month}/day=${day}/${sensorType}.jsonl`
  const jsonl   = allRows.map(r => JSON.stringify(r)).join('\n')
  const bytes   = await uploadToGCS(token, gcsPath, jsonl)

  // Record the archive entry
  await supabase.from('sensor_reading_archives').insert({
    sensor_type: sensorType,
    date,
    gcs_path:   `gs://${GCS_BUCKET}/${gcsPath}`,
    row_count:  allRows.length,
    size_bytes: bytes,
  })

  // Delete archived rows from hot tier
  const ids = allRows.map(r => r.id)
  await supabase.from('sensor_readings').delete().in('id', ids)

  await appendAudit('data_archived', {
    sensor_type: sensorType,
    date,
    gcs_path:   `gs://${GCS_BUCKET}/${gcsPath}`,
    row_count:  allRows.length,
    size_bytes: bytes,
  })

  return { skipped: false, rows: allRows.length, bytes }
}

// ─── main ────────────────────────────────────────────────────────────────────

Deno.serve(async () => {
  const cutoff = new Date(Date.now() - HOT_DAYS * 86_400_000).toISOString().slice(0, 10)

  // Find distinct (sensor_type, date) combinations older than cutoff
  const { data: candidates, error } = await supabase
    .from('sensor_readings')
    .select('sensor_type, timestamp')
    .lt('timestamp', `${cutoff}T00:00:00Z`)
    .order('timestamp', { ascending: true })
    .limit(2000)

  if (error) return new Response(JSON.stringify({ error: error.message }), { status: 500 })
  if (!candidates || candidates.length === 0) {
    return new Response(JSON.stringify({ ok: true, message: 'Nothing to archive' }), {
      headers: { 'Content-Type': 'application/json' },
    })
  }

  // Deduplicate into unique (sensor_type, date) pairs
  const pairs = new Map<string, { sensor_type: string; date: string }>()
  for (const row of candidates as { sensor_type: string; timestamp: string }[]) {
    const date = row.timestamp.slice(0, 10)
    const key  = `${row.sensor_type}::${date}`
    if (!pairs.has(key)) pairs.set(key, { sensor_type: row.sensor_type, date })
  }

  let token: string
  try { token = await getGCSToken() }
  catch (e) {
    return new Response(JSON.stringify({ error: `GCS auth: ${(e as Error).message}` }), { status: 500 })
  }

  const results: Record<string, unknown>[] = []
  let totalRows = 0
  let totalBytes = 0

  for (const { sensor_type, date } of pairs.values()) {
    try {
      const r = await archiveBatch(token, sensor_type, date)
      results.push({ sensor_type, date, ...r })
      totalRows  += r.rows
      totalBytes += r.bytes
    } catch (e) {
      results.push({ sensor_type, date, error: (e as Error).message })
    }
  }

  return new Response(JSON.stringify({
    ok: true,
    cutoff,
    hot_tier_days: HOT_DAYS,
    gcs_bucket:    GCS_BUCKET,
    total_rows_archived:  totalRows,
    total_bytes_uploaded: totalBytes,
    batches: results,
  }), { headers: { 'Content-Type': 'application/json' } })
})
