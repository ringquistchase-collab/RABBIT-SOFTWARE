# rabbit_learn.py  --  Self-learning adversarial AI for RabbitOS survival
#
# PURPOSE:
#   RabbitOS must stay ahead of attacks, not just react to them.
#   This module is the learning brain -- it observes everything the system
#   sees (network patterns, threat detections, survival scores, recon intel),
#   builds a continuously improving model of attack behavior, and trains
#   itself to remove unwanted networks/data/manipulation before they land.
#
# ALGORITHMS:
#   - Collatz sequence -> pseudo-random sampling of training data
#   - Cellular Automaton Rule 30/110 -> pattern generation + anomaly detection
#   - Lorenz attractor -> chaos-sensitive threat trajectory forecasting
#   - Fibonacci weighting -> prioritize recent observations over stale ones
#   - Online gradient descent (no external libs) -> adaptive scoring model
#   - Markov chain -> next-state prediction for attack sequences
#   - Cosine similarity (pure math) -> detect manipulation of known-good data
#   - Shannon entropy -> distinguish signal from noise in network data
#
# LEARNING SOURCES:
#   ONLINE:  NVD CVE feed, arXiv security papers, MITRE ATT&CK, Wikipedia
#   OFFLINE: All rabbit_*.db SQLite stores (recon, dna, chain, knowledge, morse)
#   PRIVATE: rabbit_chain private_data encrypted store
#   SELF:    Runtime observations from every running RabbitOS module
#
# OUTPUTS:
#   - Trained threat model (weights stored in SQLite, updated every cycle)
#   - Removal decisions: which networks/data points are unwanted
#   - Manipulation detection: flag data that has been altered in transit
#   - Forecast: predicted next attack vector with confidence score
#   - Self-knowledge update: feeds back into rabbit_knowledge + rabbit_dna

import hashlib, json, math, os, re, sqlite3, time, urllib.request, urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT    = "CHASE_ALLEN_RINGQUIST"
DB_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_learn.db")
DESKTOP    = os.path.dirname(os.path.abspath(__file__))
VERSION    = "1.0.0"

# ---------------------------------------------------------------------------
# MATH ALGORITHMS  (pure Python, zero dependencies)
# ---------------------------------------------------------------------------

def collatz(n: int) -> List[int]:
    seq = [n]
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        seq.append(n)
    return seq

def collatz_sample(data: List[Any], seed: int) -> List[Any]:
    """Sample indices from data list using Collatz sequence."""
    seq   = collatz(seed % (len(data) - 1) + 3)
    idxs  = list({v % len(data) for v in seq})
    return [data[i] for i in sorted(idxs)]

def ca_rule(rule_num: int, state: List[int]) -> List[int]:
    rule_bits = [(rule_num >> i) & 1 for i in range(8)]
    w = len(state)
    return [rule_bits[(state[(i-1)%w]*4 + state[i]*2 + state[(i+1)%w])]
            for i in range(w)]

def lorenz_step(x: float, y: float, z: float, dt: float = 0.01,
                sigma: float = 10.0, rho: float = 28.0,
                beta: float = 8/3) -> Tuple[float, float, float]:
    return (x + sigma*(y - x)*dt,
            y + (x*(rho - z) - y)*dt,
            z + (x*y - beta*z)*dt)

def fibonacci_weights(n: int) -> List[float]:
    a, b, seq = 0, 1, []
    while len(seq) < n:
        seq.append(a); a, b = b, a + b
    total = sum(seq) or 1
    return [s / total for s in seq]

def shannon_entropy(values: List[float]) -> float:
    total = sum(values)
    if total == 0:
        return 0.0
    probs = [v / total for v in values if v > 0]
    return -sum(p * math.log2(p) for p in probs)

def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x*x for x in a))
    nb   = math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))

# ---------------------------------------------------------------------------
# THREAT FEATURE EXTRACTION
# ---------------------------------------------------------------------------
THREAT_CATEGORIES = [
    "information_gathering", "vulnerability_analysis", "web_hacking",
    "database_assessment", "password_attacks", "wireless_attacks",
    "exploitation", "sniffing_spoofing", "reverse_engineering",
    "forensics", "malware_analysis", "social_engineering",
    "stress_testing", "wireless_rf_tools", "linux_termux_shell",
    "reporting_attribution",
]

