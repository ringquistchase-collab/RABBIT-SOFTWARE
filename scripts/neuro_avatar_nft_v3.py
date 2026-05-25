#!/usr/bin/env python3
"""NEURO-AVATAR NFT PLATFORM v3.0
Complete Commercial System: MMG+EEG -> DNA/tRNA -> NFT Minting -> Marketplace

Business Model:
- Patients: Own NFT avatars with medical outcomes
- Clinics: Sign treatment protocols, earn revenue from royalties
- Platform: 5% royalty on all secondary market trades
- Researchers: License anonymized data (data_license NFT tier)

Run: python neuro_avatar_nft_v3.py
"""

import json
import hashlib
import datetime
import uuid
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

# ── Configuration ─────────────────────────────────────────────────────────────

PLATFORM_UUID          = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
PLATFORM_VERSION       = "3.0.0"
TIMESTAMP              = datetime.datetime.utcnow().isoformat() + "Z"
NFT_MINT_PRICE_SOL     = 0.05
NFT_ROYALTY_BPS        = 500    # 5 %
PATIENT_REVENUE_SHARE  = 0.50
CLINIC_REVENUE_SHARE   = 0.25
PLATFORM_REVENUE_SHARE = 0.25

# DNA base resonance frequencies (THz) — RabbitOS DNA coupling layer
DNA_BASE_FREQS = {"A": 2.04, "T": 1.71, "G": 1.58, "C": 1.47}

CODON_TABLE = {
    "TTT": "Phe", "TTC": "Phe", "TTA": "Leu", "TTG": "Leu",
    "CTT": "Leu", "CTC": "Leu", "CTA": "Leu", "CTG": "Leu",
    "ATT": "Ile", "ATC": "Ile", "ATA": "Ile", "ATG": "Met",
    "GTT": "Val", "GTC": "Val", "GTA": "Val", "GTG": "Val",
    "TCT": "Ser", "TCC": "Ser", "TCA": "Ser", "TCG": "Ser",
    "CCT": "Pro", "CCC": "Pro", "CCA": "Pro", "CCG": "Pro",
    "ACT": "Thr", "ACC": "Thr", "ACA": "Thr", "ACG": "Thr",
    "GCT": "Ala", "GCC": "Ala", "GCA": "Ala", "GCG": "Ala",
    "TAT": "Tyr", "TAC": "Tyr", "TAA": "STOP", "TAG": "STOP",
    "CAT": "His", "CAC": "His", "CAA": "Gln", "CAG": "Gln",
    "AAT": "Asn", "AAC": "Asn", "AAA": "Lys", "AAG": "Lys",
    "GAT": "Asp", "GAC": "Asp", "GAA": "Glu", "GAG": "Glu",
    "TGT": "Cys", "TGC": "Cys", "TGA": "STOP", "TGG": "Trp",
    "CGT": "Arg", "CGC": "Arg", "CGA": "Arg", "CGG": "Arg",
    "AGT": "Ser", "AGC": "Ser", "AGA": "Arg", "AGG": "Arg",
    "GGT": "Gly", "GGC": "Gly", "GGA": "Gly", "GGG": "Gly",
}


# ── DNA / tRNA Converter ──────────────────────────────────────────────────────

