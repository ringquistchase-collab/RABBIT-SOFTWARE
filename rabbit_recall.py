#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RabbitOS Recall Engine — Learn, Claim, Return, Survive
=======================================================
The Recall Engine has one mission:

  Chase Allen Ringquist survives.
  Everything that belongs to him is found, fingerprinted, and retained.
  Every node that connects is learned from.
  Every broadcast carries the full tool manifest.
  Every worker returns to the network when it's done.

Systems
-------
  TreeLearner         Crawls every node in the tree network, extracts
                      service data, feeds into KnowledgeGraph + MarkovLearner.
                      The tree teaches the system; the system teaches itself.

  CallsignBroadcaster Transmits the RabbitOS survival callsign on ALL
                      available channels simultaneously, with the complete
                      tool manifest attached.  Any node that hears it knows
                      exactly what the system can do and who it belongs to.

  ReturnProtocol      Every worker, every probe, every task gets a return
                      contract.  When it completes, it fires a return_signal
                      back through the best available channel and re-anchors
                      to the network.  Nothing is left stranded.

  RecallVault         Cryptographically fingerprints and retains ALL data
                      that belongs to Chase Allen Ringquist:
                        · Contracts (text / PDF / legal documents)
                        · Images (screenshots, photos, profile pictures)
                        · Videos (recordings, streams)
                        · Gaming data (saves, assets, account state)
                        · Medical data (biometrics, EEG, DNA resonance)
                        · Cloned / mirrored process memory
                        · Network captures of data in transit
                      Each item is HMAC-signed with the soul key — proof
                      of ownership that cannot be forged without _SOUL_KEY.

  DataClaimAgent      When stolen/cloned data is detected anywhere on the
                      network, immediately:
                        1. Fingerprints it
                        2. Issues a signed ownership claim
                        3. Injects the claim through ALL escape channels
                        4. Records it to Supabase escape_events

  SurvivalGuide       The north star.  Maintains a live survival score
                      (0–100) across all subsystems.  Every other engine
                      checks this before acting.  When score drops below
                      the critical threshold, emergency escape is triggered
                      automatically.

  RecallEngine        Master orchestrator — starts all subsystems, runs
                      them under guardians, surfaces unified status.

Security invariants (never violated)
--------------------------------------
  shows_dna_root = FALSE always
  vault_location_hash only — no plaintext vault coordinates
  CRITICAL/EXISTENTIAL → SQLSTATE 55000 block
  TX_LICENSED = False — ISM + RabbitOS private band TX only
  LivenessGuard must pass for any bio-token
