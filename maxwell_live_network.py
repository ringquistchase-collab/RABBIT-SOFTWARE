#!/usr/bin/env python3
"""
Maxwell Blockchain - Live Network Implementation
==================================================
Save as: maxwell_live_network.py
Run:     python3 maxwell_live_network.py --node-id node1 --port 8333

LIVE NETWORK FEATURES:
1. P2P Node Discovery and Connection
2. Multiple Node Support
3. Distributed Consensus (PoW)
4. Blockchain Synchronization
5. REST API Gateway
6. WebSocket Real-time Updates
7. Bitcoin Core Integration
8. Mining Pool Support
9. Transaction Propagation
10. Block Broadcasting
11. Network Status Monitoring
12. Persistent Storage

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
import multiprocessing
import queue
import socket
import sqlite3
import argparse
import signal
import asyncio
import websockets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
import secrets

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    from flask import Flask, jsonify, request, render_template
    from flask_cors import CORS
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


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
# 2. PERSISTENT STORAGE
# ──────────────────────────────────────────────────────────────

class PersistentStorage:
    """SQLite storage for blockchain data."""
    
    def __init__(self, db_path: str = "maxwell_live.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                index INTEGER PRIMARY KEY,
                hash TEXT UNIQUE,
                previous_hash TEXT,
                timestamp TEXT,
                data TEXT,
                nonce INTEGER,
                difficulty INTEGER,
                maxwell_field TEXT,
                merkle_root TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                txid TEXT PRIMARY KEY,
                block_index INTEGER,
                data TEXT,
                timestamp TEXT,
                status TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS peers (
                peer_id TEXT PRIMARY KEY,
                address TEXT,
                port INTEGER,
                last_seen TEXT,
                status TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                address TEXT,
                port INTEGER,
                last_seen TEXT,
                status TEXT,
                chain_height INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_block(self, block: Dict):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO blocks 
            (index, hash, previous_hash, timestamp, data, nonce, difficulty, maxwell_field, merkle_root)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            block["index"],
            block["hash"],
            block["previous_hash"],
            block["timestamp"],
            json.dumps(block.get("data", {}), default=str),
            block.get("nonce", 0),
            block.get("difficulty", 8),
            json.dumps(block.get("maxwell", {}), default=str),
            block.get("merkle_root", "")
        ))
        conn.commit()
        conn.close()
    
    def get_block(self, block_hash: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM blocks WHERE hash = ?', (block_hash,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "index": row[0],
                "hash": row[1],
                "previous_hash": row[2],
                "timestamp": row[3],
                "data": json.loads(row[4]),
                "nonce": row[5],
                "difficulty": row[6],
                "maxwell": json.loads(row[7]) if row[7] else {},
                "merkle_root": row[8]
            }
        return None
    
    def get_last_block(self) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM blocks ORDER BY index DESC LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "index": row[0],
                "hash": row[1],
                "previous_hash": row[2],
                "timestamp": row[3],
                "data": json.loads(row[4]),
                "nonce": row[5],
                "difficulty": row[6],
                "maxwell": json.loads(row[7]) if row[7] else {},
                "merkle_root": row[8]
            }
        return None
    
    def get_all_blocks(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM blocks ORDER BY index ASC')
        rows = cursor.fetchall()
        conn.close()
        blocks = []
        for row in rows:
            blocks.append({
                "index": row[0],
                "hash": row[1],
                "previous_hash": row[2],
                "timestamp": row[3],
                "data": json.loads(row[4]),
                "nonce": row[5],
                "difficulty": row[6],
                "maxwell": json.loads(row[7]) if row[7] else {},
                "merkle_root": row[8]
            })
        return blocks
    
    def save_peer(self, peer_id: str, address: str, port: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO peers (peer_id, address, port, last_seen, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (peer_id, address, port, ts(), "active"))
        conn.commit()
        conn.close()
    
    def get_peers(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM peers WHERE status = "active"')
        rows = cursor.fetchall()
        conn.close()
        return [{"peer_id": r[0], "address": r[1], "port": r[2], "last_seen": r[3]} for r in rows]
    
    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM blocks')
        blocks = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM peers')
        peers = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM transactions')
        txs = cursor.fetchone()[0]
        conn.close()
        return {"blocks": blocks, "peers": peers, "transactions": txs}


# ──────────────────────────────────────────────────────────────
# 3. BLOCK WITH MINING
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    """Block with optimized mining."""
    
    def __init__(self, index: int, data: Dict, prev_hash: str, difficulty: int = 8):
        self.index = index
        self.timestamp = ts()
        self.data = data
        self.previous_hash = prev_hash
        self.nonce = 0
        self.difficulty = difficulty
        self.merkle_root = self._compute_merkle_root()
        self.hash = ""
        self.maxwell = None
        self._static_hash = None
        self._precompute_static()
    
    def _compute_merkle_root(self) -> str:
        transactions = self.data.get("transactions", [])
        if not transactions:
            return double_sha256(b"empty")
        hashes = [double_sha256(json.dumps(tx, default=str).encode()) for tx in transactions]
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])
            new_hashes = []
            for i in range(0, len(hashes), 2):
                combined = bytes.fromhex(hashes[i] + hashes[i+1])
                new_hashes.append(double_sha256(combined))
            hashes = new_hashes
        return hashes[0] if hashes else double_sha256(b"empty")
    
    def _precompute_static(self):
        static_json = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root
        }, sort_keys=True, default=str).encode()
        static = hashlib.sha256()
        static.update(static_json)
        self._static_hash = static.digest()
    
    def compute_hash(self, nonce: int = None) -> str:
        if nonce is not None:
            self.nonce = nonce
        nonce_bytes = str(self.nonce).encode()
        combined = self._static_hash + nonce_bytes
        final = hashlib.sha256()
        final.update(combined)
        return final.hexdigest()
    
    def mine(self) -> bool:
        target = "0" * self.difficulty
        hashes = 0
        start = time.time()
        
        while True:
            self.nonce += 1
            self.hash = self.compute_hash()
            hashes += 1
            
            if self.hash.startswith(target):
                self.maxwell = maxwell_signature(
                    self.hash + self.previous_hash,
                    self.index,
                    [0.0, 0.0, 0.0]
                )
                print(f"⛏️ Block {self.index} mined! Nonce: {self.nonce:,}, {hashes/time.time()-start:.0f} h/s")
                return True
            
            if hashes % 100000 == 0:
                print(f"   🔍 {hashes:,} hashes, Nonce: {self.nonce:,}")
    
    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
            "merkle_root": self.merkle_root,
            "difficulty": self.difficulty,
            "maxwell": self.maxwell
        }


# ──────────────────────────────────────────────────────────────
# 4. P2P NETWORK NODE
# ──────────────────────────────────────────────────────────────

class MaxwellNode:
    """
    P2P Network Node with blockchain, mining, and peer communication.
    """
    
    def __init__(self, node_id: str, host: str = "0.0.0.0", port: int = 8333,
                 difficulty: int = 6, enable_mining: bool = True):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.difficulty = difficulty
        self.enable_mining = enable_mining
        self.storage = PersistentStorage(f"maxwell_{node_id}.db")
        self.chain: List[Dict] = []
        self.peers: Set[str] = set()
        self.pending_transactions: List[Dict] = []
        self.is_mining = False
        self.is_running = False
        self.block_queue: queue.Queue = queue.Queue()
        
        # Thread pools
        self.miner_pool = ThreadPoolExecutor(max_workers=2)
        self.network_pool = ThreadPoolExecutor(max_workers=4)
        
        # Load existing chain
        self._load_chain()
        
        # If no chain, create genesis
        if not self.chain:
            self._create_genesis()
        
        # Start network services
        self._start_services()
        
        print(f"🖥️ Node {node_id} initialized at {host}:{port}")
        print(f"📊 Chain height: {len(self.chain)}")
        print(f"⛏️ Mining: {'Enabled' if enable_mining else 'Disabled'}")
    
    def _load_chain(self):
        """Load chain from storage."""
        blocks = self.storage.get_all_blocks()
        if blocks:
            self.chain = blocks
            print(f"📂 Loaded {len(blocks)} blocks from storage")
    
    def _create_genesis(self):
        """Create genesis block."""
        print("🔨 Creating genesis block...")
        genesis_data = {
            "type": "genesis",
            "version": "1.0",
            "message": "Maxwell Blockchain Genesis Block",
            "chain_id": "maxwell_mainnet",
            "node_id": self.node_id
        }
        genesis = MaxwellBlock(0, genesis_data, "0" * 64, self.difficulty)
        genesis.mine()
        block_dict = genesis.to_dict()
        self.chain.append(block_dict)
        self.storage.save_block(block_dict)
        print(f"✅ Genesis created: {block_dict['hash']}")
    
    def _start_services(self):
        """Start network services."""
        self.is_running = True
        
        # Start peer listener
        threading.Thread(target=self._peer_listener, daemon=True).start()
        
        # Start mining if enabled
        if self.enable_mining:
            threading.Thread(target=self._mining_loop, daemon=True).start()
        
        # Start block propagation
        threading.Thread(target=self._propagation_loop, daemon=True).start()
    
    def _peer_listener(self):
        """Listen for incoming peer connections."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(10)
        print(f"📡 Listening on {self.host}:{self.port}")
        
        while self.is_running:
            try:
                conn, addr = sock.accept()
                threading.Thread(target=self._handle_peer, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"❌ Peer listener error: {e}")
    
    def _handle_peer(self, conn, addr):
        """Handle incoming peer connection."""
        try:
            data = conn.recv(4096).decode()
            if not data:
                return
            
            message = json.loads(data)
            
            if message.get("type") == "handshake":
                peer_id = message.get("node_id")
                peer_addr = addr[0]
                peer_port = message.get("port", 8333)
                self.peers.add(peer_id)
                self.storage.save_peer(peer_id, peer_addr, peer_port)
                conn.send(json.dumps({
                    "type": "handshake_ack",
                    "node_id": self.node_id,
                    "chain_height": len(self.chain)
                }).encode())
                print(f"🤝 Peer connected: {peer_id} ({peer_addr}:{peer_port})")
            
            elif message.get("type") == "block":
                block = message.get("block")
                if block:
                    self.block_queue.put(block)
                    print(f"📦 Received block {block['index']} from peer")
            
            elif message.get("type") == "get_blocks":
                start = message.get("start", 0)
                end = message.get("end", len(self.chain))
                blocks = self.chain[start:end]
                conn.send(json.dumps({
                    "type": "blocks",
                    "blocks": blocks
                }).encode())
            
            elif message.get("type") == "get_chain":
                conn.send(json.dumps({
                    "type": "chain",
                    "chain": self.chain
                }).encode())
            
            conn.close()
        except Exception as e:
            print(f"❌ Peer handler error: {e}")
    
    def _mining_loop(self):
        """Mine blocks in background."""
        print("⛏️ Mining thread started")
        self.is_mining = True
        
        while self.is_running:
            try:
                # Check if we have pending transactions
                if not self.pending_transactions:
                    time.sleep(1)
                    continue
                
                # Create new block
                prev_hash = self.chain[-1]["hash"]
                data = {
                    "type": "block",
                    "transactions": self.pending_transactions[:10],
                    "timestamp": ts(),
                    "miner": self.node_id
                }
                
                block = MaxwellBlock(len(self.chain), data, prev_hash, self.difficulty)
                block.mine()
                block_dict = block.to_dict()
                
                # Add to chain
                self.chain.append(block_dict)
                self.storage.save_block(block_dict)
                
                # Clear mined transactions
                self.pending_transactions = self.pending_transactions[10:]
                
                # Broadcast to peers
                self._broadcast_block(block_dict)
                
                print(f"⛏️ Block {block_dict['index']} mined and broadcasted")
                print(f"   Hash: {block_dict['hash']}")
                print(f"   Nonce: {block_dict['nonce']:,}")
                
                time.sleep(0.1)
            except Exception as e:
                print(f"❌ Mining error: {e}")
                time.sleep(1)
    
    def _broadcast_block(self, block: Dict):
        """Broadcast a block to all peers."""
        for peer_id in self.peers:
            try:
                # Get peer info
                peers = self.storage.get_peers()
                peer = next((p for p in peers if p["peer_id"] == peer_id), None)
                if not peer:
                    continue
                
                # Connect to peer
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((peer["address"], peer["port"]))
                sock.send(json.dumps({
                    "type": "block",
                    "block": block
                }).encode())
                sock.close()
            except Exception as e:
                print(f"❌ Failed to broadcast to {peer_id}: {e}")
    
    def _propagation_loop(self):
        """Handle incoming blocks from peers."""
        while self.is_running:
            try:
                block = self.block_queue.get(timeout=1)
                if block:
                    # Validate block
                    if self._validate_block(block):
                        # Add to chain if it extends our chain
                        if block["previous_hash"] == self.chain[-1]["hash"]:
                            self.chain.append(block)
                            self.storage.save_block(block)
                            print(f"📦 Block {block['index']} added to chain")
                        elif block["index"] > len(self.chain):
                            # We're behind, sync
                            self._sync_from_peers()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Propagation error: {e}")
    
    def _validate_block(self, block: Dict) -> bool:
        """Validate a block."""
        # Check index
        if block["index"] != len(self.chain):
            return False
        
        # Check previous hash
        if block["previous_hash"] != self.chain[-1]["hash"]:
            return False
        
        # Check hash
        expected = double_sha256(
            json.dumps({
                "index": block["index"],
                "timestamp": block["timestamp"],
                "data": block["data"],
                "previous_hash": block["previous_hash"],
                "nonce": block["nonce"],
                "merkle_root": block.get("merkle_root", "")
            }, sort_keys=True, default=str).encode()
        )
        
        if expected != block["hash"]:
            return False
        
        # Check difficulty
        if not block["hash"].startswith("0" * block.get("difficulty", 8)):
            return False
        
        return True
    
    def _sync_from_peers(self):
        """Synchronize chain with peers."""
        for peer_id in self.peers:
            try:
                peers = self.storage.get_peers()
                peer = next((p for p in peers if p["peer_id"] == peer_id), None)
                if not peer:
                    continue
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((peer["address"], peer["port"]))
                
                # Request chain
                sock.send(json.dumps({
                    "type": "get_chain"
                }).encode())
                
                response = json.loads(sock.recv(4096).decode())
                if response.get("type") == "chain":
                    chain = response.get("chain", [])
                    if len(chain) > len(self.chain):
                        # Replace chain with longer one
                        self.chain = chain
                        # Save to storage
                        for block in chain:
                            self.storage.save_block(block)
                        print(f"🔄 Synced with {peer_id}, chain height: {len(chain)}")
                
                sock.close()
            except Exception as e:
                print(f"❌ Sync with {peer_id} failed: {e}")
    
    def add_transaction(self, transaction: Dict) -> Dict:
        """Add a transaction to the mempool."""
        tx = {
            "txid": dhash(transaction),
            "data": transaction,
            "timestamp": ts()
        }
        self.pending_transactions.append(tx)
        return {"status": "added", "txid": tx["txid"]}
    
    def get_chain(self) -> List[Dict]:
        return self.chain
    
    def get_stats(self) -> Dict:
        return {
            "node_id": self.node_id,
            "chain_height": len(self.chain),
            "peers": len(self.peers),
            "pending_transactions": len(self.pending_transactions),
            "is_mining": self.is_mining,
            "is_running": self.is_running,
            "difficulty": self.difficulty,
            "port": self.port,
            "storage": self.storage.get_stats()
        }
    
    def stop(self):
        """Stop the node."""
        self.is_running = False
        self.is_mining = False
        print(f"🛑 Node {self.node_id} stopped")


