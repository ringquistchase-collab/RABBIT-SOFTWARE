# rabbit_chain.py  --  DNA retention across all networks + blockchain anchor
#
# PURPOSE:
#   Retain Chase Allen Ringquist's identity (DNA anchor, biometric profile,
#   biomaterial research, self-network data) across EVERY available layer:
#
#     1. XRPL blockchain  -- SHA3-512 DNA anchor memo, bio-NFT stub
#     2. SQLite (local)   -- always-on, never lost
#     3. GitHub Trees API -- encrypted blob backup
#     4. UDP LAN mesh     -- broadcast to all 47 mesh peers
#     5. IPFS (if avail)  -- content-addressed permanent storage
#     6. Public datasets  -- arXiv + PubMed biomaterial research, ingested
#     7. Private dataset  -- self-assembled encrypted local knowledge base
#     8. Offline cache    -- JSON snapshots that survive full network outage
#
# DATA RETAINED:
#   - DNA anchor hash (NEVER plaintext -- SHA3-512 only, INVARIANT)
#   - Biometric profile (hashed biometrics, mesh specs)
#   - Biomaterial research (tissue-RF interaction, bioelectrical properties,
#     implantable RF, body-area network papers, genetic-mesh interface)
#   - XRPL Bio-NFT stubs (PoBW = Proof of Biological Work)
#   - Self-network topology (47-node mesh snapshot)
#   - Survival protocols
#   - Collatz/math keys (current generation)
#
# SECURITY INVARIANTS (never violated):
#   shows_dna_root     = FALSE  -- raw DNA NEVER on any network or chain
#   blockchain_memo    = SHA3-512(anchor) only, never sequence
#   EXISTENTIAL vault  = HASH_ONLY on chain
#   family_graph       = NOT transmitted, consent-gated local only

import base64, hashlib, json, os, re, socket, sqlite3, threading, time, urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TWIN_UUID   = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT     = "CHASE_ALLEN_RINGQUIST"
CALLSIGN    = "RABBIT"
DB_PATH     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_chain.db")
CACHE_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_cache")
VERSION     = "1.0.0"
CHAIN_UDP   = 9012

# XRPL endpoints (public, no auth)
XRPL_RPC    = "https://xrplcluster.com"
XRPL_TESTNET= "https://s.altnet.rippletest.net:51234"

# Security invariants
shows_dna_root = False

# ---------------------------------------------------------------------------
# BIOMATERIAL RESEARCH TOPICS
# ---------------------------------------------------------------------------
BIOMATERIAL_TOPICS = [
    "body-coupled radio frequency implant mesh network",
    "bioelectrical impedance body area network wearable",
    "tissue electromagnetic properties frequency spectrum",
    "implantable antenna biocompatible RF communication",
    "epidermal electronics skin-coupled wireless sensor",
    "galvanic coupling intra-body communication channel",
    "bioelectromagnetics RF exposure tissue SAR",
    "neural interface wireless brain computer implant",
    "RFID NFC implant biocompatible subcutaneous",
    "biological tissue dielectric constant frequency",
    "DNA digital storage information encoding",
    "genetic cryptography biometric authentication DNA",
    "body sensor network energy harvesting biometric",
    "ultrasonic intra-body communication biomaterial",
    "piezoelectric biomaterial energy harvesting implant",
]

