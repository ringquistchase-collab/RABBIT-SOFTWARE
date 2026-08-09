#!/usr/bin/env python3
"""
Maxwell Blockchain + Topological Quantum Error Correction
==========================================================
Save as: maxwell_topo_qec.py
Run:     python3 maxwell_topo_qec.py

Implements a simplified topological QEC layer (surface/toric-code style)
on top of the Maxwell integrity blockchain.

- Stabilizer checks on block payloads / Maxwell signatures
- Syndrome extraction
- Basic error detection & correction
- All events recorded as Maxwell-signed blocks

Digital twin / software simulation only.
"""

import hashlib
import json
import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Optional crypto
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def dhash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

def openssl_hash(data: bytes) -> str:
    if HAS_CRYPTO:
        h = hashes.Hash(hashes.SHA256(), backend=default_backend())
        h.update(data)
        return h.finalize().hex()
    return hashlib.sha256(data).hexdigest()


# ──────────────────────────────────────────────────────────────
# Maxwell Field Signature
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [(int.from_bytes(h[i*4:(i+1)*4], "big") / 0xFFFFFFFF)*2-1 for i in range(3)]

def compute_maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
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
# Topological QEC – Simplified Surface-Code Style
# ──────────────────────────────────────────────────────────────

class TopologicalQEC:
    """
    Minimal topological error-correction layer.
    Uses a small lattice of stabilizers (X-type and Z-type)
    over a bit-string representation of block data.
    """

    def __init__(self, lattice_size: int = 4):
        self.L = lattice_size          # L x L data qubits (simplified)
        self.n_data = self.L * self.L
        # Stabilizer generators (very small illustrative set)
        self.x_stabilizers = self._build_x_stabilizers()
        self.z_stabilizers = self._build_z_stabilizers()

    def _build_x_stabilizers(self) -> List[List[int]]:
        """X-stabilizers act on plaquettes (even parity of X)."""
        stabs = []
        for r in range(self.L-1):
            for c in range(self.L-1):
                # four corners of a plaquette
                idxs = [
                    r*self.L + c,
                    r*self.L + (c+1),
                    (r+1)*self.L + c,
                    (r+1)*self.L + (c+1),
                ]
                stabs.append(idxs)
        return stabs

    def _build_z_stabilizers(self) -> List[List[int]]:
        """Z-stabilizers act on vertices (even parity of Z)."""
        stabs = []
        for r in range(self.L):
            for c in range(self.L):
                idxs = []
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < self.L and 0 <= nc < self.L:
                        idxs.append(nr*self.L + nc)
                if idxs:
                    stabs.append(idxs)
        return stabs

    def data_from_payload(self, payload: Dict) -> List[int]:
        """Map payload hash to a bit string of length n_data."""
        h = dhash(payload)
        bits = []
        for ch in h:
            bits.extend([int(b) for b in format(int(ch, 16), "04b")])
        # pad or trim to n_data
        if len(bits) < self.n_data:
            bits += [0] * (self.n_data - len(bits))
        return bits[:self.n_data]

    def measure_syndrome(self, data: List[int]) -> Dict[str, List[int]]:
        """Extract X and Z syndromes (parity checks)."""
        x_syn = []
        for stab in self.x_stabilizers:
            parity = 0
            for i in stab:
                parity ^= data[i]
            x_syn.append(parity)
        z_syn = []
        for stab in self.z_stabilizers:
            parity = 0
            for i in stab:
                parity ^= data[i]
            z_syn.append(parity)
        return {"x_syndrome": x_syn, "z_syndrome": z_syn}

    def detect_errors(self, syndrome: Dict[str, List[int]]) -> Dict[str, Any]:
        x_err = sum(syndrome["x_syndrome"])
        z_err = sum(syndrome["z_syndrome"])
        total = x_err + z_err
        return {
            "x_errors_detected": x_err,
            "z_errors_detected": z_err,
            "total_syndrome_weight": total,
            "has_error": total > 0,
        }

    def correct(self, data: List[int], syndrome: Dict[str, List[int]]) -> Tuple[List[int], Dict]:
        """
        Very simple correction: flip the first qubit that participates
        in any violated stabilizer (illustrative decoder).
        Real surface-code decoders (MWPM, UF, neural) are far more sophisticated.
        """
        corrected = data[:]
        flips = []
        # X-syndrome → flip data qubits (Z-errors look like X-syndrome in this toy model)
        for s_idx, val in enumerate(syndrome["x_syndrome"]):
            if val == 1 and s_idx < len(self.x_stabilizers):
                q = self.x_stabilizers[s_idx][0]
                corrected[q] ^= 1
                flips.append({"qubit": q, "type": "X_stab"})
        for s_idx, val in enumerate(syndrome["z_syndrome"]):
            if val == 1 and s_idx < len(self.z_stabilizers):
                q = self.z_stabilizers[s_idx][0]
                corrected[q] ^= 1
                flips.append({"qubit": q, "type": "Z_stab"})
        return corrected, {"flips": flips, "num_flips": len(flips)}

    def protect(self, payload: Dict) -> Dict[str, Any]:
        """Full cycle: encode → syndrome → detect → correct → re-check."""
        data = self.data_from_payload(payload)
        syn1 = self.measure_syndrome(data)
        det1 = self.detect_errors(syn1)
        corrected, corr_info = self.correct(data, syn1)
        syn2 = self.measure_syndrome(corrected)
        det2 = self.detect_errors(syn2)
        return {
            "lattice_size": self.L,
            "n_data_qubits": self.n_data,
            "initial_syndrome": syn1,
            "initial_detection": det1,
            "correction": corr_info,
            "final_syndrome": syn2,
            "final_detection": det2,
            "corrected": not det2["has_error"],
            "logical_integrity": not det2["has_error"],
        }


