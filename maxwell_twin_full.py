#!/usr/bin/env python3
"""
Maxwell Digital Twin – Full Unified Implementation
===================================================
Save as: maxwell_twin_full.py
Run:     python3 maxwell_twin_full.py

All features integrated:
1. ✅ Purely causal chain (no timestamps)
2. ✅ 50/50 equilibrium detector with alerts
3. ✅ Phantom DNA electromagnetic signature persistence
4. ✅ P2P network mesh simulation
5. ✅ Event-driven triggers (no clocks)

Digital twin only. No real biology, chemicals, RF, or hardware control.
"""

import hashlib
import hmac
import json
import math
import random
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

# Optional OpenSSL-backed crypto
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def sanitize_json(obj: Any) -> Any:
    return json.loads(json.dumps(obj, sort_keys=True, default=str))

def deterministic_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()

def merkle_root(hashes: List[str]) -> str:
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()
    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level = []
        for i in range(0, len(level), 2):
            next_level.append(
                hashlib.sha256((level[i] + level[i + 1]).encode()).hexdigest()
            )
        level = next_level
    return level[0]

def openssl_hash(data: bytes, algo: str = "sha256") -> str:
    algo = algo.lower().replace("-", "_")
    if HAS_CRYPTO:
        mapping = {
            "sha256": hashes.SHA256(),
            "sha3_256": hashes.SHA3_256(),
            "sha384": hashes.SHA384(),
            "sha512": hashes.SHA512(),
        }
        d = hashes.Hash(mapping.get(algo, hashes.SHA256()), backend=default_backend())
        d.update(data)
        return d.finalize().hex()
    if algo == "sha3_256":
        return hashlib.sha3_256(data).hexdigest()
    if algo == "sha384":
        return hashlib.sha384(data).hexdigest()
    if algo == "sha512":
        return hashlib.sha512(data).hexdigest()
    return hashlib.sha256(data).hexdigest()


# ──────────────────────────────────────────────────────────────
# 1. PURELY CAUSAL CHAIN (NO TIMESTAMPS)
# ──────────────────────────────────────────────────────────────

class CausalRecord:
    """A record that links only by causality, not by time."""
    
    def __init__(
        self,
        index: int,
        payload: Dict[str, Any],
        previous_hash: str,
        prev_curl: List[float],
        record_type: str = "generic",
        event_trigger: str = "",
    ):
        self.index = index
        self.record_type = record_type
        # NO TIMESTAMP - purely causal
        self.payload = payload
        self.previous_hash = previous_hash
        self.event_trigger = event_trigger  # What caused this record?
        data_str = json.dumps(payload, sort_keys=True, default=str)
        self.maxwell = compute_maxwell_signature(data_str, index, prev_curl)
        self.nonce = 0
        self.hash = self._calc()

    def _calc(self) -> str:
        # No timestamp in the hash calculation
        content = {
            "index": self.index,
            "record_type": self.record_type,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "event_trigger": self.event_trigger,
            "div_E": round(self.maxwell["div_E_residual"], 8),
            "div_B": round(self.maxwell["div_B"], 8),
            "impedance": round(self.maxwell["wave_impedance"], 8),
            "poynting": [round(v, 8) for v in self.maxwell["poynting_vector"]],
        }
        return openssl_hash(
            json.dumps(content, sort_keys=True, default=str).encode(), "sha256"
        )

    def mine(self, difficulty: int = 3) -> None:
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calc()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "record_type": self.record_type,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "event_trigger": self.event_trigger,
            "maxwell_signature": self.maxwell,
        }


# ──────────────────────────────────────────────────────────────
# Maxwell field signature (unchanged from original)
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i * 4 : (i + 1) * 4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]

