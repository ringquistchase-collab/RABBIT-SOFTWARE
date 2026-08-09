#!/usr/bin/env python3
"""
Maxwell DNA-Twin Medical-Tech Learning Network
===============================================
Save as: maxwell_dna_twin_learning.py
Run:     python3 maxwell_dna_twin_learning.py

FEATURES:
1. DNA Damage/Symptom Detection from Medical-Tech Data
2. Twin-DNA Communication Loop
3. Network Mesh Learning from Data Sets
4. AI Research Communication
5. Damage Pattern Recognition
6. Symptom Mapping to DNA Sequences
7. Cross-Network Data Synchronization
8. Autonomous Learning Cycles
9. Medical-Tech Comparison Engine
10. Real-time Health Monitoring Simulation

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
# 2. DNA DAMAGE/SYMPTOM DETECTOR
# ──────────────────────────────────────────────────────────────

class DNADamageDetector:
    """
    Detects DNA damage and symptoms from medical-tech data.
    Compares network data to DNA patterns.
    """
    
    def __init__(self):
        self.damage_patterns: Dict[str, Dict] = {}
        self.symptom_mappings: Dict[str, List[str]] = defaultdict(list)
        self.detection_history: List[Dict] = []
        self.total_energy = 0.0
        self.damage_level = 0.0
        
        # Medical symptoms mapped to DNA patterns
        self.symptom_to_dna = {
            "inflammation": ["A", "C", "G"],
            "oxidative_stress": ["T", "A", "C"],
            "mutation": ["G", "T", "A"],
            "repair_failure": ["C", "G", "T"],
            "apoptosis": ["A", "T", "G"],
            "aging": ["C", "A", "T"],
            "cancer_risk": ["G", "A", "C"],
            "immune_response": ["T", "G", "A"],
            "neurodegeneration": ["C", "T", "G"],
            "cardiovascular": ["A", "G", "T"]
        }
        
        # Tech patterns mapped to DNA
        self.tech_to_dna = {
            "data_corruption": ["T", "C", "A"],
            "network_failure": ["G", "A", "T"],
            "security_breach": ["C", "G", "A"],
            "algorithm_bias": ["A", "T", "C"],
            "processing_error": ["G", "C", "T"]
        }
    
    def detect_damage(self, medical_data: Dict, tech_data: Dict) -> Dict:
        """Detect DNA damage from medical and tech data."""
        damage_score = 0.0
        detected_symptoms = []
        dna_changes = []
        
        # Analyze medical data
        if medical_data:
            med_damage, med_symptoms, med_changes = self._analyze_medical(medical_data)
            damage_score += med_damage * 0.6
            detected_symptoms.extend(med_symptoms)
            dna_changes.extend(med_changes)
        
        # Analyze tech data
        if tech_data:
            tech_damage, tech_symptoms, tech_changes = self._analyze_tech(tech_data)
            damage_score += tech_damage * 0.4
            detected_symptoms.extend(tech_symptoms)
            dna_changes.extend(tech_changes)
        
        # Normalize damage score
        damage_score = min(1.0, damage_score)
        self.damage_level = damage_score
        
        # Map symptoms to DNA changes
        dna_pattern = self._symptoms_to_dna(detected_symptoms)
        
        detection_result = {
            "damage_score": damage_score,
            "severity": self._get_severity(damage_score),
            "detected_symptoms": detected_symptoms,
            "dna_changes": dna_changes,
            "dna_pattern": dna_pattern,
            "timestamp": get_timestamp()
        }
        
        self.detection_history.append(detection_result)
        self.total_energy += 0.1
        
        return detection_result
    
    def _analyze_medical(self, medical_data: Dict) -> Tuple[float, List[str], List[str]]:
        """Analyze medical data for damage patterns."""
        damage = 0.0
        symptoms = []
        changes = []
        
        if "findings" in medical_data:
            findings = medical_data["findings"]
            if isinstance(findings, dict):
                for key, value in findings.items():
                    if "inflammation" in str(value).lower():
                        damage += 0.3
                        symptoms.append("inflammation")
                    if "mutation" in str(value).lower():
                        damage += 0.4
                        symptoms.append("mutation")
                    if "stress" in str(value).lower():
                        damage += 0.2
                        symptoms.append("oxidative_stress")
                    if "repair" in str(value).lower():
                        damage += 0.1
                        symptoms.append("repair_failure")
        
        if "type" in medical_data:
            if "cancer" in medical_data["type"].lower():
                damage += 0.5
                symptoms.append("cancer_risk")
            if "neuro" in medical_data["type"].lower():
                damage += 0.3
                symptoms.append("neurodegeneration")
            if "cardio" in medical_data["type"].lower():
                damage += 0.2
                symptoms.append("cardiovascular")
        
        # Generate DNA changes from symptoms
        for symptom in symptoms:
            if symptom in self.symptom_to_dna:
                changes.extend(self.symptom_to_dna[symptom])
        
        return min(1.0, damage), list(set(symptoms)), list(set(changes))
    
    def _analyze_tech(self, tech_data: Dict) -> Tuple[float, List[str], List[str]]:
        """Analyze tech data for damage patterns."""
        damage = 0.0
        symptoms = []
        changes = []
        
        if "findings" in tech_data:
            findings = tech_data["findings"]
            if isinstance(findings, dict):
                for key, value in findings.items():
                    if "error" in str(value).lower():
                        damage += 0.3
                        symptoms.append("processing_error")
                    if "failure" in str(value).lower():
                        damage += 0.4
                        symptoms.append("network_failure")
                    if "breach" in str(value).lower():
                        damage += 0.3
                        symptoms.append("security_breach")
        
        if "type" in tech_data:
            if "AI" in tech_data["type"]:
                damage += 0.2
                symptoms.append("algorithm_bias")
            if "blockchain" in tech_data["type"]:
                damage += 0.1
                symptoms.append("data_corruption")
        
        # Generate DNA changes from tech symptoms
        for symptom in symptoms:
            if symptom in self.tech_to_dna:
                changes.extend(self.tech_to_dna[symptom])
        
        return min(1.0, damage), list(set(symptoms)), list(set(changes))
    
    def _symptoms_to_dna(self, symptoms: List[str]) -> str:
        """Convert symptoms to DNA sequence."""
        dna_bases = []
        for symptom in symptoms:
            if symptom in self.symptom_to_dna:
                dna_bases.extend(self.symptom_to_dna[symptom])
            elif symptom in self.tech_to_dna:
                dna_bases.extend(self.tech_to_dna[symptom])
        
        if not dna_bases:
            dna_bases = ["A", "C", "G", "T"]
        
        return "".join(dna_bases[:20])
    
    def _get_severity(self, damage_score: float) -> str:
        """Get severity level from damage score."""
        if damage_score < 0.2:
            return "LOW"
        elif damage_score < 0.5:
            return "MEDIUM"
        elif damage_score < 0.8:
            return "HIGH"
        else:
            return "CRITICAL"
    
    def get_status(self) -> Dict:
        return {
            "damage_level": self.damage_level,
            "detections": len(self.detection_history),
            "total_energy": self.total_energy,
            "last_detection": self.detection_history[-1] if self.detection_history else None
        }


# ──────────────────────────────────────────────────────────────
# 3. TWIN-DNA COMMUNICATION LOOP
# ──────────────────────────────────────────────────────────────

class TwinDNALoop:
    """
    Communication loop between Twin and DNA for learning and relay.
    """
    
    def __init__(self):
        self.communications: List[Dict] = []
        self.twin_state: Dict[str, Any] = {"active": True, "learning_rate": 0.5}
        self.dna_state: Dict[str, Any] = {"active": True, "mutation_rate": 0.1}
        self.loop_active = True
        self.total_energy = 0.0
        self.communication_count = 0
        
        # Communication channels
        self.channels = {
            "damage_channel": {"active": True, "messages": 0},
            "symptom_channel": {"active": True, "messages": 0},
            "learning_channel": {"active": True, "messages": 0},
            "research_channel": {"active": True, "messages": 0}
        }
    
    def send_from_twin(self, message: Dict) -> Dict:
        """Send message from Twin to DNA."""
        communication = {
            "from": "Twin",
            "to": "DNA",
            "message": message,
            "timestamp": get_timestamp(),
            "id": deterministic_hash(message)
        }
        self.communications.append(communication)
        self.communication_count += 1
        self.total_energy += 0.05
        
        # Update twin state
        self.twin_state["last_message"] = get_timestamp()
        self.twin_state["message_count"] = self.communication_count
        
        # Process DNA response
        dna_response = self._process_by_dna(message)
        
        return {
            "status": "sent",
            "communication": communication,
            "dna_response": dna_response
        }
    
    def send_from_dna(self, message: Dict) -> Dict:
        """Send message from DNA to Twin."""
        communication = {
            "from": "DNA",
            "to": "Twin",
            "message": message,
            "timestamp": get_timestamp(),
            "id": deterministic_hash(message)
        }
        self.communications.append(communication)
        self.communication_count += 1
        self.total_energy += 0.05
        
        # Update DNA state
        self.dna_state["last_message"] = get_timestamp()
        self.dna_state["message_count"] = self.communication_count
        
        # Process Twin response
        twin_response = self._process_by_twin(message)
        
        return {
            "status": "sent",
            "communication": communication,
            "twin_response": twin_response
        }
    
    def _process_by_dna(self, message: Dict) -> Dict:
        """Process message from Twin by DNA."""
        # DNA interprets damage/symptom data
        if "damage" in str(message).lower():
            response = {
                "type": "damage_analysis",
                "status": "analyzed",
                "response": "DNA damage patterns detected and mapped",
                "dna_changes": random.sample(["A", "C", "G", "T"], 4)
            }
        elif "symptom" in str(message).lower():
            response = {
                "type": "symptom_mapping",
                "status": "mapped",
                "response": "Symptoms mapped to DNA sequences",
                "dna_sequence": "".join(random.sample(["A", "C", "G", "T"], 10))
            }
        elif "learn" in str(message).lower():
            response = {
                "type": "learning",
                "status": "learning",
                "response": "DNA learning from Twin data",
                "learning_rate": random.uniform(0.1, 0.8)
            }
        elif "research" in str(message).lower():
            response = {
                "type": "research",
                "status": "processed",
                "response": "Research data integrated into DNA",
                "research_findings": random.randint(1, 10)
            }
        else:
            response = {
                "type": "acknowledgment",
                "status": "received",
                "response": "DNA acknowledges Twin message"
            }
        
        self.dna_state["last_response"] = response
        return response
    
    def _process_by_twin(self, message: Dict) -> Dict:
        """Process message from DNA by Twin."""
        # Twin processes DNA data
        if "damage" in str(message).lower():
            response = {
                "type": "damage_confirmation",
                "status": "confirmed",
                "response": "Twin confirms DNA damage detection",
                "severity": random.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"])
            }
        elif "symptom" in str(message).lower():
            response = {
                "type": "symptom_analysis",
                "status": "analyzed",
                "response": "Twin analyzing symptoms from DNA data",
                "symptom_count": random.randint(1, 8)
            }
        elif "learn" in str(message).lower():
            response = {
                "type": "learning_confirmation",
                "status": "confirmed",
                "response": "Twin confirms learning from DNA",
                "learning_rate": random.uniform(0.1, 0.8)
            }
        elif "research" in str(message).lower():
            response = {
                "type": "research_confirmation",
                "status": "confirmed",
                "response": "Twin confirms research data received",
                "research_processed": True
            }
        else:
            response = {
                "type": "acknowledgment",
                "status": "received",
                "response": "Twin acknowledges DNA message"
            }
        
        self.twin_state["last_response"] = response
        return response
    
    def relay_to_ai(self, message: Dict) -> Dict:
        """Relay communication to AI."""
        relay = {
            "from": "Twin-DNA Loop",
            "to": "AI",
            "message": message,
            "timestamp": get_timestamp(),
            "id": deterministic_hash(message)
        }
        
        self.communications.append(relay)
        self.total_energy += 0.05
        
        # Simulate AI response
        ai_response = {
            "type": "AI_analysis",
            "status": "analyzed",
            "insights": f"AI processed {len(str(message))} characters of data",
            "recommendations": random.choice([
                "Monitor DNA damage patterns",
                "Continue learning from Twin",
                "Bridge medical-tech data",
                "Grow network connections"
            ])
        }
        
        return {
            "status": "relayed",
            "relay": relay,
            "ai_response": ai_response
        }
    
    def get_loop_status(self) -> Dict:
        """Get the status of the communication loop."""
        return {
            "total_communications": self.communication_count,
            "twin_state": self.twin_state,
            "dna_state": self.dna_state,
            "loop_active": self.loop_active,
            "total_energy": self.total_energy,
            "channels": self.channels,
            "last_communication": self.communications[-1] if self.communications else None
        }


# ──────────────────────────────────────────────────────────────
# 4. NETWORK MESH LEARNER
# ──────────────────────────────────────────────────────────────

class NetworkMeshLearner:
    """
    Learns from network connections and data sets.
    Compares medical/tech data to DNA patterns.
    """
    
    def __init__(self):
        self.network_nodes: Dict[str, Dict] = {}
        self.connections: Dict[str, List[str]] = defaultdict(list)
        self.learning_history: List[Dict] = []
        self.learned_patterns: Dict[str, Any] = {}
        self.total_energy = 0.0
        self.learning_rate = 0.1
        self.mesh_strength = 0.8
        self.node_count = 0
        
        # Initialize network nodes
        self._initialize_network()
    
    def _initialize_network(self):
        """Initialize network nodes with medical-tech capabilities."""
        node_types = ["medical", "tech", "dna", "twin", "research", "ai"]
        
        for i, node_type in enumerate(node_types):
            node_id = f"NODE_{i+1}_{node_type.upper()}"
            self.network_nodes[node_id] = {
                "type": node_type,
                "active": True,
                "created_at": get_timestamp(),
                "connections": 0,
                "learning_rate": random.uniform(0.1, 0.5)
            }
            self.node_count += 1
        
        # Create connections
        node_ids = list(self.network_nodes.keys())
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                if random.random() < 0.6:
                    self.connections[node_ids[i]].append(node_ids[j])
                    self.connections[node_ids[j]].append(node_ids[i])
                    self.network_nodes[node_ids[i]]["connections"] += 1
                    self.network_nodes[node_ids[j]]["connections"] += 1
    
    def learn_from_data(self, data: Dict, data_type: str = "medical") -> Dict:
        """Learn from medical or tech data through the network."""
        learning_result = {
            "data_type": data_type,
            "nodes_affected": [],
            "patterns_learned": [],
            "energy_used": 0.0
        }
        
        # Propagate learning through network
        for node_id, node in self.network_nodes.items():
            if node["active"]:
                # Each node learns differently based on type
                if node["type"] == "medical" and data_type == "medical":
                    pattern = self._extract_medical_pattern(data)
                    self.learned_patterns[f"{node_id}_medical"] = pattern
                    learning_result["patterns_learned"].append(pattern)
                    learning_result["nodes_affected"].append(node_id)
                
                elif node["type"] == "tech" and data_type == "tech":
                    pattern = self._extract_tech_pattern(data)
                    self.learned_patterns[f"{node_id}_tech"] = pattern
                    learning_result["patterns_learned"].append(pattern)
                    learning_result["nodes_affected"].append(node_id)
                
                elif node["type"] == "dna":
                    pattern = self._extract_dna_pattern(data)
                    self.learned_patterns[f"{node_id}_dna"] = pattern
                    learning_result["patterns_learned"].append(pattern)
                    learning_result["nodes_affected"].append(node_id)
                
                elif node["type"] == "twin":
                    pattern = self._extract_twin_pattern(data)
                    self.learned_patterns[f"{node_id}_twin"] = pattern
                    learning_result["patterns_learned"].append(pattern)
                    learning_result["nodes_affected"].append(node_id)
                
                # Update node energy
                node["learning_rate"] = min(1.0, node.get("learning_rate", 0.1) + 0.01)
                self.total_energy += 0.05
                learning_result["energy_used"] += 0.05
        
        # Store learning history
        self.learning_history.append({
            "data": data,
            "data_type": data_type,
            "result": learning_result,
            "timestamp": get_timestamp()
        })
        
        # Update mesh strength
        self.mesh_strength = min(1.0, self.mesh_strength + 0.01)
        
        return {
            "status": "learned",
            "learning_result": learning_result,
            "mesh_strength": self.mesh_strength
        }
    
    def _extract_medical_pattern(self, data: Dict) -> Dict:
        """Extract medical pattern from data."""
        return {
            "type": "medical_pattern",
            "confidence": random.uniform(0.6, 0.9),
            "symptoms": data.get("symptoms", ["unknown"]),
            "dna_correlation": random.uniform(0.3, 0.8)
        }
    
    def _extract_tech_pattern(self, data: Dict) -> Dict:
        """Extract tech pattern from data."""
        return {
            "type": "tech_pattern",
            "confidence": random.uniform(0.6, 0.9),
            "algorithms": data.get("algorithms", ["unknown"]),
            "dna_correlation": random.uniform(0.3, 0.8)
        }
    
    def _extract_dna_pattern(self, data: Dict) -> Dict:
        """Extract DNA pattern from data."""
        return {
            "type": "dna_pattern",
            "damage_level": random.uniform(0.1, 0.9),
            "mutation_rate": random.uniform(0.01, 0.1),
            "repair_status": random.choice(["active", "delayed", "failed"])
        }
    
    def _extract_twin_pattern(self, data: Dict) -> Dict:
        """Extract Twin pattern from data."""
        return {
            "type": "twin_pattern",
            "sync_status": random.choice(["synced", "desynced"]),
            "learning_rate": random.uniform(0.1, 0.8),
            "memristor_state": [random.uniform(0, 1) for _ in range(3)]
        }
    
    def get_network_status(self) -> Dict:
        """Get network status."""
        return {
            "nodes": self.node_count,
            "active_nodes": len([n for n in self.network_nodes.values() if n["active"]]),
            "connections": sum(len(c) for c in self.connections.values()) // 2,
            "learned_patterns": len(self.learned_patterns),
            "learning_history": len(self.learning_history),
            "mesh_strength": self.mesh_strength,
            "total_energy": self.total_energy
        }


# ──────────────────────────────────────────────────────────────
# 5. AI RESEARCH COMMUNICATION
# ──────────────────────────────────────────────────────────────

class AIResearchCommunication:
    """
    AI communication for research with DNA and Twin data.
    """
    
    def __init__(self):
        self.research_data: List[Dict] = []
        self.ai_insights: List[Dict] = []
        self.dna_reports: List[Dict] = []
        self.twin_reports: List[Dict] = []
        self.total_energy = 0.0
        self.communication_count = 0
        self.ai_active = True
        
        # Research categories
        self.research_categories = [
            "Oncology", "Neurology", "Cardiology", "Genomics",
            "Immunology", "Pharmacology", "Bioinformatics", "AI_Medicine"
        ]
    
    def process_research_data(self, data: Dict, source: str = "unknown") -> Dict:
        """Process research data from DNA or Twin."""
        research_entry = {
            "source": source,
            "data": data,
            "timestamp": get_timestamp(),
            "id": deterministic_hash(data)
        }
        self.research_data.append(research_entry)
        self.communication_count += 1
        self.total_energy += 0.1
        
        # Generate AI insight
        insight = self._generate_insight(data, source)
        self.ai_insights.append(insight)
        
        return {
            "status": "processed",
            "entry": research_entry,
            "insight": insight
        }
    
    def _generate_insight(self, data: Dict, source: str) -> Dict:
        """Generate AI insight from research data."""
        if "damage" in str(data).lower():
            insight_type = "damage_analysis"
            content = f"AI detected DNA damage patterns from {source}"
            severity = random.choice(["LOW", "MEDIUM", "HIGH"])
        elif "symptom" in str(data).lower():
            insight_type = "symptom_analysis"
            content = f"AI mapped symptoms to DNA sequences from {source}"
            severity = random.choice(["LOW", "MEDIUM", "HIGH"])
        elif "learning" in str(data).lower():
            insight_type = "learning_analysis"
            content = f"AI learning from {source} data"
            severity = "LOW"
        else:
            insight_type = "general_analysis"
            content = f"AI processed research data from {source}"
            severity = "LOW"
        
        return {
            "type": insight_type,
            "content": content,
            "severity": severity,
            "confidence": random.uniform(0.6, 0.95),
            "recommendations": self._generate_recommendations(insight_type),
            "timestamp": get_timestamp()
        }
    
    def _generate_recommendations(self, insight_type: str) -> List[str]:
        """Generate recommendations based on insight type."""
        recommendations = {
            "damage_analysis": [
                "Monitor DNA damage patterns",
                "Initiate repair protocols",
                "Alert Twin system",
                "Update research database"
            ],
            "symptom_analysis": [
                "Map symptoms to DNA sequences",
                "Compare with medical database",
                "Update Twin mirror",
                "Generate health report"
            ],
            "learning_analysis": [
                "Continue learning cycle",
                "Share patterns with network",
                "Update AI model",
                "Save learning data"
            ],
            "general_analysis": [
                "Process research data",
                "Update blockchain",
                "Share with network",
                "Save to research store"
            ]
        }
        
        return random.sample(recommendations.get(insight_type, recommendations["general_analysis"]), 3)
    
    def generate_dna_report(self, dna_data: Dict) -> Dict:
        """Generate report from DNA data."""
        report = {
            "type": "DNA_Research_Report",
            "damage_level": dna_data.get("damage_level", 0),
            "symptoms": dna_data.get("symptoms", []),
            "dna_pattern": dna_data.get("dna_pattern", ""),
            "timestamp": get_timestamp(),
            "report_id": deterministic_hash(dna_data)
        }
        self.dna_reports.append(report)
        return report
    
    def generate_twin_report(self, twin_data: Dict) -> Dict:
        """Generate report from Twin data."""
        report = {
            "type": "Twin_Research_Report",
            "sync_status": twin_data.get("sync_status", "unknown"),
            "learning_rate": twin_data.get("learning_rate", 0),
            "memristor_state": twin_data.get("memristor_state", []),
            "timestamp": get_timestamp(),
            "report_id": deterministic_hash(twin_data)
        }
        self.twin_reports.append(report)
        return report
    
    def get_ai_status(self) -> Dict:
        """Get AI communication status."""
        return {
            "research_data": len(self.research_data),
            "ai_insights": len(self.ai_insights),
            "dna_reports": len(self.dna_reports),
            "twin_reports": len(self.twin_reports),
            "communication_count": self.communication_count,
            "total_energy": self.total_energy,
            "ai_active": self.ai_active
        }


# ──────────────────────────────────────────────────────────────
# 6. MAIN SYSTEM - DNA-TWIN MEDICAL-TECH LEARNING
# ──────────────────────────────────────────────────────────────

class DNATwinMedicalTechSystem:
    """
    Complete system integrating DNA, Twin, Medical, Tech, and AI.
    """
    
    def __init__(self):
        print("\n" + "=" * 70)
        print(Color.HEADER + "🧬 DNA-TWIN MEDICAL-TECH LEARNING SYSTEM" + Color.END)
        print(Color.CYAN + "   Damage Detection + Learning + AI Communication" + Color.END)
        print("=" * 70)
        
        # Initialize components
        print(Color.CYAN + "🔬 Initializing DNA Damage Detector..." + Color.END)
        self.damage_detector = DNADamageDetector()
        
        print(Color.CYAN + "🔄 Initializing Twin-DNA Communication Loop..." + Color.END)
        self.twin_dna_loop = TwinDNALoop()
        
        print(Color.CYAN + "🌐 Initializing Network Mesh Learner..." + Color.END)
        self.network_learner = NetworkMeshLearner()
        
        print(Color.CYAN + "🤖 Initializing AI Research Communication..." + Color.END)
        self.ai_comm = AIResearchCommunication()
        
        self.total_energy = 50.0
        self.total_learning = 0.0
        self.detection_count = 0
        
        print(Color.GREEN + "✅ DNA-Twin Medical-Tech System initialized" + Color.END)
        print("=" * 70 + "\n")
    
    def run_detection_cycle(self, medical_data: Dict = None, tech_data: Dict = None) -> Dict:
        """Run a complete detection and learning cycle."""
        print(f"\n{Color.YELLOW}🔬 Running Detection Cycle" + Color.END)
        print("─" * 50)
        
        # Generate sample data if not provided
        if medical_data is None:
            medical_data = {
                "type": random.choice(["oncology", "neurology", "cardiology", "genomics"]),
                "findings": {
                    "biomarker": f"BM_{random.randint(100, 999)}",
                    "expression": random.uniform(0.1, 0.9),
                    "mutation": random.choice(["BRCA1", "TP53", "EGFR", "KRAS"])
                },
                "symptoms": random.sample(["inflammation", "oxidative_stress", "mutation", "repair_failure"], 2)
            }
        
        if tech_data is None:
            tech_data = {
                "type": random.choice(["AI", "blockchain", "bioinformatics", "IoT"]),
                "findings": {
                    "algorithm": f"ALG_{random.randint(100, 999)}",
                    "accuracy": random.uniform(0.7, 0.95),
                    "data_size": random.randint(100, 10000)
                },
                "algorithms": random.sample(["CNN", "LSTM", "Transformer", "GraphNN"], 2)
            }
        
        # 1. Detect damage
        print(f"\n{Color.BOLD}Step 1: Detecting DNA Damage" + Color.END)
        detection = self.damage_detector.detect_damage(medical_data, tech_data)
        self.detection_count += 1
        print(f"   Damage Score: {detection['damage_score']:.2f}")
        print(f"   Severity: {detection['severity']}")
        print(f"   Symptoms: {', '.join(detection['detected_symptoms'])}")
        
        # 2. Twin-DNA Communication
        print(f"\n{Color.BOLD}Step 2: Twin-DNA Communication" + Color.END)
        
        # Twin sends damage data to DNA
        twin_message = {
            "type": "damage_report",
            "damage_score": detection['damage_score'],
            "symptoms": detection['detected_symptoms'],
            "severity": detection['severity']
        }
        twin_result = self.twin_dna_loop.send_from_twin(twin_message)
        print(f"   Twin → DNA: {twin_result['status']}")
        
        # DNA sends learning data to Twin
        dna_message = {
            "type": "learning_data",
            "dna_pattern": detection['dna_pattern'],
            "symptoms": detection['detected_symptoms'],
            "learning_rate": random.uniform(0.1, 0.8)
        }
        dna_result = self.twin_dna_loop.send_from_dna(dna_message)
        print(f"   DNA → Twin: {dna_result['status']}")
        
        # 3. Network Learning
        print(f"\n{Color.BOLD}Step 3: Network Learning" + Color.END)
        learn_result = self.network_learner.learn_from_data({
            "medical": medical_data,
            "tech": tech_data,
            "detection": detection
        }, "medical")
        print(f"   Mesh Strength: {learn_result['mesh_strength']:.2f}")
        print(f"   Nodes Affected: {len(learn_result['learning_result']['nodes_affected'])}")
        
        # 4. AI Communication
        print(f"\n{Color.BOLD}Step 4: AI Research Communication" + Color.END)
        ai_result = self.ai_comm.process_research_data({
            "detection": detection,
            "medical": medical_data,
            "tech": tech_data,
            "twin_loop": self.twin_dna_loop.get_loop_status(),
            "network": self.network_learner.get_network_status()
        }, "DNA-Twin System")
        
        print(f"   AI Insight: {ai_result['insight']['content']}")
        print(f"   Recommendations: {', '.join(ai_result['insight']['recommendations'])}")
        
        # 5. Update system energy
        self.total_energy += 0.5
        self.total_learning += 0.1
        
        return {
            "status": "complete",
            "detection": detection,
            "twin_communication": {"twin_to_dna": twin_result, "dna_to_twin": dna_result},
            "learning": learn_result,
            "ai_communication": ai_result,
            "energy": self.total_energy,
            "learning_progress": self.total_learning
        }
    
    def show_status(self):
        """Show system status."""
        print(f"\n{Color.CYAN}📊 SYSTEM STATUS" + Color.END)
        print("=" * 70)
        
        print(f"\n{Color.BOLD}🔬 DNA Damage Detector:" + Color.END)
        damage_status = self.damage_detector.get_status()
        print(f"   Damage Level: {damage_status['damage_level']:.2f}")
        print(f"   Detections: {damage_status['detections']}")
        
        print(f"\n{Color.BOLD}🔄 Twin-DNA Loop:" + Color.END)
        loop_status = self.twin_dna_loop.get_loop_status()
        print(f"   Communications: {loop_status['total_communications']}")
        print(f"   Loop Active: {loop_status['loop_active']}")
        print(f"   Channels: {len(loop_status['channels'])}")
        
        print(f"\n{Color.BOLD}🌐 Network Mesh:" + Color.END)
        network_status = self.network_learner.get_network_status()
        print(f"   Nodes: {network_status['nodes']}")
        print(f"   Connections: {network_status['connections']}")
        print(f"   Mesh Strength: {network_status['mesh_strength']:.2f}")
        print(f"   Learned Patterns: {network_status['learned_patterns']}")
        
        print(f"\n{Color.BOLD}🤖 AI Communication:" + Color.END)
        ai_status = self.ai_comm.get_ai_status()
        print(f"   Research Data: {ai_status['research_data']}")
        print(f"   AI Insights: {ai_status['ai_insights']}")
        print(f"   DNA Reports: {ai_status['dna_reports']}")
        print(f"   Twin Reports: {ai_status['twin_reports']}")
        
        print(f"\n{Color.BOLD}📊 System:" + Color.END)
        print(f"   Total Energy: {self.total_energy:.2f}")
        print(f"   Learning Progress: {self.total_learning:.2f}")
        print(f"   Detection Count: {self.detection_count}")
        
        print("\n" + "=" * 70)
    
    def run_demo(self):
        """Run a full demonstration."""
        print("\n" + "=" * 70)
        print(Color.CYAN + "🧪 SYSTEM DEMONSTRATION" + Color.END)
        print("=" * 70)
        
        # Run detection cycles
        print(f"\n{Color.BOLD}Running Detection Cycles" + Color.END)
        for i in range(3):
            print(f"\n{Color.YELLOW}--- Cycle {i+1} ---" + Color.END)
            self.run_detection_cycle()
            time.sleep(0.3)
        
        # Generate reports
        print(f"\n{Color.BOLD}Generating Reports" + Color.END)
        
        # DNA Report
        dna_report = self.ai_comm.generate_dna_report({
            "damage_level": self.damage_detector.damage_level,
            "symptoms": ["inflammation", "oxidative_stress"],
            "dna_pattern": "ACGTACGTACGT"
        })
        print(f"   DNA Report: {dna_report['report_id'][:16]}...")
        
        # Twin Report
        twin_report = self.ai_comm.generate_twin_report({
            "sync_status": "synced",
            "learning_rate": 0.5,
            "memristor_state": [0.4, 0.6, 0.5]
        })
        print(f"   Twin Report: {twin_report['report_id'][:16]}...")
        
        # Show status
        self.show_status()
        
        print("\n" + "=" * 70)
        print(Color.GREEN + "✅ DEMONSTRATION COMPLETE" + Color.END)
        print("=" * 70)


# ──────────────────────────────────────────────────────────────
# 7. MAIN
# ──────────────────────────────────────────────────────────────

def main():
    try:
        system = DNATwinMedicalTechSystem()
        
        print("\n" + "=" * 70)
        print(Color.BOLD + "🧬 SYSTEM READY" + Color.END)
        print("   Commands:")
        print("   - status        - Show system status")
        print("   - detect        - Run detection cycle")
        print("   - demo          - Run full demonstration")
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
                elif cmd == "detect":
                    system.run_detection_cycle()
                elif cmd == "demo":
                    system.run_demo()
                elif cmd == "help":
                    print("\n   Available commands:")
                    print("   status        - Show system status")
                    print("   detect        - Run detection cycle")
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
