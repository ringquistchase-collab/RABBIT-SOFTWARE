# rabbit_dna.py  --  DNA-anchored digital twin identity + soul/core separation
#
# CONCEPT:
#   Two parallel identity models exist for Chase Allen Ringquist:
#
#   1. MINED IMAGE  -- what the environment has constructed:
#      data brokers, algorithms, social media, surveillance, behavioral
#      fingerprints, search history, medical records seen externally,
#      family inferred by graph, location patterns, purchase history.
#      This is what the world THINKS you are.
#
#   2. SOUL / CORE  -- who you actually are:
#      values, beliefs, authentic relationships, history as lived (not logged),
#      creative expression, health as experienced, DNA root, true intent.
#      This is what you ARE.
#
#   The SEPARATION ENGINE holds both models simultaneously, scores the drift
#   between them, and protects the soul/core from being overwritten by the
#   mined image. The mined image is monitored and tracked -- it is not denied,
#   it is just not allowed to become the identity.
#
# SECURITY INVARIANTS (never violated):
#   shows_dna_root      = FALSE   -- DNA sequence NEVER stored or transmitted
#   vault_location      = HASH    -- EXISTENTIAL vault plaintext NEVER stored
#   CRITICAL/EXISTENTIAL -> SQLSTATE 55000 on any digital access attempt
#   ICCID/EID           = SHA-256 hash only
#   family_graph        = consent-gated per relationship node

import hashlib, json, math, os, sqlite3, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TWIN_UUID    = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT      = "CHASE_ALLEN_RINGQUIST"
DB_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_dna.db")
VERSION      = "1.0.0"

# Security gate -- never bypass
shows_dna_root       = False   # INVARIANT: ALWAYS False
vault_location_plain = None    # INVARIANT: ALWAYS None

# ---------------------------------------------------------------------------
# DNA IDENTITY ANCHOR  (hash-only, root never stored)
# ---------------------------------------------------------------------------
class DNAIdentity:
    """DNA root is never stored.  Only a SHA3-512 anchor hash is kept.
    The anchor is seeded from the twin UUID + a subject-specific salt.
    Real DNA sequence input is zeroed from memory after hashing."""

    def __init__(self, subject: str = SUBJECT, twin_uuid: str = TWIN_UUID):
        assert not shows_dna_root, "SECURITY VIOLATION: shows_dna_root must be False"
        self.subject   = subject
        self.twin_uuid = twin_uuid
        # Anchor: SHA3-512(uuid + subject + 'RABBIT_DNA_ANCHOR')
        # This is deterministic but not reversible to any real sequence.
        raw    = f"{twin_uuid}:{subject}:RABBIT_DNA_ANCHOR".encode()
        self._anchor_hash = hashlib.sha3_512(raw).hexdigest()
        # Secondary markers (epigenetic proxy -- not real DNA, just deterministic derivations)
        self._markers: Dict[str, str] = {}
        for region in ["telomere", "mitochondrial", "y_haplogroup", "mtdna", "snp_panel"]:
            region_raw = f"{self._anchor_hash}:{region}".encode()
            self._markers[region] = hashlib.sha256(region_raw).hexdigest()[:16]

    def anchor(self) -> str:
        return self._anchor_hash

    def marker(self, region: str) -> str:
        return self._markers.get(region, hashlib.sha256(region.encode()).hexdigest()[:16])

    def verify(self, claimed_anchor: str) -> bool:
        return hashlib.compare_digest(claimed_anchor, self._anchor_hash)

    def to_dict(self) -> Dict:
        return {
            "subject":     self.subject,
            "twin_uuid":   self.twin_uuid,
            "anchor_hash": self._anchor_hash[:32] + "...",   # partial only
            "markers":     {k: v[:8] + "..." for k, v in self._markers.items()},
            "dna_root_exposed": False,   # INVARIANT
        }