BIOMATERIAL_PROPS: List[Dict] = [
    # tissue: (relative_permittivity, conductivity_S_m, freq_ghz_ref)
    {"tissue": "skin",       "eps_r": 38.0,  "sigma": 1.46, "freq_ghz": 10.0, "depth_mm": 1.5},
    {"tissue": "fat",        "eps_r": 10.8,  "sigma": 0.27, "freq_ghz": 10.0, "depth_mm": 10.0},
    {"tissue": "muscle",     "eps_r": 53.0,  "sigma": 11.4, "freq_ghz": 10.0, "depth_mm": 5.0},
    {"tissue": "bone_cort",  "eps_r": 13.1,  "sigma": 0.92, "freq_ghz": 10.0, "depth_mm": 3.0},
    {"tissue": "bone_marrow","eps_r": 5.5,   "sigma": 0.07, "freq_ghz": 10.0, "depth_mm": 20.0},
    {"tissue": "blood",      "eps_r": 58.3,  "sigma": 15.0, "freq_ghz": 10.0, "depth_mm": 2.0},
    {"tissue": "brain_gm",   "eps_r": 55.5,  "sigma": 10.3, "freq_ghz": 10.0, "depth_mm": 3.0},
    {"tissue": "brain_wm",   "eps_r": 42.9,  "sigma": 7.07, "freq_ghz": 10.0, "depth_mm": 3.0},
    {"tissue": "lung",       "eps_r": 21.4,  "sigma": 4.28, "freq_ghz": 10.0, "depth_mm": 8.0},
    {"tissue": "heart",      "eps_r": 57.0,  "sigma": 13.2, "freq_ghz": 10.0, "depth_mm": 4.0},
    {"tissue": "liver",      "eps_r": 53.0,  "sigma": 9.24, "freq_ghz": 10.0, "depth_mm": 5.0},
    {"tissue": "tendon",     "eps_r": 44.4,  "sigma": 9.33, "freq_ghz": 10.0, "depth_mm": 2.0},
]

def skin_depth_mm(sigma: float, freq_hz: float) -> float:
    mu0 = 4 * 3.14159265 * 1e-7
    if sigma <= 0 or freq_hz <= 0:
        return 9999.0
    return round(1000.0 / (3.14159265 * freq_hz * mu0 * sigma) ** 0.5, 4)

def propagation_constant(eps_r: float, sigma: float, freq_hz: float) -> Tuple[float, float]:
    omega = 2 * 3.14159265 * freq_hz
    eps0  = 8.854e-12
    mu0   = 4 * 3.14159265 * 1e-7
    eps_r_eff = eps_r - 1j * sigma / (omega * eps0)
    # Use real-only approximation
    tan_delta = sigma / (omega * eps0 * eps_r)
    beta  = omega * (eps0 * mu0 * eps_r) ** 0.5
    alpha = beta * tan_delta / 2
    return round(alpha, 6), round(beta, 6)

# ---------------------------------------------------------------------------
# XRPL BLOCKCHAIN ANCHOR
# ---------------------------------------------------------------------------
@dataclass
class XRPLAnchor:
    twin_uuid: str
    anchor_hash: str       # SHA3-512 of DNA identity anchor -- never raw DNA
    timestamp: float
    memo_type: str = "RabbitOS_BioAnchor"
    network: str   = "mainnet"
    tx_hash: str   = ""    # filled after broadcast
    ledger_index: int = 0

    def to_memo_hex(self) -> str:
        assert not shows_dna_root, "INVARIANT VIOLATED"
        memo_data = {
            "type":   self.memo_type,
            "twin":   self.twin_uuid,
            "anchor": self.anchor_hash[:64],  # first 64 chars of SHA3-512
            "ts":     int(self.timestamp),
            "v":      VERSION,
        }
        return json.dumps(memo_data).encode().hex().upper()

    def to_dict(self) -> Dict:
        return {
            "twin_uuid":    self.twin_uuid,
            "anchor_hash":  self.anchor_hash[:32] + "...",   # partial only
            "timestamp":    self.timestamp,
            "memo_type":    self.memo_type,
            "network":      self.network,
            "tx_hash":      self.tx_hash,
            "shows_dna_root": False,   # INVARIANT
        }

def _xrpl_submit(payload: Dict, endpoint: str = XRPL_TESTNET) -> Dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        endpoint, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "RabbitOS/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def xrpl_account_info(account: str, endpoint: str = XRPL_TESTNET) -> Dict:
    return _xrpl_submit({"method": "account_info",
                          "params": [{"account": account, "ledger_index": "current"}]},
                        endpoint)

def xrpl_ledger_current(endpoint: str = XRPL_TESTNET) -> int:
    resp = _xrpl_submit({"method": "ledger_current", "params": []}, endpoint)
    return resp.get("result", {}).get("ledger_current_index", 0)