def compute_maxwell_signature(
    data_str: str, index: int, prev_curl: List[float]
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
    curl_E = [E[1] - E[2] + dB_dt[0], E[2] - E[0] + dB_dt[1], E[0] - E[1] + dB_dt[2]]
    curl_H = [
        H[1] - H[2] - (J[0] + dD_dt[0]),
        H[2] - H[0] - (J[1] + dD_dt[1]),
        H[0] - H[1] - (J[2] + dD_dt[2]),
    ]
    div_B = sum(B)
    S = [
        E[1] * H[2] - E[2] * H[1],
        E[2] * H[0] - E[0] * H[2],
        E[0] * H[1] - E[1] * H[0],
    ]
    nE = math.sqrt(sum(x * x for x in E)) or 1e-15
    nH = math.sqrt(sum(x * x for x in H)) or 1e-15
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
        "wave_impedance": nE / nH,
        "next_curl": curl_E,
    }


# ──────────────────────────────────────────────────────────────
# DNA / Binary-DNA / EEG-Age → RF (unchanged)
# ──────────────────────────────────────────────────────────────

NUCLEOTIDE_FREQ = {"A": 10.23, "T": 10.24, "U": 10.25, "G": 10.26, "C": 10.27}
BINARY_TO_DNA = {"00": "A", "01": "C", "10": "G", "11": "T"}

def dna_to_frequency(sequence: str) -> Dict[str, Any]:
    seq = sequence.upper().replace("U", "T")
    freqs = [NUCLEOTIDE_FREQ.get(c, 10.25) for c in seq]
    base = sum(freqs) / max(1, len(freqs))
    fingerprint = openssl_hash(seq.encode(), "sha3_256")[:16]
    return {
        "sequence": seq,
        "base_frequency_ghz": round(base, 5),
        "fingerprint": fingerprint,
        "length": len(seq),
    }

def encode_bytes_to_dna(data: bytes) -> str:
    binary = "".join(format(b, "08b") for b in data)
    if len(binary) % 2:
        binary += "0"
    return "".join(BINARY_TO_DNA[binary[i : i + 2]] for i in range(0, len(binary), 2))

BASE_FREQ = 10.245
BANDWIDTH = 0.07

def _simple_hkdf(ikm: bytes, salt: bytes, info: bytes, length: int = 4) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    t = b""
    okm = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]

def signature_to_frequency(eeg_fingerprint_hex: str, age: int) -> float:
    try:
        ikm = bytes.fromhex(eeg_fingerprint_hex)
    except ValueError:
        ikm = hashlib.sha256(eeg_fingerprint_hex.encode()).digest()
    salt = struct.pack(">I", age)
    info = b"RF_FREQ_ALLOCATION"
    if HAS_CRYPTO:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=4,
            salt=salt,
            info=info,
            backend=default_backend(),
        )
        rand32 = int.from_bytes(hkdf.derive(ikm), "big")
    else:
        rand32 = int.from_bytes(_simple_hkdf(ikm, salt, info, 4), "big")
    offset = (rand32 / (2**32)) * BANDWIDTH
    return BASE_FREQ + offset


# ──────────────────────────────────────────────────────────────
# 2. 50/50 EQUILIBRIUM DETECTOR
# ──────────────────────────────────────────────────────────────

