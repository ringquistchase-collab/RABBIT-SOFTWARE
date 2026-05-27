#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_datastore.py — RabbitOS Unified Datastore (Supabase-Free)
=================================================================
Drop-in replacement for all Supabase REST calls.

Storage layers (in priority order):
  1. SQLite      — always-on, fully offline, primary truth
  2. GitHub      — cloud sync via Git Trees API (fork already wired)
  3. UDP mesh    — real-time broadcast to LAN peers
  4. JSON files  — human-readable local snapshots

Internet fetch (no auth required):
  arXiv API       — research papers on body-coupled RF, EEG, HRV
  PubMed E-utils  — biomedical literature
  Wikipedia REST  — technology articles
  GitHub raw      — datasets and code

No Supabase. No service_role key. No cloud dependency.
"""

from __future__ import annotations
import os, sys, json, time, sqlite3, threading, hashlib, base64
import urllib.request, urllib.error, urllib.parse, socket, struct
from datetime import datetime, timezone
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple

TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"
GITHUB_API = "https://api.github.com"
REPO       = "therealsickonechase-bit/RABBIT-SOFTWARE"
DB_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_data.db")
SNAP_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_cache")
UDP_PORT   = 9010   # datastore sync port (separate from morse 9009)

# ─── internet sources (no auth, all public) ──────────────────────────────────
ARXIV_URL   = "https://export.arxiv.org/api/query"
PUBMED_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH= "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
WIKI_URL    = "https://en.wikipedia.org/api/rest_v1/page/summary"

# Search topics relevant to the system
RESEARCH_TOPICS = [
    "body-coupled communication microwave",
    "digital twin biometric EEG HRV",
    "software defined radio mesh network",
    "survival radio communication AM FM",
    "body area network RF propagation tissue",
    "wearable biosensor galvanic skin response",
    "cortisol measurement biosensor wearable",
    "frequency hopping spread spectrum survival",
]

# ─── schema ───────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS kv_store (
    ns         TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT,
    updated_at TEXT,
    PRIMARY KEY (ns, key)
);
CREATE TABLE IF NOT EXISTS research (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT,
    topic      TEXT,
    title      TEXT,
    summary    TEXT,
    url        TEXT,
    fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT,
    payload    TEXT,
    origin     TEXT,
    ts         TEXT
);
CREATE TABLE IF NOT EXISTS sync_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    method     TEXT,
    target     TEXT,
    rows       INTEGER,
    ok         BOOLEAN,
    ts         TEXT
);
CREATE TABLE IF NOT EXISTS topology (
    node_id    TEXT PRIMARY KEY,
    freq_hz    REAL,
    role       TEXT,
    x          REAL,
    y          REAL,
    z          REAL,
    links      TEXT,
    ts         TEXT
);
"""

# ─── SQLite layer ─────────────────────────────────────────────────────────────

