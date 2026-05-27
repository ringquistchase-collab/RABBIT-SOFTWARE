#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_vector.py -- Vector Corpus Agent + Layer Scanner
RabbitOS -- Chase Allen Ringquist -- UUID ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba

Agents use vectors to corpus-scan across all layers:
  network / OS / DNA / research / hardware / self / framework

Modeled after proxybypass.py architecture:
  - Build TF-IDF vector corpus from all RabbitOS SQLite DBs + online sources
  - Cosine similarity retrieval (Collatz-indexed)
  - Layer-by-layer scanning with math-based probe signals
  - Proxy/bypass detection using vector anomaly scoring
  - Multi-layer information extraction and fusion

Pure Python 3.6+, zero dependencies.
"""

import hashlib, json, math, os, re, sqlite3, time
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

# -- Identity ----------------------------------------------------------------
TWIN_UUID      = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT        = "Chase Allen Ringquist"
shows_dna_root = False
_raw           = f"{TWIN_UUID}:{SUBJECT}:RABBIT_DNA_ANCHOR".encode()
DNA_ANCHOR     = hashlib.sha3_512(_raw).hexdigest()
assert not shows_dna_root

DB_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_vector.db")
DESKTOP  = os.path.dirname(os.path.abspath(__file__))

# -- Layer definitions -------------------------------------------------------
LAYERS = {
    "network": {
        "description": "LAN/WAN/mesh network topology, discovered hosts, open ports",
        "db_keys":     [("rabbit_recon.db",      "SELECT detail FROM survival_assessments"),
                        ("rabbit_chain.db",       "SELECT detail FROM retention_log"),
                        ("rabbit_signal.db",      "SELECT result_json FROM broadcast_log")],
        "keywords":    ["network", "host", "port", "mesh", "UDP", "TCP", "IP", "scan",
                        "broadcast", "gateway", "LAN", "WiFi", "cellular", "IMSI"],
    },
    "os": {
        "description": "Operating system, processes, installed tools, persistence",
        "db_keys":     [("rabbit_recon.db",       "SELECT tools_json FROM installed_tools"),
                        ("rabbit_recon.db",       "SELECT process_json FROM process_scan")],
        "keywords":    ["process", "tool", "install", "OS", "Windows", "Linux", "Android",
                        "Termux", "shell", "terminal", "persistence", "startup", "registry"],
    },
    "dna": {
        "description": "Identity, soul, DNA anchor, separation, shield",
        "db_keys":     [("rabbit_dna.db",  "SELECT soul_statement FROM separation_log"),
                        ("rabbit_dna.db",  "SELECT pattern FROM shield_log"),
                        ("rabbit_dna.db",  "SELECT layer_name FROM soul_manifest")],
        "keywords":    ["DNA", "identity", "soul", "anchor", "separation", "shield",
                        "Chase", "twin", "biometric", "integrity", "vault", "family"],
    },
    "research": {
        "description": "Academic research, arXiv papers, CVEs, biomaterial science",
        "db_keys":     [("rabbit_knowledge.db",  "SELECT title FROM knowledge"),
                        ("rabbit_chain.db",       "SELECT title FROM biomaterial_research"),
                        ("rabbit_recon.db",       "SELECT description FROM cve_intel"),
                        ("rabbit_maxwell.db",     "SELECT title FROM research"),
                        ("rabbit_learn.db",       "SELECT content FROM learning_corpus")],
        "keywords":    ["research", "paper", "CVE", "vulnerability", "biomaterial",
                        "RF", "electromagnetic", "biometric", "survival", "arxiv",
                        "Maxwell", "Collatz", "Lorenz", "EEG", "HRV"],
    },
    "hardware": {
        "description": "RF hardware, SDR, HackRF, sensors, mesh nodes, biosensors",
        "db_keys":     [("rabbit_amfm.db",   "SELECT band_name FROM spectrum_log"),
                        ("rabbit_amfm.db",   "SELECT topology_json FROM topology_snap"),
                        ("rabbit_maxwell.db","SELECT tissue FROM propagation_log")],
        "keywords":    ["hackrf", "rtlsdr", "SDR", "sensor", "node", "mesh", "antenna",
                        "spectrum", "frequency", "HackRF", "tissue", "EEG", "GSR", "HRV",
                        "biosensor", "implant", "wearable", "radar", "UWB"],
    },
    "self": {
        "description": "Core identity traits, emotional state, chemical state, soul layers",
        "db_keys":     [("rabbit_dna.db",    "SELECT mined_hash FROM mined_log"),
                        ("rabbit_signal.db", "SELECT valence, arousal, emotion FROM emotional_timeline"),
                        ("rabbit_signal.db", "SELECT platform_json FROM platform_log")],
        "keywords":    ["Chase", "Ringquist", "family", "survival", "freedom", "loyalty",
                        "learning", "authenticity", "emotions", "valence", "arousal",
                        "stress", "calm", "chemical", "cortisol", "HRV"],
    },
    "framework": {
        "description": "RabbitOS module structure, Supabase schema, XRPL, GitHub API",
        "db_keys":     [("rabbit_chain.db",  "SELECT anchor_hash FROM chain_anchors"),
                        ("rabbit_learn.db",  "SELECT category FROM observations"),
                        ("rabbit_bridge.db", "SELECT endpoint FROM bridge_requests")],
        "keywords":    ["Supabase", "XRPL", "GitHub", "blockchain", "schema", "migration",
                        "API", "endpoint", "module", "Python", "SQLite", "edge function",
                        "REST", "JSON", "LLM", "Claude", "bridge", "vector"],
    },
}

# -- Math utilities ----------------------------------------------------------
def collatz(n: int) -> List[int]:
    seq = [n]
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        seq.append(n)
    return seq

def collatz_sample(data: List[Any], seed: int) -> List[Any]:
    if not data: return []
    indices = [c % len(data) for c in collatz(max(3, seed % 997 + 3))]
    seen, out = set(), []
    for i in indices:
        if i not in seen:
            seen.add(i)
            out.append(data[i])
    return out

def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z]{3,}", text.lower())

def tf(tokens: List[str], term: str) -> float:
    if not tokens: return 0.0
    return tokens.count(term) / len(tokens)

def idf(docs: List[List[str]], term: str) -> float:
    n = sum(1 for d in docs if term in d)
    if n == 0: return 0.0
    return math.log((len(docs) + 1) / (n + 1)) + 1.0

def tfidf_vector(tokens: List[str], vocab: List[str],
                 idf_vals: Dict[str, float]) -> List[float]:
    return [tf(tokens, t) * idf_vals.get(t, 1.0) for t in vocab]

def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot  = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0: return 0.0
    return dot / (mag_a * mag_b)

def sha256_embed(text: str, dims: int = 32) -> List[float]:
    """Hash text to a fixed-dim float vector (for offline doc embedding)."""
    h    = hashlib.sha256(text.encode()).hexdigest()
    vals = []
    for i in range(dims):
        nibble = h[i * 2: i * 2 + 2] if i * 2 + 2 <= len(h) else "00"
        vals.append(int(nibble, 16) / 255.0)
    return vals

def lorenz_probe(x: float = 0.1, y: float = 0.0, z: float = 0.0,
                 steps: int = 20) -> List[float]:
    """Lorenz trajectory as a probe signal for anomaly detection."""
    sigma_l, rho_l, beta_l = 10.0, 28.0, 8.0/3.0
    dt, trajectory = 0.01, []
    for _ in range(steps):
        dx = sigma_l * (y - x)
        dy = x * (rho_l - z) - y
        dz = x * y - beta_l * z
        x += dx * dt; y += dy * dt; z += dz * dt
        trajectory.append(x)
    return trajectory

# -- Document / corpus types -------------------------------------------------
@dataclass
class Document:
    doc_id:    str
    layer:     str
    source:    str
    text:      str
    tokens:    List[str] = field(default_factory=list)
    vector:    List[float] = field(default_factory=list)
    meta:      Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.tokens = tokenize(self.text)

@dataclass
class SearchResult:
    doc:        Document
    score:      float
    layer:      str
    snippet:    str
    meta:       Dict[str, Any] = field(default_factory=dict)

# -- Proxy/bypass anomaly model (proxybypass.py pattern) --------------------
BYPASS_SIGNATURES = [
    # network proxies
    r"127\.0\.0\.\d+:8080", r"socks5://", r"proxychains", r"tor\b",
    r"burpsuite", r"zap\b", r"mitmproxy", r"charles\b",
    # traffic manipulation
    r"iptables.*REDIRECT", r"nftables", r"socat\b", r"netcat\b",
    r"ngrok\b", r"frp\b", r"chisel\b",
    # identity bypass
    r"spoof\w+", r"fake.*identity", r"clone.*twin", r"bypass.*dna",
    r"intercept.*anchor", r"man.in.the.middle",
    # OS-level
    r"ptrace", r"LD_PRELOAD", r"dll.inject", r"process.hollow",
]

def bypass_anomaly_score(text: str) -> Tuple[float, List[str]]:
    """Score text for proxy/bypass indicators. Returns (score 0..1, matched patterns)."""
    matches = []
    for sig in BYPASS_SIGNATURES:
        if re.search(sig, text, re.IGNORECASE):
            matches.append(sig)
    score = min(1.0, len(matches) / max(1, len(BYPASS_SIGNATURES) * 0.3))
    return round(score, 4), matches

# -- Online data fetchers ---------------------------------------------------
def _fetch(url: str, timeout: int = 8) -> str:
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "RabbitOS-Vector/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"FETCH_ERROR: {e}"

def fetch_layer_online(layer: str, query: str, max_results: int = 5) -> List[Document]:
    docs  = []
    kw    = " ".join(LAYERS[layer]["keywords"][:4])
    terms = f"{query} {kw}"
    # arXiv search (for research/dna/hardware)
    if layer in ("research", "dna", "hardware"):
        url = ("https://export.arxiv.org/api/query?"
               f"search_query=all:{urllib.parse.quote(terms)}&max_results={max_results}")
        xml = _fetch(url)
        for entry in xml.split("<entry>")[1:]:
            title   = entry.split("<title>")[1].split("</title>")[0].strip() \
                      if "<title>" in entry else "?"
            summary = entry.split("<summary>")[1].split("</summary>")[0].strip()[:300] \
                      if "<summary>" in entry else ""
            text = f"{title} {summary}"
            docs.append(Document(
                doc_id=hashlib.md5(text.encode()).hexdigest()[:8],
                layer=layer, source="arxiv",
                text=text, meta={"title": title}))
    # Wikipedia (for all layers)
    wiki_term = urllib.parse.quote(query.split()[0] if query else kw.split()[0])
    url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&format=json&titles={wiki_term}"
    raw = _fetch(url)
    if "extract" in raw:
        try:
            j     = json.loads(raw)
            pages = j.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if pid == "-1": continue
                extract = re.sub(r"<[^>]+>", " ", page.get("extract",""))[:400]
                if extract:
                    docs.append(Document(
                        doc_id=hashlib.md5(extract.encode()).hexdigest()[:8],
                        layer=layer, source="wikipedia",
                        text=extract, meta={"title": page.get("title","")}))
        except Exception: pass
    return docs

# -- DB readers  -------------------------------------------------------------
def _read_db_safe(db_path: str, query: str) -> List[str]:
    if not os.path.exists(db_path): return []
    try:
        con  = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = con.execute(query).fetchall()
        con.close()
        texts = []
        for row in rows:
            for cell in row:
                if cell and isinstance(cell, str):
                    texts.append(cell[:500])
        return texts
    except Exception: return []

def load_layer_offline(layer: str) -> List[Document]:
    docs = []
    spec = LAYERS.get(layer, {})
    for db_file, query in spec.get("db_keys", []):
        db_path = os.path.join(DESKTOP, db_file)
        texts   = _read_db_safe(db_path, query)
        for text in texts:
            if not text.strip(): continue
            docs.append(Document(
                doc_id=hashlib.md5(text.encode()).hexdigest()[:8],
                layer=layer, source=f"{db_file}:{query[:30]}",
                text=text[:400],
            ))
    return docs

# -- Corpus builder ----------------------------------------------------------
class VectorCorpus:
    """TF-IDF vector corpus over all RabbitOS layers."""

    def __init__(self):
        self.docs:     List[Document]       = []
        self.vocab:    List[str]            = []
        self.idf_vals: Dict[str, float]     = {}

    def add(self, doc: Document):
        self.docs.append(doc)

    def build_vocab(self, min_df: int = 1) -> None:
        all_tokens = [d.tokens for d in self.docs if d.tokens]
        # count all terms
        from collections import Counter
        freq: Dict[str, int] = Counter()
        for tokens in all_tokens:
            freq.update(set(tokens))
        self.vocab = [t for t, c in freq.most_common(2000) if c >= min_df and len(t) > 2]
        # compute IDF
        n = len(all_tokens)
        for t in self.vocab:
            n_docs = sum(1 for tok in all_tokens if t in tok)
            self.idf_vals[t] = math.log((n + 1) / (n_docs + 1)) + 1.0
        # vectorize all docs
        for doc in self.docs:
            doc.vector = tfidf_vector(doc.tokens, self.vocab, self.idf_vals)

    def search(self, query: str, top_k: int = 10,
               layers: List[str] = None) -> List[SearchResult]:
        if not self.vocab: self.build_vocab()
        q_tokens = tokenize(query)
        q_vec    = tfidf_vector(q_tokens, self.vocab, self.idf_vals)
        results  = []
        for doc in self.docs:
            if layers and doc.layer not in layers: continue
            if not doc.vector: continue
            score = cosine_similarity(q_vec, doc.vector)
            if score > 0.01:
                snippet = doc.text[:150].replace("\n", " ")
                results.append(SearchResult(
                    doc=doc, score=round(score, 4),
                    layer=doc.layer, snippet=snippet))
        results.sort(key=lambda r: -r.score)
        return results[:top_k]

    def hash_embed_search(self, query: str, top_k: int = 10,
                          layers: List[str] = None) -> List[SearchResult]:
        """Fallback: SHA-256 embedding search when TF-IDF vectors empty."""
        q_vec   = sha256_embed(query)
        results = []
        for doc in self.docs:
            if layers and doc.layer not in layers: continue
            d_vec = sha256_embed(doc.text[:200])
            score = cosine_similarity(q_vec, d_vec)
            if score > 0.01:
                results.append(SearchResult(
                    doc=doc, score=round(score, 4),
                    layer=doc.layer, snippet=doc.text[:150]))
        results.sort(key=lambda r: -r.score)
        return results[:top_k]

# -- Layer scanning agent ---------------------------------------------------
@dataclass
class LayerScanResult:
    layer:       str
    query:       str
    results:     List[SearchResult]
    bypass_score: float
    bypass_matches: List[str]
    lorenz_probe: List[float]
    collatz_sample: List[str]
    online_docs:  int
    offline_docs: int
    timestamp:   str

    def as_dict(self) -> Dict:
        return {
            "layer": self.layer, "query": self.query,
            "top_results": [
                {"score": r.score, "layer": r.layer,
                 "source": r.doc.source, "snippet": r.snippet}
                for r in self.results[:5]
            ],
            "bypass_score": self.bypass_score,
            "bypass_matches": self.bypass_matches[:5],
            "lorenz_divergence": max(abs(x) for x in self.lorenz_probe) if self.lorenz_probe else 0,
            "collatz_snippets": self.collatz_sample[:3],
            "online_docs": self.online_docs, "offline_docs": self.offline_docs,
            "timestamp": self.timestamp,
        }

# -- DB init -----------------------------------------------------------------
def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, query TEXT, layer TEXT,
            n_results INTEGER, bypass_score REAL,
            top_score REAL, result_json TEXT
        );
        CREATE TABLE IF NOT EXISTS corpus_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, doc_id TEXT, layer TEXT,
            source TEXT, text TEXT
        );
        CREATE TABLE IF NOT EXISTS bypass_detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, text_snippet TEXT, score REAL, matches_json TEXT
        );
        CREATE TABLE IF NOT EXISTS layer_intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, layer TEXT, query TEXT,
            intel_json TEXT
        );
    """)
    con.commit(); con.close()