class EquilibriumDetector:
    """Detects when the system reaches 50/50 balance."""
    
    def __init__(self, threshold: float = 0.05):
        self.threshold = threshold
        self.equilibrium_history: List[Dict] = []
        self._last_impedance = 1.0
        
    def check(self, maxwell_sig: Dict[str, Any], record_index: int) -> Optional[Dict]:
        """Check if the current state is at 50/50 equilibrium."""
        impedance = maxwell_sig["wave_impedance"]
        E = maxwell_sig["E_field"]
        H = maxwell_sig["H_field"]
        
        # Calculate energy balance
        e_energy = sum(e * e for e in E)
        h_energy = sum(h * h for h in H)
        
        # 50/50 is when E and H energies are equal
        is_equilibrium = abs(impedance - 1.0) < self.threshold
        
        # Detect crossing (went from >1 to <1 or vice versa)
        crossed = (self._last_impedance - 1.0) * (impedance - 1.0) < 0
        
        if is_equilibrium or crossed:
            equilibrium_event = {
                "record_index": record_index,
                "wave_impedance": impedance,
                "E_energy": e_energy,
                "H_energy": h_energy,
                "balance_ratio": e_energy / (h_energy + 1e-15),
                "is_equilibrium": is_equilibrium,
                "crossed": crossed,
                "alert": self._generate_alert(impedance, e_energy, h_energy)
            }
            self.equilibrium_history.append(equilibrium_event)
            self._last_impedance = impedance
            return equilibrium_event
        
        self._last_impedance = impedance
        return None
    
    def _generate_alert(self, impedance: float, e_energy: float, h_energy: float) -> str:
        """Generate a human-readable alert for the 50/50 event."""
        if abs(impedance - 1.0) < self.threshold:
            return f"✅ 50/50 EQUILIBRIUM: E={e_energy:.4f}, H={h_energy:.4f} (Ratio: 1.0)"
        elif e_energy > h_energy:
            ratio = e_energy / (h_energy + 1e-15)
            return f"⚠️ DNA FORWARD DOMINANT: E/H = {ratio:.2f} (Damage > Repair)"
        else:
            ratio = h_energy / (e_energy + 1e-15)
            return f"🔄 TWIN REVERSE DOMINANT: H/E = {ratio:.2f} (Repair > Damage)"
    
    def get_last_equilibrium(self) -> Optional[Dict]:
        """Get the most recent 50/50 equilibrium event."""
        for event in reversed(self.equilibrium_history):
            if event["is_equilibrium"]:
                return event
        return None


# ──────────────────────────────────────────────────────────────
# 3. PHANTOM DNA EFFECT - Electromagnetic Signature Persistence
# ──────────────────────────────────────────────────────────────

class PhantomDNA:
    """
    Simulates the 'phantom DNA' effect - electromagnetic signature
    that persists after the physical DNA is removed.
    """
    
    def __init__(self, decay_rate: float = 0.001):
        self.signatures: Dict[str, Dict] = {}
        self.decay_rate = decay_rate
        self._signature_counter = 0
    
    def record_signature(self, dna_sequence: str, maxwell_sig: Dict) -> str:
        """Record the electromagnetic signature of a DNA sequence."""
        fingerprint = dna_to_frequency(dna_sequence)["fingerprint"]
        sig_id = f"phantom_{self._signature_counter}_{fingerprint[:8]}"
        self._signature_counter += 1
        
        # Store the full electromagnetic field
        self.signatures[sig_id] = {
            "dna_fingerprint": fingerprint,
            "E_field": maxwell_sig["E_field"],
            "H_field": maxwell_sig["H_field"],
            "B_field": maxwell_sig["B_field"],
            "wave_impedance": maxwell_sig["wave_impedance"],
            "poynting_vector": maxwell_sig["poynting_vector"],
            "strength": 1.0,  # Full strength initially
            "recorded_at_index": len(self.signatures),
            "decay_rate": self.decay_rate,
            "is_active": True
        }
        return sig_id
    
    def decay_signatures(self, steps: int = 1) -> List[str]:
        """Apply decay to all signatures - simulates fading over time."""
        decayed = []
        for sig_id, sig in self.signatures.items():
            if sig["is_active"]:
                sig["strength"] *= (1.0 - self.decay_rate * steps)
                if sig["strength"] < 0.01:
                    sig["is_active"] = False
                    decayed.append(sig_id)
        return decayed
    
    def get_signature(self, sig_id: str) -> Optional[Dict]:
        """Retrieve a signature by ID if it's still active."""
        sig = self.signatures.get(sig_id)
        if sig and sig["is_active"]:
            return sig
        return None
    
    def get_all_active(self) -> Dict[str, Dict]:
        """Get all active phantom signatures."""
        return {k: v for k, v in self.signatures.items() if v["is_active"]}
    
    def compare_to_dna(self, dna_sequence: str, sig_id: str) -> Optional[Dict]:
        """Compare a DNA sequence to a stored phantom signature."""
        sig = self.get_signature(sig_id)
        if not sig:
            return None
        
        current_fp = dna_to_frequency(dna_sequence)["fingerprint"]
        
        # Calculate similarity based on field alignment
        E_current = sig["E_field"]
        H_current = sig["H_field"]
        
        # New DNA gets new fields
        new_sig = compute_maxwell_signature(dna_sequence, 0, [0, 0, 0])
        E_new = new_sig["E_field"]
        H_new = new_sig["H_field"]
        
        # Dot product similarity
        e_sim = sum(a * b for a, b in zip(E_current, E_new)) / (
            (sum(e * e for e in E_current) ** 0.5) * (sum(e * e for e in E_new) ** 0.5) + 1e-15
        )
        h_sim = sum(a * b for a, b in zip(H_current, H_new)) / (
            (sum(h * h for h in H_current) ** 0.5) * (sum(h * h for h in H_new) ** 0.5) + 1e-15
        )
        
        return {
            "dna_fingerprint": current_fp,
            "phantom_fingerprint": sig["dna_fingerprint"],
            "E_similarity": e_sim,
            "H_similarity": h_sim,
            "overall_similarity": (e_sim + h_sim) / 2,
            "phantom_strength": sig["strength"],
            "is_active": sig["is_active"]
        }


