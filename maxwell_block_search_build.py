#!/usr/bin/env python3
"""
Maxwell Block Search & Build System - Multi-Chain Integration
===============================================================
Save as: maxwell_block_search_build.py
Run:     python3 maxwell_block_search_build.py

FEATURES:
1. Block Search Across Maxwell, Bitcoin, and Connected Chains
2. Block Building from Any Hash (0x000000000...)
3. Cross-Chain Block Discovery
4. Chain State Search
5. Block Data Mining
6. Maxwell Field Validation
7. Multi-Chain Block Linking
8. Autonomous Block Building
9. Search Through Chain History
10. Block Construction from Found Data

Digital twin only - no real biology, chemicals, RF, or hardware control.
"""

import hashlib
import json
import math
import os
import random
import secrets
import struct
import sys
import time
import traceback
import threading
import queue
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
# 1. BLOCK DATA STRUCTURES
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    """Maxwell block with data and validation."""
    
    def __init__(self, index: int, data: Dict, prev_hash: str, maxwell_field: Dict = None):
        self.index = index
        self.timestamp = ts()
        self.data = data
        self.previous_hash = prev_hash
        self.nonce = 0
        self.maxwell_field = maxwell_field or maxwell_signature(
            json.dumps(data, default=str),
            index,
            [0.0, 0.0, 0.0]
        )
        self.hash = self._calculate_hash()
    
    def _calculate_hash(self) -> str:
        return double_sha256(
            json.dumps({
                "index": self.index,
                "timestamp": self.timestamp,
                "data": self.data,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
                "maxwell": self.maxwell_field
            }, sort_keys=True, default=str).encode()
        )
    
    def mine(self, difficulty: int = 3) -> None:
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calculate_hash()
    
    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "maxwell": self.maxwell_field
        }


class BitcoinBlock:
    """Bitcoin-style block for cross-chain search."""
    
    def __init__(self, index: int, data: Dict, prev_hash: str):
        self.index = index
        self.timestamp = ts()
        self.data = data
        self.previous_hash = prev_hash
        self.nonce = 0
        self.merkle_root = self._calculate_merkle_root()
        self.hash = self._calculate_hash()
    
    def _calculate_merkle_root(self) -> str:
        tx_hashes = [double_sha256(json.dumps(tx, default=str).encode()) 
                     for tx in self.data.get("transactions", [])]
        if not tx_hashes:
            return double_sha256(b"empty").hex()
        while len(tx_hashes) > 1:
            if len(tx_hashes) % 2 == 1:
                tx_hashes.append(tx_hashes[-1])
            new_hashes = []
            for i in range(0, len(tx_hashes), 2):
                combined = tx_hashes[i] + tx_hashes[i+1]
                new_hashes.append(double_sha256(bytes.fromhex(combined)))
            tx_hashes = new_hashes
        return tx_hashes[0]
    
    def _calculate_hash(self) -> str:
        return double_sha256(
            json.dumps({
                "index": self.index,
                "timestamp": self.timestamp,
                "data": self.data,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
                "merkle_root": self.merkle_root
            }, sort_keys=True, default=str).encode()
        )
    
    def mine(self, difficulty: int = 3) -> None:
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calculate_hash()
    
    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "merkle_root": self.merkle_root
        }


# ──────────────────────────────────────────────────────────────
# 2. BLOCK SEARCH ENGINE
# ──────────────────────────────────────────────────────────────

