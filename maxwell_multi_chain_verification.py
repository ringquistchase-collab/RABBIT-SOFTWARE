#!/usr/bin/env python3
"""
Maxwell Blockchain - Multi-Chain Verification with DNA/TWIN Identity
=====================================================================
Save as: maxwell_multi_chain_verification.py
Run:     python3 maxwell_multi_chain_verification.py

FEATURES:
1. Multi-Chain Verification Protocol
2. Cross-Chain DNA/TWIN Identity Verification
3. Network Consensus with Maxwell Fields
4. Inter-Chain Validation
5. Identity Anchoring Across Chains
6. Autonomous Chain Synchronization
7. Chain Health Monitoring
8. Cross-Chain Merkle Proofs
9. Identity Federation
10. Network Mesh Verification

Digital twin only - no real biology, chemicals, RF, or hardware control.
"""

import hashlib
import hmac
import json
import math
import os
import secrets
import struct
import sys
import time
import traceback
import threading
import queue
import socket
import random
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ──────────────────────────────────────────────────────────────
# 0. COLOR CLASS & UTILITIES
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


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def dhash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def double_sha256(data: bytes) -> str:
    return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


def hash160(data: bytes) -> str:
    return hashlib.new('ripemd160', hashlib.sha256(data).digest()).hexdigest()


# ──────────────────────────────────────────────────────────────
# 1. MAXWELL FIELD SIGNATURE
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
    curl_E = [E[1]-E[2]+dB_dt[0], E[2]-E[0]+dB_dt[1], E[0]-E[1]+dB_dt[2]]
    curl_H = [
        H[1]-H[2]-(J[0]+dD_dt[0]),
        H[2]-H[0]-(J[1]+dD_dt[1]),
        H[0]-H[1]-(J[2]+dD_dt[2]),
    ]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15
    return {
        "div_E": div_E, "div_B": div_B,
        "curl_E": curl_E, "next_curl": curl_E,
        "impedance": nE / nH, "energy": nE * nH,
        "E_field": E, "H_field": H, "B_field": B
    }


# ──────────────────────────────────────────────────────────────
# 2. DNA/TWIN IDENTITY VERIFICATION
# ──────────────────────────────────────────────────────────────

class DNATWINIdentity:
    """
    DNA/TWIN Identity verification across chains.
    """
    
    def __init__(self):
        self.identities: Dict[str, Dict] = {}
        self.identity_chain_links: Dict[str, Set[str]] = defaultdict(set)
        self.verification_history: List[Dict] = []
        self.total_energy = 0.0
        
        # DNA/TWIN markers
        self.markers = {
            "dna": ["ATGC", "CGTA", "GATC"],
            "twin": ["MIRROR", "SYNC", "DUAL"],
            "hash": ["SHA256", "MAXWELL", "FIELD"]
        }
    
    def register_identity(self, identity_id: str, dna_hash: str, twin_hash: str, chain_id: str = "main") -> Dict:
        """Register a DNA/TWIN identity on a chain."""
        identity_data = {
            "identity_id": identity_id,
            "dna_hash": dna_hash,
            "twin_hash": twin_hash,
            "registered_on": chain_id,
            "created_at": ts(),
            "verification_hash": dhash({
                "dna": dna_hash,
                "twin": twin_hash,
                "chain": chain_id,
                "timestamp": ts()
            })
        }
        
        self.identities[identity_id] = identity_data
        self.identity_chain_links[identity_id].add(chain_id)
        self.total_energy += 0.1
        
        return {
            "status": "registered",
            "identity_id": identity_id,
            "verification_hash": identity_data["verification_hash"],
            "chain_id": chain_id
        }
    
    def verify_identity_across_chains(self, identity_id: str, chain_ids: List[str]) -> Dict:
        """Verify identity across multiple chains."""
        if identity_id not in self.identities:
            return {"status": "error", "reason": "identity_not_found"}
        
        identity = self.identities[identity_id]
        verification_results = []
        verified_chains = []
        
        for chain_id in chain_ids:
            # Verify identity on chain
            is_verified = self._verify_on_chain(identity, chain_id)
            verification_results.append({
                "chain_id": chain_id,
                "verified": is_verified,
                "timestamp": ts()
            })
            if is_verified:
                verified_chains.append(chain_id)
                self.identity_chain_links[identity_id].add(chain_id)
        
        verification_record = {
            "identity_id": identity_id,
            "results": verification_results,
            "verified_chains": verified_chains,
            "verification_hash": identity["verification_hash"],
            "timestamp": ts()
        }
        
        self.verification_history.append(verification_record)
        self.total_energy += 0.1
        
        return {
            "status": "verified" if verified_chains else "unverified",
            "identity_id": identity_id,
            "verified_chains": verified_chains,
            "total_chains": len(chain_ids),
            "verification_hash": identity["verification_hash"]
        }
    
    def _verify_on_chain(self, identity: Dict, chain_id: str) -> bool:
        """Internal verification on a specific chain."""
        # Simulate chain verification
        # In real implementation, this would query the chain
        return random.random() > 0.1  # 90% verification rate
    
    def get_identity_chain_map(self) -> Dict:
        """Get the mapping of identities to chains."""
        return {k: list(v) for k, v in self.identity_chain_links.items()}
    
    def get_stats(self) -> Dict:
        return {
            "total_identities": len(self.identities),
            "identity_chain_links": sum(len(v) for v in self.identity_chain_links.values()),
            "verifications": len(self.verification_history),
            "total_energy": self.total_energy
        }