class SQLiteLayer:
    def __init__(self, db_path: str = DB_PATH):
        self._db = db_path
        os.makedirs(SNAP_DIR, exist_ok=True)
        con = sqlite3.connect(db_path)
        con.executescript(SCHEMA)
        con.commit()
        con.close()

    def _con(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db, timeout=10)

    def put(self, ns: str, key: str, value: Any) -> bool:
        try:
            con = self._con()
            con.execute(
                "INSERT OR REPLACE INTO kv_store(ns,key,value,updated_at) VALUES(?,?,?,?)",
                (ns, key, json.dumps(value),
                 datetime.now(timezone.utc).isoformat())
            )
            con.commit()
            con.close()
            return True
        except Exception:
            return False

    def get(self, ns: str, key: str) -> Optional[Any]:
        try:
            con = self._con()
            row = con.execute(
                "SELECT value FROM kv_store WHERE ns=? AND key=?", (ns, key)
            ).fetchone()
            con.close()
            return json.loads(row[0]) if row else None
        except Exception:
            return None

    def list_ns(self, ns: str) -> List[Dict]:
        try:
            con = self._con()
            rows = con.execute(
                "SELECT key,value,updated_at FROM kv_store WHERE ns=? ORDER BY updated_at DESC",
                (ns,)
            ).fetchall()
            con.close()
            return [{"key": r[0], "value": json.loads(r[1]), "ts": r[2]} for r in rows]
        except Exception:
            return []

    def log_event(self, kind: str, payload: Any, origin: str = "local"):
        try:
            con = self._con()
            con.execute(
                "INSERT INTO events(kind,payload,origin,ts) VALUES(?,?,?,?)",
                (kind, json.dumps(payload), origin,
                 datetime.now(timezone.utc).isoformat())
            )
            con.commit()
            con.close()
        except Exception:
            pass

    def save_research(self, source: str, topic: str, title: str,
                      summary: str, url: str):
        try:
            con = self._con()
            con.execute(
                "INSERT INTO research(source,topic,title,summary,url,fetched_at)"
                " VALUES(?,?,?,?,?,?)",
                (source, topic, title[:200], summary[:1000], url,
                 datetime.now(timezone.utc).isoformat())
            )
            con.commit()
            con.close()
        except Exception:
            pass

    def search_research(self, query: str, limit: int = 10) -> List[Dict]:
        try:
            q = f"%{query}%"
            con = self._con()
            rows = con.execute(
                "SELECT source,topic,title,summary,url,fetched_at FROM research"
                " WHERE title LIKE ? OR summary LIKE ? OR topic LIKE ?"
                " ORDER BY fetched_at DESC LIMIT ?",
                (q, q, q, limit)
            ).fetchall()
            con.close()
            return [{"source": r[0], "topic": r[1], "title": r[2],
                     "summary": r[3], "url": r[4], "ts": r[5]} for r in rows]
        except Exception:
            return []

    def save_topology(self, nodes: List[Dict]):
        try:
            con = self._con()
            ts = datetime.now(timezone.utc).isoformat()
            for n in nodes:
                con.execute(
                    "INSERT OR REPLACE INTO topology"
                    "(node_id,freq_hz,role,x,y,z,links,ts) VALUES(?,?,?,?,?,?,?,?)",
                    (n["id"], n.get("freq_hz", 0), n.get("role", ""),
                     n.get("x", 0), n.get("y", 0), n.get("z", 0),
                     json.dumps(n.get("links", [])), ts)
                )
            con.commit()
            con.close()
        except Exception:
            pass

    def count(self) -> Dict[str, int]:
        try:
            con = self._con()
            return {
                "kv":       con.execute("SELECT COUNT(*) FROM kv_store").fetchone()[0],
                "research": con.execute("SELECT COUNT(*) FROM research").fetchone()[0],
                "events":   con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                "topology": con.execute("SELECT COUNT(*) FROM topology").fetchone()[0],
            }
        except Exception:
            return {}
        finally:
            try: con.close()
            except: pass

    def snapshot_json(self) -> str:
        """Write full DB snapshot to JSON file. Returns path."""
        snap = {
            "twin_id": TWIN_UUID,
            "ts":      datetime.now(timezone.utc).isoformat(),
            "kv":      [{"ns": r[0], "key": r[1], "value": json.loads(r[2])}
                        for r in sqlite3.connect(self._db).execute(
                            "SELECT ns,key,value FROM kv_store").fetchall()],
            "research_count":  self.count().get("research", 0),
            "topology_count":  self.count().get("topology", 0),
        }
        fname = f"rabbit_snap_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        path  = os.path.join(SNAP_DIR, fname)
        with open(path, "w") as f:
            json.dump(snap, f, indent=2)
        return path

# ─── GitHub sync layer ────────────────────────────────────────────────────────

class GitHubSyncLayer:
    def __init__(self, token: str = ""):
        self._token = token
        self.available = bool(token)

    def _api(self, url: str, method: str = "GET",
             data: Any = None) -> Tuple[Any, int]:
        import urllib.request, json
        req = urllib.request.Request(
            url, data=json.dumps(data).encode() if data else None,
            method=method,
            headers={
                "Authorization": f"token {self._token}",
                "Content-Type":  "application/json",
                "User-Agent":    "RabbitOS/1.0",
                "Accept":        "application/vnd.github.v3+json",
            }
        )
        try:
            resp = urllib.request.urlopen(req, timeout=12)
            return json.loads(resp.read()), resp.status
        except Exception as e:
            return {"error": str(e)}, 0

    def push_snapshot(self, sq: SQLiteLayer) -> Dict:
        if not self.available:
            return {"ok": False, "reason": "no token"}
        try:
            snap_path = sq.snapshot_json()
            with open(snap_path, "rb") as f:
                content = f.read()

            fname = os.path.basename(snap_path)
            # Get HEAD
            ref, _ = self._api(
                f"{GITHUB_API}/repos/{REPO}/git/ref/heads/main")
            base_sha = ref.get("object", {}).get("sha", "")
            if not base_sha:
                return {"ok": False, "reason": "no base sha"}

            commit_info, _ = self._api(
                f"{GITHUB_API}/repos/{REPO}/git/commits/{base_sha}")
            base_tree = commit_info.get("tree", {}).get("sha", "")

            blob, _ = self._api(
                f"{GITHUB_API}/repos/{REPO}/git/blobs",
                method="POST",
                data={"content": base64.b64encode(content).decode(),
                      "encoding": "base64"}
            )
            blob_sha = blob.get("sha", "")
            if not blob_sha:
                return {"ok": False, "reason": "blob failed"}

            new_tree, _ = self._api(
                f"{GITHUB_API}/repos/{REPO}/git/trees",
                method="POST",
                data={"base_tree": base_tree,
                      "tree": [{"path": f"data/{fname}",
                                 "mode": "100644",
                                 "type": "blob",
                                 "sha": blob_sha}]}
            )
            new_tree_sha = new_tree.get("sha", "")

            ts_str = datetime.now(timezone.utc).isoformat()
            new_commit, _ = self._api(
                f"{GITHUB_API}/repos/{REPO}/git/commits",
                method="POST",
                data={"message": f"RabbitOS datastore snapshot [{ts_str[:19]}]",
                      "tree":    new_tree_sha,
                      "parents": [base_sha]}
            )
            new_sha = new_commit.get("sha", "")
            if not new_sha:
                return {"ok": False, "reason": "commit failed"}

            self._api(
                f"{GITHUB_API}/repos/{REPO}/git/refs/heads/main",
                method="PATCH",
                data={"sha": new_sha, "force": False}
            )
            return {"ok": True, "commit": new_sha[:12], "file": f"data/{fname}"}
        except Exception as e:
            return {"ok": False, "reason": str(e)[:60]}

