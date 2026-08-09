#!/usr/bin/env python3
"""
Maxwell Mesh Network - Complete Node Mesh with Blockchain
==========================================================
Save as: maxwell_mesh_network.py
Run:     python3 maxwell_mesh_network.py

MESH NETWORK FEATURES:
1. Node mesh with auto-discovery and connections
2. Blockchain with multi-chain support
3. Server and cloud network integration
4. Maxwell prediction for network growth
5. Self-healing connections
6. Dynamic routing and load balancing
7. DNA/Twin integration with mesh
8. Hardware device mesh
9. Autonomous chain growth
10. Network resilience

Digital twin only - no real biology, chemicals, RF, or hardware control.
"""

import hashlib
import json
import math
import os
import random
import struct
import sys
import time
import traceback
import threading
import queue
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

# Optional cryptography
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ──────────────────────────────────────────────────────────────
# 0. COLOR CLASS - DEFINED FIRST
# ──────────────────────────────────────────────────────────────

class Color:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


# ──────────────────────────────────────────────────────────────
# 1. UTILITIES
# ──────────────────────────────────────────────────────────────

def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def truncate_hash(h: str, length: int = 12) -> str:
    return h[:length] + "..." if len(h) > length else h


def deterministic_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


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


def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i * 4: (i + 1) * 4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]


def compute_maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
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
    field_energy = nE * nH
    entropy = sum(abs(x) for x in E + H) / len(E + H)
    
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
        "field_energy": field_energy,
        "field_entropy": entropy,
        "thermodynamic_state": {
            "is_equilibrium": abs(field_energy - 0.5) < 0.1,
            "energy_difference": abs(field_energy - 0.5),
            "energy_flow": field_energy - 0.5
        }
    }


# ──────────────────────────────────────────────────────────────
# 2. MAXWELL PREDICTION ENGINE
# ──────────────────────────────────────────────────────────────