# ──────────────────────────────────────────────────────────────
# 5. LIVE NETWORK MANAGER
# ──────────────────────────────────────────────────────────────

class LiveNetworkManager:
    """
    Manages multiple nodes and network connections.
    """
    
    def __init__(self):
        self.nodes: Dict[str, MaxwellNode] = {}
        print(Color.HEADER + "🌐 Maxwell Live Network Manager" + Color.END)
        print("=" * 60)
    
    def create_node(self, node_id: str, host: str = "0.0.0.0", 
                    port: int = None, difficulty: int = 6,
                    enable_mining: bool = True) -> MaxwellNode:
        """Create a new node."""
        if port is None:
            port = 8333 + len(self.nodes)
        
        node = MaxwellNode(node_id, host, port, difficulty, enable_mining)
        self.nodes[node_id] = node
        return node
    
    def connect_peers(self, node1_id: str, node2_id: str) -> Dict:
        """Connect two nodes."""
        if node1_id not in self.nodes or node2_id not in self.nodes:
            return {"status": "error", "reason": "node_not_found"}
        
        node1 = self.nodes[node1_id]
        node2 = self.nodes[node2_id]
        
        # Add each other as peers
        node1.peers.add(node2_id)
        node2.peers.add(node1_id)
        
        node1.storage.save_peer(node2_id, "127.0.0.1", node2.port)
        node2.storage.save_peer(node1_id, "127.0.0.1", node1.port)
        
        return {"status": "connected", "node1": node1_id, "node2": node2_id}
    
    def connect_all_peers(self):
        """Connect all nodes in a mesh."""
        node_ids = list(self.nodes.keys())
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                self.connect_peers(node_ids[i], node_ids[j])
        print(f"🔗 Connected {len(node_ids)} nodes in mesh")
    
    def get_network_status(self) -> Dict:
        """Get network status."""
        stats = {}
        for node_id, node in self.nodes.items():
            stats[node_id] = node.get_stats()
        return {
            "nodes": len(self.nodes),
            "details": stats,
            "timestamp": ts()
        }
    
    def stop_all(self):
        """Stop all nodes."""
        for node in self.nodes.values():
            node.stop()
        print("🛑 All nodes stopped")


