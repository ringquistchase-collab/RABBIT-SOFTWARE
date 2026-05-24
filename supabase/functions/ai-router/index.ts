// RabbitOS AI task router — ports the Python routing logic to Deno/TypeScript
// Routes: code→deepseek, analysis→llama, chat→mistral, research→claude
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const ANTHROPIC_KEY = Deno.env.get('ANTHROPIC_API_KEY')
const OPENAI_KEY    = Deno.env.get('OPENAI_API_KEY')
const OLLAMA_URL    = Deno.env.get('OLLAMA_URL') ?? 'http://localhost:11434'

type TaskType = 'code' | 'analysis' | 'chat' | 'research'

const ROUTES: Record<TaskType, { provider: 'ollama' | 'anthropic' | 'openai'; model: string }> = {
  code:     { provider: 'ollama',     model: 'deepseek-coder' },
  analysis: { provider: 'ollama',     model: 'llama3'         },
  chat:     { provider: 'ollama',     model: 'mistral'        },
  research: { provider: 'anthropic',  model: 'claude-sonnet-4-6' },
}

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

async function callOllama(model: string, prompt: string): Promise<string> {
  const r = await fetch(`${OLLAMA_URL}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, prompt, stream: false }),
  })
  return ((await r.json()) as { response?: string }).response ?? ''
}

async function callAnthropic(model: string, prompt: string): Promise<string> {
  if (!ANTHROPIC_KEY) throw new Error('ANTHROPIC_API_KEY not set')
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': ANTHROPIC_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({ model, max_tokens: 1024, messages: [{ role: 'user', content: prompt }] }),
  })
  const j = await r.json()
  return j.content?.[0]?.text ?? ''
}

async function callOpenAI(model: string, prompt: string): Promise<string> {
  if (!OPENAI_KEY) throw new Error('OPENAI_API_KEY not set')
  const r = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${OPENAI_KEY}` },
    body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }] }),
  })
  const j = await r.json()
  return j.choices?.[0]?.message?.content ?? ''
}

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: { type: TaskType; prompt: string }
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const { type: taskType, prompt } = body
  if (!taskType || !prompt) return new Response(JSON.stringify({ error: 'Missing type or prompt' }), { status: 400 })

  const route = ROUTES[taskType] ?? ROUTES.chat
  let result = ''
  let usedModel = route.model
  let fallback = false

  try {
    if (route.provider === 'anthropic') result = await callAnthropic(route.model, prompt)
    else if (route.provider === 'openai')  result = await callOpenAI(route.model, prompt)
    else                                   result = await callOllama(route.model, prompt)
  } catch (e) {
    // Fall back to Claude if primary model unreachable
    if (!ANTHROPIC_KEY) return new Response(JSON.stringify({ error: `Model failed: ${(e as Error).message}` }), { status: 502 })
    result = await callAnthropic('claude-sonnet-4-6', prompt)
    usedModel = 'claude-sonnet-4-6 (fallback)'
    fallback = true
  }

  await appendAudit('ai_router', { task_type: taskType, model: usedModel, fallback, prompt_len: prompt.length })

  return new Response(JSON.stringify({ result, model: usedModel, task_type: taskType, fallback }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
