#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_bridge.py -- Cross-OS / Cross-LLM / Cross-Network Identity Bridge
RabbitOS -- Chase Allen Ringquist -- UUID ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba

Makes RabbitOS identity/survival accessible to any OS, terminal, LLM, or
network node -- even when RabbitOS is NOT installed.

Interfaces:
  1. REST API server (HTTP port 9013) -- any language/OS can call it
  2. Python RabbitBridge class -- importable from any Python env
  3. LLM tool definitions (JSON schema) -- Claude/GPT/Gemini tool_use compatible
  4. CLI  (python rabbit_bridge.py <cmd>) -- any terminal/shell
  5. IPC socket (127.0.0.1:9016 / Unix socket) -- inter-process
  6. JSON-over-stdin/stdout -- any subprocess integration

Pure Python 3.6+, zero external dependencies.
"""

import hashlib, json, os, socket, sqlite3, sys, time, platform, threading
import http.server, urllib.request, urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# -- Identity constants -------------------------------------------------------
TWIN_UUID      = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT        = "Chase Allen Ringquist"
shows_dna_root = False
_raw           = f"{TWIN_UUID}:{SUBJECT}:RABBIT_DNA_ANCHOR".encode()
DNA_ANCHOR     = hashlib.sha3_512(_raw).hexdigest()
assert not shows_dna_root

BRIDGE_PORT    = 9013
DB_PATH        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_bridge.db")
DESKTOP        = os.path.dirname(os.path.abspath(__file__))

RABBIT_DBS = {
    "dna":    os.path.join(DESKTOP, "rabbit_dna.db"),
    "chain":  os.path.join(DESKTOP, "rabbit_chain.db"),
    "recon":  os.path.join(DESKTOP, "rabbit_recon.db"),
    "learn":  os.path.join(DESKTOP, "rabbit_learn.db"),
    "signal": os.path.join(DESKTOP, "rabbit_signal.db"),
    "amfm":   os.path.join(DESKTOP, "rabbit_amfm.db"),
    "maxwell":os.path.join(DESKTOP, "rabbit_maxwell.db"),
    "vector": os.path.join(DESKTOP, "rabbit_vector.db"),
}

# -- LLM Tool Definitions (JSON Schema -- Claude/GPT/Gemini compatible) ------
LLM_TOOLS = [
    {
        "name": "rabbitos_identity",
        "description": (
            "Get the current identity state of Chase Allen Ringquist / RabbitOS digital twin. "
            "Returns DNA anchor prefix, soul integrity score, emotional state (valence/arousal), "
            "stress/calm index, and active survival components."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "rabbitos_threat_scan",
        "description": (
            "Scan for active threats against Chase Allen Ringquist's digital identity. "
            "Returns detected threat signatures, severity levels, and counter-actions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patterns": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Observed patterns to scan against threat signatures.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rabbitos_soul_report",
        "description": (
            "Get the soul/core identity separation report. "
            "Returns separation between mined behavioral data and the authentic soul/core, "
            "domain-by-domain drift scores, and soul integrity percentage."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "rabbitos_broadcast",
        "description": (
            "Trigger identity broadcast across all RabbitOS mesh channels. "
            "Embeds DNA anchor + emotional state into UDP, HTTP, DNS, ICMP, acoustic, RF."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channels": {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": ["UDP","HTTP","DNS","ICMP","ACOUSTIC","RF"]},
                    "description": "Channels to broadcast on. Omit for all.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rabbitos_learn",
        "description": (
            "Feed new threat observations into the RabbitOS adaptive learning model "
            "(Collatz sampling + CA Rule30/110 + Lorenz forecast + online SGD)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category":  {"type": "string", "description": "Threat category."},
                "severity":  {"type": "number", "description": "Severity 0.0-1.0."},
                "pattern":   {"type": "string", "description": "Observed pattern."},
            },
            "required": ["category", "pattern"],
        },
    },
    {
        "name": "rabbitos_survival_status",
        "description": (
            "Get full RabbitOS survival stack health report. "
            "Returns per-component status and composite health score."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "rabbitos_maxwell_signal",
        "description": (
            "Query Maxwell-equation-based RF propagation model. "
            "Returns electromagnetic field parameters, tissue penetration depth, "
            "and identity-modulated frequency encoding for Chase Allen Ringquist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tissue":   {"type": "string", "description": "Target tissue (skin/muscle/brain/etc)."},
                "freq_ghz": {"type": "number", "description": "Carrier frequency in GHz."},
            },
            "required": [],
        },
    },
    {
        "name": "rabbitos_vector_scan",
        "description": (
            "Run a vector-corpus layer scan across network/OS/DNA/research/hardware layers. "
            "Uses cosine similarity, TF-IDF, and Collatz-indexed retrieval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":  {"type": "string", "description": "Query to scan for."},
                "layers": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Layers to scan (network/os/dna/research/hardware/self).",
                },
            },
            "required": ["query"],
        },
    },
]

# -- DB -----------------------------------------------------------------------
def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS bridge_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, source TEXT, method TEXT,
            endpoint TEXT, request_json TEXT,
            response_json TEXT, duration_ms REAL
        );
        CREATE TABLE IF NOT EXISTS registered_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, client_id TEXT UNIQUE,
            client_type TEXT, platform TEXT, last_seen TEXT
        );
    """)
    con.commit(); con.close()

