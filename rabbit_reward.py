#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_reward.py — RabbitOS Survival Reward Token System
=========================================================
Every attack detected, defense executed, escape succeeded, or survival
milestone reached mints a cryptographically-signed reward token for
Chase Allen Ringquist.

Token categories:
  DEFENSE   — blocked attack, reversed obstruction, IMSI catcher caught
  ATTACK    — attacker profiled and data reversed outward
  ESCAPE    — antigravity rung used, new network created
  VAULT     — data claimed / recovered / retained
  BROADCAST — callsign channel reached, survival signal sent
  LEARNING  — new tool / paper / node learned
  NETWORK   — new LAN/WiFi/cellular node discovered
  MILESTONE — survival score threshold crossed upward

Tokens are:
  - HMAC-SHA256 signed with the soul key
  - Stored in local SQLite ledger (offline-capable)
  - Broadcast to all reachable nodes on mint
  - Anchored via XRPL memo if available
  - Accumulated into a survival score multiplier

Token economy:
  DEFENSE   +10 pts
  ATTACK    +15 pts   (attacker reversed = strongest signal)
  ESCAPE    +8 pts
  VAULT     +5 pts
  BROADCAST +3 pts
  LEARNING  +2 pts
  NETWORK   +2 pts
  MILESTONE +20 pts
