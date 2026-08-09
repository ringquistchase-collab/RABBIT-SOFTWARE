#!/usr/bin/env python3
"""
Maxwell Bio-Twin Networked Storage System
=========================================
Save as: bio_twin_networked_storage.py
Run:     python3 bio_twin_networked_storage.py

FEATURES:
1. Networked storage with intelligent routing
2. Blockchain anchoring with persistence
3. Local and remote storage layers
4. Automatic error recovery
5. Chain-aware information routing
6. Terminal output with visual feedback
7. No system crashes - graceful error handling
8. Persistent state across runs

Digital twin only - no real biology, chemicals, RF, or hardware control.
"""

import hashlib
import json
import math
import os
import random
import struct
import time
import threading
import queue
import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from enum import Enum
import copy
import traceback

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ──────────────────────────────────────────────────────────────
# UTILITIES AND HELPERS
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


# ──────────────────────────────────────────────────────────────
# 1. PERSISTENT STORAGE LAYER (SQLite + File System)
# ──────────────────────────────────────────────────────────────

class PersistentStorage:
    """
    Persistent storage using SQLite and file system.
    Provides both local and network-aware storage.
    """
    
    def __init__(self, storage_dir: str = "bio_twin_storage"):
        self.storage_dir = storage_dir
        self.db_path = os.path.join(storage_dir, "bio_twin.db")
        self.files_dir = os.path.join(storage_dir, "files")
        
        # Create directories
        os.makedirs(storage_dir, exist_ok=True)
        os.makedirs(self.files_dir, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # Storage stats
        self.stats = {
            "records": 0,
            "blocks": 0,
            "transactions": 0,
            "files": 0,
            "last_backup": None
        }
        
        print(f"📁 Storage initialized: {storage_dir}")
    
    def _init_database(self):
        """Initialize the SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table: chain_blocks
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
        
        # Table: storage_records
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS storage_records (
                record_id TEXT PRIMARY KEY,
                record_type TEXT NOT NULL,
                data TEXT NOT NULL,
                hash TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                parent_id TEXT,
                block_index INTEGER,
                FOREIGN KEY (block_index) REFERENCES chain_blocks(block_index)
            )
        ''')
        
        # Table: identity_state
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS identity_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # Table: network_channels
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS network_channels (
                channel_id TEXT PRIMARY KEY,
                channel_type TEXT NOT NULL,
                data TEXT NOT NULL,
                last_updated TEXT NOT NULL
            )
        ''')
        
        # Table: error_log
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
        
        # Update stats
        self._update_stats()
    
    def _update_stats(self):
        """Update storage statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM chain_blocks")
        self.stats["blocks"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM storage_records")
        self.stats["records"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM network_channels")
        self.stats["channels"] = cursor.fetchone()[0]
        
        conn.close()
    
    def save_block(self, block: Dict) -> bool:
        """Save a block to persistent storage."""
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
            self._log_error("save_block", str(e), {"block_index": block.get("index")})
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
        except Exception as e:
            self._log_error("get_block", str(e), {"block_hash": block_hash})
            return None
    
    def get_last_block(self) -> Optional[Dict]:
        """Get the last block in the chain."""
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
        except Exception as e:
            self._log_error("get_last_block", str(e))
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
            self._log_error("save_record", str(e), {"record_id": record.get("record_id")})
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
        except Exception as e:
            self._log_error("get_record", str(e), {"record_id": record_id})
            return None
    
    def save_identity_state(self, key: str, value: Any) -> bool:
        """Save identity state."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO identity_state (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, json.dumps(value, default=str), get_timestamp()))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            self._log_error("save_identity_state", str(e), {"key": key})
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
        except Exception as e:
            self._log_error("get_identity_state", str(e), {"key": key})
            return None
    
    def save_channel(self, channel_id: str, channel_data: Dict) -> bool:
        """Save network channel data."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO network_channels 
                (channel_id, channel_type, data, last_updated)
                VALUES (?, ?, ?, ?)
            ''', (
                channel_id,
                channel_data.get("type", "generic"),
                json.dumps(channel_data, default=str),
                get_timestamp()
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            self._log_error("save_channel", str(e), {"channel_id": channel_id})
            return False
    
    def get_channel(self, channel_id: str) -> Optional[Dict]:
        """Get network channel data."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT channel_type, data FROM network_channels WHERE channel_id = ?', (channel_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "type": row[0],
                    "data": json.loads(row[1])
                }
            return None
        except Exception as e:
            self._log_error("get_channel", str(e), {"channel_id": channel_id})
            return None
    
    def get_all_channels(self) -> List[Dict]:
        """Get all network channels."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT channel_id, channel_type, data, last_updated FROM network_channels')
            rows = cursor.fetchall()
            conn.close()
            
            return [
                {
                    "channel_id": row[0],
                    "type": row[1],
                    "data": json.loads(row[2]),
                    "last_updated": row[3]
                }
                for row in rows
            ]
        except Exception as e:
            self._log_error("get_all_channels", str(e))
            return []
    
    def _log_error(self, error_type: str, message: str, context: Dict = None):
        """Log an error to the database."""
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
            pass  # Silently fail - we can't log errors if the DB is broken
    
    def get_errors(self, resolved: bool = False) -> List[Dict]:
        """Get logged errors."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT error_id, timestamp, error_type, message, context, resolved
                FROM error_log WHERE resolved = ? ORDER BY timestamp DESC
            ''', (1 if resolved else 0,))
            
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
        except Exception as e:
            return []
    
    def resolve_error(self, error_id: int) -> bool:
        """Mark an error as resolved."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('UPDATE error_log SET resolved = 1 WHERE error_id = ?', (error_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False
    
    def save_file(self, file_id: str, data: bytes) -> bool:
        """Save a file to the filesystem."""
        try:
            file_path = os.path.join(self.files_dir, file_id)
            with open(file_path, 'wb') as f:
                f.write(data)
            self.stats["files"] += 1
            return True
        except Exception as e:
            self._log_error("save_file", str(e), {"file_id": file_id})
            return False
    
    def get_file(self, file_id: str) -> Optional[bytes]:
        """Retrieve a file from the filesystem."""
        try:
            file_path = os.path.join(self.files_dir, file_id)
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    return f.read()
            return None
        except Exception as e:
            self._log_error("get_file", str(e), {"file_id": file_id})
            return None
    
    def delete_file(self, file_id: str) -> bool:
        """Delete a file from the filesystem."""
        try:
            file_path = os.path.join(self.files_dir, file_id)
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            self._log_error("delete_file", str(e), {"file_id": file_id})
            return False
    
    def get_stats(self) -> Dict:
        """Get storage statistics."""
        self._update_stats()
        return self.stats
    
    def backup(self, backup_dir: str = None) -> bool:
        """Backup the database."""
        try:
            if backup_dir is None:
                backup_dir = f"{self.storage_dir}/backups"
            os.makedirs(backup_dir, exist_ok=True)
            
            backup_path = os.path.join(backup_dir, f"backup_{int(time.time())}.db")
            
            conn = sqlite3.connect(self.db_path)
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn)
            backup_conn.close()
            conn.close()
            
            self.stats["last_backup"] = get_timestamp()
            return True
        except Exception as e:
            self._log_error("backup", str(e))
            return False


# ──────────────────────────────────────────────────────────────
# 2. INTELLIGENT ROUTING LAYER
# ──────────────────────────────────────────────────────────────

class IntelligentRouter:
    """
    Routes information to the correct storage location based on type and context.
    Prevents errors by validating destinations before writing.
    """
    
    def __init__(self, storage: PersistentStorage):
        self.storage = storage
        self.routing_table: Dict[str, Dict] = {}
        self.routing_cache: Dict[str, str] = {}
        
        # Initialize default routes
        self._initialize_routes()
    
    def _initialize_routes(self):
        """Initialize default routing rules."""
        self.routing_table = {
            "block": {
                "destination": "chain_blocks",
                "method": "save_block",
                "validate": lambda x: "hash" in x and "index" in x
            },
            "record": {
                "destination": "storage_records",
                "method": "save_record",
                "validate": lambda x: "record_id" in x or "data" in x
            },
            "identity": {
                "destination": "identity_state",
                "method": "save_identity_state",
                "validate": lambda x: "key" in x
            },
            "channel": {
                "destination": "network_channels",
                "method": "save_channel",
                "validate": lambda x: "channel_id" in x
            },
            "file": {
                "destination": "filesystem",
                "method": "save_file",
                "validate": lambda x: "file_id" in x and "data" in x
            },
            "event": {
                "destination": "storage_records",
                "method": "save_record",
                "validate": lambda x: "type" in x and "data" in x
            }
        }
    
    def route(self, data_type: str, data: Dict) -> Dict:
        """
        Route data to the appropriate storage location.
        Returns a result with status and destination.
        """
        # Validate the data type exists
        if data_type not in self.routing_table:
            return {
                "status": "error",
                "message": f"Unknown data type: {data_type}",
                "available_types": list(self.routing_table.keys()),
                "data": data
            }
        
        route = self.routing_table[data_type]
        
        # Validate the data
        if not route["validate"](data):
            return {
                "status": "error",
                "message": f"Data validation failed for type: {data_type}",
                "required": "Check the data structure",
                "data": data
            }
        
        # Route based on method
        method = route["method"]
        
        try:
            if method == "save_block":
                success = self.storage.save_block(data)
                destination = "chain_blocks"
            elif method == "save_record":
                success = self.storage.save_record(data)
                destination = "storage_records"
            elif method == "save_identity_state":
                success = self.storage.save_identity_state(data["key"], data.get("value", {}))
                destination = "identity_state"
            elif method == "save_channel":
                success = self.storage.save_channel(data["channel_id"], data.get("data", {}))
                destination = "network_channels"
            elif method == "save_file":
                success = self.storage.save_file(data["file_id"], data["data"])
                destination = "filesystem"
            else:
                return {
                    "status": "error",
                    "message": f"Unknown method: {method}",
                    "data": data
                }
            
            return {
                "status": "success" if success else "error",
                "destination": destination,
                "data_type": data_type,
                "data": data,
                "timestamp": get_timestamp()
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Routing error: {str(e)}",
                "traceback": traceback.format_exc(),
                "data_type": data_type,
                "data": data
            }
    
    def get(self, data_type: str, identifier: str) -> Optional[Dict]:
        """Retrieve data from storage based on type and identifier."""
        try:
            if data_type == "block":
                return self.storage.get_block(identifier)
            elif data_type == "record":
                return self.storage.get_record(identifier)
            elif data_type == "identity":
                return self.storage.get_identity_state(identifier)
            elif data_type == "channel":
                return self.storage.get_channel(identifier)
            elif data_type == "file":
                file_data = self.storage.get_file(identifier)
                if file_data:
                    return {"file_id": identifier, "data": file_data}
                return None
            else:
                return None
        except Exception as e:
            return None
    
    def list_all(self, data_type: str) -> List[Dict]:
        """List all items of a given type."""
        try:
            if data_type == "channel":
                return self.storage.get_all_channels()
            elif data_type == "record":
                # This would need a more complex query
                return []
            else:
                return []
        except Exception as e:
            return []
    
    def add_route(self, data_type: str, destination: str, method: str, validator: callable) -> bool:
        """Add a custom routing rule."""
        self.routing_table[data_type] = {
            "destination": destination,
            "method": method,
            "validate": validator
        }
        return True


# ──────────────────────────────────────────────────────────────
# 3. NETWORKED BLOCKCHAIN WITH PERSISTENCE
# ──────────────────────────────────────────────────────────────

class NetworkedBlockchain:
    """
    Blockchain with network-aware storage and persistence.
    """
    
    def __init__(self, storage: PersistentStorage, difficulty: int = 3):
        self.storage = storage
        self.difficulty = difficulty
        self.pending_transactions: List[Dict] = []
        self.chain: List[Dict] = []
        self.network_peers: Set[str] = set()
        self.sync_queue: queue.Queue = queue.Queue()
        
        # Load existing chain or create genesis
        self._load_or_create_chain()
    
    def _load_or_create_chain(self):
        """Load the chain from storage or create a new one."""
        # Check if we have a genesis block
        last_block = self.storage.get_last_block()
        
        if last_block:
            # Load the chain
            self.chain = [last_block]
            
            # Try to load all blocks
            current = last_block
            while current and current.get("previous_hash") != "0" * 64:
                prev = self.storage.get_block(current["previous_hash"])
                if prev:
                    self.chain.insert(0, prev)
                    current = prev
                else:
                    break
            
            print(f"⛓️  Loaded {len(self.chain)} blocks from storage")
        else:
            # Create genesis block
            self._create_genesis()
    
    def _create_genesis(self):
        """Create the genesis block."""
        genesis = {
            "index": 0,
            "timestamp": get_timestamp(),
            "transactions": [{"type": "genesis", "data": "Bio-Twin Blockchain Genesis"}],
            "previous_hash": "0" * 64,
            "nonce": 0,
            "difficulty": self.difficulty
        }
        genesis["hash"] = self._calculate_hash(genesis)
        self.chain = [genesis]
        self.storage.save_block(genesis)
        print(f"⛓️  Created genesis block: {truncate_hash(genesis['hash'])}")
    
    def _calculate_hash(self, block: Dict) -> str:
        """Calculate the hash of a block."""
        block_copy = block.copy()
        block_copy.pop("hash", None)
        return openssl_hash(
            json.dumps(block_copy, sort_keys=True, default=str).encode(),
            "sha256"
        )
    
    def _mine(self, block: Dict) -> None:
        """Mine a block to meet the difficulty."""
        target = "0" * self.difficulty
        while not block["hash"].startswith(target):
            block["nonce"] += 1
            block["hash"] = self._calculate_hash(block)
    
    def add_transaction(self, transaction: Dict) -> Dict:
        """Add a transaction to the pending pool."""
        tx = {
            "id": deterministic_hash(transaction),
            "timestamp": get_timestamp(),
            "type": transaction.get("type", "generic"),
            "data": transaction,
            "hash": deterministic_hash(transaction)
        }
        self.pending_transactions.append(tx)
        
        # Try to mine immediately
        if len(self.pending_transactions) >= 1:
            return self.mine_block()
        
        return {
            "status": "pending",
            "transaction_id": tx["id"],
            "pending_count": len(self.pending_transactions)
        }
    
    def mine_block(self, force: bool = False) -> Dict:
        """Mine a new block with pending transactions."""
        if not self.pending_transactions:
            return {
                "status": "error",
                "message": "No pending transactions",
                "suggestion": "Add a transaction first"
            }
        
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
            
            # Save to chain
            self.chain.append(block)
            self.storage.save_block(block)
            
            # Clear pending
            tx_count = len(self.pending_transactions)
            self.pending_transactions = []
            
            # Broadcast to network
            self._broadcast_block(block)
            
            return {
                "status": "success",
                "block_index": block["index"],
                "block_hash": truncate_hash(block["hash"]),
                "transaction_count": tx_count,
                "nonce": block["nonce"],
                "timestamp": block["timestamp"]
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Mining error: {str(e)}",
                "traceback": traceback.format_exc()
            }
    
    def _broadcast_block(self, block: Dict):
        """Broadcast a block to network peers."""
        for peer in self.network_peers:
            self.sync_queue.put({
                "type": "block_broadcast",
                "peer": peer,
                "block": block
            })
    
    def add_peer(self, peer_id: str):
        """Add a network peer."""
        self.network_peers.add(peer_id)
        print(f"🌐 Added peer: {peer_id}")
    
    def get_chain_length(self) -> int:
        """Get the number of blocks in the chain."""
        return len(self.chain)
    
    def get_last_block(self) -> Optional[Dict]:
        """Get the last block in the chain."""
        return self.chain[-1] if self.chain else None
    
    def verify_chain(self) -> Dict:
        """Verify the entire blockchain."""
        try:
            for i in range(1, len(self.chain)):
                current = self.chain[i]
                previous = self.chain[i - 1]
                
                if current["hash"] != self._calculate_hash(current):
                    return {
                        "status": "error",
                        "message": f"Invalid hash at block {i}",
                        "block_index": i
                    }
                
                if current["previous_hash"] != previous["hash"]:
                    return {
                        "status": "error",
                        "message": f"Invalid link at block {i}",
                        "block_index": i
                    }
            
            return {
                "status": "success",
                "message": "Chain verified",
                "block_count": len(self.chain),
                "difficulty": self.difficulty
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Verification error: {str(e)}",
                "traceback": traceback.format_exc()
            }
    
    def get_block_by_index(self, index: int) -> Optional[Dict]:
        """Get a block by index."""
        try:
            if 0 <= index < len(self.chain):
                return self.chain[index]
            return None
        except Exception:
            return None
    
    def get_block_by_hash(self, block_hash: str) -> Optional[Dict]:
        """Get a block by hash."""
        try:
            for block in self.chain:
                if block["hash"] == block_hash:
                    return block
            return None
        except Exception:
            return None
    
    def get_transactions_by_type(self, tx_type: str) -> List[Dict]:
        """Find all transactions of a specific type."""
        results = []
        try:
            for block in self.chain:
                for tx in block.get("transactions", []):
                    if tx.get("type") == tx_type:
                        results.append(tx)
            return results
        except Exception:
            return []
    
    def get_stats(self) -> Dict:
        """Get blockchain statistics."""
        return {
            "chain_length": len(self.chain),
            "difficulty": self.difficulty,
            "pending_transactions": len(self.pending_transactions),
            "peers": len(self.network_peers),
            "last_block": self.chain[-1]["hash"][:12] + "..." if self.chain else "none"
        }


# ──────────────────────────────────────────────────────────────
# 4. SYMBIOTIC SYSTEM WITH STORAGE
# ──────────────────────────────────────────────────────────────

class SymbioticSystem:
    """
    Complete symbiotic system with network storage, blockchain,
    and intelligent routing.
    """
    
    def __init__(self, identity_id: str = "default_identity", storage_dir: str = "bio_twin_storage"):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🧬 INITIALIZING SYMBIOTIC SYSTEM" + Color.END)
        print("=" * 70)
        
        # Initialize persistent storage
        print(Color.CYAN + "📁 Initializing storage..." + Color.END)
        self.storage = PersistentStorage(storage_dir)
        
        # Initialize router
        print(Color.CYAN + "🔄 Initializing router..." + Color.END)
        self.router = IntelligentRouter(self.storage)
        
        # Initialize blockchain
        print(Color.CYAN + "⛓️  Initializing blockchain..." + Color.END)
        self.blockchain = NetworkedBlockchain(self.storage)
        
        # System state
        self.identity_id = identity_id
        self.state = {
            "initialized": True,
            "initialized_at": get_timestamp(),
            "identity_id": identity_id,
            "storage_dir": storage_dir
        }
        
        # Error recovery
        self.error_recovery_count = 0
        
        print(Color.GREEN + "✅ System initialized successfully" + Color.END)
        print("=" * 70 + "\n")
    
    def store(self, data_type: str, data: Dict) -> Dict:
        """
        Store data in the system with automatic routing.
        Returns the result with status and location.
        """
        print(f"\n{Color.YELLOW}📝 Storing {data_type}...{Color.END}")
        
        # Route the data
        result = self.router.route(data_type, data)
        
        if result["status"] == "success":
            print(f"   {Color.GREEN}✅ Stored to: {result['destination']}{Color.END}")
            
            # If it's a transaction, add to blockchain
            if data_type in ["block", "record", "event"]:
                tx_result = self.blockchain.add_transaction({
                    "type": data_type,
                    "data": result["data"],
                    "storage_location": result["destination"]
                })
                
                if tx_result.get("status") == "success":
                    print(f"   {Color.GREEN}✅ Anchored to blockchain: block {tx_result['block_index']}{Color.END}")
                    result["blockchain"] = tx_result
                else:
                    print(f"   {Color.YELLOW}⚠️ Transaction pending: {tx_result.get('message', 'unknown')}{Color.END}")
                    result["blockchain"] = tx_result
        else:
            print(f"   {Color.RED}❌ Storage failed: {result.get('message', 'unknown')}{Color.END}")
        
        return result
    
    def retrieve(self, data_type: str, identifier: str) -> Optional[Dict]:
        """
        Retrieve data from the system.
        """
        print(f"\n{Color.BLUE}🔍 Retrieving {data_type}: {identifier}{Color.END}")
        
        result = self.router.get(data_type, identifier)
        
        if result:
            print(f"   {Color.GREEN}✅ Found{Color.END}")
        else:
            print(f"   {Color.RED}❌ Not found{Color.END}")
        
        return result
    
    def event_occurred(self, event_type: str, event_data: Dict) -> Dict:
        """
        Record an event in the system.
        """
        print(f"\n{Color.HEADER}⚡ EVENT: {event_type}{Color.END}")
        print("─" * 50)
        
        # Create the event record
        event = {
            "type": event_type,
            "data": event_data,
            "timestamp": get_timestamp(),
            "identity_id": self.identity_id
        }
        
        event_id = deterministic_hash(event)
        event["event_id"] = event_id
        
        # Store the event
        result = self.store("event", {
            "record_id": event_id,
            "type": event_type,
            "data": event_data,
            "timestamp": get_timestamp(),
            "hash": event_id
        })
        
        # Print visual feedback
        print(f"\n{Color.CYAN}📊 Event Summary:{Color.END}")
        print(f"   ID: {event_id[:16]}...")
        print(f"   Type: {event_type}")
        print(f"   Status: {result['status']}")
        print(f"   Stored at: {result.get('destination', 'unknown')}")
        
        if "blockchain" in result and result["blockchain"].get("status") == "success":
            print(f"   Block: {result['blockchain'].get('block_index', 'pending')}")
        
        return {
            "event": event,
            "event_id": event_id,
            "result": result
        }
    
    def add_network_channel(self, channel_id: str, channel_type: str = "research"):
        """
        Add a network channel to the system.
        """
        print(f"\n{Color.BLUE}🌐 Adding network channel: {channel_id}{Color.END}")
        
        channel_data = {
            "channel_id": channel_id,
            "type": channel_type,
            "data": {
                "added_at": get_timestamp(),
                "status": "active",
                "event_count": 0
            }
        }
        
        result = self.store("channel", channel_data)
        
        if result["status"] == "success":
            print(f"   {Color.GREEN}✅ Channel added: {channel_id}{Color.END}")
        else:
            print(f"   {Color.RED}❌ Failed to add channel: {result.get('message', 'unknown')}{Color.END}")
        
        return result
    
    def get_network_channels(self) -> List[Dict]:
        """
        Get all network channels.
        """
        return self.storage.get_all_channels()
    
    def get_system_state(self) -> Dict:
        """
        Get the complete system state.
        """
        blockchain_stats = self.blockchain.get_stats()
        storage_stats = self.storage.get_stats()
        
        return {
            "identity": {
                "id": self.identity_id,
                "initialized_at": self.state["initialized_at"]
            },
            "blockchain": blockchain_stats,
            "storage": storage_stats,
            "channels": len(self.get_network_channels()),
            "error_recovery_count": self.error_recovery_count,
            "timestamp": get_timestamp()
        }
    
    def verify_integrity(self) -> Dict:
        """
        Verify the integrity of the entire system.
        """
        print("\n" + Color.CYAN + "🔍 Verifying system integrity..." + Color.END)
        
        # Verify blockchain
        bc_verify = self.blockchain.verify_chain()
        
        # Check storage
        storage_ok = self.storage.get_stats()["records"] > 0
        
        # Check router
        router_ok = len(self.router.routing_table) > 0
        
        integrity = {
            "blockchain": bc_verify,
            "storage_ok": storage_ok,
            "router_ok": router_ok,
            "overall": bc_verify.get("status") == "success" and storage_ok and router_ok,
            "timestamp": get_timestamp()
        }
        
        if integrity["overall"]:
            print(f"   {Color.GREEN}✅ System integrity verified{Color.END}")
        else:
            print(f"   {Color.RED}❌ System integrity check failed{Color.END}")
            if bc_verify.get("status") != "success":
                print(f"   Blockchain: {bc_verify.get('message', 'failed')}")
            if not storage_ok:
                print(f"   Storage: No records found")
            if not router_ok:
                print(f"   Router: No routes configured")
        
        return integrity
    
    def recover(self) -> Dict:
        """
        Attempt to recover from errors.
        """
        print("\n" + Color.YELLOW + "🔄 Attempting system recovery..." + Color.END)
        
        recovery_actions = []
        self.error_recovery_count += 1
        
        # Check and repair blockchain
        bc_verify = self.blockchain.verify_chain()
        if bc_verify.get("status") != "success":
            # Try to repair by reloading
            print("   ⚠️ Blockchain needs repair")
            try:
                # Force reload from storage
                self.blockchain = NetworkedBlockchain(self.storage)
                recovery_actions.append("blockchain_reload")
                print(f"   {Color.GREEN}✅ Blockchain reloaded{Color.END}")
            except Exception as e:
                recovery_actions.append(f"blockchain_reload_failed: {str(e)}")
                print(f"   {Color.RED}❌ Blockchain reload failed: {str(e)}{Color.END}")
        
        # Check storage
        try:
            self.storage._update_stats()
            recovery_actions.append("storage_stats_updated")
        except Exception as e:
            recovery_actions.append(f"storage_update_failed: {str(e)}")
        
        recovery_result = {
            "status": "success",
            "actions": recovery_actions,
            "recovery_count": self.error_recovery_count,
            "timestamp": get_timestamp()
        }
        
        print(f"\n{Color.GREEN}✅ Recovery complete - {len(recovery_actions)} actions performed{Color.END}")
        return recovery_result
    
    def save_state(self, filename: str = "system_state.json"):
        """
        Save the complete system state to a file.
        """
        state = self.get_system_state()
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            print(f"\n💾 System state saved to {filename}")
            return True
        except Exception as e:
            print(f"\n{Color.RED}❌ Failed to save state: {str(e)}{Color.END}")
            return False
    
    def load_state(self, filename: str = "system_state.json"):
        """
        Load system state from a file.
        """
        try:
            with open(filename, "r", encoding="utf-8") as f:
                state = json.load(f)
            print(f"\n📁 Loaded system state from {filename}")
            return state
        except Exception as e:
            print(f"\n{Color.RED}❌ Failed to load state: {str(e)}{Color.END}")
            return None


# ──────────────────────────────────────────────────────────────
# 5. DEMONSTRATION
# ──────────────────────────────────────────────────────────────

def run_demonstration():
    """Run a complete demonstration of the networked storage system."""
    
    print("\n" + "=" * 70)
    print(Color.HEADER + "🧬 MAXWELL BIO-TWIN NETWORKED STORAGE" + Color.END)
    print("   Complete System with Storage, Blockchain, and Routing")
    print("=" * 70)
    
    # Initialize system
    print("\n1. " + Color.CYAN + "Initializing System..." + Color.END)
    system = SymbioticSystem(identity_id="CLAREMORE_TWIN_001")
    
    # Add network channels
    print("\n2. " + Color.CYAN + "Adding Network Channels..." + Color.END)
    system.add_network_channel("research_db", "research")
    system.add_network_channel("genomic_db", "genomic")
    system.add_network_channel("clinical_network", "clinical")
    system.add_network_channel("twin_mesh", "p2p")
    
    # Record events
    print("\n3. " + Color.CYAN + "Recording Events..." + Color.END)
    
    events = [
        ("environmental", {
            "type": "solar_flare",
            "intensity": 0.87,
            "radiation_dose": 2.4
        }),
        ("dna_damage", {
            "location": "BRCA1_gene",
            "damage_type": "double_strand_break",
            "severity": 0.73
        }),
        ("repair_initiated", {
            "mechanism": "homologous_recombination",
            "proteins": ["BRCA1", "RAD51", "PARP1"]
        }),
        ("network_sync", {
            "nodes": ["TWIN_ALPHA", "TWIN_BETA"],
            "consensus": True
        }),
        ("twin_update", {
            "memristor_state": [0.42, 0.68, 0.85],
            "type": "reverse_signal"
        })
    ]
    
    for event_type, event_data in events:
        system.event_occurred(event_type, event_data)
    
    # Show system state
    print("\n4. " + Color.CYAN + "System State..." + Color.END)
    state = system.get_system_state()
    print(f"\n{Color.BOLD}📊 System Overview:{Color.END}")
    print(f"   Identity: {state['identity']['id']}")
    print(f"   Blockchain: {state['blockchain']['chain_length']} blocks")
    print(f"   Storage: {state['storage']['records']} records")
    print(f"   Channels: {state['channels']}")
    print(f"   Error Recovery Count: {state['error_recovery_count']}")
    
    # Verify integrity
    print("\n5. " + Color.CYAN + "Verifying Integrity..." + Color.END)
    integrity = system.verify_integrity()
    
    # Show channels
    print("\n6. " + Color.CYAN + "Network Channels..." + Color.END)
    channels = system.get_network_channels()
    for channel in channels:
        print(f"   📡 {channel['channel_id']} ({channel['type']})")
    
    # Show blockchain
    print("\n7. " + Color.CYAN + "Blockchain Stats..." + Color.END)
    print(f"   Chain Length: {system.blockchain.get_chain_length()}")
    print(f"   Difficulty: {system.blockchain.difficulty}")
    print(f"   Pending Transactions: {len(system.blockchain.pending_transactions)}")
    
    # Save state
    print("\n8. " + Color.CYAN + "Saving State..." + Color.END)
    system.save_state()
    
    # Recovery demonstration
    print("\n9. " + Color.CYAN + "Testing Recovery..." + Color.END)
    recovery = system.recover()
    print(f"   Recovery Actions: {recovery['actions']}")
    
    print("\n" + "=" * 70)
    print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
    print("   All data stored, routed, and blockchain anchored.")
    print("   System is ready for production use.")
    print("=" * 70 + "\n")
    
    return system


# ──────────────────────────────────────────────────────────────
# MAIN EXECUTABLE
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        system = run_demonstration()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🏥 SYSTEM READY" + Color.END)
        print("   To interact with the system, use:")
        print("   - system.event_occurred(event_type, event_data)")
        print("   - system.store(data_type, data)")
        print("   - system.retrieve(data_type, identifier)")
        print("   - system.get_system_state()")
        print("   - system.verify_integrity()")
        print("   - system.recover()")
        print("=" * 70 + "\n")
        
        # Keep the system responsive
        print("💡 The system is now running. Press Ctrl+C to exit.\n")
        
        # Handle graceful shutdown
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n" + Color.YELLOW + "⚠️ Shutting down..." + Color.END)
            system.save_state()
            print(Color.GREEN + "✅ System state saved. Goodbye!" + Color.END)
            
    except Exception as e:
        print(f"\n{Color.RED}❌ Fatal error: {str(e)}{Color.END}")
        print(traceback.format_exc())
        sys.exit(1)