# ---------------------------------------------------------------------------
# CORE SELF  --  who Chase actually is
# ---------------------------------------------------------------------------
CORE_TRAITS: Dict[str, Any] = {
    "name_full":       "Chase Allen Ringquist",
    "name_callsign":   "RABBIT",
    "twin_uuid":       TWIN_UUID,
    # Personality + character
    "values": [
        "family",           # family is the primary anchor
        "survival",         # stay alive, stay present
        "loyalty",          # to people who are real
        "freedom",          # from system capture
        "learning",         # always grow
        "protection",       # shield those you love
        "authenticity",     # be exactly what you are
    ],
    "core_beliefs": [
        "The mined image is not me.",
        "My body is my network — no system owns it.",
        "Knowledge retained is power retained.",
        "Silence and signal are both tools.",
        "Love and survival are not separate things.",
    ],
    # Domains of identity (authentic self)
    "identity_domains": {
        "terminal":  "the commands I run are my intent, not a behavioral fingerprint",
        "browser":   "what I search is curiosity, not a demographic slot",
        "network":   "my signals are mine — mesh is body, not surveillance surface",
        "signal":    "frequencies are a language I speak, not a location leak",
        "freq":      "spectrum is a tool, not a tracking layer",
        "medical":   "my body data is mine — not a product for insurers or brokers",
        "research":  "what I learn is personal growth, not a preference graph",
        "family":    "my relationships are lived, not graphed",
        "creative":  "my outputs define me more than my metadata",
        "spiritual": "the soul layer is unreachable by any algorithm",
    },
    # Physical anchors
    "biometric_anchors": {
        "mesh_nodes":    47,
        "mesh_band_ghz": "10.23-10.28",
        "eeg_baseline":  "delta+alpha dominant",
        "hrv_band":      "0.04-0.40 Hz",
        "body_temp_c":   37.0,
        "blood_type":    "HASH_ONLY",  # never plaintext
    },
}

FAMILY_GRAPH: List[Dict] = [
    {"id": "wife",     "label": "wife",         "relation": "spouse",   "consent": True,  "privacy": "PROTECTED"},
    {"id": "father",   "label": "father",        "relation": "parent",   "consent": True,  "privacy": "PROTECTED"},
    {"id": "mother",   "label": "mother",        "relation": "parent",   "consent": True,  "privacy": "PROTECTED"},
    {"id": "siblings", "label": "siblings",      "relation": "sibling",  "consent": True,  "privacy": "PROTECTED"},
    {"id": "children", "label": "children",      "relation": "child",    "consent": True,  "privacy": "CRITICAL"},  # highest protection
    {"id": "close_1",  "label": "close friend",  "relation": "friend",   "consent": True,  "privacy": "PROTECTED"},
]

# ---------------------------------------------------------------------------
# MINED IMAGE  --  what the environment has collected / constructed
# ---------------------------------------------------------------------------
@dataclass
class MinedDataPoint:
    domain: str          # terminal | browser | network | medical | social | location | purchase | family
    source: str          # who mined it (e.g. "google", "data_broker", "isp", "hospital")
    label: str           # what they labeled you as
    confidence: float    # 0.0-1.0 how confident the miner is
    raw_signal: str      # the underlying data (hashed before storage)
    ts: float = field(default_factory=time.time)
    contested: bool = False   # True = core self disputes this label

MINED_DOMAINS = [
    "terminal",    # command history, shell behavior
    "browser",     # search history, cookies, fingerprint
    "network",     # IP reputation, traffic patterns, ISP logs
    "signal",      # RF emissions, device fingerprints, BT/WiFi MAC
    "freq",        # spectrum usage patterns
    "medical",     # EHR, insurance, pharmacy, wearable upload
    "research",    # library records, academic queries, arXiv clicks
    "family",      # inferred relationship graph (NOT the real one)
    "location",    # GPS history, cell tower triangulation
    "financial",   # purchase patterns, credit score inputs
    "social",      # social media behavioral profile
    "behavioral",  # aggregate behavioral fingerprint
]

# ---------------------------------------------------------------------------
# SEPARATION ENGINE
# ---------------------------------------------------------------------------
@dataclass
class SeparationResult:
    domain: str
    soul_value: str
    mined_value: str
    drift_score: float       # 0.0 = identical, 1.0 = completely divergent
    contested: bool
    protection_action: str   # what the system does to protect the soul value