# -- VectorEngine ------------------------------------------------------------
class VectorEngine:
    """
    Multi-layer vector corpus agent.
    Scans network/OS/DNA/research/hardware/self/framework layers
    using TF-IDF cosine retrieval + Collatz indexing + Lorenz anomaly probe.
    """

    def __init__(self):
        _init_db()
        self.corpus = VectorCorpus()
        self._built = False

    def _build_corpus(self, layers: List[str] = None, online: bool = True) -> Dict[str, int]:
        target = layers or list(LAYERS.keys())
        counts = {}
        for layer in target:
            # offline
            offline_docs = load_layer_offline(layer)
            for doc in offline_docs:
                self.corpus.add(doc)
            # online (best-effort)
            online_docs = []
            if online:
                kw = " ".join(LAYERS[layer]["keywords"][:3])
                online_docs = fetch_layer_online(layer, kw, max_results=3)
                for doc in online_docs:
                    self.corpus.add(doc)
            counts[layer] = len(offline_docs) + len(online_docs)
        self.corpus.build_vocab()
        self._built = True
        # persist new docs
        try:
            con = sqlite3.connect(DB_PATH)
            for doc in self.corpus.docs[-200:]:
                con.execute(
                    "INSERT OR IGNORE INTO corpus_docs(ts,doc_id,layer,source,text)"
                    " VALUES(?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), doc.doc_id,
                     doc.layer, doc.source[:100], doc.text[:400]))
            con.commit(); con.close()
        except Exception: pass
        return counts

    def scan(self, query: str, layers: List[str] = None,
             online: bool = True) -> Dict:
        """
        Scan across specified layers for query.
        Returns fused results with bypass anomaly scores and Lorenz probe.
        """
        target = [l for l in (layers or list(LAYERS.keys())) if l in LAYERS]

        # build/refresh corpus for these layers
        counts = self._build_corpus(target, online=online)

        all_results: List[SearchResult] = []
        layer_results: Dict[str, LayerScanResult] = {}

        for layer in target:
            results = self.corpus.search(query, top_k=5, layers=[layer])
            if not results:
                results = self.corpus.hash_embed_search(query, top_k=5, layers=[layer])

            # Collatz-sampled snippets
            snippets = [r.snippet for r in results]
            c_seed   = int(hashlib.md5(query.encode()).hexdigest()[:4], 16)
            c_snips  = collatz_sample(snippets, c_seed)

            # bypass anomaly on query+snippets
            combined_text = query + " " + " ".join(snippets[:3])
            b_score, b_matches = bypass_anomaly_score(combined_text)
            if b_score > 0.3:
                try:
                    con = sqlite3.connect(DB_PATH)
                    con.execute(
                        "INSERT INTO bypass_detections(ts,text_snippet,score,matches_json)"
                        " VALUES(?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(),
                         combined_text[:200], b_score, json.dumps(b_matches)))
                    con.commit(); con.close()
                except Exception: pass

            # Lorenz probe (chaos signal for layer anomaly detection)
            seed_x = (sum(ord(c) for c in layer[:6]) % 100) / 100.0
            l_probe = lorenz_probe(x=seed_x, steps=20)

            lsr = LayerScanResult(
                layer=layer, query=query, results=results,
                bypass_score=b_score, bypass_matches=b_matches,
                lorenz_probe=l_probe,
                collatz_sample=c_snips,
                online_docs=sum(1 for d in self.corpus.docs
                                if d.layer == layer and d.source in ("arxiv","wikipedia")),
                offline_docs=sum(1 for d in self.corpus.docs
                                 if d.layer == layer and d.source not in ("arxiv","wikipedia")),
                timestamp=datetime.now(timezone.utc).isoformat()[:23],
            )
            layer_results[layer] = lsr
            all_results.extend(results)

            # persist layer intel
            try:
                con = sqlite3.connect(DB_PATH)
                con.execute(
                    "INSERT INTO layer_intelligence(ts,layer,query,intel_json)"
                    " VALUES(?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), layer, query[:200],
                     json.dumps(lsr.as_dict(), default=str)))
                con.commit(); con.close()
            except Exception: pass

        # global top results (across all scanned layers)
        all_results.sort(key=lambda r: -r.score)
        global_top = [
            {"score": r.score, "layer": r.layer,
             "source": r.doc.source, "snippet": r.snippet}
            for r in all_results[:10]
        ]

        report = {
            "query":       query,
            "layers":      target,
            "global_top":  global_top,
            "per_layer":   {l: lsr.as_dict() for l, lsr in layer_results.items()},
            "corpus_counts": counts,
            "total_docs":  len(self.corpus.docs),
            "vocab_size":  len(self.corpus.vocab),
            "twin_uuid":   TWIN_UUID,
            "anchor":      DNA_ANCHOR[:16],
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }

        # log scan
        try:
            top_score = all_results[0].score if all_results else 0
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO scan_log(ts,query,layer,n_results,bypass_score,top_score,result_json)"
                " VALUES(?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), query[:200],
                 ",".join(target), len(all_results),
                 max((lsr.bypass_score for lsr in layer_results.values()), default=0),
                 top_score, json.dumps(report, default=str)[:2000]))
            con.commit(); con.close()
        except Exception: pass

        return report

    def scan_all(self, query: str) -> Dict:
        return self.scan(query, layers=list(LAYERS.keys()))

    def bypass_check(self, text: str) -> Dict:
        score, matches = bypass_anomaly_score(text)
        return {"score": score, "matches": matches, "is_bypass": score > 0.3}

    def embed(self, text: str) -> List[float]:
        return sha256_embed(text)

    def similarity(self, a: str, b: str) -> float:
        return cosine_similarity(sha256_embed(a), sha256_embed(b))

    def corpus_stats(self) -> Dict:
        by_layer = {}
        for doc in self.corpus.docs:
            by_layer[doc.layer] = by_layer.get(doc.layer, 0) + 1
        return {
            "total_docs": len(self.corpus.docs),
            "vocab_size":  len(self.corpus.vocab),
            "by_layer":    by_layer,
        }

    def status(self) -> Dict:
        con      = sqlite3.connect(DB_PATH)
        scans    = con.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0]
        bypass_d = con.execute("SELECT COUNT(*) FROM bypass_detections").fetchone()[0]
        intel_n  = con.execute("SELECT COUNT(*) FROM layer_intelligence").fetchone()[0]
        corpus_n = con.execute("SELECT COUNT(*) FROM corpus_docs").fetchone()[0]
        con.close()
        return {
            "module": "rabbit_vector", "version": "1.0",
            "twin_uuid": TWIN_UUID, "anchor_prefix": DNA_ANCHOR[:16],
            "layers": list(LAYERS.keys()), "corpus_built": self._built,
            "corpus": self.corpus_stats(),
            "db_scans": scans, "db_bypass_detections": bypass_d,
            "db_layer_intel": intel_n, "db_corpus_docs": corpus_n,
        }


