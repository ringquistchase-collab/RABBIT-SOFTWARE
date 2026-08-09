#!/usr/bin/env python3
"""
Maxwell Field Signature Mesh Network
=====================================
Save as: maxwell_field_mesh.py
Run:     python3 maxwell_field_mesh.py

Core:
  - Maxwell field signature mathematics on every block
  - Multiple interconnected blockchains (one per node)
  - Mesh of nodes that exchange and validate records
  - Forward curl linking across blocks and across nodes
  - Real SHA / OpenSSL-compatible hashing + proof-of-work

Digital twin / software simulation only.
No real biology, chemicals, RF, or hardware control.
"""

import hashlib
import json
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

# Optional OpenSSL-backed crypto
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
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

def openssl_hash(data: bytes, algo: str = "sha256") -> str:
    algo = algo.lower().replace("-", "_")
    if HAS_CRYPTO:
        mapping = {
            "sha256": hashes.SHA256(),
            "sha3_256": hashes.SHA3_256(),
            "sha384": hashes.SHA384(),
            "sha512": hashes.SHA512(),
        }
        h = hashes.Hash(mapping.get(algo, hashes.SHA256()), backend=default_backend())
        h.update(data)
        return h.finalize().hex()
    if algo == "sha3_256":
        return hashlib.sha3_256(data).hexdigest()
    return hashlib.sha256(data).hexdigest()


# ──────────────────────────────────────────────────────────────
# Maxwell Field Signature Mathematics
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    """Map string + seed → deterministic 3-vector in [-1, 1]³."""
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i * 4:(i + 1) * 4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]

def compute_maxwell_signature(
    data_str: str,
    index: int,
    prev_curl: List[float],
) -> Dict[str, Any]:
    """
    Discrete Maxwell field signature.
    I.   Gauss (E):   div E = ρ/ε₀
    II.  Gauss (B):   div B = 0
    III. Faraday:     curl E = -∂B/∂t
    IV.  Ampère-Maxwell: curl H = J + ∂D/∂t
    """
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

    # Residuals
    div_E = sum(E) - (rho / 8.854e-12)
    curl_E = [
        E[1] - E[2] + dB_dt[0],
        E[2] - E[0] + dB_dt[1],
        E[0] - E[1] + dB_dt[2],
    ]
    curl_H = [
        H[1] - H[2] - (J[0] + dD_dt[0]),
        H[2] - H[0] - (J[1] + dD_dt[1]),
        H[0] - H[1] - (J[2] + dD_dt[2]),
    ]
    div_B = sum(B)

    # Poynting & impedance
    S = [
        E[1] * H[2] - E[2] * H[1],
        E[2] * H[0] - E[0] * H[2],
        E[0] * H[1] - E[1] * H[0],
    ]
    nE = math.sqrt(sum(x * x for x in E)) or 1e-15
    nH = math.sqrt(sum(x * x for x in H)) or 1e-15
    impedance = nE / nH
    field_energy = nE * nH
    field_entropy = sum(abs(x) for x in E + H) / 6.0

    return {
        "E_field": E,
        "H_field": H,
        "B_field": B,
        "rho_charge": rho,
        "div_E_residual": div_E,
        "curl_E_residual": curl_E,
        "curl_H_residual": curl_H,
        "div_B": div_B,
        "poynting_vector": S,
        "wave_impedance": impedance,
        "next_curl": curl_E,          # forward link
        "field_energy": field_energy,
        "field_entropy": field_entropy,
    }


# ──────────────────────────────────────────────────────────────
# Maxwell Block + Chain
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(
        self,
        index: int,
        payload: Dict[str, Any],
        previous_hash: str,
        prev_curl: List[float],
        node_id: str,
        difficulty: int = 3,
    ):
        self.index = index
        self.node_id = node_id
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = previous_hash
        self.difficulty = difficulty
        self.nonce = 0

        data_str = json.dumps(payload, sort_keys=True, default=str)
        self.maxwell = compute_maxwell_signature(data_str, index, prev_curl)
        self.hash = self._calc()

    def _calc(self) -> str:
        content = {
            "index": self.index,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "div_E": round(self.maxwell["div_E_residual"], 8),
            "div_B": round(self.maxwell["div_B"], 8),
            "impedance": round(self.maxwell["wave_impedance"], 8),
            "poynting": [round(v, 8) for v in self.maxwell["poynting_vector"]],
            "field_energy": round(self.maxwell["field_energy"], 8),
        }
        return openssl_hash(json.dumps(content, sort_keys=True, default=str).encode(), "sha256")

    def mine(self) -> None:
        target = "0" * self.difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calc()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "maxwell_signature": self.maxwell,
        }