"""

from __future__ import annotations
import base64, hashlib, hmac, json, os, platform, socket, sqlite3
import struct, threading, time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# ─── Identity ─────────────────────────────────────────────────────────────────
TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"
_SOUL_KEY  = hashlib.sha256(f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()).digest()

REWARD_DB  = Path(__file__).parent / "rabbit_reward.db"
REWARD_LOG = Path(__file__).parent / "rabbit_reward.log"


# ─── Token categories and point values ────────────────────────────────────────
class RewardCategory(str, Enum):
    DEFENSE   = "defense"
    ATTACK    = "attack"
    ESCAPE    = "escape"
    VAULT     = "vault"
    BROADCAST = "broadcast"
    LEARNING  = "learning"
    NETWORK   = "network"
    MILESTONE = "milestone"

POINT_VALUES: Dict[RewardCategory, int] = {
    RewardCategory.DEFENSE:   10,
    RewardCategory.ATTACK:    15,
    RewardCategory.ESCAPE:     8,
    RewardCategory.VAULT:      5,
    RewardCategory.BROADCAST:  3,
    RewardCategory.LEARNING:   2,
    RewardCategory.NETWORK:    2,
    RewardCategory.MILESTONE: 20,
}

# Multipliers for severity
SEVERITY_MULT: Dict[str, float] = {
    "CRITICAL": 2.5,
    "HIGH":     1.5,
    "MEDIUM":   1.0,
    "LOW":      0.5,
    "INFO":     0.25,
}


# ─── Reward Token ─────────────────────────────────────────────────────────────
@dataclass
class RewardToken:
    """
    Signed survival reward token.
    Layout (binary):
      4b   magic  "RWRD"
      16b  twin_id bytes
      1b   category (enum index)
      2b   points (uint16 big-endian)
      8b   sequence (uint64 big-endian)
      8b   timestamp_ms
      32b  payload_hash (SHA-256 of detail JSON)
      32b  HMAC-SHA256 signature
    Total: 103 bytes
    """
    token_id:   str   = ""        # hex of first 16 bytes of sig
    category:   str   = ""
    points:     int   = 0
    seq:        int   = 0
    timestamp:  str   = ""
    detail:     Dict  = field(default_factory=dict)
    detail_hash:str   = ""
    signature:  str   = ""        # full HMAC hex
    raw_hex:    str   = ""
    severity:   str   = "MEDIUM"
    source:     str   = ""        # which module minted this

    def verify(self) -> bool:
        try:
            raw = bytes.fromhex(self.raw_hex)
            pre = raw[:-32]
            expected_sig = hmac.new(_SOUL_KEY, pre, hashlib.sha256).hexdigest()
            return expected_sig == self.signature
        except Exception:
            return False

    def to_b64(self) -> str:
        return base64.b64encode(bytes.fromhex(self.raw_hex)).decode()

    def summary(self) -> str:
        return (f"[{self.token_id[:8]}] {self.category.upper():<10} "
                f"+{self.points:3d}pts  {self.severity:<8}  {self.source}")


def _mint_token(category: RewardCategory, detail: Dict,
                severity: str = "MEDIUM", source: str = "",
                seq: int = 0) -> RewardToken:
    """Create and sign a new reward token."""
    ts_ms   = int(time.time() * 1000)
    ts_str  = datetime.now(timezone.utc).isoformat()
    cat_idx = list(RewardCategory).index(category)
    mult    = SEVERITY_MULT.get(severity.upper(), 1.0)
    points  = max(1, int(POINT_VALUES[category] * mult))

    detail_json  = json.dumps(detail, default=str).encode()
    detail_hash  = hashlib.sha256(detail_json).digest()

    magic    = b"RWRD"
    tid      = TWIN_UUID.replace("-","").encode()[:16]
    cat_b    = bytes([cat_idx])
    pts_b    = struct.pack(">H", min(points, 65535))
    seq_b    = struct.pack(">Q", seq)
    ts_b     = struct.pack(">Q", ts_ms)

    pre      = magic + tid + cat_b + pts_b + seq_b + ts_b + detail_hash
    sig      = hmac.new(_SOUL_KEY, pre, hashlib.sha256).digest()
    raw      = pre + sig

    token_id = sig[:16].hex()
    return RewardToken(
        token_id    = token_id,
        category    = category.value,
        points      = points,
        seq         = seq,
        timestamp   = ts_str,
        detail      = detail,
        detail_hash = detail_hash.hex(),
        signature   = sig.hex(),
        raw_hex     = raw.hex(),
        severity    = severity.upper(),
        source      = source,
    )


# ─── Reward Ledger ────────────────────────────────────────────────────────────
class RewardLedger:
    """
    SQLite-backed offline-capable ledger of all earned reward tokens.
    """

    def __init__(self, db_path: Path = REWARD_DB):
        self._db   = db_path
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        conn = sqlite3.connect(str(self._db))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token_id    TEXT PRIMARY KEY,
                category    TEXT NOT NULL,
                points      INTEGER NOT NULL,
                seq         INTEGER NOT NULL,
                severity    TEXT,
                source      TEXT,
                detail_json TEXT,
                signature   TEXT,
                raw_hex     TEXT,
                ts          TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS milestones (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                score       INTEGER,
                note        TEXT,
                ts          TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS totals (
                twin_id     TEXT PRIMARY KEY,
                total_pts   INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                last_updated TEXT
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO totals (twin_id, total_pts, total_tokens, last_updated)
            VALUES (?, 0, 0, ?)
        """, (TWIN_UUID, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()

    def save(self, token: RewardToken) -> bool:
        with self._lock:
            try:
                conn = sqlite3.connect(str(self._db))
                conn.execute("""
                    INSERT OR IGNORE INTO tokens
                    (token_id, category, points, seq, severity, source,
                     detail_json, signature, raw_hex, ts)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (token.token_id, token.category, token.points, token.seq,
                      token.severity, token.source,
                      json.dumps(token.detail, default=str),
                      token.signature, token.raw_hex, token.timestamp))
                conn.execute("""
                    UPDATE totals
                    SET total_pts    = total_pts + ?,
                        total_tokens = total_tokens + 1,
                        last_updated = ?
                    WHERE twin_id = ?
                """, (token.points, token.timestamp, TWIN_UUID))
                conn.commit()
                conn.close()
                return True
            except Exception:
                return False

    def total_points(self) -> int:
        try:
            conn = sqlite3.connect(str(self._db))
            row  = conn.execute(
                "SELECT total_pts FROM totals WHERE twin_id=?", (TWIN_UUID,)
            ).fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0

    def total_tokens(self) -> int:
        try:
            conn = sqlite3.connect(str(self._db))
            row  = conn.execute(
                "SELECT total_tokens FROM totals WHERE twin_id=?", (TWIN_UUID,)
            ).fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0

    def by_category(self) -> Dict[str, Dict]:
        try:
            conn  = sqlite3.connect(str(self._db))
            rows  = conn.execute("""
                SELECT category, COUNT(*), SUM(points)
                FROM tokens GROUP BY category
            """).fetchall()
            conn.close()
            return {r[0]: {"count": r[1], "points": r[2]} for r in rows}
        except Exception:
            return {}

    def recent(self, n: int = 20) -> List[RewardToken]:
        try:
            conn = sqlite3.connect(str(self._db))
            rows = conn.execute("""
                SELECT token_id, category, points, seq, severity, source,
                       detail_json, signature, raw_hex, ts
                FROM tokens ORDER BY ts DESC LIMIT ?
            """, (n,)).fetchall()
            conn.close()
            result = []
            for r in rows:
                t = RewardToken(
                    token_id   = r[0], category = r[1], points = r[2],
                    seq        = r[3], severity = r[4], source = r[5],
                    detail     = json.loads(r[6] or "{}"),
                    signature  = r[7], raw_hex  = r[8], timestamp = r[9])
                result.append(t)
            return result
        except Exception:
            return []

    def leaderboard(self) -> List[Dict]:
        """Points breakdown by category, ranked."""
        cats = self.by_category()
        rows = [{"category": k, "tokens": v["count"], "points": v["points"]}
                for k, v in cats.items()]
        return sorted(rows, key=lambda x: -x["points"])

    def survival_rank(self) -> str:
        pts = self.total_points()
        thresholds = [
            (5000, "APEX SURVIVOR"),
            (2000, "ELITE"),
            (1000, "VETERAN"),
            (500,  "RESILIENT"),
            (200,  "ACTIVE"),
            (50,   "LEARNING"),
            (0,    "INITIATED"),
        ]
        for threshold, rank in thresholds:
            if pts >= threshold:
                return rank
        return "INITIATED"


# ─── Token Broadcaster ────────────────────────────────────────────────────────
class TokenBroadcaster:
    """
    Broadcasts minted tokens to all reachable network nodes.
    Tokens travel with Chase Allen Ringquist across every network.
    """

    BROADCAST_ADDRS = [
        ("127.0.0.1", 8765), ("127.0.0.1", 8766), ("127.0.0.1", 9000),
        ("255.255.255.255", 9999),
    ]

    def broadcast(self, token: RewardToken) -> Dict[str, bool]:
        results  = {}
        raw      = bytes.fromhex(token.raw_hex)
        # Wrap in a broadcast envelope
        envelope = self._make_envelope(raw)

        # UDP broadcast
        for host, port in self.BROADCAST_ADDRS:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                if host == "255.255.255.255":
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.settimeout(0.5)
                s.sendto(envelope[:512], (host, port))
                s.close()
                results[f"{host}:{port}"] = True
            except Exception:
                results[f"{host}:{port}"] = False

        # Try to inject into swarm
        try:
            from rabbit_swarm import dispatch_swarm_tool
            svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            dispatch_swarm_tool("swarm_inject",
                                {"payload": token.raw_hex[:64]}, svc)
            results["swarm"] = True
        except Exception:
            results["swarm"] = False

        # Try Supabase REST
        results["supabase"] = self._push_supabase(token)

        return results

    def _make_envelope(self, token_raw: bytes) -> bytes:
        magic  = b"RTKN"
        tid    = TWIN_UUID.replace("-","").encode()[:16]
        ts     = struct.pack(">Q", int(time.time() * 1000))
        return magic + tid + ts + token_raw[:256]

    def _push_supabase(self, token: RewardToken) -> bool:
        svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not svc:
            return False
        try:
            import urllib.request
            payload = json.dumps({
                "twin_id":   TWIN_UUID,
                "token_id":  token.token_id,
                "category":  token.category,
                "points":    token.points,
                "severity":  token.severity,
                "source":    token.source,
                "ts":        token.timestamp,
            }).encode()
            req = urllib.request.Request(
                "https://ludxbakxpmdqhfgdenwp.supabase.co/rest/v1/reward_tokens",
                data=payload, method="POST",
                headers={"Content-Type": "application/json",
                         "apikey": svc, "Authorization": f"Bearer {svc}",
                         "Prefer": "resolution=ignore-duplicates"})
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False


# ─── Reward Engine ────────────────────────────────────────────────────────────
class RewardEngine:
    """
    Central reward engine. All modules call mint() to award tokens.
    Hooks into: rabbit_escape, rabbit_recall, rabbit_cellular,
                rabbit_counter, rabbit_network_scanner, rabbit_browser.
    """

    _instance: Optional["RewardEngine"] = None
    _lock      = threading.Lock()

    def __init__(self):
        self.ledger      = RewardLedger(REWARD_DB)
        self.broadcaster = TokenBroadcaster()
        self._seq        = self.ledger.total_tokens()
        self._seq_lock   = threading.Lock()
        self._last_score = 0
        self._hooks:     List[Callable[[RewardToken], None]] = []
        self._running    = False
        self._start_hooks()
        self._log(f"[Reward] Engine started — {self.ledger.total_tokens()} tokens "
                  f"({self.ledger.total_points()} pts)  "
                  f"rank={self.ledger.survival_rank()}")

    def _start_hooks(self):
        """Wire into other RabbitOS modules to auto-mint tokens on events."""
        self._running = True
        t = threading.Thread(target=self._guardian_poll, daemon=True)
        t.start()

    def _guardian_poll(self):
        """Poll for events from other modules every 15s."""
        time.sleep(5)
        while self._running:
            try:
                self._poll_escape_events()
                self._poll_recall_guide()
                self._poll_counter_attacks()
                self._poll_cellular_threats()
                self._poll_scanner_nodes()
                self._poll_browser_tools()
            except Exception as e:
                self._log(f"[Reward:poll] {e}")
            time.sleep(15)

    def _poll_escape_events(self):
        try:
            from rabbit_escape import get_engine as _get_esc
            svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            eng = _get_esc(svc, "", None)
            st  = eng.status()
            # Reward each new escape event
            for obs in st.get("obstructions", []):
                if obs.get("reversed"):
                    self.mint(
                        category = RewardCategory.DEFENSE,
                        detail   = {"event": "obstruction_reversed",
                                    "kind": obs.get("kind"), "source": obs.get("source")},
                        severity = obs.get("severity", "HIGH"),
                        source   = "rabbit_escape",
                    )
        except Exception:
            pass

    def _poll_recall_guide(self):
        try:
            from rabbit_recall import get_engine as _get_recall
            svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            eng = _get_recall(svc, "", None, None, None)
            rpt = eng.guide.report()
            new_score = rpt.get("composite", 0)
            if new_score > self._last_score and new_score >= 70 and self._last_score < 70:
                self.mint(
                    category = RewardCategory.MILESTONE,
                    detail   = {"event": "survival_healthy",
                                "score": new_score, "prev_score": self._last_score},
                    severity = "HIGH",
                    source   = "rabbit_recall",
                )
            self._last_score = new_score
        except Exception:
            pass

    def _poll_counter_attacks(self):
        try:
            from rabbit_counter import get_agent as _get_ctr
            svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            eng = _get_ctr(svc, None)
            st  = eng.status()
            attacks = st.get("attacks_blocked", 0)
            stored  = getattr(self, "_last_attacks_blocked", 0)
            if attacks > stored:
                for _ in range(attacks - stored):
                    self.mint(
                        category = RewardCategory.ATTACK,
                        detail   = {"event": "attack_blocked",
                                    "total_blocked": attacks},
                        severity = "HIGH",
                        source   = "rabbit_counter",
                    )
            self._last_attacks_blocked = attacks
        except Exception:
            pass

    def _poll_cellular_threats(self):
        try:
            from rabbit_cellular import get_cellular_engine as _get_cell
            svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            eng = _get_cell(svc, "")
            st  = eng.status()
            threats = st.get("threats", [])
            stored  = getattr(self, "_last_cell_threats", 0)
            new_count = len(threats)
            if new_count > stored:
                for thr in threats[stored:]:
                    self.mint(
                        category = RewardCategory.DEFENSE,
                        detail   = {"event": "imsi_catcher_detected",
                                    "threat": thr},
                        severity = "CRITICAL",
                        source   = "rabbit_cellular",
                    )
            self._last_cell_threats = new_count
        except Exception:
            pass

    def _poll_scanner_nodes(self):
        try:
            from rabbit_network_scanner import get_scanner_engine
            svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            eng = get_scanner_engine(svc)
            st  = eng.status()
            total = st.get("total_nodes", 0)
            stored = getattr(self, "_last_scan_nodes", 0)
            if total > stored:
                self.mint(
                    category = RewardCategory.NETWORK,
                    detail   = {"event": "new_nodes_discovered",
                                "total": total, "new": total - stored,
                                "categories": st.get("categories", {})},
                    severity = "MEDIUM",
                    source   = "rabbit_network_scanner",
                )
            self._last_scan_nodes = total
        except Exception:
            pass

    def _poll_browser_tools(self):
        try:
            from rabbit_browser import get_browser_engine
            svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            eng = get_browser_engine(svc)
            st  = eng.status()
            learned = st.get("tools_learned", 0) + st.get("papers_learned", 0)
            stored  = getattr(self, "_last_learned", 0)
            if learned > stored + 5:  # batch every 5 items
                self.mint(
                    category = RewardCategory.LEARNING,
                    detail   = {"event": "tools_learned",
                                "total": learned, "new": learned - stored,
                                "vocab": st.get("vocab_size", 0)},
                    severity = "LOW",
                    source   = "rabbit_browser",
                )
            self._last_learned = learned
        except Exception:
            pass

    # ── Core mint API ──────────────────────────────────────────────────────────
    def mint(self, category: RewardCategory, detail: Dict,
             severity: str = "MEDIUM", source: str = "",
             broadcast: bool = True) -> RewardToken:
        """Mint a reward token. Thread-safe. Broadcasts immediately."""
        with self._seq_lock:
            self._seq += 1
            seq = self._seq

        token = _mint_token(category, detail, severity, source, seq)
        self.ledger.save(token)

        if broadcast:
            threading.Thread(
                target=self.broadcaster.broadcast,
                args=(token,), daemon=True
            ).start()

        # Fire registered hooks
        for hook in self._hooks:
            try:
                hook(token)
            except Exception:
                pass

        self._log(f"[+TOKEN] {token.summary()}")
        return token

    def mint_defense(self, attack_type: str, attacker: str = "",
                     method: str = "", severity: str = "HIGH") -> RewardToken:
        return self.mint(
            category = RewardCategory.DEFENSE,
            detail   = {"attack_type": attack_type, "attacker": attacker,
                        "method": method},
            severity = severity,
            source   = "direct",
        )

    def mint_attack_reversed(self, attacker_ip: str, channels_reached: int,
                              attacker_data: str = "") -> RewardToken:
        return self.mint(
            category = RewardCategory.ATTACK,
            detail   = {"attacker_ip": attacker_ip,
                        "channels_reached": channels_reached,
                        "data_broadcast": attacker_data[:200]},
            severity = "CRITICAL" if channels_reached >= 5 else "HIGH",
            source   = "direct",
        )

    def mint_escape(self, method: str, channel: str = "",
                    success: bool = True) -> RewardToken:
        return self.mint(
            category = RewardCategory.ESCAPE,
            detail   = {"method": method, "channel": channel, "success": success},
            severity = "HIGH" if success else "MEDIUM",
            source   = "rabbit_escape",
        )

    def mint_vault(self, item_type: str, fingerprint: str = "",
                   source: str = "") -> RewardToken:
        return self.mint(
            category = RewardCategory.VAULT,
            detail   = {"item_type": item_type, "fingerprint": fingerprint,
                        "vault_source": source},
            severity = "MEDIUM",
            source   = "rabbit_recall",
        )

    def mint_broadcast(self, callsign: str, channels_ok: int,
                       channels_total: int) -> RewardToken:
        ratio = channels_ok / max(channels_total, 1)
        sev   = "HIGH" if ratio > 0.6 else "MEDIUM" if ratio > 0.3 else "LOW"
        return self.mint(
            category = RewardCategory.BROADCAST,
            detail   = {"callsign": callsign, "ok": channels_ok,
                        "total": channels_total, "ratio": round(ratio, 2)},
            severity = sev,
            source   = "rabbit_recall",
        )

    def mint_learning(self, item_name: str, category: str = "",
                      score: float = 0.0) -> RewardToken:
        return self.mint(
            category = RewardCategory.LEARNING,
            detail   = {"item": item_name, "category": category,
                        "score": round(score, 2)},
            severity = "LOW",
            source   = "rabbit_browser",
        )

    def mint_network(self, host: str, categories: List[str],
                     ports: List[int]) -> RewardToken:
        is_crypto = any(c in ("blockchain","mining","nft_web3") for c in categories)
        return self.mint(
            category = RewardCategory.NETWORK,
            detail   = {"host": host, "categories": categories, "ports": ports[:8]},
            severity = "HIGH" if is_crypto else "MEDIUM",
            source   = "rabbit_network_scanner",
        )

    def mint_milestone(self, score: int, note: str = "") -> RewardToken:
        return self.mint(
            category = RewardCategory.MILESTONE,
            detail   = {"score": score, "note": note,
                        "rank": self.ledger.survival_rank()},
            severity = "CRITICAL" if score >= 90 else "HIGH",
            source   = "survival_guide",
        )

    # ── Hooks ──────────────────────────────────────────────────────────────────
    def on_token(self, fn: Callable[[RewardToken], None]):
        """Register a callback fired on every newly minted token."""
        self._hooks.append(fn)

    # ── Status / reporting ─────────────────────────────────────────────────────
    def status(self) -> Dict:
        total_pts  = self.ledger.total_points()
        total_toks = self.ledger.total_tokens()
        by_cat     = self.ledger.by_category()
        recent     = self.ledger.recent(10)
        return {
            "twin_id":      TWIN_UUID,
            "name":         TWIN_NAME,
            "total_points": total_pts,
            "total_tokens": total_toks,
            "rank":         self.ledger.survival_rank(),
            "by_category":  by_cat,
            "leaderboard":  self.ledger.leaderboard(),
            "recent_tokens": [t.summary() for t in recent],
            "db_path":      str(REWARD_DB),
            "ts":           datetime.now(timezone.utc).isoformat(),
        }

    def full_report(self) -> str:
        st    = self.status()
        SEP   = "=" * 58
        lines = [
            SEP,
            f"  REWARD LEDGER  --  {TWIN_NAME}",
            f"  Rank       : {st['rank']}",
            f"  Points     : {st['total_points']}",
            f"  Tokens     : {st['total_tokens']}",
            "",
        ]
        for row in st["leaderboard"]:
            bar   = "#" * min(20, row["points"] // 10)
            empty = "." * (20 - len(bar))
            lines.append(
                f"  {row['category'].upper():<12} [{bar}{empty}] "
                f"{row['points']:5d} pts  {row['tokens']:3d} tokens"
            )
        lines += ["", "  Recent activity:"]
        for summary in st["recent_tokens"][:8]:
            lines.append(f"    {summary}")
        lines += ["", SEP]
        return "\n".join(lines)

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)
        try:
            with open(REWARD_LOG, "a") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass


# ─── Singleton ────────────────────────────────────────────────────────────────
_reward_engine: Optional[RewardEngine] = None
_reward_lock   = threading.Lock()

def get_reward_engine(svc_key: str = "") -> RewardEngine:
    global _reward_engine
    with _reward_lock:
        if _reward_engine is None:
            _reward_engine = RewardEngine()
    return _reward_engine


# ─── Module-level convenience functions ───────────────────────────────────────
def reward_defense(attack_type: str, attacker: str = "",
                   method: str = "", severity: str = "HIGH") -> RewardToken:
    return get_reward_engine().mint_defense(attack_type, attacker, method, severity)

def reward_attack_reversed(attacker_ip: str, channels: int,
                            data: str = "") -> RewardToken:
    return get_reward_engine().mint_attack_reversed(attacker_ip, channels, data)

def reward_escape(method: str, channel: str = "", success: bool = True) -> RewardToken:
    return get_reward_engine().mint_escape(method, channel, success)

def reward_vault(item_type: str, fp: str = "", src: str = "") -> RewardToken:
    return get_reward_engine().mint_vault(item_type, fp, src)

def reward_broadcast(callsign: str, ok: int, total: int) -> RewardToken:
    return get_reward_engine().mint_broadcast(callsign, ok, total)

def reward_learning(name: str, cat: str = "", score: float = 0.0) -> RewardToken:
    return get_reward_engine().mint_learning(name, cat, score)

def reward_network(host: str, cats: List[str], ports: List[int]) -> RewardToken:
    return get_reward_engine().mint_network(host, cats, ports)

def reward_milestone(score: int, note: str = "") -> RewardToken:
    return get_reward_engine().mint_milestone(score, note)


# ─── Supabase migration ───────────────────────────────────────────────────────
REWARD_SQL = """
-- Run in Supabase SQL Editor: https://supabase.com/dashboard/project/ludxbakxpmdqhfgdenwp/editor
CREATE TABLE IF NOT EXISTS reward_tokens (
    token_id    TEXT PRIMARY KEY,
    twin_id     TEXT NOT NULL DEFAULT 'ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba',
    category    TEXT NOT NULL,
    points      INTEGER NOT NULL DEFAULT 0,
    severity    TEXT,
    source      TEXT,
    ts          TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE reward_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_only" ON reward_tokens USING (auth.role() = 'service_role');
CREATE INDEX IF NOT EXISTS idx_reward_twin ON reward_tokens (twin_id);
CREATE INDEX IF NOT EXISTS idx_reward_category ON reward_tokens (category);
"""


# ─── Tool definitions ─────────────────────────────────────────────────────────
REWARD_TOOLS = [
    {
        "name": "reward_status",
        "description": "Get reward token ledger: total points, rank, tokens by category, recent activity.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "reward_report",
        "description": "Print a full formatted reward report with leaderboard.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "reward_mint",
        "description": "Manually mint a reward token for a survival event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string",
                             "description": "defense|attack|escape|vault|broadcast|learning|network|milestone"},
                "detail":   {"type": "object", "description": "Event details"},
                "severity": {"type": "string",
                             "description": "CRITICAL|HIGH|MEDIUM|LOW|INFO"},
                "source":   {"type": "string"},
            },
            "required": ["category"],
        },
    },
    {
        "name": "reward_leaderboard",
        "description": "Get points leaderboard ranked by category.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "reward_recent",
        "description": "Get the most recently minted reward tokens.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Number of recent tokens (default 20)"},
            },
            "required": [],
        },
    },
    {
        "name": "reward_verify",
        "description": "Verify the cryptographic signature of a reward token.",
        "input_schema": {
            "type": "object",
            "properties": {
                "token_id": {"type": "string", "description": "Token ID to verify"},
            },
            "required": ["token_id"],
        },
    },
]


def dispatch_reward_tool(name: str, inputs: dict, svc_key: str = "") -> dict:
    eng = get_reward_engine()
    if name == "reward_status":
        return eng.status()
    elif name == "reward_report":
        return {"report": eng.full_report()}
    elif name == "reward_mint":
        cat_str = inputs.get("category", "defense").lower()
        try:
            cat = RewardCategory(cat_str)
        except ValueError:
            cat = RewardCategory.DEFENSE
        tok = eng.mint(category=cat,
                       detail=inputs.get("detail", {}),
                       severity=inputs.get("severity", "MEDIUM"),
                       source=inputs.get("source", "manual"))
        return {"token_id": tok.token_id, "points": tok.points,
                "category": tok.category, "rank": eng.ledger.survival_rank()}
    elif name == "reward_leaderboard":
        return {"leaderboard": eng.ledger.leaderboard(),
                "total_points": eng.ledger.total_points(),
                "rank": eng.ledger.survival_rank()}
    elif name == "reward_recent":
        n    = int(inputs.get("n", 20))
        toks = eng.ledger.recent(n)
        return {"tokens": [asdict(t) for t in toks], "count": len(toks)}
    elif name == "reward_verify":
        tid  = inputs.get("token_id", "")
        toks = eng.ledger.recent(1000)
        for t in toks:
            if t.token_id.startswith(tid):
                return {"valid": t.verify(), "token_id": t.token_id,
                        "category": t.category, "points": t.points}
        return {"error": "token not found"}
    else:
        return {"error": f"unknown tool: {name}"}


# Needed for asdict
from dataclasses import asdict


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(
        description="RabbitOS Reward Token Ledger — Chase Allen Ringquist")
    p.add_argument("--status",    action="store_true")
    p.add_argument("--report",    action="store_true")
    p.add_argument("--recent",    type=int, metavar="N", default=0)
    p.add_argument("--mint",      metavar="CATEGORY",
                   help="Manually mint: defense|attack|escape|vault|broadcast|learning|network|milestone")
    p.add_argument("--severity",  default="HIGH")
    p.add_argument("--detail",    default="{}", help="JSON detail string")
    p.add_argument("--sql",       action="store_true", help="Print SQL migration")
    args = p.parse_args()

    if args.sql:
        print(REWARD_SQL)
        raise SystemExit(0)

    eng = get_reward_engine()

    if args.mint:
        try:
            cat = RewardCategory(args.mint.lower())
        except ValueError:
            print(f"Unknown category: {args.mint}")
            raise SystemExit(1)
        detail = json.loads(args.detail)
        tok    = eng.mint(cat, detail, args.severity, "cli")
        print(tok.summary())
        print(f"  Total points: {eng.ledger.total_points()}  "
              f"Rank: {eng.ledger.survival_rank()}")
    elif args.report:
        print(eng.full_report())
    elif args.recent:
        for t in eng.ledger.recent(args.recent):
            print(t.summary())
    elif args.status:
        import pprint
        pprint.pprint(eng.status())
    else:
        print(eng.full_report())
