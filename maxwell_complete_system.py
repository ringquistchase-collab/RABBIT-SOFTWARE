#!/usr/bin/env python3
"""
Maxwell Bio-Twin Complete System
================================
Save as: maxwell_complete_system.py
Run:     python3 maxwell_complete_system.py

UNIFIED SYSTEM WITH:
1. Maxwell Digital Twin Chain
2. Bio-Engineer with DNA processing
3. Twin Engineer with memristor state
4. Network nodes and connections
5. Persistent storage
6. Blockchain anchoring
7. 50/50 equilibrium detection
8. Event-driven architecture
9. Error recovery
10. Full node mesh

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
import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict
from enum import Enum

# Optional cryptography
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# Optional requests
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ──────────────────────────────────────────────────────────────
# 1. UTILITIES
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


def sanitize_json(obj: Any) -> Any:
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


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


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def truncate_hash(h: str, length: int = 12) -> str:
    return h[:length] + "..." if len(h) > length else h


def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i * 4: (i + 1) * 4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]


def compute_maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
    """Compute the Maxwell field signature for data."""
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
# 2. PERSISTENT STORAGE
# ──────────────────────────────────────────────────────────────

class PersistentStorage:
    """Persistent storage using SQLite and file system."""
    
    def __init__(self, storage_dir: str = "maxwell_storage"):
        self.storage_dir = storage_dir
        self.db_path = os.path.join(storage_dir, "maxwell.db")
        self.files_dir = os.path.join(storage_dir, "files")
        
        os.makedirs(storage_dir, exist_ok=True)
        os.makedirs(self.files_dir, exist_ok=True)
        
        self._init_database()
        self.stats = {"records": 0, "blocks": 0, "transactions": 0, "files": 0}
        
        print(f"📁 Storage initialized: {storage_dir}")
    
    def _init_database(self):
        """Initialize the SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chain_blocks (
                block_index INTEGER PRIMARY KEY,
                block_hash TEXT UNIQUE NOT NULL,
                previous_hash TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                transactions TEXT NOT NULL,
                nonce INTEGER NOT NULL,
                difficulty INTEGER NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS storage_records (
                record_id TEXT PRIMARY KEY,
                record_type TEXT NOT NULL,
                data TEXT NOT NULL,
                hash TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                parent_id TEXT,
                block_index INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS identity_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS network_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                data TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_log (
                error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                context TEXT,
                resolved INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
        self._update_stats()
    
    def _update_stats(self):
        """Update storage statistics."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM chain_blocks")
            self.stats["blocks"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM storage_records")
            self.stats["records"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM network_nodes")
            self.stats["nodes"] = cursor.fetchone()[0]
            conn.close()
        except Exception:
            pass
    
    def save_block(self, block: Dict) -> bool:
        """Save a block to storage."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO chain_blocks 
                (block_index, block_hash, previous_hash, timestamp, transactions, nonce, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                block["index"],
                block["hash"],
                block["previous_hash"],
                block.get("timestamp", get_timestamp()),
                json.dumps(block.get("transactions", []), default=str),
                block.get("nonce", 0),
                block.get("difficulty", 3)
            ))
            conn.commit()
            conn.close()
            self.stats["blocks"] += 1
            return True
        except Exception as e:
            self._log_error("save_block", str(e))
            return False
    
    def get_block(self, block_hash: str) -> Optional[Dict]:
        """Retrieve a block by hash."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT block_index, block_hash, previous_hash, timestamp, transactions, nonce, difficulty
                FROM chain_blocks WHERE block_hash = ?
            ''', (block_hash,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    "index": row[0],
                    "hash": row[1],
                    "previous_hash": row[2],
                    "timestamp": row[3],
                    "transactions": json.loads(row[4]),
                    "nonce": row[5],
                    "difficulty": row[6]
                }
            return None
        except Exception:
            return None
    
    def get_last_block(self) -> Optional[Dict]:
        """Get the last block."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT block_index, block_hash, previous_hash, timestamp, transactions, nonce, difficulty
                FROM chain_blocks ORDER BY block_index DESC LIMIT 1
            ''')
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    "index": row[0],
                    "hash": row[1],
                    "previous_hash": row[2],
                    "timestamp": row[3],
                    "transactions": json.loads(row[4]),
                    "nonce": row[5],
                    "difficulty": row[6]
                }
            return None
        except Exception:
            return None
    
    def save_record(self, record: Dict) -> bool:
        """Save a storage record."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO storage_records 
                (record_id, record_type, data, hash, timestamp, parent_id, block_index)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.get("record_id", deterministic_hash(record)),
                record.get("type", "generic"),
                json.dumps(record.get("data", {}), default=str),
                record.get("hash", deterministic_hash(record)),
                record.get("timestamp", get_timestamp()),
                record.get("parent_id", ""),
                record.get("block_index", 0)
            ))
            conn.commit()
            conn.close()
            self.stats["records"] += 1
            return True
        except Exception as e:
            self._log_error("save_record", str(e))
            return False
    
    def get_record(self, record_id: str) -> Optional[Dict]:
        """Retrieve a record by ID."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT record_id, record_type, data, hash, timestamp, parent_id, block_index
                FROM storage_records WHERE record_id = ?
            ''', (record_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    "record_id": row[0],
                    "type": row[1],
                    "data": json.loads(row[2]),
                    "hash": row[3],
                    "timestamp": row[4],
                    "parent_id": row[5],
                    "block_index": row[6]
                }
            return None
        except Exception:
            return None
    
    def save_node(self, node_id: str, node_data: Dict) -> bool:
        """Save a network node."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO network_nodes (node_id, node_type, data, last_seen)
                VALUES (?, ?, ?, ?)
            ''', (
                node_id,
                node_data.get("type", "generic"),
                json.dumps(node_data, default=str),
                get_timestamp()
            ))
            conn.commit()
            conn.close()
            self.stats["nodes"] = (self.stats.get("nodes", 0) + 1)
            return True
        except Exception as e:
            self._log_error("save_node", str(e))
            return False
    
    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get a network node."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT node_type, data FROM network_nodes WHERE node_id = ?', (node_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {"type": row[0], "data": json.loads(row[1])}
            return None
        except Exception:
            return None
    
    def get_all_nodes(self) -> List[Dict]:
        """Get all network nodes."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT node_id, node_type, data, last_seen FROM network_nodes')
            rows = cursor.fetchall()
            conn.close()
            return [{"node_id": row[0], "type": row[1], "data": json.loads(row[2]), "last_seen": row[3]} for row in rows]
        except Exception:
            return []
    
    def save_identity_state(self, key: str, value: Any) -> bool:
        """Save identity state."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO identity_state (key, value, updated_at) VALUES (?, ?, ?)',
                          (key, json.dumps(value, default=str), get_timestamp()))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False
    
    def get_identity_state(self, key: str) -> Optional[Any]:
        """Get identity state."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM identity_state WHERE key = ?', (key,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
            return None
        except Exception:
            return None
    
    def _log_error(self, error_type: str, message: str, context: Dict = None):
        """Log an error."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO error_log (timestamp, error_type, message, context)
                VALUES (?, ?, ?, ?)
            ''', (get_timestamp(), error_type, message, json.dumps(context or {}, default=str)))
            conn.commit()
            conn.close()
        except Exception:
            pass
    
    def get_errors(self) -> List[Dict]:
        """Get logged errors."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT error_id, timestamp, error_type, message, context, resolved
                FROM error_log ORDER BY timestamp DESC LIMIT 50
            ''')
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    "error_id": row[0],
                    "timestamp": row[1],
                    "type": row[2],
                    "message": row[3],
                    "context": json.loads(row[4]) if row[4] else {},
                    "resolved": bool(row[5])
                }
                for row in rows
            ]
        except Exception:
            return []
    
    def get_stats(self) -> Dict:
        """Get storage statistics."""
        self._update_stats()
        return self.stats


# ──────────────────────────────────────────────────────────────
# 3. NETWORKED BLOCKCHAIN
# ──────────────────────────────────────────────────────────────

class NetworkedBlockchain:
    """Blockchain with persistence and network awareness."""
    
    def __init__(self, storage: PersistentStorage, difficulty: int = 3):
        self.storage = storage
        self.difficulty = difficulty
        self.pending_transactions: List[Dict] = []
        self.chain: List[Dict] = []
        self.network_peers: Set[str] = set()
        self.sync_queue: queue.Queue = queue.Queue()
        
        self._load_or_create_chain()
    
    def _load_or_create_chain(self):
        """Load chain from storage or create genesis."""
        last_block = self.storage.get_last_block()
        
        if last_block:
            self.chain = [last_block]
            current = last_block
            while current and current.get("previous_hash") != "0" * 64:
                prev = self.storage.get_block(current["previous_hash"])
                if prev:
                    self.chain.insert(0, prev)
                    current = prev
                else:
                    break
            print(f"⛓️ Loaded {len(self.chain)} blocks from storage")
        else:
            self._create_genesis()
    
    def _create_genesis(self):
        """Create the genesis block."""
        genesis = {
            "index": 0,
            "timestamp": get_timestamp(),
            "transactions": [{"type": "genesis", "data": "Maxwell Bio-Twin Genesis"}],
            "previous_hash": "0" * 64,
            "nonce": 0,
            "difficulty": self.difficulty
        }
        genesis["hash"] = self._calculate_hash(genesis)
        self.chain = [genesis]
        self.storage.save_block(genesis)
        print(f"⛓️ Created genesis block: {truncate_hash(genesis['hash'])}")
    
    def _calculate_hash(self, block: Dict) -> str:
        """Calculate block hash."""
        block_copy = block.copy()
        block_copy.pop("hash", None)
        return openssl_hash(json.dumps(block_copy, sort_keys=True, default=str).encode(), "sha256")
    
    def _mine(self, block: Dict) -> None:
        """Mine a block."""
        target = "0" * self.difficulty
        while not block["hash"].startswith(target):
            block["nonce"] += 1
            block["hash"] = self._calculate_hash(block)
    
    def add_transaction(self, transaction: Dict) -> Dict:
        """Add a transaction to pending pool."""
        tx = {
            "id": deterministic_hash(transaction),
            "timestamp": get_timestamp(),
            "type": transaction.get("type", "generic"),
            "data": transaction,
            "hash": deterministic_hash(transaction)
        }
        self.pending_transactions.append(tx)
        
        if len(self.pending_transactions) >= 1:
            return self.mine_block()
        
        return {"status": "pending", "transaction_id": tx["id"], "pending_count": len(self.pending_transactions)}
    
    def mine_block(self) -> Dict:
        """Mine a new block."""
        if not self.pending_transactions:
            return {"status": "error", "message": "No pending transactions"}
        
        try:
            prev_block = self.chain[-1]
            block = {
                "index": len(self.chain),
                "timestamp": get_timestamp(),
                "transactions": self.pending_transactions.copy(),
                "previous_hash": prev_block["hash"],
                "nonce": 0,
                "difficulty": self.difficulty
            }
            block["hash"] = self._calculate_hash(block)
            self._mine(block)
            
            self.chain.append(block)
            self.storage.save_block(block)
            
            tx_count = len(self.pending_transactions)
            self.pending_transactions = []
            
            return {
                "status": "success",
                "block_index": block["index"],
                "block_hash": truncate_hash(block["hash"]),
                "transaction_count": tx_count,
                "nonce": block["nonce"]
            }
        except Exception as e:
            return {"status": "error", "message": f"Mining error: {str(e)}"}
    
    def add_peer(self, peer_id: str):
        """Add a network peer."""
        self.network_peers.add(peer_id)
        print(f"🌐 Added peer: {peer_id}")
    
    def get_chain_length(self) -> int:
        return len(self.chain)
    
    def get_last_block(self) -> Optional[Dict]:
        return self.chain[-1] if self.chain else None
    
    def verify_chain(self) -> Dict:
        """Verify the entire chain."""
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            
            if current["hash"] != self._calculate_hash(current):
                return {"status": "error", "message": f"Invalid hash at block {i}", "block_index": i}
            
            if current["previous_hash"] != previous["hash"]:
                return {"status": "error", "message": f"Invalid link at block {i}", "block_index": i}
        
        return {"status": "success", "message": "Chain verified", "block_count": len(self.chain)}
    
    def get_stats(self) -> Dict:
        return {
            "chain_length": len(self.chain),
            "difficulty": self.difficulty,
            "pending_transactions": len(self.pending_transactions),
            "peers": len(self.network_peers)
        }


# ──────────────────────────────────────────────────────────────
# 4. DNA DATA PROVIDER (FIXED)
# ──────────────────────────────────────────────────────────────

class DNADataProvider:
    """Fetches DNA data with fallback to synthetic generation."""
    
    def __init__(self):
        self.cache: Dict[str, Dict] = {}
        self.request_log: List[Dict] = []
    
    def fetch_sequence(self, gene_name: str, species: str = "human") -> Optional[Dict]:
        """Fetch a DNA sequence for a given gene."""
        cache_key = f"{species}:{gene_name}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Try API if available
        if HAS_REQUESTS:
            try:
                url = f"https://rest.ensembl.org/sequence/id/{gene_name}?content-type=application/json"
                response = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if "seq" in data:
                        result = {
                            "gene": gene_name,
                            "species": species,
                            "sequence": data["seq"][:1000],
                            "source": "ensembl",
                            "length": len(data["seq"]),
                            "timestamp": get_timestamp()
                        }
                        self.cache[cache_key] = result
                        return result
            except Exception:
                pass
        
        # Fallback to synthetic
        return self._generate_synthetic_sequence(gene_name, species)
    
    def _generate_synthetic_sequence(self, gene_name: str, species: str) -> Dict:
        """Generate a reproducible synthetic sequence."""
        seed_str = f"{species}:{gene_name}"
        seed_hash = hashlib.sha256(seed_str.encode()).hexdigest()
        bases = "ACGT"
        seq_parts = []
        
        # Process hash in chunks of 2
        for i in range(0, min(len(seed_hash), 200), 2):
            chunk = seed_hash[i:i+2]
            if len(chunk) == 2:
                try:
                    idx = int(chunk, 16) % 4
                    seq_parts.append(bases[idx])
                except ValueError:
                    seq_parts.append('A')
            else:
                chunk = chunk + '0'
                try:
                    idx = int(chunk, 16) % 4
                    seq_parts.append(bases[idx])
                except ValueError:
                    seq_parts.append('A')
        
        # Ensure we have enough sequence
        while len(seq_parts) < 100:
            seq_parts.extend(['A', 'C', 'G', 'T'])
        
        seq = "".join(seq_parts)[:200]
        
        return {
            "gene": gene_name,
            "species": species,
            "sequence": seq,
            "source": "synthetic",
            "length": len(seq),
            "timestamp": get_timestamp(),
            "note": "Synthetic sequence generated from hash seed"
        }
    
    def fetch_genomic_variants(self, gene_name: str) -> List[Dict]:
        """Generate simulated variants."""
        seq_data = self.fetch_sequence(gene_name)
        if not seq_data:
            return []
        
        seq = seq_data["sequence"]
        variants = []
        
        for i in range(min(10, len(seq) // 20)):
            try:
                pos = random.randint(10, len(seq) - 10)
                ref = seq[pos] if pos < len(seq) else 'A'
                alt = random.choice([b for b in "ACGT" if b != ref])
                variants.append({
                    "position": pos,
                    "ref": ref,
                    "alt": alt,
                    "type": "SNP",
                    "gene": gene_name,
                    "source": "simulated",
                    "clinical_significance": random.choice(["Benign", "Likely Benign", "Uncertain", "Likely Pathogenic", "Pathogenic"])
                })
            except Exception:
                continue
        
        return variants
    
    def fetch_methylation_data(self, gene_name: str) -> Dict:
        """Generate simulated methylation data."""
        seq_data = self.fetch_sequence(gene_name)
        if not seq_data:
            return {"methylation_sites": [], "average_methylation": 0.5}
        
        seq = seq_data["sequence"]
        sites = []
        
        for i, base in enumerate(seq):
            if base == "C" and i < len(seq) - 1 and seq[i+1] == "G":
                sites.append({
                    "position": i,
                    "context": "CpG",
                    "methylation_level": random.uniform(0.1, 0.9)
                })
        
        avg_methylation = sum(s["methylation_level"] for s in sites) / max(1, len(sites))
        return {
            "gene": gene_name,
            "methylation_sites": sites[:50],
            "average_methylation": avg_methylation,
            "total_sites": len(sites),
            "source": "simulated"
        }
    
    def fetch_expression_data(self, gene_name: str) -> Dict:
        """Generate simulated expression data."""
        seed = hashlib.sha256(gene_name.encode()).hexdigest()
        base_expr = int(seed[:4], 16) / 65536 * 100 if len(seed) >= 4 else 50
        
        tissues = ["brain", "liver", "heart", "kidney", "muscle", "lung", "skin", "blood"]
        expression = {}
        for t in tissues:
            expression[t] = base_expr * random.uniform(0.5, 1.5)
        
        return {
            "gene": gene_name,
            "expression": expression,
            "primary_tissue": max(expression, key=expression.get) if expression else "unknown",
            "source": "simulated"
        }


# ──────────────────────────────────────────────────────────────
# 5. RESEARCH KNOWLEDGE GRAPH
# ──────────────────────────────────────────────────────────────

class ResearchKnowledgeGraph:
    """Knowledge graph of research papers."""
    
    def __init__(self):
        self.nodes: Dict[str, Dict] = {}
        self.edges: Dict[str, Set[str]] = defaultdict(set)
        self.categories: Set[str] = set()
        self._initialize_base_knowledge()
    
    def _initialize_base_knowledge(self):
        """Initialize with core biological knowledge."""
        base_papers = [
            {
                "id": "paper_001",
                "title": "Central Dogma of Molecular Biology",
                "content": {"key": "DNA → RNA → Protein"},
                "authors": ["Crick F"],
                "category": "molecular_biology",
                "tags": ["central_dogma", "transcription", "translation"]
            },
            {
                "id": "paper_002",
                "title": "Epigenetic Regulation and Gene Expression",
                "content": {"key": "DNA methylation and histone modification"},
                "authors": ["Allis CD", "Jenuwein T"],
                "category": "epigenetics",
                "tags": ["methylation", "histones", "chromatin"]
            },
            {
                "id": "paper_003",
                "title": "CRISPR-Cas9 Genome Editing",
                "content": {"key": "Precise genome modification"},
                "authors": ["Doudna J", "Charpentier E"],
                "category": "gene_editing",
                "tags": ["crispr", "cas9", "genome_editing"]
            },
            {
                "id": "paper_004",
                "title": "DNA Damage and Repair Mechanisms",
                "content": {"key": "PARP, BRCA, and DNA repair"},
                "authors": ["Lindahl T", "Modrich P"],
                "category": "dna_repair",
                "tags": ["damage", "repair", "PARP", "BRCA"]
            }
        ]
        
        for paper in base_papers:
            self.nodes[paper["id"]] = paper
            self.categories.add(paper["category"])
        
        # Add citations
        for from_id, to_id in [("paper_001", "paper_002"), ("paper_002", "paper_003"), ("paper_001", "paper_004")]:
            self.edges[from_id].add(to_id)
            self.edges[to_id].add(from_id)
    
    def add_paper(self, title: str, content: Dict, authors: List[str], category: str, tags: List[str]) -> Dict:
        """Add a paper to the knowledge graph."""
        node_id = deterministic_hash({"title": title, "authors": sorted(authors)})
        if node_id in self.nodes:
            return self.nodes[node_id]
        
        paper = {
            "id": node_id,
            "title": title,
            "content": content,
            "authors": authors,
            "category": category,
            "tags": tags,
            "timestamp": get_timestamp()
        }
        self.nodes[node_id] = paper
        self.categories.add(category)
        return paper
    
    def search_by_tag(self, tag: str) -> List[Dict]:
        return [n for n in self.nodes.values() if tag in n.get("tags", [])]
    
    def search_by_category(self, category: str) -> List[Dict]:
        return [n for n in self.nodes.values() if n.get("category") == category]
    
    def get_related(self, paper_id: str, max_depth: int = 2) -> List[Dict]:
        """Find related papers using graph traversal."""
        if paper_id not in self.nodes:
            return []
        
        visited = set()
        results = []
        queue = [(paper_id, 0)]
        
        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)
            
            node = self.nodes.get(current_id)
            if node and current_id != paper_id:
                results.append(node)
                
                for neighbor in self.edges.get(current_id, set()):
                    if neighbor not in visited:
                        queue.append((neighbor, depth + 1))
        
        return results


# ──────────────────────────────────────────────────────────────
# 6. BIO ENGINEER
# ──────────────────────────────────────────────────────────────

class BioEngineer:
    """Bio-Engineer that learns from DNA data."""
    
    def __init__(self, engineer_id: str = "bio_engineer_001"):
        self.engineer_id = engineer_id
        self.data_provider = DNADataProvider()
        self.knowledge_graph = ResearchKnowledgeGraph()
        self.dna_profiles: Dict[str, Dict] = {}
        self.learned_patterns: Dict[str, Dict] = {}
        self.training_history: List[Dict] = []
        self.twin_engineer = None
    
    def learn_from_dna(self, gene_name: str, species: str = "human") -> Dict:
        """Learn from DNA data for a specific gene."""
        try:
            seq_data = self.data_provider.fetch_sequence(gene_name, species)
            if not seq_data:
                return {"status": "error", "reason": "no_data", "gene": gene_name}
            
            variants = self.data_provider.fetch_genomic_variants(gene_name)
            methylation = self.data_provider.fetch_methylation_data(gene_name)
            expression = self.data_provider.fetch_expression_data(gene_name)
            
            profile_key = f"{species}:{gene_name}"
            profile = {
                "gene": gene_name,
                "species": species,
                "sequence": seq_data["sequence"][:200],
                "sequence_hash": hashlib.sha256(seq_data["sequence"].encode()).hexdigest(),
                "variants": variants,
                "methylation": methylation,
                "expression": expression,
                "learned_at": get_timestamp()
            }
            
            self.dna_profiles[profile_key] = profile
            pattern = self._extract_patterns(profile)
            self.learned_patterns[gene_name] = pattern
            
            self.training_history.append({
                "action": "learn_from_dna",
                "gene": gene_name,
                "species": species,
                "timestamp": get_timestamp()
            })
            
            return {
                "status": "success",
                "gene": gene_name,
                "sequence_length": seq_data["length"],
                "variants_found": len(variants),
                "methylation_sites": len(methylation.get("methylation_sites", [])),
                "pattern_hash": deterministic_hash(pattern)
            }
        except Exception as e:
            return {"status": "error", "reason": str(e), "gene": gene_name}
    
    def _extract_patterns(self, profile: Dict) -> Dict:
        """Extract meaningful patterns from DNA data."""
        variants = profile.get("variants", [])
        methylation = profile.get("methylation", {})
        expression = profile.get("expression", {})
        
        mutation_types = defaultdict(int)
        for v in variants:
            mutation_types[v.get("type", "unknown")] += 1
        
        regulatory_regions = []
        for site in methylation.get("methylation_sites", []):
            if site.get("methylation_level", 0) > 0.8:
                regulatory_regions.append(site)
        
        return {
            "gene": profile.get("gene", "unknown"),
            "mutation_signature": dict(mutation_types),
            "methylation_profile": {
                "avg_methylation": methylation.get("average_methylation", 0.5),
                "high_methylation_sites": len(regulatory_regions)
            },
            "expression_profile": expression.get("expression", {}),
            "primary_tissue": expression.get("primary_tissue", "unknown"),
            "variant_count": len(variants)
        }
    
    def predict_mutations(self, gene_name: str) -> List[Dict]:
        """Predict potential future mutations."""
        profile_key = f"human:{gene_name}"
        profile = self.dna_profiles.get(profile_key)
        if not profile:
            return []
        
        seq = profile.get("sequence", "")
        if not seq:
            return []
        
        predictions = []
        for i in range(min(20, len(seq) - 10)):
            context = seq[i:i+10]
            gc_count = context.count("G") + context.count("C")
            if gc_count > 5:
                predictions.append({
                    "position": i,
                    "context": context,
                    "predicted_type": random.choice(["SNP", "Deletion", "Insertion"]),
                    "confidence": min(0.9, gc_count / 10),
                    "gene": gene_name,
                    "source": "bio_engineer_prediction"
                })
        
        return predictions
    
    def research_related(self, gene_name: str) -> List[Dict]:
        """Find related research papers."""
        results = []
        
        for tag in ["gene", gene_name, "genetics", "mutation"]:
            papers = self.knowledge_graph.search_by_tag(tag)
            for paper in papers:
                if paper["id"] not in [r.get("id") for r in results]:
                    results.append(paper)
        
        for category in ["molecular_biology", "genetics", "epigenetics"]:
            papers = self.knowledge_graph.search_by_category(category)
            for paper in papers[:3]:
                if paper["id"] not in [r.get("id") for r in results]:
                    results.append(paper)
        
        return results[:20]
    
    def synthesize_insight(self, gene_name: str) -> Dict:
        """Synthesize a comprehensive insight about a gene."""
        try:
            profile_key = f"human:{gene_name}"
            profile = self.dna_profiles.get(profile_key)
            if not profile:
                return {"status": "error", "reason": f"Gene '{gene_name}' not learned"}
            
            variants = profile.get("variants", [])
            methylation = profile.get("methylation", {})
            expression = profile.get("expression", {})
            pattern = self.learned_patterns.get(gene_name, {})
            predictions = self.predict_mutations(gene_name)
            research = self.research_related(gene_name)
            
            pathogenic = sum(1 for v in variants if v.get("clinical_significance") in ["Pathogenic", "Likely Pathogenic"])
            
            insight = {
                "gene": gene_name,
                "overview": {
                    "sequence_length": len(profile.get("sequence", "")),
                    "expression_profile": expression.get("primary_tissue", "unknown"),
                    "methylation_level": methylation.get("average_methylation", 0.5)
                },
                "variants": {
                    "total": len(variants),
                    "pathogenic": pathogenic,
                    "types": pattern.get("mutation_signature", {})
                },
                "predictions": {
                    "future_mutations": len(predictions),
                    "hotspots": [p["position"] for p in predictions[:5]]
                },
                "research_connections": {
                    "papers": len(research),
                    "tags": list(set([tag for r in research for tag in r.get("tags", [])]))
                },
                "synthesized_insight": self._generate_insight_text(gene_name, profile, pattern),
                "timestamp": get_timestamp()
            }
            
            return insight
        except Exception as e:
            return {"status": "error", "reason": str(e), "gene": gene_name}
    
    def _generate_insight_text(self, gene_name: str, profile: Dict, pattern: Dict) -> str:
        """Generate human-readable insight text."""
        lines = [
            f"Gene {gene_name} analysis complete.",
            f"Sequence length: {len(profile.get('sequence', ''))} base pairs.",
            f"Expression primary tissue: {pattern.get('primary_tissue', 'unknown')}.",
            f"Average methylation: {pattern.get('methylation_profile', {}).get('avg_methylation', 0.5):.2f}.",
            f"Found {pattern.get('variant_count', 0)} variants.",
            f"Mutation types: {pattern.get('mutation_signature', {})}.",
            "Future mutation predictions available."
        ]
        return " ".join(lines)


# ──────────────────────────────────────────────────────────────
# 7. TWIN ENGINEER
# ──────────────────────────────────────────────────────────────

class TwinEngineer:
    """Twin Engineer that mirrors the Bio-Engineer."""
    
    def __init__(self, twin_id: str = "twin_engineer_001"):
        self.twin_id = twin_id
        self.bio_engineer = None
        self.twin_knowledge: Dict[str, Dict] = {}
        self.memristor_state: List[float] = [0.5, 0.5, 0.5]
        self.balance_metric: float = 1.0
        self.consensus_history: List[Dict] = []
        self.connected_nodes: Set[str] = set()
        self.maxwell_signature = compute_maxwell_signature(twin_id, 0, [0.0, 0.0, 0.0])
    
    def connect_to_bio_engineer(self, bio_engineer: BioEngineer):
        """Connect to a Bio-Engineer."""
        self.bio_engineer = bio_engineer
        bio_engineer.twin_engineer = self
        print(f"[TWIN] Connected to Bio-Engineer {bio_engineer.engineer_id}")
    
    def sync_from_bio_engineer(self) -> Dict:
        """Synchronize from the Bio-Engineer."""
        if not self.bio_engineer:
            return {"status": "error", "reason": "not_connected"}
        
        for gene, profile in self.bio_engineer.dna_profiles.items():
            if gene not in self.twin_knowledge:
                self.twin_knowledge[gene] = {
                    "mirror_of": gene,
                    "profile_hash": deterministic_hash(profile),
                    "synced_at": get_timestamp()
                }
        
        for gene in self.bio_engineer.learned_patterns:
            pattern = self.bio_engineer.learned_patterns.get(gene, {})
            mutation_count = pattern.get("variant_count", 0)
            self.memristor_state[0] += 0.01 * mutation_count / 10
            self.memristor_state[1] -= 0.01 * mutation_count / 10
        
        self.memristor_state = [max(0, min(1, v)) for v in self.memristor_state]
        
        e_energy = sum(self.memristor_state)
        h_energy = 3 - e_energy
        self.balance_metric = e_energy / max(1e-15, h_energy)
        
        return {
            "status": "success",
            "genes_mirrored": len(self.bio_engineer.dna_profiles),
            "balance_metric": self.balance_metric,
            "is_balanced": abs(self.balance_metric - 1.0) < 0.1,
            "timestamp": get_timestamp()
        }
    
    def query_about_gene(self, gene_name: str) -> Dict:
        """Query about a specific gene."""
        if not self.bio_engineer:
            return {"status": "error", "reason": "bio_engineer_not_connected"}
        
        insight = self.bio_engineer.synthesize_insight(gene_name)
        research = self.bio_engineer.research_related(gene_name)
        predictions = self.bio_engineer.predict_mutations(gene_name)
        
        return {
            "gene": gene_name,
            "insight": insight,
            "research": research[:5],
            "predictions": predictions[:5],
            "timestamp": get_timestamp()
        }
    
    def get_50_50_status(self) -> Dict:
        """Get the current 50/50 status."""
        if not self.bio_engineer:
            return {"status": "error", "reason": "not_connected"}
        
        is_balanced = abs(self.balance_metric - 1.0) < 0.1
        
        return {
            "is_balanced": is_balanced,
            "balance_metric": self.balance_metric,
            "memristor_state": self.memristor_state,
            "timestamp": get_timestamp()
        }
    
    def record_consensus(self, event: Dict) -> Dict:
        """Record a consensus event."""
        consensus = {
            "event_id": deterministic_hash(event),
            "event_type": event.get("type", "unknown"),
            "balance_metric": self.balance_metric,
            "timestamp": get_timestamp()
        }
        self.consensus_history.append(consensus)
        return consensus


# ──────────────────────────────────────────────────────────────
# 8. NETWORK NODE
# ──────────────────────────────────────────────────────────────

class NetworkNode:
    """A network node in the mesh."""
    
    def __init__(self, node_id: str, node_type: str = "twin", storage: PersistentStorage = None):
        self.node_id = node_id
        self.node_type = node_type
        self.storage = storage
        self.peers: Set[str] = set()
        self.message_queue: queue.Queue = queue.Queue()
        self.is_active = True
        self.created_at = get_timestamp()
        
        if storage:
            storage.save_node(node_id, {"type": node_type, "created_at": self.created_at})
        
        print(f"🖥️ Node initialized: {node_id} ({node_type})")
    
    def add_peer(self, peer_id: str):
        """Add a peer node."""
        self.peers.add(peer_id)
        print(f"🔗 {self.node_id} connected to {peer_id}")
    
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
        
        return {
            "status": "broadcast",
            "from": self.node_id,
            "peers": list(self.peers),
            "delivered": delivered,
            "message_id": msg["id"]
        }
    
    def receive(self, message: Dict) -> Dict:
        """Receive a message."""
        self.message_queue.put(message)
        return {
            "status": "received",
            "from": message.get("from", "unknown"),
            "message_id": message.get("id", "unknown"),
            "timestamp": get_timestamp()
        }
    
    def get_status(self) -> Dict:
        """Get node status."""
        return {
            "node_id": self.node_id,
            "type": self.node_type,
            "active": self.is_active,
            "peers": list(self.peers),
            "message_count": self.message_queue.qsize(),
            "created_at": self.created_at
        }


# ──────────────────────────────────────────────────────────────
# 9. UNIFIED SYSTEM
# ──────────────────────────────────────────────────────────────

class UnifiedBioTwinSystem:
    """Complete unified system with all components."""
    
    def __init__(self, storage_dir: str = "maxwell_storage"):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🧬 MAXWELL BIO-TWIN COMPLETE SYSTEM" + Color.END)
        print("=" * 70)
        
        # Storage
        print(Color.CYAN + "📁 Initializing storage..." + Color.END)
        self.storage = PersistentStorage(storage_dir)
        
        # Blockchain
        print(Color.CYAN + "⛓️ Initializing blockchain..." + Color.END)
        self.blockchain = NetworkedBlockchain(self.storage)
        
        # Bio-Engineer
        print(Color.CYAN + "🧬 Initializing Bio-Engineer..." + Color.END)
        self.bio_engineer = BioEngineer("bio_engineer_main")
        
        # Twin-Engineer
        print(Color.CYAN + "🔄 Initializing Twin-Engineer..." + Color.END)
        self.twin_engineer = TwinEngineer("twin_engineer_main")
        self.twin_engineer.connect_to_bio_engineer(self.bio_engineer)
        
        # Network Nodes
        print(Color.CYAN + "🌐 Initializing network nodes..." + Color.END)
        self.nodes: Dict[str, NetworkNode] = {}
        self._initialize_nodes()
        
        self.state = {
            "initialized": True,
            "initialized_at": get_timestamp()
        }
        
        print(Color.GREEN + "✅ System initialized successfully" + Color.END)
        print("=" * 70 + "\n")
    
    def _initialize_nodes(self):
        """Initialize network nodes."""
        node_names = ["TWIN_ALPHA", "TWIN_BETA", "TWIN_GAMMA", "TWIN_DELTA"]
        for name in node_names:
            node = NetworkNode(name, "twin", self.storage)
            self.nodes[name] = node
        
        # Connect nodes in a mesh
        for i, name1 in enumerate(node_names):
            for name2 in node_names[i+1:]:
                self.nodes[name1].add_peer(name2)
                self.nodes[name2].add_peer(name1)
    
    def process_dna_sequence(self, gene_name: str, species: str = "human") -> Dict:
        """Process a DNA sequence through the full pipeline."""
        print(f"\n🧬 Processing {species} gene: {gene_name}")
        print("─" * 50)
        
        # 1. Learn from DNA
        learn_result = self.bio_engineer.learn_from_dna(gene_name, species)
        if learn_result.get("status") != "success":
            print(f"   ❌ Failed: {learn_result.get('reason', 'unknown')}")
            return learn_result
        print(f"   ✅ Bio-Engineer learned: {gene_name}")
        
        # 2. Twin sync
        sync_result = self.twin_engineer.sync_from_bio_engineer()
        print(f"   ✅ Twin synced: balance={sync_result.get('balance_metric', 0):.2f}")
        
        # 3. Get insight
        insight = self.bio_engineer.synthesize_insight(gene_name)
        if insight.get("synthesized_insight"):
            print(f"   💡 {insight['synthesized_insight'][:100]}...")
        
        # 4. Record consensus
        consensus = self.twin_engineer.record_consensus({
            "type": "dna_processing",
            "gene": gene_name,
            "species": species
        })
        print(f"   🤝 Consensus: {consensus['event_id'][:16]}...")
        
        # 5. Anchor to blockchain
        tx_result = self.blockchain.add_transaction({
            "type": "dna_processing",
            "gene": gene_name,
            "species": species,
            "balance": self.twin_engineer.balance_metric
        })
        if tx_result.get("status") == "success":
            print(f"   ⛓️ Block: {tx_result.get('block_index', 'pending')}")
        
        # 6. Broadcast to network
        broadcast_result = self._broadcast_event({
            "type": "dna_processing",
            "gene": gene_name,
            "status": "completed"
        })
        print(f"   📡 Broadcast: {broadcast_result.get('status', 'unknown')}")
        
        # 7. Get 50/50 status
        eq_status = self.twin_engineer.get_50_50_status()
        print(f"   ⚖️ 50/50: {'✅ BALANCED' if eq_status['is_balanced'] else '🔄 Adjusting'} ({eq_status['balance_metric']:.2f})")
        
        return {
            "gene": gene_name,
            "learn_result": learn_result,
            "sync_result": sync_result,
            "insight": insight,
            "consensus": consensus,
            "blockchain": tx_result,
            "broadcast": broadcast_result,
            "equilibrium": eq_status
        }
    
    def _broadcast_event(self, event: Dict) -> Dict:
        """Broadcast an event to all network nodes."""
        results = []
        for node_id, node in self.nodes.items():
            result = node.broadcast({"event": event, "source": "system"})
            results.append(result)
        return {"status": "broadcast", "nodes": len(results), "results": results}
    
    def query_system(self, gene_name: str) -> Dict:
        """Query the system about a gene."""
        print(f"\n🔍 Querying: {gene_name}")
        result = self.twin_engineer.query_about_gene(gene_name)
        
        if result.get("insight", {}).get("synthesized_insight"):
            print(f"   💡 {result['insight']['synthesized_insight']}")
        
        if result.get("research"):
            print(f"   📚 Found {len(result['research'])} research papers")
        
        if result.get("predictions"):
            print(f"   🔬 Found {len(result['predictions'])} mutation predictions")
        
        return result
    
    def get_network_status(self) -> Dict:
        """Get the status of all network nodes."""
        return {
            "nodes": {node_id: node.get_status() for node_id, node in self.nodes.items()},
            "total_nodes": len(self.nodes)
        }
    
    def get_system_state(self) -> Dict:
        """Get the complete system state."""
        return {
            "identity": {"id": "CLAREMORE_TWIN_001"},
            "blockchain": self.blockchain.get_stats(),
            "storage": self.storage.get_stats(),
            "network": self.get_network_status(),
            "balance": self.twin_engineer.get_50_50_status(),
            "timestamp": get_timestamp()
        }
    
    def run_demo(self):
        """Run a complete demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 SYSTEM DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # Process genes
        genes = ["BRCA1", "TP53", "EGFR", "MYC", "KRAS"]
        results = []
        
        for gene in genes[:3]:
            result = self.process_dna_sequence(gene)
            results.append(result)
        
        # Query one gene
        print("\n" + "=" * 70)
        print(Color.BOLD + "📊 DETAILED QUERY: BRCA1" + Color.END)
        print("=" * 70)
        query_result = self.query_system("BRCA1")
        
        # Show network status
        print("\n" + "=" * 70)
        print(Color.CYAN + "🌐 NETWORK STATUS" + Color.END)
        print("=" * 70)
        network = self.get_network_status()
        for node_id, status in network["nodes"].items():
            print(f"   🖥️ {node_id}: {status['type']}, peers={len(status['peers'])}, msgs={status['message_count']}")
        
        # Show blockchain stats
        print("\n" + "=" * 70)
        print(Color.CYAN + "⛓️ BLOCKCHAIN STATS" + Color.END)
        print("=" * 70)
        bc_stats = self.blockchain.get_stats()
        print(f"   Chain Length: {bc_stats['chain_length']}")
        print(f"   Difficulty: {bc_stats['difficulty']}")
        print(f"   Peers: {bc_stats['peers']}")
        print(f"   Pending: {bc_stats['pending_transactions']}")
        
        # Show final 50/50 status
        eq_status = self.twin_engineer.get_50_50_status()
        print("\n" + "=" * 70)
        print(Color.BOLD + "⚖️ FINAL 50/50 STATUS" + Color.END)
        print("=" * 70)
        print(f"   Balanced: {'✅' if eq_status['is_balanced'] else '❌'}")
        print(f"   Balance Metric: {eq_status['balance_metric']:.4f}")
        print(f"   Memristor State: {[round(v, 2) for v in eq_status['memristor_state']]}")
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)
        
        return results


# ──────────────────────────────────────────────────────────────
# 10. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = UnifiedBioTwinSystem()
        system.run_demo()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🏥 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - system.process_dna_sequence(gene_name)")
        print("   - system.query_system(gene_name)")
        print("   - system.get_system_state()")
        print("   - system.get_network_status()")
        print("=" * 70 + "\n")
        
        # Interactive loop
        print("💡 Interactive mode. Type 'exit' to quit.\n")
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip()
                if cmd.lower() == "exit":
                    break
                elif cmd.lower().startswith("process "):
                    gene = cmd.split(" ")[1].strip().upper()
                    system.process_dna_sequence(gene)
                elif cmd.lower().startswith("query "):
                    gene = cmd.split(" ")[1].strip().upper()
                    system.query_system(gene)
                elif cmd.lower() == "status":
                    state = system.get_system_state()
                    print(f"   Balance: {state['balance']['balance_metric']:.3f}")
                    print(f"   Chain: {state['blockchain']['chain_length']} blocks")
                    print(f"   Nodes: {state['network']['total_nodes']}")
                elif cmd.lower() == "help":
                    print("   Commands:")
                    print("   process <gene> - Process a DNA sequence")
                    print("   query <gene> - Query about a gene")
                    print("   status - Show system status")
                    print("   exit - Quit")
                else:
                    print("   Unknown command. Type 'help' for available commands.")
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