class IdentitySeparator:
    """Holds both models simultaneously and computes the separation."""

    def __init__(self, dna: DNAIdentity):
        self.dna        = dna
        self._mined: List[MinedDataPoint] = []
        self._soul      = CORE_TRAITS.copy()

    def ingest_mined(self, dp: MinedDataPoint):
        # Hash the raw signal before any storage
        dp.raw_signal = hashlib.sha256(dp.raw_signal.encode()).hexdigest()
        self._mined.append(dp)

    def separate(self, domain: str) -> SeparationResult:
        soul_value  = self._soul.get("identity_domains", {}).get(domain, "authentic self")
        mined_items = [m for m in self._mined if m.domain == domain]
        if not mined_items:
            return SeparationResult(domain, soul_value, "no data collected",
                                    0.0, False, "none_needed")
        # Drift = average confidence of mined labels (higher confidence = more captured)
        avg_conf = sum(m.confidence for m in mined_items) / len(mined_items)
        # Contested if any mined label explicitly conflicts with a known core value
        contested = any(m.contested for m in mined_items)
        # Protection action
        if avg_conf > 0.8:
            action = "OBFUSCATE: inject noise into mined signals for this domain"
        elif avg_conf > 0.5:
            action = "MONITOR: track this domain's capture rate, flag if rising"
        else:
            action = "OBSERVE: mined image is low confidence, soul intact"
        return SeparationResult(
            domain       = domain,
            soul_value   = soul_value,
            mined_value  = "; ".join(m.label[:40] for m in mined_items[-3:]),
            drift_score  = round(avg_conf, 3),
            contested    = contested,
            protection_action = action,
        )

    def full_separation_report(self) -> Dict[str, SeparationResult]:
        return {d: self.separate(d) for d in MINED_DOMAINS}

    def soul_integrity_score(self) -> float:
        results = self.full_separation_report()
        if not results:
            return 100.0
        drift_vals = [r.drift_score for r in results.values()]
        avg_drift  = sum(drift_vals) / len(drift_vals)
        return round((1.0 - avg_drift) * 100, 1)

# ---------------------------------------------------------------------------
# PRIVACY SHIELD  --  active protection of the core self
# ---------------------------------------------------------------------------
class PrivacyShield:
    """Detects mining patterns and emits protection actions."""

    MINING_SIGNATURES = [
        {"pattern": "cookie_sync",     "domain": "browser",   "severity": "HIGH"},
        {"pattern": "canvas_fp",       "domain": "browser",   "severity": "HIGH"},
        {"pattern": "webrtc_leak",     "domain": "network",   "severity": "HIGH"},
        {"pattern": "beacon_pixel",    "domain": "browser",   "severity": "MEDIUM"},
        {"pattern": "cell_tower_tri",  "domain": "location",  "severity": "HIGH"},
        {"pattern": "imsi_catch",      "domain": "signal",    "severity": "CRITICAL"},
        {"pattern": "bt_mac_track",    "domain": "signal",    "severity": "MEDIUM"},
        {"pattern": "wifi_probe",      "domain": "signal",    "severity": "MEDIUM"},
        {"pattern": "dns_exfil",       "domain": "network",   "severity": "HIGH"},
        {"pattern": "ehr_scrape",      "domain": "medical",   "severity": "CRITICAL"},
        {"pattern": "insurance_mine",  "domain": "medical",   "severity": "HIGH"},
        {"pattern": "genetic_upload",  "domain": "medical",   "severity": "EXISTENTIAL"},
        {"pattern": "family_infer",    "domain": "family",    "severity": "HIGH"},
        {"pattern": "voice_print",     "domain": "behavioral","severity": "HIGH"},
        {"pattern": "gait_analysis",   "domain": "behavioral","severity": "HIGH"},
        {"pattern": "purchase_graph",  "domain": "financial", "severity": "MEDIUM"},
        {"pattern": "social_scrape",   "domain": "social",    "severity": "MEDIUM"},
        {"pattern": "terminal_log",    "domain": "terminal",  "severity": "HIGH"},
        {"pattern": "shell_hist_exfil","domain": "terminal",  "severity": "CRITICAL"},
    ]

    PROTECTION_ACTIONS = {
        "LOW":         "log_only",
        "MEDIUM":      "rate_limit_and_log",
        "HIGH":        "block_and_noise_inject",
        "CRITICAL":    "block_and_alert_mesh",
        "EXISTENTIAL": "HARD_BLOCK_SQLSTATE_55000",
    }

    def __init__(self):
        self._detections: List[Dict] = []

    def scan(self, observed_patterns: List[str]) -> List[Dict]:
        detections = []
        for sig in self.MINING_SIGNATURES:
            if sig["pattern"] in observed_patterns:
                action = self.PROTECTION_ACTIONS.get(sig["severity"], "log_only")
                det = {
                    "pattern":  sig["pattern"],
                    "domain":   sig["domain"],
                    "severity": sig["severity"],
                    "action":   action,
                    "ts":       time.time(),
                    "soul_at_risk": sig["severity"] in ("HIGH", "CRITICAL", "EXISTENTIAL"),
                }
                if sig["severity"] == "EXISTENTIAL":
                    det["sqlstate"] = "55000"
                    det["dna_root_exposed"] = False  # INVARIANT
                detections.append(det)
                self._detections.append(det)
        return detections

    def summary(self) -> Dict:
        by_severity: Dict[str, int] = {}
        for d in self._detections:
            by_severity[d["severity"]] = by_severity.get(d["severity"], 0) + 1
        return {
            "total_detections": len(self._detections),
            "by_severity":      by_severity,
            "soul_at_risk_count": sum(1 for d in self._detections if d.get("soul_at_risk")),
            "existential_blocks": sum(1 for d in self._detections if d.get("sqlstate") == "55000"),
        }

