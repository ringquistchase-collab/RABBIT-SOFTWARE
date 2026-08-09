#!/usr/bin/env python3
"""
Maxwell Medical Research Blockchain System
===========================================
Save as: maxwell_medical_research.py
Run:     python3 maxwell_medical_research.py

FEATURES:
1. Medical research data integration
2. Public dataset mining (NCBI, ClinicalTrials, OpenResearch)
3. Blockchain storage of research data
4. Data mining with pattern recognition
5. Maxwell predictions on research trends
6. DNA/Twin integration with medical data
7. Research network connections
8. Open research data aggregation
9. Medical research blockchain blocks
10. Autonomous research data mining

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

# Optional requests for API calls
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


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
# 2. MEDICAL RESEARCH DATA PROVIDER
# ──────────────────────────────────────────────────────────────

class MedicalResearchProvider:
    """
    Fetches medical research data from public datasets and APIs.
    Simulates real data when APIs are unavailable.
    """
    
    def __init__(self):
        self.cache: Dict[str, Dict] = {}
        self.research_history: List[Dict] = []
        self.total_energy = 0.0
        
        # Medical research categories
        self.research_categories = [
            "oncology", "neurology", "cardiology", "immunology",
            "genomics", "epidemiology", "pharmacology", "psychiatry",
            "dermatology", "endocrinology", "hematology", "pathology"
        ]
        
        # Public datasets
        self.public_datasets = {
            "ncbi": "https://www.ncbi.nlm.nih.gov/pubmed",
            "clinicaltrials": "https://clinicaltrials.gov",
            "openresearch": "https://openresearch.org",
            "biorxiv": "https://www.biorxiv.org",
            "medrxiv": "https://www.medrxiv.org"
        }
        
        # Research tags
        self.research_tags = [
            "DNA", "RNA", "protein", "gene_expression", "mutation",
            "clinical_trial", "therapy", "drug_discovery", "biomarker",
            "imaging", "surgery", "immunotherapy", "gene_editing",
            "CRISPR", "stem_cell", "regenerative_medicine"
        ]
    
    def fetch_pubmed_article(self, query: str) -> Dict:
        """Fetch a simulated PubMed article."""
        article_id = f"PMID_{random.randint(10000000, 99999999)}"
        title = f"Research on {query} in medical applications"
        
        article = {
            "id": article_id,
            "title": title,
            "authors": [f"Author_{random.randint(1, 100)}" for _ in range(random.randint(1, 5))],
            "journal": random.choice(["Nature Medicine", "The Lancet", "NEJM", "Cell", "Science"]),
            "year": random.randint(2010, 2024),
            "volume": random.randint(10, 500),
            "pages": f"{random.randint(100, 999)}-{random.randint(1000, 9999)}",
            "doi": f"10.{random.randint(1000, 9999)}/{query.replace(' ', '_')}_{article_id}",
            "abstract": f"This study investigates the role of {query} in human health and disease. "
                       f"We found significant correlations with {random.choice(['disease progression', 'treatment response', 'survival rates'])}.",
            "keywords": [query] + random.sample(self.research_tags, min(3, len(self.research_tags))),
            "source": "pubmed",
            "timestamp": get_timestamp()
        }
        
        self.cache[article_id] = article
        self.research_history.append({"type": "pubmed", "data": article})
        self.total_energy += 0.1
        return article
    
    def fetch_clinical_trial(self) -> Dict:
        """Fetch a simulated clinical trial."""
        trial_id = f"NCT{random.randint(10000000, 99999999)}"
        conditions = [
            "Breast Cancer", "Alzheimer's Disease", "Cardiovascular Disease",
            "Type 2 Diabetes", "Parkinson's Disease", "Lung Cancer",
            "Multiple Sclerosis", "Leukemia", "Autoimmune Disorder"
        ]
        
        trial = {
            "id": trial_id,
            "title": f"Phase {random.choice(['I', 'II', 'III', 'IV'])} trial for {random.choice(conditions)}",
            "status": random.choice(["Recruiting", "Active", "Completed", "Suspended"]),
            "phase": random.choice(["Phase 1", "Phase 2", "Phase 3", "Phase 4"]),
            "sponsor": random.choice(["NIH", "Pfizer", "Merck", "AstraZeneca", "Academic Research"]),
            "condition": random.choice(conditions),
            "intervention": random.choice(["Drug", "Device", "Procedure", "Behavioral"]),
            "location": random.choice(["USA", "UK", "Germany", "France", "Japan", "Multiple"]),
            "enrollment": random.randint(10, 5000),
            "start_date": f"{random.randint(2018, 2023)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "completion_date": f"{random.randint(2024, 2026)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "source": "clinicaltrials",
            "timestamp": get_timestamp()
        }
        
        self.cache[trial_id] = trial
        self.research_history.append({"type": "clinical_trial", "data": trial})
        self.total_energy += 0.15
        return trial
    
    def fetch_open_research(self) -> Dict:
        """Fetch simulated open research data."""
        research_id = f"OR_{random.randint(10000, 99999)}"
        topics = [
            "Genomic variations in cancer", "Neural network imaging",
            "Cardiac gene therapy", "Immunotherapy biomarkers",
            "CRISPR applications", "Stem cell therapies",
            "Dementia biomarkers", "Drug repurposing"
        ]
        
        research = {
            "id": research_id,
            "title": random.choice(topics),
            "authors": [f"Researcher_{random.randint(1, 50)}" for _ in range(random.randint(2, 6))],
            "institution": random.choice(["Harvard", "Stanford", "MIT", "Oxford", "Cambridge", "NIH"]),
            "preprint": f"https://doi.org/{random.randint(1000, 9999)}/{research_id}",
            "submission_date": f"{random.randint(2023, 2024)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "abstract": f"We present novel findings in {random.choice(topics)} using state-of-the-art methods.",
            "keywords": random.sample(self.research_tags, 4),
            "open_access": random.choice([True, False]),
            "source": "openresearch",
            "timestamp": get_timestamp()
        }
        
        self.cache[research_id] = research
        self.research_history.append({"type": "open_research", "data": research})
        self.total_energy += 0.12
        return research
    
    def fetch_medical_dataset(self, dataset_name: str) -> Dict:
        """Fetch a simulated medical dataset."""
        datasets = {
            "genomic": {
                "name": "Genomic Cancer Dataset",
                "records": random.randint(1000, 100000),
                "features": ["gene_expression", "mutations", "copy_number_variations"],
                "description": "Comprehensive genomic profiling of cancer patients"
            },
            "clinical": {
                "name": "Clinical Outcomes Dataset",
                "records": random.randint(5000, 500000),
                "features": ["age", "gender", "diagnosis", "treatment", "outcome"],
                "description": "Electronic health records analysis"
            },
            "imaging": {
                "name": "Medical Imaging Dataset",
                "records": random.randint(1000, 10000),
                "features": ["MRI", "CT", "PET", "ultrasound"],
                "description": "Multi-modal imaging data"
            },
            "pharma": {
                "name": "Drug Discovery Dataset",
                "records": random.randint(10000, 1000000),
                "features": ["drug_id", "target", "activity", "toxicity"],
                "description": "High-throughput screening data"
            }
        }
        
        data = datasets.get(dataset_name, datasets["genomic"])
        dataset = {
            "id": f"DS_{deterministic_hash(dataset_name)[:8]}",
            "name": data["name"],
            "records": data["records"],
            "features": data["features"],
            "description": data["description"],
            "source": "public_dataset",
            "timestamp": get_timestamp()
        }
        
        self.cache[dataset["id"]] = dataset
        self.research_history.append({"type": "dataset", "data": dataset})
        self.total_energy += 0.2
        return dataset
    
    def mine_research_trends(self) -> Dict:
        """Mine research trends from collected data."""
        trends = defaultdict(int)
        
        for entry in self.research_history[-20:]:  # Analyze recent data
            if "data" in entry:
                data = entry["data"]
                if "keywords" in data:
                    for keyword in data.get("keywords", []):
                        trends[keyword] += 1
        
        # Add recent clinical trial data
        clinical_trials = [e for e in self.research_history if e.get("type") == "clinical_trial"]
        if clinical_trials:
            trends["clinical_trials"] = len(clinical_trials)
        
        # Add publication trends
        publications = [e for e in self.research_history if e.get("type") in ["pubmed", "open_research"]]
        trends["publications"] = len(publications)
        
        # Calculate trend scores
        total = sum(trends.values())
        trend_scores = {k: v / total for k, v in trends.items()} if total > 0 else {}
        
        return {
            "trends": dict(trends),
            "trend_scores": trend_scores,
            "top_trends": sorted(trends.items(), key=lambda x: x[1], reverse=True)[:5],
            "timestamp": get_timestamp()
        }
    
    def get_stats(self) -> Dict:
        return {
            "research_entries": len(self.research_history),
            "cache_size": len(self.cache),
            "total_energy": self.total_energy,
            "research_categories": len(self.research_categories),
            "datasets": len([e for e in self.research_history if e.get("type") == "dataset"])
        }


# ──────────────────────────────────────────────────────────────
# 3. MAXWELL RESEARCH BLOCKCHAIN
# ──────────────────────────────────────────────────────────────

class MaxwellResearchBlock:
    """Block storing medical research data."""
    
    def __init__(self, index: int, transactions: List[Dict], previous_hash: str,
                 chain_id: str = "medical_research", difficulty: int = 3):
        self.index = index
        self.timestamp = get_timestamp()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.nonce = 0
        self.energy = 1.0
        self.entropy = 0.0
        self.research_hash = deterministic_hash(transactions)
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
            "research_hash": self.research_hash
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
    
    def get_research_summary(self) -> Dict:
        """Extract research data summary from block transactions."""
        research_count = len(self.transactions)
        types = defaultdict(int)
        keywords = defaultdict(int)
        
        for tx in self.transactions:
            if tx.get("data", {}).get("type"):
                types[tx["data"]["type"]] += 1
            for key in tx.get("data", {}).get("keywords", []):
                keywords[key] += 1
        
        return {
            "block_index": self.index,
            "research_count": research_count,
            "types": dict(types),
            "keywords": dict(keywords),
            "energy": self.energy,
            "entropy": self.entropy,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }
    
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
            "research_hash": self.research_hash,
            "research_summary": self.get_research_summary(),
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


class MaxwellResearchChain:
    """Blockchain for medical research data."""
    
    def __init__(self, chain_id: str = "medical_research", difficulty: int = 2):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellResearchBlock] = []
        self.total_energy = 0.0
        self.total_entropy = 0.0
        self.status = "active"
        self.created_at = get_timestamp()
        self.research_count = 0
        
        self._create_genesis()
    
    def _create_genesis(self):
        genesis_data = [{
            "type": "genesis",
            "data": {
                "message": f"Medical Research Blockchain - {self.chain_id}",
                "timestamp": get_timestamp()
            }
        }]
        genesis = MaxwellResearchBlock(0, genesis_data, "0" * 64, self.chain_id, self.difficulty)
        genesis.mine()
        self.blocks.append(genesis)
        self.total_energy += genesis.energy
    
    def add_research_transaction(self, research_data: Dict) -> Dict:
        """Add a research transaction to the blockchain."""
        transaction = {
            "type": research_data.get("type", "research"),
            "data": research_data,
            "timestamp": get_timestamp(),
            "id": deterministic_hash(research_data)
        }
        
        # Mine a new block for each research transaction
        previous_hash = self.blocks[-1].hash
        block = MaxwellResearchBlock(
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
        self.research_count += 1
        
        return {
            "status": "success",
            "block_index": block.index,
            "block_hash": truncate_hash(block.hash),
            "research_id": transaction["id"],
            "energy": block.energy
        }
    
    def add_batch_transactions(self, research_data_list: List[Dict]) -> Dict:
        """Add multiple research transactions in one block."""
        transactions = []
        for data in research_data_list:
            transactions.append({
                "type": data.get("type", "research"),
                "data": data,
                "timestamp": get_timestamp(),
                "id": deterministic_hash(data)
            })
        
        previous_hash = self.blocks[-1].hash
        block = MaxwellResearchBlock(
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
        self.research_count += len(transactions)
        
        return {
            "status": "success",
            "block_index": block.index,
            "block_hash": truncate_hash(block.hash),
            "transaction_count": len(transactions),
            "energy": block.energy
        }
    
    def search_research(self, keyword: str) -> List[Dict]:
        """Search research data by keyword."""
        results = []
        keyword_lower = keyword.lower()
        
        for block in self.blocks:
            for tx in block.transactions:
                data = tx.get("data", {})
                # Search in various fields
                search_text = json.dumps(data).lower()
                if keyword_lower in search_text:
                    results.append({
                        "block_index": block.index,
                        "transaction_id": tx.get("id"),
                        "data": data,
                        "timestamp": tx.get("timestamp")
                    })
        
        return results
    
    def get_health(self) -> Dict:
        """Get chain health metrics."""
        return {
            "chain_id": self.chain_id,
            "blocks": len(self.blocks),
            "status": self.status,
            "research_count": self.research_count,
            "total_energy": self.total_energy,
            "total_entropy": self.total_entropy,
            "efficiency": 1.0 / (1.0 + self.total_entropy / (self.total_energy + 1e-15)),
            "created_at": self.created_at
        }
    
    def get_research_stats(self) -> Dict:
        """Get research statistics from the blockchain."""
        type_counts = defaultdict(int)
        keyword_counts = defaultdict(int)
        
        for block in self.blocks:
            for tx in block.transactions:
                data = tx.get("data", {})
                type_counts[data.get("type", "unknown")] += 1
                for keyword in data.get("keywords", []):
                    keyword_counts[keyword] += 1
        
        return {
            "total_research": self.research_count,
            "type_distribution": dict(type_counts),
            "keyword_distribution": dict(keyword_counts),
            "top_keywords": sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        }
    
    def to_dict(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "blocks": [block.to_dict() for block in self.blocks],
            "total_energy": self.total_energy,
            "total_entropy": self.total_entropy,
            "status": self.status,
            "research_count": self.research_count,
            "created_at": self.created_at
        }


# ──────────────────────────────────────────────────────────────
# 4. MEDICAL RESEARCH DATA MINER
# ──────────────────────────────────────────────────────────────

class MedicalResearchMiner:
    """
    Mines medical research data from multiple sources.
    """
    
    def __init__(self, provider: MedicalResearchProvider):
        self.provider = provider
        self.mining_history: List[Dict] = []
        self.mining_patterns: Dict[str, Any] = {}
        self.energy = 10.0
        self.entropy = 0.0
        self.discoveries: List[Dict] = []
    
    def mine_single_source(self, source_type: str) -> Dict:
        """Mine research data from a single source."""
        result = {}
        
        if source_type == "pubmed":
            query = random.choice(self.provider.research_tags)
            result = self.provider.fetch_pubmed_article(query)
        elif source_type == "clinicaltrials":
            result = self.provider.fetch_clinical_trial()
        elif source_type == "openresearch":
            result = self.provider.fetch_open_research()
        elif source_type == "dataset":
            dataset_names = ["genomic", "clinical", "imaging", "pharma"]
            result = self.provider.fetch_medical_dataset(random.choice(dataset_names))
        else:
            return {"status": "error", "reason": "unknown_source"}
        
        # Record mining
        self.mining_history.append({
            "source": source_type,
            "result": result,
            "timestamp": get_timestamp()
        })
        self.energy -= 0.1
        self.entropy += 0.01
        
        return result
    
    def mine_all_sources(self) -> Dict:
        """Mine research data from all available sources."""
        results = []
        sources = ["pubmed", "clinicaltrials", "openresearch", "dataset"]
        
        for source in sources:
            try:
                result = self.mine_single_source(source)
                results.append({
                    "source": source,
                    "status": "success",
                    "data": result
                })
            except Exception as e:
                results.append({
                    "source": source,
                    "status": "error",
                    "error": str(e)
                })
        
        return {
            "status": "success",
            "results": results,
            "energy": self.energy,
            "entropy": self.entropy
        }
    
    def discover_patterns(self) -> Dict:
        """Discover patterns in mined research data."""
        patterns = {
            "trending_topics": [],
            "emerging_fields": [],
            "research_gaps": [],
            "collaboration_networks": []
        }
        
        # Analyze mining history
        topic_counts = defaultdict(int)
        author_counts = defaultdict(int)
        source_counts = defaultdict(int)
        
        for entry in self.mining_history:
            data = entry.get("result", {})
            source = entry.get("source", "unknown")
            source_counts[source] += 1
            
            if "keywords" in data:
                for keyword in data["keywords"]:
                    topic_counts[keyword] += 1
            
            if "authors" in data:
                for author in data["authors"]:
                    author_counts[author] += 1
        
        # Identify trends
        if topic_counts:
            patterns["trending_topics"] = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        if author_counts:
            patterns["collaboration_networks"] = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        patterns["source_distribution"] = dict(source_counts)
        patterns["total_mining_events"] = len(self.mining_history)
        patterns["energy_remaining"] = self.energy
        patterns["entropy_generated"] = self.entropy
        
        self.mining_patterns = patterns
        
        # Record discovery
        discovery = {
            "type": "pattern_discovery",
            "patterns": patterns,
            "timestamp": get_timestamp()
        }
        self.discoveries.append(discovery)
        
        return patterns
    
    def get_stats(self) -> Dict:
        return {
            "mining_events": len(self.mining_history),
            "energy": self.energy,
            "entropy": self.entropy,
            "discoveries": len(self.discoveries),
            "patterns": self.mining_patterns
        }


# ──────────────────────────────────────────────────────────────
# 5. DNA/TWIN MEDICAL RESEARCH SYSTEM
# ──────────────────────────────────────────────────────────────

class DNAMedicalSegment:
    """DNA segment with medical research data."""
    
    def __init__(self, sequence: str, name: str = ""):
        self.sequence = sequence
        self.name = name or f"DNA_MED_{random.randint(1000, 9999)}"
        self.hash = hashlib.sha256(sequence.encode()).hexdigest()
        self.medical_conditions: List[str] = []
        self.research_bindings: List[str] = []
        self.health_markers: Dict[str, float] = {}
        self.twin_link: Optional['TwinMedicalSegment'] = None
        self.creation_time = get_timestamp()
        self.maxwell_sig = compute_maxwell_signature(sequence + name, 0, [0.0, 0.0, 0.0])
    
    def add_medical_condition(self, condition: str) -> Dict:
        self.medical_conditions.append(condition)
        return {"status": "added", "condition": condition}
    
    def add_health_marker(self, marker: str, value: float) -> Dict:
        self.health_markers[marker] = value
        return {"status": "added", "marker": marker, "value": value}
    
    def bind_research(self, research_id: str) -> Dict:
        self.research_bindings.append(research_id)
        return {"status": "bound", "research": research_id}
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "sequence": self.sequence[:50] + "...",
            "hash": self.hash[:16],
            "medical_conditions": self.medical_conditions,
            "health_markers": self.health_markers,
            "research_bindings": self.research_bindings,
            "twin_link": self.twin_link.name if self.twin_link else None,
            "creation_time": self.creation_time,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


class TwinMedicalSegment:
    """Twin segment with medical research mirroring."""
    
    def __init__(self, name: str = ""):
        self.name = name or f"TWIN_MED_{random.randint(1000, 9999)}"
        self.dna_link: Optional[DNAMedicalSegment] = None
        self.medical_mirror: List[str] = []
        self.research_mirror: List[str] = []
        self.memristor_state = [0.5, 0.5, 0.5]
        self.health_predictions: Dict[str, float] = {}
        self.creation_time = get_timestamp()
        self.maxwell_sig = compute_maxwell_signature(name, 0, [0.0, 0.0, 0.0])
    
    def mirror_dna(self, dna: DNAMedicalSegment) -> Dict:
        self.dna_link = dna
        dna.twin_link = self
        
        self.medical_mirror = dna.medical_conditions.copy()
        self.research_mirror = dna.research_bindings.copy()
        
        # Update memristor state
        for i, condition in enumerate(dna.medical_conditions[:3]):
            self.memristor_state[i] = (hash(condition) % 10) / 10
        
        return {"status": "mirrored", "twin": self.name, "dna": dna.name}
    
    def predict_health_risk(self, condition: str) -> float:
        """Predict health risk based on twin data."""
        if condition in self.medical_mirror:
            base_risk = 0.7 + random.random() * 0.3
        else:
            base_risk = random.random() * 0.5
        
        # Adjust based on memristor state
        risk = base_risk * (1 + sum(self.memristor_state) / 3)
        risk = min(1.0, max(0.0, risk))
        self.health_predictions[condition] = risk
        return risk
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "dna_link": self.dna_link.name if self.dna_link else None,
            "medical_mirror": self.medical_mirror,
            "research_mirror": self.research_mirror,
            "memristor_state": self.memristor_state,
            "health_predictions": self.health_predictions,
            "creation_time": self.creation_time,
            "maxwell_impedance": self.maxwell_sig.get("wave_impedance", 1.0)
        }


# ──────────────────────────────────────────────────────────────
# 6. MAIN RESEARCH SYSTEM
# ──────────────────────────────────────────────────────────────

class MaxwellMedicalResearchSystem:
    """Complete medical research system with blockchain and DNA/Twin."""
    
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🧬 MAXWELL MEDICAL RESEARCH SYSTEM" + Color.END)
        print(Color.CYAN + "   Blockchain + DNA/Twin + Data Mining" + Color.END)
        print("=" * 70)
        
        # Initialize components
        print(Color.CYAN + "📊 Initializing Medical Research Provider..." + Color.END)
        self.provider = MedicalResearchProvider()
        
        print(Color.CYAN + "⛓️ Initializing Research Blockchain..." + Color.END)
        self.blockchain = MaxwellResearchChain("maxwell_medical", difficulty=2)
        
        print(Color.CYAN + "⛏️ Initializing Research Miner..." + Color.END)
        self.miner = MedicalResearchMiner(self.provider)
        
        print(Color.CYAN + "🧬 Initializing DNA Medical Segments..." + Color.END)
        self.dna_segments: Dict[str, DNAMedicalSegment] = {}
        self.twin_segments: Dict[str, TwinMedicalSegment] = {}
        self._initialize_segments()
        
        print(Color.GREEN + "✅ System initialized with medical research" + Color.END)
        print("=" * 70 + "\n")
    
    def _initialize_segments(self):
        """Initialize DNA and Twin medical segments."""
        dna_sequences = [
            ("ATGCGATCGTAGCTAGCTAGCTAGCTAGC", "DNA_MED_MAIN"),
            ("GCTAGCTAGCTAGCTAGCATGCGATCGTA", "DNA_MED_BACKUP"),
            ("TAGCTAGCTAGCATGCGATCGTAGCTAGC", "DNA_MED_QUANTUM"),
        ]
        
        conditions = [
            ["Breast Cancer", "BRCA1", "Ovarian Cancer"],
            ["Alzheimer's", "APOE4", "Cognitive Decline"],
            ["Cardiovascular", "Heart Disease", "Hyperlipidemia"]
        ]
        
        for i, (seq, name) in enumerate(dna_sequences):
            dna = DNAMedicalSegment(seq, name)
            self.dna_segments[name] = dna
            
            # Add medical conditions
            if i < len(conditions):
                for condition in conditions[i]:
                    dna.add_medical_condition(condition)
            
            # Add health markers
            dna.add_health_marker("inflammation", random.uniform(0.1, 0.9))
            dna.add_health_marker("oxidative_stress", random.uniform(0.1, 0.9))
            dna.add_health_marker("hormone_level", random.uniform(0.1, 0.9))
            
            # Create twin
            twin = TwinMedicalSegment(f"TWIN_{name}")
            self.twin_segments[twin.name] = twin
            twin.mirror_dna(dna)
        
        print(f"   ✅ Created {len(self.dna_segments)} DNA segments")
        print(f"   ✅ Created {len(self.twin_segments)} Twin segments")
    
    def mine_research_data(self) -> Dict:
        """Mine research data and add to blockchain."""
        print(f"\n{Color.YELLOW}⛏️ Mining Research Data..." + Color.END)
        
        # Mine all sources
        result = self.miner.mine_all_sources()
        
        # Add successful results to blockchain
        for item in result.get("results", []):
            if item.get("status") == "success":
                data = item.get("data", {})
                if data:
                    blockchain_result = self.blockchain.add_research_transaction(data)
                    print(f"   ✅ Added {item['source']} to blockchain (Block {blockchain_result['block_index']})")
        
        # Discover patterns
        patterns = self.miner.discover_patterns()
        print(f"   📊 Discovered patterns: {len(patterns.get('trending_topics', []))} trending topics")
        
        return {
            "status": "success",
            "mining_results": result,
            "patterns": patterns,
            "blockchain_stats": self.blockchain.get_health()
        }
    
    def search_research(self, keyword: str) -> Dict:
        """Search research data on the blockchain."""
        print(f"\n{Color.BLUE}🔍 Searching: {keyword}" + Color.END)
        results = self.blockchain.search_research(keyword)
        print(f"   Found {len(results)} results")
        return {"status": "success", "results": results, "count": len(results)}
    
    def analyze_research_trends(self) -> Dict:
        """Analyze research trends."""
        print(f"\n{Color.CYAN}📊 Analyzing Research Trends..." + Color.END)
        trends = self.provider.mine_research_trends()
        print(f"   Top trend: {trends['top_trends'][0] if trends['top_trends'] else 'None'}")
        return trends
    
    def get_health_predictions(self, condition: str) -> Dict:
        """Get health predictions from the twin system."""
        predictions = {}
        for twin in self.twin_segments.values():
            risk = twin.predict_health_risk(condition)
            predictions[twin.name] = {
                "risk": risk,
                "risk_level": "High" if risk > 0.7 else "Medium" if risk > 0.4 else "Low",
                "memristor_state": twin.memristor_state
            }
        return predictions
    
    def show_status(self):
        """Show system status."""
        blockchain_health = self.blockchain.get_health()
        research_stats = self.blockchain.get_research_stats()
        miner_stats = self.miner.get_stats()
        provider_stats = self.provider.get_stats()
        
        print(f"\n{Color.CYAN}📊 SYSTEM STATUS" + Color.END)
        print("=" * 60)
        
        print(f"\n{Color.BOLD}⛓️ Blockchain:" + Color.END)
        print(f"   Chain: {blockchain_health['chain_id']}")
        print(f"   Blocks: {blockchain_health['blocks']}")
        print(f"   Research Records: {blockchain_health['research_count']}")
        print(f"   Energy: {blockchain_health['total_energy']:.2f}")
        print(f"   Efficiency: {blockchain_health['efficiency']:.2%}")
        
        print(f"\n{Color.BOLD}📊 Research Stats:" + Color.END)
        print(f"   Total Research: {research_stats['total_research']}")
        print(f"   Types: {len(research_stats['type_distribution'])}")
        if research_stats['top_keywords']:
            print(f"   Top Keyword: {research_stats['top_keywords'][0][0]} ({research_stats['top_keywords'][0][1]})")
        
        print(f"\n{Color.BOLD}⛏️ Miner:" + Color.END)
        print(f"   Events: {miner_stats['mining_events']}")
        print(f"   Energy: {miner_stats['energy']:.2f}")
        print(f"   Discoveries: {miner_stats['discoveries']}")
        
        print(f"\n{Color.BOLD}🧬 DNA/Twin:" + Color.END)
        print(f"   DNA Segments: {len(self.dna_segments)}")
        print(f"   Twin Segments: {len(self.twin_segments)}")
        
        print("\n" + "=" * 60)
    
    def run_demo(self):
        """Run a complete demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 MEDICAL RESEARCH DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # 1. Mine research data
        print(f"\n{Color.BOLD}Step 1: Mining Research Data" + Color.END)
        self.mine_research_data()
        
        # 2. Mine more data
        print(f"\n{Color.BOLD}Step 2: Mining Additional Data" + Color.END)
        for _ in range(3):
            self.miner.mine_all_sources()
        
        # 3. Analyze trends
        print(f"\n{Color.BOLD}Step 3: Analyzing Trends" + Color.END)
        trends = self.analyze_research_trends()
        print(f"   Top 3 Research Trends:")
        for trend, count in trends['top_trends'][:3]:
            print(f"      • {trend}: {count}")
        
        # 4. Search research
        print(f"\n{Color.BOLD}Step 4: Searching Research" + Color.END)
        search_term = "cancer"
        search_results = self.search_research(search_term)
        print(f"   Found {search_results['count']} results for '{search_term}'")
        
        # 5. Health predictions
        print(f"\n{Color.BOLD}Step 5: Health Predictions" + Color.END)
        predictions = self.get_health_predictions("Breast Cancer")
        for twin, pred in predictions.items():
            print(f"   {twin}: {pred['risk_level']} risk ({pred['risk']:.2f})")
        
        # 6. Show final status
        self.show_status()
        
        # 7. Show blockchain research summary
        print(f"\n{Color.BOLD}⛓️ Blockchain Research Summary" + Color.END)
        print("=" * 60)
        research_stats = self.blockchain.get_research_stats()
        print(f"   Total Research Records: {research_stats['total_research']}")
        print(f"   Type Distribution:")
        for type_name, count in research_stats['type_distribution'].items():
            print(f"      • {type_name}: {count}")
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)
    
    def run_autonomous(self, cycles: int = 5):
        """Run autonomous cycles of research mining."""
        print(f"\n{Color.CYAN}🤖 RUNNING AUTONOMOUSLY FOR {cycles} CYCLES" + Color.END)
        print("=" * 70)
        
        for i in range(cycles):
            print(f"\n{Color.YELLOW}=== Cycle {i+1}/{cycles} ===" + Color.END)
            self.mine_research_data()
            time.sleep(0.5)
            
            # Add health predictions
            for twin in self.twin_segments.values():
                for condition in twin.medical_mirror[:2]:
                    twin.predict_health_risk(condition)
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ AUTONOMOUS RUN COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 7. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = MaxwellMedicalResearchSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🧬 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show system status")
        print("   - mine          - Mine research data")
        print("   - search <term> - Search research")
        print("   - trends        - Analyze trends")
        print("   - predict       - Show health predictions")
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
                elif cmd == "mine":
                    system.mine_research_data()
                elif cmd.startswith("search "):
                    term = cmd[7:].strip()
                    if term:
                        system.search_research(term)
                    else:
                        print("   Usage: search <term>")
                elif cmd == "trends":
                    system.analyze_research_trends()
                elif cmd == "predict":
                    predictions = system.get_health_predictions("Breast Cancer")
                    print(f"\n{Color.CYAN}📊 Health Predictions" + Color.END)
                    print("=" * 50)
                    for twin, pred in predictions.items():
                        print(f"   {twin}: {pred['risk_level']} risk ({pred['risk']:.2f})")
                    print("=" * 50)
                elif cmd == "demo":
                    system.run_demo()
                elif cmd.startswith("auto"):
                    parts = cmd.split()
                    cycles = int(parts[1]) if len(parts) > 1 else 3
                    system.run_autonomous(cycles)
                elif cmd == "help":
                    print("\n   Available commands:")
                    print("   status        - Show system status")
                    print("   mine          - Mine research data")
                    print("   search <term> - Search research")
                    print("   trends        - Analyze trends")
                    print("   predict       - Show health predictions")
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
