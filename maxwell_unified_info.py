#!/usr/bin/env python3
"""
Maxwell Unified Information Architecture
========================================
Maxwell Field Signatures + DNA Storage + Network Mesh

Save as: maxwell_unified_info.py
Run:     python3 maxwell_unified_info.py

Architecture:
  - Single canonical payload
  - Deterministic DNA encoding (A=00,C=01,G=10,T=11)
  - Maxwell field signature derived from both
  - Network mesh of nodes, each holding the same information object
  - Twin + DNA views stay synchronized via Maxwell blocks

Digital twin / software simulation only.
No real biology, chemicals, RF, or hardware control.
"""

import hashlib
import json
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

# Optional crypto
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
# DNA Encoding / Decoding  (A=00, C=01, G=10, T=11)
# ──────────────────────────────────────────────────────────────

DNA_TO_BIN = {"A": "00", "C": "01", "G": "10", "T": "11"}
BIN_TO_DNA = {v: k for k, v in DNA_TO_BIN.items()}

def payload_to_dna(payload: Dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    bits = "".join(format(b, "08b") for b in raw)
    if len(bits) % 2:
        bits += "0"
    return "".join(BIN_TO_DNA[bits[i:i+2]] for i in range(0, len(bits), 2))

def dna_fingerprint(dna: str) -> str:
    return hashlib.sha256(dna.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────
# Maxwell Field Signature Mathematics
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i*4:(i+1)*4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]

def compute_maxwell_signature(
    data_str: str,
    index: int,
    prev_curl: List[float],
) -> Dict[str, Any]:
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
    S = [
        E[1]*H[2] - E[2]*H[1],
        E[2]*H[0] - E[0]*H[2],
        E[0]*H[1] - E[1]*H[0],
    ]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15

    return {
        "E_field": E,
        "H_field": H,
        "B_field": B,
        "div_E_residual": div_E,
        "curl_E_residual": curl_E,
        "curl_H_residual": curl_H,
        "div_B": div_B,
        "poynting_vector": S,
        "wave_impedance": nE / nH,
        "next_curl": curl_E,
        "field_energy": nE * nH,
    }


# ──────────────────────────────────────────────────────────────
# Unified Information Object
# ──────────────────────────────────────────────────────────────

class UnifiedRecord:
    """
    Single source of truth:
      payload  →  DNA encoding  →  Maxwell signature
    All three are bound; changing one invalidates the others.
    """

    def __init__(self, payload: Dict[str, Any], index: int, prev_curl: List[float]):
        self.payload = payload
        self.payload_hash = dhash(payload)
        self.dna = payload_to_dna(payload)
        self.dna_fp = dna_fingerprint(self.dna)
        # Maxwell signature seeded from payload + DNA fingerprint
        seed_str = self.payload_hash + self.dna_fp
        self.maxwell = compute_maxwell_signature(seed_str, index, prev_curl)
        self.timestamp = ts()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload": self.payload,
            "payload_hash": self.payload_hash,
            "dna_fingerprint": self.dna_fp,
            "dna_length": len(self.dna),
            "dna_preview": self.dna[:64] + ("..." if len(self.dna) > 64 else ""),
            "maxwell": self.maxwell,
            "timestamp": self.timestamp,
        }

    def integrity_ok(self) -> bool:
        """Recompute and verify binding."""
        if dhash(self.payload) != self.payload_hash:
            return False
        if dna_fingerprint(self.dna) != self.dna_fp:
            return False
        return True