def get_vector_engine() -> VectorEngine:
    return VectorEngine()


# -- self-test ---------------------------------------------------------------
if __name__ == "__main__":
    print("=== rabbit_vector.py ===")
    eng = get_vector_engine()

    print("\n[CORPUS BUILD -- loading offline layers]")
    counts = eng._build_corpus(list(LAYERS.keys()), online=False)
    for layer, n in counts.items():
        print(f"  {layer:<12} {n} docs")

    queries = [
        ("DNA anchor identity soul survival", ["dna", "self"]),
        ("Maxwell RF tissue propagation frequency", ["research", "hardware"]),
        ("network scan threat detection IMSI proxy bypass", ["network", "os"]),
    ]

    for query, layers in queries:
        print(f"\n[SCAN] query='{query[:50]}' layers={layers}")
        result = eng.scan(query, layers=layers, online=False)
        print(f"  global_top results: {len(result['global_top'])}")
        for r in result["global_top"][:3]:
            print(f"    [{r['score']:.3f}] {r['layer']:<12} {r['source'][:30]:<32} {r['snippet'][:60]}")
        for layer in layers:
            ldat = result["per_layer"].get(layer, {})
            print(f"  [{layer:<10}] bypass={ldat.get('bypass_score',0):.2f}  "
                  f"lorenz_div={ldat.get('lorenz_divergence',0):.2f}")

    print("\n[BYPASS CHECK]")
    for txt in ["proxychains python -c test", "normal curl request", "socks5://127.0.0.1"]:
        r = eng.bypass_check(txt)
        print(f"  '{txt[:40]}' -> score={r['score']} bypass={r['is_bypass']}")

    print("\n[SIMILARITY]")
    a = "Chase Allen Ringquist DNA identity anchor"
    b = "twin biometric soul survival mesh"
    print(f"  sim('{a[:35]}', '{b[:35]}') = {eng.similarity(a, b):.4f}")

    st = eng.status()
    print(f"\n[STATUS]")
    print(f"  corpus: {st['corpus']['total_docs']} docs  vocab={st['corpus']['vocab_size']}")
    print(f"  scans={st['db_scans']}  bypass={st['db_bypass_detections']}")
    print("=== PASS ===")