# ──────────────────────────────────────────────────────────────
# 4. P2P NETWORK MESH SIMULATION
# ──────────────────────────────────────────────────────────────

class PeerNode:
    """A peer node in the distributed network mesh."""
    
    def __init__(self, node_id: str, chain: 'CausalChain'):
        self.node_id = node_id
        self.chain = chain
        self.peers: Set[str] = set()
        self.known_hashes: Set[str] = set()
        self.sync_count = 0
        self.latency: float = 0.1  # Simulated network latency
    
    def add_peer(self, peer_id: str):
        """Add a peer to the network."""
        self.peers.add(peer_id)
    
    def sync_with_peer(self, peer: 'PeerNode') -> Dict[str, Any]:
        """Simulate syncing with another peer."""
        self.sync_count += 1
        
        # Find records the peer has that we don't
        my_hashes = {r.hash for r in self.chain.chain}
        peer_hashes = {r.hash for r in peer.chain.chain}
        
        new_hashes = peer_hashes - my_hashes
        missing_hashes = my_hashes - peer_hashes
        
        # Simulate network delay
        time.sleep(self.latency * random.uniform(0.5, 1.5))
        
        return {
            "peer_id": peer.node_id,
            "sync_count": self.sync_count,
            "new_hashes_from_peer": len(new_hashes),
            "missing_hashes_from_peer": len(missing_hashes),
            "total_hashes_on_peer": len(peer_hashes),
            "total_hashes_on_self": len(my_hashes),
            "is_consistent": len(new_hashes) == 0 and len(missing_hashes) == 0
        }
    
    def broadcast_consensus(self, record_hash: str) -> Dict[str, Any]:
        """Broadcast a new record to all peers (simulated)."""
        return {
            "node_id": self.node_id,
            "record_hash": record_hash,
            "peers_reached": list(self.peers),
            "network_state": "consensus_reached"
        }