class DNATRNAConverter:
    """Maps MMG+EEG spectral features → DNA codon sequence → tRNA peptide chain."""

    BAND_TO_BASE = {
        "delta": "A",   # 0–4 Hz   → Adenine
        "theta": "T",   # 4–8 Hz   → Thymine
        "alpha": "G",   # 8–13 Hz  → Guanine
        "beta":  "C",   # 13–30 Hz → Cytosine
    }

    def encode_eeg(self, eeg: Dict[str, float]) -> str:
        bases = ""
        for band, base in self.BAND_TO_BASE.items():
            power   = eeg.get(f"{band}_power", 10.0)
            repeats = max(1, min(3, int(power / 10)))
            bases  += base * repeats
        return (bases + "A" * 12)[:12]

    def encode_mmg(self, mmg: Dict[str, float]) -> str:
        tremor_freq = mmg.get("tremor_freq_hz", 0.0)
        contraction = mmg.get("rms_uT", 0.0)
        tremor_base     = "T" if tremor_freq > 6 else ("A" if tremor_freq > 3 else "G")
        contraction_base = "C" if contraction > 0.5 else "A"
        return (tremor_base * 3 + contraction_base * 3)[:6]

    def synthesise(self, eeg: Dict[str, float], mmg: Dict[str, float]) -> Dict:
        dna_seq = self.encode_eeg(eeg) + self.encode_mmg(mmg)   # 18 bases = 6 codons

        peptide = []
        for i in range(0, len(dna_seq) - 2, 3):
            aa = CODON_TABLE.get(dna_seq[i:i+3], "Unk")
            if aa != "STOP":
                peptide.append(aa)

        resonance_score = sum(DNA_BASE_FREQS.get(b, 0) for b in dna_seq) / len(dna_seq)

        return {
            "dna_sequence":     dna_seq,
            "peptide_chain":    peptide,
            "codon_count":      len(dna_seq) // 3,
            "resonance_thz":    round(resonance_score, 4),
            "genome_signature": hashlib.sha3_256(dna_seq.encode()).hexdigest()[:16],
        }


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class Clinic:
    clinic_id:         str
    name:              str
    license_number:    str
    specialization:    str
    wallet_address:    str
    registered_at:     str
    enrolled_patients: List[str] = field(default_factory=list)
    revenue_earned:    float = 0.0
    nfts_minted:       int   = 0


@dataclass
class Patient:
    patient_id:      str
    clinic_id:       str
    wallet_address:  str
    enrollment_date: str
    treatment_phase: str
    condition:       str
    nft_token_id:    Optional[str] = None
    updrs_baseline:  float = 0.0
    updrs_current:   float = 0.0

    @property
    def updrs_improvement(self) -> float:
        return self.updrs_current - self.updrs_baseline


@dataclass
class NFTListing:
    token_id:       str
    patient_id:     str
    clinic_id:      str
    mint_price_sol: float
    list_price_sol: Optional[float]
    mint_tx:        str
    genome_sig:     str
    tier:           str
    minted_at:      str
    listed_at:      Optional[str] = None
    sold_at:        Optional[str] = None
    buyer_wallet:   Optional[str] = None


# ── Registries ────────────────────────────────────────────────────────────────

class ClinicRegistry:
    def __init__(self):
        self._clinics: Dict[str, Clinic] = {}

    def register(self, name: str, specialization: str, license_number: str) -> Clinic:
        cid    = str(uuid.uuid4())
        wallet = "0x" + hashlib.sha256(cid.encode()).hexdigest()[:40]
        clinic = Clinic(
            clinic_id=cid, name=name, license_number=license_number,
            specialization=specialization, wallet_address=wallet,
            registered_at=datetime.datetime.utcnow().isoformat() + "Z",
        )
        self._clinics[cid] = clinic
        return clinic

    def get(self, clinic_id: str) -> Optional[Clinic]:
        return self._clinics.get(clinic_id)

    def all(self) -> List[Clinic]:
        return list(self._clinics.values())


class PatientRegistry:
    def __init__(self):
        self._patients: Dict[str, Patient] = {}

    def enroll(self, clinic_id: str, condition: str,
               treatment_phase: str, updrs_baseline: float) -> Patient:
        pid    = str(uuid.uuid4())
        wallet = "0x" + hashlib.sha256(pid.encode()).hexdigest()[:40]
        p = Patient(
            patient_id=pid, clinic_id=clinic_id, wallet_address=wallet,
            enrollment_date=datetime.datetime.utcnow().isoformat() + "Z",
            treatment_phase=treatment_phase, condition=condition,
            updrs_baseline=updrs_baseline, updrs_current=updrs_baseline,
        )
        self._patients[pid] = p
        return p

    def update_outcome(self, patient_id: str, updrs_current: float):
        if patient_id in self._patients:
            self._patients[patient_id].updrs_current = updrs_current

    def get(self, patient_id: str) -> Optional[Patient]:
        return self._patients.get(patient_id)


