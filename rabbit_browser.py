#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_browser.py — RabbitOS Browser Agent + ML Learning Engine
================================================================
Cross-platform web agent that:
  - Crawls public code, papers, tools, APIs (GitHub/PyPI/HuggingFace/arXiv/npm)
  - Learns offline/online/sleep mode using local ML + deep learning if available
  - Embeds learned improvements back into RabbitOS knowledge graph
  - Travels with Chase Allen Ringquist across all networks
  - Runs in console mode with full network tool integration per OS
  - Works with embedded tokens/weights that persist locally

No external browser required — pure HTTP(S) requests.
Respects public API rate limits. Uses only public/open data.
"""

from __future__ import annotations
import base64, hashlib, hmac, html, json, math, os, pickle, platform
import queue, re, shutil, socket, sqlite3, struct, subprocess, sys, threading
import time, traceback, urllib.error, urllib.parse, urllib.request
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

# ─── Identity ─────────────────────────────────────────────────────────────────
TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"
_SOUL_KEY  = hashlib.sha256(f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()).digest()

BROWSER_DB   = Path(__file__).parent / "rabbit_browser.db"
BROWSER_LOG  = Path(__file__).parent / "rabbit_browser.log"
MODEL_DIR    = Path(__file__).parent / "rabbit_models"
CACHE_DIR    = Path(__file__).parent / "rabbit_cache"

MODEL_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# ─── HTTP Browser ──────────────────────────────────────────────────────────────
class HTTPBrowser:
    """
    Pure Python HTTP(S) browser. No selenium. Works in console.
    Rate-limited, cached, user-agent rotated.
    """

    USER_AGENTS = [
        "RabbitOS/14 (Chase Allen Ringquist; +https://github.com/therealsickonechase-bit/RABBIT-SOFTWARE)",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "curl/8.5.0",
        "python-requests/2.31.0",
    ]

    def __init__(self, cache_db: Path = BROWSER_DB, timeout: int = 12):
        self._timeout   = timeout
        self._cache_db  = cache_db
        self._ua_idx    = 0
        self._lock      = threading.Lock()
        self._last_fetch: Dict[str, float] = {}  # domain → last_time
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self._cache_db))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS page_cache (
                url         TEXT PRIMARY KEY,
                content     TEXT,
                status      INTEGER,
                fetched_at  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_tools (
                name        TEXT PRIMARY KEY,
                description TEXT,
                url         TEXT,
                category    TEXT,
                stars       INTEGER DEFAULT 0,
                score       REAL DEFAULT 0.0,
                payload     TEXT,
                learned_at  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_embeddings (
                key         TEXT PRIMARY KEY,
                vector      BLOB,
                dim         INTEGER,
                updated_at  TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _next_ua(self) -> str:
        ua = self.USER_AGENTS[self._ua_idx % len(self.USER_AGENTS)]
        self._ua_idx += 1
        return ua

    def _rate_limit(self, domain: str, min_gap: float = 1.0):
        with self._lock:
            last = self._last_fetch.get(domain, 0)
            wait = min_gap - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            self._last_fetch[domain] = time.time()

    def fetch(self, url: str, use_cache: bool = True,
              cache_ttl_hours: int = 24) -> Tuple[int, str]:
        """Fetch URL, return (status_code, body_text)."""
        # Check cache
        if use_cache:
            cached = self._from_cache(url, cache_ttl_hours)
            if cached is not None:
                return 200, cached

        domain = urllib.parse.urlparse(url).netloc
        self._rate_limit(domain)

        try:
            req = urllib.request.Request(url,
                headers={"User-Agent": self._next_ua(),
                         "Accept": "application/json, text/html, */*",
                         "Accept-Language": "en-US,en;q=0.9"})
            resp = urllib.request.urlopen(req, timeout=self._timeout)
            body = resp.read().decode(errors="replace")
            status = resp.status
            if use_cache and status == 200:
                self._to_cache(url, body, status)
            return status, body
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception as e:
            return 0, str(e)

    def fetch_json(self, url: str, use_cache: bool = True) -> Optional[Any]:
        status, body = self.fetch(url, use_cache)
        if status == 200 and body:
            try:
                return json.loads(body)
            except Exception:
                pass
        return None

    def _from_cache(self, url: str, ttl_hours: int) -> Optional[str]:
        try:
            conn = sqlite3.connect(str(self._cache_db))
            row  = conn.execute(
                "SELECT content, fetched_at FROM page_cache WHERE url=?", (url,)
            ).fetchone()
            conn.close()
            if row:
                fetched = datetime.fromisoformat(row[1])
                age_h   = (datetime.now(timezone.utc) - fetched.replace(
                    tzinfo=timezone.utc)).total_seconds() / 3600
                if age_h < ttl_hours:
                    return row[0]
        except Exception:
            pass
        return None

    def _to_cache(self, url: str, content: str, status: int):
        try:
            conn = sqlite3.connect(str(self._cache_db))
            conn.execute("""
                INSERT OR REPLACE INTO page_cache (url, content, status, fetched_at)
                VALUES (?,?,?,?)
            """, (url, content[:500_000], status,
                  datetime.now(timezone.utc).isoformat()))
            conn.commit()
            conn.close()
        except Exception:
            pass


# ─── Minimal HTML parser ──────────────────────────────────────────────────────
def _strip_html(raw: str) -> str:
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', raw, flags=re.S|re.I)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.S|re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def _extract_links(html_body: str, base_url: str) -> List[str]:
    links = re.findall(r'href=["\']([^"\']+)["\']', html_body, re.I)
    result = []
    for link in links:
        try:
            full = urllib.parse.urljoin(base_url, link)
            if full.startswith("http"):
                result.append(full)
        except Exception:
            pass
    return result[:50]


# ─── Public Data Sources ───────────────────────────────────────────────────────
class PublicCodeHarvester:
    """
    Pulls public code, tools, models, papers from open APIs.
    All data is public domain / open source.
    """

    GITHUB_API   = "https://api.github.com"
    PYPI_API     = "https://pypi.org/pypi"
    HF_API       = "https://huggingface.co/api"
    ARXIV_API    = "https://export.arxiv.org/api/query"
    NPM_API      = "https://registry.npmjs.org"

    # Topics that improve RabbitOS
    TOPICS = [
        "software-defined-radio", "gnuradio", "hackrf", "rtlsdr",
        "network-scanning", "packet-capture", "bluetooth-le",
        "mesh-networking", "peer-to-peer", "tor-network",
        "machine-learning", "neural-network", "deep-learning",
        "natural-language-processing", "embeddings",
        "biometrics", "eeg", "heart-rate-variability",
        "cryptography", "zero-knowledge-proof", "blockchain",
        "iot", "embedded-systems", "rtos",
        "port-scanning", "network-security", "intrusion-detection",
        "dns", "protocol-analysis", "pcap",
        # Biological / environmental data storage
        "dna-data-storage", "dna-computing", "synthetic-biology",
        "mycelium-network", "fungal-communication", "bioacoustics",
        "molecular-communication", "chemical-signaling", "bioelectronics",
        "atmospheric-sensor", "barometric-pressure-data", "weather-data-network",
        "ads-b", "air-traffic-data", "1090mhz",
        "rf-biology", "bio-inspired-computing", "slime-mold-network",
        "quorum-sensing", "plant-electrical-signal", "neuromorphic-computing",
    ]

    PYPI_PACKAGES = [
        "scapy", "impacket", "pyshark", "dpkt",
        "gnuradio", "pyrtlsdr", "osmosdr",
        "sklearn", "numpy", "scipy", "torch", "tensorflow",
        "transformers", "sentence-transformers", "onnxruntime",
        "redis", "psycopg2", "pymongo", "elasticsearch",
        "cryptography", "pyopenssl", "paramiko",
        "celery", "aiomqtt", "paho-mqtt",
        "mne", "pyedflib", "biosppy",
        "networkx", "igraph", "pyvis",
        "requests", "httpx", "aiohttp",
    ]

    HF_MODELS = [
        "sentence-transformers/all-MiniLM-L6-v2",
        "microsoft/codebert-base",
        "facebook/bart-base",
        "openai/whisper-tiny",
        "google/flan-t5-small",
    ]

    ARXIV_QUERIES = [
        "mesh network survival autonomous",
        "edge computing offline machine learning",
        "federated learning privacy preserving",
        "biometric authentication neural network",
        "software defined radio deep learning",
        "network anomaly detection LSTM",
        "distributed systems self-healing",
        # Biological / environmental data channels
        "DNA data storage encoding retrieval",
        "fungal mycelium network information transfer",
        "molecular communication channel capacity",
        "atmospheric pressure data encoding signal",
        "ADS-B air traffic surveillance data extraction",
        "RF signal biological tissue propagation",
        "chemical signaling network distributed computing",
        "slime mold Physarum network optimization",
        "plant electrical signal data encoding",
        "quorum sensing distributed information",
    ]

    def __init__(self, browser: HTTPBrowser, gh_token: str = ""):
        self._browser   = browser
        self._gh_token  = gh_token

    def harvest_github_repos(self, topic: str, limit: int = 5) -> List[Dict]:
        url  = (f"{self.GITHUB_API}/search/repositories"
                f"?q=topic:{topic}&sort=stars&order=desc&per_page={limit}")
        headers_extra = {}
        if self._gh_token:
            headers_extra["Authorization"] = f"token {self._gh_token}"
        data = self._browser.fetch_json(url, use_cache=True)
        if not data:
            return []
        items = data.get("items", [])
        result = []
        for item in items:
            result.append({
                "name":        item.get("full_name", ""),
                "description": item.get("description", "")[:200],
                "stars":       item.get("stargazers_count", 0),
                "language":    item.get("language", ""),
                "url":         item.get("html_url", ""),
                "clone_url":   item.get("clone_url", ""),
                "topics":      item.get("topics", []),
                "updated_at":  item.get("updated_at", ""),
            })
        return result

    def harvest_pypi_package(self, name: str) -> Optional[Dict]:
        url  = f"{self.PYPI_API}/{name}/json"
        data = self._browser.fetch_json(url)
        if not data:
            return None
        info = data.get("info", {})
        return {
            "name":        info.get("name", name),
            "version":     info.get("version", ""),
            "summary":     info.get("summary", "")[:300],
            "home_page":   info.get("home_page", ""),
            "keywords":    info.get("keywords", ""),
            "requires":    (info.get("requires_dist") or [])[:10],
            "downloads":   data.get("urls", [{}])[0].get("downloads", 0),
        }

    def harvest_huggingface_model(self, model_id: str) -> Optional[Dict]:
        url  = f"{self.HF_API}/models/{model_id}"
        data = self._browser.fetch_json(url)
        if not data:
            return None
        return {
            "id":          data.get("id", model_id),
            "pipeline":    data.get("pipeline_tag", ""),
            "downloads":   data.get("downloads", 0),
            "likes":       data.get("likes", 0),
            "tags":        data.get("tags", [])[:10],
            "library":     data.get("library_name", ""),
            "description": str(data.get("cardData", {}).get("language", ""))[:200],
        }

    def harvest_arxiv_papers(self, query: str, max_results: int = 5) -> List[Dict]:
        params = urllib.parse.urlencode({
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        })
        url    = f"{self.ARXIV_API}?{params}"
        status, body = self._browser.fetch(url)
        if status != 200 or not body:
            return []
        papers = []
        entries = re.findall(r'<entry>(.*?)</entry>', body, re.S)
        for entry in entries:
            title   = re.search(r'<title>(.*?)</title>', entry, re.S)
            summary = re.search(r'<summary>(.*?)</summary>', entry, re.S)
            link    = re.search(r'<id>(.*?)</id>', entry, re.S)
            papers.append({
                "title":   _strip_html(title.group(1)).strip() if title else "",
                "summary": _strip_html(summary.group(1)).strip()[:400] if summary else "",
                "url":     link.group(1).strip() if link else "",
            })
        return papers

    def fetch_github_readme(self, full_name: str) -> str:
        url    = f"{self.GITHUB_API}/repos/{full_name}/readme"
        data   = self._browser.fetch_json(url)
        if not data:
            return ""
        content_b64 = data.get("content", "")
        try:
            return base64.b64decode(content_b64.replace("\n","")).decode(errors="replace")[:8000]
        except Exception:
            return ""

    def fetch_pypi_source_snippet(self, name: str) -> str:
        """Fetch top-level __init__.py from PyPI source if available."""
        url    = f"{self.PYPI_API}/{name}/json"
        data   = self._browser.fetch_json(url)
        if not data:
            return ""
        src_url = data.get("info", {}).get("home_page", "")
        if "github.com" in src_url:
            # Try to fetch raw __init__.py
            parts = src_url.rstrip("/").split("/")
            if len(parts) >= 5:
                owner, repo = parts[-2], parts[-1]
                raw = (f"https://raw.githubusercontent.com/{owner}/{repo}/"
                       f"main/{repo}/__init__.py")
                _, body = self._browser.fetch(raw)
                return body[:3000]
        return ""


# ─── Pure-Python ML Engine ────────────────────────────────────────────────────
class LocalMLEngine:
    """
    Self-contained ML engine. Runs on pure Python with no dependencies.
    If numpy/torch/sklearn are present, uses them for better performance.
    Models are saved to disk and travel with Chase.
    """

    def __init__(self, model_dir: Path = MODEL_DIR):
        self._dir     = model_dir
        self._vocab:  Dict[str, int]   = {}
        self._idf:    Dict[int, float] = {}
        self._weights: Dict[str, Any]  = {}
        self._lock    = threading.Lock()
        self._load_state()

        # Optional acceleration
        self._np  = None
        self._torch = None
        try:
            import numpy as np
            self._np = np
        except ImportError:
            pass
        try:
            import torch
            self._torch = torch
        except ImportError:
            pass

    # ── Text Vectorization (TF-IDF, pure Python) ──────────────────────────────
    def tokenize(self, text: str) -> List[str]:
        text = text.lower()
        tokens = re.findall(r"[a-z][a-z0-9_]{2,}", text)
        return tokens

    def build_vocab(self, documents: List[str]):
        """Build vocabulary and IDF weights from a corpus."""
        all_tokens: Counter = Counter()
        doc_freq:   Counter = Counter()
        for doc in documents:
            toks = set(self.tokenize(doc))
            all_tokens.update(toks)
            doc_freq.update(toks)
        # Keep top 8192 tokens
        top = [tok for tok, _ in all_tokens.most_common(8192)]
        self._vocab = {tok: i for i, tok in enumerate(top)}
        N = len(documents)
        self._idf = {}
        for tok, idx in self._vocab.items():
            df = doc_freq.get(tok, 1)
            self._idf[idx] = math.log((N + 1) / (df + 1)) + 1.0
        self._save_state()

    def vectorize(self, text: str) -> List[float]:
        """TF-IDF vector (sparse via list). Pure Python."""
        toks = self.tokenize(text)
        tf: Counter = Counter(toks)
        total = max(len(toks), 1)
        vec = [0.0] * len(self._vocab)
        for tok, count in tf.items():
            idx = self._vocab.get(tok)
            if idx is not None:
                vec[idx] = (count / total) * self._idf.get(idx, 1.0)
        return vec

    def cosine_sim(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        if self._np:
            an = self._np.array(a)
            bn = self._np.array(b)
            denom = self._np.linalg.norm(an) * self._np.linalg.norm(bn)
            if denom == 0:
                return 0.0
            return float(self._np.dot(an, bn) / denom)
        # Pure Python
        dot   = sum(x*y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x*x for x in a))
        norm_b = math.sqrt(sum(x*x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ── Simple Neural Net (pure Python, no deps) ──────────────────────────────
    def _sigmoid(self, x: float) -> float:
        return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))

    def classify(self, vec: List[float], classes: List[str]) -> str:
        """Simple linear classifier using stored weights."""
        best_cls  = classes[0] if classes else "unknown"
        best_score = -float("inf")
        for cls in classes:
            w = self._weights.get(f"w_{cls}", [])
            if not w or len(w) != len(vec):
                continue
            score = sum(a * b for a, b in zip(vec, w))
            if score > best_score:
                best_score = score
                best_cls   = cls
        return best_cls

    def train_sgd(self, examples: List[Tuple[List[float], str]],
                  classes: List[str], lr: float = 0.01, epochs: int = 5):
        """One-vs-rest SGD logistic regression, pure Python."""
        dim = len(examples[0][0]) if examples else 0
        if dim == 0:
            return
        # Init weights
        for cls in classes:
            key = f"w_{cls}"
            if key not in self._weights or len(self._weights[key]) != dim:
                self._weights[key] = [0.0] * dim

        for _ in range(epochs):
            for vec, label in examples:
                for cls in classes:
                    target = 1.0 if cls == label else 0.0
                    w = self._weights[f"w_{cls}"]
                    raw = sum(a * b for a, b in zip(vec, w))
                    pred = self._sigmoid(raw)
                    err  = pred - target
                    self._weights[f"w_{cls}"] = [
                        wi - lr * err * xi for wi, xi in zip(w, vec)
                    ]
        self._save_state()

    # ── Character N-gram Embeddings (no external deps) ────────────────────────
    def char_ngram_embed(self, text: str, n: int = 3, dim: int = 64) -> List[float]:
        """Character trigram hash embedding."""
        text   = text.lower()[:256]
        vec    = [0.0] * dim
        for i in range(len(text) - n + 1):
            gram = text[i:i+n]
            h    = int(hashlib.md5(gram.encode()).hexdigest(), 16) % dim
            vec[h] += 1.0
        total = sum(vec) or 1.0
        return [v / total for v in vec]

    # ── Deep Learning Bridge (torch/transformers if available) ─────────────────
    def deep_embed(self, text: str) -> Optional[List[float]]:
        """Use sentence-transformers if installed for real embeddings."""
        try:
            from sentence_transformers import SentenceTransformer
            model_path = self._dir / "sentence_model"
            if model_path.exists():
                m = SentenceTransformer(str(model_path))
            else:
                m = SentenceTransformer("all-MiniLM-L6-v2")
                m.save(str(model_path))
            emb = m.encode(text[:512])
            return emb.tolist()
        except Exception:
            pass
        return None

    def load_onnx_model(self, model_name: str):
        """Load ONNX model from local cache if available."""
        try:
            import onnxruntime as ort
            path = self._dir / f"{model_name}.onnx"
            if path.exists():
                return ort.InferenceSession(str(path))
        except Exception:
            pass
        return None

    # ── Persistence ────────────────────────────────────────────────────────────
    def _save_state(self):
        try:
            state = {"vocab": self._vocab, "idf": self._idf,
                     "weights": self._weights}
            with open(self._dir / "ml_state.pkl", "wb") as f:
                pickle.dump(state, f)
        except Exception:
            pass

    def _load_state(self):
        try:
            path = self._dir / "ml_state.pkl"
            if path.exists():
                with open(path, "rb") as f:
                    state = pickle.load(f)
                self._vocab   = state.get("vocab", {})
                self._idf     = state.get("idf", {})
                self._weights = state.get("weights", {})
        except Exception:
            pass

    def score_tool_for_rabbitos(self, name: str, description: str,
                                 readme: str = "") -> float:
        """Score how useful a tool/library is for improving RabbitOS."""
        KEYWORDS = {
            "sdr": 3.0, "radio": 2.5, "rf": 2.0, "gnuradio": 3.0,
            "hackrf": 3.0, "rtlsdr": 3.0, "spectrum": 2.0,
            "mesh": 2.5, "p2p": 2.0, "distributed": 1.5,
            "biometric": 3.0, "eeg": 3.0, "hrv": 2.5, "neural": 2.0,
            "packet": 2.0, "scapy": 2.5, "pcap": 2.0, "network": 1.5,
            "encrypt": 2.0, "crypto": 1.5, "zero-knowledge": 2.5,
            "embedding": 2.0, "transformer": 2.0, "llm": 1.5,
            "iot": 1.5, "bluetooth": 2.0, "wifi": 2.0, "cellular": 2.5,
            "survival": 2.0, "resilient": 1.5, "fault-tolerant": 1.5,
            "offline": 2.0, "sync": 1.5, "peer": 2.0,
            "autonomous": 2.0, "self-healing": 2.5, "adaptive": 2.0,
        }
        text  = f"{name} {description} {readme[:2000]}".lower()
        score = 0.0
        for kw, weight in KEYWORDS.items():
            if kw in text:
                score += weight
        return min(score, 20.0)


# ─── Cross-Platform Console Network Tools ─────────────────────────────────────
class CrossPlatformConsole:
    """
    Detects OS and runs native network/system tools.
    Learns new tools available on the current system.
    Works in Windows PowerShell, Linux bash, macOS zsh.
    """

    TOOLS_BY_OS: Dict[str, List[Dict]] = {
        "Windows": [
            {"name": "netsh",      "cmd": ["netsh", "wlan", "show", "networks"],     "category": "wifi"},
            {"name": "netstat",    "cmd": ["netstat", "-ano"],                        "category": "connections"},
            {"name": "arp",        "cmd": ["arp", "-a"],                              "category": "lan"},
            {"name": "nslookup",   "cmd": ["nslookup", "supabase.com"],               "category": "dns"},
            {"name": "tracert",    "cmd": ["tracert", "-d", "-h", "5", "8.8.8.8"],   "category": "routing"},
            {"name": "ipconfig",   "cmd": ["ipconfig", "/all"],                       "category": "interfaces"},
            {"name": "route",      "cmd": ["route", "print"],                         "category": "routing"},
            {"name": "netsh_mbn",  "cmd": ["netsh", "mbn", "show", "interfaces"],    "category": "cellular"},
            {"name": "powershell_wifi",
             "cmd": ["powershell", "-Command",
                     "(netsh wlan show interfaces) -match 'Signal'"],                 "category": "wifi"},
            {"name": "tasklist",   "cmd": ["tasklist", "/FO", "CSV"],                "category": "processes"},
            {"name": "wmic_cpu",   "cmd": ["wmic", "cpu", "get", "loadpercentage"],  "category": "system"},
        ],
        "Linux": [
            {"name": "iwlist",     "cmd": ["iwlist", "scan"],                         "category": "wifi"},
            {"name": "netstat",    "cmd": ["netstat", "-tulpn"],                      "category": "connections"},
            {"name": "ss",         "cmd": ["ss", "-tulpn"],                           "category": "connections"},
            {"name": "arp",        "cmd": ["arp", "-n"],                              "category": "lan"},
            {"name": "dig",        "cmd": ["dig", "supabase.com"],                    "category": "dns"},
            {"name": "traceroute", "cmd": ["traceroute", "-n", "-m", "5", "8.8.8.8"],"category": "routing"},
            {"name": "ip_addr",    "cmd": ["ip", "addr"],                             "category": "interfaces"},
            {"name": "ip_route",   "cmd": ["ip", "route"],                            "category": "routing"},
            {"name": "mmcli",      "cmd": ["mmcli", "-L"],                            "category": "cellular"},
            {"name": "lsblk",      "cmd": ["lsblk"],                                 "category": "storage"},
            {"name": "dmesg_net",  "cmd": ["dmesg", "|", "grep", "net"],             "category": "system"},
            {"name": "rfkill",     "cmd": ["rfkill", "list"],                         "category": "rf"},
        ],
        "Darwin": [  # macOS
            {"name": "airport",
             "cmd": ["/System/Library/PrivateFrameworks/Apple80211.framework/"
                     "Versions/Current/Resources/airport", "-s"],                     "category": "wifi"},
            {"name": "netstat",    "cmd": ["netstat", "-an"],                         "category": "connections"},
            {"name": "arp",        "cmd": ["arp", "-a"],                              "category": "lan"},
            {"name": "dig",        "cmd": ["dig", "supabase.com"],                    "category": "dns"},
            {"name": "traceroute", "cmd": ["traceroute", "-n", "-m", "5", "8.8.8.8"],"category": "routing"},
            {"name": "ifconfig",   "cmd": ["ifconfig"],                               "category": "interfaces"},
            {"name": "system_profiler",
             "cmd": ["system_profiler", "SPNetworkDataType"],                         "category": "system"},
        ],
    }

    def __init__(self):
        self._os      = platform.system()
        self._results: Dict[str, str] = {}
        self._avail:   Set[str]       = set()
        self._detect_installed_tools()

    def _detect_installed_tools(self):
        """Find which tools are actually installed on this system."""
        check_tools = [
            "python3", "python", "node", "npm", "git", "curl", "wget",
            "nmap", "masscan", "wireshark", "tshark",
            "gnuradio-companion", "hackrf_info", "rtl_test",
            "ffmpeg", "sox", "gqrx",
            "docker", "kubectl", "terraform",
            "gcc", "clang", "make", "cmake",
            "pip3", "pip", "cargo", "go", "rustc",
            "nc", "ncat", "socat", "ssh", "scp",
            "tcpdump", "aircrack-ng", "kismet",
            "mmcli", "rfkill", "iwconfig", "iwlist",
        ]
        for tool in check_tools:
            path = shutil.which(tool)
            if path:
                self._avail.add(tool)

    def run_tool(self, name: str, timeout: int = 8) -> str:
        tools = self.TOOLS_BY_OS.get(self._os, [])
        for t in tools:
            if t["name"] == name:
                try:
                    cmd = t["cmd"]
                    # Handle piped commands on linux
                    if "|" in cmd:
                        result = subprocess.run(
                            " ".join(cmd), shell=True, capture_output=True,
                            text=True, timeout=timeout, errors="replace")
                    else:
                        result = subprocess.run(
                            cmd, capture_output=True, text=True,
                            timeout=timeout, errors="replace")
                    return result.stdout + result.stderr
                except Exception as e:
                    return str(e)
        return f"tool {name} not found for {self._os}"

    def run_all(self, categories: Optional[List[str]] = None) -> Dict[str, str]:
        results = {}
        tools   = self.TOOLS_BY_OS.get(self._os, [])
        for t in tools:
            if categories and t["category"] not in categories:
                continue
            results[t["name"]] = self.run_tool(t["name"])
        self._results = results
        return results

    def available_tools(self) -> List[str]:
        return sorted(self._avail)

    def install_python_pkg(self, package: str) -> str:
        """Install a Python package via pip for self-improvement."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", package],
                capture_output=True, text=True, timeout=120, errors="replace")
            return ("ok" if result.returncode == 0
                    else result.stderr[:200])
        except Exception as e:
            return str(e)

    def learn_new_tool(self, tool_name: str) -> Dict:
        """Discover a tool's capabilities from --help output."""
        info = {}
        for flag in ["--help", "-h", "--version"]:
            try:
                result = subprocess.run(
                    [tool_name, flag], capture_output=True, text=True,
                    timeout=5, errors="replace")
                out = (result.stdout + result.stderr)[:1000]
                if out.strip():
                    info[flag] = out
                    break
            except Exception:
                pass
        return {"tool": tool_name, "info": info,
                "available": bool(shutil.which(tool_name))}