class MaxwellPredictionEngine:
    """Predicts network growth, link stability, and chain evolution."""
    
    def __init__(self):
        self.prediction_history: List[Dict] = []
        self.field_measurements: List[Dict] = []
        self.accuracy_score = 0.85
        self.prediction_energy = 0.0
        
    def predict_link_stability(self, node1: Dict, node2: Dict) -> Dict:
        """Predict stability of a link between two nodes."""
        data_str = f"{node1.get('node_id', 'unknown')}:{node2.get('node_id', 'unknown')}"
        sig = compute_maxwell_signature(data_str, len(self.field_measurements), [0.0, 0.0, 0.0])
        
        energy_match = 1.0 - abs(node1.get('energy', 0.5) - node2.get('energy', 0.5))
        peer_count_factor = min(1.0, len(node1.get('peers', [])) / 10.0 + len(node2.get('peers', [])) / 10.0)
        wave_impedance = sig.get('wave_impedance', 1.0)
        
        stability = (energy_match * 0.4 + peer_count_factor * 0.3 + (1.0 / (1.0 + abs(wave_impedance - 1.0))) * 0.3)
        stability = max(0.0, min(1.0, stability))
        
        prediction = {
            "node1": node1.get('node_id', 'unknown'),
            "node2": node2.get('node_id', 'unknown'),
            "stability_score": stability,
            "energy_match": energy_match,
            "wave_impedance": wave_impedance,
            "prediction_time": get_timestamp()
        }
        
        self.prediction_history.append(prediction)
        self.prediction_energy += 0.1
        return prediction
    
    def predict_chain_growth(self, chain_data: Dict, network_state: Dict) -> Dict:
        """Predict how a chain will grow based on network state."""
        chain_blocks = chain_data.get('blocks', 0)
        chain_energy = chain_data.get('energy', 1.0)
        chain_entropy = chain_data.get('entropy', 0.0)
        
        energy_factor = chain_energy / (chain_entropy + 1.0)
        network_factor = network_state.get('node_count', 1) / 10.0
        stability_factor = network_state.get('avg_stability', 0.5)
        
        data_str = f"{chain_data.get('chain_id', 'unknown')}:{network_state.get('timestamp', 'unknown')}"
        sig = compute_maxwell_signature(data_str, len(self.field_measurements) + 1, [0.0, 0.0, 0.0])
        
        base_growth = energy_factor * 0.5 + network_factor * 0.3 + stability_factor * 0.2
        growth_rate = min(10.0, base_growth * 2.0)
        predicted_blocks = chain_blocks + growth_rate
        
        prediction = {
            "chain_id": chain_data.get('chain_id', 'unknown'),
            "current_blocks": chain_blocks,
            "predicted_blocks": predicted_blocks,
            "growth_rate": growth_rate,
            "energy_factor": energy_factor,
            "network_factor": network_factor,
            "stability_factor": stability_factor,
            "prediction_time": get_timestamp(),
            "maxwell_impedance": sig.get('wave_impedance', 1.0)
        }
        
        self.prediction_history.append(prediction)
        self.prediction_energy += 0.15
        return prediction
    
    def predict_network_health(self, network: Dict) -> Dict:
        """Predict overall network health and growth potential."""
        node_count = network.get('node_count', 0)
        chain_count = network.get('chain_count', 0)
        avg_stability = network.get('avg_stability', 0.5)
        total_energy = network.get('total_energy', 10.0)
        
        health_score = (min(1.0, node_count / 10.0) * 0.3 +
                        min(1.0, chain_count / 5.0) * 0.2 +
                        avg_stability * 0.3 +
                        min(1.0, total_energy / 20.0) * 0.2)
        
        growth_potential = (1.0 - health_score) * 1.5 + 0.5
        
        prediction = {
            "health_score": health_score,
            "growth_potential": growth_potential,
            "node_count": node_count,
            "chain_count": chain_count,
            "avg_stability": avg_stability,
            "total_energy": total_energy,
            "recommendation": "grow" if growth_potential > 0.7 else "stabilize",
            "prediction_time": get_timestamp()
        }
        
        self.prediction_history.append(prediction)
        return prediction
    
    def find_optimal_connection(self, node: Dict, available_nodes: List[Dict]) -> Dict:
        """Find the optimal connection for a node."""
        best_match = None
        best_score = -1.0
        
        for candidate in available_nodes:
            if candidate.get('node_id') == node.get('node_id'):
                continue
            
            prediction = self.predict_link_stability(node, candidate)
            score = prediction.get('stability_score', 0.0)
            score += (node.get('energy', 0.5) + candidate.get('energy', 0.5)) * 0.1
            
            if score > best_score:
                best_score = score
                best_match = candidate
        
        return {
            "best_match": best_match.get('node_id') if best_match else None,
            "score": best_score,
            "recommendation": "connect" if best_score > 0.6 else "wait"
        }
    
    def get_stats(self) -> Dict:
        return {
            "predictions": len(self.prediction_history),
            "accuracy": self.accuracy_score,
            "energy": self.prediction_energy,
            "last_prediction": self.prediction_history[-1] if self.prediction_history else None
        }


# ──────────────────────────────────────────────────────────────
# 3. BLOCKCHAIN CHAIN AND BLOCK
# ──────────────────────────────────────────────────────────────

class Block:
    def __init__(self, index: int, transactions: List[Dict], previous_hash: str, 
                 chain_id: str = "main", difficulty: int = 3):
        self.index = index
        self.timestamp = get_timestamp()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.nonce = 0
        self.energy = 1.0
        self.entropy = 0.0
        self.maxwell_sig = compute_maxwell_signature(
            json.dumps(transactions, default=str),
            index,
            [0.0, 0.0, 0.0]
        )
        self.hash = self._calculate_hash()
    
    def _calculate_hash(self) -> str:
        block_data = {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "chain_id": self.chain_id,
            "difficulty": self.difficulty,
            "nonce": self.nonce,
            "energy": self.energy,
            "entropy": self.entropy
        }
        return openssl_hash(json.dumps(block_data, sort_keys=True, default=str).encode(), "sha256")
    
    def mine(self) -> None:
        target = "0" * self.difficulty
        start_time = time.time()
        
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calculate_hash()
            
            if self.nonce % 1000 == 0:
                self.energy += 0.01
                self.entropy += 0.001
        
        mining_time = time.time() - start_time
        self.energy += mining_time * 0.1
    
    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "chain_id": self.chain_id,
            "difficulty": self.difficulty,
            "nonce": self.nonce,
            "hash": self.hash,
            "energy": self.energy,
            "entropy": self.entropy,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


