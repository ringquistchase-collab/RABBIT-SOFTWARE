#!/usr/bin/env python3
"""
Maxwell · DNA · EEG · Network  –  Unified On-Chain Communication System
=======================================================================
Save as: maxwell_dna_eeg_network.py
Run:     python3 maxwell_dna_eeg_network.py

Features:
  • Maxwell field signature mathematics on every record
  • DNA encoding/decoding of all payloads
  • EEG pattern generation & network communication
  • Mesh network of nodes (gossip-style propagation)
  • Everything written on-chain (single unified information object)
  • Multi-view: logical / DNA / EEG / Maxwell stay synchronized

Digital twin / software simulation only.
No real biology, chemicals, RF, neural hardware, or medical control.
"""

import hashlib
import json
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

# Optional
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ──────────────────────────────────────────────────────────────
# Utilities
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


# ──────────────────────────────────────────────────────────────
# DNA Encoding (A=00, C=01, G=10, T=11)
# ──────────────────────────────────────────────────────────────

DNA_TO_BIN = {"A": "00", "C": "01", "G": "10", "T": "11"}
BIN_TO_DNA = {v: k for k, v in DNA_TO_BIN.items()}

def to_dna(payload: Dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    bits = "".join(format(b, "08b") for b in raw)
    if len(bits) % 2:
        bits += "0"
    return "".join(BIN_TO_DNA[bits[i:i+2]] for i in range(0, len(bits), 2))

def dna_fp(dna: str) -> str:
    return hashlib.sha256(dna.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────
# EEG Pattern Engine (simulation)
# ──────────────────────────────────────────────────────────────

BANDS = ["delta", "theta", "alpha", "beta", "gamma"]

def generate_eeg(seed_str: str, intensity: float = 0.5) -> Dict[str, float]:
    """Deterministic EEG-like band powers from a seed string."""
    h = hashlib.sha256(seed_str.encode()).digest()
    powers = {}
    for i, band in enumerate(BANDS):
        # map bytes to [0,1] then scale by intensity
        v = h[i] / 255.0
        powers[band] = round(min(1.0, v * (0.4 + intensity * 0.6)), 4)
    return powers

def eeg_dominant(eeg: Dict[str, float]) -> str:
    return max(eeg, key=eeg.get)

def eeg_to_vector(eeg: Dict[str, float]) -> List[float]:
    return [eeg.get(b, 0.0) for b in BANDS]

def eeg_message(eeg: Dict[str, float], text: str = "") -> Dict[str, Any]:
    """Package an EEG pattern as a network communication message."""
    return {
        "type": "eeg_comm",
        "bands": eeg,
        "dominant": eeg_dominant(eeg),
        "vector": eeg_to_vector(eeg),
        "text": text,
        "ts": ts(),
    }


# ──────────────────────────────────────────────────────────────
# Maxwell Field Signature
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [(int.from_bytes(h[i*4:(i+1)*4], "big") / 0xFFFFFFFF)*2-1 for i in range(3)]

def maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
    seed = index * 1337
    E = hash_to_vec(data_str, seed)
    H = hash_to_vec(data_str[::-1], seed+1)
    B = hash_to_vec(data_str, seed+2)
    raw = hashlib.sha256(data_str.encode()).hexdigest()
    rho = int(raw[:8], 16) / 1e10
    J = [index*0.01, index*0.007, index*0.003]
    dD_dt = [c*0.1 for c in prev_curl]
    angle = (index % 1.4) % 1.4
    dB_dt = [math.sin(index), math.cos(index), math.tan(angle*0.5)]
    div_E = sum(E) - (rho / 8.854e-12)
    curl_E = [E[1]-E[2]+dB_dt[0], E[2]-E[0]+dB_dt[1], E[0]-E[1]+dB_dt[2]]
    curl_H = [H[1]-H[2]-(J[0]+dD_dt[0]), H[2]-H[0]-(J[1]+dD_dt[1]), H[0]-H[1]-(J[2]+dD_dt[2])]
    div_B = sum(B)
    S = [E[1]*H[2]-E[2]*H[1], E[2]*H[0]-E[0]*H[2], E[0]*H[1]-E[1]*H[0]]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15
    return {
        "E_field": E, "H_field": H, "B_field": B,
        "div_E_residual": div_E, "curl_E_residual": curl_E,
        "curl_H_residual": curl_H, "div_B": div_B,
        "poynting_vector": S, "wave_impedance": nE/nH,
        "next_curl": curl_E, "field_energy": nE*nH,
    }


# ──────────────────────────────────────────────────────────────
# Unified On-Chain Record (Payload + DNA + EEG + Maxwell)
# ──────────────────────────────────────────────────────────────

class UnifiedRecord:
    def __init__(self, payload: Dict, index: int, prev_curl: List[float]):
        self.payload = payload
        self.payload_hash = dhash(payload)
        self.dna = to_dna(payload)
        self.dna_fp = dna_fp(self.dna)
        # EEG derived from the same information
        self.eeg = generate_eeg(self.payload_hash + self.dna_fp)
        # Maxwell seeded from payload + DNA + EEG vector
        seed_str = self.payload_hash + self.dna_fp + dhash(self.eeg)
        self.maxwell = maxwell_signature(seed_str, index, prev_curl)
        self.timestamp = ts()

    def to_dict(self) -> Dict:
        return {
            "payload": self.payload,
            "payload_hash": self.payload_hash,
            "dna_fp": self.dna_fp,
            "dna_len": len(self.dna),
            "dna_preview": self.dna[:48] + ("..." if len(self.dna) > 48 else ""),
            "eeg": self.eeg,
            "eeg_dominant": eeg_dominant(self.eeg),
            "maxwell": self.maxwell,
            "timestamp": self.timestamp,
        }

    def integrity_ok(self) -> bool:
        return (
            dhash(self.payload) == self.payload_hash
            and dna_fp(self.dna) == self.dna_fp
        )


# ──────────────────────────────────────────────────────────────
# Block + Chain
# ──────────────────────────────────────────────────────────────

class Block:
    def __init__(self, index: int, record: UnifiedRecord, prev_hash: str,
                 node_id: str, difficulty: int = 3):
        self.index = index
        self.node_id = node_id
        self.record = record
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0
        self.timestamp = record.timestamp
        self.hash = self._calc()

    def _calc(self) -> str:
        c = {
            "index": self.index,
            "node_id": self.node_id,
            "payload_hash": self.record.payload_hash,
            "dna_fp": self.record.dna_fp,
            "eeg_dom": eeg_dominant(self.record.eeg),
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "Z": round(self.record.maxwell["wave_impedance"], 8),
            "div_B": round(self.record.maxwell["div_B"], 8),
        }
        return openssl_hash(json.dumps(c, sort_keys=True, default=str).encode())

    def mine(self):
        target = "0" * self.difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calc()

    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "record": self.record.to_dict(),
        }


class Chain:
    def __init__(self, node_id: str, difficulty: int = 3):
        self.node_id = node_id
        self.difficulty = difficulty
        self.blocks: List[Block] = []
        self._genesis()

    def _genesis(self):
        payload = {"type": "genesis", "node": self.node_id,
                   "msg": "Maxwell+DNA+EEG unified chain"}
        rec = UnifiedRecord(payload, 0, [0.0, 0.0, 0.0])
        b = Block(0, rec, "0"*64, self.node_id, self.difficulty)
        b.mine()
        self.blocks.append(b)

    def add(self, payload: Dict) -> Block:
        prev = self.blocks[-1]
        rec = UnifiedRecord(payload, len(self.blocks), prev.record.maxwell["next_curl"])
        b = Block(len(self.blocks), rec, prev.hash, self.node_id, self.difficulty)
        b.mine()
        self.blocks.append(b)
        return b

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            if self.blocks[i].previous_hash != self.blocks[i-1].hash:
                return False
            if not self.blocks[i].record.integrity_ok():
                return False
        return True


# ──────────────────────────────────────────────────────────────
# Network Node + Mesh Communication
# ──────────────────────────────────────────────────────────────

class Node:
    def __init__(self, node_id: str, difficulty: int = 3):
        self.node_id = node_id
        self.chain = Chain(node_id, difficulty)
        self.peers: Set[str] = set()
        self.inbox: List[Dict] = []
        self.eeg_log: List[Dict] = []
        self.energy = 10.0

    def connect(self, peer: str):
        self.peers.add(peer)

    def emit(self, text: str = "", intensity: float = 0.6) -> Block:
        """
        Create an on-chain communication event:
        payload → DNA → EEG pattern → Maxwell signature → mined block
        """
        payload = {
            "type": "network_comm",
            "from": self.node_id,
            "text": text or f"signal from {self.node_id}",
            "intensity": intensity,
            "lang": "universal",          # placeholder for multi-language tag
            "ts": ts(),
        }
        block = self.chain.add(payload)
        # EEG communication package (derived from the same record)
        msg = eeg_message(block.record.eeg, text=payload["text"])
        msg["block_hash"] = block.hash
        msg["dna_fp"] = block.record.dna_fp
        msg["from"] = self.node_id
        self.eeg_log.append(msg)
        self.energy += 0.05
        return block

    def receive(self, msg: Dict):
        self.inbox.append(msg)
        self.energy += 0.01

    def process_inbox(self) -> int:
        n = len(self.inbox)
        self.inbox.clear()
        return n

    def status(self) -> Dict:
        last = self.chain.blocks[-1]
        return {
            "node": self.node_id,
            "blocks": len(self.chain.blocks),
            "peers": list(self.peers),
            "valid": self.chain.validate(),
            "energy": round(self.energy, 3),
            "last_Z": round(last.record.maxwell["wave_impedance"], 4),
            "last_eeg": eeg_dominant(last.record.eeg),
            "last_dna": last.record.dna_fp[:14] + "…",
        }


class Mesh:
    def __init__(self, difficulty: int = 3):
        self.difficulty = difficulty
        self.nodes: Dict[str, Node] = {}
        print("=" * 66)
        print("MAXWELL · DNA · EEG · NETWORK  –  Unified On-Chain System")
        print("One information object → payload + DNA + EEG + Maxwell")
        print("All communication recorded on-chain and propagated on mesh")
        print("=" * 66)

    def add_node(self, nid: str) -> Node:
        n = Node(nid, self.difficulty)
        self.nodes[nid] = n
        print(f"[+] {nid} online")
        return n

    def link(self, a: str, b: str):
        if a in self.nodes and b in self.nodes:
            self.nodes[a].connect(b)
            self.nodes[b].connect(a)
            print(f"[↔] {a} ↔ {b}")

    def mesh_connect(self, density: float = 0.75):
        ids = list(self.nodes)
        for i, a in enumerate(ids):
            for b in ids[i+1:]:
                if random.random() < density:
                    self.link(a, b)

    def communicate(self, from_id: str, text: str = "", intensity: float = 0.6) -> Optional[Block]:
        if from_id not in self.nodes:
            return None
        node = self.nodes[from_id]
        block = node.emit(text=text, intensity=intensity)
        rec = block.record
        # Gossip EEG+DNA+Maxwell summary to peers
        msg = {
            "from": from_id,
            "block_hash": block.hash,
            "payload_hash": rec.payload_hash,
            "dna_fp": rec.dna_fp,
            "eeg": rec.eeg,
            "eeg_dominant": eeg_dominant(rec.eeg),
            "Z": rec.maxwell["wave_impedance"],
            "text": text,
            "ts": ts(),
        }
        delivered = 0
        for peer in node.peers:
            if peer in self.nodes:
                self.nodes[peer].receive(msg)
                delivered += 1
        print(f"[{from_id}] #{block.index}  DNA={rec.dna_fp[:10]}…  "
              f"EEG={eeg_dominant(rec.eeg):5}  Z={rec.maxwell['wave_impedance']:.3f}  "
              f"→ {delivered} peers  | {text[:40]}")
        return block

    def tick(self):
        for n in self.nodes.values():
            n.process_inbox()

    def status(self):
        print("\n── Network Status ──")
        for n in self.nodes.values():
            s = n.status()
            print(f"  {s['node']:8} blocks={s['blocks']:2}  peers={len(s['peers'])}  "
                  f"valid={s['valid']}  Z={s['last_Z']:.3f}  "
                  f"EEG={s['last_eeg']:5}  DNA={s['last_dna']}")

    def validate_all(self) -> bool:
        ok = all(n.chain.validate() for n in self.nodes.values())
        print(f"\n[Validate] All chains + unified records OK: {ok}")
        return ok


# ──────────────────────────────────────────────────────────────
# Demo – multi-language style communication tags
# ──────────────────────────────────────────────────────────────

def main():
    mesh = Mesh(difficulty=3)

    for name in ["ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON"]:
        mesh.add_node(name)
    mesh.mesh_connect(density=0.8)

    print("\n── On-chain EEG + DNA + Maxwell communication ──\n")

    messages = [
        ("ALPHA",   "hello mesh",           0.5),
        ("BETA",    "status query",         0.4),
        ("GAMMA",   "dna sync pulse",       0.7),
        ("DELTA",   "eeg pattern share",    0.6),
        ("EPSILON", "field continuity",     0.55),
        ("ALPHA",   "ack + coherence",      0.65),
        ("BETA",    "research marker set",  0.5),
    ]

    for nid, text, intensity in messages:
        mesh.communicate(nid, text=text, intensity=intensity)
        mesh.tick()
        time.sleep(0.05)

    mesh.status()
    mesh.validate_all()

    # Show one full unified record
    sample = mesh.nodes["ALPHA"].chain.blocks[-1].record
    print("\n── Sample Unified On-Chain Record (ALPHA) ──")
    print(f"  payload_hash : {sample.payload_hash[:28]}…")
    print(f"  dna_fp       : {sample.dna_fp[:28]}…")
    print(f"  dna_len      : {len(sample.dna)} bases")
    print(f"  eeg bands    : {sample.eeg}")
    print(f"  eeg dominant : {eeg_dominant(sample.eeg)}")
    print(f"  wave_Z       : {sample.maxwell['wave_impedance']:.4f}")
    print(f"  div_B        : {sample.maxwell['div_B']:.4f}")
    print(f"  integrity    : {sample.integrity_ok()}")

    print("\nSystem active:")
    print("  • Maxwell field equations bind every record")
    print("  • DNA encoding of the same payload")
    print("  • EEG patterns generated from the same data")
    print("  • Network communication carries all three")
    print("  • Everything is on-chain and mesh-synchronized")


if __name__ == "__main__":
    main()