class BlockSearchEngine:
    """
    Search engine for blocks across Maxwell, Bitcoin, and connected chains.
    """
    
    def __init__(self):
        self.maxwell_chain: List[Dict] = []
        self.bitcoin_chain: List[Dict] = []
        self.connected_chains: Dict[str, List[Dict]] = {}
        self.search_history: List[Dict] = []
        self.total_energy = 0.0
        self.search_count = 0
        
        # Initialize with genesis blocks
        self._initialize_chains()
    
    def _initialize_chains(self):
        """Initialize chains with genesis blocks."""
        # Maxwell genesis
        maxwell_genesis = {
            "index": 0,
            "timestamp": ts(),
            "data": {"type": "genesis", "chain": "maxwell"},
            "previous_hash": "0" * 64,
            "nonce": 0,
            "hash": "0000000000000000000000000000000000000000000000000000000000000000",
            "maxwell": maxwell_signature("genesis", 0, [0.0, 0.0, 0.0])
        }
        self.maxwell_chain.append(maxwell_genesis)
        
        # Bitcoin genesis
        bitcoin_genesis = {
            "index": 0,
            "timestamp": ts(),
            "data": {"type": "genesis", "chain": "bitcoin"},
            "previous_hash": "0" * 64,
            "nonce": 0,
            "hash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
            "merkle_root": "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
        }
        self.bitcoin_chain.append(bitcoin_genesis)
        
        # Connected chains
        self.connected_chains = {
            "ethereum": [{"index": 0, "hash": "0xd4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3"}],
            "hyperledger": [{"index": 0, "hash": "0x0000000000000000000000000000000000000000000000000000000000000000"}],
            "cosmos": [{"index": 0, "hash": "0x0000000000000000000000000000000000000000000000000000000000000000"}],
            "polkadot": [{"index": 0, "hash": "0x91b171bb158e2d3848fa23a9f1c25182fb8e20313b2c1eb49219da7a70ce90c3"}]
        }
    
    def search_by_hash(self, target_hash: str, chain_type: str = "all") -> Dict:
        """Search for a block by hash across chains."""
        results = []
        
        if chain_type in ["all", "maxwell"]:
            for block in self.maxwell_chain:
                if block.get("hash", "").startswith(target_hash):
                    results.append({"chain": "maxwell", "block": block})
        
        if chain_type in ["all", "bitcoin"]:
            for block in self.bitcoin_chain:
                if block.get("hash", "").startswith(target_hash):
                    results.append({"chain": "bitcoin", "block": block})
        
        if chain_type in ["all", "connected"]:
            for chain_name, chain in self.connected_chains.items():
                for block in chain:
                    if block.get("hash", "").startswith(target_hash):
                        results.append({"chain": chain_name, "block": block})
        
        search_record = {
            "target_hash": target_hash,
            "chain_type": chain_type,
            "results": results,
            "result_count": len(results),
            "timestamp": ts(),
            "search_id": dhash({"target": target_hash, "time": ts()})
        }
        
        self.search_history.append(search_record)
        self.search_count += 1
        self.total_energy += 0.1
        
        return search_record
    
    def search_by_index(self, index: int, chain_type: str = "all") -> Dict:
        """Search for a block by index across chains."""
        results = []
        
        if chain_type in ["all", "maxwell"]:
            for block in self.maxwell_chain:
                if block.get("index") == index:
                    results.append({"chain": "maxwell", "block": block})
        
        if chain_type in ["all", "bitcoin"]:
            for block in self.bitcoin_chain:
                if block.get("index") == index:
                    results.append({"chain": "bitcoin", "block": block})
        
        if chain_type in ["all", "connected"]:
            for chain_name, chain in self.connected_chains.items():
                for block in chain:
                    if block.get("index") == index:
                        results.append({"chain": chain_name, "block": block})
        
        return {
            "index": index,
            "chain_type": chain_type,
            "results": results,
            "result_count": len(results),
            "timestamp": ts()
        }
    
    def search_by_data(self, data_query: str, chain_type: str = "all") -> Dict:
        """Search for blocks containing specific data."""
        results = []
        query_lower = data_query.lower()
        
        chains_to_search = []
        if chain_type in ["all", "maxwell"]:
            chains_to_search.append(("maxwell", self.maxwell_chain))
        if chain_type in ["all", "bitcoin"]:
            chains_to_search.append(("bitcoin", self.bitcoin_chain))
        if chain_type in ["all", "connected"]:
            for name, chain in self.connected_chains.items():
                chains_to_search.append((name, chain))
        
        for chain_name, chain in chains_to_search:
            for block in chain:
                block_str = json.dumps(block, default=str).lower()
                if query_lower in block_str:
                    results.append({"chain": chain_name, "block": block})
        
        return {
            "query": data_query,
            "chain_type": chain_type,
            "results": results,
            "result_count": len(results),
            "timestamp": ts()
        }
    
    def add_block(self, block: Dict, chain_type: str = "maxwell") -> Dict:
        """Add a block to a chain."""
        if chain_type == "maxwell":
            self.maxwell_chain.append(block)
        elif chain_type == "bitcoin":
            self.bitcoin_chain.append(block)
        elif chain_type in self.connected_chains:
            self.connected_chains[chain_type].append(block)
        else:
            return {"status": "error", "reason": "unknown_chain"}
        
        return {
            "status": "added",
            "chain": chain_type,
            "block_index": block.get("index", len(self.maxwell_chain) - 1)
        }
    
    def get_chain_state(self, chain_type: str = "maxwell") -> Dict:
        """Get the current state of a chain."""
        if chain_type == "maxwell":
            chain = self.maxwell_chain
        elif chain_type == "bitcoin":
            chain = self.bitcoin_chain
        elif chain_type in self.connected_chains:
            chain = self.connected_chains[chain_type]
        else:
            return {"status": "error", "reason": "unknown_chain"}
        
        return {
            "chain": chain_type,
            "blocks": len(chain),
            "last_block": chain[-1] if chain else None,
            "first_block": chain[0] if chain else None,
            "timestamp": ts()
        }
    
    def get_stats(self) -> Dict:
        return {
            "search_count": self.search_count,
            "total_energy": self.total_energy,
            "maxwell_blocks": len(self.maxwell_chain),
            "bitcoin_blocks": len(self.bitcoin_chain),
            "connected_chains": len(self.connected_chains),
            "last_search": self.search_history[-1] if self.search_history else None
        }