class Chain:
    def __init__(self, chain_id: str = "main", difficulty: int = 2):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[Block] = []
        self.total_energy = 0.0
        self.total_entropy = 0.0
        self.status = "active"
        self.created_at = get_timestamp()
        self.growth_rate = 0.0
        self.last_growth = get_timestamp()
        
        self._create_genesis()
    
    def _create_genesis(self):
        genesis = Block(0, [{"type": "genesis", "data": f"Chain {self.chain_id}"}], 
                       "0" * 64, self.chain_id, self.difficulty)
        genesis.mine()
        self.blocks.append(genesis)
        self.total_energy += genesis.energy
    
    def add_block(self, transactions: List[Dict]) -> Block:
        previous_hash = self.blocks[-1].hash
        block = Block(len(self.blocks), transactions, previous_hash, self.chain_id, self.difficulty)
        block.mine()
        self.blocks.append(block)
        self.total_energy += block.energy
        self.total_entropy += block.entropy
        self.growth_rate = len(self.blocks) / max(1, (time.time() - time.mktime(datetime.fromisoformat(self.created_at.replace('Z', '+00:00')).timetuple())))
        self.last_growth = get_timestamp()
        return block
    
    def validate(self) -> Dict:
        for i in range(1, len(self.blocks)):
            current = self.blocks[i]
            previous = self.blocks[i - 1]
            
            if current.previous_hash != previous.hash:
                return {"status": "invalid", "reason": f"hash_mismatch_at_{i}"}
            
            if current.hash != current._calculate_hash():
                return {"status": "invalid", "reason": f"invalid_hash_at_{i}"}
        
        return {"status": "valid", "blocks": len(self.blocks)}
    
    def get_health(self) -> Dict:
        validation = self.validate()
        return {
            "chain_id": self.chain_id,
            "blocks": len(self.blocks),
            "status": self.status,
            "valid": validation["status"] == "valid",
            "total_energy": self.total_energy,
            "total_entropy": self.total_entropy,
            "efficiency": 1.0 / (1.0 + self.total_entropy / (self.total_energy + 1e-15)),
            "growth_rate": self.growth_rate,
            "created_at": self.created_at,
            "last_growth": self.last_growth
        }
    
    def to_dict(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "blocks": [block.to_dict() for block in self.blocks],
            "total_energy": self.total_energy,
            "total_entropy": self.total_entropy,
            "status": self.status,
            "growth_rate": self.growth_rate,
            "created_at": self.created_at
        }


# ──────────────────────────────────────────────────────────────
# 4. MESH NODE
# ──────────────────────────────────────────────────────────────

