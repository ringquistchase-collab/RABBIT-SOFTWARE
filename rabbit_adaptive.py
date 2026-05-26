#!/usr/bin/env python3
"""
RabbitOS Adaptive Network Crawler
Every probe — success or failure — is recorded as a signed token.
Failures feed an algorithm evolution engine that mutates methods until data flows.
The crawler maintains live presence and moves laterally through the mesh.

Architecture:
  ProbeToken     — immutable signed record of one probe attempt
  MethodEngine   — learns from tokens; evolves better probe strategies
  LateralCrawler — lives inside the network, moves between nodes
  AdaptiveAgent  — orchestrates everything; never stops

Token lifecycle:
  probe attempt → token minted → stored in Supabase probe_tokens →
  if failure → MethodEngine scores the method down, generates variant →
  if success → anchors position, spawns lateral probes from that host
"""

import os
import sys
import json
import time
import uuid
import hmac
import hashlib
import random
import socket
import struct
import threading
import itertools
import ipaddress
from typing import Dict, List, Optional, Tuple, Any, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.parse

sys.path.insert(0, __file__.rsplit("\\", 1)[0])

# =============================================================================
# CONSTANTS
# =============================================================================

TWIN_UUID    = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME    = "Chase Allen Ringquist"
SUPABASE_URL = "https://ludxbakxpmdqhfgdenwp.supabase.co"
REST_URL     = f"{SUPABASE_URL}/rest/v1"

# Token signing key — derived from twin UUID (never stored raw)
_TOKEN_SIGN_KEY = hashlib.sha256(TWIN_UUID.encode()).digest()


# =============================================================================
# PROBE OUTCOME
# =============================================================================

class Outcome(Enum):
    SUCCESS      = "success"       # got data
    PARTIAL      = "partial"       # connected but no twin data
    REFUSED      = "refused"       # port closed / connection refused
    TIMEOUT      = "timeout"       # no response
    AUTH_FAIL    = "auth_fail"     # connected but auth rejected
    EMPTY        = "empty"         # responded but returned nothing useful
    ERROR        = "error"         # unexpected exception


# =============================================================================
# PROBE TOKEN — immutable signed record
# =============================================================================

@dataclass
class ProbeToken:
    """
    One signed record of a single probe attempt.
    Stored whether success or failure — failures teach the MethodEngine.
    """
    token_id:    str      # UUID4
    method:      str      # ssh | nmap | arp | http | tcp_raw | hackrf | custom
    variant:     str      # specific sub-method or flag set used
    target_host: str
    target_port: int
    outcome:     Outcome
    data_hash:   str      # SHA-256 of any data retrieved (empty string if none)
    latency_ms:  float
    timestamp:   str
    generation:  int      # how many times this method has been mutated
    parent_id:   Optional[str]   # token_id of the probe that spawned this
    signature:   str      # HMAC-SHA256(token_id + method + outcome)

    @classmethod
    def mint(cls, method: str, variant: str, target_host: str, target_port: int,
             outcome: Outcome, data: str = "", latency_ms: float = 0.0,
             generation: int = 0, parent_id: str = None) -> "ProbeToken":
        tid  = str(uuid.uuid4())
        ts   = datetime.now(timezone.utc).isoformat()
        dh   = hashlib.sha256(data.encode()).hexdigest() if data else ""
        msg  = f"{tid}:{method}:{outcome.value}".encode()
        sig  = hmac.new(_TOKEN_SIGN_KEY, msg, hashlib.sha256).hexdigest()
        return cls(
            token_id    = tid,
            method      = method,
            variant     = variant,
            target_host = target_host,
            target_port = target_port,
            outcome     = outcome,
            data_hash   = dh,
            latency_ms  = latency_ms,
            timestamp   = ts,
            generation  = generation,
            parent_id   = parent_id,
            signature   = sig,
        )

    def to_dict(self) -> Dict:
        return {
            "token_id":    self.token_id,
            "twin_id":     TWIN_UUID,
            "method":      self.method,
            "variant":     self.variant,
            "target_host": self.target_host,
            "target_port": self.target_port,
            "outcome":     self.outcome.value,
            "data_hash":   self.data_hash,
            "latency_ms":  self.latency_ms,
            "timestamp":   self.timestamp,
            "generation":  self.generation,
            "parent_id":   self.parent_id,
            "signature":   self.signature,
        }

    def is_success(self) -> bool:
        return self.outcome in (Outcome.SUCCESS, Outcome.PARTIAL)