# ──────────────────────────────────────────────────────────────
# 3. CHAIN VERIFICATION PROTOCOL
# ──────────────────────────────────────────────────────────────

class ChainVerificationProtocol:
    """
    Protocol for verifying chains against each other.
    Includes cross-chain merkle proofs and consensus.
    """
    
    def __init__(self):
        self.chains: Dict[str, Dict] = {}
        self.chain_links: Dict[str, Set[str]] = defaultdict(set)
        self.verification_proofs: Dict[str, Dict] = {}
        self.consensus_history: List[Dict] = []
        self.total_energy = 0.0
        self.network_health = 1.0
    
    def register_chain(self, chain_id: str, chain_data: Dict) -> Dict:
        """Register a chain for verification."""
        self.chains[chain_id] = {
            "data": chain_data,
            "registered_at": ts(),
            "last_verified": ts(),
            "health_score": 1.0,
            "peers": []
        }
        self.total_energy += 0.1
        return {"status": "registered", "chain_id": chain_id}
    
    def link_chains(self, chain1_id: str, chain2_id: str) -> Dict:
        """Create a link between two chains."""
        if chain1_id not in self.chains or chain2_id not in self.chains:
            return {"status": "error", "reason": "chain_not_found"}
        
        self.chain_links[chain1_id].add(chain2_id)
        self.chain_links[chain2_id].add(chain1_id)
        
        if chain1_id in self.chains:
            self.chains[chain1_id]["peers"].append(chain2_id)
        if chain2_id in self.chains:
            self.chains[chain2_id]["peers"].append(chain1_id)
        
        self.total_energy += 0.05
        return {"status": "linked", "chain1": chain1_id, "chain2": chain2_id}
    
    def generate_cross_chain_proof(self, chain_id: str, target_chain_id: str) -> Dict:
        """Generate a cross-chain verification proof."""
        if chain_id not in self.chains or target_chain_id not in self.chains:
            return {"status": "error", "reason": "chain_not_found"}
        
        proof_id = dhash({
            "source": chain_id,
            "target": target_chain_id,
            "timestamp": ts()
        })
        
        proof = {
            "proof_id": proof_id,
            "source_chain": chain_id,
            "target_chain": target_chain_id,
            "merkle_root": double_sha256(f"{chain_id}:{target_chain_id}".encode()),
            "maxwell_signature": maxwell_signature(
                proof_id,
                len(self.verification_proofs),
                [0.0, 0.0, 0.0]
            ),
            "timestamp": ts(),
            "valid": True
        }
        
        self.verification_proofs[proof_id] = proof
        self.total_energy += 0.1
        
        return proof
    
    def verify_chain_consensus(self, chain_ids: List[str]) -> Dict:
        """Verify consensus across multiple chains."""
        if not chain_ids:
            return {"status": "error", "reason": "no_chains"}
        
        consensus_results = []
        chain_hashes = []
        
        for chain_id in chain_ids:
            if chain_id in self.chains:
                chain_hash = dhash(self.chains[chain_id])
                chain_hashes.append(chain_hash)
                consensus_results.append({
                    "chain_id": chain_id,
                    "hash": chain_hash[:16] + "...",
                    "status": "active"
                })
        
        # Check consensus
        unique_hashes = len(set(chain_hashes))
        is_consensus = unique_hashes == 1
        consensus_level = 1.0 / max(1, unique_hashes)
        
        consensus_record = {
            "chains": chain_ids,
            "unique_hashes": unique_hashes,
            "is_consensus": is_consensus,
            "consensus_level": consensus_level,
            "timestamp": ts(),
            "consensus_id": dhash({"chains": sorted(chain_ids), "timestamp": ts()})
        }
        
        self.consensus_history.append(consensus_record)
        self.total_energy += 0.1
        
        return {
            "status": "consensus_reached" if is_consensus else "consensus_pending",
            "consensus_level": consensus_level,
            "consensus_record": consensus_record,
            "chains": consensus_results
        }
    
    def get_verification_status(self) -> Dict:
        """Get the overall verification status."""
        return {
            "chains": len(self.chains),
            "chain_links": sum(len(v) for v in self.chain_links.values()),
            "proofs": len(self.verification_proofs),
            "consensus_events": len(self.consensus_history),
            "network_health": self.network_health,
            "total_energy": self.total_energy
        }