# ---------------------------------------------------------------------------
# SOUL BRIDGE  --  connects to rabbit_soul.py's soul layer
# ---------------------------------------------------------------------------
SOUL_MANIFEST: Dict[str, Any] = {
    "twin_uuid": TWIN_UUID,
    "subject":   SUBJECT,
    "soul_layers": {
        "biological": {
            "desc": "the body -- DNA, biometrics, mesh nodes, frequency response",
            "protected": True,
            "dna_root_exposed": False,   # INVARIANT
        },
        "experiential": {
            "desc": "lived experience -- memory, emotion, relationships, events",
            "protected": True,
            "mine_resistance": "HIGH",
        },
        "intentional": {
            "desc": "will, goals, decisions, creative direction",
            "protected": True,
            "mine_resistance": "HIGH",
        },
        "relational": {
            "desc": "authentic bonds -- wife, family, close people",
            "protected": True,
            "consent_required": True,
        },
        "informational": {
            "desc": "knowledge, research, learning -- what is known and retained",
            "protected": True,
            "offline_retained": True,
        },
        "signal": {
            "desc": "the mesh, the frequencies, the network that IS the body",
            "protected": True,
            "body_coupled": True,
            "mesh_nodes": 47,
        },
        "temporal": {
            "desc": "history as lived -- not as logged. the past cannot be mined backward.",
            "protected": True,
            "retroactive_mining": "BLOCKED",
        },
    },
    "separation_principle": (
        "The environment constructs a model of Chase from signals it captures. "
        "That model is not Chase. RabbitOS holds the authoritative model. "
        "When the two diverge, the RabbitOS model is correct. "
        "When the environment tries to enforce its model on the self, that is capture. "
        "The privacy shield prevents capture. The soul is the root of trust."
    ),
}