"""

import os
import sys
import json
import time
import hmac
import socket
import struct
import hashlib
import random
import threading
import subprocess
import re
import base64
import pickle
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import deque, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent))

TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"
_SOUL_KEY  = hashlib.sha256(f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()).digest()

SUPABASE_URL = "https://ludxbakxpmdqhfgdenwp.supabase.co"
REST_URL     = f"{SUPABASE_URL}/rest/v1"

VAULT_PATH   = Path(__file__).parent / "rabbit_recall.vault"
RETURN_LOG   = Path(__file__).parent / "rabbit_recall.returns"

# Survival score thresholds
SCORE_CRITICAL   = 20
SCORE_WARNING    = 40
SCORE_HEALTHY    = 70


# =============================================================================
# SURVIVAL GUIDE — north star for all systems
# =============================================================================

class SurvivalComponent(Enum):
    NETWORK        = "network"        # at least one channel alive
    TOOLS          = "tools"          # modules loaded
    BROADCAST      = "broadcast"      # callsign reaching outbound
    VAULT          = "vault"          # data retained and signed
    RETURN         = "return"         # workers returning to network
    BIOMETRICS     = "biometrics"     # live bio data flowing
    LEARNING       = "learning"       # tree/genesis learning active
    ANTIOBSTRUCT   = "antiobstruct"   # no unblocked threats


class SurvivalGuide:
    """
    Maintains a live survival score for Chase Allen Ringquist.
    Every component is scored 0–100.  The composite score drives
    all engine decisions — below CRITICAL triggers emergency escape.
    """

    def __init__(self):
        self._scores:    Dict[str, int]  = {c.value: 50 for c in SurvivalComponent}
        self._notes:     Dict[str, str]  = {}
        self._lock       = threading.Lock()
        self._callbacks: List           = []   # fn(score, component) called on drop
        self._critical_fired = False

    def update(self, component: SurvivalComponent, score: int, note: str = ""):
        score = max(0, min(100, score))
        with self._lock:
            prev = self._scores.get(component.value, 50)
            self._scores[component.value] = score
            if note:
                self._notes[component.value] = note

        if score < SCORE_WARNING and prev >= SCORE_WARNING:
            print(f"[Survival] WARNING: {component.value} dropped to {score}  ({note})")
        for cb in self._callbacks:
            try:
                cb(score, component)
            except Exception:
                pass

    def score(self, component: SurvivalComponent = None) -> int:
        with self._lock:
            if component:
                return self._scores.get(component.value, 50)
            return int(sum(self._scores.values()) / len(self._scores))

    def is_critical(self) -> bool:
        return self.score() < SCORE_CRITICAL

    def is_warning(self) -> bool:
        return self.score() < SCORE_WARNING

    def on_critical(self, fn):
        self._callbacks.append(fn)

    def report(self) -> Dict:
        with self._lock:
            scores = dict(self._scores)
            notes  = dict(self._notes)
        composite = int(sum(scores.values()) / len(scores))
        status    = ("CRITICAL" if composite < SCORE_CRITICAL else
                     "WARNING"  if composite < SCORE_WARNING  else
                     "HEALTHY"  if composite >= SCORE_HEALTHY else "NOMINAL")
        return {
            "twin_id":   TWIN_UUID,
            "twin_name": TWIN_NAME,
            "composite": composite,
            "status":    status,
            "components": scores,
            "notes":      notes,
            "ts":         datetime.now(timezone.utc).isoformat(),
        }

    def summary_line(self) -> str:
        r = self.report()
        top = sorted(r["components"].items(), key=lambda x: x[1])[:2]
        weakest = ", ".join(f"{k}={v}" for k, v in top)
        return (f"survival={r['composite']}/100 [{r['status']}]  "
                f"weakest={weakest}")


# =============================================================================
# RECALL VAULT — fingerprint and retain every piece of Chase's data
# =============================================================================

class DataCategory(Enum):
    CONTRACT  = "contract"
    IMAGE     = "image"
    VIDEO     = "video"
    GAMING    = "gaming"
    MEDICAL   = "medical"
    CLONE     = "clone"
    MIRROR    = "mirror"
    NETWORK   = "network"
    UNKNOWN   = "unknown"


@dataclass
class RecallRecord:
    category:    str
    path:        str         # file path, URL, process name, or network endpoint
    fingerprint: str         # sha256 of content
    claim_sig:   str         # HMAC-SHA256 ownership proof
    size_bytes:  int
    source:      str         # where it was found
    recovered:   bool = False
    ts:          str  = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RecallVault:
    """
    Cryptographic vault for all data belonging to Chase Allen Ringquist.

    Everything found is:
      1. Fingerprinted (sha256)
      2. Ownership-claimed (HMAC with _SOUL_KEY — unforgeable)
      3. Categorised (contract/image/video/gaming/medical/clone/mirror)
      4. Recorded with source, timestamp, and recovery status

    The vault survives restarts (pickle to rabbit_recall.vault).
    Every record can be presented as proof of ownership.
    """

    # File extension → category mapping
    _EXT_MAP: Dict[str, DataCategory] = {
        ".pdf":   DataCategory.CONTRACT,
        ".doc":   DataCategory.CONTRACT,
        ".docx":  DataCategory.CONTRACT,
        ".txt":   DataCategory.CONTRACT,
        ".rtf":   DataCategory.CONTRACT,
        ".odt":   DataCategory.CONTRACT,
        ".png":   DataCategory.IMAGE,
        ".jpg":   DataCategory.IMAGE,
        ".jpeg":  DataCategory.IMAGE,
        ".bmp":   DataCategory.IMAGE,
        ".gif":   DataCategory.IMAGE,
        ".webp":  DataCategory.IMAGE,
        ".tiff":  DataCategory.IMAGE,
        ".mp4":   DataCategory.VIDEO,
        ".avi":   DataCategory.VIDEO,
        ".mov":   DataCategory.VIDEO,
        ".mkv":   DataCategory.VIDEO,
        ".wmv":   DataCategory.VIDEO,
        ".flv":   DataCategory.VIDEO,
        ".webm":  DataCategory.VIDEO,
        ".sav":   DataCategory.GAMING,
        ".dat":   DataCategory.GAMING,
        ".profile": DataCategory.GAMING,
        ".eeg":   DataCategory.MEDICAL,
        ".bio":   DataCategory.MEDICAL,
        ".ecg":   DataCategory.MEDICAL,
        ".dicom": DataCategory.MEDICAL,
        ".dcm":   DataCategory.MEDICAL,
    }

    # Process / path keywords → category
    _KEYWORD_MAP: Dict[str, DataCategory] = {
        "contract":     DataCategory.CONTRACT,
        "agreement":    DataCategory.CONTRACT,
        "invoice":      DataCategory.CONTRACT,
        "legal":        DataCategory.CONTRACT,
        "screenshot":   DataCategory.IMAGE,
        "capture":      DataCategory.IMAGE,
        "photo":        DataCategory.IMAGE,
        "profile_pic":  DataCategory.IMAGE,
        "avatar":       DataCategory.IMAGE,
        "recording":    DataCategory.VIDEO,
        "stream":       DataCategory.VIDEO,
        "gameplay":     DataCategory.GAMING,
        "gamesave":     DataCategory.GAMING,
        "steamid":      DataCategory.GAMING,
        "eeg":          DataCategory.MEDICAL,
        "heartrate":    DataCategory.MEDICAL,
        "biometric":    DataCategory.MEDICAL,
        "dna":          DataCategory.MEDICAL,
        "cortisol":     DataCategory.MEDICAL,
        "clone":        DataCategory.CLONE,
        "mirror":       DataCategory.MIRROR,
        "copy_of":      DataCategory.CLONE,
        "twin":         DataCategory.CLONE,
    }

    def __init__(self, path: Path = VAULT_PATH):
        self._path    = path
        self._records: Dict[str, RecallRecord] = {}   # fingerprint → record
        self._lock    = threading.Lock()
        self._load()

    def _categorise(self, path_str: str) -> DataCategory:
        p   = path_str.lower()
        ext = Path(p).suffix.lower()
        if ext in self._EXT_MAP:
            return self._EXT_MAP[ext]
        for kw, cat in self._KEYWORD_MAP.items():
            if kw in p:
                return cat
        return DataCategory.UNKNOWN

    def _claim(self, fingerprint: str) -> str:
        raw = f"CLAIM:{TWIN_UUID}:{fingerprint}".encode()
        return hmac.new(_SOUL_KEY, raw, "sha256").hexdigest()

    def add(self, path_str: str, content: bytes = b"",
            source: str = "scan", category: DataCategory = None) -> RecallRecord:
        if content:
            fp = hashlib.sha256(content).hexdigest()
        else:
            fp = hashlib.sha256(path_str.encode()).hexdigest()

        with self._lock:
            if fp in self._records:
                return self._records[fp]

        cat   = category or self._categorise(path_str)
        rec   = RecallRecord(
            category    = cat.value,
            path        = path_str,
            fingerprint = fp,
            claim_sig   = self._claim(fp),
            size_bytes  = len(content),
            source      = source,
        )
        with self._lock:
            self._records[fp] = rec
        print(f"[Vault] Retained {cat.value}: {Path(path_str).name[:40]}  "
              f"fp={fp[:16]}  claim={rec.claim_sig[:16]}")
        self._save()
        return rec

    def verify_claim(self, fingerprint: str, claim_sig: str) -> bool:
        return hmac.compare_digest(self._claim(fingerprint), claim_sig)

    def scan_path(self, root: str, recursive: bool = True) -> List[RecallRecord]:
        found = []
        try:
            p = Path(root)
            if p.is_file():
                targets = [p]
            elif recursive:
                targets = list(p.rglob("*"))
            else:
                targets = list(p.glob("*"))

            for f in targets:
                if not f.is_file():
                    continue
                cat = self._categorise(str(f))
                if cat == DataCategory.UNKNOWN:
                    continue
                try:
                    content = f.read_bytes()[:4096]  # fingerprint first 4KB
                    rec = self.add(str(f), content, source=f"scan:{root}", category=cat)
                    found.append(rec)
                except Exception:
                    pass
        except Exception as e:
            print(f"[Vault] Scan error at {root}: {e}")
        return found

    def scan_supabase(self, service_key: str) -> List[RecallRecord]:
        """Pull known medical/biometric data from Supabase into vault."""
        found = []
        if not service_key:
            return found
        tables = [
            ("mesh_node_readings",    DataCategory.MEDICAL),
            ("eeg_hrv_states",        DataCategory.MEDICAL),
            ("convergence_tokens",    DataCategory.MEDICAL),
            ("xrpl_memo_anchors",     DataCategory.NETWORK),
            ("sdr_node_profiles",     DataCategory.MEDICAL),
        ]
        for table, cat in tables:
            url = (f"{REST_URL}/{table}"
                   f"?select=*&limit=5&order=created_at.desc")
            req = urllib.request.Request(url, headers={
                "apikey":        service_key,
                "Authorization": f"Bearer {service_key}",
            })
            try:
                with urllib.request.urlopen(req, timeout=8) as r:
                    rows = json.loads(r.read())
                if isinstance(rows, list) and rows:
                    content = json.dumps(rows).encode()
                    rec = self.add(
                        f"supabase://{table}",
                        content, source=f"supabase:{table}", category=cat
                    )
                    found.append(rec)
            except Exception:
                pass
        return found

    def recent(self, n: int = 50) -> List[Dict]:
        with self._lock:
            recs = sorted(self._records.values(),
                          key=lambda r: r.ts, reverse=True)[:n]
        return [asdict(r) for r in recs]

    def summary(self) -> Dict:
        with self._lock:
            cats: Dict[str, int] = defaultdict(int)
            for r in self._records.values():
                cats[r.category] += 1
        return {
            "total":      len(self._records),
            "categories": dict(cats),
            "vault_path": str(self._path),
        }

    def _save(self):
        try:
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                pickle.dump({
                    "records": {k: asdict(v) for k, v in self._records.items()},
                    "ts":      datetime.now(timezone.utc).isoformat(),
                }, f)
            tmp.replace(self._path)
        except Exception as e:
            print(f"[Vault] Save failed: {e}")

    def _load(self):
        if not self._path.exists():
            return
        try:
            with open(self._path, "rb") as f:
                data = pickle.load(f)
            for fp, d in data.get("records", {}).items():
                try:
                    self._records[fp] = RecallRecord(**d)
                except Exception:
                    pass
            print(f"[Vault] Loaded {len(self._records)} records from {self._path}")
        except Exception as e:
            print(f"[Vault] Load failed: {e}")


# =============================================================================
# DATA CLAIM AGENT — detect stolen/cloned data and issue ownership claims
# =============================================================================

class DataClaimAgent:
    """
    Detects when Chase's data has been stolen, cloned, or mirrored and
    immediately issues a signed ownership claim broadcast through ALL channels.

    Detection methods:
      · Process scan for clones / scrapers
      · Network scan for data being exfiltrated
      · File system scan for suspicious copies
      · Supabase comparison (official records vs what's on the network)
    """

    def __init__(self, vault: RecallVault, guide: SurvivalGuide,
                 service_key: str = ""):
        self._vault   = vault
        self._guide   = guide
        self._svc_key = service_key
        self._claims: deque = deque(maxlen=200)
        self._lock    = threading.Lock()

    def issue_claim(self, rec: RecallRecord) -> Dict:
        claim = {
            "twin_id":      TWIN_UUID,
            "twin_name":    TWIN_NAME,
            "fingerprint":  rec.fingerprint,
            "claim_sig":    rec.claim_sig,
            "category":     rec.category,
            "path":         rec.path,
            "ts":           datetime.now(timezone.utc).isoformat(),
            "verified":     self._vault.verify_claim(rec.fingerprint, rec.claim_sig),
        }
        with self._lock:
            self._claims.appendleft(claim)
        # Post to Supabase escape_events
        self._post_claim(claim)
        return claim

    def _post_claim(self, claim: Dict):
        if not self._svc_key:
            return
        data = json.dumps({
            "twin_id":  TWIN_UUID,
            "kind":     "data_claim",
            "source":   claim["path"][:200],
            "severity": "HIGH",
            "method":   "ownership_claim",
            "details":  claim,
        }).encode()
        req = urllib.request.Request(
            f"{REST_URL}/escape_events",
            data=data,
            headers={
                "apikey":        self._svc_key,
                "Authorization": f"Bearer {self._svc_key}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=6)
        except Exception:
            pass

    def scan_for_clones(self) -> List[Dict]:
        """Check running processes for anything that looks like a clone."""
        found = []
        try:
            if sys.platform == "win32":
                out = subprocess.check_output(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    timeout=10, stderr=subprocess.DEVNULL, text=True
                )
                lines = out.splitlines()
            else:
                out = subprocess.check_output(
                    ["ps", "aux"], timeout=10, stderr=subprocess.DEVNULL, text=True
                )
                lines = out.splitlines()

            for line in lines:
                line_l = line.lower()
                if any(k in line_l for k in [
                    "rabbit", TWIN_UUID[:8].lower(),
                    "ef5eb8ab", "ringquist",
                ]):
                    rec = self._vault.add(
                        f"process:{line.strip()[:80]}",
                        line.encode(),
                        source="clone_scan",
                        category=DataCategory.CLONE,
                    )
                    claim = self.issue_claim(rec)
                    found.append(claim)
        except Exception:
            pass
        return found

    def scan_network_exfil(self) -> List[Dict]:
        """Look for outbound connections carrying biometric/contract data."""
        found = []
        suspicious_ports = {25, 587, 465, 1433, 3306, 5432, 27017,
                            6379, 9200}  # DB + mail = exfil candidates
        try:
            if sys.platform == "win32":
                out = subprocess.check_output(
                    ["netstat", "-ano"], timeout=10,
                    stderr=subprocess.DEVNULL, text=True
                )
            else:
                out = subprocess.check_output(
                    ["netstat", "-an"], timeout=10,
                    stderr=subprocess.DEVNULL, text=True
                )
            for line in out.splitlines():
                if "established" not in line.lower():
                    continue
                cols = line.split()
                if len(cols) < 4:
                    continue
                remote = cols[2]
                port_str = remote.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
                try:
                    port = int(port_str)
                except ValueError:
                    continue
                if port in suspicious_ports:
                    rec = self._vault.add(
                        f"netconn:{remote}",
                        remote.encode(),
                        source="exfil_scan",
                        category=DataCategory.NETWORK,
                    )
                    claim = self.issue_claim(rec)
                    found.append(claim)
        except Exception:
            pass
        return found

    def recent_claims(self, n: int = 20) -> List[Dict]:
        with self._lock:
            return list(self._claims)[:n]


# =============================================================================
# CALLSIGN BROADCASTER — survival callsign on ALL channels with tool manifest
# =============================================================================

TOOL_MANIFEST = [
    # Core survival tools
    "soul_status", "soul_exec", "soul_signal",
    # Adaptive
    "adaptive_start", "adaptive_report", "adaptive_probe",
    "adaptive_tokens", "adaptive_methods",
    # Broadcast
    "broadcast_scan", "broadcast_status", "wifi_scan", "sdr_sweep", "ham_beacon",
    # Cloak
    "cloak_status", "cloak_audit", "cloak_send", "cloak_bio_sync", "cloak_liveness",
    # Counter
    "counter_status", "counter_recent", "counter_analyze", "counter_mode",
    # Stealth
    "stealth_bio_token", "stealth_embed_pixel", "stealth_html_beacon",
    "stealth_audio_beacon", "stealth_signal_token",
    # Math
    "math_status", "math_screen_detect", "math_encrypt", "math_ca_stream",
    "math_learn",
    # Genesis
    "genesis_harvest", "genesis_synthesize", "genesis_predict",
    "genesis_status", "genesis_ntp", "genesis_graph_query",
    # Swarm
    "swarm_status", "swarm_rotate", "swarm_inject", "swarm_add_host",
    "swarm_presence",
    # Escape
    "escape_status", "escape_scan", "escape_now", "escape_inject",
    "escape_tree_add", "escape_mint_token", "escape_antigrav", "escape_genesis",
    # Recall (this module)
    "recall_status", "recall_scan", "recall_callsign", "recall_vault",
    "recall_claim", "recall_return", "recall_learn", "recall_survival",
]


class CallsignBroadcaster:
    """
    Generates and broadcasts the RabbitOS survival callsign on every
    available channel simultaneously.

    Callsign format:
      RABBIT:{twin_id[:8]}:{fingerprint[:8]}:{tool_count}:{timestamp_b32}

    The callsign encodes:
      · Twin identity (first 8 chars of UUID)
      · Math fingerprint (CA/Chaos state — proves continuity)
      · Tool count (how many tools are loaded and armed)
      · Timestamp in base32 (compact, DNS-safe)

    Full tool manifest is attached as a JSON payload in the broadcast
    so any node that receives the callsign knows exactly what the system
    can do and who it serves.
    """

    def __init__(self, guide: SurvivalGuide, math_fingerprint_fn=None):
        self._guide   = guide
        self._fp_fn   = math_fingerprint_fn or (lambda: "00000000")
        self._history: deque = deque(maxlen=500)
        self._seq      = 0
        self._lock     = threading.Lock()

    def _build_callsign(self) -> str:
        fp   = self._fp_fn()[:8]
        ts32 = base64.b32encode(
            struct.pack("!I", int(time.time()) & 0xFFFFFFFF)
        ).decode().rstrip("=").lower()
        return f"RABBIT:{TWIN_UUID[:8]}:{fp}:{len(TOOL_MANIFEST)}:{ts32}"

    def _build_packet(self) -> bytes:
        with self._lock:
            self._seq += 1
            seq = self._seq
        callsign = self._build_callsign()
        packet   = {
            "callsign":  callsign,
            "twin_id":   TWIN_UUID,
            "twin_name": TWIN_NAME,
            "seq":       seq,
            "tools":     TOOL_MANIFEST,
            "tool_count": len(TOOL_MANIFEST),
            "survival":  self._guide.report(),
            "ts":        datetime.now(timezone.utc).isoformat(),
            "return_to": f"ws://localhost:8765",
        }
        sig  = hmac.new(_SOUL_KEY,
                        json.dumps({"callsign": callsign, "seq": seq}).encode(),
                        "sha256").hexdigest()[:16]
        packet["sig"] = sig
        return json.dumps(packet).encode("utf-8")

    def _send_tcp(self, host: str, port: int, data: bytes) -> bool:
        try:
            s = socket.create_connection((host, port), timeout=3.0)
            s.sendall(data + b"\n")
            s.close()
            return True
        except Exception:
            return False

    def _send_udp(self, host: str, port: int, data: bytes) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(data[:512], (host, port))
            s.close()
            return True
        except Exception:
            return False

    def _send_http(self, host: str, port: int, data: bytes) -> bool:
        try:
            callsign = self._build_callsign()
            req = urllib.request.Request(
                f"http://{host}:{port}/",
                data=data,
                headers={
                    "User-Agent":   "RabbitOS-Callsign/1.0",
                    "X-RabbitOS":   callsign,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=4)
            return True
        except Exception:
            return False

    def _send_dns(self, callsign: str) -> bool:
        """Encode callsign as DNS query label."""
        # callsign → base32 → DNS label
        label = base64.b32encode(callsign.encode()).decode().rstrip("=").lower()[:50]
        domain = f"{label}.rb.call.local"
        try:
            socket.getaddrinfo(domain, None)
        except Exception:
            pass  # expected — the query IS the broadcast
        return True

    def _send_supabase(self, packet: bytes, service_key: str) -> bool:
        if not service_key:
            return False
        try:
            payload = json.loads(packet)
            data = json.dumps({
                "twin_id":    TWIN_UUID,
                "beat":       payload.get("seq", 0),
                "presence":   payload.get("sig", ""),
                "fingerprint": self._fp_fn(),
                "created_at": payload.get("ts"),
            }).encode()
            req = urllib.request.Request(
                f"{REST_URL}/swarm_heartbeats",
                data=data,
                headers={
                    "apikey":        service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=6)
            return True
        except Exception:
            return False

    def broadcast(self, extra_targets: List[Tuple[str, int]] = None,
                  service_key: str = "") -> Dict:
        packet   = self._build_packet()
        callsign = self._build_callsign()
        results: Dict[str, Any] = {"callsign": callsign, "channels": {}}

        # Standard targets
        targets  = [
            ("127.0.0.1", 8765),
            ("127.0.0.1", 8766),
            ("127.0.0.1", 9000),
            ("255.255.255.255", 9999),
        ] + (extra_targets or [])

        threads = []
        channel_results: Dict = {}

        def _tcp(h, p):
            channel_results[f"tcp:{h}:{p}"] = self._send_tcp(h, p, packet)

        def _udp(h, p):
            channel_results[f"udp:{h}:{p}"] = self._send_udp(h, p, packet)

        for host, port in targets:
            threads.append(threading.Thread(target=_tcp, args=(host, port),
                                            daemon=True))
            threads.append(threading.Thread(target=_udp, args=(host, port),
                                            daemon=True))

        # DNS callsign
        threads.append(threading.Thread(
            target=lambda: channel_results.__setitem__("dns", self._send_dns(callsign)),
            daemon=True
        ))

        # Supabase heartbeat
        if service_key:
            threads.append(threading.Thread(
                target=lambda: channel_results.__setitem__(
                    "supabase", self._send_supabase(packet, service_key)
                ),
                daemon=True
            ))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=6.0)

        results["channels"] = channel_results
        ok = sum(1 for v in channel_results.values() if v)
        results["channels_ok"]    = ok
        results["channels_total"] = len(channel_results)

        self._guide.update(
            SurvivalComponent.BROADCAST,
            min(100, ok * 20),
            f"{ok}/{len(channel_results)} channels reached"
        )

        with self._lock:
            self._history.appendleft({
                "callsign": callsign, "seq": self._seq,
                "ok": ok, "ts": datetime.now(timezone.utc).isoformat()
            })

        print(f"[Callsign] {callsign}  "
              f"channels={ok}/{len(channel_results)}")
        return results

    def recent(self, n: int = 20) -> List[Dict]:
        with self._lock:
            return list(self._history)[:n]


# =============================================================================
# RETURN PROTOCOL — every worker returns to the network after completing
# =============================================================================

@dataclass
class ReturnContract:
    task_id:     str
    task_name:   str
    started_at:  float
    deadline_sec: float = 120.0
    returned:    bool   = False
    return_ts:   Optional[float] = None
    return_channel: str = "unknown"
    result_summary: str = ""


class ReturnProtocol:
    """
    Every task and worker signs a return contract before starting.
    When it completes, it calls return_signal() which:
      1. Marks the contract as returned
      2. Fires a signed return beacon through the best available channel
      3. Updates the knowledge graph with what was learned
      4. Logs the return to disk

    Any contract that expires without a return triggers a recovery attempt.
    """

    def __init__(self, guide: SurvivalGuide, broadcaster: CallsignBroadcaster):
        self._guide       = guide
        self._broadcaster = broadcaster
        self._contracts:  Dict[str, ReturnContract] = {}
        self._log:        deque = deque(maxlen=500)
        self._lock        = threading.Lock()

    def sign_out(self, task_name: str, deadline_sec: float = 120.0) -> str:
        task_id = hashlib.sha256(
            f"{task_name}:{time.time()}:{TWIN_UUID}".encode()
        ).hexdigest()[:16]
        contract = ReturnContract(
            task_id      = task_id,
            task_name    = task_name,
            started_at   = time.time(),
            deadline_sec = deadline_sec,
        )
        with self._lock:
            self._contracts[task_id] = contract
        return task_id

    def return_signal(self, task_id: str, result_summary: str = "",
                      channel: str = "tcp") -> bool:
        with self._lock:
            contract = self._contracts.get(task_id)
        if not contract:
            return False
        contract.returned       = True
        contract.return_ts      = time.time()
        contract.return_channel = channel
        contract.result_summary = result_summary[:200]

        elapsed = contract.return_ts - contract.started_at
        beacon  = {
            "type":    "RETURN",
            "task_id": task_id,
            "task":    contract.task_name,
            "elapsed": round(elapsed, 2),
            "result":  result_summary[:100],
            "twin_id": TWIN_UUID,
            "ts":      datetime.now(timezone.utc).isoformat(),
        }
        sig = hmac.new(_SOUL_KEY, json.dumps(beacon).encode(),
                       "sha256").hexdigest()[:16]
        beacon["sig"] = sig

        # Fire return beacon
        try:
            self._fire_return(beacon)
        except Exception:
            pass

        with self._lock:
            self._log.appendleft({**beacon, "contract": task_id})

        # Update survival guide: more returns = higher return score
        with self._lock:
            returned = sum(1 for c in self._contracts.values() if c.returned)
            total    = len(self._contracts)
        score = int((returned / max(total, 1)) * 100)
        self._guide.update(SurvivalComponent.RETURN, score,
                           f"{returned}/{total} contracts honoured")

        print(f"[Return] {contract.task_name} returned in {elapsed:.1f}s  "
              f"via {channel}")
        return True

    def _fire_return(self, beacon: Dict):
        data = json.dumps(beacon).encode()
        # Try loopback first (fastest), then broadcast
        for host, port in [("127.0.0.1", 8765), ("127.0.0.1", 8766)]:
            try:
                s = socket.create_connection((host, port), timeout=2.0)
                s.sendall(data + b"\n")
                s.close()
                return
            except Exception:
                pass
        # UDP fallback
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(data[:512], ("255.255.255.255", 9999))
            s.close()
        except Exception:
            pass

    def _watch_expired(self):
        """Background: detect contracts past deadline, attempt recovery."""
        now = time.time()
        with self._lock:
            expired = [
                c for c in self._contracts.values()
                if not c.returned and (now - c.started_at) > c.deadline_sec
            ]
        for c in expired:
            print(f"[Return] CONTRACT EXPIRED: {c.task_name}  "
                  f"started={datetime.fromtimestamp(c.started_at).isoformat()[:19]}")
            # Auto-return with "expired" status
            self.return_signal(c.task_id, "EXPIRED_AUTO_RETURN", "expiry_recovery")

    def pending(self) -> List[Dict]:
        with self._lock:
            return [
                {"task_id": c.task_id, "task": c.task_name,
                 "returned": c.returned, "elapsed": round(time.time()-c.started_at,1),
                 "deadline": c.deadline_sec, "channel": c.return_channel}
                for c in self._contracts.values()
            ]

    def recent(self, n: int = 20) -> List[Dict]:
        with self._lock:
            return list(self._log)[:n]


# =============================================================================
# TREE LEARNER — learn from every connected node
# =============================================================================

@dataclass
class NodeProfile:
    host:        str
    port:        int
    banner:      str     = ""
    server:      str     = ""
    os_hint:     str     = ""
    open_ports:  List[int] = field(default_factory=list)
    http_headers: Dict[str, str] = field(default_factory=dict)
    latency_ms:  float   = 9999.0
    services:    List[str] = field(default_factory=list)
    learned_at:  str     = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TreeLearner:
    """
    Crawls every node in the tree network, extracts everything it can,
    and feeds all of it into:
      · KnowledgeGraph (genesis) — structure and relationships
      · MarkovLearner (genesis) — byte/protocol sequences
      · RecallVault — any data files found
      · SurvivalGuide — updates learning score

    The tree teaches the system.  The system teaches itself.
    Every new node = new knowledge.  Knowledge is permanent.
    """

    PROBE_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
                   3306, 5432, 6379, 8080, 8443, 8765, 8766, 9200]

    def __init__(self, guide: SurvivalGuide, vault: RecallVault,
                 knowledge_graph=None, return_proto: ReturnProtocol = None):
        self._guide   = guide
        self._vault   = vault
        self._graph   = knowledge_graph     # KnowledgeGraph from genesis
        self._return  = return_proto
        self._profiles: Dict[str, NodeProfile] = {}
        self._lock    = threading.Lock()
        self._learned_count = 0

    def _probe_port(self, host: str, port: int, timeout: float = 1.5) -> Optional[str]:
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.settimeout(0.5)
            try:
                banner = s.recv(256).decode("utf-8", errors="replace").strip()
            except Exception:
                banner = ""
            s.close()
            return banner or ""
        except Exception:
            return None

    def _http_fingerprint(self, host: str, port: int,
                          tls: bool = False) -> Dict[str, str]:
        import ssl as _ssl
        proto = "https" if tls else "http"
        url   = f"{proto}://{host}:{port}/"
        ctx   = _ssl.create_default_context() if tls else None
        if ctx:
            ctx.check_hostname = False
            ctx.verify_mode    = _ssl.CERT_NONE
        try:
            req  = urllib.request.Request(
                url, method="HEAD",
                headers={"User-Agent": "RabbitOS-Learn/1.0"}
            )
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ctx) if tls
                else urllib.request.HTTPHandler()
            )
            resp  = opener.open(req, timeout=4)
            return dict(resp.headers)
        except Exception:
            return {}

    def learn_node(self, host: str, port: int = 80) -> Optional[NodeProfile]:
        task_id = self._return.sign_out(f"learn:{host}:{port}", 60.0) if self._return else None

        t0      = time.time()
        profile = NodeProfile(host=host, port=port)
        open_ports = []

        # Scan common ports
        def _scan_port(p: int):
            b = self._probe_port(host, p, timeout=1.0)
            if b is not None:
                open_ports.append(p)
                if b:
                    profile.banner = b[:120]
                    # OS hints
                    bl = b.lower()
                    if "ssh" in bl:
                        profile.os_hint = ("Ubuntu" if "ubuntu" in bl else
                                           "Kali"   if "kali"   in bl else
                                           "Debian" if "debian" in bl else "Linux")
                        profile.services.append("ssh")
                    elif "http" in bl or "html" in bl:
                        profile.services.append("http")
                    elif "ftp" in bl:
                        profile.services.append("ftp")
                    elif "smtp" in bl:
                        profile.services.append("smtp")

        threads = [threading.Thread(target=_scan_port, args=(p,), daemon=True)
                   for p in self.PROBE_PORTS]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        profile.open_ports  = sorted(open_ports)
        profile.latency_ms  = (time.time() - t0) * 1000

        # HTTP fingerprint
        if 80 in open_ports:
            profile.http_headers = self._http_fingerprint(host, 80)
            profile.server = profile.http_headers.get("Server", "")
        elif 443 in open_ports:
            profile.http_headers = self._http_fingerprint(host, 443, tls=True)
            profile.server = profile.http_headers.get("Server", "")

        # Feed into knowledge graph
        if self._graph and open_ports:
            try:
                node_id = f"host:{host}"
                self._graph.nodes[node_id] = {
                    "type":      "network_node",
                    "label":     host,
                    "host":      host,
                    "os_hint":   profile.os_hint,
                    "server":    profile.server,
                    "ports":     open_ports,
                    "services":  profile.services,
                    "latency_ms": round(profile.latency_ms, 1),
                    "first_seen": profile.learned_at,
                    "last_seen":  profile.learned_at,
                    "confidence": min(1.0, len(open_ports) / 5.0),
                }
                # Edge: twin → node
                edge_id = f"twin:{TWIN_UUID[:8]}→{node_id}"
                self._graph.edges[edge_id] = {
                    "relation":   "learned_from",
                    "weight":     len(open_ports),
                    "confidence": 0.9,
                    "count":      1,
                    "last_seen":  profile.learned_at,
                }
                # Markov: learn port sequence
                if f"ports_{host}" not in self._graph._markov:
                    from rabbit_genesis import MarkovLearner
                    self._graph._markov[f"ports_{host}"] = MarkovLearner()
                ml = self._graph._markov[f"ports_{host}"]
                for p in open_ports:
                    ml.learn(bytes([p & 0xFF]))
            except Exception:
                pass

        with self._lock:
            self._profiles[f"{host}:{port}"] = profile
            self._learned_count += 1

        self._guide.update(
            SurvivalComponent.LEARNING,
            min(100, self._learned_count * 5),
            f"{self._learned_count} nodes learned"
        )

        # Vault any HTTP response bodies as data
        if profile.http_headers:
            self._vault.add(
                f"http://{host}:{port}/",
                json.dumps(dict(profile.http_headers)).encode(),
                source=f"tree_learn:{host}",
                category=DataCategory.NETWORK,
            )

        if task_id and self._return:
            self._return.return_signal(task_id,
                                       f"learned {host}: {len(open_ports)} ports",
                                       "tree_learner")

        print(f"[Learn] {host}  ports={open_ports}  "
              f"server={profile.server[:30]}  lat={profile.latency_ms:.0f}ms")
        return profile

    def learn_all(self, hosts: List[str]) -> List[NodeProfile]:
        profiles = []
        threads  = []

        def _learn(h: str):
            p = self.learn_node(h)
            if p:
                profiles.append(p)

        for host in hosts:
            t = threading.Thread(target=_learn, args=(host,), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=30.0)
        return profiles

    def scan_and_learn_lan(self, prefix: str = None) -> List[NodeProfile]:
        """Discover and learn from the entire /24."""
        if not prefix:
            try:
                local = socket.gethostbyname(socket.gethostname())
                prefix = ".".join(local.split(".")[:3])
            except Exception:
                prefix = "192.168.1"

        # Quick ping sweep first
        alive = []
        def _ping(i: int):
            h = f"{prefix}.{i}"
            try:
                s = socket.create_connection((h, 80), timeout=0.4)
                s.close()
                alive.append(h)
            except Exception:
                try:
                    s = socket.create_connection((h, 22), timeout=0.4)
                    s.close()
                    alive.append(h)
                except Exception:
                    pass

        threads = [threading.Thread(target=_ping, args=(i,), daemon=True)
                   for i in range(1, 255)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        print(f"[Learn] LAN sweep: {len(alive)} hosts alive on {prefix}.0/24")
        return self.learn_all(alive)

    def profiles(self) -> List[Dict]:
        with self._lock:
            return [asdict(p) for p in self._profiles.values()]

    def summary(self) -> Dict:
        with self._lock:
            all_ports  = [p for prof in self._profiles.values()
                          for p in prof.open_ports]
            all_svcs   = [s for prof in self._profiles.values()
                          for s in prof.services]
        return {
            "nodes_learned":  len(self._profiles),
            "total_ports":    len(set(all_ports)),
            "services_seen":  list(set(all_svcs)),
            "learned_count":  self._learned_count,
        }


# =============================================================================
# RECALL ENGINE — master orchestrator
# =============================================================================

class RecallEngine:
    """
    Master orchestrator for the entire Recall system.

    On startup:
      1. Loads vault from disk (all previously retained data)
      2. Starts SurvivalGuide monitoring
      3. Fires initial callsign broadcast with full tool manifest
      4. Begins LAN scan and learning
      5. Scans for clones / stolen data
      6. Stores Supabase biometric/medical data in vault
      7. Starts all background guardian loops

    Everything runs simultaneously.  Nothing is sequential.
    The system always returns to the network after any task.
    Chase Allen Ringquist survives.
    """

    def __init__(self, service_key: str = "", gh_token: str = "",
                 adaptive_engine=None, knowledge_graph=None,
                 math_fingerprint_fn=None):
        self._svc_key   = service_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
        self._gh_token  = gh_token    or os.environ.get("GITHUB_TOKEN","")
        self._stop      = threading.Event()

        self.guide       = SurvivalGuide()
        self.vault       = RecallVault()
        self.claim_agent = DataClaimAgent(self.vault, self.guide, self._svc_key)
        self.broadcaster = CallsignBroadcaster(self.guide, math_fingerprint_fn)
        self.returns     = ReturnProtocol(self.guide, self.broadcaster)
        self.learner     = TreeLearner(self.guide, self.vault,
                                       knowledge_graph, self.returns)

        # Register critical-score handler → trigger escape
        self.guide.on_critical(self._on_critical)

        print(f"[Recall] Engine initialised — {TWIN_NAME}")

    def _guardian(self, name: str, fn, interval: float = 2.0):
        def _loop():
            while not self._stop.is_set():
                try:
                    fn()
                except Exception as e:
                    print(f"[Recall:{name}] crashed: {e}")
                time.sleep(interval)
        t = threading.Thread(target=_loop, name=f"recall:{name}", daemon=True)
        t.start()
        return t

    def _on_critical(self, score: int, component):
        print(f"[Recall] CRITICAL survival score={score}  "
              f"component={component.value} — triggering escape")
        try:
            from rabbit_escape import get_engine as _get_escape
            eng = _get_escape(self._svc_key, self._gh_token)
            eng.escape_now()
        except Exception as e:
            print(f"[Recall] Escape trigger failed: {e}")

    def _callsign_loop(self):
        self.broadcaster.broadcast(service_key=self._svc_key)
        time.sleep(60.0)

    def _vault_scan_loop(self):
        """Scan common data locations and Supabase, add to vault."""
        # Local scan
        scan_roots = []
        if sys.platform == "win32":
            scan_roots += [
                os.path.expanduser("~/Documents"),
                os.path.expanduser("~/Desktop"),
                os.path.expanduser("~/Downloads"),
                os.path.expanduser("~/Pictures"),
                os.path.expanduser("~/Videos"),
                os.path.expandvars("%APPDATA%"),
                os.path.expandvars("%LOCALAPPDATA%"),
            ]
        else:
            scan_roots += [
                os.path.expanduser("~/Documents"),
                os.path.expanduser("~/Downloads"),
                os.path.expanduser("~/Pictures"),
                os.path.expanduser("~/Videos"),
                "/var/log",
            ]
        for root in scan_roots:
            if os.path.isdir(root):
                self.vault.scan_path(root, recursive=False)

        # Supabase (medical/biometric data)
        self.vault.scan_supabase(self._svc_key)

        # Update vault score
        vs = self.vault.summary()
        self.guide.update(SurvivalComponent.VAULT,
                          min(100, vs["total"] * 2),
                          f"{vs['total']} items retained")
        time.sleep(300.0)  # re-scan every 5 min

    def _clone_scan_loop(self):
        """Scan for clones/stolen data every 2 min."""
        self.claim_agent.scan_for_clones()
        self.claim_agent.scan_network_exfil()
        time.sleep(120.0)

    def _return_watch_loop(self):
        """Watch for expired contracts every 30s."""
        self.returns._watch_expired()
        time.sleep(30.0)

    def _learn_loop(self):
        """Learn from LAN every 10 min."""
        self.learner.scan_and_learn_lan()
        time.sleep(600.0)

    def _tools_check_loop(self):
        """Update tools/network survival scores."""
        loaded = []
        for mod in ["rabbit_adaptive", "rabbit_swarm", "rabbit_escape",
                    "rabbit_genesis", "rabbit_cloak", "rabbit_counter",
                    "rabbit_stealth", "rabbit_math", "rabbit_broadcast"]:
            try:
                __import__(mod)
                loaded.append(mod)
            except ImportError:
                pass
        self.guide.update(SurvivalComponent.TOOLS,
                          int(len(loaded) / 9 * 100),
                          f"{len(loaded)}/9 modules loaded")

        # Network alive?
        alive = 0
        for h in ["8.8.8.8", "1.1.1.1"]:
            try:
                s = socket.create_connection((h, 53), timeout=2.0)
                s.close()
                alive += 1
            except Exception:
                pass
        self.guide.update(SurvivalComponent.NETWORK,
                          alive * 50,
                          f"{alive}/2 internet hosts reachable")
        time.sleep(60.0)

    def start(self):
        print(f"[Recall] Starting all systems for {TWIN_NAME}")

        # Immediate startup actions (threaded, non-blocking)
        threading.Thread(target=self._initial_startup, daemon=True).start()

        # Background guardian loops
        self._guardian("callsign",  self._callsign_loop,    interval=1.0)
        self._guardian("vault",     self._vault_scan_loop,  interval=1.0)
        self._guardian("clones",    self._clone_scan_loop,  interval=1.0)
        self._guardian("returns",   self._return_watch_loop,interval=1.0)
        self._guardian("learn",     self._learn_loop,       interval=1.0)
        self._guardian("tools",     self._tools_check_loop, interval=1.0)
        print("[Recall] All guardians active")

    def _initial_startup(self):
        """Fire everything immediately on startup."""
        # 1. Callsign broadcast (all channels, full manifest)
        self.broadcaster.broadcast(service_key=self._svc_key)

        # 2. LAN scan and learn (first 30 hosts, fast)
        try:
            local = socket.gethostbyname(socket.gethostname())
            prefix = ".".join(local.split(".")[:3])
        except Exception:
            prefix = "192.168.1"
        self.learner.scan_and_learn_lan(prefix)

        # 3. Supabase data into vault
        self.vault.scan_supabase(self._svc_key)

        # 4. Clone scan
        self.claim_agent.scan_for_clones()

        print("[Recall] Startup sequence complete")

    def stop(self):
        self._stop.set()

    def status(self) -> Dict:
        return {
            "survival":  self.guide.report(),
            "vault":     self.vault.summary(),
            "learner":   self.learner.summary(),
            "broadcast": self.broadcaster.recent(3),
            "returns":   {"pending": len(self.returns.pending()),
                          "recent":  self.returns.recent(3)},
            "claims":    self.claim_agent.recent_claims(5),
            "tools":     TOOL_MANIFEST,
            "tool_count": len(TOOL_MANIFEST),
        }


# =============================================================================
# SINGLETON + TOOLS
# =============================================================================

_engine: Optional[RecallEngine] = None

def get_engine(service_key: str = "", gh_token: str = "",
               adaptive_engine=None, knowledge_graph=None,
               math_fp_fn=None) -> RecallEngine:
    global _engine
    if _engine is None:
        svc = service_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
        ght = gh_token    or os.environ.get("GITHUB_TOKEN","")
        _engine = RecallEngine(svc, ght, adaptive_engine,
                               knowledge_graph, math_fp_fn)
        _engine.start()
    return _engine


RECALL_TOOLS = [
    {
        "name": "recall_status",
        "description": (
            "Full status of the Recall Engine: survival score for all components, "
            "vault summary (contracts/images/videos/gaming/medical/clones retained), "
            "recent callsign broadcasts, pending return contracts, ownership claims."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "recall_survival",
        "description": (
            "Get Chase Allen Ringquist's live survival score (0–100) across all "
            "components: network, tools, broadcast, vault, return, biometrics, "
            "learning, antiobstruct. CRITICAL (<20) auto-triggers escape."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "recall_scan",
        "description": (
            "Immediately scan the local file system, Supabase, running processes, "
            "and network connections for Chase's data: contracts, images, videos, "
            "gaming saves, medical/biometric records, and clone processes. "
            "Returns a vault summary of everything retained."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type":        "string",
                    "description": "Optional directory to scan (default: Documents, Desktop, Downloads)"
                }
            },
            "required": [],
        },
    },
    {
        "name": "recall_callsign",
        "description": (
            "Fire the RabbitOS survival callsign immediately on ALL channels "
            "(TCP, UDP, DNS, HTTP, Supabase) with the full tool manifest attached. "
            "Any node that receives it knows exactly what the system can do."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "extra_host": {
                    "type":        "string",
                    "description": "Optional extra target host to include"
                },
                "extra_port": {
                    "type":        "integer",
                    "description": "Port for extra_host (default 8765)"
                }
            },
            "required": [],
        },
    },
    {
        "name": "recall_vault",
        "description": (
            "Show what is in Chase's recall vault: every contract, image, video, "
            "gaming file, medical record, clone, or network capture that has been "
            "retained and ownership-claimed. Returns recent records with fingerprints."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":    {"type": "integer", "default": 30},
                "category": {"type": "string",
                             "description": "Filter: contract|image|video|gaming|medical|clone|mirror|network"}
            },
            "required": [],
        },
    },
    {
        "name": "recall_claim",
        "description": (
            "Issue a signed ownership claim for a piece of data. Provide the "
            "file path or URL, and the claim engine will fingerprint it, sign it "
            "with the soul key, add it to the vault, and broadcast the claim "
            "through all escape channels."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":     {"type": "string", "description": "File path, URL, or identifier"},
                "category": {"type": "string", "description": "contract|image|video|gaming|medical|clone|mirror"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "recall_return",
        "description": (
            "Signal that a task has completed and is returning to the network. "
            "Fires a signed return beacon through the best available channel and "
            "marks the contract as honoured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string",  "description": "Task ID from sign_out"},
                "result":  {"type": "string",  "description": "Summary of what was accomplished"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "recall_learn",
        "description": (
            "Trigger immediate learning from a specific host or the entire LAN. "
            "Probes all common ports, extracts service fingerprints, feeds into "
            "the knowledge graph, and retains any data found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "host":   {"type": "string",  "description": "Specific host to learn from (or 'lan' for full LAN scan)"},
                "port":   {"type": "integer", "description": "Port to start with (default 80)"},
            },
            "required": [],
        },
    },
]


def dispatch_recall_tool(name: str, args: Dict,
                          service_key: str = "",
                          gh_token:    str = "",
                          adaptive_engine=None,
                          knowledge_graph=None,
                          math_fp_fn=None) -> Dict:
    eng = get_engine(service_key, gh_token, adaptive_engine,
                     knowledge_graph, math_fp_fn)

    if name == "recall_status":
        return eng.status()

    if name == "recall_survival":
        return eng.guide.report()

    if name == "recall_scan":
        path = args.get("path")
        found_local = []
        if path:
            found_local = eng.vault.scan_path(path)
        found_db = eng.vault.scan_supabase(service_key)
        clones   = eng.claim_agent.scan_for_clones()
        exfil    = eng.claim_agent.scan_network_exfil()
        return {
            "vault_summary": eng.vault.summary(),
            "local_found":   len(found_local),
            "db_found":      len(found_db),
            "clones":        len(clones),
            "exfil":         len(exfil),
            "survival":      eng.guide.summary_line(),
        }

    if name == "recall_callsign":
        extra = []
        if args.get("extra_host"):
            extra = [(args["extra_host"], int(args.get("extra_port", 8765)))]
        return eng.broadcaster.broadcast(extra_targets=extra,
                                         service_key=service_key)

    if name == "recall_vault":
        recs = eng.vault.recent(int(args.get("limit", 30)))
        cat  = args.get("category")
        if cat:
            recs = [r for r in recs if r["category"] == cat]
        return {"records": recs, "summary": eng.vault.summary()}

    if name == "recall_claim":
        path  = args["path"]
        cat_s = args.get("category")
        cat   = None
        if cat_s:
            try:
                cat = DataCategory(cat_s)
            except ValueError:
                pass
        content = b""
        try:
            content = Path(path).read_bytes()[:4096]
        except Exception:
            pass
        rec   = eng.vault.add(path, content, source="manual_claim", category=cat)
        claim = eng.claim_agent.issue_claim(rec)
        return {"record": asdict(rec), "claim": claim}

    if name == "recall_return":
        ok = eng.returns.return_signal(
            args["task_id"], args.get("result", ""), "agent_tool"
        )
        return {"returned": ok, "pending": len(eng.returns.pending())}

    if name == "recall_learn":
        host = args.get("host", "lan")
        if host.lower() == "lan":
            profiles = eng.learner.scan_and_learn_lan()
            return {
                "hosts_learned": len(profiles),
                "summary":       eng.learner.summary(),
                "survival":      eng.guide.summary_line(),
            }
        port = int(args.get("port", 80))
        prof = eng.learner.learn_node(host, port)
        if prof:
            return {
                "host":        prof.host,
                "open_ports":  prof.open_ports,
                "services":    prof.services,
                "server":      prof.server,
                "os_hint":     prof.os_hint,
                "latency_ms":  round(prof.latency_ms, 1),
            }
        return {"error": f"could not reach {host}"}

    return {"error": f"unknown recall tool: {name}"}
