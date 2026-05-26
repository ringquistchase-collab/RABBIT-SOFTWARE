#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RabbitOS Counter-Intelligence Engine
=====================================
Survival by absorption.

The system listens on decoy ports.  When something probes or attacks,
it does not just block — it captures the raw payload, reverse-engineers
the attacking tool's protocol, fingerprint, and intent, then crafts a
counter-injection tuned to that exact method and sends it back through
the attacker's own channel.

Every attack teaches the mesh a new probe technique.  Learned methods
are fed directly into the AdaptiveAgent's MethodEngine so the next
generation of probes inherits the attacker's knowledge.

Flow
----
  inbound connection
    -> AttackSensor captures raw bytes
    -> AttackAnalyzer reverse-engineers payload (protocol, tool, intent, source)
    -> SurvivalMemory records event, checks if pattern is new
    -> HoneypotResponder crafts a deceptive response (honeypot creds, false mesh data)
    -> CounterInjector sends response + optional reverse-probe back to source
    -> MethodEngine.inject_learned() registers new probe variant from attack pattern
    -> Supabase: attack_events table records everything (hash only, never raw)

Counter-injection modes
-----------------------
  PASSIVE   Log and record only.  No response sent.
  DECEPTIVE Respond on our listening socket with honeypot data.
  ACTIVE    Also reverse-probe the attacker's source on their own ports.
            Requires explicit opt-in (COUNTER_MODE = "ACTIVE").
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
import threading
import base64
import re
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum
from datetime import datetime, timezone

# ─── identity ───────────────────────────────────────────────────────────────
TWIN_UUID    = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUPABASE_URL = "https://ludxbakxpmdqhfgdenwp.supabase.co"
REST_URL     = f"{SUPABASE_URL}/rest/v1"
_SIGN_KEY    = hashlib.sha256(TWIN_UUID.encode()).digest()

COUNTER_MODE = os.environ.get("COUNTER_MODE", "DECEPTIVE")  # PASSIVE|DECEPTIVE|ACTIVE


# =============================================================================
# ATTACK EVENT — immutable record of one detected attack
# =============================================================================

class AttackClass(str, Enum):
    PORT_SCAN    = "port_scan"
    BRUTE_FORCE  = "brute_force"
    SQLI         = "sqli"
    PATH_TRAV    = "path_traversal"
    CMD_INJECT   = "cmd_injection"
    FUZZING      = "fuzzing"
    RABBIT_HUNT  = "rabbit_hunt"   # attacker looking for RabbitOS specifically
    UNKNOWN      = "unknown"


@dataclass
class AttackEvent:
    event_id:    str
    src_ip:      str
    src_port:    int
    dst_port:    int
    raw_hash:    str          # SHA-256 of first packet; never store raw bytes
    protocol:    str          # tcp | udp | http | ssh | mysql | ...
    tool_hint:   str          # nmap | masscan | hydra | sqlmap | custom | unknown
    attack_class:AttackClass
    payload_len: int
    intent_tags: List[str]    # sqli | cmd_inject | rabbit_hunt | cred_stuff ...
    timestamp:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    counter_sent:bool = False
    learned_method: Optional[str] = None  # if a new probe method was extracted


# =============================================================================
# ATTACK ANALYZER — reverse engineer inbound payloads
# =============================================================================