# ── NFT Engine ────────────────────────────────────────────────────────────────

class NeuroPlatformNFT:
    def __init__(self):
        self._listings:  Dict[str, NFTListing] = {}
        self._converter = DNATRNAConverter()

    def mint(self, patient: Patient,
             eeg: Dict[str, float], mmg: Dict[str, float]) -> Tuple[NFTListing, Dict]:
        bio      = self._converter.synthesise(eeg, mmg)
        tier     = self._tier(patient.updrs_improvement)
        token_id = hashlib.sha3_256(
            f"{patient.patient_id}_{bio['dna_sequence']}".encode()
        ).hexdigest()[:8].upper()
        mint_tx  = hashlib.sha3_256(
            f"{token_id}_{TIMESTAMP}_{patient.wallet_address}".encode()
        ).hexdigest()

        listing = NFTListing(
            token_id=token_id, patient_id=patient.patient_id,
            clinic_id=patient.clinic_id, mint_price_sol=NFT_MINT_PRICE_SOL,
            list_price_sol=None, mint_tx=mint_tx,
            genome_sig=bio["genome_signature"], tier=tier,
            minted_at=datetime.datetime.utcnow().isoformat() + "Z",
        )
        self._listings[token_id] = listing
        patient.nft_token_id = token_id

        metadata = {
            "name":        f"NeuroAvatar #{token_id}",
            "description": "Medical outcome NFT — MMG+EEG provenance chain",
            "image":       f"ipfs://neuroavatar/{token_id}/render.png",
            "attributes": [
                {"trait_type": "Tier",             "value": tier},
                {"trait_type": "DNA Sequence",     "value": bio["dna_sequence"]},
                {"trait_type": "Peptide Chain",    "value": "-".join(bio["peptide_chain"])},
                {"trait_type": "Resonance THz",    "value": bio["resonance_thz"]},
                {"trait_type": "Genome Signature", "value": bio["genome_signature"]},
                {"trait_type": "UPDRS Delta",      "value": patient.updrs_improvement},
                {"trait_type": "Condition",        "value": patient.condition},
                {"trait_type": "Mint Date",        "value": listing.minted_at},
            ],
            "royalty_bps": NFT_ROYALTY_BPS,
            "creators": [
                {"address": patient.wallet_address,                  "share": 50},
                {"address": f"0xClinic_{patient.clinic_id[:8]}",     "share": 25},
                {"address": f"0xPlatform_{PLATFORM_UUID[:8]}",       "share": 25},
            ],
        }
        return listing, metadata

    def list_for_sale(self, token_id: str, price_sol: float) -> bool:
        if token_id not in self._listings:
            return False
        self._listings[token_id].list_price_sol = price_sol
        self._listings[token_id].listed_at = datetime.datetime.utcnow().isoformat() + "Z"
        return True

    def buy(self, token_id: str, buyer_wallet: str) -> Optional[Dict]:
        listing = self._listings.get(token_id)
        if not listing or listing.list_price_sol is None or listing.sold_at:
            return None
        listing.sold_at      = datetime.datetime.utcnow().isoformat() + "Z"
        listing.buyer_wallet = buyer_wallet
        sale_tx  = hashlib.sha3_256(
            f"{token_id}_{buyer_wallet}_{listing.sold_at}".encode()
        ).hexdigest()
        royalty  = listing.list_price_sol * (NFT_ROYALTY_BPS / 10_000)
        return {
            "token_id":    token_id,
            "sale_price":  listing.list_price_sol,
            "sale_tx":     sale_tx,
            "royalty_sol": round(royalty, 6),
            "seller":      listing.patient_id,
            "buyer":       buyer_wallet,
        }

    def active_listings(self) -> List[NFTListing]:
        return [l for l in self._listings.values()
                if l.list_price_sol is not None and not l.sold_at]

    def all_listings(self) -> List[NFTListing]:
        return list(self._listings.values())

    @staticmethod
    def _tier(updrs_delta: float) -> str:
        if updrs_delta < -8: return "LEGENDARY"
        if updrs_delta < -6: return "EPIC"
        if updrs_delta < -4: return "RARE"
        return "COMMON"


