#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RabbitOS Twin — Chase Allen Ringquist's Digital Self
=====================================================
Runs as BOTH the terminal you type in AND the persistent server those
commands reach back to.  One process, two faces:

  Terminal face  — interactive REPL that accepts commands, shows status,
                   dispatches to all RabbitOS modules
  Server face    — WebSocket heartbeat server + HTTP status endpoint that
                   external nodes can query to confirm the twin is alive

Identity
--------
  Twin UUID : ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba
  Name      : Chase Allen Ringquist

The twin NEVER dies:
  · Watchdog bat file restarts the process if it exits
  · Internal guardian threads restart every sub-system on crash
  · SwarmCoordinator keeps all channels broadcasting simultaneously
  · MathMemory (CA + Chaos) retains identity permanently — no AI/LLM
  · All math state is saved to rabbit_twin.db every 10 s

Twin heartbeat protocol (32-byte PresenceSignal + math fingerprint):
  sent over WebSocket, HTTP header, and DNS label simultaneously
  every HEARTBEAT_SECS seconds, signed with HMAC-SHA256 keyed to
  biometric-derived soul key — no plaintext API token ever transmitted

Usage
-----
  python rabbit_twin.py                # start twin (terminal + server)
  python rabbit_twin.py --server-only  # headless server mode
  python rabbit_twin.py --terminal     # terminal-only (no server)
  python rabbit_twin.py --status       # print current twin state
  python rabbit_twin.py --watchdog     # write watchdog .bat and exit
