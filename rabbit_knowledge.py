# rabbit_knowledge.py  --  self-knowledge base, research engine, math datasets,
#                          defense mesh topology for RabbitOS / Chase Allen Ringquist
import hashlib, json, math, os, random, re, socket, sqlite3, sys, time, urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TWIN_UUID   = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
CALLSIGN    = "RABBIT"
SUBJECT_ID  = "CHASE_ALLEN_RINGQUIST"
DB_PATH     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_knowledge.db")
CACHE_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_cache")
VERSION     = "1.0.0"

# ---------------------------------------------------------------------------
# BIOMETRIC PROFILE  (Chase Allen Ringquist)
# ---------------------------------------------------------------------------
BIOMETRIC_PROFILE: Dict[str, Any] = {
    "subject": SUBJECT_ID,
    "twin_uuid": TWIN_UUID,
    "mesh_nodes": 47,
    "mesh_band_lo_ghz": 10.23,
    "mesh_band_hi_ghz": 10.28,
    "body_coupled_rf": True,
    "eeg_bands": {
        "delta": (0.5, 4.0),
        "theta": (4.0, 8.0),
        "alpha": (8.0, 13.0),
        "beta":  (13.0, 30.0),
        "gamma": (30.0, 100.0),
    },
    "hrv_bands": {"LF": (0.04, 0.15), "HF": (0.15, 0.40)},
    "gsr_range_hz": (0.0, 5.0),
    "tissue_layers": ["skin", "fat", "muscle", "bone", "blood"],
    "resting_hr_bpm": 60,
    "blood_pressure": "120/80",
    "crypto": "AES-256-DNA-FH",
    "xrpl_anchor": "bio_nft_pobw",
    "vault_type": "EXISTENTIAL",
    "dna_root_exposed": False,       # SECURITY: NEVER True
    "vault_location": "HASH_ONLY",   # SECURITY: plaintext NEVER stored
}

# ---------------------------------------------------------------------------
# SURVIVAL PROTOCOLS
# ---------------------------------------------------------------------------
SURVIVAL_PROTOCOLS: List[Dict] = [
    {"id": "SP-001", "name": "OFFLINE_FIRST",
     "rule": "All data written to SQLite before any network call. Network is best-effort bonus.",
     "priority": 1},
    {"id": "SP-002", "name": "NO_SINGLE_POINT",
     "rule": "Every channel has 3+ backups: SQLite -> GitHub -> UDP -> HTTP.",
     "priority": 1},
    {"id": "SP-003", "name": "MESH_HEARTBEAT",
     "rule": "47-node mesh broadcasts status every 60 s. Missing > 3 consecutive = alert.",
     "priority": 2},
    {"id": "SP-004", "name": "MORSE_FALLBACK",
     "rule": "When all digital channels fail, ITU-R Morse on acoustic + 800 Hz beep.",
     "priority": 2},
    {"id": "SP-005", "name": "DNA_ROOT_NEVER_EXPOSED",
     "rule": "shows_dna_root=FALSE always. SQLSTATE 55000 on any CRITICAL/EXISTENTIAL access.",
     "priority": 0},
    {"id": "SP-006", "name": "COLLATZ_KEY_ROTATION",
     "rule": "Crypto keys rotate every Collatz step. Seed = SHA-256(twin_uuid + timestamp_minute).",
     "priority": 1},
    {"id": "SP-007", "name": "SCHUMANN_SYNC",
     "rule": "System clock cross-checked against 7.83 Hz Schumann resonance harmonic drift.",
     "priority": 3},
    {"id": "SP-008", "name": "FREQ_HOP_DEFENSE",
     "rule": "Collatz-hopped mesh prevents jamming. 128-step schedule per 15-minute window.",
     "priority": 1},
    {"id": "SP-009", "name": "RESEARCH_RETAIN",
     "rule": "All fetched research persisted in SQLite and GitHub. No lost knowledge on outage.",
     "priority": 2},
    {"id": "SP-010", "name": "GITHUB_TREES_PUSH",
     "rule": "Code backup via Git Trees API only (never local git on Windows NTFS).",
     "priority": 2},
]