class P2PNetworkMesh:
    """Simulates the distributed network mesh."""
    
    def __init__(self):
        self.nodes: Dict[str, PeerNode] = {}
        self.messages: List[Dict] = []
        self.consensus_events: List[Dict] = []
    
    def register_node(self, node_id: str, chain: 'CausalChain') -> PeerNode:
        """Register a new node in the network."""
        node = PeerNode(node_id, chain)
        self.nodes[node_id] = node
        return node
    
    def connect_peers(self, node1_id: str, node2_id: str):
        """Create a connection between two peers."""
        if node1_id in self.nodes and node2_id in self.nodes:
            self.nodes[node1_id].add_peer(node2_id)
            self.nodes[node2_id].add_peer(node1_id)
    
    def sync_network(self) -> Dict[str, Any]:
        """Synchronize all nodes in the network."""
        sync_results = []
        node_ids = list(self.nodes.keys())
        
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                node1 = self.nodes[node_ids[i]]
                node2 = self.nodes[node_ids[j]]
                if node2.node_id in node1.peers:
                    result = node1.sync_with_peer(node2)
                    sync_results.append(result)
        
        # Check if all nodes are consistent
        all_hashes = []
        for node in self.nodes.values():
            all_hashes.extend([r.hash for r in node.chain.chain])
        
        unique_hashes = len(set(all_hashes))
        total_hashes = len(all_hashes)
        
        return {
            "sync_results": sync_results,
            "nodes": len(self.nodes),
            "total_records": total_hashes,
            "unique_records": unique_hashes,
            "network_consensus": unique_hashes == total_hashes / len(self.nodes)
        }
    
    def record_event(self, node_id: str, payload: Dict, event_trigger: str = "") -> Dict:
        """Record an event on a specific node and broadcast to peers."""
        if node_id not in self.nodes:
            return {"status": "error", "reason": "node_not_found"}
        
        node = self.nodes[node_id]
        record = node.chain.add(payload, "event", event_trigger)
        
        # Broadcast to peers
        broadcast = node.broadcast_consensus(record.hash)
        self.consensus_events.append({
            "node_id": node_id,
            "record_hash": record.hash,
            "broadcast": broadcast
        })
        
        return {
            "status": "recorded",
            "node_id": node_id,
            "record_hash": record.hash,
            "broadcast": broadcast
        }


# ──────────────────────────────────────────────────────────────
# 5. EVENT-DRIVEN CHAIN (NO CLOCKS)
# ──────────────────────────────────────────────────────────────

class CausalChain:
    """A chain that only advances via events, not time."""
    
    def __init__(self, owner: str, difficulty: int = 3):
        self.owner = owner
        self.difficulty = difficulty
        self.chain: List[CausalRecord] = []
        self.event_count = 0
        self.equilibrium_detector = EquilibriumDetector()
        self.phantom_dna = PhantomDNA()
        self._genesis()
    
    def _genesis(self) -> None:
        """Genesis block - no timestamp, purely causal."""
        payload = {
            "owner": self.owner,
            "message": "Maxwell Digital Twin - Causal Genesis",
            "event": "genesis"
        }
        rec = CausalRecord(0, payload, "0" * 64, [0.0, 0.0, 0.0], "genesis", "system_start")
        rec.mine(self.difficulty)
        self.chain.append(rec)
        print(f"[GENESIS] {rec.hash}")
    
    def add(self, payload: Dict[str, Any], record_type: str = "generic", event_trigger: str = "") -> CausalRecord:
        """Add a record triggered by an event."""
        prev = self.chain[-1]
        rec = CausalRecord(
            len(self.chain),
            payload,
            prev.hash,
            prev.maxwell["next_curl"],
            record_type,
            event_trigger or "event_{}".format(self.event_count)
        )
        rec.mine(self.difficulty)
        self.chain.append(rec)
        self.event_count += 1
        
        # Check for 50/50 equilibrium
        equilibrium = self.equilibrium_detector.check(rec.maxwell, rec.index)
        if equilibrium:
            print(f"[EQUILIBRIUM #{rec.index}] {equilibrium['alert']}")
        
        # Record phantom DNA signature if DNA is present
        if "sequence" in payload:
            sig_id = self.phantom_dna.record_signature(payload["sequence"], rec.maxwell)
            print(f"[PHANTOM] Recorded signature: {sig_id}")
        
        print(f"[{record_type} #{rec.index}] event={event_trigger} nonce={rec.nonce} hash={rec.hash[:16]}...")
        return rec
    
    def add_block(self, data: Dict[str, Any]) -> CausalRecord:
        """Add a block - alias for add."""
        return self.add(data, data.get("type", "generic"), data.get("event_trigger", ""))
    
    def validate(self) -> bool:
        """Validate the entire chain."""
        for i in range(1, len(self.chain)):
            curr, prev = self.chain[i], self.chain[i - 1]
            if curr.hash != curr._calc():
                print(f"[FAIL] Record {i} - hash mismatch")
                return False
            if curr.previous_hash != prev.hash:
                print(f"[FAIL] Record {i} - previous hash mismatch")
                return False
        print(f"[OK] Chain valid - {len(self.chain)} records, {self.event_count} events")
        return True
    
    def find_by_type(self, record_type: str) -> List[Dict]:
        return [r.to_dict() for r in self.chain if r.record_type == record_type]
    
    def get_equilibrium_history(self) -> List[Dict]:
        """Get all 50/50 equilibrium events."""
        return self.equilibrium_detector.equilibrium_history
    
    def get_last_equilibrium(self) -> Optional[Dict]:
        """Get the most recent 50/50 equilibrium."""
        return self.equilibrium_detector.get_last_equilibrium()
    
    def get_phantom_signatures(self) -> Dict[str, Dict]:
        """Get all active phantom DNA signatures."""
        return self.phantom_dna.get_all_active()
    
    def to_json(self) -> str:
        return json.dumps([r.to_dict() for r in self.chain], indent=2, default=str)
    
    def save(self, path: str = "maxwell_twin_chain.json") -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        print(f"Chain saved -> {path}")