# ──────────────────────────────────────────────────────────────
# 4. MAXWELL MULTI-CHAIN BLOCKCHAIN
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(self, index: int, payload: Dict, prev_hash: str, prev_curl: List[float],
                 chain_id: str = "maxwell", difficulty: int = 3):
        self.index = index
        self.chain_id = chain_id
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0
        self.merkleroot = double_sha256(json.dumps(payload, default=str).encode())
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
            "merkleroot": self.merkleroot,
            "impedance": round(self.maxwell["impedance"], 8),
            "energy": round(self.maxwell["energy"], 8),
        }
        return double_sha256(json.dumps(c, sort_keys=True, default=str).encode())
    
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
            "merkleroot": self.merkleroot,
            "maxwell": self.maxwell
        }


class MaxwellMultiChain:
    def __init__(self, chain_id: str = "main", difficulty: int = 3):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self.bitcoin = None  # Will be integrated
        self.identity_verifier = DNATWINIdentity()
        self.chain_verifier = ChainVerificationProtocol()
        self.cross_chain_links: List[Dict] = []
        self.storage = None
        
        # Register this chain
        self.chain_verifier.register_chain(chain_id, {"difficulty": difficulty, "blocks": 0})
        
        # Genesis block
        genesis = MaxwellBlock(0, {"type": "genesis", "chain": chain_id},
                               "0"*64, [0.0, 0.0, 0.0], chain_id, difficulty)
        genesis.mine()
        self.blocks.append(genesis)
        
        # Update chain data
        self.chain_verifier.chains[chain_id]["data"]["blocks"] = 1
        
        print(f"⛓️ Maxwell Multi-Chain initialized: {chain_id}")
    
    def add_block(self, payload: Dict) -> MaxwellBlock:
        prev = self.blocks[-1]
        b = MaxwellBlock(len(self.blocks), payload, prev.hash,
                         prev.maxwell["next_curl"], self.chain_id, self.difficulty)
        b.mine()
        self.blocks.append(b)
        
        # Update chain data
        if self.chain_id in self.chain_verifier.chains:
            self.chain_verifier.chains[self.chain_id]["data"]["blocks"] = len(self.blocks)
        
        return b
    
    def register_identity(self, identity_id: str, dna_hash: str, twin_hash: str) -> Dict:
        result = self.identity_verifier.register_identity(identity_id, dna_hash, twin_hash, self.chain_id)
        
        self.add_block({
            "type": "identity_registration",
            "identity_id": identity_id,
            "dna_hash": dna_hash[:16] + "...",
            "twin_hash": twin_hash[:16] + "...",
            "chain_id": self.chain_id
        })
        
        return result
    
    def verify_identity_across_chains(self, identity_id: str, chain_ids: List[str]) -> Dict:
        return self.identity_verifier.verify_identity_across_chains(identity_id, chain_ids)
    
    def link_with_chain(self, target_chain_id: str) -> Dict:
        result = self.chain_verifier.link_chains(self.chain_id, target_chain_id)
        
        if result.get("status") == "linked":
            self.cross_chain_links.append({
                "source": self.chain_id,
                "target": target_chain_id,
                "timestamp": ts(),
                "link_id": dhash({"source": self.chain_id, "target": target_chain_id})
            })
            
            self.add_block({
                "type": "cross_chain_link",
                "source": self.chain_id,
                "target": target_chain_id,
                "timestamp": ts()
            })
        
        return result
    
    def verify_network_consensus(self) -> Dict:
        all_chains = list(self.chain_verifier.chains.keys())
        return self.chain_verifier.verify_chain_consensus(all_chains)
    
    def get_chain_status(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "blocks": len(self.blocks),
            "difficulty": self.difficulty,
            "cross_chain_links": len(self.cross_chain_links),
            "identities": len(self.identity_verifier.identities),
            "chain_links": len(self.chain_verifier.chain_links),
            "network_health": self.chain_verifier.network_health
        }


