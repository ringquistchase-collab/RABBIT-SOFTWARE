#!/usr/bin/env python3
"""
Maxwell Inter-Network Discovery Layer
=====================================
Save as: maxwell_network_discovery.py
Run:     python3 maxwell_network_discovery.py

Links Maxwell chains to other chain networks so blocks can be discovered:
  • Local Maxwell multi-chain (HUB, MEMORY, AI, QUANTUM, …)
  • Foreign network registry (other Maxwell meshes / external chains)
  • Discovery records on a DISCOVERY specialty chain
  • Cross-network block pointers (network_id + chain_id + block_hash)
  • Hub index for global lookup
  • Maxwell signatures on every record

Digital twin / software simulation only.
"""

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

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
# Maxwell signature
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
# Block + Chain
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

    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "chain_id": self.chain_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "Z": self.maxwell["impedance"],
        }


class MaxwellChain:
    def __init__(self, chain_id: str, network_id: str, difficulty: int = 3):
        self.chain_id = chain_id
        self.network_id = network_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        genesis = {
            "type": "genesis",
            "chain": chain_id,
            "network": network_id,
        }
        b = MaxwellBlock(0, genesis, "0"*64, [0.0, 0.0, 0.0], chain_id, difficulty)
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

    def find_by_hash(self, block_hash: str) -> Optional[MaxwellBlock]:
        for b in self.blocks:
            if b.hash == block_hash or b.hash.startswith(block_hash):
                return b
        return None


# ──────────────────────────────────────────────────────────────
# Foreign / peer network registry
# ──────────────────────────────────────────────────────────────

class NetworkRegistry:
    """
    Registry of other chain networks Maxwell can link to.
    Each entry is a discoverable peer network (id, endpoint, chains).
    """

    def __init__(self):
        self.networks: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        network_id: str,
        label: str,
        endpoint: str = "",
        chains: Optional[List[str]] = None,
        meta: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        entry = {
            "network_id": network_id,
            "label": label,
            "endpoint": endpoint or f"mesh://{network_id}",
            "chains": chains or [],
            "meta": meta or {},
            "registered_at": ts(),
        }
        self.networks[network_id] = entry
        return entry

    def list(self) -> List[Dict[str, Any]]:
        return list(self.networks.values())

    def get(self, network_id: str) -> Optional[Dict[str, Any]]:
        return self.networks.get(network_id)


# ──────────────────────────────────────────────────────────────
# Discovery pointer (how blocks are found across networks)
# ──────────────────────────────────────────────────────────────

def make_discovery_pointer(
    target_network: str,
    target_chain: str,
    target_block_hash: str,
    target_index: int,
    local_chain: str,
    local_block_hash: str,
    purpose: str = "cross_network_link",
) -> Dict[str, Any]:
    """
    A discovery pointer is the on-chain object that lets any node
    find a block on another network/chain.
    """
    return {
        "type": "discovery_pointer",
        "purpose": purpose,
        "target": {
            "network_id": target_network,
            "chain_id": target_chain,
            "block_hash": target_block_hash,
            "block_index": target_index,
        },
        "local": {
            "chain_id": local_chain,
            "block_hash": local_block_hash,
        },
        "pointer_id": dhash({
            "tn": target_network,
            "tc": target_chain,
            "th": target_block_hash,
            "lh": local_block_hash,
        })[:24],
        "ts": ts(),
    }


# ──────────────────────────────────────────────────────────────
# Maxwell Network (local) + inter-network discovery
# ──────────────────────────────────────────────────────────────

