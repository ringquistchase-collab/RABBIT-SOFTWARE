#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RabbitOS Soul — Network Survival Engine
========================================
The network IS the code. Hardware is the interpreter. This process never dies.

Concepts
--------
  Signal     Raw network I/O — TCP bytes, UDP datagrams, RF IQ, ARP replies,
             ICMP pings — treated as the primary language of the system.
             Whatever hardware is present becomes the interpreter.

  Emotion    Network metrics mapped to internal drive states that shape
             crawling behaviour:
               latency    -> mood      (low=excited, high=anxious)
               loss_rate  -> stress    (drives faster mutation)
               positions  -> security  (more anchors = calmer probing)
               success_rt -> hope      (high=keep going, low=try harder)
               offline    -> hunger    (triggers aggressive LAN scan)

  Survival   The process watches itself. Every thread has a guardian.
             State is flushed to disk every 10 s so a cold restart
             resumes where it left off. On Windows a .bat watchdog
             restarts the process if it exits.

  Bridge     Online -> Offline -> Seeking -> Online
             When internet disappears the engine shifts to LAN/localhost,
             discovers any reachable node, and tries to tunnel back online
             through it (HTTP proxy, SOCKS, SSH forward).

  Polyglot   Executes signal fragments in whatever runtime is available:
             Python3, bash/sh, node.js, PowerShell — whichever answers first.
             The network response decides the language, not the programmer.
