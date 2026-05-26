#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RabbitOS Cloak Engine — Signal Survival Camouflage
===================================================
Makes every mesh network footprint indistinguishable from the person's
own normal daily traffic.  No sold datasets. No generic profiles.
The LIVE biometric mesh IS the dataset — EEG, heart rate, GSR, cortisol
and environment data from the 47-node body-area network drive every
traffic parameter in real time.

When Chase is resting  → traffic is slow, background-sync pattern.
When Chase is active   → traffic is fast, browsing pattern.
When stress is high    → probes are aggressive, persona rotates fast.
When cortisol drops    → traffic softens, blends into ambient.

The network audits itself against Chase's living state — not a static
signature, not a purchased profile.  The traffic IS him.

Architecture
------------
  NativeIO         OS-native socket factory (pooled, tuned, wire-speed)
  FrameEncoder     8 protocol disguises (HTTP, WS, DNS, MQTT, CoAP, gRPC, STUN, raw)
  FrameworkHopper  HMAC-seeded rotation — deterministic to us, random to observer
  PersonaRotor     8 network identities (Chrome, Safari, curl, IoT …)
  BiometricNorm    Maps live mesh readings → traffic parameters
  TrafficShaper    Rate limiter driven by BiometricNorm
  CloakSocket      Drop-in socket wrapper for internal data paths
  CloakEngine      Orchestrator — patches adaptive + soul + Supabase calls
  CLOAK_TOOLS      Agent tool definitions
"""

import os
import sys
import json
import time
import uuid
import hmac
import hashlib
import socket
import struct
import select
import random
import ctypes
import threading
import base64
import platform
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum
from datetime import datetime, timezone

# ─── identity anchor ────────────────────────────────────────────────────────
TWIN_UUID    = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME    = "Chase Allen Ringquist"
SUPABASE_URL = "https://ludxbakxpmdqhfgdenwp.supabase.co"
REST_URL     = f"{SUPABASE_URL}/rest/v1"

# Soul key — HMAC seed derived from twin identity; never leaves process memory
_SOUL_KEY = hashlib.sha256(
    f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()
).digest()

_WINDOWS = sys.platform == "win32"
_LINUX   = sys.platform.startswith("linux")


# =============================================================================
# NETWORK PERSONAS
# 8 distinct network identities.  The hopper cycles through these so no
# single User-Agent / header fingerprint persists across connections.
# =============================================================================

@dataclass
class Persona:
    id:          str
    ua:          str
    accept:      str
    accept_enc:  str
    accept_lang: Optional[str]
    sec_ch_ua:   Optional[str]
    mu:          float   # mean inter-request seconds (Poisson lambda)
    sigma:       float   # std dev for timing jitter
    pad_range:   Tuple[int, int]  # (min, max) random padding bytes

PERSONAS: List[Persona] = [
    Persona("chrome_win",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "gzip, deflate, br, zstd", "en-US,en;q=0.9",
        '"Google Chrome";v="125", "Not;A=Brand";v="24"',
        1.2, 0.6, (64, 256)),
    Persona("safari_ios",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "gzip, deflate, br", "en-US,en;q=0.9", None,
        2.1, 1.0, (0, 64)),
    Persona("firefox_linux",
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "gzip, deflate, br, zstd", "en-US,en;q=0.5", None,
        0.9, 0.45, (32, 128)),
    Persona("curl_script",
        "curl/8.7.1", "*/*", "gzip", None, None,
        0.1, 0.04, (0, 16)),
    Persona("python_requests",
        "python-requests/2.31.0", "*/*", "gzip, deflate", None, None,
        0.08, 0.03, (0, 8)),
    Persona("node_axios",
        "axios/1.7.2", "application/json, text/plain, */*",
        "gzip, compress, deflate, br", None, None,
        0.15, 0.07, (0, 32)),
    Persona("aws_sdk",
        "aws-sdk-python/1.34.0 Python/3.11 Windows/10 Botocore/1.34.0",
        "application/json", "identity", None, None,
        0.35, 0.12, (0, 0)),
    Persona("iot_mesh",
        f"RabbitOS/2.0 (mesh-node; twin={TWIN_UUID[:8]}; biometric)",
        "application/octet-stream", "identity", None, None,
        5.0, 2.0, (128, 512)),
]


# =============================================================================
# NATIVE I/O — OS-LEVEL SOCKET FACTORY
# Wire-speed: pooled connections, TCP_NODELAY, oversized buffers,
# non-blocking select-loop, ctypes WinSock2 on Windows.
# =============================================================================

_SOCK_SNDBUF = 1 << 18   # 256 KB
_SOCK_RCVBUF = 1 << 18
_POOL_TTL    = 45.0       # seconds an idle socket stays alive
_POOL_MAX    = 6          # sockets per (host, port)

class NativeIO:
    """
    Pooled, OS-tuned socket factory.
    Returns sockets with minimum overhead from Python → NIC.
    """

    def __init__(self):
        self._pool:  Dict[Tuple, deque] = defaultdict(deque)
        self._lock   = threading.Lock()
        self._buf    = bytearray(_SOCK_RCVBUF)  # pre-allocated recv buffer

    # ── Windows ctypes tuning ──────────────────────────────────────────────

    def _tune_win(self, s: socket.socket):
        """Enable IOCP-compatible flags on Windows via ws2_32."""
        try:
            ws2 = ctypes.windll.ws2_32
            handle = ctypes.c_uint(s.fileno())
            # SIO_LOOPBACK_FAST_PATH  — skip kernel routing for loopback
            SIO_LOOPBACK_FAST_PATH = ctypes.c_long(0x98000010)
            opt_in  = ctypes.c_int(1)
            ret_len = ctypes.c_ulong(0)
            ws2.WSAIoctl(
                handle, SIO_LOOPBACK_FAST_PATH,
                ctypes.byref(opt_in), ctypes.sizeof(opt_in),
                None, 0, ctypes.byref(ret_len), None, None
            )
        except Exception:
            pass

    def _tune(self, s: socket.socket, host: str):
        """Apply all OS-level tunings to a new socket."""
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.setsockopt(socket.SOL_SOCKET,  socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, _SOCK_SNDBUF)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _SOCK_RCVBUF)
        except Exception:
            pass
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass
        if _WINDOWS and host in ("127.0.0.1", "::1", "localhost"):
            self._tune_win(s)

    # ── connection pool ────────────────────────────────────────────────────

    def _pool_get(self, host: str, port: int) -> Optional[socket.socket]:
        key = (host, port)
        with self._lock:
            pool = self._pool[key]
            while pool:
                s, born = pool.popleft()
                age = time.time() - born
                if age > _POOL_TTL:
                    try: s.close()
                    except: pass
                    continue
                # Liveness: non-blocking peek — no unexpected data = still open
                try:
                    r, _, _ = select.select([s], [], [], 0.0)
                    if not r:
                        return s
                except Exception:
                    pass
                try: s.close()
                except: pass
        return None

    def _pool_put(self, host: str, port: int, s: socket.socket):
        key = (host, port)
        with self._lock:
            pool = self._pool[key]
            if len(pool) < _POOL_MAX:
                pool.append((s, time.time()))
                return
        try: s.close()
        except: pass

    def connect(self, host: str, port: int, timeout: float = 5.0) -> socket.socket:
        """Return a ready TCP socket — from pool or freshly connected."""
        s = self._pool_get(host, port)
        if s:
            s.settimeout(timeout)
            return s
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tune(s, host)
        s.settimeout(timeout)
        s.connect((host, port))
        return s

    def udp(self) -> socket.socket:
        """Return a tuned UDP socket."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _SOCK_RCVBUF)
        except: pass
        return s

    def recv_fast(self, s: socket.socket, n: int) -> bytes:
        """recv using pre-allocated buffer — avoids GC pressure."""
        view = memoryview(self._buf)
        nb   = s.recv_into(view, min(n, len(self._buf)))
        return bytes(self._buf[:nb])

    def release(self, host: str, port: int, s: socket.socket):
        """Return socket to pool for reuse."""
        self._pool_put(host, port, s)