class AttackAnalyzer:
    """
    Given raw bytes from an inbound connection, determine:
      - What protocol the attacker is using
      - Which tool likely generated it
      - What they are looking for
      - What probe technique can be learned from it
    """

    # Tool fingerprints in payload bytes
    TOOL_SIGS: Dict[bytes, str] = {
        b"Nmap":               "nmap",
        b"masscan":            "masscan",
        b"HYDRA":              "hydra",
        b"zgrab":              "zgrab",
        b"Go-http-client":     "go_scanner",
        b"python-requests":    "python_script",
        b"libwww-perl":        "perl_script",
        b"curl/":              "curl",
        b"Nikto":              "nikto",
        b"sqlmap":             "sqlmap",
        b"dirbuster":          "dirbuster",
        b"WPScan":             "wpscan",
        b"Shodan":             "shodan",
        b"ZAP/":               "owasp_zap",
        b"Burp":               "burpsuite",
    }

    # SQL injection fragments
    SQLI: List[bytes] = [
        b"SELECT ", b"UNION ", b"DROP TABLE", b"INSERT INTO",
        b"OR 1=1", b"' OR '", b"--\r\n", b"#\r\n",
        b"SLEEP(", b"BENCHMARK(", b"xp_cmdshell",
    ]

    # Path traversal
    PATH: List[bytes] = [
        b"../", b"..\\", b"%2e%2e", b"....//",
        b"/etc/passwd", b"/etc/shadow", b"C:\\Windows",
        b"boot.ini", b"/proc/self",
    ]

    # Command injection
    CMD: List[bytes] = [
        b"cmd.exe", b"/bin/sh", b"/bin/bash",
        b";ls ", b";id;", b"`id`", b"$(id)",
        b"system(", b"exec(", b"passthru(",
        b"wget http", b"curl http",
    ]

    # RabbitOS-specific hunting patterns
    RABBIT: List[bytes] = [
        b"ludxbakxpmdqhfgdenwp",
        b"ef5eb8ab",
        b"rabbit",
        b"mesh_node",
        b"twin_identity",
        b"agent_credentials",
        b"supabase.co",
    ]

    # Protocol magic bytes
    SSH_MAGIC    = b"SSH-"
    HTTP_METHODS = (b"GET ", b"POST ", b"PUT ", b"DELETE ", b"HEAD ",
                    b"OPTIONS ", b"PATCH ", b"CONNECT ")
    MYSQL_MAGIC  = bytes([0x0a])   # server greeting starts with 0x0a
    PG_MAGIC     = bytes([0x00, 0x00, 0x00])  # startup message
    REDIS_MAGIC  = b"*"            # RESP array
    MQTT_MAGIC   = bytes([0x10])   # CONNECT
    DNS_MIN_LEN  = 12

    @classmethod
    def analyze(cls, raw: bytes, src_ip: str, src_port: int,
                dst_port: int) -> AttackEvent:
        payload_hash = hashlib.sha256(raw).hexdigest()
        protocol     = cls._id_protocol(raw, dst_port)
        tool         = cls._id_tool(raw)
        tags         = cls._extract_tags(raw)
        attack_class = cls._classify(tags, dst_port, raw)
        learned      = cls._extract_learned_method(raw, protocol, tool)

        return AttackEvent(
            event_id     = uuid.uuid4().hex,
            src_ip       = src_ip,
            src_port     = src_port,
            dst_port     = dst_port,
            raw_hash     = payload_hash,
            protocol     = protocol,
            tool_hint    = tool,
            attack_class = attack_class,
            payload_len  = len(raw),
            intent_tags  = tags,
            learned_method = learned,
        )

    @classmethod
    def _id_protocol(cls, raw: bytes, port: int) -> str:
        if raw.startswith(cls.SSH_MAGIC):
            return "ssh"
        if any(raw.startswith(m) for m in cls.HTTP_METHODS):
            return "http"
        if len(raw) > 4 and raw[1:2] == b"Q":   # TLS ClientHello
            return "tls"
        if port in (3306, 33060):
            return "mysql"
        if port == 5432:
            return "postgresql"
        if port == 6379:
            return "redis"
        if port in (1883, 8883):
            return "mqtt"
        if port == 27017:
            return "mongodb"
        if port == 9200:
            return "elasticsearch"
        if port == 25:
            return "smtp"
        if port == 21:
            return "ftp"
        if port == 23:
            return "telnet"
        if len(raw) >= cls.DNS_MIN_LEN and port == 53:
            return "dns"
        return "tcp_raw"

    @classmethod
    def _id_tool(cls, raw: bytes) -> str:
        low = raw.lower()
        for sig, name in cls.TOOL_SIGS.items():
            if sig.lower() in low:
                return name
        # TCP option fingerprinting — window size hints
        # nmap default: window=1024 or 512; masscan: window=1024 with TTL=128
        # (we can't read TTL from payload but window size is in SYN)
        if len(raw) == 0:
            return "syn_scanner"  # empty payload = SYN-only probe
        if len(raw) < 4 and raw == b"\r\n\r\n":
            return "banner_grabber"
        return "unknown"

    @classmethod
    def _extract_tags(cls, raw: bytes) -> List[str]:
        low  = raw.lower()
        tags = []
        if any(p.lower() in low for p in cls.SQLI):
            tags.append("sqli")
        if any(p.lower() in low for p in cls.PATH):
            tags.append("path_traversal")
        if any(p.lower() in low for p in cls.CMD):
            tags.append("cmd_injection")
        if any(p.lower() in low for p in cls.RABBIT):
            tags.append("rabbit_hunt")
        # Credential stuffing: looks for 'password', 'passwd', 'user' in POST
        if b"password" in low or b"passwd" in low:
            tags.append("cred_stuff")
        # Fuzzing: long repeating patterns or binary garbage
        if len(raw) > 200 and len(set(raw)) < 20:
            tags.append("fuzzing")
        return tags or ["probe"]

    @classmethod
    def _classify(cls, tags: List[str], port: int,
                  raw: bytes) -> AttackClass:
        if "rabbit_hunt" in tags:
            return AttackClass.RABBIT_HUNT
        if "sqli" in tags:
            return AttackClass.SQLI
        if "cmd_injection" in tags:
            return AttackClass.CMD_INJECT
        if "path_traversal" in tags:
            return AttackClass.PATH_TRAV
        if "fuzzing" in tags:
            return AttackClass.FUZZING
        if "cred_stuff" in tags:
            return AttackClass.BRUTE_FORCE
        if len(raw) == 0 or len(raw) < 4:
            return AttackClass.PORT_SCAN
        return AttackClass.UNKNOWN

    @classmethod
    def _extract_learned_method(cls, raw: bytes, protocol: str,
                                tool: str) -> Optional[str]:
        """
        If the attack uses a non-trivial technique, extract it as
        a method name that can be registered in the MethodEngine.
        """
        if len(raw) == 0:
            return None
        # HTTP probes: extract the path pattern as a learned probe
        if protocol == "http":
            try:
                first_line = raw.split(b"\r\n")[0].decode(errors="replace")
                parts = first_line.split()
                if len(parts) >= 2:
                    path = parts[1]
                    # Interesting non-standard paths become new probe variants
                    if any(x in path for x in [".git", ".env", "admin", "api",
                                                "phpinfo", "wp-login", "config"]):
                        return f"http_path:{path[:40]}"
            except Exception:
                pass
        # SSH: non-standard banner = new variant
        if protocol == "ssh" and raw != b"SSH-2.0-OpenSSH_8.9\r\n":
            version = raw[:40].decode(errors="replace").strip()
            return f"ssh_banner:{version[:30]}"
        # Unknown tool with significant payload = new fuzzing variant
        if tool == "unknown" and len(raw) > 8:
            sig = base64.b64encode(raw[:8]).decode()
            return f"raw_probe:{sig}"
        return None