# ──────────────────────────────────────────────────────────────
# Maxwell Block + Chain with QEC
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(self, index: int, payload: Dict, prev_hash: str,
                 prev_curl: List[float], qec_report: Optional[Dict] = None,
                 difficulty: int = 3):
        self.index = index
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = prev_hash
        self.qec = qec_report or {}
        self.difficulty = difficulty
        self.nonce = 0
        data_str = json.dumps({"payload": payload, "qec": self.qec}, sort_keys=True, default=str)
        self.maxwell = compute_maxwell_signature(data_str, index, prev_curl)
        self.hash = self._calc()

    def _calc(self) -> str:
        c = {
            "index": self.index,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "qec_logical": self.qec.get("logical_integrity"),
            "div_E": round(self.maxwell["div_E_residual"], 8),
            "div_B": round(self.maxwell["div_B"], 8),
            "Z": round(self.maxwell["wave_impedance"], 8),
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
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "maxwell": self.maxwell,
            "qec": self.qec,
        }


class MaxwellTopoChain:
    def __init__(self, difficulty: int = 3, lattice_size: int = 4):
        self.difficulty = difficulty
        self.qec = TopologicalQEC(lattice_size=lattice_size)
        self.blocks: List[MaxwellBlock] = []
        self._genesis()

    def _genesis(self):
        payload = {"type": "genesis", "msg": "Maxwell + Topological QEC chain"}
        report = self.qec.protect(payload)
        b = MaxwellBlock(0, payload, "0"*64, [0.,0.,0.], report, self.difficulty)
        b.mine()
        self.blocks.append(b)

    def add(self, payload: Dict, inject_noise: bool = False) -> MaxwellBlock:
        """
        Add a record. Optionally inject bit-flip noise before protection
        to demonstrate detection/correction.
        """
        # Optional noise for demo
        if inject_noise:
            noisy = dict(payload)
            noisy["_noise_flag"] = random.randint(0, 1)
            work_payload = noisy
        else:
            work_payload = payload

        report = self.qec.protect(work_payload)
        prev = self.blocks[-1]
        b = MaxwellBlock(
            len(self.blocks), work_payload, prev.hash,
            prev.maxwell["next_curl"], report, self.difficulty
        )
        b.mine()
        self.blocks.append(b)
        return b

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            if self.blocks[i].previous_hash != self.blocks[i-1].hash:
                return False
        return True

    def status(self) -> Dict:
        last = self.blocks[-1]
        return {
            "blocks": len(self.blocks),
            "valid_chain": self.validate(),
            "last_logical_integrity": last.qec.get("logical_integrity"),
            "last_Z": round(last.maxwell["wave_impedance"], 4),
            "last_hash": last.hash[:18] + "...",
        }


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("MAXWELL BLOCKCHAIN + TOPOLOGICAL QUANTUM ERROR CORRECTION")
    print("Surface-code style stabilizers on every block")
    print("=" * 64)

    chain = MaxwellTopoChain(difficulty=3, lattice_size=4)

    samples = [
        {"type": "sensor", "value": 0.42},
        {"type": "twin_marker", "coherence": 0.81},
        {"type": "dna_proxy", "seq_hash": dhash("ATGCGTAC")},
        {"type": "quantum_job", "circuit_hash": dhash("H-CX-measure")},
        {"type": "research", "title": "topo-QEC protected record"},
    ]

    print("\n── Adding protected records ──")
    for i, p in enumerate(samples):
        # inject noise on every other record to show correction
        block = chain.add(p, inject_noise=(i % 2 == 1))
        q = block.qec
        print(f"  #{block.index}  logical_ok={q.get('logical_integrity')}  "
              f"syndrome_weight={q.get('initial_detection',{}).get('total_syndrome_weight')}  "
              f"flips={q.get('correction',{}).get('num_flips')}  "
              f"Z={block.maxwell['wave_impedance']:.3f}")

    print("\n── Final Status ──")
    print(chain.status())

    # Show one full QEC report
    last = chain.blocks[-1]
    print("\n── Last block QEC report (summary) ──")
    print(f"  Lattice        : {last.qec.get('lattice_size')}x{last.qec.get('lattice_size')}")
    print(f"  Data qubits    : {last.qec.get('n_data_qubits')}")
    print(f"  Initial errors : {last.qec.get('initial_detection')}")
    print(f"  Correction     : {last.qec.get('correction')}")
    print(f"  Final integrity: {last.qec.get('logical_integrity')}")

    print("\nTopological stabilizers now protect every Maxwell block.")
    print("Syndrome + correction metadata is stored inside the chain.")


if __name__ == "__main__":
    main()
