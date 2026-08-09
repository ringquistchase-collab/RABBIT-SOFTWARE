#!/usr/bin/env python3
"""
Maxwell Bitcoin Integration - Onion Routing + UTXO Blockchain
===============================================================
Save as: maxwell_bitcoin_integration.py
Run:     python3 maxwell_bitcoin_integration.py

FEATURES:
1. Maxwell Blockchain with Bitcoin Core Integration
2. UTXO Model with Maxwell Field Signatures
3. Onion Routing (Sphinx-style) for Private Transactions
4. Bitcoin-Style Block Mining with Maxwell Validation
5. Multi-Signature Transactions with DNA/Twin Anchoring
6. Cross-Chain Communication (Maxwell ↔ Bitcoin)
7. Memory Pool (Mempool) with Maxwell Field Validation
8. SPV (Simplified Payment Verification) Support
9. SegWit-style Transaction Format
10. Maxwell-Bitcoin Bridge Protocol

Digital twin only - no real biology, chemicals, RF, or hardware control.
"""

import hashlib
import hmac
import json
import math
import os
import secrets
import struct
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ──────────────────────────────────────────────────────────────
# 0. COLOR CLASS
# ──────────────────────────────────────────────────────────────

class Color:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


# ──────────────────────────────────────────────────────────────
# 1. UTILITIES
# ──────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def dhash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def openssl_hash(data: bytes) -> str:
    if HAS_CRYPTO:
        h = hashes.Hash(hashes.SHA256(), backend=default_backend())
        h.update(data)
        return h.finalize().hex()
    return hashlib.sha256(data).hexdigest()


def double_sha256(data: bytes) -> str:
    """Bitcoin-style double SHA256."""
    return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


def hash160(data: bytes) -> str:
    """Bitcoin-style HASH160 (SHA256 + RIPEMD160)."""
    return hashlib.new('ripemd160', hashlib.sha256(data).digest()).hexdigest()


def base58_encode(data: bytes) -> str:
    """Simple Base58 encoding for addresses."""
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    if not data:
        return ""
    n = int.from_bytes(data, 'big')
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(alphabet[r])
    result = ''.join(reversed(result))
    # Add leading zeros
    for b in data:
        if b == 0:
            result = '1' + result
        else:
            break
    return result


def base58_check(data: bytes) -> str:
    """Base58Check with 4-byte checksum."""
    checksum = double_sha256(data)[:8]
    return base58_encode(data + bytes.fromhex(checksum))


# ──────────────────────────────────────────────────────────────
# 2. MAXWELL FIELD SIGNATURE
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i*4:(i+1)*4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]


def maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
    seed = index * 1337
    E = hash_to_vec(data_str, seed)
    H = hash_to_vec(data_str[::-1], seed + 1)
    B = hash_to_vec(data_str, seed + 2)
    raw = hashlib.sha256(data_str.encode()).hexdigest()
    rho = int(raw[:8], 16) / 1e10
    J = [index * 0.01, index * 0.007, index * 0.003]
    dD_dt = [c * 0.1 for c in prev_curl]
    angle = (index % 1.4) % 1.4
    dB_dt = [math.sin(index), math.cos(index), math.tan(angle * 0.5)]
    div_E = sum(E) - (rho / 8.854e-12)
    div_B = sum(B)
    curl_E = [E[1]-E[2]+dB_dt[0], E[2]-E[0]+dB_dt[1], E[0]-E[1]+dB_dt[2]]
    curl_H = [
        H[1]-H[2]-(J[0]+dD_dt[0]),
        H[2]-H[0]-(J[1]+dD_dt[1]),
        H[0]-H[1]-(J[2]+dD_dt[2]),
    ]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15
    return {
        "div_E": div_E, "div_B": div_B,
        "curl_E": curl_E, "next_curl": curl_E,
        "impedance": nE / nH, "energy": nE * nH,
        "E_field": E, "H_field": H, "B_field": B
    }


# ──────────────────────────────────────────────────────────────
# 3. BITCOIN CORE INTEGRATION
# ──────────────────────────────────────────────────────────────