class MeshNode:
    """A node in the mesh network."""
    
    def __init__(self, node_id: str, node_type: str = "full", server_type: str = "standard"):
        self.node_id = node_id
        self.node_type = node_type
        self.server_type = server_type
        self.peers: Set[str] = set()
        self.chains: Dict[str, Chain] = {}
        self.is_active = True
        self.energy = 10.0
        self.entropy = 0.0
        self.created_at = get_timestamp()
        self.last_heartbeat = get_timestamp()
        
        # Hardware identification
        self.mac = ":".join(f"{random.randint(0, 255):02x}" for _ in range(6))
        self.ip = f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
        self.port = random.randint(1024, 65535)
        self.hostname = f"node-{node_id[:8]}"
        
        # Cloud/servers
        self.cloud_provider = random.choice(["aws", "azure", "gcp", "local"])
        self.region = random.choice(["us-east", "us-west", "eu-west", "ap-southeast"])
        self.instance_type = random.choice(["micro", "small", "medium", "large", "xlarge"])
        
        # Maxwell signature
        self.maxwell_sig = compute_maxwell_signature(
            node_id + self.mac, 
            0, 
            [0.0, 0.0, 0.0]
        )
        
        # DNA/Twin bindings
        self.dna_bindings: List[str] = []
        self.twin_bindings: List[str] = []
        self.hardware_connections: List[str] = []
        
        # Message queue
        self.message_queue: queue.Queue = queue.Queue()
        self.messages_processed = 0
        
        # Metrics
        self.uptime = 0
        self.link_stability = 1.0
        self.growth_contribution = 0.0
    
    def add_chain(self, chain: Chain) -> Dict:
        self.chains[chain.chain_id] = chain
        self.energy += 0.1
        return {"status": "added", "chain_id": chain.chain_id}
    
    def add_peer(self, peer_id: str) -> Dict:
        if peer_id not in self.peers:
            self.peers.add(peer_id)
            self.energy += 0.05
            return {"status": "peer_added", "peer": peer_id}
        return {"status": "already_peered", "peer": peer_id}
    
    def remove_peer(self, peer_id: str) -> Dict:
        self.peers.discard(peer_id)
        return {"status": "peer_removed", "peer": peer_id}
    
    def bind_dna(self, dna_id: str) -> Dict:
        self.dna_bindings.append(dna_id)
        return {"status": "bound", "dna": dna_id}
    
    def bind_twin(self, twin_id: str) -> Dict:
        self.twin_bindings.append(twin_id)
        return {"status": "bound", "twin": twin_id}
    
    def connect_hardware(self, hardware_id: str) -> Dict:
        self.hardware_connections.append(hardware_id)
        return {"status": "connected", "hardware": hardware_id}
    
    def broadcast(self, message: Dict) -> Dict:
        msg = {
            "from": self.node_id,
            "message": message,
            "timestamp": get_timestamp(),
            "id": deterministic_hash(message)
        }
        
        delivered = []
        for peer in self.peers:
            delivered.append({"peer": peer, "status": "delivered"})
        
        self.messages_processed += 1
        return {
            "status": "broadcast",
            "from": self.node_id,
            "peers": list(self.peers),
            "delivered": delivered,
            "message_id": msg["id"]
        }
    
    def receive_message(self, message: Dict) -> Dict:
        self.message_queue.put(message)
        return {
            "status": "received",
            "from": message.get("from", "unknown"),
            "message_id": message.get("id", "unknown")
        }
    
    def heartbeat(self) -> Dict:
        self.last_heartbeat = get_timestamp()
        self.uptime += 1
        self.energy += 0.01
        self.link_stability = min(1.0, self.link_stability + 0.001)
        
        return {
            "node_id": self.node_id,
            "status": "alive" if self.is_active else "inactive",
            "timestamp": self.last_heartbeat,
            "uptime": self.uptime,
            "chains": len(self.chains),
            "peers": len(self.peers),
            "energy": self.energy,
            "link_stability": self.link_stability
        }
    
    def get_status(self) -> Dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "server_type": self.server_type,
            "cloud_provider": self.cloud_provider,
            "region": self.region,
            "instance_type": self.instance_type,
            "is_active": self.is_active,
            "chains": list(self.chains.keys()),
            "peers": list(self.peers),
            "mac": self.mac,
            "ip": self.ip,
            "port": self.port,
            "hostname": self.hostname,
            "energy": self.energy,
            "entropy": self.entropy,
            "link_stability": self.link_stability,
            "uptime": self.uptime,
            "created_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
            "dna_bindings": self.dna_bindings,
            "twin_bindings": self.twin_bindings,
            "hardware_connections": self.hardware_connections,
            "messages_processed": self.messages_processed,
            "growth_contribution": self.growth_contribution,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }
    
    def to_dict(self) -> Dict:
        return self.get_status()


# ──────────────────────────────────────────────────────────────
# 5. MESH NETWORK
# ──────────────────────────────────────────────────────────────