# =============================================================================
# HONEYPOT RESPONDER — deceptive responses that feed attackers false data
# =============================================================================

class HoneypotResponder:
    """
    Crafts protocol-appropriate fake responses.
    Data is plausible but poisoned — API keys are canary tokens,
    mesh data is fictional, credentials will trigger alerts if used.

    The goal: drain attacker time, feed them false information about
    the mesh, and embed tracking tokens in what they receive.
    """

    # Canary token prefix — if these appear in our logs, attacker used our bait
    _CANARY = "cny_" + hashlib.sha256(_SIGN_KEY + b"canary").hexdigest()[:16]

    @classmethod
    def _canary_key(cls, label: str) -> str:
        return f"{cls._CANARY}_{label}_{uuid.uuid4().hex[:8]}"

    @classmethod
    def http_response(cls, event: AttackEvent) -> bytes:
        """Return a fake HTTP 200 with convincing but poisoned JSON."""
        if "rabbit_hunt" in event.intent_tags:
            # They're hunting RabbitOS — give them a fake twin record
            body = json.dumps({
                "twin_id":   str(uuid.uuid4()),  # fake UUID
                "name":      "RabbitOS Node",
                "api_key":   cls._canary_key("api"),
                "status":    "active",
                "mesh_nodes": 0,
                "supabase_url": "https://decoy.supabase.co",
            })
        elif "sqli" in event.intent_tags:
            # SQL injection — return fake DB dump
            body = json.dumps({
                "users": [{"id": 1, "email": f"{cls._canary_key('user')}@decoy.mesh",
                           "password_hash": hashlib.sha256(b"canary").hexdigest()}]
            })
        elif "cred_stuff" in event.intent_tags:
            # Credential stuffing — fake auth success with canary session token
            body = json.dumps({
                "token": cls._canary_key("session"),
                "expires": "2026-12-31T00:00:00Z",
                "user_id": str(uuid.uuid4()),
            })
        else:
            # Generic: fake 200 with empty data
            body = json.dumps({"status": "ok", "data": []})

        body_b = body.encode()
        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body_b)}\r\n"
            f"Server: nginx/1.24.0\r\n"
            f"X-Request-ID: {uuid.uuid4()}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()
        return header + body_b

    @classmethod
    def ssh_banner(cls) -> bytes:
        """Return a fake SSH banner identifying as a different OS version."""
        versions = [
            b"SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.7\r\n",
            b"SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.11\r\n",
            b"SSH-2.0-dropbear_2022.83\r\n",
        ]
        return random.choice(versions)

    @classmethod
    def mysql_greeting(cls) -> bytes:
        """Fake MySQL server greeting."""
        server_ver = b"5.7.44-decoy\x00"
        conn_id    = struct.pack("<I", random.randint(1, 9999))
        auth_data  = os.urandom(8) + b"\x00"
        caps       = struct.pack("<H", 0xF7FF)
        payload    = (b"\x0a" + server_ver + conn_id + auth_data +
                      caps + b"\x08\x02\x00" + b"\x00" * 13 + os.urandom(12) + b"\x00")
        length     = struct.pack("<I", len(payload))[:3]
        return length + b"\x00" + payload

    @classmethod
    def redis_info(cls) -> bytes:
        """Fake Redis INFO response."""
        info = (
            b"$1024\r\n"
            b"# Server\r\nredis_version:6.2.7\r\n"
            b"os:Linux 5.15.0 x86_64\r\n"
            b"arch_bits:64\r\n"
            b"# Clients\r\nconnected_clients:1\r\n"
            b"# Memory\r\nused_memory:1024000\r\n"
            b"\r\n"
        )
        return info

    @classmethod
    def ftp_banner(cls) -> bytes:
        return b"220 FTP server ready\r\n"

    @classmethod
    def smtp_banner(cls) -> bytes:
        return b"220 mail.decoy.local ESMTP Postfix\r\n"

    @classmethod
    def craft(cls, event: AttackEvent) -> bytes:
        """Pick the right honeypot response for the detected protocol."""
        proto = event.protocol
        if proto == "http":     return cls.http_response(event)
        if proto == "ssh":      return cls.ssh_banner()
        if proto == "mysql":    return cls.mysql_greeting()
        if proto == "redis":    return cls.redis_info()
        if proto == "ftp":      return cls.ftp_banner()
        if proto == "smtp":     return cls.smtp_banner()
        # Default: send HTTP response for anything unknown
        return cls.http_response(event)