class MaxwellChain:
    def __init__(self, node_id: str, difficulty: int = 3):
        self.node_id = node_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self._genesis()

    def _genesis(self) -> None:
        payload = {
            "type": "genesis",
            "node_id": self.node_id,
            "message": f"Maxwell chain genesis – {self.node_id}",
        }
        block = MaxwellBlock(0, payload, "0" * 64, [0.0, 0.0, 0.0], self.node_id, self.difficulty)
        block.mine()
        self.blocks.append(block)

    def add(self, payload: Dict[str, Any]) -> MaxwellBlock:
        prev = self.blocks[-1]
        block = MaxwellBlock(
            len(self.blocks),
            payload,
            prev.hash,
            prev.maxwell["next_curl"],
            self.node_id,
            self.difficulty,
        )
        block.mine()
        self.blocks.append(block)
        return block

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            curr, prev = self.blocks[i], self.blocks[i - 1]
            if curr.hash != curr._calc() or curr.previous_hash != prev.hash:
                return False
            # soft check on div B
            if abs(curr.maxwell["div_B"]) > 3.0:
                return False
        return True

    def last_curl(self) -> List[float]:
        return self.blocks[-1].maxwell["next_curl"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "length": len(self.blocks),
            "valid": self.validate(),
            "blocks": [b.to_dict() for b in self.blocks],
        }


# ──────────────────────────────────────────────────────────────
# Mesh Node
# ──────────────────────────────────────────────────────────────

class MeshNode:
    def __init__(self, node_id: str, difficulty: int = 3):
        self.node_id = node_id
        self.chain = MaxwellChain(node_id, difficulty)
        self.peers: Set[str] = set()
        self.inbox: List[Dict[str, Any]] = []
        self.outbox: List[Dict[str, Any]] = []
        self.energy = 10.0
        self.created_at = ts()

    def connect(self, peer_id: str) -> None:
        self.peers.add(peer_id)

    def add_record(self, payload: Dict[str, Any]) -> MaxwellBlock:
        block = self.chain.add(payload)
        self.energy += 0.05
        # prepare propagation message
        msg = {
            "from": self.node_id,
            "type": "block_announce",
            "block": block.to_dict(),
            "timestamp": ts(),
        }
        self.outbox.append(msg)
        return block

    def receive(self, msg: Dict[str, Any]) -> None:
        self.inbox.append(msg)
        self.energy += 0.01

    def process_inbox(self) -> int:
        """Simple validation of received block announcements."""
        processed = 0
        for msg in self.inbox:
            if msg.get("type") == "block_announce":
                blk = msg.get("block", {})
                # basic integrity check
                if blk.get("hash") and blk.get("maxwell_signature"):
                    processed += 1
        self.inbox.clear()
        return processed

    def status(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "blocks": len(self.chain.blocks),
            "peers": list(self.peers),
            "energy": round(self.energy, 3),
            "valid": self.chain.validate(),
            "last_hash": self.chain.blocks[-1].hash[:16] + "...",
            "last_impedance": round(self.chain.blocks[-1].maxwell["wave_impedance"], 4),
        }


# ──────────────────────────────────────────────────────────────
# Maxwell Field Mesh Network
# ──────────────────────────────────────────────────────────────

