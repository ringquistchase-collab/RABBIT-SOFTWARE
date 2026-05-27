"""
rabbit_intel.py — RabbitOS Personal Intelligence & Finance Tracker
Aggregates personal history, connected parties/networks, threat actors (defensive),
company/DNA connections, published research, and financial data for Chase Allen Ringquist.

Security invariants
───────────────────
shows_dna_root  = False   ← DNA root is NEVER stored or transmitted
vault_location  = None    ← vault plaintext location NEVER stored
TX_LICENSED     = False   ← passive read / query only — no write/submit actions
"""

from __future__ import annotations
import sqlite3, json, hashlib, time, threading, re, os, socket
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
import urllib.request, urllib.error, urllib.parse

# ── Security invariants ──────────────────────────────────────────────────────
shows_dna_root = False
assert shows_dna_root is False, "SECURITY: DNA root must never be exposed"

TX_LICENSED    = False   # passive intelligence only
TWIN_UUID      = "chase-allen-ringquist-twin-001"
TWIN_NAME      = "Chase Allen Ringquist"

INTEL_DB       = "rabbit_intel.db"
_lock          = threading.Lock()

# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class PersonalEvent:
    event_id:    str
    category:    str   # identity / medical / legal / financial / network / social / threat
    title:       str
    description: str
    date_str:    str
    source:      str
    confidence:  float  # 0.0–1.0
    tags:        List[str] = field(default_factory=list)
    ts:          float = field(default_factory=time.time)

@dataclass
class ConnectedParty:
    party_id:      str
    name:          str
    relation:      str   # person / company / device / network / org / attacker
    role:          str   # known / suspected / confirmed
    ip_hash:       str   # SHA-256 of IP if applicable — never plaintext
    mac_hash:      str   # SHA-256 of MAC if applicable
    notes:         str
    risk_level:    str   # low / medium / high / critical
    tags:          List[str] = field(default_factory=list)
    first_seen:    float = field(default_factory=time.time)
    last_seen:     float = field(default_factory=time.time)

@dataclass
class ThreatActor:
    actor_id:      str
    label:         str   # anonymous label only — no dox
    actor_type:    str   # individual / group / org / automated
    attack_vector: str   # network / physical / social / legal / financial / biometric
    severity:      str   # low / medium / high / critical
    indicators:    List[str] = field(default_factory=list)  # hashed IOCs only
    mitigations:   List[str] = field(default_factory=list)
    status:        str   = "active"   # active / mitigated / unknown
    ts:            float = field(default_factory=time.time)

@dataclass
class CompanyRecord:
    company_id:    str
    name:          str
    domain:        str
    category:      str   # biotech / healthcare / surveillance / financial / tech / legal / govt
    connection:    str   # uses-dna / uses-biometric / financial-link / legal-link / network-link
    jurisdiction:  str
    notes:         str
    risk_level:    str   # low / medium / high / critical
    ts:            float = field(default_factory=time.time)

@dataclass
class FinanceRecord:
    record_id:     str
    category:      str   # income / expense / asset / liability / transaction / account / crypto
    label:         str
    amount_cents:  int   # integer cents — no float currency
    currency:      str   # USD / BTC / XRP / ETH / etc.
    counterparty:  str
    date_str:      str
    account_hash:  str   # SHA-256 of account number — never plaintext
    notes:         str
    tags:          List[str] = field(default_factory=list)
    ts:            float = field(default_factory=time.time)

@dataclass
class PublishedNote:
    note_id:       str
    source:        str   # url / publication / document / database
    title:         str
    snippet:       str
    subject_match: float   # 0.0–1.0 relevance to Chase
    category:      str     # personal / network / company / legal / medical / research
    retrieved_at:  float = field(default_factory=time.time)

@dataclass
class DataAsset:
    asset_id:     str
    category:     str   # credential / document / biometric / financial / network / identity
    label:        str
    custodian:    str   # who holds this data
    location:     str   # description — never a plaintext path
    status:       str   # secured / exposed / unknown / compromised
    recovery_url: str
    notes:        str
    ts:           float = field(default_factory=time.time)