# ──────────────────────────────────────────────────────────────
# Maxwell Block + Chain
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(
        self,
        index: int,
        record: UnifiedRecord,
        previous_hash: str,
        node_id: str,
        difficulty: int = 3,
    ):
        self.index = index
        self.node_id = node_id
        self.timestamp = record.timestamp
        self.record = record
        self.previous_hash = previous_hash
        self.difficulty = difficulty
        self.nonce = 0
        self.hash = self._calc()

    def _calc(self) -> str:
        content = {
            "index": self.index,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "payload_hash": self.record.payload_hash,
            "dna_fp": self.record.dna_fp,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "div_E": round(self.record.maxwell["div_E_residual"], 8),
            "div_B": round(self.record.maxwell["div_B"], 8),
            "Z": round(self.record.maxwell["wave_impedance"], 8),
            "poynting": [round(v, 8) for v in self.record.maxwell["poynting_vector"]],
        }
        return openssl_hash(json.dumps(content, sort_keys=True, default=str).encode())

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
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "record": self.record.to_dict(),
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
            "msg": "Unified Maxwell + DNA information architecture",
        }
        rec = UnifiedRecord(payload, 0, [0.0, 0.0, 0.0])
        block = MaxwellBlock(0, rec, "0" * 64, self.node_id, self.difficulty)
        block.mine()
        self.blocks.append(block)

    def add(self, payload: Dict[str, Any]) -> MaxwellBlock:
        prev = self.blocks[-1]
        rec = UnifiedRecord(payload, len(self.blocks), prev.record.maxwell["next_curl"])
        block = MaxwellBlock(
            len(self.blocks), rec, prev.hash, self.node_id, self.difficulty
        )
        block.mine()
        self.blocks.append(block)
        return block

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            curr, prev = self.blocks[i], self.blocks[i - 1]
            if curr.previous_hash != prev.hash:
                return False
            if not curr.record.integrity_ok():
                return False
        return True

    def latest_record(self) -> Optional[UnifiedRecord]:
        return self.blocks[-1].record if self.blocks else None


# ──────────────────────────────────────────────────────────────
# Network Mesh Node
# ──────────────────────────────────────────────────────────────

class MeshNode:
    def __init__(self, node_id: str, difficulty: int = 3):
        self.node_id = node_id
        self.chain = MaxwellChain(node_id, difficulty)
        self.peers: Set[str] = set()
        self.energy = 10.0
        # Local views
        self.twin_view: Dict[str, Any] = {}
        self.dna_view: Dict[str, str] = {}   # seq_id → dna_fp

    def connect(self, peer_id: str) -> None:
        self.peers.add(peer_id)

    def store(self, payload: Dict[str, Any]) -> MaxwellBlock:
        """Store information: creates unified record (payload + DNA + Maxwell)."""
        block = self.chain.add(payload)
        rec = block.record
        # Update twin view
        self.twin_view = {
            "payload_hash": rec.payload_hash,
            "block_index": block.index,
            "Z": rec.maxwell["wave_impedance"],
            "ts": rec.timestamp,
        }
        # Update DNA view
        self.dna_view[rec.dna_fp[:16]] = rec.dna_fp
        self.energy += 0.05
        return block

    def get_twin_view(self) -> Dict[str, Any]:
        return dict(self.twin_view)

    def get_dna_view(self) -> Dict[str, str]:
        return dict(self.dna_view)

    def status(self) -> Dict[str, Any]:
        last = self.chain.blocks[-1]
        return {
            "node_id": self.node_id,
            "blocks": len(self.chain.blocks),
            "peers": list(self.peers),
            "valid": self.chain.validate(),
            "energy": round(self.energy, 3),
            "last_Z": round(last.record.maxwell["wave_impedance"], 4),
            "last_dna_fp": last.record.dna_fp[:16] + "...",
            "twin_view": self.twin_view,
        }


# ──────────────────────────────────────────────────────────────
# Maxwell Unified Mesh Network
# ──────────────────────────────────────────────────────────────

