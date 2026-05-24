// XRPL Bio Black Box anchor — open-source stack
// Libraries: xrpl.js (MIT) + Web Crypto (built-in) + Claude/llama3 for summaries
// Anchors audit_log hashes to XRP Ledger via Memo field on Payment transactions
// Batch mode builds a Merkle root over a time window before anchoring
import { createClient }                          from 'https://esm.sh/@supabase/supabase-js@2'
import { Client, Wallet, xrpToDrops }            from 'https://esm.sh/xrpl@3'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const XRPL_NODE     = Deno.env.get('XRPL_NODE')        ?? 'wss://s.altnet.rippletest.net:51234'
const XRPL_SEED     = Deno.env.get('XRPL_WALLET_SEED') // sXXX... format — add as Supabase secret
const XRPL_TESTNET  = Deno.env.get('XRPL_TESTNET')     !== 'false'  // testnet by default
const ANTHROPIC_KEY = Deno.env.get('ANTHROPIC_API_KEY')
const OLLAMA_URL    = Deno.env.get('OLLAMA_URL')        ?? 'http://localhost:11434'

// ─── sha256 ──────────────────────────────────────────────────────────────────

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

// ─── Merkle tree (pure Web Crypto — no deps) ─────────────────────────────────

async function merkleRoot(leaves: string[]): Promise<string> {
  if (leaves.length === 0) return '0'.repeat(64)
  if (leaves.length === 1) return leaves[0]
  const level = [...leaves]
  if (level.length % 2 !== 0) level.push(level[level.length - 1]) // duplicate last leaf
  const parents: string[] = []
  for (let i = 0; i < level.length; i += 2) {
    parents.push(await sha256(level[i] + level[i + 1]))
  }
  return merkleRoot(parents)
}

// ─── audit log helpers ───────────────────────────────────────────────────────

async function appendAudit(eventType: string, payload: Record<string, unknown>) {
  const payloadHash = await sha256(JSON.stringify(payload))
  const { data: last } = await supabase.from('audit_log').select('chain_hash').order('id', { ascending: false }).limit(1).maybeSingle()
  const prevHash  = last?.chain_hash ?? '0'.repeat(64)
  const chainHash = await sha256(prevHash + payloadHash)
  await supabase.from('audit_log').insert({ event_type: eventType, payload, payload_hash: payloadHash, prev_hash: prevHash, chain_hash: chainHash })
}

// ─── LLM anchor summary: Claude → llama3 fallback (open source) ──────────────