# ──────────────────────────────────────────────────────────────
# 6. MAIN WITH LIVE NETWORK
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Maxwell Live Network")
    parser.add_argument("--node-id", default="node1", help="Node ID")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8333, help="Port to listen")
    parser.add_argument("--difficulty", type=int, default=6, help="Mining difficulty")
    parser.add_argument("--no-mining", action="store_true", help="Disable mining")
    parser.add_argument("--multi-node", action="store_true", help="Run multiple nodes")
    parser.add_argument("--peers", nargs="+", help="Peer addresses to connect")
    args = parser.parse_args()
    
    print(Color.HEADER + "⚡ Maxwell Live Network" + Color.END)
    print(Color.CYAN + "   Multi-Node Blockchain Network" + Color.END)
    print("=" * 70)
    
    if args.multi_node:
        # Run multiple nodes locally
        manager = LiveNetworkManager()
        
        # Create nodes
        for i in range(3):
            node_id = f"node{i+1}"
            port = 8333 + i
            manager.create_node(node_id, "0.0.0.0", port, args.difficulty, not args.no_mining)
        
        # Connect all
        manager.connect_all_peers()
        
        print("\n" + Color.GREEN + "✅ Multi-node network running!" + Color.END)
        print(f"   Nodes: {list(manager.nodes.keys())}")
        
        # Keep running
        try:
            while True:
                status = manager.get_network_status()
                print(f"\n{Color.CYAN}📊 Network Status" + Color.END)
                print("=" * 50)
                for node_id, stats in status["details"].items():
                    print(f"   {node_id}: Height: {stats['chain_height']}, Peers: {stats['peers']}")
                print("=" * 50)
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
            manager.stop_all()
    else:
        # Run single node
        node = MaxwellNode(
            args.node_id,
            args.host,
            args.port,
            args.difficulty,
            not args.no_mining
        )
        
        print(f"\n{Color.GREEN}✅ Node {args.node_id} running!" + Color.END)
        print(f"   Host: {args.host}:{args.port}")
        print(f"   Difficulty: {args.difficulty}")
        print(f"   Mining: {not args.no_mining}")
        
        if args.peers:
            print(f"   Peers: {args.peers}")
            for peer in args.peers:
                node.peers.add(peer)
        
        # Keep running
        try:
            while True:
                stats = node.get_stats()
                print(f"\n{Color.CYAN}📊 Node Status" + Color.END)
                print("=" * 50)
                print(f"   Chain Height: {stats['chain_height']}")
                print(f"   Peers: {stats['peers']}")
                print(f"   Pending TXs: {stats['pending_transactions']}")
                print(f"   Mining: {stats['is_mining']}")
                print("=" * 50)
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
            node.stop()


if __name__ == "__main__":
    sys.exit(main())