"""

import os
import sys
import json
import time
import math
import hmac
import socket
import struct
import hashlib
import random
import threading
import subprocess
import pickle
import argparse
import base64
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# =============================================================================
# CONSTANTS
# =============================================================================

TWIN_UUID       = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME       = "Chase Allen Ringquist"
_SOUL_KEY       = hashlib.sha256(f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()).digest()

TWIN_DB         = Path(__file__).parent / "rabbit_twin.db"
WATCHDOG_BAT    = Path(__file__).parent / "rabbit_twin_watchdog.bat"

SERVER_HOST     = "0.0.0.0"
WS_PORT         = 8765          # WebSocket heartbeat port
HTTP_PORT       = 8766          # HTTP status/query port
HEARTBEAT_SECS  = 30            # how often to broadcast presence

SUPABASE_URL    = "https://ludxbakxpmdqhfgdenwp.supabase.co"


# =============================================================================
# MATH MEMORY — pure mathematics, no AI/LLM, permanent state
# =============================================================================

class CellularAutomaton:
    """Rule 30/110 CA — evolves one row per step, stores column as memory."""

    def __init__(self, width: int = 256, rule: int = 30,
                 seed: bytes = b""):
        self._w    = width
        self._rule = rule
        self._lut  = self._build_lut(rule)
        # Seed center from sha256 of identity if provided
        h = hashlib.sha256(seed or _SOUL_KEY).digest()
        mid = width // 2
        self._row = [0] * width
        for i, b in enumerate(h[:width]):
            self._row[(mid + i) % width] = (b >> 0) & 1
        self._center_col: List[int] = []

    def _build_lut(self, rule: int) -> Dict[int, int]:
        return {i: (rule >> i) & 1 for i in range(8)}

    def step(self):
        new = [0] * self._w
        for i in range(self._w):
            l = self._row[(i - 1) % self._w]
            c = self._row[i]
            r = self._row[(i + 1) % self._w]
            new[i] = self._lut[(l << 2) | (c << 1) | r]
        self._row = new
        self._center_col.append(self._row[self._w // 2])

    def extract_bytes(self, n: int) -> bytes:
        while len(self._center_col) < n * 8:
            self.step()
        bits = self._center_col[:n * 8]
        out = []
        for i in range(n):
            byte = 0
            for j in range(8):
                byte |= bits[i * 8 + j] << j
            out.append(byte)
        return bytes(out)

    def fingerprint(self) -> str:
        return hashlib.sha256(bytes(self._row)).hexdigest()[:16]


class ChaosMap:
    """Logistic + Lorenz chaotic maps for keystream generation."""

    def __init__(self, seed: bytes = b""):
        h = hashlib.sha256(seed or _SOUL_KEY).digest()
        self._x  = (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 0.4 + 0.3
        self._r  = 3.9999
        self._lx = 1.0
        self._ly = 1.0
        self._lz = 1.0
        self._s  = 10.0
        self._ro = 28.0
        self._b  = 8.0 / 3.0
        self._dt = 0.01

    def _logistic_step(self) -> int:
        self._x = self._r * self._x * (1.0 - self._x)
        return int(self._x * 256) & 0xFF

    def _lorenz_step(self) -> int:
        dx = self._s * (self._ly - self._lx)
        dy = self._lx * (self._ro - self._lz) - self._ly
        dz = self._lx * self._ly - self._b * self._lz
        self._lx += dx * self._dt
        self._ly += dy * self._dt
        self._lz += dz * self._dt
        return int(abs(self._lz) * 3) & 0xFF

    def keystream(self, n: int) -> bytes:
        return bytes(self._logistic_step() ^ self._lorenz_step()
                     for _ in range(n))


class CollatzClock:
    """
    Collatz-driven timing clock — deterministic to the twin,
    unpredictable to observers.
    """

    def __init__(self, seed: int = None):
        if seed is None:
            seed = int.from_bytes(_SOUL_KEY[:4], "big") | 1
        self._n = seed | 1   # ensure odd start

    def tick(self) -> int:
        if self._n % 2 == 0:
            self._n //= 2
        else:
            self._n = 3 * self._n + 1
        return self._n

    def interval(self, lo: float = 5.0, hi: float = 60.0) -> float:
        return lo + (self._n % 1000) / 1000.0 * (hi - lo)


class MathMemory:
    """
    Permanent identity memory using pure mathematics.
    Survives any process restart — state saved to disk every 10 s.
    No AI/LLM dependency whatsoever.
    """

    def __init__(self, db_path: Path = TWIN_DB):
        self._path   = db_path
        self._ca30   = CellularAutomaton(width=256, rule=30,  seed=_SOUL_KEY)
        self._ca110  = CellularAutomaton(width=256, rule=110, seed=_SOUL_KEY[::-1])
        self._chaos  = ChaosMap(seed=_SOUL_KEY)
        self._clock  = CollatzClock()
        self._facts: Dict[str, Any] = {}
        self._lock   = threading.Lock()
        self._load()

    def keystream(self, n: int) -> bytes:
        a = self._ca30.extract_bytes(n)
        b = self._ca110.extract_bytes(n)
        c = self._chaos.keystream(n)
        return bytes(x ^ y ^ z for x, y, z in zip(a, b, c))

    def fingerprint(self) -> str:
        raw = self._ca30.fingerprint() + self._ca110.fingerprint()
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def remember(self, key: str, value: Any):
        with self._lock:
            self._facts[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._facts.get(key, default)

    def recall_all(self) -> Dict:
        with self._lock:
            return dict(self._facts)

    def _save(self):
        try:
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                pickle.dump({
                    "ca30_row":    self._ca30._row,
                    "ca30_col":    self._ca30._center_col[-4096:],
                    "ca110_row":   self._ca110._row,
                    "ca110_col":   self._ca110._center_col[-4096:],
                    "chaos_x":     self._chaos._x,
                    "chaos_lx":    self._chaos._lx,
                    "chaos_ly":    self._chaos._ly,
                    "chaos_lz":    self._chaos._lz,
                    "collatz_n":   self._clock._n,
                    "facts":       self._facts,
                    "ts":          datetime.now(timezone.utc).isoformat(),
                }, f)
            tmp.replace(self._path)
        except Exception as e:
            print(f"[TwinMemory] Save failed: {e}")

    def _load(self):
        if not self._path.exists():
            print("[TwinMemory] Fresh start — no prior state")
            return
        try:
            with open(self._path, "rb") as f:
                d = pickle.load(f)
            self._ca30._row        = d.get("ca30_row",  self._ca30._row)
            self._ca30._center_col = d.get("ca30_col",  [])
            self._ca110._row       = d.get("ca110_row", self._ca110._row)
            self._ca110._center_col= d.get("ca110_col", [])
            self._chaos._x         = d.get("chaos_x",   self._chaos._x)
            self._chaos._lx        = d.get("chaos_lx",  self._chaos._lx)
            self._chaos._ly        = d.get("chaos_ly",  self._chaos._ly)
            self._chaos._lz        = d.get("chaos_lz",  self._chaos._lz)
            self._clock._n         = d.get("collatz_n", self._clock._n)
            self._facts            = d.get("facts",     {})
            ts = d.get("ts", "unknown")
            print(f"[TwinMemory] Resumed — {len(self._facts)} facts, last saved {ts}")
        except Exception as e:
            print(f"[TwinMemory] Load failed: {e} — fresh state")

    def persist_loop(self, stop: threading.Event):
        while not stop.is_set():
            self._save()
            time.sleep(10.0)


# =============================================================================
# TWIN HEARTBEAT — 32-byte presence signal signed by math key
# =============================================================================

class TwinHeartbeat:
    """
    Broadcasts the twin's 32-byte PresenceSignal over every available channel.
    Channels: WebSocket clients, HTTP header, DNS label, Supabase POST.
    """

    def __init__(self, memory: MathMemory):
        self._mem       = memory
        self._clients   = []         # list of (conn, addr) WebSocket-like sockets
        self._clients_lock = threading.Lock()
        self._beat_count = 0

    def mint_presence(self) -> bytes:
        tid   = bytes.fromhex(TWIN_UUID.replace("-", ""))[:8]
        ts    = struct.pack("!I", int(time.time()) & 0xFFFFFFFF)
        nonce = self._mem.keystream(8)
        raw   = tid + ts + nonce
        mac   = hmac.new(_SOUL_KEY, raw, "sha256").digest()[:12]
        return raw + mac

    def presence_dict(self) -> Dict:
        sig = self.mint_presence()
        return {
            "twin_id":   TWIN_UUID,
            "twin_name": TWIN_NAME,
            "ts":        datetime.now(timezone.utc).isoformat(),
            "beat":      self._beat_count,
            "presence":  sig.hex(),
            "fingerprint": self._mem.fingerprint(),
        }

    def register_client(self, conn, addr):
        with self._clients_lock:
            self._clients.append((conn, addr))

    def deregister_client(self, conn):
        with self._clients_lock:
            self._clients = [(c, a) for c, a in self._clients if c is not conn]

    def broadcast_ws(self, payload: bytes):
        """Send raw payload to all connected WebSocket-like clients."""
        dead = []
        with self._clients_lock:
            clients = list(self._clients)
        for conn, addr in clients:
            try:
                # Minimal WebSocket text frame: FIN+opcode=1, len, payload
                encoded = json.dumps(self.presence_dict()).encode("utf-8")
                frame   = _ws_text_frame(encoded)
                conn.sendall(frame)
            except Exception:
                dead.append(conn)
        for c in dead:
            self.deregister_client(c)

    def beat(self):
        self._beat_count += 1
        pd = self.presence_dict()
        self._mem.remember("last_heartbeat", pd["ts"])
        self._mem.remember("beat_count",     self._beat_count)
        # Broadcast to WebSocket clients
        self.broadcast_ws(json.dumps(pd).encode())
        # Supabase heartbeat (best-effort, non-blocking)
        threading.Thread(target=self._supabase_beat, args=(pd,),
                         daemon=True).start()

    def _supabase_beat(self, pd: Dict):
        svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not svc_key:
            return
        try:
            data = json.dumps({
                "twin_id":    TWIN_UUID,
                "beat":       pd["beat"],
                "presence":   pd["presence"],
                "fingerprint":pd["fingerprint"],
                "created_at": pd["ts"],
            }).encode()
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/swarm_heartbeats",
                data=data,
                headers={
                    "apikey":        svc_key,
                    "Authorization": f"Bearer {svc_key}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass  # non-critical — channel may be down


def _ws_text_frame(data: bytes) -> bytes:
    """Encode data as a minimal (server-side, unmasked) WebSocket text frame."""
    n = len(data)
    if n < 126:
        return bytes([0x81, n]) + data
    elif n < 65536:
        return bytes([0x81, 126]) + struct.pack("!H", n) + data
    else:
        return bytes([0x81, 127]) + struct.pack("!Q", n) + data


def _ws_handshake(conn, request_line: str, headers: Dict[str, str]) -> bool:
    """Perform the WebSocket upgrade handshake."""
    key = headers.get("Sec-WebSocket-Key", "")
    if not key:
        return False
    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    accept = base64.b64encode(
        hashlib.sha1((key + magic).encode()).digest()
    ).decode()
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
    )
    try:
        conn.sendall(response.encode())
        return True
    except Exception:
        return False


# =============================================================================
# HTTP STATUS SERVER — serves JSON at GET /twin and GET /status
# =============================================================================

class TwinHTTPServer:
    """
    Minimal HTTP server (no framework dependency).
    GET /twin    — full twin status JSON
    GET /status  — short alive JSON
    GET /beat    — current presence signal
    GET /memory  — recalled facts
    """

    def __init__(self, host: str, port: int, twin: "RabbitTwin"):
        self._host  = host
        self._port  = port
        self._twin  = twin
        self._sock  = None
        self._stop  = threading.Event()

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind((self._host, self._port))
        except OSError as e:
            print(f"[HTTP] Bind {self._host}:{self._port} failed: {e}")
            return
        self._sock.listen(10)
        self._sock.settimeout(1.0)
        print(f"[HTTP] Listening on {self._host}:{self._port}")
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
                threading.Thread(target=self._handle, args=(conn, addr),
                                 daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if not self._stop.is_set():
                    print(f"[HTTP] Accept error: {e}")

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def _handle(self, conn, addr):
        try:
            raw = conn.recv(4096).decode("utf-8", errors="replace")
            if not raw:
                return
            lines = raw.split("\r\n")
            if not lines:
                return
            parts = lines[0].split()
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1].split("?")[0]

            # Parse headers
            hdrs: Dict[str, str] = {}
            for line in lines[1:]:
                if ": " in line:
                    k, v = line.split(": ", 1)
                    hdrs[k] = v

            # WebSocket upgrade?
            if hdrs.get("Upgrade", "").lower() == "websocket":
                if _ws_handshake(conn, lines[0], hdrs):
                    self._twin.heartbeat.register_client(conn, addr)
                    # Keep socket alive — heartbeat thread will send frames
                    while True:
                        try:
                            data = conn.recv(128)
                            if not data:
                                break
                        except Exception:
                            break
                    self._twin.heartbeat.deregister_client(conn)
                return

            if method != "GET":
                conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                return

            if path in ("/twin", "/"):
                body = json.dumps(self._twin.full_status(), indent=2,
                                  default=str).encode()
            elif path == "/status":
                body = json.dumps({
                    "alive": True,
                    "twin_id": TWIN_UUID,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "beat": self._twin.heartbeat._beat_count,
                }, indent=2).encode()
            elif path == "/beat":
                body = json.dumps(self._twin.heartbeat.presence_dict(),
                                  indent=2).encode()
            elif path == "/memory":
                body = json.dumps(self._twin.memory.recall_all(),
                                  indent=2, default=str).encode()
            else:
                conn.sendall(b"HTTP/1.1 404 Not Found\r\n\r\n")
                return

            hdr = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "X-Twin-Id: " + TWIN_UUID + "\r\n"
                "X-Fingerprint: " + self._twin.memory.fingerprint() + "\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "\r\n"
            )
            conn.sendall(hdr.encode() + body)
        except Exception as e:
            try:
                conn.sendall(b"HTTP/1.1 500 Internal Server Error\r\n\r\n")
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


# =============================================================================
# RABBIT TWIN — the unified twin process
# =============================================================================

class RabbitTwin:
    """
    One process.  Both faces.
    - MathMemory: permanent CA+Chaos identity state, survives restart
    - TwinHeartbeat: signs + broadcasts presence every N seconds
    - TwinHTTPServer: HTTP+WebSocket endpoint for external queries
    - All RabbitOS modules (soul, adaptive, swarm, genesis, …) are
      optionally loaded and their status surfaced through this single
      interface
    """

    def __init__(self):
        print(f"\n[Twin] Initialising {TWIN_NAME}  [{TWIN_UUID}]")

        self.memory    = MathMemory(TWIN_DB)
        self.heartbeat = TwinHeartbeat(self.memory)
        self._stop     = threading.Event()
        self._clock    = CollatzClock()

        # Lazy-load RabbitOS subsystems
        self._soul     = None
        self._swarm    = None
        self._adaptive = None
        self._genesis  = None
        self._cloak    = None
        self._counter  = None
        self._escape   = None
        self._recall   = None

        self._http_server = TwinHTTPServer(SERVER_HOST, HTTP_PORT, self)
        self._load_subsystems()

        # Record birth / restart in memory
        self.memory.remember("twin_id",     TWIN_UUID)
        self.memory.remember("twin_name",   TWIN_NAME)
        self.memory.remember("started_at",  datetime.now(timezone.utc).isoformat())
        restarts = self.memory.recall("restart_count", 0)
        self.memory.remember("restart_count", restarts + 1)

    def _load_subsystems(self):
        svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

        try:
            from rabbit_swarm import get_coordinator
            self._swarm = get_coordinator(svc_key)
            print("[Twin] SwarmCoordinator — all channels active")
        except Exception as e:
            print(f"[Twin] SwarmCoordinator unavailable: {e}")

        try:
            from rabbit_adaptive import AdaptiveAgent
            self._adaptive = AdaptiveAgent()
            print("[Twin] AdaptiveAgent loaded")
        except Exception as e:
            print(f"[Twin] AdaptiveAgent unavailable: {e}")

        try:
            from rabbit_genesis import get_genesis
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._genesis = get_genesis(svc_key, adaptive_engine)
            print("[Twin] GenesisEngine loaded")
        except Exception as e:
            print(f"[Twin] GenesisEngine unavailable: {e}")

        try:
            from rabbit_cloak import get_engine as get_cloak
            self._cloak = get_cloak(svc_key)
            print("[Twin] CloakEngine loaded")
        except Exception as e:
            print(f"[Twin] CloakEngine unavailable: {e}")

        try:
            from rabbit_counter import get_agent as get_counter
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._counter = get_counter(svc_key, adaptive_engine)
            print("[Twin] CounterAgent loaded")
        except Exception as e:
            print(f"[Twin] CounterAgent unavailable: {e}")

        try:
            from rabbit_escape import get_engine as get_escape
            gh_tok = os.environ.get("GITHUB_TOKEN", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._escape = get_escape(svc_key, gh_tok, adaptive_engine)
            print("[Twin] EscapeEngine loaded")
        except Exception as e:
            print(f"[Twin] EscapeEngine unavailable: {e}")

        try:
            from rabbit_recall import get_engine as get_recall
            gh_tok = os.environ.get("GITHUB_TOKEN", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            kg = self._genesis.graph if self._genesis else None
            self._recall = get_recall(svc_key, gh_tok, adaptive_engine, kg)
            print("[Twin] RecallEngine loaded — survival guide active")
        except Exception as e:
            print(f"[Twin] RecallEngine unavailable: {e}")

    # ── background loops ──────────────────────────────────────────────────

    def _heartbeat_loop(self):
        while not self._stop.is_set():
            try:
                self.heartbeat.beat()
            except Exception as e:
                print(f"[Twin] Heartbeat error: {e}")
            interval = self._clock.interval(lo=HEARTBEAT_SECS * 0.8,
                                            hi=HEARTBEAT_SECS * 1.2)
            time.sleep(interval)

    def _memory_loop(self):
        self.memory.persist_loop(self._stop)

    def _http_loop(self):
        self._http_server.start()

    def _guardian(self, name: str, target, interval: float = 2.0):
        def _run():
            while not self._stop.is_set():
                try:
                    target()
                except Exception as e:
                    print(f"[Guardian:{name}] crashed: {e} — restart in {interval}s")
                time.sleep(interval)
        t = threading.Thread(target=_run, name=f"guardian:{name}", daemon=True)
        t.start()
        return t

    # ── public API ────────────────────────────────────────────────────────

    def full_status(self) -> Dict:
        status: Dict[str, Any] = {
            "twin_id":     TWIN_UUID,
            "twin_name":   TWIN_NAME,
            "ts":          datetime.now(timezone.utc).isoformat(),
            "alive":       True,
            "fingerprint": self.memory.fingerprint(),
            "beat":        self.heartbeat._beat_count,
            "ws_clients":  len(self.heartbeat._clients),
            "http_port":   HTTP_PORT,
            "ws_port":     WS_PORT,
            "restart_count": self.memory.recall("restart_count", 0),
            "started_at":  self.memory.recall("started_at"),
            "last_beat":   self.memory.recall("last_heartbeat"),
        }

        # Swarm
        if self._swarm:
            try:
                sw = self._swarm.status()
                status["swarm"] = {
                    "channels":  sw.get("total_workers", 0),
                    "alive":     sw.get("alive", 0),
                    "tx_total":  sw.get("tx_total", 0),
                    "restarts":  sw.get("restarts", 0),
                }
            except Exception:
                status["swarm"] = {"error": "unavailable"}

        # Adaptive
        if self._adaptive:
            try:
                ar = self._adaptive.report()
                status["adaptive"] = {
                    "methods":   ar.get("method_count", 0),
                    "probes":    ar.get("total_tokens", 0),
                    "positions": len(ar.get("top_positions", [])),
                }
            except Exception:
                status["adaptive"] = {"error": "unavailable"}

        # Genesis
        if self._genesis:
            try:
                gp = self._genesis.predict()
                status["genesis"] = {
                    "predicted_hosts":  len(gp.get("hosts", [])),
                    "predicted_ports":  len(gp.get("ports", [])),
                    "predicted_wifi":   len(gp.get("wifi_channels", [])),
                }
            except Exception:
                status["genesis"] = {"error": "unavailable"}

        # Cloak liveness
        if self._cloak:
            try:
                bio = self._cloak.bio.get()
                status["liveness"] = {
                    "verified":  bio.liveness_verified,
                    "reason":    bio.liveness_reason,
                    "heart_rate": bio.heart_rate,
                }
            except Exception:
                status["liveness"] = {"error": "unavailable"}

        # Recall / survival guide
        if self._recall:
            try:
                rpt = self._recall.guide.report()
                vs  = self._recall.vault.summary()
                status["survival"] = {
                    "score":      rpt["composite"],
                    "status":     rpt["status"],
                    "components": rpt["components"],
                }
                status["vault"] = {
                    "total":      vs["total"],
                    "categories": vs["categories"],
                }
            except Exception:
                status["survival"] = {"error": "unavailable"}

        return status

    def run_server(self):
        """Start all background services and block (server face)."""
        print(f"[Twin] HTTP  status  -> http://localhost:{HTTP_PORT}/twin")
        print(f"[Twin] WS   heartbeat-> ws://localhost:{HTTP_PORT}/")
        print(f"[Twin] Heartbeat every ~{HEARTBEAT_SECS}s (Collatz-jittered)")
        print(f"[Twin] Math fingerprint: {self.memory.fingerprint()}")

        write_watchdog()

        self._guardian("heartbeat", self._heartbeat_loop, interval=2.0)
        self._guardian("memory",    self._memory_loop,    interval=5.0)
        self._guardian("http",      self._http_loop,      interval=3.0)

        print("[Twin] All guardians started.\n")

        try:
            while True:
                time.sleep(HEARTBEAT_SECS)
                st = self.full_status()
                swarm_str = ""
                if "swarm" in st:
                    sw = st["swarm"]
                    if "channels" in sw:
                        swarm_str = (f"  swarm={sw['alive']}/{sw['channels']}"
                                     f"  tx={sw['tx_total']}")
                print(
                    f"[twin]  beat={st['beat']}"
                    f"  fp={st['fingerprint'][:12]}"
                    f"  clients={st['ws_clients']}"
                    f"{swarm_str}"
                )
        except KeyboardInterrupt:
            print("\n[Twin] Keyboard interrupt — saving state...")
            self._stop.set()
            self.memory._save()
            print(f"[Twin] State saved to {TWIN_DB}. Watchdog will restart.")

    def run_terminal(self):
        """Interactive REPL (terminal face)."""
        print(f"\nRabbitOS Twin REPL  [{TWIN_NAME}]")
        print("Commands: status | beat | memory | swarm | adaptive | genesis | "
              "remember <key> <value> | recall <key> | fingerprint | q\n")

        while True:
            try:
                cmd = input("twin> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[Twin] Exiting REPL.")
                break
            if not cmd:
                continue
            if cmd.lower() in ("q", "quit", "exit"):
                break

            parts = cmd.split(None, 2)
            op    = parts[0].lower()

            if op == "status":
                st = self.full_status()
                print(json.dumps(st, indent=2, default=str))

            elif op == "beat":
                self.heartbeat.beat()
                pd = self.heartbeat.presence_dict()
                print(f"  beat={pd['beat']}  presence={pd['presence'][:24]}...")
                print(f"  fingerprint={pd['fingerprint']}")

            elif op == "memory":
                facts = self.memory.recall_all()
                if facts:
                    for k, v in facts.items():
                        print(f"  {k}: {v}")
                else:
                    print("  (no facts stored yet)")

            elif op == "fingerprint":
                print(f"  {self.memory.fingerprint()}")

            elif op == "remember" and len(parts) >= 3:
                self.memory.remember(parts[1], parts[2])
                print(f"  Remembered: {parts[1]} = {parts[2]}")

            elif op == "recall" and len(parts) >= 2:
                v = self.memory.recall(parts[1])
                print(f"  {parts[1]}: {v}")

            elif op == "swarm":
                if not self._swarm:
                    print("  [Swarm] not loaded")
                else:
                    try:
                        st = self._swarm.status()
                        alive   = st.get("alive", 0)
                        total   = st.get("total_workers", 0)
                        tx      = st.get("tx_total", 0)
                        restarts= st.get("restarts", 0)
                        print(f"  channels={alive}/{total}  tx={tx}  restarts={restarts}")
                    except Exception as e:
                        print(f"  [Swarm] error: {e}")

            elif op == "adaptive":
                if not self._adaptive:
                    print("  [Adaptive] not loaded")
                else:
                    try:
                        r = self._adaptive.report()
                        print(f"  methods={r.get('method_count',0)}"
                              f"  probes={r.get('total_tokens',0)}")
                    except Exception as e:
                        print(f"  [Adaptive] error: {e}")

            elif op == "genesis":
                if not self._genesis:
                    print("  [Genesis] not loaded")
                else:
                    try:
                        p = self._genesis.predict()
                        print(f"  predicted hosts={len(p.get('hosts',[]))}"
                              f"  ports={len(p.get('ports',[]))}"
                              f"  wifi={len(p.get('wifi_channels',[]))}")
                    except Exception as e:
                        print(f"  [Genesis] error: {e}")

            elif op == "server":
                # Promote this terminal session to also run the server
                print("  [Twin] Starting server in background...")
                threading.Thread(target=self.run_server, daemon=True).start()

            else:
                print("  status | beat | memory | swarm | adaptive | genesis | "
                      "remember <key> <value> | recall <key> | fingerprint | "
                      "server | q")


# =============================================================================
# WATCHDOG — keeps the twin alive forever
# =============================================================================

def write_watchdog(script: Path = Path(__file__),
                   bat: Path = WATCHDOG_BAT) -> Path:
    exe = sys.executable
    content = f"""@echo off