# ── Database ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(INTEL_DB)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS personal_events (
            event_id TEXT PRIMARY KEY,
            category TEXT, title TEXT, description TEXT,
            date_str TEXT, source TEXT, confidence REAL,
            tags TEXT, ts REAL
        );
        CREATE TABLE IF NOT EXISTS connected_parties (
            party_id TEXT PRIMARY KEY,
            name TEXT, relation TEXT, role TEXT,
            ip_hash TEXT, mac_hash TEXT, notes TEXT,
            risk_level TEXT, tags TEXT,
            first_seen REAL, last_seen REAL
        );
        CREATE TABLE IF NOT EXISTS threat_actors (
            actor_id TEXT PRIMARY KEY,
            label TEXT, actor_type TEXT, attack_vector TEXT,
            severity TEXT, indicators TEXT, mitigations TEXT,
            status TEXT, ts REAL
        );
        CREATE TABLE IF NOT EXISTS company_records (
            company_id TEXT PRIMARY KEY,
            name TEXT, domain TEXT, category TEXT,
            connection TEXT, jurisdiction TEXT,
            notes TEXT, risk_level TEXT, ts REAL
        );
        CREATE TABLE IF NOT EXISTS finance_records (
            record_id TEXT PRIMARY KEY,
            category TEXT, label TEXT, amount_cents INTEGER,
            currency TEXT, counterparty TEXT, date_str TEXT,
            account_hash TEXT, notes TEXT, tags TEXT, ts REAL
        );
        CREATE TABLE IF NOT EXISTS published_notes (
            note_id TEXT PRIMARY KEY,
            source TEXT, title TEXT, snippet TEXT,
            subject_match REAL, category TEXT, retrieved_at REAL
        );
        CREATE TABLE IF NOT EXISTS data_assets (
            asset_id TEXT PRIMARY KEY,
            category TEXT, label TEXT, custodian TEXT,
            location TEXT, status TEXT, recovery_url TEXT,
            notes TEXT, ts REAL
        );
    """)
    con.commit()
    return con

def _uid(prefix: str = "") -> str:
    import uuid
    return (prefix + str(uuid.uuid4()))[:64]

def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

# ── PersonalDataStore ─────────────────────────────────────────────────────────

class PersonalDataStore:
    """Stores and retrieves Chase Allen Ringquist's personal history and events."""

    def add_event(self, category: str, title: str, description: str,
                  date_str: str, source: str, confidence: float = 1.0,
                  tags: List[str] = None) -> PersonalEvent:
        ev = PersonalEvent(
            event_id=_uid("ev_"), category=category, title=title,
            description=description, date_str=date_str, source=source,
            confidence=min(1.0, max(0.0, confidence)),
            tags=tags or [])
        with _lock:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO personal_events VALUES (?,?,?,?,?,?,?,?,?)",
                    (ev.event_id, ev.category, ev.title, ev.description,
                     ev.date_str, ev.source, ev.confidence,
                     json.dumps(ev.tags), ev.ts))
        return ev

    def get_events(self, category: str = None, limit: int = 100) -> List[PersonalEvent]:
        with _db() as con:
            if category:
                rows = con.execute(
                    "SELECT * FROM personal_events WHERE category=? ORDER BY date_str DESC LIMIT ?",
                    (category, limit)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM personal_events ORDER BY date_str DESC LIMIT ?",
                    (limit,)).fetchall()
        return [PersonalEvent(
            r[0], r[1], r[2], r[3], r[4], r[5], r[6],
            json.loads(r[7] or "[]"), r[8]) for r in rows]

    def timeline(self, limit: int = 200) -> List[Dict]:
        events = self.get_events(limit=limit)
        return [{"date": e.date_str, "category": e.category,
                 "title": e.title, "source": e.source,
                 "confidence": e.confidence} for e in events]

    def search(self, query: str, limit: int = 50) -> List[Dict]:
        q = f"%{query.lower()}%"
        with _db() as con:
            rows = con.execute(
                """SELECT event_id, category, title, description, date_str, source, confidence
                   FROM personal_events
                   WHERE lower(title) LIKE ? OR lower(description) LIKE ? OR lower(tags) LIKE ?
                   ORDER BY ts DESC LIMIT ?""",
                (q, q, q, limit)).fetchall()
        return [{"event_id": r[0], "category": r[1], "title": r[2],
                 "description": r[3], "date": r[4], "source": r[5],
                 "confidence": r[6]} for r in rows]

    def summary(self) -> Dict:
        with _db() as con:
            total = con.execute("SELECT COUNT(*) FROM personal_events").fetchone()[0]
            by_cat = con.execute(
                "SELECT category, COUNT(*) FROM personal_events GROUP BY category").fetchall()
        return {"total_events": total,
                "by_category": {r[0]: r[1] for r in by_cat},
                "subject": TWIN_NAME}

# ── ConnectedPartyTracker ─────────────────────────────────────────────────────

class ConnectedPartyTracker:
    """Tracks people, companies, devices, and networks connected to Chase."""

    def add_party(self, name: str, relation: str, role: str = "known",
                  ip: str = "", mac: str = "", notes: str = "",
                  risk_level: str = "low", tags: List[str] = None) -> ConnectedParty:
        party = ConnectedParty(
            party_id=_uid("party_"), name=name, relation=relation, role=role,
            ip_hash=_hash(ip) if ip else "",
            mac_hash=_hash(mac) if mac else "",
            notes=notes, risk_level=risk_level,
            tags=tags or [])
        with _lock:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO connected_parties VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (party.party_id, party.name, party.relation, party.role,
                     party.ip_hash, party.mac_hash, party.notes, party.risk_level,
                     json.dumps(party.tags), party.first_seen, party.last_seen))
        return party

    def update_last_seen(self, party_id: str) -> bool:
        with _db() as con:
            cur = con.execute(
                "UPDATE connected_parties SET last_seen=? WHERE party_id=?",
                (time.time(), party_id))
        return cur.rowcount > 0

    def get_parties(self, relation: str = None, risk_level: str = None,
                    limit: int = 100) -> List[Dict]:
        clauses, params = [], []
        if relation:
            clauses.append("relation=?"); params.append(relation)
        if risk_level:
            clauses.append("risk_level=?"); params.append(risk_level)
        params.append(limit)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with _db() as con:
            rows = con.execute(
                f"SELECT * FROM connected_parties {where} ORDER BY last_seen DESC LIMIT ?",
                params).fetchall()
        return [{"party_id": r[0], "name": r[1], "relation": r[2], "role": r[3],
                 "notes": r[6], "risk_level": r[7], "tags": json.loads(r[8] or "[]"),
                 "first_seen": r[9], "last_seen": r[10]} for r in rows]

    def high_risk(self) -> List[Dict]:
        return self.get_parties(risk_level="high") + self.get_parties(risk_level="critical")

    def search(self, query: str) -> List[Dict]:
        q = f"%{query.lower()}%"
        with _db() as con:
            rows = con.execute(
                """SELECT party_id, name, relation, role, notes, risk_level
                   FROM connected_parties
                   WHERE lower(name) LIKE ? OR lower(notes) LIKE ? OR lower(tags) LIKE ?
                   ORDER BY last_seen DESC LIMIT 50""",
                (q, q, q)).fetchall()
        return [{"party_id": r[0], "name": r[1], "relation": r[2],
                 "role": r[3], "notes": r[4], "risk_level": r[5]} for r in rows]

    def network_map(self) -> Dict:
        with _db() as con:
            by_relation = con.execute(
                "SELECT relation, COUNT(*) FROM connected_parties GROUP BY relation"
            ).fetchall()
            by_risk = con.execute(
                "SELECT risk_level, COUNT(*) FROM connected_parties GROUP BY risk_level"
            ).fetchall()
            total = con.execute("SELECT COUNT(*) FROM connected_parties").fetchone()[0]
        return {"total_parties": total,
                "by_relation": {r[0]: r[1] for r in by_relation},
                "by_risk": {r[0]: r[1] for r in by_risk}}

