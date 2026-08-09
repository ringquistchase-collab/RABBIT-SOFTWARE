#!/usr/bin/env python3
"""
Maxwell Equations + Quantum-DNA Computing + Blockchain Integration
==================================================================
Save as: maxwell_quantum_dna_chain.py
Run:     python3 maxwell_quantum_dna_chain.py

Layers:
  1. Maxwell field equations (discrete, hash-bound)
  2. DNA encoding of payloads
  3. Quantum-inspired DNA state (amplitudes + measurement)
  4. Blockchain integration (every action is a Maxwell-signed block)

Digital twin / software simulation only.
"""

import hashlib
import json
import math
import random
import cmath
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
# 1. Maxwell Equations in Python (discrete form)
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    """Map string → deterministic 3-vector in [-1, 1]³."""
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i*4:(i+1)*4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]

def maxwell_equations(
    data_str: str,
    index: int,
    prev_curl: List[float],
) -> Dict[str, Any]:
    """
    Discrete Maxwell field signature.

    I.   Gauss (E):   ∇·E  = ρ/ε₀
    II.  Gauss (B):   ∇·B  = 0
    III. Faraday:     ∇×E  = -∂B/∂t
    IV.  Ampère-Maxwell: ∇×H = J + ∂D/∂t
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

    # Residuals (the “equations” evaluated on the discrete fields)
    div_E = sum(E) - (rho / 8.854e-12)          # Gauss E
    div_B = sum(B)                              # Gauss B (≈ 0)
    curl_E = [                                  # Faraday
        E[1] - E[2] + dB_dt[0],
        E[2] - E[0] + dB_dt[1],
        E[0] - E[1] + dB_dt[2],
    ]
    curl_H = [                                  # Ampère-Maxwell
        H[1] - H[2] - (J[0] + dD_dt[0]),
        H[2] - H[0] - (J[1] + dD_dt[1]),
        H[0] - H[1] - (J[2] + dD_dt[2]),
    ]

    # Derived quantities
    S = [                                       # Poynting vector E × H
        E[1]*H[2] - E[2]*H[1],
        E[2]*H[0] - E[0]*H[2],
        E[0]*H[1] - E[1]*H[0],
    ]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15

    return {
        "E": E, "H": H, "B": B,
        "rho": rho,
        "div_E": div_E,           # residual of Gauss E
        "div_B": div_B,           # residual of Gauss B
        "curl_E": curl_E,         # residual of Faraday
        "curl_H": curl_H,         # residual of Ampère-Maxwell
        "poynting": S,
        "impedance": nE / nH,
        "next_curl": curl_E,      # forward link for next block
        "energy": nE * nH,
    }


# ──────────────────────────────────────────────────────────────
# 2. DNA Encoding
# ──────────────────────────────────────────────────────────────

DNA_TO_BIN = {"A": "00", "C": "01", "G": "10", "T": "11"}
BIN_TO_DNA = {v: k for k, v in DNA_TO_BIN.items()}

def payload_to_dna(payload: Dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    bits = "".join(format(b, "08b") for b in raw)
    if len(bits) % 2:
        bits += "0"
    return "".join(BIN_TO_DNA[bits[i:i+2]] for i in range(0, len(bits), 2))

def dna_hash(dna: str) -> str:
    return hashlib.sha256(dna.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────
# 3. Quantum-DNA Computing Layer (software simulation)
# ──────────────────────────────────────────────────────────────

class QuantumDNARegister:
    """
    Quantum-inspired register over DNA bases.
    Each base is a 2-amplitude qubit-like state.
    Measurement collapses to a classical DNA string.
    """

    BASES = ["A", "C", "G", "T"]

    def __init__(self, length: int = 8):
        self.length = length
        # Each position: complex amplitudes for A,C,G,T (normalized)
        self.state: List[List[complex]] = []
        self._init_superposition()

    def _init_superposition(self):
        for _ in range(self.length):
            amps = [complex(random.uniform(-1, 1), random.uniform(-1, 1)) for _ in range(4)]
            norm = math.sqrt(sum(abs(a)**2 for a in amps)) or 1.0
            self.state.append([a / norm for a in amps])

    def encode_classical_dna(self, dna: str):
        """Load a classical DNA string into the register (basis states)."""
        self.length = len(dna)
        self.state = []
        for base in dna:
            amps = [complex(0), complex(0), complex(0), complex(0)]
            if base in self.BASES:
                amps[self.BASES.index(base)] = complex(1)
            else:
                amps[0] = complex(1)
            self.state.append(amps)

    def apply_hadamard_like(self, positions: Optional[List[int]] = None):
        """Simple mixing of amplitudes (toy ‘Hadamard’ on base space)."""
        positions = positions or list(range(self.length))
        for i in positions:
            if i >= self.length:
                continue
            old = self.state[i]
            # equal superposition mix
            s = sum(old) / 2.0
            self.state[i] = [(old[k] + s) / 1.5 for k in range(4)]
            norm = math.sqrt(sum(abs(a)**2 for a in self.state[i])) or 1.0
            self.state[i] = [a / norm for a in self.state[i]]

    def measure(self) -> str:
        """Collapse each position to one base according to |amp|²."""
        result = []
        for amps in self.state:
            probs = [abs(a)**2 for a in amps]
            total = sum(probs) or 1.0
            probs = [p / total for p in probs]
            r = random.random()
            cum = 0.0
            chosen = 0
            for k, p in enumerate(probs):
                cum += p
                if r <= cum:
                    chosen = k
                    break
            result.append(self.BASES[chosen])
            # collapse
            new_amps = [complex(0)] * 4
            new_amps[chosen] = complex(1)
            self.state[self.state.index(amps) if amps in self.state else 0] = new_amps
        return "".join(result)

    def state_commitment(self) -> str:
        """Hash of the full complex state (for on-chain commitment)."""
        flat = []
        for amps in self.state:
            for a in amps:
                flat.append(round(a.real, 8))
                flat.append(round(a.imag, 8))
        return dhash(flat)

    def to_dict(self) -> Dict:
        return {
            "length": self.length,
            "commitment": self.state_commitment(),
            "measured_preview": self.measure()[:32] if self.length else "",
        }


# ──────────────────────────────────────────────────────────────
# 4. Blockchain Integration Layer
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(
        self,
        index: int,
        payload: Dict,
        dna: str,
        qdna_commitment: str,
        prev_hash: str,
        prev_curl: List[float],
        difficulty: int = 3,
    ):
        self.index = index
        self.timestamp = ts()
        self.payload = payload
        self.dna = dna
        self.dna_fp = dna_hash(dna)
        self.qdna_commitment = qdna_commitment
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0

        # Maxwell equations applied to the unified data
        seed_str = dhash(payload) + self.dna_fp + qdna_commitment
        self.maxwell = maxwell_equations(seed_str, index, prev_curl)
        self.hash = self._calc()

    def _calc(self) -> str:
        c = {
            "index": self.index,
            "timestamp": self.timestamp,
            "payload_hash": dhash(self.payload),
            "dna_fp": self.dna_fp,
            "qdna": self.qdna_commitment,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "div_E": round(self.maxwell["div_E"], 8),
            "div_B": round(self.maxwell["div_B"], 8),
            "Z": round(self.maxwell["impedance"], 8),
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
            "dna_fp": self.dna_fp,
            "dna_len": len(self.dna),
            "qdna_commitment": self.qdna_commitment,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "maxwell": self.maxwell,
        }


class MaxwellQuantumDNAChain:
    def __init__(self, difficulty: int = 3):
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self.qdna = QuantumDNARegister(length=16)
        self._genesis()

    def _genesis(self):
        payload = {"type": "genesis", "msg": "Maxwell + Quantum-DNA chain"}
        dna = payload_to_dna(payload)
        self.qdna.encode_classical_dna(dna[:16] if len(dna) >= 16 else dna.ljust(16, "A"))
        commit = self.qdna.state_commitment()
        b = MaxwellBlock(0, payload, dna, commit, "0"*64, [0.0, 0.0, 0.0], self.difficulty)
        b.mine()
        self.blocks.append(b)

    def add(self, payload: Dict, apply_quantum: bool = True) -> MaxwellBlock:
        dna = payload_to_dna(payload)

        # Quantum-DNA step
        if apply_quantum:
            segment = dna[:16] if len(dna) >= 16 else dna.ljust(16, "A")
            self.qdna.encode_classical_dna(segment)
            self.qdna.apply_hadamard_like()
            measured = self.qdna.measure()
            commit = self.qdna.state_commitment()
            payload = dict(payload)
            payload["qdna_measured_preview"] = measured[:16]
        else:
            commit = dhash(dna)

        prev = self.blocks[-1]
        b = MaxwellBlock(
            len(self.blocks),
            payload,
            dna,
            commit,
            prev.hash,
            prev.maxwell["next_curl"],
            self.difficulty,
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
            "valid": self.validate(),
            "last_Z": round(last.maxwell["impedance"], 4),
            "last_div_B": round(last.maxwell["div_B"], 4),
            "last_dna_fp": last.dna_fp[:16] + "…",
            "last_qdna": last.qdna_commitment[:16] + "…",
            "last_hash": last.hash[:18] + "…",
        }


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 66)
    print("MAXWELL EQUATIONS + QUANTUM-DNA COMPUTING + BLOCKCHAIN")
    print("=" * 66)

    chain = MaxwellQuantumDNAChain(difficulty=3)

    samples = [
        {"type": "sensor", "value": 0.37},
        {"type": "dna_event", "label": "segment_A"},
        {"type": "quantum_job", "circuit": "H-CX"},
        {"type": "twin_marker", "coherence": 0.79},
        {"type": "research", "title": "maxwell-qdna integration"},
    ]

    print("\n── Adding records (Maxwell + DNA + Quantum-DNA) ──")
    for p in samples:
        block = chain.add(p, apply_quantum=True)
        m = block.maxwell
        print(f"  #{block.index}  Z={m['impedance']:.3f}  div_B={m['div_B']:.3f}  "
              f"DNA={block.dna_fp[:10]}…  QDNA={block.qdna_commitment[:10]}…  "
              f"nonce={block.nonce}")

    print("\n── Chain Status ──")
    print(chain.status())

    # Show Maxwell equation residuals for last block
    last = chain.blocks[-1]
    print("\n── Maxwell Equation Residuals (last block) ──")
    print(f"  Gauss E  (∇·E - ρ/ε₀) = {last.maxwell['div_E']:.6e}")
    print(f"  Gauss B  (∇·B)        = {last.maxwell['div_B']:.6f}")
    print(f"  Faraday  curl_E       = {[round(x,4) for x in last.maxwell['curl_E']]}")
    print(f"  Ampère   curl_H       = {[round(x,4) for x in last.maxwell['curl_H']]}")
    print(f"  Impedance Z           = {last.maxwell['impedance']:.4f}")
    print(f"  Poynting |S|          = {math.sqrt(sum(x*x for x in last.maxwell['poynting'])):.4f}")

    print("\nLayers active:")
    print("  • Maxwell equations evaluated on every block")
    print("  • DNA encoding of the same payload")
    print("  • Quantum-DNA register (superposition → measure → commitment)")
    print("  • Full blockchain integration (hash + PoW + forward curl link)")


if __name__ == "__main__":
    main()