# ─── Sleep Mode Learner ───────────────────────────────────────────────────────
class SleepModeLearner:
    """
    Detects when the system is idle and runs deep background learning.
    Keeps learning even when the user is not actively using the terminal.
    """

    IDLE_THRESHOLD_SECS = 120  # 2 minutes of no user input = "sleep mode"

    def __init__(self, ml: LocalMLEngine, harvester: PublicCodeHarvester,
                 console: CrossPlatformConsole):
        self._ml        = ml
        self._harvester = harvester
        self._console   = console
        self._last_active = time.time()
        self._sleeping  = False
        self._corpus:   List[str] = []
        self._lock      = threading.Lock()
        self._queue:    queue.Queue = queue.Queue()
        t = threading.Thread(target=self._sleep_loop, daemon=True)
        t.start()

    def ping(self):
        """Call this on any user activity to reset idle timer."""
        self._last_active = time.time()
        self._sleeping    = False

    def queue_task(self, task: Dict):
        """Queue a learning task for sleep-mode execution."""
        self._queue.put(task)

    def _idle_seconds(self) -> float:
        return time.time() - self._last_active

    def _sleep_loop(self):
        time.sleep(10)
        while True:
            try:
                idle = self._idle_seconds()
                if idle >= self.IDLE_THRESHOLD_SECS:
                    if not self._sleeping:
                        self._sleeping = True
                    self._do_sleep_work()
                time.sleep(30)
            except Exception:
                time.sleep(60)

    def _do_sleep_work(self):
        """Perform one unit of background learning work."""
        # Process queued tasks first
        try:
            task = self._queue.get_nowait()
            self._execute_task(task)
            return
        except queue.Empty:
            pass

        # Auto-generate background work
        import random
        choices = [
            self._learn_random_topic,
            self._train_ml_model,
            self._run_console_tools,
        ]
        random.choice(choices)()

    def _learn_random_topic(self):
        try:
            import random
            topic = random.choice(self._harvester.TOPICS)
            repos = self._harvester.harvest_github_repos(topic, limit=3)
            for repo in repos:
                readme = self._harvester.fetch_github_readme(repo["name"])
                if readme:
                    with self._lock:
                        self._corpus.append(readme[:2000])
        except Exception:
            pass

    def _train_ml_model(self):
        with self._lock:
            corpus = list(self._corpus[-500:])  # last 500 docs
        if len(corpus) < 10:
            return
        self._ml.build_vocab(corpus)

    def _run_console_tools(self):
        self._console.run_all(categories=["wifi", "lan", "interfaces"])

    def _execute_task(self, task: Dict):
        kind = task.get("kind", "")
        if kind == "fetch_url":
            self._harvester._browser.fetch(task.get("url", ""))
        elif kind == "train":
            docs = task.get("docs", [])
            if docs:
                self._ml.build_vocab(docs)
        elif kind == "install_pkg":
            self._console.install_python_pkg(task.get("package", ""))

    @property
    def is_sleeping(self) -> bool:
        return self._sleeping

    def status(self) -> Dict:
        return {
            "sleeping":      self._sleeping,
            "idle_secs":     int(self._idle_seconds()),
            "corpus_size":   len(self._corpus),
            "queue_depth":   self._queue.qsize(),
            "vocab_size":    len(self._ml._vocab),
        }