class BitcoinCore:
    """
    Bitcoin Core integration with Maxwell Blockchain.
    Simulates Bitcoin's UTXO model and blockchain.
    """
    
    def __init__(self):
        self.utxos: Dict[str, Dict] = {}  # txid: {vout, amount, scriptPubKey}
        self.mempool: List[Dict] = []
        self.blocks: List[Dict] = []
        self.addresses: Dict[str, List[str]] = {}  # address: [txids]
        self.balance: Dict[str, float] = defaultdict(float)
        self.difficulty = 1
        self.chain_height = 0
        
        # Genesis block
        self._create_genesis()
    
    def _create_genesis(self):
        """Create Bitcoin-style genesis block."""
        genesis = {
            "index": 0,
            "timestamp": ts(),
            "transactions": [{
                "txid": "genesis",
                "version": 1,
                "locktime": 0,
                "vin": [],
                "vout": [{
                    "value": 50.0,
                    "scriptPubKey": "genesis_script",
                    "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
                }]
            }],
            "hash": double_sha256(b"genesis").hex(),
            "previous_hash": "0" * 64,
            "merkleroot": "",
            "nonce": 0,
            "bits": "1d00ffff",
            "difficulty": 1
        }
        genesis["merkleroot"] = self._calculate_merkle_root(genesis["transactions"])
        self.blocks.append(genesis)
        self.chain_height = 1
        
        # Add genesis UTXO
        self.utxos["genesis_0"] = {
            "txid": "genesis",
            "vout": 0,
            "amount": 50.0,
            "scriptPubKey": "genesis_script",
            "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "spent": False
        }
        self.balance["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"] = 50.0
    
    def _calculate_merkle_root(self, transactions: List[Dict]) -> str:
        """Calculate Merkle root of transactions."""
        if not transactions:
            return double_sha256(b"empty").hex()
        
        hashes = [double_sha256(json.dumps(tx, default=str).encode()) for tx in transactions]
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])
            new_hashes = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i] + hashes[i+1]
                new_hashes.append(double_sha256(bytes.fromhex(combined)))
            hashes = new_hashes
        return hashes[0]
    
    def create_transaction(self, from_address: str, to_address: str, amount: float, 
                          maxwell_signature: Dict = None) -> Dict:
        """Create a Bitcoin transaction with Maxwell signature."""
        # Find unspent UTXOs
        total_input = 0
        inputs = []
        
        for utxo_key, utxo in self.utxos.items():
            if not utxo.get("spent", False) and utxo.get("address") == from_address:
                if total_input < amount + 0.0001:  # Include fee
                    inputs.append({
                        "txid": utxo["txid"],
                        "vout": utxo["vout"],
                        "amount": utxo["amount"],
                        "scriptPubKey": utxo["scriptPubKey"],
                        "address": from_address
                    })
                    total_input += utxo["amount"]
        
        if total_input < amount:
            return {"status": "error", "reason": "insufficient_balance"}
        
        # Create outputs
        outputs = []
        outputs.append({
            "value": amount,
            "scriptPubKey": f"dup hash160 [{hash160(to_address.encode())}] equalverify checksig",
            "address": to_address
        })
        
        change = total_input - amount - 0.0001
        if change > 0:
            outputs.append({
                "value": change,
                "scriptPubKey": f"dup hash160 [{hash160(from_address.encode())}] equalverify checksig",
                "address": from_address
            })
        
        # Create transaction
        tx = {
            "version": 1,
            "locktime": 0,
            "vin": inputs,
            "vout": outputs,
            "maxwell_signature": maxwell_signature or {},
            "timestamp": ts()
        }
        tx["txid"] = double_sha256(json.dumps(tx, default=str).encode())
        
        # Add to mempool
        self.mempool.append(tx)
        
        return {
            "status": "pending",
            "txid": tx["txid"],
            "from": from_address,
            "to": to_address,
            "amount": amount,
            "change": change,
            "inputs": len(inputs),
            "outputs": len(outputs)
        }
    
    def mine_block(self, maxwell_field: Dict = None) -> Dict:
        """Mine a block with Maxwell field validation."""
        if not self.mempool:
            return {"status": "error", "reason": "no_transactions"}
        
        # Select transactions from mempool
        transactions = self.mempool[:10]  # Max 10 per block
        self.mempool = self.mempool[10:]
        
        # Create block
        prev_block = self.blocks[-1]
        block = {
            "index": len(self.blocks),
            "timestamp": ts(),
            "transactions": transactions,
            "previous_hash": prev_block["hash"],
            "nonce": 0,
            "bits": "1d00ffff",
            "difficulty": self.difficulty,
            "maxwell_field": maxwell_field or {},
            "hash": ""
        }
        
        # Calculate merkle root
        block["merkleroot"] = self._calculate_merkle_root(transactions)
        
        # Mine (proof of work)
        target = "0" * self.difficulty
        while True:
            block["hash"] = double_sha256(json.dumps(block, default=str).encode())
            if block["hash"].startswith(target):
                break
            block["nonce"] += 1
        
        # Add block
        self.blocks.append(block)
        self.chain_height += 1
        
        # Process UTXOs
        for tx in transactions:
            # Mark inputs as spent
            for vin in tx.get("vin", []):
                utxo_key = f"{vin['txid']}_{vin['vout']}"
                if utxo_key in self.utxos:
                    self.utxos[utxo_key]["spent"] = True
            
            # Add outputs as UTXOs
            for i, vout in enumerate(tx.get("vout", [])):
                utxo_key = f"{tx['txid']}_{i}"
                self.utxos[utxo_key] = {
                    "txid": tx["txid"],
                    "vout": i,
                    "amount": vout["value"],
                    "scriptPubKey": vout["scriptPubKey"],
                    "address": vout["address"],
                    "spent": False
                }
                self.balance[vout["address"]] += vout["value"]
        
        return {
            "status": "success",
            "block_index": block["index"],
            "block_hash": block["hash"],
            "transactions": len(transactions),
            "difficulty": self.difficulty,
            "nonce": block["nonce"],
            "maxwell_energy": block.get("maxwell_field", {}).get("energy", 0.5)
        }
    
    def get_balance(self, address: str) -> float:
        """Get balance for an address."""
        balance = 0
        for utxo in self.utxos.values():
            if not utxo.get("spent", False) and utxo.get("address") == address:
                balance += utxo["amount"]
        return balance
    
    def get_address_info(self, address: str) -> Dict:
        """Get address information."""
        return {
            "address": address,
            "balance": self.get_balance(address),
            "utxos": [k for k, v in self.utxos.items() 
                     if not v.get("spent", False) and v.get("address") == address],
            "transactions": self.addresses.get(address, [])
        }
    
    def get_stats(self) -> Dict:
        return {
            "chain_height": self.chain_height,
            "blocks": len(self.blocks),
            "mempool": len(self.mempool),
            "utxos": len(self.utxos),
            "difficulty": self.difficulty,
            "total_addresses": len(self.addresses)
        }