# =============================================================================
# COUNTER INJECTOR — send counter-payload back to source
# =============================================================================

class CounterInjector:
    """
    Sends the honeypot response back to the attacker through their channel.
    In ACTIVE mode, also reverse-probes the source to establish presence.
    """

    def __init__(self):
        self._sent  = 0
        self._lock  = threading.Lock()

    def inject(self, event: AttackEvent, response: bytes,
               src_sock: Optional[socket.socket] = None) -> bool:
        """
        Send counter-response.
        src_sock: the accepted socket from AttackSensor (if available).
        Falls back to a new connection in ACTIVE mode.
        """
        sent = False

        # Always try to respond on the existing inbound socket first
        if src_sock and COUNTER_MODE != "PASSIVE":
            try:
                src_sock.settimeout(2.0)
                src_sock.sendall(response)
                sent = True
            except Exception:
                pass

        # ACTIVE: also open a new connection back to the attacker
        if COUNTER_MODE == "ACTIVE" and not sent:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3.0)
                # Connect to the same port they came FROM (often an open service)
                s.connect((event.src_ip, event.src_port))
                s.sendall(response)
                s.close()
                sent = True
            except Exception:
                pass

        if sent:
            with self._lock:
                self._sent += 1

        return sent

    def reverse_probe(self, event: AttackEvent) -> Dict:
        """
        Probe the attacker's source IP using the same method they used on us.
        Learns their open ports, services, and feeds that back to the mesh.
        Only runs in ACTIVE mode.
        """
        if COUNTER_MODE != "ACTIVE":
            return {"skipped": "ACTIVE mode required"}

        results = {}
        src = event.src_ip

        # Try the port they connected from
        for port in [event.src_port, 80, 443, 22, 8080]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect((src, port))
                banner = b""
                try:
                    s.settimeout(1.0)
                    banner = s.recv(1024)
                except Exception:
                    pass
                s.close()
                results[port] = {
                    "open": True,
                    "banner": banner[:80].decode(errors="replace"),
                }
            except Exception:
                results[port] = {"open": False}

        return {"src_ip": src, "ports": results}

    @property
    def total_sent(self) -> int:
        with self._lock: return self._sent


