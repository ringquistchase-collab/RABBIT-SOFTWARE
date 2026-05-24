// Ethereum integration for RabbitOS audit anchoring
// READ-ONLY mode: monitors contract events, builds unsigned transactions
// To enable writes: add WALLET_PRIVATE_KEY as a Supabase secret
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const CONTRACT   = '0x04129bdae6695b81d2258f14de5d32eac61cba13'
const ETH_RPC    = Deno.env.get('ETH_RPC_URL')      ?? 'https://ethereum.publicnode.com'
const ESCAN_KEY  = Deno.env.get('ETHERSCAN_API_KEY') ?? ''
const HAS_KEY    = !!Deno.env.get('WALLET_PRIVATE_KEY')

// ─── helpers ────────────────────────────────────────────────────────────────

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

async function rpc(method: string, params: unknown[]): Promise<unknown> {
  const r = await fetch(ETH_RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  })
  const j = await r.json()
  if (j.error) throw new Error(j.error.message)
  return j.result
}

// ─── ABI encoding (manual — replace selector once you have the full ABI) ───

// Selector = keccak256("storeFrozenTimeline(uint256,bytes32)")[0:4]
// Placeholder: verify against your deployed ABI with:
//   ethers.id("storeFrozenTimeline(uint256,bytes32)").slice(0,10)
const SELECTOR = '0x????????'

function abiEncodeUint256(n: bigint): string {
  return n.toString(16).padStart(64, '0')
}

function abiEncodeBytes32(hex: string): string {
  const clean = hex.startsWith('0x') ? hex.slice(2) : hex
  return clean.padEnd(64, '0').slice(0, 64)
}

function buildCalldata(age: number, eegDataHash: string): string {
  return SELECTOR
    + abiEncodeUint256(BigInt(age))
    + abiEncodeBytes32(eegDataHash)
}

// ─── mode: build unsigned transaction ───────────────────────────────────────

async function buildUnsignedTx(age: number, eegDataHash: string) {
  const nonce  = await rpc('eth_getTransactionCount', [CONTRACT, 'latest'])
  const gasPrice = await rpc('eth_gasPrice', [])

  const unsignedTx = {
    to:       CONTRACT,
    data:     buildCalldata(age, eegDataHash),
    value:    '0x0',
    nonce,
    gasPrice,
    // Estimate gas — will fail without real ABI/selector; safe fallback shown
    gas:      '0x186A0', // 100,000 — replace after estimateGas with real selector
    chainId:  1,         // Ethereum mainnet
    note:     'Add WALLET_PRIVATE_KEY secret to Supabase to sign and submit.',
    selector_warning: SELECTOR === '0x????????'
      ? 'Replace SELECTOR constant with keccak256("storeFrozenTimeline(uint256,bytes32)")[0:4]'
      : 'ok',
  }

  await appendAudit('eth_tx_built', { age, eeg_data_hash: eegDataHash, to: CONTRACT })
  return unsignedTx
}

// ─── mode: sync events from Etherscan ───────────────────────────────────────

interface EtherscanTx {
  hash: string
  blockNumber: string
  timeStamp: string
  from: string
  to: string
  value: string
  input: string
  isError: string
  txreceipt_status: string
}

async function syncEvents() {
  // Fetch the latest stored block to avoid re-inserting old entries
  const { data: latest } = await supabase
    .from('audit_log')
    .select('payload')
    .eq('event_type', 'eth_event')
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle()

  const startBlock = (latest?.payload as { block_number?: string } | null)?.block_number ?? '0'

  const url = new URL('https://api.etherscan.io/api')
  url.searchParams.set('module', 'account')
  url.searchParams.set('action', 'txlist')
  url.searchParams.set('address', CONTRACT)
  url.searchParams.set('startblock', startBlock)
  url.searchParams.set('endblock', '99999999')
  url.searchParams.set('sort', 'asc')
  if (ESCAN_KEY) url.searchParams.set('apikey', ESCAN_KEY)

  const resp = await fetch(url.toString())
  const json = await resp.json()

  if (json.status !== '1' || !Array.isArray(json.result)) {
    return { synced: 0, message: json.message ?? 'No new transactions' }
  }

  const txs: EtherscanTx[] = json.result
  let synced = 0

  for (const tx of txs) {
    if (tx.isError === '1') continue
    await appendAudit('eth_event', {
      tx_hash:      tx.hash,
      block_number: tx.blockNumber,
      timestamp:    new Date(parseInt(tx.timeStamp) * 1000).toISOString(),
      from:         tx.from,
      method_input: tx.input.slice(0, 10), // first 4 bytes = selector
      status:       tx.txreceipt_status === '1' ? 'success' : 'pending',
    })
    synced++
  }

  return { synced, latest_block: txs[txs.length - 1]?.blockNumber ?? startBlock }
}

// ─── mode: get latest contract state via eth_call ───────────────────────────

async function getContractInfo() {
  const blockHex = (await rpc('eth_blockNumber', [])) as string
  const blockNum = parseInt(blockHex, 16)
  return {
    contract:    CONTRACT,
    chain:       'ethereum',
    latest_block: blockNum,
    rpc_endpoint: ETH_RPC.replace(/\/[^/]*key[^/]*/i, '/[redacted]'),
    write_enabled: HAS_KEY,
  }
}

// ─── router ─────────────────────────────────────────────────────────────────

Deno.serve(async (req) => {
  const method = req.method

  // Scheduled sync (GET) or explicit sync request
  if (method === 'GET') {
    const info   = await getContractInfo()
    const synced = await syncEvents()
    return new Response(JSON.stringify({ ...info, sync: synced }), {
      headers: { 'Content-Type': 'application/json' },
    })
  }

  if (method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: { mode?: string; age?: number; eeg_data_hash?: string }
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  switch (body.mode) {
    case 'build_tx': {
      if (body.age === undefined || !body.eeg_data_hash) {
        return new Response(JSON.stringify({ error: 'Missing age or eeg_data_hash' }), { status: 400 })
      }
      const tx = await buildUnsignedTx(body.age, body.eeg_data_hash)
      return new Response(JSON.stringify(tx), { headers: { 'Content-Type': 'application/json' } })
    }

    case 'sync':
      return new Response(JSON.stringify(await syncEvents()), { headers: { 'Content-Type': 'application/json' } })

    case 'submit_tx':
      if (!HAS_KEY) {
        return new Response(JSON.stringify({
          error:       'Write mode disabled',
          instructions: 'Add WALLET_PRIVATE_KEY as a Supabase secret, then redeploy to enable transaction signing.',
        }), { status: 403 })
      }
      // Key path — implement signing here once WALLET_PRIVATE_KEY is available
      return new Response(JSON.stringify({ error: 'Signing not yet implemented' }), { status: 501 })

    default:
      return new Response(JSON.stringify({ error: 'Unknown mode. Use: build_tx | sync | submit_tx' }), { status: 400 })
  }
})