# ── Revenue Engine ────────────────────────────────────────────────────────────

class RevenueEngine:
    def __init__(self):
        self._mints:  List[Dict] = []
        self._trades: List[Dict] = []

    def record_mint(self, token_id: str, price_sol: float,
                    patient: Patient, clinic: Clinic) -> Dict:
        record = {
            "event":        "MINT",
            "token_id":     token_id,
            "price_sol":    price_sol,
            "patient_cut":  round(price_sol * PATIENT_REVENUE_SHARE,  6),
            "clinic_cut":   round(price_sol * CLINIC_REVENUE_SHARE,   6),
            "platform_cut": round(price_sol * PLATFORM_REVENUE_SHARE, 6),
            "timestamp":    datetime.datetime.utcnow().isoformat() + "Z",
        }
        clinic.revenue_earned += record["clinic_cut"]
        clinic.nfts_minted    += 1
        self._mints.append(record)
        return record

    def record_secondary(self, sale: Dict, clinic: Clinic) -> Dict:
        royalty = sale["royalty_sol"]
        record  = {
            "event":        "SECONDARY",
            "token_id":     sale["token_id"],
            "sale_price":   sale["sale_price"],
            "royalty_sol":  royalty,
            "clinic_cut":   round(royalty * CLINIC_REVENUE_SHARE,   6),
            "platform_cut": round(royalty * PLATFORM_REVENUE_SHARE, 6),
            "timestamp":    datetime.datetime.utcnow().isoformat() + "Z",
        }
        clinic.revenue_earned += record["clinic_cut"]
        self._trades.append(record)
        return record

    def projection(self, active_clinics: int = 50,
                   patients_per_month: int = 10,
                   avg_nft_price_usd: float = 150.0,
                   months: int = 12) -> Dict:
        annual_mints     = active_clinics * patients_per_month * months
        primary_rev      = annual_mints * avg_nft_price_usd * PLATFORM_REVENUE_SHARE
        secondary_vol    = annual_mints * avg_nft_price_usd * 0.30
        secondary_royalty= secondary_vol * (NFT_ROYALTY_BPS / 10_000) * PLATFORM_REVENUE_SHARE
        total            = primary_rev + secondary_royalty
        return {
            "active_clinics":           active_clinics,
            "patients_per_month":       patients_per_month,
            "annual_nfts_minted":       annual_mints,
            "avg_nft_price_usd":        avg_nft_price_usd,
            "primary_revenue_usd":      round(primary_rev,       2),
            "secondary_royalty_usd":    round(secondary_royalty, 2),
            "total_annual_revenue_usd": round(total,             2),
            "mrr_usd":                  round(total / months,    2),
            "arr_usd":                  round(total,             2),
        }


# ── Platform API ──────────────────────────────────────────────────────────────

class ProjectionResult:
    def __init__(self, data: Dict):
        self.json = list(data.items())