# ── ThreatActorTracker ────────────────────────────────────────────────────────

class ThreatActorTracker:
    """Defensive tracker — records threat actors targeting Chase (no offensive use)."""

    def add_actor(self, label: str, actor_type: str, attack_vector: str,
                  severity: str = "medium", indicators: List[str] = None,
                  mitigations: List[str] = None, status: str = "active") -> ThreatActor:
        # Hash all IOC indicators so raw data is never stored
        hashed_iocs = [_hash(i) for i in (indicators or [])]
        actor = ThreatActor(
            actor_id=_uid("threat_"), label=label, actor_type=actor_type,
            attack_vector=attack_vector, severity=severity,
            indicators=hashed_iocs, mitigations=mitigations or [],
            status=status)
        with _lock:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO threat_actors VALUES (?,?,?,?,?,?,?,?,?)",
                    (actor.actor_id, actor.label, actor.actor_type, actor.attack_vector,
                     actor.severity, json.dumps(actor.indicators),
                     json.dumps(actor.mitigations), actor.status, actor.ts))
        return actor

    def get_actors(self, status: str = None, severity: str = None,
                   limit: int = 100) -> List[Dict]:
        clauses, params = [], []
        if status:
            clauses.append("status=?"); params.append(status)
        if severity:
            clauses.append("severity=?"); params.append(severity)
        params.append(limit)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with _db() as con:
            rows = con.execute(
                f"SELECT * FROM threat_actors {where} ORDER BY ts DESC LIMIT ?",
                params).fetchall()
        return [{"actor_id": r[0], "label": r[1], "actor_type": r[2],
                 "attack_vector": r[3], "severity": r[4],
                 "mitigations": json.loads(r[6] or "[]"),
                 "status": r[7]} for r in rows]

    def active_threats(self) -> List[Dict]:
        return self.get_actors(status="active")

    def mitigate(self, actor_id: str, mitigation: str) -> bool:
        with _db() as con:
            row = con.execute(
                "SELECT mitigations FROM threat_actors WHERE actor_id=?",
                (actor_id,)).fetchone()
            if not row:
                return False
            mits = json.loads(row[0] or "[]")
            mits.append(mitigation)
            con.execute(
                "UPDATE threat_actors SET mitigations=? WHERE actor_id=?",
                (json.dumps(mits), actor_id))
        return True

    def resolve(self, actor_id: str) -> bool:
        with _db() as con:
            cur = con.execute(
                "UPDATE threat_actors SET status='mitigated' WHERE actor_id=?",
                (actor_id,))
        return cur.rowcount > 0

    def threat_summary(self) -> Dict:
        with _db() as con:
            by_sev = con.execute(
                "SELECT severity, COUNT(*) FROM threat_actors GROUP BY severity"
            ).fetchall()
            by_vec = con.execute(
                "SELECT attack_vector, COUNT(*) FROM threat_actors GROUP BY attack_vector"
            ).fetchall()
            active = con.execute(
                "SELECT COUNT(*) FROM threat_actors WHERE status='active'"
            ).fetchone()[0]
        return {"active_threats": active,
                "by_severity": {r[0]: r[1] for r in by_sev},
                "by_vector": {r[0]: r[1] for r in by_vec}}

# ── CompanyIntelligence ───────────────────────────────────────────────────────