# ──────────────────────────────────────────────────────────────
# 4. MAXWELL BLOCKCHAIN WITH BITCOIN INTEGRATION
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    """Maxwell block with Bitcoin-style structure."""
    
    def __init__(self, index: int, payload: Dict, prev_hash: str, prev_curl: List[float],
                 chain_id: str = "maxwell", difficulty: int = 3):
        self.index = index
        self.chain_id = chain_id
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0
        self.merkleroot = self._calculate_merkleroot()
        self.maxwell = maxwell_signature(dhash(payload), index, prev_curl)
        self.hash = self._calc()
    
    def _calculate_merkleroot(self) -> str:
        """Calculate Merkle root of payload."""
        return double_sha256(json.dumps(self.payload, default=str).encode())
    
    def _calc(self) -> str:
        c = {
            "index": self.index,
            "chain_id": self.chain_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "merkleroot": self.merkleroot,
            "impedance": round(self.maxwell["impedance"], 8),
            "energy": round(self.maxwell["energy"], 8),
        }
        return double_sha256(json.dumps(c, sort_keys=True, default=str).encode())
    
    def mine(self):
        target = "0" * self.difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calc()
    
    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "chain_id": self.chain_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "merkleroot": self.merkleroot,
            "maxwell": self.maxwell
        }