# ──────────────────────────────────────────────────────────────
# 5. COMPLETE MULTI-CHAIN SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxwellMultiChainSystem:
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "⚡ MAXWELL MULTI-CHAIN VERIFICATION SYSTEM" + Color.END)
        print(Color.CYAN + "   DNA/TWIN Identity + Cross-Chain Consensus" + Color.END)
        print("=" * 70)
        
        # Initialize multiple chains
        print(Color.CYAN + "⛓️ Initializing Multi-Chain Network..." + Color.END)
        self.chains: Dict[str, MaxwellMultiChain] = {}
        self._initialize_chains()
        
        print(Color.CYAN + "🧬 Registering DNA/TWIN Identities..." + Color.END)
        self._register_identities()
        
        print(Color.CYAN + "🔗 Linking Chains..." + Color.END)
        self._link_chains()
        
        self.transaction_count = 0
        self.verification_count = 0
        
        print(Color.GREEN + "✅ Multi-Chain System initialized" + Color.END)
        print("=" * 70 + "\n")
    
    def _initialize_chains(self):
        chain_names = ["main", "research", "medical", "tech", "identity"]
        for name in chain_names:
            self.chains[name] = MaxwellMultiChain(name, difficulty=3)
    
    def _register_identities(self):
        identities = [
            ("alice", "dna_alice_001", "twin_alice_001"),
            ("bob", "dna_bob_001", "twin_bob_001"),
            ("charlie", "dna_charlie_001", "twin_charlie_001"),
            ("dave", "dna_dave_001", "twin_dave_001"),
            ("eve", "dna_eve_001", "twin_eve_001")
        ]
        
        for identity_id, dna_hash, twin_hash in identities:
            for chain_name in ["main", "research", "medical"]:
                self.chains[chain_name].register_identity(identity_id, dna_hash, twin_hash)
    
    def _link_chains(self):
        chain_names = list(self.chains.keys())
        for i in range(len(chain_names)):
            for j in range(i + 1, len(chain_names)):
                self.chains[chain_names[i]].link_with_chain(chain_names[j])
    
    def register_identity_on_all_chains(self, identity_id: str, dna_hash: str, twin_hash: str) -> Dict:
        results = []
        for chain_name, chain in self.chains.items():
            result = chain.register_identity(identity_id, dna_hash, twin_hash)
            results.append({
                "chain": chain_name,
                "status": result.get("status", "unknown")
            })
        
        self.transaction_count += 1
        
        return {
            "status": "registered",
            "identity_id": identity_id,
            "chains": results
        }
    
    def verify_identity_network(self, identity_id: str) -> Dict:
        chain_ids = list(self.chains.keys())
        
        # Verify identity across all chains
        verification_results = []
        for chain_name, chain in self.chains.items():
            result = chain.identity_verifier.verify_identity_across_chains(identity_id, chain_ids)
            verification_results.append({
                "chain": chain_name,
                "status": result.get("status", "unknown"),
                "verified_chains": result.get("verified_chains", [])
            })
        
        self.verification_count += 1
        
        return {
            "identity_id": identity_id,
            "verification_results": verification_results,
            "total_chains": len(chain_ids),
            "timestamp": ts()
        }
    
    def get_network_consensus(self) -> Dict:
        chain_names = list(self.chains.keys())
        consensus_results = []
        
        for chain_name, chain in self.chains.items():
            result = chain.verify_network_consensus()
            consensus_results.append({
                "chain": chain_name,
                "status": result.get("status", "unknown"),
                "consensus_level": result.get("consensus_level", 0)
            })
        
        return {
            "consensus_results": consensus_results,
            "network_health": sum(r.get("consensus_level", 0) for r in consensus_results) / max(1, len(consensus_results)),
            "timestamp": ts()
        }
    
    def verify_cross_chain_identities(self) -> Dict:
        """Verify all identities across all chains."""
        all_identities = set()
        for chain in self.chains.values():
            all_identities.update(chain.identity_verifier.identities.keys())
        
        results = []
        for identity_id in all_identities:
            result = self.verify_identity_network(identity_id)
            results.append(result)
        
        return {
            "total_identities": len(all_identities),
            "verified_identities": len([r for r in results if "verified" in str(r)]),
            "results": results[:5]  # Limit for display
        }
    
    def show_status(self):
        print(f"\n{Color.CYAN}📊 MULTI-CHAIN SYSTEM STATUS" + Color.END)
        print("=" * 70)
        
        print(f"\n{Color.BOLD}⛓️ Chains:" + Color.END)
        for chain_name, chain in self.chains.items():
            status = chain.get_chain_status()
            print(f"   {chain_name}: {status['blocks']} blocks, {status['identities']} identities")
            print(f"      Links: {status['cross_chain_links']}, Health: {status['network_health']:.2f}")
        
        print(f"\n{Color.BOLD}🔗 Chain Links:" + Color.END)
        chain_names = list(self.chains.keys())
        for i in range(len(chain_names)):
            for j in range(i + 1, len(chain_names)):
                print(f"   {chain_names[i]} ↔ {chain_names[j]}")
        
        print(f"\n{Color.BOLD}🧬 DNA/TWIN Identities:" + Color.END)
        for chain in self.chains.values():
            for identity_id in chain.identity_verifier.identities:
                chains = list(chain.identity_verifier.identity_chain_links.get(identity_id, []))
                print(f"   {identity_id}: {chains}")
                break  # Show first few
        
        print(f"\n{Color.BOLD}📊 System:" + Color.END)
        print(f"   Total Chains: {len(self.chains)}")
        print(f"   Transactions: {self.transaction_count}")
        print(f"   Verifications: {self.verification_count}")
        
        print("\n" + "=" * 70)
    
    def run_demo(self):
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 MULTI-CHAIN VERIFICATION DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # 1. Register identity on all chains
        print("\n1. Registering Identity on All Chains...")
        identity_id = "test_user_001"
        result = self.register_identity_on_all_chains(
            identity_id,
            "dna_test_001",
            "twin_test_001"
        )
        print(f"   Identity: {identity_id}")
        print(f"   Chains: {len(result['chains'])}")
        
        # 2. Verify identity network
        print("\n2. Verifying Identity Network...")
        verification = self.verify_identity_network(identity_id)
        print(f"   Identity: {identity_id}")
        print(f"   Results: {len(verification['verification_results'])}")
        
        # 3. Get network consensus
        print("\n3. Network Consensus...")
        consensus = self.get_network_consensus()
        print(f"   Health: {consensus['network_health']:.2f}")
        print(f"   Consensus Results: {len(consensus['consensus_results'])}")
        
        # 4. Cross-chain identity verification
        print("\n4. Cross-Chain Identity Verification...")
        cross_verify = self.verify_cross_chain_identities()
        print(f"   Total Identities: {cross_verify['total_identities']}")
        print(f"   Verified: {cross_verify['verified_identities']}")
        
        self.show_status()
        
        print("\n" + Color.GREEN + "✅ Demo complete" + Color.END)