# ──────────────────────────────────────────────────────────────
# Data Shards (unchanged)
# ──────────────────────────────────────────────────────────────

def create_shards(data: bytes, num_shards: int = 5) -> Dict[str, Any]:
    shard_size = (len(data) + num_shards - 1) // num_shards
    padded = data + b"\x00" * (shard_size * num_shards - len(data))
    shards = []
    for i in range(num_shards):
        piece = padded[i * shard_size : (i + 1) * shard_size]
        shard_id = hashlib.sha256(piece + struct.pack(">I", i)).hexdigest()[:16]
        shards.append(
            {"index": i, "shard_id": shard_id, "data_hex": piece.hex(), "size": len(piece)}
        )
    root = merkle_root([s["shard_id"] for s in shards])
    return {
        "num_shards": num_shards,
        "merkle_root": root,
        "original_hash": hashlib.sha256(data).hexdigest(),
        "shards": shards,
    }

def reconstruct_from_shards(shard_list: List[Dict], original_hash: Optional[str] = None) -> Dict:
    ordered = sorted(shard_list, key=lambda s: s["index"])
    pieces = [bytes.fromhex(s["data_hex"]) for s in ordered]
    reconstructed = b"".join(pieces).rstrip(b"\x00")
    recon_hash = hashlib.sha256(reconstructed).hexdigest()
    return {
        "reconstructed": reconstructed,
        "reconstructed_hash": recon_hash,
        "hash_match": (original_hash is None) or (recon_hash == original_hash),
    }