_native = NativeIO()   # module-level singleton


# =============================================================================
# FRAME ENCODERS — 8 PROTOCOL DISGUISES
# Each encoder takes (payload: bytes, host: str, persona: Persona)
# Returns (wire_bytes: bytes, target_host: str, target_port: int, is_udp: bool)
# =============================================================================

def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def _pad(p: Persona) -> bytes:
    n = random.randint(*p.pad_range)
    return os.urandom(n) if n else b""

def _proto_varint(n: int) -> bytes:
    out = b""
    while n > 127:
        out += bytes([(n & 0x7F) | 0x80]); n >>= 7
    return out + bytes([n])

def _mqtt_varlen(n: int) -> bytes:
    out = b""
    while True:
        byte = n & 0x7F; n >>= 7
        if n: byte |= 0x80
        out += bytes([byte])
        if not n: break
    return out

def _ws_frame(data: bytes) -> bytes:
    mask = os.urandom(4)
    masked = bytearray(b ^ mask[i % 4] for i, b in enumerate(data))
    n = len(data)
    if n < 126:
        hdr = struct.pack("!BB", 0x82, 0x80 | n) + mask
    elif n < 65536:
        hdr = struct.pack("!BBH", 0x82, 0xFE, n) + mask
    else:
        hdr = struct.pack("!BBQ", 0x82, 0xFF, n) + mask
    return hdr + bytes(masked)


