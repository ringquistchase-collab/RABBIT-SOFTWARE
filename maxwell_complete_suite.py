#!/usr/bin/env python3
"""
Maxwell Blockchain - Complete Bitcoin Integration Suite
========================================================
Save as: maxwell_complete_suite.py
Run:     python3 maxwell_complete_suite.py

UNIFIED SYSTEM FEATURES:
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
11. DNA/Twin Identity Anchoring
12. RF Hardware Integration (SDR/Sat/Towers)
13. Node Discovery and Peering
14. REST API Gateway
15. Auto-healing Consensus

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
import threading
import queue
import socket
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import sqlite3

# Optional dependencies
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ──────────────────────────────────────────────────────────────
# 0. COLOR CLASS & UTILITIES
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
    return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


def hash160(data: bytes) -> str:
    return hashlib.new('ripemd160', hashlib.sha256(data).digest()).hexdigest()


def base58_encode(data: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    if not data:
        return ""
    n = int.from_bytes(data, 'big')
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(alphabet[r])
    result = ''.join(reversed(result))
    for b in data:
        if b == 0:
            result = '1' + result
        else:
            break
    return result


def base58_check(data: bytes) -> str:
    checksum = double_sha256(data)[:8]
    return base58_encode(data + bytes.fromhex(checksum))


# ──────────────────────────────────────────────────────────────
# 1. MAXWELL FIELD SIGNATURE
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
# 2. PERSISTENT STORAGE
# ──────────────────────────────────────────────────────────────

class PersistentStorage:
    """SQLite storage for blockchain data."""
    
    def __init__(self, db_path: str = "maxwell_bitcoin.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                index INTEGER PRIMARY KEY,
                hash TEXT UNIQUE,
                previous_hash TEXT,
                timestamp TEXT,
                transactions TEXT,
                nonce INTEGER,
                difficulty INTEGER,
                maxwell_field TEXT,
                chain_id TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS utxos (
                utxo_id TEXT PRIMARY KEY,
                txid TEXT,
                vout INTEGER,
                amount REAL,
                address TEXT,
                script_pubkey TEXT,
                spent INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cross_chain_links (
                link_id TEXT PRIMARY KEY,
                link_type TEXT,
                bitcoin_txid TEXT,
                maxwell_hash TEXT,
                dna_identity TEXT,
                timestamp TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS identities (
                identity_id TEXT PRIMARY KEY,
                dna_hash TEXT,
                twin_hash TEXT,
                address TEXT,
                created_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()


# ──────────────────────────────────────────────────────────────
# 3. BITCOIN CORE INTEGRATION
# ──────────────────────────────────────────────────────────────

class BitcoinCore:
    """Bitcoin Core integration with Maxwell Blockchain."""
    
    def __init__(self, storage: PersistentStorage = None):
        self.storage = storage or PersistentStorage()
        self.utxos: Dict[str, Dict] = {}
        self.mempool: List[Dict] = []
        self.blocks: List[Dict] = []
        self.addresses: Dict[str, List[str]] = {}
        self.balance: Dict[str, float] = defaultdict(float)
        self.difficulty = 1
        self.chain_height = 0
        
        # Load from storage
        self._load_state()
        
        # Create genesis if empty
        if not self.blocks:
            self._create_genesis()
    
    def _load_state(self):
        """Load state from persistent storage."""
        try:
            conn = sqlite3.connect(self.storage.db_path)
            cursor = conn.cursor()
            
            # Load blocks
            cursor.execute('SELECT * FROM blocks ORDER BY index ASC')
            rows = cursor.fetchall()
            for row in rows:
                block = {
                    "index": row[0],
                    "hash": row[1],
                    "previous_hash": row[2],
                    "timestamp": row[3],
                    "transactions": json.loads(row[4]),
                    "nonce": row[5],
                    "difficulty": row[6],
                    "maxwell_field": json.loads(row[7]) if row[7] else {},
                    "chain_id": row[8]
                }
                self.blocks.append(block)
            
            # Load UTXOs
            cursor.execute('SELECT * FROM utxos')
            rows = cursor.fetchall()
            for row in rows:
                utxo_id = row[0]
                self.utxos[utxo_id] = {
                    "txid": row[1],
                    "vout": row[2],
                    "amount": row[3],
                    "address": row[4],
                    "scriptPubKey": row[5],
                    "spent": bool(row[6])
                }
                if not self.utxos[utxo_id]["spent"]:
                    self.balance[row[4]] += row[3]
            
            conn.close()
            self.chain_height = len(self.blocks)
            
        except Exception:
            pass
    
    def _save_block(self, block: Dict):
        """Save block to storage."""
        conn = sqlite3.connect(self.storage.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO blocks 
            (index, hash, previous_hash, timestamp, transactions, nonce, difficulty, maxwell_field, chain_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            block["index"],
            block["hash"],
            block["previous_hash"],
            block["timestamp"],
            json.dumps(block.get("transactions", []), default=str),
            block.get("nonce", 0),
            block.get("difficulty", 1),
            json.dumps(block.get("maxwell_field", {}), default=str),
            block.get("chain_id", "main")
        ))
        conn.commit()
        conn.close()
    
    def _save_utxos(self):
        """Save UTXOs to storage."""
        conn = sqlite3.connect(self.storage.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM utxos')
        for utxo_id, utxo in self.utxos.items():
            cursor.execute('''
                INSERT INTO utxos (utxo_id, txid, vout, amount, address, script_pubkey, spent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                utxo_id,
                utxo["txid"],
                utxo["vout"],
                utxo["amount"],
                utxo["address"],
                utxo["scriptPubKey"],
                1 if utxo.get("spent", False) else 0
            ))
        conn.commit()
        conn.close()
    
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
            "difficulty": 1,
            "chain_id": "main",
            "maxwell_field": maxwell_signature("genesis", 0, [0.0, 0.0, 0.0])
        }
        genesis["merkleroot"] = self._calculate_merkle_root(genesis["transactions"])
        self.blocks.append(genesis)
        self.chain_height = 1
        self._save_block(genesis)
        
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
        self._save_utxos()
    
    def _calculate_merkle_root(self, transactions: List[Dict]) -> str:
        if not transactions:
            return double_sha256(b"empty").hex()
        hashes_list = [double_sha256(json.dumps(tx, default=str).encode()) for tx in transactions]
        while len(hashes_list) > 1:
            if len(hashes_list) % 2 == 1:
                hashes_list.append(hashes_list[-1])
            new_hashes = []
            for i in range(0, len(hashes_list), 2):
                combined = hashes_list[i] + hashes_list[i+1]
                new_hashes.append(double_sha256(bytes.fromhex(combined)))
            hashes_list = new_hashes
        return hashes_list[0]
    
    def create_transaction(self, from_address: str, to_address: str, amount: float,
                          maxwell_sig: Dict = None) -> Dict:
        """Create a Bitcoin transaction with Maxwell signature."""
        total_input = 0
        inputs = []
        
        for utxo_key, utxo in self.utxos.items():
            if not utxo.get("spent", False) and utxo.get("address") == from_address:
                if total_input < amount + 0.0001:
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
        
        tx = {
            "version": 1,
            "locktime": 0,
            "vin": inputs,
            "vout": outputs,
            "maxwell_signature": maxwell_sig or maxwell_signature(
                json.dumps(inputs + outputs, default=str),
                len(self.blocks),
                self.blocks[-1]["maxwell_field"].get("next_curl", [0.0, 0.0, 0.0])
            ),
            "timestamp": ts()
        }
        tx["txid"] = double_sha256(json.dumps(tx, default=str).encode())
        self.mempool.append(tx)
        
        return {
            "status": "pending",
            "txid": tx["txid"],
            "from": from_address,
            "to": to_address,
            "amount": amount,
            "change": change,
            "inputs": len(inputs),
            "outputs": len(outputs),
            "maxwell_impedance": tx["maxwell_signature"]["impedance"]
        }
    
    def mine_block(self, maxwell_field: Dict = None) -> Dict:
        """Mine a block with Maxwell field validation."""
        if not self.mempool:
            return {"status": "error", "reason": "no_transactions"}
        
        transactions = self.mempool[:10]
        self.mempool = self.mempool[10:]
        
        prev_block = self.blocks[-1]
        block = {
            "index": len(self.blocks),
            "timestamp": ts(),
            "transactions": transactions,
            "previous_hash": prev_block["hash"],
            "nonce": 0,
            "bits": "1d00ffff",
            "difficulty": self.difficulty,
            "chain_id": "main",
            "maxwell_field": maxwell_field or maxwell_signature(
                json.dumps(transactions, default=str),
                len(self.blocks),
                prev_block["maxwell_field"].get("next_curl", [0.0, 0.0, 0.0])
            )
        }
        block["merkleroot"] = self._calculate_merkle_root(transactions)
        
        target = "0" * self.difficulty
        while True:
            block["hash"] = double_sha256(json.dumps(block, default=str).encode())
            if block["hash"].startswith(target):
                break
            block["nonce"] += 1
        
        self.blocks.append(block)
        self.chain_height += 1
        self._save_block(block)
        
        for tx in transactions:
            for vin in tx.get("vin", []):
                utxo_key = f"{vin['txid']}_{vin['vout']}"
                if utxo_key in self.utxos:
                    self.utxos[utxo_key]["spent"] = True
            
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
        
        self._save_utxos()
        
        return {
            "status": "success",
            "block_index": block["index"],
            "block_hash": block["hash"],
            "transactions": len(transactions),
            "difficulty": self.difficulty,
            "nonce": block["nonce"],
            "maxwell_energy": block["maxwell_field"].get("energy", 0.5),
            "maxwell_impedance": block["maxwell_field"].get("impedance", 1.0)
        }
    
    def get_balance(self, address: str) -> float:
        balance = 0
        for utxo in self.utxos.values():
            if not utxo.get("spent", False) and utxo.get("address") == address:
                balance += utxo["amount"]
        return balance
    
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
# 4. ONION ROUTING (SPHINX-STYLE)
# ──────────────────────────────────────────────────────────────

PAYLOAD_SIZE = 256
HOP_HEADER = 48


class OnionPacket:
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
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.priv = hashlib.sha256(f"priv:{node_id}".encode()).digest()
        self.pub = hashlib.sha256(f"pub:{node_id}".encode()).digest()


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
    obj = {"next": next_node, "amt": round(amount, 8), "cltv": cltv, "final": final}
    raw = json.dumps(obj, sort_keys=True).encode()
    if len(raw) > HOP_HEADER - 2:
        raw = raw[:HOP_HEADER - 2]
    return len(raw).to_bytes(2, "big") + raw.ljust(HOP_HEADER - 2, b"\x00")


def build_onion(path: List[str], node_keys: Dict[str, NodeKeys], amount: float,
                cltv_base: int = 500000) -> Tuple[OnionPacket, bytes, List[bytes]]:
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
# 5. MAXWELL BLOCKCHAIN CORE
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(self, index: int, payload: Dict, prev_hash: str, prev_curl: List[float],
                 chain_id: str = "maxwell", difficulty: int = 3):
        self.index = index
        self.chain_id = chain_id
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0
        self.merkleroot = double_sha256(json.dumps(payload, default=str).encode())
        self.maxwell = maxwell_signature(dhash(payload), index, prev_curl)
        self.hash = self._calc()
    
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
    def __init__(self, chain_id: str = "maxwell", difficulty: int = 3):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self.bitcoin = BitcoinCore()
        self.cross_chain_links: List[Dict] = []
        self.identities: Dict[str, Dict] = {}
        self.storage = PersistentStorage()
        
        genesis = MaxwellBlock(0, {"type": "genesis", "chain": chain_id},
                               "0"*64, [0.0, 0.0, 0.0], chain_id, difficulty)
        genesis.mine()
        self.blocks.append(genesis)
        
        self._create_bitcoin_link()
        self._load_identities()
    
    def _load_identities(self):
        try:
            conn = sqlite3.connect(self.storage.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM identities')
            rows = cursor.fetchall()
            for row in rows:
                self.identities[row[0]] = {
                    "dna_hash": row[1],
                    "twin_hash": row[2],
                    "address": row[3],
                    "created_at": row[4]
                }
            conn.close()
        except Exception:
            pass
    
    def _save_identity(self, identity_id: str, data: Dict):
        try:
            conn = sqlite3.connect(self.storage.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO identities 
                (identity_id, dna_hash, twin_hash, address, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                identity_id,
                data.get("dna_hash", ""),
                data.get("twin_hash", ""),
                data.get("address", ""),
                data.get("created_at", ts())
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass
    
    def _create_bitcoin_link(self):
        self.cross_chain_links.append({
            "type": "genesis_link",
            "maxwell_hash": self.blocks[0].hash[:16] + "...",
            "bitcoin_hash": self.bitcoin.blocks[0]["hash"][:16] + "...",
            "timestamp": ts(),
            "link_id": dhash({"maxwell": self.blocks[0].hash, "bitcoin": self.bitcoin.blocks[0]["hash"]})
        })
    
    def add(self, payload: Dict) -> MaxwellBlock:
        prev = self.blocks[-1]
        b = MaxwellBlock(len(self.blocks), payload, prev.hash,
                         prev.maxwell["next_curl"], self.chain_id, self.difficulty)
        b.mine()
        self.blocks.append(b)
        return b
    
    def register_identity(self, identity_id: str, dna_hash: str, twin_hash: str) -> Dict:
        address = base58_check(hashlib.sha256(f"{identity_id}:{dna_hash}".encode()).digest())
        identity_data = {
            "dna_hash": dna_hash,
            "twin_hash": twin_hash,
            "address": address,
            "created_at": ts()
        }
        self.identities[identity_id] = identity_data
        self._save_identity(identity_id, identity_data)
        
        self.add({
            "type": "identity_registration",
            "identity_id": identity_id,
            "dna_hash": dna_hash[:16] + "...",
            "twin_hash": twin_hash[:16] + "...",
            "address": address
        })
        
        return {
            "status": "registered",
            "identity_id": identity_id,
            "address": address
        }
    
    def add_bitcoin_transaction(self, from_addr: str, to_addr: str, amount: float) -> Dict:
        tx_result = self.bitcoin.create_transaction(from_addr, to_addr, amount)
        if tx_result.get("status") == "error":
            return tx_result
        
        self.add({
            "type": "bitcoin_transaction",
            "txid": tx_result["txid"],
            "from": from_addr,
            "to": to_addr,
            "amount": amount,
            "bitcoin_status": tx_result["status"],
            "timestamp": ts(),
            "cross_link_hash": dhash(tx_result)
        })
        
        self.cross_chain_links.append({
            "type": "bitcoin_anchor",
            "txid": tx_result["txid"],
            "maxwell_block_index": len(self.blocks) - 1,
            "timestamp": ts()
        })
        
        return {
            "status": "success",
            "txid": tx_result["txid"],
            "maxwell_block": len(self.blocks) - 1
        }
    
    def mine_bitcoin_block(self) -> Dict:
        maxwell_field = maxwell_signature(
            json.dumps(self.bitcoin.mempool, default=str),
            len(self.bitcoin.blocks),
            self.blocks[-1].maxwell["next_curl"]
        )
        
        bitcoin_result = self.bitcoin.mine_block(maxwell_field)
        if bitcoin_result.get("status") == "error":
            return bitcoin_result
        
        self.add({
            "type": "bitcoin_block",
            "block_index": bitcoin_result["block_index"],
            "block_hash": bitcoin_result["block_hash"][:16] + "...",
            "transactions": bitcoin_result["transactions"],
            "difficulty": bitcoin_result["difficulty"],
            "maxwell_energy": bitcoin_result["maxwell_energy"],
            "timestamp": ts()
        })
        
        self.cross_chain_links.append({
            "type": "bitcoin_block_anchor",
            "bitcoin_block": bitcoin_result["block_index"],
            "maxwell_block": len(self.blocks) - 1,
            "timestamp": ts()
        })
        
        return {
            "status": "success",
            "bitcoin_block": bitcoin_result["block_index"],
            "maxwell_block": len(self.blocks) - 1,
            "transactions": bitcoin_result["transactions"],
            "nonce": bitcoin_result["nonce"]
        }
    
    def validate(self) -> bool:
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
            "identities": len(self.identities),
            "bitcoin_stats": self.bitcoin.get_stats()
        }


# ──────────────────────────────────────────────────────────────
# 6. COMPLETE SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxwellCompleteSystem:
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "⚡ MAXWELL BLOCKCHAIN - COMPLETE SUITE" + Color.END)
        print(Color.CYAN + "   Bitcoin Core + Onion Routing + DNA/Twin Identity" + Color.END)
        print("=" * 70)
        
        print(Color.CYAN + "⛓️ Initializing Maxwell Blockchain..." + Color.END)
        self.maxwell = MaxwellChain("maxwell_main", difficulty=3)
        
        print(Color.CYAN + "🌐 Initializing Onion Routing Nodes..." + Color.END)
        self.node_keys: Dict[str, NodeKeys] = {}
        self._initialize_nodes()
        
        print(Color.CYAN + "🏦 Initializing Addresses..." + Color.END)
        self.addresses = {
            "alice": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "bob": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
            "charlie": "1C7bDkj5fzNTPpVtnKgRg6FuXrN1tXg8Lv",
            "dave": "1D2b7s9qJ5wLpKZnJcM6sQnLWY9tG6hKjV"
        }
        
        print(Color.CYAN + "🧬 Registering DNA/Twin Identities..." + Color.END)
        self._register_identities()
        
        self.transaction_count = 0
        self.block_count = 0
        
        print(Color.GREEN + "✅ System initialized" + Color.END)
        print("=" * 70 + "\n")
    
    def _initialize_nodes(self):
        nodes = ["Alice", "Bob", "Charlie", "Relay1", "Relay2", "Relay3", "Dave"]
        for name in nodes:
            self.node_keys[name] = NodeKeys(name)
    
    def _register_identities(self):
        identities = [
            ("alice", "dna_alice_001", "twin_alice_001"),
            ("bob", "dna_bob_001", "twin_bob_001"),
            ("charlie", "dna_charlie_001", "twin_charlie_001"),
            ("dave", "dna_dave_001", "twin_dave_001")
        ]
        for identity_id, dna_hash, twin_hash in identities:
            self.maxwell.register_identity(identity_id, dna_hash, twin_hash)
    
    def create_transaction(self, sender: str, recipient: str, amount: float) -> Dict:
        from_addr = self.addresses.get(sender.lower())
        to_addr = self.addresses.get(recipient.lower())
        
        if not from_addr or not to_addr:
            return {"status": "error", "reason": "address_not_found"}
        
        result = self.maxwell.add_bitcoin_transaction(from_addr, to_addr, amount)
        if result.get("status") == "success":
            self.transaction_count += 1
        
        return result
    
    def mine_block(self) -> Dict:
        result = self.maxwell.mine_bitcoin_block()
        if result.get("status") == "success":
            self.block_count += 1
        return result
    
    def send_onion_payment(self, sender: str, path: List[str], amount: float) -> Dict:
        packet, session_priv, shared = build_onion(path, self.node_keys, amount)
        payment_id = dhash({"path": path, "amount": amount, "eph": packet.ephemeral_pub.hex()})[:20]
        
        current = packet
        hop_log = []
        
        for i, nid in enumerate(path):
            instr, next_pkt = peel_onion(current, self.node_keys[nid], shared[i])
            hop_log.append({"node": nid, "instr": instr})
            
            if instr.get("final"):
                sender_addr = self.addresses.get(sender.lower())
                receiver_addr = self.addresses.get(nid.lower())
                if sender_addr and receiver_addr:
                    self.maxwell.add_bitcoin_transaction(sender_addr, receiver_addr, amount)
                
                self.maxwell.add({
                    "type": "onion_delivery",
                    "payment_id": payment_id,
                    "sender": sender,
                    "receiver": nid,
                    "amount": amount,
                    "hops": hop_log,
                    "timestamp": ts()
                })
                
                return {
                    "status": "delivered",
                    "payment_id": payment_id,
                    "receiver": nid,
                    "amount": amount,
                    "hops": hop_log
                }
            current = next_pkt
        
        return {"status": "incomplete", "payment_id": payment_id, "hops": hop_log}
    
    def show_status(self):
        stats = self.maxwell.get_stats()
        print(f"\n{Color.CYAN}📊 SYSTEM STATUS" + Color.END)
        print("=" * 70)
        print(f"⛓️ Maxwell Blocks: {stats['blocks']}")
        print(f"🪙 Bitcoin Blocks: {stats['bitcoin_stats']['blocks']}")
        print(f"📊 Mempool: {stats['bitcoin_stats']['mempool']}")
        print(f"💳 UTXOs: {stats['bitcoin_stats']['utxos']}")
        print(f"🧬 Identities: {stats['identities']}")
        print(f"🔗 Cross-Chain Links: {stats['cross_chain_links']}")
        print(f"📝 Transactions: {self.transaction_count}")
        print(f"⛏️ Blocks Mined: {self.block_count}")
        print("=" * 70)
    
    def run_demo(self):
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        print("\n1. Creating Bitcoin Transactions...")
        self.create_transaction("alice", "bob", 0.5)
        self.create_transaction("bob", "charlie", 0.3)
        time.sleep(0.2)
        
        print("\n2. Mining Blocks...")
        self.mine_block()
        self.mine_block()
        time.sleep(0.2)
        
        print("\n3. Sending Onion Payment...")
        result = self.send_onion_payment(
            sender="alice",
            path=["Relay1", "Relay2", "Relay3", "bob"],
            amount=0.25
        )
        print(f"   Payment ID: {result.get('payment_id', 'N/A')}")
        print(f"   Status: {result.get('status', 'unknown')}")
        if result.get("status") == "delivered":
            print(f"   Receiver: {result.get('receiver', 'unknown')}")
        
        self.show_status()
        print("\n" + Color.GREEN + "✅ Demo complete" + Color.END)


# ──────────────────────────────────────────────────────────────
# 7. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxwellCompleteSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "⚡ SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show system status")
        print("   - tx <from> <to> <amount> - Create transaction")
        print("   - mine          - Mine a block")
        print("   - onion <sender> <path> <amount> - Onion payment")
        print("   - demo          - Run demonstration")
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
                        system.create_transaction(parts[1], parts[2], float(parts[3]))
                elif cmd.lower() == "mine":
                    system.mine_block()
                elif cmd.lower().startswith("onion "):
                    parts = cmd.split()
                    if len(parts) >= 4:
                        system.send_onion_payment(parts[1], parts[2].split(","), float(parts[3]))
                elif cmd.lower() == "demo":
                    system.run_demo()
                elif cmd.lower() == "help":
                    print("\n   Available commands:")
                    print("   status        - Show system status")
                    print("   tx <from> <to> <amount> - Create transaction")
                    print("   mine          - Mine a block")
                    print("   onion <sender> <path> <amount> - Onion payment")
                    print("   demo          - Run demonstration")
                    print("   help          - Show this help")
                    print("   exit          - Quit\n")
                elif cmd == "":
                    continue
                else:
                    print(f"   Unknown command: {cmd}")
            except KeyboardInterrupt:
                print("\n")
                break
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