# =============================================================================
# SURVIVAL MEMORY — learn from attacks, teach the adaptive engine
# =============================================================================

class SurvivalMemory:
    """
    Persists attack events to Supabase and feeds learned probe methods
    into the AdaptiveAgent's MethodEngine.

    Attack → learned method → new ProbeMethod registered in MethodEngine
    → next generation of probes inherits the attacker's technique.
    """

    def __init__(self, service_key: str = "", adaptive_engine=None):
        self._key     = service_key
        self._engine  = adaptive_engine   # MethodEngine reference
        self._seen:   deque = deque(maxlen=10000)  # raw_hash ring buffer (dedup)
        self._events: deque = deque(maxlen=1000)
        self._lock    = threading.Lock()
        self._learned_count = 0

    def is_new(self, raw_hash: str) -> bool:
        with self._lock:
            if raw_hash in self._seen:
                return False
            self._seen.append(raw_hash)
            return True

    def record(self, event: AttackEvent, counter_sent: bool = False):
        event.counter_sent = counter_sent
        with self._lock:
            self._events.appendleft(vars(event))

        # Teach the adaptive engine
        if event.learned_method and self._engine:
            self._inject_into_engine(event)

        # Persist to Supabase (hash only — never raw payload)
        self._push_supabase(event)

    def _inject_into_engine(self, event: AttackEvent):
        """Register the learned probe method into the AdaptiveAgent MethodEngine."""
        if not self._engine or not event.learned_method:
            return
        method_name = f"counter_learned"
        variant     = event.learned_method[:40].replace(":", "_").replace("/", "_")
        src_ip      = event.src_ip
        src_port    = event.src_port
        proto       = event.protocol

        def learned_probe(host: str, port: int, ctx: dict):
            """Auto-generated from reverse-engineered attack."""
            try:
                s = socket.create_connection((host, port),
                                             timeout=ctx.get("timeout", 5))
                # Mirror what the attacker sent us, aimed at the target
                if proto == "http":
                    s.sendall(b"GET / HTTP/1.0\r\nHost: " +
                              host.encode() + b"\r\n\r\n")
                    resp = s.recv(1024)
                    s.close()
                    return bool(resp)
                else:
                    banner = s.recv(256)
                    s.close()
                    return bool(banner)
            except Exception:
                return False

        try:
            self._engine.register(
                method     = method_name,
                variant    = variant,
                func       = learned_probe,
                generation = 0,
                parent     = f"counter:{event.src_ip}",
            )
            with self._lock:
                self._learned_count += 1
            print(f"  [Counter] Learned: {method_name}::{variant} "
                  f"from {src_ip} ({proto})")
        except Exception as e:
            print(f"  [Counter] Learn failed: {e}")

    def _push_supabase(self, event: AttackEvent):
        if not self._key:
            return
        try:
            row = {
                "twin_id":     TWIN_UUID,
                "src_ip":      event.src_ip,
                "src_port":    event.src_port,
                "dst_port":    event.dst_port,
                "raw_hash":    event.raw_hash,
                "protocol":    event.protocol,
                "tool_hint":   event.tool_hint,
                "attack_class":event.attack_class,
                "intent_tags": json.dumps(event.intent_tags),
                "payload_len": event.payload_len,
                "counter_sent":event.counter_sent,
                "learned_method": event.learned_method,
                "timestamp":   event.timestamp,
            }
            data = json.dumps(row).encode()
            req  = urllib.request.Request(
                f"{REST_URL}/attack_events",
                data    = data,
                method  = "POST",
                headers = {
                    "apikey":       self._key,
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                    "Prefer":       "return=minimal",
                },
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass   # Supabase not available — in-memory buffer still works

    def recent(self, n: int = 50) -> List[Dict]:
        with self._lock:
            return list(self._events)[:n]

    def stats(self) -> Dict:
        with self._lock:
            events = list(self._events)
        if not events:
            return {"total": 0}
        classes  = defaultdict(int)
        tools    = defaultdict(int)
        src_ips  = defaultdict(int)
        for e in events:
            classes[e.get("attack_class", "?")] += 1
            tools[e.get("tool_hint", "?")] += 1
            src_ips[e.get("src_ip", "?")] += 1
        top_src = sorted(src_ips.items(), key=lambda x: -x[1])[:5]
        return {
            "total":          len(events),
            "learned_methods": self._learned_count,
            "classes":        dict(classes),
            "tools":          dict(tools),
            "top_sources":    top_src,
        }


# =============================================================================
# ATTACK SENSOR — listens on decoy ports, captures raw inbound data
# =============================================================================

class AttackSensor:
    """
    Binds listening sockets on known honeypot ports.
    Any inbound connection is automatically suspicious.
    Captures first 4096 bytes of payload for analysis.
    """

    # Ports real services don't use on a standard RabbitOS node
    DECOY_PORTS = [21, 23, 25, 110, 143, 3306, 5432, 6379, 9200, 27017]

    def __init__(self, ports: Optional[List[int]] = None,
                 memory: Optional[SurvivalMemory] = None,
                 injector: Optional[CounterInjector] = None):
        self._ports    = ports or self.DECOY_PORTS
        self._memory   = memory
        self._injector = injector
        self._sockets: List[socket.socket] = []
        self._running  = False
        self._queue:   deque = deque(maxlen=500)
        self._lock     = threading.Lock()
        self._thread:  Optional[threading.Thread] = None

    def _bind_sockets(self) -> int:
        bound = 0
        for port in self._ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                s.listen(5)
                s.setblocking(False)
                self._sockets.append(s)
                bound += 1
            except Exception:
                pass   # port already in use — skip it
        return bound

    def _handle_conn(self, conn: socket.socket, addr: Tuple):
        src_ip, src_port = addr
        try:
            conn.settimeout(2.0)
            raw = b""
            try:
                raw = conn.recv(4096)
            except Exception:
                pass

            # Determine which listening port was hit
            dst_port = 0
            try:
                dst_port = conn.getsockname()[1]
            except Exception:
                pass

            event = AttackAnalyzer.analyze(raw, src_ip, src_port, dst_port)

            # Skip duplicates
            if self._memory and not self._memory.is_new(event.raw_hash):
                return

            print(f"  [Counter] ATTACK  {src_ip}:{src_port} -> :{dst_port}"
                  f"  class={event.attack_class}  tool={event.tool_hint}"
                  f"  tags={event.intent_tags}")

            response     = HoneypotResponder.craft(event)
            counter_sent = False
            if self._injector and COUNTER_MODE != "PASSIVE":
                counter_sent = self._injector.inject(event, response, conn)

            if self._memory:
                self._memory.record(event, counter_sent)

            with self._lock:
                self._queue.appendleft(vars(event))

        except Exception:
            pass
        finally:
            try: conn.close()
            except: pass

    def _loop(self):
        if not self._sockets:
            print("[Counter] No sockets bound — sensor inactive")
            return
        while self._running:
            try:
                readable, _, _ = select.select(self._sockets, [], [], 1.0)
                for srv in readable:
                    try:
                        conn, addr = srv.accept()
                        t = threading.Thread(
                            target=self._handle_conn,
                            args=(conn, addr),
                            daemon=True,
                        )
                        t.start()
                    except Exception:
                        pass
            except Exception:
                pass

    def start(self):
        bound = self._bind_sockets()
        print(f"[Counter] Sensor bound on {bound}/{len(self._ports)} decoy ports: "
              + str([s.getsockname()[1] for s in self._sockets]))
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True,
                                         name="attack-sensor")
        self._thread.start()

    def stop(self):
        self._running = False
        for s in self._sockets:
            try: s.close()
            except: pass
        self._sockets.clear()

    def recent(self, n: int = 20) -> List[Dict]:
        with self._lock:
            return list(self._queue)[:n]


