"""
rabbit_assistant.py — RabbitOS Cross-Platform Browser + Voice + Calling Assistant
Chase Allen Ringquist | RABBIT-SOFTWARE

Covers:
  - BrowserAgent: multi-tab web research with cross-source verification
  - CodingAgent: AI-assisted code generation and analysis
  - VoiceAssistant: TTS (gTTS / pyttsx3 / Azure / ElevenLabs) + STT (Whisper / vosk)
  - CallingAgent: WebRTC data-channel, SIP over UDP, PSTN via Twilio
  - CrossPlatformAgent: unified interface for Windows/Linux/macOS/Android/iOS/BlackBerry
  - CloudTrail: log all agent actions to Supabase + local SQLite + distributed cold nodes
  - ColdNetworkRegistry: online/offline node tracker with last-seen, storage metrics
  - StorageDiscovery: finds new storage methods (IPFS, Storj, R2, S3, local, mesh)
  - LLMNetworkStore: uses network nodes as distributed LLM storage / model shards
"""

from __future__ import annotations

import base64
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
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

shows_dna_root = False
assert shows_dna_root is False

_LOG = logging.getLogger("rabbit.assistant")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [ASST] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)


def _log(msg: str) -> None:
    try:
        _LOG.info(msg)
    except UnicodeEncodeError:
        _LOG.info(msg.encode("ascii", "replace").decode("ascii"))


