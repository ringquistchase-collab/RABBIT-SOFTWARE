#!/usr/bin/env python3
"""
Maxwell Blockchain – Shor + Multi-Algorithm + Multi-Chain
=========================================================
Save as: maxwell_shor_multichain.py
Run:     python3 maxwell_shor_multichain.py

Implements:
  • Discrete Maxwell field signatures on every block
  • Specialty chains: Shor, VQE, QAOA, Grover, Simulation, Hub
  • Classical demo of Shor period-finding + factoring (small N)
  • Uniform quantum-job commitments for all algorithms
  • Cross-links from specialty chains → Hub chain
  • Parallel-style recording of many algorithms running together

Digital twin / software simulation only.
No real QPU execution required.
"""

import hashlib
import json
import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
# Maxwell Field Signature
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
        E[1]*H[2] - E[2]*H[1],
        E[2]*H[0] - E[0]*H[2],
        E[0]*H[1] - E[1]*H[0],
    ]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15

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
# Classical Shor helpers (demo scale)
# ──────────────────────────────────────────────────────────────

def gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a

def continued_fraction_period(x: int, Q: int, N: int) -> Optional[int]:
    """Very small demo continued-fraction style period extraction."""
    if x == 0:
        return None
    # candidates near x/Q
    for r in range(1, N * 2):
        if pow(2, r, N) == 1 or True:  # placeholder; real CF is more precise
            pass
    # For demo we return a plausible r when known
    return None

