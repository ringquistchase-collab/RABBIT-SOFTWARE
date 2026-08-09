#!/usr/bin/env python3
"""
Maxwell Blockchain + Quantum Algorithm Integration Layer
========================================================
Save as: maxwell_quantum_algorithms.py
Run:     python3 maxwell_quantum_algorithms.py

One script that:
  • Implements discrete Maxwell field signatures
  • Maintains a Maxwell integrity blockchain
  • Records ANY quantum algorithm as on-chain commitments
    (VQE, QAOA, Grover, Shor, simulation, QML, QEC, annealing, …)
  • Binds circuit_hash + param_hash + result_commitment
    into every Maxwell-signed block

Digital twin / software simulation only.
Does not execute real QPU jobs; records metadata & commitments.
"""

import hashlib
import json
import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
# Maxwell Field Signature Mathematics
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i * 4:(i + 1) * 4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]

def maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
    """
    Discrete Maxwell equations:
      I.   Gauss E:   ∇·E = ρ/ε₀
      II.  Gauss B:   ∇·B = 0
      III. Faraday:   ∇×E = -∂B/∂t
      IV.  Ampère:    ∇×H = J + ∂D/∂t
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

    div_E = sum(E) - (rho / 8.854e-12)
    div_B = sum(B)
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
    S = [
        E[1] * H[2] - E[2] * H[1],
        E[2] * H[0] - E[0] * H[2],
        E[0] * H[1] - E[1] * H[0],
    ]
    nE = math.sqrt(sum(x * x for x in E)) or 1e-15
    nH = math.sqrt(sum(x * x for x in H)) or 1e-15

    return {
        "E": E, "H": H, "B": B,
        "div_E": div_E, "div_B": div_B,
        "curl_E": curl_E, "curl_H": curl_H,
        "poynting": S,
        "impedance": nE / nH,
        "next_curl": curl_E,
        "energy": nE * nH,
    }


# ──────────────────────────────────────────────────────────────
# Quantum Algorithm Job Descriptor
# ──────────────────────────────────────────────────────────────

SUPPORTED_ALGORITHMS = [
    "VQE", "QAOA", "Grover", "Shor", "QPE",
    "TrotterSimulation", "QML", "QSVM", "QNN",
    "QEC", "Annealing", "Custom",
]

def make_quantum_job(
    algorithm: str,
    circuit_desc: str,
    parameters: Optional[Dict] = None,
    result: Optional[Dict] = None,
    backend: str = "simulator",
    shots: int = 1024,
    extra: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Build a uniform job record for ANY quantum algorithm.
    Only commitments (hashes) are stored on-chain.
    """
    if algorithm not in SUPPORTED_ALGORITHMS:
        algorithm = "Custom"

    circuit_hash = dhash(circuit_desc)
    param_hash = dhash(parameters or {})
    result_commitment = dhash(result or {})

    job = {
        "type": "quantum_job",
        "algorithm": algorithm,
        "circuit_hash": circuit_hash,
        "param_hash": param_hash,
        "result_commitment": result_commitment,
        "backend": backend,
        "shots": shots,
        "ts": ts(),
    }
    if extra:
        job["extra"] = extra
    return job


# ──────────────────────────────────────────────────────────────
# Maxwell Block + Chain
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(
        self,
        index: int,
        payload: Dict,
        prev_hash: str,
        prev_curl: List[float],
        difficulty: int = 3,
    ):
        self.index = index
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0

        seed_str = dhash(payload)
        self.maxwell = maxwell_signature(seed_str, index, prev_curl)
        self.hash = self._calc()

    def _calc(self) -> str:
        c = {
            "index": self.index,
            "timestamp": self.timestamp,
            "payload": self.payload,
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
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "maxwell": self.maxwell,
        }


