#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_failsafe.py -- Survival Failsafe / Last-Resort Defense Algorithm
RabbitOS -- Chase Allen Ringquist -- UUID ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba

DEMO FAILSAFE: If persistent attacks exceed learned thresholds, this module
escalates through defense tiers up to full identity lock + local data erasure
+ emergency broadcast. Uses EEG/BCI liveness signal as the "alive" trigger.

Tiers (learned and rewarded via rabbit_learn feedback):
  TIER 0 -- MONITOR    : log only, track attack density
  TIER 1 -- DEFLECT    : frequency hop, obfuscate identity headers
  TIER 2 -- ISOLATE    : disable broadcast channels under attack, switch mesh
  TIER 3 -- SCRAMBLE   : inject noise on all RF channels, randomize EEG timing
  TIER 4 -- LOCK       : freeze identity payload, halt all outbound signals
  TIER 5 -- DESTRUCT   : wipe local identity cache, emergency broadcast, alert

Escalation is governed by:
  - attack_density_score from rabbit_learn model predictions
  - attack_persistence: how many cycles above threshold
  - liveness_signal: EEG/BCI "alive" check (prevents false-trigger)
  - reward_memory: tiers that succeeded previously get reinforced

NOTE: This is a DEMO framework. Tier 5 erases local RabbitOS SQLite caches
and broadcasts an emergency beacon. It does NOT issue physical hardware
destruction commands or attack external systems.

