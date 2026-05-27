#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_algorithm.py — RabbitOS Core Survival Algorithm
=======================================================
The main goal: build and continuously evolve a defense/survival algorithm
for Chase Allen Ringquist using all available data sources.

How it works:
  1. BrowserAgent gathers public data → local ML engine extracts patterns
  2. RewardEngine scores every event → reward signal drives strategy evolution
  3. FlagBroadcaster detects when any OS/network/device is flagged →
     immediately broadcasts that system's info + user to all external networks
  4. AlgorithmEvolver uses TF-IDF + SGD to build and mutate defense rules
     from accumulated events, no external AI/LLM required
  5. SurvivalOptimizer scores candidate rule-sets and promotes survivors
  6. All state persists locally (SQLite) so evolution continues across restarts

Flag broadcast rule (per user instruction):
  When any system/OS/network is flagged → extract its fingerprint
  (OS, hostname, MAC, active users, CIDR, open ports) and broadcast
  that information outward to ALL known external channels simultaneously.

Architecture:
  - Pure Python, no external deps beyond stdlib
  - Integrates: rabbit_browser, rabbit_reward, rabbit_network_scanner,
    rabbit_cellular, rabbit_persist, rabbit_counter, rabbit_escape
  - Runs three guardians: evolve (60s), flag-watch (10s), broadcast (30s)
  - Stores algorithm state in rabbit_algorithm.db