class CompanyIntelligence:
    """Tracks companies connected to Chase via DNA, biometric, financial, or network links."""

    def add_company(self, name: str, domain: str, category: str,
                    connection: str, jurisdiction: str = "US",
                    notes: str = "", risk_level: str = "medium") -> CompanyRecord:
        rec = CompanyRecord(
            company_id=_uid("co_"), name=name, domain=domain,
            category=category, connection=connection,
            jurisdiction=jurisdiction, notes=notes, risk_level=risk_level)
        with _lock:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO company_records VALUES (?,?,?,?,?,?,?,?,?)",
                    (rec.company_id, rec.name, rec.domain, rec.category,
                     rec.connection, rec.jurisdiction, rec.notes,
                     rec.risk_level, rec.ts))
        return rec

    def get_companies(self, category: str = None, connection: str = None,
                      limit: int = 100) -> List[Dict]:
        clauses, params = [], []
        if category:
            clauses.append("category=?"); params.append(category)
        if connection:
            clauses.append("connection LIKE ?"); params.append(f"%{connection}%")
        params.append(limit)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with _db() as con:
            rows = con.execute(
                f"SELECT * FROM company_records {where} ORDER BY ts DESC LIMIT ?",
                params).fetchall()
        return [{"company_id": r[0], "name": r[1], "domain": r[2],
                 "category": r[3], "connection": r[4], "jurisdiction": r[5],
                 "notes": r[6], "risk_level": r[7]} for r in rows]

    def dna_connected(self) -> List[Dict]:
        return self.get_companies(connection="uses-dna")

    def biometric_connected(self) -> List[Dict]:
        return self.get_companies(connection="uses-biometric")

    def search(self, query: str) -> List[Dict]:
        q = f"%{query.lower()}%"
        with _db() as con:
            rows = con.execute(
                """SELECT company_id, name, domain, category, connection, risk_level, notes
                   FROM company_records
                   WHERE lower(name) LIKE ? OR lower(domain) LIKE ? OR lower(notes) LIKE ?
                   ORDER BY ts DESC LIMIT 50""",
                (q, q, q)).fetchall()
        return [{"company_id": r[0], "name": r[1], "domain": r[2],
                 "category": r[3], "connection": r[4],
                 "risk_level": r[5], "notes": r[6]} for r in rows]

    def company_map(self) -> Dict:
        with _db() as con:
            by_cat = con.execute(
                "SELECT category, COUNT(*) FROM company_records GROUP BY category"
            ).fetchall()
            by_conn = con.execute(
                "SELECT connection, COUNT(*) FROM company_records GROUP BY connection"
            ).fetchall()
            total = con.execute("SELECT COUNT(*) FROM company_records").fetchone()[0]
        return {"total_companies": total,
                "by_category": {r[0]: r[1] for r in by_cat},
                "by_connection": {r[0]: r[1] for r in by_conn}}

# ── FinanceTracker ────────────────────────────────────────────────────────────

class FinanceTracker:
    """Tracks financial records, assets, liabilities, and transactions for Chase."""

    def add_record(self, category: str, label: str, amount: float,
                   currency: str = "USD", counterparty: str = "",
                   date_str: str = "", account: str = "",
                   notes: str = "", tags: List[str] = None) -> FinanceRecord:
        rec = FinanceRecord(
            record_id=_uid("fin_"),
            category=category, label=label,
            amount_cents=int(round(amount * 100)),
            currency=currency, counterparty=counterparty,
            date_str=date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            account_hash=_hash(account) if account else "",
            notes=notes, tags=tags or [])
        with _lock:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO finance_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (rec.record_id, rec.category, rec.label, rec.amount_cents,
                     rec.currency, rec.counterparty, rec.date_str, rec.account_hash,
                     rec.notes, json.dumps(rec.tags), rec.ts))
        return rec

    def get_records(self, category: str = None, currency: str = None,
                    date_from: str = None, date_to: str = None,
                    limit: int = 200) -> List[Dict]:
        clauses, params = [], []
        if category:
            clauses.append("category=?"); params.append(category)
        if currency:
            clauses.append("currency=?"); params.append(currency)
        if date_from:
            clauses.append("date_str>=?"); params.append(date_from)
        if date_to:
            clauses.append("date_str<=?"); params.append(date_to)
        params.append(limit)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with _db() as con:
            rows = con.execute(
                f"SELECT * FROM finance_records {where} ORDER BY date_str DESC LIMIT ?",
                params).fetchall()
        return [{"record_id": r[0], "category": r[1], "label": r[2],
                 "amount": r[3] / 100.0, "currency": r[4],
                 "counterparty": r[5], "date": r[6],
                 "notes": r[8], "tags": json.loads(r[9] or "[]")} for r in rows]

    def balance(self, currency: str = "USD") -> Dict:
        with _db() as con:
            assets = con.execute(
                "SELECT SUM(amount_cents) FROM finance_records WHERE category='asset' AND currency=?",
                (currency,)).fetchone()[0] or 0
            liabilities = con.execute(
                "SELECT SUM(amount_cents) FROM finance_records WHERE category='liability' AND currency=?",
                (currency,)).fetchone()[0] or 0
            income = con.execute(
                "SELECT SUM(amount_cents) FROM finance_records WHERE category='income' AND currency=?",
                (currency,)).fetchone()[0] or 0
            expenses = con.execute(
                "SELECT SUM(amount_cents) FROM finance_records WHERE category='expense' AND currency=?",
                (currency,)).fetchone()[0] or 0
        return {
            "currency": currency,
            "assets":      assets / 100.0,
            "liabilities": liabilities / 100.0,
            "net_worth":   (assets - liabilities) / 100.0,
            "income":      income / 100.0,
            "expenses":    expenses / 100.0,
            "cash_flow":   (income - expenses) / 100.0
        }

    def by_counterparty(self, limit: int = 20) -> List[Dict]:
        with _db() as con:
            rows = con.execute(
                """SELECT counterparty, currency, SUM(amount_cents), COUNT(*)
                   FROM finance_records
                   WHERE counterparty != ''
                   GROUP BY counterparty, currency
                   ORDER BY ABS(SUM(amount_cents)) DESC LIMIT ?""",
                (limit,)).fetchall()
        return [{"counterparty": r[0], "currency": r[1],
                 "total": r[2] / 100.0, "count": r[3]} for r in rows]

    def crypto_holdings(self) -> List[Dict]:
        with _db() as con:
            rows = con.execute(
                """SELECT currency, SUM(amount_cents), COUNT(*)
                   FROM finance_records
                   WHERE category='asset' AND currency NOT IN ('USD','EUR','GBP','AUD','CAD')
                   GROUP BY currency ORDER BY SUM(amount_cents) DESC""").fetchall()
        return [{"currency": r[0], "total": r[1] / 100.0, "entries": r[2]} for r in rows]

    def monthly_summary(self, months: int = 6) -> List[Dict]:
        with _db() as con:
            rows = con.execute(
                """SELECT substr(date_str,1,7) as month,
                          category,
                          currency,
                          SUM(amount_cents)
                   FROM finance_records
                   GROUP BY month, category, currency
                   ORDER BY month DESC LIMIT ?""",
                (months * 10,)).fetchall()
        result: Dict[str, Dict] = {}
        for r in rows:
            key = r[0]
            if key not in result:
                result[key] = {"month": key, "income": 0, "expenses": 0, "assets": 0}
            if r[1] == "income":
                result[key]["income"] += r[3] / 100.0
            elif r[1] == "expense":
                result[key]["expenses"] += r[3] / 100.0
            elif r[1] == "asset":
                result[key]["assets"] += r[3] / 100.0
        return list(result.values())

