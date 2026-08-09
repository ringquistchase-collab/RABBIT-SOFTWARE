#!/usr/bin/env python3
"""
Maxwell Chain – Off-Chain Memory Branch
=======================================
Save as: maxwell_memory_chain.py
Run:     python3 maxwell_memory_chain.py

Off-chain Memory Branch linked into the Maxwell network:
  • Full data stored off-chain (MemoryBranch)
  • Commitments on MEMORY chain (memory_id + content_hash)
  • Specialty jobs carry memory_id pointers
  • HUB cross-links for network discovery
  • Maxwell field signatures on every block

Digital twin / software simulation only.
"""

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


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
# Off-Chain Memory Branch
# ──────────────────────────────────────────────────────────────

class MemoryBranch:
    """Full data off-chain; only commitments go on-chain."""

    def __init__(self, root_dir: str = "maxwell_memory"):
        self.root_dir = root_dir
        self.index: Dict[str, Dict[str, Any]] = {}
        os.makedirs(root_dir, exist_ok=True)
        self._load()

    def _path(self) -> str:
        return os.path.join(self.root_dir, "index.json")

    def _load(self):
        p = self._path()
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    self.index = json.load(f)
            except Exception:
                self.index = {}

    def _save(self):
        with open(self._path(), "w", encoding="utf-8") as f:
            json.dump(self.index, f, indent=2, default=str)

    def store(self, data: Any, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        content = {"data": data, "tags": tags or [], "stored_at": ts()}
        raw = json.dumps(content, sort_keys=True, default=str).encode()
        content_hash = hashlib.sha256(raw).hexdigest()
        memory_id = content_hash[:32]
        blob = os.path.join(self.root_dir, f"{memory_id}.json")
        with open(blob, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, default=str)
        meta = {
            "memory_id": memory_id,
            "content_hash": content_hash,
            "path": blob,
            "tags": tags or [],
            "size": len(raw),
            "stored_at": content["stored_at"],
        }
        self.index[memory_id] = meta
        self._save()
        return meta

    def fetch(self, memory_id: str) -> Optional[Any]:
        meta = self.index.get(memory_id)
        if not meta or not os.path.isfile(meta.get("path", "")):
            return None
        with open(meta["path"], "r", encoding="utf-8") as f:
            return json.load(f)

    def commitment(self, memory_id: str) -> Dict[str, Any]:
        meta = self.index.get(memory_id, {})
        return {
            "type": "memory_commit",
            "memory_id": memory_id,
            "content_hash": meta.get("content_hash", ""),
            "tags": meta.get("tags", []),
            "ts": ts(),
        }


# ──────────────────────────────────────────────────────────────
# Maxwell Block + Chain
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(self, index, payload, prev_hash, prev_curl, chain_id, difficulty=3):
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


class MaxwellChain:
    def __init__(self, chain_id: str, difficulty: int = 3):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        payload = {"type": "genesis", "chain": chain_id}
        b = MaxwellBlock(0, payload, "0"*64, [0.0, 0.0, 0.0], chain_id, difficulty)
        b.mine()
        self.blocks.append(b)

    def add(self, payload: Dict) -> MaxwellBlock:
        prev = self.blocks[-1]
        b = MaxwellBlock(
            len(self.blocks), payload, prev.hash,
            prev.maxwell["next_curl"], self.chain_id, self.difficulty
        )
        b.mine()
        self.blocks.append(b)
        return b

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            if self.blocks[i].previous_hash != self.blocks[i-1].hash:
                return False
        return True


# ──────────────────────────────────────────────────────────────
# Network: MEMORY branch + specialty chains + HUB
# ──────────────────────────────────────────────────────────────

class MaxwellMemoryNetwork:
    def __init__(self, difficulty: int = 3, memory_dir: str = "maxwell_memory"):
        self.difficulty = difficulty
        self.memory = MemoryBranch(memory_dir)
        self.chains = {
            name: MaxwellChain(name, difficulty)
            for name in ["HUB", "MEMORY", "AI", "QUANTUM", "TWIN"]
        }
        print("=" * 64)
        print("MAXWELL MEMORY BRANCH NETWORK")
        print("Off-chain data · on-chain commitments · Hub links")
        print("=" * 64)

    def link_hub(self, from_chain: str, block: MaxwellBlock, label: str = ""):
        self.chains["HUB"].add({
            "type": "cross_link",
            "from_chain": from_chain,
            "block_index": block.index,
            "block_hash": block.hash,
            "label": label,
            "ts": ts(),
        })

    def store_and_link(
        self,
        full_data: Any,
        job: Dict[str, Any],
        specialty: str = "AI",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        1. Off-chain: full data → MemoryBranch
        2. On-chain:  commitment → MEMORY chain
        3. On-chain:  job + memory_id → specialty chain
        4. On-chain:  cross-link → HUB
        """
        if specialty not in self.chains:
            specialty = "HUB"

        # 1. off-chain store
        meta = self.memory.store(full_data, tags=tags or [specialty.lower()])

        # 2. MEMORY chain commitment
        commit = self.memory.commitment(meta["memory_id"])
        mem_block = self.chains["MEMORY"].add(commit)
        self.link_hub("MEMORY", mem_block, label="memory_commit")

        # 3. specialty job with pointer only
        job = dict(job)
        job["memory_id"] = meta["memory_id"]
        job["content_hash"] = meta["content_hash"]
        job_block = self.chains[specialty].add(job)
        self.link_hub(specialty, job_block, label=job.get("type", "job"))

        return {
            "memory_id": meta["memory_id"],
            "content_hash": meta["content_hash"],
            "memory_block": mem_block.index,
            "memory_hash": mem_block.hash,
            "job_block": job_block.index,
            "job_hash": job_block.hash,
            "specialty": specialty,
            "Z_memory": mem_block.maxwell["impedance"],
            "Z_job": job_block.maxwell["impedance"],
        }

    def fetch(self, memory_id: str) -> Optional[Any]:
        return self.memory.fetch(memory_id)

    def status(self):
        print("\n── Chains ──")
        for name, ch in self.chains.items():
            last = ch.blocks[-1]
            print(f"  {name:8} blocks={len(ch.blocks):2}  valid={ch.validate()}  "
                  f"Z={last.maxwell['impedance']:.3f}  hash={last.hash[:14]}…")
        print(f"\n── Memory Branch ── entries={len(self.memory.index)}  "
              f"dir={self.memory.root_dir}")


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    net = MaxwellMemoryNetwork(difficulty=3)

    print("\n── Store AI conversation off-chain, link on-chain ──")
    ai_full = {
        "prompt": "How does Maxwell bind quantum job commitments?",
        "response": "circuit_hash + result_commitment seed the Maxwell signature...",
        "model": "demo-llm",
    }
    ai_job = {
        "type": "ai_job",
        "model": "demo-llm",
        "prompt_hash": dhash(ai_full["prompt"]),
        "response_commitment": dhash(ai_full["response"]),
        "ts": ts(),
    }
    r1 = net.store_and_link(ai_full, ai_job, specialty="AI", tags=["ai", "llm"])
    print(f"  memory_id={r1['memory_id'][:18]}…  MEMORY#{r1['memory_block']}  AI#{r1['job_block']}")

    print("\n── Store quantum result off-chain, link on-chain ──")
    q_full = {
        "algorithm": "VQE",
        "energy_curve": [-1.0, -1.1, -1.136],
        "log": "full optimizer trace...",
    }
    q_job = {
        "type": "quantum_job",
        "algorithm": "VQE",
        "circuit_hash": dhash("UCCSD-H2"),
        "result_commitment": dhash({"energy": -1.136}),
        "ts": ts(),
    }
    r2 = net.store_and_link(q_full, q_job, specialty="QUANTUM", tags=["vqe", "quantum"])
    print(f"  memory_id={r2['memory_id'][:18]}…  MEMORY#{r2['memory_block']}  QUANTUM#{r2['job_block']}")

    print("\n── Store twin snapshot off-chain, link on-chain ──")
    twin_full = {"markers": {"coherence": 0.82, "stress": 0.18}, "note": "session dump"}
    twin_job = {
        "type": "twin_snapshot",
        "markers_hash": dhash(twin_full["markers"]),
        "ts": ts(),
    }
    r3 = net.store_and_link(twin_full, twin_job, specialty="TWIN", tags=["twin"])
    print(f"  memory_id={r3['memory_id'][:18]}…  MEMORY#{r3['memory_block']}  TWIN#{r3['job_block']}")

    net.status()

    print("\n── Fetch full AI data from Memory Branch ──")
    got = net.fetch(r1["memory_id"])
    if got:
        print(f"  prompt : {got['data']['prompt'][:56]}…")
        print(f"  model  : {got['data']['model']}")

    print("\nWritten into the chain:")
    print("  • Full data     → off-chain Memory Branch (files)")
    print("  • Commitment    → MEMORY chain (Maxwell-signed)")
    print("  • Job + pointer → AI / QUANTUM / TWIN chains")
    print("  • Discovery     → HUB cross-links")


if __name__ == "__main__":
    main()