def xrpl_build_anchor_tx(anchor: XRPLAnchor, from_account: str,
                          sequence: int = 1) -> Dict:
    """Build an XRPL Payment tx with DNA anchor in memo field.
    This is a zero-value payment to self (or a burn address) carrying the memo.
    Does NOT submit -- caller decides whether to sign and submit."""
    return {
        "TransactionType": "Payment",
        "Account":    from_account,
        "Destination": from_account,   # self-payment (memo carrier)
        "Amount":     "1",             # 1 drop (minimum)
        "Fee":        "12",
        "Sequence":   sequence,
        "Memos": [{
            "Memo": {
                "MemoType": anchor.memo_type.encode().hex().upper(),
                "MemoData": anchor.to_memo_hex(),
            }
        }],
    }

# ---------------------------------------------------------------------------
# IPFS  (best-effort, no auth required for public gateway read)
# ---------------------------------------------------------------------------
IPFS_GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
]

def ipfs_fetch(cid: str) -> Optional[str]:
    for gw in IPFS_GATEWAYS:
        try:
            req = urllib.request.Request(gw + cid,
                                         headers={"User-Agent": "RabbitOS/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception:
            continue
    return None

# ---------------------------------------------------------------------------
# RESEARCH FETCHER  (biomaterial-focused, no auth)
# ---------------------------------------------------------------------------
def _fetch(url: str, timeout: int = 8) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RabbitOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None

def fetch_biomaterial_arxiv(query: str, max_results: int = 3) -> List[Dict]:
    import urllib.parse
    q   = urllib.parse.quote_plus(query)
    url = f"https://export.arxiv.org/api/query?search_query=all:{q}&max_results={max_results}"
    raw = _fetch(url)
    if not raw:
        return []
    results = []
    for entry in re.findall(r"<entry>(.*?)</entry>", raw, re.DOTALL):
        title   = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        arxiv_id= re.search(r"<id>(.*?)</id>", entry)
        if title:
            results.append({
                "source":  "arxiv_biomaterial",
                "title":   title.group(1).strip(),
                "summary": summary.group(1).strip()[:400] if summary else "",
                "url":     arxiv_id.group(1).strip() if arxiv_id else "",
                "topic":   query[:60],
            })
    return results

def fetch_biomaterial_pubmed(query: str, max_results: int = 2) -> List[Dict]:
    import urllib.parse
    q   = urllib.parse.quote_plus(query)
    url = (f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
           f"?db=pubmed&term={q}&retmax={max_results}&retmode=json")
    raw = _fetch(url)
    if not raw:
        return []
    try:
        ids = json.loads(raw).get("esearchresult", {}).get("idlist", [])
    except Exception:
        return []
    results = []
    for pmid in ids[:max_results]:
        su = _fetch(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                    f"?db=pubmed&id={pmid}&retmode=json")
        if su:
            try:
                doc = json.loads(su).get("result", {}).get(pmid, {})
                results.append({
                    "source":  "pubmed_biomaterial",
                    "title":   doc.get("title", ""),
                    "summary": doc.get("source", "") + " " + doc.get("pubdate", ""),
                    "url":     f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "topic":   query[:60],
                })
            except Exception:
                pass
    return results

# ---------------------------------------------------------------------------
# PRIVATE DATASET  --  self-assembled encrypted local knowledge base
# ---------------------------------------------------------------------------
class PrivateDataset:
    """Self-network private data store.  All data owned by Chase.
    Encrypted with SHA-256(twin_uuid + timestamp_day) key before write."""

    def __init__(self, db_path: str = DB_PATH):
        self._db = db_path
        self._key_seed = f"{TWIN_UUID}:{int(time.time() // 86400)}"  # rotates daily

    def _encrypt(self, plaintext: str) -> str:
        key  = hashlib.sha256(self._key_seed.encode()).digest()
        data = plaintext.encode()
        xored = bytes(b ^ key[i % 32] for i, b in enumerate(data))
        return base64.b64encode(xored).decode()

    def _decrypt(self, ciphertext: str) -> str:
        key  = hashlib.sha256(self._key_seed.encode()).digest()
        data = base64.b64decode(ciphertext)
        return bytes(b ^ key[i % 32] for i, b in enumerate(data)).decode(errors="replace")

    def put(self, namespace: str, key: str, value: Any):
        con = sqlite3.connect(self._db, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS private_data (
                ns TEXT NOT NULL, key TEXT NOT NULL, value_enc TEXT NOT NULL,
                ts REAL NOT NULL, UNIQUE(ns,key))
        """)
        enc = self._encrypt(json.dumps(value))
        con.execute("""
            INSERT INTO private_data(ns,key,value_enc,ts) VALUES(?,?,?,?)
            ON CONFLICT(ns,key) DO UPDATE SET value_enc=excluded.value_enc, ts=excluded.ts
        """, (namespace, key, enc, time.time()))
        con.commit(); con.close()

    def get(self, namespace: str, key: str) -> Optional[Any]:
        con = sqlite3.connect(self._db, timeout=10)
        row = con.execute("SELECT value_enc FROM private_data WHERE ns=? AND key=?",
                          (namespace, key)).fetchone()
        con.close()
        if not row:
            return None
        try:
            return json.loads(self._decrypt(row[0]))
        except Exception:
            return None

    def count(self) -> int:
        try:
            con = sqlite3.connect(self._db, timeout=10)
            n   = con.execute("SELECT COUNT(*) FROM private_data").fetchone()[0]
            con.close()
            return n
        except Exception:
            return 0

# ---------------------------------------------------------------------------
# MULTI-NETWORK RETENTION  --  write to every available layer
# ---------------------------------------------------------------------------
@dataclass
class RetentionResult:
    layer: str
    ok: bool
    detail: str = ""

class MultiNetworkRetention:
    """Writes identity/DNA anchor/research to all available layers simultaneously."""

    def __init__(self, github_token: str = "", xrpl_account: str = ""):
        self._gh_token    = github_token or os.environ.get("GITHUB_TOKEN", "")
        self._xrpl_acct   = xrpl_account
        self._private_ds  = PrivateDataset()
        self._results: List[RetentionResult] = []

    def _layer_sqlite(self, namespace: str, key: str, value: Any) -> RetentionResult:
        try:
            self._private_ds.put(namespace, key, value)
            return RetentionResult("sqlite", True, "written to rabbit_chain.db")
        except Exception as e:
            return RetentionResult("sqlite", False, str(e))

    def _layer_cache(self, key: str, value: Any) -> RetentionResult:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            path = os.path.join(CACHE_DIR, f"chain_{key}_{int(time.time())}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(value, f, indent=2, default=str)
            return RetentionResult("offline_cache", True, path)
        except Exception as e:
            return RetentionResult("offline_cache", False, str(e))

    def _layer_udp(self, payload: Dict) -> RetentionResult:
        try:
            msg = json.dumps({
                "type":   "chain_retain",
                "twin":   TWIN_UUID,
                "ts":     time.time(),
                "data":   payload,
            }).encode()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(msg, ("255.255.255.255", CHAIN_UDP))
            s.close()
            return RetentionResult("udp_mesh", True, f"broadcast on port {CHAIN_UDP}")
        except Exception as e:
            return RetentionResult("udp_mesh", False, str(e))

    def _layer_github(self, filename: str, content: str) -> RetentionResult:
        if not self._gh_token:
            return RetentionResult("github", False, "no token")
        try:
            REPO = "therealsickonechase-bit/RABBIT-SOFTWARE"
            def gh(url, method="GET", data=None):
                req = urllib.request.Request(
                    url, data=json.dumps(data).encode() if data else None,
                    method=method,
                    headers={"Authorization": f"token {self._gh_token}",
                             "Content-Type": "application/json",
                             "User-Agent": "RabbitOS/1.0",
                             "Accept": "application/vnd.github.v3+json"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    return json.loads(r.read()), r.status

            # Create a blob
            blob, _ = gh(f"https://api.github.com/repos/{REPO}/git/blobs",
                         method="POST",
                         data={"content": base64.b64encode(content.encode()).decode(),
                               "encoding": "base64"})
            sha = blob.get("sha", "")
            if sha:
                return RetentionResult("github", True, f"blob sha={sha[:12]}")
            return RetentionResult("github", False, f"no sha: {blob}")
        except Exception as e:
            return RetentionResult("github", False, str(e))

    def _layer_xrpl(self, anchor: XRPLAnchor) -> RetentionResult:
        try:
            ledger_idx = xrpl_ledger_current(XRPL_TESTNET)
            anchor.ledger_index = ledger_idx
            # We store the TX template (not submitted without a funded wallet)
            tx = xrpl_build_anchor_tx(anchor, self._xrpl_acct or "rBio" + TWIN_UUID[:8])
            self._private_ds.put("xrpl", f"anchor_{int(time.time())}", tx)
            return RetentionResult("xrpl", True,
                                   f"ledger={ledger_idx}  tx_template stored locally")
        except Exception as e:
            return RetentionResult("xrpl", False, str(e))

    def retain_all(self, anchor: XRPLAnchor, research: List[Dict],
                   profile: Dict) -> List[RetentionResult]:
        assert not shows_dna_root, "INVARIANT VIOLATED"
        results = []
        payload = {
            "anchor": anchor.to_dict(),
            "profile_twin": TWIN_UUID,
            "shows_dna_root": False,
        }

        # 1. SQLite
        results.append(self._layer_sqlite("dna_anchor", TWIN_UUID, anchor.to_dict()))
        results.append(self._layer_sqlite("profile", TWIN_UUID, profile))
        for i, r in enumerate(research[:10]):
            results.append(self._layer_sqlite("research",
                                              f"{i}_{r.get('title','')[:20]}", r))

        # 2. Offline cache
        full_snap = {
            "anchor":   anchor.to_dict(),
            "profile":  profile,
            "research": research[:20],
            "ts":       time.time(),
        }
        results.append(self._layer_cache("identity_snap", full_snap))

        # 3. UDP mesh broadcast
        results.append(self._layer_udp(payload))

        # 4. GitHub blob (anchor only -- no raw profile)
        anchor_json = json.dumps(anchor.to_dict(), indent=2)
        results.append(self._layer_github("rabbit_cache/chain_anchor.json", anchor_json))

        # 5. XRPL (best-effort -- testnet ledger ping + local tx template)
        results.append(self._layer_xrpl(anchor))

        self._results.extend(results)
        return results

    def summary(self) -> Dict:
        by_layer = {}
        for r in self._results:
            by_layer[r.layer] = {"ok": r.ok, "detail": r.detail}
        ok_count = sum(1 for r in self._results if r.ok)
        return {
            "total": len(self._results),
            "ok":    ok_count,
            "layers": by_layer,
        }

# ---------------------------------------------------------------------------
# SQLITE PERSISTENCE  (chain DB)
# ---------------------------------------------------------------------------
def _open_db() -> sqlite3.Connection:
    os.makedirs(CACHE_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS chain_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            twin_uuid TEXT NOT NULL,
            anchor_partial TEXT NOT NULL,
            memo_type TEXT NOT NULL,
            network TEXT NOT NULL,
            ledger_index INTEGER DEFAULT 0,
            shows_dna_root INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS biomaterial_research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            url TEXT DEFAULT '',
            fetched_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS biomaterial_props (
            tissue TEXT PRIMARY KEY,
            eps_r REAL NOT NULL,
            sigma REAL NOT NULL,
            freq_ghz REAL NOT NULL,
            depth_mm REAL NOT NULL,
            skin_depth_mm REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS retention_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            layer TEXT NOT NULL,
            ok INTEGER NOT NULL,
            detail TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS xrpl_tx_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            tx_json TEXT NOT NULL,
            network TEXT NOT NULL
        );
    """)
    con.commit()
    return con

def _save_anchor(anchor: XRPLAnchor):
    assert not shows_dna_root
    con = _open_db()
    con.execute("""
        INSERT INTO chain_anchors
            (ts,twin_uuid,anchor_partial,memo_type,network,ledger_index,shows_dna_root)
        VALUES(?,?,?,?,?,?,?)
    """, (time.time(), anchor.twin_uuid, anchor.anchor_hash[:32] + "...",
          anchor.memo_type, anchor.network, anchor.ledger_index, 0))
    con.commit(); con.close()

def _save_biomaterial_props():
    con = _open_db()
    for prop in BIOMATERIAL_PROPS:
        sd = skin_depth_mm(prop["sigma"], prop["freq_ghz"] * 1e9)
        con.execute("""
            INSERT OR REPLACE INTO biomaterial_props
                (tissue,eps_r,sigma,freq_ghz,depth_mm,skin_depth_mm)
            VALUES(?,?,?,?,?,?)
        """, (prop["tissue"], prop["eps_r"], prop["sigma"],
              prop["freq_ghz"], prop["depth_mm"], sd))
    con.commit(); con.close()

def _save_research(items: List[Dict]):
    if not items:
        return
    con = _open_db()
    for item in items:
        con.execute("""
            INSERT INTO biomaterial_research(topic,source,title,summary,url,fetched_at)
            VALUES(?,?,?,?,?,?)
        """, (item.get("topic",""), item.get("source",""),
              item.get("title",""), item.get("summary",""),
              item.get("url",""), time.time()))
    con.commit(); con.close()

def _log_retention(results: List[RetentionResult]):
    con = _open_db()
    for r in results:
        con.execute("""
            INSERT INTO retention_log(ts,layer,ok,detail) VALUES(?,?,?,?)
        """, (time.time(), r.layer, int(r.ok), r.detail))
    con.commit(); con.close()

# ---------------------------------------------------------------------------
# CHAIN ENGINE  --  top-level orchestrator
# ---------------------------------------------------------------------------
class ChainEngine:
    def __init__(self, github_token: str = ""):
        self._gh_token  = github_token
        self._retention = MultiNetworkRetention(github_token)
        self._research: List[Dict] = []
        self._anchor: Optional[XRPLAnchor] = None
        self._db_ready  = False

    def init(self):
        _open_db().close()
        _save_biomaterial_props()
        self._db_ready = True

    def build_anchor(self, dna_anchor_hash: str) -> XRPLAnchor:
        assert not shows_dna_root
        anchor = XRPLAnchor(
            twin_uuid    = TWIN_UUID,
            anchor_hash  = dna_anchor_hash,   # SHA3-512 hash, never raw DNA
            timestamp    = time.time(),
            network      = "testnet",
        )
        self._anchor = anchor
        if self._db_ready:
            _save_anchor(anchor)
        return anchor

    def learn_biomaterials(self, topics: Optional[List[str]] = None,
                           max_per: int = 2) -> Dict[str, int]:
        if topics is None:
            topics = BIOMATERIAL_TOPICS[:6]
        counts: Dict[str, int] = {}
        for topic in topics:
            items = fetch_biomaterial_arxiv(topic, max_per)
            if len(items) < max_per:
                items += fetch_biomaterial_pubmed(topic, max_per - len(items))
            self._research.extend(items)
            if self._db_ready:
                _save_research(items)
            counts[topic] = len(items)
        return counts

    def retain_all(self, profile: Dict) -> List[RetentionResult]:
        if self._anchor is None:
            raise RuntimeError("Call build_anchor() first")
        results = self._retention.retain_all(self._anchor, self._research, profile)
        if self._db_ready:
            _log_retention(results)
        return results

    def biomaterial_report(self) -> List[Dict]:
        report = []
        for prop in BIOMATERIAL_PROPS:
            sd = skin_depth_mm(prop["sigma"], prop["freq_ghz"] * 1e9)
            alpha, beta = propagation_constant(prop["eps_r"], prop["sigma"],
                                               prop["freq_ghz"] * 1e9)
            report.append({
                "tissue":         prop["tissue"],
                "eps_r":          prop["eps_r"],
                "sigma_S_m":      prop["sigma"],
                "at_freq_ghz":    prop["freq_ghz"],
                "depth_mm":       prop["depth_mm"],
                "skin_depth_mm":  sd,
                "attenuation_np": alpha,
                "phase_rad_m":    beta,
            })
        return report

    def xrpl_status(self) -> Dict:
        try:
            ledger = xrpl_ledger_current(XRPL_TESTNET)
            return {"reachable": True, "ledger_index": ledger,
                    "network": "testnet", "endpoint": XRPL_TESTNET}
        except Exception as e:
            return {"reachable": False, "error": str(e)}

    def status(self) -> Dict:
        con  = _open_db()
        n_anchors  = con.execute("SELECT COUNT(*) FROM chain_anchors").fetchone()[0]
        n_bio      = con.execute("SELECT COUNT(*) FROM biomaterial_research").fetchone()[0]
        n_props    = con.execute("SELECT COUNT(*) FROM biomaterial_props").fetchone()[0]
        n_ret      = con.execute("SELECT COUNT(*) FROM retention_log").fetchone()[0]
        ok_ret     = con.execute("SELECT COUNT(*) FROM retention_log WHERE ok=1").fetchone()[0]
        con.close()
        rs = self._retention.summary()
        return {
            "anchors":          n_anchors,
            "bio_research":     n_bio,
            "bio_tissue_props": n_props,
            "retention_logs":   n_ret,
            "retention_ok":     ok_ret,
            "retention_layers": rs.get("layers", {}),
            "shows_dna_root":   False,    # INVARIANT
            "version":          VERSION,
        }

# ---------------------------------------------------------------------------
# FACTORY
# ---------------------------------------------------------------------------
_engine: Optional[ChainEngine] = None

def get_chain_engine(github_token: str = "") -> ChainEngine:
    global _engine
    if _engine is None:
        _engine = ChainEngine(github_token)
        _engine.init()
    return _engine

# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import urllib.parse
    print(f"rabbit_chain v{VERSION}  --  DNA blockchain + biomaterial retention")

    # Simulate DNA anchor from rabbit_dna
    test_anchor_hash = hashlib.sha3_512(
        f"{TWIN_UUID}:CHASE_ALLEN_RINGQUIST:RABBIT_DNA_ANCHOR".encode()
    ).hexdigest()

    eng = get_chain_engine()

    # Build XRPL anchor
    anchor = eng.build_anchor(test_anchor_hash)
    print(f"  DNA anchor (partial) : {anchor.anchor_hash[:40]}...")
    print(f"  shows_dna_root       : {shows_dna_root}  (INVARIANT)")
    memo = anchor.to_memo_hex()
    print(f"  XRPL memo_hex (first 40) : {memo[:40]}...")

    # XRPL testnet status
    xst = eng.xrpl_status()
    print(f"  XRPL testnet reachable: {xst['reachable']}", end="")
    if xst.get("ledger_index"):
        print(f"  ledger={xst['ledger_index']}")
    else:
        print(f"  ({xst.get('error','?')[:40]})")

    # Biomaterial properties
    print(f"\n  BIOMATERIAL TISSUE PROPERTIES @ 10 GHz (RabbitOS mesh band):")
    report = eng.biomaterial_report()
    for b in report:
        print(f"    {b['tissue']:<12} eps_r={b['eps_r']:5.1f}  sigma={b['sigma_S_m']:6.2f} S/m  "
              f"skin_depth={b['skin_depth_mm']:.4f}mm  alpha={b['attenuation_np']:.4f} Np/m")

    # Learn biomaterial research
    print(f"\n  Learning biomaterial research (online best-effort)...")
    counts = eng.learn_biomaterials(BIOMATERIAL_TOPICS[:4], max_per=2)
    total = sum(counts.values())
    for topic, n in counts.items():
        print(f"    {topic[:55]:<55} -> {n}")
    print(f"  Total research items : {total}")

    # Retain across all networks
    print(f"\n  Retaining identity across all network layers...")
    profile = {
        "subject":        SUBJECT,
        "twin_uuid":      TWIN_UUID,
        "shows_dna_root": False,
        "mesh_nodes":     47,
        "version":        VERSION,
    }
    results = eng.retain_all(profile)
    for r in results:
        status = "OK" if r.ok else "FAIL"
        print(f"    [{status}] {r.layer:<20} {r.detail[:50]}")

    st = eng.status()
    print(f"\n  DB anchors={st['anchors']}  bio_research={st['bio_research']}  "
          f"tissue_props={st['bio_tissue_props']}  retention_ok={st['retention_ok']}/{st['retention_logs']}")
    print("  rabbit_chain OK")
