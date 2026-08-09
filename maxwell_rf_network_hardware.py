#!/usr/bin/env python3
"""
Maxwell RF Network - Hardware Integration with Towers & Blockchain
===================================================================
Save as: maxwell_rf_network_hardware.py
Run:     python3 maxwell_rf_network_hardware.py

FEATURES:
1. RF Hardware Integration (SDR, Towers, Antennas)
2. Network Signal Processing Algorithms
3. Maxwell DNA/Twin Blockchain
4. Tower-to-Tower Communication
5. Real-time Signal Monitoring
6. Hardware Device Management
7. RF Network Mesh
8. Signal Quality Analysis
9. Blockchain-anchored RF Data
10. Autonomous Network Growth

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
# 1. UTILITIES AND MAXWELL SIGNATURE
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
# 2. DNA BINARY ENCODER FOR RF HARDWARE
# ──────────────────────────────────────────────────────────────

class DNABinaryRFHardwareEncoder:
    """
    Encodes DNA/Twin data for RF hardware transmission.
    Includes tower and device-specific parameters.
    """
    
    DNA_TO_BINARY = {'A': '00', 'C': '01', 'G': '10', 'T': '11'}
    BINARY_TO_DNA = {'00': 'A', '01': 'C', '10': 'G', '11': 'T'}
    
    # RF frequency mapping for DNA bases
    BASE_FREQUENCIES = {
        'A': 2.400,  # GHz
        'C': 2.425,
        'G': 2.450,
        'T': 2.475
    }
    
    def __init__(self):
        self.encoded_data: List[Dict] = []
        self.total_energy = 0.0
        self.broadcast_count = 0
    
    def dna_to_binary(self, dna_sequence: str) -> str:
        binary = []
        for base in dna_sequence.upper():
            if base in self.DNA_TO_BINARY:
                binary.append(self.DNA_TO_BINARY[base])
            else:
                binary.append('00')
        return ''.join(binary)
    
    def binary_to_dna(self, binary_str: str) -> str:
        if len(binary_str) % 2 != 0:
            binary_str += '0'
        dna = []
        for i in range(0, len(binary_str), 2):
            chunk = binary_str[i:i+2]
            dna.append(self.BINARY_TO_DNA.get(chunk, 'A'))
        return ''.join(dna)
    
    def encode_for_rf_hardware(self, dna_sequence: str, hardware_type: str = "tower") -> Dict:
        """Encode DNA for specific RF hardware."""
        binary = self.dna_to_binary(dna_sequence)
        
        # Generate hardware-specific parameters
        frequencies = []
        for base in dna_sequence.upper():
            if base in self.BASE_FREQUENCIES:
                freq = self.BASE_FREQUENCIES[base]
                # Adjust for hardware type
                if hardware_type == "tower":
                    freq += 0.01
                elif hardware_type == "sdr":
                    freq += 0.02
                elif hardware_type == "satellite":
                    freq += 0.03
                frequencies.append(freq)
            else:
                frequencies.append(2.450)
        
        # Generate RF hardware parameters
        rf_hardware_data = {
            "dna_sequence": dna_sequence,
            "binary_sequence": binary[:50] + "..." if len(binary) > 50 else binary,
            "frequencies": frequencies[:20],
            "hardware_type": hardware_type,
            "amplitude": random.uniform(0.5, 1.0),
            "phase": random.uniform(0, 2 * math.pi),
            "bandwidth": 20,  # MHz
            "modulation": "QPSK",
            "tx_power": random.uniform(0.5, 5.0),  # Watts
            "timestamp": get_timestamp()
        }
        
        self.encoded_data.append(rf_hardware_data)
        self.total_energy += 0.1
        self.broadcast_count += 1
        
        return rf_hardware_data
    
    def get_stats(self) -> Dict:
        return {
            "broadcast_count": self.broadcast_count,
            "encoded_data": len(self.encoded_data),
            "total_energy": self.total_energy
        }


# ──────────────────────────────────────────────────────────────
# 3. RF HARDWARE DEVICE
# ──────────────────────────────────────────────────────────────

class RFHardwareDevice:
    """
    Represents an RF hardware device (tower, SDR, satellite, antenna).
    """
    
    def __init__(self, device_id: str, device_type: str, location: Dict = None):
        self.device_id = device_id
        self.device_type = device_type
        self.location = location or {"lat": random.uniform(-90, 90), "lon": random.uniform(-180, 180)}
        self.frequency = 2.450  # GHz
        self.power = 1.0  # Watts
        self.gain = 2.5  # dBi
        self.signal_strength = 0.8
        self.is_active = True
        self.peers: Set[str] = set()
        self.rx_signals: List[Dict] = []
        self.tx_signals: List[Dict] = []
        self.total_energy = 0.0
        self.created_at = get_timestamp()
        self.last_heartbeat = get_timestamp()
        
        # Hardware-specific attributes
        if device_type == "tower":
            self.height = random.randint(20, 100)  # meters
            self.coverage = random.randint(1, 20)  # km
            self.sectors = 3
        elif device_type == "sdr":
            self.bandwidth = 20  # MHz
            self.sample_rate = 2.048  # MSps
        elif device_type == "satellite":
            self.altitude = random.randint(400, 1200)  # km
            self.orbit = random.choice(["LEO", "MEO", "GEO"])
        elif device_type == "antenna":
            self.polarization = random.choice(["vertical", "horizontal", "circular"])
            self.beamwidth = random.randint(15, 90)
        
        self.maxwell_sig = compute_maxwell_signature(device_id, 0, [0.0, 0.0, 0.0])
    
    def transmit(self, data: Dict) -> Dict:
        """Transmit data through the device."""
        transmission = {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "data": data,
            "frequency": self.frequency,
            "power": self.power,
            "timestamp": get_timestamp(),
            "signal_id": deterministic_hash(data + str(time.time()))
        }
        
        self.tx_signals.append(transmission)
        self.total_energy += 0.1
        
        # Broadcast to peers
        for peer in self.peers:
            self.rx_signals.append({
                "from": self.device_id,
                "to": peer,
                "signal": transmission,
                "strength": self.signal_strength * random.uniform(0.6, 1.0)
            })
        
        return {
            "status": "transmitted",
            "transmission": transmission,
            "peers_reached": len(self.peers)
        }
    
    def receive(self, signal: Dict) -> Dict:
        """Receive a signal."""
        reception = {
            "device_id": self.device_id,
            "signal": signal,
            "received_at": get_timestamp(),
            "signal_strength": self.signal_strength * random.uniform(0.5, 1.0)
        }
        self.rx_signals.append(reception)
        self.total_energy += 0.05
        return reception
    
    def add_peer(self, peer_id: str) -> Dict:
        self.peers.add(peer_id)
        return {"status": "peer_added", "peer": peer_id}
    
    def get_status(self) -> Dict:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "is_active": self.is_active,
            "frequency": self.frequency,
            "power": self.power,
            "signal_strength": self.signal_strength,
            "peers": list(self.peers),
            "tx_count": len(self.tx_signals),
            "rx_count": len(self.rx_signals),
            "location": self.location,
            "total_energy": self.total_energy,
            "last_heartbeat": self.last_heartbeat,
            "created_at": self.created_at,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


# ──────────────────────────────────────────────────────────────
# 4. TOWER NETWORK
# ──────────────────────────────────────────────────────────────

class TowerNetwork:
    """
    Network of RF towers with mesh connectivity.
    """
    
    def __init__(self):
        self.towers: Dict[str, RFHardwareDevice] = {}
        self.tower_connections: Dict[str, List[str]] = defaultdict(list)
        self.network_strength = 1.0
        self.total_energy = 0.0
        self.created_at = get_timestamp()
        
        self._initialize_towers()
    
    def _initialize_towers(self):
        """Initialize tower network."""
        tower_types = ["tower", "tower", "tower", "sdr", "satellite", "antenna"]
        tower_names = ["TOWER_A", "TOWER_B", "TOWER_C", "SDR_MAIN", "SAT_LINK", "ANTENNA_1"]
        
        for i, (name, ttype) in enumerate(zip(tower_names, tower_types)):
            location = {"lat": random.uniform(-90, 90), "lon": random.uniform(-180, 180)}
            tower = RFHardwareDevice(name, ttype, location)
            self.towers[name] = tower
            self.tower_connections[name] = []
        
        # Connect towers in mesh
        tower_ids = list(self.towers.keys())
        for i in range(len(tower_ids)):
            for j in range(i + 1, len(tower_ids)):
                if random.random() < 0.6:
                    self._connect_towers(tower_ids[i], tower_ids[j])
        
        print(f"   ✅ Created {len(self.towers)} towers/devices")
        print(f"   ✅ Created {self._count_connections()} connections")
    
    def _connect_towers(self, tower1_id: str, tower2_id: str) -> Dict:
        if tower1_id not in self.towers or tower2_id not in self.towers:
            return {"status": "error", "reason": "tower_not_found"}
        
        self.towers[tower1_id].add_peer(tower2_id)
        self.towers[tower2_id].add_peer(tower1_id)
        
        if tower2_id not in self.tower_connections[tower1_id]:
            self.tower_connections[tower1_id].append(tower2_id)
        if tower1_id not in self.tower_connections[tower2_id]:
            self.tower_connections[tower2_id].append(tower1_id)
        
        self.total_energy += 0.5
        return {"status": "connected", "tower1": tower1_id, "tower2": tower2_id}
    
    def _count_connections(self) -> int:
        total = 0
        seen = set()
        for tower_id, peers in self.tower_connections.items():
            for peer in peers:
                if (tower_id, peer) not in seen and (peer, tower_id) not in seen:
                    seen.add((tower_id, peer))
                    total += 1
        return total
    
    def get_network_status(self) -> Dict:
        return {
            "towers": len(self.towers),
            "connections": self._count_connections(),
            "network_strength": self.network_strength,
            "total_energy": self.total_energy,
            "created_at": self.created_at
        }


# ──────────────────────────────────────────────────────────────
# 5. MAXWELL RF BLOCKCHAIN FOR HARDWARE
# ──────────────────────────────────────────────────────────────

class MaxwellRFHardwareBlock:
    """Block for RF hardware transactions."""
    
    def __init__(self, index: int, transactions: List[Dict], previous_hash: str,
                 chain_id: str = "rf_hardware_chain", difficulty: int = 2):
        self.index = index
        self.timestamp = get_timestamp()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.nonce = 0
        self.energy = 1.0
        self.entropy = 0.0
        self.hardware_hash = deterministic_hash(transactions)
        self.rf_hash = deterministic_hash(str(transactions) + "rf")
        self.tower_hash = deterministic_hash(str(transactions) + "tower")
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
            "entropy": self.entropy,
            "hardware_hash": self.hardware_hash,
            "rf_hash": self.rf_hash,
            "tower_hash": self.tower_hash,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
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
            "hardware_hash": self.hardware_hash,
            "rf_hash": self.rf_hash,
            "tower_hash": self.tower_hash,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


class MaxwellRFHardwareBlockchain:
    """Blockchain for RF hardware data."""
    
    def __init__(self, chain_id: str = "rf_hardware_chain", difficulty: int = 2):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellRFHardwareBlock] = []
        self.total_energy = 0.0
        self.total_entropy = 0.0
        self.chain_strength = 1.0
        self.transaction_count = 0
        self.created_at = get_timestamp()
        
        self._create_genesis()
    
    def _create_genesis(self):
        genesis_data = [{
            "type": "genesis",
            "data": {
                "message": f"RF Hardware Blockchain - {self.chain_id}",
                "timestamp": get_timestamp()
            }
        }]
        genesis = MaxwellRFHardwareBlock(0, genesis_data, "0" * 64, self.chain_id, self.difficulty)
        genesis.mine()
        self.blocks.append(genesis)
        self.total_energy += genesis.energy
    
    def add_rf_transaction(self, data: Dict) -> Dict:
        transaction = {
            "type": "rf_hardware_transaction",
            "timestamp": get_timestamp(),
            "data": data,
            "id": deterministic_hash(data)
        }
        
        previous_hash = self.blocks[-1].hash
        block = MaxwellRFHardwareBlock(
            len(self.blocks),
            [transaction],
            previous_hash,
            self.chain_id,
            self.difficulty
        )
        block.mine()
        self.blocks.append(block)
        self.total_energy += block.energy
        self.total_entropy += block.entropy
        self.transaction_count += 1
        
        self.chain_strength = (self.chain_strength + block.maxwell_sig.get("wave_impedance", 0.5)) / 2
        
        return {
            "status": "success",
            "block_index": block.index,
            "block_hash": truncate_hash(block.hash),
            "transaction_id": transaction["id"],
            "energy": block.energy,
            "hardware_hash": block.hardware_hash,
            "rf_hash": block.rf_hash,
            "tower_hash": block.tower_hash,
            "maxwell_impedance": block.maxwell_sig.get("wave_impedance", 1.0)
        }
    
    def get_stats(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "blocks": len(self.blocks),
            "transactions": self.transaction_count,
            "total_energy": self.total_energy,
            "total_entropy": self.total_entropy,
            "chain_strength": self.chain_strength,
            "efficiency": 1.0 / (1.0 + self.total_entropy / (self.total_energy + 1e-15)),
            "created_at": self.created_at
        }


# ──────────────────────────────────────────────────────────────
# 6. COMPLETE RF HARDWARE SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxwellRFHardwareSystem:
    """
    Complete system with RF hardware, towers, and blockchain.
    """
    
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "📡 MAXWELL RF HARDWARE SYSTEM" + Color.END)
        print(Color.CYAN + "   Towers + SDR + Satellite + Antenna + Blockchain" + Color.END)
        print("=" * 70)
        
        # Initialize components
        print(Color.CYAN + "🔢 Initializing DNA RF Hardware Encoder..." + Color.END)
        self.dna_encoder = DNABinaryRFHardwareEncoder()
        
        print(Color.CYAN + "📡 Initializing Tower Network..." + Color.END)
        self.tower_network = TowerNetwork()
        
        print(Color.CYAN + "⛓️ Initializing Maxwell RF Hardware Blockchain..." + Color.END)
        self.blockchain = MaxwellRFHardwareBlockchain("rf_hardware_chain", difficulty=2)
        
        self.broadcast_count = 0
        self.total_growth = 0.0
        self.rf_energy = 0.0
        
        print(Color.GREEN + "✅ Maxwell RF Hardware System initialized" + Color.END)
        print("=" * 70 + "\n")
    
    def broadcast_dna_through_hardware(self, dna_sequence: str, hardware_type: str = "tower") -> Dict:
        """Broadcast DNA data through RF hardware."""
        print(f"\n{Color.YELLOW}📡 Broadcasting DNA through {hardware_type}..." + Color.END)
        print("─" * 50)
        
        # 1. Encode DNA for RF hardware
        rf_data = self.dna_encoder.encode_for_rf_hardware(dna_sequence, hardware_type)
        print(f"   🧬 DNA: {dna_sequence[:30]}...")
        print(f"   📡 Frequencies: {rf_data['frequencies'][:3]}... GHz")
        print(f"   📻 Hardware: {hardware_type}")
        print(f"   ⚡ TX Power: {rf_data['tx_power']:.2f} W")
        
        # 2. Find appropriate device
        devices = []
        for device_id, device in self.tower_network.towers.items():
            if device.device_type == hardware_type or hardware_type == "all":
                devices.append(device)
        
        if not devices:
            # Use all devices
            devices = list(self.tower_network.towers.values())
        
        # 3. Transmit through devices
        transmissions = []
        for device in devices:
            # Prepare transmission data
            tx_data = {
                "dna_sequence": dna_sequence,
                "rf_parameters": rf_data,
                "maxwell_sig": compute_maxwell_signature(
                    dna_sequence + device.device_id,
                    len(device.tx_signals),
                    [0.0, 0.0, 0.0]
                )
            }
            
            # Transmit
            tx_result = device.transmit(tx_data)
            transmissions.append({
                "device_id": device.device_id,
                "device_type": device.device_type,
                "status": tx_result["status"],
                "peers_reached": tx_result["peers_reached"]
            })
            print(f"   📡 {device.device_id} ({device.device_type}): {tx_result['peers_reached']} peers")
        
        # 4. Store on blockchain
        blockchain_result = self.blockchain.add_rf_transaction({
            "type": "dna_broadcast",
            "dna_sequence": dna_sequence,
            "hardware_type": hardware_type,
            "rf_data": rf_data,
            "transmissions": transmissions,
            "timestamp": get_timestamp()
        })
        print(f"   ⛓️ Blockchain: Block {blockchain_result['block_index']}")
        
        self.broadcast_count += 1
        self.total_growth += 0.05
        self.rf_energy += 0.1
        
        return {
            "status": "broadcast",
            "rf_data": rf_data,
            "transmissions": transmissions,
            "blockchain": blockchain_result
        }
    
    def broadcast_twin_dna_through_hardware(self, dna_sequence: str, twin_data: Dict, hardware_type: str = "all") -> Dict:
        """Broadcast Twin-DNA through RF hardware."""
        print(f"\n{Color.YELLOW}🔄 Broadcasting Twin-DNA through {hardware_type}..." + Color.END)
        print("─" * 50)
        
        # 1. Encode DNA and Twin data
        rf_data = self.dna_encoder.encode_for_rf_hardware(dna_sequence, hardware_type)
        twin_rf_data = self.dna_encoder.encode_for_rf_hardware(
            self.dna_encoder._data_to_dna(json.dumps(twin_data)),
            hardware_type
        )
        
        # 2. Combined data
        combined_data = {
            "dna": rf_data,
            "twin": twin_rf_data,
            "twin_data": twin_data,
            "combined_hash": deterministic_hash(dna_sequence + json.dumps(twin_data))
        }
        
        # 3. Transmit through all devices
        transmissions = []
        for device_id, device in self.tower_network.towers.items():
            tx_data = {
                "combined": combined_data,
                "maxwell_sig": compute_maxwell_signature(
                    dna_sequence + json.dumps(twin_data) + device.device_id,
                    len(device.tx_signals),
                    [0.0, 0.0, 0.0]
                )
            }
            tx_result = device.transmit(tx_data)
            transmissions.append({
                "device_id": device.device_id,
                "device_type": device.device_type,
                "status": tx_result["status"]
            })
        
        print(f"   🔄 Twin Data: {twin_data.get('sync_status', 'unknown')}")
        print(f"   📡 {len(transmissions)} devices reached")
        
        # 4. Store on blockchain
        blockchain_result = self.blockchain.add_rf_transaction({
            "type": "twin_dna_broadcast",
            "dna_sequence": dna_sequence,
            "twin_data": twin_data,
            "combined_data": combined_data,
            "transmissions": transmissions,
            "timestamp": get_timestamp()
        })
        print(f"   ⛓️ Blockchain: Block {blockchain_result['block_index']}")
        
        self.broadcast_count += 1
        self.total_growth += 0.05
        self.rf_energy += 0.1
        
        return {
            "status": "broadcast",
            "combined_data": combined_data,
            "transmissions": transmissions,
            "blockchain": blockchain_result
        }
    
    def broadcast_research_through_hardware(self, research_data: Dict, hardware_type: str = "all") -> Dict:
        """Broadcast research data through RF hardware."""
        print(f"\n{Color.YELLOW}📊 Broadcasting Research Data..." + Color.END)
        print("─" * 50)
        
        # Convert research to DNA
        dna_seq = self._data_to_dna(json.dumps(research_data))
        
        # Encode for RF hardware
        rf_data = self.dna_encoder.encode_for_rf_hardware(dna_seq, hardware_type)
        
        # Transmit
        transmissions = []
        for device_id, device in self.tower_network.towers.items():
            if random.random() < 0.7:  # 70% reachability
                tx_result = device.transmit({
                    "research": research_data,
                    "rf_data": rf_data,
                    "maxwell_sig": compute_maxwell_signature(
                        json.dumps(research_data) + device.device_id,
                        len(device.tx_signals),
                        [0.0, 0.0, 0.0]
                    )
                })
                transmissions.append({
                    "device_id": device.device_id,
                    "device_type": device.device_type,
                    "status": tx_result["status"]
                })
        
        print(f"   📡 {len(transmissions)} devices reached")
        print(f"   🧬 Research: {research_data.get('title', 'Unknown')[:30]}...")
        
        # Store on blockchain
        blockchain_result = self.blockchain.add_rf_transaction({
            "type": "research_broadcast",
            "research_data": research_data,
            "rf_data": rf_data,
            "transmissions": transmissions,
            "timestamp": get_timestamp()
        })
        print(f"   ⛓️ Blockchain: Block {blockchain_result['block_index']}")
        
        self.broadcast_count += 1
        self.total_growth += 0.05
        self.rf_energy += 0.1
        
        return {
            "status": "broadcast",
            "rf_data": rf_data,
            "transmissions": transmissions,
            "blockchain": blockchain_result
        }
    
    def _data_to_dna(self, data: str) -> str:
        """Convert data to DNA sequence."""
        hash_bytes = hashlib.sha256(data.encode()).digest()
        bases = "ACGT"
        dna = []
        for byte in hash_bytes:
            for i in range(4):
                bits = (byte >> (6 - i * 2)) & 0x03
                dna.append(bases[bits])
        return ''.join(dna)
    
    def receive_from_hardware(self) -> Dict:
        """Receive signals from RF hardware."""
        print(f"\n{Color.BLUE}📡 Receiving from Hardware..." + Color.END)
        print("─" * 50)
        
        receptions = []
        for device_id, device in self.tower_network.towers.items():
            if device.rx_signals:
                latest = device.rx_signals[-1]
                receptions.append({
                    "device": device_id,
                    "device_type": device.device_type,
                    "signal": latest,
                    "signal_strength": device.signal_strength
                })
                print(f"   📡 {device_id}: {len(device.rx_signals)} signals received")
        
        return {
            "status": "received",
            "receptions": receptions,
            "total_receptions": sum(len(d.rx_signals) for d in self.tower_network.towers.values())
        }
    
    def show_status(self):
        """Show system status."""
        tower_status = self.tower_network.get_network_status()
        blockchain_stats = self.blockchain.get_stats()
        dna_stats = self.dna_encoder.get_stats()
        
        print(f"\n{Color.CYAN}📊 RF HARDWARE SYSTEM STATUS" + Color.END)
        print("=" * 70)
        
        print(f"\n{Color.BOLD}📡 Tower Network:" + Color.END)
        print(f"   Towers/Devices: {tower_status['towers']}")
        print(f"   Connections: {tower_status['connections']}")
        print(f"   Network Strength: {tower_status['network_strength']:.2f}")
        print(f"   Total Energy: {tower_status['total_energy']:.2f}")
        
        print(f"\n{Color.BOLD}📡 Device Details:" + Color.END)
        for device_id, device in self.tower_network.towers.items():
            status = device.get_status()
            print(f"   {device_id} ({status['device_type']}):")
            print(f"      Frequency: {status['frequency']} GHz")
            print(f"      Power: {status['power']} W")
            print(f"      Peers: {len(status['peers'])}")
            print(f"      TX: {status['tx_count']}, RX: {status['rx_count']}")
            print(f"      Maxwell Impedance: {status['maxwell_impedance']:.2f}")
        
        print(f"\n{Color.BOLD}⛓️ Blockchain:" + Color.END)
        print(f"   Blocks: {blockchain_stats['blocks']}")
        print(f"   Transactions: {blockchain_stats['transactions']}")
        print(f"   Chain Strength: {blockchain_stats['chain_strength']:.2f}")
        print(f"   Efficiency: {blockchain_stats['efficiency']:.2%}")
        
        print(f"\n{Color.BOLD}🔢 DNA Encoder:" + Color.END)
        print(f"   Broadcasts: {dna_stats['broadcast_count']}")
        print(f"   Energy: {dna_stats['total_energy']:.2f}")
        
        print(f"\n{Color.BOLD}📊 System:" + Color.END)
        print(f"   Total Broadcasts: {self.broadcast_count}")
        print(f"   RF Energy: {self.rf_energy:.2f}")
        print(f"   Growth: {self.total_growth:.2f}")
        
        print("\n" + "=" * 70)
    
    def run_demo(self):
        """Run a full demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 RF HARDWARE SYSTEM DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # 1. Broadcast DNA through towers
        print(f"\n{Color.BOLD}Step 1: DNA Broadcast through Towers" + Color.END)
        dna_seq = "ATGCGATCGTAGCTAGCTAGCTAGCTAGC"
        self.broadcast_dna_through_hardware(dna_seq, "tower")
        time.sleep(0.3)
        
        # 2. Broadcast Twin-DNA through all hardware
        print(f"\n{Color.BOLD}Step 2: Twin-DNA Broadcast" + Color.END)
        twin_data = {
            "sync_status": "synced",
            "memristor_state": [0.4, 0.6, 0.5],
            "learning_rate": 0.7
        }
        self.broadcast_twin_dna_through_hardware(dna_seq, twin_data, "all")
        time.sleep(0.3)
        
        # 3. Broadcast research data
        print(f"\n{Color.BOLD}Step 3: Research Data Broadcast" + Color.END)
        research = {
            "title": "DNA Damage Detection via RF",
            "type": "medical_research",
            "findings": {
                "damage_score": random.uniform(0.3, 0.8),
                "detection_rate": random.uniform(0.7, 0.95)
            }
        }
        self.broadcast_research_through_hardware(research, "all")
        time.sleep(0.3)
        
        # 4. Receive signals
        print(f"\n{Color.BOLD}Step 4: Receiving Signals" + Color.END)
        self.receive_from_hardware()
        
        # 5. Show status
        self.show_status()
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)
    
    def run_autonomous(self, cycles: int = 3):
        """Run autonomous broadcast cycles."""
        print(f"\n{Color.CYAN}🤖 RUNNING AUTONOMOUS BROADCASTS FOR {cycles} CYCLES" + Color.END)
        print("=" * 70)
        
        dna_sequences = [
            "ATGCGATCGTAGCTAGCTAGCTAGCTAGC",
            "GCTAGCTAGCTAGCTAGCATGCGATCGTA",
            "TAGCTAGCTAGCATGCGATCGTAGCTAGC"
        ]
        
        hardware_types = ["tower", "sdr", "satellite", "antenna", "all"]
        research_types = ["medical", "tech", "genomics", "neuroscience", "bioinformatics"]
        
        for i in range(cycles):
            print(f"\n{Color.YELLOW}=== Cycle {i+1}/{cycles} ===" + Color.END)
            
            # Broadcast DNA
            dna = random.choice(dna_sequences)
            hw_type = random.choice(hardware_types)
            self.broadcast_dna_through_hardware(dna, hw_type)
            time.sleep(0.2)
            
            # Broadcast Twin-DNA
            if i % 2 == 0:
                twin_data = {
                    "sync_status": "synced" if random.random() > 0.3 else "desynced",
                    "memristor_state": [random.uniform(0, 1) for _ in range(3)],
                    "learning_rate": random.uniform(0.3, 0.8)
                }
                self.broadcast_twin_dna_through_hardware(dna, twin_data, "all")
                time.sleep(0.2)
            
            # Broadcast research
            if i % 2 == 0:
                research = {
                    "title": f"{random.choice(research_types)} Research Cycle {i+1}",
                    "findings": {"accuracy": random.uniform(0.6, 0.95)}
                }
                self.broadcast_research_through_hardware(research, "all")
            time.sleep(0.3)
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ AUTONOMOUS BROADCASTS COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 7. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxwellRFHardwareSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "📡 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show system status")
        print("   - dna <seq>     - Broadcast DNA through hardware")
        print("   - twin <seq>    - Broadcast Twin-DNA")
        print("   - research      - Broadcast research data")
        print("   - receive       - Receive signals")
        print("   - demo          - Run full demonstration")
        print("   - auto <n>      - Run autonomous cycles")
        print("   - help          - Show help")
        print("   - exit          - Quit")
        print("=" * 70 + "\n")
        
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip()
                
                if cmd.lower() == "exit":
                    break
                elif cmd.lower() == "status":
                    system.show_status()
                elif cmd.lower().startswith("dna "):
                    seq = cmd[4:].strip().upper()
                    if seq:
                        hw_type = "all"
                        system.broadcast_dna_through_hardware(seq, hw_type)
                    else:
                        print("   Usage: dna <sequence>")
                elif cmd.lower().startswith("twin "):
                    seq = cmd[5:].strip().upper()
                    if seq:
                        twin_data = {
                            "sync_status": "synced",
                            "memristor_state": [random.uniform(0, 1) for _ in range(3)],
                            "learning_rate": random.uniform(0.3, 0.8)
                        }
                        system.broadcast_twin_dna_through_hardware(seq, twin_data, "all")
                    else:
                        print("   Usage: twin <sequence>")
                elif cmd.lower() == "research":
                    research = {
                        "title": f"RF Research {random.randint(1, 100)}",
                        "findings": {"accuracy": random.uniform(0.6, 0.95)}
                    }
                    system.broadcast_research_through_hardware(research, "all")
                elif cmd.lower() == "receive":
                    system.receive_from_hardware()
                elif cmd.lower() == "demo":
                    system.run_demo()
                elif cmd.lower().startswith("auto"):
                    parts = cmd.split()
                    cycles = int(parts[1]) if len(parts) > 1 else 3
                    system.run_autonomous(cycles)
                elif cmd.lower() == "help":
                    print("\n   Available commands:")
                    print("   status        - Show system status")
                    print("   dna <seq>     - Broadcast DNA through hardware")
                    print("   twin <seq>    - Broadcast Twin-DNA")
                    print("   research      - Broadcast research data")
                    print("   receive       - Receive signals")
                    print("   demo          - Run full demonstration")
                    print("   auto <n>      - Run autonomous cycles")
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