# ──────────────────────────────────────────────────────────────
# 3. BLOCK BUILDER
# ──────────────────────────────────────────────────────────────

class BlockBuilder:
    """
    Builds new blocks from found data and chain states.
    """
    
    def __init__(self):
        self.built_blocks: List[Dict] = []
        self.build_history: List[Dict] = []
        self.total_energy = 0.0
        self.build_count = 0
    
    def build_from_hash(self, start_hash: str, chain_type: str = "maxwell", 
                       data: Dict = None, difficulty: int = 3) -> Dict:
        """Build a new block starting from a specific hash."""
        # Find the block with the start hash
        search_engine = BlockSearchEngine()
        search_result = search_engine.search_by_hash(start_hash, chain_type)
        
        if search_result["result_count"] == 0:
            return {"status": "error", "reason": "block_not_found", "hash": start_hash}
        
        # Get the found block
        found = search_result["results"][0]
        prev_block = found["block"]
        
        # Create new block
        if chain_type == "maxwell":
            block = MaxwellBlock(
                index=len(search_engine.maxwell_chain),
                data=data or {"type": "built", "from_hash": start_hash, "timestamp": ts()},
                prev_hash=prev_block.get("hash", "0" * 64)
            )
            block.mine(difficulty)
            block_dict = block.to_dict()
        elif chain_type == "bitcoin":
            block = BitcoinBlock(
                index=len(search_engine.bitcoin_chain),
                data=data or {"type": "built", "from_hash": start_hash, "transactions": []},
                prev_hash=prev_block.get("hash", "0" * 64)
            )
            block.mine(difficulty)
            block_dict = block.to_dict()
        else:
            return {"status": "error", "reason": "unsupported_chain_type"}
        
        # Add the block to the chain
        search_engine.add_block(block_dict, chain_type)
        
        build_record = {
            "build_id": dhash({"hash": start_hash, "time": ts()}),
            "start_hash": start_hash,
            "chain_type": chain_type,
            "new_block": block_dict,
            "prev_block": prev_block,
            "difficulty": difficulty,
            "timestamp": ts()
        }
        
        self.built_blocks.append(block_dict)
        self.build_history.append(build_record)
        self.build_count += 1
        self.total_energy += 0.2
        
        return {
            "status": "built",
            "build_record": build_record,
            "new_block": block_dict,
            "energy": self.total_energy
        }
    
    def build_chain_from_hash(self, start_hash: str, chain_type: str = "maxwell",
                             num_blocks: int = 5, difficulty: int = 3) -> Dict:
        """Build a chain of blocks starting from a hash."""
        blocks = []
        current_hash = start_hash
        
        for i in range(num_blocks):
            result = self.build_from_hash(current_hash, chain_type, 
                                         {"type": f"chain_block_{i}", "sequence": i, "timestamp": ts()},
                                         difficulty)
            if result.get("status") == "built":
                new_block = result["new_block"]
                blocks.append(new_block)
                current_hash = new_block.get("hash", "0" * 64)
            else:
                return {"status": "error", "reason": f"build_failed_at_{i}"}
        
        return {
            "status": "chain_built",
            "blocks": blocks,
            "block_count": len(blocks),
            "start_hash": start_hash,
            "end_hash": current_hash,
            "chain_type": chain_type,
            "timestamp": ts()
        }
    
    def build_from_latest(self, chain_type: str = "maxwell", data: Dict = None) -> Dict:
        """Build a block from the latest block in the chain."""
        search_engine = BlockSearchEngine()
        chain_state = search_engine.get_chain_state(chain_type)
        
        if chain_state.get("status") == "error":
            return chain_state
        
        last_block = chain_state.get("last_block")
        if not last_block:
            return {"status": "error", "reason": "no_blocks_in_chain"}
        
        last_hash = last_block.get("hash", "0" * 64)
        return self.build_from_hash(last_hash, chain_type, data)
    
    def get_stats(self) -> Dict:
        return {
            "build_count": self.build_count,
            "total_energy": self.total_energy,
            "built_blocks": len(self.built_blocks),
            "last_build": self.build_history[-1] if self.build_history else None
        }