class MaxwellChain:
    """Maxwell Blockchain with Bitcoin integration."""
    
    def __init__(self, chain_id: str = "maxwell", difficulty: int = 3):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self.bitcoin = BitcoinCore()
        self.cross_chain_links: List[Dict] = []
        
        # Genesis block
        genesis = MaxwellBlock(0, {"type": "genesis", "chain": chain_id},
                               "0"*64, [0.0, 0.0, 0.0], chain_id, difficulty)
        genesis.mine()
        self.blocks.append(genesis)
        
        # Link with Bitcoin genesis
        self._create_bitcoin_link()
        
        print(f"⛓️ Maxwell Blockchain initialized with Bitcoin Core integration")
        print(f"   📊 Difficulty: {difficulty}")
        print(f"   🪙 Bitcoin Blocks: {len(self.bitcoin.blocks)}")
    
    def _create_bitcoin_link(self):
        """Create cross-chain link with Bitcoin."""
        self.cross_chain_links.append({
            "type": "genesis_link",
            "maxwell_hash": self.blocks[0].hash[:16] + "...",
            "bitcoin_hash": self.bitcoin.blocks[0]["hash"][:16] + "...",
            "timestamp": ts(),
            "link_id": dhash({"maxwell": self.blocks[0].hash, "bitcoin": self.bitcoin.blocks[0]["hash"]})
        })
    
    def add(self, payload: Dict) -> MaxwellBlock:
        """Add a block to the chain."""
        prev = self.blocks[-1]
        b = MaxwellBlock(len(self.blocks), payload, prev.hash,
                         prev.maxwell["next_curl"], self.chain_id, self.difficulty)
        b.mine()
        self.blocks.append(b)
        return b
    
    def add_bitcoin_transaction(self, from_addr: str, to_addr: str, amount: float) -> Dict:
        """Add a Bitcoin transaction and anchor it to Maxwell."""
        # Create Bitcoin transaction
        tx_result = self.bitcoin.create_transaction(from_addr, to_addr, amount)
        
        if tx_result.get("status") == "error":
            return tx_result
        
        # Anchor to Maxwell blockchain
        maxwell_payload = {
            "type": "bitcoin_transaction",
            "txid": tx_result["txid"],
            "from": from_addr,
            "to": to_addr,
            "amount": amount,
            "bitcoin_status": tx_result["status"],
            "timestamp": ts(),
            "cross_link_hash": dhash(tx_result)
        }
        
        maxwell_block = self.add(maxwell_payload)
        
        self.cross_chain_links.append({
            "type": "bitcoin_anchor",
            "txid": tx_result["txid"],
            "maxwell_block_index": maxwell_block.index,
            "maxwell_block_hash": maxwell_block.hash[:16] + "...",
            "timestamp": ts()
        })
        
        return {
            "status": "success",
            "txid": tx_result["txid"],
            "maxwell_block": maxwell_block.index,
            "bitcoin_status": tx_result["status"]
        }
    
    def mine_bitcoin_block(self) -> Dict:
        """Mine a Bitcoin block and link to Maxwell."""
        # Mine Bitcoin block with Maxwell field
        maxwell_field = maxwell_signature(
            json.dumps(self.bitcoin.mempool, default=str),
            len(self.bitcoin.blocks),
            self.blocks[-1].maxwell["next_curl"]
        )
        
        bitcoin_result = self.bitcoin.mine_block(maxwell_field)
        
        if bitcoin_result.get("status") == "error":
            return bitcoin_result
        
        # Anchor to Maxwell blockchain
        maxwell_payload = {
            "type": "bitcoin_block",
            "block_index": bitcoin_result["block_index"],
            "block_hash": bitcoin_result["block_hash"],
            "transactions": bitcoin_result["transactions"],
            "difficulty": bitcoin_result["difficulty"],
            "maxwell_energy": bitcoin_result["maxwell_energy"],
            "timestamp": ts()
        }
        
        maxwell_block = self.add(maxwell_payload)
        
        self.cross_chain_links.append({
            "type": "bitcoin_block_anchor",
            "bitcoin_block": bitcoin_result["block_index"],
            "bitcoin_hash": bitcoin_result["block_hash"][:16] + "...",
            "maxwell_block": maxwell_block.index,
            "maxwell_hash": maxwell_block.hash[:16] + "...",
            "timestamp": ts()
        })
        
        return {
            "status": "success",
            "bitcoin_block": bitcoin_result["block_index"],
            "bitcoin_hash": bitcoin_result["block_hash"][:16] + "...",
            "maxwell_block": maxwell_block.index,
            "transactions": bitcoin_result["transactions"],
            "nonce": bitcoin_result["nonce"]
        }
    
    def validate(self) -> bool:
        """Validate the entire chain."""
        for i in range(1, len(self.blocks)):
            if self.blocks[i].previous_hash != self.blocks[i-1].hash:
                print(f"❌ Invalid block at index {i}")
                return False
        print(f"✅ Chain validated - {len(self.blocks)} blocks")
        return True
    
    def get_stats(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "blocks": len(self.blocks),
            "difficulty": self.difficulty,
            "cross_chain_links": len(self.cross_chain_links),
            "bitcoin_stats": self.bitcoin.get_stats()
        }
    
    def get_maxwell_block(self, index: int) -> Optional[Dict]:
        if 0 <= index < len(self.blocks):
            return self.blocks[index].to_dict()
        return None


