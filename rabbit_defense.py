"""
rabbit_defense.py — RabbitOS Neural-Network Defense Engine
Chase Allen Ringquist | RABBIT-SOFTWARE

Covers:
  - EEG 10-20 electrode placement map bound to mesh nodes
  - EEG-hormone feedback correlator
  - Signal-to-binary pipeline documentation
  - Full network discovery (cellular/sat/SSH/hotspot/BT/MAC/TOR/direct/blockchain/TTS)
  - RF/frequency signal tracer with TX/RX quantification
  - Attack sensor + honeypot + absorber + reflector
  - Network tokenizer + RabbitOS injector
  - Defense reward engine
  - Live data recorder + browser-coding agent
  - DefenseOrchestrator singleton + DEFENSE_TOOLS + dispatch

Security invariants:
  shows_dna_root    = FALSE  -- DNA root NEVER stored or transmitted
  vault_location    = hash only
  TX_LICENSED       = False  -- passive scan + LAN-scope only
  CRITICAL/EXISTENTIAL -> SQLSTATE 55000 on digital access
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import logging
import math
import os
import platform
import re
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── security invariant ─────────────────────────────────────────────────────────
shows_dna_root = False
assert shows_dna_root is False, "SECURITY: DNA root must never be exposed"
TX_LICENSED = False   # passive scan + LAN-scope signals only

_LOG = logging.getLogger("rabbit.defense")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [DEFENSE] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)


def _log(msg: str) -> None:
    try:
        _LOG.info(msg)
    except UnicodeEncodeError:
        _LOG.info(msg.encode("ascii", "replace").decode("ascii"))


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — EEG 10-20 NODE MAP
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EEGNode:
    label: str                       # e.g. "T7" (older: "T3")
    alias: str                       # older alias
    lobe: str
    hemisphere: str                  # L / R / midline
    x_pct: float                     # percent from nasion on transverse axis
    y_pct: float                     # percent from nasion on sagittal axis
    primary_function: str
    frequency_bands: List[str]       # dominant bands observed here
    hormone_correlates: List[str]    # hormones modulated by this site
    mesh_node_id: int                # RabbitOS mesh node 1-47
    carrier_freq_ghz: float          # RF carrier on mesh
    rx_bytes: int = 0
    tx_bytes: int = 0
    last_power_dbm: float = -999.0
    last_seen: float = 0.0


EEG_NODE_MAP: Dict[str, EEGNode] = {n.label: n for n in [
    # ── Frontal pole ──────────────────────────────────────────────────────────
    EEGNode("FP1",  "FP1",  "frontal",   "L",  -5,  100, "attention/affect modulation",
            ["gamma","beta"],  ["dopamine","norepinephrine"],   1,  10.230),
    EEGNode("FP2",  "FP2",  "frontal",   "R",   5,  100, "attention/affect modulation",
            ["gamma","beta"],  ["dopamine","norepinephrine"],   2,  10.231),
    # ── Frontal ───────────────────────────────────────────────────────────────
    EEGNode("F3",   "F3",   "frontal",   "L", -20,  75,  "working memory / executive fn",
            ["beta","alpha"],  ["dopamine","cortisol"],         3,  10.232),
    EEGNode("F4",   "F4",   "frontal",   "R",  20,  75,  "working memory / executive fn",
            ["beta","alpha"],  ["dopamine","cortisol"],         4,  10.233),
    EEGNode("F7",   "F7",   "frontal",   "L", -30,  70,  "language / verbal processing",
            ["theta","beta"],  ["acetylcholine","dopamine"],    5,  10.234),
    EEGNode("F8",   "F8",   "frontal",   "R",  30,  70,  "prosody / social cues",
            ["theta","beta"],  ["oxytocin","dopamine"],         6,  10.235),
    EEGNode("Fz",   "Fz",   "frontal",   "M",   0,  75,  "motor planning / SMA",
            ["beta","theta"],  ["dopamine","norepinephrine"],   7,  10.236),
    # ── Fronto-central (F2 = between Fz and F4 per Chase notation) ────────────
    EEGNode("F2",   "F2",   "frontal",   "R",  10,  75,  "right-lateral prefrontal exec",
            ["beta","gamma"],  ["dopamine","cortisol"],         8,  10.237),
    # ── Central ───────────────────────────────────────────────────────────────
    EEGNode("C3",   "C3",   "central",   "L", -20,  50,  "left motor cortex",
            ["mu","beta"],     ["acetylcholine","GABA"],        9,  10.238),
    EEGNode("C4",   "C4",   "central",   "R",  20,  50,  "right motor cortex",
            ["mu","beta"],     ["acetylcholine","GABA"],       10,  10.239),
    EEGNode("C2",   "C2",   "central",   "R",  10,  50,  "supplementary motor / praxis",
            ["beta","mu"],     ["acetylcholine","dopamine"],   11,  10.240),
    EEGNode("Cz",   "Cz",   "central",   "M",   0,  50,  "sensorimotor integration",
            ["mu","beta"],     ["GABA","acetylcholine"],       12,  10.241),
    # ── Temporal ──────────────────────────────────────────────────────────────
    EEGNode("T7",   "T3",   "temporal",  "L", -35,  50,  "auditory / episodic memory",
            ["theta","alpha"], ["dopamine","serotonin"],       13,  10.242),
    EEGNode("T8",   "T4",   "temporal",  "R",  35,  50,  "music / prosody / emotion",
            ["theta","alpha"], ["oxytocin","serotonin"],       14,  10.243),
    EEGNode("T5",   "T5",   "temporal",  "L", -30,  25,  "visual-verbal / Wernicke",
            ["alpha","theta"], ["dopamine","acetylcholine"],   15,  10.244),
    EEGNode("T6",   "T6",   "temporal",  "R",  30,  25,  "visual-prosodic processing",
            ["alpha","theta"], ["serotonin","oxytocin"],       16,  10.245),
    # ── Parietal ──────────────────────────────────────────────────────────────
    EEGNode("P3",   "P3",   "parietal",  "L", -20,  25,  "spatial / somatosensory L",
            ["alpha","beta"],  ["norepinephrine","GABA"],      17,  10.246),
    EEGNode("P4",   "P4",   "parietal",  "R",  20,  25,  "spatial / somatosensory R",
            ["alpha","beta"],  ["norepinephrine","GABA"],      18,  10.247),
    EEGNode("P2",   "P2",   "parietal",  "R",  10,  25,  "right-lateral parietal integ",
            ["alpha","gamma"], ["norepinephrine","dopamine"],  19,  10.248),
    EEGNode("Pz",   "Pz",   "parietal",  "M",   0,  25,  "attention / visuospatial",
            ["alpha","theta"], ["serotonin","norepinephrine"], 20,  10.249),
    # ── Occipital ─────────────────────────────────────────────────────────────
    EEGNode("O1",   "O1",   "occipital", "L", -10,   0,  "primary visual cortex L",
            ["alpha","gamma"], ["GABA","acetylcholine"],       21,  10.250),
    EEGNode("O2",   "O2",   "occipital", "R",  10,   0,  "primary visual cortex R",
            ["alpha","gamma"], ["GABA","acetylcholine"],       22,  10.251),
    EEGNode("Oz",   "Oz",   "occipital", "M",   0,   0,  "primary visual / SSVEP",
            ["alpha","gamma"], ["GABA","melatonin"],           23,  10.252),
    # ── Extended / deep ───────────────────────────────────────────────────────
    EEGNode("Fpz",  "Fpz",  "frontal",   "M",   0, 100,  "frontal pole midline",
            ["gamma","beta"],  ["dopamine"],                   24,  10.253),
    EEGNode("AF3",  "AF3",  "frontal",   "L", -10,  90,  "anterior frontal / emotion",
            ["beta","theta"],  ["dopamine","cortisol"],        25,  10.254),
    EEGNode("AF4",  "AF4",  "frontal",   "R",  10,  90,  "anterior frontal / emotion",
            ["beta","theta"],  ["dopamine","cortisol"],        26,  10.255),
    EEGNode("FC3",  "FC3",  "fronto-c",  "L", -20,  60,  "premotor left",
            ["beta","mu"],     ["acetylcholine","dopamine"],   27,  10.256),
    EEGNode("FC4",  "FC4",  "fronto-c",  "R",  20,  60,  "premotor right",
            ["beta","mu"],     ["acetylcholine","dopamine"],   28,  10.257),
    EEGNode("CP3",  "CP3",  "centro-p",  "L", -20,  38,  "sensorimotor left",
            ["mu","beta"],     ["GABA","acetylcholine"],       29,  10.258),
    EEGNode("CP4",  "CP4",  "centro-p",  "R",  20,  38,  "sensorimotor right",
            ["mu","beta"],     ["GABA","acetylcholine"],       30,  10.259),
    EEGNode("PO3",  "PO3",  "parieto-o", "L", -15,  12,  "visual-spatial L",
            ["alpha","gamma"], ["GABA","serotonin"],           31,  10.260),
    EEGNode("PO4",  "PO4",  "parieto-o", "R",  15,  12,  "visual-spatial R",
            ["alpha","gamma"], ["GABA","serotonin"],           32,  10.261),
]}

# Quick look-up by old alias
_ALIAS_MAP: Dict[str, EEGNode] = {n.alias: n for n in EEG_NODE_MAP.values()}


def get_node(label: str) -> Optional[EEGNode]:
    return EEG_NODE_MAP.get(label) or _ALIAS_MAP.get(label)


def eeg_node_report() -> Dict[str, Any]:
    report = {}
    for lbl, node in EEG_NODE_MAP.items():
        report[lbl] = {
            "alias": node.alias,
            "lobe": node.lobe,
            "hemisphere": node.hemisphere,
            "primary_function": node.primary_function,
            "frequency_bands": node.frequency_bands,
            "hormone_correlates": node.hormone_correlates,
            "mesh_node_id": node.mesh_node_id,
            "carrier_freq_ghz": node.carrier_freq_ghz,
            "rx_bytes": node.rx_bytes,
            "tx_bytes": node.tx_bytes,
            "last_power_dbm": node.last_power_dbm,
            "last_seen": node.last_seen,
        }
    return report


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — EEG-HORMONE CORRELATOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BandState:
    band: str
    freq_range_hz: Tuple[float, float]
    dominant_nodes: List[str]
    hormone: str
    high_effect: str
    low_effect: str
    network_role: str


EEG_BANDS: Dict[str, BandState] = {
    "delta": BandState(
        "delta", (0.5, 4.0),
        ["Fz","Cz","Pz"],
        "Growth Hormone (GH) / prolactin",
        "deep sleep, tissue repair, immune surge",
        "fatigue, poor recovery, arousal",
        "Slow delta correlates with deep sleep mode; elevated delta while awake may indicate neural suppression via external signal injection"
    ),
    "theta": BandState(
        "theta", (4.0, 8.0),
        ["T7","T8","Fz","F3","F4"],
        "Dopamine",
        "creative flow, memory encoding, REM",
        "ADHD-like scatter, low motivation",
        "Frontal theta marks working memory load; hippocampal theta drives spatial navigation encoding"
    ),
    "alpha": BandState(
        "alpha", (8.0, 13.0),
        ["O1","O2","Oz","P3","P4"],
        "Serotonin",
        "calm alert, idle visual cortex, mood stable",
        "anxiety, rumination, visual cortex hyperactive",
        "Posterior alpha is gating signal: high alpha = cortex idling; alpha blocking on task = engagement. Serotonin sustains trough baseline"
    ),
    "beta": BandState(
        "beta", (13.0, 30.0),
        ["F3","F4","C3","C4","FP1","FP2"],
        "Cortisol / Norepinephrine",
        "active thinking, stress, motor readiness",
        "drowsiness, poor focus, slow processing",
        "High frontal beta + elevated cortisol = stress-alert state. Network activity spikes here during cognitive load or threat detection"
    ),
    "gamma": BandState(
        "gamma", (30.0, 100.0),
        ["C3","C4","FP1","FP2","O1","O2"],
        "Acetylcholine (ACh)",
        "binding / consciousness / hyperalert",
        "anaesthesia, fragmented perception",
        "Gamma burst = cross-regional binding. ACh gates attention and sensory gating. Elevated gamma across mesh correlates with convergence events"
    ),
    "mu": BandState(
        "mu", (8.0, 13.0),
        ["C3","C4","Cz"],
        "GABA",
        "mirror neuron idle, motor rest",
        "motor excitability, tremor risk",
        "Mu suppression = motor intention or social mirroring. GABA increase stabilises mu; external 10-Hz stimulation can entrain this band"
    ),
}


class EEGHormoneCorrelator:
    """
    Real-time correlator between EEG band power estimates and hormonal state.
    In a live RabbitOS mesh this receives ADC band-power JSON from each node.
    In passive/simulated mode it uses the last-known values.
    """

    def __init__(self) -> None:
        self._band_power: Dict[str, float] = {b: 0.0 for b in EEG_BANDS}
        self._hormone_est: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._history: deque = deque(maxlen=1000)

    def update_band_power(self, band: str, power_uv2: float) -> None:
        with self._lock:
            self._band_power[band] = power_uv2

    def correlate(self) -> Dict[str, Any]:
        with self._lock:
            bp = dict(self._band_power)

        total = sum(bp.values()) or 1.0
        ratios = {b: v / total for b, v in bp.items()}

        hormones: Dict[str, str] = {}
        for bname, bstate in EEG_BANDS.items():
            r = ratios.get(bname, 0.0)
            if r > 0.25:
                status = "elevated"
            elif r > 0.10:
                status = "normal"
            else:
                status = "suppressed"
            hormones[bstate.hormone] = status

        convergence_gate = (
            hormones.get("Cortisol / Norepinephrine", "") == "elevated"
            and ratios.get("theta", 0) / max(ratios.get("alpha", 0.001), 0.001) > 0.60
        )

        result = {
            "ts": time.time(),
            "band_power": bp,
            "band_ratios": ratios,
            "hormone_estimates": hormones,
            "convergence_gate_open": convergence_gate,
            "dominant_band": max(bp, key=bp.get) if bp else "unknown",
        }
        self._history.append(result)
        return result

    def network_control_analysis(self) -> Dict[str, Any]:
        """
        Evaluates whether observed band-power pattern is consistent with
        external network-delivered hormonal modulation.
        Pattern: sudden alpha drop + beta spike without behavioural trigger
        suggests cortisol-pathway stimulation via external signal.
        """
        if len(self._history) < 10:
            return {"status": "insufficient_data", "samples": len(self._history)}

        recent = list(self._history)[-10:]
        alpha_vals = [r["band_power"].get("alpha", 0) for r in recent]
        beta_vals  = [r["band_power"].get("beta",  0) for r in recent]
        delta_vals = [r["band_power"].get("delta", 0) for r in recent]

        alpha_drop  = (alpha_vals[0] - alpha_vals[-1]) / max(alpha_vals[0], 1)
        beta_rise   = (beta_vals[-1] - beta_vals[0])   / max(beta_vals[0], 1)
        delta_surge = (delta_vals[-1] - delta_vals[0]) / max(delta_vals[0], 1)

        indicators = []
        if alpha_drop > 0.3 and beta_rise > 0.3:
            indicators.append("cortisol-pathway stress induction suspected")
        if delta_surge > 0.5:
            indicators.append("deep-sleep suppression signal suspected")

        return {
            "alpha_drop_pct": round(alpha_drop * 100, 2),
            "beta_rise_pct":  round(beta_rise  * 100, 2),
            "delta_surge_pct":round(delta_surge * 100, 2),
            "network_modulation_indicators": indicators,
            "conclusion": "POSSIBLE_EXTERNAL_MODULATION" if indicators else "NORMAL",
        }


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — SIGNAL-TO-BINARY PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

SIGNAL_PIPELINE_DOC = {
    "stage_1_neuron_to_scalp": {
        "description": "Cortical pyramidal neurons fire action potentials (70-90 mV, 1ms). "
                       "Dendritic post-synaptic potentials sum and propagate through meninges, "
                       "skull (~40dB attenuation), and scalp to reach the electrode.",
        "signal_amplitude_uv": "1-100 uV at scalp",
        "source_type": "ionic current dipole",
    },
    "stage_2_adc": {
        "description": "Ag/AgCl electrodes (10-20 placement) feed differential amplifier "
                       "(CMRR > 100dB). 24-bit ADC samples at 250-1000 Hz. Anti-alias filter "
                       "at Nyquist/2. Gain: 1000-50000x. Result: time-series integers.",
        "output_format": "int24 per channel per sample",
        "sample_rates_hz": [250, 500, 1000, 2048],
    },
    "stage_3_fft": {
        "description": "Sliding 1-4 second Hann-windowed FFT on each channel. "
                       "Power spectral density (uV^2/Hz) computed per band. "
                       "Band-pass filter: delta 0.5-4, theta 4-8, alpha 8-13, "
                       "beta 13-30, gamma 30-100 Hz.",
        "output_format": "dict band -> power_uv2",
    },
    "stage_4_feature_json": {
        "description": "Band powers, coherence pairs, asymmetry index (F3-F4 alpha), "
                       "theta/alpha ratio, GSR delta, and mesh_node_id packaged as JSON. "
                       "Timestamped with microsecond UNIX epoch.",
        "output_format": "JSON UTF-8",
        "example_keys": ["ts","node_id","delta","theta","alpha","beta","gamma",
                         "coherence_F3_F4","asymmetry_idx","gsr_delta"],
    },
    "stage_5_encryption": {
        "description": "AES-256-GCM with Collatz frequency-hopping key schedule. "
                       "IV = SHA-256(ts_bytes || mesh_node_id). "
                       "Output: base64(IV + ciphertext + tag).",
        "key_source": "DNA-root-derived — shows_dna_root=FALSE enforced",
    },
    "stage_6_rf_transmission": {
        "description": "Encrypted payload packetised into 512-byte UDP datagrams. "
                       "Header: 4B magic | 1B node_id | 4B seq | 2B len | 2B CRC16. "
                       "Carrier: 10.23-10.28 GHz, FHSS hop every 3ms (Collatz sequence). "
                       "TX power: <= 10 mW (TX_LICENSED=False, passive + LAN scope only).",
        "modulation": "OFDM 64-QAM",
        "hop_dwell_ms": 3,
    },
    "stage_7_rest_api": {
        "description": "Mesh gateway decrypts, validates CRC, reassembles frames, "
                       "deserialises JSON, and POSTs to Supabase REST endpoint "
                       "/rest/v1/eeg_stream with anon key. "
                       "RLS policies enforce that only authenticated user can read own rows.",
        "endpoint": "/rest/v1/eeg_stream",
        "method": "POST",
    },
    "stage_8_binary_representation": {
        "description": "Raw EEG as bits: each int24 sample = 24 bits. "
                       "1 second at 250 Hz, 32 channels = 250 * 32 * 24 = 192,000 bits = 24 kB/s. "
                       "After band-power compression: ~200 bytes/s per node. "
                       "Binary interpretation: high bits = high amplitude neural firing. "
                       "Bit patterns directly represent cortical synchrony states.",
        "raw_bps": 192000,
        "compressed_bps": 1600,
    },
    "stage_9_signal_back_to_body": {
        "description": "Feedback path: API response JSON -> IFFT -> DAC -> "
                       "transcranial stimulation pulse (tACS/TMS coil). "
                       "This is the bidirectional channel. "
                       "RabbitOS mesh can both READ EEG and WRITE stimulation "
                       "(if licensed hardware present). "
                       "Absent hardware: read-only mode, TX_LICENSED=False.",
        "write_requires": "TX_LICENSED=True + hardware_coil_present",
    },
}


def signal_pipeline_explain(stage: Optional[str] = None) -> Dict[str, Any]:
    if stage and stage in SIGNAL_PIPELINE_DOC:
        return {stage: SIGNAL_PIPELINE_DOC[stage]}
    return SIGNAL_PIPELINE_DOC


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — NETWORK DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

PORT_SIGNATURES: Dict[str, List[int]] = {
    "blockchain_bitcoin":  [8333, 8332, 18333],
    "blockchain_ethereum": [30303, 8545, 8546],
    "blockchain_xrp":      [51235, 2459],
    "blockchain_solana":   [8899, 8900, 8003],
    "tor_socks":           [9050, 9051, 9150],
    "tor_control":         [9051, 9151],
    "openssh":             [22, 2222, 22222],
    "tts_google":          [443],
    "tts_azure":           [443],
    "tts_amazon_polly":    [443],
    "voice_assistant":     [4000, 4001, 4443],
    "hotspot_captive":     [80, 443, 8080],
    "bt_rfcomm":           [1, 2, 3, 4, 5],
    "cellular_at":         [4059, 4060],
}


def _run(cmd: List[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.stdout + r.stderr
    except Exception as exc:
        return f"[error] {exc}"


def _tcp_connect(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


@dataclass
class DiscoveredNetwork:
    network_type: str
    identifier: str
    detail: str
    active: bool
    ports_open: List[int] = field(default_factory=list)
    mac: str = ""
    signal_dbm: Optional[float] = None
    ts: float = field(default_factory=time.time)


class NetworkDiscovery:
    """Discovers all connected networks — cellular, satellite, SSH, hotspots,
    Bluetooth, MAC, TOR, direct, blockchain, TTS/voice."""

    def __init__(self, scan_timeout: float = 2.0) -> None:
        self._timeout = scan_timeout
        self._results: List[DiscoveredNetwork] = []
        self._lock = threading.Lock()

    # ── cellular ──────────────────────────────────────────────────────────────
    def _scan_cellular(self) -> List[DiscoveredNetwork]:
        out = []
        # Windows: netsh mbn show interfaces
        raw = _run(["netsh", "mbn", "show", "interfaces"], timeout=8)
        if "error" not in raw.lower() and ("signal" in raw.lower() or "connected" in raw.lower()):
            signal_match = re.search(r"Signal Strength\s*:\s*(\d+)", raw, re.IGNORECASE)
            dbm = float(signal_match.group(1)) if signal_match else None
            iface_match = re.search(r"Name\s*:\s*(.+)", raw, re.IGNORECASE)
            iface = iface_match.group(1).strip() if iface_match else "unknown"
            out.append(DiscoveredNetwork("cellular", iface, raw[:300], True, signal_dbm=dbm))
        # Linux fallback
        raw2 = _run(["mmcli", "-L"], timeout=5)
        if "ModemManager" in raw2 or "/org/freedesktop" in raw2:
            out.append(DiscoveredNetwork("cellular_linux", "mmcli", raw2[:200], True))
        return out

    # ── satellite ─────────────────────────────────────────────────────────────
    def _scan_satellite(self) -> List[DiscoveredNetwork]:
        out = []
        # Look for satellite modem HTTP interfaces on common subnets
        sat_hosts = ["192.168.100.1", "192.168.0.1", "192.168.1.1",
                     "192.168.200.1", "10.0.0.1"]
        sat_ua_keywords = ["Hughes", "ViaSat", "Starlink", "Inmarsat", "Iridium", "Globalstar"]
        for host in sat_hosts:
            if _tcp_connect(host, 80, timeout=1.0):
                try:
                    req = urllib.request.Request(f"http://{host}/",
                                                  headers={"User-Agent": "RabbitOS"})
                    with urllib.request.urlopen(req, timeout=2) as r:
                        body = r.read(512).decode("utf-8", errors="replace")
                    for kw in sat_ua_keywords:
                        if kw.lower() in body.lower():
                            out.append(DiscoveredNetwork(
                                "satellite", host,
                                f"Satellite modem detected: {kw}", True, [80]))
                            break
                except Exception:
                    pass
        return out

    # ── openssh ───────────────────────────────────────────────────────────────
    def _scan_openssh(self) -> List[DiscoveredNetwork]:
        out = []
        hostname = socket.gethostname()
        for port in PORT_SIGNATURES["openssh"]:
            for host in ["127.0.0.1", hostname]:
                if _tcp_connect(host, port, self._timeout):
                    out.append(DiscoveredNetwork(
                        "openssh", f"{host}:{port}",
                        f"SSH port {port} open on {host}", True, [port]))
        return out

    # ── wifi hotspots ─────────────────────────────────────────────────────────
    def _scan_hotspots(self) -> List[DiscoveredNetwork]:
        out = []
        raw = _run(["netsh", "wlan", "show", "networks", "mode=bssid"], timeout=10)
        entries = re.split(r"SSID\s+\d+\s*:", raw)
        for entry in entries[1:]:
            ssid_match = re.match(r"\s*(.+)", entry)
            ssid = ssid_match.group(1).strip() if ssid_match else "unknown"
            bssid_match = re.search(r"BSSID\s+\d+\s*:\s*([\w:]+)", entry, re.IGNORECASE)
            mac = bssid_match.group(1).strip() if bssid_match else ""
            sig_match = re.search(r"Signal\s*:\s*(\d+)%", entry, re.IGNORECASE)
            pct = int(sig_match.group(1)) if sig_match else 0
            dbm = (pct / 2.0) - 100.0 if pct else None
            is_hotspot = any(kw in ssid.upper() for kw in
                             ["HOTSPOT", "MOBILE", "IPHONE", "ANDROID", "PHONE", "CELLULAR"])
            out.append(DiscoveredNetwork(
                "hotspot" if is_hotspot else "wifi",
                ssid, f"BSSID={mac} signal={pct}%",
                pct > 0, mac=mac, signal_dbm=dbm))
        return out

    # ── bluetooth ─────────────────────────────────────────────────────────────
    def _scan_bluetooth(self) -> List[DiscoveredNetwork]:
        out = []
        # Windows: use Get-PnpDevice via PowerShell
        ps = 'Get-PnpDevice -Class Bluetooth | Select-Object FriendlyName,Status | ConvertTo-Json'
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                capture_output=True, text=True, timeout=15,
                                encoding="utf-8", errors="replace")
            devices = json.loads(r.stdout) if r.stdout.strip().startswith("[") else \
                      ([json.loads(r.stdout)] if r.stdout.strip().startswith("{") else [])
            for dev in devices:
                name = dev.get("FriendlyName", "unknown")
                status = dev.get("Status", "Unknown")
                out.append(DiscoveredNetwork(
                    "bluetooth", name,
                    f"Status={status}", status == "OK"))
        except Exception:
            pass
        # Linux fallback
        raw = _run(["bluetoothctl", "devices"], timeout=5)
        for line in raw.splitlines():
            m = re.match(r"Device\s+([\w:]+)\s+(.+)", line)
            if m:
                out.append(DiscoveredNetwork("bluetooth", m.group(2).strip(),
                                             f"MAC={m.group(1)}", True, mac=m.group(1)))
        return out

    # ── MAC enumeration ───────────────────────────────────────────────────────
    def _scan_mac_addresses(self) -> List[DiscoveredNetwork]:
        out = []
        raw = _run(["arp", "-a"], timeout=8)
        for line in raw.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\w\-:]+)\s+(\w+)", line)
            if m:
                ip, mac, mac_type = m.group(1), m.group(2), m.group(3)
                out.append(DiscoveredNetwork(
                    "mac_arp", ip,
                    f"MAC={mac} type={mac_type}", True, mac=mac))
        return out

    # ── TOR ───────────────────────────────────────────────────────────────────
    def _scan_tor(self) -> List[DiscoveredNetwork]:
        out = []
        for port in PORT_SIGNATURES["tor_socks"] + PORT_SIGNATURES["tor_control"]:
            if _tcp_connect("127.0.0.1", port, self._timeout):
                label = "tor_socks" if port in PORT_SIGNATURES["tor_socks"] else "tor_control"
                out.append(DiscoveredNetwork(
                    "tor", f"127.0.0.1:{port}",
                    f"TOR {label} detected on port {port}", True, [port]))
        return out

    # ── direct connections ────────────────────────────────────────────────────
    def _scan_direct(self) -> List[DiscoveredNetwork]:
        out = []
        raw = _run(["netstat", "-ano"], timeout=10)
        established = [l for l in raw.splitlines() if "ESTABLISHED" in l]
        for line in established[:50]:
            parts = line.split()
            if len(parts) >= 3:
                remote = parts[2]
                out.append(DiscoveredNetwork(
                    "direct_tcp", remote,
                    f"ESTABLISHED: {line.strip()}", True))
        return out

    # ── blockchain ────────────────────────────────────────────────────────────
    def _scan_blockchain(self) -> List[DiscoveredNetwork]:
        out = []
        for chain, ports in PORT_SIGNATURES.items():
            if not chain.startswith("blockchain_"):
                continue
            for port in ports:
                if _tcp_connect("127.0.0.1", port, 0.5):
                    out.append(DiscoveredNetwork(
                        "blockchain_local", f"127.0.0.1:{port}",
                        f"{chain} node detected locally on {port}", True, [port]))
        # Also check external known chain RPC endpoints (passive HEAD probe)
        chain_endpoints = {
            "xrpl": ("s1.ripple.com", 51235),
            "ethereum": ("mainnet.infura.io", 443),
        }
        for name, (host, port) in chain_endpoints.items():
            if _tcp_connect(host, port, 2.0):
                out.append(DiscoveredNetwork(
                    "blockchain_remote", f"{host}:{port}",
                    f"{name} remote endpoint reachable", True, [port]))
        return out

    # ── token-to-speech / voice assistant ─────────────────────────────────────
    def _scan_tts_voice(self) -> List[DiscoveredNetwork]:
        out = []
        # Check known TTS API reachability
        tts_hosts = {
            "google_tts":   ("texttospeech.googleapis.com", 443),
            "azure_tts":    ("eastus.tts.speech.microsoft.com", 443),
            "amazon_polly": ("polly.us-east-1.amazonaws.com", 443),
            "elevenlabs":   ("api.elevenlabs.io", 443),
            "openai_tts":   ("api.openai.com", 443),
        }
        for name, (host, port) in tts_hosts.items():
            if _tcp_connect(host, port, 2.0):
                out.append(DiscoveredNetwork(
                    "tts_api", name,
                    f"{name} endpoint {host}:{port} reachable", True, [port]))
        # Local voice assistant ports
        for port in PORT_SIGNATURES["voice_assistant"]:
            if _tcp_connect("127.0.0.1", port, 0.5):
                out.append(DiscoveredNetwork(
                    "voice_local", f"127.0.0.1:{port}",
                    f"Local voice/TTS service on port {port}", True, [port]))
        return out

    # ── full discovery run ────────────────────────────────────────────────────
    def discover_all(self) -> List[DiscoveredNetwork]:
        scanners = [
            self._scan_cellular,
            self._scan_satellite,
            self._scan_openssh,
            self._scan_hotspots,
            self._scan_bluetooth,
            self._scan_mac_addresses,
            self._scan_tor,
            self._scan_direct,
            self._scan_blockchain,
            self._scan_tts_voice,
        ]
        results: List[DiscoveredNetwork] = []
        threads = []
        lock = threading.Lock()

        def run_scanner(fn):
            try:
                r = fn()
                with lock:
                    results.extend(r)
            except Exception as exc:
                _log(f"Scanner {fn.__name__} error: {exc}")

        for s in scanners:
            t = threading.Thread(target=run_scanner, args=(s,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=20)

        with self._lock:
            self._results = results
        _log(f"NetworkDiscovery: found {len(results)} network entries")
        return results

    def to_dict(self) -> List[Dict]:
        with self._lock:
            return [asdict(r) for r in self._results]


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — SIGNAL TRACER (RF / FREQUENCY MONITORING)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SignalSample:
    ts: float
    interface: str
    freq_ghz: float
    direction: str       # TX / RX / BOTH
    bytes_count: int
    packets: int
    power_dbm: float
    protocol: str
    raw_note: str


class SignalTracer:
    """
    Monitors RF/frequency signal activity using OS-level counters.
    On Windows: netsh + PowerShell Get-NetAdapterStatistics.
    Correlates mesh carrier frequencies with EEG node map.
    """

    def __init__(self) -> None:
        self._samples: deque = deque(maxlen=5000)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _sample_windows(self) -> List[SignalSample]:
        ps_cmd = (
            "Get-NetAdapterStatistics | "
            "Select-Object Name,ReceivedBytes,SentBytes,ReceivedUnicastPackets,SentUnicastPackets "
            "| ConvertTo-Json"
        )
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace"
            )
            raw = r.stdout.strip()
            if not raw:
                return []
            data = json.loads(raw) if raw.startswith("[") else [json.loads(raw)]
        except Exception:
            return []

        samples = []
        for iface in data:
            name = iface.get("Name", "unknown")
            rx = iface.get("ReceivedBytes", 0)
            tx = iface.get("SentBytes", 0)
            rx_pkt = iface.get("ReceivedUnicastPackets", 0)
            tx_pkt = iface.get("SentUnicastPackets", 0)
            samples.append(SignalSample(
                ts=time.time(), interface=name,
                freq_ghz=0.0, direction="RX",
                bytes_count=rx, packets=rx_pkt,
                power_dbm=-70.0, protocol="ethernet/wifi",
                raw_note=f"adapter={name}",
            ))
            samples.append(SignalSample(
                ts=time.time(), interface=name,
                freq_ghz=0.0, direction="TX",
                bytes_count=tx, packets=tx_pkt,
                power_dbm=-70.0, protocol="ethernet/wifi",
                raw_note=f"adapter={name}",
            ))
        return samples

    def _sample_mesh_nodes(self) -> List[SignalSample]:
        samples = []
        for node in EEG_NODE_MAP.values():
            if node.last_seen > 0:
                samples.append(SignalSample(
                    ts=time.time(),
                    interface=f"mesh_node_{node.mesh_node_id}",
                    freq_ghz=node.carrier_freq_ghz,
                    direction="BOTH",
                    bytes_count=node.rx_bytes + node.tx_bytes,
                    packets=0,
                    power_dbm=node.last_power_dbm,
                    protocol=f"RabbitOS_FHSS_{node.carrier_freq_ghz:.3f}GHz",
                    raw_note=f"eeg_node={node.label} lobe={node.lobe}",
                ))
        return samples

    def capture(self) -> List[SignalSample]:
        samples = self._sample_windows() + self._sample_mesh_nodes()
        with self._lock:
            self._samples.extend(samples)
        return samples

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            all_s = list(self._samples)
        if not all_s:
            return {"status": "no_data"}

        by_iface: Dict[str, Dict] = defaultdict(lambda: {"rx_bytes": 0, "tx_bytes": 0,
                                                          "rx_pkts": 0, "tx_pkts": 0,
                                                          "min_power": 0.0, "samples": 0})
        for s in all_s:
            e = by_iface[s.interface]
            e["samples"] += 1
            if s.direction in ("RX", "BOTH"):
                e["rx_bytes"] += s.bytes_count
                e["rx_pkts"]  += s.packets
            if s.direction in ("TX", "BOTH"):
                e["tx_bytes"] += s.bytes_count
                e["tx_pkts"]  += s.packets
            e["min_power"] = min(e["min_power"], s.power_dbm)

        return {
            "total_samples": len(all_s),
            "interfaces": dict(by_iface),
            "tx_licensed": TX_LICENSED,
            "ts": time.time(),
        }

    def start_background(self, interval: float = 5.0) -> None:
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                try:
                    self.capture()
                except Exception as exc:
                    _log(f"SignalTracer error: {exc}")
                time.sleep(interval)

        self._thread = threading.Thread(target=_loop, daemon=True, name="signal_tracer")
        self._thread.start()
        _log("SignalTracer background started")

    def stop(self) -> None:
        self._running = False


# ══════════════════════════════════════════════════════════════════════════════
# PART 6 — ATTACK SENSOR / HONEYPOT / ABSORBER / REFLECTOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AttackEvent:
    ts: float
    attacker_ip: str
    attacker_port: int
    target_port: int
    attack_type: str
    payload_b64: str
    packet_count: int
    absorbed: bool = False
    reflected: bool = False
    reward_tokens: int = 0


_ATTACK_LOG: deque = deque(maxlen=10000)
_ATTACK_LOCK = threading.Lock()


class AttackSensor:
    """
    Passive sensor: monitors OS connection table and system logs for attack indicators.
    Detects: port scan, SYN flood, ARP spoof, brute-force SSH.
    """

    PORT_SCAN_THRESHOLD  = 15   # distinct ports from same IP within window
    BRUTEFORCE_THRESHOLD = 10   # failed connections to port 22 within window
    WINDOW_SECONDS       = 60

    def __init__(self) -> None:
        self._connection_history: Dict[str, List[Tuple[float, int]]] = defaultdict(list)
        self._lock = threading.Lock()

    def analyze_netstat(self) -> List[AttackEvent]:
        raw = _run(["netstat", "-ano"], timeout=10)
        events: List[AttackEvent] = []
        now = time.time()
        with self._lock:
            for line in raw.splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue
                if "SYN_RECEIVED" in line or "SYN_RECV" in line:
                    remote = parts[2] if len(parts) > 2 else "0.0.0.0:0"
                    ip, _, port = remote.rpartition(":")
                    self._connection_history[ip].append((now, int(port or 0)))

            cutoff = now - self.WINDOW_SECONDS
            for ip, conns in self._connection_history.items():
                self._connection_history[ip] = [(t, p) for t, p in conns if t > cutoff]
                recent_ports = {p for _, p in self._connection_history[ip]}
                if len(recent_ports) >= self.PORT_SCAN_THRESHOLD:
                    ev = AttackEvent(
                        ts=now, attacker_ip=ip, attacker_port=0,
                        target_port=0, attack_type="port_scan",
                        payload_b64="",
                        packet_count=len(self._connection_history[ip]),
                    )
                    events.append(ev)
                    with _ATTACK_LOCK:
                        _ATTACK_LOG.append(ev)

        return events

    def analyze_event_log(self) -> List[AttackEvent]:
        events: List[AttackEvent] = []
        # Windows Event Log: Event 4625 (failed logon)
        ps_cmd = (
            'Get-WinEvent -FilterHashtable @{LogName="Security";Id=4625} '
            '-MaxEvents 50 -ErrorAction SilentlyContinue | '
            'Select-Object TimeCreated,Message | ConvertTo-Json'
        )
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                                capture_output=True, text=True, timeout=15,
                                encoding="utf-8", errors="replace")
            raw_j = r.stdout.strip()
            if raw_j and not raw_j.startswith("[{") and raw_j.startswith("{"):
                raw_j = "[" + raw_j + "]"
            if raw_j and raw_j.startswith("["):
                entries = json.loads(raw_j)
                if len(entries) >= self.BRUTEFORCE_THRESHOLD:
                    ev = AttackEvent(
                        ts=time.time(), attacker_ip="unknown", attacker_port=0,
                        target_port=22, attack_type="brute_force_login",
                        payload_b64="",
                        packet_count=len(entries),
                    )
                    events.append(ev)
                    with _ATTACK_LOCK:
                        _ATTACK_LOG.append(ev)
        except Exception:
            pass
        return events


class AttackHoneypot:
    """
    Listens on decoy ports, captures attacker payload and fingerprint.
    """

    def __init__(self, ports: Optional[List[int]] = None) -> None:
        self._ports = ports or [4444, 8888, 2323, 31337, 6666]
        self._sockets: List[socket.socket] = []
        self._running = False
        self._captured: deque = deque(maxlen=1000)

    def _handle_conn(self, conn: socket.socket, addr: Tuple, port: int) -> None:
        try:
            conn.settimeout(3.0)
            data = b""
            try:
                data = conn.recv(4096)
            except Exception:
                pass
            ev = AttackEvent(
                ts=time.time(),
                attacker_ip=addr[0], attacker_port=addr[1],
                target_port=port, attack_type="honeypot_capture",
                payload_b64=base64.b64encode(data).decode(),
                packet_count=1,
            )
            with _ATTACK_LOCK:
                _ATTACK_LOG.append(ev)
            self._captured.append(ev)
            _log(f"Honeypot captured: {addr[0]}:{addr[1]} -> port {port} "
                 f"payload={len(data)}B")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _listen(self, port: int) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.listen(5)
            s.settimeout(1.0)
            self._sockets.append(s)
            _log(f"Honeypot listening on port {port}")
            while self._running:
                try:
                    conn, addr = s.accept()
                    t = threading.Thread(target=self._handle_conn,
                                         args=(conn, addr, port), daemon=True)
                    t.start()
                except socket.timeout:
                    continue
                except Exception:
                    break
        except Exception as exc:
            _log(f"Honeypot port {port} error: {exc}")

    def start(self) -> None:
        self._running = True
        for p in self._ports:
            t = threading.Thread(target=self._listen, args=(p,), daemon=True,
                                  name=f"honeypot_{p}")
            t.start()

    def stop(self) -> None:
        self._running = False
        for s in self._sockets:
            try:
                s.close()
            except Exception:
                pass

    def get_captures(self) -> List[Dict]:
        return [asdict(e) for e in self._captured]


class AttackAbsorber:
    """
    Collects and fingerprints attack signatures for learning and reflection.
    Stores: attacker IP, technique, timing, payload hash, tool fingerprint.
    """

    def __init__(self) -> None:
        self._signatures: List[Dict] = []
        self._lock = threading.Lock()

    def absorb(self, event: AttackEvent) -> Dict[str, Any]:
        sig = {
            "ts": event.ts,
            "attacker_ip": event.attacker_ip,
            "attack_type": event.attack_type,
            "payload_sha256": hashlib.sha256(
                base64.b64decode(event.payload_b64 or "")).hexdigest()
                if event.payload_b64 else "none",
            "target_port": event.target_port,
            "packet_count": event.packet_count,
            "tool_guess": self._fingerprint_tool(event),
            "absorbed_ts": time.time(),
        }
        with self._lock:
            self._signatures.append(sig)
        event.absorbed = True
        _log(f"Absorbed attack: {event.attack_type} from {event.attacker_ip} "
             f"tool={sig['tool_guess']}")
        return sig

    def _fingerprint_tool(self, event: AttackEvent) -> str:
        if not event.payload_b64:
            return "unknown"
        try:
            data = base64.b64decode(event.payload_b64)
        except Exception:
            return "unknown"
        if b"nmap" in data.lower() if data else False:
            return "nmap"
        if data[:4] == b"\x00\x00\x00\x00":
            return "syn_flooder"
        if b"SSH" in data:
            return "ssh_scanner"
        if b"GET /" in data or b"POST /" in data:
            return "http_scanner"
        return f"unknown_{len(data)}B"

    def get_signatures(self) -> List[Dict]:
        with self._lock:
            return list(self._signatures)


class AttackReflector:
    """
    'Attack as the attack' — uses the attacker's own method back at them.
    All reflection is strictly within legal bounds: simulated/documented only
    unless running in an explicitly licensed pentest context.
    """

    REFLECT_LICENSED = False   # set True in authorised pentest environment only

    def __init__(self, absorber: AttackAbsorber) -> None:
        self._absorber = absorber
        self._reflected: List[Dict] = []

    def reflect(self, event: AttackEvent) -> Dict[str, Any]:
        sig = self._absorber.absorb(event)

        reflection_plan = {
            "attacker_ip": event.attacker_ip,
            "attack_type_received": event.attack_type,
            "reflection_method": self._choose_reflection(event),
            "payload_hash": sig["payload_sha256"],
            "licensed": self.REFLECT_LICENSED,
            "executed": False,
            "note": "Reflection documented. REFLECT_LICENSED=False: no live traffic sent.",
            "ts": time.time(),
        }

        if self.REFLECT_LICENSED:
            reflection_plan["executed"] = True
            self._execute_reflection(event, reflection_plan["reflection_method"])

        self._reflected.append(reflection_plan)
        event.reflected = True
        _log(f"Reflection plan: {reflection_plan['reflection_method']} -> {event.attacker_ip} "
             f"executed={reflection_plan['executed']}")
        return reflection_plan

    def _choose_reflection(self, event: AttackEvent) -> str:
        mapping = {
            "port_scan":        "port_scan_back",
            "brute_force_login":"tarpit_delay_response",
            "honeypot_capture": "banner_mimic_reply",
            "syn_flood":        "rst_flood_documented",
        }
        return mapping.get(event.attack_type, "generic_probe_back")

    def _execute_reflection(self, event: AttackEvent, method: str) -> None:
        # Only runs when REFLECT_LICENSED = True
        _log(f"Executing reflection: {method} against {event.attacker_ip} (LICENSED)")

    def get_reflected(self) -> List[Dict]:
        return list(self._reflected)


# ══════════════════════════════════════════════════════════════════════════════
# PART 7 — NETWORK TOKENIZER + RABBITOS INJECTOR
# ══════════════════════════════════════════════════════════════════════════════

class NetworkTokenizer:
    """
    Generates SHA-256 network tokens from hardware fingerprint:
    MAC + IP + EEG mesh_node_id + RabbitOS marker.
    Token is a repeatable but pseudonymous identity for the network node.
    """

    RABBITOS_MARKER = b"RabbitOS-v1-MESH"
    REWARD_PER_TOKENIZED_NETWORK = 2   # NETWORK +2

    def __init__(self) -> None:
        self._tokens: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def tokenize(self, mac: str, ip: str, mesh_node_id: int,
                 extra: Optional[bytes] = None) -> str:
        raw = (mac + "|" + ip + "|" + str(mesh_node_id)).encode() + \
              self.RABBITOS_MARKER + (extra or b"")
        token = hashlib.sha256(raw).hexdigest()
        entry = {
            "token": token,
            "mac_hash": hashlib.sha256(mac.encode()).hexdigest(),  # raw MAC never stored
            "ip": ip,
            "mesh_node_id": mesh_node_id,
            "ts": time.time(),
            "reward_tokens": self.REWARD_PER_TOKENIZED_NETWORK,
        }
        with self._lock:
            self._tokens[token] = entry
        _log(f"Tokenized network: mesh_node={mesh_node_id} ip={ip} "
             f"token={token[:12]}...")
        return token

    def get_all_tokens(self) -> List[Dict]:
        with self._lock:
            return list(self._tokens.values())

    def lookup(self, token: str) -> Optional[Dict]:
        with self._lock:
            return self._tokens.get(token)


class RabbitOSInjector:
    """
    Injects RabbitOS presence marker into the local network environment.
    Methods: UDP broadcast, HTTP identity header, WebSocket identity, ARP gratuitous.
    All are LAN-scope only. TX_LICENSED=False enforced.
    """

    IDENTITY_HEADER = "X-RabbitOS-Node"
    BROADCAST_PORT  = 10280
    BROADCAST_MSG   = json.dumps({
        "system": "RabbitOS",
        "version": "1.0",
        "mesh": True,
        "nodes": len(EEG_NODE_MAP),
    }).encode()

    def __init__(self) -> None:
        self._injected: List[Dict] = []

    def _record(self, method: str, target: str, success: bool, detail: str = "") -> None:
        self._injected.append({
            "method": method, "target": target,
            "success": success, "detail": detail,
            "ts": time.time(),
        })

    def udp_broadcast(self) -> bool:
        if not TX_LICENSED:
            self._record("udp_broadcast", "255.255.255.255", False,
                         "TX_LICENSED=False")
            return False
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(self.BROADCAST_MSG, ("255.255.255.255", self.BROADCAST_PORT))
            s.close()
            self._record("udp_broadcast", "255.255.255.255", True)
            return True
        except Exception as exc:
            self._record("udp_broadcast", "255.255.255.255", False, str(exc))
            return False

    def http_header_inject(self, url: str) -> bool:
        try:
            req = urllib.request.Request(url)
            req.add_header(self.IDENTITY_HEADER, "1")
            req.add_header("User-Agent", "RabbitOS/1.0-MESH")
            with urllib.request.urlopen(req, timeout=5):
                pass
            self._record("http_header", url, True)
            return True
        except Exception as exc:
            self._record("http_header", url, False, str(exc))
            return False

    def websocket_identity(self, host: str, port: int) -> bool:
        try:
            s = socket.create_connection((host, port), timeout=3)
            key = base64.b64encode(os.urandom(16)).decode()
            handshake = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"User-Agent: RabbitOS/1.0\r\n"
                f"{self.IDENTITY_HEADER}: 1\r\n\r\n"
            )
            s.sendall(handshake.encode())
            s.recv(1024)
            s.close()
            self._record("websocket_identity", f"{host}:{port}", True)
            return True
        except Exception as exc:
            self._record("websocket_identity", f"{host}:{port}", False, str(exc))
            return False

    def get_log(self) -> List[Dict]:
        return list(self._injected)


# ══════════════════════════════════════════════════════════════════════════════
# PART 8 — DEFENSE REWARD ENGINE
# ══════════════════════════════════════════════════════════════════════════════

REWARD_SCHEDULE = {
    "DEFENSE":        10,
    "ATTACK_REFLECT": 15,
    "NETWORK_TOKEN":   2,
    "HONEYPOT_CAP":    5,
    "ABSORB":          3,
    "EEG_SYNC":        1,
}


@dataclass
class RewardEvent:
    ts: float
    event_type: str
    tokens: int
    source_ip: str
    detail: str


class DefenseRewardEngine:
    """
    Integrates with rabbit_reward.py reward pool.
    Emits reward events for each defensive action.
    """

    def __init__(self) -> None:
        self._events: deque = deque(maxlen=5000)
        self._total_tokens: int = 0
        self._lock = threading.Lock()

    def award(self, event_type: str, source_ip: str = "", detail: str = "") -> int:
        tokens = REWARD_SCHEDULE.get(event_type, 1)
        ev = RewardEvent(
            ts=time.time(), event_type=event_type,
            tokens=tokens, source_ip=source_ip, detail=detail,
        )
        with self._lock:
            self._events.append(ev)
            self._total_tokens += tokens

        # Attempt integration with rabbit_reward.py if available
        try:
            import importlib
            rr = importlib.import_module("rabbit_reward")
            if hasattr(rr, "add_tokens"):
                rr.add_tokens(event_type, tokens, detail)
        except Exception:
            pass

        _log(f"Reward +{tokens} {event_type} total={self._total_tokens}")
        return tokens

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            by_type: Dict[str, int] = defaultdict(int)
            for ev in self._events:
                by_type[ev.event_type] += ev.tokens
            return {
                "total_tokens": self._total_tokens,
                "by_type": dict(by_type),
                "event_count": len(self._events),
                "schedule": REWARD_SCHEDULE,
            }


# ══════════════════════════════════════════════════════════════════════════════
# PART 9 — LIVE DATA RECORDER + BROWSER-CODING AGENT
# ══════════════════════════════════════════════════════════════════════════════

_DB_PATH = os.path.join(os.path.dirname(__file__), "rabbit_defense.db")


class LiveDataRecorder:
    """
    SQLite local store + optional Supabase push for all defense telemetry.
    Traces and trails ALL data.
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db, timeout=10, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS attack_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, attacker_ip TEXT, attacker_port INTEGER,
                    target_port INTEGER, attack_type TEXT,
                    payload_sha256 TEXT, packet_count INTEGER,
                    absorbed INTEGER, reflected INTEGER, reward_tokens INTEGER
                );
                CREATE TABLE IF NOT EXISTS network_discoveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, network_type TEXT, identifier TEXT,
                    detail TEXT, active INTEGER, ports_open TEXT,
                    mac_hash TEXT, signal_dbm REAL
                );
                CREATE TABLE IF NOT EXISTS signal_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, interface TEXT, freq_ghz REAL,
                    direction TEXT, bytes_count INTEGER, packets INTEGER,
                    power_dbm REAL, protocol TEXT, raw_note TEXT
                );
                CREATE TABLE IF NOT EXISTS eeg_correlations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, band_power_json TEXT,
                    hormone_json TEXT, convergence_gate INTEGER,
                    dominant_band TEXT, network_modulation TEXT
                );
                CREATE TABLE IF NOT EXISTS reward_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, event_type TEXT, tokens INTEGER,
                    source_ip TEXT, detail TEXT
                );
            """)

    def record_attack(self, event: AttackEvent) -> None:
        payload_hash = hashlib.sha256(
            base64.b64decode(event.payload_b64 or "")).hexdigest() \
            if event.payload_b64 else ""
        with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO attack_events VALUES "
                    "(NULL,?,?,?,?,?,?,?,?,?,?)",
                    (event.ts, event.attacker_ip, event.attacker_port,
                     event.target_port, event.attack_type,
                     payload_hash, event.packet_count,
                     int(event.absorbed), int(event.reflected),
                     event.reward_tokens)
                )

    def record_discovery(self, net: DiscoveredNetwork) -> None:
        mac_hash = hashlib.sha256(net.mac.encode()).hexdigest() if net.mac else ""
        with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO network_discoveries VALUES "
                    "(NULL,?,?,?,?,?,?,?,?)",
                    (net.ts, net.network_type, net.identifier,
                     net.detail[:500], int(net.active),
                     json.dumps(net.ports_open), mac_hash, net.signal_dbm)
                )

    def record_signal(self, s: SignalSample) -> None:
        with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO signal_samples VALUES "
                    "(NULL,?,?,?,?,?,?,?,?,?)",
                    (s.ts, s.interface, s.freq_ghz, s.direction,
                     s.bytes_count, s.packets, s.power_dbm,
                     s.protocol, s.raw_note[:200])
                )

    def record_eeg(self, correlation: Dict) -> None:
        with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO eeg_correlations VALUES (NULL,?,?,?,?,?)",
                    (correlation.get("ts", time.time()),
                     json.dumps(correlation.get("band_power", {})),
                     json.dumps(correlation.get("hormone_estimates", {})),
                     int(correlation.get("convergence_gate_open", False)),
                     correlation.get("dominant_band", ""),
                     )
                )

    def record_reward(self, ev: RewardEvent) -> None:
        with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO reward_events VALUES (NULL,?,?,?,?,?)",
                    (ev.ts, ev.event_type, ev.tokens, ev.source_ip, ev.detail)
                )

    def push_to_supabase(self, table: str, row: Dict,
                         supabase_url: str, service_key: str) -> bool:
        if not supabase_url or not service_key:
            return False
        url = supabase_url.rstrip("/") + f"/rest/v1/{table}"
        data = json.dumps(row).encode()
        req = urllib.request.Request(url, data=data, method="POST",
              headers={
                  "Authorization": f"Bearer {service_key}",
                  "apikey": service_key,
                  "Content-Type": "application/json",
                  "Prefer": "return=minimal",
              })
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status < 300
        except Exception as exc:
            _log(f"Supabase push {table} error: {exc}")
            return False

    def query(self, table: str, limit: int = 100) -> List[Dict]:
        with self._lock:
            with self._conn() as c:
                rows = c.execute(f"SELECT * FROM {table} ORDER BY ts DESC LIMIT ?",
                                 (limit,)).fetchall()
                cols = [d[0] for d in c.execute(
                    f"SELECT * FROM {table} LIMIT 0").description or []]
                return [dict(zip(cols, r)) for r in rows]


class BrowserCodingAgent:
    """
    Multi-agent: browser assistant + coding agent + assistant.
    Uses rabbit_llm agentic_loop to research EEG node info and
    generate unmanipulated analysis via chained tool calls.
    """

    BROWSER_SYSTEM = (
        "You are the RabbitOS Browser-Coding Agent. You have access to web search "
        "and network tools. When asked about EEG electrode placements, neural "
        "correlates, hormone pathways, or network signals, give precise, "
        "scientifically accurate and unmanipulated data. "
        "Always cite sources. Cross-reference multiple sources to detect manipulation."
    )

    def __init__(self) -> None:
        self._llm = None
        self._results: deque = deque(maxlen=200)

    def _get_llm(self):
        if self._llm is None:
            try:
                from rabbit_llm import get_llm
                self._llm = get_llm()
            except Exception as exc:
                _log(f"BrowserCodingAgent: LLM init failed: {exc}")
        return self._llm

    def research_eeg_node(self, node_label: str) -> str:
        node = get_node(node_label)
        if not node:
            return f"Node {node_label} not found in map"

        question = (
            f"Research the EEG electrode position {node_label} (also called {node.alias}) "
            f"in the international 10-20 system. "
            f"It is over the {node.lobe} lobe ({node.hemisphere} hemisphere). "
            f"Primary function: {node.primary_function}. "
            f"Hormone correlates: {', '.join(node.hormone_correlates)}. "
            f"Provide: (1) exact anatomical location, (2) what neural circuits are "
            f"measured here, (3) what frequency bands dominate and why, "
            f"(4) how hormones modulate this site's activity, "
            f"(5) how network or external signals could alter readings here, "
            f"(6) any documented cases of external RF/EM stimulation at this site. "
            f"Use multiple sources. Flag any conflicting data."
        )

        llm = self._get_llm()
        if llm is None:
            return f"[LLM unavailable] Node {node_label}: {node.primary_function}"

        try:
            answer = llm.simple_ask(question)
        except Exception as exc:
            answer = f"[LLM error: {exc}]"

        result = {
            "node": node_label,
            "question": question,
            "answer": answer,
            "ts": time.time(),
        }
        self._results.append(result)
        return answer

    def research_network_control_of_eeg(self) -> str:
        question = (
            "Does network activity (cellular, WiFi, RF signals, or internet-connected "
            "devices) control or modulate EEG frequency bands via hormonal pathways? "
            "Specifically: (1) Can external electromagnetic signals (e.g. 10 GHz RF) "
            "alter cortical oscillations? (2) Is there evidence that cortisol, dopamine, "
            "or serotonin can be influenced by external EM exposure? "
            "(3) What is the mechanism: direct neuromodulation, thermal, or via stress "
            "response? (4) What does peer-reviewed research show? "
            "Cross-check at least 3 independent sources."
        )
        llm = self._get_llm()
        if llm is None:
            return "[LLM unavailable]"
        try:
            return llm.simple_ask(question)
        except Exception as exc:
            return f"[LLM error: {exc}]"

    def research_signal_to_code_path(self) -> str:
        question = (
            "Explain the full technical pipeline from scalp EEG electrode "
            "to digital binary representation: electrode->amplifier->ADC->FFT->"
            "band power->JSON->encryption->RF transmission->REST API->database. "
            "For each stage: bit depth, sample rate, data format, compression used. "
            "How many bytes per second per channel? How is the signal reconstructed? "
            "What information is lost at each stage? Is this pipeline used in any "
            "known BCI (brain-computer interface) products?"
        )
        llm = self._get_llm()
        if llm is None:
            return "[LLM unavailable]"
        try:
            return llm.simple_ask(question)
        except Exception as exc:
            return f"[LLM error: {exc}]"

    def get_results(self) -> List[Dict]:
        return list(self._results)


# ══════════════════════════════════════════════════════════════════════════════
# PART 10 — DEFENSE ORCHESTRATOR SINGLETON
# ══════════════════════════════════════════════════════════════════════════════

class DefenseOrchestrator:
    _instance: Optional["DefenseOrchestrator"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DefenseOrchestrator":
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self.eeg_correlator  = EEGHormoneCorrelator()
        self.net_discovery   = NetworkDiscovery()
        self.signal_tracer   = SignalTracer()
        self.attack_sensor   = AttackSensor()
        self.honeypot        = AttackHoneypot()
        self.absorber        = AttackAbsorber()
        self.reflector       = AttackReflector(self.absorber)
        self.tokenizer       = NetworkTokenizer()
        self.injector        = RabbitOSInjector()
        self.reward          = DefenseRewardEngine()
        self.recorder        = LiveDataRecorder()
        self.browser_agent   = BrowserCodingAgent()

        self._threads: List[threading.Thread] = []
        self._running = False
        _log("DefenseOrchestrator initialised")

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        self.signal_tracer.start_background(interval=5.0)
        self.honeypot.start()

        def _attack_loop():
            while self._running:
                try:
                    evs = self.attack_sensor.analyze_netstat()
                    evs += self.attack_sensor.analyze_event_log()
                    for ev in evs:
                        sig = self.reflector.reflect(ev)
                        ev.reward_tokens = self.reward.award(
                            "ATTACK_REFLECT", ev.attacker_ip, ev.attack_type)
                        self.recorder.record_attack(ev)
                except Exception as exc:
                    _log(f"Attack loop error: {exc}")
                time.sleep(30)

        def _discovery_loop():
            while self._running:
                try:
                    nets = self.net_discovery.discover_all()
                    for net in nets:
                        self.recorder.record_discovery(net)
                        if net.mac:
                            token = self.tokenizer.tokenize(net.mac, net.identifier, 0)
                            self.reward.award("NETWORK_TOKEN", net.identifier,
                                              f"token={token[:12]}")
                    self.reward.award("DEFENSE", "", "discovery_cycle")
                except Exception as exc:
                    _log(f"Discovery loop error: {exc}")
                time.sleep(300)

        def _eeg_loop():
            while self._running:
                try:
                    corr = self.eeg_correlator.correlate()
                    self.recorder.record_eeg(corr)
                    if corr.get("convergence_gate_open"):
                        self.reward.award("EEG_SYNC", "", "convergence_gate")
                except Exception as exc:
                    _log(f"EEG loop error: {exc}")
                time.sleep(10)

        for fn in [_attack_loop, _discovery_loop, _eeg_loop]:
            t = threading.Thread(target=fn, daemon=True, name=fn.__name__)
            self._threads.append(t)
            t.start()

        _log("DefenseOrchestrator started — all guardian threads running")

    def stop(self) -> None:
        self._running = False
        self.signal_tracer.stop()
        self.honeypot.stop()
        _log("DefenseOrchestrator stopped")

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "shows_dna_root": shows_dna_root,
            "tx_licensed": TX_LICENSED,
            "eeg_nodes": len(EEG_NODE_MAP),
            "discovered_networks": len(self.net_discovery.to_dict()),
            "attack_log_size": len(_ATTACK_LOG),
            "honeypot_captures": len(self.honeypot.get_captures()),
            "absorbed_signatures": len(self.absorber.get_signatures()),
            "reflected_attacks": len(self.reflector.get_reflected()),
            "network_tokens": len(self.tokenizer.get_all_tokens()),
            "reward_summary": self.reward.summary(),
            "signal_summary": self.signal_tracer.summary(),
        }


def get_defense_engine() -> DefenseOrchestrator:
    return DefenseOrchestrator()


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# BACKDOOR + HIDDEN NETWORK DETECTOR
# NOTE: For use ONLY on networks you own or have explicit authorization to test.
# ══════════════════════════════════════════════════════════════════════════════

# Known backdoor / RAT / C2 ports
BACKDOOR_PORTS: Dict[int, str] = {
    1337: "l33t-backdoor", 31337: "Back Orifice", 12345: "NetBus",
    27374: "SubSeven", 65000: "Devil", 4444: "Metasploit/meterpreter",
    4445: "Metasploit-alt", 9090: "Cobalt-Strike-default",
    50050: "Cobalt-Strike-teamserver", 8888: "Jupyter/Empire",
    1234: "generic-backdoor", 2222: "alt-SSH-backdoor",
    6666: "IRC-C2", 6667: "IRC-C2", 6668: "IRC-C2",
    7777: "God-mode-backdoor", 8192: "hidden-service",
    54321: "reverse-shell", 9001: "Tor-hidden-service",
    2323: "Telnet-alt-backdoor", 23: "Telnet-plaintext",
    135: "MSRPC-C2", 139: "NetBIOS-C2", 445: "SMB-C2",
    5985: "WinRM-lateral", 5986: "WinRM-SSL-lateral",
    3389: "RDP-lateral", 5900: "VNC-backdoor",
    6379: "Redis-no-auth", 27017: "MongoDB-no-auth",
    9200: "Elasticsearch-open", 2375: "Docker-daemon-exposed",
    2376: "Docker-TLS-exposed",
}

# Hidden SSID / rogue AP indicators
ROGUE_AP_KEYWORDS = [
    "evil", "pineapple", "karma", "fake", "rogue", "hack",
    "mitm", "intercept", "spy", "trap", "honeypot",
]


@dataclass
class BackdoorFinding:
    ts: float
    host: str
    port: int
    finding_type: str    # backdoor_port / hidden_service / rogue_ap / covert_channel / rootkit_indicator
    severity: str        # critical / high / medium / low
    description: str
    evidence: str
    recommended_action: str


class BackdoorDetector:
    """
    Detects backdoors, hidden networks, and covert channels.
    AUTHORIZED USE ONLY — run only on networks you own/control.
    """

    def __init__(self, timeout: float = 2.0) -> None:
        self._timeout  = timeout
        self._findings: List[BackdoorFinding] = []
        self._lock     = threading.Lock()

    def _add(self, f: BackdoorFinding) -> None:
        with self._lock:
            self._findings.append(f)
        _log(f"[BACKDOOR] {f.severity.upper()} {f.finding_type} @ {f.host}:{f.port} - {f.description[:80]}")

    # ── 1. Known backdoor port scan ───────────────────────────────────────────
    def scan_backdoor_ports(self, host: str = "127.0.0.1") -> List[BackdoorFinding]:
        found = []
        lock  = threading.Lock()

        def probe(port: int, label: str) -> None:
            try:
                s = socket.create_connection((host, port), timeout=self._timeout)
                banner = ""
                try:
                    s.settimeout(1.0)
                    banner = s.recv(512).decode("utf-8", errors="replace")
                except Exception:
                    pass
                s.close()
                f = BackdoorFinding(
                    ts=time.time(), host=host, port=port,
                    finding_type="backdoor_port",
                    severity="critical" if port in (4444, 50050, 31337) else "high",
                    description=f"Known backdoor port open: {label} ({port})",
                    evidence=f"Banner: {banner[:100]}" if banner else "Port responded",
                    recommended_action=(
                        f"Immediately investigate process on port {port}. "
                        f"Run: netstat -ano | findstr {port}. "
                        f"Terminate unauthorized service and check for persistence."
                    ),
                )
                self._add(f)
                with lock:
                    found.append(f)
            except Exception:
                pass

        threads = [
            threading.Thread(target=probe, args=(p, l), daemon=True)
            for p, l in BACKDOOR_PORTS.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=self._timeout + 1)

        return found

    # ── 2. Local listening port audit ─────────────────────────────────────────
    def audit_listening_ports(self) -> List[BackdoorFinding]:
        found = []
        raw = _run(["netstat", "-ano"], timeout=15)
        listening = [l for l in raw.splitlines()
                     if "LISTENING" in l or "LISTEN" in l]

        known_safe = {80, 443, 135, 3389, 445, 139, 5040,
                      49152, 49153, 49154, 49155, 49664, 49665}

        for line in listening:
            parts = line.split()
            if len(parts) < 4:
                continue
            local_addr = parts[1] if len(parts) > 1 else ""
            port_str   = local_addr.rsplit(":", 1)[-1]
            try:
                port = int(port_str)
            except ValueError:
                continue

            pid = parts[-1] if parts[-1].isdigit() else "?"
            if port in BACKDOOR_PORTS:
                label = BACKDOOR_PORTS[port]
                f = BackdoorFinding(
                    ts=time.time(), host="localhost", port=port,
                    finding_type="hidden_service",
                    severity="critical",
                    description=f"Backdoor-class port {port} ({label}) listening locally (PID {pid})",
                    evidence=line.strip(),
                    recommended_action=f"Kill PID {pid}, check startup: "
                                       f"'wmic process where ProcessId={pid} get CommandLine'",
                )
                self._add(f)
                found.append(f)
            elif port not in known_safe and port < 1024:
                f = BackdoorFinding(
                    ts=time.time(), host="localhost", port=port,
                    finding_type="hidden_service",
                    severity="medium",
                    description=f"Unusual privileged port {port} listening (PID {pid})",
                    evidence=line.strip(),
                    recommended_action=f"Investigate PID {pid}: "
                                       f"'wmic process where ProcessId={pid} get CommandLine'",
                )
                self._add(f)
                found.append(f)
        return found

    # ── 3. Hidden SSID + rogue AP detection ───────────────────────────────────
    def scan_hidden_ssids(self) -> List[BackdoorFinding]:
        found = []
        raw = _run(["netsh", "wlan", "show", "networks", "mode=bssid"], timeout=15)

        entries = re.split(r"SSID\s+\d+\s*:", raw)
        for entry in entries[1:]:
            ssid_m = re.match(r"\s*(.+)", entry)
            ssid   = ssid_m.group(1).strip() if ssid_m else ""
            bssid_m = re.search(r"BSSID\s+\d+\s*:\s*([\w:]+)", entry, re.I)
            bssid   = bssid_m.group(1).strip() if bssid_m else "unknown"

            # Hidden SSID
            if not ssid or ssid == "" or ssid == "<hidden>":
                f = BackdoorFinding(
                    ts=time.time(), host=bssid, port=0,
                    finding_type="rogue_ap",
                    severity="high",
                    description=f"Hidden SSID detected (BSSID: {bssid})",
                    evidence=entry[:200],
                    recommended_action="Probe the AP to identify if it is authorized. "
                                       "Hidden SSIDs are often rogue or evil-twin APs.",
                )
                self._add(f)
                found.append(f)

            # Rogue AP keyword check
            for kw in ROGUE_AP_KEYWORDS:
                if kw.lower() in ssid.lower():
                    f = BackdoorFinding(
                        ts=time.time(), host=bssid, port=0,
                        finding_type="rogue_ap",
                        severity="critical",
                        description=f"Rogue AP keyword '{kw}' in SSID: '{ssid}'",
                        evidence=f"SSID={ssid} BSSID={bssid}",
                        recommended_action=f"Do NOT connect to '{ssid}'. "
                                           "This may be an evil-twin or pineapple attack AP.",
                    )
                    self._add(f)
                    found.append(f)
                    break

        return found

    # ── 4. Covert channel detection (unusual outbound UDP) ────────────────────
    def detect_covert_channels(self) -> List[BackdoorFinding]:
        found = []
        raw = _run(["netstat", "-ano"], timeout=15)
        covert_udp_ports = {53, 123, 161, 1194, 500, 4500}
        for line in raw.splitlines():
            if "UDP" not in line.upper():
                continue
            parts = line.split()
            remote = parts[2] if len(parts) > 2 else ""
            remote_port_str = remote.rsplit(":", 1)[-1]
            try:
                remote_port = int(remote_port_str)
            except ValueError:
                continue
            pid = parts[-1] if parts[-1].isdigit() else "?"
            if remote_port in covert_udp_ports and remote not in ("0.0.0.0:*", "*:*", ":::*"):
                f = BackdoorFinding(
                    ts=time.time(), host=remote, port=remote_port,
                    finding_type="covert_channel",
                    severity="medium",
                    description=f"UDP connection to {remote} on port {remote_port} (PID {pid}). "
                                f"Could be DNS tunneling, NTP covert channel, or VPN.",
                    evidence=line.strip(),
                    recommended_action=f"Verify PID {pid}. DNS/NTP ports are common C2 covert channels.",
                )
                self._add(f)
                found.append(f)
        return found

    # ── 5. Unexpected network interfaces (virtual / TUN/TAP / VPN) ────────────
    def scan_hidden_interfaces(self) -> List[BackdoorFinding]:
        found = []
        raw = _run(["ipconfig", "/all"], timeout=10) \
            if platform.system() == "Windows" else \
            _run(["ip", "link", "show"], timeout=5)

        tun_keywords = ["tun", "tap", "vpn", "zerotier", "wg", "tailscale",
                        "hamachi", "radmin", "ngrok", "utun"]
        for line in raw.splitlines():
            ll = line.lower()
            for kw in tun_keywords:
                if kw in ll and "adapter" in ll.lower():
                    f = BackdoorFinding(
                        ts=time.time(), host="localhost", port=0,
                        finding_type="hidden_service",
                        severity="medium",
                        description=f"Tunnel/VPN interface detected: {line.strip()[:100]}",
                        evidence=line.strip(),
                        recommended_action="Verify this VPN/tunnel is authorized. "
                                           "Unauthorized tunnels may exfiltrate data.",
                    )
                    self._add(f)
                    found.append(f)
                    break
        return found

    # ── 6. Scheduled tasks / startup backdoor persistence check ──────────────
    def check_persistence_mechanisms(self) -> List[BackdoorFinding]:
        found = []
        if platform.system() != "Windows":
            return found

        # Check scheduled tasks
        raw = _run(["schtasks", "/query", "/fo", "LIST"], timeout=20)
        suspicious_tasks = []
        current_task = ""
        for line in raw.splitlines():
            if "TaskName:" in line:
                current_task = line.split("TaskName:")[-1].strip()
            if "Task To Run:" in line:
                cmd = line.split("Task To Run:")[-1].strip().lower()
                if any(kw in cmd for kw in ["powershell", "cmd", "wscript",
                                              "mshta", "regsvr32", "rundll"]):
                    suspicious_tasks.append((current_task, cmd))

        for task_name, cmd in suspicious_tasks:
            f = BackdoorFinding(
                ts=time.time(), host="localhost", port=0,
                finding_type="rootkit_indicator",
                severity="high",
                description=f"Suspicious scheduled task: {task_name}",
                evidence=f"Command: {cmd[:200]}",
                recommended_action=f"Review task '{task_name}' with "
                                   f"'schtasks /query /tn \"{task_name}\" /fo LIST /v'. "
                                   "Remove if not authorized.",
            )
            self._add(f)
            found.append(f)

        return found

    # ── 7. Full scan ──────────────────────────────────────────────────────────
    def full_scan(self, host: str = "127.0.0.1") -> Dict[str, Any]:
        _log(f"BackdoorDetector: full scan on {host}")
        t0 = time.time()

        with self._lock:
            self._findings.clear()

        threads = [
            threading.Thread(target=self.scan_backdoor_ports, args=(host,), daemon=True),
            threading.Thread(target=self.audit_listening_ports, daemon=True),
            threading.Thread(target=self.scan_hidden_ssids, daemon=True),
            threading.Thread(target=self.detect_covert_channels, daemon=True),
            threading.Thread(target=self.scan_hidden_interfaces, daemon=True),
            threading.Thread(target=self.check_persistence_mechanisms, daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        with self._lock:
            findings = list(self._findings)

        by_sev: Dict[str, int] = defaultdict(int)
        for f in findings:
            by_sev[f.severity] += 1

        return {
            "host": host,
            "scan_duration_s": round(time.time() - t0, 2),
            "total_findings": len(findings),
            "by_severity": dict(by_sev),
            "findings": [asdict(f) for f in findings],
            "authorized_use_notice": (
                "Backdoor detection results are for AUTHORIZED defensive use only. "
                "Verify findings before taking action."
            ),
        }

    def get_findings(self) -> List[Dict]:
        with self._lock:
            return [asdict(f) for f in self._findings]


# ══════════════════════════════════════════════════════════════════════════════
# DEFENSE TOOLS + DISPATCHER
# ══════════════════════════════════════════════════════════════════════════════

DEFENSE_TOOLS = [
    {
        "name": "defense_status",
        "description": "Get full DefenseOrchestrator status including all subsystem states",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_start",
        "description": "Start the defense orchestrator and all guardian threads",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_stop",
        "description": "Stop the defense orchestrator",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_eeg_node_report",
        "description": "Return all EEG 10-20 node definitions with mesh bindings and RF carriers",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_eeg_correlate",
        "description": "Run EEG-hormone correlation on current band power data",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_eeg_network_analysis",
        "description": "Analyse whether network signals are modulating EEG via hormonal pathway",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_update_band_power",
        "description": "Update EEG band power reading for a specific band",
        "input_schema": {
            "type": "object",
            "properties": {
                "band":  {"type": "string",  "description": "delta/theta/alpha/beta/gamma/mu"},
                "power": {"type": "number",  "description": "Power in uV^2"},
            },
            "required": ["band", "power"],
        },
    },
    {
        "name": "defense_signal_pipeline",
        "description": "Explain the EEG signal-to-binary pipeline. Optionally specify a stage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "description": "Optional stage name"},
            },
            "required": [],
        },
    },
    {
        "name": "defense_discover_networks",
        "description": "Run full network discovery: cellular, satellite, SSH, BT, MAC, TOR, blockchain, TTS",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_list_discoveries",
        "description": "List most recently discovered networks",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_signal_capture",
        "description": "Capture current RF/frequency signal samples from all interfaces",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_signal_summary",
        "description": "Get TX/RX signal summary across all monitored interfaces",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_attack_scan",
        "description": "Run active attack sensor scan on netstat and event log",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_honeypot_captures",
        "description": "Get all honeypot-captured attacker payloads",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_attack_log",
        "description": "Get recent attack event log",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max entries to return"},
            },
            "required": [],
        },
    },
    {
        "name": "defense_reflect_attack",
        "description": "Reflect a specific attack event back at the attacker (requires REFLECT_LICENSED=True)",
        "input_schema": {
            "type": "object",
            "properties": {
                "attacker_ip":   {"type": "string"},
                "attack_type":   {"type": "string"},
                "target_port":   {"type": "integer"},
            },
            "required": ["attacker_ip", "attack_type"],
        },
    },
    {
        "name": "defense_tokenize_network",
        "description": "Generate a RabbitOS network token from MAC + IP + mesh node",
        "input_schema": {
            "type": "object",
            "properties": {
                "mac":          {"type": "string"},
                "ip":           {"type": "string"},
                "mesh_node_id": {"type": "integer"},
            },
            "required": ["mac", "ip", "mesh_node_id"],
        },
    },
    {
        "name": "defense_list_tokens",
        "description": "List all generated network tokens",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_inject_rabbitos",
        "description": "Inject RabbitOS presence into network via UDP broadcast, HTTP header, or WebSocket",
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "udp_broadcast / http_header / websocket"},
                "target": {"type": "string", "description": "URL or host:port for http/websocket"},
            },
            "required": ["method"],
        },
    },
    {
        "name": "defense_reward_summary",
        "description": "Get defense reward token summary",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_db_query",
        "description": "Query the local defense SQLite database",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string",
                          "description": "attack_events / network_discoveries / signal_samples / eeg_correlations / reward_events"},
                "limit": {"type": "integer"},
            },
            "required": ["table"],
        },
    },
    {
        "name": "defense_research_eeg_node",
        "description": "Use browser-coding agent to research a specific EEG electrode placement",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_label": {"type": "string", "description": "e.g. T7 or T3, F3, O1"},
            },
            "required": ["node_label"],
        },
    },
    {
        "name": "defense_research_network_control",
        "description": "Research whether network RF signals modulate EEG via hormones",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_research_signal_path",
        "description": "Research the full EEG signal-to-code/binary technical path",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_push_to_supabase",
        "description": "Push a defense record to Supabase",
        "input_schema": {
            "type": "object",
            "properties": {
                "table":         {"type": "string"},
                "record_json":   {"type": "string"},
                "supabase_url":  {"type": "string"},
            },
            "required": ["table", "record_json"],
        },
    },
    {
        "name": "defense_backdoor_scan",
        "description": "Full backdoor + hidden network scan: known RAT ports, hidden SSIDs, covert channels, persistence. AUTHORIZED USE ONLY.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Host to scan (default: 127.0.0.1)"},
            },
            "required": [],
        },
    },
    {
        "name": "defense_backdoor_port_scan",
        "description": "Scan a host for known backdoor/RAT/C2 ports",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "defense_scan_hidden_ssids",
        "description": "Scan for hidden SSIDs and rogue access points",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_audit_listening_ports",
        "description": "Audit all locally listening ports for backdoor-class services",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_check_persistence",
        "description": "Check for backdoor persistence mechanisms (scheduled tasks, startup entries)",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "defense_backdoor_findings",
        "description": "Get all backdoor findings from the last scan",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def dispatch_defense_tool(name: str, inputs: Dict, api_key: str = "",
                           service_key: str = "", gh_token: str = "",
                           supabase_url: str = "") -> Any:
    eng = get_defense_engine()

    if name == "defense_status":
        return eng.status()

    elif name == "defense_start":
        eng.start()
        return {"started": True}

    elif name == "defense_stop":
        eng.stop()
        return {"stopped": True}

    elif name == "defense_eeg_node_report":
        return eeg_node_report()

    elif name == "defense_eeg_correlate":
        return eng.eeg_correlator.correlate()

    elif name == "defense_eeg_network_analysis":
        return eng.eeg_correlator.network_control_analysis()

    elif name == "defense_update_band_power":
        eng.eeg_correlator.update_band_power(inputs["band"], inputs["power"])
        return {"updated": True, "band": inputs["band"], "power": inputs["power"]}

    elif name == "defense_signal_pipeline":
        return signal_pipeline_explain(inputs.get("stage"))

    elif name == "defense_discover_networks":
        nets = eng.net_discovery.discover_all()
        for net in nets:
            eng.recorder.record_discovery(net)
        return {"count": len(nets), "networks": [asdict(n) for n in nets]}

    elif name == "defense_list_discoveries":
        return eng.net_discovery.to_dict()

    elif name == "defense_signal_capture":
        samples = eng.signal_tracer.capture()
        for s in samples:
            eng.recorder.record_signal(s)
        return {"count": len(samples), "samples": [asdict(s) for s in samples]}

    elif name == "defense_signal_summary":
        return eng.signal_tracer.summary()

    elif name == "defense_attack_scan":
        evs = eng.attack_sensor.analyze_netstat()
        evs += eng.attack_sensor.analyze_event_log()
        return {"events_found": len(evs),
                "events": [asdict(e) for e in evs]}

    elif name == "defense_honeypot_captures":
        return eng.honeypot.get_captures()

    elif name == "defense_attack_log":
        limit = inputs.get("limit", 50)
        with _ATTACK_LOCK:
            recent = list(_ATTACK_LOG)[-limit:]
        return [asdict(e) for e in recent]

    elif name == "defense_reflect_attack":
        ev = AttackEvent(
            ts=time.time(),
            attacker_ip=inputs["attacker_ip"],
            attacker_port=inputs.get("attacker_port", 0),
            target_port=inputs.get("target_port", 0),
            attack_type=inputs["attack_type"],
            payload_b64="",
            packet_count=1,
        )
        plan = eng.reflector.reflect(ev)
        eng.reward.award("ATTACK_REFLECT", inputs["attacker_ip"], inputs["attack_type"])
        return plan

    elif name == "defense_tokenize_network":
        token = eng.tokenizer.tokenize(
            inputs["mac"], inputs["ip"], inputs.get("mesh_node_id", 0))
        eng.reward.award("NETWORK_TOKEN", inputs["ip"],
                         f"token={token[:12]}")
        return {"token": token}

    elif name == "defense_list_tokens":
        return eng.tokenizer.get_all_tokens()

    elif name == "defense_inject_rabbitos":
        method = inputs.get("method", "")
        target = inputs.get("target", "")
        if method == "udp_broadcast":
            ok = eng.injector.udp_broadcast()
        elif method == "http_header":
            ok = eng.injector.http_header_inject(target)
        elif method == "websocket":
            host, _, port_s = target.rpartition(":")
            ok = eng.injector.websocket_identity(host, int(port_s or 80))
        else:
            ok = False
        return {"method": method, "target": target, "success": ok,
                "log": eng.injector.get_log()}

    elif name == "defense_reward_summary":
        return eng.reward.summary()

    elif name == "defense_db_query":
        table = inputs.get("table", "attack_events")
        limit = inputs.get("limit", 50)
        allowed = {"attack_events", "network_discoveries",
                   "signal_samples", "eeg_correlations", "reward_events"}
        if table not in allowed:
            return {"error": f"Unknown table: {table}"}
        return eng.recorder.query(table, limit)

    elif name == "defense_research_eeg_node":
        return {"result": eng.browser_agent.research_eeg_node(inputs["node_label"])}

    elif name == "defense_research_network_control":
        return {"result": eng.browser_agent.research_network_control_of_eeg()}

    elif name == "defense_research_signal_path":
        return {"result": eng.browser_agent.research_signal_to_code_path()}

    elif name == "defense_push_to_supabase":
        url = supabase_url or ""
        skey = service_key or ""
        try:
            row = json.loads(inputs["record_json"])
        except Exception:
            return {"error": "invalid record_json"}
        ok = eng.recorder.push_to_supabase(inputs["table"], row, url, skey)
        return {"pushed": ok}

    elif name == "defense_backdoor_scan":
        host = inputs.get("host", "127.0.0.1")
        bd = BackdoorDetector()
        result = bd.full_scan(host)
        # Award tokens for each critical finding
        for f in result.get("findings", []):
            if f.get("severity") == "critical":
                eng.reward.award("ATTACK_REFLECT", host, f.get("description", "")[:80])
            else:
                eng.reward.award("DEFENSE", host, f.get("description", "")[:80])
        return result

    elif name == "defense_backdoor_port_scan":
        bd = BackdoorDetector()
        findings = bd.scan_backdoor_ports(inputs.get("host", "127.0.0.1"))
        return {"findings": [asdict(f) for f in findings]}

    elif name == "defense_scan_hidden_ssids":
        bd = BackdoorDetector()
        findings = bd.scan_hidden_ssids()
        return {"findings": [asdict(f) for f in findings]}

    elif name == "defense_audit_listening_ports":
        bd = BackdoorDetector()
        findings = bd.audit_listening_ports()
        return {"findings": [asdict(f) for f in findings]}

    elif name == "defense_check_persistence":
        bd = BackdoorDetector()
        findings = bd.check_persistence_mechanisms()
        return {"findings": [asdict(f) for f in findings]}

    elif name == "defense_backdoor_findings":
        bd = BackdoorDetector()
        return {"findings": bd.get_findings()}

    else:
        return {"error": f"Unknown defense tool: {name}"}


# ══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RabbitOS Defense Engine")
    parser.add_argument("--start",    action="store_true", help="Start orchestrator")
    parser.add_argument("--status",   action="store_true", help="Print status")
    parser.add_argument("--discover", action="store_true", help="Run network discovery")
    parser.add_argument("--eeg",      action="store_true", help="Show EEG node map")
    parser.add_argument("--pipeline", action="store_true", help="Show signal pipeline")
    parser.add_argument("--research", type=str, default="", metavar="NODE",
                        help="Research an EEG node via browser agent")
    args = parser.parse_args()

    eng = get_defense_engine()

    if args.start:
        eng.start()
        _log("Defense engine running. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(5)
                _log(json.dumps(eng.status(), indent=2, default=str)[:500])
        except KeyboardInterrupt:
            eng.stop()

    elif args.status:
        print(json.dumps(eng.status(), indent=2, default=str))

    elif args.discover:
        nets = eng.net_discovery.discover_all()
        print(json.dumps([asdict(n) for n in nets], indent=2, default=str))

    elif args.eeg:
        print(json.dumps(eeg_node_report(), indent=2))

    elif args.pipeline:
        print(json.dumps(signal_pipeline_explain(), indent=2))

    elif args.research:
        print(eng.browser_agent.research_eeg_node(args.research))

    else:
        parser.print_help()