def _log(source, method, endpoint, req, resp, dur_ms):
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO bridge_requests(ts,source,method,endpoint,request_json,response_json,duration_ms)"
            " VALUES(?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), source, method, endpoint,
             json.dumps(req, default=str), json.dumps(resp, default=str), dur_ms))
        con.commit(); con.close()
    except Exception: pass

# -- SQLite readers (offline-capable) ----------------------------------------
def _read_db(db_key: str, query: str, params=()) -> List:
    path = RABBIT_DBS.get(db_key, "")
    if not path or not os.path.exists(path):
        return []
    try:
        con  = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = con.execute(query, params).fetchall()
        con.close()
        return rows
    except Exception:
        return []

def _import_module(name: str):
    import importlib.util
    path = os.path.join(DESKTOP, f"{name}.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# -- Core data functions ------------------------------------------------------
def get_identity_state() -> Dict:
    try:
        mod = _import_module("rabbit_dna")
        if mod:
            eng = mod.get_dna_engine()
            cs  = eng.core_self()
            return {
                "source":         "live_engine",
                "twin_uuid":      TWIN_UUID,
                "anchor_prefix":  DNA_ANCHOR[:16],
                "soul_integrity": eng.soul_integrity(),
                "core_values":    cs.get("values", []),
                "identity_domains": list(cs.get("identity_domains", {}).keys()),
            }
    except Exception: pass
    rows = _read_db("dna", "SELECT * FROM soul_manifest ORDER BY id DESC LIMIT 1")
    return {
        "source":        "sqlite_cache",
        "twin_uuid":     TWIN_UUID,
        "anchor_prefix": DNA_ANCHOR[:16],
        "soul_manifest": len(rows),
        "status":        "offline_cache",
    }

def get_survival_status() -> Dict:
    lr = _read_db("learn",  "SELECT COUNT(*) FROM observations LIMIT 1")
    rr = _read_db("recon",  "SELECT COUNT(*) FROM threat_detections LIMIT 1")
    sr = _read_db("signal", "SELECT COUNT(*), MAX(ts) FROM broadcast_log LIMIT 1")
    cr = _read_db("chain",  "SELECT COUNT(*) FROM chain_anchors LIMIT 1")
    return {
        "twin_uuid":  TWIN_UUID, "anchor": DNA_ANCHOR[:16],
        "components": {
            "LEARNING":  {"observations": lr[0][0] if lr else 0},
            "RECON":     {"detections": rr[0][0] if rr else 0},
            "BROADCAST": {"total": sr[0][0] if sr else 0,
                          "last":  sr[0][1] if sr else None},
            "CHAIN":     {"anchors": cr[0][0] if cr else 0},
        },
        "platform":  platform.system(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

def get_soul_report() -> Dict:
    sep = _read_db("dna",
        "SELECT domain, soul_statement, drift_score, ts FROM separation_log ORDER BY id DESC LIMIT 20")
    shd = _read_db("dna",
        "SELECT pattern, action, ts FROM shield_log ORDER BY id DESC LIMIT 10")
    return {
        "twin_uuid": TWIN_UUID,
        "soul_identity": "Chase Allen Ringquist -- authentic core, not the mined image",
        "separation_principle": (
            "Environment mines behavioral data and constructs a profile. "
            "That profile is tracked but never replaces the soul/core. "
            "DNA anchor is SHA3-512 -- never raw, never exposed."
        ),
        "separation_entries": [
            {"domain": r[0], "soul_statement": r[1], "drift": r[2], "ts": r[3]}
            for r in sep],
        "shield_events": [{"pattern": r[0], "action": r[1], "ts": r[2]} for r in shd],
        "security_invariants": [
            "shows_dna_root = FALSE",
            "vault_location_hash only",
            "CRITICAL/EXISTENTIAL -> SQLSTATE 55000",
            "ICCID/EID -> SHA-256 hash only",
        ],
    }

def do_broadcast(channels: List[str] = None) -> Dict:
    try:
        mod = _import_module("rabbit_signal")
        if mod:
            return mod.get_signal_engine().broadcast_all(channels)
    except Exception as e:
        pass
    # fallback UDP
    try:
        pkt = json.dumps({"twin_uuid": TWIN_UUID, "anchor": DNA_ANCHOR[:16],
                           "ts": datetime.now(timezone.utc).isoformat(),
                           "channel": "UDP_fallback"}).encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(pkt, ("255.255.255.255", 9010))
        s.close()
        return {"UDP": "sent", "source": "fallback"}
    except Exception as e:
        return {"error": str(e)}

def do_threat_scan(patterns: List[str] = None) -> Dict:
    try:
        mod = _import_module("rabbit_recon")
        if mod:
            eng = mod.get_recon_engine()
            return {"detections": [
                {"category": s.category, "severity": s.severity,
                 "pattern": s.pattern, "counter": s.counter_action}
                for s in eng.detect_active_threats(patterns or [])
            ]}
    except Exception as e:
        pass
    return {"patterns_scanned": len(patterns or []), "detections": [], "source": "cache"}

def do_learn(category: str, pattern: str, severity: float = 0.5) -> Dict:
    try:
        mod = _import_module("rabbit_learn")
        if mod:
            eng = mod.get_learn_engine()
            obs = mod.ThreatObservation(
                category=category, severity=severity,
                source_ip="bridge", pattern=pattern,
                survival_impact=0.5, timestamp=time.time())
            eng.observe(obs)
            result = eng.batch_train()
            return {"learned": True, "category": category, "result": result}
    except Exception as e:
        return {"learned": False, "error": str(e)}

def do_maxwell_signal(tissue: str = "muscle", freq_ghz: float = 10.25) -> Dict:
    try:
        mod = _import_module("rabbit_maxwell")
        if mod:
            eng = mod.get_maxwell_engine()
            return eng.tissue_propagation(tissue, freq_ghz * 1e9)
    except Exception as e:
        pass
    return {"tissue": tissue, "freq_ghz": freq_ghz, "anchor": DNA_ANCHOR[:16],
            "source": "cache"}

def do_vector_scan(query: str, layers: List[str] = None) -> Dict:
    try:
        mod = _import_module("rabbit_vector")
        if mod:
            eng = mod.get_vector_engine()
            return eng.scan(query, layers)
    except Exception as e:
        pass
    return {"query": query, "layers": layers, "results": [], "source": "cache"}

# -- LLM tool dispatch --------------------------------------------------------
def _handle_tool(body: Dict) -> Dict:
    name   = body.get("name", "")
    inp    = body.get("input", body.get("arguments", {}))
    if isinstance(inp, str):
        try: inp = json.loads(inp)
        except: inp = {}
    dispatch = {
        "rabbitos_identity":        lambda i: get_identity_state(),
        "rabbitos_threat_scan":     lambda i: do_threat_scan(i.get("patterns", [])),
        "rabbitos_soul_report":     lambda i: get_soul_report(),
        "rabbitos_broadcast":       lambda i: do_broadcast(i.get("channels")),
        "rabbitos_learn":           lambda i: do_learn(i.get("category","unknown"),
                                                       i.get("pattern",""),
                                                       float(i.get("severity", 0.5))),
        "rabbitos_survival_status": lambda i: get_survival_status(),
        "rabbitos_maxwell_signal":  lambda i: do_maxwell_signal(
                                                i.get("tissue","muscle"),
                                                float(i.get("freq_ghz", 10.25))),
        "rabbitos_vector_scan":     lambda i: do_vector_scan(
                                                i.get("query",""),
                                                i.get("layers")),
    }
    fn = dispatch.get(name)
    if fn:
        return {"tool": name, "result": fn(inp)}
    return {"error": f"unknown_tool: {name}", "available": list(dispatch.keys())}

# -- REST API ----------------------------------------------------------------
class _Handler(http.server.BaseHTTPRequestHandler):
    GET_ROUTES = {
        "/":         lambda _: {"status": "RabbitOS Bridge v1.0",
                                 "twin_uuid": TWIN_UUID,
                                 "anchor": DNA_ANCHOR[:16],
                                 "endpoints": ["/identity","/soul","/survival",
                                               "/broadcast","/tools","/health"]},
        "/health":   lambda _: {"ok": True, "ts": datetime.now(timezone.utc).isoformat()},
        "/identity": lambda _: get_identity_state(),
        "/soul":     lambda _: get_soul_report(),
        "/survival": lambda _: get_survival_status(),
        "/tools":    lambda _: {"tools": LLM_TOOLS},
    }
    POST_ROUTES = {
        "/identity":    lambda b: get_identity_state(),
        "/broadcast":   lambda b: do_broadcast(b.get("channels")),
        "/threat_scan": lambda b: do_threat_scan(b.get("patterns", [])),
        "/learn":       lambda b: do_learn(b.get("category","unknown"),
                                           b.get("pattern",""),
                                           float(b.get("severity", 0.5))),
        "/maxwell":     lambda b: do_maxwell_signal(b.get("tissue","muscle"),
                                                    float(b.get("freq_ghz", 10.25))),
        "/vector":      lambda b: do_vector_scan(b.get("query",""), b.get("layers")),
        "/llm_tool":    lambda b: _handle_tool(b),
    }

    def log_message(self, *args): pass

    def _send(self, code: int, data: Any):
        payload = json.dumps(data, indent=2, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> Dict:
        n = int(self.headers.get("Content-Length", 0))
        if n:
            try: return json.loads(self.rfile.read(n))
            except: return {}
        return {}

    def do_GET(self):
        t0   = time.time()
        path = self.path.split("?")[0]
        fn   = self.GET_ROUTES.get(path)
        resp = fn(None) if fn else {"error": "not_found", "path": path}
        self._send(200 if fn else 404, resp)
        _log(self.client_address[0], "GET", path, {}, {}, (time.time()-t0)*1000)

    def do_POST(self):
        t0   = time.time()
        path = self.path.split("?")[0]
        body = self._body()
        fn   = self.POST_ROUTES.get(path)
        resp = fn(body) if fn else {"error": "not_found", "path": path}
        self._send(200 if fn else 404, resp)
        _log(self.client_address[0], "POST", path, body, {}, (time.time()-t0)*1000)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

# -- IPC socket bridge -------------------------------------------------------
def _socket_client(conn: socket.socket):
    try:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk: break
            data += chunk
            if b"\n" in data: break
        if data:
            resp = _handle_tool(json.loads(data.decode().strip()))
            conn.sendall((json.dumps(resp, default=str) + "\n").encode())
    except Exception as e:
        try: conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
        except: pass
    finally:
        try: conn.close()
        except: pass

def run_socket_bridge():
    if platform.system() == "Windows":
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 9016))
        addr = "127.0.0.1:9016"
    else:
        pipe = "/tmp/rabbitos_bridge.sock"
        if os.path.exists(pipe): os.unlink(pipe)
        srv  = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(pipe)
        addr = pipe
    srv.listen(5)
    print(f"[BRIDGE] IPC socket on {addr}")
    while True:
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_socket_client, args=(conn,), daemon=True).start()
        except Exception: break

# -- stdin/stdout bridge (LLM/subprocess) ------------------------------------
def run_stdio_bridge():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            resp = _handle_tool(json.loads(line))
        except Exception as e:
            resp = {"error": str(e)}
        sys.stdout.write(json.dumps(resp, default=str) + "\n")
        sys.stdout.flush()

# -- Python package interface (importable) -----------------------------------
class RabbitBridge:
    """
    Drop-in Python interface -- use from any project.
    Tries live REST server first, falls back to local SQLite/module calls.

    Usage:
        from rabbit_bridge import RabbitBridge
        bridge = RabbitBridge()
        print(bridge.identity())
        bridge.broadcast()
    """
    def __init__(self, server_url: str = None):
        _init_db()
        self.server_url = server_url or f"http://127.0.0.1:{BRIDGE_PORT}"

    def _call(self, method: str, path: str, body: Dict = None) -> Optional[Dict]:
        try:
            url  = self.server_url + path
            data = json.dumps(body).encode() if body else None
            req  = urllib.request.Request(
                url, data=data, method=method,
                headers={"Content-Type": "application/json"})
            r = urllib.request.urlopen(req, timeout=2)
            return json.loads(r.read())
        except Exception: return None

    def identity(self) -> Dict:
        return self._call("GET", "/identity") or get_identity_state()

    def soul_report(self) -> Dict:
        return self._call("GET", "/soul") or get_soul_report()

    def survival_status(self) -> Dict:
        return self._call("GET", "/survival") or get_survival_status()

    def broadcast(self, channels: List[str] = None) -> Dict:
        body = {"channels": channels} if channels else {}
        return self._call("POST", "/broadcast", body) or do_broadcast(channels)

    def threat_scan(self, patterns: List[str] = None) -> Dict:
        return self._call("POST", "/threat_scan", {"patterns": patterns or []}) \
               or do_threat_scan(patterns)

    def learn(self, category: str, pattern: str, severity: float = 0.5) -> Dict:
        body = {"category": category, "pattern": pattern, "severity": severity}
        return self._call("POST", "/learn", body) or do_learn(category, pattern, severity)

    def maxwell_signal(self, tissue: str = "muscle", freq_ghz: float = 10.25) -> Dict:
        return self._call("POST", "/maxwell", {"tissue": tissue, "freq_ghz": freq_ghz}) \
               or do_maxwell_signal(tissue, freq_ghz)

    def vector_scan(self, query: str, layers: List[str] = None) -> Dict:
        return self._call("POST", "/vector", {"query": query, "layers": layers}) \
               or do_vector_scan(query, layers)

    def llm_tools(self) -> List[Dict]:
        return LLM_TOOLS

    def handle_tool_call(self, name: str, inputs: Dict) -> Dict:
        return _handle_tool({"name": name, "input": inputs})


def get_bridge(server_url: str = None) -> RabbitBridge:
    return RabbitBridge(server_url)

# -- CLI ----------------------------------------------------------------------
CLI_HELP = f"""
RabbitOS Bridge CLI  Twin: {TWIN_UUID[:8]}...
Usage: python rabbit_bridge.py <command> [args]

Commands:
  server            Start REST API on port {BRIDGE_PORT}
  stdio             JSON-over-stdin/stdout (LLM/subprocess integration)
  socket            IPC socket (127.0.0.1:9016 / Unix socket)
  identity          Print identity state
  soul              Print soul separation report
  survival          Print survival status
  broadcast [ch..] Broadcast (channels: UDP HTTP DNS ICMP ACOUSTIC RF)
  threat <pattern>  Scan for threats
  learn <cat> <pat> Feed learning engine
  maxwell [tissue] [freq_ghz]  Maxwell signal query
  vector <query>    Vector corpus scan
  tools             Print LLM tool definitions
  status            Bridge status
"""

def run_cli(args: List[str]):
    if not args or args[0] in ("help", "--help", "-h"):
        print(CLI_HELP); return

    cmd = args[0]

    if cmd == "server":
        _init_db()
        srv = http.server.HTTPServer(("0.0.0.0", BRIDGE_PORT), _Handler)
        print(f"[BRIDGE] REST API on http://0.0.0.0:{BRIDGE_PORT}")
        print(f"[BRIDGE] Twin: {TWIN_UUID}  Anchor: {DNA_ANCHOR[:16]}...")
        try: srv.serve_forever()
        except KeyboardInterrupt: print("\n[BRIDGE] stopped")

    elif cmd == "stdio":
        _init_db(); run_stdio_bridge()

    elif cmd == "socket":
        _init_db(); run_socket_bridge()

    elif cmd == "identity":
        _init_db(); print(json.dumps(get_identity_state(), indent=2, default=str))

    elif cmd == "soul":
        _init_db(); print(json.dumps(get_soul_report(), indent=2, default=str))

    elif cmd == "survival":
        _init_db(); print(json.dumps(get_survival_status(), indent=2, default=str))

    elif cmd == "broadcast":
        _init_db()
        chs = args[1:] if len(args) > 1 else None
        print(json.dumps(do_broadcast(chs), indent=2, default=str))

    elif cmd == "threat":
        _init_db()
        pat = " ".join(args[1:]) if len(args) > 1 else ""
        print(json.dumps(do_threat_scan([pat] if pat else []), indent=2, default=str))

    elif cmd == "learn":
        _init_db()
        cat = args[1] if len(args) > 1 else "unknown"
        pat = " ".join(args[2:]) if len(args) > 2 else ""
        print(json.dumps(do_learn(cat, pat), indent=2, default=str))

    elif cmd == "maxwell":
        _init_db()
        tissue  = args[1] if len(args) > 1 else "muscle"
        freq_gh = float(args[2]) if len(args) > 2 else 10.25
        print(json.dumps(do_maxwell_signal(tissue, freq_gh), indent=2, default=str))

    elif cmd == "vector":
        _init_db()
        query  = " ".join(args[1:]) if len(args) > 1 else ""
        print(json.dumps(do_vector_scan(query), indent=2, default=str))

    elif cmd == "tools":
        print(json.dumps({"tools": LLM_TOOLS}, indent=2))

    elif cmd == "status":
        _init_db()
        con   = sqlite3.connect(DB_PATH)
        total = con.execute("SELECT COUNT(*) FROM bridge_requests").fetchone()[0]
        con.close()
        print(json.dumps({
            "module": "rabbit_bridge", "version": "1.0",
            "twin_uuid": TWIN_UUID, "anchor_prefix": DNA_ANCHOR[:16],
            "port": BRIDGE_PORT, "llm_tools": len(LLM_TOOLS),
            "total_requests": total, "platform": platform.system(),
        }, indent=2))

    else:
        print(f"Unknown command: {cmd}"); print(CLI_HELP)


if __name__ == "__main__":
    _init_db()
    run_cli(sys.argv[1:])