async function summarizeAnchor(payload: Record<string, unknown>): Promise<string> {
  const prompt = [
    'You are an audit system. Write one sentence describing what this XRPL anchor record proves.',
    `Events anchored: ${payload.event_count}. Merkle root: ${String(payload.merkle_root).slice(0, 16)}...`,
    `Time window: ${payload.window ?? 'single event'}. Network: ${XRPL_TESTNET ? 'testnet' : 'mainnet'}.`,
    'Be factual. Do not embellish.',
  ].join(' ')

  if (ANTHROPIC_KEY) {
    try {
      const r = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': ANTHROPIC_KEY, 'anthropic-version': '2023-06-01' },
        body: JSON.stringify({ model: 'claude-haiku-4-5-20251001', max_tokens: 80, messages: [{ role: 'user', content: prompt }] }),
      })
      const j = await r.json()
      if (j.content?.[0]?.text) return j.content[0].text
    } catch { /* fall through */ }
  }

  // Open-source fallback: Ollama llama3
  try {
    const r = await fetch(`${OLLAMA_URL}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'llama3', prompt, stream: false }),
    })
    const j = await r.json()
    if (j.response) return j.response
  } catch { /* unavailable */ }

  return `Anchored ${payload.event_count} audit events to XRPL. Merkle root: ${payload.merkle_root}`
}

// ─── XRPL helpers ────────────────────────────────────────────────────────────

function toHex(text: string): string {
  return Array.from(new TextEncoder().encode(text))
    .map(b => b.toString(16).padStart(2, '0')).join('').toUpperCase()
}

async function submitAnchor(merkle: string, summary: string, eventCount: number): Promise<string> {
  if (!XRPL_SEED) throw new Error('XRPL_WALLET_SEED not set — add as Supabase secret')

  const client = new Client(XRPL_NODE)
  await client.connect()

  try {
    const wallet = Wallet.fromSeed(XRPL_SEED)

    const tx = await client.autofill({
      TransactionType: 'Payment',
      Account:         wallet.address,
      Destination:     wallet.address,   // self-payment — just a memo carrier
      Amount:          xrpToDrops('0.000001'),
      Memos: [
        {
          Memo: {
            MemoType: toHex('rabbitos/audit'),
            MemoData: toHex(merkle),
          },
        },
        {
          Memo: {
            MemoType: toHex('rabbitos/meta'),
            MemoData: toHex(JSON.stringify({ events: eventCount, summary: summary.slice(0, 120) })),
          },
        },
      ],
    })

    const signed    = wallet.sign(tx)
    const result    = await client.submitAndWait(signed.tx_blob)
    const txHash    = result.result.hash ?? signed.hash
    return txHash as string
  } finally {
    await client.disconnect()
  }
}

// ─── verify tx on ledger ─────────────────────────────────────────────────────

async function verifyTx(txHash: string): Promise<Record<string, unknown>> {
  const client = new Client(XRPL_NODE)
  await client.connect()
  try {
    const result = await client.request({ command: 'tx', transaction: txHash })
    const r = result.result as Record<string, unknown>
    return {
      found:       true,
      validated:   r.validated,
      ledger_index: r.ledger_index,
      date:        r.date,
      fee:         r.Fee,
      memos:       (r.Memos as { Memo: { MemoType: string; MemoData: string } }[])?.map(m => ({
        type: Buffer.from(m.Memo.MemoType, 'hex').toString('utf8'),
        data: Buffer.from(m.Memo.MemoData, 'hex').toString('utf8'),
      })),
    }
  } catch {
    return { found: false, tx_hash: txHash }
  } finally {
    await client.disconnect()
  }
}

// ─── wallet info ─────────────────────────────────────────────────────────────

async function walletInfo(): Promise<Record<string, unknown>> {
  if (!XRPL_SEED) return { error: 'XRPL_WALLET_SEED not configured', write_enabled: false }
  const wallet = Wallet.fromSeed(XRPL_SEED)
  const client = new Client(XRPL_NODE)
  await client.connect()
  try {
    const info = await client.request({ command: 'account_info', account: wallet.address, ledger_index: 'validated' })
    const acc  = (info.result as { account_data: { Balance: string; Sequence: number } }).account_data
    return {
      address:      wallet.address,
      balance_xrp:  parseInt(acc.Balance) / 1_000_000,
      sequence:     acc.Sequence,
      network:      XRPL_TESTNET ? 'testnet' : 'mainnet',
      node:         XRPL_NODE,
      write_enabled: true,
    }
  } catch (e) {
    return { address: wallet.address, error: (e as Error).message, write_enabled: false }
  } finally {
    await client.disconnect()
  }
}

// ─── mode: anchor specific audit_log rows ────────────────────────────────────

async function anchorEvents(auditIds: number[]): Promise<Record<string, unknown>> {
  const { data, error } = await supabase
    .from('audit_log')
    .select('id, event_type, chain_hash, created_at')
    .in('id', auditIds)
    .order('id', { ascending: true })

  if (error) throw new Error(error.message)
  if (!data || data.length === 0) return { error: 'No matching audit_log rows found' }

  const leaves  = (data as { chain_hash: string }[]).map(r => r.chain_hash)
  const merkle  = await merkleRoot(leaves)
  const summary = await summarizeAnchor({ event_count: data.length, merkle_root: merkle })
  const txHash  = await submitAnchor(merkle, summary, data.length)

  await appendAudit('xrpl_anchor', {
    tx_hash:     txHash,
    merkle_root: merkle,
    audit_ids:   auditIds,
    event_count: data.length,
    network:     XRPL_TESTNET ? 'testnet' : 'mainnet',
    summary,
  })

  return { ok: true, tx_hash: txHash, merkle_root: merkle, event_count: data.length, summary, network: XRPL_TESTNET ? 'testnet' : 'mainnet' }
}

// ─── mode: batch Merkle anchor over a time window ────────────────────────────

async function anchorMerkle(windowMinutes: number): Promise<Record<string, unknown>> {
  const since = new Date(Date.now() - windowMinutes * 60 * 1000).toISOString()

  const { data, error } = await supabase
    .from('audit_log')
    .select('id, chain_hash, event_type')
    .gte('created_at', since)
    .order('id', { ascending: true })

  if (error) throw new Error(error.message)
  if (!data || data.length === 0) return { message: 'No events in window', window_minutes: windowMinutes }

  const leaves  = (data as { chain_hash: string }[]).map(r => r.chain_hash)
  const merkle  = await merkleRoot(leaves)
  const summary = await summarizeAnchor({ event_count: data.length, merkle_root: merkle, window: `${windowMinutes}m` })
  const txHash  = await submitAnchor(merkle, summary, data.length)

  await appendAudit('xrpl_merkle_anchor', {
    tx_hash:        txHash,
    merkle_root:    merkle,
    event_count:    data.length,
    window_minutes: windowMinutes,
    since,
    network:        XRPL_TESTNET ? 'testnet' : 'mainnet',
    summary,
  })

  return { ok: true, tx_hash: txHash, merkle_root: merkle, event_count: data.length, window_minutes: windowMinutes, summary }
}

// ─── router ──────────────────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method === 'GET') {
    return new Response(JSON.stringify(await walletInfo()), { headers: { 'Content-Type': 'application/json' } })
  }

  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: { mode: string; audit_ids?: number[]; window_minutes?: number; tx_hash?: string }
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  try {
    switch (body.mode) {
      case 'anchor_event':
        if (!body.audit_ids?.length) return new Response(JSON.stringify({ error: 'Provide audit_ids array' }), { status: 400 })
        return new Response(JSON.stringify(await anchorEvents(body.audit_ids)), { headers: { 'Content-Type': 'application/json' } })

      case 'anchor_merkle':
        return new Response(JSON.stringify(await anchorMerkle(body.window_minutes ?? 60)), { headers: { 'Content-Type': 'application/json' } })

      case 'verify':
        if (!body.tx_hash) return new Response(JSON.stringify({ error: 'Provide tx_hash' }), { status: 400 })
        return new Response(JSON.stringify(await verifyTx(body.tx_hash)), { headers: { 'Content-Type': 'application/json' } })

      default:
        return new Response(JSON.stringify({ error: 'Unknown mode. Use: anchor_event | anchor_merkle | verify' }), { status: 400 })
    }
  } catch (e) {
    return new Response(JSON.stringify({ error: (e as Error).message }), { status: 500 })
  }
})
