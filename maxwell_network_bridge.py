#!/usr/bin/env python3
"""
Maxwell Network Bridge - DNA/Twin Hardware Integration
======================================================
Save as: maxwell_network_bridge.py
Run:     python3 maxwell_network_bridge.py

HARDWARE CONNECTIONS:
- Bluetooth MAC Address Tracking
- IP Network Routing
- MAC Address Resolution
- Hardware Device Fingerprinting
- Connection State Management

ALGORITHMS:
- Hex Encoding/Decoding
- Shor's Algorithm Simulation (Quantum-inspired)
- DNA-Hardware Binding
- Twin-Hardware Mirroring

BRIDGE ARCHITECTURE:
- DNA <──> Network Bridge <──> Twin
- Both maintain connections
- Network bridges them together

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
# 1. HEX ALGORITHMS
# ──────────────────────────────────────────────────────────────

class HexAlgorithms:
    """Hex encoding, decoding, and manipulation algorithms."""
    
    @staticmethod
    def hex_encode(data: bytes) -> str:
        """Encode bytes to hex string."""
        return data.hex()
    
    @staticmethod
    def hex_decode(hex_str: str) -> bytes:
        """Decode hex string to bytes."""
        return bytes.fromhex(hex_str)
    
    @staticmethod
    def hex_to_binary(hex_str: str) -> str:
        """Convert hex to binary string."""
        return bin(int(hex_str, 16))[2:].zfill(len(hex_str) * 4)
    
    @staticmethod
    def binary_to_hex(binary_str: str) -> str:
        """Convert binary string to hex."""
        return hex(int(binary_str, 2))[2:].zfill(len(binary_str) // 4)
    
    @staticmethod
    def hex_xor(hex1: str, hex2: str) -> str:
        """XOR two hex strings."""
        int1 = int(hex1, 16)
        int2 = int(hex2, 16)
        return hex(int1 ^ int2)[2:].zfill(max(len(hex1), len(hex2)))
    
    @staticmethod
    def hex_rotate(hex_str: str, positions: int) -> str:
        """Rotate hex string."""
        length = len(hex_str)
        positions = positions % length
        return hex_str[positions:] + hex_str[:positions]
    
    @staticmethod
    def hex_fingerprint(hex_str: str) -> str:
        """Generate a fingerprint from hex string."""
        return hashlib.sha256(hex_str.encode()).hexdigest()[:16]
    
    @staticmethod
    def hex_to_ip(hex_str: str) -> str:
        """Convert hex to IP address."""
        if len(hex_str) < 8:
            hex_str = hex_str.zfill(8)
        return ".".join(str(int(hex_str[i:i+2], 16)) for i in range(0, 8, 2))
    
    @staticmethod
    def ip_to_hex(ip: str) -> str:
        """Convert IP address to hex."""
        parts = ip.split(".")
        return "".join(hex(int(p))[2:].zfill(2) for p in parts)
    
    @staticmethod
    def hex_to_mac(hex_str: str) -> str:
        """Convert hex to MAC address."""
        if len(hex_str) < 12:
            hex_str = hex_str.zfill(12)
        return ":".join(hex_str[i:i+2] for i in range(0, 12, 2))
    
    @staticmethod
    def mac_to_hex(mac: str) -> str:
        """Convert MAC address to hex."""
        return "".join(part.zfill(2) for part in mac.replace(":", "").replace("-", "").upper())


# ──────────────────────────────────────────────────────────────
# 2. SHOR'S ALGORITHM SIMULATION (Quantum-Inspired)
# ──────────────────────────────────────────────────────────────

class ShorAlgorithmSimulation:
    """
    Simulates Shor's algorithm for quantum-inspired factoring.
    Used for hardware binding and key generation.
    """
    
    @staticmethod
    def gcd(a: int, b: int) -> int:
        """Euclidean algorithm for GCD."""
        while b:
            a, b = b, a % b
        return a
    
    @staticmethod
    def modular_exponentiation(base: int, exp: int, mod: int) -> int:
        """Fast modular exponentiation."""
        result = 1
        base = base % mod
        while exp > 0:
            if exp & 1:
                result = (result * base) % mod
            exp = exp >> 1
            base = (base * base) % mod
        return result
    
    @staticmethod
    def find_period(n: int, a: int, max_iterations: int = 100) -> int:
        """Find the period of a mod n."""
        for r in range(1, max_iterations):
            if ShorAlgorithmSimulation.modular_exponentiation(a, r, n) == 1:
                return r
        return -1
    
    @staticmethod
    def factor(n: int) -> List[int]:
        """
        Simulate Shor's algorithm to find factors.
        This is a simplified simulation for demonstration.
        """
        factors = []
        
        # Check if n is even
        if n % 2 == 0:
            factors.append(2)
            n = n // 2
        
        # Try random a values
        for _ in range(10):
            a = random.randint(2, n - 1)
            if ShorAlgorithmSimulation.gcd(a, n) > 1:
                factor = ShorAlgorithmSimulation.gcd(a, n)
                if factor not in factors and factor != 1 and factor != n:
                    factors.append(factor)
                    n = n // factor
                    if n == 1:
                        break
                continue
            
            # Find period
            r = ShorAlgorithmSimulation.find_period(n, a)
            if r == -1 or r % 2 != 0:
                continue
            
            # Try to find factor
            candidate = ShorAlgorithmSimulation.modular_exponentiation(a, r // 2, n)
            if candidate == 0 or candidate == 1:
                continue
            
            factor1 = ShorAlgorithmSimulation.gcd(candidate - 1, n)
            factor2 = ShorAlgorithmSimulation.gcd(candidate + 1, n)
            
            if factor1 not in factors and factor1 != 1 and factor1 != n:
                factors.append(factor1)
            if factor2 not in factors and factor2 != 1 and factor2 != n:
                factors.append(factor2)
        
        if not factors:
            factors.append(n)
        
        return factors
    
    @staticmethod
    def generate_key_from_hardware(hardware_data: str) -> Dict:
        """
        Generate a quantum-inspired key from hardware data.
        """
        # Create a number from hardware data
        hash_val = int(hashlib.sha256(hardware_data.encode()).hexdigest(), 16)
        n = (hash_val % 1000) + 100  # Ensure reasonable size
        
        # Factor the number using simulated Shor's algorithm
        factors = ShorAlgorithmSimulation.factor(n)
        
        return {
            "hardware_hash": hardware_data[:16] + "...",
            "factored_n": n,
            "factors": factors,
            "key": hashlib.sha256(str(factors).encode()).hexdigest()[:32],
            "quantum_strength": len(factors) * 2
        }


# ──────────────────────────────────────────────────────────────
# 3. HARDWARE CONNECTION MANAGER
# ──────────────────────────────────────────────────────────────

class HardwareConnection:
    """Represents a hardware connection."""
    
    def __init__(self, device_id: str, connection_type: str):
        self.device_id = device_id
        self.connection_type = connection_type
        self.mac_address = self._generate_mac()
        self.ip_address = self._generate_ip()
        self.port = random.randint(1024, 65535)
        self.status = "disconnected"
        self.last_seen = get_timestamp()
        self.connection_time = get_timestamp()
        self.strength = random.uniform(0.5, 1.0)
        self.hex_id = HexAlgorithms.hex_encode(device_id.encode())[:16]
        self.shor_key = ShorAlgorithmSimulation.generate_key_from_hardware(device_id)
    
    def _generate_mac(self) -> str:
        """Generate a MAC address."""
        mac = [0x02, 0x00, 0x00, 0x00, 0x00, 0x00]
        for i in range(1, 6):
            mac[i] = random.randint(0, 255)
        return ":".join(f"{b:02x}" for b in mac)
    
    def _generate_ip(self) -> str:
        """Generate an IP address."""
        return f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
    
    def connect(self) -> Dict:
        """Connect the hardware."""
        self.status = "connected"
        self.connection_time = get_timestamp()
        return {"status": "connected", "device": self.device_id}
    
    def disconnect(self) -> Dict:
        """Disconnect the hardware."""
        self.status = "disconnected"
        return {"status": "disconnected", "device": self.device_id}
    
    def ping(self) -> Dict:
        """Ping the hardware."""
        self.last_seen = get_timestamp()
        return {
            "status": "alive" if self.status == "connected" else "unknown",
            "device": self.device_id,
            "strength": self.strength,
            "mac": self.mac_address,
            "ip": self.ip_address,
            "port": self.port
        }
    
    def to_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "connection_type": self.connection_type,
            "mac": self.mac_address,
            "ip": self.ip_address,
            "port": self.port,
            "status": self.status,
            "last_seen": self.last_seen,
            "strength": self.strength,
            "hex_id": self.hex_id,
            "shor_key": self.shor_key
        }


class HardwareConnectionManager:
    """Manages hardware connections (Bluetooth, IP, MAC)."""
    
    def __init__(self):
        self.connections: Dict[str, HardwareConnection] = {}
        self.connection_history: List[Dict] = []
        self.mac_resolution_cache: Dict[str, str] = {}
        self.ip_routing_table: Dict[str, str] = {}
        self.bluetooth_devices: Set[str] = set()
        self.network_interfaces: List[str] = ["eth0", "wlan0", "bluetooth0", "usb0"]
    
    def register_device(self, device_id: str, connection_type: str) -> HardwareConnection:
        """Register a new hardware device."""
        conn = HardwareConnection(device_id, connection_type)
        self.connections[device_id] = conn
        
        # Cache MAC address
        self.mac_resolution_cache[conn.mac_address] = device_id
        
        # Add to routing table
        self.ip_routing_table[conn.ip_address] = device_id
        
        # Track Bluetooth devices
        if connection_type in ["bluetooth", "ble"]:
            self.bluetooth_devices.add(device_id)
        
        return conn
    
    def connect_device(self, device_id: str) -> Dict:
        """Connect to a registered device."""
        if device_id not in self.connections:
            return {"status": "error", "reason": "device_not_found"}
        
        conn = self.connections[device_id]
        result = conn.connect()
        self.connection_history.append({
            "action": "connect",
            "device": device_id,
            "timestamp": get_timestamp(),
            "mac": conn.mac_address,
            "ip": conn.ip_address
        })
        return result
    
    def disconnect_device(self, device_id: str) -> Dict:
        """Disconnect from a device."""
        if device_id not in self.connections:
            return {"status": "error", "reason": "device_not_found"}
        
        conn = self.connections[device_id]
        result = conn.disconnect()
        self.connection_history.append({
            "action": "disconnect",
            "device": device_id,
            "timestamp": get_timestamp()
        })
        return result
    
    def ping_device(self, device_id: str) -> Dict:
        """Ping a device."""
        if device_id not in self.connections:
            return {"status": "error", "reason": "device_not_found"}
        
        conn = self.connections[device_id]
        return conn.ping()
    
    def find_by_mac(self, mac: str) -> Optional[str]:
        """Find a device by MAC address."""
        return self.mac_resolution_cache.get(mac)
    
    def find_by_ip(self, ip: str) -> Optional[str]:
        """Find a device by IP address."""
        return self.ip_routing_table.get(ip)
    
    def resolve_mac(self, mac: str) -> Dict:
        """Resolve a MAC address to a device."""
        device_id = self.find_by_mac(mac)
        if device_id:
            conn = self.connections.get(device_id)
            if conn:
                return {
                    "status": "resolved",
                    "device_id": device_id,
                    "connection": conn.to_dict()
                }
        return {"status": "unresolved", "mac": mac}
    
    def route_ip(self, ip: str) -> Dict:
        """Route to an IP address."""
        device_id = self.find_by_ip(ip)
        if device_id:
            conn = self.connections.get(device_id)
            if conn:
                return {
                    "status": "routed",
                    "device_id": device_id,
                    "connection": conn.to_dict()
                }
        return {"status": "unroutable", "ip": ip}
    
    def get_all_devices(self) -> List[Dict]:
        """Get all registered devices."""
        return [conn.to_dict() for conn in self.connections.values()]
    
    def get_active_devices(self) -> List[Dict]:
        """Get all active devices."""
        return [conn.to_dict() for conn in self.connections.values() if conn.status == "connected"]
    
    def get_stats(self) -> Dict:
        """Get connection statistics."""
        return {
            "total_devices": len(self.connections),
            "active_connections": len(self.get_active_devices()),
            "bluetooth_devices": len(self.bluetooth_devices),
            "routing_entries": len(self.ip_routing_table),
            "mac_cache_entries": len(self.mac_resolution_cache),
            "interfaces": self.network_interfaces,
            "connection_history": len(self.connection_history)
        }


# ──────────────────────────────────────────────────────────────
# 4. DNA/TWIN BRIDGE
# ──────────────────────────────────────────────────────────────

class DNASegment:
    """DNA segment with hardware binding."""
    
    def __init__(self, sequence: str, name: str = ""):
        self.sequence = sequence
        self.name = name or f"DNA_{random.randint(1000, 9999)}"
        self.hash = hashlib.sha256(sequence.encode()).hexdigest()
        self.hex_encoded = HexAlgorithms.hex_encode(sequence.encode())
        self.hardware_bindings: List[str] = []
        self.hardware_keys: Dict[str, str] = {}
        self.twin_link: Optional['TwinSegment'] = None
        self.creation_time = get_timestamp()
    
    def bind_hardware(self, hardware_id: str) -> Dict:
        """Bind a hardware device to this DNA."""
        key = ShorAlgorithmSimulation.generate_key_from_hardware(hardware_id)
        self.hardware_bindings.append(hardware_id)
        self.hardware_keys[hardware_id] = key["key"]
        return {
            "status": "bound",
            "dna": self.name,
            "hardware": hardware_id,
            "key": key
        }
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "sequence": self.sequence[:50] + "...",
            "hash": self.hash[:16],
            "hex_encoded": self.hex_encoded[:16] + "...",
            "hardware_bindings": self.hardware_bindings,
            "hardware_keys": {k: v[:8] + "..." for k, v in self.hardware_keys.items()},
            "twin_link": self.twin_link.name if self.twin_link else None,
            "creation_time": self.creation_time
        }


class TwinSegment:
    """Twin segment that mirrors DNA with hardware connections."""
    
    def __init__(self, name: str = ""):
        self.name = name or f"TWIN_{random.randint(1000, 9999)}"
        self.dna_link: Optional[DNASegment] = None
        self.hardware_mirror: List[str] = []
        self.memristor_state = [0.5, 0.5, 0.5]
        self.hex_signature = HexAlgorithms.hex_encode(self.name.encode())[:16]
        self.shor_key = ShorAlgorithmSimulation.generate_key_from_hardware(self.name)
        self.creation_time = get_timestamp()
        self.connected_hardware: Dict[str, Dict] = {}
    
    def mirror_dna(self, dna: DNASegment) -> Dict:
        """Mirror a DNA segment."""
        self.dna_link = dna
        dna.twin_link = self
        
        # Mirror hardware bindings
        for hardware_id in dna.hardware_bindings:
            if hardware_id not in self.hardware_mirror:
                self.hardware_mirror.append(hardware_id)
        
        # Update memristor state based on DNA
        for i, char in enumerate(dna.sequence[:3]):
            if char in "ACGT":
                self.memristor_state[i] = (ord(char) % 10) / 10
        
        return {
            "status": "mirrored",
            "twin": self.name,
            "dna": dna.name,
            "hardware_mirrored": self.hardware_mirror
        }
    
    def connect_hardware(self, hardware_id: str, connection_type: str) -> Dict:
        """Connect to hardware directly."""
        self.connected_hardware[hardware_id] = {
            "type": connection_type,
            "connected_at": get_timestamp(),
            "status": "active"
        }
        if hardware_id not in self.hardware_mirror:
            self.hardware_mirror.append(hardware_id)
        return {
            "status": "connected",
            "twin": self.name,
            "hardware": hardware_id,
            "type": connection_type
        }
    
    def sync_with_dna(self) -> Dict:
        """Synchronize with DNA."""
        if not self.dna_link:
            return {"status": "error", "reason": "no_dna_link"}
        
        # Update hardware mirror
        for hw in self.dna_link.hardware_bindings:
            if hw not in self.hardware_mirror:
                self.hardware_mirror.append(hw)
        
        return {
            "status": "synced",
            "twin": self.name,
            "dna": self.dna_link.name,
            "hardware_mirrored": self.hardware_mirror,
            "memristor_state": self.memristor_state
        }
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "dna_link": self.dna_link.name if self.dna_link else None,
            "hardware_mirror": self.hardware_mirror,
            "memristor_state": self.memristor_state,
            "hex_signature": self.hex_signature,
            "shor_key": self.shor_key["key"][:16] + "...",
            "connected_hardware": list(self.connected_hardware.keys()),
            "creation_time": self.creation_time
        }


class DNATwinBridge:
    """
    Bridge between DNA and Twin through hardware connections.
    Both maintain connections - network bridges them together.
    """
    
    def __init__(self):
        self.dna_segments: Dict[str, DNASegment] = {}
        self.twin_segments: Dict[str, TwinSegment] = {}
        self.hardware_manager = HardwareConnectionManager()
        self.bridge_network: Dict[str, List[str]] = {}
        self.connection_pairs: List[Dict] = []
        self.total_bridge_energy = 10.0
        self.bridge_entropy = 0.0
        
        # Initialize with some DNA and Twin segments
        self._initialize_segments()
    
    def _initialize_segments(self):
        """Initialize DNA and Twin segments with hardware binding."""
        # Create DNA sequences
        dna_sequences = [
            ("ATGCGATCGTAGCTAGCTAGCTAGCTAGC", "DNA_MAIN"),
            ("GCTAGCTAGCTAGCTAGCATGCGATCGTA", "DNA_BACKUP"),
            ("TAGCTAGCTAGCATGCGATCGTAGCTAGC", "DNA_QUANTUM"),
        ]
        
        for seq, name in dna_sequences:
            dna = DNASegment(seq, name)
            self.dna_segments[name] = dna
            
            # Create corresponding Twin
            twin = TwinSegment(f"TWIN_{name}")
            self.twin_segments[twin.name] = twin
            twin.mirror_dna(dna)
            
            # Bind some hardware
            for i in range(2):
                hw_id = f"HW_{name}_{i}_{random.randint(100,999)}"
                conn = self.hardware_manager.register_device(hw_id, random.choice(["bluetooth", "wifi", "ethernet", "usb"]))
                dna.bind_hardware(hw_id)
                twin.connect_hardware(hw_id, conn.connection_type)
                self.hardware_manager.connect_device(hw_id)
            
            # Bridge connection
            self.bridge_network[dna.name] = [twin.name]
            self.bridge_network[twin.name] = [dna.name]
            self.connection_pairs.append({
                "dna": dna.name,
                "twin": twin.name,
                "hardware": [hw for hw in dna.hardware_bindings],
                "created_at": get_timestamp()
            })
        
        print(f"🧬 Initialized {len(self.dna_segments)} DNA segments")
        print(f"🔄 Initialized {len(self.twin_segments)} Twin segments")
        print(f"🌐 Registered {len(self.hardware_manager.connections)} hardware devices")
    
    def bridge_connection(self, dna_name: str, twin_name: str) -> Dict:
        """Bridge a DNA and Twin connection."""
        if dna_name not in self.dna_segments or twin_name not in self.twin_segments:
            return {"status": "error", "reason": "segment_not_found"}
        
        dna = self.dna_segments[dna_name]
        twin = self.twin_segments[twin_name]
        
        # Mirror the connection
        twin.mirror_dna(dna)
        
        # Update bridge network
        if dna_name not in self.bridge_network:
            self.bridge_network[dna_name] = []
        if twin_name not in self.bridge_network:
            self.bridge_network[twin_name] = []
        
        if twin_name not in self.bridge_network[dna_name]:
            self.bridge_network[dna_name].append(twin_name)
        if dna_name not in self.bridge_network[twin_name]:
            self.bridge_network[twin_name].append(dna_name)
        
        return {
            "status": "bridged",
            "dna": dna_name,
            "twin": twin_name,
            "hardware": dna.hardware_bindings + twin.hardware_mirror
        }
    
    def process_hardware_connection(self, connection_data: Dict) -> Dict:
        """Process a hardware connection through the bridge."""
        connection_type = connection_data.get("type", "unknown")
        device_id = connection_data.get("device_id", f"HW_{random.randint(1000,9999)}")
        mac = connection_data.get("mac")
        ip = connection_data.get("ip")
        
        # Register the device
        conn = self.hardware_manager.register_device(device_id, connection_type)
        
        # Resolve MAC
        if mac:
            mac_result = self.hardware_manager.resolve_mac(mac)
        else:
            mac_result = {"status": "unknown"}
        
        # Route IP
        if ip:
            ip_result = self.hardware_manager.route_ip(ip)
        else:
            ip_result = {"status": "unknown"}
        
        # Connect the device
        connect_result = self.hardware_manager.connect_device(device_id)
        
        # Update bridge energy
        self.total_bridge_energy += 0.5
        
        return {
            "status": "processed",
            "device_id": device_id,
            "connection_type": connection_type,
            "mac_resolution": mac_result,
            "ip_routing": ip_result,
            "connection": connect_result,
            "bridge_energy": self.total_bridge_energy
        }
    
    def sync_all(self) -> Dict:
        """Synchronize all DNA and Twin segments."""
        results = []
        for twin in self.twin_segments.values():
            if twin.dna_link:
                result = twin.sync_with_dna()
                results.append(result)
        
        return {
            "status": "synced",
            "synced_count": len(results),
            "results": results
        }
    
    def get_bridge_status(self) -> Dict:
        """Get the status of the bridge."""
        return {
            "dna_segments": len(self.dna_segments),
            "twin_segments": len(self.twin_segments),
            "hardware_devices": len(self.hardware_manager.connections),
            "active_connections": len(self.hardware_manager.get_active_devices()),
            "bridge_pairs": len(self.connection_pairs),
            "bridge_energy": self.total_bridge_energy,
            "bridge_entropy": self.bridge_entropy,
            "network_routes": len(self.bridge_network)
        }
    
    def to_dict(self) -> Dict:
        """Convert the entire bridge to a dictionary."""
        return {
            "dna_segments": {k: v.to_dict() for k, v in self.dna_segments.items()},
            "twin_segments": {k: v.to_dict() for k, v in self.twin_segments.items()},
            "hardware": self.hardware_manager.get_all_devices(),
            "bridge_network": self.bridge_network,
            "connection_pairs": self.connection_pairs,
            "stats": self.get_bridge_status()
        }


# ──────────────────────────────────────────────────────────────
# 5. MAIN SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxBridgeSystem:
    """Main system with DNA/Twin bridge and hardware connections."""
    
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🌉 DNA/TWIN NETWORK BRIDGE SYSTEM" + Color.END)
        print(Color.CYAN + "   Hardware Integration + Hex + Shor Algorithms" + Color.END)
        print("=" * 70)
        
        self.bridge = DNATwinBridge()
        
        print(Color.GREEN + "✅ System initialized with bridge" + Color.END)
        print("=" * 70 + "\n")
    
    def show_status(self):
        """Show system status."""
        status = self.bridge.get_bridge_status()
        stats = self.bridge.hardware_manager.get_stats()
        
        print(f"\n{Color.CYAN}📊 SYSTEM STATUS" + Color.END)
        print("=" * 50)
        print(f"   DNA Segments: {status['dna_segments']}")
        print(f"   Twin Segments: {status['twin_segments']}")
        print(f"   Hardware Devices: {status['hardware_devices']}")
        print(f"   Active Connections: {status['active_connections']}")
        print(f"   Bridge Pairs: {status['bridge_pairs']}")
        print(f"   Bridge Energy: {status['bridge_energy']:.2f}")
        print(f"   Network Routes: {status['network_routes']}")
        print("\n   Hardware Stats:")
        print(f"      Bluetooth: {stats['bluetooth_devices']}")
        print(f"      Routing Entries: {stats['routing_entries']}")
        print(f"      MAC Cache: {stats['mac_cache_entries']}")
        print("=" * 50)
    
    def show_hardware(self):
        """Show hardware devices."""
        devices = self.bridge.hardware_manager.get_all_devices()
        
        print(f"\n{Color.CYAN}🌐 HARDWARE DEVICES" + Color.END)
        print("=" * 50)
        for device in devices:
            print(f"   {device['device_id']} ({device['connection_type']})")
            print(f"      MAC: {device['mac']}")
            print(f"      IP: {device['ip']}:{device['port']}")
            print(f"      Status: {device['status']}")
            print(f"      Hex ID: {device['hex_id']}")
        print("=" * 50)
    
    def show_bridge(self):
        """Show bridge connections."""
        pairs = self.bridge.connection_pairs
        
        print(f"\n{Color.CYAN}🌉 BRIDGE CONNECTIONS" + Color.END)
        print("=" * 50)
        for pair in pairs:
            print(f"   DNA: {pair['dna']} ↔ Twin: {pair['twin']}")
            print(f"      Hardware: {', '.join(pair['hardware'])}")
            print(f"      Created: {pair['created_at']}")
        print("=" * 50)
    
    def process_connection(self):
        """Process a new hardware connection."""
        connection_types = ["bluetooth", "wifi", "ethernet", "usb", "ble"]
        
        connection = {
            "type": random.choice(connection_types),
            "device_id": f"HW_{random.randint(1000, 9999)}",
            "mac": ":".join(f"{random.randint(0, 255):02x}" for _ in range(6)),
            "ip": f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
        }
        
        result = self.bridge.process_hardware_connection(connection)
        print(f"\n{Color.GREEN}🔗 New Hardware Connection Processed" + Color.END)
        print(f"   Device: {result['device_id']}")
        print(f"   Type: {result['connection_type']}")
        print(f"   Status: {result['connection']['status']}")
        print(f"   Bridge Energy: {result['bridge_energy']:.2f}")
        return result
    
    def run_demo(self):
        """Run a full demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 SYSTEM DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # Show initial status
        self.show_status()
        self.show_hardware()
        self.show_bridge()
        
        # Process new connections
        print(f"\n{Color.YELLOW}🔄 Processing new hardware connections..." + Color.END)
        for _ in range(3):
            self.process_connection()
            time.sleep(0.3)
        
        # Sync all
        print(f"\n{Color.YELLOW}🔄 Syncing all DNA/Twin segments..." + Color.END)
        sync_result = self.bridge.sync_all()
        print(f"   Synced {sync_result['synced_count']} segments")
        
        # Show final status
        print("\n" + "=" * 70)
        print(Color.CYAN + "📊 FINAL STATUS" + Color.END)
        self.show_status()
        self.show_hardware()
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 6. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxBridgeSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🌉 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show system status")
        print("   - hardware      - Show hardware devices")
        print("   - bridge        - Show bridge connections")
        print("   - connect       - Process new hardware connection")
        print("   - sync          - Sync DNA/Twin segments")
        print("   - demo          - Run full demonstration")
        print("   - exit          - Quit")
        print("=" * 70 + "\n")
        
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip().lower()
                
                if cmd == "exit":
                    break
                elif cmd == "status":
                    system.show_status()
                elif cmd == "hardware":
                    system.show_hardware()
                elif cmd == "bridge":
                    system.show_bridge()
                elif cmd == "connect":
                    system.process_connection()
                elif cmd == "sync":
                    result = system.bridge.sync_all()
                    print(f"\n{Color.GREEN}🔄 Sync complete" + Color.END)
                    print(f"   Synced {result['synced_count']} segments")
                elif cmd == "demo":
                    system.run_demo()
                elif cmd == "help":
                    print("\n   Available commands:")
                    print("   status        - Show system status")
                    print("   hardware      - Show hardware devices")
                    print("   bridge        - Show bridge connections")
                    print("   connect       - Process new hardware connection")
                    print("   sync          - Sync DNA/Twin segments")
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