# =============================================================================
# COUNTER AGENT — main orchestrator
# =============================================================================

class CounterAgent:
    """
    Ties all components together:
      sensor   → captures inbound attacks
      analyzer → reverse-engineers each attack
      responder→ crafts honeypot response
      injector → sends counter-injection back
      memory   → records + teaches adaptive engine

    Call .attach_adaptive(engine) to wire learned methods into probing.
    """

    def __init__(self, service_key: str = "", adaptive_engine=None,
                 decoy_ports: Optional[List[int]] = None):
        self.injector = CounterInjector()
        self.memory   = SurvivalMemory(service_key, adaptive_engine)
        self.sensor   = AttackSensor(decoy_ports, self.memory, self.injector)
        self._running = False

    def attach_adaptive(self, engine):
        """Wire in an AdaptiveAgent MethodEngine to receive learned probe methods."""
        self.memory._engine = engine

    def start(self):
        self.sensor.start()
        self._running = True
        print(f"[Counter] Agent started  mode={COUNTER_MODE}")

    def stop(self):
        self.sensor.stop()
        self._running = False

    def status(self) -> Dict:
        stats = self.memory.stats()
        return {
            "running":         self._running,
            "counter_mode":    COUNTER_MODE,
            "total_attacks":   stats.get("total", 0),
            "learned_methods": stats.get("learned_methods", 0),
            "counter_sent":    self.injector.total_sent,
            "attack_classes":  stats.get("classes", {}),
            "top_tools":       stats.get("tools", {}),
            "top_sources":     stats.get("top_sources", []),
        }

    def recent_attacks(self, n: int = 20) -> List[Dict]:
        return self.memory.recent(n)

    def manual_analyze(self, raw_hex: str, src_ip: str = "0.0.0.0",
                       src_port: int = 0, dst_port: int = 80) -> Dict:
        """Analyze a raw payload manually — for testing or agent use."""
        raw   = bytes.fromhex(raw_hex)
        event = AttackAnalyzer.analyze(raw, src_ip, src_port, dst_port)
        resp  = HoneypotResponder.craft(event)
        return {
            "event_id":     event.event_id,
            "protocol":     event.protocol,
            "tool_hint":    event.tool_hint,
            "attack_class": event.attack_class,
            "intent_tags":  event.intent_tags,
            "learned_method": event.learned_method,
            "response_len": len(resp),
            "response_preview": resp[:80].decode(errors="replace"),
        }


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_agent: Optional[CounterAgent] = None