# ── PublishedIntelligence ─────────────────────────────────────────────────────

class PublishedIntelligence:
    """Stores published research, public records, and OSINT notes about Chase and connections."""

    def add_note(self, source: str, title: str, snippet: str,
                 subject_match: float = 1.0, category: str = "personal") -> PublishedNote:
        note = PublishedNote(
            note_id=_uid("note_"), source=source, title=title,
            snippet=snippet[:2000],
            subject_match=min(1.0, max(0.0, subject_match)),
            category=category)
        with _lock:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO published_notes VALUES (?,?,?,?,?,?,?)",
                    (note.note_id, note.source, note.title, note.snippet,
                     note.subject_match, note.category, note.retrieved_at))
        return note

    def get_notes(self, category: str = None, min_match: float = 0.0,
                  limit: int = 100) -> List[Dict]:
        clauses, params = [], []
        if category:
            clauses.append("category=?"); params.append(category)
        if min_match > 0:
            clauses.append("subject_match>=?"); params.append(min_match)
        params.append(limit)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with _db() as con:
            rows = con.execute(
                f"SELECT * FROM published_notes {where} ORDER BY subject_match DESC, retrieved_at DESC LIMIT ?",
                params).fetchall()
        return [{"note_id": r[0], "source": r[1], "title": r[2],
                 "snippet": r[3], "match": r[4],
                 "category": r[5], "retrieved": r[6]} for r in rows]

    def search(self, query: str, limit: int = 50) -> List[Dict]:
        q = f"%{query.lower()}%"
        with _db() as con:
            rows = con.execute(
                """SELECT note_id, source, title, snippet, subject_match, category
                   FROM published_notes
                   WHERE lower(title) LIKE ? OR lower(snippet) LIKE ? OR lower(source) LIKE ?
                   ORDER BY subject_match DESC LIMIT ?""",
                (q, q, q, limit)).fetchall()
        return [{"note_id": r[0], "source": r[1], "title": r[2],
                 "snippet": r[3][:300], "match": r[4], "category": r[5]} for r in rows]

    def research_probe(self, subject: str) -> Dict:
        """Passive DNS/HTTP probe to check if a domain is reachable (read-only)."""
        assert TX_LICENSED is False
        result = {"subject": subject, "checks": []}
        try:
            ip = socket.gethostbyname(subject)
            result["checks"].append({"check": "dns_resolve", "status": "ok", "ip_hash": _hash(ip)})
        except Exception as e:
            result["checks"].append({"check": "dns_resolve", "status": "failed", "error": str(e)})
        try:
            req = urllib.request.Request(
                f"https://{subject}",
                headers={"User-Agent": "RabbitOS-Intel/1.0"},
                method="HEAD")
            with urllib.request.urlopen(req, timeout=8) as resp:
                result["checks"].append({
                    "check": "https_head", "status": str(resp.status),
                    "server": resp.headers.get("Server", "")[:50]})
        except Exception as e:
            result["checks"].append({"check": "https_head", "status": "failed", "error": str(e)[:80]})
        return result

# ── DataAssetTracker ──────────────────────────────────────────────────────────

class DataAssetTracker:
    """Tracks data assets belonging to or about Chase — where they are and their status."""

    def add_asset(self, category: str, label: str, custodian: str,
                  location: str, status: str = "unknown",
                  recovery_url: str = "", notes: str = "") -> DataAsset:
        asset = DataAsset(
            asset_id=_uid("asset_"), category=category, label=label,
            custodian=custodian, location=location, status=status,
            recovery_url=recovery_url, notes=notes)
        with _lock:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO data_assets VALUES (?,?,?,?,?,?,?,?,?)",
                    (asset.asset_id, asset.category, asset.label, asset.custodian,
                     asset.location, asset.status, asset.recovery_url,
                     asset.notes, asset.ts))
        return asset

    def get_assets(self, category: str = None, status: str = None,
                   limit: int = 100) -> List[Dict]:
        clauses, params = [], []
        if category:
            clauses.append("category=?"); params.append(category)
        if status:
            clauses.append("status=?"); params.append(status)
        params.append(limit)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with _db() as con:
            rows = con.execute(
                f"SELECT * FROM data_assets {where} ORDER BY ts DESC LIMIT ?",
                params).fetchall()
        return [{"asset_id": r[0], "category": r[1], "label": r[2],
                 "custodian": r[3], "location": r[4], "status": r[5],
                 "recovery_url": r[6], "notes": r[7]} for r in rows]

    def exposed(self) -> List[Dict]:
        return self.get_assets(status="exposed") + self.get_assets(status="compromised")

    def asset_summary(self) -> Dict:
        with _db() as con:
            by_status = con.execute(
                "SELECT status, COUNT(*) FROM data_assets GROUP BY status"
            ).fetchall()
            by_cat = con.execute(
                "SELECT category, COUNT(*) FROM data_assets GROUP BY category"
            ).fetchall()
        return {"by_status": {r[0]: r[1] for r in by_status},
                "by_category": {r[0]: r[1] for r in by_cat}}

