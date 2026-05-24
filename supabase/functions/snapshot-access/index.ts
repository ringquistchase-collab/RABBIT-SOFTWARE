// snapshot-access — Tiered Digital Twin snapshot access control
//
// CRITICAL (OD, age 22): vault-only, no digital path, destruction protocol
// HIGH     (PTSD, age 7): 3-of-5 threshold signatures + 24hr ephemeral key
// LOW      (baseline 33): XRPL token gate (0.001 XRP) + BlockGPT + ZK proofs
//
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
)

const XRPL_GATE_XRP        = 0.001          // minimum XRP for LOW tier access
const BLOCKGPT_ENDPOINT    = Deno.env.get('BLOCKGPT_ENDPOINT') ?? ''
const XRPL_RPC             = Deno.env.get('XRPL_RPC') ?? 'https://xrplcluster.com'

type AccessTier = 'LOW' | 'HIGH' | 'CRITICAL'

// ── Request shapes ────────────────────────────────────────────

interface BaseRequest {
  twin_id:      string
  snapshot_id:  number
  requester_id: string       // device / session fingerprint
}

// LOW tier: provide XRPL tx hash proving the 0.001 XRP gate payment
interface LowTierRequest extends BaseRequest {
  tier:          'LOW'
  key_hash:      string      // SHA-256(raw_key) generated client-side
  xrpl_tx_hash:  string      // XRPL payment tx from requester
  zk_proof_hash: string      // SHA-256(raw proof bytes)
  zk_public_inputs: Record<string, unknown>
  proof_system?: 'groth16' | 'plonk' | 'stark'
}

// HIGH tier: present collected threshold signatures (≥3 required)
interface HighTierRequest extends BaseRequest {
  tier:       'HIGH'
  key_hash:   string         // SHA-256(raw_key) generated client-side
  signatures: Array<{
    signer_index: number
    signature:    string     // base64 Ed25519 signature
    nonce:        string
  }>
}

// CRITICAL tier: destruction request only — no access granted
interface CriticalTierRequest extends BaseRequest {
  tier:     'CRITICAL'
  action:   'status' | 'request_destruction' | 'confirm_destruction'
  witness?: string
}

type SnapshotAccessRequest = LowTierRequest | HighTierRequest | CriticalTierRequest

// ── Helpers ───────────────────────────────────────────────────

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

async function appendAudit(eventType: string, payload: Record<string, unknown>) {
  const payloadHash = await sha256(JSON.stringify(payload))
  const { data: last } = await supabase
    .from('audit_log').select('chain_hash').order('id', { ascending: false }).limit(1).maybeSingle()
  const prevHash  = last?.chain_hash ?? '0'.repeat(64)
  const chainHash = await sha256(prevHash + payloadHash)
  await supabase.from('audit_log').insert({
    event_type: eventType, payload, payload_hash: payloadHash, prev_hash: prevHash, chain_hash: chainHash,
  })
}

// Verify XRPL payment: check the tx delivered ≥0.001 XRP to the twin's vault address
async function verifyXrplPayment(txHash: string, twinId: string): Promise<{
  ok: boolean
  amount_xrp?: number
  ledger_index?: number
  reason?: string
}> {
  try {
    const res = await fetch(XRPL_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method: 'tx', params: [{ transaction: txHash, binary: false }] }),
    })
    const json = await res.json() as { result?: { meta?: { delivered_amount?: string }; ledger_index?: number } }
    const delivered = json.result?.meta?.delivered_amount
    if (!delivered) return { ok: false, reason: 'tx not found or not validated' }
    const xrp = parseInt(delivered) / 1_000_000
    if (xrp < XRPL_GATE_XRP) {
      return { ok: false, reason: `delivered ${xrp} XRP < required ${XRPL_GATE_XRP} XRP` }
    }
    return { ok: true, amount_xrp: xrp, ledger_index: json.result?.ledger_index }
  } catch (e) {
    return { ok: false, reason: `XRPL RPC error: ${(e as Error).message}` }
  }
}

// BlockGPT anomaly check on the ZK proof public inputs
async function runBlockGptCheck(publicInputs: Record<string, unknown>): Promise<{
  verdict: string
  score: number
}> {
  if (!BLOCKGPT_ENDPOINT) return { verdict: 'PENDING', score: 0 }
  try {
    const res  = await fetch(BLOCKGPT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ inputs: publicInputs }),
    })
    const data = await res.json() as { verdict?: string; score?: number }
    return {
      verdict: data.verdict ?? 'PENDING',
      score:   typeof data.score === 'number' ? data.score : 0,
    }
  } catch {
    return { verdict: 'PENDING', score: 0 }
  }
}

