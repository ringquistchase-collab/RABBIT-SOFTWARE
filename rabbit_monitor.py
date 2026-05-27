"""
rabbit_monitor.py — RabbitOS Live Network + Identity Monitor
Chase Allen Ringquist | RABBIT-SOFTWARE

Covers:
  - NetworkConnectionMonitor  : real-time netstat delta (new/closed connections)
  - ARPTableMonitor           : new/gone devices on LAN, device fingerprinting
  - InterfaceStatMonitor      : per-interface bandwidth, packet counters, state
  - PortActivityMonitor       : open/closed port change detection
  - DNSActivityMonitor        : DNS query/response tracking
  - ChaseRingquistMonitor     : personal identity stream — EEG mesh nodes, biometric
                                packet rates, identity match score, XRPL anchor,
                                cold network presence, cloud trail velocity,
                                survival queue, active agent sessions
  - AlertEngine               : threshold alerts + anomaly detection for all monitors
  - LiveMonitorDashboard      : aggregates all streams, background polling,
                                SQLite + Supabase persistence
  - MONITOR_TOOLS             : 28 tools auto-wired into rabbit_agent
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

shows_dna_root = False
assert shows_dna_root is False

_LOG = logging.getLogger("rabbit.monitor")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [MONITOR] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

_BASE = Path(__file__).parent
_MON_DB = _BASE / "rabbit_monitor.db"

TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"

# Mesh RF carrier frequencies (GHz) mapped to EEG electrode positions
MESH_CARRIERS = {
    "A": 10.23, "T": 10.24, "U": 10.25,
    "G": 10.26, "C": 10.27,
    "HEAD_01":  10.245,
    "CHEST_01": 10.251,
}

# Alert severity levels
SEVERITY_INFO    = "info"
SEVERITY_WARN    = "warn"
SEVERITY_ALERT   = "alert"
SEVERITY_CRITICAL= "critical"


def _log(msg: str) -> None:
    try:
        _LOG.info(msg)
    except UnicodeEncodeError:
        _LOG.info(msg.encode("ascii", "replace").decode())


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class NetworkConnection:
    proto:    str
    local:    str
    remote:   str
    state:    str
    pid:      str = ""
    process:  str = ""
    ts:       float = field(default_factory=time.time)

    @property
    def key(self) -> str:
        return f"{self.proto}:{self.local}:{self.remote}"


@dataclass
class ARPEntry:
    ip:       str
    mac_hash: str          # SHA-256 of raw MAC — never store plaintext MAC
    iface:    str = ""
    vendor:   str = ""
    ts:       float = field(default_factory=time.time)
    online:   bool = True

    @property
    def key(self) -> str:
        return f"{self.ip}:{self.mac_hash[:8]}"


@dataclass
class InterfaceStat:
    name:       str
    bytes_sent: int = 0
    bytes_recv: int = 0
    pkts_sent:  int = 0
    pkts_recv:  int = 0
    errors_in:  int = 0
    errors_out: int = 0
    state:      str = "unknown"
    ts:         float = field(default_factory=time.time)


@dataclass
class MonitorAlert:
    alert_id:   str
    source:     str       # network / arp / port / identity / eeg / biometric / ...
    severity:   str       # info / warn / alert / critical
    title:      str
    detail:     str
    data:       Dict = field(default_factory=dict)
    ts:         float = field(default_factory=time.time)
    acked:      bool = False


@dataclass
class MeshNodeStatus:
    node_id:        str
    label:          str
    carrier_ghz:    float
    online:         bool
    last_seen:      float
    signal_strength: float = 0.0
    eeg_band:       str = ""
    biometric_rate: float = 0.0   # packets/min
    ts:             float = field(default_factory=time.time)


@dataclass
class IdentityStreamSnapshot:
    twin_uuid:        str
    twin_name:        str
    timestamp:        float
    eeg_nodes_online: int
    eeg_nodes_total:  int
    biometric_rate:   float     # packets/min
    identity_score:   float     # 0.0–1.0 match confidence
    xrpl_ledger_seq:  int
    xrpl_reachable:   bool
    cold_nodes_online:int
    cold_nodes_total: int
    trail_actions_1m: int       # cloud trail actions in last minute
    survival_queued:  int       # tasks in survival queue
    active_modules:   List[str]
    alerts:           int       # active unacked alerts
    shows_dna_root:   bool = False


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — NETWORK CONNECTION MONITOR
# ══════════════════════════════════════════════════════════════════════════════

class NetworkConnectionMonitor:
    """
    Polls netstat every N seconds. Tracks new/closed connections.
    Emits MonitorAlerts for unexpected outbound connections.
    """

    SUSPICIOUS_PORTS = {
        31337, 4444, 12345, 27374, 50050, 1080,
        6667, 6668, 6669,   # IRC (C2 channel indicator)
        9050,               # Tor SOCKS
        65535,              # common RAT port
    }

    def __init__(self) -> None:
        self._prev: Dict[str, NetworkConnection] = {}
        self._curr: Dict[str, NetworkConnection] = {}
        self._lock = threading.Lock()
        self._new_conns:    deque = deque(maxlen=500)
        self._closed_conns: deque = deque(maxlen=500)

    def _parse_netstat(self) -> Dict[str, NetworkConnection]:
        conns: Dict[str, NetworkConnection] = {}
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True, text=True, timeout=10,
                    errors="replace").stdout
                for line in out.splitlines():
                    m = re.match(
                        r'\s+(TCP|UDP)\s+([\d.:*]+)\s+([\d.:*]+)\s+(\w+)\s+(\d+)',
                        line, re.I)
                    if m:
                        c = NetworkConnection(
                            proto=m.group(1).upper(),
                            local=m.group(2), remote=m.group(3),
                            state=m.group(4).upper(), pid=m.group(5))
                        conns[c.key] = c
            else:
                out = subprocess.run(
                    ["ss", "-tunp"],
                    capture_output=True, text=True, timeout=10).stdout
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 5:
                        c = NetworkConnection(
                            proto=parts[0].upper(),
                            local=parts[4], remote=parts[5] if len(parts) > 5 else "*",
                            state=parts[1].upper())
                        conns[c.key] = c
        except Exception as exc:
            _log(f"netstat parse: {exc}")
        return conns

    def poll(self) -> Tuple[List[NetworkConnection], List[NetworkConnection]]:
        """Returns (new_connections, closed_connections) since last poll."""
        curr = self._parse_netstat()
        with self._lock:
            prev = self._prev
            new_keys    = set(curr.keys()) - set(prev.keys())
            closed_keys = set(prev.keys()) - set(curr.keys())
            new    = [curr[k] for k in new_keys]
            closed = [prev[k] for k in closed_keys]
            self._prev = curr
            self._curr = curr
            for c in new:
                self._new_conns.append(c)
            for c in closed:
                self._closed_conns.append(c)
        return new, closed

    def check_suspicious(self, conns: List[NetworkConnection]) -> List[MonitorAlert]:
        alerts = []
        for c in conns:
            remote_port = 0
            try:
                remote_port = int(c.remote.rsplit(":", 1)[-1])
            except Exception:
                pass
            if remote_port in self.SUSPICIOUS_PORTS:
                alerts.append(MonitorAlert(
                    alert_id=hashlib.sha256(
                        f"{c.key}{time.time()}".encode()).hexdigest()[:12],
                    source="network",
                    severity=SEVERITY_ALERT,
                    title=f"Suspicious outbound: port {remote_port}",
                    detail=f"{c.local} -> {c.remote} ({c.state})",
                    data=asdict(c),
                ))
        return alerts

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            by_state: Dict[str, int] = defaultdict(int)
            by_proto: Dict[str, int] = defaultdict(int)
            for c in self._curr.values():
                by_state[c.state] += 1
                by_proto[c.proto] += 1
        return {
            "total":         len(self._curr),
            "by_state":      dict(by_state),
            "by_proto":      dict(by_proto),
            "new_last_poll": len(self._new_conns),
            "closed_last_poll": len(self._closed_conns),
            "recent_new":    [asdict(c) for c in list(self._new_conns)[-10:]],
        }

    def all_connections(self) -> List[Dict]:
        with self._lock:
            return [asdict(c) for c in self._curr.values()]


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — ARP TABLE MONITOR
# ══════════════════════════════════════════════════════════════════════════════

class ARPTableMonitor:
    """
    Polls the ARP table. Detects new devices appearing on LAN,
    devices going offline, and MAC address changes (potential ARP spoofing).
    MACs are stored as SHA-256 hashes only.
    """

    def __init__(self) -> None:
        self._known: Dict[str, ARPEntry] = {}
        self._lock  = threading.Lock()

    def _parse_arp(self) -> Dict[str, ARPEntry]:
        entries: Dict[str, ARPEntry] = {}
        try:
            out = subprocess.run(
                ["arp", "-a"],
                capture_output=True, text=True, timeout=8,
                errors="replace").stdout
            for line in out.splitlines():
                m = re.search(r"([\d.]+)\s+([\w\-:]+)", line)
                if m:
                    ip  = m.group(1)
                    mac = m.group(2).lower().replace("-", ":")
                    if mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
                        continue
                    mac_hash = hashlib.sha256(mac.encode()).hexdigest()
                    iface_m = re.search(r"Interface: ([\d.]+)", line)
                    e = ARPEntry(
                        ip=ip, mac_hash=mac_hash,
                        iface=iface_m.group(1) if iface_m else "")
                    entries[ip] = e
        except Exception as exc:
            _log(f"ARP parse: {exc}")
        return entries

    def poll(self) -> Tuple[List[ARPEntry], List[ARPEntry], List[ARPEntry]]:
        """Returns (new_devices, gone_devices, changed_mac_devices)."""
        curr = self._parse_arp()
        with self._lock:
            known = self._known
            new_ips     = set(curr.keys()) - set(known.keys())
            gone_ips    = set(known.keys()) - set(curr.keys())
            shared_ips  = set(curr.keys()) & set(known.keys())
            changed = [curr[ip] for ip in shared_ips
                       if curr[ip].mac_hash != known[ip].mac_hash]
            new   = [curr[ip] for ip in new_ips]
            gone  = [known[ip] for ip in gone_ips]
            for ip in gone_ips:
                known[ip].online = False
            self._known.update(curr)
        return new, gone, changed

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            online = [e for e in self._known.values() if e.online]
            offline = [e for e in self._known.values() if not e.online]
        return {
            "total_known":   len(self._known),
            "online":        len(online),
            "offline":       len(offline),
            "devices":       [
                {"ip": e.ip, "mac_hash": e.mac_hash[:12],
                 "online": e.online, "iface": e.iface}
                for e in list(self._known.values())[:50]
            ],
        }

    def check_arp_spoof(self, changed: List[ARPEntry]) -> List[MonitorAlert]:
        return [
            MonitorAlert(
                alert_id=hashlib.sha256(
                    f"arp_spoof{e.ip}{time.time()}".encode()).hexdigest()[:12],
                source="arp",
                severity=SEVERITY_CRITICAL,
                title=f"Possible ARP spoof: {e.ip}",
                detail=f"MAC changed for {e.ip} — potential MITM attack",
                data={"ip": e.ip, "new_mac_hash": e.mac_hash[:16]},
            )
            for e in changed
        ]


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — INTERFACE STAT MONITOR
# ══════════════════════════════════════════════════════════════════════════════

class InterfaceStatMonitor:
    """
    Tracks per-interface byte/packet counters. Computes bandwidth utilisation.
    Detects interface state changes (up/down).
    """

    def __init__(self) -> None:
        self._prev: Dict[str, InterfaceStat] = {}
        self._lock  = threading.Lock()

    def _read_stats(self) -> Dict[str, InterfaceStat]:
        stats: Dict[str, InterfaceStat] = {}
        try:
            import psutil
            for name, s in psutil.net_io_counters(pernic=True).items():
                stats[name] = InterfaceStat(
                    name=name,
                    bytes_sent=s.bytes_sent, bytes_recv=s.bytes_recv,
                    pkts_sent=s.packets_sent, pkts_recv=s.packets_recv,
                    errors_in=s.errin, errors_out=s.errout,
                )
            for name, addrs in psutil.net_if_stats().items():
                if name in stats:
                    stats[name].state = "up" if addrs.isup else "down"
            return stats
        except ImportError:
            pass

        # Windows fallback: netstat -e
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["netstat", "-e"], capture_output=True, text=True,
                    timeout=8, errors="replace").stdout
                m_recv = re.search(r"Bytes\s+(\d+)\s+(\d+)", out)
                if m_recv:
                    stats["all"] = InterfaceStat(
                        name="all",
                        bytes_recv=int(m_recv.group(1)),
                        bytes_sent=int(m_recv.group(2)),
                    )
        except Exception:
            pass
        return stats

    def poll(self) -> Dict[str, Dict]:
        """Return bandwidth delta (bytes/s) since last poll."""
        curr = self._read_stats()
        delta: Dict[str, Dict] = {}
        with self._lock:
            prev = self._prev
            for name, stat in curr.items():
                if name in prev:
                    p = prev[name]
                    elapsed = max(stat.ts - p.ts, 0.001)
                    bw_in   = max(0, stat.bytes_recv - p.bytes_recv) / elapsed
                    bw_out  = max(0, stat.bytes_sent - p.bytes_sent) / elapsed
                    delta[name] = {
                        "bw_in_bps":  round(bw_in),
                        "bw_out_bps": round(bw_out),
                        "bw_in_kb":   round(bw_in / 1024, 1),
                        "bw_out_kb":  round(bw_out / 1024, 1),
                        "state":      stat.state,
                        "errors_in":  stat.errors_in,
                        "errors_out": stat.errors_out,
                    }
            self._prev = curr
        return delta

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "interfaces": [
                    {"name": s.name, "state": s.state,
                     "bytes_recv_mb": round(s.bytes_recv / 1e6, 2),
                     "bytes_sent_mb": round(s.bytes_sent / 1e6, 2),
                     "errors": s.errors_in + s.errors_out}
                    for s in self._prev.values()
                ]
            }


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — PORT ACTIVITY MONITOR
# ══════════════════════════════════════════════════════════════════════════════

class PortActivityMonitor:
    """
    Tracks which TCP/UDP ports are open (LISTENING) on this machine.
    Alerts on unexpected new listening ports.
    """

    EXPECTED_PORTS: Set[int] = {
        80, 443, 8080, 8443, 9014, 9015, 9016,
        3389,   # RDP (Windows)
        5040,   # Windows service
    }

    def __init__(self) -> None:
        self._prev_ports: Set[int] = set()
        self._lock = threading.Lock()

    def _get_listening_ports(self) -> Set[int]:
        ports: Set[int] = set()
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["netstat", "-ano"], capture_output=True,
                    text=True, timeout=10, errors="replace").stdout
                for line in out.splitlines():
                    if "LISTENING" in line.upper():
                        m = re.search(r"[\d.]+:(\d+)\s+[\d.*:]+\s+LISTENING", line)
                        if m:
                            ports.add(int(m.group(1)))
            else:
                out = subprocess.run(
                    ["ss", "-tlnp"], capture_output=True, text=True,
                    timeout=8).stdout
                for line in out.splitlines():
                    m = re.search(r":(\d+)\s", line)
                    if m:
                        ports.add(int(m.group(1)))
        except Exception as exc:
            _log(f"port monitor: {exc}")
        return ports

    def poll(self) -> Tuple[Set[int], Set[int]]:
        curr = self._get_listening_ports()
        with self._lock:
            new_ports    = curr - self._prev_ports
            closed_ports = self._prev_ports - curr
            self._prev_ports = curr
        return new_ports, closed_ports

    def check_unexpected(self, new_ports: Set[int]) -> List[MonitorAlert]:
        unexpected = new_ports - self.EXPECTED_PORTS
        return [
            MonitorAlert(
                alert_id=hashlib.sha256(
                    f"port_{p}{time.time()}".encode()).hexdigest()[:12],
                source="port",
                severity=SEVERITY_WARN,
                title=f"Unexpected new listener: port {p}",
                detail=f"Port {p} is now LISTENING — not in expected set",
                data={"port": p},
            )
            for p in unexpected
        ]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            ports = sorted(self._prev_ports)
        return {
            "listening_count": len(ports),
            "ports":           ports[:100],
            "unexpected":      sorted(self._prev_ports - self.EXPECTED_PORTS)[:20],
        }


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — DNS ACTIVITY MONITOR
# ══════════════════════════════════════════════════════════════════════════════

class DNSActivityMonitor:
    """
    Lightweight DNS resolver cache tracker.
    Probes known DNS servers for response time and integrity.
    Detects DNS poisoning (unexpected IP for known-good domains).
    """

    REFERENCE = {
        "google.com":    "142.250.",
        "github.com":    "140.82.",
        "cloudflare.com":"104.16.",
        "api.anthropic.com": "104.",
    }

    def __init__(self) -> None:
        self._resolved: Dict[str, str] = {}
        self._lock = threading.Lock()

    def resolve_check(self) -> List[MonitorAlert]:
        alerts = []
        for domain, expected_prefix in self.REFERENCE.items():
            try:
                ip = socket.gethostbyname(domain)
                with self._lock:
                    prev = self._resolved.get(domain)
                    self._resolved[domain] = ip
                if prev and prev != ip and not ip.startswith(expected_prefix):
                    alerts.append(MonitorAlert(
                        alert_id=hashlib.sha256(
                            f"dns_{domain}{time.time()}".encode()).hexdigest()[:12],
                        source="dns",
                        severity=SEVERITY_ALERT,
                        title=f"DNS change: {domain}",
                        detail=f"Resolved to {ip} (was {prev}) — possible poisoning",
                        data={"domain": domain, "ip": ip, "prev": prev},
                    ))
            except Exception:
                pass
        return alerts

    def dns_latency(self) -> Dict[str, float]:
        results: Dict[str, float] = {}
        for server in ["8.8.8.8", "1.1.1.1", "9.9.9.9"]:
            t0 = time.time()
            try:
                socket.create_connection((server, 53), timeout=2).close()
                results[server] = round((time.time() - t0) * 1000, 1)
            except Exception:
                results[server] = -1.0
        return results

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            resolved = dict(self._resolved)
        return {
            "resolved_domains": resolved,
            "dns_latency_ms":   self.dns_latency(),
        }


# ══════════════════════════════════════════════════════════════════════════════
# PART 6 — CHASE RINGQUIST IDENTITY MONITOR
# ══════════════════════════════════════════════════════════════════════════════

class ChaseRingquistMonitor:
    """
    Real-time monitor for Chase Allen Ringquist's RabbitOS identity stream.

    Aggregates:
    - EEG mesh node online status (RF carriers 10.23–10.28 GHz)
    - Biometric packet collection rate
    - Identity match score from IdentityMatchEngine
    - XRPL Bio-NFT ledger sequence (read-only, no TX)
    - Cold network node count (online/offline)
    - CloudTrail action velocity (actions/min)
    - Survival mode queue depth
    - Active rabbit_* module sessions
    - Defense alert count

    Security invariants enforced:
      shows_dna_root = FALSE — never retrieves or stores DNA root
      vault_location_hash only — no plaintext vault location
      TX_LICENSED = False — XRPL probe is read-only
    """

    TX_LICENSED = False

    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._trail_times: deque = deque(maxlen=1000)
        self._last_snapshot: Optional[IdentityStreamSnapshot] = None

    def _eeg_node_status(self) -> Tuple[int, int, List[MeshNodeStatus]]:
        """Returns (online_count, total_count, node_list)."""
        nodes: List[MeshNodeStatus] = []
        try:
            from rabbit_defense import EEG_NODE_MAP
            total  = len(EEG_NODE_MAP)
            online = 0
            for label, node in EEG_NODE_MAP.items():
                is_online = (time.time() - node.last_seen) < 300
                if is_online:
                    online += 1
                nodes.append(MeshNodeStatus(
                    node_id=node.mesh_node_id,
                    label=label,
                    carrier_ghz=node.carrier_freq_ghz,
                    online=is_online,
                    last_seen=node.last_seen,
                ))
            return online, total, nodes
        except Exception:
            pass

        # Fallback: probe carriers directly
        total  = len(MESH_CARRIERS)
        online = 0
        for label, ghz in MESH_CARRIERS.items():
            nodes.append(MeshNodeStatus(
                node_id=f"mesh_{label}",
                label=label,
                carrier_ghz=ghz,
                online=False,
                last_seen=0.0,
            ))
        return online, total, nodes

    def _biometric_rate(self) -> float:
        """Returns biometric packets per minute from medical module."""
        try:
            from rabbit_medical import MedicalDataStore
            store = MedicalDataStore()
            conn  = store._conn()
            row   = conn.execute(
                "SELECT COUNT(*) FROM biometric_packets "
                "WHERE ts > ?", (time.time() - 60,)).fetchone()
            conn.close()
            return float(row[0]) if row else 0.0
        except Exception:
            return 0.0

    def _identity_score(self) -> float:
        """Returns last known identity match score."""
        try:
            from rabbit_medical import IdentityMatchEngine
            engine = IdentityMatchEngine()
            result = engine.match({})
            return round(result.get("match_score", 0.0), 3)
        except Exception:
            return 0.0

    def _xrpl_ledger_seq(self) -> Tuple[bool, int]:
        """Read-only XRPL ledger sequence probe. No TX submitted."""
        assert self.TX_LICENSED is False
        assert shows_dna_root is False
        try:
            import ssl
            s = socket.create_connection(("s1.ripple.com", 6006), timeout=4)
            ws_key = __import__("base64").b64encode(
                __import__("os").urandom(16)).decode()
            shake = (
                "GET / HTTP/1.1\r\nHost: s1.ripple.com:6006\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\nUser-Agent: RabbitOS\r\n\r\n"
            ).encode()
            s.sendall(shake)
            resp = s.recv(512).decode(errors="replace")
            if "101 Switching" not in resp:
                s.close()
                return False, 0
            payload = json.dumps({"id": 1, "command": "server_info"}).encode()
            mask    = __import__("os").urandom(4)
            masked  = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
            frame   = bytes([0x81, 0x80 | len(payload)]) + mask + masked
            s.sendall(frame)
            data    = s.recv(1024)
            text    = data[6:].decode(errors="replace")[:400]
            info    = json.loads(text)
            seq     = (info.get("result", {})
                          .get("info", {})
                          .get("validated_ledger", {})
                          .get("seq", 0))
            s.close()
            return True, seq
        except Exception:
            return False, 0

    def _cold_network_status(self) -> Tuple[int, int]:
        """Returns (online_nodes, total_nodes) from cold network registry."""
        try:
            from rabbit_assistant import get_assistant
            reg = get_assistant().registry
            online = len(reg.get_online())
            total  = len(reg.to_dict())
            return online, total
        except Exception:
            return 0, 0

    def _trail_velocity(self) -> int:
        """Returns cloud trail actions in the last 60 seconds."""
        try:
            from rabbit_assistant import get_assistant
            now = time.time()
            rows = get_assistant().trail.query(limit=200)
            return sum(1 for r in rows
                       if now - r.get("ts", 0) <= 60)
        except Exception:
            return 0

    def _survival_queue_depth(self) -> int:
        """Returns number of tasks in the survival queue."""
        try:
            from rabbit_agent import get_survival_mode
            q = get_survival_mode().get_queue()
            return len(q)
        except Exception:
            try:
                db = _BASE / "rabbit_survival.db"
                if db.exists():
                    conn = sqlite3.connect(str(db), timeout=3)
                    row  = conn.execute(
                        "SELECT COUNT(*) FROM task_queue "
                        "WHERE status='pending'").fetchone()
                    conn.close()
                    return row[0] if row else 0
            except Exception:
                return 0

    def _active_modules(self) -> List[str]:
        """Returns list of rabbit_* modules that appear to be running."""
        active = []
        try:
            for mod in [
                "rabbit_defense", "rabbit_assistant",
                "rabbit_mcp", "rabbit_nettools",
                "rabbit_shell", "rabbit_medical",
            ]:
                if mod in sys.modules:
                    active.append(mod)
        except Exception:
            pass
        return active

    def _defense_alert_count(self) -> int:
        try:
            from rabbit_defense import DefenseOrchestrator
            orch = DefenseOrchestrator()
            findings = orch.backdoor_detector.full_scan("127.0.0.1") \
                if hasattr(orch, "backdoor_detector") else []
            return len(findings)
        except Exception:
            return 0

    def snapshot(self) -> IdentityStreamSnapshot:
        """Collect all identity/biometric streams into one snapshot."""
        eeg_online, eeg_total, _ = self._eeg_node_status()
        bio_rate    = self._biometric_rate()
        id_score    = self._identity_score()
        xrpl_reach, xrpl_seq = self._xrpl_ledger_seq()
        cold_on, cold_tot    = self._cold_network_status()
        trail_vel   = self._trail_velocity()
        surv_depth  = self._survival_queue_depth()
        active_mods = self._active_modules()

        snap = IdentityStreamSnapshot(
            twin_uuid=TWIN_UUID,
            twin_name=TWIN_NAME,
            timestamp=time.time(),
            eeg_nodes_online=eeg_online,
            eeg_nodes_total=eeg_total,
            biometric_rate=bio_rate,
            identity_score=id_score,
            xrpl_ledger_seq=xrpl_seq,
            xrpl_reachable=xrpl_reach,
            cold_nodes_online=cold_on,
            cold_nodes_total=cold_tot,
            trail_actions_1m=trail_vel,
            survival_queued=surv_depth,
            active_modules=active_mods,
            alerts=0,
            shows_dna_root=False,
        )
        with self._lock:
            self._last_snapshot = snap
        _log(f"[Identity] eeg={eeg_online}/{eeg_total} "
             f"bio={bio_rate:.1f}/min id={id_score:.2f} "
             f"xrpl={'ok' if xrpl_reach else 'offline'} "
             f"cold={cold_on}/{cold_tot}")
        return snap

    def last_snapshot(self) -> Optional[IdentityStreamSnapshot]:
        with self._lock:
            return self._last_snapshot

    def mesh_node_list(self) -> List[MeshNodeStatus]:
        _, _, nodes = self._eeg_node_status()
        return nodes


# ══════════════════════════════════════════════════════════════════════════════
# PART 7 — ALERT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AlertEngine:
    """
    Aggregates alerts from all monitor components.
    Persists to SQLite. Pushes to Supabase async.
    Supports threshold-based and anomaly-based triggering.
    """

    def __init__(self, supabase_url: str = "",
                 service_key: str = "") -> None:
        self._sup_url  = supabase_url
        self._sup_key  = service_key
        self._alerts:  deque = deque(maxlen=2000)
        self._lock     = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    source TEXT, severity TEXT, title TEXT,
                    detail TEXT, data TEXT, ts REAL, acked INTEGER DEFAULT 0
                )""")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def ingest(self, alerts: List[MonitorAlert]) -> None:
        if not alerts:
            return
        with self._lock:
            for a in alerts:
                self._alerts.append(a)
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=10)
            for a in alerts:
                conn.execute(
                    "INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?,?,?,?)",
                    (a.alert_id, a.source, a.severity, a.title,
                     a.detail[:500], json.dumps(a.data, default=str)[:1000],
                     a.ts, 0))
            conn.commit()
            conn.close()
        except Exception:
            pass
        if self._sup_url and self._sup_key:
            threading.Thread(
                target=self._push_supabase, args=(alerts,), daemon=True).start()

    def _push_supabase(self, alerts: List[MonitorAlert]) -> None:
        for a in alerts:
            try:
                url  = self._sup_url.rstrip("/") + "/rest/v1/monitor_alerts"
                data = json.dumps({
                    "alert_id":  a.alert_id,
                    "source":    a.source,
                    "severity":  a.severity,
                    "title":     a.title,
                    "detail":    a.detail[:400],
                    "ts":        a.ts,
                    "twin_id":   TWIN_UUID,
                }).encode()
                req = urllib.request.Request(
                    url, data=data, method="POST",
                    headers={
                        "Authorization": f"Bearer {self._sup_key}",
                        "apikey":        self._sup_key,
                        "Content-Type":  "application/json",
                        "Prefer":        "return=minimal",
                    })
                with urllib.request.urlopen(req, timeout=8):
                    pass
            except Exception:
                pass

    def check_identity_thresholds(
            self, snap: IdentityStreamSnapshot) -> List[MonitorAlert]:
        alerts: List[MonitorAlert] = []

        if snap.eeg_nodes_total > 0:
            eeg_pct = snap.eeg_nodes_online / snap.eeg_nodes_total
            if eeg_pct < 0.5:
                alerts.append(MonitorAlert(
                    alert_id=hashlib.sha256(
                        f"eeg_low{snap.timestamp}".encode()).hexdigest()[:12],
                    source="identity",
                    severity=SEVERITY_WARN,
                    title=f"EEG mesh degraded: {snap.eeg_nodes_online}/{snap.eeg_nodes_total} nodes",
                    detail="More than half of RabbitOS mesh EEG nodes are offline",
                    data={"online": snap.eeg_nodes_online,
                          "total": snap.eeg_nodes_total},
                ))

        if snap.identity_score > 0 and snap.identity_score < 0.75:
            alerts.append(MonitorAlert(
                alert_id=hashlib.sha256(
                    f"id_low{snap.timestamp}".encode()).hexdigest()[:12],
                source="identity",
                severity=SEVERITY_ALERT,
                title=f"Low identity match score: {snap.identity_score:.2f}",
                detail="Chase Ringquist identity confidence below 75%",
                data={"score": snap.identity_score},
            ))

        if not snap.xrpl_reachable:
            alerts.append(MonitorAlert(
                alert_id=hashlib.sha256(
                    f"xrpl_off{snap.timestamp}".encode()).hexdigest()[:12],
                source="identity",
                severity=SEVERITY_WARN,
                title="XRPL Bio-NFT anchor unreachable",
                detail="Cannot reach s1.ripple.com for ledger sync",
                data={},
            ))

        if snap.survival_queued > 50:
            alerts.append(MonitorAlert(
                alert_id=hashlib.sha256(
                    f"surv_q{snap.timestamp}".encode()).hexdigest()[:12],
                source="identity",
                severity=SEVERITY_WARN,
                title=f"Survival queue buildup: {snap.survival_queued} tasks",
                detail="Survival mode task queue is accumulating — possible offline state",
                data={"queued": snap.survival_queued},
            ))

        return alerts

    def get_active(self, severity: str = "",
                   limit: int = 50) -> List[Dict]:
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=5)
            if severity:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE acked=0 AND severity=? "
                    "ORDER BY ts DESC LIMIT ?", (severity, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE acked=0 "
                    "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
            desc = conn.execute("SELECT * FROM alerts LIMIT 0").description or []
            cols = [d[0] for d in desc]
            conn.close()
            return [dict(zip(cols, r)) for r in rows]
        except Exception:
            with self._lock:
                items = [a for a in self._alerts if not a.acked]
                if severity:
                    items = [a for a in items if a.severity == severity]
                return [asdict(a) for a in items[-limit:]]

    def ack_alert(self, alert_id: str) -> bool:
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=5)
            conn.execute("UPDATE alerts SET acked=1 WHERE alert_id=?", (alert_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        with self._lock:
            for a in self._alerts:
                if a.alert_id == alert_id:
                    a.acked = True
                    return True
        return False

    def stats(self) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=5)
            by_sev = dict(conn.execute(
                "SELECT severity, COUNT(*) FROM alerts "
                "WHERE acked=0 GROUP BY severity").fetchall())
            total  = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            conn.close()
        except Exception:
            by_sev, total = {}, 0
        return {
            "total_alerts":  total,
            "active_by_severity": by_sev,
            "critical": by_sev.get("critical", 0),
            "alert":    by_sev.get("alert", 0),
            "warn":     by_sev.get("warn", 0),
            "info":     by_sev.get("info", 0),
        }


# ══════════════════════════════════════════════════════════════════════════════
# PART 8 — LIVE MONITOR DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

class LiveMonitorDashboard:
    """
    Aggregates all monitor streams into a single polling background agent.
    Stores all events in SQLite. Provides a unified status view.
    """

    _instance: Optional["LiveMonitorDashboard"] = None
    _cls_lock  = threading.Lock()

    def __new__(cls) -> "LiveMonitorDashboard":
        with cls._cls_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instance = inst
        return cls._instance

    def __init__(self, supabase_url: str = "",
                 service_key: str = "") -> None:
        if self._initialized:
            return
        self._initialized = True

        self.conn_mon   = NetworkConnectionMonitor()
        self.arp_mon    = ARPTableMonitor()
        self.iface_mon  = InterfaceStatMonitor()
        self.port_mon   = PortActivityMonitor()
        self.dns_mon    = DNSActivityMonitor()
        self.chase_mon  = ChaseRingquistMonitor()
        self.alert_eng  = AlertEngine(supabase_url, service_key)

        self._running   = False
        self._cycle     = 0
        self._lock      = threading.Lock()
        self._last_full: Dict[str, Any] = {}
        self._init_db()
        _log("LiveMonitorDashboard initialized")

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_cycles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, cycle INTEGER,
                    connections INTEGER, arp_devices INTEGER,
                    new_conns INTEGER, new_devices INTEGER,
                    eeg_online INTEGER, identity_score REAL,
                    alerts_new INTEGER, detail TEXT
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS identity_stream (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, twin_uuid TEXT,
                    eeg_online INTEGER, eeg_total INTEGER,
                    biometric_rate REAL, identity_score REAL,
                    xrpl_seq INTEGER, xrpl_reachable INTEGER,
                    cold_online INTEGER, cold_total INTEGER,
                    trail_velocity INTEGER, survival_queued INTEGER
                )""")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def poll_once(self) -> Dict[str, Any]:
        """Run one full poll across all monitors. Returns unified snapshot."""
        self._cycle += 1
        t0 = time.time()
        all_alerts: List[MonitorAlert] = []

        # Network connections
        new_conns, closed_conns = self.conn_mon.poll()
        all_alerts += self.conn_mon.check_suspicious(new_conns)
        conn_snap = self.conn_mon.snapshot()

        # ARP table
        new_devs, gone_devs, changed_macs = self.arp_mon.poll()
        all_alerts += self.arp_mon.check_arp_spoof(changed_macs)
        arp_snap = self.arp_mon.snapshot()

        # Interface stats
        iface_delta = self.iface_mon.poll()
        iface_snap  = self.iface_mon.snapshot()

        # Port activity
        new_ports, closed_ports = self.port_mon.poll()
        all_alerts += self.port_mon.check_unexpected(new_ports)
        port_snap = self.port_mon.snapshot()

        # DNS
        all_alerts += self.dns_mon.resolve_check()
        dns_snap = self.dns_mon.snapshot()

        # Chase Ringquist identity stream
        identity_snap = self.chase_mon.snapshot()
        all_alerts += self.alert_eng.check_identity_thresholds(identity_snap)

        # Update alert count in identity snapshot
        identity_snap.alerts = len(all_alerts)

        # Ingest all alerts
        self.alert_eng.ingest(all_alerts)

        # Persist
        self._persist_cycle(
            conn_snap, arp_snap, new_conns, new_devs,
            identity_snap, all_alerts)

        elapsed = round(time.time() - t0, 2)
        result  = {
            "cycle":     self._cycle,
            "elapsed_s": elapsed,
            "ts":        time.time(),
            "network": {
                "connections": conn_snap,
                "arp":         arp_snap,
                "interfaces":  iface_snap,
                "ports":       port_snap,
                "dns":         dns_snap,
                "bandwidth":   iface_delta,
                "new_connections":   [asdict(c) for c in new_conns[:20]],
                "closed_connections":[asdict(c) for c in closed_conns[:10]],
                "new_devices":  [asdict(d) for d in new_devs],
                "gone_devices": [asdict(d) for d in gone_devs],
                "new_ports":    sorted(new_ports),
                "closed_ports": sorted(closed_ports),
            },
            "identity": asdict(identity_snap),
            "alerts": {
                "new_this_cycle": len(all_alerts),
                "stats": self.alert_eng.stats(),
                "recent": [asdict(a) for a in all_alerts[:10]],
            },
        }

        with self._lock:
            self._last_full = result

        if all_alerts:
            critical = [a for a in all_alerts
                        if a.severity == SEVERITY_CRITICAL]
            if critical:
                _log(f"[CRITICAL] {len(critical)} critical alerts: "
                     + "; ".join(a.title for a in critical[:3]))

        _log(f"[Monitor] Cycle {self._cycle}: "
             f"conns={conn_snap['total']}  "
             f"new_conns={len(new_conns)}  "
             f"new_devs={len(new_devs)}  "
             f"alerts={len(all_alerts)}  "
             f"id_score={identity_snap.identity_score:.2f}  "
             f"elapsed={elapsed}s")
        return result

    def _persist_cycle(self, conn_snap, arp_snap,
                       new_conns, new_devs,
                       identity_snap: IdentityStreamSnapshot,
                       alerts: List[MonitorAlert]) -> None:
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=10)
            conn.execute(
                "INSERT INTO monitor_cycles VALUES "
                "(NULL,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), self._cycle,
                 conn_snap.get("total", 0),
                 arp_snap.get("total_known", 0),
                 len(new_conns), len(new_devs),
                 identity_snap.eeg_nodes_online,
                 identity_snap.identity_score,
                 len(alerts),
                 json.dumps({"ports": conn_snap.get("by_state", {})},
                            default=str)[:500]))
            conn.execute(
                "INSERT INTO identity_stream VALUES "
                "(NULL,?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), TWIN_UUID,
                 identity_snap.eeg_nodes_online,
                 identity_snap.eeg_nodes_total,
                 identity_snap.biometric_rate,
                 identity_snap.identity_score,
                 identity_snap.xrpl_ledger_seq,
                 int(identity_snap.xrpl_reachable),
                 identity_snap.cold_nodes_online,
                 identity_snap.cold_nodes_total,
                 identity_snap.trail_actions_1m,
                 identity_snap.survival_queued))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def start(self, network_interval: float = 15.0,
              identity_interval: float = 60.0) -> None:
        if self._running:
            return
        self._running = True

        def _net_loop():
            while self._running:
                try:
                    self.poll_once()
                except Exception as exc:
                    _log(f"Monitor poll error: {exc}")
                time.sleep(network_interval)

        threading.Thread(target=_net_loop, daemon=True,
                         name="monitor_net").start()
        _log(f"LiveMonitorDashboard started "
             f"(net={network_interval}s id={identity_interval}s)")

    def stop(self) -> None:
        self._running = False

    def current(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._last_full) if self._last_full else {}

    def identity_history(self, limit: int = 100) -> List[Dict]:
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=5)
            rows = conn.execute(
                "SELECT ts, eeg_online, eeg_total, biometric_rate, "
                "identity_score, xrpl_seq, xrpl_reachable, cold_online, "
                "cold_total, trail_velocity, survival_queued "
                "FROM identity_stream ORDER BY ts DESC LIMIT ?",
                (limit,)).fetchall()
            conn.close()
            cols = ["ts", "eeg_online", "eeg_total", "biometric_rate",
                    "identity_score", "xrpl_seq", "xrpl_reachable",
                    "cold_online", "cold_total", "trail_velocity",
                    "survival_queued"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception:
            return []

    def network_history(self, limit: int = 100) -> List[Dict]:
        try:
            conn = sqlite3.connect(str(_MON_DB), timeout=5)
            rows = conn.execute(
                "SELECT ts, cycle, connections, arp_devices, "
                "new_conns, new_devices, alerts_new "
                "FROM monitor_cycles ORDER BY ts DESC LIMIT ?",
                (limit,)).fetchall()
            conn.close()
            cols = ["ts", "cycle", "connections", "arp_devices",
                    "new_conns", "new_devices", "alerts_new"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception:
            return []


def get_monitor(supabase_url: str = "",
                service_key: str = "") -> LiveMonitorDashboard:
    return LiveMonitorDashboard(supabase_url, service_key)


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR TOOLS + DISPATCHER
# ══════════════════════════════════════════════════════════════════════════════

MONITOR_TOOLS = [
    # ── Dashboard ─────────────────────────────────────────────────────────────
    {
        "name": "monitor_start",
        "description": (
            "Start the live network + identity monitor background agent. "
            "Polls network connections, ARP devices, ports, DNS, and "
            "Chase Ringquist identity stream continuously."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "network_interval": {"type": "integer",
                                      "description": "Poll interval seconds (default 15)"},
            },
            "required": [],
        },
    },
    {
        "name": "monitor_stop",
        "description": "Stop the live monitor background agent.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_current",
        "description": (
            "Get the most recent full monitor snapshot: all network activity, "
            "ARP devices, bandwidth, open ports, and Chase Ringquist identity stream."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_poll",
        "description": "Run one immediate monitor poll across all streams. Returns full snapshot.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ── Network ───────────────────────────────────────────────────────────────
    {
        "name": "monitor_connections",
        "description": "Get all current TCP/UDP connections with state, proto, local/remote, PID.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_arp_devices",
        "description": (
            "Get all LAN devices from ARP table: IP, MAC hash, interface, "
            "online/offline status. Detects new devices and ARP spoofing."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_bandwidth",
        "description": "Get per-interface bandwidth (bytes/s in and out) and state.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_open_ports",
        "description": "Get all currently LISTENING TCP/UDP ports on this machine.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_dns",
        "description": "Check DNS resolution for key domains. Detects cache poisoning and latency.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_network_history",
        "description": "Get historical network monitor cycles: connection counts, ARP devices, alert counts.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    # ── Chase Ringquist Identity ───────────────────────────────────────────────
    {
        "name": "monitor_identity_snapshot",
        "description": (
            "Get a full Chase Allen Ringquist identity stream snapshot: "
            "EEG mesh node status, biometric packet rate, identity match score, "
            "XRPL Bio-NFT ledger sequence, cold network nodes, cloud trail velocity, "
            "survival queue depth, active modules. shows_dna_root=FALSE enforced."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_mesh_nodes",
        "description": (
            "Get all 47-node RabbitOS EEG mesh node statuses: "
            "carrier frequency (GHz), online/offline, last seen, electrode label."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_xrpl_status",
        "description": (
            "Check XRPL Bio-NFT anchor node reachability and current ledger sequence. "
            "Read-only probe — TX_LICENSED=False, no transactions submitted."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_biometric_rate",
        "description": "Get current biometric packet collection rate (packets/minute) from rabbit_medical.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_identity_score",
        "description": (
            "Get Chase Ringquist's current identity match score (0.0–1.0) "
            "from IdentityMatchEngine (DNA 30%, EEG 25%, HRV 15%, GSR 10%, gait 10%, "
            "thermal 5%, net_tokens 5%)."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_identity_history",
        "description": "Get historical identity stream records: score, EEG, biometric, XRPL, cold nodes.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "monitor_cold_network",
        "description": "Get online/offline status of all cold network nodes registered to Chase's mesh.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_trail_velocity",
        "description": "Get cloud trail action rate: actions per minute across all rabbit_* agents.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_survival_queue",
        "description": "Get current survival mode task queue depth (pending tasks while offline).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ── Alerts ────────────────────────────────────────────────────────────────
    {
        "name": "monitor_alerts",
        "description": "Get active (unacknowledged) monitor alerts. Filter by severity: info/warn/alert/critical.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string",
                             "enum": ["info", "warn", "alert", "critical", ""]},
                "limit":    {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "monitor_alert_stats",
        "description": "Get alert count summary by severity.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_ack_alert",
        "description": "Acknowledge (dismiss) a monitor alert by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"alert_id": {"type": "string"}},
            "required": ["alert_id"],
        },
    },
    # ── Specific checks ───────────────────────────────────────────────────────
    {
        "name": "monitor_check_arp_spoof",
        "description": "Run ARP table poll and check for MAC address changes (ARP spoofing / MITM).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_check_suspicious_conns",
        "description": "Poll connections and flag any connecting to known suspicious/backdoor ports.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_check_new_listeners",
        "description": "Check for unexpected new LISTENING ports not in the expected set.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_interface_stats",
        "description": "Get full interface statistics: bytes, packets, errors, state for all adapters.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_summary",
        "description": (
            "Get a high-level monitor summary: network health, "
            "Chase Ringquist identity score, active alerts, "
            "mesh nodes online, XRPL status."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "monitor_full_report",
        "description": (
            "Run an immediate poll and return the complete monitor state: "
            "all network activity + identity stream + all active alerts."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def dispatch_monitor_tool(name: str, inputs: Dict,
                           supabase_url: str = "",
                           service_key: str = "") -> Any:
    mon = get_monitor(supabase_url, service_key)

    if name == "monitor_start":
        mon.start(network_interval=inputs.get("network_interval", 15))
        return {"started": True,
                "interval": inputs.get("network_interval", 15)}

    elif name == "monitor_stop":
        mon.stop()
        return {"stopped": True}

    elif name == "monitor_current":
        c = mon.current()
        return c if c else {"note": "No data yet — run monitor_poll first"}

    elif name == "monitor_poll":
        return mon.poll_once()

    elif name == "monitor_connections":
        return mon.conn_mon.snapshot()

    elif name == "monitor_arp_devices":
        return mon.arp_mon.snapshot()

    elif name == "monitor_bandwidth":
        return mon.iface_mon.poll()

    elif name == "monitor_open_ports":
        return mon.port_mon.snapshot()

    elif name == "monitor_dns":
        return mon.dns_mon.snapshot()

    elif name == "monitor_network_history":
        return mon.network_history(inputs.get("limit", 100))

    elif name == "monitor_identity_snapshot":
        snap = mon.chase_mon.snapshot()
        return asdict(snap)

    elif name == "monitor_mesh_nodes":
        nodes = mon.chase_mon.mesh_node_list()
        return [asdict(n) for n in nodes]

    elif name == "monitor_xrpl_status":
        reachable, seq = mon.chase_mon._xrpl_ledger_seq()
        return {
            "reachable":    reachable,
            "ledger_seq":   seq,
            "xrpl_host":    "s1.ripple.com",
            "shows_dna_root": False,
            "tx_licensed":  False,
        }

    elif name == "monitor_biometric_rate":
        rate = mon.chase_mon._biometric_rate()
        return {"biometric_packets_per_min": rate,
                "twin_uuid": TWIN_UUID}

    elif name == "monitor_identity_score":
        score = mon.chase_mon._identity_score()
        return {"identity_score": score,
                "twin_uuid": TWIN_UUID,
                "twin_name": TWIN_NAME,
                "shows_dna_root": False}

    elif name == "monitor_identity_history":
        return mon.identity_history(inputs.get("limit", 100))

    elif name == "monitor_cold_network":
        online, total = mon.chase_mon._cold_network_status()
        try:
            from rabbit_assistant import get_assistant
            nodes = get_assistant().registry.to_dict()
        except Exception:
            nodes = []
        return {"online": online, "total": total, "nodes": nodes[:30]}

    elif name == "monitor_trail_velocity":
        vel = mon.chase_mon._trail_velocity()
        return {"trail_actions_per_min": vel,
                "twin_uuid": TWIN_UUID}

    elif name == "monitor_survival_queue":
        depth = mon.chase_mon._survival_queue_depth()
        return {"survival_queued": depth,
                "twin_uuid": TWIN_UUID}

    elif name == "monitor_alerts":
        return mon.alert_eng.get_active(
            severity=inputs.get("severity", ""),
            limit=inputs.get("limit", 50))

    elif name == "monitor_alert_stats":
        return mon.alert_eng.stats()

    elif name == "monitor_ack_alert":
        ok = mon.alert_eng.ack_alert(inputs["alert_id"])
        return {"acked": ok, "alert_id": inputs["alert_id"]}

    elif name == "monitor_check_arp_spoof":
        new, gone, changed = mon.arp_mon.poll()
        alerts = mon.arp_mon.check_arp_spoof(changed)
        mon.alert_eng.ingest(alerts)
        return {
            "new_devices":     [asdict(d) for d in new],
            "gone_devices":    [asdict(d) for d in gone],
            "changed_macs":    [asdict(d) for d in changed],
            "spoof_alerts":    [asdict(a) for a in alerts],
        }

    elif name == "monitor_check_suspicious_conns":
        new, _ = mon.conn_mon.poll()
        alerts  = mon.conn_mon.check_suspicious(new)
        mon.alert_eng.ingest(alerts)
        return {
            "new_connections": [asdict(c) for c in new[:30]],
            "suspicious":      [asdict(a) for a in alerts],
        }

    elif name == "monitor_check_new_listeners":
        new_ports, closed_ports = mon.port_mon.poll()
        alerts = mon.port_mon.check_unexpected(new_ports)
        mon.alert_eng.ingest(alerts)
        return {
            "new_ports":    sorted(new_ports),
            "closed_ports": sorted(closed_ports),
            "unexpected":   [asdict(a) for a in alerts],
        }

    elif name == "monitor_interface_stats":
        return mon.iface_mon.snapshot()

    elif name == "monitor_summary":
        snap = mon.chase_mon.last_snapshot()
        if snap is None:
            snap = mon.chase_mon.snapshot()
        alert_stats = mon.alert_eng.stats()
        return {
            "twin_name":      TWIN_NAME,
            "twin_uuid":      TWIN_UUID,
            "identity_score": snap.identity_score,
            "eeg_mesh":       f"{snap.eeg_nodes_online}/{snap.eeg_nodes_total}",
            "xrpl":           "ok" if snap.xrpl_reachable else "offline",
            "xrpl_ledger":    snap.xrpl_ledger_seq,
            "cold_nodes":     f"{snap.cold_nodes_online}/{snap.cold_nodes_total}",
            "biometric_rate": snap.biometric_rate,
            "survival_queue": snap.survival_queued,
            "trail_velocity": snap.trail_actions_1m,
            "active_modules": snap.active_modules,
            "alerts_critical":alert_stats.get("critical", 0),
            "alerts_active":  alert_stats.get("alert", 0),
            "connections":    mon.conn_mon.snapshot().get("total", 0),
            "arp_devices":    mon.arp_mon.snapshot().get("online", 0),
            "shows_dna_root": False,
        }

    elif name == "monitor_full_report":
        result = mon.poll_once()
        return result

    else:
        return {"error": f"Unknown monitor tool: {name}"}


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse, pprint

    p = argparse.ArgumentParser(description="RabbitOS Live Monitor")
    p.add_argument("--poll",      action="store_true", help="Run one monitor poll")
    p.add_argument("--summary",   action="store_true", help="Show summary")
    p.add_argument("--identity",  action="store_true", help="Show Chase identity snapshot")
    p.add_argument("--mesh",      action="store_true", help="Show mesh node status")
    p.add_argument("--network",   action="store_true", help="Show network connections + ARP")
    p.add_argument("--alerts",    action="store_true", help="Show active alerts")
    p.add_argument("--ports",     action="store_true", help="Show open ports")
    p.add_argument("--dns",       action="store_true", help="Check DNS health")
    p.add_argument("--xrpl",      action="store_true", help="Check XRPL ledger")
    p.add_argument("--daemon",    action="store_true", help="Run as daemon")
    p.add_argument("--interval",  type=int, default=15)
    args = p.parse_args()

    svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    url = os.environ.get("SUPABASE_URL", "")
    mon = get_monitor(url, svc)

    if args.poll:
        pprint.pprint(mon.poll_once())
    elif args.summary:
        pprint.pprint(dispatch_monitor_tool("monitor_summary", {}, url, svc))
    elif args.identity:
        snap = mon.chase_mon.snapshot()
        print(f"\n=== Chase Allen Ringquist Identity Stream ===")
        print(f"  UUID:          {snap.twin_uuid}")
        print(f"  EEG Mesh:      {snap.eeg_nodes_online}/{snap.eeg_nodes_total} nodes online")
        print(f"  Biometric:     {snap.biometric_rate:.1f} packets/min")
        print(f"  ID Score:      {snap.identity_score:.3f}")
        print(f"  XRPL:          {'online' if snap.xrpl_reachable else 'offline'} "
              f"(ledger #{snap.xrpl_ledger_seq})")
        print(f"  Cold Nodes:    {snap.cold_nodes_online}/{snap.cold_nodes_total}")
        print(f"  Trail Vel:     {snap.trail_actions_1m}/min")
        print(f"  Survival Q:    {snap.survival_queued}")
        print(f"  Active Mods:   {', '.join(snap.active_modules) or 'none'}")
        print(f"  shows_dna_root: {snap.shows_dna_root}")
    elif args.mesh:
        nodes = mon.chase_mon.mesh_node_list()
        print(f"\n=== RabbitOS Mesh Nodes ({len(nodes)}) ===")
        for n in nodes:
            sym = "[ON]" if n.online else "[--]"
            print(f"  {sym} {n.label:12s} {n.carrier_ghz:.3f} GHz  "
                  f"id={n.node_id[:8]}")
    elif args.network:
        new, _, _ = mon.arp_mon.poll()
        snap = mon.conn_mon.snapshot()
        arp  = mon.arp_mon.snapshot()
        print(f"\nConnections: {snap['total']}  "
              f"By state: {snap['by_state']}")
        print(f"ARP devices: {arp['online']} online / "
              f"{arp['offline']} offline")
        for dev in arp["devices"][:15]:
            sym = "[ON]" if dev["online"] else "[--]"
            print(f"  {sym} {dev['ip']:16s}  "
                  f"mac={dev['mac_hash'][:12]}  {dev['iface']}")
    elif args.alerts:
        stats = mon.alert_eng.stats()
        print(f"\nAlerts — Critical:{stats['critical']}  "
              f"Alert:{stats['alert']}  Warn:{stats['warn']}")
        for a in mon.alert_eng.get_active(limit=20):
            print(f"  [{a['severity'].upper():8s}] {a['source']:12s} "
                  f"{a['title'][:60]}")
    elif args.ports:
        snap = mon.port_mon.snapshot()
        print(f"\nListening: {snap['listening_count']} ports")
        print(f"Unexpected: {snap['unexpected']}")
    elif args.dns:
        snap = mon.dns_mon.snapshot()
        print(f"\nDNS resolved: {snap['resolved_domains']}")
        print(f"Latency (ms): {snap['dns_latency_ms']}")
    elif args.xrpl:
        r = dispatch_monitor_tool("monitor_xrpl_status", {}, url, svc)
        print(f"\nXRPL: {'online' if r['reachable'] else 'offline'}  "
              f"ledger=#{r['ledger_seq']}")
    elif args.daemon:
        mon.start(network_interval=args.interval)
        print(f"[Monitor] Daemon running (interval={args.interval}s). Ctrl+C to stop.")
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            mon.stop()
            print("\n[Monitor] Stopped.")
    else:
        p.print_help()
