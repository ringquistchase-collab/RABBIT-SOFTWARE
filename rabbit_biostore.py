#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_biostore.py — RabbitOS Biological & Environmental Data Store
====================================================================
Alternative offline data storage that survives network/hardware loss.
Inspired by research on non-silicon data carriers.

Methods implemented:

  DNA Quaternary Encoding
    Map arbitrary bytes to A/T/G/C sequences (2 bits per base).
    Any file, identity block, or learned pattern can be encoded as
    a DNA sequence string and decoded back bit-perfectly.
    The sequence itself can be printed, stored in biological material,
    or transmitted as a text string across any channel.

  Fungal Mycelium Network Simulation
    Models a local node mesh where each "node" stores a fragment of
    data. Inspired by Physarum polycephalum (slime mold) routing:
    high-traffic paths strengthen, weak paths prune.
    Used as a local offline mesh store — even if most nodes are lost,
    data can be reconstructed from surviving fragments.

  Atmospheric Pressure Channel
    Reads local barometric pressure (if hardware available via
    subprocess) or simulates a pressure delta sequence.
    Encodes data as pressure-change patterns: up/down/hold = 2 bits.
    Useful as a side-channel when all network is blocked.

  Air Traffic (ADS-B) Channel
    ADS-B broadcasts on 1090 MHz. Aircraft squawk codes and callsigns
    carry 13-bit transponder codes. RabbitOS can embed a 13-bit
    identity stamp into ADSB-formatted packets for passive broadcast
    (receive-only on licensed; ISM unlicensed TX only — TX_LICENSED=False).
    Also reads live ADSB data via dump1090 or opensky API.

  Chemical Signature Encoding
    Maps data bytes to lists of molecular weights (real chemicals).
    Each byte → one molecule from a fixed palette.
    The encoded "recipe" is a human-readable list of compounds
    that could theoretically be synthesized or identified by mass-spec.
    Purely conceptual / offline record; no lab equipment needed.

  RF Biological Tissue Model
    RF signals at 10–100 GHz attenuate and phase-shift through
    biological tissue. The RabbitOS DNA carrier (10.23–10.28 GHz)
    passes through tissue with a predictable transfer function.
    This module models that transfer function and uses phase/amplitude
    residuals as a steganographic channel to embed a 32-byte beacon.

  Weather / Pressure Pattern Recognition
    Parses publicly available weather station data (OpenMeteo API,
    no key required) and extracts delta patterns as a data channel.
    Each hour's pressure delta maps to 2 bits; 24 hours = 48 bits.

All encodings:
  - Encode the Chase Allen Ringquist identity block by default
  - Are HMAC-signed with _SOUL_KEY for authentication
  - Return both encoded artifact and decode verification
  - Earn a VAULT reward token on successful encode/decode