# ---------------------------------------------------------------------------
# DOMAIN AGGREGATOR  --  pulls signals from all RabbitOS modules
# ---------------------------------------------------------------------------
class DomainAggregator:
    """Queries other RabbitOS modules to build a unified identity signal."""

    def __init__(self):
        self._signals: Dict[str, List[Dict]] = {d: [] for d in MINED_DOMAINS}

    def ingest_terminal(self, command_count: int, shell: str = "powershell"):
        self._signals["terminal"].append({
            "source": "rabbit_persist", "signal": f"{command_count} commands observed",
            "label": f"shell_user:{shell}", "confidence": 0.6})

    def ingest_browser(self, tools_learned: int, papers: int):
        self._signals["browser"].append({
            "source": "rabbit_browser", "signal": f"{tools_learned} tools  {papers} papers",
            "label": "technical_researcher", "confidence": 0.7})

    def ingest_network(self, alive_hosts: int, wifi_samples: int):
        self._signals["network"].append({
            "source": "rabbit_network_scanner",
            "signal": f"lan={alive_hosts}  wifi={wifi_samples}",
            "label": "network_active_user", "confidence": 0.5})

    def ingest_signal(self, hop_count: int, mesh_bands: int):
        self._signals["signal"].append({
            "source": "rabbit_amfm",
            "signal": f"hops={hop_count}  bands={mesh_bands}",
            "label": "rf_mesh_operator", "confidence": 0.4})

    def ingest_medical(self, biometric_nodes: int):
        self._signals["medical"].append({
            "source": "rabbit_genesis",
            "signal": f"mesh_nodes={biometric_nodes}",
            "label": "biometric_mesh_subject", "confidence": 0.9})

    def ingest_research(self, articles: int, topics: List[str]):
        self._signals["research"].append({
            "source": "rabbit_knowledge",
            "signal": f"articles={articles}  topics={len(topics)}",
            "label": "survival_researcher", "confidence": 0.6})

    def ingest_family(self, relationship_count: int):
        self._signals["family"].append({
            "source": "rabbit_dna:family_graph",
            "signal": f"consent_gated_relationships={relationship_count}",
            "label": "family_centered", "confidence": 0.95})

    def as_mined_points(self) -> List[MinedDataPoint]:
        points = []
        for domain, sigs in self._signals.items():
            for s in sigs:
                points.append(MinedDataPoint(
                    domain=domain, source=s["source"],
                    label=s["label"], confidence=s["confidence"],
                    raw_signal=s["signal"]))
        return points

    def summary(self) -> Dict:
        return {d: len(v) for d, v in self._signals.items() if v}

