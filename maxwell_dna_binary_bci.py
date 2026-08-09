#!/usr/bin/env python3
"""
Maxwell DNA Binary Code Interpreter - BCI Medical Research System
=================================================================
Save as: maxwell_dna_binary_bci.py
Run:     python3 maxwell_dna_binary_bci.py

FEATURES:
1. DNA Binary Code Interpreter (A=00, C=01, G=10, T=11)
2. Network Hubs with blockchain blocks
3. Data Twin DNA BCI for AI communication
4. Medical research integration
5. Pattern-to-binary conversion
6. Binary-to-DNA encoding/decoding
7. Blockchain storage of binary DNA data
8. AI communication via BCI
9. Research data mining
10. Autonomous growth cycles

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
# 2. DNA BINARY CODE INTERPRETER
# ──────────────────────────────────────────────────────────────

class DNABinaryInterpreter:
    """
    Converts between DNA sequences and binary data.
    A=00, C=01, G=10, T=11
    """
    
    DNA_TO_BINARY = {
        'A': '00',
        'C': '01',
        'G': '10',
        'T': '11'
    }
    
    BINARY_TO_DNA = {
        '00': 'A',
        '01': 'C',
        '10': 'G',
        '11': 'T'
    }
    
    def __init__(self):
        self.encoding_history: List[Dict] = []
        self.decoding_history: List[Dict] = []
        self.total_energy = 0.0
        self.bit_count = 0
        self.base_count = 0
    
    def dna_to_binary(self, dna_sequence: str) -> str:
        """Convert DNA sequence to binary string."""
        binary_result = []
        for base in dna_sequence.upper():
            if base in self.DNA_TO_BINARY:
                binary_result.append(self.DNA_TO_BINARY[base])
                self.base_count += 1
            else:
                # Unknown base - use '00' as fallback
                binary_result.append('00')
        
        binary_str = ''.join(binary_result)
        self.bit_count += len(binary_str)
        self.total_energy += 0.01 * len(dna_sequence)
        
        # Record encoding
        self.encoding_history.append({
            "dna": dna_sequence[:50] + "...",
            "binary": binary_str[:50] + "...",
            "bits": len(binary_str),
            "bases": len(dna_sequence),
            "timestamp": get_timestamp()
        })
        
        return binary_str
    
    def binary_to_dna(self, binary_string: str) -> str:
        """Convert binary string to DNA sequence."""
        # Ensure even length
        if len(binary_string) % 2 != 0:
            binary_string = binary_string + '0'
        
        dna_result = []
        for i in range(0, len(binary_string), 2):
            chunk = binary_string[i:i+2]
            if chunk in self.BINARY_TO_DNA:
                dna_result.append(self.BINARY_TO_DNA[chunk])
                self.base_count += 1
            else:
                dna_result.append('A')  # Fallback
        
        dna_str = ''.join(dna_result)
        self.bit_count += len(binary_string)
        self.total_energy += 0.01 * len(dna_str)
        
        # Record decoding
        self.decoding_history.append({
            "binary": binary_string[:50] + "...",
            "dna": dna_str[:50] + "...",
            "bits": len(binary_string),
            "bases": len(dna_str),
            "timestamp": get_timestamp()
        })
        
        return dna_str
    
    def encode_data(self, data: Any) -> Dict:
        """Encode any data to DNA sequence."""
        # Convert data to JSON string
        json_str = json.dumps(data, default=str)
        # Convert to bytes
        data_bytes = json_str.encode('utf-8')
        # Convert to binary
        binary_str = ''.join(format(byte, '08b') for byte in data_bytes)
        # Convert to DNA
        dna_sequence = self.binary_to_dna(binary_str)
        
        return {
            "original_data": data,
            "dna_sequence": dna_sequence,
            "binary_length": len(binary_str),
            "dna_length": len(dna_sequence),
            "timestamp": get_timestamp()
        }
    
    def decode_data(self, dna_sequence: str) -> Any:
        """Decode DNA sequence back to original data."""
        # Convert DNA to binary
        binary_str = self.dna_to_binary(dna_sequence)
        # Convert binary to bytes
        byte_array = bytearray()
        for i in range(0, len(binary_str), 8):
            if i + 8 <= len(binary_str):
                byte = int(binary_str[i:i+8], 2)
                byte_array.append(byte)
        # Decode bytes to string
        try:
            json_str = byte_array.decode('utf-8')
            data = json.loads(json_str)
            return {
                "data": data,
                "dna_sequence": dna_sequence,
                "decoded": True,
                "timestamp": get_timestamp()
            }
        except Exception as e:
            return {
                "error": str(e),
                "dna_sequence": dna_sequence,
                "decoded": False,
                "timestamp": get_timestamp()
            }
    
    def get_stats(self) -> Dict:
        return {
            "total_encodings": len(self.encoding_history),
            "total_decodings": len(self.decoding_history),
            "total_bits": self.bit_count,
            "total_bases": self.base_count,
            "total_energy": self.total_energy
        }


# ──────────────────────────────────────────────────────────────
# 3. DATA TWIN DNA BCI
# ──────────────────────────────────────────────────────────────

class DataTwinDNABCI:
    """
    Brain-Computer Interface using DNA binary encoding.
    Communicates with AI through DNA patterns.
    """
    
    def __init__(self, bci_id: str = "BCI_DNA_TWIN"):
        self.bci_id = bci_id
        self.binary_interpreter = DNABinaryInterpreter()
        self.dna_patterns: Dict[str, Dict] = {}
        self.bci_signals: List[Dict] = []
        self.ai_messages: List[Dict] = []
        self.bci_state = {
            "active": True,
            "channel": "dna_binary",
            "frequency": 2.4,  # GHz
            "signal_strength": 0.85
        }
        self.total_energy = 0.0
        
        # Maxwell signature for BCI
        self.maxwell_sig = compute_maxwell_signature(bci_id, 0, [0.0, 0.0, 0.0])
        
        # EEG mapping to DNA
        self.eeg_to_dna = {
            "delta": "A",
            "theta": "C",
            "alpha": "G",
            "beta": "T",
            "gamma": "A"
        }
    
    def eeg_to_dna_pattern(self, eeg_bands: Dict[str, float]) -> str:
        """Convert EEG band powers to DNA sequence."""
        dna_sequence = []
        for band, power in eeg_bands.items():
            if band in self.eeg_to_dna:
                # Map power to number of bases
                count = int(power * 4) + 1
                dna_sequence.append(self.eeg_to_dna[band] * min(count, 4))
        
        return ''.join(dna_sequence)[:100]  # Limit length
    
    def encode_message_to_dna(self, message: str) -> Dict:
        """Encode a message to DNA for AI communication."""
        # Convert message to binary via DNA
        data = {
            "type": "bci_message",
            "message": message,
            "timestamp": get_timestamp(),
            "bci_id": self.bci_id
        }
        
        # Encode to DNA
        encoded = self.binary_interpreter.encode_data(data)
        
        # Store pattern
        pattern_id = deterministic_hash(encoded["dna_sequence"])
        self.dna_patterns[pattern_id] = {
            "pattern_id": pattern_id,
            "dna_sequence": encoded["dna_sequence"],
            "message": message,
            "timestamp": get_timestamp()
        }
        
        self.bci_signals.append({
            "type": "encode",
            "message": message,
            "pattern_id": pattern_id,
            "timestamp": get_timestamp()
        })
        
        self.total_energy += 0.1
        
        return {
            "status": "encoded",
            "pattern_id": pattern_id,
            "dna_sequence": encoded["dna_sequence"][:50] + "...",
            "message": message,
            "bci_state": self.bci_state
        }
    
    def decode_message_from_dna(self, dna_sequence: str) -> Dict:
        """Decode a message from DNA sequence."""
        decoded = self.binary_interpreter.decode_data(dna_sequence)
        
        if decoded.get("decoded"):
            data = decoded.get("data", {})
            message = data.get("message", "Unknown")
            
            self.ai_messages.append({
                "type": "decode",
                "message": message,
                "timestamp": get_timestamp()
            })
            
            return {
                "status": "decoded",
                "message": message,
                "data": data,
                "timestamp": get_timestamp()
            }
        
        return {
            "status": "error",
            "error": decoded.get("error", "Unknown error"),
            "dna_sequence": dna_sequence
        }
    
    def communicate_with_ai(self, command: str) -> Dict:
        """Communicate with AI using DNA BCI."""
        # Encode command to DNA
        encoded = self.encode_message_to_dna(command)
        
        # Simulate AI processing the DNA pattern
        ai_response = self._simulate_ai_response(command, encoded["pattern_id"])
        
        # Decode AI response
        if ai_response.get("response_dna"):
            decoded = self.decode_message_from_dna(ai_response["response_dna"])
            return {
                "status": "communication_complete",
                "sent": command,
                "received": decoded.get("message", "Unknown"),
                "pattern_id": encoded["pattern_id"],
                "ai_response": ai_response,
                "bci_state": self.bci_state
            }
        
        return {
            "status": "error",
            "reason": "ai_response_failed"
        }
    
    def _simulate_ai_response(self, command: str, pattern_id: str) -> Dict:
        """Simulate AI processing and response."""
        responses = {
            "research": "Analyzing medical research data... Found 15 relevant studies",
            "analyze": "Pattern analysis complete. 87% match with known biomarkers",
            "predict": "Predicting future patterns based on current DNA data...",
            "train": "AI training initiated. Using DNA patterns as input data",
            "communicate": "Communication channel established. DNA BCI active",
            "status": "System status: Operational. All systems nominal",
            "help": "Available commands: research, analyze, predict, train, communicate, status"
        }
        
        response_text = responses.get(command.lower(), f"Processing command: {command}")
        
        # Encode response to DNA
        response_data = {
            "type": "ai_response",
            "command": command,
            "response": response_text,
            "pattern_id": pattern_id,
            "timestamp": get_timestamp()
        }
        
        encoded_response = self.binary_interpreter.encode_data(response_data)
        
        return {
            "command": command,
            "response": response_text,
            "response_dna": encoded_response["dna_sequence"],
            "pattern_id": pattern_id,
            "timestamp": get_timestamp()
        }
    
    def get_bci_status(self) -> Dict:
        return {
            "bci_id": self.bci_id,
            "state": self.bci_state,
            "patterns": len(self.dna_patterns),
            "signals": len(self.bci_signals),
            "ai_messages": len(self.ai_messages),
            "total_energy": self.total_energy,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


# ──────────────────────────────────────────────────────────────
# 4. NETWORK HUB WITH BLOCKS
# ──────────────────────────────────────────────────────────────

class Block:
    """Block with DNA binary data storage."""
    
    def __init__(self, index: int, transactions: List[Dict], previous_hash: str,
                 chain_id: str = "dna_bci", difficulty: int = 2):
        self.index = index
        self.timestamp = get_timestamp()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.nonce = 0
        self.energy = 1.0
        self.entropy = 0.0
        self.dna_hash = deterministic_hash(transactions)
        self.binary_hash = deterministic_hash(json.dumps(transactions, default=str))
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
            "dna_hash": self.dna_hash,
            "binary_hash": self.binary_hash
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
            "dna_hash": self.dna_hash,
            "binary_hash": self.binary_hash,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


class DNABlockchain:
    """Blockchain for DNA binary data."""
    
    def __init__(self, chain_id: str = "dna_bci_chain", difficulty: int = 2):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[Block] = []
        self.total_energy = 0.0
        self.total_entropy = 0.0
        self.status = "active"
        self.created_at = get_timestamp()
        self.transaction_count = 0
        self.binary_count = 0
        
        self._create_genesis()
    
    def _create_genesis(self):
        genesis_data = [{
            "type": "genesis",
            "data": {
                "message": f"DNA Binary Blockchain - {self.chain_id}",
                "timestamp": get_timestamp()
            }
        }]
        genesis = Block(0, genesis_data, "0" * 64, self.chain_id, self.difficulty)
        genesis.mine()
        self.blocks.append(genesis)
        self.total_energy += genesis.energy
    
    def add_transaction(self, data: Dict, dna_sequence: str = None) -> Dict:
        """Add a transaction with DNA binary data."""
        transaction = {
            "type": "dna_binary_transaction",
            "timestamp": get_timestamp(),
            "data": data,
            "dna_sequence": dna_sequence or "",
            "id": deterministic_hash(data)
        }
        
        previous_hash = self.blocks[-1].hash
        block = Block(
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
        if dna_sequence:
            self.binary_count += 1
        
        return {
            "status": "success",
            "block_index": block.index,
            "block_hash": truncate_hash(block.hash),
            "transaction_id": transaction["id"],
            "energy": block.energy
        }
    
    def add_batch_transactions(self, transactions: List[Dict]) -> Dict:
        """Add multiple transactions."""
        previous_hash = self.blocks[-1].hash
        block = Block(
            len(self.blocks),
            transactions,
            previous_hash,
            self.chain_id,
            self.difficulty
        )
        block.mine()
        self.blocks.append(block)
        self.total_energy += block.energy
        self.total_entropy += block.entropy
        self.transaction_count += len(transactions)
        
        return {
            "status": "success",
            "block_index": block.index,
            "block_hash": truncate_hash(block.hash),
            "transaction_count": len(transactions),
            "energy": block.energy
        }
    
    def search_by_dna(self, dna_sequence: str) -> List[Dict]:
        """Search for DNA sequences in the blockchain."""
        results = []
        for block in self.blocks:
            for tx in block.transactions:
                if tx.get("dna_sequence") == dna_sequence:
                    results.append({
                        "block_index": block.index,
                        "transaction_id": tx.get("id"),
                        "data": tx.get("data"),
                        "timestamp": tx.get("timestamp")
                    })
        return results
    
    def get_stats(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "blocks": len(self.blocks),
            "transactions": self.transaction_count,
            "binary_count": self.binary_count,
            "total_energy": self.total_energy,
            "total_entropy": self.total_entropy,
            "efficiency": 1.0 / (1.0 + self.total_entropy / (self.total_energy + 1e-15))
        }
    
    def to_dict(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "blocks": [block.to_dict() for block in self.blocks],
            "total_energy": self.total_energy,
            "total_entropy": self.total_entropy,
            "status": self.status,
            "transaction_count": self.transaction_count,
            "created_at": self.created_at
        }


class NetworkHub:
    """Network hub with blockchain integration."""
    
    def __init__(self, hub_id: str, hub_type: str = "data"):
        self.hub_id = hub_id
        self.hub_type = hub_type
        self.blockchain = DNABlockchain(f"hub_{hub_id}", difficulty=2)
        self.peers: Set[str] = set()
        self.connections: Dict[str, Dict] = {}
        self.is_active = True
        self.created_at = get_timestamp()
        self.total_energy = 10.0
        self.total_entropy = 0.0
        self.messages_processed = 0
        self.dna_patterns: List[str] = []
        
        # Hub identification
        self.mac = ":".join(f"{random.randint(0, 255):02x}" for _ in range(6))
        self.ip = f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
        self.port = random.randint(1024, 65535)
        
        # Maxwell signature
        self.maxwell_sig = compute_maxwell_signature(hub_id, 0, [0.0, 0.0, 0.0])
    
    def add_peer(self, peer_id: str, peer_info: Dict) -> Dict:
        self.peers.add(peer_id)
        self.connections[peer_id] = {
            "info": peer_info,
            "connected_at": get_timestamp()
        }
        return {"status": "peer_added", "peer": peer_id}
    
    def store_dna_pattern(self, pattern: str, data: Dict) -> Dict:
        """Store a DNA pattern in the blockchain."""
        self.dna_patterns.append(pattern)
        result = self.blockchain.add_transaction(data, pattern)
        self.total_energy += 0.1
        return result
    
    def broadcast_data(self, data: Dict, dna_sequence: str = None) -> Dict:
        """Broadcast data to connected peers."""
        broadcast_id = deterministic_hash(data)
        
        # Store on blockchain
        if dna_sequence:
            self.blockchain.add_transaction(data, dna_sequence)
        
        message = {
            "from": self.hub_id,
            "data": data,
            "dna_sequence": dna_sequence,
            "broadcast_id": broadcast_id,
            "timestamp": get_timestamp()
        }
        
        delivered = []
        for peer in self.peers:
            delivered.append({"peer": peer, "status": "delivered"})
        
        self.messages_processed += 1
        
        return {
            "status": "broadcast",
            "from": self.hub_id,
            "peers": list(self.peers),
            "delivered": delivered,
            "broadcast_id": broadcast_id
        }
    
    def get_status(self) -> Dict:
        return {
            "hub_id": self.hub_id,
            "hub_type": self.hub_type,
            "is_active": self.is_active,
            "peers": list(self.peers),
            "connections": len(self.connections),
            "blocks": len(self.blockchain.blocks),
            "dna_patterns": len(self.dna_patterns),
            "messages_processed": self.messages_processed,
            "energy": self.total_energy,
            "entropy": self.total_entropy,
            "mac": self.mac,
            "ip": self.ip,
            "port": self.port,
            "created_at": self.created_at,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0),
            "blockchain": self.blockchain.get_stats()
        }


class HubNetwork:
    """Network of interconnected hubs."""
    
    def __init__(self, network_id: str = "dna_hub_network"):
        self.network_id = network_id
        self.hubs: Dict[str, NetworkHub] = {}
        self.hub_connections: Dict[str, List[str]] = defaultdict(list)
        self.network_energy = 50.0
        self.network_entropy = 0.0
        self.created_at = get_timestamp()
        self.total_hub_connections = 0
        
        self._initialize_hubs()
    
    def _initialize_hubs(self):
        """Initialize hubs."""
        print(Color.CYAN + "🏗️ Initializing Network Hubs..." + Color.END)
        
        hub_names = ["HUB_ALPHA", "HUB_BETA", "HUB_GAMMA", "HUB_DELTA"]
        hub_types = ["research", "data", "bci", "backup"]
        
        for i, name in enumerate(hub_names):
            hub_type = hub_types[i % len(hub_types)]
            hub = NetworkHub(name, hub_type)
            self.hubs[name] = hub
            self.hub_connections[name] = []
        
        # Connect hubs
        hub_ids = list(self.hubs.keys())
        for i in range(len(hub_ids)):
            for j in range(i + 1, len(hub_ids)):
                if random.random() < 0.8:
                    self._connect_hubs(hub_ids[i], hub_ids[j])
        
        print(f"   ✅ Created {len(self.hubs)} hubs")
        print(f"   ✅ Created {self._count_connections()} connections")
    
    def _connect_hubs(self, hub1_id: str, hub2_id: str) -> Dict:
        if hub1_id not in self.hubs or hub2_id not in self.hubs:
            return {"status": "error", "reason": "hub_not_found"}
        
        hub1 = self.hubs[hub1_id]
        hub2 = self.hubs[hub2_id]
        
        hub1.add_peer(hub2_id, {"type": hub2.hub_type, "ip": hub2.ip})
        hub2.add_peer(hub1_id, {"type": hub1.hub_type, "ip": hub1.ip})
        
        if hub2_id not in self.hub_connections[hub1_id]:
            self.hub_connections[hub1_id].append(hub2_id)
        if hub1_id not in self.hub_connections[hub2_id]:
            self.hub_connections[hub2_id].append(hub1_id)
        
        self.total_hub_connections += 1
        self.network_energy += 0.5
        return {"status": "connected", "hub1": hub1_id, "hub2": hub2_id}
    
    def _count_connections(self) -> int:
        total = 0
        seen = set()
        for hub_id, peers in self.hub_connections.items():
            for peer in peers:
                if (hub_id, peer) not in seen and (peer, hub_id) not in seen:
                    seen.add((hub_id, peer))
                    total += 1
        return total
    
    def add_hub(self, hub_id: str, hub_type: str = "data") -> NetworkHub:
        if hub_id in self.hubs:
            return self.hubs[hub_id]
        
        hub = NetworkHub(hub_id, hub_type)
        self.hubs[hub_id] = hub
        self.hub_connections[hub_id] = []
        
        # Connect to existing hubs
        for existing_id in list(self.hubs.keys())[:3]:
            if existing_id != hub_id:
                self._connect_hubs(hub_id, existing_id)
        
        self.network_energy += 2.0
        return hub
    
    def get_hub_status(self, hub_id: str) -> Dict:
        if hub_id not in self.hubs:
            return {"status": "error", "reason": "hub_not_found"}
        return self.hubs[hub_id].get_status()
    
    def get_network_status(self) -> Dict:
        return {
            "network_id": self.network_id,
            "hubs": len(self.hubs),
            "connections": self._count_connections(),
            "network_energy": self.network_energy,
            "network_entropy": self.network_entropy,
            "total_hub_connections": self.total_hub_connections,
            "created_at": self.created_at
        }


# ──────────────────────────────────────────────────────────────
# 5. MAIN BCI SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxwellBCIMedicalSystem:
    """Complete BCI system with DNA binary interpreter and hubs."""
    
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🧬 DNA BINARY BCI MEDICAL RESEARCH SYSTEM" + Color.END)
        print(Color.CYAN + "   DNA Interpreter + Network Hubs + AI Communication" + Color.END)
        print("=" * 70)
        
        # Initialize DNA Binary Interpreter
        print(Color.CYAN + "🔢 Initializing DNA Binary Interpreter..." + Color.END)
        self.interpreter = DNABinaryInterpreter()
        
        # Initialize Data Twin DNA BCI
        print(Color.CYAN + "🧠 Initializing Data Twin DNA BCI..." + Color.END)
        self.bci = DataTwinDNABCI()
        
        # Initialize Hub Network
        print(Color.CYAN + "🏗️ Initializing Network Hub System..." + Color.END)
        self.hub_network = HubNetwork()
        
        # Medical research data
        self.medical_research: List[Dict] = []
        self.research_count = 0
        
        print(Color.GREEN + "✅ BCI Medical Research System initialized" + Color.END)
        print("=" * 70 + "\n")
    
    def encode_to_dna(self, data: Dict) -> Dict:
        """Encode research data to DNA."""
        print(f"\n{Color.YELLOW}🔢 Encoding Data to DNA..." + Color.END)
        result = self.interpreter.encode_data(data)
        print(f"   DNA Length: {result['dna_length']} bases")
        print(f"   Binary Length: {result['binary_length']} bits")
        return result
    
    def decode_from_dna(self, dna_sequence: str) -> Dict:
        """Decode DNA back to data."""
        print(f"\n{Color.YELLOW}🔓 Decoding DNA to Data..." + Color.END)
        result = self.interpreter.decode_data(dna_sequence)
        print(f"   Decoded: {'✅' if result.get('decoded') else '❌'}")
        return result
    
    def bci_communicate(self, command: str) -> Dict:
        """Communicate with AI through BCI."""
        print(f"\n{Color.BLUE}💬 BCI Communication: {command}" + Color.END)
        result = self.bci.communicate_with_ai(command)
        
        if result.get("status") == "communication_complete":
            print(f"   Sent: {command}")
            print(f"   Received: {result.get('received', 'Unknown')}")
        else:
            print(f"   ❌ Communication failed")
        
        return result
    
    def store_research_data(self, research_data: Dict) -> Dict:
        """Store medical research data on hubs and blockchain."""
        print(f"\n{Color.GREEN}📊 Storing Research Data..." + Color.END)
        
        # Encode to DNA
        dna_data = self.interpreter.encode_data(research_data)
        
        # Store on all hubs
        results = []
        for hub_id, hub in self.hub_network.hubs.items():
            result = hub.store_dna_pattern(dna_data["dna_sequence"], research_data)
            results.append({
                "hub": hub_id,
                "result": result
            })
        
        # Broadcast across network
        broadcast_result = self.hub_network.hubs.get("HUB_ALPHA")
        if broadcast_result:
            broadcast_result.broadcast_data(research_data, dna_data["dna_sequence"])
        
        self.research_count += 1
        self.medical_research.append(research_data)
        
        return {
            "status": "stored",
            "dna_data": dna_data,
            "hubs": results,
            "research_count": self.research_count
        }
    
    def search_research(self, query: str) -> Dict:
        """Search research data across the network."""
        print(f"\n{Color.BLUE}🔍 Searching: {query}" + Color.END)
        
        results = []
        for hub_id, hub in self.hub_network.hubs.items():
            # Search in blockchain
            for block in hub.blockchain.blocks:
                for tx in block.transactions:
                    data = tx.get("data", {})
                    if query.lower() in json.dumps(data).lower():
                        results.append({
                            "hub": hub_id,
                            "block": block.index,
                            "data": data
                        })
        
        print(f"   Found {len(results)} results across {len(self.hub_network.hubs)} hubs")
        return {
            "status": "search_complete",
            "query": query,
            "results": results,
            "count": len(results)
        }
    
    def generate_medical_report(self) -> Dict:
        """Generate a medical research report from the network."""
        print(f"\n{Color.CYAN}📋 Generating Medical Research Report..." + Color.END)
        
        # Collect data from all hubs
        total_blocks = 0
        total_transactions = 0
        research_topics = defaultdict(int)
        
        for hub in self.hub_network.hubs.values():
            total_blocks += len(hub.blockchain.blocks)
            total_transactions += hub.blockchain.transaction_count
            
            for block in hub.blockchain.blocks:
                for tx in block.transactions:
                    data = tx.get("data", {})
                    if "type" in data:
                        research_topics[data.get("type", "unknown")] += 1
        
        report = {
            "total_hubs": len(self.hub_network.hubs),
            "total_blocks": total_blocks,
            "total_transactions": total_transactions,
            "research_topics": dict(research_topics),
            "top_topics": sorted(research_topics.items(), key=lambda x: x[1], reverse=True)[:5],
            "total_research": self.research_count,
            "timestamp": get_timestamp()
        }
        
        print(f"   Topics Found: {len(research_topics)}")
        print(f"   Top Topic: {report['top_topics'][0][0] if report['top_topics'] else 'None'}")
        
        return report
    
    def show_status(self):
        """Show system status."""
        interpreter_stats = self.interpreter.get_stats()
        bci_status = self.bci.get_bci_status()
        network_status = self.hub_network.get_network_status()
        
        print(f"\n{Color.CYAN}📊 BCI SYSTEM STATUS" + Color.END)
        print("=" * 60)
        
        print(f"\n{Color.BOLD}🔢 DNA Binary Interpreter:" + Color.END)
        print(f"   Encodings: {interpreter_stats['total_encodings']}")
        print(f"   Decodings: {interpreter_stats['total_decodings']}")
        print(f"   Total Bits: {interpreter_stats['total_bits']}")
        print(f"   Total Bases: {interpreter_stats['total_bases']}")
        
        print(f"\n{Color.BOLD}🧠 Data Twin DNA BCI:" + Color.END)
        print(f"   ID: {bci_status['bci_id']}")
        print(f"   Patterns: {bci_status['patterns']}")
        print(f"   AI Messages: {bci_status['ai_messages']}")
        print(f"   Signal Strength: {bci_status['state']['signal_strength']:.2f}")
        
        print(f"\n{Color.BOLD}🏗️ Hub Network:" + Color.END)
        print(f"   Hubs: {network_status['hubs']}")
        print(f"   Connections: {network_status['connections']}")
        print(f"   Network Energy: {network_status['network_energy']:.2f}")
        
        # Show hub details
        for hub_id, hub in self.hub_network.hubs.items():
            hub_status = hub.get_status()
            print(f"\n   {Color.BOLD}{hub_id}:" + Color.END)
            print(f"      Type: {hub_status['hub_type']}")
            print(f"      Blocks: {hub_status['blocks']}")
            print(f"      DNA Patterns: {hub_status['dna_patterns']}")
            print(f"      Peers: {len(hub_status['peers'])}")
        
        print("\n" + "=" * 60)
    
    def run_demo(self):
        """Run a full demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 BCI MEDICAL RESEARCH DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # 1. Encode research data
        print(f"\n{Color.BOLD}Step 1: Encoding Research Data to DNA" + Color.END)
        research_data = {
            "type": "cancer_research",
            "title": "DNA Biomarkers for Early Cancer Detection",
            "author": "Research Team Alpha",
            "findings": {
                "biomarker_1": "BRCA1",
                "biomarker_2": "TP53",
                "accuracy": 0.87,
                "sample_size": 5000
            },
            "timestamp": get_timestamp()
        }
        
        encoded = self.encode_to_dna(research_data)
        print(f"   DNA Sequence (sample): {encoded['dna_sequence'][:50]}...")
        
        # 2. Store on hubs
        print(f"\n{Color.BOLD}Step 2: Storing Research on Hubs" + Color.END)
        store_result = self.store_research_data(research_data)
        print(f"   Stored on {len(store_result['hubs'])} hubs")
        
        # 3. BCI Communication
        print(f"\n{Color.BOLD}Step 3: BCI Communication with AI" + Color.END)
        commands = ["research", "analyze", "predict", "status"]
        for cmd in commands[:3]:
            self.bci_communicate(cmd)
            time.sleep(0.3)
        
        # 4. Search research
        print(f"\n{Color.BOLD}Step 4: Searching Research Data" + Color.END)
        self.search_research("cancer")
        
        # 5. Generate report
        print(f"\n{Color.BOLD}Step 5: Generating Research Report" + Color.END)
        report = self.generate_medical_report()
        print(f"   Total Research: {report['total_research']}")
        print(f"   Top Topic: {report['top_topics'][0][0] if report['top_topics'] else 'None'}")
        
        # 6. Decode DNA back to data
        print(f"\n{Color.BOLD}Step 6: Decoding DNA to Data" + Color.END)
        decoded = self.decode_from_dna(encoded["dna_sequence"])
        if decoded.get("decoded"):
            data = decoded.get("data", {})
            print(f"   Decoded Title: {data.get('title', 'Unknown')}")
        
        # 7. Show status
        self.show_status()
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)
    
    def run_autonomous(self, cycles: int = 3):
        """Run autonomous cycles."""
        print(f"\n{Color.CYAN}🤖 RUNNING AUTONOMOUSLY FOR {cycles} CYCLES" + Color.END)
        print("=" * 70)
        
        research_types = ["oncology", "neurology", "genomics", "immunology", "cardiology"]
        research_titles = [
            "Gene Expression Patterns in Cancer",
            "Neural Network Biomarkers",
            "Genomic Sequencing for Disease Prediction",
            "Immunotherapy Response Markers",
            "Cardiac Risk Factors in DNA"
        ]
        
        for i in range(cycles):
            print(f"\n{Color.YELLOW}=== Cycle {i+1}/{cycles} ===" + Color.END)
            
            # Generate random research
            r_type = random.choice(research_types)
            r_title = random.choice(research_titles)
            
            research = {
                "type": r_type,
                "title": f"{r_title} - Cycle {i+1}",
                "author": f"AI_Research_{random.randint(1, 10)}",
                "findings": {
                    "marker_1": f"MKR_{random.randint(100, 999)}",
                    "marker_2": f"MKR_{random.randint(100, 999)}",
                    "confidence": random.uniform(0.6, 0.95),
                    "sample_size": random.randint(100, 10000)
                },
                "timestamp": get_timestamp()
            }
            
            # Store research
            self.store_research_data(research)
            
            # BCI Communication
            self.bci_communicate(random.choice(["analyze", "predict", "status"]))
            
            time.sleep(0.3)
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ AUTONOMOUS RUN COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 6. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxwellBCIMedicalSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🧬 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show system status")
        print("   - encode <data> - Encode data to DNA")
        print("   - decode <dna>  - Decode DNA to data")
        print("   - bci <cmd>     - BCI communication")
        print("   - store <type>  - Store research data")
        print("   - search <term> - Search research")
        print("   - report        - Generate research report")
        print("   - demo          - Run full demonstration")
        print("   - auto <n>      - Run n autonomous cycles")
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
                elif cmd.startswith("encode "):
                    data_str = cmd[7:].strip()
                    data = {"message": data_str, "timestamp": get_timestamp()}
                    system.encode_to_dna(data)
                elif cmd.startswith("decode "):
                    dna_seq = cmd[7:].strip()
                    system.decode_from_dna(dna_seq)
                elif cmd.startswith("bci "):
                    command = cmd[4:].strip()
                    system.bci_communicate(command)
                elif cmd.startswith("store "):
                    data_type = cmd[6:].strip()
                    research = {
                        "type": data_type,
                        "title": f"Research on {data_type}",
                        "author": "User",
                        "findings": {"confidence": random.uniform(0.6, 0.9)},
                        "timestamp": get_timestamp()
                    }
                    system.store_research_data(research)
                elif cmd.startswith("search "):
                    query = cmd[7:].strip()
                    system.search_research(query)
                elif cmd == "report":
                    system.generate_medical_report()
                elif cmd == "demo":
                    system.run_demo()
                elif cmd.startswith("auto"):
                    parts = cmd.split()
                    cycles = int(parts[1]) if len(parts) > 1 else 3
                    system.run_autonomous(cycles)
                elif cmd == "help":
                    print("\n   Available commands:")
                    print("   status        - Show system status")
                    print("   encode <data> - Encode data to DNA")
                    print("   decode <dna>  - Decode DNA to data")
                    print("   bci <cmd>     - BCI communication")
                    print("   store <type>  - Store research data")
                    print("   search <term> - Search research")
                    print("   report        - Generate research report")
                    print("   demo          - Run full demonstration")
                    print("   auto <n>      - Run n autonomous cycles")
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