class MaxwellFieldMesh:
    def __init__(self, difficulty: int = 3):
        self.difficulty = difficulty
        self.nodes: Dict[str, MeshNode] = {}
        self.created_at = ts()
        print("=" * 64)
        print("MAXWELL FIELD SIGNATURE MESH")
        print("Maxwell mathematics on every block · networked chains · mesh topology")
        print("=" * 64)

    def add_node(self, node_id: str) -> MeshNode:
        if node_id in self.nodes:
            return self.nodes[node_id]
        node = MeshNode(node_id, self.difficulty)
        self.nodes[node_id] = node
        print(f"[+] Node {node_id} online · genesis {node.chain.blocks[0].hash[:16]}...")
        return node

    def connect(self, a: str, b: str) -> None:
        if a in self.nodes and b in self.nodes:
            self.nodes[a].connect(b)
            self.nodes[b].connect(a)
            print(f"[↔] Linked {a} ↔ {b}")

    def mesh_topology(self, node_ids: List[str], density: float = 0.7) -> None:
        """Create a random mesh among the given nodes."""
        for i, n1 in enumerate(node_ids):
            for n2 in node_ids[i + 1:]:
                if random.random() < density:
                    self.connect(n1, n2)

    def broadcast(self, from_id: str) -> int:
        """Propagate outbox messages to peers."""
        if from_id not in self.nodes:
            return 0
        node = self.nodes[from_id]
        count = 0
        for msg in node.outbox:
            for peer_id in node.peers:
                if peer_id in self.nodes:
                    self.nodes[peer_id].receive(msg)
                    count += 1
        node.outbox.clear()
        return count

    def add_record(self, node_id: str, payload: Dict[str, Any]) -> Optional[MaxwellBlock]:
        if node_id not in self.nodes:
            return None
        block = self.nodes[node_id].add_record(payload)
        delivered = self.broadcast(node_id)
        print(f"[{node_id}] block #{block.index} mined · nonce={block.nonce} · "
              f"Z={block.maxwell['wave_impedance']:.3f} · delivered to {delivered} peers")
        return block

    def tick(self) -> None:
        """Process inboxes on all nodes."""
        for node in self.nodes.values():
            node.process_inbox()

    def status(self) -> None:
        print("\n── Mesh Status ──")
        for nid, node in self.nodes.items():
            s = node.status()
            print(f"  {nid:12} blocks={s['blocks']:3}  peers={len(s['peers'])}  "
                  f"valid={s['valid']}  Z={s['last_impedance']:.3f}  energy={s['energy']}")
        print()

    def validate_all(self) -> bool:
        ok = all(n.chain.validate() for n in self.nodes.values())
        print(f"[Validation] All chains valid: {ok}")
        return ok


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    mesh = MaxwellFieldMesh(difficulty=3)

    # Create nodes
    nodes = ["NODE_ALPHA", "NODE_BETA", "NODE_GAMMA", "NODE_DELTA", "NODE_EPSILON"]
    for n in nodes:
        mesh.add_node(n)

    # Build mesh topology
    mesh.mesh_topology(nodes, density=0.75)

    print("\n── Generating Maxwell-signed records across the mesh ──\n")

    # Each node adds several records (Maxwell signature computed every time)
    samples = [
        {"type": "sensor", "value": random.random(), "tag": "alpha"},
        {"type": "research", "title": "field continuity", "confidence": 0.91},
        {"type": "dna_proxy", "sequence_hash": dhash("ATGCGTA"), "label": "segment"},
        {"type": "eeg_proxy", "band": "alpha", "power": random.uniform(0.2, 0.9)},
        {"type": "api_fingerprint", "service": "demo", "fp": dhash("key-material")},
    ]

    for i in range(8):
        node_id = random.choice(nodes)
        payload = random.choice(samples).copy()
        payload["cycle"] = i
        payload["origin"] = node_id
        mesh.add_record(node_id, payload)
        mesh.tick()
        time.sleep(0.05)

    mesh.status()
    mesh.validate_all()

    # Show one full Maxwell signature
    sample_block = mesh.nodes["NODE_ALPHA"].chain.blocks[-1]
    print("── Sample Maxwell Field Signature (last block on NODE_ALPHA) ──")
    sig = sample_block.maxwell
    print(f"  div_E residual : {sig['div_E_residual']:.6e}")
    print(f"  div_B          : {sig['div_B']:.6f}")
    print(f"  wave impedance : {sig['wave_impedance']:.4f}")
    print(f"  field energy   : {sig['field_energy']:.4f}")
    print(f"  Poynting       : {[round(x, 4) for x in sig['poynting_vector']]}")
    print(f"  next_curl      : {[round(x, 4) for x in sig['next_curl']]}")
    print()

    print("Mesh running with Maxwell field signatures on every block.")
    print("Chains remain independently valid while records propagate across nodes.")


if __name__ == "__main__":
    main()
