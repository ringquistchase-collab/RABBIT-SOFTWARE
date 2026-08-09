#!/usr/bin/env python3
"""
Maxwell Data Mesh - DNA/Twin/EEG/Network Growth System
========================================================
Save as: maxwell_data_mesh.py
Run:     python3 maxwell_data_mesh.py

DATA MESH FEATURES:
1. DNA events triggering EEG patterns
2. Twin mirroring with damage detection
3. Network mesh learning from patterns
4. AI communication across all layers
5. Event-driven growth and learning
6. Damage detection and repair
7. Pattern evolution across the mesh
8. Self-organizing data network
9. Autonomous growth cycles
10. Multi-layer communication

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
# 0. COLOR CLASS
# ──────────────────────────────────────────────────────────────

class Color:
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
# 2. DNA EVENT SYSTEM
# ──────────────────────────────────────────────────────────────

class DNAEvent:
    """An event that occurs in DNA, triggering changes across the mesh."""
    
    EVENT_TYPES = {
        "mutation": {"severity": 0.7, "damage": 0.5, "repair": 0.3},
        "damage": {"severity": 0.8, "damage": 0.9, "repair": 0.1},
        "repair": {"severity": 0.4, "damage": 0.1, "repair": 0.9},
        "methylation": {"severity": 0.5, "damage": 0.3, "repair": 0.5},
        "expression": {"severity": 0.3, "damage": 0.2, "repair": 0.6},
        "stress": {"severity": 0.6, "damage": 0.7, "repair": 0.2},
        "replication": {"severity": 0.2, "damage": 0.1, "repair": 0.8},
        "recombination": {"severity": 0.4, "damage": 0.2, "repair": 0.7}
    }
    
    def __init__(self, event_type: str, location: str = "", intensity: float = 0.5):
        self.event_type = event_type
        self.location = location or f"gene_{random.randint(1, 100)}"
        self.intensity = min(1.0, max(0.0, intensity))
        self.timestamp = get_timestamp()
        self.event_id = deterministic_hash({
            "type": event_type,
            "location": self.location,
            "intensity": self.intensity,
            "timestamp": self.timestamp
        })
        
        # Get event properties
        props = self.EVENT_TYPES.get(event_type, self.EVENT_TYPES["mutation"])
        self.severity = props["severity"] * self.intensity
        self.damage_potential = props["damage"] * self.intensity
        self.repair_potential = props["repair"] * self.intensity
        
        # Generate EEG pattern from event
        self.eeg_pattern = self._generate_eeg_from_event()
    
    def _generate_eeg_from_event(self) -> Dict[str, float]:
        """Generate an EEG pattern based on the event type."""
        # Map event type to EEG bands
        band_mapping = {
            "mutation": {"delta": 0.8, "theta": 0.6, "alpha": 0.3, "beta": 0.2, "gamma": 0.1},
            "damage": {"delta": 0.9, "theta": 0.7, "alpha": 0.2, "beta": 0.1, "gamma": 0.1},
            "repair": {"delta": 0.2, "theta": 0.3, "alpha": 0.7, "beta": 0.6, "gamma": 0.4},
            "methylation": {"delta": 0.3, "theta": 0.5, "alpha": 0.6, "beta": 0.4, "gamma": 0.3},
            "expression": {"delta": 0.2, "theta": 0.3, "alpha": 0.5, "beta": 0.7, "gamma": 0.6},
            "stress": {"delta": 0.7, "theta": 0.8, "alpha": 0.3, "beta": 0.2, "gamma": 0.1},
            "replication": {"delta": 0.1, "theta": 0.2, "alpha": 0.6, "beta": 0.8, "gamma": 0.7},
            "recombination": {"delta": 0.2, "theta": 0.4, "alpha": 0.5, "beta": 0.6, "gamma": 0.5}
        }
        
        base_pattern = band_mapping.get(self.event_type, band_mapping["mutation"])
        
        # Apply intensity scaling
        pattern = {}
        for band, value in base_pattern.items():
            pattern[band] = min(1.0, value * (0.5 + self.intensity * 0.5))
        
        return pattern
    
    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "type": self.event_type,
            "location": self.location,
            "intensity": self.intensity,
            "severity": self.severity,
            "damage_potential": self.damage_potential,
            "repair_potential": self.repair_potential,
            "eeg_pattern": self.eeg_pattern,
            "timestamp": self.timestamp
        }


class DNAEventSystem:
    """Manages DNA events and their propagation through the mesh."""
    
    def __init__(self):
        self.events: List[DNAEvent] = []
        self.event_history: List[Dict] = []
        self.active_events: List[DNAEvent] = []
        self.total_energy = 0.0
        self.damage_accumulated = 0.0
        
        # Event generators
        self.event_types = list(DNAEvent.EVENT_TYPES.keys())
        self.locations = [f"gene_{i}" for i in range(1, 50)]
    
    def create_event(self, event_type: str = None, intensity: float = None) -> DNAEvent:
        """Create a new DNA event."""
        if event_type is None:
            event_type = random.choice(self.event_types)
        if intensity is None:
            intensity = random.uniform(0.2, 0.9)
        
        location = random.choice(self.locations)
        event = DNAEvent(event_type, location, intensity)
        
        self.events.append(event)
        self.active_events.append(event)
        self.event_history.append(event.to_dict())
        self.total_energy += event.severity
        self.damage_accumulated += event.damage_potential
        
        return event
    
    def get_active_events(self) -> List[DNAEvent]:
        """Get all active events."""
        return self.active_events
    
    def resolve_events(self) -> Dict:
        """Resolve active events (damage vs repair)."""
        resolved_count = 0
        total_damage = 0
        total_repair = 0
        
        for event in self.active_events[:]:
            if random.random() < 0.3:  # 30% chance of resolution
                if random.random() < event.repair_potential:
                    # Event repaired
                    total_repair += event.repair_potential
                else:
                    # Event caused damage
                    total_damage += event.damage_potential
                
                self.active_events.remove(event)
                resolved_count += 1
        
        return {
            "resolved": resolved_count,
            "damage": total_damage,
            "repair": total_repair,
            "remaining": len(self.active_events)
        }
    
    def get_stats(self) -> Dict:
        return {
            "total_events": len(self.events),
            "active_events": len(self.active_events),
            "total_energy": self.total_energy,
            "damage_accumulated": self.damage_accumulated,
            "event_types": {t: len([e for e in self.events if e.event_type == t]) 
                           for t in self.event_types}
        }


# ──────────────────────────────────────────────────────────────
# 3. EEG PATTERN GENERATOR
# ──────────────────────────────────────────────────────────────

class EEGPattern:
    """EEG pattern generated from DNA events."""
    
    FREQUENCY_BANDS = ["delta", "theta", "alpha", "beta", "gamma"]
    
    def __init__(self, pattern_id: str = "", source_event: DNAEvent = None):
        self.pattern_id = pattern_id or f"EEG_{random.randint(1000, 9999)}"
        self.timestamp = get_timestamp()
        self.band_power: Dict[str, float] = {}
        self.coherence: Dict[str, float] = {}
        self.source_event_id = source_event.event_id if source_event else None
        self.damage_level = 0.0
        self.repair_level = 0.0
        
        if source_event:
            self._generate_from_event(source_event)
        else:
            self._generate_random()
    
    def _generate_from_event(self, event: DNAEvent):
        """Generate EEG pattern from a DNA event."""
        # Copy event's EEG pattern
        self.band_power = event.eeg_pattern.copy()
        
        # Calculate damage/repair from event
        self.damage_level = event.damage_potential
        self.repair_level = event.repair_potential
        
        # Add coherence based on event type
        for band in self.FREQUENCY_BANDS:
            self.coherence[f"{band}_coherence"] = random.uniform(0.3, 0.8) * (1 - event.damage_potential * 0.3)
    
    def _generate_random(self):
        """Generate a random EEG pattern."""
        for band in self.FREQUENCY_BANDS:
            self.band_power[band] = random.uniform(0.1, 1.0)
            self.coherence[f"{band}_coherence"] = random.uniform(0.2, 0.9)
    
    def get_dominant_band(self) -> str:
        return max(self.band_power, key=self.band_power.get)
    
    def to_vector(self) -> List[float]:
        vector = []
        for band in self.FREQUENCY_BANDS:
            vector.append(self.band_power.get(band, 0.0))
        for band in self.FREQUENCY_BANDS:
            vector.append(self.coherence.get(f"{band}_coherence", 0.0))
        return vector
    
    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "band_power": self.band_power,
            "coherence": self.coherence,
            "dominant_band": self.get_dominant_band(),
            "damage_level": self.damage_level,
            "repair_level": self.repair_level,
            "source_event_id": self.source_event_id,
            "timestamp": self.timestamp
        }


class EEGGenerator:
    """Generates EEG patterns from DNA events."""
    
    def __init__(self):
        self.patterns: List[EEGPattern] = []
        self.pattern_cache: Dict[str, EEGPattern] = {}
        self.total_energy = 0.0
    
    def generate_from_event(self, event: DNAEvent) -> EEGPattern:
        """Generate EEG pattern from a DNA event."""
        pattern = EEGPattern(source_event=event)
        self.patterns.append(pattern)
        self.pattern_cache[pattern.pattern_id] = pattern
        self.total_energy += 0.1
        return pattern
    
    def get_pattern(self, pattern_id: str) -> Optional[EEGPattern]:
        return self.pattern_cache.get(pattern_id)
    
    def get_recent_patterns(self, count: int = 5) -> List[EEGPattern]:
        return self.patterns[-count:]
    
    def get_stats(self) -> Dict:
        return {
            "total_patterns": len(self.patterns),
            "cache_size": len(self.pattern_cache),
            "total_energy": self.total_energy
        }


# ──────────────────────────────────────────────────────────────
# 4. TWIN DAMAGE DETECTION AND REPAIR
# ──────────────────────────────────────────────────────────────

class TwinDamageDetector:
    """
    Detects damage in the Twin system and initiates repair.
    Mirrors DNA events and their effects.
    """
    
    def __init__(self, twin_id: str = "TWIN_DAMAGE_DETECTOR"):
        self.twin_id = twin_id
        self.damage_log: List[Dict] = []
        self.repair_log: List[Dict] = []
        self.active_damage: Dict[str, float] = {}
        self.memristor_state = [0.5, 0.5, 0.5]
        self.total_energy = 0.0
        self.repair_efficiency = 0.7
        
        # Maxwell signature for twin
        self.maxwell_sig = compute_maxwell_signature(twin_id, 0, [0.0, 0.0, 0.0])
    
    def detect_damage_from_event(self, event: DNAEvent) -> Dict:
        """Detect damage from a DNA event."""
        damage_level = event.damage_potential * event.intensity
        
        # Record damage
        damage_record = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "damage_level": damage_level,
            "location": event.location,
            "timestamp": get_timestamp()
        }
        self.damage_log.append(damage_record)
        self.active_damage[event.event_id] = damage_level
        
        # Update memristor state
        self.memristor_state[0] = min(1.0, self.memristor_state[0] + damage_level * 0.1)
        self.memristor_state[1] = max(0.0, self.memristor_state[1] - damage_level * 0.05)
        self.memristor_state[2] = min(1.0, self.memristor_state[2] + damage_level * 0.05)
        
        self.total_energy += damage_level
        
        return {
            "status": "damage_detected",
            "damage_level": damage_level,
            "memristor_state": self.memristor_state,
            "repair_needed": damage_level > 0.5
        }
    
    def initiate_repair(self, event_id: str = None) -> Dict:
        """Initiate repair for detected damage."""
        repair_results = []
        
        if event_id:
            # Repair specific event
            if event_id in self.active_damage:
                damage = self.active_damage[event_id]
                repair_amount = damage * self.repair_efficiency
                
                repair_record = {
                    "event_id": event_id,
                    "damage_before": damage,
                    "repair_amount": repair_amount,
                    "damage_after": damage - repair_amount,
                    "timestamp": get_timestamp()
                }
                self.repair_log.append(repair_record)
                
                if repair_amount >= damage * 0.8:
                    del self.active_damage[event_id]
                    repair_results.append({"event_id": event_id, "status": "fully_repaired"})
                else:
                    self.active_damage[event_id] = damage - repair_amount
                    repair_results.append({"event_id": event_id, "status": "partially_repaired"})
        else:
            # Repair all active damage
            for eid, damage in list(self.active_damage.items()):
                repair_amount = damage * self.repair_efficiency * random.uniform(0.7, 1.0)
                self.active_damage[eid] = damage - repair_amount
                
                if self.active_damage[eid] < 0.1:
                    del self.active_damage[eid]
                    repair_results.append({"event_id": eid, "status": "fully_repaired"})
                else:
                    repair_results.append({"event_id": eid, "status": "partially_repaired"})
        
        # Update memristor state after repair
        self.memristor_state[0] = max(0.0, self.memristor_state[0] - 0.1)
        self.memristor_state[1] = min(1.0, self.memristor_state[1] + 0.05)
        
        return {
            "status": "repair_initiated",
            "repairs": repair_results,
            "remaining_damage": len(self.active_damage),
            "memristor_state": self.memristor_state
        }
    
    def get_damage_status(self) -> Dict:
        """Get current damage status."""
        return {
            "active_damage": self.active_damage,
            "damage_count": len(self.active_damage),
            "total_damage_logged": len(self.damage_log),
            "total_repairs": len(self.repair_log),
            "repair_efficiency": self.repair_efficiency,
            "memristor_state": self.memristor_state
        }
    
    def to_dict(self) -> Dict:
        return {
            "twin_id": self.twin_id,
            "active_damage": self.active_damage,
            "damage_count": len(self.damage_log),
            "repair_count": len(self.repair_log),
            "repair_efficiency": self.repair_efficiency,
            "memristor_state": self.memristor_state,
            "total_energy": self.total_energy,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


# ──────────────────────────────────────────────────────────────
# 5. DATA MESH NETWORK
# ──────────────────────────────────────────────────────────────

class DataMeshNode:
    """A node in the data mesh network."""
    
    def __init__(self, node_id: str, node_type: str = "mesh"):
        self.node_id = node_id
        self.node_type = node_type
        self.peers: Set[str] = set()
        self.data_store: Dict[str, Any] = {}
        self.patterns: List[EEGPattern] = []
        self.events: List[DNAEvent] = []
        self.learning_history: List[Dict] = []
        self.energy = 10.0
        self.entropy = 0.0
        self.created_at = get_timestamp()
        self.last_heartbeat = get_timestamp()
        self.growth_count = 0
        self.connections_made = 0
        
        # Maxwell signature
        self.maxwell_sig = compute_maxwell_signature(node_id, 0, [0.0, 0.0, 0.0])
        
        # Message queue
        self.message_queue: queue.Queue = queue.Queue()
        self.messages_processed = 0
    
    def add_peer(self, peer_id: str) -> Dict:
        if peer_id not in self.peers:
            self.peers.add(peer_id)
            self.connections_made += 1
            self.energy += 0.1
            return {"status": "peer_added", "peer": peer_id}
        return {"status": "already_peered"}
    
    def remove_peer(self, peer_id: str) -> Dict:
        self.peers.discard(peer_id)
        return {"status": "peer_removed", "peer": peer_id}
    
    def store_pattern(self, pattern: EEGPattern) -> Dict:
        """Store an EEG pattern in the node."""
        self.patterns.append(pattern)
        self.data_store[f"pattern_{pattern.pattern_id}"] = pattern.to_dict()
        self.energy += 0.05
        return {"status": "stored", "pattern_id": pattern.pattern_id}
    
    def store_event(self, event: DNAEvent) -> Dict:
        """Store a DNA event in the node."""
        self.events.append(event)
        self.data_store[f"event_{event.event_id}"] = event.to_dict()
        self.energy += 0.05
        return {"status": "stored", "event_id": event.event_id}
    
    def learn_from_data(self, data: Dict) -> Dict:
        """Learn from incoming data and update the node."""
        learning_result = {
            "patterns_learned": 0,
            "events_learned": 0,
            "connections_updated": 0
        }
        
        if "pattern" in data:
            pattern_data = data["pattern"]
            if isinstance(pattern_data, EEGPattern):
                self.store_pattern(pattern_data)
                learning_result["patterns_learned"] += 1
        
        if "event" in data:
            event_data = data["event"]
            if isinstance(event_data, DNAEvent):
                self.store_event(event_data)
                learning_result["events_learned"] += 1
        
        # Update learning history
        self.learning_history.append({
            "data": data,
            "learning_result": learning_result,
            "timestamp": get_timestamp()
        })
        
        self.energy += 0.1
        self.growth_count += 1
        
        return {
            "status": "learned",
            "learning_result": learning_result,
            "node_energy": self.energy
        }
    
    def broadcast(self, message: Dict) -> Dict:
        """Broadcast a message to all peers."""
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
        """Receive and process a message."""
        self.message_queue.put(message)
        return {
            "status": "received",
            "from": message.get("from", "unknown"),
            "message_id": message.get("id", "unknown")
        }
    
    def heartbeat(self) -> Dict:
        """Send a heartbeat."""
        self.last_heartbeat = get_timestamp()
        self.energy += 0.01
        return {
            "node_id": self.node_id,
            "status": "alive",
            "timestamp": self.last_heartbeat,
            "patterns": len(self.patterns),
            "events": len(self.events),
            "peers": len(self.peers),
            "energy": self.energy
        }
    
    def get_status(self) -> Dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "peers": list(self.peers),
            "patterns": len(self.patterns),
            "events": len(self.events),
            "learning_history": len(self.learning_history),
            "energy": self.energy,
            "entropy": self.entropy,
            "growth_count": self.growth_count,
            "connections_made": self.connections_made,
            "messages_processed": self.messages_processed,
            "created_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


class DataMeshNetwork:
    """
    The data mesh network that grows and learns together.
    """
    
    def __init__(self, network_id: str = "data_mesh"):
        self.network_id = network_id
        self.nodes: Dict[str, DataMeshNode] = {}
        self.node_connections: Dict[str, List[str]] = defaultdict(list)
        self.network_energy = 50.0
        self.network_entropy = 0.0
        self.growth_cycles = 0
        self.created_at = get_timestamp()
        self.shared_patterns: List[EEGPattern] = []
        self.shared_events: List[DNAEvent] = []
        self.learning_history: List[Dict] = []
        
        # Initialize mesh nodes
        self._initialize_mesh()
    
    def _initialize_mesh(self):
        """Initialize the data mesh with nodes."""
        print(Color.CYAN + "🌐 Initializing Data Mesh..." + Color.END)
        
        node_names = ["MESH_ALPHA", "MESH_BETA", "MESH_GAMMA", "MESH_DELTA", "MESH_EPSILON"]
        
        for name in node_names:
            node = DataMeshNode(name, "mesh")
            self.nodes[name] = node
            self.node_connections[name] = []
        
        # Connect nodes in a mesh
        node_ids = list(self.nodes.keys())
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                if random.random() < 0.7:
                    self._connect_nodes(node_ids[i], node_ids[j])
        
        print(f"   ✅ Created {len(self.nodes)} nodes")
        print(f"   ✅ Created {self._count_connections()} connections")
    
    def _connect_nodes(self, node1_id: str, node2_id: str) -> Dict:
        if node1_id not in self.nodes or node2_id not in self.nodes:
            return {"status": "error", "reason": "node_not_found"}
        
        node1 = self.nodes[node1_id]
        node2 = self.nodes[node2_id]
        
        node1.add_peer(node2_id)
        node2.add_peer(node1_id)
        
        if node2_id not in self.node_connections[node1_id]:
            self.node_connections[node1_id].append(node2_id)
        if node1_id not in self.node_connections[node2_id]:
            self.node_connections[node2_id].append(node1_id)
        
        self.network_energy += 0.5
        return {"status": "connected", "node1": node1_id, "node2": node2_id}
    
    def _count_connections(self) -> int:
        total = 0
        seen = set()
        for node_id, peers in self.node_connections.items():
            for peer in peers:
                if (node_id, peer) not in seen and (peer, node_id) not in seen:
                    seen.add((node_id, peer))
                    total += 1
        return total
    
    def add_node(self, node_id: str, node_type: str = "mesh") -> DataMeshNode:
        if node_id in self.nodes:
            return self.nodes[node_id]
        
        node = DataMeshNode(node_id, node_type)
        self.nodes[node_id] = node
        self.node_connections[node_id] = []
        
        # Connect to existing nodes
        for existing_id in list(self.nodes.keys())[:3]:
            if existing_id != node_id:
                self._connect_nodes(node_id, existing_id)
        
        self.network_energy += 2.0
        return node
    
    def propagate_pattern(self, pattern: EEGPattern) -> Dict:
        """Propagate an EEG pattern through the mesh."""
        propagation_results = []
        
        for node in self.nodes.values():
            result = node.store_pattern(pattern)
            propagation_results.append(result)
            
            # Broadcast to peers
            if len(node.peers) > 0:
                node.broadcast({"type": "pattern_propagation", "pattern_id": pattern.pattern_id})
        
        self.shared_patterns.append(pattern)
        self.network_energy += 0.1
        
        return {
            "status": "propagated",
            "pattern_id": pattern.pattern_id,
            "nodes_reached": len(propagation_results)
        }
    
    def propagate_event(self, event: DNAEvent) -> Dict:
        """Propagate a DNA event through the mesh."""
        propagation_results = []
        
        for node in self.nodes.values():
            result = node.store_event(event)
            propagation_results.append(result)
            
            if len(node.peers) > 0:
                node.broadcast({"type": "event_propagation", "event_id": event.event_id})
        
        self.shared_events.append(event)
        self.network_energy += 0.1
        
        return {
            "status": "propagated",
            "event_id": event.event_id,
            "nodes_reached": len(propagation_results)
        }
    
    def mesh_learn(self, data: Dict) -> Dict:
        """All nodes learn from data together."""
        learning_results = []
        
        for node in self.nodes.values():
            result = node.learn_from_data(data)
            learning_results.append(result)
        
        self.learning_history.append({
            "data": data,
            "learning_results": learning_results,
            "timestamp": get_timestamp()
        })
        
        self.network_energy += 0.2
        
        return {
            "status": "learned",
            "nodes": len(learning_results),
            "results": learning_results
        }
    
    def grow_mesh(self) -> Dict:
        """Grow the mesh based on learning and patterns."""
        self.growth_cycles += 1
        
        growth_actions = []
        
        # Add new node if energy is sufficient
        if self.network_energy > 15.0 and len(self.nodes) < 10:
            new_id = f"MESH_{len(self.nodes) + 1}"
            self.add_node(new_id)
            growth_actions.append(f"added_node_{new_id}")
            self.network_energy -= 5.0
        
        # Create new connections
        node_ids = list(self.nodes.keys())
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                if node_ids[j] not in self.node_connections[node_ids[i]]:
                    if random.random() < 0.2:  # 20% chance of new connection
                        self._connect_nodes(node_ids[i], node_ids[j])
                        growth_actions.append(f"connected_{node_ids[i]}_{node_ids[j]}")
                        self.network_energy -= 0.5
        
        # Share patterns across nodes
        if self.shared_patterns and len(self.shared_patterns) > 0:
            pattern = self.shared_patterns[-1]
            self.propagate_pattern(pattern)
            growth_actions.append("propagated_pattern")
        
        return {
            "status": "grown",
            "growth_actions": growth_actions,
            "nodes": len(self.nodes),
            "connections": self._count_connections(),
            "network_energy": self.network_energy
        }
    
    def get_status(self) -> Dict:
        return {
            "network_id": self.network_id,
            "nodes": len(self.nodes),
            "connections": self._count_connections(),
            "network_energy": self.network_energy,
            "network_entropy": self.network_entropy,
            "growth_cycles": self.growth_cycles,
            "shared_patterns": len(self.shared_patterns),
            "shared_events": len(self.shared_events),
            "learning_history": len(self.learning_history),
            "created_at": self.created_at
        }
    
    def to_dict(self) -> Dict:
        return {
            "network_id": self.network_id,
            "nodes": {nid: node.get_status() for nid, node in self.nodes.items()},
            "connections": self.node_connections,
            "shared_patterns": [p.to_dict() for p in self.shared_patterns[-10:]],
            "shared_events": [e.to_dict() for e in self.shared_events[-10:]],
            "status": self.get_status()
        }


# ──────────────────────────────────────────────────────────────
# 6. MAIN DATA MESH SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxwellDataMeshSystem:
    """Complete data mesh system with DNA, EEG, Twin, and Network."""
    
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🌐 MAXWELL DATA MESH SYSTEM" + Color.END)
        print(Color.CYAN + "   DNA → EEG → Twin → Network Growth" + Color.END)
        print("=" * 70)
        
        # Initialize components
        print(Color.CYAN + "🧬 Initializing DNA Event System..." + Color.END)
        self.dna_events = DNAEventSystem()
        
        print(Color.CYAN + "🧠 Initializing EEG Generator..." + Color.END)
        self.eeg_generator = EEGGenerator()
        
        print(Color.CYAN + "🔧 Initializing Twin Damage Detector..." + Color.END)
        self.twin_detector = TwinDamageDetector()
        
        print(Color.CYAN + "🌐 Initializing Data Mesh Network..." + Color.END)
        self.mesh = DataMeshNetwork()
        
        self.total_energy = 100.0
        self.total_entropy = 0.0
        self.event_count = 0
        self.pattern_count = 0
        
        print(Color.GREEN + "✅ Data Mesh System initialized" + Color.END)
        print("=" * 70 + "\n")
    
    def create_event_cycle(self) -> Dict:
        """Create a full event cycle through the mesh."""
        print(f"\n{Color.YELLOW}⚡ Creating Event Cycle..." + Color.END)
        
        # 1. Create a DNA event
        event = self.dna_events.create_event()
        self.event_count += 1
        print(f"   🧬 DNA Event: {event.event_type} ({event.intensity:.2f})")
        
        # 2. Generate EEG pattern from event
        pattern = self.eeg_generator.generate_from_event(event)
        self.pattern_count += 1
        print(f"   🧠 EEG Pattern: {pattern.pattern_id} ({pattern.get_dominant_band()})")
        
        # 3. Detect damage in Twin
        damage_result = self.twin_detector.detect_damage_from_event(event)
        print(f"   🔧 Twin Damage: {damage_result['damage_level']:.2f}")
        
        # 4. Propagate through mesh
        mesh_result = self.mesh.propagate_event(event)
        print(f"   🌐 Mesh: {mesh_result['nodes_reached']} nodes")
        
        # 5. Propagate EEG pattern
        pattern_result = self.mesh.propagate_pattern(pattern)
        
        # 6. Mesh learns from the data
        learning_result = self.mesh.mesh_learn({
            "event": event.to_dict(),
            "pattern": pattern.to_dict(),
            "damage": damage_result
        })
        print(f"   📊 Mesh Learning: {learning_result['nodes']} nodes")
        
        # 7. Repair if needed
        if damage_result["repair_needed"]:
            repair_result = self.twin_detector.initiate_repair()
            print(f"   🔧 Twin Repair: {len(repair_result['repairs'])} repairs")
        
        # 8. Grow mesh
        growth_result = self.mesh.grow_mesh()
        print(f"   🌱 Mesh Growth: {len(growth_result['growth_actions'])} actions")
        
        self.total_energy += 0.5
        self.total_entropy += 0.02
        
        return {
            "event": event.to_dict(),
            "pattern": pattern.to_dict(),
            "damage": damage_result,
            "mesh": mesh_result,
            "learning": learning_result,
            "growth": growth_result
        }
    
    def autonomous_cycle(self) -> Dict:
        """Run one autonomous cycle of the system."""
        print(f"\n{Color.YELLOW}🔄 Autonomous Cycle {self.mesh.growth_cycles + 1}" + Color.END)
        print("─" * 50)
        
        result = self.create_event_cycle()
        
        print(f"\n{Color.CYAN}📊 Cycle Summary:" + Color.END)
        print(f"   Events: {self.event_count}")
        print(f"   Patterns: {self.pattern_count}")
        print(f"   Nodes: {len(self.mesh.nodes)}")
        print(f"   Connections: {self.mesh._count_connections()}")
        print(f"   Energy: {self.total_energy:.2f}")
        print(f"   Entropy: {self.total_entropy:.4f}")
        
        return result
    
    def show_status(self):
        """Show system status."""
        dna_stats = self.dna_events.get_stats()
        eeg_stats = self.eeg_generator.get_stats()
        twin_status = self.twin_detector.get_damage_status()
        mesh_status = self.mesh.get_status()
        
        print(f"\n{Color.CYAN}📊 DATA MESH STATUS" + Color.END)
        print("=" * 60)
        
        print(f"\n{Color.BOLD}🧬 DNA Events:" + Color.END)
        print(f"   Total: {dna_stats['total_events']}")
        print(f"   Active: {dna_stats['active_events']}")
        print(f"   Energy: {dna_stats['total_energy']:.2f}")
        print(f"   Damage: {dna_stats['damage_accumulated']:.2f}")
        
        print(f"\n{Color.BOLD}🧠 EEG Patterns:" + Color.END)
        print(f"   Total: {eeg_stats['total_patterns']}")
        print(f"   Energy: {eeg_stats['total_energy']:.2f}")
        
        print(f"\n{Color.BOLD}🔧 Twin Damage:" + Color.END)
        print(f"   Active Damage: {twin_status['damage_count']}")
        print(f"   Repairs: {twin_status['total_repairs']}")
        print(f"   Efficiency: {twin_status['repair_efficiency']:.2%}")
        print(f"   Memristor: {[round(v, 2) for v in twin_status['memristor_state']]}")
        
        print(f"\n{Color.BOLD}🌐 Data Mesh:" + Color.END)
        print(f"   Nodes: {mesh_status['nodes']}")
        print(f"   Connections: {mesh_status['connections']}")
        print(f"   Network Energy: {mesh_status['network_energy']:.2f}")
        print(f"   Growth Cycles: {mesh_status['growth_cycles']}")
        print(f"   Shared Patterns: {mesh_status['shared_patterns']}")
        print(f"   Shared Events: {mesh_status['shared_events']}")
        
        print("\n" + "=" * 60)
    
    def run_demo(self):
        """Run a full demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 DATA MESH DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        print(f"\n{Color.BOLD}Step 1: Running Autonomous Cycles" + Color.END)
        for i in range(5):
            self.autonomous_cycle()
            time.sleep(0.3)
        
        print(f"\n{Color.BOLD}Step 2: Final System Status" + Color.END)
        self.show_status()
        
        print(f"\n{Color.BOLD}Step 3: Mesh Network Visualization" + Color.END)
        print("=" * 60)
        for node_id, node in self.mesh.nodes.items():
            status = node.get_status()
            print(f"\n{Color.BOLD}{node_id}" + Color.END)
            print(f"   Peers: {status['peers']}")
            print(f"   Patterns: {status['patterns']}")
            print(f"   Events: {status['events']}")
            print(f"   Learning: {status['learning_history']}")
            print(f"   Energy: {status['energy']:.2f}")
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)
    
    def run_autonomous(self, cycles: int = 5):
        """Run autonomous cycles."""
        print(f"\n{Color.CYAN}🤖 RUNNING AUTONOMOUSLY FOR {cycles} CYCLES" + Color.END)
        print("=" * 70)
        
        for i in range(cycles):
            self.autonomous_cycle()
            time.sleep(0.3)
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ AUTONOMOUS RUN COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 7. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxwellDataMeshSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🌐 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show system status")
        print("   - cycle         - Run one event cycle")
        print("   - auto <n>      - Run n autonomous cycles")
        print("   - demo          - Run full demonstration")
        print("   - help          - Show help")
        print("   - exit          - Quit")
        print("=" * 70 + "\n")
        
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip().lower()
                
                if cmd == "exit":
                    break
                elif cmd == "status":
                    system.show_status()
                elif cmd == "cycle":
                    system.autonomous_cycle()
                elif cmd.startswith("auto"):
                    parts = cmd.split()
                    cycles = int(parts[1]) if len(parts) > 1 else 3
                    system.run_autonomous(cycles)
                elif cmd == "demo":
                    system.run_demo()
                elif cmd == "help":
                    print("\n   Available commands:")
                    print("   status        - Show system status")
                    print("   cycle         - Run one event cycle")
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