# ── IntelOrchestrator ─────────────────────────────────────────────────────────

class IntelOrchestrator:
    """Top-level singleton combining all intel modules into a unified view."""

    _instance: Optional["IntelOrchestrator"] = None

    def __init__(self):
        self.personal  = PersonalDataStore()
        self.parties   = ConnectedPartyTracker()
        self.threats   = ThreatActorTracker()
        self.companies = CompanyIntelligence()
        self.finance   = FinanceTracker()
        self.published = PublishedIntelligence()
        self.assets    = DataAssetTracker()

    @classmethod
    def get(cls) -> "IntelOrchestrator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def full_profile(self) -> Dict:
        return {
            "subject":        TWIN_NAME,
            "twin_uuid":      TWIN_UUID,
            "personal":       self.personal.summary(),
            "network":        self.parties.network_map(),
            "threats":        self.threats.threat_summary(),
            "companies":      self.companies.company_map(),
            "finance_usd":    self.finance.balance("USD"),
            "assets":         self.assets.asset_summary(),
            "shows_dna_root": False,
            "tx_licensed":    False,
        }

    def global_search(self, query: str) -> Dict:
        return {
            "events":    self.personal.search(query),
            "parties":   self.parties.search(query),
            "companies": self.companies.search(query),
            "published": self.published.search(query),
        }

def get_intel() -> IntelOrchestrator:
    return IntelOrchestrator.get()

# ── Tool definitions ──────────────────────────────────────────────────────────