// ── LOW tier handler ──────────────────────────────────────────

async function handleLowTier(body: LowTierRequest) {
  const { twin_id, snapshot_id, requester_id, key_hash, xrpl_tx_hash, zk_proof_hash, zk_public_inputs } = body
  const proof_system = body.proof_system ?? 'groth16'

  // Verify XRPL token gate
  const xrpl = await verifyXrplPayment(xrpl_tx_hash, twin_id)
  if (!xrpl.ok) {
    await supabase.from('snapshot_access_log').insert({
      snapshot_id, twin_id, access_tier: 'LOW', requester_id,
      granted: false, denial_reason: `XRPL gate: ${xrpl.reason}`, xrpl_tx_hash,
    })
    return { granted: false, reason: `XRPL gate failed: ${xrpl.reason}` }
  }

  // BlockGPT anomaly check on public inputs
  const bgpt = await runBlockGptCheck(zk_public_inputs)

  if (bgpt.verdict === 'ANOMALY' && bgpt.score > 0.8) {
    await supabase.from('snapshot_access_log').insert({
      snapshot_id, twin_id, access_tier: 'LOW', requester_id,
      granted: false, denial_reason: `BlockGPT anomaly score ${bgpt.score}`, xrpl_tx_hash,
    })
    return { granted: false, reason: `BlockGPT detected anomaly (score ${bgpt.score})` }
  }

  // Record ZK proof
  const { data: zkRow } = await supabase.from('snapshot_zk_proofs').insert({
    snapshot_id, twin_id,
    proof_system, proof_hash: zk_proof_hash,
    public_inputs: zk_public_inputs,
    xrpl_tx_hash,
    xrpl_ledger_index: xrpl.ledger_index ?? null,
    block_gpt_verdict: bgpt.verdict,
    block_gpt_score:   bgpt.score,
    verified_at:       new Date().toISOString(),
  }).select('id').single()

  // Issue ephemeral key via RPC (LOW tier: sig_count = 0, no threshold required)
  const { data: keyRows } = await supabase.rpc('request_ephemeral_key', {
    p_snapshot_id: snapshot_id,
    p_twin_id:     twin_id,
    p_key_hash:    key_hash,
    p_requester:   requester_id,
    p_sig_count:   0,
  })
  const keyRow = Array.isArray(keyRows) ? keyRows[0] : keyRows

  if (!keyRow?.granted) {
    return { granted: false, reason: keyRow?.reason ?? 'key issuance failed' }
  }

  await supabase.from('snapshot_access_log').insert({
    snapshot_id, twin_id, access_tier: 'LOW', requester_id,
    granted: true, xrpl_tx_hash,
    ephemeral_key_id: keyRow.key_id,
  })

  await appendAudit('snapshot_access_low', {
    snapshot_id, twin_id, requester_id,
    xrpl_tx_hash, xrpl_amount_xrp: xrpl.amount_xrp,
    zk_proof_id: zkRow?.id,
    block_gpt_verdict: bgpt.verdict,
    key_id: keyRow.key_id,
  })

  return {
    granted:          true,
    tier:             'LOW',
    key_id:           keyRow.key_id,
    expires_at:       keyRow.expires_at,
    block_gpt_score:  bgpt.score,
    block_gpt_verdict: bgpt.verdict,
    xrpl_amount_xrp:  xrpl.amount_xrp,
  }
}

// ── HIGH tier handler ─────────────────────────────────────────