# ──────────────────────────────────────────────────────────────
# 6. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxwellMultiChainSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "⚡ SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status           - Show system status")
        print("   - register <id> <dna> <twin> - Register identity")
        print("   - verify <id>      - Verify identity network")
        print("   - consensus        - Get network consensus")
        print("   - cross_verify     - Cross-chain identity verification")
        print("   - demo             - Run demonstration")
        print("   - help             - Show help")
        print("   - exit             - Quit")
        print("=" * 70 + "\n")
        
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip()
                
                if cmd.lower() == "exit":
                    break
                elif cmd.lower() == "status":
                    system.show_status()
                elif cmd.lower().startswith("register "):
                    parts = cmd.split()
                    if len(parts) >= 4:
                        system.register_identity_on_all_chains(parts[1], parts[2], parts[3])
                elif cmd.lower().startswith("verify "):
                    parts = cmd.split()
                    if len(parts) >= 2:
                        system.verify_identity_network(parts[1])
                elif cmd.lower() == "consensus":
                    system.get_network_consensus()
                elif cmd.lower() == "cross_verify":
                    system.verify_cross_chain_identities()
                elif cmd.lower() == "demo":
                    system.run_demo()
                elif cmd.lower() == "help":
                    print("\n   Available commands:")
                    print("   status           - Show system status")
                    print("   register <id> <dna> <twin> - Register identity")
                    print("   verify <id>      - Verify identity network")
                    print("   consensus        - Get network consensus")
                    print("   cross_verify     - Cross-chain identity verification")
                    print("   demo             - Run demonstration")
                    print("   help             - Show this help")
                    print("   exit             - Quit\n")
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