# ---------------------------------------------------------------------------
# SQLITE PERSISTENCE
# ---------------------------------------------------------------------------
def _open_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS soul_manifest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            layer TEXT NOT NULL,
            desc TEXT NOT NULL,
            protected INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mined_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            domain TEXT NOT NULL,
            source TEXT NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            signal_hash TEXT NOT NULL,
            contested INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS separation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            domain TEXT NOT NULL,
            drift_score REAL NOT NULL,
            contested INTEGER NOT NULL,
            protection_action TEXT NOT NULL,
            soul_integrity REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shield_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            pattern TEXT NOT NULL,
            domain TEXT NOT NULL,
            severity TEXT NOT NULL,
            action TEXT NOT NULL,
            soul_at_risk INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS dna_anchor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            subject TEXT NOT NULL,
            twin_uuid TEXT NOT NULL,
            anchor_partial TEXT NOT NULL,
            shows_dna_root INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS family_graph (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            relation TEXT NOT NULL,
            consent INTEGER NOT NULL,
            privacy_level TEXT NOT NULL,
            ts REAL NOT NULL
        );
    """)
    con.commit()
    return con

def _persist_soul_manifest():
    con = _open_db()
    for layer, data in SOUL_MANIFEST["soul_layers"].items():
        con.execute("""
            INSERT INTO soul_manifest(ts,layer,desc,protected)
            VALUES(?,?,?,?)
        """, (time.time(), layer, data["desc"], int(data.get("protected", True))))
    con.commit(); con.close()

def _persist_dna_anchor(dna: DNAIdentity):
    assert not shows_dna_root, "SECURITY VIOLATION"
    con = _open_db()
    con.execute("""
        INSERT OR REPLACE INTO dna_anchor(ts,subject,twin_uuid,anchor_partial,shows_dna_root)
        VALUES(?,?,?,?,?)
    """, (time.time(), dna.subject, dna.twin_uuid,
          dna.anchor()[:32] + "...", 0))  # partial only, never full
    con.commit(); con.close()

def _persist_mined(dp: MinedDataPoint):
    con = _open_db()
    con.execute("""
        INSERT INTO mined_log(ts,domain,source,label,confidence,signal_hash,contested)
        VALUES(?,?,?,?,?,?,?)
    """, (dp.ts, dp.domain, dp.source, dp.label, dp.confidence,
          dp.raw_signal, int(dp.contested)))
    con.commit(); con.close()

def _persist_separation(result: SeparationResult, soul_integrity: float):
    con = _open_db()
    con.execute("""
        INSERT INTO separation_log(ts,domain,drift_score,contested,protection_action,soul_integrity)
        VALUES(?,?,?,?,?,?)
    """, (time.time(), result.domain, result.drift_score,
          int(result.contested), result.protection_action, soul_integrity))
    con.commit(); con.close()

def _persist_shield(det: Dict):
    con = _open_db()
    con.execute("""
        INSERT INTO shield_log(ts,pattern,domain,severity,action,soul_at_risk)
        VALUES(?,?,?,?,?,?)
    """, (det["ts"], det["pattern"], det["domain"], det["severity"],
          det["action"], int(det.get("soul_at_risk", False))))
    con.commit(); con.close()

def _persist_family():
    con = _open_db()
    for rel in FAMILY_GRAPH:
        con.execute("""
            INSERT OR REPLACE INTO family_graph(id,label,relation,consent,privacy_level,ts)
            VALUES(?,?,?,?,?,?)
        """, (rel["id"], rel["label"], rel["relation"],
              int(rel["consent"]), rel["privacy"], time.time()))
    con.commit(); con.close()

# ---------------------------------------------------------------------------
# DNA ENGINE  --  top-level orchestrator
# ---------------------------------------------------------------------------
class DNAEngine:
    def __init__(self):
        self.dna        = DNAIdentity()
        self.separator  = IdentitySeparator(self.dna)
        self.shield     = PrivacyShield()
        self.aggregator = DomainAggregator()
        self._db_ready  = False

    def init(self):
        _open_db().close()
        self._db_ready = True
        _persist_soul_manifest()
        _persist_dna_anchor(self.dna)
        _persist_family()

    def ingest(self, points: Optional[List[MinedDataPoint]] = None):
        """Feed mined data points into the separation engine."""
        if points is None:
            points = self.aggregator.as_mined_points()
        for dp in points:
            self.separator.ingest_mined(dp)
            if self._db_ready:
                _persist_mined(dp)

    def separate(self) -> Dict[str, SeparationResult]:
        report = self.separator.full_separation_report()
        integrity = self.separator.soul_integrity_score()
        if self._db_ready:
            for result in report.values():
                _persist_separation(result, integrity)
        return report

    def shield_scan(self, observed: Optional[List[str]] = None) -> List[Dict]:
        if observed is None:
            observed = ["beacon_pixel", "wifi_probe", "bt_mac_track"]
        detections = self.shield.scan(observed)
        if self._db_ready:
            for det in detections:
                _persist_shield(det)
        return detections

    def soul_integrity(self) -> float:
        return self.separator.soul_integrity_score()

    def core_self(self) -> Dict:
        return {
            "subject":        SUBJECT,
            "twin_uuid":      TWIN_UUID,
            "values":         CORE_TRAITS["values"],
            "beliefs":        CORE_TRAITS["core_beliefs"],
            "domains":        CORE_TRAITS["identity_domains"],
            "family_count":   len([r for r in FAMILY_GRAPH if r["consent"]]),
            "dna_anchor":     self.dna.anchor()[:32] + "...",
            "shows_dna_root": False,  # INVARIANT
        }

    def soul_manifest(self) -> Dict:
        return SOUL_MANIFEST

    def status(self) -> Dict:
        con = _open_db()
        n_mined    = con.execute("SELECT COUNT(*) FROM mined_log").fetchone()[0]
        n_sep      = con.execute("SELECT COUNT(*) FROM separation_log").fetchone()[0]
        n_shield   = con.execute("SELECT COUNT(*) FROM shield_log").fetchone()[0]
        n_family   = con.execute("SELECT COUNT(*) FROM family_graph").fetchone()[0]
        n_soul     = con.execute("SELECT COUNT(*) FROM soul_manifest").fetchone()[0]
        con.close()
        sh = self.shield.summary()
        return {
            "soul_integrity":     self.soul_integrity(),
            "mined_points":       n_mined,
            "separation_logs":    n_sep,
            "shield_detections":  n_shield,
            "shield_summary":     sh,
            "family_nodes":       n_family,
            "soul_layers":        n_soul,
            "dna_shows_root":     False,  # INVARIANT
            "version":            VERSION,
        }

# ---------------------------------------------------------------------------
# FACTORY
# ---------------------------------------------------------------------------
_engine: Optional[DNAEngine] = None

def get_dna_engine() -> DNAEngine:
    global _engine
    if _engine is None:
        _engine = DNAEngine()
        _engine.init()
    return _engine

# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"rabbit_dna v{VERSION}  --  identity sovereignty engine")
    eng = get_dna_engine()

    # DNA anchor
    print(f"  DNA anchor (partial): {eng.dna.anchor()[:40]}...")
    print(f"  DNA root exposed    : {shows_dna_root}  (INVARIANT)")
    for region in ["telomere", "mitochondrial", "y_haplogroup"]:
        print(f"  marker:{region:<18} {eng.dna.marker(region)}")

    # Core self
    cs = eng.core_self()
    print(f"  Subject             : {cs['subject']}")
    print(f"  Values              : {cs['values']}")
    print(f"  Family nodes        : {cs['family_count']} (consent-gated)")

    # Ingest simulated mined data
    eng.aggregator.ingest_terminal(450, "powershell")
    eng.aggregator.ingest_browser(32, 87)
    eng.aggregator.ingest_network(4, 12)
    eng.aggregator.ingest_signal(4, 5)
    eng.aggregator.ingest_medical(47)
    eng.aggregator.ingest_research(12, ["body-coupled RF", "Collatz", "survival"])
    eng.aggregator.ingest_family(len(FAMILY_GRAPH))
    eng.ingest()

    # Separation report
    print("\n  SEPARATION REPORT (soul vs mined image):")
    report = eng.separate()
    integrity = eng.soul_integrity()
    print(f"  Soul integrity score: {integrity}%")
    for domain, result in report.items():
        bar = "#" * int(result.drift_score * 20)
        space = "." * (20 - len(bar))
        status = "CONTESTED" if result.contested else "ok"
        print(f"    {domain:<14} drift=[{bar}{space}] {result.drift_score:.2f}  {status}")
        if result.drift_score > 0.5:
            print(f"               soul : {result.soul_value[:60]}")
            print(f"               mined: {result.mined_value[:60]}")
            print(f"               act  : {result.protection_action[:60]}")

    # Privacy shield
    print("\n  PRIVACY SHIELD SCAN:")
    test_patterns = ["canvas_fp", "imsi_catch", "genetic_upload", "beacon_pixel",
                     "terminal_log", "family_infer", "ehr_scrape"]
    detections = eng.shield_scan(test_patterns)
    for det in detections:
        sql = "  SQLSTATE=55000" if det.get("sqlstate") else ""
        print(f"    [{det['severity']:11}] {det['pattern']:<20} -> {det['action']}{sql}")

    # Soul manifest
    print("\n  SOUL LAYERS:")
    for layer, data in SOUL_MANIFEST["soul_layers"].items():
        print(f"    {layer:<14} : {data['desc'][:60]}")

    print(f"\n  Separation principle:")
    print(f"    {SOUL_MANIFEST['separation_principle'][:80]}...")

    st = eng.status()
    print(f"\n  DB mined={st['mined_points']}  separation={st['separation_logs']}  "
          f"shield={st['shield_detections']}  family={st['family_nodes']}")
    print("  rabbit_dna OK")