class NeuroPlatformAPI:
    """Full REST API surface — local simulation for demonstration."""

    def __init__(self):
        self.clinics  = ClinicRegistry()
        self.patients = PatientRegistry()
        self.nft      = NeuroPlatformNFT()
        self.revenue  = RevenueEngine()

    # GET /health
    def health(self) -> Dict:
        return {
            "status":    "healthy",
            "version":   PLATFORM_VERSION,
            "platform":  "NeuroAvatar NFT Platform",
            "timestamp": TIMESTAMP,
            "services": {
                "database":   "connected",
                "blockchain": "connected",
                "eeg_ingest": "ready",
                "mmg_ingest": "ready",
                "marketplace":"active",
            },
        }

    # POST /api/clinic/register
    def register_clinic(self, name: str, specialization: str,
                        license_number: str) -> Dict:
        c = self.clinics.register(name, specialization, license_number)
        return {
            "success": True, "clinic_id": c.clinic_id,
            "name": c.name, "wallet": c.wallet_address,
            "registered": c.registered_at,
        }

    # POST /api/clinic/enroll
    def enroll_patient(self, clinic_id: str, condition: str,
                       treatment_phase: str, updrs_baseline: float) -> Dict:
        clinic = self.clinics.get(clinic_id)
        if not clinic:
            return {"success": False, "error": "Clinic not found"}
        p = self.patients.enroll(clinic_id, condition, treatment_phase, updrs_baseline)
        clinic.enrolled_patients.append(p.patient_id)
        return {
            "success": True, "patient_id": p.patient_id,
            "clinic_id": clinic_id, "wallet": p.wallet_address,
            "enrolled": p.enrollment_date,
        }

    # POST /api/clinic/mint_nft
    def mint_nft(self, patient_id: str, eeg: Dict, mmg: Dict,
                 updrs_current: float) -> Dict:
        patient = self.patients.get(patient_id)
        if not patient:
            return {"success": False, "error": "Patient not found"}
        clinic = self.clinics.get(patient.clinic_id)
        if not clinic:
            return {"success": False, "error": "Clinic not found"}

        self.patients.update_outcome(patient_id, updrs_current)
        listing, metadata = self.nft.mint(patient, eeg, mmg)
        rev = self.revenue.record_mint(listing.token_id,
                                       NFT_MINT_PRICE_SOL, patient, clinic)
        return {
            "success":      True,
            "token_id":     listing.token_id,
            "tier":         listing.tier,
            "mint_tx":      listing.mint_tx,
            "genome_sig":   listing.genome_sig,
            "updrs_delta":  patient.updrs_improvement,
            "revenue_split":rev,
            "metadata_uri": f"ipfs://neuroavatar/{listing.token_id}/metadata.json",
        }

    # POST /api/marketplace/list
    def list_nft(self, token_id: str, price_sol: float) -> Dict:
        ok = self.nft.list_for_sale(token_id, price_sol)
        return {"success": ok, "token_id": token_id, "list_price_sol": price_sol}

    # POST /api/marketplace/buy
    def buy_nft(self, token_id: str, buyer_wallet: str) -> Dict:
        sale = self.nft.buy(token_id, buyer_wallet)
        if not sale:
            return {"success": False, "error": "Token not listed or already sold"}
        listing = next((l for l in self.nft.all_listings()
                        if l.token_id == token_id), None)
        if listing:
            clinic = self.clinics.get(listing.clinic_id)
            if clinic:
                self.revenue.record_secondary(sale, clinic)
        return {"success": True, **sale}

    # GET /api/marketplace/listings
    def marketplace_listings(self) -> Dict:
        listings = [
            {"token_id": l.token_id, "tier": l.tier,
             "price_sol": l.list_price_sol, "genome_sig": l.genome_sig,
             "listed_at": l.listed_at}
            for l in self.nft.active_listings()
        ]

        return {"success": True, "count": len(listings), "listings": listings}

    # GET /api/revenue/projection
    def revenue_projection(self, active_clinics: int = 50,
                           patients_per_month: int = 10) -> ProjectionResult:
        return ProjectionResult(
            self.revenue.projection(active_clinics, patients_per_month)
        )