def get_agent(service_key: str = "", adaptive_engine=None) -> CounterAgent:
    global _agent
    if _agent is None:
        _agent = CounterAgent(service_key, adaptive_engine)
        _agent.start()
    elif adaptive_engine and _agent.memory._engine is None:
        _agent.attach_adaptive(adaptive_engine)
    return _agent


# =============================================================================
# AGENT TOOLS
# =============================================================================

COUNTER_TOOLS = [
    {
        "name": "counter_status",
        "description": (
            "Return live status of the CounterAgent: total attacks detected, "
            "counter-injections sent, learned probe methods, top attack tools "
            "and source IPs."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "counter_recent",
        "description": (
            "List recent attack events: source IP/port, protocol, tool hint, "
            "attack class, intent tags, whether a counter-injection was sent, "
            "and any probe method learned from the attack."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20,
                          "description": "Max events to return"},
            },
            "required": [],
        },
    },
    {
        "name": "counter_analyze",
        "description": (
            "Manually reverse-engineer a raw payload (hex-encoded). "
            "Returns protocol, tool fingerprint, attack class, intent tags, "
            "and the honeypot response that would be sent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "raw_hex":  {"type": "string", "description": "Hex-encoded bytes"},
                "src_ip":   {"type": "string", "default": "0.0.0.0"},
                "src_port": {"type": "integer", "default": 0},
                "dst_port": {"type": "integer", "default": 80},
            },
            "required": ["raw_hex"],
        },
    },
    {
        "name": "counter_mode",
        "description": (
            "Change the counter-intelligence operating mode: "
            "PASSIVE (log only), DECEPTIVE (respond with honeypot), "
            "or ACTIVE (respond + reverse-probe attacker)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["PASSIVE", "DECEPTIVE", "ACTIVE"]},
            },
            "required": ["mode"],
        },
    },
]