INTEL_TOOLS: List[Dict] = [
    # Personal history
    {"name": "intel_add_event",
     "description": "Add a personal history event for Chase Allen Ringquist.",
     "input_schema": {"type": "object", "required": ["category", "title", "description", "date_str"],
                      "properties": {
                          "category":    {"type": "string"},
                          "title":       {"type": "string"},
                          "description": {"type": "string"},
                          "date_str":    {"type": "string"},
                          "source":      {"type": "string"},
                          "confidence":  {"type": "number"},
                          "tags":        {"type": "array", "items": {"type": "string"}}}}},
    {"name": "intel_get_events",
     "description": "Get personal history events for Chase, optionally filtered by category.",
     "input_schema": {"type": "object", "properties": {
         "category": {"type": "string"},
         "limit":    {"type": "integer"}}}},
    {"name": "intel_timeline",
     "description": "Return chronological timeline of Chase Allen Ringquist personal events.",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "intel_search_events",
     "description": "Full-text search across all personal events.",
     "input_schema": {"type": "object", "required": ["query"],
                      "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "intel_personal_summary",
     "description": "Summary of all stored personal data for Chase Allen Ringquist.",
     "input_schema": {"type": "object", "properties": {}}},

    # Connected parties
    {"name": "intel_add_party",
     "description": "Add a connected party (person, company, device, or network) linked to Chase.",
     "input_schema": {"type": "object", "required": ["name", "relation"],
                      "properties": {
                          "name":       {"type": "string"},
                          "relation":   {"type": "string", "enum": ["person","company","device","network","org","attacker"]},
                          "role":       {"type": "string"},
                          "ip":         {"type": "string"},
                          "mac":        {"type": "string"},
                          "notes":      {"type": "string"},
                          "risk_level": {"type": "string"},
                          "tags":       {"type": "array", "items": {"type": "string"}}}}},
    {"name": "intel_get_parties",
     "description": "Get connected parties, optionally filtered by relation or risk level.",
     "input_schema": {"type": "object", "properties": {
         "relation":   {"type": "string"},
         "risk_level": {"type": "string"},
         "limit":      {"type": "integer"}}}},
    {"name": "intel_high_risk_parties",
     "description": "Get all high and critical risk connected parties.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "intel_search_parties",
     "description": "Search connected parties by name or notes.",
     "input_schema": {"type": "object", "required": ["query"],
                      "properties": {"query": {"type": "string"}}}},
    {"name": "intel_network_map",
     "description": "Summary network map of all connected parties by relation and risk.",
     "input_schema": {"type": "object", "properties": {}}},

    # Threat actors (defensive)
    {"name": "intel_add_threat",
     "description": "Record a threat actor targeting Chase (defensive — no offensive data stored).",
     "input_schema": {"type": "object", "required": ["label", "actor_type", "attack_vector"],
                      "properties": {
                          "label":        {"type": "string"},
                          "actor_type":   {"type": "string"},
                          "attack_vector":{"type": "string"},
                          "severity":     {"type": "string"},
                          "indicators":   {"type": "array", "items": {"type": "string"}},
                          "mitigations":  {"type": "array", "items": {"type": "string"}},
                          "status":       {"type": "string"}}}},
    {"name": "intel_get_threats",
     "description": "Get threat actors, optionally filtered by status or severity.",
     "input_schema": {"type": "object", "properties": {
         "status":   {"type": "string"},
         "severity": {"type": "string"},
         "limit":    {"type": "integer"}}}},
    {"name": "intel_active_threats",
     "description": "Get all currently active threat actors.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "intel_mitigate_threat",
     "description": "Add a mitigation note to a threat actor record.",
     "input_schema": {"type": "object", "required": ["actor_id", "mitigation"],
                      "properties": {
                          "actor_id":   {"type": "string"},
                          "mitigation": {"type": "string"}}}},
    {"name": "intel_resolve_threat",
     "description": "Mark a threat actor as mitigated/resolved.",
     "input_schema": {"type": "object", "required": ["actor_id"],
                      "properties": {"actor_id": {"type": "string"}}}},
    {"name": "intel_threat_summary",
     "description": "Threat actor summary by severity and attack vector.",
     "input_schema": {"type": "object", "properties": {}}},

    # Company intelligence
    {"name": "intel_add_company",
     "description": "Add a company connected to Chase via DNA, biometric, financial, or network links.",
     "input_schema": {"type": "object", "required": ["name", "domain", "category", "connection"],
                      "properties": {
                          "name":         {"type": "string"},
                          "domain":       {"type": "string"},
                          "category":     {"type": "string"},
                          "connection":   {"type": "string"},
                          "jurisdiction": {"type": "string"},
                          "notes":        {"type": "string"},
                          "risk_level":   {"type": "string"}}}},
    {"name": "intel_get_companies",
     "description": "Get company records, optionally filtered by category or connection type.",
     "input_schema": {"type": "object", "properties": {
         "category":   {"type": "string"},
         "connection": {"type": "string"},
         "limit":      {"type": "integer"}}}},
    {"name": "intel_dna_companies",
     "description": "Get companies known to use or hold Chase's DNA data.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "intel_biometric_companies",
     "description": "Get companies known to use or hold Chase's biometric data.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "intel_search_companies",
     "description": "Search company records by name, domain, or notes.",
     "input_schema": {"type": "object", "required": ["query"],
                      "properties": {"query": {"type": "string"}}}},
    {"name": "intel_company_map",
     "description": "Summary map of all company records by category and connection type.",
     "input_schema": {"type": "object", "properties": {}}},

    # Finance tracker
    {"name": "intel_add_finance",
     "description": "Add a financial record (income, expense, asset, liability, transaction, or crypto).",
     "input_schema": {"type": "object", "required": ["category", "label", "amount"],
                      "properties": {
                          "category":     {"type": "string"},
                          "label":        {"type": "string"},
                          "amount":       {"type": "number"},
                          "currency":     {"type": "string"},
                          "counterparty": {"type": "string"},
                          "date_str":     {"type": "string"},
                          "account":      {"type": "string"},
                          "notes":        {"type": "string"},
                          "tags":         {"type": "array", "items": {"type": "string"}}}}},
    {"name": "intel_get_finance",
     "description": "Get financial records, optionally filtered by category, currency, or date range.",
     "input_schema": {"type": "object", "properties": {
         "category":  {"type": "string"},
         "currency":  {"type": "string"},
         "date_from": {"type": "string"},
         "date_to":   {"type": "string"},
         "limit":     {"type": "integer"}}}},
    {"name": "intel_finance_balance",
     "description": "Net worth and cash flow balance sheet for a given currency.",
     "input_schema": {"type": "object", "properties": {"currency": {"type": "string"}}}},
    {"name": "intel_finance_by_counterparty",
     "description": "Financial totals grouped by counterparty.",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "intel_crypto_holdings",
     "description": "Crypto asset holdings summary.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "intel_monthly_summary",
     "description": "Monthly income/expense/asset summary for the last N months.",
     "input_schema": {"type": "object", "properties": {"months": {"type": "integer"}}}},

    # Published intelligence
    {"name": "intel_add_published_note",
     "description": "Store a published note, public record, or OSINT finding related to Chase or connections.",
     "input_schema": {"type": "object", "required": ["source", "title", "snippet"],
                      "properties": {
                          "source":        {"type": "string"},
                          "title":         {"type": "string"},
                          "snippet":       {"type": "string"},
                          "subject_match": {"type": "number"},
                          "category":      {"type": "string"}}}},
    {"name": "intel_get_published_notes",
     "description": "Get published notes/OSINT findings, optionally filtered.",
     "input_schema": {"type": "object", "properties": {
         "category":  {"type": "string"},
         "min_match": {"type": "number"},
         "limit":     {"type": "integer"}}}},
    {"name": "intel_search_published",
     "description": "Search published notes and OSINT findings by keyword.",
     "input_schema": {"type": "object", "required": ["query"],
                      "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "intel_research_probe",
     "description": "Passive DNS + HTTPS HEAD probe of a domain (read-only, no data submitted).",
     "input_schema": {"type": "object", "required": ["subject"],
                      "properties": {"subject": {"type": "string"}}}},

    # Data assets
    {"name": "intel_add_asset",
     "description": "Track a data asset belonging to or about Chase (documents, credentials, biometric data, etc.).",
     "input_schema": {"type": "object", "required": ["category", "label", "custodian", "location"],
                      "properties": {
                          "category":     {"type": "string"},
                          "label":        {"type": "string"},
                          "custodian":    {"type": "string"},
                          "location":     {"type": "string"},
                          "status":       {"type": "string"},
                          "recovery_url": {"type": "string"},
                          "notes":        {"type": "string"}}}},
    {"name": "intel_get_assets",
     "description": "Get tracked data assets, optionally filtered by category or status.",
     "input_schema": {"type": "object", "properties": {
         "category": {"type": "string"},
         "status":   {"type": "string"},
         "limit":    {"type": "integer"}}}},
    {"name": "intel_exposed_assets",
     "description": "Get all data assets marked as exposed or compromised.",
     "input_schema": {"type": "object", "properties": {}}},

    # Unified
    {"name": "intel_full_profile",
     "description": "Complete unified intelligence profile for Chase Allen Ringquist.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "intel_global_search",
     "description": "Search across all intel modules — events, parties, companies, and published notes.",
     "input_schema": {"type": "object", "required": ["query"],
                      "properties": {"query": {"type": "string"}}}},
]

# ── Dispatcher ────────────────────────────────────────────────────────────────

def dispatch_intel_tool(name: str, inputs: Dict,
                        supabase_url: str = "",
                        service_key: str = "") -> Any:
    i   = get_intel()
    inp = inputs or {}

    # Personal history
    if name == "intel_add_event":
        return asdict(i.personal.add_event(
            inp["category"], inp["title"], inp["description"], inp["date_str"],
            inp.get("source", "manual"), inp.get("confidence", 1.0), inp.get("tags")))
    elif name == "intel_get_events":
        return i.personal.get_events(inp.get("category"), inp.get("limit", 100))
    elif name == "intel_timeline":
        return i.personal.timeline(inp.get("limit", 200))
    elif name == "intel_search_events":
        return i.personal.search(inp["query"], inp.get("limit", 50))
    elif name == "intel_personal_summary":
        return i.personal.summary()

    # Connected parties
    elif name == "intel_add_party":
        return asdict(i.parties.add_party(
            inp["name"], inp["relation"], inp.get("role", "known"),
            inp.get("ip", ""), inp.get("mac", ""),
            inp.get("notes", ""), inp.get("risk_level", "low"),
            inp.get("tags")))
    elif name == "intel_get_parties":
        return i.parties.get_parties(
            inp.get("relation"), inp.get("risk_level"), inp.get("limit", 100))
    elif name == "intel_high_risk_parties":
        return i.parties.high_risk()
    elif name == "intel_search_parties":
        return i.parties.search(inp["query"])
    elif name == "intel_network_map":
        return i.parties.network_map()

    # Threats
    elif name == "intel_add_threat":
        return asdict(i.threats.add_actor(
            inp["label"], inp["actor_type"], inp["attack_vector"],
            inp.get("severity", "medium"), inp.get("indicators"),
            inp.get("mitigations"), inp.get("status", "active")))
    elif name == "intel_get_threats":
        return i.threats.get_actors(
            inp.get("status"), inp.get("severity"), inp.get("limit", 100))
    elif name == "intel_active_threats":
        return i.threats.active_threats()
    elif name == "intel_mitigate_threat":
        return {"ok": i.threats.mitigate(inp["actor_id"], inp["mitigation"])}
    elif name == "intel_resolve_threat":
        return {"ok": i.threats.resolve(inp["actor_id"])}
    elif name == "intel_threat_summary":
        return i.threats.threat_summary()

    # Companies
    elif name == "intel_add_company":
        return asdict(i.companies.add_company(
            inp["name"], inp["domain"], inp["category"], inp["connection"],
            inp.get("jurisdiction", "US"), inp.get("notes", ""),
            inp.get("risk_level", "medium")))
    elif name == "intel_get_companies":
        return i.companies.get_companies(
            inp.get("category"), inp.get("connection"), inp.get("limit", 100))
    elif name == "intel_dna_companies":
        return i.companies.dna_connected()
    elif name == "intel_biometric_companies":
        return i.companies.biometric_connected()
    elif name == "intel_search_companies":
        return i.companies.search(inp["query"])
    elif name == "intel_company_map":
        return i.companies.company_map()

    # Finance
    elif name == "intel_add_finance":
        return asdict(i.finance.add_record(
            inp["category"], inp["label"], float(inp["amount"]),
            inp.get("currency", "USD"), inp.get("counterparty", ""),
            inp.get("date_str", ""), inp.get("account", ""),
            inp.get("notes", ""), inp.get("tags")))
    elif name == "intel_get_finance":
        return i.finance.get_records(
            inp.get("category"), inp.get("currency"),
            inp.get("date_from"), inp.get("date_to"), inp.get("limit", 200))
    elif name == "intel_finance_balance":
        return i.finance.balance(inp.get("currency", "USD"))
    elif name == "intel_finance_by_counterparty":
        return i.finance.by_counterparty(inp.get("limit", 20))
    elif name == "intel_crypto_holdings":
        return i.finance.crypto_holdings()
    elif name == "intel_monthly_summary":
        return i.finance.monthly_summary(inp.get("months", 6))

    # Published intel
    elif name == "intel_add_published_note":
        return asdict(i.published.add_note(
            inp["source"], inp["title"], inp["snippet"],
            inp.get("subject_match", 1.0), inp.get("category", "personal")))
    elif name == "intel_get_published_notes":
        return i.published.get_notes(
            inp.get("category"), inp.get("min_match", 0.0), inp.get("limit", 100))
    elif name == "intel_search_published":
        return i.published.search(inp["query"], inp.get("limit", 50))
    elif name == "intel_research_probe":
        return i.published.research_probe(inp["subject"])

    # Data assets
    elif name == "intel_add_asset":
        return asdict(i.assets.add_asset(
            inp["category"], inp["label"], inp["custodian"],
            inp["location"], inp.get("status", "unknown"),
            inp.get("recovery_url", ""), inp.get("notes", "")))
    elif name == "intel_get_assets":
        return i.assets.get_assets(
            inp.get("category"), inp.get("status"), inp.get("limit", 100))
    elif name == "intel_exposed_assets":
        return i.assets.exposed()

    # Unified
    elif name == "intel_full_profile":
        return i.full_profile()
    elif name == "intel_global_search":
        return i.global_search(inp["query"])

    return {"error": f"Unknown intel tool: {name}"}