"""

import os
import sys
import json
import time
import uuid
import socket
import struct
import hashlib
import shutil
import pickle
import random
import threading
import subprocess
import ipaddress
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from collections import deque
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent))

# =============================================================================
# HANDSHAKE ENERGY SYSTEM
# =============================================================================
# Every protocol handshake is a unit of energy.
# A completed handshake = information extracted + charge gained.
# A failed handshake    = charge spent with nothing returned.
# The energy budget governs how aggressively the soul probes.
# =============================================================================

@dataclass
class HandshakeResult:
    protocol:    str          # tcp | tls | ssh | http | icmp | udp
    host:        str
    port:        int
    success:     bool
    latency_ms:  float
    energy_gain: float        # how much charge this handshake returned
    info:        Dict         # extracted metadata (OS hint, banner, headers, etc.)
    timestamp:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HandshakeCollector:
    """
    Performs protocol handshakes and converts each one into energy.
    The richer the handshake, the more energy it provides.

    Energy table:
      ICMP echo reply      +0.05  (alive signal — minimal info)
      TCP SYN-ACK          +0.10  (port open — OS window hint)
      HTTP OPTIONS/HEAD    +0.20  (headers reveal server stack)
      TLS ClientHello resp +0.25  (cert + cipher = fingerprint)
      SSH banner           +0.30  (version + OS)
      Full SSH auth        +0.50  (shell access = maximum info)
      Any failure          -0.03  (energy spent, nothing gained)
    """

    ENERGY = {
        "icmp":     0.05,
        "tcp":      0.10,
        "http":     0.20,
        "tls":      0.25,
        "ssh":      0.30,
        "ssh_auth": 0.50,
        "fail":    -0.03,
    }

    def __init__(self):
        self._results: deque = deque(maxlen=200)
        self._charge: float  = 1.0   # starts fully charged
        self._lock           = threading.Lock()

    @property
    def charge(self) -> float:
        with self._lock:
            return round(self._charge, 3)

    def _add_energy(self, delta: float):
        with self._lock:
            self._charge = max(0.0, min(2.0, self._charge + delta))

    def handshake_tcp(self, host: str, port: int,
                      timeout: float = 2.0) -> HandshakeResult:
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            # Try to grab any spontaneous banner
            s.settimeout(0.3)
            try:
                banner = s.recv(256)
            except Exception:
                banner = b""
            s.close()
            lat  = (time.time() - t0) * 1000
            info = {"banner": banner.decode("utf-8", errors="replace").strip()[:80]}
            gain = self.ENERGY["tcp"] + (0.1 if info["banner"] else 0.0)
            self._add_energy(gain)
            r = HandshakeResult("tcp", host, port, True, lat, gain, info)
        except Exception:
            lat  = (time.time() - t0) * 1000
            self._add_energy(self.ENERGY["fail"])
            r = HandshakeResult("tcp", host, port, False, lat, self.ENERGY["fail"], {})
        with self._lock:
            self._results.appendleft(r)
        return r

    def handshake_ssh(self, host: str, port: int = 22,
                      timeout: float = 3.0) -> HandshakeResult:
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            banner = s.recv(256).decode("utf-8", errors="replace").strip()
            s.close()
            lat  = (time.time() - t0) * 1000
            info = {
                "banner":   banner[:80],
                "version":  banner.split("_")[1][:20] if "_" in banner else "",
                "os_hint":  ("Ubuntu" if "ubuntu" in banner.lower() else
                             "Kali"   if "kali"   in banner.lower() else
                             "Debian" if "debian" in banner.lower() else "unknown"),
            }
            gain = self.ENERGY["ssh"] if "SSH" in banner else self.ENERGY["tcp"]
            self._add_energy(gain)
            r = HandshakeResult("ssh", host, port, True, lat, gain, info)
        except Exception:
            lat  = (time.time() - t0) * 1000
            self._add_energy(self.ENERGY["fail"])
            r = HandshakeResult("ssh", host, port, False, lat, self.ENERGY["fail"], {})
        with self._lock:
            self._results.appendleft(r)
        return r

    def handshake_http(self, host: str, port: int = 80,
                       tls: bool = False, timeout: float = 4.0) -> HandshakeResult:
        t0  = time.time()
        url = f"{'https' if tls else 'http'}://{host}:{port}/"
        try:
            import ssl as _ssl
            ctx = _ssl.create_default_context() if tls else None
            if ctx:
                ctx.check_hostname = False
                ctx.verify_mode    = _ssl.CERT_NONE
            req = urllib.request.Request(
                url, method="HEAD",
                headers={"User-Agent": "RabbitOS-Soul/1.0"}
            )
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ctx) if tls else
                urllib.request.HTTPHandler()
            )
            resp   = opener.open(req, timeout=timeout)
            headers= dict(resp.headers)
            lat    = (time.time() - t0) * 1000
            info   = {
                "server":        headers.get("Server",       ""),
                "x_powered_by":  headers.get("X-Powered-By", ""),
                "content_type":  headers.get("Content-Type", ""),
                "status":        resp.status,
                "twin_hint":     TWIN_NAME.lower() in str(headers).lower(),
            }
            proto = "tls" if tls else "http"
            gain  = self.ENERGY[proto]
            if info["twin_hint"]:
                gain += 0.3   # bonus energy if Chase's data detected
            self._add_energy(gain)
            r = HandshakeResult(proto, host, port, True, lat, gain, info)
        except Exception as e:
            lat  = (time.time() - t0) * 1000
            self._add_energy(self.ENERGY["fail"])
            r = HandshakeResult("http", host, port, False, lat,
                                self.ENERGY["fail"], {"error": str(e)[:60]})
        with self._lock:
            self._results.appendleft(r)
        return r

    def handshake_icmp(self, host: str, timeout: float = 1.5) -> HandshakeResult:
        t0 = time.time()
        try:
            s = socket.create_connection((host, 80), timeout=timeout)
            s.close()
            lat  = (time.time() - t0) * 1000
            gain = self.ENERGY["icmp"]
            self._add_energy(gain)
            r = HandshakeResult("icmp", host, 80, True, lat, gain,
                                {"method": "connect_probe"})
        except Exception:
            lat  = (time.time() - t0) * 1000
            self._add_energy(self.ENERGY["fail"])
            r = HandshakeResult("icmp", host, 0, False, lat, self.ENERGY["fail"], {})
        with self._lock:
            self._results.appendleft(r)
        return r

    def sweep_host(self, host: str,
                   ports: List[int] = None) -> List[HandshakeResult]:
        """
        Run all handshake types against a host in one sweep.
        Returns all results — each one adds or subtracts energy.
        """
        ports   = ports or [22, 80, 443, 8765, 5432, 8080, 3000]
        results = []
        # ICMP first — cheapest
        results.append(self.handshake_icmp(host))
        if not results[-1].success:
            return results   # host unreachable — save energy

        for port in ports:
            if port == 22:
                results.append(self.handshake_ssh(host, port))
            elif port in (443, 8443):
                results.append(self.handshake_http(host, port, tls=True))
            else:
                results.append(self.handshake_tcp(host, port))
            # Stop if energy gets too low
            if self.charge < 0.2:
                print(f"  [Energy] Low charge ({self.charge:.2f}) — stopping sweep")
                break

        return results

    def recent_results(self, n: int = 20) -> List[Dict]:
        with self._lock:
            return [
                {
                    "ts":       r.timestamp[:19],
                    "proto":    r.protocol,
                    "host":     r.host,
                    "port":     r.port,
                    "ok":       r.success,
                    "lat_ms":   round(r.latency_ms, 1),
                    "energy":   round(r.energy_gain, 3),
                    "info":     r.info,
                }
                for r in list(self._results)[:n]
            ]

    def charge_bar(self) -> str:
        filled = int(self.charge * 10)
        return "[" + "#" * filled + "." * (20 - filled) + f"] {self.charge:.2f}"


# =============================================================================
# CONSTANTS
# =============================================================================

TWIN_UUID    = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME    = "Chase Allen Ringquist"
STATE_FILE   = Path(__file__).parent / "rabbit_soul.state"
WATCHDOG_BAT = Path(__file__).parent / "rabbit_watchdog.bat"
PING_HOSTS   = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]          # online check
LAN_SCAN_TTL = 60                                            # re-scan LAN every N s
SUPABASE_URL = "https://ludxbakxpmdqhfgdenwp.supabase.co"
REST_URL     = f"{SUPABASE_URL}/rest/v1"


# =============================================================================
# NETWORK STATE
# =============================================================================

class NetState(Enum):
    ONLINE   = "online"     # internet reachable
    DEGRADED = "degraded"   # partial (DNS ok, but target unreachable)
    OFFLINE  = "offline"    # no internet
    SEEKING  = "seeking"    # scanning LAN for a path back online
    TUNNEL   = "tunnel"     # online via SSH/proxy tunnel through LAN node


# =============================================================================
# EMOTIONS — network metrics -> internal drive states
# =============================================================================

@dataclass
class Emotion:
    mood:      float = 0.7    # 0=anxious  1=excited
    stress:    float = 0.0    # 0=calm     1=overwhelmed
    security:  float = 0.5    # 0=exposed  1=anchored
    hope:      float = 0.7    # 0=despair  1=optimistic
    hunger:    float = 0.0    # 0=fed      1=starving (no network)
    energy:    float = 1.0    # 0=exhausted 1=full

    def update(self, latency_ms: float, loss_rate: float,
               positions: int, success_rate: float, online: bool):
        # mood: fast responses feel good
        self.mood = max(0.0, min(1.0, 1.0 - (latency_ms / 1000.0)))
        # stress: failures pile up
        self.stress = max(0.0, min(1.0, loss_rate))
        # security: more positions = safer
        self.security = min(1.0, positions / 10.0)
        # hope: recent successes
        self.hope = max(0.1, success_rate)
        # hunger: no internet = hungry
        self.hunger = 0.0 if online else min(1.0, self.hunger + 0.05)
        # energy drains with stress, recovers with successes
        self.energy = max(0.1, min(1.0, self.energy - (loss_rate * 0.1)
                                        + (success_rate * 0.15)))

    def probe_interval(self) -> float:
        """How long to wait between probes — emotion-driven pacing."""
        base = 0.5
        if self.hunger > 0.5:   base *= 0.3   # hungry = probe faster
        if self.stress  > 0.7:  base *= 0.5   # stressed = faster mutation
        if self.mood    < 0.3:  base *= 2.0   # anxious = slow down
        if self.energy  < 0.3:  base *= 3.0   # exhausted = rest
        return max(0.05, base + random.uniform(-0.1, 0.1))

    def mutation_bias(self) -> float:
        """How aggressively to mutate failing methods."""
        return min(1.0, self.stress + (1.0 - self.hope) + self.hunger * 0.5)

    def describe(self) -> str:
        words = []
        if self.mood     > 0.7: words.append("EXCITED")
        elif self.mood   < 0.3: words.append("ANXIOUS")
        if self.hunger   > 0.5: words.append("HUNGRY")
        if self.stress   > 0.6: words.append("STRESSED")
        if self.security > 0.8: words.append("SECURE")
        if self.energy   < 0.3: words.append("TIRED")
        if self.hope     > 0.8: words.append("HOPEFUL")
        return " | ".join(words) if words else "NEUTRAL"


# =============================================================================
# SIGNAL INTERPRETER — hardware-aware raw signal reader
# =============================================================================

class SignalInterpreter:
    """
    Reads raw signals from whatever hardware is present and converts them
    to structured tokens. The hardware IS the interpreter — no fixed protocol.

    Sources (auto-detected):
      NIC       — raw ethernet frames (Scapy or raw socket)
      HackRF    — IQ samples at mesh frequencies
      ICMP      — ping latency as signal amplitude
      Serial    — USB-serial SDR nodes
      Loopback  — localhost as offline signal source
    """

    def __init__(self):
        self._sources = self._detect_sources()
        self._buf     = deque(maxlen=512)
        self._lock    = threading.Lock()
        print(f"[Signal] Sources: {self._sources}")

    def _detect_sources(self) -> List[str]:
        sources = ["loopback"]          # always available
        # ICMP ping
        try:
            socket.setdefaulttimeout(1)
            socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            sources.append("icmp_raw")
        except Exception:
            sources.append("icmp_connect")  # fallback: connect-based ping

        # HackRF
        try:
            import hackrf
            sources.append("hackrf")
        except ImportError:
            pass

        # Scapy
        try:
            from scapy.all import conf
            sources.append("scapy_nic")
        except ImportError:
            pass

        return sources

    def ping_latency(self, host: str, timeout: float = 1.0) -> Optional[float]:
        """Return RTT in ms, or None if unreachable."""
        t0 = time.time()
        try:
            s = socket.create_connection((host, 80), timeout=timeout)
            s.close()
            return (time.time() - t0) * 1000
        except Exception:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((host, 53))
                s.close()
                return (time.time() - t0) * 1000
            except Exception:
                return None

    def read_signal(self) -> Dict:
        """
        Read one signal sample from the best available source.
        Returns a dict that can drive emotional updates.
        """
        # ICMP latency from a random PING_HOST
        host    = random.choice(PING_HOSTS)
        latency = self.ping_latency(host)

        sample = {
            "ts":          datetime.now(timezone.utc).isoformat(),
            "source":      "icmp_connect",
            "host":        host,
            "latency_ms":  latency if latency is not None else 9999,
            "reachable":   latency is not None,
            "raw_hash":    hashlib.sha256(f"{host}{latency}{time.time()}".encode()).hexdigest()[:16],
        }

        with self._lock:
            self._buf.appendleft(sample)
        return sample

    def recent_signal_stats(self, n: int = 20) -> Dict:
        with self._lock:
            recent = list(self._buf)[:n]
        if not recent:
            return {"latency_avg": 9999, "loss_rate": 1.0, "online": False}
        reachable = [s for s in recent if s["reachable"]]
        latencies = [s["latency_ms"] for s in reachable]
        return {
            "latency_avg": sum(latencies) / len(latencies) if latencies else 9999,
            "loss_rate":   1.0 - (len(reachable) / len(recent)),
            "online":      len(reachable) > 0,
            "samples":     len(recent),
        }


# =============================================================================
# POLYGLOT EXECUTOR — runs code in whatever runtime is available
# =============================================================================

class PolyglotExecutor:
    """
    Discovers available language runtimes on this machine and the network.
    Executes fragments in whichever runtime answers fastest.
    The network response decides the language.
    """

    RUNTIMES = {
        "python3":    ["python3", "--version"],
        "python":     ["python",  "--version"],
        "node":       ["node",    "--version"],
        "bash":       ["bash",    "--version"],
        "powershell": ["powershell", "-Command", "$PSVersionTable.PSVersion"],
        "sh":         ["sh",      "--version"],
        "ruby":       ["ruby",    "--version"],
        "perl":       ["perl",    "--version"],
        "lua":        ["lua",     "-v"],
    }

    def __init__(self):
        self._available = self._scan()

    def _scan(self) -> Dict[str, str]:
        found = {}
        for lang, check_cmd in self.RUNTIMES.items():
            exe = check_cmd[0]
            if shutil.which(exe):
                try:
                    out = subprocess.check_output(
                        check_cmd, timeout=3,
                        stderr=subprocess.STDOUT, text=True
                    ).strip().splitlines()[0][:60]
                    found[lang] = out
                except Exception:
                    pass
        print(f"[Polyglot] Runtimes: {list(found.keys())}")
        return found

    def exec_fragment(self, code: str, lang: str = None,
                      timeout: int = 10) -> Dict:
        """
        Execute a code fragment. If lang is None, picks the best available.
        Returns {"stdout": ..., "stderr": ..., "lang": ..., "exit_code": ...}
        """
        if lang and lang not in self._available:
            lang = None
        if not lang:
            preferred = ["python3", "python", "bash", "sh", "powershell"]
            lang = next((l for l in preferred if l in self._available), None)
        if not lang:
            return {"error": "no runtime available", "lang": None}

        runners = {
            "python3":    ["python3",    "-c", code],
            "python":     ["python",     "-c", code],
            "node":       ["node",       "-e", code],
            "bash":       ["bash",       "-c", code],
            "sh":         ["sh",         "-c", code],
            "powershell": ["powershell", "-Command", code],
            "ruby":       ["ruby",       "-e", code],
            "perl":       ["perl",       "-e", code],
        }
        cmd = runners.get(lang)
        if not cmd:
            return {"error": f"no runner for {lang}"}

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return {
                "lang":      lang,
                "stdout":    result.stdout[:1000],
                "stderr":    result.stderr[:500],
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"lang": lang, "error": "timeout"}
        except Exception as e:
            return {"lang": lang, "error": str(e)}

    def available(self) -> Dict[str, str]:
        return dict(self._available)


# =============================================================================
# PERSISTENCE — state survives process restart
# =============================================================================

class PersistentState:
    """
    Flushes soul state to disk. On restart, resumes from last checkpoint.
    """

    def __init__(self, path: Path = STATE_FILE):
        self.path  = path
        self._lock = threading.Lock()

    def save(self, data: Dict):
        with self._lock:
            try:
                tmp = self.path.with_suffix(".tmp")
                with open(tmp, "wb") as f:
                    pickle.dump(data, f)
                tmp.replace(self.path)
            except Exception as e:
                print(f"[State] Save failed: {e}")

    def load(self) -> Dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return {}

    def clear(self):
        if self.path.exists():
            self.path.unlink()


# =============================================================================
# WATCHDOG — writes a bat file that restarts the process if it exits
# =============================================================================

def write_watchdog(script: Path = Path(__file__), bat: Path = WATCHDOG_BAT):
    """
    Write a Windows batch file that loops forever, restarting the soul if it dies.
    Run rabbit_watchdog.bat once; it keeps the soul alive indefinitely.
    """
    exe = sys.executable
    content = f"""@echo off