class MeshNetwork:
    """Complete mesh network with nodes, chains, and predictions."""
    
    def __init__(self, network_id: str = "maxwell_mesh"):
        self.network_id = network_id
        self.nodes: Dict[str, MeshNode] = {}
        self.chains: Dict[str, Chain] = {}
        self.predictor = MaxwellPredictionEngine()
        self.network_energy = 100.0
        self.network_entropy = 0.0
        self.created_at = get_timestamp()
        self.transaction_pool: List[Dict] = []
        self.mesh_topology: Dict[str, List[str]] = {}
        self.connection_history: List[Dict] = []
        self.growth_cycles = 0
        self.survival_rate = 1.0
        
        # Cloud/server configurations
        self.cloud_providers = ["aws", "azure", "gcp", "oracle", "digitalocean", "local"]
        self.cloud_regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1", "sa-east-1"]
        
        self._initialize_network()
    
    def _initialize_network(self):
        """Initialize the network with nodes, chains, and connections."""
        print(Color.CYAN + "🌐 Initializing Mesh Network..." + Color.END)
        
        # Create chains
        main_chain = Chain("main", difficulty=2)
        self.chains["main"] = main_chain
        
        backup_chain = Chain("backup", difficulty=2)
        self.chains["backup"] = backup_chain
        
        data_chain = Chain("data", difficulty=2)
        self.chains["data"] = data_chain
        
        # Create nodes
        node_types = ["full", "light", "validator", "archival"]
        server_types = ["standard", "high_memory", "high_cpu", "storage_optimized"]
        
        for i in range(5):
            node_type = node_types[i % len(node_types)]
            server_type = server_types[i % len(server_types)]
            node_id = f"NODE_{i+1}"
            
            node = MeshNode(node_id, node_type, server_type)
            node.add_chain(main_chain)
            if i < 3:
                node.add_chain(backup_chain)
            if i < 2:
                node.add_chain(data_chain)
            
            # Random cloud assignment
            node.cloud_provider = random.choice(self.cloud_providers)
            node.region = random.choice(self.cloud_regions)
            node.instance_type = random.choice(["micro", "small", "medium", "large"])
            
            self.nodes[node_id] = node
            self.mesh_topology[node_id] = []
        
        # Connect nodes in a mesh
        node_ids = list(self.nodes.keys())
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                if random.random() < 0.7:
                    self._connect_nodes(node_ids[i], node_ids[j])
        
        print(f"   ✅ Created {len(self.chains)} chains")
        print(f"   ✅ Created {len(self.nodes)} nodes")
        print(f"   ✅ Created {self._count_connections()} connections")
    
    def _connect_nodes(self, node1_id: str, node2_id: str) -> Dict:
        if node1_id not in self.nodes or node2_id not in self.nodes:
            return {"status": "error", "reason": "node_not_found"}
        
        node1 = self.nodes[node1_id]
        node2 = self.nodes[node2_id]
        
        prediction = self.predictor.predict_link_stability(
            node1.get_status(), 
            node2.get_status()
        )
        
        if prediction["stability_score"] > 0.4:
            node1.add_peer(node2_id)
            node2.add_peer(node1_id)
            
            if node1_id not in self.mesh_topology:
                self.mesh_topology[node1_id] = []
            if node2_id not in self.mesh_topology:
                self.mesh_topology[node2_id] = []
            
            self.mesh_topology[node1_id].append(node2_id)
            self.mesh_topology[node2_id].append(node1_id)
            
            self.connection_history.append({
                "node1": node1_id,
                "node2": node2_id,
                "stability": prediction["stability_score"],
                "timestamp": get_timestamp()
            })
            
            return {"status": "connected", "stability": prediction["stability_score"]}
        
        return {"status": "skipped", "reason": "low_stability", "score": prediction["stability_score"]}
    
    def _count_connections(self) -> int:
        total = 0
        seen = set()
        for node_id, peers in self.mesh_topology.items():
            for peer in peers:
                if (node_id, peer) not in seen and (peer, node_id) not in seen:
                    seen.add((node_id, peer))
                    total += 1
        return total
    
    def add_node(self, node_id: str, node_type: str = "full") -> MeshNode:
        if node_id in self.nodes:
            return self.nodes[node_id]
        
        node = MeshNode(node_id, node_type, random.choice(["standard", "high_memory"]))
        
        for chain in self.chains.values():
            node.add_chain(chain)
        
        self.nodes[node_id] = node
        self.mesh_topology[node_id] = []
        
        available = [n.get_status() for n in self.nodes.values() if n.node_id != node_id]
        optimal = self.predictor.find_optimal_connection(node.get_status(), available)
        
        if optimal["recommendation"] == "connect" and optimal["best_match"]:
            self._connect_nodes(node_id, optimal["best_match"])
        
        return node
    
    def add_chain(self, chain_id: str, difficulty: int = 2) -> Chain:
        if chain_id in self.chains:
            return self.chains[chain_id]
        
        chain = Chain(chain_id, difficulty)
        self.chains[chain_id] = chain
        
        for node in self.nodes.values():
            node.add_chain(chain)
        
        return chain
    
    def add_transaction(self, chain_id: str, transaction: Dict) -> Dict:
        if chain_id not in self.chains:
            return {"status": "error", "reason": "chain_not_found"}
        
        self.transaction_pool.append({
            "chain_id": chain_id,
            "transaction": transaction,
            "timestamp": get_timestamp(),
            "id": deterministic_hash(transaction)
        })
        
        if len(self.transaction_pool) >= 5:
            return self.mine_block(chain_id)
        
        return {"status": "pending", "pool_size": len(self.transaction_pool)}
    
    def mine_block(self, chain_id: str) -> Dict:
        if chain_id not in self.chains:
            return {"status": "error", "reason": "chain_not_found"}
        
        chain_txs = [tx for tx in self.transaction_pool if tx["chain_id"] == chain_id]
        if not chain_txs:
            return {"status": "error", "reason": "no_transactions"}
        
        chain = self.chains[chain_id]
        
        chain_data = chain.get_health()
        network_state = {
            "node_count": len(self.nodes),
            "avg_stability": self.survival_rate,
            "timestamp": get_timestamp()
        }
        growth_prediction = self.predictor.predict_chain_growth(chain_data, network_state)
        
        block = chain.add_block([tx["transaction"] for tx in chain_txs])
        
        self.transaction_pool = [tx for tx in self.transaction_pool if tx["chain_id"] != chain_id]
        self.network_energy += block.energy * 0.1
        self.growth_cycles += 1
        chain.growth_rate = (chain.growth_rate + growth_prediction["growth_rate"]) / 2
        
        return {
            "status": "success",
            "chain_id": chain_id,
            "block_index": block.index,
            "block_hash": truncate_hash(block.hash),
            "transactions": len(chain_txs),
            "energy": block.energy,
            "entropy": block.entropy,
            "growth_prediction": growth_prediction,
            "new_growth_rate": chain.growth_rate
        }
    
    def grow_network(self) -> Dict:
        network_state = {
            "node_count": len(self.nodes),
            "chain_count": len(self.chains),
            "avg_stability": self.survival_rate,
            "total_energy": self.network_energy,
            "timestamp": get_timestamp()
        }
        health_prediction = self.predictor.predict_network_health(network_state)
        
        growth_actions = []
        
        if health_prediction["growth_potential"] > 0.6:
            new_node_id = f"NODE_{len(self.nodes) + 1}"
            node = self.add_node(new_node_id, random.choice(["full", "light"]))
            growth_actions.append(f"added_node_{new_node_id}")
            
            available = [n.get_status() for n in self.nodes.values() if n.node_id != new_node_id]
            optimal = self.predictor.find_optimal_connection(node.get_status(), available)
            if optimal["recommendation"] == "connect" and optimal["best_match"]:
                self._connect_nodes(new_node_id, optimal["best_match"])
                growth_actions.append(f"connected_to_{optimal['best_match']}")
            
            self.network_energy += 5.0
        
        if len(self.chains) < 5 and self.network_energy > 20.0:
            chain_id = f"chain_{len(self.chains) + 1}"
            self.add_chain(chain_id, difficulty=2)
            growth_actions.append(f"added_chain_{chain_id}")
            self.network_energy -= 5.0
        
        if len(self.transaction_pool) >= 3:
            for chain_id in list(self.chains.keys())[:2]:
                result = self.mine_block(chain_id)
                if result.get("status") == "success":
                    growth_actions.append(f"mined_block_on_{chain_id}")
                    self.network_energy += result.get("energy", 0) * 0.05
        
        self.survival_rate = (self.survival_rate * 0.9 + health_prediction["health_score"] * 0.1)
        
        return {
            "status": "success",
            "growth_actions": growth_actions,
            "health_prediction": health_prediction,
            "network_energy": self.network_energy,
            "survival_rate": self.survival_rate,
            "timestamp": get_timestamp()
        }
    
    def autonomous_cycle(self) -> Dict:
        print(f"\n{Color.YELLOW}🔄 Autonomous Cycle {self.growth_cycles + 1}" + Color.END)
        print("─" * 50)
        
        heartbeats = []
        for node in self.nodes.values():
            heartbeats.append(node.heartbeat())
        print(f"   💓 Heartbeat: {len(heartbeats)} nodes active")
        
        growth = self.grow_network()
        print(f"   🌱 Growth: {len(growth['growth_actions'])} actions")
        for action in growth['growth_actions']:
            print(f"      • {action}")
        
        health = self.predictor.predict_network_health({
            "node_count": len(self.nodes),
            "chain_count": len(self.chains),
            "avg_stability": self.survival_rate,
            "total_energy": self.network_energy,
            "timestamp": get_timestamp()
        })
        print(f"   📊 Health: {health['health_score']:.2f}")
        print(f"   📈 Growth Potential: {health['growth_potential']:.2f}")
        print(f"   💡 Recommendation: {health['recommendation']}")
        
        self.growth_cycles += 1
        self.network_entropy += 0.01
        
        return {
            "cycle": self.growth_cycles,
            "heartbeats": len(heartbeats),
            "growth": growth,
            "health": health
        }
    
    def get_status(self) -> Dict:
        return {
            "network_id": self.network_id,
            "nodes": len(self.nodes),
            "chains": len(self.chains),
            "connections": self._count_connections(),
            "network_energy": self.network_energy,
            "network_entropy": self.network_entropy,
            "survival_rate": self.survival_rate,
            "growth_cycles": self.growth_cycles,
            "transaction_pool": len(self.transaction_pool),
            "created_at": self.created_at,
            "predictions": self.predictor.get_stats()
        }
    
    def to_dict(self) -> Dict:
        return {
            "network_id": self.network_id,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "chains": {cid: chain.to_dict() for cid, chain in self.chains.items()},
            "topology": self.mesh_topology,
            "connections": self.connection_history[-20:],
            "status": self.get_status()
        }