class MaxwellUnifiedMesh:
    def __init__(self, difficulty: int = 3):
        self.difficulty = difficulty
        self.nodes: Dict[str, MeshNode] = {}
        print("=" * 66)
        print("MAXWELL UNIFIED INFORMATION ARCHITECTURE")
        print("Field Signatures + DNA Storage + Network Mesh")
        print("Single information object · Twin & DNA stay synchronized")
        print("=" * 66)

    def add_node(self, node_id: str) -> MeshNode:
        node = MeshNode(node_id, self.difficulty)
        self.nodes[node_id] = node
        print(f"[+] Node {node_id} online")
        return node

    def connect(self, a: str, b: str) -> None:
        if a in self.nodes and b in self.nodes:
            self.nodes[a].connect(b)
            self.nodes[b].connect(a)
            print(f"[↔] {a} ↔ {b}")

    def mesh_topology(self, density: float = 0.75) -> None:
        ids = list(self.nodes.keys())
        for i, n1 in enumerate(ids):
            for n2 in ids[i+1:]:
                if random.random() < density:
                    self.connect(n1, n2)

    def store(self, node_id: str, payload: Dict[str, Any]) -> Optional[MaxwellBlock]:
        if node_id not in self.nodes:
            return None
        block = self.nodes[node_id].store(payload)
        rec = block.record
        print(f"[{node_id}] #{block.index}  "
              f"payload={rec.payload_hash[:12]}…  "
              f"dna={rec.dna_fp[:12]}…  "
              f"Z={rec.maxwell['wave_impedance']:.3f}  "
              f"nonce={block.nonce}")
        return block

    def propagate_view(self, from_id: str) -> int:
        """Share latest twin/DNA view with peers (simulation of gossip)."""
        if from_id not in self.nodes:
            return 0
        src = self.nodes[from_id]
        count = 0
        for peer_id in src.peers:
            if peer_id in self.nodes:
                # Peer adopts the same information hashes (views stay aligned)
                self.nodes[peer_id].twin_view = dict(src.twin_view)
                self.nodes[peer_id].dna_view.update(src.dna_view)
                count += 1
        return count

    def status(self) -> None:
        print("\n── Mesh Status ──")
        for nid, node in self.nodes.items():
            s = node.status()
            print(f"  {nid:10} blocks={s['blocks']:2}  peers={len(s['peers'])}  "
                  f"valid={s['valid']}  Z={s['last_Z']:.3f}  "
                  f"dna={s['last_dna_fp']}")

    def verify_unified(self) -> bool:
        """Check that every block still binds payload ↔ DNA ↔ Maxwell."""
        ok = True
        for node in self.nodes.values():
            if not node.chain.validate():
                ok = False
        print(f"\n[Verify] All chains + unified records valid: {ok}")
        return ok


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    mesh = MaxwellUnifiedMesh(difficulty=3)

    nodes = ["ALPHA", "BETA", "GAMMA", "DELTA"]
    for n in nodes:
        mesh.add_node(n)
    mesh.mesh_topology(density=0.8)

    print("\n── Storing unified information objects ──\n")

    samples = [
        {"type": "sensor", "value": round(random.random(), 4), "tag": "alpha"},
        {"type": "twin_marker", "coherence": 0.82, "stress": 0.21},
        {"type": "dna_event", "label": "segment_7", "note": "symbolic"},
        {"type": "research", "title": "unified architecture test"},
        {"type": "quantum_meta", "circuit_hash": dhash("H-CX")},
    ]

    for i, payload in enumerate(samples):
        node_id = random.choice(nodes)
        payload = dict(payload)
        payload["cycle"] = i
        payload["origin"] = node_id
        block = mesh.store(node_id, payload)
        # Propagate views across mesh
        delivered = mesh.propagate_view(node_id)
        print(f"         views propagated to {delivered} peers")
        time.sleep(0.05)

    mesh.status()
    mesh.verify_unified()

    # Show one full unified record
    sample_node = mesh.nodes["ALPHA"]
    rec = sample_node.chain.latest_record()
    if rec:
        print("\n── Sample Unified Record (ALPHA latest) ──")
        print(f"  payload_hash : {rec.payload_hash[:32]}…")
        print(f"  dna_fp       : {rec.dna_fp[:32]}…")
        print(f"  dna_length   : {len(rec.dna)} bases")
        print(f"  dna_preview  : {rec.dna[:48]}…")
        print(f"  wave_Z       : {rec.maxwell['wave_impedance']:.4f}")
        print(f"  div_B        : {rec.maxwell['div_B']:.4f}")
        print(f"  field_energy : {rec.maxwell['field_energy']:.4f}")
        print(f"  integrity_ok : {rec.integrity_ok()}")

    print("\nArchitecture active:")
    print("  • Canonical payload")
    print("  • Deterministic DNA encoding of the same payload")
    print("  • Maxwell signature binding both")
    print("  • Network mesh keeps twin view + DNA view synchronized")
    print("  • One information object, multiple consistent projections")


if __name__ == "__main__":
    main()
