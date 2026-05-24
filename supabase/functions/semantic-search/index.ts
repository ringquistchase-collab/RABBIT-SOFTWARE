// Natural language + state-based similarity search over telemetry embeddings
// "find past states similar to this one" — powers memory retrieval and pattern detection
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const OPENAI_KEY = Deno.env.get('OPENAI_API_KEY')
const OLLAMA_URL = Deno.env.get('OLLAMA_URL') ?? 'http://localhost:11434'
const EMBED_DIMS = 768

// ─── embedding (mirrors embed-telemetry) ─────────────────────────────────────

async function embedOpenAI(text: string): Promise<number[]> {
  const r = await fetch('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${OPENAI_KEY}` },
    body: JSON.stringify({ model: 'text-embedding-3-small', input: text, dimensions: EMBED_DIMS }),
  })
  const j = await r.json()
  if (!j.data?.[0]?.embedding) throw new Error(`OpenAI: ${JSON.stringify(j.error)}`)
  return j.data[0].embedding
}

async function embedOllama(text: string): Promise<number[]> {
  const r = await fetch(`${OLLAMA_URL}/api/embeddings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'nomic-embed-text', prompt: text }),
  })
  const j = await r.json()
  if (!j.embedding) throw new Error(`Ollama: ${JSON.stringify(j)}`)
  return j.embedding
}

async function embed(text: string): Promise<number[]> {
  if (OPENAI_KEY) {
    try { return await embedOpenAI(text) } catch { /* fall through */ }
  }
  return await embedOllama(text)
}

// ─── query builder — turn a structured state into search text ────────────────

function stateToText(body: SearchRequest): string {
  if (body.query) return body.query  // natural language query takes priority

  const parts: string[] = []
  if (body.sensor_type) parts.push(`sensor_type: ${body.sensor_type}`)
  if (body.state)       parts.push(`state: ${body.state}`)
  if (body.metrics)     Object.entries(body.metrics).forEach(([k, v]) => parts.push(`${k}: ${v}`))
  return parts.join('. ') || 'telemetry event'
}

// ─── types ───────────────────────────────────────────────────────────────────

interface SearchRequest {
  query?:              string   // natural language: "high stress events at night"
  sensor_type?:        string   // filter: eeg | rf | noaa_weather | ...
  event_type?:         string   // filter: bio_fusion | eeg_process | ...
  state?:              string   // filter: STRESS_CONFIRMED | BASELINE | ...
  metrics?:            Record<string, unknown>  // structured state to match against
  match_threshold?:    number   // cosine similarity floor (default 0.70)
  match_count?:        number   // max results (default 10)
}

// ─── main ────────────────────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: SearchRequest
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const searchText = stateToText(body)
  if (!searchText) return new Response(JSON.stringify({ error: 'Provide query or at least one filter' }), { status: 400 })

  let queryVector: number[]
  try { queryVector = await embed(searchText) }
  catch (e) {
    return new Response(JSON.stringify({ error: `Embedding failed: ${(e as Error).message}` }), { status: 502 })
  }

  const { data, error } = await supabase.rpc('match_telemetry', {
    query_embedding:    `[${queryVector.join(',')}]`,
    match_threshold:    body.match_threshold    ?? 0.70,
    match_count:        body.match_count        ?? 10,
    filter_sensor_type: body.sensor_type        ?? null,
    filter_event_type:  body.event_type         ?? null,
    filter_state:       body.state              ?? null,
  })

  if (error) return new Response(JSON.stringify({ error: error.message }), { status: 500 })

  return new Response(JSON.stringify({
    query:   searchText,
    count:   (data as unknown[]).length,
    results: data,
  }), { headers: { 'Content-Type': 'application/json' } })
})