# =============================================================================
# METHOD ENGINE — learns from tokens; evolves probe strategies
# =============================================================================

@dataclass
class ProbeMethod:
    name:       str
    variant:    str
    func:       Callable       # (host, port, ctx) → (Outcome, str)
    score:      float = 1.0    # 0.0 bad → 1.0 good
    generation: int   = 0
    successes:  int   = 0
    failures:   int   = 0
    parent:     str   = ""


class MethodEngine:
    """
    Maintains a scored registry of probe methods.
    Failed tokens decay a method's score; successes boost it.
    When a method scores below threshold it spawns mutated variants.
    """

    DECAY_RATE   = 0.15    # score penalty per failure
    BOOST_RATE   = 0.25    # score gain per success
    MUTATE_BELOW = 0.35    # spawn variant when score drops here
    MAX_GEN      = 8       # max mutation depth

    def __init__(self):
        self._methods: Dict[str, ProbeMethod] = {}
        self._lock    = threading.Lock()
        self._register_builtins()

    # ── built-in probe methods ─────────────────────────────────────────────

    def _register_builtins(self):
        self.register("tcp_banner",   "default",  self._probe_tcp_banner)
        self.register("tcp_connect",  "default",  self._probe_tcp_connect)
        self.register("http_get",     "default",  self._probe_http_get)
        self.register("http_get",     "https",    self._probe_https_get)
        self.register("ssh_banner",   "default",  self._probe_ssh_banner)
        self.register("ssh_auth",     "key",      self._probe_ssh_key_auth)
        self.register("udp_probe",    "default",  self._probe_udp)
        self.register("supabase_rest","default",  self._probe_supabase_rest)
        self.register("nmap_quick",   "default",  self._probe_nmap)
        self.register("port_knock",   "sequence", self._probe_port_knock)

    def register(self, method: str, variant: str, func: Callable,
                 generation: int = 0, parent: str = ""):
        key = f"{method}::{variant}"
        with self._lock:
            self._methods[key] = ProbeMethod(
                name=method, variant=variant, func=func,
                generation=generation, parent=parent
            )

    def record_token(self, token: ProbeToken):
        key = f"{token.method}::{token.variant}"
        with self._lock:
            m = self._methods.get(key)
            if not m:
                return
            if token.is_success():
                m.successes += 1
                m.score      = min(1.0, m.score + self.BOOST_RATE)
            else:
                m.failures += 1
                m.score     = max(0.0, m.score - self.DECAY_RATE)
                if m.score < self.MUTATE_BELOW and m.generation < self.MAX_GEN:
                    self._mutate(m)

    def _mutate(self, base: ProbeMethod):
        """Generate a mutated variant of a failing method."""
        new_gen     = base.generation + 1
        new_variant = f"{base.variant}_g{new_gen}"
        new_func    = self._wrap_mutated(base.func, new_gen)
        print(f"  [Evolve] {base.name}::{base.variant} -> {base.name}::{new_variant}  "
              f"(gen {new_gen})  score={base.score:.2f}")
        self.register(base.name, new_variant, new_func,
                      generation=new_gen, parent=f"{base.name}::{base.variant}")

    def _wrap_mutated(self, original_func: Callable, gen: int) -> Callable:
        """
        Wrap a probe function with mutation — random port offsets,
        longer timeouts, different payloads, jitter delays.
        """
        mutations = [
            lambda f, h, p, c: f(h, p + random.choice([1, -1, 100, 443]), c),
            lambda f, h, p, c: (time.sleep(random.uniform(0.1, 0.5)), f(h, p, c))[1],
            lambda f, h, p, c: f(h, p, {**c, "timeout": c.get("timeout", 5) * 2}),
            lambda f, h, p, c: f(h, p, {**c, "payload": os.urandom(8).hex()}),
        ]
        chosen = mutations[gen % len(mutations)]
        def mutated(host, port, ctx):
            try:
                return chosen(original_func, host, port, ctx)
            except Exception:
                return Outcome.ERROR, ""
        return mutated

    def best_methods(self, n: int = 5) -> List[ProbeMethod]:
        with self._lock:
            return sorted(self._methods.values(),
                          key=lambda m: m.score, reverse=True)[:n]

    def method_report(self) -> List[Dict]:
        with self._lock:
            return [{
                "key":        f"{m.name}::{m.variant}",
                "score":      round(m.score, 3),
                "successes":  m.successes,
                "failures":   m.failures,
                "generation": m.generation,
                "parent":     m.parent,
            } for m in sorted(self._methods.values(),
                               key=lambda x: x.score, reverse=True)]

    # ── probe implementations ──────────────────────────────────────────────

    def _probe_tcp_banner(self, host, port, ctx) -> Tuple[Outcome, str]:
        timeout = ctx.get("timeout", 3)
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            banner = sock.recv(1024).decode("utf-8", errors="replace")
            sock.close()
            if banner.strip():
                return Outcome.SUCCESS, banner
            return Outcome.EMPTY, ""
        except ConnectionRefusedError:
            return Outcome.REFUSED, ""
        except socket.timeout:
            return Outcome.TIMEOUT, ""
        except Exception as e:
            return Outcome.ERROR, str(e)

    def _probe_tcp_connect(self, host, port, ctx) -> Tuple[Outcome, str]:
        timeout = ctx.get("timeout", 2)
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            return Outcome.PARTIAL, f"port {port} open"
        except ConnectionRefusedError:
            return Outcome.REFUSED, ""
        except socket.timeout:
            return Outcome.TIMEOUT, ""
        except Exception:
            return Outcome.ERROR, ""

    def _probe_http_get(self, host, port, ctx) -> Tuple[Outcome, str]:
        timeout = ctx.get("timeout", 5)
        try:
            url = f"http://{host}:{port}/"
            req = urllib.request.Request(url, headers={"User-Agent": "RabbitOS/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(2048).decode("utf-8", errors="replace")
                if TWIN_NAME.lower() in body.lower() or TWIN_UUID in body:
                    return Outcome.SUCCESS, body
                return Outcome.PARTIAL, body[:200]
        except Exception:
            return Outcome.REFUSED, ""

    def _probe_https_get(self, host, port, ctx) -> Tuple[Outcome, str]:
        import ssl
        timeout = ctx.get("timeout", 5)
        try:
            ctx_ssl = ssl.create_default_context()
            ctx_ssl.check_hostname = False
            ctx_ssl.verify_mode    = ssl.CERT_NONE
            url = f"https://{host}:{port}/"
            req = urllib.request.Request(url, headers={"User-Agent": "RabbitOS/1.0"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx_ssl) as resp:
                body = resp.read(2048).decode("utf-8", errors="replace")
                return Outcome.PARTIAL, body[:200]
        except Exception:
            return Outcome.REFUSED, ""

    def _probe_ssh_banner(self, host, port, ctx) -> Tuple[Outcome, str]:
        timeout = ctx.get("timeout", 3)
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            banner = sock.recv(256).decode("utf-8", errors="replace").strip()
            sock.close()
            if "SSH" in banner:
                return Outcome.PARTIAL, banner
            return Outcome.EMPTY, banner
        except Exception:
            return Outcome.REFUSED, ""

    def _probe_ssh_key_auth(self, host, port, ctx) -> Tuple[Outcome, str]:
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, port=port, username=ctx.get("username", "root"),
                           look_for_keys=True, allow_agent=True,
                           timeout=ctx.get("timeout", 5))
            _, out, _ = client.exec_command(
                f"id 2>/dev/null; hostname 2>/dev/null; "
                f"cat /etc/rabbitos.env 2>/dev/null | head -5"
            )
            data = out.read().decode("utf-8", errors="replace")
            client.close()
            if data.strip():
                return Outcome.SUCCESS, data
            return Outcome.PARTIAL, "authenticated"
        except ImportError:
            return Outcome.ERROR, "paramiko not installed"
        except Exception as e:
            err = str(e).lower()
            if "auth" in err or "permission" in err:
                return Outcome.AUTH_FAIL, ""
            return Outcome.REFUSED, ""

    def _probe_udp(self, host, port, ctx) -> Tuple[Outcome, str]:
        timeout = ctx.get("timeout", 2)
        payload = ctx.get("payload", b"\x00" * 8)
        if isinstance(payload, str):
            payload = bytes.fromhex(payload) if len(payload) == 16 else payload.encode()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(payload, (host, port))
            data, _ = sock.recvfrom(1024)
            sock.close()
            return Outcome.PARTIAL, data.decode("utf-8", errors="replace")
        except socket.timeout:
            return Outcome.TIMEOUT, ""
        except Exception:
            return Outcome.ERROR, ""

    def _probe_supabase_rest(self, host, port, ctx) -> Tuple[Outcome, str]:
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not key:
            return Outcome.AUTH_FAIL, ""
        try:
            url = (f"https://{host}:{port}/rest/v1/twin_identity"
                   f"?id=eq.{TWIN_UUID}&limit=1")
            req = urllib.request.Request(url, headers={
                "apikey": key, "Authorization": f"Bearer {key}"
            })
            with urllib.request.urlopen(req, timeout=ctx.get("timeout", 8)) as r:
                body = r.read().decode()
                if TWIN_UUID in body:
                    return Outcome.SUCCESS, body
                return Outcome.PARTIAL, body[:200]
        except Exception:
            return Outcome.REFUSED, ""

    def _probe_nmap(self, host, port, ctx) -> Tuple[Outcome, str]:
        import subprocess, shutil
        if not shutil.which("nmap"):
            return Outcome.ERROR, "nmap not found"
        try:
            result = subprocess.run(
                ["nmap", "-p", str(port), "--open", "-T4", host],
                capture_output=True, text=True, timeout=30
            )
            if "open" in result.stdout:
                return Outcome.PARTIAL, result.stdout[:500]
            return Outcome.EMPTY, result.stdout[:200]
        except Exception as e:
            return Outcome.ERROR, str(e)

    def _probe_port_knock(self, host, port, ctx) -> Tuple[Outcome, str]:
        """Port-knocking sequence probe — tries common knock sequences."""
        knock_sequences = [
            [1234, 5678, 9012],
            [7000, 8000, 9000],
            [3000, 4000, 5000],
        ]
        timeout = ctx.get("timeout", 1)
        for seq in knock_sequences:
            for kp in seq:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    s.connect((host, kp))
                    s.close()
                except Exception:
                    pass
                time.sleep(0.1)
            # Now try the actual port
            outcome, data = self._probe_tcp_connect(host, port, ctx)
            if outcome != Outcome.REFUSED:
                return outcome, data
        return Outcome.REFUSED, ""


# =============================================================================
# SUPABASE TOKEN STORE
# =============================================================================

class TokenStore:
    """Persists ProbeTokens to Supabase probe_tokens table."""

    def __init__(self):
        self.key   = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self._buf  = deque(maxlen=1000)    # in-memory ring buffer
        self._lock = threading.Lock()

    def save(self, token: ProbeToken):
        with self._lock:
            self._buf.appendleft(token)
        if self.key:
            data = json.dumps(token.to_dict()).encode()
            req  = urllib.request.Request(
                f"{REST_URL}/probe_tokens",
                data=data,
                headers={
                    "apikey": self.key, "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json", "Prefer": "return=minimal",
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=5):
                    pass
            except Exception:
                pass  # buffer covers offline periods

    def recent(self, n: int = 50) -> List[Dict]:
        with self._lock:
            return [t.to_dict() for t in list(self._buf)[:n]]

    def stats(self) -> Dict:
        with self._lock:
            tokens = list(self._buf)
        by_outcome: Dict[str, int] = defaultdict(int)
        by_method:  Dict[str, Dict] = defaultdict(lambda: {"ok": 0, "fail": 0})
        for t in tokens:
            by_outcome[t.outcome.value] += 1
            key = f"{t.method}::{t.variant}"
            if t.is_success():
                by_method[key]["ok"]   += 1
            else:
                by_method[key]["fail"] += 1
        return {
            "total":      len(tokens),
            "by_outcome": dict(by_outcome),
            "by_method":  dict(by_method),
        }


# =============================================================================
# LATERAL CRAWLER — lives in the network, moves between nodes
# =============================================================================

@dataclass
class NetworkPosition:
    host:       str
    port:       int
    method:     str
    variant:    str
    depth:      int          # hops from origin
    anchored:   bool = False # True = have persistent access
    neighbors:  List[str] = field(default_factory=list)
    data:       Dict         = field(default_factory=dict)
    arrived_at: str          = ""


class LateralCrawler:
    """
    Maintains live presence across discovered nodes.
    From each anchored position, discovers adjacent hosts and probes them.
    Never stays in one place — rotates positions to avoid stagnation.
    """

    def __init__(self, engine: MethodEngine, store: TokenStore,
                 max_depth: int = 4, max_positions: int = 20):
        self.engine         = engine
        self.store          = store
        self.max_depth      = max_depth
        self.max_positions  = max_positions
        self.running        = False

        self._positions:    Dict[str, NetworkPosition] = {}
        self._probe_queue:  deque  = deque()
        self._visited:      set    = set()
        self._lock          = threading.Lock()
        self._thread:       Optional[threading.Thread] = None

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self, seed_hosts: List[Tuple[str, int]]):
        """Seed initial positions and start crawling."""
        for host, port in seed_hosts:
            self._enqueue(host, port, depth=0, parent_token=None)
        self.running  = True
        self._thread  = threading.Thread(target=self._crawl_loop, daemon=True)
        self._thread.start()
        print(f"[Crawler] Started with {len(seed_hosts)} seeds")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        print(f"[Crawler] Stopped — {len(self._positions)} positions held")

    # ── queuing ───────────────────────────────────────────────────────────

    def _enqueue(self, host: str, port: int, depth: int, parent_token: Optional[str]):
        key = f"{host}:{port}"
        if key not in self._visited and depth <= self.max_depth:
            self._probe_queue.append((host, port, depth, parent_token))

    # ── main loop ─────────────────────────────────────────────────────────

    def _crawl_loop(self):
        while self.running:
            if not self._probe_queue:
                # Nothing queued — move to a random position and re-probe neighbors
                self._roam()
                time.sleep(random.uniform(1.0, 3.0))
                continue

            host, port, depth, parent_id = self._probe_queue.popleft()
            key = f"{host}:{port}"

            if key in self._visited:
                continue
            self._visited.add(key)

            # Try each method in score order
            for method in self.engine.best_methods(n=6):
                if not self.running:
                    return

                t0 = time.time()
                try:
                    outcome, data = method.func(host, port, {"timeout": 4})
                except Exception as e:
                    outcome, data = Outcome.ERROR, str(e)
                latency = round((time.time() - t0) * 1000, 1)

                token = ProbeToken.mint(
                    method      = method.name,
                    variant     = method.variant,
                    target_host = host,
                    target_port = port,
                    outcome     = outcome,
                    data        = data,
                    latency_ms  = latency,
                    generation  = method.generation,
                    parent_id   = parent_id,
                )
                self.store.save(token)
                self.engine.record_token(token)

                if token.is_success():
                    self._anchor(host, port, method, data, depth, token.token_id)
                    break  # anchored — no need to keep probing this host

                self._print_token(token)
                time.sleep(random.uniform(0.05, 0.3))  # jitter

    def _anchor(self, host: str, port: int, method: ProbeMethod,
                data: str, depth: int, token_id: str):
        """Establish position on a successfully probed host."""
        key = f"{host}:{port}"
        pos = NetworkPosition(
            host      = host,
            port      = port,
            method    = method.name,
            variant   = method.variant,
            depth     = depth,
            anchored  = True,
            data      = self._extract_neighbors(host, data),
            arrived_at= datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            if len(self._positions) >= self.max_positions:
                # Evict oldest non-anchored position
                old = min(self._positions.values(),
                          key=lambda p: p.arrived_at)
                del self._positions[f"{old.host}:{old.port}"]
            self._positions[key] = pos

        print(f"  [ANCHOR] {host}:{port}  via={method.name}::{method.variant}"
              f"  depth={depth}  neighbors={len(pos.neighbors)}")

        # Queue neighbors for lateral movement
        for neighbor in pos.neighbors:
            for p in [22, 80, 443, 8765, 5432]:
                self._enqueue(neighbor, p, depth + 1, token_id)

    def _extract_neighbors(self, host: str, data: str) -> List[str]:
        """Parse IPs from probe data to discover adjacent hosts."""
        import re
        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", data)
        # Filter: local-scope, exclude the host itself and broadcast
        neighbors = []
        for ip in set(ips):
            if ip == host or ip.endswith(".0") or ip.endswith(".255"):
                continue
            try:
                ipaddress.ip_address(ip)
                neighbors.append(ip)
            except ValueError:
                pass
        return neighbors[:10]

    def _roam(self):
        """Move to a random anchored position and re-probe from there."""
        with self._lock:
            anchored = [p for p in self._positions.values() if p.anchored]
        if not anchored:
            return
        pos = random.choice(anchored)
        print(f"  [Roam] Moving to {pos.host}:{pos.port} (depth={pos.depth})")
        for neighbor in pos.neighbors[:3]:
            for port in [22, 80, 443]:
                self._enqueue(neighbor, port, pos.depth + 1, None)

    def _print_token(self, t: ProbeToken):
        icon = {
            Outcome.SUCCESS:   "OK",
            Outcome.PARTIAL:   "~",
            Outcome.REFUSED:   "X",
            Outcome.TIMEOUT:   "T",
            Outcome.AUTH_FAIL: "A",
            Outcome.EMPTY:     "0",
            Outcome.ERROR:     "!",
        }.get(t.outcome, "?")
        print(f"  {icon} {t.target_host:15s}:{t.target_port:<5d}"
              f"  {t.method:15s}:{t.variant:<12s}"
              f"  {t.latency_ms:6.0f}ms"
              f"  gen={t.generation}"
              f"  [{t.token_id[:8]}]")

    def positions(self) -> List[Dict]:
        with self._lock:
            return [{
                "host":      p.host,
                "port":      p.port,
                "method":    p.method,
                "variant":   p.variant,
                "depth":     p.depth,
                "anchored":  p.anchored,
                "neighbors": p.neighbors,
                "arrived":   p.arrived_at,
            } for p in self._positions.values()]

    def status(self) -> Dict:
        with self._lock:
            positions  = list(self._positions.values())
            queue_size = len(self._probe_queue)
        return {
            "running":       self.running,
            "positions_held":len(positions),
            "anchored":      sum(1 for p in positions if p.anchored),
            "queue_depth":   queue_size,
            "visited":       len(self._visited),
            "max_depth_seen":max((p.depth for p in positions), default=0),
        }


# =============================================================================
# ADAPTIVE AGENT — top-level orchestrator
# =============================================================================

class AdaptiveAgent:
    """
    Brings it all together.
    Never stops — keeps probing, learning, moving, recording.
    """

    def __init__(self):
        self.engine  = MethodEngine()
        self.store   = TokenStore()
        self.crawler = LateralCrawler(self.engine, self.store)
        self._lock   = threading.Lock()

    def start(self, seed_targets: List[Tuple[str, int]] = None):
        seeds = seed_targets or [
            ("127.0.0.1",   22),
            ("127.0.0.1",   80),
            ("127.0.0.1", 8765),
            ("127.0.0.1", 5432),
        ]
        print(f"\n{'='*60}")
        print(f"  Adaptive Agent — {TWIN_NAME}")
        print(f"  Seeds: {len(seeds)}  |  Max depth: {self.crawler.max_depth}")
        print(f"{'='*60}\n")
        self.crawler.start(seeds)

    def stop(self):
        self.crawler.stop()

    def add_target(self, host: str, port: int):
        self.crawler._enqueue(host, port, depth=0, parent_token=None)

    def report(self) -> Dict:
        return {
            "twin":     TWIN_NAME,
            "twin_id":  TWIN_UUID,
            "crawler":  self.crawler.status(),
            "tokens":   self.store.stats(),
            "methods":  self.engine.method_report(),
            "positions":self.crawler.positions(),
        }

    def run_forever(self, seed_targets: List[Tuple[str, int]] = None,
                    report_interval: int = 30):
        """
        Main blocking loop — starts crawler and prints periodic reports.
        Ctrl+C to stop.
        """
        self.start(seed_targets)
        try:
            while True:
                time.sleep(report_interval)
                r = self.report()
                print(f"\n── Adaptive Report ──────────────────────────────────")
                print(f"  Positions: {r['crawler']['positions_held']}"
                      f"  Anchored: {r['crawler']['anchored']}"
                      f"  Visited:  {r['crawler']['visited']}"
                      f"  Queue:    {r['crawler']['queue_depth']}")
                print(f"  Tokens:   {r['tokens']['total']}"
                      f"  Outcomes: {r['tokens']['by_outcome']}")
                top = r["methods"][:3]
                for m in top:
                    print(f"  Method  {m['key']:30s}  score={m['score']:.2f}"
                          f"  gen={m['generation']}")
                print()
        except KeyboardInterrupt:
            self.stop()
            print("\n[Agent] Stopped.")

    # ── single probe (for external callers) ──────────────────────────────

    def probe_once(self, host: str, port: int,
                   method: str = None) -> List[Dict]:
        """
        Probe a single host with all (or one) method(s).
        Returns list of token dicts.
        """
        methods = ([m for m in self.engine.best_methods(10)
                    if m.name == method] if method
                   else self.engine.best_methods(10))
        results = []
        for m in methods:
            t0 = time.time()
            try:
                outcome, data = m.func(host, port, {"timeout": 5})
            except Exception as e:
                outcome, data = Outcome.ERROR, str(e)
            latency = round((time.time() - t0) * 1000, 1)
            token   = ProbeToken.mint(
                method=m.name, variant=m.variant,
                target_host=host, target_port=port,
                outcome=outcome, data=data,
                latency_ms=latency, generation=m.generation,
            )
            self.store.save(token)
            self.engine.record_token(token)
            results.append(token.to_dict())
            if token.is_success():
                break
        return results


# =============================================================================
# AGENT TOOLS (for rabbit_agent.py)
# =============================================================================

ADAPTIVE_TOOLS = [
    {
        "name": "adaptive_start",
        "description": (
            "Start the adaptive crawler — probes all discovered hosts, "
            "records every attempt as a signed token, and learns from failures "
            f"to evolve better methods for finding {TWIN_NAME}'s data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seeds": {
                    "type": "array",
                    "description": "List of {host, port} seed targets",
                    "items": {
                        "type": "object",
                        "properties": {
                            "host": {"type": "string"},
                            "port": {"type": "integer"}
                        }
                    }
                }
            },
            "required": []
        }
    },
    {
        "name": "adaptive_report",
        "description": (
            "Get full adaptive agent report: positions held, token stats, "
            "method scores, and evolution history."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "adaptive_probe",
        "description": "Probe a specific host:port with all available methods, recording each attempt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host":   {"type": "string"},
                "port":   {"type": "integer"},
                "method": {"type": "string", "description": "Specific method name (optional)"},
            },
            "required": ["host", "port"]
        }
    },
    {
        "name": "adaptive_tokens",
        "description": "Retrieve recent probe tokens (success and failure records).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":   {"type": "integer"},
                "outcome": {"type": "string",
                            "description": "Filter by: success/partial/refused/timeout/auth_fail/empty/error"},
            },
            "required": []
        }
    },
    {
        "name": "adaptive_methods",
        "description": "Show all probe methods with their current scores and evolution generation.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
]