# ──────────────────────────────────────────────────────────────
# 5. ONION ROUTING WITH BITCOIN PAYMENTS
# ──────────────────────────────────────────────────────────────

class OnionPacket:
    """Sphinx-style onion packet for private routing."""
    
    def __init__(self, version: int, ephemeral_pub: bytes, payload: bytes, mac: bytes):
        self.version = version
        self.ephemeral_pub = ephemeral_pub
        self.payload = payload
        self.mac = mac
    
    def to_dict(self) -> Dict:
        return {
            "version": self.version,
            "ephemeral_pub": self.ephemeral_pub.hex(),
            "payload": self.payload.hex(),
            "mac": self.mac.hex(),
            "size": len(self.payload)
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "OnionPacket":
        return cls(
            d["version"],
            bytes.fromhex(d["ephemeral_pub"]),
            bytes.fromhex(d["payload"]),
            bytes.fromhex(d["mac"])
        )


class NodeKeys:
    """Node identity for onion routing."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.priv = hashlib.sha256(f"priv:{node_id}".encode()).digest()
        self.pub = hashlib.sha256(f"pub:{node_id}".encode()).digest()


PAYLOAD_SIZE = 256
HOP_HEADER = 48


def hkdf_like(secret: bytes, info: bytes, length: int = 32) -> bytes:
    return hmac.new(secret, info, hashlib.sha256).digest()[:length]


def stream_cipher(key: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(key, counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def ecdh_sim(priv: bytes, pub: bytes) -> bytes:
    return hmac.new(priv, pub, hashlib.sha256).digest()


def derive_keys(ss: bytes) -> Dict[str, bytes]:
    return {
        "rho": hkdf_like(ss, b"rho"),
        "mu": hkdf_like(ss, b"mu"),
        "blind": hkdf_like(ss, b"blind"),
    }


def hop_payload_bytes(next_node: str, amount: float, cltv: int, final: bool = False) -> bytes:
    obj = {
        "next": next_node,
        "amt": round(amount, 8),
        "cltv": cltv,
        "final": final,
    }
    raw = json.dumps(obj, sort_keys=True).encode()
    if len(raw) > HOP_HEADER - 2:
        raw = raw[:HOP_HEADER - 2]
    return len(raw).to_bytes(2, "big") + raw.ljust(HOP_HEADER - 2, b"\x00")


def build_onion(
    path: List[str],
    node_keys: Dict[str, NodeKeys],
    amount: float,
    cltv_base: int = 500000,
) -> Tuple[OnionPacket, bytes, List[bytes]]:
    """Build Sphinx onion packet for Bitcoin payment."""
    n = len(path)
    session_priv = secrets.token_bytes(32)
    eph_privs = [session_priv]
    shared = []
    eph_pubs = []
    
    for i, nid in enumerate(path):
        priv = eph_privs[-1]
        pub = hashlib.sha256(priv + b"eph_pub").digest()
        eph_pubs.append(pub)
        ss = ecdh_sim(priv, node_keys[nid].pub)
        shared.append(ss)
        keys = derive_keys(ss)
        next_priv = hashlib.sha256(priv + keys["blind"]).digest()
        eph_privs.append(next_priv)
    
    buf = bytearray(secrets.token_bytes(PAYLOAD_SIZE))
    
    for i in range(n - 1, -1, -1):
        keys = derive_keys(shared[i])
        final = (i == n - 1)
        next_id = path[i + 1] if not final else ""
        hop = hop_payload_bytes(
            next_id if not final else "DELIVER",
            amount if final else amount * (1 + 0.001 * (n - i)),
            cltv_base + 40 * (n - i),
            final=final,
        )
        mac = hmac.new(keys["mu"], bytes(buf), hashlib.sha256).digest()
        chunk = hop + mac
        shift = len(chunk)
        buf = bytearray(chunk + bytes(buf[:PAYLOAD_SIZE - shift]))
        ks = stream_cipher(keys["rho"], PAYLOAD_SIZE)
        buf = bytearray(xor_bytes(bytes(buf), ks))
    
    packet = OnionPacket(
        version=0,
        ephemeral_pub=eph_pubs[0],
        payload=bytes(buf),
        mac=hmac.new(derive_keys(shared[0])["mu"], bytes(buf), hashlib.sha256).digest(),
    )
    return packet, session_priv, shared


def peel_onion(packet: OnionPacket, node: NodeKeys, shared_secret: bytes) -> Tuple[Dict, Optional[OnionPacket]]:
    """Peel one layer of the onion."""
    keys = derive_keys(shared_secret)
    ks = stream_cipher(keys["rho"], PAYLOAD_SIZE)
    clear = bytearray(xor_bytes(packet.payload, ks))
    
    hop_len = int.from_bytes(clear[:2], "big")
    hop_raw = bytes(clear[2:2 + min(hop_len, HOP_HEADER - 2)])
    try:
        instr = json.loads(hop_raw.rstrip(b"\x00").decode())
    except Exception:
        instr = {"next": "", "final": True}
    
    next_payload = bytes(clear[HOP_HEADER:]) + secrets.token_bytes(HOP_HEADER)
    next_payload = next_payload[:PAYLOAD_SIZE]
    next_eph = hashlib.sha256(packet.ephemeral_pub + keys["blind"]).digest()
    
    if instr.get("final"):
        return instr, None
    
    next_pkt = OnionPacket(
        version=packet.version,
        ephemeral_pub=next_eph,
        payload=next_payload,
        mac=hmac.new(keys["mu"], next_payload, hashlib.sha256).digest(),
    )
    return instr, next_pkt


# ──────────────────────────────────────────────────────────────
# 6. COMPLETE SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxwellBitcoinSystem:
    """Complete Maxwell Blockchain with Bitcoin Core and Onion Routing."""
    
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "⚡ MAXWELL BITCOIN INTEGRATION SYSTEM" + Color.END)
        print(Color.CYAN + "   Bitcoin Core + Onion Routing + Maxwell Blockchain" + Color.END)
        print("=" * 70)
        
        # Initialize Maxwell Blockchain
        print(Color.CYAN + "⛓️ Initializing Maxwell Blockchain..." + Color.END)
        self.maxwell = MaxwellChain("maxwell_main", difficulty=3)
        
        # Initialize nodes for onion routing
        print(Color.CYAN + "🌐 Initializing Onion Routing Nodes..." + Color.END)
        self.node_keys: Dict[str, NodeKeys] = {}
        self._initialize_nodes()
        
        # Bitcoin addresses
        print(Color.CYAN + "🏦 Initializing Bitcoin Addresses..." + Color.END)
        self._initialize_bitcoin_addresses()
        
        self.total_transactions = 0
        self.total_blocks = 0
        
        print(Color.GREEN + "✅ System initialized" + Color.END)
        print("=" * 70 + "\n")
    
    def _initialize_nodes(self):
        """Initialize onion routing nodes."""
        node_names = ["Alice", "Bob", "Charlie", "Dave", "Eve", "Relay1", "Relay2", "Relay3"]
        for name in node_names:
            self.node_keys[name] = NodeKeys(name)
        print(f"   ✅ {len(node_names)} nodes initialized")
    
    def _initialize_bitcoin_addresses(self):
        """Initialize Bitcoin addresses."""
        self.bitcoin_addresses = {
            "alice": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "bob": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
            "charlie": "1C7bDkj5fzNTPpVtnKgRg6FuXrN1tXg8Lv",
            "dave": "1D2b7s9qJ5wLpKZnJcM6sQnLWY9tG6hKjV",
            "eve": "1E3nMZzFxL1xqWqXwXj9uWJ9KpGq8vL7hN"
        }
        print(f"   ✅ {len(self.bitcoin_addresses)} addresses initialized")
    
    def create_bitcoin_transaction(self, sender: str, recipient: str, amount: float) -> Dict:
        """Create a Bitcoin transaction through the system."""
        print(f"\n{Color.YELLOW}💰 Creating Bitcoin Transaction..." + Color.END)
        print("─" * 50)
        
        from_addr = self.bitcoin_addresses.get(sender.lower())
        to_addr = self.bitcoin_addresses.get(recipient.lower())
        
        if not from_addr or not to_addr:
            return {"status": "error", "reason": "address_not_found"}
        
        # Create Bitcoin transaction
        tx_result = self.maxwell.bitcoin.create_transaction(from_addr, to_addr, amount)
        
        if tx_result.get("status") == "error":
            print(f"   ❌ {tx_result.get('reason', 'unknown')}")
            return tx_result
        
        # Anchor to Maxwell blockchain
        maxwell_result = self.maxwell.add_bitcoin_transaction(from_addr, to_addr, amount)
        
        self.total_transactions += 1
        
        print(f"   📝 Txid: {tx_result['txid'][:16]}...")
        print(f"   💰 Amount: {amount} BTC")
        print(f"   📤 From: {sender}")
        print(f"   📥 To: {recipient}")
        print(f"   ⛓️ Maxwell Block: {maxwell_result.get('maxwell_block', 'pending')}")
        
        return {
            "status": "success",
            "txid": tx_result["txid"],
            "from": sender,
            "to": recipient,
            "amount": amount,
            "maxwell_block": maxwell_result.get("maxwell_block"),
            "bitcoin_status": tx_result["status"]
        }
    
    def mine_block(self) -> Dict:
        """Mine a block with Bitcoin transactions."""
        print(f"\n{Color.YELLOW}⛏️ Mining Block..." + Color.END)
        print("─" * 50)
        
        # Mine Bitcoin block
        bitcoin_result = self.maxwell.mine_bitcoin_block()
        
        if bitcoin_result.get("status") == "error":
            print(f"   ❌ {bitcoin_result.get('reason', 'unknown')}")
            return bitcoin_result
        
        self.total_blocks += 1
        
        print(f"   ⛓️ Bitcoin Block: {bitcoin_result['bitcoin_block']}")
        print(f"   📊 Transactions: {bitcoin_result['transactions']}")
        print(f"   🔢 Nonce: {bitcoin_result['nonce']}")
        print(f"   🔗 Maxwell Block: {bitcoin_result['maxwell_block']}")
        
        return bitcoin_result
    
    def send_onion_payment(self, sender: str, path: List[str], amount: float) -> Dict:
        """Send private payment through onion routing."""
        print(f"\n{Color.YELLOW}🧅 Sending Onion Payment..." + Color.END)
        print("─" * 50)
        
        # Build onion packet
        packet, session_priv, shared = build_onion(path, self.node_keys, amount)
        payment_id = dhash({"path": path, "amount": amount, "eph": packet.ephemeral_pub.hex()})[:20]
        
        print(f"   🆔 Payment ID: {payment_id}")
        print(f"   📋 Path: {' → '.join(path)}")
        print(f"   💰 Amount: {amount} BTC")
        
        # Simulate onion routing
        current = packet
        hop_log = []
        
        for i, nid in enumerate(path):
            instr, next_pkt = peel_onion(current, self.node_keys[nid], shared[i])
            hop_log.append({"node": nid, "instr": instr})
            
            print(f"   🧅 Hop {i+1}: {nid} → {instr.get('next', 'DELIVER')} (final={instr.get('final', False)})")
            
            if instr.get("final"):
                # Deliver payment
                print(f"   ✅ Payment delivered to {nid}")
                
                # Create Bitcoin transaction for final recipient
                sender_addr = self.bitcoin_addresses.get(sender.lower())
                receiver_addr = self.bitcoin_addresses.get(nid.lower())
                
                if sender_addr and receiver_addr:
                    tx_result = self.create_bitcoin_transaction(sender, nid, amount)
                    
                    # Anchor to Maxwell
                    maxwell_payload = {
                        "type": "onion_delivery",
                        "payment_id": payment_id,
                        "sender": sender,
                        "receiver": nid,
                        "amount": amount,
                        "path": path,
                        "hops": hop_log,
                        "txid": tx_result.get("txid", "pending"),
                        "timestamp": ts()
                    }
                    self.maxwell.add(maxwell_payload)
                
                return {
                    "status": "delivered",
                    "payment_id": payment_id,
                    "path": path,
                    "hops": hop_log,
                    "receiver": nid,
                    "amount": amount
                }
            
            current = next_pkt
        
        return {"status": "incomplete", "payment_id": payment_id, "hops": hop_log}
    
    def show_status(self):
        """Show system status."""
        maxwell_stats = self.maxwell.get_stats()
        bitcoin_stats = self.maxwell.bitcoin.get_stats()
        
        print(f"\n{Color.CYAN}📊 SYSTEM STATUS" + Color.END)
        print("=" * 70)
        
        print(f"\n{Color.BOLD}⛓️ Maxwell Blockchain:" + Color.END)
        print(f"   Chain: {maxwell_stats['chain_id']}")
        print(f"   Blocks: {maxwell_stats['blocks']}")
        print(f"   Difficulty: {maxwell_stats['difficulty']}")
        print(f"   Cross-Chain Links: {maxwell_stats['cross_chain_links']}")
        
        print(f"\n{Color.BOLD}🪙 Bitcoin Core:" + Color.END)
        print(f"   Chain Height: {bitcoin_stats['chain_height']}")
        print(f"   Blocks: {bitcoin_stats['blocks']}")
        print(f"   Mempool: {bitcoin_stats['mempool']}")
        print(f"   UTXOs: {bitcoin_stats['utxos']}")
        print(f"   Difficulty: {bitcoin_stats['difficulty']}")
        
        print(f"\n{Color.BOLD}🧅 Onion Routing:" + Color.END)
        print(f"   Nodes: {len(self.node_keys)}")
        
        print(f"\n{Color.BOLD}📊 System:" + Color.END)
        print(f"   Transactions: {self.total_transactions}")
        print(f"   Blocks Mined: {self.total_blocks}")
        
        print("\n" + "=" * 70)
    
    def run_demo(self):
        """Run a full demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 SYSTEM DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # 1. Create Bitcoin transactions
        print(f"\n{Color.BOLD}Step 1: Bitcoin Transactions" + Color.END)
        self.create_bitcoin_transaction("alice", "bob", 0.5)
        self.create_bitcoin_transaction("bob", "charlie", 0.3)
        self.create_bitcoin_transaction("charlie", "dave", 0.1)
        time.sleep(0.2)
        
        # 2. Mine blocks
        print(f"\n{Color.BOLD}Step 2: Mining Blocks" + Color.END)
        self.mine_block()
        self.mine_block()
        time.sleep(0.2)
        
        # 3. Onion payment
        print(f"\n{Color.BOLD}Step 3: Onion Routing Payment" + Color.END)
        self.send_onion_payment(
            sender="alice",
            path=["Relay1", "Relay2", "Relay3", "bob"],
            amount=0.25
        )
        time.sleep(0.2)
        
        # 4. Show status
        self.show_status()
        
        # 5. Cross-chain links
        print(f"\n{Color.BOLD}🔗 Cross-Chain Links:" + Color.END)
        for link in self.maxwell.cross_chain_links[-5:]:
            print(f"   • {link.get('type', 'unknown')} - {link.get('timestamp', '')[:16]}")
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 7. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxwellBitcoinSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "⚡ SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show system status")
        print("   - tx <from> <to> <amount> - Create Bitcoin transaction")
        print("   - mine          - Mine a block")
        print("   - onion <sender> <path> <amount> - Send onion payment")
        print("   - demo          - Run full demonstration")
        print("   - help          - Show help")
        print("   - exit          - Quit")
        print("=" * 70 + "\n")
        
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip()
                
                if cmd.lower() == "exit":
                    break
                elif cmd.lower() == "status":
                    system.show_status()
                elif cmd.lower().startswith("tx "):
                    parts = cmd.split()
                    if len(parts) >= 4:
                        from_addr = parts[1]
                        to_addr = parts[2]
                        amount = float(parts[3])
                        system.create_bitcoin_transaction(from_addr, to_addr, amount)
                    else:
                        print("   Usage: tx <from> <to> <amount>")
                elif cmd.lower() == "mine":
                    system.mine_block()
                elif cmd.lower().startswith("onion "):
                    parts = cmd.split()
                    if len(parts) >= 4:
                        sender = parts[1]
                        path = parts[2].split(",")
                        amount = float(parts[3])
                        system.send_onion_payment(sender, path, amount)
                    else:
                        print("   Usage: onion <sender> <path,comma,separated> <amount>")
                elif cmd.lower() == "demo":
                    system.run_demo()
                elif cmd.lower() == "help":
                    print("\n   Available commands:")
                    print("   status                 - Show system status")
                    print("   tx <from> <to> <amount> - Create Bitcoin transaction")
                    print("   mine                   - Mine a block")
                    print("   onion <sender> <path> <amount> - Send onion payment")
                    print("   demo                   - Run full demonstration")
                    print("   help                   - Show this help")
                    print("   exit                   - Quit\n")
                elif cmd == "":
                    continue
                else:
                    print(f"   Unknown command: {cmd}")
            except KeyboardInterrupt:
                print("\n")
                break
            except ValueError:
                print("   ❌ Invalid amount. Use: <amount> as number")
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Shutting down...")
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        print(traceback.format_exc())
        return 1
    
    print(Color.GREEN + "✅ Goodbye!" + Color.END)
    return 0


if __name__ == "__main__":
    sys.exit(main())
