"""
Integrated person profile: DNA + medical history + family history.

Design principle: full sensitive data (genomics, medical history, family
history) is NEVER put directly on-chain. It lives in an access-controlled
"off-chain store" (here, a local JSON file standing in for a real encrypted
database / FHIR server). The blockchain only ever receives:
    - a one-way hash of the person's identifier (not the identifier itself)
    - a one-way hash of the full record (proves integrity/existence without
      exposing content)
    - the minimal derived clinical output (risk score, mutation burden)

This means the chain can prove "this exact record existed, unaltered, at
this time" without ever holding, replicating, or leaking the underlying PHI
to every node in the network -- which a naive "put everything on-chain"
design cannot do (you can't delete/redact data from an immutable ledger,
and every node ends up holding a full copy of everyone's medical history).

All data in this module is SYNTHETIC. Do not populate this with a real
person's real medical/genomic data without proper consent, encryption, and
regulatory review (HIPAA/GDPR) -- this demo intentionally stays fictional.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MedicalHistoryEntry:
    condition: str
    diagnosed_year: int
    status: str  # "active", "resolved", "chronic"


@dataclass
class FamilyHistoryEntry:
    relation: str        # "mother", "father", "sibling", "maternal grandmother", ...
    condition: str
    age_at_onset: int


@dataclass
class PersonProfile:
    person_id: str                 # internal identifier -- never put raw on-chain
    age: int
    sex: str
    nutrition_score: float
    days_since_diagnosis: int
    dna_sample_id: str
    medical_history: List[MedicalHistoryEntry] = field(default_factory=list)
    family_history: List[FamilyHistoryEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Off-chain secure store (stand-in for a real encrypted EHR/genomic database)
# ---------------------------------------------------------------------------

class OffChainStore:
    """
    Stand-in for a real secure system (encrypted DB, FHIR server, access
    control, audit logging). This demo version just writes JSON to disk --
    that is NOT sufficient for real PHI, it only demonstrates the
    on-chain/off-chain split.
    """

    def __init__(self, path: str = "offchain_store.json"):
        self.path = path
        if not os.path.exists(self.path):
            with open(self.path, "w") as f:
                json.dump({}, f)

    def _read_all(self) -> Dict[str, Any]:
        with open(self.path, "r") as f:
            return json.load(f)

    def _write_all(self, data: Dict[str, Any]) -> None:
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def save_bundle(self, record_hash: str, bundle: Dict[str, Any]) -> None:
        data = self._read_all()
        data[record_hash] = bundle
        self._write_all(data)

    def get_bundle(self, record_hash: str) -> Dict[str, Any]:
        data = self._read_all()
        return data.get(record_hash)


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def sha256_obj(obj: Dict[str, Any]) -> str:
    return sha256_str(json.dumps(obj, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# Risk scoring extended with family history
# ---------------------------------------------------------------------------

HEREDITARY_CANCER_TERMS = {"breast cancer", "ovarian cancer", "colorectal cancer",
                            "pancreatic cancer", "prostate cancer", "melanoma"}


def family_history_factor(family_history: List[FamilyHistoryEntry]) -> float:
    """
    Toy heuristic: each first-degree relative (parent/sibling) with a
    hereditary-pattern cancer, especially early-onset, nudges risk up. Real
    versions of this exist (e.g. Gail model, Tyrer-Cuzick, BRCAPRO) and are
    validated on real epidemiological data -- this is illustrative only.
    """
    first_degree = {"mother", "father", "sibling", "brother", "sister"}
    factor = 1.0
    for entry in family_history:
        if entry.condition.lower() in HEREDITARY_CANCER_TERMS:
            bump = 0.15 if entry.relation.lower() in first_degree else 0.07
            if entry.age_at_onset < 50:
                bump *= 1.5  # early onset weighted higher
            factor += bump
    return round(factor, 3)


def medical_history_factor(medical_history: List[MedicalHistoryEntry]) -> float:
    """Toy: active chronic conditions relevant to DNA repair / immune
    surveillance nudge risk slightly. Illustrative only."""
    relevant = {"diabetes", "chronic inflammation", "immunodeficiency", "prior cancer"}
    factor = 1.0
    for entry in medical_history:
        if entry.condition.lower() in relevant and entry.status in ("active", "chronic"):
            factor += 0.05
    return round(factor, 3)


# ---------------------------------------------------------------------------
# Build the on-chain record (minimal) + off-chain bundle (full)
# ---------------------------------------------------------------------------

def build_integrated_record(profile: PersonProfile, trajectory: Dict[str, Any],
                             base_risk_score: float, store: OffChainStore) -> Dict[str, Any]:
    """
    Combines genomics (trajectory), medical history, and family history into
    one adjusted risk assessment. Returns ONLY the minimal on-chain record.
    The full bundle (with all identifying/clinical detail) is written to the
    off-chain store, referenced on-chain by hash only.
    """
    fam_factor = family_history_factor(profile.family_history)
    med_factor = medical_history_factor(profile.medical_history)
    adjusted_risk = round(min(1.0, base_risk_score * fam_factor * med_factor), 4)

    full_bundle = {
        "profile": profile.to_dict(),
        "trajectory": trajectory,
        "base_risk_score": base_risk_score,
        "family_history_factor": fam_factor,
        "medical_history_factor": med_factor,
        "adjusted_risk_score": adjusted_risk,
        "generated_at": time.time(),
    }
    bundle_hash = sha256_obj(full_bundle)
    store.save_bundle(bundle_hash, full_bundle)

    on_chain_record = {
        "person_id_hash": sha256_str(profile.person_id),
        "off_chain_ref": bundle_hash,       # pointer + integrity proof, no raw content
        "tumor_mutation_burden": trajectory["tumor_mutation_burden"],
        "adjusted_risk_score": adjusted_risk,
        "timestamp": time.time(),
    }
    return on_chain_record


def verify_offchain_integrity(record: Dict[str, Any], store: OffChainStore) -> bool:
    """Given an on-chain record, fetches the referenced off-chain bundle and
    confirms its hash still matches -- proves the off-chain data hasn't been
    silently altered since the on-chain record was created."""
    bundle = store.get_bundle(record["off_chain_ref"])
    if bundle is None:
        return False
    return sha256_obj(bundle) == record["off_chain_ref"]