class MaxwellQuantumChain:
    def __init__(self, difficulty: int = 3):
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self.job_count = 0
        self._genesis()

    def _genesis(self):
        payload = {
            "type": "genesis",
            "msg": "Maxwell Quantum Algorithm Integration Chain",
            "supported": SUPPORTED_ALGORITHMS,
        }
        b = MaxwellBlock(0, payload, "0" * 64, [0.0, 0.0, 0.0], self.difficulty)
        b.mine()
        self.blocks.append(b)

    def record_job(self, job: Dict[str, Any]) -> MaxwellBlock:
        """Record any quantum algorithm job as a Maxwell-signed block."""
        prev = self.blocks[-1]
        b = MaxwellBlock(
            len(self.blocks),
            job,
            prev.hash,
            prev.maxwell["next_curl"],
            self.difficulty,
        )
        b.mine()
        self.blocks.append(b)
        self.job_count += 1
        return b

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            if self.blocks[i].previous_hash != self.blocks[i - 1].hash:
                return False
        return True

    def status(self) -> Dict:
        last = self.blocks[-1]
        return {
            "blocks": len(self.blocks),
            "quantum_jobs": self.job_count,
            "valid": self.validate(),
            "last_Z": round(last.maxwell["impedance"], 4),
            "last_hash": last.hash[:20] + "…",
        }

    def jobs_by_algorithm(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for b in self.blocks:
            if b.payload.get("type") == "quantum_job":
                alg = b.payload.get("algorithm", "Unknown")
                counts[alg] = counts.get(alg, 0) + 1
        return counts


# ──────────────────────────────────────────────────────────────
# Demo: record many quantum algorithm types
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 66)
    print("MAXWELL BLOCKCHAIN × QUANTUM ALGORITHMS")
    print("One chain · all algorithm families · Maxwell signatures")
    print("=" * 66)

    chain = MaxwellQuantumChain(difficulty=3)

    # ── Example jobs for major algorithm families ──
    demos = [
        make_quantum_job(
            "VQE",
            circuit_desc="ansatz: Ry-CX hardware-efficient, 4 qubits",
            parameters={"theta": [0.12, 0.45, 0.78, 1.01]},
            result={"energy": -1.136},
            backend="local_simulator",
            shots=2048,
            extra={"molecule": "H2", "optimizer": "COBYLA"},
        ),
        make_quantum_job(
            "QAOA",
            circuit_desc="QAOA p=2, MaxCut graph n=6",
            parameters={"gamma": [0.3, 0.6], "beta": [0.2, 0.5]},
            result={"approx_ratio": 0.87, "best_bitstring": "101010"},
            backend="local_simulator",
            shots=1024,
        ),
        make_quantum_job(
            "Grover",
            circuit_desc="Grover oracle for marked state |101>",
            parameters={"iterations": 1},
            result={"measured": "101", "probability": 0.94},
            backend="local_simulator",
            shots=512,
        ),
        make_quantum_job(
            "Shor",
            circuit_desc="period-finding for N=15 (demo)",
            parameters={"N": 15, "a": 7},
            result={"period": 4, "factors": [3, 5]},
            backend="local_simulator",
            shots=256,
        ),
        make_quantum_job(
            "TrotterSimulation",
            circuit_desc="Ising Trotter step dt=0.1, steps=10",
            parameters={"dt": 0.1, "steps": 10, "J": 1.0},
            result={"magnetization": 0.42},
            backend="local_simulator",
            shots=1024,
        ),
        make_quantum_job(
            "QML",
            circuit_desc="quantum kernel 2-qubit feature map",
            parameters={"feature_map": "ZZFeatureMap"},
            result={"accuracy": 0.91},
            backend="local_simulator",
            shots=1024,
            extra={"dataset": "demo_blobs"},
        ),
        make_quantum_job(
            "QEC",
            circuit_desc="surface-code distance-3 syndrome cycle",
            parameters={"distance": 3, "rounds": 5},
            result={"logical_error_rate": 0.002},
            backend="local_simulator",
            shots=0,
        ),
        make_quantum_job(
            "Annealing",
            circuit_desc="QUBO 8-variable embedding",
            parameters={"chain_strength": 2.0},
            result={"best_energy": -12.5, "occurrences": 48},
            backend="annealer_stub",
            shots=100,
        ),
    ]

    print("\n── Recording quantum algorithm jobs ──\n")
    for job in demos:
        block = chain.record_job(job)
        print(
            f"  #{block.index:02d}  {job['algorithm']:18s}  "
            f"Z={block.maxwell['impedance']:.3f}  "
            f"circuit={job['circuit_hash'][:10]}…  "
            f"result={job['result_commitment'][:10]}…  "
            f"nonce={block.nonce}"
        )

    print("\n── Chain Status ──")
    print(chain.status())

    print("\n── Jobs by algorithm ──")
    for alg, cnt in chain.jobs_by_algorithm().items():
        print(f"  {alg:18s}  {cnt}")

    # Show Maxwell residuals for last block
    last = chain.blocks[-1]
    print("\n── Maxwell residuals (last block) ──")
    print(f"  div_E (Gauss E) = {last.maxwell['div_E']:.6e}")
    print(f"  div_B (Gauss B) = {last.maxwell['div_B']:.6f}")
    print(f"  impedance Z     = {last.maxwell['impedance']:.4f}")
    print(f"  energy          = {last.maxwell['energy']:.4f}")

    print("\nIntegration rule used by every job:")
    print("  circuit_hash + param_hash + result_commitment")
    print("  → Maxwell signature → mined block → chain continuity")
    print("\nAny quantum algorithm that can produce those three")
    print("commitments can be recorded on this chain.")


if __name__ == "__main__":
    main()