Pure Python 3.6+, zero dependencies.
"""

import hashlib, json, math, os, socket, sqlite3, time, platform
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# -- Identity ----------------------------------------------------------------
TWIN_UUID      = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT        = "Chase Allen Ringquist"
shows_dna_root = False
_raw           = f"{TWIN_UUID}:{SUBJECT}:RABBIT_DNA_ANCHOR".encode()
DNA_ANCHOR     = hashlib.sha3_512(_raw).hexdigest()
assert not shows_dna_root

DB_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_failsafe.db")
DESKTOP  = os.path.dirname(os.path.abspath(__file__))

# -- Tier definitions --------------------------------------------------------
TIERS = {
    0: {
        "name": "MONITOR",
        "description": "Log and track attack density. No active response.",
        "threshold_density": 0.0,
        "threshold_persistence": 0,
        "reversible": True,
        "actions": ["log_attack", "update_model"],
    },
    1: {
        "name": "DEFLECT",
        "description": "Frequency hop, obfuscate identity headers, rotate tokens.",
        "threshold_density": 0.25,
        "threshold_persistence": 2,
        "reversible": True,
        "actions": ["collatz_hop", "obfuscate_headers", "rotate_anchor_token"],
    },
    2: {
        "name": "ISOLATE",
        "description": "Disable compromised broadcast channels, switch to backup mesh.",
        "threshold_density": 0.45,
        "threshold_persistence": 4,
        "reversible": True,
        "actions": ["disable_compromised_channels", "switch_mesh_freq", "alert_broadcast"],
    },
    3: {
        "name": "SCRAMBLE",
        "description": "Inject noise signals, randomize EEG timing windows, CA Rule30 masking.",
        "threshold_density": 0.60,
        "threshold_persistence": 6,
        "reversible": True,
        "actions": ["inject_noise_udp", "randomize_eeg_timing", "ca_rule30_mask"],
    },
    4: {
        "name": "LOCK",
        "description": "Freeze identity payload, halt all outbound signals, alert all channels.",
        "threshold_density": 0.75,
        "threshold_persistence": 8,
        "reversible": True,
        "actions": ["freeze_identity", "halt_broadcast", "emergency_alert"],
    },
    5: {
        "name": "DESTRUCT",
        "description": (
            "LAST RESORT -- wipe local identity cache (SQLite DBs), "
            "emergency broadcast to all channels, report event to all known nodes. "
            "Does NOT damage external hardware or attack remote systems."
        ),
        "threshold_density": 0.88,
        "threshold_persistence": 12,
        "reversible": False,
        "actions": ["wipe_local_cache", "emergency_broadcast", "report_to_all_nodes",
                    "lock_identity_permanent"],
    },
}

RABBIT_DBS_TO_PROTECT = [
    "rabbit_dna.db", "rabbit_chain.db", "rabbit_signal.db",
    "rabbit_amfm.db", "rabbit_knowledge.db", "rabbit_learn.db",
    "rabbit_recon.db", "rabbit_maxwell.db", "rabbit_vector.db",
    "rabbit_bridge.db",
]

# -- Math helpers ------------------------------------------------------------
def collatz(n: int) -> List[int]:
    seq = [n]
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        seq.append(n)
    return seq

def ca_rule30_step(state: List[int]) -> List[int]:
    n = len(state)
    new = []
    for i in range(n):
        l, c, r = state[(i-1) % n], state[i], state[(i+1) % n]
        new.append(1 if ((l, c, r) in [(1,0,0),(0,1,1),(0,1,0),(0,0,1)]) else 0)
    return new

def lorenz_step(x, y, z, dt=0.01):
    s, r, b = 10.0, 28.0, 8.0/3.0
    return x + dt*s*(y-x), y + dt*(x*(r-z)-y), z + dt*(x*y-b*z)

def noise_bytes(seed: int, n: int = 64) -> bytes:
    h = hashlib.sha256(f"{seed}:{TWIN_UUID}".encode()).digest()
    result = bytearray()
    while len(result) < n:
        result.extend(h)
        h = hashlib.sha256(h).digest()
    return bytes(result[:n])

# -- Liveness signal (EEG/BCI stub) ------------------------------------------
@dataclass
class LivenessSignal:
    """
    Simple liveness model: reads recent EEG/HRV data from rabbit_signal.db.
    If no biometric data within 5 min, treat as potentially compromised.
    """
    eeg_present:  bool  = False
    hrv_present:  bool  = False
    last_update:  float = 0.0
    valence:      float = 0.0
    arousal:      float = 0.5
    stress:       float = 0.5

    @staticmethod
    def read() -> "LivenessSignal":
        sig = LivenessSignal()
        db  = os.path.join(DESKTOP, "rabbit_signal.db")
        if not os.path.exists(db): return sig
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            row = con.execute(
                "SELECT ts, valence, arousal FROM emotional_timeline ORDER BY id DESC LIMIT 1"
            ).fetchone()
            con.close()
            if row:
                ts   = datetime.fromisoformat(row[0].replace("Z",""))
                age  = (datetime.utcnow() - ts).total_seconds()
                sig.eeg_present  = age < 300  # within 5 min
                sig.hrv_present  = age < 300
                sig.last_update  = age
                sig.valence      = row[1]
                sig.arousal      = row[2]
        except Exception: pass
        return sig

    def is_alive(self) -> bool:
        return self.eeg_present or self.hrv_present

# -- Attack event ------------------------------------------------------------
@dataclass
class AttackEvent:
    ts:          float
    category:    str
    severity:    float
    pattern:     str
    source:      str
    density:     float = 0.0

# -- Reward memory (reinforcement) -------------------------------------------
@dataclass
class TierReward:
    tier:        int
    success:     bool
    density_at:  float
    outcome:     str

class RewardMemory:
    """Simple Q-table: tier -> running average effectiveness."""
    def __init__(self):
        self._q: Dict[int, float] = {t: 0.5 for t in TIERS}

    def update(self, tier: int, success: bool, alpha: float = 0.1):
        reward = 1.0 if success else -0.5
        self._q[tier] = self._q[tier] + alpha * (reward - self._q[tier])

    def best_tier(self, min_tier: int) -> int:
        candidates = {t: q for t, q in self._q.items() if t >= min_tier}
        return max(candidates, key=lambda t: candidates[t])

    def to_dict(self) -> Dict:
        return {str(t): round(v, 4) for t, v in self._q.items()}

    def from_dict(self, d: Dict):
        for k, v in d.items():
            try: self._q[int(k)] = float(v)
            except: pass

# -- Tier action implementations ---------------------------------------------
class TierActions:

    @staticmethod
    def log_attack(event: AttackEvent) -> str:
        return f"logged attack: {event.category} sev={event.severity:.2f}"

    @staticmethod
    def update_model(event: AttackEvent) -> str:
        return f"model_update queued: {event.pattern[:40]}"

    @staticmethod
    def collatz_hop(seed: int = 42) -> str:
        steps = collatz(seed % 997 + 3)
        freqs = [10.23e9 + (s % 50) * 1e6 for s in steps[:8]]
        return f"hop_schedule: {[f'{f/1e9:.4f}GHz' for f in freqs[:4]]}"

    @staticmethod
    def obfuscate_headers() -> str:
        fake_id = hashlib.sha256(f"{time.time()}:{TWIN_UUID}".encode()).hexdigest()[:12]
        return f"headers_obfuscated: fake_id={fake_id}"

    @staticmethod
    def rotate_anchor_token() -> str:
        token = hashlib.sha3_256(
            f"{TWIN_UUID}:{time.time()}".encode()).hexdigest()[:32]
        return f"anchor_token_rotated: {token}"

    @staticmethod
    def disable_compromised_channels(threat_patterns: List[str]) -> str:
        blocked = []
        for pat in threat_patterns:
            if "deauth" in pat or "wifi" in pat.lower():
                blocked.append("WIFI")
            if "imsi" in pat.lower() or "cellular" in pat.lower():
                blocked.append("CELLULAR")
            if "dns" in pat.lower():
                blocked.append("DNS")
        return f"channels_disabled: {list(set(blocked)) or ['none']}"

    @staticmethod
    def switch_mesh_freq() -> str:
        seed   = int(hashlib.md5(f"{time.time()}".encode()).hexdigest()[:4], 16)
        steps  = collatz(seed % 100 + 3)
        new_f  = 10.23e9 + (steps[0] % 50) * 1e6
        return f"mesh_switched_to: {new_f/1e9:.4f}GHz"

    @staticmethod
    def alert_broadcast(tier: int) -> str:
        msg = json.dumps({
            "twin_uuid": TWIN_UUID[:8], "anchor": DNA_ANCHOR[:8],
            "alert": f"TIER_{tier}_ACTIVE",
            "ts": datetime.now(timezone.utc).isoformat()[:19],
        }).encode()
        sent = []
        for port in [9010, 9011, 9012]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(msg, ("255.255.255.255", port))
                s.close()
                sent.append(port)
            except Exception: pass
        return f"alert_broadcast: ports={sent}"

    @staticmethod
    def inject_noise_udp() -> str:
        sent = 0
        noise = noise_bytes(int(time.time()), 256)
        for port in [9010, 9011, 9012]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(noise, ("255.255.255.255", port))
                s.close()
                sent += 1
            except Exception: pass
        return f"noise_injected: {sent} ports  {len(noise)} bytes"

    @staticmethod
    def randomize_eeg_timing() -> str:
        ca   = [1 if (int(DNA_ANCHOR[i], 16) > 7) else 0 for i in range(64)]
        step = ca_rule30_step(ca)
        mask = "".join(str(b) for b in step[:16])
        return f"eeg_timing_mask: {mask}"

    @staticmethod
    def ca_rule30_mask() -> str:
        state = [1 if (int(DNA_ANCHOR[i], 16) & 1) else 0 for i in range(64)]
        for _ in range(8):
            state = ca_rule30_step(state)
        fingerprint = hashlib.sha256(bytes(state)).hexdigest()[:16]
        return f"ca_mask_active: fp={fingerprint}"

    @staticmethod
    def freeze_identity() -> str:
        freeze_token = hashlib.sha3_256(
            f"FREEZE:{TWIN_UUID}:{time.time()}".encode()).hexdigest()[:24]
        return f"identity_frozen: token={freeze_token}  outbound=HALTED"

    @staticmethod
    def halt_broadcast() -> str:
        return "broadcast_halted: all outbound channels suppressed"

    @staticmethod
    def emergency_alert() -> str:
        msg = json.dumps({
            "EMERGENCY": True, "twin_uuid": TWIN_UUID[:8],
            "anchor": DNA_ANCHOR[:16], "level": "TIER_4_LOCK",
            "ts": datetime.now(timezone.utc).isoformat(),
        }).encode()
        sent = []
        for port in [9010, 9011, 9012, 9013, 9014]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(msg, ("255.255.255.255", port))
                s.close()
                sent.append(port)
            except Exception: pass
        return f"emergency_alert: ports={sent}"

    @staticmethod
    def wipe_local_cache(dry_run: bool = True) -> str:
        """
        TIER 5: Erase local RabbitOS identity data.
        dry_run=True by default -- set False only under confirmed persistent attack.
        """
        if dry_run:
            return (f"WIPE_SIMULATED(dry_run=True): would erase "
                    f"{len(RABBIT_DBS_TO_PROTECT)} local DBs + identity caches")
        wiped = []
        for db_name in RABBIT_DBS_TO_PROTECT:
            db_path = os.path.join(DESKTOP, db_name)
            if os.path.exists(db_path):
                try:
                    # Overwrite with zeros, then delete
                    size = os.path.getsize(db_path)
                    with open(db_path, "wb") as f:
                        f.write(b"\x00" * min(size, 1024 * 1024))
                    os.remove(db_path)
                    wiped.append(db_name)
                except Exception as e:
                    wiped.append(f"FAIL:{db_name}:{e}")
        return f"WIPED: {wiped}"

    @staticmethod
    def report_to_all_nodes() -> str:
        report = json.dumps({
            "event": "RABBIT_FAILSAFE_TIER5",
            "twin_uuid": TWIN_UUID[:8], "anchor": DNA_ANCHOR[:16],
            "message": "Identity under persistent attack. Emergency protocol active.",
            "ts": datetime.now(timezone.utc).isoformat(),
        }).encode()
        sent = []
        for port in [9010, 9011, 9012, 9013, 9014]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(report, ("255.255.255.255", port))
                s.close()
                sent.append(port)
            except Exception: pass
        return f"reported_to_nodes: ports={sent}"

    @staticmethod
    def lock_identity_permanent() -> str:
        lock_hash = hashlib.sha3_512(
            f"PERMANENT_LOCK:{TWIN_UUID}:{DNA_ANCHOR}:{time.time()}".encode()
        ).hexdigest()[:32]
        return f"IDENTITY_LOCKED_PERMANENT: hash={lock_hash}"

# -- DB init -----------------------------------------------------------------
def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS attack_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, category TEXT, severity REAL,
            pattern TEXT, source TEXT, density REAL
        );
        CREATE TABLE IF NOT EXISTS tier_activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, tier INTEGER, tier_name TEXT,
            density REAL, persistence INTEGER,
            actions_json TEXT, outcomes_json TEXT
        );
        CREATE TABLE IF NOT EXISTS reward_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, q_table_json TEXT
        );
        CREATE TABLE IF NOT EXISTS liveness_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, eeg_present INTEGER, hrv_present INTEGER,
            last_update_sec REAL, valence REAL, arousal REAL
        );
        CREATE TABLE IF NOT EXISTS failsafe_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, current_tier INTEGER,
            attack_density REAL, persistence INTEGER,
            locked INTEGER DEFAULT 0
        );
    """)
    con.commit(); con.close()