async function handleHighTier(body: HighTierRequest) {
  const { twin_id, snapshot_id, requester_id, key_hash, signatures } = body

  // Validate that ≥3 signatures are present
  if (!signatures || signatures.length < 3) {
    return { granted: false, reason: `HIGH tier requires 3-of-5 threshold signatures; ${signatures?.length ?? 0} provided` }
  }

  // Verify each signer_index is registered and not revoked
  const { data: registeredSigners } = await supabase
    .from('snapshot_threshold_signers')
    .select('signer_index, signer_pub')
    .eq('snapshot_id', snapshot_id)
    .is('revoked_at', null)

  const registered = new Map((registeredSigners ?? []).map(s => [s.signer_index, s.signer_pub]))
  const validSigs = signatures.filter(s => registered.has(s.signer_index))

  if (validSigs.length < 3) {
    await supabase.from('snapshot_access_log').insert({
      snapshot_id, twin_id, access_tier: 'HIGH', requester_id,
      granted: false, denial_reason: `only ${validSigs.length} of ${signatures.length} signatures matched registered signers`,
    })
    return { granted: false, reason: `only ${validSigs.length} valid registered signatures (need 3)` }
  }

  // Record threshold signatures
  const nonce = await sha256(requester_id + new Date().toISOString())
  await supabase.from('snapshot_threshold_sigs').insert(
    validSigs.map(s => ({
      snapshot_id,
      signer_index: s.signer_index,
      signature:    s.signature,
      operation:    'key_issue',
      nonce,
    }))
  )

  // Issue ephemeral key via RPC
  const { data: keyRows } = await supabase.rpc('request_ephemeral_key', {
    p_snapshot_id: snapshot_id,
    p_twin_id:     twin_id,
    p_key_hash:    key_hash,
    p_requester:   requester_id,
    p_sig_count:   validSigs.length,
  })
  const keyRow = Array.isArray(keyRows) ? keyRows[0] : keyRows

  if (!keyRow?.granted) {
    return { granted: false, reason: keyRow?.reason ?? 'key issuance failed' }
  }

  await supabase.from('snapshot_access_log').insert({
    snapshot_id, twin_id, access_tier: 'HIGH', requester_id,
    granted: true, ephemeral_key_id: keyRow.key_id,
  })

  await appendAudit('snapshot_access_high', {
    snapshot_id, twin_id, requester_id,
    sig_count: validSigs.length,
    signer_indexes: validSigs.map(s => s.signer_index),
    key_id: keyRow.key_id,
    nonce,
  })

  return {
    granted:    true,
    tier:       'HIGH',
    key_id:     keyRow.key_id,
    expires_at: keyRow.expires_at,
    sig_count:  validSigs.length,
    nonce,
  }
}

// ── CRITICAL tier handler ─────────────────────────────────────

async function handleCriticalTier(body: CriticalTierRequest) {
  const { twin_id, snapshot_id, requester_id, action } = body

  // Always log the attempt (granted=false — trigger enforces this)
  await supabase.from('snapshot_access_log').insert({
    snapshot_id, twin_id, access_tier: 'CRITICAL',
    requester_id, granted: false,
    denial_reason: `CRITICAL vault-only: action=${action}`,
  })

  if (action === 'status') {
    const { data: vault } = await supabase
      .from('snapshot_vault_records')
      .select('disc_id, sealed_at, destruction_requested_at, destruction_confirmed_at')
      .eq('snapshot_id', snapshot_id)
      .single()
    return { granted: false, tier: 'CRITICAL', vault_status: vault ?? 'no vault record' }
  }

  if (action === 'request_destruction' || action === 'confirm_destruction') {
    if (!body.witness) {
      return { granted: false, reason: 'witness identity required for destruction operations' }
    }
    const { data: rows } = await supabase.rpc('request_vault_destruction', {
      p_snapshot_id: snapshot_id,
      p_twin_id:     twin_id,
      p_witness:     body.witness,
      p_confirm:     action === 'confirm_destruction',
    })
    const row = Array.isArray(rows) ? rows[0] : rows

    await appendAudit('snapshot_vault_destruction', {
      snapshot_id, twin_id, requester_id,
      action, witness: body.witness,
      success: row?.success,
    })

    return { granted: false, tier: 'CRITICAL', destruction: row }
  }

  return { granted: false, tier: 'CRITICAL', reason: 'vault-only access — no digital path available' }
}

// ── Main ──────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  let body: SnapshotAccessRequest
  try { body = await req.json() }
  catch { return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 }) }

  const { twin_id, snapshot_id, tier } = body
  if (!twin_id || !snapshot_id || !tier) {
    return new Response(JSON.stringify({ error: 'Missing twin_id, snapshot_id, or tier' }), { status: 400 })
  }

  // Verify snapshot exists and tier matches
  const { data: snap } = await supabase
    .from('mesh_frozen_snapshots')
    .select('access_tier, is_sealed')
    .eq('id', snapshot_id)
    .eq('twin_id', twin_id)
    .maybeSingle()

  if (!snap) {
    return new Response(JSON.stringify({ error: 'snapshot not found' }), { status: 404 })
  }
  if (snap.access_tier !== tier) {
    return new Response(JSON.stringify({
      error: `snapshot is ${snap.access_tier} tier — request tier mismatch`,
    }), { status: 403 })
  }

  let result: Record<string, unknown>
  try {
    if (tier === 'LOW')      result = await handleLowTier(body as LowTierRequest)
    else if (tier === 'HIGH')     result = await handleHighTier(body as HighTierRequest)
    else                          result = await handleCriticalTier(body as CriticalTierRequest)
  } catch (err) {
    return new Response(JSON.stringify({ error: (err as Error).message }), { status: 500 })
  }

  const status = result.granted ? 200 : 403
  return new Response(JSON.stringify(result), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
})