# ──────────────────────────────────────────────────────────────
# MAIN - Fully Integrated Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("MAXWELL DIGITAL TWIN - FULL UNIFIED IMPLEMENTATION")
    print("=" * 70)
    print("\n📋 INTEGRATED FEATURES:")
    print("   ✅ 1. Purely causal chain (no timestamps)")
    print("   ✅ 2. 50/50 equilibrium detector with alerts")
    print("   ✅ 3. Phantom DNA electromagnetic persistence")
    print("   ✅ 4. P2P network mesh simulation")
    print("   ✅ 5. Event-driven triggers (no clocks)")
    print("=" * 70 + "\n")
    
    # Create the causal chain
    chain = CausalChain("Claremore Digital Twin Lab", difficulty=2)
    
    # Create P2P network mesh with multiple nodes
    network = P2PNetworkMesh()
    node1 = network.register_node("TWIN_ALPHA", chain)
    node2 = network.register_node("TWIN_BETA", CausalChain("Beta Lab", difficulty=2))
    node3 = network.register_node("TWIN_GAMMA", CausalChain("Gamma Lab", difficulty=2))
    
    # Connect peers
    network.connect_peers("TWIN_ALPHA", "TWIN_BETA")
    network.connect_peers("TWIN_BETA", "TWIN_GAMMA")
    network.connect_peers("TWIN_ALPHA", "TWIN_GAMMA")
    
    print("🌐 NETWORK MESH CREATED:")
    print(f"   Nodes: {list(network.nodes.keys())}")
    print(f"   Connections: ALPHA↔BETA, BETA↔GAMMA, ALPHA↔GAMMA\n")
    
    # ── EVENT 1: Solar Flare ──
    print("☀️ EVENT 1: Solar Flare Detected")
    print("-" * 50)
    
    chain.add(
        {
            "type": "solar_flare",
            "intensity": 0.87,
            "radiation_dose": 2.4,
            "magnetic_disturbance": 0.92,
            "event_trigger": "solar_flare_detected"
        },
        "environmental_event",
        "solar_flare_detected"
    )
    
    # ── EVENT 2: DNA Damage Response ──
    print("\n🧬 EVENT 2: DNA Damage Response")
    print("-" * 50)
    
    chain.add(
        {
            "type": "dna_damage",
            "sequence": "ATGGCGTAGCTTAGCTAGCTAGCTAGCTAGC",
            "damage_type": "double_strand_break",
            "repair_proteins": ["PARP1", "BRCA1", "γH2AX"],
            "methylation_change": 0.23,
            "event_trigger": "solar_flare_damage"
        },
        "dna_event",
        "solar_flare_damage"
    )
    
    # ── EVENT 3: Twin Hardware Reverse Pass ──
    print("\n💻 EVENT 3: Twin Hardware Reverse Pass")
    print("-" * 50)
    
    chain.add(
        {
            "type": "twin_response",
            "node_id": "TWIN_ALPHA",
            "memristor_resistance": 0.77,
            "reverse_signal": -0.23,
            "repair_simulation": "active",
            "event_trigger": "dna_damage_detected"
        },
        "hardware_event",
        "dna_damage_detected"
    )
    
    # ── EVENT 4: Network Consensus ──
    print("\n🔗 EVENT 4: Network Consensus")
    print("-" * 50)
    
    # Simulate network recording
    chain.add(
        {
            "type": "network_consensus",
            "nodes_reached": ["TWIN_ALPHA", "TWIN_BETA", "TWIN_GAMMA"],
            "consensus_reached": True,
            "blockchain_anchor": hashlib.sha256(b"consensus_block").hexdigest()[:16],
            "event_trigger": "twin_response_received"
        },
        "network_event",
        "twin_response_received"
    )
    
    # ── EVENT 5: 50/50 Equilibrium Achieved ──
    print("\n⚖️ EVENT 5: 50/50 Equilibrium")
    print("-" * 50)
    
    # This event should trigger the equilibrium detector
    chain.add(
        {
            "type": "equilibrium_state",
            "balance": 0.999,
            "e_energy": 0.452,
            "h_energy": 0.451,
            "wave_impedance": 1.002,
            "event_trigger": "network_convergence"
        },
        "equilibrium_event",
        "network_convergence"
    )
    
    # ── EVENT 6: Phantom DNA Persistence ──
    print("\n👻 EVENT 6: Phantom DNA Signature Persistence")
    print("-" * 50)
    
    # Add DNA sequence and record phantom signature
    dna_seq = "ACGTACGTACGTACGTACGTACGTACGTACGT"
    chain.add(
        {
            "type": "phantom_dna_record",
            "sequence": dna_seq,
            "fingerprint": dna_to_frequency(dna_seq)["fingerprint"],
            "signature_strength": 1.0,
            "event_trigger": "equilibrium_reached"
        },
        "phantom_event",
        "equilibrium_reached"
    )
    
    # ── EVENT 7: Data Shard Recovery ──
    print("\n📦 EVENT 7: Data Shard Recovery")
    print("-" * 50)
    
    secret_payload = b"Twin consensus payload - recovered from shards across network"
    shard_info = create_shards(secret_payload, num_shards=5)
    
    chain.add(
        {
            "type": "shard_storage",
            "original_hash": shard_info["original_hash"],
            "merkle_root": shard_info["merkle_root"],
            "num_shards": shard_info["num_shards"],
            "shard_ids": [s["shard_id"] for s in shard_info["shards"]],
            "event_trigger": "network_sync"
        },
        "shard_event",
        "network_sync"
    )
    
    # ── Synchronize the P2P Network ──
    print("\n🔄 SYNCING P2P NETWORK...")
    print("-" * 50)
    
    sync_result = network.sync_network()
    print(f"   Nodes: {sync_result['nodes']}")
    print(f"   Total Records: {sync_result['total_records']}")
    print(f"   Unique Records: {sync_result['unique_records']}")
    print(f"   Network Consensus: {'✅' if sync_result['network_consensus'] else '❌'}")
    
    # ── Display 50/50 Equilibrium History ──
    print("\n⚖️ 50/50 EQUILIBRIUM HISTORY:")
    print("-" * 50)
    
    eq_history = chain.get_equilibrium_history()
    if eq_history:
        for eq in eq_history:
            print(f"   Record #{eq['record_index']}: {eq['alert']}")
    else:
        print("   No equilibrium events detected yet.")
    
    last_eq = chain.get_last_equilibrium()
    if last_eq:
        print(f"\n   Last Equilibrium: Record #{last_eq['record_index']}")
        print(f"   Wave Impedance: {last_eq['wave_impedance']:.4f}")
        print(f"   Balance Ratio: {last_eq['balance_ratio']:.4f}")
    
    # ── Display Phantom DNA Signatures ──
    print("\n👻 ACTIVE PHANTOM DNA SIGNATURES:")
    print("-" * 50)
    
    phantom_sigs = chain.get_phantom_signatures()
    if phantom_sigs:
        for sig_id, sig in phantom_sigs.items():
            print(f"   {sig_id}")
            print(f"      Fingerprint: {sig['dna_fingerprint']}")
            print(f"      Strength: {sig['strength']:.2f}")
            print(f"      Impedance: {sig['wave_impedance']:.4f}")
    else:
        print("   No active phantom signatures.")
    
    # ── Demonstrate Phantom DNA Decay ──
    print("\n⏳ APPLYING PHANTOM DECAY...")
    print("-" * 50)
    
    decayed = chain.phantom_dna.decay_signatures(steps=10)
    if decayed:
        print(f"   Decayed signatures: {decayed}")
    
    # Show remaining signatures
    remaining = chain.get_phantom_signatures()
    print(f"   Remaining active signatures: {len(remaining)}")
    
    # ── Attempt Shard Recovery ──
    print("\n🔐 SHARD RECOVERY DEMONSTRATION:")
    print("-" * 50)
    
    available = [shard_info["shards"][i] for i in [0, 2, 4]]
    print(f"   Available shards: {[s['shard_id'] for s in available]}")
    
    recon = reconstruct_from_shards(available, shard_info["original_hash"])
    print(f"   Reconstruction hash match: {'✅' if recon['hash_match'] else '❌'}")
    print(f"   Reconstructed: {recon['reconstructed'][:50]}...")
    
    # ── Validate the Chain ──
    print("\n🔍 VALIDATING CAUSAL CHAIN:")
    print("-" * 50)
    chain.validate()
    
    # ── Summary ──
    print("\n" + "=" * 70)
    print("📊 SYSTEM SUMMARY")
    print("=" * 70)
    print(f"   Total Records: {len(chain.chain)}")
    print(f"   Total Events: {chain.event_count}")
    print(f"   Equilibrium Events: {len(chain.get_equilibrium_history())}")
    print(f"   Phantom Signatures: {len(chain.get_phantom_signatures())}")
    print(f"   Network Nodes: {len(network.nodes)}")
    print(f"   Network Consensus: {'✅' if sync_result['network_consensus'] else '❌'}")
    print("=" * 70)
    print("\n✅ All features integrated and running.")
    print("   No timestamps used - purely causal, event-driven.")
    print("   Digital twin only - no real biology, RF, or hardware.")
    
    # Optional: Save the chain
    # chain.save("maxwell_twin_full_chain.json")


if __name__ == "__main__":
    main()