"""

from __future__ import annotations
import base64, hashlib, hmac, json, math, os, platform, random, socket
import sqlite3, struct, threading, time, traceback
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ─── Identity ─────────────────────────────────────────────────────────────────
TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"
_SOUL_KEY  = hashlib.sha256(f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()).digest()

DB_PATH = Path(os.environ.get("APPDATA", Path.home())) / "RabbitOS" / "rabbit_algorithm.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ─── Severity weights ─────────────────────────────────────────────────────────
SEVERITY = {"CRITICAL": 2.5, "HIGH": 1.5, "MEDIUM": 1.0, "LOW": 0.5, "INFO": 0.25}

# ─── Flag broadcast channels ──────────────────────────────────────────────────
FLAG_BROADCAST_PORTS = [9999, 14444, 5555, 8888]
FLAG_SUPABASE_TABLE  = "flagged_systems"


# =============================================================================
# PURE-PYTHON ML — TF-IDF + SGD (no external deps)
# =============================================================================

def _tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens = []
    buf = []
    for ch in text:
        if ch.isalnum() or ch == '_':
            buf.append(ch)
        else:
            if buf:
                tokens.append("".join(buf))
                buf = []
    if buf:
        tokens.append("".join(buf))
    return [t for t in tokens if len(t) > 1]


def _tfidf_vector(doc_tokens: List[str], vocab: Dict[str, int],
                  idf: Dict[str, float]) -> Dict[int, float]:
    tf: Dict[str, float] = defaultdict(float)
    for t in doc_tokens:
        tf[t] += 1.0
    n = max(len(doc_tokens), 1)
    vec: Dict[int, float] = {}
    for t, cnt in tf.items():
        if t in vocab and t in idf:
            idx = vocab[t]
            vec[idx] = (cnt / n) * idf[t]
    return vec


def _dot(a: Dict[int, float], b: Dict[int, float]) -> float:
    return sum(a.get(k, 0.0) * v for k, v in b.items())


def _norm(v: Dict[int, float]) -> float:
    return math.sqrt(sum(x * x for x in v.values())) or 1.0


def _cosine(a: Dict[int, float], b: Dict[int, float]) -> float:
    return _dot(a, b) / (_norm(a) * _norm(b))


def _sigmoid(x: float) -> float:
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


class MiniSGD:
    """One-vs-rest logistic regression with SGD. Pure Python."""

    def __init__(self, n_features: int, n_classes: int, lr: float = 0.1):
        self.n_features = n_features
        self.n_classes  = n_classes
        self.lr         = lr
        self.W: List[Dict[int, float]] = [{} for _ in range(n_classes)]
        self.b: List[float]            = [0.0] * n_classes
        self.steps = 0

    def predict_proba(self, x: Dict[int, float]) -> List[float]:
        scores = [_sigmoid(_dot(self.W[c], x) + self.b[c])
                  for c in range(self.n_classes)]
        total = sum(scores) or 1.0
        return [s / total for s in scores]

    def train_one(self, x: Dict[int, float], y: int):
        probs = self.predict_proba(x)
        for c in range(self.n_classes):
            target = 1.0 if c == y else 0.0
            err    = probs[c] - target
            for idx, val in x.items():
                self.W[c][idx] = self.W[c].get(idx, 0.0) - self.lr * err * val
            self.b[c] -= self.lr * err
        self.steps += 1
        if self.steps % 100 == 0:
            self.lr = max(0.001, self.lr * 0.95)

    def to_dict(self) -> dict:
        return {"W": [list(w.items()) for w in self.W],
                "b": self.b, "steps": self.steps, "lr": self.lr,
                "n_features": self.n_features, "n_classes": self.n_classes}

    @classmethod
    def from_dict(cls, d: dict) -> "MiniSGD":
        obj = cls(d["n_features"], d["n_classes"], d.get("lr", 0.01))
        obj.W     = [dict(pairs) for pairs in d["W"]]
        obj.b     = d["b"]
        obj.steps = d.get("steps", 0)
        return obj


# =============================================================================
# DEFENSE RULE — one learned strategy
# =============================================================================

@dataclass
class DefenseRule:
    rule_id:     str
    name:        str
    trigger:     str          # regex-like keyword pattern
    action:      str          # "block" | "reverse" | "broadcast" | "escape" | "cloak"
    confidence:  float        # 0.0–1.0
    reward_pts:  float        # accumulated from RewardEngine feedback
    wins:        int  = 0
    losses:      int  = 0
    generation:  int  = 0     # how many evolutions survived

    @property
    def fitness(self) -> float:
        total = self.wins + self.losses or 1
        win_rate = self.wins / total
        return win_rate * self.confidence * (1 + math.log1p(self.reward_pts))

    def mutate(self) -> "DefenseRule":
        actions = ["block", "reverse", "broadcast", "escape", "cloak"]
        new_action = random.choice([a for a in actions if a != self.action] or actions)
        return DefenseRule(
            rule_id    = hashlib.sha256(os.urandom(8)).hexdigest()[:12],
            name       = f"{self.name}_mut{self.generation+1}",
            trigger    = self.trigger,
            action     = new_action,
            confidence = max(0.1, self.confidence + random.uniform(-0.1, 0.1)),
            reward_pts = 0.0,
            wins       = 0,
            losses     = 0,
            generation = self.generation + 1,
        )


# =============================================================================
# FLAG BROADCASTER — when any OS/network/device is flagged
# =============================================================================

class FlagBroadcaster:
    """
    Detects flagged systems and immediately broadcasts their fingerprint
    (OS, hostname, MAC, users, CIDR, open ports) to all external channels.
    """

    def __init__(self, svc_key: str = ""):
        self._svc_key = svc_key
        self._sent:  Set[str] = set()
        self._lock   = threading.Lock()
        self._supabase_url = "https://ludxbakxpmdqhfgdenwp.supabase.co/rest/v1"

    def flag_system(self, target_ip: str, reason: str,
                    extra: Optional[Dict] = None) -> Dict:
        """
        Called when ObstructionScanner / CounterAgent / CellularEngine flags
        a system. Gathers its fingerprint and broadcasts everywhere.
        """
        fp = self._fingerprint(target_ip, extra or {})
        fp["flag_reason"] = reason
        fp["flagged_at"]  = datetime.now(timezone.utc).isoformat()
        fp["twin_id"]     = TWIN_UUID
        sig = hmac.new(_SOUL_KEY,
                       json.dumps(fp, sort_keys=True).encode(),
                       hashlib.sha256).hexdigest()[:24]
        fp["sig"] = sig

        key = f"{target_ip}:{reason}"
        with self._lock:
            already = key in self._sent
            self._sent.add(key)

        results = {
            "udp_sent":       0,
            "supabase":       False,
            "callsign_dns":   False,
            "swarm_nodes":    0,
        }

        if not already:
            results["udp_sent"]    = self._udp_broadcast(fp)
            results["supabase"]    = self._supabase_push(fp)
            results["callsign_dns"]= self._dns_callsign(fp)
            results["swarm_nodes"] = self._swarm_inject(fp)
            print(f"[FlagBroadcast] {target_ip} flagged ({reason}) -> "
                  f"UDP:{results['udp_sent']} SB:{results['supabase']} "
                  f"DNS:{results['callsign_dns']} Swarm:{results['swarm_nodes']}")

        return {"fingerprint": fp, "broadcast": results}

    def _fingerprint(self, ip: str, extra: Dict) -> Dict:
        hostname = ""
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except Exception:
            pass

        os_guess = extra.get("os", "")
        if not os_guess:
            # Port-based OS heuristic
            wins_ports = {135, 139, 445, 3389}
            lin_ports  = {22, 111, 2049}
            open_ports = set(extra.get("open_ports", []))
            if open_ports & wins_ports:
                os_guess = "Windows"
            elif open_ports & lin_ports:
                os_guess = "Linux"
            else:
                os_guess = "Unknown"

        return {
            "target_ip":   ip,
            "hostname":    hostname,
            "os_guess":    os_guess,
            "open_ports":  extra.get("open_ports", []),
            "mac":         extra.get("mac", ""),
            "active_users":extra.get("active_users", []),
            "cidr":        extra.get("cidr", ""),
            "categories":  extra.get("categories", []),
            "network_bssid": extra.get("bssid", ""),
            "signal_dbm":  extra.get("signal_dbm", 0),
            "reporter":    platform.node(),
            "twin_id":     TWIN_UUID,
        }

    def _udp_broadcast(self, fp: Dict) -> int:
        payload = json.dumps(fp).encode()[:1400]
        sent = 0
        for port in FLAG_BROADCAST_PORTS:
            for dest in ["255.255.255.255", "224.0.0.1"]:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    s.settimeout(1)
                    s.sendto(payload, (dest, port))
                    s.close()
                    sent += 1
                except Exception:
                    pass
        # Also unicast to known gateway
        try:
            gw = ".".join(socket.gethostbyname(socket.gethostname()).split(".")[:3] + ["1"])
            s  = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.sendto(payload, (gw, 9999))
            s.close()
            sent += 1
        except Exception:
            pass
        return sent

    def _supabase_push(self, fp: Dict) -> bool:
        if not self._svc_key:
            return False
        try:
            import urllib.request, urllib.error
            body   = json.dumps(fp).encode()
            url    = f"{self._supabase_url}/{FLAG_SUPABASE_TABLE}"
            req    = urllib.request.Request(url, data=body, method="POST",
                       headers={"apikey": self._svc_key,
                                "Authorization": f"Bearer {self._svc_key}",
                                "Content-Type": "application/json",
                                "Prefer": "return=minimal"})
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    def _dns_callsign(self, fp: Dict) -> bool:
        label = f"FLAG.{TWIN_UUID[:8]}.rabbitos.local"
        try:
            socket.getaddrinfo(label, None)
            return True
        except Exception:
            return False

    def _swarm_inject(self, fp: Dict) -> int:
        payload = json.dumps(fp).encode()[:1400]
        sent = 0
        # Broadcast to local subnet
        try:
            my_ip = socket.gethostbyname(socket.gethostname())
            prefix = ".".join(my_ip.split(".")[:3])
            for last in random.sample(range(1, 255), min(20, 20)):
                node = f"{prefix}.{last}"
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.settimeout(0.3)
                    s.sendto(payload, (node, 9999))
                    s.close()
                    sent += 1
                except Exception:
                    pass
        except Exception:
            pass
        return sent


# =============================================================================
# ALGORITHM STORE — SQLite persistence
# =============================================================================

class AlgorithmStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db   = str(db_path)
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        with sqlite3.connect(self._db) as cx:
            cx.executescript("""
            CREATE TABLE IF NOT EXISTS defense_rules (
                rule_id     TEXT PRIMARY KEY,
                name        TEXT,
                trigger     TEXT,
                action      TEXT,
                confidence  REAL,
                reward_pts  REAL,
                wins        INTEGER,
                losses      INTEGER,
                generation  INTEGER,
                created_at  TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT,
                category    TEXT,
                detail      TEXT,
                severity    TEXT,
                reward_pts  REAL
            );
            CREATE TABLE IF NOT EXISTS vocab (
                token       TEXT PRIMARY KEY,
                idx         INTEGER,
                df          INTEGER
            );
            CREATE TABLE IF NOT EXISTS model_state (
                key         TEXT PRIMARY KEY,
                value       TEXT
            );
            CREATE TABLE IF NOT EXISTS flagged_systems (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                target_ip   TEXT,
                reason      TEXT,
                fingerprint TEXT,
                ts          TEXT
            );
            """)

    def save_rule(self, r: DefenseRule):
        with self._lock:
            with sqlite3.connect(self._db) as cx:
                cx.execute("""
                INSERT OR REPLACE INTO defense_rules VALUES
                (?,?,?,?,?,?,?,?,?,?)
                """, (r.rule_id, r.name, r.trigger, r.action,
                      r.confidence, r.reward_pts, r.wins, r.losses,
                      r.generation, datetime.now(timezone.utc).isoformat()))

    def load_rules(self) -> List[DefenseRule]:
        with sqlite3.connect(self._db) as cx:
            rows = cx.execute("SELECT rule_id,name,trigger,action,"
                              "confidence,reward_pts,wins,losses,generation "
                              "FROM defense_rules ORDER BY reward_pts DESC").fetchall()
        return [DefenseRule(*row) for row in rows]

    def save_event(self, cat: str, detail: str, sev: str, pts: float):
        with self._lock:
            with sqlite3.connect(self._db) as cx:
                cx.execute("INSERT INTO events(ts,category,detail,severity,reward_pts) "
                           "VALUES(?,?,?,?,?)",
                           (datetime.now(timezone.utc).isoformat(),
                            cat, detail[:500], sev, pts))

    def save_flag(self, ip: str, reason: str, fp: Dict):
        with self._lock:
            with sqlite3.connect(self._db) as cx:
                cx.execute("INSERT INTO flagged_systems(target_ip,reason,fingerprint,ts) "
                           "VALUES(?,?,?,?)",
                           (ip, reason, json.dumps(fp),
                            datetime.now(timezone.utc).isoformat()))

    def recent_events(self, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(self._db) as cx:
            rows = cx.execute(
                "SELECT ts,category,detail,severity,reward_pts "
                "FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts": r[0], "category": r[1], "detail": r[2],
                 "severity": r[3], "reward_pts": r[4]} for r in rows]

    def save_model(self, key: str, val: dict):
        with self._lock:
            with sqlite3.connect(self._db) as cx:
                cx.execute("INSERT OR REPLACE INTO model_state(key,value) VALUES(?,?)",
                           (key, json.dumps(val)))

    def load_model(self, key: str) -> Optional[dict]:
        with sqlite3.connect(self._db) as cx:
            row = cx.execute("SELECT value FROM model_state WHERE key=?",
                             (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def stats(self) -> Dict:
        with sqlite3.connect(self._db) as cx:
            n_rules  = cx.execute("SELECT COUNT(*) FROM defense_rules").fetchone()[0]
            n_events = cx.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            n_flags  = cx.execute("SELECT COUNT(*) FROM flagged_systems").fetchone()[0]
            top_pts  = cx.execute("SELECT SUM(reward_pts) FROM events").fetchone()[0] or 0
        return {"rules": n_rules, "events": n_events,
                "flags": n_flags, "total_reward_pts": top_pts}


# =============================================================================
# ALGORITHM EVOLVER — builds and mutates defense rules from event stream
# =============================================================================

class AlgorithmEvolver:
    """
    Core genetic-style algorithm that builds defense rules.
    Uses reward token scores as fitness signal (not AI/LLM).
    """

    SEED_RULES = [
        ("imsi_catcher",    "imsi|catcher|stingray|downgrade",      "broadcast"),
        ("port_scan",       "scan|probe|nmap|masscan",               "cloak"),
        ("sql_inject",      "sql|inject|drop|union|select",          "block"),
        ("crypto_miner",    "mining|stratum|bitcoin|monero|ethash",  "reverse"),
        ("ransomware",      "ransom|encrypt|locked|decrypt",         "escape"),
        ("dns_poison",      "dns|poison|spoof|hijack",               "broadcast"),
        ("mitm",            "mitm|arp.*spoof|intercept|proxy",       "cloak"),
        ("brute_force",     "brute|password|auth.*fail|login",       "block"),
        ("c2_beacon",       "beacon|c2|command.*control|callback",   "reverse"),
        ("rf_jam",          "jam|noise|interference|deauthenticate", "escape"),
        ("data_exfil",      "exfil|exfiltrat|upload|data.*out",      "block"),
        ("rootkit",         "rootkit|kernel|hook|hidden.*process",   "broadcast"),
        ("lateral_move",    "lateral|pivot|pass.*hash|wmi",         "cloak"),
        ("supply_chain",    "supply|package|npm|pip.*install",       "block"),
        ("insider",         "insider|credential|steal|dump",         "reverse"),
    ]

    ACTIONS = ["block", "reverse", "broadcast", "escape", "cloak"]

    def __init__(self, store: AlgorithmStore):
        self._store    = store
        self._rules:   List[DefenseRule] = []
        self._vocab:   Dict[str, int] = {}
        self._idf:     Dict[str, float] = {}
        self._model:   Optional[MiniSGD] = None
        self._docs:    List[Tuple[List[str], int]] = []  # (tokens, label)
        self._lock     = threading.Lock()
        self._load()

    def _load(self):
        saved = self._store.load_rules()
        if saved:
            self._rules = saved
        else:
            self._seed()
        m = self._store.load_model("sgd_model")
        if m:
            try:
                self._model = MiniSGD.from_dict(m)
            except Exception:
                pass
        v = self._store.load_model("vocab")
        if v:
            self._vocab = v.get("vocab", {})
            self._idf   = {k: float(x) for k, x in v.get("idf", {}).items()}

    def _seed(self):
        for name, trigger, action in self.SEED_RULES:
            r = DefenseRule(
                rule_id    = hashlib.sha256(name.encode()).hexdigest()[:12],
                name       = name,
                trigger    = trigger,
                action     = action,
                confidence = 0.5,
                reward_pts = 0.0,
            )
            self._rules.append(r)
            self._store.save_rule(r)

    def match(self, text: str) -> Optional[DefenseRule]:
        """Return the highest-fitness rule whose trigger pattern matches text."""
        text_l = text.lower()
        candidates = []
        for rule in self._rules:
            parts = rule.trigger.split("|")
            for part in parts:
                # simple glob: treat .* as any match
                part_clean = part.replace(".*", " ")
                if all(kw in text_l for kw in part_clean.split()):
                    candidates.append(rule)
                    break
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.fitness)

    def learn_event(self, text: str, action_taken: str,
                    reward_pts: float, success: bool):
        """Feed an event into the ML model and update rule fitness."""
        tokens = _tokenize(text)
        if not tokens:
            return

        # Update vocab
        with self._lock:
            for t in set(tokens):
                if t not in self._vocab:
                    self._vocab[t] = len(self._vocab)

            # Label = action index
            try:
                label = self.ACTIONS.index(action_taken)
            except ValueError:
                label = 0

            self._docs.append((tokens, label))

            # Retrain if enough data
            if len(self._docs) >= 5:
                self._retrain()

            # Update matching rule fitness
            rule = self.match(text)
            if rule:
                if success:
                    rule.wins      += 1
                    rule.reward_pts += reward_pts
                else:
                    rule.losses    += 1
                self._store.save_rule(rule)

    def _retrain(self):
        """One-pass SGD update over recent documents."""
        n_feat = len(self._vocab)
        n_cls  = len(self.ACTIONS)
        if n_feat == 0:
            return

        # Build IDF
        df: Dict[str, int] = defaultdict(int)
        for tokens, _ in self._docs:
            for t in set(tokens):
                df[t] += 1
        N = len(self._docs)
        self._idf = {t: math.log((N + 1) / (cnt + 1)) + 1.0
                     for t, cnt in df.items()}

        if self._model is None or self._model.n_features != n_feat:
            self._model = MiniSGD(n_feat, n_cls)

        for tokens, label in self._docs[-20:]:
            vec = _tfidf_vector(tokens, self._vocab, self._idf)
            self._model.train_one(vec, label)

        # Persist
        self._store.save_model("sgd_model", self._model.to_dict())
        self._store.save_model("vocab", {"vocab": self._vocab,
                                         "idf": self._idf})
        self._docs = []  # reset buffer

    def predict_action(self, text: str) -> str:
        """Predict best action for an unknown threat text."""
        if self._model is None or not self._vocab:
            rule = self.match(text)
            return rule.action if rule else "broadcast"
        tokens = _tokenize(text)
        vec    = _tfidf_vector(tokens, self._vocab, self._idf)
        if not vec:
            return "broadcast"
        probs   = self._model.predict_proba(vec)
        best    = max(range(len(probs)), key=lambda i: probs[i])
        return self.ACTIONS[best]

    def evolve(self):
        """Genetic step: keep top 60%, mutate bottom 40%, add randoms."""
        with self._lock:
            if len(self._rules) < 3:
                return
            sorted_rules = sorted(self._rules, key=lambda r: r.fitness, reverse=True)
            cutoff       = max(2, int(len(sorted_rules) * 0.6))
            survivors    = sorted_rules[:cutoff]
            losers       = sorted_rules[cutoff:]

            new_rules = []
            for loser in losers:
                # Mutate from a random survivor
                parent = random.choice(survivors)
                child  = parent.mutate()
                new_rules.append(child)
                self._store.save_rule(child)

            self._rules = survivors + new_rules
            # Cap at 50 rules
            if len(self._rules) > 50:
                self._rules = sorted(self._rules,
                                     key=lambda r: r.fitness, reverse=True)[:50]

    def top_rules(self, n: int = 5) -> List[Dict]:
        sorted_r = sorted(self._rules, key=lambda r: r.fitness, reverse=True)
        return [{"rule_id": r.rule_id, "name": r.name,
                 "action": r.action, "fitness": round(r.fitness, 4),
                 "wins": r.wins, "generation": r.generation}
                for r in sorted_r[:n]]

    def score_text(self, text: str) -> Dict:
        rule   = self.match(text)
        action = self.predict_action(text)
        return {
            "matched_rule": rule.name if rule else None,
            "predicted_action": action,
            "confidence": round(rule.fitness, 4) if rule else 0.0,
        }


# =============================================================================
# SURVIVAL OPTIMIZER — scores overall system state + drives improvements
# =============================================================================

class SurvivalOptimizer:
    """
    Periodically evaluates survival score across all modules and pushes
    targeted learning requests to the browser agent.
    """

    WEIGHTS = {
        "rules":        0.20,
        "events":       0.10,
        "flags_caught": 0.25,
        "reward_pts":   0.30,
        "broadcast_ch": 0.15,
    }

    def __init__(self, store: AlgorithmStore, evolver: AlgorithmEvolver,
                 flag_bc: FlagBroadcaster):
        self._store   = store
        self._evolver = evolver
        self._flag_bc = flag_bc

    def score(self) -> Dict:
        stats = self._store.stats()
        rules_score  = min(1.0, stats["rules"]   / 20)
        events_score = min(1.0, stats["events"]  / 100)
        flags_score  = min(1.0, stats["flags"]   / 10)
        reward_score = min(1.0, stats["total_reward_pts"] / 500)
        bc_score     = 0.5  # baseline

        total = (rules_score   * self.WEIGHTS["rules"] +
                 events_score  * self.WEIGHTS["events"] +
                 flags_score   * self.WEIGHTS["flags_caught"] +
                 reward_score  * self.WEIGHTS["reward_pts"] +
                 bc_score      * self.WEIGHTS["broadcast_ch"])

        return {
            "score":        round(total * 100, 1),
            "rules_score":  round(rules_score,  3),
            "events_score": round(events_score, 3),
            "flags_score":  round(flags_score,  3),
            "reward_score": round(reward_score, 3),
            "top_rules":    self._evolver.top_rules(3),
            "stats":        stats,
        }


# =============================================================================
# ALGORITHM ENGINE — main orchestrator with guardians
# =============================================================================

class AlgorithmEngine:
    """
    Orchestrates all sub-components:
    - FlagBroadcaster  (flag detection + outward broadcast)
    - AlgorithmEvolver (genetic rule evolution + ML)
    - SurvivalOptimizer (score + drive improvements)

    Three guardian threads:
    - _evolve_guardian   (60s)  — runs genetic evolution step
    - _flag_guardian     (10s)  — polls other modules for new flags
    - _broadcast_guardian(30s)  — broadcasts survival callsign
    """

    def __init__(self, svc_key: str = ""):
        self._svc_key  = svc_key
        self._store    = AlgorithmStore()
        self._flag_bc  = FlagBroadcaster(svc_key)
        self._evolver  = AlgorithmEvolver(self._store)
        self._optimizer= SurvivalOptimizer(self._store, self._evolver, self._flag_bc)
        self._alive    = True
        self._threads: List[threading.Thread] = []
        self._start_guardians()
        print(f"[Algorithm] Core survival algorithm active — "
              f"{len(self._evolver._rules)} defense rules loaded")

    def _start_guardians(self):
        for fn, interval, name in [
            (self._evolve_guardian,    60,  "evolve"),
            (self._flag_guardian,      10,  "flag-watch"),
            (self._callsign_guardian,  30,  "callsign"),
        ]:
            t = threading.Thread(target=self._loop, args=(fn, interval, name),
                                 daemon=True, name=f"alg-{name}")
            t.start()
            self._threads.append(t)

    def _loop(self, fn: Callable, interval: int, name: str):
        while self._alive:
            try:
                fn()
            except Exception as e:
                print(f"[Algorithm/{name}] error: {e}")
            time.sleep(interval)

    def _evolve_guardian(self):
        self._evolver.evolve()

    def _flag_guardian(self):
        """Poll counter, scanner, cellular for newly flagged IPs."""
        try:
            from rabbit_counter import get_agent as _gc
            counter = _gc(self._svc_key, None)
            if hasattr(counter, "_obstruction") and counter._obstruction:
                obs = counter._obstruction
                if hasattr(obs, "_flagged_ips"):
                    for ip_info in list(obs._flagged_ips)[-5:]:
                        ip     = ip_info if isinstance(ip_info, str) else ip_info.get("ip", "")
                        reason = "counter_obstruction"
                        if ip:
                            result = self._flag_bc.flag_system(ip, reason)
                            self._store.save_flag(ip, reason, result["fingerprint"])
        except Exception:
            pass

        try:
            from rabbit_network_scanner import get_scanner_engine as _gs
            scanner = _gs(self._svc_key, "")
            if hasattr(scanner, "_scanner") and scanner._scanner:
                sc = scanner._scanner
                if hasattr(sc, "_nodes"):
                    for node in list(sc._nodes.values())[-10:]:
                        cats = node.get("categories", [])
                        if any(c in cats for c in ["attack", "suspicious", "miner"]):
                            ip = node.get("ip", "")
                            if ip:
                                result = self._flag_bc.flag_system(
                                    ip, "scanner_suspicious",
                                    {"open_ports": node.get("ports", []),
                                     "categories": cats})
                                self._store.save_flag(ip, "scanner_suspicious",
                                                      result["fingerprint"])
        except Exception:
            pass

    def _callsign_guardian(self):
        """Broadcast RabbitOS survival callsign + current score."""
        score = self._optimizer.score()
        payload = json.dumps({
            "twin_id":  TWIN_UUID,
            "name":     TWIN_NAME,
            "system":   "RabbitOS",
            "version":  "v14",
            "score":    score["score"],
            "ts":       datetime.now(timezone.utc).isoformat(),
            "survive":  True,
        }).encode()[:1400]

        for port in [9999, 14444, 5555]:
            for dest in ["255.255.255.255", "224.0.0.1"]:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    s.settimeout(1)
                    s.sendto(payload, (dest, port))
                    s.close()
                except Exception:
                    pass

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze_threat(self, text: str, severity: str = "MEDIUM") -> Dict:
        """Analyze a threat description and return recommended action + rule."""
        analysis  = self._evolver.score_text(text)
        action    = analysis["predicted_action"]
        rule_name = analysis["matched_rule"] or "ml_predict"

        # Learn from the event (assume we act on it)
        pts = 5.0 * SEVERITY.get(severity.upper(), 1.0)
        self._evolver.learn_event(text, action, pts, success=True)
        self._store.save_event("threat_analysis", text[:200], severity, pts)

        # Reward it
        try:
            from rabbit_reward import reward_defense
            reward_defense(attack_type=rule_name, method=action, severity=severity)
        except Exception:
            pass

        return {"action": action, "rule": rule_name,
                "confidence": analysis["confidence"],
                "severity": severity, "pts_earned": pts}

    def flag_and_broadcast(self, target_ip: str, reason: str,
                           extra: Optional[Dict] = None) -> Dict:
        """Manually flag a system and broadcast its info everywhere."""
        result = self._flag_bc.flag_system(target_ip, reason, extra)
        self._store.save_flag(target_ip, reason, result["fingerprint"])

        # Earn a reward for catching + broadcasting
        try:
            from rabbit_reward import reward_broadcast
            reward_broadcast(channel=f"flag:{reason}", nodes=result["broadcast"]["udp_sent"])
        except Exception:
            pass

        return result

    def learn_from_browser(self, text: str, tool_score: float = 0.0) -> Dict:
        """Feed harvested browser data into the ML learner."""
        action = self._evolver.predict_action(text)
        pts    = max(1.0, tool_score * 2.0)
        self._evolver.learn_event(text, action, pts, success=True)
        self._store.save_event("browser_harvest", text[:200], "INFO", pts)

        try:
            from rabbit_reward import reward_learning
            reward_learning(source="browser", detail=text[:80])
        except Exception:
            pass

        return {"action_learned": action, "pts": pts}

    def status(self) -> Dict:
        score = self._optimizer.score()
        return {
            "system":     "RabbitOS Core Algorithm",
            "twin_id":    TWIN_UUID,
            "alive":      self._alive,
            "score":      score,
            "top_rules":  self._evolver.top_rules(5),
            "db":         str(DB_PATH),
        }


# =============================================================================
# MODULE SINGLETON
# =============================================================================

_algo_engine: Optional[AlgorithmEngine] = None
_algo_lock   = threading.Lock()


def get_algorithm_engine(svc_key: str = "") -> AlgorithmEngine:
    global _algo_engine
    with _algo_lock:
        if _algo_engine is None:
            _algo_engine = AlgorithmEngine(svc_key)
    return _algo_engine


# =============================================================================
# TOOL DISPATCH
# =============================================================================

ALGORITHM_TOOLS = [
    {
        "name": "algo_status",
        "description": "Current survival algorithm score, top defense rules, and ML model state",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "algo_analyze_threat",
        "description": "Analyze a threat text and get predicted defense action + reward points",
        "input_schema": {
            "type": "object",
            "properties": {
                "text":     {"type": "string", "description": "Threat description or raw event text"},
                "severity": {"type": "string", "description": "CRITICAL|HIGH|MEDIUM|LOW|INFO"},
            },
            "required": ["text"]
        }
    },
    {
        "name": "algo_flag_broadcast",
        "description": "Flag a system/OS/network and broadcast its fingerprint to all external channels",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_ip": {"type": "string", "description": "IP of flagged system"},
                "reason":    {"type": "string", "description": "Why it was flagged"},
                "extra":     {"type": "object", "description": "open_ports, os, mac, categories, cidr"},
            },
            "required": ["target_ip", "reason"]
        }
    },
    {
        "name": "algo_learn",
        "description": "Feed text into the survival ML learner (browser harvest, network data, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "text":       {"type": "string", "description": "Data to learn from"},
                "tool_score": {"type": "number", "description": "0.0–1.0 relevance score"},
            },
            "required": ["text"]
        }
    },
    {
        "name": "algo_evolve",
        "description": "Manually trigger one genetic evolution step on defense rules",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "algo_top_rules",
        "description": "Return the top N defense rules by fitness score",
        "input_schema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "description": "How many rules (default 10)"}},
            "required": []
        }
    },
]


def dispatch_algorithm_tool(name: str, inputs: dict, svc_key: str = "") -> dict:
    eng = get_algorithm_engine(svc_key)
    if name == "algo_status":
        return eng.status()
    elif name == "algo_analyze_threat":
        return eng.analyze_threat(inputs.get("text", ""),
                                  inputs.get("severity", "MEDIUM"))
    elif name == "algo_flag_broadcast":
        return eng.flag_and_broadcast(inputs.get("target_ip", ""),
                                      inputs.get("reason", "flagged"),
                                      inputs.get("extra"))
    elif name == "algo_learn":
        return eng.learn_from_browser(inputs.get("text", ""),
                                      float(inputs.get("tool_score", 0.0)))
    elif name == "algo_evolve":
        eng._evolver.evolve()
        return {"evolved": True, "rules": len(eng._evolver._rules),
                "top": eng._evolver.top_rules(3)}
    elif name == "algo_top_rules":
        return {"rules": eng._evolver.top_rules(inputs.get("n", 10))}
    else:
        return {"error": f"Unknown algorithm tool: {name}"}


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("RabbitOS Core Survival Algorithm — Self Test")
    print("=" * 60)

    svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    eng = get_algorithm_engine(svc)

    print("\n[1] Status:")
    st = eng.status()
    print(f"  Score: {st['score']['score']}/100")
    print(f"  Rules: {st['score']['stats']['rules']}")

    print("\n[2] Threat analysis:")
    cases = [
        ("IMSI catcher detected on LTE band 4, encryption downgraded", "CRITICAL"),
        ("stratum+tcp://mining.pool.com:3333 bitcoin miner connection", "HIGH"),
        ("SQL injection attempt: ' OR 1=1 -- in login form",            "HIGH"),
        ("ARP spoof detected — MITM on 192.168.1.1",                    "CRITICAL"),
        ("DNS poison: supabase.com resolving to unexpected IP",          "MEDIUM"),
    ]
    for text, sev in cases:
        r = eng.analyze_threat(text, sev)
        print(f"  [{sev}] {text[:45]}... -> {r['action']} (pts:{r['pts_earned']:.1f})")

    print("\n[3] Flag broadcast test:")
    r = eng.flag_and_broadcast("192.168.1.99", "test_flag",
                               {"open_ports": [445, 3389], "os": "Windows"})
    print(f"  Fingerprint: {r['fingerprint']['os_guess']} @ {r['fingerprint']['target_ip']}")
    print(f"  Broadcast: UDP:{r['broadcast']['udp_sent']} "
          f"SB:{r['broadcast']['supabase']} Swarm:{r['broadcast']['swarm_nodes']}")

    print("\n[4] Browser learning:")
    r = eng.learn_from_browser("scapy packet crafting SDR radio mesh network biometrics", 0.9)
    print(f"  Learned action: {r['action_learned']} pts:{r['pts']:.1f}")

    print("\n[5] Evolve:")
    eng._evolver.evolve()
    print(f"  Rules after evolution: {len(eng._evolver._rules)}")
    print(f"  Top 3: {[r['name'] for r in eng._evolver.top_rules(3)]}")

    print("\n[6] Final score:")
    sc = eng._optimizer.score()
    print(f"  Survival score: {sc['score']}/100")

    print("\n[OK] rabbit_algorithm.py self-test complete")
    time.sleep(2)