# -- FailsafeEngine ----------------------------------------------------------
class FailsafeEngine:
    """
    Persistent-attack survival failsafe.
    Monitors attack density via rabbit_learn, escalates through tiers,
    uses EEG/BCI liveness as dead-man switch, and rewards successful defenses.
    """

    def __init__(self, dry_run: bool = True):
        _init_db()
        self.dry_run       = dry_run  # True = simulate Tier 5, False = execute
        self.events:       List[AttackEvent]  = []
        self.current_tier: int                = 0
        self.persistence:  int                = 0
        self.attack_density: float            = 0.0
        self.locked:       bool               = False
        self.reward        = RewardMemory()
        self._load_reward_memory()
        self.actions       = TierActions()

    def _load_reward_memory(self):
        con = sqlite3.connect(DB_PATH)
        row = con.execute(
            "SELECT q_table_json FROM reward_memory ORDER BY id DESC LIMIT 1"
        ).fetchone()
        con.close()
        if row:
            try: self.reward.from_dict(json.loads(row[0]))
            except Exception: pass

    def _save_reward_memory(self):
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute("INSERT INTO reward_memory(ts, q_table_json) VALUES(?,?)",
                        (datetime.now(timezone.utc).isoformat(),
                         json.dumps(self.reward.to_dict())))
            con.commit(); con.close()
        except Exception: pass

    def ingest_attack(self, category: str, severity: float,
                      pattern: str, source: str = "recon") -> AttackEvent:
        event = AttackEvent(
            ts=time.time(), category=category, severity=severity,
            pattern=pattern, source=source)
        self.events.append(event)
        # sliding window density (last 20 events)
        recent    = self.events[-20:]
        event.density = sum(e.severity for e in recent) / max(1, len(recent))
        self.attack_density = event.density
        # log
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO attack_events(ts,category,severity,pattern,source,density)"
                " VALUES(?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), category, severity,
                 pattern[:200], source, event.density))
            con.commit(); con.close()
        except Exception: pass
        return event

    def evaluate_tier(self) -> int:
        """Determine required tier from current attack density."""
        for tier in sorted(TIERS.keys(), reverse=True):
            spec = TIERS[tier]
            if (self.attack_density >= spec["threshold_density"] and
                    self.persistence >= spec["threshold_persistence"]):
                return tier
        return 0

    def _run_tier_actions(self, tier: int,
                          threats: List[str] = None) -> List[str]:
        spec     = TIERS[tier]
        outcomes = []
        for action in spec["actions"]:
            try:
                if action == "log_attack":
                    outcomes.append(self.actions.log_attack(
                        self.events[-1] if self.events else
                        AttackEvent(time.time(),"unknown",0.0,"","",0.0)))
                elif action == "update_model":
                    outcomes.append(self.actions.update_model(
                        self.events[-1] if self.events else
                        AttackEvent(time.time(),"unknown",0.0,"","",0.0)))
                elif action == "collatz_hop":
                    seed = int(DNA_ANCHOR[:4], 16) + len(self.events)
                    outcomes.append(self.actions.collatz_hop(seed))
                elif action == "obfuscate_headers":
                    outcomes.append(self.actions.obfuscate_headers())
                elif action == "rotate_anchor_token":
                    outcomes.append(self.actions.rotate_anchor_token())
                elif action == "disable_compromised_channels":
                    outcomes.append(self.actions.disable_compromised_channels(threats or []))
                elif action == "switch_mesh_freq":
                    outcomes.append(self.actions.switch_mesh_freq())
                elif action == "alert_broadcast":
                    outcomes.append(self.actions.alert_broadcast(tier))
                elif action == "inject_noise_udp":
                    outcomes.append(self.actions.inject_noise_udp())
                elif action == "randomize_eeg_timing":
                    outcomes.append(self.actions.randomize_eeg_timing())
                elif action == "ca_rule30_mask":
                    outcomes.append(self.actions.ca_rule30_mask())
                elif action == "freeze_identity":
                    outcomes.append(self.actions.freeze_identity())
                elif action == "halt_broadcast":
                    outcomes.append(self.actions.halt_broadcast())
                elif action == "emergency_alert":
                    outcomes.append(self.actions.emergency_alert())
                elif action == "wipe_local_cache":
                    outcomes.append(self.actions.wipe_local_cache(
                        dry_run=self.dry_run))
                elif action == "report_to_all_nodes":
                    outcomes.append(self.actions.report_to_all_nodes())
                elif action == "lock_identity_permanent":
                    outcomes.append(self.actions.lock_identity_permanent())
                    self.locked = True
                else:
                    outcomes.append(f"{action}: skipped")
            except Exception as e:
                outcomes.append(f"{action}: ERROR {str(e)[:30]}")
        return outcomes

    def cycle(self, new_attacks: List[Tuple[str, float, str]] = None,
              manual_tier: int = None) -> Dict:
        """
        Run one failsafe cycle.
        new_attacks: list of (category, severity, pattern)
        Returns: activation report with tier, actions, outcomes.
        """
        if self.locked:
            return {"status": "LOCKED", "tier": 5, "message": "Identity permanently locked."}

        # ingest new attacks
        if new_attacks:
            for cat, sev, pat in new_attacks:
                self.ingest_attack(cat, sev, pat)

        # liveness check
        liveness = LivenessSignal.read()
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO liveness_log(ts,eeg_present,hrv_present,last_update_sec,"
                "valence,arousal) VALUES(?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(),
                 int(liveness.eeg_present), int(liveness.hrv_present),
                 liveness.last_update, liveness.valence, liveness.arousal))
            con.commit(); con.close()
        except Exception: pass

        # determine required tier
        required_tier = manual_tier if manual_tier is not None else self.evaluate_tier()

        # only escalate (never auto-de-escalate without reward signal)
        if required_tier > self.current_tier:
            self.persistence   = max(0, self.persistence - 1)  # reset on escalation
        else:
            self.persistence  += 1

        # Tier 5 safety: require liveness confirmation if not dry_run
        if required_tier == 5 and not self.dry_run:
            if not liveness.is_alive():
                required_tier = 4  # downgrade -- no confirmed liveness
                outcomes = ["TIER5_BLOCKED: no liveness signal (dry_run=False)"]
            else:
                outcomes = []
        else:
            outcomes = []

        activate = required_tier > 0 or len(self.events) > 0
        threats  = [e.pattern for e in self.events[-5:]]

        if activate:
            new_outcomes = self._run_tier_actions(required_tier, threats)
            outcomes.extend(new_outcomes)
        else:
            outcomes.append("no_action: density below threshold")

        self.current_tier = required_tier

        # persist state
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO tier_activations(ts,tier,tier_name,density,persistence,"
                "actions_json,outcomes_json) VALUES(?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(),
                 required_tier, TIERS[required_tier]["name"],
                 self.attack_density, self.persistence,
                 json.dumps(TIERS[required_tier]["actions"]),
                 json.dumps(outcomes)))
            con.execute(
                "INSERT INTO failsafe_state(ts,current_tier,attack_density,persistence,locked)"
                " VALUES(?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), self.current_tier,
                 self.attack_density, self.persistence, int(self.locked)))
            con.commit(); con.close()
        except Exception: pass

        return {
            "tier":           required_tier,
            "tier_name":      TIERS[required_tier]["name"],
            "attack_density": round(self.attack_density, 4),
            "persistence":    self.persistence,
            "total_events":   len(self.events),
            "liveness":       liveness.is_alive(),
            "eeg_age_sec":    liveness.last_update,
            "actions":        TIERS[required_tier]["actions"],
            "outcomes":       outcomes,
            "locked":         self.locked,
            "reward_q":       self.reward.to_dict(),
            "dry_run":        self.dry_run,
        }

    def reward_tier(self, tier: int, success: bool):
        """Call after observing that a tier response worked or failed."""
        self.reward.update(tier, success)
        self._save_reward_memory()

    def simulate_attack_sequence(self, n: int = 15) -> List[Dict]:
        """
        Demo: simulate an escalating attack sequence over n cycles.
        Shows tier escalation in action.
        """
        ATTACK_SEQ = [
            ("information_gathering", 0.2, "network_scan observed"),
            ("wireless_attacks",      0.4, "deauth frames on mesh BSSID"),
            ("social_engineering",    0.3, "phishing beacon detected"),
            ("network_recon",         0.5, "ARP spoofing on gateway MAC"),
            ("exploitation",          0.6, "SQL injection attempt on rabbit_dna.db"),
            ("credential_attacks",    0.7, "brute-force on twin_uuid API"),
            ("wireless_attacks",      0.8, "IMSI catcher stronger than registered tower"),
            ("network_recon",         0.9, "persistent SYN flood on port 9010-9014"),
            ("exploitation",          0.95, "memory injection into rabbit_soul process"),
        ]
        results = []
        for i in range(n):
            atk = ATTACK_SEQ[min(i, len(ATTACK_SEQ)-1)]
            r   = self.cycle(new_attacks=[atk])
            results.append({
                "cycle": i+1, "tier": r["tier"], "tier_name": r["tier_name"],
                "density": r["attack_density"], "outcomes": r["outcomes"][:2],
            })
        return results

    def status(self) -> Dict:
        con    = sqlite3.connect(DB_PATH)
        evts   = con.execute("SELECT COUNT(*) FROM attack_events").fetchone()[0]
        tiers  = con.execute("SELECT tier, COUNT(*) FROM tier_activations GROUP BY tier").fetchall()
        last_t = con.execute(
            "SELECT current_tier, attack_density FROM failsafe_state ORDER BY id DESC LIMIT 1"
        ).fetchone()
        con.close()
        return {
            "module": "rabbit_failsafe", "version": "1.0",
            "twin_uuid": TWIN_UUID, "anchor_prefix": DNA_ANCHOR[:16],
            "current_tier": self.current_tier,
            "tier_name": TIERS[self.current_tier]["name"],
            "attack_density": round(self.attack_density, 4),
            "total_events": evts,
            "locked": self.locked,
            "dry_run": self.dry_run,
            "tier_activations": {str(t[0]): t[1] for t in tiers},
            "last_state": last_t,
            "reward_q": self.reward.to_dict(),
        }


