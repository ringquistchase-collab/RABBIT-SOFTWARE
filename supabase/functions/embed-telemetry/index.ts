// Converts telemetry events into vector embeddings and stores in pgvector
// Embedding model: OpenAI text-embedding-3-small (768 dims) → Ollama nomic-embed-text fallback
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const OPENAI_KEY = Deno.env.get('OPENAI_API_KEY')
const OLLAMA_URL = Deno.env.get('OLLAMA_URL') ?? 'http://localhost:11434'
const EMBED_DIMS = 768

// ─── embedding providers ─────────────────────────────────────────────────────

async function embedOpenAI(text: string): Promise<number[]> {
  const r = await fetch('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${OPENAI_KEY}` },
    body: JSON.stringify({ model: 'text-embedding-3-small', input: text, dimensions: EMBED_DIMS }),
  })
  const j = await r.json()
  if (!j.data?.[0]?.embedding) throw new Error(`OpenAI embed failed: ${JSON.stringify(j.error)}`)
  return j.data[0].embedding
}

async function embedOllama(text: string): Promise<number[]> {
  const r = await fetch(`${OLLAMA_URL}/api/embeddings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'nomic-embed-text', prompt: text }),
  })
  const j = await r.json()
  if (!j.embedding) throw new Error(`Ollama embed failed: ${JSON.stringify(j)}`)
  // nomic-embed-text returns 768 dims — matches EMBED_DIMS
  return j.embedding
}

async function embed(text: string): Promise<{ vector: number[]; model: string }> {
  if (OPENAI_KEY) {
    try { return { vector: await embedOpenAI(text), model: 'text-embedding-3-small' } }
    catch { /* fall through */ }
  }
  return { vector: await embedOllama(text), model: 'nomic-embed-text' }
}

// ─── text serializer — converts structured telemetry into embeddable text ────

function serializeEvent(body: EmbedRequest): string {
  const parts: string[] = [
    `sensor_id: ${body.sensor_id}`,
    `sensor_type: ${body.sensor_type}`,
    `event: ${body.event_type}`,
  ]
  if (body.state)   parts.push(`state: ${body.state}`)
  if (body.content) return body.content  // caller supplied their own text

  if (body.metadata) {
    for (const [k, v] of Object.entries(body.metadata)) {
      if (v !== null && v !== undefined) parts.push(`${k}: ${v}`)
    }
  }
  return parts.join('. ')
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

// ─── types ───────────────────────────────────────────────────────────────────

interface EmbedRequest {
  sensor_id:   string
  sensor_type: string
  event_type:  string
  state?:      string
  content?:    string        // optional: override auto-generated text
  metadata?:   Record<string, unknown>
}

// ─── main ────────────────────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: EmbedRequest | EmbedRequest[]
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const events = Array.isArray(body) ? body : [body]
  const results: Record<string, unknown>[] = []

  for (const event of events) {
    if (!event.sensor_id || !event.sensor_type || !event.event_type) {
      results.push({ error: 'Missing sensor_id, sensor_type, or event_type', event })
      continue
    }

    const content = serializeEvent(event)

    let vector: number[]
    let model: string
    try {
      ;({ vector, model } = await embed(content))
    } catch (e) {
      results.push({ error: `Embedding failed: ${(e as Error).message}`, event })
      continue
    }

    const { error } = await supabase.from('telemetry_embeddings').insert({
      sensor_id:   event.sensor_id,
      sensor_type: event.sensor_type,
      event_type:  event.event_type,
      state:       event.state ?? null,
      content,
      embedding:   JSON.stringify(vector),  // pgvector accepts JSON array string
      metadata:    { ...event.metadata, embed_model: model },
    })

    if (error) {
      results.push({ error: error.message, event })
      continue
    }

    await appendAudit('telemetry_embedded', {
      sensor_id:  event.sensor_id,
      event_type: event.event_type,
      state:      event.state ?? null,
      model,
    })

    results.push({ ok: true, sensor_id: event.sensor_id, event_type: event.event_type, model, dims: vector.length })
  }

  return new Response(JSON.stringify({ embedded: results.filter(r => r.ok).length, results }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