# ─── Knowledge Embedder ───────────────────────────────────────────────────────
class KnowledgeEmbedder:
    """
    Takes learned tools/models/papers and feeds them back into
    the RabbitOS KnowledgeGraph so the system improves automatically.
    """

    def __init__(self, ml: LocalMLEngine):
        self._ml = ml

    def embed_tool(self, tool: Dict, genesis_graph=None) -> bool:
        name   = tool.get("name", "")
        desc   = tool.get("description", "")
        cat    = tool.get("category", "tool")
        score  = self._ml.score_tool_for_rabbitos(name, desc)

        if genesis_graph is None:
            return False
        try:
            key = f"tool:{name}"
            genesis_graph.nodes[key] = {
                "kind":        "tool",
                "name":        name,
                "description": desc[:200],
                "category":    cat,
                "score":       score,
                "ts":          datetime.now(timezone.utc).isoformat(),
            }
            # Add edges to related existing nodes
            for node_key in list(genesis_graph.nodes.keys())[:20]:
                node = genesis_graph.nodes.get(node_key, {})
                if isinstance(node, dict):
                    node_text = str(node.get("description", "")) + str(node.get("name",""))
                    if any(kw in node_text.lower() for kw in
                           name.lower().split("-") + desc.lower().split()[:5]):
                        genesis_graph.edges.add((key, node_key))
            return True
        except Exception:
            return False

    def embed_paper(self, paper: Dict, genesis_graph=None) -> bool:
        if genesis_graph is None:
            return False
        try:
            key  = f"paper:{hashlib.md5(paper.get('url','').encode()).hexdigest()[:8]}"
            genesis_graph.nodes[key] = {
                "kind":    "paper",
                "title":   paper.get("title", "")[:100],
                "summary": paper.get("summary", "")[:400],
                "url":     paper.get("url", ""),
                "ts":      datetime.now(timezone.utc).isoformat(),
            }
            return True
        except Exception:
            return False


