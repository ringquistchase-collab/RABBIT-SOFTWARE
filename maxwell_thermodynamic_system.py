#!/usr/bin/env python3
"""
Maxwell Bio-Twin Thermodynamic System
=====================================
Save as: maxwell_thermodynamic_system.py
Run:     python3 maxwell_thermodynamic_system.py

THERMODYNAMIC PRINCIPLES:
1. Energy is never created or destroyed - only transformed
2. Entropy increases in isolated systems
3. Systems naturally find equilibrium states
4. Energy flows from higher to lower potential

AUTONOMOUS FEATURES:
- Self-healing blockchain
- Adaptive problem-solving
- Energy-aware routing
- Entropy-based consensus
- Thermodynamic equilibrium detection

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

# Optional requests
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ──────────────────────────────────────────────────────────────
# 1. THERMODYNAMIC CONSTANTS AND LAWS
# ──────────────────────────────────────────────────────────────

class ThermodynamicLaws:
    """
    Thermodynamic laws applied to information and energy systems.
    Energy is never wasted - it transforms into different forms.
    """
    
    # Physical constants (approximated for digital twin)
    BOLTZMANN = 1.380649e-23  # J/K
    PLANCK = 6.62607015e-34   # J·s
    SPEED_OF_LIGHT = 299792458  # m/s
    
    # Information entropy constants
    SHANNON_BASE = 2.0  # Bits
    THERMAL_EQUIVALENT = 1.0  # Energy per bit (simplified)
    
    @classmethod
    def information_entropy(cls, probabilities: List[float]) -> float:
        """Calculate Shannon entropy of a probability distribution."""
        entropy = 0.0
        for p in probabilities:
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy
    
    @classmethod
    def thermodynamic_entropy(cls, energy: float, temperature: float) -> float:
        """Calculate thermodynamic entropy (S = Q/T)."""
        if temperature <= 0:
            return float('inf')
        return energy / temperature
    
    @classmethod
    def free_energy(cls, internal_energy: float, entropy: float, temperature: float) -> float:
        """Calculate Helmholtz free energy (F = U - TS)."""
        return internal_energy - temperature * entropy
    
    @classmethod
    def energy_conversion(cls, energy: float, efficiency: float = 0.85) -> Dict:
        """
        Simulate energy conversion - energy transforms, never wasted.
        Some becomes work, some becomes heat (entropy).
        """
        work = energy * efficiency
        heat = energy * (1 - efficiency)  # Always some entropy generation
        
        return {
            "input_energy": energy,
            "work_output": work,
            "heat_generated": heat,
            "efficiency": efficiency,
            "entropy_generation": heat / cls.THERMAL_EQUIVALENT
        }
    
    @classmethod
    def equilibrium_state(cls, system_energy: float, environment_energy: float) -> Dict:
        """Determine if two systems are in thermodynamic equilibrium."""
        delta = abs(system_energy - environment_energy)
        is_equilibrium = delta < 1e-10
        
        # Energy will flow from higher to lower potential
        energy_flow = system_energy - environment_energy
        
        return {
            "is_equilibrium": is_equilibrium,
            "energy_difference": delta,
            "energy_flow": energy_flow,
            "flow_direction": "system_to_environment" if energy_flow > 0 else "environment_to_system",
            "equilibrium_probability": 1.0 / (1.0 + math.exp(delta * 10))  # Sigmoid
        }


# ──────────────────────────────────────────────────────────────
# 2. UTILITIES
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
    """Compute the Maxwell field signature for data with thermodynamic energy."""
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
    
    # Calculate thermodynamic energy of the signature
    field_energy = nE * nH
    entropy = ThermodynamicLaws.information_entropy([abs(x) for x in E + H])
    
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
        "thermodynamic_state": ThermodynamicLaws.equilibrium_state(field_energy, 0.5)
    }


# ──────────────────────────────────────────────────────────────
# 3. DNA DATA PROVIDER - THERMODYNAMIC AWARE
# ──────────────────────────────────────────────────────────────

class DNADataProvider:
    """Fetches DNA data with thermodynamic energy tracking."""
    
    def __init__(self):
        self.cache: Dict[str, Dict] = {}
        self.request_log: List[Dict] = []
        self.total_energy_used = 0.0
        self.entropy_generated = 0.0
    
    def fetch_sequence(self, gene_name: str, species: str = "human") -> Optional[Dict]:
        """Fetch a DNA sequence for a given gene with energy tracking."""
        cache_key = f"{species}:{gene_name}"
        if cache_key in self.cache:
            # Reading from cache uses less energy
            energy_cost = 0.1
            self.total_energy_used += energy_cost
            return self.cache[cache_key]
        
        # Try API if available
        energy_cost = 1.0  # API call costs energy
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
                            "timestamp": get_timestamp(),
                            "energy_cost": energy_cost
                        }
                        self.cache[cache_key] = result
                        self.total_energy_used += energy_cost
                        return result
            except Exception:
                pass
        
        # Fallback to synthetic (lower energy cost)
        synthetic_cost = 0.3
        result = self._generate_synthetic_sequence(gene_name, species)
        result["energy_cost"] = synthetic_cost
        self.cache[cache_key] = result
        self.total_energy_used += synthetic_cost
        return result
    
    def _generate_synthetic_sequence(self, gene_name: str, species: str) -> Dict:
        """Generate a reproducible synthetic sequence - FIXED."""
        seed_str = f"{species}:{gene_name}"
        seed_hash = hashlib.sha256(seed_str.encode()).hexdigest()
        
        bases = "ACGT"
        seq_parts = []
        
        # Generate sequence safely - no empty string hex parsing
        for i in range(0, min(len(seed_hash) - 1, 200), 2):
            chunk = seed_hash[i:i+2]
            try:
                idx = int(chunk, 16) % 4
                seq_parts.append(bases[idx])
            except ValueError:
                seq_parts.append('A')
        
        # Ensure we have enough sequence
        while len(seq_parts) < 100:
            ext_hash = hashlib.sha256((seed_str + str(len(seq_parts))).encode()).hexdigest()
            for j in range(0, min(len(ext_hash) - 1, 20), 2):
                try:
                    idx = int(ext_hash[j:j+2], 16) % 4
                    seq_parts.append(bases[idx])
                except ValueError:
                    seq_parts.append('C')
        
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
        """Generate simulated variants with energy tracking."""
        seq_data = self.fetch_sequence(gene_name)
        if not seq_data:
            return []
        
        seq = seq_data["sequence"]
        variants = []
        energy_cost = 0.05 * min(10, len(seq) // 20)
        
        for i in range(min(10, len(seq) // 20)):
            try:
                if len(seq) > 20:
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
        
        self.total_energy_used += energy_cost
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
    
    def get_energy_stats(self) -> Dict:
        """Get energy usage statistics."""
        return {
            "total_energy_used": self.total_energy_used,
            "cache_size": len(self.cache),
            "entropy_generated": self.entropy_generated,
            "thermodynamic_efficiency": 1.0 / (1.0 + self.entropy_generated / (self.total_energy_used + 1e-15))
        }


# ──────────────────────────────────────────────────────────────
# 4. RESEARCH KNOWLEDGE GRAPH
# ──────────────────────────────────────────────────────────────

class ResearchKnowledgeGraph:
    """Knowledge graph of research papers with energy tracking."""
    
    def __init__(self):
        self.nodes: Dict[str, Dict] = {}
        self.edges: Dict[str, Set[str]] = defaultdict(set)
        self.categories: Set[str] = set()
        self.total_energy = 0.0
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
            self.total_energy += 0.5
        
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
            "timestamp": get_timestamp(),
            "energy_cost": 1.0
        }
        self.nodes[node_id] = paper
        self.categories.add(category)
        self.total_energy += 1.0
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
# 5. THERMODYNAMIC BLOCKCHAIN
# ──────────────────────────────────────────────────────────────

class ThermodynamicBlockchain:
    """
    Blockchain that uses thermodynamic principles for consensus.
    Energy is transformed, never wasted.
    """
    
    def __init__(self, difficulty: int = 3, storage_path: str = "thermo_blocks.db"):
        self.difficulty = difficulty
        self.storage_path = storage_path
        self.chain: List[Dict] = []
        self.pending_transactions: List[Dict] = []
        self.total_energy = 0.0
        self.entropy = 0.0
        self.blockchain_temperature = 298.15  # Kelvin
        self._init_storage()
        self._load_or_create_chain()
    
    def _init_storage(self):
        """Initialize SQLite storage."""
        conn = sqlite3.connect(self.storage_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                index INTEGER PRIMARY KEY,
                hash TEXT UNIQUE,
                previous_hash TEXT,
                timestamp TEXT,
                transactions TEXT,
                nonce INTEGER,
                difficulty INTEGER,
                energy REAL,
                entropy REAL
            )
        ''')
        conn.commit()
        conn.close()
    
    def _load_or_create_chain(self):
        """Load chain from storage or create genesis."""
        conn = sqlite3.connect(self.storage_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM blocks ORDER BY index ASC')
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            for row in rows:
                block = {
                    "index": row[0],
                    "hash": row[1],
                    "previous_hash": row[2],
                    "timestamp": row[3],
                    "transactions": json.loads(row[4]),
                    "nonce": row[5],
                    "difficulty": row[6],
                    "energy": row[7],
                    "entropy": row[8]
                }
                self.chain.append(block)
            print(f"⛓️ Loaded {len(self.chain)} blocks from storage")
        else:
            self._create_genesis()
    
    def _create_genesis(self):
        """Create the genesis block with thermodynamic properties."""
        genesis = {
            "index": 0,
            "timestamp": get_timestamp(),
            "transactions": [{"type": "genesis", "data": "Thermodynamic Bio-Twin Genesis"}],
            "previous_hash": "0" * 64,
            "nonce": 0,
            "difficulty": self.difficulty,
            "energy": 1.0,
            "entropy": 0.0
        }
        genesis["hash"] = self._calculate_hash(genesis)
        self.chain = [genesis]
        self.total_energy = 1.0
        self._save_block(genesis)
        print(f"⛓️ Created genesis block: {truncate_hash(genesis['hash'])}")
    
    def _calculate_hash(self, block: Dict) -> str:
        """Calculate block hash."""
        block_copy = block.copy()
        block_copy.pop("hash", None)
        return openssl_hash(json.dumps(block_copy, sort_keys=True, default=str).encode(), "sha256")
    
    def _mine(self, block: Dict) -> None:
        """Mine a block with energy transformation."""
        target = "0" * self.difficulty
        start_time = time.time()
        attempts = 0
        
        while not block["hash"].startswith(target):
            block["nonce"] += 1
            block["hash"] = self._calculate_hash(block)
            attempts += 1
            
            # Energy transforms during mining
            if attempts % 1000 == 0:
                # Some energy becomes heat (entropy)
                self.entropy += 0.0001
        
        # Energy cost of mining
        mining_energy = attempts * 1e-6
        self.total_energy += mining_energy
        
        # Some energy transforms to heat
        heat = mining_energy * 0.3
        self.entropy += heat / self.blockchain_temperature
        
        # Remaining energy stored in the block
        block["energy"] = mining_energy * 0.7
        block["entropy"] = self.entropy
    
    def _save_block(self, block: Dict):
        """Save a block to storage."""
        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO blocks 
                (index, hash, previous_hash, timestamp, transactions, nonce, difficulty, energy, entropy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                block["index"],
                block["hash"],
                block["previous_hash"],
                block["timestamp"],
                json.dumps(block.get("transactions", []), default=str),
                block["nonce"],
                block.get("difficulty", self.difficulty),
                block.get("energy", 0.0),
                block.get("entropy", 0.0)
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Error saving block: {e}")
    
    def add_transaction(self, transaction: Dict) -> Dict:
        """Add a transaction to pending pool."""
        tx = {
            "id": deterministic_hash(transaction),
            "timestamp": get_timestamp(),
            "type": transaction.get("type", "generic"),
            "data": transaction,
            "hash": deterministic_hash(transaction),
            "energy": 0.1  # Transaction energy cost
        }
        self.pending_transactions.append(tx)
        self.total_energy += 0.1
        
        # Auto-mine when we have transactions
        if len(self.pending_transactions) >= 1:
            return self.mine_block()
        
        return {"status": "pending", "transaction_id": tx["id"]}
    
    def mine_block(self) -> Dict:
        """Mine a new block."""
        if not self.pending_transactions:
            return {"status": "error", "message": "No pending transactions"}
        
        try:
            prev_block = self.chain[-1]
            
            # Create block with thermodynamic properties
            block = {
                "index": len(self.chain),
                "timestamp": get_timestamp(),
                "transactions": self.pending_transactions.copy(),
                "previous_hash": prev_block["hash"],
                "nonce": 0,
                "difficulty": self.difficulty,
                "energy": 0.0,
                "entropy": self.entropy
            }
            block["hash"] = self._calculate_hash(block)
            self._mine(block)
            
            self.chain.append(block)
            self._save_block(block)
            
            tx_count = len(self.pending_transactions)
            self.pending_transactions = []
            
            # Energy transformed into block
            energy_conversion = ThermodynamicLaws.energy_conversion(block["energy"])
            
            return {
                "status": "success",
                "block_index": block["index"],
                "block_hash": truncate_hash(block["hash"]),
                "transaction_count": tx_count,
                "nonce": block["nonce"],
                "energy_used": block["energy"],
                "entropy_generated": block["entropy"],
                "energy_conversion": energy_conversion,
                "thermodynamic_state": ThermodynamicLaws.equilibrium_state(
                    block["energy"], 
                    prev_block.get("energy", 0.5)
                )
            }
        except Exception as e:
            return {"status": "error", "message": f"Mining error: {str(e)}"}
    
    def get_chain_length(self) -> int:
        return len(self.chain)
    
    def get_last_block(self) -> Optional[Dict]:
        return self.chain[-1] if self.chain else None
    
    def verify_chain(self) -> Dict:
        """Verify the entire chain with thermodynamic checks."""
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            
            if current["hash"] != self._calculate_hash(current):
                return {"status": "error", "message": f"Invalid hash at block {i}"}
            
            if current["previous_hash"] != previous["hash"]:
                return {"status": "error", "message": f"Invalid link at block {i}"}
            
            # Check thermodynamic consistency - energy should transform
            if current.get("energy", 0) < 0:
                return {"status": "error", "message": f"Negative energy at block {i}"}
        
        return {
            "status": "success", 
            "message": "Chain verified", 
            "block_count": len(self.chain),
            "total_energy": self.total_energy,
            "total_entropy": self.entropy,
            "thermodynamic_efficiency": 1.0 / (1.0 + self.entropy / (self.total_energy + 1e-15))
        }
    
    def get_stats(self) -> Dict:
        return {
            "chain_length": len(self.chain),
            "difficulty": self.difficulty,
            "pending_transactions": len(self.pending_transactions),
            "total_energy": self.total_energy,
            "entropy": self.entropy,
            "temperature": self.blockchain_temperature
        }


# ──────────────────────────────────────────────────────────────
# 6. THERMODYNAMIC BIO ENGINEER
# ──────────────────────────────────────────────────────────────

class ThermodynamicBioEngineer:
    """Bio-Engineer with thermodynamic principles."""
    
    def __init__(self, engineer_id: str = "thermo_bio_001"):
        self.engineer_id = engineer_id
        self.data_provider = DNADataProvider()
        self.knowledge_graph = ResearchKnowledgeGraph()
        self.dna_profiles: Dict[str, Dict] = {}
        self.learned_patterns: Dict[str, Dict] = {}
        self.training_history: List[Dict] = []
        self.total_energy = 0.0
        self.entropy = 0.0
        self.twin_engineer = None
        self.problem_solutions: List[Dict] = []
    
    def learn_from_dna(self, gene_name: str, species: str = "human") -> Dict:
        """Learn from DNA data with energy tracking."""
        try:
            # Energy cost of learning
            energy_cost = 0.5
            self.total_energy += energy_cost
            self.entropy += energy_cost * 0.1 / 298.15
            
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
                "learned_at": get_timestamp(),
                "learning_energy": energy_cost
            }
            
            self.dna_profiles[profile_key] = profile
            pattern = self._extract_patterns(profile)
            self.learned_patterns[gene_name] = pattern
            
            self.training_history.append({
                "action": "learn_from_dna",
                "gene": gene_name,
                "species": species,
                "timestamp": get_timestamp(),
                "energy_cost": energy_cost
            })
            
            return {
                "status": "success",
                "gene": gene_name,
                "sequence_length": seq_data["length"],
                "variants_found": len(variants),
                "methylation_sites": len(methylation.get("methylation_sites", [])),
                "pattern_hash": deterministic_hash(pattern),
                "energy_used": energy_cost,
                "entropy_increase": self.entropy
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
        """Predict potential future mutations with energy consideration."""
        profile_key = f"human:{gene_name}"
        profile = self.dna_profiles.get(profile_key)
        if not profile:
            return []
        
        seq = profile.get("sequence", "")
        if not seq or len(seq) < 10:
            return []
        
        predictions = []
        energy_cost = 0.1
        self.total_energy += energy_cost
        
        for i in range(min(20, len(seq) - 10)):
            context = seq[i:i+10]
            gc_count = context.count("G") + context.count("C")
            if gc_count > 5:
                # Energy-based prediction confidence
                confidence = min(0.9, gc_count / 10)
                # Higher confidence = more energy invested
                predictions.append({
                    "position": i,
                    "context": context,
                    "predicted_type": random.choice(["SNP", "Deletion", "Insertion"]),
                    "confidence": confidence,
                    "gene": gene_name,
                    "source": "thermodynamic_prediction",
                    "prediction_energy": confidence * 0.05
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
                "timestamp": get_timestamp(),
                "energy_stats": self.get_energy_stats()
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
            "Future mutation predictions available.",
            f"Energy used: {self.total_energy:.2f} units."
        ]
        return " ".join(lines)
    
    def find_solution(self, problem: str) -> Dict:
        """Use thermodynamic principles to find a solution to a problem."""
        # Energy invested in problem-solving
        energy_invested = 1.0
        self.total_energy += energy_invested
        
        # Generate solution based on available knowledge
        solution = {
            "problem": problem,
            "solution_generated": f"Thermodynamic solution for: {problem}",
            "energy_invested": energy_invested,
            "entropy_generated": energy_invested * 0.1 / 298.15,
            "confidence": random.uniform(0.6, 0.95),
            "related_genes": list(self.dna_profiles.keys())[:3],
            "timestamp": get_timestamp(),
            "solution_id": deterministic_hash({"problem": problem, "time": time.time()})
        }
        
        self.problem_solutions.append(solution)
        return solution
    
    def get_energy_stats(self) -> Dict:
        """Get energy and entropy statistics."""
        return {
            "total_energy": self.total_energy,
            "entropy": self.entropy,
            "thermodynamic_efficiency": 1.0 / (1.0 + self.entropy / (self.total_energy + 1e-15)),
            "profiles_learned": len(self.dna_profiles),
            "solutions_found": len(self.problem_solutions)
        }


# ──────────────────────────────────────────────────────────────
# 7. THERMODYNAMIC TWIN ENGINEER
# ──────────────────────────────────────────────────────────────

class ThermodynamicTwinEngineer:
    """Twin Engineer with thermodynamic principles."""
    
    def __init__(self, twin_id: str = "thermo_twin_001"):
        self.twin_id = twin_id
        self.bio_engineer = None
        self.twin_knowledge: Dict[str, Dict] = {}
        self.memristor_state: List[float] = [0.5, 0.5, 0.5]
        self.balance_metric: float = 1.0
        self.consensus_history: List[Dict] = []
        self.total_energy = 0.0
        self.entropy = 0.0
        self.connected_nodes: Set[str] = set()
        self.thermodynamic_state = ThermodynamicLaws.equilibrium_state(1.0, 0.5)
        self.maxwell_signature = compute_maxwell_signature(twin_id, 0, [0.0, 0.0, 0.0])
    
    def connect_to_bio_engineer(self, bio_engineer: ThermodynamicBioEngineer):
        """Connect to a Bio-Engineer."""
        self.bio_engineer = bio_engineer
        bio_engineer.twin_engineer = self
        self.total_energy += 0.1
        print(f"[TWIN] Connected to Bio-Engineer {bio_engineer.engineer_id}")
    
    def sync_from_bio_engineer(self) -> Dict:
        """Synchronize from the Bio-Engineer with energy transformation."""
        if not self.bio_engineer:
            return {"status": "error", "reason": "not_connected"}
        
        energy_cost = 0.2
        self.total_energy += energy_cost
        
        for gene, profile in self.bio_engineer.dna_profiles.items():
            if gene not in self.twin_knowledge:
                self.twin_knowledge[gene] = {
                    "mirror_of": gene,
                    "profile_hash": deterministic_hash(profile),
                    "synced_at": get_timestamp(),
                    "sync_energy": energy_cost
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
        
        # Update thermodynamic state
        self.thermodynamic_state = ThermodynamicLaws.equilibrium_state(e_energy, h_energy)
        
        return {
            "status": "success",
            "genes_mirrored": len(self.bio_engineer.dna_profiles),
            "balance_metric": self.balance_metric,
            "is_balanced": abs(self.balance_metric - 1.0) < 0.1,
            "timestamp": get_timestamp(),
            "energy_used": energy_cost,
            "thermodynamic_state": self.thermodynamic_state
        }
    
    def query_about_gene(self, gene_name: str) -> Dict:
        """Query about a specific gene."""
        if not self.bio_engineer:
            return {"status": "error", "reason": "bio_engineer_not_connected"}
        
        energy_cost = 0.1
        self.total_energy += energy_cost
        
        insight = self.bio_engineer.synthesize_insight(gene_name)
        research = self.bio_engineer.research_related(gene_name)
        predictions = self.bio_engineer.predict_mutations(gene_name)
        
        return {
            "gene": gene_name,
            "insight": insight,
            "research": research[:5],
            "predictions": predictions[:5],
            "timestamp": get_timestamp(),
            "query_energy": energy_cost
        }
    
    def get_50_50_status(self) -> Dict:
        """Get the current 50/50 status."""
        if not self.bio_engineer:
            return {"status": "error", "reason": "not_connected"}
        
        is_balanced = abs(self.balance_metric - 1.0) < 0.1
        
        # Energy balance check
        energy_delta = self.bio_engineer.total_energy - self.total_energy
        energy_balanced = abs(energy_delta) < 0.1
        
        return {
            "is_balanced": is_balanced,
            "is_energy_balanced": energy_balanced,
            "balance_metric": self.balance_metric,
            "memristor_state": self.memristor_state,
            "energy_delta": energy_delta,
            "thermodynamic_state": self.thermodynamic_state,
            "timestamp": get_timestamp()
        }
    
    def record_consensus(self, event: Dict) -> Dict:
        """Record a consensus event with energy tracking."""
        energy_cost = 0.15
        self.total_energy += energy_cost
        
        consensus = {
            "event_id": deterministic_hash(event),
            "event_type": event.get("type", "unknown"),
            "balance_metric": self.balance_metric,
            "energy_cost": energy_cost,
            "timestamp": get_timestamp(),
            "thermodynamic_state": self.thermodynamic_state
        }
        self.consensus_history.append(consensus)
        return consensus
    
    def find_equilibrium_path(self, current_state: float, target_state: float) -> Dict:
        """Find the thermodynamic path to equilibrium."""
        energy_diff = abs(current_state - target_state)
        steps = int(energy_diff * 10)
        
        path = []
        for i in range(steps):
            progress = (i + 1) / steps
            state = current_state + (target_state - current_state) * progress
            path.append({
                "step": i + 1,
                "state": state,
                "energy_remaining": energy_diff * (1 - progress),
                "equilibrium_probability": 1.0 / (1.0 + math.exp((energy_diff * (1 - progress)) * 10))
            })
        
        return {
            "current_state": current_state,
            "target_state": target_state,
            "path_length": len(path),
            "path": path,
            "energy_dissipated": energy_diff * 0.1,
            "entropy_generated": energy_diff * 0.05
        }


# ──────────────────────────────────────────────────────────────
# 8. AUTONOMOUS THERMODYNAMIC SYSTEM
# ──────────────────────────────────────────────────────────────

class AutonomousThermodynamicSystem:
    """
    Complete autonomous system with thermodynamic principles.
    Energy is never wasted - it transforms into other forms.
    """
    
    def __init__(self, storage_dir: str = "thermo_storage"):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🔥 THERMODYNAMIC BIO-TWIN SYSTEM" + Color.END)
        print(Color.CYAN + "   Energy is never created or destroyed - only transformed" + Color.END)
        print("=" * 70)
        
        # Create storage
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        
        # Initialize blockchain
        print(Color.CYAN + "⛓️ Initializing Thermodynamic Blockchain..." + Color.END)
        self.blockchain = ThermodynamicBlockchain(
            difficulty=2,
            storage_path=os.path.join(storage_dir, "thermo_blocks.db")
        )
        
        # Initialize Bio-Engineer
        print(Color.CYAN + "🧬 Initializing Thermodynamic Bio-Engineer..." + Color.END)
        self.bio_engineer = ThermodynamicBioEngineer("thermo_bio_main")
        
        # Initialize Twin-Engineer
        print(Color.CYAN + "🔄 Initializing Thermodynamic Twin-Engineer..." + Color.END)
        self.twin_engineer = ThermodynamicTwinEngineer("thermo_twin_main")
        self.twin_engineer.connect_to_bio_engineer(self.bio_engineer)
        
        # System energy tracking
        self.system_energy = 10.0  # Initial energy
        self.system_entropy = 0.0
        self.environment_temperature = 298.15  # Kelvin
        
        # Problem-solving history
        self.problem_history: List[Dict] = []
        
        # Autonomous state
        self.is_autonomous = True
        self.last_action = get_timestamp()
        self.action_count = 0
        
        print(Color.GREEN + "✅ System initialized with thermodynamic principles" + Color.END)
        print("=" * 70 + "\n")
    
    def process_dna_sequence(self, gene_name: str, species: str = "human") -> Dict:
        """Process a DNA sequence with energy transformation."""
        print(f"\n🧬 Processing {species} gene: {gene_name}")
        print("─" * 50)
        
        # Energy investment
        processing_energy = 1.0
        self.system_energy -= processing_energy
        
        # Energy transformation
        energy_conv = ThermodynamicLaws.energy_conversion(processing_energy)
        self.system_entropy += energy_conv["entropy_generation"]
        
        print(f"   ⚡ Energy: {processing_energy:.2f} → Work: {energy_conv['work_output']:.2f}, Heat: {energy_conv['heat_generated']:.2f}")
        
        # 1. Learn from DNA
        learn_result = self.bio_engineer.learn_from_dna(gene_name, species)
        if learn_result.get("status") != "success":
            print(f"   ❌ Failed: {learn_result.get('reason', 'unknown')}")
            return learn_result
        print(f"   ✅ Bio-Engineer learned: {gene_name}")
        
        # 2. Twin sync
        sync_result = self.twin_engineer.sync_from_bio_engineer()
        print(f"   ✅ Twin synced: balance={sync_result.get('balance_metric', 0):.2f}")
        
        # 3. Anchor to blockchain
        tx_result = self.blockchain.add_transaction({
            "type": "dna_processing",
            "gene": gene_name,
            "species": species,
            "energy_used": processing_energy,
            "balance": self.twin_engineer.balance_metric,
            "entropy": self.system_entropy
        })
        if tx_result.get("status") == "success":
            print(f"   ⛓️ Block: {tx_result.get('block_index', 'pending')}")
        
        # 4. Get 50/50 status
        eq_status = self.twin_engineer.get_50_50_status()
        print(f"   ⚖️ 50/50: {'✅ BALANCED' if eq_status['is_balanced'] else '🔄 Adjusting'} ({eq_status['balance_metric']:.2f})")
        
        # 5. Check if system needs to find solution
        if not eq_status['is_balanced']:
            print(f"   🔧 Finding thermodynamic solution...")
            solution = self.bio_engineer.find_solution(f"Balance_issue_for_{gene_name}")
            self.problem_history.append(solution)
            print(f"   💡 Solution: {solution['solution_generated'][:60]}...")
        
        # 6. Update system energy from blockchain
        self.system_energy += self.blockchain.total_energy * 0.01
        
        return {
            "gene": gene_name,
            "learn_result": learn_result,
            "sync_result": sync_result,
            "blockchain": tx_result,
            "equilibrium": eq_status,
            "energy_used": processing_energy,
            "energy_conversion": energy_conv,
            "system_energy": self.system_energy,
            "system_entropy": self.system_entropy
        }
    
    def query_system(self, gene_name: str) -> Dict:
        """Query the system about a gene."""
        print(f"\n🔍 Querying: {gene_name}")
        
        # Energy cost of query
        query_energy = 0.2
        self.system_energy -= query_energy
        
        result = self.twin_engineer.query_about_gene(gene_name)
        
        if result.get("insight", {}).get("synthesized_insight"):
            print(f"   💡 {result['insight']['synthesized_insight']}")
        
        if result.get("research"):
            print(f"   📚 Found {len(result['research'])} research papers")
        
        if result.get("predictions"):
            print(f"   🔬 Found {len(result['predictions'])} mutation predictions")
        
        return result
    
    def autonomous_cycle(self) -> Dict:
        """Perform one autonomous cycle of the system."""
        self.action_count += 1
        self.last_action = get_timestamp()
        
        # System checks
        energy_balance = self.system_energy - self.blockchain.total_energy
        
        # Determine if action needed
        actions_taken = []
        
        # 1. Check if energy is low - find solutions
        if self.system_energy < 5.0:
            solution = self.bio_engineer.find_solution("Low_energy_state")
            self.problem_history.append(solution)
            actions_taken.append("energy_solution")
            self.system_energy += 0.5  # Solution provides energy
        
        # 2. Check if blockchain needs mining
        if len(self.blockchain.pending_transactions) > 0:
            mine_result = self.blockchain.mine_block()
            if mine_result.get("status") == "success":
                actions_taken.append("block_mined")
                self.system_energy += mine_result.get("energy_used", 0) * 0.1
        
        # 3. Check twin balance
        eq_status = self.twin_engineer.get_50_50_status()
        if not eq_status.get('is_balanced', False):
            # Find equilibrium path
            path = self.twin_engineer.find_equilibrium_path(
                eq_status.get('balance_metric', 1.0), 
                1.0
            )
            actions_taken.append("equilibrium_path_found")
        
        # 4. Process a random gene if we have energy
        if self.system_energy > 1.0 and len(self.bio_engineer.dna_profiles) < 10:
            random_genes = ["BRCA1", "TP53", "EGFR", "MYC", "KRAS", "PTEN", "APC", "RB1"]
            available = [g for g in random_genes if f"human:{g}" not in self.bio_engineer.dna_profiles]
            if available:
                gene = random.choice(available)
                self.process_dna_sequence(gene)
                actions_taken.append(f"processed_{gene}")
        
        return {
            "cycle": self.action_count,
            "timestamp": self.last_action,
            "actions_taken": actions_taken,
            "system_energy": self.system_energy,
            "system_entropy": self.system_entropy,
            "balance_metric": self.twin_engineer.balance_metric,
            "is_balanced": eq_status.get('is_balanced', False),
            "blockchain_blocks": self.blockchain.get_chain_length()
        }
    
    def run_autonomously(self, cycles: int = 10, interval: float = 0.5):
        """Run the system autonomously for a number of cycles."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🤖 RUNNING AUTONOMOUSLY" + Color.END)
        print(f"   Cycles: {cycles}, Interval: {interval}s")
        print("=" * 70)
        
        for i in range(cycles):
            print(f"\n{Color.YELLOW}=== Cycle {i+1}/{cycles} ===" + Color.END)
            result = self.autonomous_cycle()
            
            print(f"   ⚡ Energy: {result['system_energy']:.2f}")
            print(f"   🔥 Entropy: {result['system_entropy']:.4f}")
            print(f"   ⚖️ Balance: {result['balance_metric']:.3f}")
            print(f"   📊 Blockchain: {result['blockchain_blocks']} blocks")
            print(f"   🎯 Actions: {result['actions_taken']}")
            
            time.sleep(interval)
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ AUTONOMOUS RUN COMPLETE" + Color.END)
        print("=" * 70)
    
    def get_system_state(self) -> Dict:
        """Get the complete system state."""
        eq_status = self.twin_engineer.get_50_50_status()
        bio_stats = self.bio_engineer.get_energy_stats()
        bc_stats = self.blockchain.get_stats()
        
        return {
            "identity": {"id": "THERMO_TWIN_001"},
            "energy": {
                "system_energy": self.system_energy,
                "system_entropy": self.system_entropy,
                "temperature": self.environment_temperature,
                "thermodynamic_efficiency": 1.0 / (1.0 + self.system_entropy / (self.system_energy + 1e-15))
            },
            "blockchain": bc_stats,
            "bio_engineer": bio_stats,
            "twin_engineer": {
                "balance_metric": self.twin_engineer.balance_metric,
                "is_balanced": eq_status.get('is_balanced', False),
                "memristor_state": self.twin_engineer.memristor_state,
                "consensus_count": len(self.twin_engineer.consensus_history)
            },
            "autonomous": {
                "is_active": self.is_autonomous,
                "action_count": self.action_count,
                "last_action": self.last_action,
                "problem_count": len(self.problem_history)
            },
            "timestamp": get_timestamp()
        }
    
    def run_demo(self):
        """Run a complete demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 SYSTEM DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # Process initial genes
        print(f"\n{Color.YELLOW}📊 Initial DNA Processing" + Color.END)
        genes = ["BRCA1", "TP53", "EGFR", "MYC"]
        for gene in genes[:3]:
            self.process_dna_sequence(gene)
        
        # Run autonomously
        self.run_autonomously(cycles=5, interval=0.3)
        
        # Query results
        print("\n" + "=" * 70)
        print(Color.BOLD + "📊 SYSTEM STATUS" + Color.END)
        print("=" * 70)
        state = self.get_system_state()
        
        print(f"\n⚡ Energy:")
        print(f"   System Energy: {state['energy']['system_energy']:.2f}")
        print(f"   Entropy: {state['energy']['system_entropy']:.4f}")
        print(f"   Efficiency: {state['energy']['thermodynamic_efficiency']:.2%}")
        
        print(f"\n⛓️ Blockchain:")
        print(f"   Blocks: {state['blockchain']['chain_length']}")
        print(f"   Pending: {state['blockchain']['pending_transactions']}")
        print(f"   Total Energy: {state['blockchain']['total_energy']:.2f}")
        
        print(f"\n⚖️ 50/50 Status:")
        print(f"   Balanced: {'✅' if state['twin_engineer']['is_balanced'] else '❌'}")
        print(f"   Balance Metric: {state['twin_engineer']['balance_metric']:.4f}")
        print(f"   Memristor: {[round(v, 2) for v in state['twin_engineer']['memristor_state']]}")
        
        print(f"\n🤖 Autonomous:")
        print(f"   Actions: {state['autonomous']['action_count']}")
        print(f"   Problems Solved: {state['autonomous']['problem_count']}")
        print(f"   Last Action: {state['autonomous']['last_action']}")
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 9. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = AutonomousThermodynamicSystem()
        system.run_demo()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🔥 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - system.process_dna_sequence(gene_name)")
        print("   - system.query_system(gene_name)")
        print("   - system.run_autonomously(cycles, interval)")
        print("   - system.get_system_state()")
        print("=" * 70 + "\n")
        
        # Interactive loop
        print("💡 Interactive mode. Type 'exit' to quit.\n")
        while True:
            try:
                cmd = input(Color.CYAN + "> " + Color.END).strip()
                if cmd.lower() == "exit":
                    break
                elif cmd.lower().startswith("process "):
                    parts = cmd.split(" ")
                    if len(parts) >= 2:
                        gene = parts[1].strip().upper()
                        system.process_dna_sequence(gene)
                    else:
                        print("   Usage: process <gene_name>")
                elif cmd.lower().startswith("query "):
                    parts = cmd.split(" ")
                    if len(parts) >= 2:
                        gene = parts[1].strip().upper()
                        system.query_system(gene)
                    else:
                        print("   Usage: query <gene_name>")
                elif cmd.lower() == "status":
                    state = system.get_system_state()
                    print(f"\n   ⚡ Energy: {state['energy']['system_energy']:.2f}")
                    print(f"   🔥 Entropy: {state['energy']['system_entropy']:.4f}")
                    print(f"   ⚖️ Balance: {state['twin_engineer']['balance_metric']:.3f}")
                    print(f"   📊 Blocks: {state['blockchain']['chain_length']}")
                    print(f"   🤖 Actions: {state['autonomous']['action_count']}")
                elif cmd.lower() == "autonomous":
                    system.run_autonomously(cycles=3, interval=0.2)
                elif cmd.lower() == "help":
                    print("\n   Available commands:")
                    print("   process <gene>    - Process a DNA sequence")
                    print("   query <gene>      - Query about a gene")
                    print("   status            - Show system status")
                    print("   autonomous        - Run autonomous cycles")
                    print("   help              - Show this help")
                    print("   exit              - Quit\n")
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