def shor_classical_demo(N: int = 15, a: int = 7) -> Dict[str, Any]:
    """
    Classical stand-in for Shor on tiny N.
    Finds order of a mod N and factors (when possible).
    """
    if gcd(a, N) != 1:
        return {
            "success": True,
            "N": N, "a": a,
            "order": None,
            "factors": [gcd(a, N), N // gcd(a, N)],
            "method": "gcd_trivial",
        }

    # Find order r: a^r ≡ 1 (mod N)
    r = None
    val = 1
    for cand in range(1, N * 2):
        val = (val * a) % N
        if val == 1:
            r = cand
            break

    factors = []
    success = False
    if r and r % 2 == 0:
        x = pow(a, r // 2, N)
        f1 = gcd(x - 1, N)
        f2 = gcd(x + 1, N)
        for f in (f1, f2):
            if 1 < f < N:
                factors.append(f)
                success = True
        factors = sorted(set(factors))
        if success and len(factors) == 1:
            factors.append(N // factors[0])

    return {
        "success": success,
        "N": N,
        "a": a,
        "order": r,
        "factors": factors,
        "method": "classical_order_finding_demo",
    }


# ──────────────────────────────────────────────────────────────
# Uniform quantum job builder
# ──────────────────────────────────────────────────────────────

def make_job(
    algorithm: str,
    circuit_desc: str,
    parameters: Optional[Dict] = None,
    result: Optional[Dict] = None,
    backend: str = "simulator",
    shots: int = 1024,
    extra: Optional[Dict] = None,
) -> Dict[str, Any]:
    return {
        "type": "quantum_job",
        "algorithm": algorithm,
        "circuit_hash": dhash(circuit_desc),
        "param_hash": dhash(parameters or {}),
        "result_commitment": dhash(result or {}),
        "backend": backend,
        "shots": shots,
        "result_preview": result,          # small demos only
        "extra": extra or {},
        "ts": ts(),
    }


# ──────────────────────────────────────────────────────────────
# Maxwell Block + Specialty Chain
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(
        self,
        index: int,
        payload: Dict,
        prev_hash: str,
        prev_curl: List[float],
        chain_id: str,
        difficulty: int = 3,
    ):
        self.index = index
        self.chain_id = chain_id
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0
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
            "chain_id": self.chain_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "maxwell_Z": self.maxwell["impedance"],
            "div_B": self.maxwell["div_B"],
        }


class MaxwellChain:
    def __init__(self, chain_id: str, difficulty: int = 3):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self._genesis()

    def _genesis(self):
        payload = {"type": "genesis", "chain": self.chain_id}
        b = MaxwellBlock(0, payload, "0"*64, [0.0, 0.0, 0.0], self.chain_id, self.difficulty)
        b.mine()
        self.blocks.append(b)

    def add(self, payload: Dict) -> MaxwellBlock:
        prev = self.blocks[-1]
        b = MaxwellBlock(
            len(self.blocks),
            payload,
            prev.hash,
            prev.maxwell["next_curl"],
            self.chain_id,
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

    def last_hash(self) -> str:
        return self.blocks[-1].hash


# ──────────────────────────────────────────────────────────────
# Multi-Chain Hub
# ──────────────────────────────────────────────────────────────

class MaxwellMultiChain:
    def __init__(self, difficulty: int = 3):
        self.difficulty = difficulty
        self.chains: Dict[str, MaxwellChain] = {}
        # specialty chains
        for name in ["HUB", "SHOR", "VQE", "QAOA", "GROVER", "SIM"]:
            self.chains[name] = MaxwellChain(name, difficulty)
        print("=" * 66)
        print("MAXWELL MULTI-CHAIN  ·  Shor + VQE + QAOA + Grover + Sim + Hub")
        print("=" * 66)

    def record(self, chain_name: str, job: Dict) -> MaxwellBlock:
        if chain_name not in self.chains:
            chain_name = "HUB"
        block = self.chains[chain_name].add(job)
        # cross-link on Hub
        if chain_name != "HUB":
            link = {
                "type": "cross_link",
                "from_chain": chain_name,
                "block_index": block.index,
                "block_hash": block.hash,
                "algorithm": job.get("algorithm"),
                "ts": ts(),
            }
            self.chains["HUB"].add(link)
        return block

    def run_shor_demo(self, N: int = 15, a: int = 7) -> MaxwellBlock:
        result = shor_classical_demo(N, a)
        circuit_desc = f"Shor period-finding modexp+QFT N={N} a={a}"
        job = make_job(
            algorithm="Shor",
            circuit_desc=circuit_desc,
            parameters={"N": N, "a": a},
            result=result,
            backend="classical_demo",
            shots=0,
            extra={"note": "order-finding demo for small N"},
        )
        block = self.record("SHOR", job)
        return block

    def status(self):
        print("\n── Multi-Chain Status ──")
        for name, ch in self.chains.items():
            last = ch.blocks[-1]
            print(f"  {name:7}  blocks={len(ch.blocks):2}  valid={ch.validate()}  "
                  f"Z={last.maxwell['impedance']:.3f}  hash={last.hash[:14]}…")


# ──────────────────────────────────────────────────────────────
# Demo – algorithms running together
# ──────────────────────────────────────────────────────────────

def main():
    hub = MaxwellMultiChain(difficulty=3)

    print("\n── Shor demos on SHOR chain ──")
    for N, a in [(15, 7), (15, 4), (21, 2)]:
        block = hub.run_shor_demo(N, a)
        res = block.payload.get("result_preview", {})
        print(f"  #{block.index}  N={N} a={a}  order={res.get('order')}  "
              f"factors={res.get('factors')}  success={res.get('success')}  "
              f"Z={block.maxwell['impedance']:.3f}")

    print("\n── Other algorithms on specialty chains ──")
    others = [
        ("VQE", make_job("VQE", "Ry-CX ansatz 4q",
                         {"theta": [0.1, 0.4, 0.7]},
                         {"energy": -1.13}, shots=2048)),
        ("QAOA", make_job("QAOA", "MaxCut p=2 n=6",
                          {"gamma": [0.3, 0.6], "beta": [0.2, 0.5]},
                          {"approx_ratio": 0.88}, shots=1024)),
        ("GROVER", make_job("Grover", "oracle marked |101>",
                            {"iterations": 1},
                            {"measured": "101", "prob": 0.94}, shots=512)),
        ("SIM", make_job("TrotterSimulation", "Ising dt=0.1 steps=10",
                         {"dt": 0.1, "steps": 10},
                         {"magnetization": 0.41}, shots=1024)),
        ("VQE", make_job("VQE", "UCCSD H2",
                         {"params": [0.2, 0.5]},
                         {"energy": -1.136}, shots=4096,
                         extra={"molecule": "H2"})),
    ]

    for chain_name, job in others:
        block = hub.record(chain_name, job)
        print(f"  [{chain_name:6}] #{block.index}  {job['algorithm']:18}  "
              f"Z={block.maxwell['impedance']:.3f}  "
              f"circuit={job['circuit_hash'][:10]}…")

    hub.status()

    # Summary of Shor chain
    shor_chain = hub.chains["SHOR"]
    print("\n── SHOR chain job summary ──")
    for b in shor_chain.blocks[1:]:
        p = b.payload
        rp = p.get("result_preview", {})
        print(f"  block {b.index}: N={rp.get('N')}  factors={rp.get('factors')}  "
              f"hash={b.hash[:16]}…")

    print("\n── Hub cross-links (last 5) ──")
    for b in hub.chains["HUB"].blocks[-5:]:
        p = b.payload
        if p.get("type") == "cross_link":
            print(f"  {p.get('from_chain'):6} block#{p.get('block_index')}  "
                  f"alg={p.get('algorithm')}  → hub#{b.index}")

    print("\nAll algorithms recorded under Maxwell signatures.")
    print("Specialty chains run side-by-side; Hub holds cross-links.")
    print("Shor uses classical order-finding demo for small N only.")


if __name__ == "__main__":
    main()