# ─── internet research fetcher ────────────────────────────────────────────────

class ResearchFetcher:
    """Fetch research from arXiv, PubMed, Wikipedia — no API keys needed."""

    def _get(self, url: str, params: Dict = None, timeout: int = 8) -> str:
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "RabbitOS/1.0"})
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def arxiv(self, query: str, max_results: int = 5) -> List[Dict]:
        import re
        raw = self._get(ARXIV_URL, {
            "search_query": f"all:{urllib.parse.quote(query)}",
            "start": 0,
            "max_results": max_results,
        })
        papers = []
        for entry in re.findall(r"<entry>(.*?)</entry>", raw, re.DOTALL):
            title   = re.findall(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary = re.findall(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            link    = re.findall(r'href="(https://arxiv\.org/abs/[^"]+)"', entry)
            if title and summary:
                papers.append({
                    "source":  "arxiv",
                    "title":   title[0].strip().replace("\n", " "),
                    "summary": summary[0].strip()[:400].replace("\n", " "),
                    "url":     link[0] if link else "",
                })
        return papers

    def pubmed(self, query: str, max_results: int = 5) -> List[Dict]:
        import re
        # Search for IDs
        raw = self._get(PUBMED_URL, {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
        })
        try:
            data = json.loads(raw)
            ids  = data.get("esearchresult", {}).get("idlist", [])
        except Exception:
            return []
        if not ids:
            return []
        # Fetch abstracts
        fetch_raw = self._get(PUBMED_FETCH, {
            "db": "pubmed",
            "id": ",".join(ids[:3]),
            "retmode": "text",
            "rettype": "abstract",
        })
        papers = []
        for block in fetch_raw.split("\n\n"):
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if len(lines) >= 2:
                papers.append({
                    "source":  "pubmed",
                    "title":   lines[0][:200],
                    "summary": " ".join(lines[1:4])[:400],
                    "url":     f"https://pubmed.ncbi.nlm.nih.gov/{ids[0]}/",
                })
        return papers[:max_results]

    def wikipedia(self, topic: str) -> Optional[Dict]:
        slug = topic.replace(" ", "_")
        raw  = self._get(f"{WIKI_URL}/{urllib.parse.quote(slug)}")
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return {
                "source":  "wikipedia",
                "title":   data.get("title", topic),
                "summary": data.get("extract", "")[:500],
                "url":     data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            }
        except Exception:
            return None

    def fetch_all(self, topic: str) -> List[Dict]:
        results = []
        results += self.arxiv(topic, max_results=3)
        results += self.pubmed(topic, max_results=3)
        wiki = self.wikipedia(topic)
        if wiki:
            results.append(wiki)
        return results

# ─── UDP sync layer ───────────────────────────────────────────────────────────

class UDPSyncLayer:
    """Broadcast datastore events to LAN peers. No server needed."""

    def __init__(self, port: int = UDP_PORT):
        self._port = port
        self._peers: List[str] = []

    def broadcast(self, event: Dict):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(1)
            payload = json.dumps({
                "type":  "datastore_event",
                "twin":  TWIN_UUID,
                "event": event,
                "ts":    datetime.now(timezone.utc).isoformat(),
            }).encode()
            s.sendto(payload, ("255.255.255.255", self._port))
            # Also target known peers
            for peer in self._peers:
                try: s.sendto(payload, (peer, self._port))
                except: pass
            s.close()
        except Exception:
            pass

    def add_peer(self, ip: str):
        if ip not in self._peers:
            self._peers.append(ip)

# ─── unified datastore ────────────────────────────────────────────────────────

class RabbitDatastore:
    """
    Unified RabbitOS datastore — no Supabase required.
    SQLite is always primary. GitHub and UDP are async backup.
    """

    def __init__(self, github_token: str = ""):
        self._sq    = SQLiteLayer()
        self._gh    = GitHubSyncLayer(github_token)
        self._udp   = UDPSyncLayer()
        self._fetch = ResearchFetcher()
        self._dirty = 0
        self._lock  = threading.Lock()

    # ── generic KV ────────────────────────────────────────────────────────────
    def put(self, ns: str, key: str, value: Any) -> bool:
        ok = self._sq.put(ns, key, value)
        if ok:
            with self._lock:
                self._dirty += 1
            self._udp.broadcast({"op": "put", "ns": ns, "key": key})
        return ok

    def get(self, ns: str, key: str) -> Optional[Any]:
        return self._sq.get(ns, key)

    def list_ns(self, ns: str) -> List[Dict]:
        return self._sq.list_ns(ns)

    def log_event(self, kind: str, payload: Any, origin: str = "local"):
        self._sq.log_event(kind, payload, origin)
        self._udp.broadcast({"op": "event", "kind": kind})

    # ── research ──────────────────────────────────────────────────────────────
    def learn(self, topic: str, save: bool = True) -> List[Dict]:
        results = self._fetch.fetch_all(topic)
        if save:
            for r in results:
                self._sq.save_research(
                    r.get("source", "?"), topic,
                    r.get("title", ""), r.get("summary", ""),
                    r.get("url", "")
                )
        return results

    def recall(self, query: str, limit: int = 10) -> List[Dict]:
        return self._sq.search_research(query, limit)

    def learn_batch(self, topics: List[str]) -> Dict[str, int]:
        results = {}
        for topic in topics:
            items = self.learn(topic)
            results[topic] = len(items)
            print(f"  [Learn] '{topic[:40]}' -> {len(items)} items")
        return results

    # ── topology ──────────────────────────────────────────────────────────────
    def save_topology(self, nodes: List[Dict]):
        self._sq.save_topology(nodes)

    # ── sync ──────────────────────────────────────────────────────────────────
    def sync_github(self) -> Dict:
        result = self._gh.push_snapshot(self._sq)
        self._sq.log_event("github_sync", result)
        with self._lock:
            self._dirty = 0
        return result

    def add_lan_peer(self, ip: str):
        self._udp.add_peer(ip)

    # ── status ────────────────────────────────────────────────────────────────
    def status(self) -> Dict:
        counts = self._sq.count()
        return {
            "db_path":       self._sq._db,
            "github_avail":  self._gh.available,
            "kv_entries":    counts.get("kv", 0),
            "research_items":counts.get("research", 0),
            "events":        counts.get("events", 0),
            "topology_nodes":counts.get("topology", 0),
            "dirty_writes":  self._dirty,
            "udp_peers":     len(self._udp._peers),
        }


_ds: Optional[RabbitDatastore] = None

def get_datastore(github_token: str = "") -> RabbitDatastore:
    global _ds
    if _ds is None:
        _ds = RabbitDatastore(github_token)
        print(f"[Datastore] SQLite primary: {DB_PATH}")
        print(f"[Datastore] GitHub sync: {'available' if _ds._gh.available else 'no token'}")
    return _ds


# ─── tool manifest ────────────────────────────────────────────────────────────

DATASTORE_TOOLS = [
    {"name": "ds_put",    "description": "Store key-value in local DB",
     "parameters": {"ns": "str", "key": "str", "value": "any"}},
    {"name": "ds_get",    "description": "Retrieve value from local DB",
     "parameters": {"ns": "str", "key": "str"}},
    {"name": "ds_learn",  "description": "Fetch research from arXiv/PubMed/Wikipedia and store offline",
     "parameters": {"topic": "str"}},
    {"name": "ds_recall", "description": "Search stored research offline",
     "parameters": {"query": "str"}},
    {"name": "ds_sync",   "description": "Push DB snapshot to GitHub",
     "parameters": {}},
    {"name": "ds_status", "description": "Datastore health and counts",
     "parameters": {}},
]


if __name__ == "__main__":
    print("RabbitOS Datastore — self-test")
    ds = get_datastore()

    # KV test
    ds.put("test", "boot_ts", datetime.now(timezone.utc).isoformat())
    v = ds.get("test", "boot_ts")
    print(f"  KV round-trip: {v}")

    # Research fetch
    print("  Fetching research: body-coupled communication microwave...")
    items = ds.learn("body-coupled communication microwave")
    for it in items[:3]:
        print(f"    [{it['source']}] {it['title'][:60]}")

    st = ds.status()
    print(f"  Status: kv={st['kv_entries']}  research={st['research_items']}  events={st['events']}")