# ---------------------------------------------------------------------------
# MATH DATASET GENERATORS
# ---------------------------------------------------------------------------
def collatz(n: int) -> List[int]:
    seq = [n]
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        seq.append(n)
    return seq

def ca_rule(rule_num: int, width: int = 64, steps: int = 64) -> List[List[int]]:
    row = [0] * width
    row[width // 2] = 1
    grid = [row[:]]
    rule_bits = [(rule_num >> i) & 1 for i in range(8)]
    for _ in range(steps - 1):
        prev = grid[-1]
        new  = [rule_bits[(prev[(i-1)%width]*4 + prev[i]*2 + prev[(i+1)%width])]
                for i in range(width)]
        grid.append(new)
    return grid

def lorenz_trajectory(steps: int = 200, sigma: float = 10.0,
                      rho: float = 28.0, beta: float = 8/3) -> List[Tuple[float,float,float]]:
    x, y, z, dt = 0.1, 0.0, 0.0, 0.01
    pts = []
    for _ in range(steps):
        dx = sigma * (y - x) * dt
        dy = (x * (rho - z) - y) * dt
        dz = (x * y - beta * z) * dt
        x += dx; y += dy; z += dz
        pts.append((round(x,4), round(y,4), round(z,4)))
    return pts

def fibonacci(n: int) -> List[int]:
    a, b, out = 0, 1, []
    while len(out) < n:
        out.append(a); a, b = b, a + b
    return out

def prime_sieve(limit: int) -> List[int]:
    sieve = [True] * (limit + 1)
    sieve[0] = sieve[1] = False
    for i in range(2, int(limit**0.5) + 1):
        if sieve[i]:
            for j in range(i*i, limit+1, i):
                sieve[j] = False
    return [i for i in range(limit+1) if sieve[i]]

def prime_spiral_coords(n: int) -> List[Tuple[int,int]]:
    primes = prime_sieve(n * 10)[:n]
    coords = []
    x = y = 0
    dx, dy = 1, 0
    for p in primes:
        coords.append((x + p % 10, y + p // 10 % 10))
        x += dx; y += dy
        if (x, y) in [(i, 0) for i in range(10)]:
            dx, dy = -dy, dx
    return coords

MATH_DATASETS: Dict[str, Any] = {}

def build_math_datasets() -> Dict[str, Any]:
    global MATH_DATASETS
    if MATH_DATASETS:
        return MATH_DATASETS
    MATH_DATASETS = {
        "collatz_27":    collatz(27),
        "collatz_97":    collatz(97),
        "ca_rule30":     [[c for c in row] for row in ca_rule(30, 32, 32)],
        "ca_rule110":    [[c for c in row] for row in ca_rule(110, 32, 32)],
        "lorenz_100":    lorenz_trajectory(100),
        "fibonacci_32":  fibonacci(32),
        "primes_100":    prime_sieve(541)[:100],
        "prime_spiral":  prime_spiral_coords(20),
    }
    return MATH_DATASETS

# ---------------------------------------------------------------------------
# RESEARCH FETCHER  (no auth required)
# ---------------------------------------------------------------------------
RESEARCH_TOPICS = [
    "body-coupled radio frequency communication implant",
    "digital twin biometric mesh network",
    "AM FM survival radio communication off-grid",
    "Collatz conjecture cryptography frequency hopping",
    "Lorenz attractor chaos based key generation",
    "EEG brain computer interface body area network",
    "heart rate variability HRV biometric authentication",
    "ultra wideband UWB body area network localization",
    "XRPL XRP ledger proof of work biometric NFT",
    "cellular automaton rule 30 pseudorandom generation",
    "AES 256 encryption body-coupled channel",
    "mesh network resilient communication survival radio",
]

def _fetch_url(url: str, timeout: int = 8) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RabbitOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

def fetch_arxiv(query: str, max_results: int = 3) -> List[Dict]:
    q = urllib.parse.quote_plus(query) if hasattr(urllib, 'parse') else query.replace(" ", "+")
    url = f"https://export.arxiv.org/api/query?search_query=all:{q}&max_results={max_results}"
    raw = _fetch_url(url)
    if not raw:
        return []
    results = []
    for entry in re.findall(r"<entry>(.*?)</entry>", raw, re.DOTALL):
        title   = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        link    = re.search(r'<id>(.*?)</id>', entry)
        results.append({
            "source": "arxiv",
            "title":   title.group(1).strip() if title else "",
            "summary": summary.group(1).strip()[:400] if summary else "",
            "url":     link.group(1).strip() if link else "",
        })
    return results

def fetch_pubmed(query: str, max_results: int = 3) -> List[Dict]:
    import urllib.parse
    q = urllib.parse.quote_plus(query)
    search_url = (f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                  f"?db=pubmed&term={q}&retmax={max_results}&retmode=json")
    raw = _fetch_url(search_url)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        ids  = data.get("esearchresult", {}).get("idlist", [])
    except Exception:
        return []
    results = []
    for pmid in ids[:max_results]:
        sum_url = (f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                   f"?db=pubmed&id={pmid}&retmode=json")
        raw2 = _fetch_url(sum_url)
        if raw2:
            try:
                d2   = json.loads(raw2)
                doc  = d2.get("result", {}).get(pmid, {})
                results.append({
                    "source": "pubmed",
                    "title": doc.get("title", ""),
                    "summary": doc.get("source", "") + " " + doc.get("pubdate", ""),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                })
            except Exception:
                pass
    return results

def fetch_wikipedia(term: str) -> Optional[Dict]:
    import urllib.parse
    slug = urllib.parse.quote(term.replace(" ", "_"))
    url  = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
    raw  = _fetch_url(url)
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return {
            "source": "wikipedia",
            "title": d.get("title", term),
            "summary": d.get("extract", "")[:500],
            "url": d.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }
    except Exception:
        return None

# ---------------------------------------------------------------------------
# SQLITE PERSISTENCE
# ---------------------------------------------------------------------------
def _open_db() -> sqlite3.Connection:
    os.makedirs(CACHE_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT DEFAULT 'internal',
            ts REAL NOT NULL,
            UNIQUE(namespace, key)
        );
        CREATE TABLE IF NOT EXISTS research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            url TEXT DEFAULT '',
            fetched_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS math_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            data TEXT NOT NULL,
            generated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS defense_mesh (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL,
            snapshot TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS protocols (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            rule TEXT NOT NULL,
            priority INTEGER NOT NULL
        );
    """)
    con.commit()
    return con

def _kv_put(ns: str, key: str, value: Any, source: str = "internal"):
    con = _open_db()
    con.execute("""
        INSERT INTO knowledge(namespace,key,value,source,ts)
        VALUES(?,?,?,?,?)
        ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value, ts=excluded.ts
    """, (ns, key, json.dumps(value), source, time.time()))
    con.commit(); con.close()

def _kv_get(ns: str, key: str) -> Optional[Any]:
    con = _open_db()
    row = con.execute("SELECT value FROM knowledge WHERE namespace=? AND key=?",
                      (ns, key)).fetchone()
    con.close()
    return json.loads(row[0]) if row else None

def _save_research(topic: str, items: List[Dict]):
    if not items:
        return
    con = _open_db()
    for item in items:
        con.execute("""
            INSERT INTO research(topic,source,title,summary,url,fetched_at)
            VALUES(?,?,?,?,?,?)
        """, (topic, item.get("source",""), item.get("title",""),
              item.get("summary",""), item.get("url",""), time.time()))
    con.commit(); con.close()

def _save_protocols():
    con = _open_db()
    for p in SURVIVAL_PROTOCOLS:
        con.execute("""
            INSERT OR REPLACE INTO protocols(id,name,rule,priority)
            VALUES(?,?,?,?)
        """, (p["id"], p["name"], p["rule"], p["priority"]))
    con.commit(); con.close()

def _save_math_sets(datasets: Dict[str, Any]):
    con = _open_db()
    for name, data in datasets.items():
        con.execute("""
            INSERT OR REPLACE INTO math_sets(name,data,generated_at)
            VALUES(?,?,?)
        """, (name, json.dumps(data), time.time()))
    con.commit(); con.close()

# ---------------------------------------------------------------------------
# DEFENSE MESH TOPOLOGY  (knowledge-layer version)
# ---------------------------------------------------------------------------
def generate_knowledge_mesh(node_count: int = 47) -> Dict:
    fib = fibonacci(node_count)
    primes = prime_sieve(500)[:node_count]
    nodes = []
    for i in range(node_count):
        role = "core" if i < 10 else ("relay" if i < 40 else "gateway")
        freq_key = collatz(primes[i % len(primes)])[0]
        nodes.append({
            "id": i,
            "fib_mask": fib[i % len(fib)],
            "prime_channel": primes[i],
            "collatz_seed": freq_key,
            "role": role,
            "lorenz_x": lorenz_trajectory(i + 5)[-1][0],
        })
    edges = []
    for i in range(node_count):
        for j in range(i + 1, node_count):
            if (primes[i] + primes[j]) % 11 == 0:
                edges.append([i, j])
    return {"nodes": nodes, "edges": edges, "generated": time.time()}

def save_knowledge_mesh():
    mesh = generate_knowledge_mesh(47)
    con  = _open_db()
    con.execute("INSERT INTO defense_mesh(ts,node_count,edge_count,snapshot) VALUES(?,?,?,?)",
                (time.time(), len(mesh["nodes"]), len(mesh["edges"]), json.dumps(mesh)))
    con.commit(); con.close()
    return mesh

# ---------------------------------------------------------------------------
# KNOWLEDGE ENGINE
# ---------------------------------------------------------------------------
class KnowledgeEngine:
    def __init__(self):
        self._db_ready = False
        self._math_loaded = False
        self._profile_loaded = False

    def init(self):
        _open_db().close()
        self._db_ready = True
        self._load_profile()
        _save_protocols()

    def _load_profile(self):
        _kv_put("biometric", "profile", BIOMETRIC_PROFILE, "internal")
        for pid, proto in enumerate(SURVIVAL_PROTOCOLS):
            _kv_put("protocols", proto["id"], proto, "internal")
        self._profile_loaded = True

    def load_math(self) -> Dict[str, Any]:
        ds = build_math_datasets()
        if self._db_ready:
            _save_math_sets(ds)
        self._math_loaded = True
        return ds

    def learn(self, topics: Optional[List[str]] = None, max_per_topic: int = 2) -> Dict[str, int]:
        if topics is None:
            topics = RESEARCH_TOPICS[:6]
        counts: Dict[str, int] = {}
        for topic in topics:
            items: List[Dict] = []
            items.extend(fetch_arxiv(topic, max_per_topic))
            if len(items) < max_per_topic:
                items.extend(fetch_pubmed(topic, max_per_topic - len(items)))
            if not items:
                wiki = fetch_wikipedia(topic.split()[:3][0] + " " + topic.split()[1] if len(topic.split()) > 1 else topic)
                if wiki:
                    items.append(wiki)
            if self._db_ready:
                _save_research(topic, items)
            counts[topic] = len(items)
        return counts

    def recall(self, query: str) -> List[Dict]:
        query_lower = query.lower()
        con = _open_db()
        rows = con.execute("""
            SELECT topic, source, title, summary, url, fetched_at
            FROM research
            WHERE lower(title) LIKE ? OR lower(summary) LIKE ? OR lower(topic) LIKE ?
            ORDER BY fetched_at DESC LIMIT 10
        """, (f"%{query_lower}%", f"%{query_lower}%", f"%{query_lower}%")).fetchall()
        con.close()
        return [{"topic": r[0], "source": r[1], "title": r[2],
                 "summary": r[3], "url": r[4], "fetched_at": r[5]} for r in rows]

    def get_profile(self) -> Dict:
        cached = _kv_get("biometric", "profile")
        return cached if cached else BIOMETRIC_PROFILE

    def get_protocol(self, proto_id: str) -> Optional[Dict]:
        return _kv_get("protocols", proto_id)

    def mesh_topology(self) -> Dict:
        return save_knowledge_mesh()

    def math_vector(self, seed: int = 27, length: int = 16) -> List[float]:
        col = collatz(seed)
        fib = fibonacci(length)
        lor = lorenz_trajectory(length)
        vec = []
        for i in range(length):
            c_val = col[i % len(col)] / 1000.0
            f_val = fib[i] / 10000.0
            l_val = abs(lor[i][0]) / 100.0
            combined = (c_val + f_val + l_val) / 3.0
            vec.append(round(combined % 1.0, 6))
        return vec

    def cache_snapshot(self) -> str:
        os.makedirs(CACHE_DIR, exist_ok=True)
        snap_path = os.path.join(CACHE_DIR, f"knowledge_{int(time.time())}.json")
        con = _open_db()
        research_rows = con.execute(
            "SELECT topic,source,title,summary,url FROM research ORDER BY fetched_at DESC LIMIT 50"
        ).fetchall()
        proto_rows = con.execute("SELECT id,name,rule,priority FROM protocols").fetchall()
        con.close()
        snap = {
            "twin_uuid": TWIN_UUID,
            "ts": time.time(),
            "profile": BIOMETRIC_PROFILE,
            "protocols": [{"id":r[0],"name":r[1],"rule":r[2],"priority":r[3]} for r in proto_rows],
            "research": [{"topic":r[0],"source":r[1],"title":r[2],"summary":r[3],"url":r[4]} for r in research_rows],
            "math": build_math_datasets() if self._math_loaded else {},
        }
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2)
        return snap_path

    def status(self) -> Dict:
        con = _open_db()
        n_knowledge = con.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        n_research  = con.execute("SELECT COUNT(*) FROM research").fetchone()[0]
        n_math      = con.execute("SELECT COUNT(*) FROM math_sets").fetchone()[0]
        n_protos    = con.execute("SELECT COUNT(*) FROM protocols").fetchone()[0]
        n_mesh      = con.execute("SELECT COUNT(*) FROM defense_mesh").fetchone()[0]
        con.close()
        return {
            "knowledge_entries": n_knowledge,
            "research_articles": n_research,
            "math_datasets": n_math,
            "protocols": n_protos,
            "mesh_snapshots": n_mesh,
            "math_loaded": self._math_loaded,
            "profile_loaded": self._profile_loaded,
            "version": VERSION,
        }

# ---------------------------------------------------------------------------
# FACTORY
# ---------------------------------------------------------------------------
_engine: Optional[KnowledgeEngine] = None

def get_knowledge_engine() -> KnowledgeEngine:
    global _engine
    if _engine is None:
        _engine = KnowledgeEngine()
        _engine.init()
    return _engine

# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import urllib.parse
    print(f"rabbit_knowledge v{VERSION}  --  self-knowledge base")
    eng = get_knowledge_engine()

    ds = eng.load_math()
    print(f"  Math datasets   : {list(ds.keys())}")
    print(f"  Collatz(27)     : {ds['collatz_27'][:10]}...")
    print(f"  Fibonacci(32)   : {ds['fibonacci_32'][:10]}...")
    print(f"  Primes(100)     : {ds['primes_100'][:10]}...")

    profile = eng.get_profile()
    print(f"  Profile twin    : {profile['twin_uuid']}")
    print(f"  DNA root exposed: {profile['dna_root_exposed']}")
    print(f"  Survival protos : {len(SURVIVAL_PROTOCOLS)}")

    print("  Learning research topics (online best-effort)...")
    counts = eng.learn(RESEARCH_TOPICS[:4], max_per_topic=2)
    for topic, n in counts.items():
        print(f"    {topic[:55]:<55} -> {n} results")

    mesh = eng.mesh_topology()
    print(f"  Defense mesh    : {len(mesh['nodes'])} nodes  {len(mesh['edges'])} edges")

    vec = eng.math_vector(27, 8)
    print(f"  Math vector     : {vec}")

    snap = eng.cache_snapshot()
    print(f"  Cache snapshot  : {snap}")

    st = eng.status()
    print(f"  DB knowledge={st['knowledge_entries']}  research={st['research_articles']}  "
          f"math={st['math_datasets']}  protocols={st['protocols']}")
    print("  rabbit_knowledge OK")