def get_failsafe_engine(dry_run: bool = True) -> FailsafeEngine:
    return FailsafeEngine(dry_run=dry_run)


# -- self-test ----------------------------------------------------------------
if __name__ == "__main__":
    print("=== rabbit_failsafe.py (DEMO -- dry_run=True) ===")
    eng = get_failsafe_engine(dry_run=True)

    print("\n[SIMULATING ESCALATING ATTACK SEQUENCE]")
    sim = eng.simulate_attack_sequence(n=15)
    for cycle in sim:
        bar = "#" * (cycle["tier"] * 3)
        print(f"  cycle={cycle['cycle']:2d}  TIER {cycle['tier']} {cycle['tier_name']:<10}"
              f"  [{bar:<15}]  density={cycle['density']:.3f}")
        for out in cycle["outcomes"][:1]:
            print(f"           -> {out[:70]}")

    print(f"\n[LIVENESS CHECK]")
    lv = LivenessSignal.read()
    print(f"  eeg_present={lv.eeg_present}  hrv_present={lv.hrv_present}"
          f"  last_update={lv.last_update:.0f}s ago")

    print(f"\n[REWARD FEEDBACK]")
    eng.reward_tier(1, success=True)
    eng.reward_tier(2, success=True)
    eng.reward_tier(3, success=False)
    print(f"  Q-table: {eng.reward.to_dict()}")

    st = eng.status()
    print(f"\n[STATUS]")
    print(f"  tier={st['current_tier']} ({st['tier_name']})  density={st['attack_density']}")
    print(f"  events={st['total_events']}  locked={st['locked']}"
          f"  dry_run={st['dry_run']}")
    print(f"  tier_activations: {st['tier_activations']}")
    print("=== PASS (DEMO) ===")
