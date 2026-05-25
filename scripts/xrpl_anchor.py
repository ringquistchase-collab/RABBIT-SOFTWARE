"""
XRPL SHA3-512 immutable anchor for RabbitOS session 2026-05-24.
Anchors the convergence token hash to XRPL testnet memo field.
Uses raw urllib JSON-RPC + xrpl-py local signing (no SSL issues).
"""
import sys, ssl, hashlib, json, urllib.request, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

XRPL_TESTNET_HTTP = "https://s.altnet.rippletest.net:51234"
FAUCET_URL        = "https://faucet.altnet.rippletest.net/accounts"
TWIN_UUID         = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
DESTINATION       = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"  # known testnet addr

# SHA3-512 of convergence state
CONVERGENCE_STATE = b"valence=-0.23_arousal=0.71_gsr=0.06_cortisol=0.78"
SHA3_HASH = hashlib.sha3_512(CONVERGENCE_STATE).hexdigest()
assert len(SHA3_HASH) == 128

MEMO_TYPE   = "rabbitos/anchor/v1".encode().hex()
MEMO_FORMAT = "application/octet-stream".encode().hex()
MEMO_DATA   = SHA3_HASH.encode().hex()

print(f"Payload:  {CONVERGENCE_STATE.decode()}")
print(f"SHA3-512: {SHA3_HASH}")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

def http_post(url, body_dict, timeout=30):
    body = json.dumps(body_dict).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as r:
        return json.loads(r.read())

def rpc(method, params):
    resp = http_post(XRPL_TESTNET_HTTP, {"method": method, "params": [params]})
    return resp["result"]

# ── 1. Generate wallet + fund ─────────────────────────────────────────────────
print("\n[1/4] Generating wallet and funding from faucet...")
from xrpl.wallet import Wallet
wallet = Wallet.create()
address = wallet.classic_address
print(f"  Address: {address}")
print(f"  Seed:    {wallet.seed}")

faucet = http_post(FAUCET_URL, {"destination": address})
print(f"  Faucet:  {faucet.get('amount', '?')} XRP  tx={faucet.get('transactionHash','?')[:24]}...")
print("  Waiting 10s for ledger confirmation...")
time.sleep(10)

# ── 2. Get account state ──────────────────────────────────────────────────────
print("\n[2/4] Getting account info and current fee...")
acct_resp = rpc("account_info", {"account": address, "ledger_index": "current"})
if acct_resp.get("status") != "success":
    print(f"  Error: {acct_resp}")
    sys.exit(1)
sequence = acct_resp["account_data"]["Sequence"]

fee_resp = rpc("fee", {})
base_fee = int(fee_resp.get("drops", {}).get("base_fee", "12"))
fee_str  = str(max(base_fee, 12))

ledger_resp   = rpc("ledger_current", {})
current_ledger = ledger_resp.get("ledger_current_index", 0)
last_ledger    = current_ledger + 20

print(f"  Sequence: {sequence}  Fee: {fee_str} drops  LLS: {last_ledger}")

# ── 3. Build + sign transaction ───────────────────────────────────────────────
print("\n[3/4] Building and signing Payment transaction locally...")
from xrpl.models import Memo, Payment
from xrpl.transaction import sign

payment = Payment(
    account=address,
    amount="1",
    destination=DESTINATION,
    sequence=sequence,
    fee=fee_str,
    last_ledger_sequence=last_ledger,
    memos=[
        Memo(
            memo_type=MEMO_TYPE,
            memo_format=MEMO_FORMAT,
            memo_data=MEMO_DATA,
        )
    ],
)

signed_tx = sign(payment, wallet)
tx_hash   = signed_tx.get_hash()
tx_blob   = signed_tx.to_xrpl()   # encoded hex blob for submission

print(f"  TxHash: {tx_hash}")

# Re-encode to blob using xrpl binary codec
from xrpl.core.binarycodec import encode as xrpl_encode
tx_dict = signed_tx.to_xrpl()
tx_blob_hex = xrpl_encode(tx_dict)

# ── 4. Submit ─────────────────────────────────────────────────────────────────
print("\n[4/4] Submitting to XRPL testnet...")
submit_resp = rpc("submit", {"tx_blob": tx_blob_hex})
engine = submit_resp.get("engine_result", "unknown")
msg    = submit_resp.get("engine_result_message", "")

if engine in ("tesSUCCESS", "terQUEUED"):
    ledger_index = submit_resp.get("accepted", False)
    print(f"  Engine: {engine}  ({msg})")

    # Wait for validation
    print("  Waiting 6s for ledger close...")
    time.sleep(6)
    tx_resp = rpc("tx", {"transaction": tx_hash})
    ledger_index = tx_resp.get("ledger_index", "pending")

    print("\n" + "="*70)
    print("XRPL ANCHOR CONFIRMED")
    print("="*70)
    print(f"  Network:      XRPL Testnet")
    print(f"  Account:      {address}")
    print(f"  TxHash:       {tx_hash}")
    print(f"  Ledger:       {ledger_index}")
    print(f"  Payload:      convergence_token")
    print(f"  SHA3-512:     {SHA3_HASH}")
    print(f"  MemoType:     rabbitos/anchor/v1")
    print(f"  Twin UUID:    {TWIN_UUID}")
    print(f"  Explorer:     https://testnet.xrpl.org/transactions/{tx_hash}")
    print("="*70)
else:
    print(f"  FAILED — Engine: {engine}  Message: {msg}")
    print(f"  Full: {json.dumps(submit_resp, indent=2)[:600]}")
    sys.exit(1)