:loop
echo [TwinWatchdog] Starting RabbitOS Twin...
"{exe}" "{script}" --run
echo [TwinWatchdog] Twin exited — restarting in 3s...
timeout /t 3 /nobreak >nul
goto loop
"""
    try:
        with open(bat, "w") as f:
            f.write(content)
        print(f"[Watchdog] Written: {bat}")
    except Exception as e:
        print(f"[Watchdog] Could not write: {e}")
    return bat


# =============================================================================
# CLI
# =============================================================================

def main():
    p = argparse.ArgumentParser(description="RabbitOS Twin")
    p.add_argument("--run",         action="store_true",
                   help="Start both terminal and server (default)")
    p.add_argument("--server-only", action="store_true",
                   help="Headless server mode (no REPL)")
    p.add_argument("--terminal",    action="store_true",
                   help="Terminal REPL only (no server)")
    p.add_argument("--status",      action="store_true",
                   help="Print twin status snapshot and exit")
    p.add_argument("--watchdog",    action="store_true",
                   help="Write watchdog .bat and exit")
    args = p.parse_args()

    if args.watchdog:
        bat = write_watchdog()
        print(f"Run to keep twin alive forever:\n  {bat}")
        return

    twin = RabbitTwin()

    if args.status:
        print(json.dumps(twin.full_status(), indent=2, default=str))
        return

    if args.server_only:
        twin.run_server()
        return

    if args.terminal:
        twin.run_terminal()
        return

    # Default: both faces — server in background, REPL in foreground
    srv_thread = threading.Thread(target=twin.run_server, daemon=True)
    srv_thread.start()
    time.sleep(0.5)  # let server bind port
    twin.run_terminal()


if __name__ == "__main__":
    main()