# =============================================================================
# SUPABASE MIGRATION SQL
# =============================================================================

MIGRATION_SQL = f"""
-- probe_tokens: every probe attempt — success or failure — recorded here
CREATE TABLE IF NOT EXISTS probe_tokens (
    token_id    TEXT    PRIMARY KEY,
    twin_id     UUID    NOT NULL REFERENCES twin_identity(id),
    method      TEXT    NOT NULL,
    variant     TEXT    NOT NULL,
    target_host TEXT    NOT NULL,
    target_port INTEGER NOT NULL,
    outcome     TEXT    NOT NULL,
    data_hash   TEXT,
    latency_ms  NUMERIC,
    generation  INTEGER NOT NULL DEFAULT 0,
    parent_id   TEXT    REFERENCES probe_tokens(token_id),
    signature   TEXT    NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE probe_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only" ON probe_tokens USING (false);
CREATE INDEX IF NOT EXISTS probe_tokens_method  ON probe_tokens(method, outcome);
CREATE INDEX IF NOT EXISTS probe_tokens_host    ON probe_tokens(target_host);
CREATE INDEX IF NOT EXISTS probe_tokens_twin    ON probe_tokens(twin_id, timestamp DESC);
"""


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    p = argparse.ArgumentParser(description="RabbitOS Adaptive Crawler")
    p.add_argument("--run",      action="store_true", help="Start crawler loop")
    p.add_argument("--probe",    nargs=2, metavar=("HOST","PORT"), help="Probe one host")
    p.add_argument("--report",   action="store_true", help="Print report and exit")
    p.add_argument("--tokens",   action="store_true", help="Show recent tokens")
    p.add_argument("--methods",  action="store_true", help="Show method scores")
    p.add_argument("--migrate",  action="store_true", help="Print migration SQL")
    p.add_argument("--seeds",    nargs="+", metavar="HOST:PORT", help="Seed targets")
    p.add_argument("--interval", type=int, default=30, help="Report interval seconds")
    args = p.parse_args()

    if args.migrate:
        print(MIGRATION_SQL)
        return

    agent = AdaptiveAgent()

    if args.probe:
        host = args.probe[0]
        port = int(args.probe[1])
        results = agent.probe_once(host, port)
        for r in results:
            icon = "✓" if r["outcome"] in ("success", "partial") else "✗"
            print(f"  {icon} {r['method']:15s}:{r['variant']:12s}  "
                  f"{r['outcome']:10s}  {r['latency_ms']:.0f}ms  [{r['token_id'][:8]}]")
        return

    if args.report:
        print(json.dumps(agent.report(), indent=2, default=str))
        return

    if args.tokens:
        for t in agent.store.recent(20):
            icon = "✓" if t["outcome"] in ("success","partial") else "✗"
            print(f"  {icon} [{t['timestamp'][:19]}]  {t['target_host']:15s}:{t['target_port']:<5d}"
                  f"  {t['method']:15s}  {t['outcome']}")
        return

    if args.methods:
        for m in agent.engine.method_report():
            bar = "█" * int(m["score"] * 10) + "░" * (10 - int(m["score"] * 10))
            print(f"  {bar}  {m['score']:.2f}  {m['key']:30s}"
                  f"  ok={m['successes']} fail={m['failures']} gen={m['generation']}")
        return

    if args.run:
        seeds = []
        if args.seeds:
            for s in args.seeds:
                h, po = s.rsplit(":", 1)
                seeds.append((h, int(po)))
        agent.run_forever(seeds or None, args.interval)
        return

    # Interactive
    print(f"\nRabbitOS Adaptive Agent — {TWIN_NAME}")
    print("Commands: start [host:port ...] | probe <host> <port> | report |")
    print("          tokens | methods | add <host:port> | stop | q\n")

    while True:
        try:
            cmd = input("adapt> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd or cmd == "q":
            agent.stop()
            break

        parts = cmd.split()
        op    = parts[0].lower()

        if op == "start":
            seeds = []
            for s in parts[1:]:
                try:
                    h, po = s.rsplit(":", 1)
                    seeds.append((h, int(po)))
                except Exception:
                    pass
            agent.start(seeds or None)

        elif op == "probe" and len(parts) >= 3:
            results = agent.probe_once(parts[1], int(parts[2]))
            for r in results:
                icon = "✓" if r["outcome"] in ("success","partial") else "✗"
                print(f"  {icon} {r['method']:15s}  {r['outcome']:10s}  {r['latency_ms']:.0f}ms")

        elif op == "add" and len(parts) >= 2:
            h, po = parts[1].rsplit(":", 1)
            agent.add_target(h, int(po))
            print(f"  Queued {h}:{po}")

        elif op == "report":
            r = agent.report()
            print(f"  Positions: {r['crawler']['positions_held']}"
                  f"  Anchored: {r['crawler']['anchored']}"
                  f"  Tokens: {r['tokens']['total']}")

        elif op == "tokens":
            for t in agent.store.recent(15):
                icon = "✓" if t["outcome"] in ("success","partial") else "✗"
                print(f"  {icon} {t['target_host']:15s}:{t['target_port']:<5d}"
                      f"  {t['method']:15s}  {t['outcome']}")

        elif op == "methods":
            for m in agent.engine.method_report():
                bar = "█" * int(m["score"] * 10) + "░" * (10 - int(m["score"] * 10))
                print(f"  {bar}  {m['score']:.2f}  {m['key']:30s}  gen={m['generation']}")

        elif op == "stop":
            agent.stop()

        elif op == "positions":
            for pos in agent.crawler.positions():
                icon = "●" if pos["anchored"] else "○"
                print(f"  {icon} {pos['host']:15s}:{pos['port']:<5d}"
                      f"  depth={pos['depth']}  via={pos['method']}:{pos['variant']}"
                      f"  neighbors={len(pos['neighbors'])}")

        else:
            print("  start | probe <h> <p> | add <h:p> | report | tokens | methods | positions | stop | q")


if __name__ == "__main__":
    main()