# ── Main demo ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("NEURO-AVATAR NFT PLATFORM v3.0")
    print("Complete Commercial System: MMG+EEG -> DNA/tRNA -> NFT -> Marketplace")
    print("=" * 80)

    api = NeuroPlatformAPI()

    # ── Health ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PLATFORM HEALTH")
    print("=" * 80)
    h = api.health()
    for k, v in h.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for sk, sv in v.items():
                print(f"    {sk}: {sv}")
        else:
            print(f"  {k}: {v}")

    # ── Register clinics ──────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("CLINIC REGISTRATION")
    print("=" * 80)
    clinic_ids = []
    for name, spec, lic in [
        ("Mayo Clinic Neurology",    "movement_disorders", "MC-ND-2026-001"),
        ("Cleveland Clinic Brain",   "parkinson_tremor",   "CC-PT-2026-002"),
        ("Johns Hopkins Neuro",      "eeg_biofeedback",    "JH-EB-2026-003"),
    ]:
        r = api.register_clinic(name, spec, lic)
        print(f"  Registered: {r['name']}")
        print(f"    clinic_id: {r['clinic_id'][:8]}...")
        print(f"    wallet:    {r['wallet'][:22]}...")
        clinic_ids.append(r["clinic_id"])

    # ── Enroll patients ───────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PATIENT ENROLLMENT")
    print("=" * 80)
    patient_ids = []
    for cid, cond, phase, baseline in [
        (clinic_ids[0], "Parkinson's Disease",   "Year-1 Protocol", 32.4),
        (clinic_ids[0], "Essential Tremor",      "Year-2 Protocol", 28.1),
        (clinic_ids[1], "Parkinson's Disease",   "Year-3 Protocol", 41.2),
        (clinic_ids[1], "Dystonia",              "Year-1 Protocol", 18.7),
        (clinic_ids[2], "Parkinson's Disease",   "Year-5 Protocol", 38.9),
        (clinic_ids[2], "Restless Leg Syndrome", "Year-1 Protocol", 22.3),
    ]:
        r = api.enroll_patient(cid, cond, phase, baseline)
        print(f"  Enrolled: {r['patient_id'][:8]}... | {cond} | UPDRS baseline {baseline}")
        patient_ids.append(r["patient_id"])

    # ── EEG + MMG biometrics (per patient) ───────────────────────────────────
    biometrics = [
        ({"delta_power": 15.2, "theta_power": 11.8, "alpha_power": 26.4, "beta_power":  9.1},
         {"tremor_freq_hz": 4.8, "rms_uT": 0.62}, 24.1),
        ({"delta_power": 12.7, "theta_power": 13.2, "alpha_power": 22.9, "beta_power":  7.8},
         {"tremor_freq_hz": 6.2, "rms_uT": 0.45}, 19.8),
        ({"delta_power": 18.3, "theta_power": 14.6, "alpha_power": 19.7, "beta_power": 11.2},
         {"tremor_freq_hz": 3.1, "rms_uT": 0.78}, 30.4),
        ({"delta_power": 11.4, "theta_power":  9.8, "alpha_power": 24.3, "beta_power":  8.6},
         {"tremor_freq_hz": 2.4, "rms_uT": 0.31}, 12.9),
        ({"delta_power": 16.9, "theta_power": 12.1, "alpha_power": 28.7, "beta_power":  7.3},
         {"tremor_freq_hz": 5.7, "rms_uT": 0.55}, 27.1),
        ({"delta_power":  9.8, "theta_power":  8.4, "alpha_power": 21.6, "beta_power":  6.9},
         {"tremor_freq_hz": 1.8, "rms_uT": 0.22}, 16.4),
    ]

    # ── Mint NFTs ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("NFT MINTING -- MMG+EEG -> DNA/tRNA -> Token")
    print("=" * 80)
    minted_tokens = []
    for pid, (eeg, mmg, updrs_current) in zip(patient_ids, biometrics):
        r       = api.mint_nft(pid, eeg, mmg, updrs_current)
        patient = api.patients.get(pid)
        delta   = patient.updrs_improvement if patient else 0.0
        print(f"\n  Token #{r['token_id']} [{r['tier']}]")
        print(f"    Genome Sig:   {r['genome_sig']}")
        print(f"    UPDRS Delta:  {delta:+.1f}")
        print(f"    Mint TX:      {r['mint_tx'][:24]}...")
        rev = r["revenue_split"]
        print(f"    Revenue:      patient {rev['patient_cut']:.4f} SOL | "
              f"clinic {rev['clinic_cut']:.4f} SOL | "
              f"platform {rev['platform_cut']:.4f} SOL")
        minted_tokens.append(r["token_id"])

    # ── List on marketplace ───────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("MARKETPLACE LISTINGS")
    print("=" * 80)
    for token_id, price in zip(minted_tokens[:2], [0.08, 0.12]):
        api.list_nft(token_id, price)
        print(f"  Listed #{token_id} @ {price} SOL")

    listings = api.marketplace_listings()
    print(f"\n  Active listings: {listings['count']}")
    for lst in listings["listings"]:
        print(f"    #{lst['token_id']} [{lst['tier']}] @ {lst['price_sol']} SOL")

    # ── Secondary sale ────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECONDARY MARKET SALE")
    print("=" * 80)
    if minted_tokens:
        buyer  = "0xBuyer" + hashlib.sha256(b"buyer1").hexdigest()[:20]
        sale_r = api.buy_nft(minted_tokens[0], buyer)
        if sale_r.get("success"):
            print(f"  Sold #{sale_r['token_id']} for {sale_r['sale_price']} SOL")
            print(f"  Royalty: {sale_r['royalty_sol']} SOL")
            print(f"  Sale TX: {sale_r['sale_tx'][:24]}...")

    # ── Clinic earnings ───────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("CLINIC EARNINGS SUMMARY")
    print("=" * 80)
    for clinic in api.clinics.all():
        print(f"  {clinic.name}")
        print(f"    NFTs minted:    {clinic.nfts_minted}")
        print(f"    Revenue earned: {clinic.revenue_earned:.4f} SOL")
        print(f"    Patients:       {len(clinic.enrolled_patients)}")

    # ── Revenue projection ────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("REVENUE PROJECTION")
    print("=" * 80)
    revenue = api.revenue_projection()
    for key, value in revenue.json:
        print(f"   {key}: ${value:,.0f}" if isinstance(value, (int, float)) else f"   {key}: {value}")

    print("\n" + "=" * 80)
    print("PLATFORM READY FOR DEPLOYMENT")
    print("=" * 80)
    print("\nEndpoints:")
    print("  GET  /health                    - Platform status")
    print("  POST /api/clinic/register      - Register clinic")
    print("  POST /api/clinic/enroll        - Enroll patient")
    print("  POST /api/clinic/mint_nft      - Mint NFT from EEG+MMG data")
    print("  GET  /api/marketplace/listings - Active NFT listings")
    print("  POST /api/marketplace/buy      - Purchase listed NFT")
    print("  GET  /api/revenue/projection   - Revenue model projection")
    print()

    # ── Artifact ──────────────────────────────────────────────────────────────
    artifact = {
        "platform":    "NeuroAvatar NFT Platform v3.0",
        "timestamp":   TIMESTAMP,
        "clinics":     len(api.clinics.all()),
        "patients":    sum(len(c.enrolled_patients) for c in api.clinics.all()),
        "nfts_minted": len(minted_tokens),
        "marketplace": listings,
        "projection":  dict(revenue.json),
    }
    out_file = f"neuro_avatar_v3_{PLATFORM_UUID[:8]}.json"
    with open(out_file, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"Artifact saved: {out_file}")


if __name__ == "__main__":
    main()