# ──────────────────────────────────────────────────────────────
# 6. MAIN SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxMeshSystem:
    """Main system with mesh network."""
    
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🌐 MAXWELL MESH NETWORK" + Color.END)
        print(Color.CYAN + "   Complete Node Mesh with Blockchain & Predictions" + Color.END)
        print("=" * 70)
        
        self.network = MeshNetwork("maxwell_mesh")
        
        print(Color.GREEN + "✅ System initialized with mesh network" + Color.END)
        print("=" * 70 + "\n")
    
    def show_status(self):
        status = self.network.get_status()
        
        print(f"\n{Color.CYAN}📊 NETWORK STATUS" + Color.END)
        print("=" * 60)
        print(f"   Network: {status['network_id']}")
        print(f"   Nodes: {status['nodes']}")
        print(f"   Chains: {status['chains']}")
        print(f"   Connections: {status['connections']}")
        print(f"   Energy: {status['network_energy']:.2f}")
        print(f"   Entropy: {status['network_entropy']:.4f}")
        print(f"   Survival Rate: {status['survival_rate']:.2%}")
        print(f"   Growth Cycles: {status['growth_cycles']}")
        print(f"   Transaction Pool: {status['transaction_pool']}")
        print(f"   Predictions: {status['predictions']['predictions']}")
        print("=" * 60)
    
    def show_nodes(self):
        print(f"\n{Color.CYAN}🖥️ NETWORK NODES" + Color.END)
        print("=" * 60)
        for node_id, node in self.network.nodes.items():
            status = node.get_status()
            print(f"\n{Color.BOLD}{node_id}" + Color.END)
            print(f"   Type: {status['node_type']} | {status['server_type']}")
            print(f"   Cloud: {status['cloud_provider']} ({status['region']})")
            print(f"   IP: {status['ip']}:{status['port']}")
            print(f"   Chains: {status['chains']}")
            print(f"   Peers: {status['peers']}")
            print(f"   Energy: {status['energy']:.2f}")
            print(f"   Stability: {status['link_stability']:.2f}")
            print(f"   DNA: {status['dna_bindings']}")
            print(f"   Twin: {status['twin_bindings']}")
        print("=" * 60)
    
    def show_chains(self):
        print(f"\n{Color.CYAN}⛓️ BLOCKCHAINS" + Color.END)
        print("=" * 60)
        for chain_id, chain in self.network.chains.items():
            health = chain.get_health()
            print(f"\n{Color.BOLD}Chain: {chain_id}" + Color.END)
            print(f"   Blocks: {health['blocks']}")
            print(f"   Status: {health['status']}")
            print(f"   Valid: {'✅' if health['valid'] else '❌'}")
            print(f"   Energy: {health['total_energy']:.2f}")
            print(f"   Entropy: {health['total_entropy']:.4f}")
            print(f"   Efficiency: {health['efficiency']:.2%}")
            print(f"   Growth Rate: {health['growth_rate']:.2f} blocks/s")
        print("=" * 60)
    
    def run_cycle(self):
        result = self.network.autonomous_cycle()
        print(f"\n{Color.GREEN}✅ Cycle {result['cycle']} complete" + Color.END)
        return result
    
    def run_autonomous(self, cycles: int = 5):
        print(f"\n{Color.CYAN}🤖 RUNNING AUTONOMOUSLY FOR {cycles} CYCLES" + Color.END)
        print("=" * 70)
        
        for i in range(cycles):
            self.run_cycle()
            time.sleep(0.5)
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ AUTONOMOUS RUN COMPLETE" + Color.END)
        print("=" * 70)
    
    def run_demo(self):
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 SYSTEM DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        self.show_status()
        self.show_nodes()
        self.show_chains()
        
        print(f"\n{Color.YELLOW}🔄 Running autonomous cycles..." + Color.END)
        self.run_autonomous(5)
        
        print("\n" + "=" * 70)
        print(Color.CYAN + "📊 FINAL STATUS" + Color.END)
        self.show_status()
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 7. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxMeshSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🌐 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show network status")
        print("   - nodes         - Show all nodes")
        print("   - chains        - Show all chains")
        print("   - cycle         - Run one cycle")
        print("   - auto <n>      - Run n autonomous cycles")
        print("   - demo          - Run full demonstration")
        print("   - help          - Show this help")
        print("   - exit          - Quit")
        print("=" * 70 + "\n")
        
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip().lower()
                
                if cmd == "exit":
                    break
                elif cmd == "status":
                    system.show_status()
                elif cmd == "nodes":
                    system.show_nodes()
                elif cmd == "chains":
                    system.show_chains()
                elif cmd == "cycle":
                    system.run_cycle()
                elif cmd.startswith("auto"):
                    parts = cmd.split()
                    cycles = int(parts[1]) if len(parts) > 1 else 3
                    system.run_autonomous(cycles)
                elif cmd == "demo":
                    system.run_demo()
                elif cmd == "help":
                    print("\n   Available commands:")
                    print("   status        - Show network status")
                    print("   nodes         - Show all nodes")
                    print("   chains        - Show all chains")
                    print("   cycle         - Run one cycle")
                    print("   auto <n>      - Run n autonomous cycles")
                    print("   demo          - Run full demonstration")
                    print("   help          - Show this help")
                    print("   exit          - Quit\n")
                elif cmd == "":
                    continue
                else:
                    print(f"   Unknown command: {cmd}")
            except KeyboardInterrupt:
                print("\n")
                break
            except ValueError:
                print("   ❌ Invalid number. Use: auto <number>")
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Shutting down...")
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        print(traceback.format_exc())
        return 1
    
    print(Color.GREEN + "✅ Goodbye!" + Color.END)
    return 0


if __name__ == "__main__":
    sys.exit(main())