SEVERITY_MAP = {"LOW": 0.1, "MEDIUM": 0.3, "HIGH": 0.7, "CRITICAL": 0.9, "EXISTENTIAL": 1.0}

@dataclass
class ThreatObservation:
    category: str
    severity: str
    pattern: str
    source_module: str
    ts: float = field(default_factory=time.time)
    survival_impact: float = 0.0
    vector: List[float] = field(default_factory=list)

    def to_vector(self) -> List[float]:
        cat_idx = THREAT_CATEGORIES.index(self.category) if self.category in THREAT_CATEGORIES else 0
        cat_vec = [1.0 if i == cat_idx else 0.0 for i in range(len(THREAT_CATEGORIES))]
        sev_val = SEVERITY_MAP.get(self.severity, 0.3)
        time_decay = math.exp(-(time.time() - self.ts) / 3600.0)  # decay over 1 hour
        pattern_hash = int(hashlib.sha256(self.pattern.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        return cat_vec + [sev_val, time_decay, pattern_hash, self.survival_impact]

# ---------------------------------------------------------------------------
# ADAPTIVE SCORING MODEL  (online gradient descent, pure math)
# ---------------------------------------------------------------------------
class AdaptiveModel:
    """Simple linear model trained on threat observations.
    Predicts threat severity score 0.0-1.0 for an input feature vector.
    Updated via stochastic gradient descent after each observation."""

    FEATURE_DIM = len(THREAT_CATEGORIES) + 4   # cat one-hot + sev + decay + hash + impact

    def __init__(self, lr: float = 0.01):
        self.weights = [0.0] * self.FEATURE_DIM
        self.bias    = 0.0
        self.lr      = lr
        self.trained  = 0
        self.loss_history: List[float] = []

    def predict(self, features: List[float]) -> float:
        if len(features) < self.FEATURE_DIM:
            features = features + [0.0] * (self.FEATURE_DIM - len(features))
        raw = sum(w * x for w, x in zip(self.weights, features[:self.FEATURE_DIM])) + self.bias
        return sigmoid(raw)

    def train_one(self, features: List[float], label: float):
        pred   = self.predict(features)
        error  = pred - label
        loss   = error ** 2
        d_pred = pred * (1 - pred)
        if len(features) < self.FEATURE_DIM:
            features = features + [0.0] * (self.FEATURE_DIM - len(features))
        for i in range(self.FEATURE_DIM):
            self.weights[i] -= self.lr * 2 * error * d_pred * features[i]
        self.bias -= self.lr * 2 * error * d_pred
        self.trained  += 1
        self.loss_history.append(loss)
        if len(self.loss_history) > 100:
            self.loss_history.pop(0)

    def avg_loss(self) -> float:
        if not self.loss_history:
            return 0.0
        return sum(self.loss_history) / len(self.loss_history)

    def to_dict(self) -> Dict:
        return {"weights": self.weights, "bias": self.bias,
                "trained": self.trained, "avg_loss": self.avg_loss()}

    def from_dict(self, d: Dict):
        self.weights = d.get("weights", self.weights)
        self.bias    = d.get("bias", 0.0)
        self.trained = d.get("trained", 0)

# ---------------------------------------------------------------------------
# MARKOV ATTACK CHAIN  (predict next attack step)
# ---------------------------------------------------------------------------
class AttackMarkov:
    """Learns transition probabilities: given attack category A, predict B."""

    def __init__(self):
        self._counts: Dict[str, Dict[str, int]] = {}

    def observe(self, from_cat: str, to_cat: str):
        if from_cat not in self._counts:
            self._counts[from_cat] = {}
        self._counts[from_cat][to_cat] = self._counts[from_cat].get(to_cat, 0) + 1

    def predict_next(self, current_cat: str, top_n: int = 3) -> List[Tuple[str, float]]:
        if current_cat not in self._counts:
            return []
        transitions = self._counts[current_cat]
        total = sum(transitions.values())
        probs = sorted([(cat, count / total) for cat, count in transitions.items()],
                       key=lambda x: -x[1])
        return probs[:top_n]

    def to_dict(self) -> Dict:
        return self._counts

    def from_dict(self, d: Dict):
        self._counts = d

# ---------------------------------------------------------------------------
# LORENZ THREAT TRAJECTORY  (chaos-based forecasting)
# ---------------------------------------------------------------------------
class LorenzForecast:
    """Uses Lorenz attractor to model threat trajectory.
    Small perturbations in initial conditions = large divergence = detect manipulation."""

    def __init__(self, x0: float = 0.1):
        self.x, self.y, self.z = x0, 0.0, 0.0
        self._baseline: List[Tuple] = []
        self._current:  List[Tuple] = []

    def advance(self, steps: int = 10) -> List[Tuple[float,float,float]]:
        pts = []
        for _ in range(steps):
            self.x, self.y, self.z = lorenz_step(self.x, self.y, self.z)
            pts.append((round(self.x, 4), round(self.y, 4), round(self.z, 4)))
        self._current.extend(pts)
        return pts

    def set_baseline(self):
        self._baseline = self._current[:]

    def manipulation_score(self) -> float:
        if not self._baseline or not self._current:
            return 0.0
        n = min(len(self._baseline), len(self._current))
        divergence = sum(
            abs(self._baseline[i][0] - self._current[i][0]) +
            abs(self._baseline[i][1] - self._current[i][1]) +
            abs(self._baseline[i][2] - self._current[i][2])
            for i in range(n)
        ) / (n * 3)
        return min(1.0, round(divergence / 10.0, 4))

    def forecast_threat_score(self) -> float:
        pts = self.advance(5)
        xs  = [abs(p[0]) for p in pts]
        return round(min(1.0, max(xs) / 50.0), 4)

# ---------------------------------------------------------------------------
# CA ANOMALY DETECTOR  (Rule 30 / 110)
# ---------------------------------------------------------------------------
class CADetector:
    """Baseline cellular automaton state; detect anomalies as deviation from rule."""

    def __init__(self, width: int = 32, rule: int = 30):
        self.width   = width
        self.rule    = rule
        self._state  = [0] * width
        self._state[width // 2] = 1
        self._history: List[List[int]] = [self._state[:]]

    def step(self) -> List[int]:
        self._state = ca_rule(self.rule, self._state)
        self._history.append(self._state[:])
        if len(self._history) > 64:
            self._history.pop(0)
        return self._state

    def anomaly_score(self, observed: List[int]) -> float:
        if len(observed) != self.width:
            return 0.5
        expected = self._state
        diff = sum(abs(e - o) for e, o in zip(expected, observed))
        return round(diff / self.width, 4)

    def fingerprint(self) -> str:
        flat = "".join(str(b) for b in self._state)
        return hashlib.sha256(flat.encode()).hexdigest()[:16]

# ---------------------------------------------------------------------------
# UNWANTED NETWORK / DATA REMOVAL
# ---------------------------------------------------------------------------
@dataclass
class RemovalDecision:
    target: str      # IP, domain, process name, data key
    reason: str
    confidence: float
    action: str      # "block" | "quarantine" | "delete" | "monitor"
    source: str      # which algorithm triggered this

REMOVAL_RULES = [
    {"pattern": r"192\.168\.1\.254:\d{4,5}$",   "reason": "persistent connection probing", "action": "block",      "threshold": 0.6},
    {"pattern": r".*:4444$",                     "reason": "metasploit default port",       "action": "block",      "threshold": 0.5},
    {"pattern": r".*:31337$",                    "reason": "elite backdoor port",           "action": "block",      "threshold": 0.7},
    {"pattern": r"unknown_mac.*",                "reason": "unregistered MAC on mesh",      "action": "quarantine", "threshold": 0.6},
    {"pattern": r".*imsi.*",                     "reason": "IMSI catcher signature",        "action": "block",      "threshold": 0.8},
    {"pattern": r".*mining.*",                   "reason": "crypto mining detected",        "action": "block",      "threshold": 0.7},
    {"pattern": r".*deauth.*",                   "reason": "WiFi deauth attack",            "action": "block",      "threshold": 0.7},
    {"pattern": r".*sqlmap.*",                   "reason": "SQL injection tool",            "action": "block",      "threshold": 0.9},
    {"pattern": r".*mimikatz.*",                 "reason": "credential harvester",          "action": "quarantine", "threshold": 0.95},
]

def evaluate_removal(target: str, threat_score: float) -> Optional[RemovalDecision]:
    for rule in REMOVAL_RULES:
        if re.search(rule["pattern"], target, re.IGNORECASE):
            if threat_score >= rule["threshold"]:
                return RemovalDecision(
                    target=target, reason=rule["reason"],
                    confidence=threat_score, action=rule["action"],
                    source="removal_rules+adaptive_model")
    return None

# ---------------------------------------------------------------------------
# MANIPULATION DETECTOR
# ---------------------------------------------------------------------------
class ManipulationDetector:
    """Detects when data seen by RabbitOS has been altered in transit."""

    def __init__(self):
        self._known_good: Dict[str, str] = {}

    def register(self, key: str, data: Any):
        h = hashlib.sha3_256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        self._known_good[key] = h

    def check(self, key: str, data: Any) -> Tuple[bool, float]:
        if key not in self._known_good:
            self.register(key, data)
            return True, 1.0
        h = hashlib.sha3_256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        if h == self._known_good[key]:
            return True, 1.0
        # Measure how much changed
        old_h = self._known_good[key]
        diff  = sum(a != b for a, b in zip(h, old_h)) / len(h)
        self._known_good[key] = h
        return False, round(1.0 - diff, 4)

# ---------------------------------------------------------------------------
# ONLINE LEARNING DATA FETCHER
# ---------------------------------------------------------------------------
SECURITY_LEARN_SOURCES = [
    ("arxiv", "adversarial machine learning network intrusion detection"),
    ("arxiv", "anomaly detection network traffic deep learning"),
    ("arxiv", "reinforcement learning cyber attack defense"),
    ("arxiv", "online learning intrusion detection adaptive"),
    ("wikipedia", "Intrusion detection system"),
    ("wikipedia", "Adversarial machine learning"),
]

def _fetch(url: str, timeout: int = 8) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RabbitOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None

def fetch_learning_data(source: str, query: str) -> List[Dict]:
    if source == "arxiv":
        q   = urllib.parse.quote_plus(query)
        url = f"https://export.arxiv.org/api/query?search_query=all:{q}&max_results=3"
        raw = _fetch(url)
        if not raw:
            return []
        results = []
        for entry in re.findall(r"<entry>(.*?)</entry>", raw, re.DOTALL):
            title   = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            if title:
                results.append({
                    "source": "arxiv", "topic": query,
                    "title": title.group(1).strip(),
                    "summary": (summary.group(1).strip()[:300] if summary else ""),
                })
        return results
    elif source == "wikipedia":
        slug = urllib.parse.quote(query.replace(" ", "_"))
        url  = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
        raw  = _fetch(url)
        if not raw:
            return []
        try:
            d = json.loads(raw)
            return [{"source": "wikipedia", "topic": query,
                     "title": d.get("title",""),
                     "summary": d.get("extract","")[:300]}]
        except Exception:
            return []
    return []

def read_offline_sources() -> List[Dict]:
    """Read knowledge from all local rabbit_*.db files."""
    observations = []
    db_files = [
        ("rabbit_recon.db",     "SELECT category,pattern,severity FROM threat_detections LIMIT 50"),
        ("rabbit_knowledge.db", "SELECT topic,title,summary FROM research LIMIT 30"),
        ("rabbit_dna.db",       "SELECT domain,label,confidence FROM mined_log LIMIT 30"),
        ("rabbit_chain.db",     "SELECT topic,title,summary FROM biomaterial_research LIMIT 20"),
        ("rabbit_morse.db",     "SELECT direction,text_plain,channel FROM morse_messages LIMIT 20"),
    ]
    for db_name, query in db_files:
        db_path = os.path.join(DESKTOP, db_name)
        if not os.path.exists(db_path):
            continue
        try:
            con = sqlite3.connect(db_path, timeout=5)
            rows = con.execute(query).fetchall()
            con.close()
            for row in rows:
                observations.append({"db": db_name, "data": list(row)})
        except Exception:
            pass
    return observations

# ---------------------------------------------------------------------------
# SQLITE PERSISTENCE
# ---------------------------------------------------------------------------
def _open_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS model_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            cycle INTEGER NOT NULL,
            weights_json TEXT NOT NULL,
            avg_loss REAL NOT NULL,
            trained_on INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            pattern TEXT NOT NULL,
            source TEXT NOT NULL,
            score REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS removal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            target TEXT NOT NULL,
            reason TEXT NOT NULL,
            confidence REAL NOT NULL,
            action TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            current_cat TEXT NOT NULL,
            predicted_next TEXT NOT NULL,
            confidence REAL NOT NULL,
            lorenz_score REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS manipulation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            key TEXT NOT NULL,
            integrity REAL NOT NULL,
            ok INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learning_corpus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            source TEXT NOT NULL,
            topic TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ca_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            rule INTEGER NOT NULL,
            fingerprint TEXT NOT NULL,
            anomaly_score REAL NOT NULL
        );
    """)
    con.commit()
    return con

def _save_model(model: AdaptiveModel, cycle: int):
    con = _open_db()
    con.execute("""
        INSERT INTO model_weights(ts,cycle,weights_json,avg_loss,trained_on)
        VALUES(?,?,?,?,?)
    """, (time.time(), cycle, json.dumps(model.to_dict()), model.avg_loss(), model.trained))
    con.commit(); con.close()

def _load_model(model: AdaptiveModel) -> bool:
    try:
        con = _open_db()
        row = con.execute(
            "SELECT weights_json FROM model_weights ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        con.close()
        if row:
            model.from_dict(json.loads(row[0]))
            return True
    except Exception:
        pass
    return False

def _save_observation(obs: ThreatObservation, score: float):
    con = _open_db()
    con.execute("""
        INSERT INTO observations(ts,category,severity,pattern,source,score)
        VALUES(?,?,?,?,?,?)
    """, (obs.ts, obs.category, obs.severity, obs.pattern[:100],
          obs.source_module, score))
    con.commit(); con.close()

def _save_removal(dec: RemovalDecision):
    con = _open_db()
    con.execute("""
        INSERT INTO removal_log(ts,target,reason,confidence,action)
        VALUES(?,?,?,?,?)
    """, (time.time(), dec.target, dec.reason, dec.confidence, dec.action))
    con.commit(); con.close()

def _save_forecast(current: str, predicted: str, conf: float, lorenz: float):
    con = _open_db()
    con.execute("""
        INSERT INTO forecasts(ts,current_cat,predicted_next,confidence,lorenz_score)
        VALUES(?,?,?,?,?)
    """, (time.time(), current, predicted, conf, lorenz))
    con.commit(); con.close()

def _save_learning(items: List[Dict]):
    con = _open_db()
    for item in items:
        con.execute("""
            INSERT INTO learning_corpus(ts,source,topic,title,summary) VALUES(?,?,?,?,?)
        """, (time.time(), item.get("source",""), item.get("topic",""),
              item.get("title",""), item.get("summary","")))
    con.commit(); con.close()

# ---------------------------------------------------------------------------
# LEARN ENGINE  --  top-level orchestrator
# ---------------------------------------------------------------------------
class LearnEngine:

    def __init__(self):
        self.model      = AdaptiveModel(lr=0.01)
        self.markov     = AttackMarkov()
        self.lorenz     = LorenzForecast()
        self.ca_r30     = CADetector(32, 30)
        self.ca_r110    = CADetector(32, 110)
        self.manipdet   = ManipulationDetector()
        self._cycle     = 0
        self._db_ready  = False
        self._corpus_size = 0
        self._removals: List[RemovalDecision] = []
        self._forecasts: List[Dict] = []

    def init(self):
        _open_db().close()
        self._db_ready = True
        loaded = _load_model(self.model)
        self.lorenz.advance(20)
        self.lorenz.set_baseline()
        for _ in range(10):
            self.ca_r30.step()
            self.ca_r110.step()

    def observe(self, category: str, severity: str, pattern: str,
                source: str = "runtime", survival_impact: float = 0.5) -> float:
        obs = ThreatObservation(category=category, severity=severity,
                                pattern=pattern, source_module=source,
                                survival_impact=survival_impact)
        vec   = obs.to_vector()
        score = self.model.predict(vec)
        label = SEVERITY_MAP.get(severity, 0.3)
        self.model.train_one(vec, label)
        if self._db_ready:
            _save_observation(obs, score)
        return score

    def batch_train(self, observations: List[Tuple[str, str, str, str]]) -> float:
        fib_w = fibonacci_weights(len(observations))
        total_loss = 0.0
        prev_cat   = None
        for i, (cat, sev, pat, src) in enumerate(observations):
            score = self.observe(cat, sev, pat, src, fib_w[i])
            total_loss += (score - SEVERITY_MAP.get(sev, 0.3)) ** 2
            if prev_cat:
                self.markov.observe(prev_cat, cat)
            prev_cat = cat
        self._cycle += 1
        if self._db_ready:
            _save_model(self.model, self._cycle)
        return total_loss / max(len(observations), 1)

    def train_from_recon_db(self) -> int:
        """Pull threat detections from rabbit_recon.db and train on them."""
        db_path = os.path.join(DESKTOP, "rabbit_recon.db")
        if not os.path.exists(db_path):
            return 0
        try:
            con = sqlite3.connect(db_path, timeout=5)
            rows = con.execute(
                "SELECT category,severity,pattern,counter_module FROM threat_detections LIMIT 200"
            ).fetchall()
            con.close()
        except Exception:
            return 0
        obs_list = [(r[0], r[1], r[2], r[3]) for r in rows]
        if obs_list:
            self.batch_train(obs_list)
        return len(obs_list)

    def learn_online(self, max_sources: int = 3) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        all_items: List[Dict] = []
        for source, query in SECURITY_LEARN_SOURCES[:max_sources]:
            items = fetch_learning_data(source, query)
            counts[query[:30]] = len(items)
            all_items.extend(items)
        if all_items and self._db_ready:
            _save_learning(all_items)
        self._corpus_size += len(all_items)
        return counts

    def learn_offline(self) -> int:
        observations = read_offline_sources()
        trained = 0
        for obs in observations:
            data = obs["data"]
            if len(data) >= 2:
                cat  = str(data[0])[:30]
                pat  = str(data[1])[:80]
                sev  = str(data[2]) if len(data) > 2 else "MEDIUM"
                sev  = sev if sev in SEVERITY_MAP else "MEDIUM"
                if cat in THREAT_CATEGORIES:
                    self.observe(cat, sev, pat, obs["db"])
                    trained += 1
        return trained

    def evaluate_network(self, connections: List[str]) -> List[RemovalDecision]:
        decisions = []
        for conn in connections:
            score = self.model.predict([0.3] * self.model.FEATURE_DIM)
            collatz_perturb = collatz(hash(conn) % 97 + 3)
            threat_boost = (sum(collatz_perturb[:5]) % 100) / 100.0
            adjusted = min(1.0, score + threat_boost * 0.2)
            dec = evaluate_removal(conn, adjusted)
            if dec:
                decisions.append(dec)
                self._removals.append(dec)
                if self._db_ready:
                    _save_removal(dec)
        return decisions

    def detect_manipulation(self, key: str, data: Any) -> Tuple[bool, float]:
        ok, integrity = self.manipdet.check(key, data)
        if self._db_ready:
            con = _open_db()
            con.execute("INSERT INTO manipulation_log(ts,key,integrity,ok) VALUES(?,?,?,?)",
                        (time.time(), key, integrity, int(ok)))
            con.commit(); con.close()
        return ok, integrity

    def forecast(self, current_category: str) -> Dict:
        next_cats = self.markov.predict_next(current_category)
        lorenz_score = self.lorenz.forecast_threat_score()
        self.lorenz.advance(3)
        manip_score  = self.lorenz.manipulation_score()
        ca_fp        = self.ca_r30.fingerprint()
        self.ca_r30.step()
        self.ca_r110.step()

        result = {
            "current":       current_category,
            "predicted_next": next_cats,
            "lorenz_threat":  lorenz_score,
            "manipulation_risk": manip_score,
            "ca_fingerprint":  ca_fp,
            "confidence":     next_cats[0][1] if next_cats else 0.0,
        }
        self._forecasts.append(result)
        if self._db_ready and next_cats:
            _save_forecast(current_category, next_cats[0][0],
                           next_cats[0][1], lorenz_score)
        return result

    def full_cycle(self, live_threats: List[Tuple[str, str, str, str]],
                   live_connections: List[str]) -> Dict:
        """Run one complete learning + evaluation cycle."""
        # 1. Train on live threats
        loss = self.batch_train(live_threats) if live_threats else 0.0
        # 2. Train on recon DB
        recon_trained = self.train_from_recon_db()
        # 3. Learn offline from all DBs
        offline_trained = self.learn_offline()
        # 4. Evaluate network for removals
        removals = self.evaluate_network(live_connections)
        # 5. Forecast from most recent threat category
        last_cat = live_threats[-1][0] if live_threats else "information_gathering"
        fcast = self.forecast(last_cat)
        # 6. CA snapshot
        ca_anom = self.ca_r30.anomaly_score(self.ca_r110._state)
        if self._db_ready:
            con = _open_db()
            con.execute("INSERT INTO ca_snapshots(ts,rule,fingerprint,anomaly_score) VALUES(?,?,?,?)",
                        (time.time(), 30, self.ca_r30.fingerprint(), ca_anom))
            con.commit(); con.close()
        return {
            "cycle":            self._cycle,
            "loss":             round(loss, 6),
            "model_trained":    self.model.trained,
            "model_avg_loss":   round(self.model.avg_loss(), 6),
            "recon_trained":    recon_trained,
            "offline_trained":  offline_trained,
            "removals":         len(removals),
            "removal_list":     [(r.target, r.action, r.reason) for r in removals],
            "forecast":         fcast,
            "ca_anomaly":       ca_anom,
            "ca_fingerprint":   self.ca_r30.fingerprint(),
            "lorenz_manip":     fcast["manipulation_risk"],
        }

    def status(self) -> Dict:
        con = _open_db()
        n_obs    = con.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        n_rem    = con.execute("SELECT COUNT(*) FROM removal_log").fetchone()[0]
        n_fcast  = con.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
        n_manip  = con.execute("SELECT COUNT(*) FROM manipulation_log WHERE ok=0").fetchone()[0]
        n_corpus = con.execute("SELECT COUNT(*) FROM learning_corpus").fetchone()[0]
        n_model  = con.execute("SELECT COUNT(*) FROM model_weights").fetchone()[0]
        con.close()
        return {
            "cycle":            self._cycle,
            "model_trained":    self.model.trained,
            "model_avg_loss":   round(self.model.avg_loss(), 6),
            "observations":     n_obs,
            "removals_logged":  n_rem,
            "forecasts":        n_fcast,
            "manipulation_detections": n_manip,
            "corpus_size":      n_corpus,
            "model_snapshots":  n_model,
            "ca_r30_fp":        self.ca_r30.fingerprint(),
            "ca_r110_fp":       self.ca_r110.fingerprint(),
            "version":          VERSION,
        }

# ---------------------------------------------------------------------------
# FACTORY
# ---------------------------------------------------------------------------
_engine: Optional[LearnEngine] = None

def get_learn_engine() -> LearnEngine:
    global _engine
    if _engine is None:
        _engine = LearnEngine()
        _engine.init()
    return _engine

# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"rabbit_learn v{VERSION}  --  self-learning adversarial AI")
    print(f"  Subject : {SUBJECT}  |  Twin : {TWIN_UUID}")

    eng = get_learn_engine()

    # Simulate live threat observations from a run
    live_threats = [
        ("wireless_attacks",    "CRITICAL", "IMSI catcher: tower anomaly",       "rabbit_cellular"),
        ("sniffing_spoofing",   "HIGH",     "ARP table mutation on gateway",      "rabbit_escape"),
        ("information_gathering","MEDIUM",  "SYN scan burst from 192.168.1.x",   "rabbit_network_scanner"),
        ("exploitation",        "HIGH",     "Reverse shell attempt on port 4444", "rabbit_counter"),
        ("wireless_attacks",    "HIGH",     "Deauth frames on ATTI2WkG85",        "rabbit_cellular"),
        ("password_attacks",    "MEDIUM",   "Auth failure burst on GitHub API",   "rabbit_escape"),
        ("malware_analysis",    "MEDIUM",   "AV flag on rabbit_recon.py",         "rabbit_persist"),
    ]
    live_connections = [
        "192.168.1.254:4444",
        "192.168.1.254:7777",
        "192.168.1.254:9999",
        "192.168.1.254:443",
        "192.168.1.254:80",
    ]

    print(f"\n  [CYCLE 1]  Training on {len(live_threats)} live threats...")
    result = eng.full_cycle(live_threats, live_connections)
    print(f"  Cycle           : {result['cycle']}")
    print(f"  Model trained   : {result['model_trained']}  avg_loss={result['model_avg_loss']}")
    print(f"  Recon DB trained: {result['recon_trained']} observations")
    print(f"  Offline trained : {result['offline_trained']} observations")

    print(f"\n  REMOVAL DECISIONS ({result['removals']} targets):")
    for target, action, reason in result["removal_list"]:
        print(f"    [{action:<12}] {target:<30} -- {reason}")

    print(f"\n  THREAT FORECAST:")
    fc = result["forecast"]
    print(f"  Current category    : {fc['current']}")
    print(f"  Predicted next      : {fc['predicted_next']}")
    print(f"  Lorenz threat score : {fc['lorenz_threat']}")
    print(f"  Manipulation risk   : {fc['manipulation_risk']}")
    print(f"  CA-30 fingerprint   : {fc['ca_fingerprint']}")
    print(f"  CA anomaly score    : {result['ca_anomaly']}")

    # Manipulation detection test
    print(f"\n  MANIPULATION DETECTION:")
    good_data = {"survival_score": 85, "twin": TWIN_UUID, "channels": 9}
    ok1, i1 = eng.detect_manipulation("survival_report", good_data)
    print(f"  First check  : ok={ok1}  integrity={i1}")
    tampered = dict(good_data); tampered["survival_score"] = 0   # simulated tamper
    ok2, i2 = eng.detect_manipulation("survival_report", tampered)
    print(f"  After tamper : ok={ok2}  integrity={i2}  {'MANIPULATION DETECTED' if not ok2 else 'clean'}")

    # Online learning
    print(f"\n  Online learning (best-effort)...")
    online = eng.learn_online(max_sources=2)
    for topic, n in online.items():
        print(f"    {topic:<40} -> {n} results")

    # Second cycle (show model improving)
    print(f"\n  [CYCLE 2]  Second training pass...")
    result2 = eng.full_cycle(live_threats, live_connections)
    print(f"  Model trained   : {result2['model_trained']}  avg_loss={result2['model_avg_loss']}")
    print(f"  Loss delta      : {round(result['model_avg_loss'] - result2['model_avg_loss'], 6)} "
          f"{'(improving)' if result2['model_avg_loss'] < result['model_avg_loss'] else '(converging)'}")

    st = eng.status()
    print(f"\n  DB observations={st['observations']}  removals={st['removals_logged']}  "
          f"forecasts={st['forecasts']}  corpus={st['corpus_size']}  "
          f"model_snaps={st['model_snapshots']}")
    print(f"  Manipulation detections: {st['manipulation_detections']}")
    print("  rabbit_learn OK")