class MaxwellNetwork:
    def __init__(self, network_id: str = "maxwell_alpha", difficulty: int = 3):
        self.network_id = network_id
        self.difficulty = difficulty
        self.registry = NetworkRegistry()
        self.chains: Dict[str, MaxwellChain] = {}
        for name in ["HUB", "DISCOVERY", "MEMORY", "AI", "QUANTUM"]:
            self.chains[name] = MaxwellChain(name, network_id, difficulty)
        # register self
        self.registry.register(
            network_id,
            label=f"Local Maxwell network {network_id}",
            endpoint=f"mesh://{network_id}",
            chains=list(self.chains.keys()),
        )
        print("=" * 66)
        print(f"MAXWELL NETWORK  id={network_id}")
        print("Inter-network discovery · DISCOVERY chain · HUB index")
        print("=" * 66)

    def add_block(self, chain_id: str, payload: Dict) -> MaxwellBlock:
        if chain_id not in self.chains:
            chain_id = "HUB"
        block = self.chains[chain_id].add(payload)
        # always index on HUB for local discovery
        if chain_id != "HUB":
            self.chains["HUB"].add({
                "type": "local_index",
                "from_chain": chain_id,
                "block_index": block.index,
                "block_hash": block.hash,
                "payload_type": payload.get("type"),
                "ts": ts(),
            })
        return block

    def register_foreign_network(
        self,
        network_id: str,
        label: str,
        endpoint: str = "",
        chains: Optional[List[str]] = None,
    ) -> MaxwellBlock:
        """Register another chain network so its blocks can be linked/discovered."""
        entry = self.registry.register(network_id, label, endpoint, chains)
        # on-chain registry record
        block = self.add_block("DISCOVERY", {
            "type": "network_register",
            "foreign_network": entry,
            "ts": ts(),
        })
        return block

    def link_foreign_block(
        self,
        foreign_network: str,
        foreign_chain: str,
        foreign_block_hash: str,
        foreign_index: int,
        local_chain: str = "HUB",
        purpose: str = "cross_network_link",
    ) -> MaxwellBlock:
        """
        Write a discovery pointer so a foreign block can be found
        from this Maxwell network.
        """
        # placeholder local anchor (hub tip)
        local_tip = self.chains[local_chain].blocks[-1].hash
        pointer = make_discovery_pointer(
            target_network=foreign_network,
            target_chain=foreign_chain,
            target_block_hash=foreign_block_hash,
            target_index=foreign_index,
            local_chain=local_chain,
            local_block_hash=local_tip,
            purpose=purpose,
        )
        block = self.add_block("DISCOVERY", pointer)
        return block

    def discover(
        self,
        network_id: Optional[str] = None,
        chain_id: Optional[str] = None,
        block_hash_prefix: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search DISCOVERY + HUB for pointers / index entries.
        This is how blocks are discovered across networks.
        """
        hits = []
        for ch_name in ("DISCOVERY", "HUB"):
            for b in self.chains[ch_name].blocks:
                p = b.payload
                if p.get("type") == "discovery_pointer":
                    t = p.get("target", {})
                    if network_id and t.get("network_id") != network_id:
                        continue
                    if chain_id and t.get("chain_id") != chain_id:
                        continue
                    if block_hash_prefix and not str(t.get("block_hash", "")).startswith(block_hash_prefix):
                        continue
                    hits.append({
                        "source": "DISCOVERY",
                        "discovery_block": b.index,
                        "discovery_hash": b.hash,
                        "pointer": p,
                    })
                elif p.get("type") == "local_index":
                    if network_id and network_id != self.network_id:
                        continue
                    if chain_id and p.get("from_chain") != chain_id:
                        continue
                    if block_hash_prefix and not str(p.get("block_hash", "")).startswith(block_hash_prefix):
                        continue
                    hits.append({
                        "source": "HUB",
                        "index_block": b.index,
                        "entry": p,
                    })
                elif p.get("type") == "network_register":
                    fn = p.get("foreign_network", {})
                    if network_id and fn.get("network_id") != network_id:
                        continue
                    hits.append({
                        "source": "DISCOVERY",
                        "registry_block": b.index,
                        "network": fn,
                    })
        return hits

    def status(self):
        print(f"\n── Network {self.network_id} ──")
        for name, ch in self.chains.items():
            last = ch.blocks[-1]
            print(f"  {name:10} blocks={len(ch.blocks):2}  valid={ch.validate()}  "
                  f"Z={last.maxwell['impedance']:.3f}")
        print(f"  foreign networks registered: {len(self.registry.networks) - 1}")


# ──────────────────────────────────────────────────────────────
# Demo: two networks linked for discovery
# ──────────────────────────────────────────────────────────────

def main():
    # Local Maxwell network
    alpha = MaxwellNetwork("maxwell_alpha", difficulty=3)

    # Register other chain networks (simulated peers)
    print("\n── Register foreign networks ──")
    alpha.register_foreign_network(
        "maxwell_beta",
        label="Peer Maxwell mesh (beta)",
        endpoint="mesh://maxwell_beta",
        chains=["HUB", "SHOR", "VQE"],
    )
    alpha.register_foreign_network(
        "ext_research_net",
        label="External research ledger",
        endpoint="https://research.example/chain",
        chains=["main", "results"],
    )
    alpha.register_foreign_network(
        "quantum_lab_net",
        label="Lab quantum job ledger",
        endpoint="mesh://quantum_lab",
        chains=["jobs", "calibration"],
    )
    print("  registered: maxwell_beta, ext_research_net, quantum_lab_net")

    # Local activity
    print("\n── Local blocks ──")
    b1 = alpha.add_block("AI", {
        "type": "ai_job",
        "model": "demo-llm",
        "prompt_hash": dhash("explain discovery"),
        "ts": ts(),
    })
    b2 = alpha.add_block("QUANTUM", {
        "type": "quantum_job",
        "algorithm": "VQE",
        "circuit_hash": dhash("UCCSD"),
        "ts": ts(),
    })
    print(f"  AI#{b1.index} {b1.hash[:14]}…")
    print(f"  QUANTUM#{b2.index} {b2.hash[:14]}…")

    # Link to foreign blocks (so they can be discovered from alpha)
    print("\n── Cross-network discovery pointers ──")
    # Simulated foreign block hashes
    foreign_links = [
        ("maxwell_beta", "SHOR", "beta_shor_abc123def456", 3),
        ("maxwell_beta", "VQE", "beta_vqe_789xyz000111", 5),
        ("ext_research_net", "results", "ext_res_555aaa666bbb", 12),
        ("quantum_lab_net", "jobs", "lab_job_cccddd12eeff", 8),
    ]
    for net_id, ch, fhash, idx in foreign_links:
        ptr = alpha.link_foreign_block(net_id, ch, fhash, idx, purpose="discover_foreign_block")
        print(f"  DISCOVERY#{ptr.index} → {net_id}/{ch} #{idx} {fhash[:16]}…")

    # Discovery queries
    print("\n── Discover: all pointers to maxwell_beta ──")
    for hit in alpha.discover(network_id="maxwell_beta"):
        if "pointer" in hit:
            t = hit["pointer"]["target"]
            print(f"  {t['network_id']}/{t['chain_id']} #{t['block_index']}  "
                  f"hash={t['block_hash'][:18]}…  via DISCOVERY#{hit['discovery_block']}")

    print("\n── Discover: local QUANTUM blocks via HUB index ──")
    for hit in alpha.discover(chain_id="QUANTUM"):
        if "entry" in hit:
            e = hit["entry"]
            print(f"  local {e['from_chain']} #{e['block_index']}  hash={e['block_hash'][:18]}…")

    print("\n── Discover: registered foreign networks ──")
    for hit in alpha.discover():
        if "network" in hit:
            n = hit["network"]
            print(f"  {n.get('network_id')}  endpoint={n.get('endpoint')}  "
                  f"chains={n.get('chains')}")

    alpha.status()

    print("\nHow discovery works:")
    print("  1. Register foreign networks on DISCOVERY chain")
    print("  2. Write discovery_pointer blocks (network + chain + block_hash)")
    print("  3. HUB indexes local blocks")
    print("  4. discover(network, chain, hash_prefix) finds them")
    print("  Other networks can mirror the same pattern to find Maxwell blocks.")


if __name__ == "__main__":
    main()