# ─── Browser Engine ───────────────────────────────────────────────────────────
class BrowserEngine:
    """
    Top-level browser/learning orchestrator.
    Runs continuous guardians for online learning, offline caching,
    and sleep-mode deep learning.
    """

    _instance: Optional["BrowserEngine"] = None
    _lock      = threading.Lock()

    def __init__(self, service_key: str = "", gh_token: str = "",
                 genesis_graph=None):
        self._svc_key      = service_key
        self._gh_token     = gh_token
        self._genesis      = genesis_graph

        self.browser       = HTTPBrowser(BROWSER_DB)
        self.harvester     = PublicCodeHarvester(self.browser, gh_token)
        self.ml            = LocalMLEngine(MODEL_DIR)
        self.console       = CrossPlatformConsole()
        self.embedder      = KnowledgeEmbedder(self.ml)
        self.sleep_learner = SleepModeLearner(self.ml, self.harvester, self.console)

        self._learned_tools: List[Dict] = []
        self._learned_papers: List[Dict] = []
        self._tool_lock      = threading.Lock()
        self._running        = False
        self._cycle          = 0

        self._start_guardians()
        self._initial_harvest()

    def _start_guardians(self):
        self._running = True
        for fn, interval, name in [
            (self._guardian_online_harvest,   600, "online_harvest"),   # 10 min
            (self._guardian_console_tools,    300, "console_tools"),    # 5 min
            (self._guardian_ml_train,         900, "ml_train"),         # 15 min
            (self._guardian_embed_knowledge,  180, "embed_knowledge"),  # 3 min
        ]:
            t = threading.Thread(target=self._guardian_loop,
                                 args=(fn, interval, name), daemon=True)
            t.start()

    def _guardian_loop(self, fn, interval: int, name: str):
        time.sleep(15)
        while self._running:
            try:
                fn()
            except Exception as e:
                self._log(f"[Guard:{name}] {e}")
            time.sleep(interval)

    def _initial_harvest(self):
        t = threading.Thread(target=self._do_initial_harvest, daemon=True)
        t.start()

    def _do_initial_harvest(self):
        time.sleep(5)
        self._log("[Browser] Initial harvest starting...")
        # Quick PyPI check for high-value packages
        for pkg in ["scapy", "numpy", "cryptography", "pyrtlsdr"][:4]:
            try:
                info = self.harvester.harvest_pypi_package(pkg)
                if info:
                    tool = {"name": info["name"], "description": info["summary"],
                            "category": "pypi", "url": info["home_page"],
                            "score": self.ml.score_tool_for_rabbitos(
                                info["name"], info["summary"])}
                    with self._tool_lock:
                        self._learned_tools.append(tool)
            except Exception:
                pass
        # Console tools snapshot
        self._guardian_console_tools()
        self._log(f"[Browser] Initial harvest: "
                  f"{len(self._learned_tools)} tools, "
                  f"installed_tools={len(self.console.available_tools())}")

    # ── Guardians ──────────────────────────────────────────────────────────────
    def _guardian_online_harvest(self):
        self._cycle += 1
        import random
        # Alternate: topics → packages → papers → models
        phase = self._cycle % 4
        new_tools = []

        if phase == 0:
            # GitHub topics
            topic = random.choice(self.harvester.TOPICS)
            repos = self.harvester.harvest_github_repos(topic, limit=5)
            for repo in repos:
                score = self.ml.score_tool_for_rabbitos(
                    repo["name"], repo.get("description", ""))
                new_tools.append({
                    "name":        repo["name"],
                    "description": repo.get("description", "")[:200],
                    "stars":       repo.get("stars", 0),
                    "url":         repo.get("url", ""),
                    "category":    f"github:{topic}",
                    "score":       score,
                })
            self._log(f"[Browser] GitHub {topic}: {len(repos)} repos scored")

        elif phase == 1:
            # PyPI packages
            pkgs = random.sample(self.harvester.PYPI_PACKAGES, min(4, len(self.harvester.PYPI_PACKAGES)))
            for pkg in pkgs:
                info = self.harvester.harvest_pypi_package(pkg)
                if info:
                    score = self.ml.score_tool_for_rabbitos(
                        info["name"], info.get("summary",""))
                    new_tools.append({
                        "name":        info["name"],
                        "description": info.get("summary","")[:200],
                        "url":         info.get("home_page",""),
                        "category":    "pypi",
                        "score":       score,
                    })
            self._log(f"[Browser] PyPI: {len(new_tools)} packages scored")

        elif phase == 2:
            # arXiv papers
            query = random.choice(self.harvester.ARXIV_QUERIES)
            papers = self.harvester.harvest_arxiv_papers(query, max_results=5)
            with self._tool_lock:
                self._learned_papers.extend(papers[:5])
            for paper in papers:
                self.embedder.embed_paper(paper, self._genesis)
            self._log(f"[Browser] arXiv '{query}': {len(papers)} papers")

        elif phase == 3:
            # HuggingFace models
            model_id = random.choice(self.harvester.HF_MODELS)
            info = self.harvester.harvest_huggingface_model(model_id)
            if info:
                score = self.ml.score_tool_for_rabbitos(
                    info["id"], " ".join(info.get("tags", [])))
                new_tools.append({
                    "name":        info["id"],
                    "description": info.get("description", "")[:200],
                    "url":         f"https://huggingface.co/{info['id']}",
                    "category":    "huggingface",
                    "score":       score,
                    "pipeline":    info.get("pipeline", ""),
                })
            self._log(f"[Browser] HuggingFace {model_id}: loaded")

        with self._tool_lock:
            self._learned_tools.extend(new_tools)
        # Embed into knowledge graph
        for t in new_tools:
            self.embedder.embed_tool(t, self._genesis)
        # Save to DB
        self._save_tools_db(new_tools)

    def _guardian_console_tools(self):
        results = self.console.run_all(
            categories=["wifi", "lan", "interfaces", "connections"])
        # Feed console output into ML corpus
        combined = " ".join(results.values())[:4000]
        if combined.strip():
            self.sleep_learner._corpus.append(combined)
        # Detect new installed tools and learn them
        avail = self.console.available_tools()
        for tool_name in avail[:5]:
            info = self.console.learn_new_tool(tool_name)
            if info.get("info"):
                desc = list(info["info"].values())[0][:300]
                with self._tool_lock:
                    self._learned_tools.append({
                        "name": tool_name, "description": desc,
                        "category": "system_tool", "score":
                        self.ml.score_tool_for_rabbitos(tool_name, desc)
                    })

    def _guardian_ml_train(self):
        with self._tool_lock:
            corpus = [f"{t['name']} {t['description']}"
                      for t in self._learned_tools if t.get("description")]
        corpus += [f"{p['title']} {p['summary']}"
                   for p in self._learned_papers if p.get("summary")]
        if len(corpus) >= 5:
            self.ml.build_vocab(corpus)
            self._log(f"[Browser:ML] Trained vocab: {len(self.ml._vocab)} tokens "
                      f"from {len(corpus)} docs")

    def _guardian_embed_knowledge(self):
        with self._tool_lock:
            recent = list(self._learned_tools[-20:])
        embedded = 0
        for tool in recent:
            if self.embedder.embed_tool(tool, self._genesis):
                embedded += 1
        if embedded:
            self._log(f"[Browser:embed] {embedded} tools → knowledge graph")

    # ── Public API ──────────────────────────────────────────────────────────────
    def harvest_now(self, topic: str = "") -> Dict:
        """Force immediate harvest of a specific topic or all sources."""
        results = {"repos": [], "packages": [], "papers": [], "models": []}
        if not topic:
            topic = "mesh-networking"
        results["repos"]    = self.harvester.harvest_github_repos(topic, limit=8)
        results["papers"]   = self.harvester.harvest_arxiv_papers(topic, max_results=5)
        # Score and store
        for r in results["repos"]:
            r["score"] = self.ml.score_tool_for_rabbitos(
                r["name"], r.get("description",""))
        with self._tool_lock:
            self._learned_tools.extend([
                {"name": r["name"], "description": r.get("description",""),
                 "category": f"github:{topic}", "score": r["score"],
                 "url": r.get("url","")}
                for r in results["repos"]
            ])
        return results

    def search_tools(self, query: str) -> List[Dict]:
        """Search learned tools by relevance to query."""
        with self._tool_lock:
            tools = list(self._learned_tools)
        if not tools:
            return []
        if not self.ml._vocab:
            # Simple keyword match fallback
            ql = query.lower()
            return sorted([t for t in tools
                           if ql in (t.get("name","") + t.get("description","")).lower()],
                          key=lambda x: -x.get("score", 0))[:10]
        q_vec   = self.ml.vectorize(query)
        scored  = []
        for tool in tools:
            desc  = f"{tool.get('name','')} {tool.get('description','')}"
            t_vec = self.ml.vectorize(desc)
            sim   = self.ml.cosine_sim(q_vec, t_vec)
            scored.append((sim + tool.get("score", 0) * 0.1, tool))
        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored[:15]]

    def install_top_tools(self, limit: int = 5) -> Dict:
        """Auto-install the highest-scored Python packages."""
        with self._tool_lock:
            pypi_tools = [t for t in self._learned_tools if t.get("category") == "pypi"]
        pypi_tools.sort(key=lambda t: -t.get("score", 0))
        results = {}
        for tool in pypi_tools[:limit]:
            name = tool["name"]
            result = self.console.install_python_pkg(name)
            results[name] = result
            self._log(f"[Browser:install] {name}: {result[:50]}")
        return results

    def status(self) -> Dict:
        with self._tool_lock:
            tool_count   = len(self._learned_tools)
            paper_count  = len(self._learned_papers)
            top_tools    = sorted(self._learned_tools,
                                  key=lambda t: -t.get("score", 0))[:8]
        return {
            "twin_id":         TWIN_UUID,
            "tools_learned":   tool_count,
            "papers_learned":  paper_count,
            "vocab_size":      len(self.ml._vocab),
            "ml_weights":      len(self.ml._weights),
            "sleep_status":    self.sleep_learner.status(),
            "installed_tools": self.console.available_tools(),
            "top_tools":       [{"name": t["name"],
                                 "score": round(t.get("score",0), 2),
                                 "category": t.get("category","")}
                                for t in top_tools],
            "cache_db":        str(BROWSER_DB),
            "model_dir":       str(MODEL_DIR),
            "cycle":           self._cycle,
            "ts":              datetime.now(timezone.utc).isoformat(),
        }

    def console_snapshot(self) -> Dict:
        """Full cross-platform network state from OS tools."""
        return {
            "os":      platform.system(),
            "tools":   self.console.run_all(),
            "avail":   self.console.available_tools(),
            "ts":      datetime.now(timezone.utc).isoformat(),
        }

    def _save_tools_db(self, tools: List[Dict]):
        try:
            conn = sqlite3.connect(str(BROWSER_DB))
            for t in tools:
                conn.execute("""
                    INSERT OR REPLACE INTO learned_tools
                    (name, description, url, category, stars, score, payload, learned_at)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (t.get("name",""), t.get("description","")[:300],
                      t.get("url",""), t.get("category",""),
                      int(t.get("stars",0)), float(t.get("score",0)),
                      json.dumps(t)[:2000],
                      datetime.now(timezone.utc).isoformat()))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)
        try:
            with open(BROWSER_LOG, "a") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass


# ─── Singleton ────────────────────────────────────────────────────────────────
_browser_engine: Optional[BrowserEngine] = None
_browser_lock   = threading.Lock()

def get_browser_engine(service_key: str = "", gh_token: str = "",
                       genesis_graph=None) -> BrowserEngine:
    global _browser_engine
    with _browser_lock:
        if _browser_engine is None:
            _browser_engine = BrowserEngine(service_key, gh_token, genesis_graph)
    return _browser_engine


# ─── Tool definitions ─────────────────────────────────────────────────────────
BROWSER_TOOLS = [
    {
        "name": "browser_status",
        "description": "Get browser/ML engine status: tools learned, vocab, sleep mode, top tools.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "browser_harvest",
        "description": "Immediately harvest public code/papers/models for a given topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string",
                          "description": "Topic to harvest (e.g. 'mesh-networking', 'sdr', 'biometrics')"},
            },
            "required": [],
        },
    },
    {
        "name": "browser_search_tools",
        "description": "Search the learned tool database by query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "browser_install_top",
        "description": "Auto-install the top-scored Python packages for RabbitOS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max packages to install"},
            },
            "required": [],
        },
    },
    {
        "name": "browser_console_snapshot",
        "description": "Run all OS network tools and return a full cross-platform network snapshot.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "browser_fetch_url",
        "description": "Fetch any public URL and return text content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_score_tool",
        "description": "Score how useful a tool or library would be for RabbitOS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":        {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name", "description"],
        },
    },
    {
        "name": "browser_install_pkg",
        "description": "Install a Python package via pip to improve RabbitOS capabilities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package name from PyPI"},
            },
            "required": ["package"],
        },
    },
]


def dispatch_browser_tool(name: str, inputs: dict,
                          service_key: str = "", gh_token: str = "",
                          genesis_graph=None) -> dict:
    eng = get_browser_engine(service_key, gh_token, genesis_graph)
    if name == "browser_status":
        return eng.status()
    elif name == "browser_harvest":
        return eng.harvest_now(inputs.get("topic", ""))
    elif name == "browser_search_tools":
        return {"tools": eng.search_tools(inputs.get("query", ""))}
    elif name == "browser_install_top":
        return eng.install_top_tools(int(inputs.get("limit", 5)))
    elif name == "browser_console_snapshot":
        return eng.console_snapshot()
    elif name == "browser_fetch_url":
        status, body = eng.browser.fetch(inputs.get("url", ""))
        return {"status": status, "content": _strip_html(body)[:3000]}
    elif name == "browser_score_tool":
        score = eng.ml.score_tool_for_rabbitos(
            inputs.get("name",""), inputs.get("description",""))
        return {"name": inputs.get("name",""), "score": score}
    elif name == "browser_install_pkg":
        result = eng.console.install_python_pkg(inputs.get("package",""))
        return {"package": inputs.get("package",""), "result": result}
    else:
        return {"error": f"unknown tool: {name}"}


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(
        description="RabbitOS Browser Agent — Chase Allen Ringquist self-learning")
    p.add_argument("--status",    action="store_true", help="Show engine status")
    p.add_argument("--harvest",   metavar="TOPIC",     help="Harvest topic now")
    p.add_argument("--search",    metavar="QUERY",     help="Search learned tools")
    p.add_argument("--install",   action="store_true", help="Auto-install top tools")
    p.add_argument("--console",   action="store_true", help="Run all console tools")
    p.add_argument("--fetch",     metavar="URL",       help="Fetch a URL")
    p.add_argument("--daemon",    action="store_true", help="Run as continuous daemon")
    args = p.parse_args()

    svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    gh  = os.environ.get("GITHUB_TOKEN", "")
    eng = get_browser_engine(svc, gh)

    if args.harvest:
        time.sleep(2)
        import pprint
        result = eng.harvest_now(args.harvest)
        for section, items in result.items():
            if items:
                print(f"\n== {section.upper()} ==")
                for item in items[:5]:
                    if isinstance(item, dict):
                        print(f"  [{item.get('score',0):.1f}] "
                              f"{item.get('name','')[:50]}  "
                              f"stars={item.get('stars',0)}")
                    else:
                        print(f"  {str(item)[:80]}")
    elif args.search:
        time.sleep(3)
        tools = eng.search_tools(args.search)
        for t in tools:
            print(f"  [{t.get('score',0):.2f}] {t.get('name',''):<40} "
                  f"{t.get('description','')[:60]}")
    elif args.install:
        time.sleep(3)
        results = eng.install_top_tools()
        for pkg, res in results.items():
            print(f"  {pkg}: {res}")
    elif args.console:
        snap = eng.console_snapshot()
        print(f"OS: {snap['os']}")
        print(f"Available tools: {snap['avail']}")
        for tool_name, output in snap["tools"].items():
            if output.strip():
                print(f"\n-- {tool_name} --")
                print(output[:400])
    elif args.fetch:
        status, body = eng.browser.fetch(args.fetch, use_cache=False)
        print(f"Status: {status}")
        print(_strip_html(body)[:3000])
    elif args.status or not any(vars(args).values()):
        time.sleep(5)
        import pprint
        pprint.pprint(eng.status())

    if args.daemon:
        print(f"\n[Browser] Daemon running. Learning continuously.")
        print(f"  OS: {platform.system()} | installed tools: {len(eng.console.available_tools())}")
        print("  Harvesting: GitHub / PyPI / arXiv / HuggingFace")
        print("  Sleep mode: learning when idle >2 min")
        print("  Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[Browser] Stopped.")