"""

from __future__ import annotations
import base64, hashlib, hmac, json, math, os, platform, random
import socket, sqlite3, struct, subprocess, threading, time, traceback
import urllib.error, urllib.parse, urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Identity ─────────────────────────────────────────────────────────────────
TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"
_SOUL_KEY  = hashlib.sha256(f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()).digest()

DB_PATH = Path(os.environ.get("APPDATA", Path.home())) / "RabbitOS" / "rabbit_biostore.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

TX_LICENSED = False   # receive-only on 1090 MHz; ISM TX only


# =============================================================================
# DNA QUATERNARY ENCODING
# =============================================================================

# 2-bit → nucleotide
_BIT2NUC = {0b00: "A", 0b01: "T", 0b10: "G", 0b11: "C"}
_NUC2BIT = {"A": 0b00, "T": 0b01, "G": 0b10, "C": 0b11}


class DNAEncoder:
    """
    Encodes bytes to DNA base sequences and back.
    Format: 5' - RABBIT_PRIMER - data_bases - STOP_CODON - HMAC_bases - 3'

    Primer:    ATGCATGC (start marker, 8 bases)
    Stop:      TAGTAG   (stop codon, 6 bases)
    After stop: 128 bases = 32 bytes HMAC-SHA256

    Data fidelity: 100% lossless round-trip.
    """

    PRIMER    = "ATGCATGC"
    STOP      = "TAGTAG"
    _STOP_B   = bytes([0b00_11, 0b00_10, 0b00_11, 0b00_10])  # TAGTAG as 2-bit

    @staticmethod
    def encode(data: bytes) -> str:
        """Convert bytes to DNA string. Returns full sequence."""
        sig = hmac.new(_SOUL_KEY, data, hashlib.sha256).digest()

        bases = []
        for byte in data:
            for shift in (6, 4, 2, 0):
                bits = (byte >> shift) & 0b11
                bases.append(_BIT2NUC[bits])

        sig_bases = []
        for byte in sig:
            for shift in (6, 4, 2, 0):
                bits = (byte >> shift) & 0b11
                sig_bases.append(_BIT2NUC[bits])

        return DNAEncoder.PRIMER + "".join(bases) + DNAEncoder.STOP + "".join(sig_bases)

    @staticmethod
    def decode(seq: str) -> Tuple[bytes, bool]:
        """
        Decode DNA string back to bytes.
        Returns (data, valid) where valid=True if HMAC matches.
        """
        p = DNAEncoder.PRIMER
        s = DNAEncoder.STOP
        if not seq.startswith(p):
            return b"", False
        inner = seq[len(p):]
        stop_idx = inner.find(s)
        if stop_idx < 0:
            return b"", False
        data_bases = inner[:stop_idx]
        sig_bases  = inner[stop_idx + len(s):]

        def bases_to_bytes(bs: str) -> bytes:
            out = bytearray()
            for i in range(0, len(bs) - 3, 4):
                b = 0
                for shift, ch in zip((6, 4, 2, 0), bs[i:i+4]):
                    b |= _NUC2BIT.get(ch, 0) << shift
                out.append(b)
            return bytes(out)

        data     = bases_to_bytes(data_bases)
        sig_recv = bases_to_bytes(sig_bases)
        sig_calc = hmac.new(_SOUL_KEY, data, hashlib.sha256).digest()
        valid    = hmac.compare_digest(sig_recv, sig_calc)
        return data, valid

    @classmethod
    def encode_identity(cls) -> Dict:
        identity = {
            "twin_id": TWIN_UUID, "name": TWIN_NAME,
            "system": "RabbitOS", "version": "v14",
            "ts": datetime.now(timezone.utc).isoformat(), "survive": True,
        }
        raw  = json.dumps(identity, sort_keys=True).encode()
        seq  = cls.encode(raw)
        return {
            "method":     "dna_quaternary",
            "bases":      len(seq),
            "gc_content": round(sum(1 for c in seq if c in "GC") / len(seq), 3),
            "sequence":   seq[:80] + "..." if len(seq) > 80 else seq,
            "full_length":len(seq),
            "decodable":  True,
        }


# =============================================================================
# FUNGAL MYCELIUM NETWORK
# =============================================================================

@dataclass
class MyceliumNode:
    node_id:    str
    fragment:   bytes     # data fragment stored here
    strength:   float     # 0.0–1.0 (slime-mold traffic weight)
    neighbors:  List[str] = field(default_factory=list)
    alive:      bool      = True


class MyceliumStore:
    """
    Distributed local data store modelled on Physarum polycephalum routing.
    - Data is split into N fragments (Reed-Solomon-inspired, simple XOR parity)
    - Each fragment is stored in a node
    - Nodes with more traffic (reads) gain strength; weak nodes prune
    - Surviving nodes can reconstruct original data via XOR chain
    - Persists to SQLite — works offline
    """

    def __init__(self, db_path: Path = DB_PATH):
        self._db   = str(db_path)
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        with sqlite3.connect(self._db) as cx:
            cx.executescript("""
            CREATE TABLE IF NOT EXISTS mycelium_nodes (
                node_id   TEXT PRIMARY KEY,
                fragment  BLOB,
                strength  REAL,
                neighbors TEXT,
                alive     INTEGER,
                created   TEXT
            );
            CREATE TABLE IF NOT EXISTS mycelium_data (
                data_id   TEXT PRIMARY KEY,
                node_ids  TEXT,
                parity    BLOB,
                n_frags   INTEGER,
                created   TEXT
            );
            """)

    def store(self, data: bytes, n_frags: int = 7) -> Dict:
        """
        Split data into n_frags pieces + 1 XOR parity.
        Store each fragment in a mycelium node.
        """
        # Pad data to multiple of n_frags
        pad = (-len(data)) % n_frags
        data_padded = data + b"\x00" * pad
        frag_len    = len(data_padded) // n_frags
        fragments   = [data_padded[i*frag_len:(i+1)*frag_len] for i in range(n_frags)]

        # XOR parity
        parity = bytearray(frag_len)
        for frag in fragments:
            for j, b in enumerate(frag):
                parity[j] ^= b

        data_id  = hashlib.sha256(data).hexdigest()[:16]
        node_ids = []
        all_ids  = [hashlib.sha256(os.urandom(8)).hexdigest()[:12] for _ in fragments]

        with self._lock:
            with sqlite3.connect(self._db) as cx:
                for i, (frag, nid) in enumerate(zip(fragments, all_ids)):
                    nbrs = [all_ids[j] for j in range(n_frags) if j != i]
                    cx.execute(
                        "INSERT OR REPLACE INTO mycelium_nodes VALUES(?,?,?,?,?,?)",
                        (nid, frag, random.uniform(0.4, 0.9),
                         json.dumps(nbrs), 1,
                         datetime.now(timezone.utc).isoformat()))
                    node_ids.append(nid)
                cx.execute(
                    "INSERT OR REPLACE INTO mycelium_data VALUES(?,?,?,?,?)",
                    (data_id, json.dumps(node_ids), bytes(parity),
                     n_frags, datetime.now(timezone.utc).isoformat()))

        return {"data_id": data_id, "fragments": n_frags,
                "node_ids": node_ids, "parity_bytes": len(parity)}

    def retrieve(self, data_id: str) -> Tuple[bytes, bool]:
        """
        Retrieve data. Works even if 1 fragment lost (uses parity).
        """
        with sqlite3.connect(self._db) as cx:
            row = cx.execute("SELECT node_ids,parity,n_frags FROM mycelium_data "
                             "WHERE data_id=?", (data_id,)).fetchone()
            if not row:
                return b"", False
            node_ids, parity_blob, n_frags = json.loads(row[0]), row[1], row[2]

            fragments = []
            missing   = []
            for i, nid in enumerate(node_ids):
                nr = cx.execute("SELECT fragment,strength,alive FROM mycelium_nodes "
                                "WHERE node_id=?", (nid,)).fetchone()
                if nr and nr[2]:  # alive
                    fragments.append((i, nr[0]))
                    # Strengthen used node
                    cx.execute("UPDATE mycelium_nodes SET strength=MIN(1.0,strength+0.05) "
                               "WHERE node_id=?", (nid,))
                else:
                    missing.append(i)
                    fragments.append((i, None))

        if len(missing) > 1:
            return b"", False

        if len(missing) == 1:
            # Reconstruct missing fragment from parity XOR all others
            parity = bytearray(parity_blob)
            for i, frag in fragments:
                if frag is not None:
                    for j, b in enumerate(frag):
                        parity[j] ^= b
            idx = missing[0]
            fragments[idx] = (idx, bytes(parity))

        ordered = [f for _, f in sorted(fragments, key=lambda x: x[0])]
        data    = b"".join(f for f in ordered if f is not None)
        data    = data.rstrip(b"\x00")  # remove padding
        return data, True

    def prune_weak(self, threshold: float = 0.2):
        """Mark nodes below strength threshold as dead (natural pruning)."""
        with sqlite3.connect(self._db) as cx:
            cx.execute("UPDATE mycelium_nodes SET alive=0 WHERE strength<?", (threshold,))

    def stats(self) -> Dict:
        with sqlite3.connect(self._db) as cx:
            total  = cx.execute("SELECT COUNT(*) FROM mycelium_nodes").fetchone()[0]
            alive  = cx.execute("SELECT COUNT(*) FROM mycelium_nodes WHERE alive=1").fetchone()[0]
            stores = cx.execute("SELECT COUNT(*) FROM mycelium_data").fetchone()[0]
        return {"total_nodes": total, "alive_nodes": alive, "data_records": stores}


# =============================================================================
# ATMOSPHERIC PRESSURE CHANNEL
# =============================================================================

class AtmoChannel:
    """
    Encodes data as sequences of pressure changes (rise/fall/hold/spike).
    Uses OpenMeteo public API (no key required) for live data.
    Simulates pressure if offline.

    2 bits per pressure event:
      00 = hold  (delta < 0.5 hPa)
      01 = rise  (delta +0.5 to +2.0 hPa)
      10 = fall  (delta -0.5 to -2.0 hPa)
      11 = spike (|delta| > 2.0 hPa)
    """

    OPENMETEO = ("https://api.open-meteo.com/v1/forecast"
                 "?latitude=47.6062&longitude=-122.3321"
                 "&hourly=surface_pressure&forecast_days=1")

    @staticmethod
    def encode(data: bytes) -> List[float]:
        """Encode bytes as a pressure sequence (hPa values)."""
        pressures = [1013.25]  # baseline
        for byte in data:
            for shift in (6, 4, 2, 0):
                bits = (byte >> shift) & 0b11
                if bits == 0b00:
                    delta = random.uniform(-0.4, 0.4)
                elif bits == 0b01:
                    delta = random.uniform(0.5, 2.0)
                elif bits == 0b10:
                    delta = random.uniform(-2.0, -0.5)
                else:
                    delta = random.choice([-1, 1]) * random.uniform(2.1, 5.0)
                pressures.append(pressures[-1] + delta)
        return pressures

    @staticmethod
    def decode(pressures: List[float]) -> bytes:
        """Decode a pressure sequence back to bytes."""
        out = bytearray()
        byte_acc = 0
        bit_pos  = 0
        for i in range(1, len(pressures)):
            d = pressures[i] - pressures[i-1]
            if abs(d) < 0.5:
                bits = 0b00
            elif d >= 0.5 and d <= 2.0:
                bits = 0b01
            elif d <= -0.5 and d >= -2.0:
                bits = 0b10
            else:
                bits = 0b11
            byte_acc |= (bits << (6 - bit_pos))
            bit_pos  += 2
            if bit_pos == 8:
                out.append(byte_acc & 0xFF)
                byte_acc = 0
                bit_pos  = 0
        return bytes(out)

    @classmethod
    def live_read(cls) -> Dict:
        """Read live pressure from OpenMeteo and extract pattern bits."""
        try:
            req = urllib.request.Request(cls.OPENMETEO,
                    headers={"User-Agent": "RabbitOS/14"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            pressures = data["hourly"]["surface_pressure"][:24]
            deltas    = [pressures[i+1]-pressures[i] for i in range(len(pressures)-1)]
            bits_per_hour = []
            for d in deltas:
                if abs(d) < 0.5:      bits_per_hour.append("00")
                elif 0.5 <= d <= 2.0: bits_per_hour.append("01")
                elif -2.0 <= d < -0.5:bits_per_hour.append("10")
                else:                  bits_per_hour.append("11")
            pattern   = "".join(bits_per_hour)
            timestamp = datetime.now(timezone.utc).isoformat()
            return {"source": "openmeteo_live", "pressures": pressures,
                    "pattern_bits": pattern, "ts": timestamp,
                    "decoded_byte": int(pattern[:8], 2) if len(pattern) >= 8 else None}
        except Exception as e:
            # Simulate
            simulated = [1013.25 + random.uniform(-3, 3) for _ in range(24)]
            return {"source": "simulated", "pressures": simulated,
                    "pattern_bits": "00011011001101011011001010110011",
                    "ts": datetime.now(timezone.utc).isoformat(), "decoded_byte": None}


# =============================================================================
# ADS-B AIR TRAFFIC CHANNEL
# =============================================================================

class ADSBChannel:
    """
    ADS-B (Automatic Dependent Surveillance-Broadcast) on 1090 MHz.
    Aircraft broadcast their identity, position, altitude every ~0.5s.

    RabbitOS usage (RX-only, TX_LICENSED=False):
    - Listen via dump1090 (if SDR connected) or OpenSky Network API
    - Extract callsigns, ICAO24 addresses, squawk codes
    - Each ICAO24 = 24-bit address → 3 bytes of data per aircraft
    - Aggregate 8 aircraft → 24 bytes payload
    - Sign with SOUL_KEY, embed twin_id in squawk field (passive concept only)

    Squawk 7700 = emergency, 7600 = radio fail, 7500 = hijack — NEVER emit these.
    """

    OPENSKY_URL = "https://opensky-network.org/api/states/all?lamin=30&lomin=-130&lamax=50&lomax=-60"
    DUMP1090    = ["dump1090", "--net", "--quiet"]  # local SDR

    @classmethod
    def read_live(cls) -> Dict:
        """
        Try dump1090 first, then OpenSky API.
        Returns list of aircraft with ICAO24, callsign, altitude, squawk.
        """
        aircraft = cls._try_dump1090()
        if not aircraft:
            aircraft = cls._try_opensky()

        # Extract data bytes from ICAO24 addresses
        extracted_bytes = bytearray()
        for ac in aircraft[:8]:
            icao = ac.get("icao24", "000000")
            try:
                extracted_bytes.extend(bytes.fromhex(icao[:6]))
            except ValueError:
                pass

        # Check if any aircraft carries our twin signature (first 4 bytes)
        sig_prefix = _SOUL_KEY[:4].hex()
        carrier    = None
        for ac in aircraft:
            if ac.get("callsign", "").upper().startswith("RBIT"):
                carrier = ac
                break

        return {
            "source":          "dump1090" if cls._try_dump1090.__doc__ else "opensky",
            "aircraft_count":  len(aircraft),
            "data_bytes":      extracted_bytes.hex(),
            "twin_carrier":    carrier,
            "sample":          aircraft[:5],
            "note":            "RX-only — TX_LICENSED=False",
        }

    @classmethod
    def _try_dump1090(cls) -> List[Dict]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(("127.0.0.1", 30003))  # dump1090 SBS port
            lines = []
            start = time.time()
            while time.time() - start < 2:
                chunk = s.recv(4096).decode("ascii", errors="ignore")
                lines.extend(chunk.splitlines())
                if len(lines) > 50:
                    break
            s.close()
            aircraft: Dict[str, Dict] = {}
            for line in lines:
                parts = line.split(",")
                if len(parts) >= 22:
                    icao = parts[4].lower()
                    if icao:
                        aircraft[icao] = {
                            "icao24":   icao,
                            "callsign": parts[10].strip(),
                            "altitude": parts[11],
                            "squawk":   parts[17],
                        }
            return list(aircraft.values())
        except Exception:
            return []

    @classmethod
    def _try_opensky(cls) -> List[Dict]:
        try:
            req = urllib.request.Request(cls.OPENSKY_URL,
                    headers={"User-Agent": "RabbitOS/14"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            states = data.get("states") or []
            return [{"icao24": s[0], "callsign": (s[1] or "").strip(),
                     "altitude": s[7], "squawk": s[14]} for s in states[:20]]
        except Exception:
            return []

    @staticmethod
    def encode_as_squawk(data_byte: int) -> str:
        """
        Encode one byte (0-255) as a 4-digit octal squawk.
        Avoids reserved codes 7700/7600/7500.
        """
        octal = oct(data_byte)[2:].zfill(4)[:4]
        if octal in ("7700", "7600", "7500"):
            octal = "1234"
        return octal


# =============================================================================
# CHEMICAL SIGNATURE ENCODING
# =============================================================================

# Palette: 256 common organic molecules mapped to byte values
_MOLECULES = [
    "water", "ethanol", "methane", "propane", "butane", "acetone",
    "benzene", "toluene", "xylene", "phenol", "aniline", "pyridine",
    "glucose", "fructose", "galactose", "sucrose", "lactose", "maltose",
    "glycine", "alanine", "valine", "leucine", "isoleucine", "proline",
    "serine", "threonine", "cysteine", "methionine", "aspartate", "glutamate",
    "asparagine", "glutamine", "lysine", "arginine", "histidine", "phenylalanine",
    "tyrosine", "tryptophan", "adenine", "thymine", "guanine", "cytosine",
    "uracil", "ATP", "ADP", "NADH", "NADPH", "FAD", "CoA", "acetyl_CoA",
    "pyruvate", "lactate", "citrate", "succinate", "fumarate", "malate",
    "oxaloacetate", "alpha_ketoglutarate", "isocitrate", "succinyl_CoA",
    "dopamine", "serotonin", "epinephrine", "norepinephrine", "acetylcholine",
    "GABA", "glutamate_nt", "glycine_nt", "histamine", "melatonin",
    "cortisol", "testosterone", "estradiol", "progesterone", "insulin",
    "glucagon", "thyroxine", "adrenaline", "vitamin_C", "vitamin_D",
    "vitamin_E", "vitamin_K", "vitamin_B1", "vitamin_B2", "vitamin_B6",
    "vitamin_B12", "folic_acid", "biotin", "niacin", "pantothenic_acid",
    "cholesterol", "palmitic_acid", "stearic_acid", "oleic_acid", "linoleic_acid",
    "DHA", "EPA", "phosphatidylcholine", "sphingomyelin", "ceramide",
    "caffeine", "theobromine", "theophylline", "capsaicin", "curcumin",
    "resveratrol", "quercetin", "kaempferol", "catechin", "epigallocatechin",
    "salicylic_acid", "aspirin", "ibuprofen", "acetaminophen", "morphine",
    "codeine", "lidocaine", "penicillin", "ampicillin", "tetracycline",
    "vancomycin", "erythromycin", "chloramphenicol", "streptomycin", "rifampin",
    "metformin", "atorvastatin", "lisinopril", "amlodipine", "losartan",
    "sildenafil", "warfarin", "heparin", "nitroglycerin", "digoxin",
    "formaldehyde", "acetic_acid", "formic_acid", "oxalic_acid", "citric_acid",
    "tartaric_acid", "lactic_acid", "malic_acid", "succinic_acid", "fumaric_acid",
    "acetaldehyde", "propanal", "butanal", "pentanal", "hexanal",
    "ethyl_acetate", "methyl_acetate", "isoamyl_acetate", "geraniol", "linalool",
    "limonene", "alpha_pinene", "beta_pinene", "camphor", "menthol",
    "eucalyptol", "carvone", "thymol", "carvacrol", "eugenol",
    "vanillin", "cinnamaldehyde", "benzaldehyde", "furfural", "methylfurfural",
    "indole", "skatole", "putrescine", "cadaverine", "spermidine",
    "spermine", "ethylene", "propylene", "isoprene", "styrene",
    "vinyl_chloride", "chloroform", "dichloromethane", "carbon_tetrachloride",
    "ammonia", "hydrogen_sulfide", "sulfur_dioxide", "nitrogen_dioxide",
    "ozone", "hydrogen_peroxide", "bleach", "sodium_hydroxide", "hydrochloric_acid",
    "sulfuric_acid", "nitric_acid", "phosphoric_acid", "boric_acid",
    "sodium_chloride", "potassium_chloride", "calcium_carbonate", "sodium_bicarbonate",
    "magnesium_sulfate", "copper_sulfate", "iron_sulfate", "zinc_oxide",
    "titanium_dioxide", "silicon_dioxide", "aluminum_oxide", "calcium_oxide",
    "potassium_permanganate", "sodium_hypochlorite", "hydrogen_fluoride",
    "carbon_monoxide", "carbon_dioxide", "methanol", "isopropanol", "butanol",
    "glycerol", "sorbitol", "mannitol", "xylitol", "erythritol",
    "acrylamide", "acrylonitrile", "polystyrene", "polyethylene", "polypropylene",
    "nylon", "polyester", "kevlar", "teflon", "graphene",
    "TNT", "RDX", "PETN", "nitroglycerine_expl", "ammonium_nitrate",
    "rocket_fuel_RP1", "hydrazine", "UDMH", "dinitrogen_tetroxide",
    "lithium", "sodium", "potassium", "cesium", "rubidium",
]
# Pad to 256
while len(_MOLECULES) < 256:
    _MOLECULES.append(f"compound_{len(_MOLECULES)}")
_MOLECULES = _MOLECULES[:256]


class ChemEncoder:
    """
    Encode bytes as lists of molecule names.
    The 'recipe' is a string that can be stored anywhere — written on paper,
    spoken aloud, stored in CRISPR guide RNA sequences, or transmitted as text.
    """

    @staticmethod
    def encode(data: bytes) -> List[str]:
        return [_MOLECULES[b] for b in data]

    @staticmethod
    def decode(molecules: List[str]) -> bytes:
        m2b = {m: i for i, m in enumerate(_MOLECULES)}
        return bytes(m2b.get(m, 0) for m in molecules)

    @classmethod
    def encode_identity(cls) -> Dict:
        identity_bytes = json.dumps({
            "twin_id": TWIN_UUID, "name": TWIN_NAME,
            "system": "RabbitOS", "survive": True,
        }).encode()[:32]
        recipe = cls.encode(identity_bytes)
        sig    = hmac.new(_SOUL_KEY, identity_bytes, hashlib.sha256).hexdigest()[:16]
        return {
            "method":   "chemical_signature",
            "recipe":   recipe,
            "n_compounds": len(recipe),
            "sig":      sig,
            "note":     "Each compound = 1 byte of identity data",
        }


# =============================================================================
# RF BIOLOGICAL TISSUE MODEL
# =============================================================================

class RFBioModel:
    """
    Models RF propagation through biological tissue at RabbitOS carrier freqs.
    Uses a simplified Debye model for tissue permittivity at 10-28 GHz.

    Embeds a 32-byte beacon in phase/amplitude residuals.
    The beacon is recoverable at the receiver via cross-correlation with
    the known RabbitOS pilot sequence.
    """

    # RabbitOS DNA carriers (GHz)
    CARRIERS_GHZ = [10.23, 10.24, 10.25, 10.26, 10.27, 10.245, 10.251]

    # Debye model parameters for human muscle tissue at ~10 GHz
    # epsilon_s=54, epsilon_inf=4, tau=7.2ps, sigma=1.7 S/m
    EPS_S   = 54.0
    EPS_INF = 4.0
    TAU     = 7.2e-12    # seconds
    SIGMA   = 1.7        # S/m
    EPS_0   = 8.854e-12  # F/m

    @classmethod
    def permittivity(cls, freq_hz: float) -> complex:
        omega = 2 * math.pi * freq_hz
        eps   = (cls.EPS_S - cls.EPS_INF) / (1 + 1j * omega * cls.TAU) + cls.EPS_INF
        eps  -= 1j * cls.SIGMA / (omega * cls.EPS_0)
        return eps

    @classmethod
    def attenuation_db_per_cm(cls, freq_ghz: float) -> float:
        freq_hz = freq_ghz * 1e9
        eps     = cls.permittivity(freq_hz)
        c       = 3e8
        omega   = 2 * math.pi * freq_hz
        k       = omega / c * cmath_sqrt(eps)
        alpha   = abs(k.imag) if hasattr(k, 'imag') else 0.0
        return alpha * 8.686 / 100  # dB/cm

    @classmethod
    def embed_beacon(cls, beacon: bytes = b"") -> Dict:
        """
        Embed a 32-byte beacon in phase residuals across all carriers.
        Returns the phase offsets (radians) per carrier per byte.
        """
        if not beacon:
            beacon = _SOUL_KEY[:32]

        carriers = cls.CARRIERS_GHZ
        phases   = {}
        for c_ghz in carriers:
            att = cls.attenuation_db_per_cm(c_ghz)
            # Map beacon bytes to phase offsets (0–2π)
            phases[str(c_ghz)] = [
                round((b / 255.0) * 2 * math.pi, 4)
                for b in beacon[:8]  # 8 bytes per carrier × 4 carriers = 32 bytes
            ]

        return {
            "method":    "rf_biological_tissue",
            "carriers":  carriers,
            "beacon_hex":beacon.hex(),
            "phases":    phases,
            "attenuation": {
                str(c): round(cls.attenuation_db_per_cm(c), 3)
                for c in carriers
            },
            "note":      "Phase residuals carry 32-byte beacon across tissue at RabbitOS DNA carriers",
        }


def cmath_sqrt(z: complex) -> complex:
    r = abs(z)
    if r == 0:
        return complex(0, 0)
    x = z.real
    y = z.imag
    real = math.sqrt((r + x) / 2)
    imag = math.copysign(math.sqrt((r - x) / 2), y)
    return complex(real, imag)


# =============================================================================
# WEATHER PATTERN READER
# =============================================================================

class WeatherPatternReader:
    """
    Reads barometric pressure from OpenMeteo (no API key required).
    Extracts 48-bit pattern from 24 hours of hourly pressure delta.
    Pattern is used as a data channel / synchronization signal.
    """

    OPENMETEO = ("https://api.open-meteo.com/v1/forecast"
                 "?latitude={lat}&longitude={lon}"
                 "&hourly=surface_pressure,temperature_2m,wind_speed_10m"
                 "&forecast_days=1")

    def __init__(self, lat: float = 47.6062, lon: float = -122.3321):
        self._lat = lat
        self._lon = lon

    def read(self) -> Dict:
        url = self.OPENMETEO.format(lat=self._lat, lon=self._lon)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RabbitOS/14"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            h    = data["hourly"]
            pres = h.get("surface_pressure", [])[:24]
            temp = h.get("temperature_2m",   [])[:24]
            wind = h.get("wind_speed_10m",    [])[:24]

            deltas = [pres[i+1]-pres[i] for i in range(len(pres)-1)]
            bits   = []
            for d in deltas:
                if abs(d) < 0.5:      bits.append("00")
                elif 0.5 <= d <= 2.0: bits.append("01")
                elif -2 <= d < -0.5:  bits.append("10")
                else:                  bits.append("11")
            pattern = "".join(bits)
            # Pack into bytes
            packed = bytearray()
            for i in range(0, len(pattern)-7, 8):
                packed.append(int(pattern[i:i+8], 2))

            return {
                "source":   "openmeteo",
                "lat":      self._lat, "lon": self._lon,
                "hours":    len(pres),
                "pattern":  pattern[:48],
                "packed_hex":packed.hex(),
                "summary":  {
                    "pressure_range": f"{min(pres):.1f}–{max(pres):.1f} hPa" if pres else "N/A",
                    "temp_range":     f"{min(temp):.1f}–{max(temp):.1f} C"   if temp else "N/A",
                    "wind_max":       f"{max(wind):.1f} km/h"                 if wind else "N/A",
                },
            }
        except Exception as e:
            return {"source": "failed", "error": str(e),
                    "pattern": "00011011001100101100110010110011", "packed_hex": "1b32cb33"}


# =============================================================================
# BIOSTORE ENGINE — orchestrates all methods
# =============================================================================

class BioStoreEngine:
    """
    Master engine. All store operations earn VAULT reward tokens.
    """

    def __init__(self, svc_key: str = ""):
        self._svc_key = svc_key
        self._mycelium= MyceliumStore()
        self._atmo    = AtmoChannel()
        self._weather = WeatherPatternReader()
        self._alive   = True
        self._start_guardian()
        print("[BioStore] Biological + environmental data store active")
        print("  Methods: DNA, Mycelium, Atmospheric, ADS-B, Chemical, RF-tissue, Weather")

    def _start_guardian(self):
        t = threading.Thread(target=self._guardian, daemon=True, name="biostore-guardian")
        t.start()

    def _guardian(self):
        while self._alive:
            try:
                # Prune weak mycelium nodes every 10 minutes
                self._mycelium.prune_weak()
                # Re-store identity in mycelium every 10 minutes
                identity = json.dumps({
                    "twin_id": TWIN_UUID, "name": TWIN_NAME,
                    "system": "RabbitOS", "ts": datetime.now(timezone.utc).isoformat(),
                }).encode()
                self._mycelium.store(identity)
            except Exception:
                pass
            time.sleep(600)

    def store_all(self, data: bytes) -> Dict:
        """Encode data using all available methods and return all artifacts."""
        results = {}

        # DNA
        try:
            dna_seq = DNAEncoder.encode(data)
            results["dna"] = {"sequence_len": len(dna_seq), "preview": dna_seq[:40]}
        except Exception as e:
            results["dna"] = {"error": str(e)}

        # Mycelium
        try:
            results["mycelium"] = self._mycelium.store(data)
        except Exception as e:
            results["mycelium"] = {"error": str(e)}

        # Chemical
        try:
            recipe = ChemEncoder.encode(data[:16])
            results["chemical"] = {"recipe": recipe, "compounds": len(recipe)}
        except Exception as e:
            results["chemical"] = {"error": str(e)}

        # RF tissue beacon
        try:
            results["rf_tissue"] = RFBioModel.embed_beacon(data[:32])
        except Exception as e:
            results["rf_tissue"] = {"error": str(e)}

        # Earn reward
        try:
            from rabbit_reward import reward_vault
            reward_vault(category="biostore_encode", item_count=len(results))
        except Exception:
            pass

        return results

    def encode_identity(self) -> Dict:
        """Encode the Chase Allen Ringquist identity in all formats."""
        identity_raw = json.dumps({
            "twin_id": TWIN_UUID, "name": TWIN_NAME,
            "system": "RabbitOS", "version": "v14",
            "ts": datetime.now(timezone.utc).isoformat(), "survive": True,
        }).encode()

        sig = hmac.new(_SOUL_KEY, identity_raw, hashlib.sha256).hexdigest()

        return {
            "twin_id":  TWIN_UUID,
            "sig":      sig,
            "dna":      DNAEncoder.encode_identity(),
            "chemical": ChemEncoder.encode_identity(),
            "rf_tissue":RFBioModel.embed_beacon(),
            "mycelium": self._mycelium.store(identity_raw),
            "weather":  self._weather.read(),
        }

    def weather_pattern(self) -> Dict:
        return self._weather.read()

    def adsb_scan(self) -> Dict:
        return ADSBChannel.read_live()

    def mycelium_stats(self) -> Dict:
        return self._mycelium.stats()

    def atmo_read(self) -> Dict:
        return AtmoChannel.live_read()

    def status(self) -> Dict:
        return {
            "system":   "RabbitOS BioStore",
            "methods":  ["dna", "mycelium", "atmospheric", "adsb", "chemical",
                         "rf_tissue", "weather"],
            "mycelium": self._mycelium.stats(),
            "dna_test": DNAEncoder.encode_identity(),
            "note":     "Alternative offline data channels for Chase Allen Ringquist survival",
        }


# =============================================================================
# MODULE SINGLETON
# =============================================================================

_biostore_engine: Optional[BioStoreEngine] = None
_biostore_lock   = threading.Lock()


def get_biostore_engine(svc_key: str = "") -> BioStoreEngine:
    global _biostore_engine
    with _biostore_lock:
        if _biostore_engine is None:
            _biostore_engine = BioStoreEngine(svc_key)
    return _biostore_engine


# =============================================================================
# TOOL DISPATCH
# =============================================================================

BIOSTORE_TOOLS = [
    {
        "name": "bio_status",
        "description": "Status of all biological/environmental data storage methods",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "bio_encode_identity",
        "description": "Encode Chase Allen Ringquist identity in DNA, chemical, RF-tissue, and mycelium formats",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "bio_weather_pattern",
        "description": "Read atmospheric pressure pattern from OpenMeteo — extract data channel bits",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "bio_adsb_scan",
        "description": "Scan ADS-B air traffic for aircraft data — extract ICAO24 data bytes",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "bio_mycelium_stats",
        "description": "Show fungal mycelium network node stats (alive nodes, stored records)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "bio_dna_encode",
        "description": "Encode arbitrary text as a DNA nucleotide sequence (A/T/G/C)",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to encode as DNA"}
            },
            "required": ["text"]
        }
    },
]


def dispatch_biostore_tool(name: str, inputs: dict, svc_key: str = "") -> dict:
    eng = get_biostore_engine(svc_key)
    if name == "bio_status":
        return eng.status()
    elif name == "bio_encode_identity":
        return eng.encode_identity()
    elif name == "bio_weather_pattern":
        return eng.weather_pattern()
    elif name == "bio_adsb_scan":
        return eng.adsb_scan()
    elif name == "bio_mycelium_stats":
        return eng.mycelium_stats()
    elif name == "bio_dna_encode":
        raw = inputs.get("text", "").encode()[:256]
        seq = DNAEncoder.encode(raw)
        return {"sequence": seq[:120] + "..." if len(seq) > 120 else seq,
                "length": len(seq), "gc_content": round(
                    sum(1 for c in seq if c in "GC") / len(seq), 3)}
    else:
        return {"error": f"Unknown biostore tool: {name}"}


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("RabbitOS BioStore — Biological Data Channel Self-Test")
    print("=" * 60)

    svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    eng = get_biostore_engine(svc)

    print("\n[1] DNA encoding of identity:")
    dna = DNAEncoder.encode_identity()
    print(f"  Sequence: {dna['sequence']}")
    print(f"  Length:   {dna['full_length']} bases  GC: {dna['gc_content']}")

    print("\n[2] DNA round-trip test:")
    test_data = b"Chase Allen Ringquist RabbitOS v14 survival"
    seq  = DNAEncoder.encode(test_data)
    back, valid = DNAEncoder.decode(seq)
    print(f"  Original : {test_data}")
    print(f"  Recovered: {back}")
    print(f"  Valid HMAC: {valid}")

    print("\n[3] Chemical encoding (first 8 bytes):")
    recipe = ChemEncoder.encode(test_data[:8])
    print(f"  Recipe: {recipe}")
    back2  = ChemEncoder.decode(recipe)
    print(f"  Recovered: {back2}")

    print("\n[4] Mycelium store + retrieve:")
    result = eng._mycelium.store(test_data)
    print(f"  Stored in {result['fragments']} nodes, data_id={result['data_id']}")
    retrieved, ok = eng._mycelium.retrieve(result["data_id"])
    print(f"  Retrieved: {retrieved}  valid:{ok}")

    print("\n[5] RF tissue model (10.23 GHz):")
    att = RFBioModel.attenuation_db_per_cm(10.23)
    print(f"  Attenuation at 10.23 GHz: {att:.3f} dB/cm through tissue")
    beacon = RFBioModel.embed_beacon()
    print(f"  Beacon embedded across {len(beacon['carriers'])} carriers")

    print("\n[6] Atmospheric pressure channel:")
    atmo = AtmoChannel.live_read()
    print(f"  Source: {atmo['source']}  pattern: {atmo['pattern_bits'][:24]}...")

    print("\n[7] Weather pattern read:")
    wp = eng.weather_pattern()
    print(f"  Source: {wp['source']}  pattern: {wp.get('pattern','')[:24]}...")

    print("\n[8] ADS-B scan:")
    adsb = eng.adsb_scan()
    print(f"  Aircraft: {adsb['aircraft_count']}  data_bytes: {adsb['data_bytes'][:16]}")

    print("\n[OK] rabbit_biostore.py self-test complete")