def _get_llm():
    try:
        from rabbit_llm import get_llm
        return get_llm()
    except Exception as exc:
        _log(f"LLM init: {exc}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — CLOUD TRAIL (all actions logged everywhere)
# ══════════════════════════════════════════════════════════════════════════════

_TRAIL_DB = os.path.join(os.path.dirname(__file__), "rabbit_trail.db")


@dataclass
class TrailEntry:
    ts: float
    agent: str
    action: str
    target: str
    result_hash: str
    status: str      # ok / error / warn
    duration_ms: float
    platform_os: str = field(default_factory=lambda: platform.system())
    node_id: str = ""
    detail: str = ""


class CloudTrail:
    """
    Logs every agent action to:
    - Local SQLite (always)
    - Supabase REST (when available)
    - Cold network nodes (when mesh is up)
    - IPFS-style content-addressed local store
    """

    def __init__(self, db_path: str = _TRAIL_DB,
                 supabase_url: str = "", service_key: str = "") -> None:
        self._db = db_path
        self._sup_url = supabase_url
        self._sup_key = service_key
        self._lock = threading.Lock()
        self._buffer: deque = deque(maxlen=5000)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db, timeout=10, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS trail (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, agent TEXT, action TEXT, target TEXT,
                    result_hash TEXT, status TEXT, duration_ms REAL,
                    platform_os TEXT, node_id TEXT, detail TEXT
                )""")

    def log(self, agent: str, action: str, target: str,
            result: Any = None, status: str = "ok",
            duration_ms: float = 0.0, node_id: str = "",
            detail: str = "") -> TrailEntry:
        result_bytes = json.dumps(result, default=str).encode() if result else b""
        entry = TrailEntry(
            ts=time.time(), agent=agent, action=action, target=target,
            result_hash=hashlib.sha256(result_bytes).hexdigest()[:16],
            status=status, duration_ms=round(duration_ms, 2),
            node_id=node_id, detail=detail[:500],
        )
        with self._lock:
            self._buffer.append(entry)
            with self._conn() as c:
                c.execute(
                    "INSERT INTO trail VALUES (NULL,?,?,?,?,?,?,?,?,?,?)",
                    (entry.ts, entry.agent, entry.action, entry.target,
                     entry.result_hash, entry.status, entry.duration_ms,
                     entry.platform_os, entry.node_id, entry.detail)
                )
        # Async push to Supabase
        if self._sup_url and self._sup_key:
            threading.Thread(
                target=self._push_supabase, args=(entry,), daemon=True).start()
        return entry

    def _push_supabase(self, entry: TrailEntry) -> None:
        try:
            url  = self._sup_url.rstrip("/") + "/rest/v1/agent_trail"
            data = json.dumps(asdict(entry)).encode()
            req  = urllib.request.Request(url, data=data, method="POST",
                   headers={
                       "Authorization": f"Bearer {self._sup_key}",
                       "apikey": self._sup_key,
                       "Content-Type": "application/json",
                       "Prefer": "return=minimal",
                   })
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            pass

    def query(self, limit: int = 100, agent: str = "") -> List[Dict]:
        with self._lock:
            with self._conn() as c:
                if agent:
                    rows = c.execute(
                        "SELECT * FROM trail WHERE agent=? ORDER BY ts DESC LIMIT ?",
                        (agent, limit)).fetchall()
                else:
                    rows = c.execute(
                        "SELECT * FROM trail ORDER BY ts DESC LIMIT ?",
                        (limit,)).fetchall()
                desc = c.execute("SELECT * FROM trail LIMIT 0").description or []
                cols = [d[0] for d in desc]
                return [dict(zip(cols, r)) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — COLD NETWORK REGISTRY (online/offline node tracker)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class NetworkNode:
    node_id: str
    label: str
    host: str
    port: int
    os_family: str         # Windows/Linux/Android/iOS/BlackBerry/mesh
    device_type: str       # desktop/mobile/embedded/server/mesh_node
    online: bool = False
    last_seen: float = 0.0
    last_offline: float = 0.0
    uptime_pct: float = 0.0
    storage_bytes: int = 0
    storage_free_bytes: int = 0
    llm_model: str = ""
    capabilities: List[str] = field(default_factory=list)
    mac_hash: str = ""


class ColdNetworkRegistry:
    """
    Tracks all connected and disconnected devices/nodes.
    Pings each on a schedule. Stores online/offline history.
    Used to discover storage opportunities for LLM shards.
    """

    _PING_INTERVAL = 60.0

    def __init__(self, trail: Optional[CloudTrail] = None) -> None:
        self._nodes: Dict[str, NetworkNode] = {}
        self._lock  = threading.Lock()
        self._trail = trail
        self._running = False
        self._check_counts: Dict[str, int] = defaultdict(int)
        self._online_counts: Dict[str, int] = defaultdict(int)

    def register(self, node: NetworkNode) -> None:
        with self._lock:
            self._nodes[node.node_id] = node

    def auto_discover(self) -> List[NetworkNode]:
        """Discover nodes from ARP table, mesh, and known service ports."""
        nodes: List[NetworkNode] = []

        # ARP table
        try:
            r = subprocess.run(["arp", "-a"], capture_output=True, text=True,
                                timeout=10, encoding="utf-8", errors="replace")
            for line in r.stdout.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\w\-:]+)", line)
                if m:
                    ip, mac = m.group(1), m.group(2)
                    node_id = hashlib.sha256(ip.encode()).hexdigest()[:12]
                    mac_hash = hashlib.sha256(mac.encode()).hexdigest()[:16]
                    n = NetworkNode(
                        node_id=node_id, label=f"arp_{ip}",
                        host=ip, port=0, os_family="unknown",
                        device_type="unknown", mac_hash=mac_hash,
                    )
                    nodes.append(n)
                    self.register(n)
        except Exception as exc:
            _log(f"ARP discover: {exc}")

        # Mesh EEG nodes
        try:
            from rabbit_defense import EEG_NODE_MAP
            for label, node in EEG_NODE_MAP.items():
                n = NetworkNode(
                    node_id=f"mesh_{node.mesh_node_id}",
                    label=label, host="mesh_rf",
                    port=int(node.carrier_freq_ghz * 1000),
                    os_family="RabbitOS_mesh",
                    device_type="mesh_node",
                    online=node.last_seen > time.time() - 300,
                    last_seen=node.last_seen,
                    llm_model="",
                    capabilities=["eeg", "rf", "biometric"],
                )
                nodes.append(n)
                self.register(n)
        except Exception:
            pass

        _log(f"Auto-discovered {len(nodes)} nodes")
        return nodes

    def _ping_node(self, node: NetworkNode) -> bool:
        if node.host in ("mesh_rf", ""):
            return node.last_seen > time.time() - 300
        try:
            socket.create_connection((node.host, node.port or 80),
                                     timeout=2.0).close()
            return True
        except Exception:
            try:
                result = subprocess.run(
                    ["ping", "-n", "1", "-w", "1000", node.host]
                    if platform.system() == "Windows" else
                    ["ping", "-c", "1", "-W", "1", node.host],
                    capture_output=True, timeout=5)
                return result.returncode == 0
            except Exception:
                return False

    def check_all(self) -> Dict[str, Any]:
        now = time.time()
        online_count = 0
        with self._lock:
            node_list = list(self._nodes.values())

        for node in node_list:
            was_online = node.online
            node.online = self._ping_node(node)
            self._check_counts[node.node_id] += 1
            if node.online:
                self._online_counts[node.node_id] += 1
                node.last_seen = now
                online_count += 1
            else:
                if was_online:
                    node.last_offline = now
            c = self._check_counts[node.node_id]
            o = self._online_counts[node.node_id]
            node.uptime_pct = round((o / c) * 100, 1) if c else 0.0

        if self._trail:
            self._trail.log("ColdNetworkRegistry", "check_all", "all_nodes",
                            result={"online": online_count, "total": len(node_list)})
        return {"online": online_count, "total": len(node_list), "ts": now}

    def get_online(self) -> List[NetworkNode]:
        with self._lock:
            return [n for n in self._nodes.values() if n.online]

    def get_offline(self) -> List[NetworkNode]:
        with self._lock:
            return [n for n in self._nodes.values() if not n.online]

    def to_dict(self) -> List[Dict]:
        with self._lock:
            return [asdict(n) for n in self._nodes.values()]

    def start_background(self, interval: float = _PING_INTERVAL) -> None:
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                try:
                    self.check_all()
                except Exception as exc:
                    _log(f"Node check error: {exc}")
                time.sleep(interval)

        threading.Thread(target=_loop, daemon=True,
                         name="cold_net_check").start()
        _log("ColdNetworkRegistry background check started")

    def stop(self) -> None:
        self._running = False


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — STORAGE DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

STORAGE_BACKENDS: Dict[str, Dict] = {
    "local_ssd":    {"type": "local",       "protocol": "file",   "latency": "low",    "cost": "free"},
    "local_mesh":   {"type": "distributed", "protocol": "udp_rf", "latency": "ultra",  "cost": "free"},
    "ipfs":         {"type": "p2p",         "protocol": "ipfs",   "latency": "medium", "cost": "free"},
    "storj":        {"type": "cloud_p2p",   "protocol": "storj",  "latency": "medium", "cost": "low"},
    "cloudflare_r2":{"type": "cloud",       "protocol": "s3",     "latency": "low",    "cost": "low"},
    "aws_s3":       {"type": "cloud",       "protocol": "s3",     "latency": "medium", "cost": "medium"},
    "supabase":     {"type": "postgres",    "protocol": "rest",   "latency": "low",    "cost": "free_tier"},
    "sqlite":       {"type": "local",       "protocol": "file",   "latency": "ultra",  "cost": "free"},
    "leveldb":      {"type": "local",       "protocol": "file",   "latency": "ultra",  "cost": "free"},
    "redis":        {"type": "in_memory",   "protocol": "tcp",    "latency": "ultra",  "cost": "free_local"},
    "cold_nodes":   {"type": "mesh_nodes",  "protocol": "http",   "latency": "variable","cost": "free"},
}


class StorageDiscovery:
    """
    Discovers and probes available storage backends for use by the LLM network.
    Scores each on latency, capacity, reliability, and cost.
    """

    def __init__(self, trail: Optional[CloudTrail] = None) -> None:
        self._trail = trail
        self._available: Dict[str, Dict] = {}

    def probe_local(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        # SQLite
        try:
            test_db = os.path.join(tempfile.gettempdir(), "_rabbitos_test.db")
            import tempfile
            c = sqlite3.connect(test_db)
            c.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
            c.execute("INSERT INTO t VALUES ('test')")
            c.commit()
            c.close()
            os.unlink(test_db)
            results["sqlite"] = {"available": True, "latency": "ultra"}
        except Exception as e:
            results["sqlite"] = {"available": False, "error": str(e)}

        # Disk space
        try:
            stat = os.statvfs(".") if hasattr(os, "statvfs") else None
            if stat:
                free_gb = stat.f_bavail * stat.f_frsize / 1e9
                results["local_ssd"] = {"available": True, "free_gb": round(free_gb, 1)}
            else:
                import shutil
                total, used, free = shutil.disk_usage(".")
                results["local_ssd"] = {"available": True,
                                         "free_gb": round(free / 1e9, 1)}
        except Exception as e:
            results["local_ssd"] = {"available": False, "error": str(e)}

        return results

    def probe_ipfs(self, host: str = "127.0.0.1", port: int = 5001) -> Dict:
        try:
            req = urllib.request.Request(
                f"http://{host}:{port}/api/v0/version",
                headers={"User-Agent": "RabbitOS"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read())
            return {"available": True, "version": data.get("Version", ""),
                    "host": host, "port": port}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def probe_redis(self, host: str = "127.0.0.1", port: int = 6379) -> Dict:
        try:
            s = socket.create_connection((host, port), timeout=2)
            s.sendall(b"PING\r\n")
            resp = s.recv(32).decode("utf-8", errors="replace")
            s.close()
            return {"available": "+PONG" in resp, "host": host, "port": port}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def probe_s3_compatible(self, endpoint: str) -> Dict:
        try:
            req = urllib.request.Request(endpoint,
                                          headers={"User-Agent": "RabbitOS"})
            with urllib.request.urlopen(req, timeout=5) as r:
                return {"available": True, "endpoint": endpoint, "status": r.status}
        except Exception as e:
            return {"available": False, "endpoint": endpoint, "error": str(e)}

    def probe_cold_nodes(self, registry: ColdNetworkRegistry) -> Dict:
        online = registry.get_online()
        storage_nodes = []
        for node in online:
            if node.storage_bytes > 0 or node.device_type in ("server", "desktop"):
                storage_nodes.append({
                    "node_id": node.node_id,
                    "label": node.label,
                    "storage_bytes": node.storage_bytes,
                    "capabilities": node.capabilities,
                })
        return {
            "available": len(storage_nodes) > 0,
            "node_count": len(storage_nodes),
            "nodes": storage_nodes,
        }

    def discover_all(self, registry: Optional[ColdNetworkRegistry] = None) -> Dict[str, Any]:
        t0 = time.time()
        results = {}
        results.update(self.probe_local())
        results["ipfs"]    = self.probe_ipfs()
        results["redis"]   = self.probe_redis()

        if registry:
            results["cold_nodes"] = self.probe_cold_nodes(registry)

        # Rank by availability + latency
        ranked = sorted(
            [(k, v) for k, v in results.items() if v.get("available")],
            key=lambda x: {"ultra": 0, "low": 1, "medium": 2,
                            "variable": 3}.get(
                STORAGE_BACKENDS.get(x[0], {}).get("latency", "medium"), 2)
        )
        results["ranked_available"] = [k for k, _ in ranked]
        results["discovery_ms"] = round((time.time() - t0) * 1000, 2)

        if self._trail:
            self._trail.log("StorageDiscovery", "discover_all", "all_backends",
                            result={"found": len(ranked)})
        return results

    def best_backend(self, results: Dict) -> str:
        ranked = results.get("ranked_available", [])
        return ranked[0] if ranked else "sqlite"


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — LLM NETWORK STORE (distributed LLM storage via mesh nodes)
# ══════════════════════════════════════════════════════════════════════════════

class LLMNetworkStore:
    """
    Uses cold network nodes as distributed storage for LLM model shards,
    embeddings, and conversation context. Each shard is content-addressed
    (SHA-256) and replicated across N available nodes.
    """

    SHARD_SIZE = 64 * 1024   # 64 kB per shard
    REPLICATION = 2

    def __init__(self, registry: ColdNetworkRegistry,
                 trail: Optional[CloudTrail] = None) -> None:
        self._registry = registry
        self._trail    = trail
        self._index: Dict[str, Dict] = {}   # content_hash -> shard metadata
        self._local_cache: Dict[str, bytes] = {}
        self._lock = threading.Lock()

    def _shard(self, data: bytes) -> List[Tuple[str, bytes]]:
        shards = []
        for i in range(0, len(data), self.SHARD_SIZE):
            chunk = data[i:i + self.SHARD_SIZE]
            h = hashlib.sha256(chunk).hexdigest()
            shards.append((h, chunk))
        return shards

    def store(self, key: str, data: bytes) -> Dict[str, Any]:
        shards = self._shard(data)
        online = self._registry.get_online()
        metadata = {
            "key": key,
            "total_bytes": len(data),
            "shard_count": len(shards),
            "shard_hashes": [],
            "node_ids": [],
            "ts": time.time(),
        }

        for shard_hash, shard_bytes in shards:
            metadata["shard_hashes"].append(shard_hash)
            with self._lock:
                self._local_cache[shard_hash] = shard_bytes

            # Push to online nodes via HTTP (if they have REST endpoint)
            pushed = 0
            for node in online[:self.REPLICATION]:
                if node.host == "mesh_rf":
                    continue
                try:
                    url = f"http://{node.host}:{node.port or 8080}/shard"
                    payload = json.dumps({
                        "shard_hash": shard_hash,
                        "data_b64": base64.b64encode(shard_bytes).decode(),
                    }).encode()
                    req = urllib.request.Request(url, data=payload, method="POST",
                          headers={"Content-Type": "application/json",
                                   "User-Agent": "RabbitOS"})
                    with urllib.request.urlopen(req, timeout=5):
                        pushed += 1
                        metadata["node_ids"].append(node.node_id)
                except Exception:
                    pass

        with self._lock:
            self._index[key] = metadata

        if self._trail:
            self._trail.log("LLMNetworkStore", "store", key,
                            result={"shards": len(shards)})
        return metadata

    def retrieve(self, key: str) -> Optional[bytes]:
        with self._lock:
            meta = self._index.get(key)
        if not meta:
            return None

        chunks = []
        for h in meta["shard_hashes"]:
            with self._lock:
                chunk = self._local_cache.get(h)
            if chunk:
                chunks.append(chunk)
            else:
                chunks.append(b"")

        data = b"".join(chunks)
        if self._trail:
            self._trail.log("LLMNetworkStore", "retrieve", key,
                            result={"bytes": len(data)})
        return data if any(c for c in chunks) else None

    def index_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "key_count": len(self._index),
                "cached_shards": len(self._local_cache),
                "total_cached_bytes": sum(len(v) for v in self._local_cache.values()),
                "keys": list(self._index.keys()),
            }


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — BROWSER AGENT
# ══════════════════════════════════════════════════════════════════════════════

class BrowserAgent:
    """
    Research agent: fetches, parses, and cross-validates web content.
    Uses rabbit_llm for synthesis. Logs all actions to CloudTrail.
    """

    HEADERS = {
        "User-Agent": "RabbitOS-BrowserAgent/1.0 (+https://github.com/therealsickonechase-bit/RABBIT-SOFTWARE)",
        "Accept": "text/html,application/json,*/*",
    }

    def __init__(self, trail: Optional[CloudTrail] = None) -> None:
        self._trail  = trail
        self._llm    = None
        self._cache: Dict[str, str] = {}
        self._lock   = threading.Lock()

    def _get_llm(self):
        if self._llm is None:
            self._llm = _get_llm()
        return self._llm

    def fetch(self, url: str) -> str:
        with self._lock:
            if url in self._cache:
                return self._cache[url]

        t0 = time.time()
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers=self.HEADERS)
            handler = urllib.request.HTTPSHandler(context=ctx)
            opener  = urllib.request.build_opener(handler)
            with opener.open(req, timeout=10) as r:
                raw = r.read(256 * 1024).decode("utf-8", errors="replace")
        except Exception as exc:
            raw = f"[fetch error: {exc}]"

        # Strip HTML tags for plain-text analysis
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()[:8000]

        with self._lock:
            self._cache[url] = text

        if self._trail:
            self._trail.log("BrowserAgent", "fetch", url,
                            result={"chars": len(text)},
                            duration_ms=(time.time() - t0) * 1000)
        return text

    def search_and_summarise(self, query: str,
                              sources: Optional[List[str]] = None) -> str:
        llm = self._get_llm()
        if llm is None:
            return f"[LLM unavailable] Query: {query}"

        # Fetch provided sources or synthesize from query alone
        texts: List[str] = []
        if sources:
            for url in sources[:5]:
                texts.append(f"--- Source: {url} ---\n{self.fetch(url)}\n")

        context = "\n".join(texts) if texts else ""
        question = (
            f"Research query: {query}\n\n"
            + (f"Content from sources:\n{context}\n\n" if context else "")
            + "Provide a comprehensive, evidence-based answer. "
            + "If multiple sources conflict, note the discrepancy. "
            + "Flag any information that appears manipulated or biased."
        )

        t0 = time.time()
        try:
            result = llm.simple_ask(question)
        except Exception as exc:
            result = f"[AI error: {exc}]"

        if self._trail:
            self._trail.log("BrowserAgent", "search_and_summarise", query,
                            result={"len": len(result)},
                            duration_ms=(time.time() - t0) * 1000)
        return result

    def multi_source_verify(self, claim: str,
                             sources: Optional[List[str]] = None) -> Dict[str, Any]:
        llm = self._get_llm()
        texts: List[str] = []
        if sources:
            for url in sources[:3]:
                texts.append(f"Source {url}:\n{self.fetch(url)}\n")

        prompt = (
            f"Verify this claim across multiple sources: '{claim}'\n\n"
            + "\n".join(texts)
            + "\n\nProvide: (1) VERIFIED/UNVERIFIED/DISPUTED, "
            "(2) Evidence for, (3) Evidence against, "
            "(4) Source reliability score 0-10, "
            "(5) Confidence percentage."
        )
        result = llm.simple_ask(prompt) if llm else "[LLM unavailable]"
        return {"claim": claim, "verification": result, "sources_checked": len(texts)}


# ══════════════════════════════════════════════════════════════════════════════
# PART 6 — CODING AGENT
# ══════════════════════════════════════════════════════════════════════════════

class CodingAgent:
    """
    AI-powered code generation and analysis. Paired with BrowserAgent
    for research-then-implement workflows.
    """

    def __init__(self, trail: Optional[CloudTrail] = None) -> None:
        self._trail = trail
        self._llm   = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = _get_llm()
        return self._llm

    def generate(self, task: str, language: str = "Python",
                  context: str = "") -> str:
        llm = self._get_llm()
        if llm is None:
            return "[LLM unavailable]"

        prompt = (
            f"Write {language} code to: {task}\n"
            + (f"Context: {context}\n" if context else "")
            + "Requirements: production-quality, no debug prints, "
            "handle errors gracefully, no hardcoded secrets."
        )
        t0 = time.time()
        try:
            result = llm.simple_ask(prompt)
        except Exception as exc:
            result = f"[error: {exc}]"
        if self._trail:
            self._trail.log("CodingAgent", "generate", task,
                            result={"chars": len(result)},
                            duration_ms=(time.time() - t0) * 1000)
        return result

    def review(self, code: str) -> str:
        llm = self._get_llm()
        if llm is None:
            return "[LLM unavailable]"
        prompt = (
            f"Review this code for: security vulnerabilities (OWASP top 10), "
            f"performance issues, logic errors, and Python best practices.\n\n"
            f"```python\n{code[:4000]}\n```\n\n"
            f"Provide: (1) Critical issues, (2) Warnings, (3) Suggestions, "
            f"(4) CVSS risk estimate for any security issues."
        )
        return llm.simple_ask(prompt)

    def explain(self, code: str) -> str:
        llm = self._get_llm()
        if llm is None:
            return "[LLM unavailable]"
        prompt = (
            f"Explain what this code does, step by step, "
            f"in plain language suitable for a non-programmer:\n\n"
            f"```\n{code[:4000]}\n```"
        )
        return llm.simple_ask(prompt)

    def research_then_implement(self, task: str,
                                  browser: Optional[BrowserAgent] = None) -> Dict[str, Any]:
        research = ""
        if browser:
            research = browser.search_and_summarise(
                f"How to implement: {task} in Python, best practices, security")

        code = self.generate(task, context=research[:2000])
        return {"task": task, "research": research, "code": code}


# ══════════════════════════════════════════════════════════════════════════════
# PART 7 — VOICE ASSISTANT
# ══════════════════════════════════════════════════════════════════════════════

class VoiceAssistant:
    """
    Cross-platform TTS (text-to-speech) and STT (speech-to-text).
    TTS priority: pyttsx3 (offline) > gTTS (online) > espeak (Linux)
    STT priority: whisper (local) > vosk (offline) > Google (online)
    """

    def __init__(self, trail: Optional[CloudTrail] = None) -> None:
        self._trail  = trail
        self._engine: Any = None
        self._tts_backend = self._detect_tts()

    def _detect_tts(self) -> str:
        try:
            import pyttsx3
            return "pyttsx3"
        except ImportError:
            pass
        if platform.system() == "Linux":
            r = subprocess.run(["which", "espeak"], capture_output=True)
            if r.returncode == 0:
                return "espeak"
        try:
            from gtts import gTTS
            return "gtts"
        except ImportError:
            pass
        return "none"

    def speak(self, text: str, lang: str = "en", voice_id: str = "") -> bool:
        t0 = time.time()
        ok = False

        if self._tts_backend == "pyttsx3":
            try:
                import pyttsx3
                if self._engine is None:
                    self._engine = pyttsx3.init()
                if voice_id:
                    voices = self._engine.getProperty("voices")
                    for v in voices:
                        if voice_id.lower() in v.name.lower():
                            self._engine.setProperty("voice", v.id)
                            break
                self._engine.say(text)
                self._engine.runAndWait()
                ok = True
            except Exception as exc:
                _log(f"pyttsx3 error: {exc}")

        elif self._tts_backend == "gtts":
            try:
                from gtts import gTTS
                import tempfile, os
                tts = gTTS(text=text, lang=lang)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    tts.save(f.name)
                    mp3 = f.name
                if platform.system() == "Windows":
                    os.startfile(mp3)
                elif platform.system() == "Darwin":
                    subprocess.run(["afplay", mp3])
                else:
                    subprocess.run(["mpg123", mp3],
                                   capture_output=True, timeout=60)
                os.unlink(mp3)
                ok = True
            except Exception as exc:
                _log(f"gTTS error: {exc}")

        elif self._tts_backend == "espeak":
            try:
                subprocess.run(["espeak", "-v", lang, text],
                               timeout=30, capture_output=True)
                ok = True
            except Exception as exc:
                _log(f"espeak error: {exc}")

        if self._trail:
            self._trail.log("VoiceAssistant", "speak", text[:50],
                            result={"ok": ok, "backend": self._tts_backend},
                            duration_ms=(time.time() - t0) * 1000)
        return ok

    def listen(self, duration_seconds: int = 5) -> str:
        """Listen for speech and return transcription."""
        # Try Whisper first
        try:
            import whisper, tempfile, sounddevice as sd, numpy as np, scipy.io.wavfile
            fs = 16000
            _log(f"Listening for {duration_seconds}s...")
            audio = sd.rec(int(duration_seconds * fs), samplerate=fs,
                           channels=1, dtype="int16")
            sd.wait()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                scipy.io.wavfile.write(f.name, fs, audio)
                wav = f.name
            model = whisper.load_model("base")
            result = model.transcribe(wav)
            os.unlink(wav)
            return result.get("text", "")
        except Exception:
            pass

        # Vosk fallback
        try:
            import vosk, sounddevice as sd, json as _json
            model = vosk.Model(lang="en-us")
            rec   = vosk.KaldiRecognizer(model, 16000)
            with sd.RawInputStream(samplerate=16000, blocksize=8000,
                                   dtype="int16", channels=1) as stream:
                for _ in range(duration_seconds * 2):
                    data, _ = stream.read(8000)
                    rec.AcceptWaveform(bytes(data))
            r = _json.loads(rec.FinalResult())
            return r.get("text", "")
        except Exception as exc:
            _log(f"STT unavailable: {exc}")
            return ""

    def speak_and_listen(self, question: str) -> str:
        self.speak(question)
        return self.listen(duration_seconds=8)

    def llm_voice_loop(self, context: str = "") -> None:
        """Interactive voice conversation with LLM until user says 'quit'."""
        llm = _get_llm()
        if llm is None:
            _log("LLM unavailable for voice loop")
            return

        self.speak("RabbitOS voice assistant ready. Say quit to exit.")
        while True:
            text = self.listen(duration_seconds=8)
            if not text:
                continue
            _log(f"User said: {text}")
            if "quit" in text.lower():
                self.speak("Goodbye.")
                break
            try:
                reply = llm.simple_ask(text, context=context)
            except Exception as exc:
                reply = f"Error: {exc}"
            _log(f"AI reply: {reply[:100]}")
            self.speak(reply[:500])


# ══════════════════════════════════════════════════════════════════════════════
# PART 8 — CALLING AGENT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CallSession:
    call_id: str
    direction: str    # inbound / outbound
    remote: str
    protocol: str     # webrtc / sip / pstn_twilio / mesh_udp
    started_ts: float
    ended_ts: float = 0.0
    duration_s: float = 0.0
    status: str = "ringing"
    transcript: str = ""


class CallingAgent:
    """
    Call management: WebRTC data channel, SIP UDP, PSTN (Twilio API),
    mesh-internal UDP voice (push-to-talk).
    """

    def __init__(self, trail: Optional[CloudTrail] = None) -> None:
        self._trail   = trail
        self._sessions: Dict[str, CallSession] = {}
        self._lock    = threading.Lock()
        self._voice   = VoiceAssistant(trail=trail)

    def _gen_call_id(self) -> str:
        return hashlib.sha256(
            f"{time.time()}{os.urandom(8).hex()}".encode()).hexdigest()[:12]

    def initiate_mesh_call(self, remote_node_id: str,
                            remote_host: str, remote_port: int = 9090) -> CallSession:
        """UDP push-to-talk call to another mesh node."""
        call_id = self._gen_call_id()
        sess = CallSession(
            call_id=call_id, direction="outbound",
            remote=f"{remote_host}:{remote_port}",
            protocol="mesh_udp", started_ts=time.time(),
            status="connecting",
        )
        with self._lock:
            self._sessions[call_id] = sess

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            hello = json.dumps({
                "type": "call_init",
                "call_id": call_id,
                "from": "RabbitOS",
                "ts": time.time(),
            }).encode()
            s.sendto(hello, (remote_host, remote_port))
            s.settimeout(3.0)
            resp = s.recv(512)
            s.close()
            if resp:
                sess.status = "connected"
                _log(f"Mesh call connected: {call_id} -> {remote_host}:{remote_port}")
        except Exception as exc:
            sess.status = f"failed: {exc}"
            _log(f"Mesh call failed: {exc}")

        if self._trail:
            self._trail.log("CallingAgent", "mesh_call", remote_node_id,
                            result={"status": sess.status})
        return sess

    def sip_register(self, server: str, user: str, password: str,
                      port: int = 5060) -> Dict[str, Any]:
        """Send a SIP REGISTER over UDP."""
        call_id = self._gen_call_id()
        sip_msg = (
            f"REGISTER sip:{server} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP 0.0.0.0:5060;rport\r\n"
            f"From: <sip:{user}@{server}>;tag={call_id}\r\n"
            f"To: <sip:{user}@{server}>\r\n"
            f"Call-ID: {call_id}@rabbitos\r\n"
            f"CSeq: 1 REGISTER\r\n"
            f"Contact: <sip:{user}@0.0.0.0:5060>\r\n"
            f"Expires: 3600\r\n"
            f"Content-Length: 0\r\n\r\n"
        )
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(5.0)
            s.sendto(sip_msg.encode(), (server, port))
            resp = s.recv(2048).decode("utf-8", errors="replace")
            s.close()
            ok = "200 OK" in resp or "401" in resp
            return {"registered": ok, "response": resp[:200], "server": server}
        except Exception as exc:
            return {"registered": False, "error": str(exc), "server": server}

    def twilio_call(self, account_sid: str, auth_token: str,
                    from_number: str, to_number: str,
                    twiml_url: str) -> Dict[str, Any]:
        """Initiate PSTN call via Twilio REST API."""
        url  = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
        auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        data = urllib.parse.urlencode({
            "From": from_number, "To": to_number, "Url": twiml_url,
        }).encode()
        req  = urllib.request.Request(url, data=data, method="POST",
               headers={"Authorization": f"Basic {auth}",
                        "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = json.loads(r.read())
            call_id = resp.get("sid", "")
            sess = CallSession(
                call_id=call_id, direction="outbound",
                remote=to_number, protocol="pstn_twilio",
                started_ts=time.time(), status=resp.get("status", "queued"),
            )
            with self._lock:
                self._sessions[call_id] = sess
            return asdict(sess)
        except Exception as exc:
            return {"error": str(exc)}

    def end_call(self, call_id: str) -> bool:
        with self._lock:
            sess = self._sessions.get(call_id)
        if not sess:
            return False
        sess.ended_ts  = time.time()
        sess.duration_s = sess.ended_ts - sess.started_ts
        sess.status    = "ended"
        _log(f"Call ended: {call_id} duration={sess.duration_s:.1f}s")
        return True

    def list_sessions(self) -> List[Dict]:
        with self._lock:
            return [asdict(s) for s in self._sessions.values()]


# ══════════════════════════════════════════════════════════════════════════════
# PART 9 — CROSS-PLATFORM ASSISTANT ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class AssistantOrchestrator:
    _instance: Optional["AssistantOrchestrator"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "AssistantOrchestrator":
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

        self.trail      = CloudTrail()
        self.registry   = ColdNetworkRegistry(trail=self.trail)
        self.storage    = StorageDiscovery(trail=self.trail)
        self.llm_store  = LLMNetworkStore(self.registry, trail=self.trail)
        self.browser    = BrowserAgent(trail=self.trail)
        self.coder      = CodingAgent(trail=self.trail)
        self.voice      = VoiceAssistant(trail=self.trail)
        self.caller     = CallingAgent(trail=self.trail)
        _log("AssistantOrchestrator initialised")

    def start(self) -> None:
        self.registry.auto_discover()
        self.registry.start_background()
        self.trail.log("AssistantOrchestrator", "start", "all_agents",
                        result={"status": "running"})
        _log("AssistantOrchestrator started")

    def status(self) -> Dict[str, Any]:
        online = self.registry.get_online()
        offline = self.registry.get_offline()
        storage_info = self.storage.discover_all(self.registry)
        return {
            "online_nodes": len(online),
            "offline_nodes": len(offline),
            "total_nodes": len(online) + len(offline),
            "storage_backends": storage_info.get("ranked_available", []),
            "best_storage": storage_info.get("ranked_available", ["none"])[0] if storage_info.get("ranked_available") else "none",
            "llm_store_index": self.llm_store.index_summary(),
            "trail_count": len(self.trail.query(limit=1)),
            "tts_backend": self.voice._tts_backend,
            "shows_dna_root": False,
        }

    def chat(self, message: str, voice_response: bool = False) -> str:
        llm = _get_llm()
        if llm is None:
            return "[LLM unavailable]"
        t0 = time.time()
        try:
            reply = llm.simple_ask(message)
        except Exception as exc:
            reply = f"[error: {exc}]"
        self.trail.log("AssistantOrchestrator", "chat", message[:50],
                        result={"chars": len(reply)},
                        duration_ms=(time.time() - t0) * 1000)
        if voice_response:
            self.voice.speak(reply[:500])
        return reply


def get_assistant() -> AssistantOrchestrator:
    return AssistantOrchestrator()


# ══════════════════════════════════════════════════════════════════════════════
# ASSISTANT TOOLS + DISPATCHER
# ══════════════════════════════════════════════════════════════════════════════

ASSISTANT_TOOLS = [
    {
        "name": "assistant_status",
        "description": "Get cross-platform assistant status: nodes, storage, TTS, trail",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "assistant_start",
        "description": "Start assistant: auto-discover nodes, begin monitoring",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "assistant_chat",
        "description": "Send a message to the AI assistant, optionally speak the response",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "voice":   {"type": "boolean", "description": "Speak response aloud"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "assistant_browser_fetch",
        "description": "Fetch and parse a URL",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "assistant_browser_research",
        "description": "Research a topic, optionally using provided URLs as sources",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":   {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
        },
    },
    {
        "name": "assistant_browser_verify",
        "description": "Cross-source verify a claim",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim":   {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["claim"],
        },
    },
    {
        "name": "assistant_code_generate",
        "description": "Generate code for a task",
        "input_schema": {
            "type": "object",
            "properties": {
                "task":     {"type": "string"},
                "language": {"type": "string"},
                "context":  {"type": "string"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "assistant_code_review",
        "description": "AI code review for security and correctness",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    {
        "name": "assistant_code_research_implement",
        "description": "Research then implement a coding task using browser + coding agent",
        "input_schema": {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
    },
    {
        "name": "assistant_voice_speak",
        "description": "Speak text aloud using TTS",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "lang": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "assistant_voice_listen",
        "description": "Listen for speech and return transcription",
        "input_schema": {
            "type": "object",
            "properties": {"duration": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "assistant_voice_loop",
        "description": "Start interactive voice conversation with AI",
        "input_schema": {
            "type": "object",
            "properties": {"context": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "assistant_call_mesh",
        "description": "Initiate UDP voice call to a mesh node",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "host":    {"type": "string"},
                "port":    {"type": "integer"},
            },
            "required": ["node_id", "host"],
        },
    },
    {
        "name": "assistant_call_sip",
        "description": "Register with a SIP server",
        "input_schema": {
            "type": "object",
            "properties": {
                "server":   {"type": "string"},
                "user":     {"type": "string"},
                "password": {"type": "string"},
                "port":     {"type": "integer"},
            },
            "required": ["server", "user", "password"],
        },
    },
    {
        "name": "assistant_call_end",
        "description": "End an active call session",
        "input_schema": {
            "type": "object",
            "properties": {"call_id": {"type": "string"}},
            "required": ["call_id"],
        },
    },
    {
        "name": "assistant_call_list",
        "description": "List all call sessions",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "assistant_nodes_discover",
        "description": "Auto-discover all network nodes (ARP + mesh)",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "assistant_nodes_check",
        "description": "Check online/offline status of all registered nodes",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "assistant_nodes_list",
        "description": "List all nodes with online/offline status",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "assistant_storage_discover",
        "description": "Discover and probe available storage backends",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "assistant_llm_store",
        "description": "Store data on LLM network (distributed across cold nodes)",
        "input_schema": {
            "type": "object",
            "properties": {
                "key":       {"type": "string"},
                "data_b64":  {"type": "string", "description": "base64-encoded data"},
            },
            "required": ["key", "data_b64"],
        },
    },
    {
        "name": "assistant_llm_retrieve",
        "description": "Retrieve data from LLM network store",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "assistant_trail_query",
        "description": "Query the cloud trail log",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "agent": {"type": "string"},
            },
            "required": [],
        },
    },
]


def dispatch_assistant_tool(name: str, inputs: Dict,
                              api_key: str = "", service_key: str = "") -> Any:
    eng = get_assistant()

    if name == "assistant_status":
        return eng.status()

    elif name == "assistant_start":
        eng.start()
        return {"started": True}

    elif name == "assistant_chat":
        return {"reply": eng.chat(inputs["message"],
                                   voice_response=inputs.get("voice", False))}

    elif name == "assistant_browser_fetch":
        return {"text": eng.browser.fetch(inputs["url"])}

    elif name == "assistant_browser_research":
        return {"result": eng.browser.search_and_summarise(
            inputs["query"], inputs.get("sources"))}

    elif name == "assistant_browser_verify":
        return eng.browser.multi_source_verify(
            inputs["claim"], inputs.get("sources"))

    elif name == "assistant_code_generate":
        return {"code": eng.coder.generate(
            inputs["task"],
            language=inputs.get("language", "Python"),
            context=inputs.get("context", ""))}

    elif name == "assistant_code_review":
        return {"review": eng.coder.review(inputs["code"])}

    elif name == "assistant_code_research_implement":
        return eng.coder.research_then_implement(inputs["task"], eng.browser)

    elif name == "assistant_voice_speak":
        ok = eng.voice.speak(inputs["text"], lang=inputs.get("lang", "en"))
        return {"spoken": ok, "backend": eng.voice._tts_backend}

    elif name == "assistant_voice_listen":
        text = eng.voice.listen(inputs.get("duration", 5))
        return {"transcription": text}

    elif name == "assistant_voice_loop":
        threading.Thread(
            target=eng.voice.llm_voice_loop,
            args=(inputs.get("context", ""),),
            daemon=True).start()
        return {"started": True, "note": "Voice loop running in background"}

    elif name == "assistant_call_mesh":
        sess = eng.caller.initiate_mesh_call(
            inputs["node_id"], inputs["host"],
            inputs.get("port", 9090))
        return asdict(sess)

    elif name == "assistant_call_sip":
        return eng.caller.sip_register(
            inputs["server"], inputs["user"], inputs["password"],
            inputs.get("port", 5060))

    elif name == "assistant_call_end":
        ok = eng.caller.end_call(inputs["call_id"])
        return {"ended": ok}

    elif name == "assistant_call_list":
        return eng.caller.list_sessions()

    elif name == "assistant_nodes_discover":
        nodes = eng.registry.auto_discover()
        return {"discovered": len(nodes), "nodes": [asdict(n) for n in nodes[:20]]}

    elif name == "assistant_nodes_check":
        return eng.registry.check_all()

    elif name == "assistant_nodes_list":
        return eng.registry.to_dict()

    elif name == "assistant_storage_discover":
        return eng.storage.discover_all(eng.registry)

    elif name == "assistant_llm_store":
        data = base64.b64decode(inputs["data_b64"])
        meta = eng.llm_store.store(inputs["key"], data)
        return meta

    elif name == "assistant_llm_retrieve":
        data = eng.llm_store.retrieve(inputs["key"])
        if data is None:
            return {"found": False}
        return {"found": True, "data_b64": base64.b64encode(data).decode(),
                "bytes": len(data)}

    elif name == "assistant_trail_query":
        return eng.trail.query(
            limit=inputs.get("limit", 50),
            agent=inputs.get("agent", ""))

    else:
        return {"error": f"Unknown assistant tool: {name}"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RabbitOS Assistant")
    parser.add_argument("--status",    action="store_true")
    parser.add_argument("--discover",  action="store_true")
    parser.add_argument("--storage",   action="store_true")
    parser.add_argument("--chat",      type=str, metavar="MESSAGE")
    parser.add_argument("--speak",     type=str, metavar="TEXT")
    parser.add_argument("--listen",    action="store_true")
    parser.add_argument("--voice-loop",action="store_true")
    args = parser.parse_args()

    eng = get_assistant()
    if args.status:
        print(json.dumps(eng.status(), indent=2, default=str))
    elif args.discover:
        nodes = eng.registry.auto_discover()
        print(json.dumps([asdict(n) for n in nodes], indent=2, default=str))
    elif args.storage:
        print(json.dumps(eng.storage.discover_all(eng.registry), indent=2, default=str))
    elif args.chat:
        print(eng.chat(args.chat))
    elif args.speak:
        eng.voice.speak(args.speak)
    elif args.listen:
        print("Transcription:", eng.voice.listen())
    elif args.voice_loop:
        eng.voice.llm_voice_loop()
    else:
        parser.print_help()