def dispatch_counter_tool(name: str, args: Dict, service_key: str = "") -> Dict:
    global COUNTER_MODE
    agent = get_agent(service_key)

    if name == "counter_status":
        return agent.status()

    if name == "counter_recent":
        return {"attacks": agent.recent_attacks(args.get("limit", 20))}

    if name == "counter_analyze":
        return agent.manual_analyze(
            args.get("raw_hex", ""),
            args.get("src_ip", "0.0.0.0"),
            args.get("src_port", 0),
            args.get("dst_port", 80),
        )

    if name == "counter_mode":
        COUNTER_MODE = args.get("mode", "DECEPTIVE").upper()
        return {"counter_mode": COUNTER_MODE, "applied": True}

    return {"error": f"unknown counter tool: {name}"}


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--test",   action="store_true", help="Analyze sample payloads")
    ap.add_argument("--listen", action="store_true", help="Start sensor and wait for attacks")
    ap.add_argument("--mode",   default="DECEPTIVE", choices=["PASSIVE","DECEPTIVE","ACTIVE"])
    args = ap.parse_args()

    COUNTER_MODE = args.mode
    svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if args.test:
        print(f"\n[Counter] Payload analysis test  mode={COUNTER_MODE}\n")
        samples = [
            ("nmap SYN",        b"",                        80),
            ("HTTP GET normal",  b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n", 80),
            ("SQL injection",    b"GET /?id=1' OR '1'='1 HTTP/1.1\r\nHost: x\r\n\r\n", 80),
            ("RabbitOS hunt",    b"GET /ludxbakxpmdqhfgdenwp HTTP/1.1\r\nHost: x\r\n\r\n", 80),
            ("SSH banner",       b"SSH-2.0-Masscan_1.0\r\n",   22),
            ("Redis probe",      b"*1\r\n$4\r\nINFO\r\n",       6379),
            ("Path traversal",   b"GET /../../../etc/passwd HTTP/1.1\r\nHost: x\r\n\r\n", 80),
            ("Cmd injection",    b"POST /api HTTP/1.1\r\n\r\ndata=;id;",  80),
        ]
        agent = CounterAgent(svc_key)
        for label, payload, port in samples:
            result = agent.manual_analyze(payload.hex(), "1.2.3.4", 54321, port)
            print(f"  [{label:20s}]  proto={result['protocol']:12s}"
                  f"  class={result['attack_class']:15s}"
                  f"  tool={result['tool_hint']:12s}"
                  f"  tags={result['intent_tags']}")
            if result.get("learned_method"):
                print(f"    -> learned: {result['learned_method']}")
        print()

    if args.listen:
        print(f"\n[Counter] Starting sensor  mode={COUNTER_MODE}")
        print("[Counter] Press Ctrl+C to stop\n")
        agent = CounterAgent(svc_key)
        agent.start()
        try:
            while True:
                time.sleep(10)
                s = agent.status()
                print(f"  attacks={s['total_attacks']}  "
                      f"sent={s['counter_sent']}  "
                      f"learned={s['learned_methods']}")
        except KeyboardInterrupt:
            agent.stop()
            print("\n[Counter] Stopped")