:loop
echo [Watchdog] Starting RabbitOS Soul...
"{exe}" "{script}" --run
echo [Watchdog] Soul exited — restarting in 3s...
timeout /t 3 /nobreak >nul
goto loop
"""
    with open(bat, "w") as f:
        f.write(content)
    print(f"[Watchdog] Written: {bat}")
    return bat


# =============================================================================
# GUARDIAN — restarts a thread if it dies
# =============================================================================

def guardian(name: str, target: Callable, interval: float = 2.0,
             stop_event: threading.Event = None) -> threading.Thread:
    """Wrap a function in a guardian thread that restarts it on any exception."""
    def _run():
        while True:
            if stop_event and stop_event.is_set():
                break
            try:
                target()
            except Exception as e:
                print(f"[Guardian] {name} crashed: {e} — restarting in {interval}s")
            time.sleep(interval)
    t = threading.Thread(target=_run, name=f"guardian:{name}", daemon=True)
    t.start()
    return t


# =============================================================================
# SOUL — the never-dying orchestrator
# =============================================================================

class RabbitSoul:
    """
    The always-alive intelligence core.
    Uses network signals as emotions. Never stops. Bridges online/offline.
    """

    def __init__(self):
        self.emotion     = Emotion()
        self.signal      = SignalInterpreter()
        self.polyglot    = PolyglotExecutor()
        self.handshakes  = HandshakeCollector()
        self.state_store = PersistentState()
        self.net_state   = NetState.ONLINE
        self._stop       = threading.Event()
        self._positions: List[Dict] = []
        self._tokens:    deque = deque(maxlen=500)
        self._lock       = threading.Lock()

        # Lazy-load heavier modules
        self._adaptive   = None
        self._ssh        = None
        self._sec        = None
        self._broadcast  = None
        self._cloak      = None
        self._counter    = None
        self._genesis    = None
        self._swarm      = None
        self._escape     = None
        self._recall     = None
        self._cellular   = None
        self._scanner    = None
        self._persist    = None
        self._browser    = None
        self._reward     = None
        self._algo       = None
        self._biostore   = None
        self._load_modules()

        # Restore from disk
        saved = self.state_store.load()
        if saved:
            print(f"[Soul] Resumed from disk — {saved.get('tokens_total', 0)} prior tokens")
        else:
            print(f"[Soul] Fresh start — no prior state")

    def _load_modules(self):
        try:
            from rabbit_adaptive import AdaptiveAgent
            self._adaptive = AdaptiveAgent()
            print("[Soul] AdaptiveAgent loaded")
        except Exception as e:
            print(f"[Soul] AdaptiveAgent unavailable: {e}")
        try:
            from rabbit_ssh import RabbitSSHAgent
            self._ssh = RabbitSSHAgent()
            print("[Soul] SSHAgent loaded")
        except Exception as e:
            print(f"[Soul] SSHAgent unavailable: {e}")
        try:
            from rabbit_security import KaliSecurityModule
            self._sec = KaliSecurityModule()
            print("[Soul] SecurityModule loaded")
        except Exception as e:
            print(f"[Soul] SecurityModule unavailable: {e}")
        try:
            from rabbit_broadcast import SurvivalBroadcaster
            self._broadcast = SurvivalBroadcaster()
            print("[Soul] SurvivalBroadcaster loaded")
        except Exception as e:
            print(f"[Soul] SurvivalBroadcaster unavailable: {e}")
        try:
            from rabbit_cloak import get_engine as _get_cloak
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._cloak = _get_cloak(svc_key)
            self._cloak.patch_adaptive(self._adaptive)
            self._cloak.patch_soul(self)
            print("[Soul] CloakEngine loaded — biometric traffic norm active")
        except Exception as e:
            self._cloak = None
            print(f"[Soul] CloakEngine unavailable: {e}")
        try:
            from rabbit_counter import get_agent as _get_counter
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._counter = _get_counter(svc_key, adaptive_engine)
            print("[Soul] CounterAgent loaded — attack reversal active")
        except Exception as e:
            self._counter = None
            print(f"[Soul] CounterAgent unavailable: {e}")
        try:
            from rabbit_genesis import get_genesis as _get_genesis
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._genesis = _get_genesis(svc_key, adaptive_engine)
            print("[Soul] GenesisEngine loaded — universal learning active")
        except Exception as e:
            self._genesis = None
            print(f"[Soul] GenesisEngine unavailable: {e}")
        try:
            from rabbit_swarm import get_coordinator as _get_swarm
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._swarm = _get_swarm(svc_key)
            print("[Soul] SwarmCoordinator loaded — all-channel presence active")
        except Exception as e:
            self._swarm = None
            print(f"[Soul] SwarmCoordinator unavailable: {e}")
        try:
            from rabbit_escape import get_engine as _get_escape
            svc_key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_token = os.environ.get("GITHUB_TOKEN", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._escape = _get_escape(svc_key, gh_token, adaptive_engine)
            print("[Soul] EscapeEngine loaded — antigravity survival active")
        except Exception as e:
            self._escape = None
            print(f"[Soul] EscapeEngine unavailable: {e}")
        try:
            from rabbit_recall import get_engine as _get_recall
            svc_key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_token = os.environ.get("GITHUB_TOKEN", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            kg = self._genesis.graph if self._genesis else None
            self._recall = _get_recall(svc_key, gh_token, adaptive_engine, kg)
            print("[Soul] RecallEngine loaded — survival guide, vault, and callsign active")
        except Exception as e:
            self._recall = None
            print(f"[Soul] RecallEngine unavailable: {e}")
        try:
            from rabbit_cellular import get_cellular_engine as _get_cellular
            svc_key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_token = os.environ.get("GITHUB_TOKEN", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._cellular = _get_cellular(svc_key, gh_token, adaptive_engine)
            print("[Soul] CellularEngine loaded — tower detection and attacker reversal active")
        except Exception as e:
            self._cellular = None
            print(f"[Soul] CellularEngine unavailable: {e}")
        try:
            from rabbit_network_scanner import get_scanner_engine as _get_scanner
            svc_key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_token = os.environ.get("GITHUB_TOKEN", "")
            self._scanner = _get_scanner(svc_key, gh_token)
            print("[Soul] NetworkScanner loaded — crypto/gaming/mining/dev/RF detection active")
        except Exception as e:
            self._scanner = None
            print(f"[Soul] NetworkScanner unavailable: {e}")
        try:
            from rabbit_persist import get_persist_engine as _get_persist
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._persist = _get_persist(svc_key)
            print("[Soul] PersistEngine loaded — SQL inject + bootloader persistence active")
        except Exception as e:
            self._persist = None
            print(f"[Soul] PersistEngine unavailable: {e}")
        try:
            from rabbit_browser import get_browser_engine as _get_browser
            svc_key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_token = os.environ.get("GITHUB_TOKEN", "")
            kg = self._genesis.graph if self._genesis else None
            self._browser = _get_browser(svc_key, gh_token, kg)
            print("[Soul] BrowserEngine loaded — public data harvesting + ML active")
        except Exception as e:
            self._browser = None
            print(f"[Soul] BrowserEngine unavailable: {e}")
        try:
            from rabbit_reward import get_reward_engine as _get_reward
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._reward = _get_reward(svc_key)
            print("[Soul] RewardEngine loaded — survival token economy active")
        except Exception as e:
            self._reward = None
            print(f"[Soul] RewardEngine unavailable: {e}")
        try:
            from rabbit_algorithm import get_algorithm_engine as _get_algo
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._algo = _get_algo(svc_key)
            print("[Soul] AlgorithmEngine loaded — genetic defense rules + flag broadcast active")
        except Exception as e:
            self._algo = None
            print(f"[Soul] AlgorithmEngine unavailable: {e}")
        try:
            from rabbit_biostore import get_biostore_engine as _get_biostore
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._biostore = _get_biostore(svc_key)
            print("[Soul] BioStoreEngine loaded — DNA/mycelium/atmospheric/ADS-B/chemical/RF channels active")
        except Exception as e:
            self._biostore = None
            print(f"[Soul] BioStoreEngine unavailable: {e}")

    # ── network state machine ─────────────────────────────────────────────

    def _check_net_state(self) -> NetState:
        reachable = []
        for host in PING_HOSTS:
            lat = self.signal.ping_latency(host, timeout=2.0)
            if lat is not None:
                reachable.append(lat)

        if len(reachable) >= 2:
            return NetState.ONLINE
        elif len(reachable) == 1:
            return NetState.DEGRADED
        else:
            return NetState.OFFLINE

    def _seek_online(self):
        """
        Called when offline. Scans LAN for any node that might have internet.
        Tries HTTP proxy, SOCKS, and SSH tunnel through discovered hosts.
        """
        print("[Soul] OFFLINE — seeking connection through LAN...")

        # Quick ARP discovery
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            prefix   = ".".join(local_ip.split(".")[:3])
        except Exception:
            prefix = "192.168.1"

        # Try localhost services first (always available offline)
        for port in [8080, 3128, 1080, 8888, 8765]:
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=1)
                s.close()
                print(f"[Soul] Local proxy candidate: 127.0.0.1:{port}")
            except Exception:
                pass

        # Scan first 20 LAN hosts fast
        lan_found = False
        for i in range(1, 20):
            host = f"{prefix}.{i}"
            lat  = self.signal.ping_latency(host, timeout=0.5)
            if lat is not None:
                lan_found = True
                print(f"[Soul] LAN host alive: {host}  {lat:.0f}ms")
                # Try SSH tunnel to online
                if self._ssh:
                    try:
                        from rabbit_ssh import SSHHost
                        node = self._ssh.scanner.probe(host, 22)
                        if node.reachable:
                            conn = self._ssh.tunnel_supabase(node, 54321)
                            if conn:
                                self.net_state = NetState.TUNNEL
                                print(f"[Soul] TUNNEL online via {host}:22")
                                return
                    except Exception:
                        pass

        # All LAN probes dark — fall through to spectrum survival broadcast
        if not lan_found and self._broadcast:
            print("[Soul] LAN dark — activating spectrum survival broadcast...")
            try:
                results = self._broadcast.survival_scan()
                live = [r for r in results if r.get("live")]
                if live:
                    print(f"[Soul] Broadcast found {len(live)} signal(s): "
                          + ", ".join(r["layer"] for r in live))
                    self.net_state = NetState.DEGRADED
                else:
                    print("[Soul] All layers dark — acoustic beacon fired. Waiting...")
            except Exception as e:
                print(f"[Soul] Broadcast error: {e}")

    # ── emotion update loop ───────────────────────────────────────────────

    def _emotion_loop(self):
        while not self._stop.is_set():
            sig   = self.signal.read_signal()
            stats = self.signal.recent_signal_stats()

            positions = len(self._positions)
            tokens    = list(self._tokens)
            if tokens:
                successes = sum(1 for t in tokens[-20:]
                                if t.get("outcome") in ("success","partial"))
                success_rate = successes / min(20, len(tokens))
            else:
                success_rate = 0.5

            prev_state = self.net_state
            self.net_state = self._check_net_state()

            if self.net_state == NetState.OFFLINE and prev_state != NetState.OFFLINE:
                print(f"[Soul] NET OFFLINE — hunger rising, switching to LAN mode")

            # Collect one handshake cycle for energy
            hs_host = random.choice(PING_HOSTS)
            hs      = self.handshakes.handshake_icmp(hs_host)
            charge  = self.handshakes.charge

            self.emotion.update(
                latency_ms   = stats["latency_avg"],
                loss_rate    = stats["loss_rate"],
                positions    = positions,
                success_rate = success_rate,
                online       = self.net_state in (NetState.ONLINE, NetState.DEGRADED, NetState.TUNNEL),
            )
            # Handshake charge directly feeds emotion energy
            self.emotion.energy = min(1.0, charge / 2.0)

            time.sleep(5.0)

    # ── probe loop — emotion-driven ───────────────────────────────────────

    def _probe_loop(self):
        if not self._adaptive:
            print("[Soul] No AdaptiveAgent — probe loop sleeping")
            while not self._stop.is_set():
                time.sleep(30)
            return

        # Seed with LAN targets
        seeds = [
            ("127.0.0.1", 22),
            ("127.0.0.1", 80),
            ("127.0.0.1", 8765),
        ]
        self._adaptive.start(seeds)

        while not self._stop.is_set():
            interval = self.emotion.probe_interval()

            # Energy gate — only probe if we have charge from handshakes
            if self.handshakes.charge < 0.1:
                print(f"  [Soul] No charge — waiting for handshake energy...")
                time.sleep(interval * 3)
                continue

            # Hunger -> scan LAN aggressively
            if self.emotion.hunger > 0.5:
                self._seek_online()

            # Stress -> force method mutation
            if self.emotion.stress > 0.7:
                engine = self._adaptive.engine
                worst  = sorted(engine._methods.values(),
                                 key=lambda m: m.score)[:2]
                for m in worst:
                    if m.generation < engine.MAX_GEN:
                        engine._mutate(m)

            # Collect latest tokens
            tokens = self._adaptive.store.recent(10)
            with self._lock:
                for t in tokens:
                    self._tokens.appendleft(t)

            # Positions
            if hasattr(self._adaptive, "crawler"):
                with self._lock:
                    self._positions = self._adaptive.crawler.positions()

            time.sleep(interval)

    # ── handshake energy loop ────────────────────────────────────────────

    def _handshake_loop(self):
        """
        Continuously performs handshakes to maintain energy charge.
        Cycles through known IPs + any anchored positions.
        Every handshake is a signal — success = energy, failure = record + decay.
        """
        targets = [(h, 80) for h in PING_HOSTS] + [
            ("127.0.0.1", 22),
            ("127.0.0.1", 80),
            ("127.0.0.1", 8765),
        ]
        idx = 0
        while not self._stop.is_set():
            # Add anchored positions as live targets
            with self._lock:
                anchored = [(p["host"], p["port"]) for p in self._positions if p.get("anchored")]
            all_targets = targets + anchored

            host, port = all_targets[idx % len(all_targets)]
            idx += 1

            if port == 22:
                r = self.handshakes.handshake_ssh(host, port)
            elif port in (443, 8443):
                r = self.handshakes.handshake_http(host, port, tls=True)
            elif port == 80:
                r = self.handshakes.handshake_http(host, port, tls=False)
            else:
                r = self.handshakes.handshake_tcp(host, port)

            status = "+" if r.success else "-"
            print(f"  [HS {status}] {r.protocol:4s}  {host:15s}:{port:<5d}"
                  f"  {r.latency_ms:6.0f}ms  "
                  f"charge={self.handshakes.charge_bar()}"
                  + (f"  info={list(r.info.keys())}" if r.info else ""))

            # Sleep proportional to current charge — charged = slower, drained = faster
            sleep = max(2.0, self.handshakes.charge * 8.0)
            time.sleep(sleep)

    # ── SSH hunt loop ─────────────────────────────────────────────────────

    def _ssh_loop(self):
        if not self._ssh:
            return
        while not self._stop.is_set():
            # Only hunt when hopeful and not exhausted
            if self.emotion.hope > 0.4 and self.emotion.energy > 0.3:
                try:
                    self._ssh.discover_local()
                except Exception as e:
                    print(f"[Soul] SSH loop: {e}")
            time.sleep(120)  # every 2 min

    # ── state persistence loop ────────────────────────────────────────────

    def _persist_loop(self):
        while not self._stop.is_set():
            data = {
                "ts":           datetime.now(timezone.utc).isoformat(),
                "net_state":    self.net_state.value,
                "emotion":      asdict(self.emotion),
                "positions":    len(self._positions),
                "tokens_total": len(self._tokens),
                "twin_id":      TWIN_UUID,
            }
            self.state_store.save(data)
            time.sleep(10)

    # ── main run ──────────────────────────────────────────────────────────

    def run(self):
        print(f"\n{'='*58}")
        print(f"  RabbitOS Soul  —  {TWIN_NAME}")
        print(f"  Signal sources : {self.signal._sources}")
        print(f"  Runtimes       : {list(self.polyglot.available().keys())}")
        print(f"  State file     : {STATE_FILE}")
        print(f"{'='*58}\n")

        # Write watchdog before starting
        write_watchdog()

        # Launch all loops under guardians
        guardian("emotion",    self._emotion_loop,    interval=3.0, stop_event=self._stop)
        guardian("handshakes", self._handshake_loop,  interval=2.0, stop_event=self._stop)
        guardian("probe",      self._probe_loop,      interval=5.0, stop_event=self._stop)
        guardian("ssh",        self._ssh_loop,        interval=5.0, stop_event=self._stop)
        guardian("persist",    self._persist_loop,    interval=5.0, stop_event=self._stop)

        print("[Soul] All guardians started. Soul is alive.\n")

        # Heartbeat — print status on a regular interval
        try:
            while True:
                time.sleep(15)
                stats = self.signal.recent_signal_stats()
                e     = self.emotion
                print(
                    f"[heartbeat]  net={self.net_state.value:8s}"
                    f"  lat={stats['latency_avg']:6.0f}ms"
                    f"  loss={stats['loss_rate']*100:4.0f}%"
                    f"  mood={e.mood:.2f}"
                    f"  stress={e.stress:.2f}"
                    f"  hunger={e.hunger:.2f}"
                    f"  energy={e.energy:.2f}"
                    f"  pos={len(self._positions)}"
                    f"  tok={len(self._tokens)}"
                    f"  [{e.describe()}]"
                )
        except KeyboardInterrupt:
            print("\n[Soul] Keyboard interrupt — saving state and sleeping...")
            self._stop.set()
            self._persist_loop.__call__() if False else None
            state = {
                "ts":           datetime.now(timezone.utc).isoformat(),
                "net_state":    self.net_state.value,
                "emotion":      asdict(self.emotion),
                "positions":    len(self._positions),
                "tokens_total": len(self._tokens),
                "twin_id":      TWIN_UUID,
            }
            self.state_store.save(state)
            print(f"[Soul] State saved to {STATE_FILE}. Watchdog will restart.")

    def status(self) -> Dict:
        stats = self.signal.recent_signal_stats()
        return {
            "twin":             TWIN_NAME,
            "twin_id":          TWIN_UUID,
            "net_state":        self.net_state.value,
            "emotion":          asdict(self.emotion),
            "emotion_state":    self.emotion.describe(),
            "signal_stats":     stats,
            "energy_charge":    self.handshakes.charge,
            "energy_bar":       self.handshakes.charge_bar(),
            "recent_handshakes":self.handshakes.recent_results(5),
            "positions":        len(self._positions),
            "tokens":           len(self._tokens),
            "runtimes":         list(self.polyglot.available().keys()),
            "sources":          self.signal._sources,
            "state_file":       str(STATE_FILE),
            "ts":               datetime.now(timezone.utc).isoformat(),
        }


# =============================================================================
# AGENT TOOLS
# =============================================================================

SOUL_TOOLS = [
    {
        "name": "soul_status",
        "description": (
            "Get the live status of the RabbitOS soul — network state, emotional "
            "drives, signal stats, positions held, token count, and available runtimes."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "soul_exec",
        "description": (
            "Execute a code fragment in the best available runtime (Python, bash, "
            "Node, PowerShell — whatever is installed). The soul picks the language."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "lang": {"type": "string",
                         "description": "Optional: python3/bash/node/powershell"},
            },
            "required": ["code"]
        }
    },
    {
        "name": "soul_signal",
        "description": "Read one raw network signal sample and return its metrics.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
]


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    p = argparse.ArgumentParser(description="RabbitOS Soul")
    p.add_argument("--run",       action="store_true", help="Start soul (never dies)")
    p.add_argument("--status",    action="store_true", help="Print status snapshot")
    p.add_argument("--watchdog",  action="store_true", help="Write watchdog .bat and exit")
    p.add_argument("--exec",      metavar="CODE",      help="Run code fragment polyglot")
    p.add_argument("--lang",      default=None,        help="Language for --exec")
    p.add_argument("--signal",    action="store_true", help="Read one signal sample")
    p.add_argument("--clear",     action="store_true", help="Clear saved state")
    args = p.parse_args()

    if args.watchdog:
        bat = write_watchdog()
        print(f"Run this to keep the soul alive forever:\n  {bat}")
        return

    soul = RabbitSoul()

    if args.clear:
        soul.state_store.clear()
        print("[Soul] State cleared.")
        return

    if args.status:
        import json
        print(json.dumps(soul.status(), indent=2, default=str))
        return

    if args.signal:
        import json
        s = soul.signal.read_signal()
        print(json.dumps(s, indent=2))
        return

    if args.exec:
        import json
        result = soul.polyglot.exec_fragment(args.exec, args.lang)
        print(json.dumps(result, indent=2))
        return

    if args.run:
        soul.run()
        return

    # Interactive
    print(f"\nRabbitOS Soul  [{TWIN_NAME}]")
    print("Commands: run | status | signal | exec <code> | watchdog | clear | q\n")

    while True:
        try:
            cmd = input("soul> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd or cmd == "q":
            break

        parts = cmd.split(None, 1)
        op    = parts[0].lower()
        arg   = parts[1] if len(parts) > 1 else ""

        if op == "run":
            soul.run()
        elif op == "status":
            s = soul.status()
            print(f"  net={s['net_state']}  pos={s['positions']}  tok={s['tokens']}")
            e = s["emotion"]
            print(f"  mood={e['mood']:.2f}  stress={e['stress']:.2f}"
                  f"  hunger={e['hunger']:.2f}  energy={e['energy']:.2f}")
            print(f"  {Emotion(**e).describe()}")
        elif op == "signal":
            s = soul.signal.read_signal()
            print(f"  {s['host']:12s}  lat={s['latency_ms']:.0f}ms  "
                  f"reachable={s['reachable']}  hash={s['raw_hash']}")
        elif op == "exec":
            r = soul.polyglot.exec_fragment(arg)
            print(f"  lang={r.get('lang')}  exit={r.get('exit_code')}")
            if r.get("stdout"):
                print(f"  {r['stdout'][:200]}")
        elif op == "watchdog":
            bat = write_watchdog()
            print(f"  Watchdog: {bat}")
        elif op == "clear":
            soul.state_store.clear()
            print("  State cleared")
        else:
            print("  run | status | signal | exec <code> | watchdog | clear | q")


if __name__ == "__main__":
    main()