# ──────────────────────────────────────────────────────────────
# 4. CROSS-CHAIN BLOCK SEARCH
# ──────────────────────────────────────────────────────────────

class CrossChainBlockSearch:
    """
    Cross-chain block search and discovery.
    """
    
    def __init__(self):
        self.search_engine = BlockSearchEngine()
        self.builder = BlockBuilder()
        self.discovered_blocks: Dict[str, List[Dict]] = defaultdict(list)
        self.cross_links: List[Dict] = []
        self.total_energy = 0.0
        self.discovery_count = 0
    
    def discover_blocks(self, start_hash: str, depth: int = 5) -> Dict:
        """Discover blocks across all chains starting from a hash."""
        discovered = []
        chains = ["maxwell", "bitcoin"] + list(self.search_engine.connected_chains.keys())
        
        for chain in chains:
            result = self.search_engine.search_by_hash(start_hash, chain)
            if result["result_count"] > 0:
                for res in result["results"]:
                    discovered.append({
                        "chain": chain,
                        "block": res["block"],
                        "found_at": ts()
                    })
        
        self.discovered_blocks[start_hash] = discovered
        self.discovery_count += 1
        self.total_energy += 0.1
        
        # Create cross-chain links
        if len(discovered) > 1:
            link = {
                "hash": start_hash,
                "chains": [d["chain"] for d in discovered],
                "discovered_at": ts(),
                "link_id": dhash({"hash": start_hash, "chains": chains, "time": ts()})
            }
            self.cross_links.append(link)
        
        return {
            "status": "discovered",
            "hash": start_hash,
            "discovered": discovered,
            "chain_count": len(discovered),
            "cross_link": self.cross_links[-1] if self.cross_links else None
        }
    
    def find_common_block(self, hash_prefix: str) -> Dict:
        """Find a block with a specific hash prefix across all chains."""
        results = []
        chains = ["maxwell", "bitcoin"] + list(self.search_engine.connected_chains.keys())
        
        for chain in chains:
            chain_state = self.search_engine.get_chain_state(chain)
            if chain_state.get("status") == "error":
                continue
            
            blocks = []
            if chain == "maxwell":
                blocks = self.search_engine.maxwell_chain
            elif chain == "bitcoin":
                blocks = self.search_engine.bitcoin_chain
            elif chain in self.search_engine.connected_chains:
                blocks = self.search_engine.connected_chains[chain]
            
            for block in blocks:
                if block.get("hash", "").startswith(hash_prefix):
                    results.append({
                        "chain": chain,
                        "block": block,
                        "found_at": ts()
                    })
        
        return {
            "hash_prefix": hash_prefix,
            "results": results,
            "result_count": len(results),
            "timestamp": ts()
        }
    
    def get_stats(self) -> Dict:
        return {
            "discoveries": self.discovery_count,
            "cross_links": len(self.cross_links),
            "discovered_blocks": sum(len(v) for v in self.discovered_blocks.values()),
            "total_energy": self.total_energy
        }