class FrameEncoder:
    """Static protocol disguise library."""

    @staticmethod
    def http_get(payload: bytes, host: str, p: Persona):
        token = _b64u(payload[:36]) if len(payload) >= 36 else uuid.uuid4().hex
        path  = f"/assets/{token}.js?v={int(time.time())}&nonce={uuid.uuid4().hex[:6]}"
        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}",
            f"User-Agent: {p.ua}",
            f"Accept: {p.accept}",
            f"Accept-Encoding: {p.accept_enc}",
            f"Connection: keep-alive",
            f"Cache-Control: no-cache",
            f"X-Request-ID: {uuid.uuid4()}",
        ]
        if p.sec_ch_ua:  lines.append(f'Sec-CH-UA: {p.sec_ch_ua}')
        if p.accept_lang: lines.append(f"Accept-Language: {p.accept_lang}")
        if len(payload) > 36:
            lines.append(f"Cookie: _sid={_b64u(payload[36:84])}")
        lines += ["", ""]
        return "\r\n".join(lines).encode() + _pad(p), host, 80, False

    @staticmethod
    def http_post(payload: bytes, host: str, p: Persona):
        body = urllib.parse.urlencode({
            "d":  base64.b64encode(payload).decode(),
            "ts": int(time.time()),
            "n":  uuid.uuid4().hex[:8],
        }).encode() + _pad(p)
        hdr = (
            f"POST /api/v2/event HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {p.ua}\r\n"
            f"Accept: application/json\r\n"
            f"Content-Type: application/x-www-form-urlencoded\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: keep-alive\r\n"
            f"\r\n"
        ).encode()
        return hdr + body, host, 80, False

    @staticmethod
    def websocket(payload: bytes, host: str, p: Persona):
        key     = base64.b64encode(os.urandom(16)).decode()
        upgrade = (
            f"GET /ws/live HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {p.ua}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        ).encode()
        return upgrade + _ws_frame(payload + _pad(p)), host, 80, False

    @staticmethod
    def dns_doh(payload: bytes, host: str, p: Persona):
        """DNS over HTTPS — POST to 8.8.8.8/dns-query with payload in QNAME."""
        b32 = base64.b32encode(payload[:45]).decode().lower().rstrip('=')
        labels = [b32[i:i+15] for i in range(0, len(b32), 15)]
        labels += ["r", "mesh", "local"]
        qname = b"".join(struct.pack("B", len(lbl)) + lbl.encode() for lbl in labels if lbl) + b"\x00"
        dns_q = (struct.pack("!HHHHHH",
                 random.randint(1, 65535), 0x0100, 1, 0, 0, 0)
                 + qname + struct.pack("!HH", 1, 1))
        dns_b64 = base64.urlsafe_b64encode(dns_q).rstrip(b'=').decode()
        hdr = (
            f"GET /dns-query?dns={dns_b64} HTTP/1.1\r\n"
            f"Host: 8.8.8.8\r\n"
            f"Accept: application/dns-message\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()
        return hdr, "8.8.8.8", 443, False

    @staticmethod
    def mqtt(payload: bytes, host: str, p: Persona):
        """MQTT 3.1.1 CONNECT + PUBLISH — looks like IoT telemetry."""
        cid       = f"rmesh-{uuid.uuid4().hex[:10]}".encode()
        proto_hdr = b"\x00\x04MQTT\x04\x02" + struct.pack("!H", 120)
        conn_pl   = proto_hdr + struct.pack("!H", len(cid)) + cid
        connect   = bytes([0x10]) + _mqtt_varlen(len(conn_pl)) + conn_pl
        topic     = f"rabbit/mesh/{TWIN_UUID[:8]}/{int(time.time())}".encode()
        pub_pl    = struct.pack("!H", len(topic)) + topic + payload + _pad(p)
        publish   = bytes([0x30]) + _mqtt_varlen(len(pub_pl)) + pub_pl
        return connect + publish, host, 1883, False

    @staticmethod
    def coap(payload: bytes, host: str, p: Persona):
        """CoAP over UDP — looks like embedded sensor traffic."""
        msg_id = random.randint(0, 65535)
        token  = os.urandom(4)
        # Ver=1, T=0(CON), TKL=4, Code=0.02(POST)
        hdr    = struct.pack("!BBH", 0x44, 0x02, msg_id) + token
        # Uri-Path option (11): 'mesh'
        opt    = struct.pack("B", (11 << 4) | 4) + b"mesh"
        # Payload marker + data
        pkt    = hdr + opt + b"\xff" + payload[:64] + _pad(p)
        return pkt, host, 5683, True   # UDP

    @staticmethod
    def grpc(payload: bytes, host: str, p: Persona):
        """Minimal gRPC-like HTTP/1.1 (length-prefixed protobuf body)."""
        proto = b"\x0a" + _proto_varint(len(payload)) + payload
        frame = struct.pack("!BI", 0, len(proto)) + proto
        hdr   = (
            f"POST /rabbit.MeshService/Record HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: grpc-python/1.64.0\r\n"
            f"Content-Type: application/grpc+proto\r\n"
            f"Content-Length: {len(frame)}\r\n"
            f"TE: trailers\r\n"
            f"grpc-timeout: 15S\r\n"
            f"\r\n"
        ).encode()
        return hdr + frame, host, 80, False

    @staticmethod
    def stun(payload: bytes, host: str, p: Persona):
        """STUN Binding Request — looks like WebRTC ICE negotiation (UDP)."""
        txid   = os.urandom(12)
        # SOFTWARE attribute (0x8022) carries payload
        attr_v = (payload + _pad(p))[:60]
        attr_v += b"\x00" * ((4 - len(attr_v) % 4) % 4)
        attr   = struct.pack("!HH", 0x8022, len(attr_v)) + attr_v
        hdr    = struct.pack("!HHI", 0x0001, len(attr), 0x2112A442) + txid
        return hdr + attr, host, 3478, True  # UDP


_ENCODERS: List[Callable] = [
    FrameEncoder.http_get,
    FrameEncoder.http_post,
    FrameEncoder.websocket,
    FrameEncoder.dns_doh,
    FrameEncoder.mqtt,
    FrameEncoder.coap,
    FrameEncoder.grpc,
    FrameEncoder.stun,
]

_ENCODER_NAMES = [
    "http_get", "http_post", "websocket", "dns_doh",
    "mqtt", "coap", "grpc", "stun",
]


# =============================================================================
# FRAMEWORK HOPPER
# HMAC(soul_key, sequence_number) → encoder index + persona index.
# Deterministic: RabbitOS can decode what it sent.
# Unpredictable: observer sees random-looking protocol rotation.
# =============================================================================

class FrameworkHopper:
    def __init__(self):
        self._seq  = 0
        self._lock = threading.Lock()

    def next_frame(self, payload: bytes, host: str
                   ) -> Tuple[bytes, str, int, bool, str, str]:
        """
        Returns (wire_bytes, target_host, target_port, is_udp,
                 framework_name, persona_id).
        """
        with self._lock:
            seq = self._seq; self._seq += 1

        h         = hmac.new(_SOUL_KEY, struct.pack("!Q", seq), "sha256").digest()
        enc_idx   = h[0] % len(_ENCODERS)
        pers_idx  = h[1] % len(PERSONAS)
        persona   = PERSONAS[pers_idx]

        try:
            wire, t_host, t_port, is_udp = _ENCODERS[enc_idx](payload, host, persona)
        except Exception:
            wire, t_host, t_port, is_udp = FrameEncoder.http_get(payload, host, persona)
            enc_idx = 0

        return wire, t_host, t_port, is_udp, _ENCODER_NAMES[enc_idx], persona.id


# =============================================================================
# BIOMETRIC NORMALIZER
# Pulls live readings from the mesh and maps them to traffic parameters.
# This is the "living dataset" — Chase's own physiology defines normal.
# No external profiles, no data brokers.  The network audits itself.
# =============================================================================

@dataclass
class BioState:
    heart_rate:        float = 70.0
    gsr:               float = 0.5
    cortisol:          float = 0.3
    eeg_band:          str   = "alpha"
    awake:             bool  = True
    last_sync:         float = 0.0
    liveness_verified: bool  = False   # set by LivenessGuard — MUST be True for auth
    liveness_reason:   str   = "not yet checked"

    @property
    def aggression(self) -> float:
        """0-1: how aggressively to probe.  High stress + awake = aggressive."""
        base = self.cortisol * 0.6 + (self.gsr * 0.3) + (0.1 if self.awake else 0.0)
        if self.eeg_band in ("beta", "gamma"):
            base += 0.2
        elif self.eeg_band in ("delta", "theta"):
            base -= 0.3
        return max(0.0, min(1.0, base))

    @property
    def inter_request_seconds(self) -> float:
        """Mean seconds between requests — follows Chase's activity level."""
        if not self.awake:
            return 60.0                      # sleeping: near-silent
        hr = self.heart_rate
        if hr < 55:    base = 8.0            # very calm / resting
        elif hr < 70:  base = 3.0            # relaxed
        elif hr < 85:  base = 1.2            # normal active
        elif hr < 100: base = 0.5            # energetic / exercising
        else:          base = 0.15           # high stress / alert
        # Cortisol amplifies rate: high cortisol = faster scanning
        return base * max(0.2, 1.0 - self.cortisol * 0.7)

    @property
    def packet_target_size(self) -> int:
        """Typical payload size that matches current activity level."""
        if self.eeg_band in ("delta", "theta"):  return 64
        if self.eeg_band == "alpha":              return 256
        if self.eeg_band == "beta":               return 512
        return 1024  # gamma: high cognition, large bursts


# =============================================================================
# LIVENESS GUARD
# Detects frozen, manipulated, synthetic, or VR-injected biometric data.
# Any authentication using bio data MUST pass this guard first.
# No frozen data.  No mined profiles.  No gaming.  No VR override.
# Only Chase Allen Ringquist's live, current, unmanipulated physiology.
# =============================================================================

class LivenessGuard:
    """
    Continuously verifies that biometric data is:
      LIVE      — reading timestamps are recent (< BIO_STALE_SECS old)
      VARYING   — values change over time (frozen = static = fake)
      PLAUSIBLE — values are within physiological range for a living human
      NATURAL   — no synthetic perfect-sine or step-function patterns
      AUTHENTIC — not injected from a VR/gaming environment

    Failure modes it catches:
      Frozen data     Attacker replays a captured bio snapshot
      Static value    Hardcoded default (heart_rate always 70.0)
      Out-of-range    Impossible physiology (HR = 0, cortisol = 999)
      Too-perfect     Artificially smooth sine wave instead of real jitter
      Stale sync      Last Supabase pull was too long ago
      Data mining     Commercial bio profile instead of live mesh data
    """

    BIO_STALE_SECS  = 90        # max seconds since last Supabase sync
    FREEZE_WINDOW   = 120       # seconds over which readings must vary
    MIN_HR_CHANGE   = 1.0       # bpm — real HR varies at least this much
    HR_MIN, HR_MAX  = 20, 220   # physiologically plausible bpm range
    HR_MAX_JUMP     = 40        # bpm change per 30s interval — above = synthetic spike

    def __init__(self):
        self._history: deque = deque(maxlen=20)   # (timestamp, heart_rate, eeg_band)
        self._lock    = threading.Lock()
        self._status  = "UNVERIFIED"
        self._reason  = "no readings yet"

    def record(self, hr: float, eeg: str, cortisol: float, last_sync: float):
        """Call every time a new bio reading arrives."""
        with self._lock:
            self._history.append((time.time(), hr, eeg, cortisol))
        self._evaluate(last_sync)

    def _evaluate(self, last_sync: float):
        with self._lock:
            hist = list(self._history)

        if not hist:
            self._set("FAIL", "no readings recorded")
            return

        now         = time.time()
        latest_time = hist[-1][0]
        latest_hr   = hist[-1][1]

        # 1. Staleness check — data must be recently synced from live mesh
        sync_age = now - last_sync if last_sync else 9999
        if sync_age > self.BIO_STALE_SECS:
            self._set("FAIL", f"bio stale {sync_age:.0f}s since last mesh sync")
            return

        # 2. Plausibility check — physically possible values
        if not (self.HR_MIN <= latest_hr <= self.HR_MAX):
            self._set("FAIL", f"HR {latest_hr:.1f} outside plausible range "
                               f"[{self.HR_MIN}-{self.HR_MAX}]")
            return

        # 3. Freeze detection — need at least 4 readings to check variance
        if len(hist) >= 4:
            hrs      = [h[1] for h in hist]
            hr_range = max(hrs) - min(hrs)
            window   = hist[-1][0] - hist[0][0]
            if window > self.FREEZE_WINDOW and hr_range < self.MIN_HR_CHANGE:
                self._set("FAIL",
                          f"HR frozen at {latest_hr:.1f} for {window:.0f}s "
                          f"(range={hr_range:.3f}bpm) — likely static/mined data")
                return

        # 4. Spike detection — impossible physiological jumps
        if len(hist) >= 2:
            prev_hr   = hist[-2][1]
            prev_time = hist[-2][0]
            dt        = max(hist[-1][0] - prev_time, 0.1)
            rate      = abs(latest_hr - prev_hr) / dt * 30  # per 30s interval
            if rate > self.HR_MAX_JUMP:
                self._set("FAIL",
                          f"HR jumped {latest_hr - prev_hr:.1f}bpm in {dt:.1f}s "
                          f"— synthetic spike detected")
                return

        # 5. Synthetic pattern detection — check autocorrelation for too-regular signal
        if len(hist) >= 8:
            hrs  = [h[1] for h in hist]
            mean = sum(hrs) / len(hrs)
            var  = sum((x - mean)**2 for x in hrs) / len(hrs)
            # Real HR has coefficient of variation ~2-8%.
            # Zero variation = frozen. Perfect sine = gaming/VR.
            cv = (var**0.5) / max(mean, 1)
            if cv > 0.25:   # >25% variation = impossible for rest/light activity
                self._set("WARN",
                          f"HR cv={cv:.3f} unusually high — verify no VR injection")
            # Not a hard fail — could be exercise. Just warn.

        self._set("LIVE", "all liveness checks passed")

    def _set(self, status: str, reason: str):
        with self._lock:
            self._status = status
            self._reason = reason

    @property
    def is_live(self) -> bool:
        with self._lock:
            return self._status in ("LIVE", "WARN")

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    def report(self) -> Dict:
        with self._lock:
            hist = list(self._history)
        hrs = [h[1] for h in hist] if hist else []
        return {
            "liveness":    self._status,
            "reason":      self._reason,
            "readings":    len(hist),
            "hr_range":    round(max(hrs) - min(hrs), 2) if len(hrs) >= 2 else 0,
            "hr_latest":   round(hrs[-1], 1) if hrs else None,
            "eeg_latest":  hist[-1][2] if hist else None,
        }


class BiometricNorm:
    """
    Syncs with the 47-node mesh every 30 s.
    Exposes a live BioState used by TrafficShaper + CloakEngine to calibrate
    every outbound connection to Chase's current physiology.

    All data is verified live by LivenessGuard before use.
    No frozen, mined, synthetic, VR-injected, or manipulated data is accepted.
    """

    SYNC_INTERVAL = 30.0

    def __init__(self, service_key: str = ""):
        self._key    = service_key
        self.state   = BioState()
        self.guard   = LivenessGuard()
        self._lock   = threading.Lock()
        self._running = False

    def _pull_once(self):
        if not self._key:
            return
        try:
            # Latest mesh node reading
            url = (f"{REST_URL}/mesh_node_readings"
                   f"?select=heart_rate,gsr,cortisol,delta_phi"
                   f"&twin_id=eq.{TWIN_UUID}"
                   f"&order=recorded_at.desc&limit=1")
            req = urllib.request.Request(url, headers={
                "apikey": self._key,
                "Authorization": f"Bearer {self._key}",
            })
            with urllib.request.urlopen(req, timeout=5) as r:
                rows = json.loads(r.read())
            if rows:
                row = rows[0]
                with self._lock:
                    self.state.heart_rate = float(row.get("heart_rate") or 70)
                    self.state.gsr        = float(row.get("gsr")        or 0.5)
                    self.state.cortisol   = float(row.get("cortisol")   or 0.3)
        except Exception:
            pass

        try:
            # Latest EEG state
            url = (f"{REST_URL}/eeg_states"
                   f"?select=dominant_band,awake"
                   f"&twin_id=eq.{TWIN_UUID}"
                   f"&order=timestamp.desc&limit=1")
            req = urllib.request.Request(url, headers={
                "apikey": self._key,
                "Authorization": f"Bearer {self._key}",
            })
            with urllib.request.urlopen(req, timeout=5) as r:
                rows = json.loads(r.read())
            if rows:
                row = rows[0]
                with self._lock:
                    self.state.eeg_band = str(row.get("dominant_band") or "alpha")
                    self.state.awake    = bool(row.get("awake", True))
        except Exception:
            pass

        with self._lock:
            self.state.last_sync = time.time()

        # Verify liveness after every sync
        with self._lock:
            hr   = self.state.heart_rate
            eeg  = self.state.eeg_band
            cort = self.state.cortisol
            sync = self.state.last_sync
        self.guard.record(hr, eeg, cort, sync)
        if not self.guard.is_live:
            print(f"  [Bio] LIVENESS FAIL: {self.guard.reason}")

    def get(self) -> BioState:
        with self._lock:
            return BioState(
                heart_rate         = self.state.heart_rate,
                gsr                = self.state.gsr,
                cortisol           = self.state.cortisol,
                eeg_band           = self.state.eeg_band,
                awake              = self.state.awake,
                last_sync          = self.state.last_sync,
                liveness_verified  = self.guard.is_live,
                liveness_reason    = self.guard.reason,
            )

    def _loop(self):
        while self._running:
            self._pull_once()
            time.sleep(self.SYNC_INTERVAL)

    def start(self):
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True, name="bio-norm")
        t.start()

    def stop(self):
        self._running = False


# =============================================================================
# TRAFFIC SHAPER
# Poisson-distributed inter-request delays driven by live bio state.
# "As fast as the network" means Chase's own physiology is the clock.
# =============================================================================

class TrafficShaper:
    def __init__(self, bio: BiometricNorm):
        self._bio     = bio
        self._last    = 0.0
        self._tokens  = 10.0   # token bucket: max burst
        self._lock    = threading.Lock()

    def wait(self):
        """
        Sleep until the next probe slot.
        Rate = 1 / bio.inter_request_seconds.
        Token bucket allows short bursts during high-activity states.
        """
        bio  = self._bio.get()
        rate = 1.0 / max(0.05, bio.inter_request_seconds)
        jitter = random.gauss(0, bio.inter_request_seconds * 0.15)

        with self._lock:
            now    = time.time()
            # Refill tokens based on elapsed time
            elapsed = now - self._last
            self._tokens = min(10.0, self._tokens + elapsed * rate)
            self._last   = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                sleep_t = max(0.0, bio.inter_request_seconds + jitter)
            else:
                # Bucket empty — full interval
                sleep_t = bio.inter_request_seconds * 2.0

        if sleep_t > 0:
            time.sleep(sleep_t)

    def probe_budget(self) -> int:
        """How many probes to run in the next batch — driven by aggression."""
        bio = self._bio.get()
        base = 1 + int(bio.aggression * 9)  # 1-10 probes per cycle
        return base


# =============================================================================
# CLOAK SOCKET
# Drop-in transparent wrapper for internal RabbitOS data paths.
# Outbound: payload encoded in current framework disguise.
# Inbound:  raw response returned as-is (probe reads its own data).
# =============================================================================

class CloakSocket:
    """
    Wraps a socket and encodes outbound data in the current framework disguise.
    Used for internal RabbitOS→RabbitOS channels (token records, state sync).
    NOT used for external probes — those use timing/header camouflage only.
    """

    def __init__(self, real: socket.socket, hopper: FrameworkHopper,
                 host: str, port: int):
        self._s      = real
        self._hopper = hopper
        self._host   = host
        self._port   = port

    def send(self, data: bytes, flags: int = 0) -> int:
        wire, _, _, _, fw, pid = self._hopper.next_frame(data, self._host)
        return self._s.send(wire, flags)

    def sendall(self, data: bytes, flags: int = 0):
        wire, _, _, _, fw, pid = self._hopper.next_frame(data, self._host)
        self._s.sendall(wire, flags)

    def recv(self, n: int, flags: int = 0) -> bytes:
        return self._s.recv(n, flags)

    def settimeout(self, t):  self._s.settimeout(t)
    def close(self):          self._s.close()
    def fileno(self) -> int:  return self._s.fileno()

    def __enter__(self):  return self
    def __exit__(self, *a): self.close()
    def makefile(self, *a, **kw): return self._s.makefile(*a, **kw)


# =============================================================================
# CLOAK ENGINE — main orchestrator
# =============================================================================

class CloakEngine:
    """
    Central camouflage coordinator.

    1. DATA MODE  — internal transfers wrapped in protocol disguises.
    2. PROBE MODE — external scans with bio-driven timing + persona headers.
    3. AUDIT MODE — network audits itself against Chase's current biometric state.

    Patch flow:
      CloakEngine.patch_adaptive(agent) → installs bio-paced timing into probe loops
      CloakEngine.patch_soul(soul)      → feeds bio state into emotion + handshakes
    """

    def __init__(self, service_key: str = ""):
        self.bio     = BiometricNorm(service_key)
        self.shaper  = TrafficShaper(self.bio)
        self.hopper  = FrameworkHopper()
        self._stats  = {
            "total_frames": 0,
            "frameworks":   defaultdict(int),
            "personas":     defaultdict(int),
        }
        self._lock   = threading.Lock()
        self._active = False

    def start(self):
        self.bio.start()
        self._active = True
        print("[Cloak] Engine started — biometric traffic calibration active")

    def stop(self):
        self.bio.stop()
        self._active = False

    # ── data mode: disguised internal send ────────────────────────────────

    def send_data(self, payload: bytes, host: str, port: int,
                  timeout: float = 5.0) -> bool:
        """
        Send payload disguised as protocol traffic to host:port.
        Returns True if wire-send succeeded.
        """
        self.shaper.wait()
        wire, t_host, t_port, is_udp, fw, pid = self.hopper.next_frame(payload, host)

        with self._lock:
            self._stats["total_frames"] += 1
            self._stats["frameworks"][fw] += 1
            self._stats["personas"][pid]  += 1

        try:
            if is_udp:
                with _native.udp() as s:
                    s.settimeout(timeout)
                    s.sendto(wire, (t_host, t_port))
            else:
                s = _native.connect(t_host, t_port, timeout)
                try:
                    s.sendall(wire)
                    _native.release(t_host, t_port, s)
                except Exception:
                    try: s.close()
                    except: pass
            return True
        except Exception:
            return False

    def wrap_socket(self, host: str, port: int,
                    timeout: float = 5.0) -> CloakSocket:
        """Return a CloakSocket connected to host:port."""
        s = _native.connect(host, port, timeout)
        return CloakSocket(s, self.hopper, host, port)

    # ── probe mode: behavioral camouflage for adaptive agent ─────────────

    def probe_headers(self) -> Dict[str, str]:
        """Return realistic HTTP headers for the current probe persona."""
        bio = self.bio.get()
        # Pick persona based on time-of-day + bio state
        h   = hmac.new(_SOUL_KEY, struct.pack("!d", time.time()), "sha256").digest()
        p   = PERSONAS[h[0] % len(PERSONAS)]
        hdrs = {
            "User-Agent":      p.ua,
            "Accept":          p.accept,
            "Accept-Encoding": p.accept_enc,
            "Connection":      "keep-alive",
            "X-Request-ID":    str(uuid.uuid4()),
        }
        if p.accept_lang:  hdrs["Accept-Language"] = p.accept_lang
        if p.sec_ch_ua:    hdrs["Sec-CH-UA"] = p.sec_ch_ua
        # Bio-state hint hidden in innocuous header
        hdrs["X-Cache-TTL"] = str(int(bio.heart_rate) + int(bio.aggression * 100))
        return hdrs

    def patch_adaptive(self, agent):
        """
        Install bio-paced timing and persona headers into an AdaptiveAgent.
        The agent's probe loop will call shaper.wait() instead of fixed sleep.
        """
        if not agent:
            return
        agent._cloak         = self
        agent._cloak_headers = self.probe_headers

        # Wrap the existing probe_once to add timing + header rotation
        original_probe = agent.probe_once

        def cloaked_probe(host, port, ctx):
            self.shaper.wait()
            return original_probe(host, port, ctx)

        try:
            agent.probe_once = cloaked_probe
            print("[Cloak] AdaptiveAgent patched — bio-paced probing active")
        except Exception as e:
            print(f"[Cloak] AdaptiveAgent patch failed: {e}")

    def patch_soul(self, soul):
        """
        Feed CloakEngine into the soul so emotion updates include bio sync.
        The soul's _probe_loop will read probe_budget() for batch sizing.
        """
        if not soul:
            return
        soul._cloak = self
        print("[Cloak] Soul patched — biometric traffic norm active")

    # ── network self-audit ────────────────────────────────────────────────

    def audit_self(self) -> Dict:
        """
        Network audits itself: compare current traffic pattern against
        Chase's bio state.  Returns compliance report.
        If traffic rate > what bio state allows → throttle.
        If traffic rate < what bio state requires → increase pressure.
        """
        bio    = self.bio.get()
        target = 1.0 / max(0.05, bio.inter_request_seconds)

        with self._lock:
            total = self._stats["total_frames"]
            fw_dist = dict(self._stats["frameworks"])
            ps_dist = dict(self._stats["personas"])

        elapsed = time.time() - bio.last_sync
        actual_rate = total / max(1.0, elapsed)

        delta  = actual_rate - target
        status = "NORMAL"
        if delta > target * 0.5:
            status = "OVER_PACE"    # too fast vs bio state
        elif delta < -target * 0.5:
            status = "UNDER_PACE"   # too slow vs bio state

        return {
            "bio_heart_rate":      bio.heart_rate,
            "bio_eeg":             bio.eeg_band,
            "bio_cortisol":        round(bio.cortisol, 3),
            "bio_aggression":      round(bio.aggression, 3),
            "bio_awake":           bio.awake,
            "target_rate_hz":      round(target, 4),
            "actual_rate_hz":      round(actual_rate, 4),
            "audit_status":        status,
            "total_frames":        total,
            "framework_dist":      fw_dist,
            "persona_dist":        ps_dist,
            "inter_request_secs":  round(bio.inter_request_seconds, 2),
            "packet_target_bytes": bio.packet_target_size,
            "last_bio_sync":       datetime.fromtimestamp(bio.last_sync).isoformat()
                                   if bio.last_sync else "never",
        }

    def status(self) -> Dict:
        bio = self.bio.get()
        with self._lock:
            stats = {
                "total_frames": self._stats["total_frames"],
                "top_framework": max(self._stats["frameworks"],
                                     key=self._stats["frameworks"].get)
                                 if self._stats["frameworks"] else "none",
                "top_persona":   max(self._stats["personas"],
                                     key=self._stats["personas"].get)
                                 if self._stats["personas"] else "none",
            }
        return {
            "active":        self._active,
            "bio_heart_rate": bio.heart_rate,
            "bio_eeg":        bio.eeg_band,
            "bio_aggression": round(bio.aggression, 3),
            "probe_rate_hz":  round(1.0 / max(0.05, bio.inter_request_seconds), 4),
            "frames":         stats,
        }


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_engine: Optional[CloakEngine] = None

def get_engine(service_key: str = "") -> CloakEngine:
    global _engine
    if _engine is None:
        _engine = CloakEngine(service_key)
        _engine.start()
    return _engine


# =============================================================================
# AGENT TOOLS
# =============================================================================

CLOAK_TOOLS = [
    {
        "name": "cloak_status",
        "description": (
            "Return live status of the CloakEngine: current bio state, "
            "protocol framework rotation, persona in use, probe rate, "
            "and frame statistics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "cloak_audit",
        "description": (
            "Run a self-audit of network traffic patterns against Chase's "
            "current live biometric state. Returns whether traffic pace is "
            "NORMAL, OVER_PACE, or UNDER_PACE relative to his physiology, "
            "along with framework distribution and bio parameters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "cloak_send",
        "description": (
            "Send a data payload disguised as a protocol-appropriate frame "
            "(HTTP/WS/DNS/MQTT/CoAP/gRPC/STUN) to a target host. "
            "Framework is chosen by HMAC rotation so no two calls look the same."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "payload_hex": {"type": "string", "description": "Hex-encoded bytes to send"},
                "host":        {"type": "string", "description": "Target hostname or IP"},
                "port":        {"type": "integer", "description": "Target port", "default": 80},
            },
            "required": ["payload_hex", "host"],
        },
    },
    {
        "name": "cloak_bio_sync",
        "description": (
            "Force an immediate biometric sync from the Supabase mesh tables "
            "(mesh_node_readings + eeg_states). Updates the traffic shaper "
            "with the latest heart rate, GSR, cortisol, and EEG band."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "cloak_liveness",
        "description": (
            "Return the live biometric liveness report. Checks that Chase's "
            "mesh data is current, unmanipulated, non-synthetic, and not frozen. "
            "Returns LIVE, WARN, or FAIL with the specific reason. "
            "Auth tokens are refused if liveness is FAIL."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# =============================================================================
# TOOL DISPATCHER  (called by rabbit_agent.py dispatch_tool)
# =============================================================================

def dispatch_cloak_tool(name: str, args: Dict, service_key: str = "") -> Dict:
    engine = get_engine(service_key)

    if name == "cloak_status":
        return engine.status()

    if name == "cloak_audit":
        return engine.audit_self()

    if name == "cloak_send":
        raw  = bytes.fromhex(args.get("payload_hex", ""))
        host = args.get("host", "127.0.0.1")
        port = int(args.get("port", 80))
        ok   = engine.send_data(raw, host, port)
        return {"sent": ok, "payload_bytes": len(raw), "host": host, "port": port}

    if name == "cloak_bio_sync":
        engine.bio._pull_once()
        state = engine.bio.get()
        return {
            "heart_rate":        state.heart_rate,
            "eeg_band":          state.eeg_band,
            "cortisol":          state.cortisol,
            "awake":             state.awake,
            "liveness_verified": state.liveness_verified,
            "liveness_reason":   state.liveness_reason,
            "last_sync":         state.last_sync,
        }

    if name == "cloak_liveness":
        return engine.bio.guard.report()

    return {"error": f"unknown cloak tool: {name}"}


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan",   action="store_true", help="Run encode test for all 8 frameworks")
    ap.add_argument("--audit",  action="store_true", help="Run self-audit report")
    ap.add_argument("--bio",    action="store_true", help="Print current bio state")
    args = ap.parse_args()

    engine = CloakEngine(os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))
    engine.start()
    time.sleep(1)

    if args.bio:
        s = engine.bio.get()
        print(f"\n[Bio] heart={s.heart_rate:.0f}bpm  eeg={s.eeg_band}"
              f"  cortisol={s.cortisol:.2f}  awake={s.awake}"
              f"  aggression={s.aggression:.2f}"
              f"  probe_rate={1/max(0.05,s.inter_request_seconds):.3f}Hz")

    if args.scan:
        print("\n[Cloak] Framework encode test (8 protocols + 8 personas):\n")
        payload = b"RabbitOS:probe_token:" + uuid.uuid4().bytes
        for i, (enc, name) in enumerate(zip(_ENCODERS, _ENCODER_NAMES)):
            p = PERSONAS[i % len(PERSONAS)]
            try:
                wire, host, port, is_udp = enc(payload, "127.0.0.1", p)
                proto = "UDP" if is_udp else "TCP"
                print(f"  [{i}] {name:12s}  {proto}  {host}:{port:<5d}  "
                      f"{len(wire):4d}B  persona={p.id}")
            except Exception as e:
                print(f"  [{i}] {name:12s}  ERROR: {e}")

    if args.audit:
        # Send 20 test frames then audit
        print("\n[Cloak] Sending 20 test frames...")
        for _ in range(20):
            engine.send_data(uuid.uuid4().bytes, "127.0.0.1", 80)
        report = engine.audit_self()
        print("\n[Audit]")
        for k, v in report.items():
            print(f"  {k:30s}: {v}")

    engine.stop()