# ──────────────────────────────────────────────────────────────
# 5. COMPLETE SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxwellBlockSearchSystem:
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "⚡ MAXWELL BLOCK SEARCH & BUILD SYSTEM" + Color.END)
        print(Color.CYAN + "   Multi-Chain Block Discovery + Building" + Color.END)
        print("=" * 70)
        
        # Initialize components
        print(Color.CYAN + "🔍 Initializing Search Engine..." + Color.END)
        self.search_engine = BlockSearchEngine()
        
        print(Color.CYAN + "🏗️ Initializing Block Builder..." + Color.END)
        self.builder = BlockBuilder()
        
        print(Color.CYAN + "🔗 Initializing Cross-Chain Search..." + Color.END)
        self.cross_search = CrossChainBlockSearch()
        
        self.total_operations = 0
        self.chain_health = 1.0
        
        print(Color.GREEN + "✅ System initialized" + Color.END)
        print("=" * 70 + "\n")
    
    def search_block(self, target: str, search_type: str = "hash", chain: str = "all") -> Dict:
        """Search for a block."""
        if search_type == "hash":
            result = self.search_engine.search_by_hash(target, chain)
        elif search_type == "index":
            try:
                result = self.search_engine.search_by_index(int(target), chain)
            except ValueError:
                return {"status": "error", "reason": "invalid_index"}
        elif search_type == "data":
            result = self.search_engine.search_by_data(target, chain)
        else:
            return {"status": "error", "reason": "invalid_search_type"}
        
        self.total_operations += 1
        return result
    
    def build_block(self, start_hash: str = None, chain: str = "maxwell", 
                   data: Dict = None, difficulty: int = 3) -> Dict:
        """Build a new block."""
        if start_hash is None:
            # Build from the latest block
            chain_state = self.search_engine.get_chain_state(chain)
            if chain_state.get("status") == "error":
                return chain_state
            last_block = chain_state.get("last_block")
            if last_block:
                start_hash = last_block.get("hash", "0" * 64)
            else:
                return {"status": "error", "reason": "no_blocks_in_chain"}
        
        result = self.builder.build_from_hash(start_hash, chain, data, difficulty)
        self.total_operations += 1
        return result
    
    def build_chain(self, start_hash: str, chain: str = "maxwell", 
                   num_blocks: int = 3, difficulty: int = 3) -> Dict:
        """Build a chain of blocks."""
        result = self.builder.build_chain_from_hash(start_hash, chain, num_blocks, difficulty)
        self.total_operations += 1
        return result
    
    def discover_blocks(self, start_hash: str, depth: int = 3) -> Dict:
        """Discover blocks across chains."""
        result = self.cross_search.discover_blocks(start_hash, depth)
        self.total_operations += 1
        return result
    
    def find_common(self, hash_prefix: str) -> Dict:
        """Find common blocks across chains."""
        result = self.cross_search.find_common_block(hash_prefix)
        self.total_operations += 1
        return result
    
    def show_status(self):
        search_stats = self.search_engine.get_stats()
        build_stats = self.builder.get_stats()
        cross_stats = self.cross_search.get_stats()
        
        print(f"\n{Color.CYAN}📊 SYSTEM STATUS" + Color.END)
        print("=" * 70)
        
        print(f"\n{Color.BOLD}🔍 Search Engine:" + Color.END)
        print(f"   Searches: {search_stats['search_count']}")
        print(f"   Maxwell Blocks: {search_stats['maxwell_blocks']}")
        print(f"   Bitcoin Blocks: {search_stats['bitcoin_blocks']}")
        print(f"   Connected Chains: {search_stats['connected_chains']}")
        
        print(f"\n{Color.BOLD}🏗️ Block Builder:" + Color.END)
        print(f"   Builds: {build_stats['build_count']}")
        print(f"   Built Blocks: {build_stats['built_blocks']}")
        print(f"   Energy: {build_stats['total_energy']:.2f}")
        
        print(f"\n{Color.BOLD}🔗 Cross-Chain:" + Color.END)
        print(f"   Discoveries: {cross_stats['discoveries']}")
        print(f"   Cross Links: {cross_stats['cross_links']}")
        print(f"   Discovered Blocks: {cross_stats['discovered_blocks']}")
        
        print(f"\n{Color.BOLD}📊 System:" + Color.END)
        print(f"   Total Operations: {self.total_operations}")
        print(f"   Chain Health: {self.chain_health:.2f}")
        
        print("\n" + "=" * 70)
    
    def run_demo(self):
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # 1. Search for genesis block
        print("\n1. Searching for Genesis Block...")
        result = self.search_block("00000000000000000000000000000000", "hash", "all")
        print(f"   Found {result['result_count']} blocks")
        
        # 2. Build a new block from genesis
        print("\n2. Building Block from Genesis...")
        build_result = self.build_block(
            start_hash="0000000000000000000000000000000000000000000000000000000000000000",
            chain="maxwell",
            data={"type": "demo_block", "message": "Hello Maxwell!"},
            difficulty=3
        )
        if build_result.get("status") == "built":
            print(f"   Built Block: {build_result['new_block']['hash'][:16]}...")
        
        # 3. Build a chain
        print("\n3. Building a Chain...")
        chain_result = self.build_chain(
            start_hash="0000000000000000000000000000000000000000000000000000000000000000",
            chain="maxwell",
            num_blocks=3,
            difficulty=3
        )
        if chain_result.get("status") == "chain_built":
            print(f"   Built {chain_result['block_count']} blocks")
        
        # 4. Cross-chain discovery
        print("\n4. Cross-Chain Discovery...")
        discover_result = self.discover_blocks(
            "0000000000000000000000000000000000000000000000000000000000000000",
            depth=3
        )
        print(f"   Discovered on {discover_result['chain_count']} chains")
        
        self.show_status()
        print("\n" + Color.GREEN + "✅ Demo complete" + Color.END)


# ──────────────────────────────────────────────────────────────
# 6. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxwellBlockSearchSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "⚡ SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status              - Show system status")
        print("   - search <hash>       - Search for a block")
        print("   - build <hash>        - Build a block from hash")
        print("   - chain <hash> <n>    - Build a chain of n blocks")
        print("   - discover <hash>     - Discover blocks across chains")
        print("   - common <prefix>     - Find common blocks")
        print("   - demo                - Run demonstration")
        print("   - help                - Show help")
        print("   - exit                - Quit")
        print("=" * 70 + "\n")
        
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip()
                
                if cmd.lower() == "exit":
                    break
                elif cmd.lower() == "status":
                    system.show_status()
                elif cmd.lower().startswith("search "):
                    parts = cmd.split()
                    if len(parts) >= 2:
                        system.search_block(parts[1])
                    else:
                        print("   Usage: search <hash>")
                elif cmd.lower().startswith("build "):
                    parts = cmd.split()
                    if len(parts) >= 2:
                        system.build_block(parts[1])
                    else:
                        print("   Usage: build <hash>")
                elif cmd.lower().startswith("chain "):
                    parts = cmd.split()
                    if len(parts) >= 3:
                        try:
                            num_blocks = int(parts[2])
                            system.build_chain(parts[1], num_blocks=num_blocks)
                        except ValueError:
                            print("   Invalid number of blocks")
                    else:
                        print("   Usage: chain <hash> <num_blocks>")
                elif cmd.lower().startswith("discover "):
                    parts = cmd.split()
                    if len(parts) >= 2:
                        system.discover_blocks(parts[1])
                    else:
                        print("   Usage: discover <hash>")
                elif cmd.lower().startswith("common "):
                    parts = cmd.split()
                    if len(parts) >= 2:
                        system.find_common(parts[1])
                    else:
                        print("   Usage: common <prefix>")
                elif cmd.lower() == "demo":
                    system.run_demo()
                elif cmd.lower() == "help":
                    print("\n   Available commands:")
                    print("   status              - Show system status")
                    print("   search <hash>       - Search for a block")
                    print("   build <hash>        - Build a block from hash")
                    print("   chain <hash> <n>    - Build a chain of n blocks")
                    print("   discover <hash>     - Discover blocks across chains")
                    print("   common <prefix>     - Find common blocks")
                    print("   demo                - Run demonstration")
                    print("   help                - Show this help")
                    print("   exit                - Quit\n")
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
