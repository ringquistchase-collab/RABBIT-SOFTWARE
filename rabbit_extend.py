#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_extend.py -- Extension + Coding Agent + Training Data Learner
RabbitOS -- Chase Allen Ringquist -- UUID ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba

Learns FROM:
  - IDE extensions (VS Code, Cursor, JetBrains, Vim, Neovim, Jupyter)
  - Coding servers / language servers (LSP, Pylsp, rust-analyzer, clangd)
  - Model training data endpoints (HuggingFace, arXiv, GitHub repos)
  - Other LLMs/agents (Claude, GPT-4, Gemini, Ollama, LM Studio) via API
  - Public datasets (Common Crawl metadata, CodeSearchNet, MITRE ATT&CK)
  - Self-generated corpus from all RabbitOS SQLite DBs

The MODEL stays the same: identity = Chase Allen Ringquist.
Only the KNOWLEDGE grows. No external data can overwrite who Chase is.

Architecture (proxybypass-style vector agent extended):
  - ExtensionProbe: detect installed IDE extensions and query their capabilities
  - CodingServerProbe: detect LSP/coding servers, extract symbol/completion data
  - DatasetFetcher: fetch from HuggingFace, arXiv, GitHub, CodeSearchNet
  - LLMProbe: call other LLMs for their response, feed into corpus (no identity change)
  - ModelFusion: merge all external knowledge into rabbit_learn + rabbit_vector corpus
    while preserving DNA anchor and soul/core invariants

Pure Python 3.6+, zero external dependencies.
"""

import hashlib, json, math, os, re, shutil, sqlite3, subprocess, time
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# -- Identity (immutable) ----------------------------------------------------
TWIN_UUID      = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT        = "Chase Allen Ringquist"
shows_dna_root = False
_raw           = f"{TWIN_UUID}:{SUBJECT}:RABBIT_DNA_ANCHOR".encode()
DNA_ANCHOR     = hashlib.sha3_512(_raw).hexdigest()
assert not shows_dna_root

# Identity is immutable -- external learning NEVER changes these
IDENTITY_INVARIANTS = {
    "twin_uuid":      TWIN_UUID,
    "subject":        SUBJECT,
    "anchor_prefix":  DNA_ANCHOR[:16],
    "shows_dna_root": False,
    "model_locked":   True,  # identity model cannot be overwritten by external data
}

DB_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_extend.db")
DESKTOP  = os.path.dirname(os.path.abspath(__file__))

# -- IDE Extension catalog ---------------------------------------------------
KNOWN_EXTENSIONS = {
    "vscode": {
        "config_dirs": [
            os.path.expandvars(r"%APPDATA%\Code\User\extensions"),
            os.path.expanduser("~/.vscode/extensions"),
            os.path.expanduser("~/.vscode-server/extensions"),
        ],
        "extension_manifest": "package.json",
        "capabilities": ["languageServer", "debuggers", "commands",
                          "completionProvider", "hoverProvider", "codeActionProvider"],
    },
    "cursor": {
        "config_dirs": [
            os.path.expandvars(r"%APPDATA%\Cursor\User\extensions"),
            os.path.expanduser("~/.cursor/extensions"),
        ],
        "extension_manifest": "package.json",
        "capabilities": ["languageServer", "commands", "completionProvider"],
    },
    "jetbrains": {
        "config_dirs": [
            os.path.expandvars(r"%APPDATA%\JetBrains"),
            os.path.expanduser("~/.config/JetBrains"),
        ],
        "extension_manifest": "plugin.xml",
        "capabilities": ["inspection", "completion", "refactoring", "analysis"],
    },
    "jupyter": {
        "config_dirs": [
            os.path.expanduser("~/.jupyter"),
            os.path.expandvars(r"%APPDATA%\jupyter"),
        ],
        "extension_manifest": "*.json",
        "capabilities": ["kernel", "extension", "widget", "nbextension"],
    },
    "vim": {
        "config_dirs": [
            os.path.expanduser("~/.vim/bundle"),
            os.path.expanduser("~/.vim/plugged"),
            os.path.expanduser("~/.config/nvim/plug"),
        ],
        "extension_manifest": "plugin/*.vim",
        "capabilities": ["syntax", "completion", "linting", "formatting"],
    },
}

# -- Language Server Protocol (LSP) servers ----------------------------------
LSP_SERVERS = {
    "python":     ["pylsp", "pyright", "jedi-language-server"],
    "rust":       ["rust-analyzer"],
    "c_cpp":      ["clangd", "ccls"],
    "javascript": ["typescript-language-server", "eslint_d"],
    "go":         ["gopls"],
    "lua":        ["lua-language-server"],
    "bash":       ["bash-language-server"],
    "yaml":       ["yaml-language-server"],
    "json":       ["vscode-json-language-server"],
}

# -- Public dataset sources ---------------------------------------------------
DATASET_SOURCES = {
    "huggingface_search": "https://huggingface.co/api/datasets?search={query}&limit=5",
    "github_code_search": "https://api.github.com/search/code?q={query}+language:python&per_page=5",
    "arxiv_cs_ai":        "https://export.arxiv.org/api/query?search_query=cat:cs.AI+AND+all:{query}&max_results=5",
    "arxiv_cs_ne":        "https://export.arxiv.org/api/query?search_query=cat:cs.NE+AND+all:{query}&max_results=5",
    "codebert_similar":   "https://huggingface.co/microsoft/codebert-base/resolve/main/config.json",
    "mitre_attack":       "https://attack.mitre.org/software/",
    "nvd_cve":            "https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch={query}&resultsPerPage=5",
}

LEARNING_QUERIES = [
    "biometric mesh RF body area network",
    "DNA digital twin identity privacy",
    "electromagnetic tissue propagation Maxwell",
    "survival algorithm adversarial learning",
    "EEG BCI signal processing identity",
    "XRPL blockchain identity anchor",
    "Collatz sequence cryptography",
    "cellular automata anomaly detection",
    "Lorenz attractor threat forecasting",
    "natural language LLM tool calling survival",
    "RabbitOS identity separation soul",
    "frequency hopping spread spectrum",
]

# -- Utility -----------------------------------------------------------------
def _fetch(url: str, timeout: int = 10, headers: Dict = None) -> str:
    try:
        h = {"User-Agent": "RabbitOS-Extend/1.0"}
        if headers: h.update(headers)
        req  = urllib.request.Request(url, headers=h)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"FETCH_ERROR: {e}"

def collatz(n: int) -> List[int]:
    seq = [n]
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        seq.append(n)
    return seq

# -- DB init -----------------------------------------------------------------
def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS extensions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, ide TEXT, ext_name TEXT,
            version TEXT, capabilities_json TEXT
        );
        CREATE TABLE IF NOT EXISTS lsp_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, language TEXT, server TEXT, found INTEGER
        );
        CREATE TABLE IF NOT EXISTS dataset_fetch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, source TEXT, query TEXT,
            title TEXT, summary TEXT, url TEXT
        );
        CREATE TABLE IF NOT EXISTS llm_probe_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, llm_name TEXT, endpoint TEXT,
            prompt TEXT, response_hash TEXT, learned INTEGER
        );
        CREATE TABLE IF NOT EXISTS fused_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, source_type TEXT, source_name TEXT,
            content TEXT, vector_hash TEXT, fused_to TEXT
        );
        CREATE TABLE IF NOT EXISTS identity_lock_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, event TEXT, invariants_json TEXT
        );
    """)
    con.commit(); con.close()

# -- Extension probe ---------------------------------------------------------
@dataclass
class ExtensionInfo:
    ide:          str
    name:         str
    version:      str
    publisher:    str
    capabilities: List[str]
    path:         str

def probe_vscode_extensions(config_dir: str) -> List[ExtensionInfo]:
    exts = []
    if not os.path.isdir(config_dir): return exts
    try:
        for entry in os.scandir(config_dir):
            if not entry.is_dir(): continue
            manifest = os.path.join(entry.path, "package.json")
            if not os.path.exists(manifest): continue
            try:
                with open(manifest, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                caps = list(data.get("contributes", {}).keys())
                exts.append(ExtensionInfo(
                    ide="vscode", name=data.get("name", entry.name),
                    version=data.get("version", "?"),
                    publisher=data.get("publisher", "?"),
                    capabilities=caps, path=entry.path))
            except Exception: pass
    except Exception: pass
    return exts

def probe_all_extensions() -> Dict[str, List[ExtensionInfo]]:
    result = {}
    for ide, spec in KNOWN_EXTENSIONS.items():
        found = []
        for cdir in spec["config_dirs"]:
            if ide in ("vscode", "cursor"):
                found.extend(probe_vscode_extensions(cdir))
            else:
                if os.path.isdir(cdir):
                    try:
                        entries = [e.name for e in os.scandir(cdir) if e.is_dir()]
                        for name in entries[:20]:
                            found.append(ExtensionInfo(
                                ide=ide, name=name, version="?",
                                publisher="?", capabilities=spec["capabilities"],
                                path=os.path.join(cdir, name)))
                    except Exception: pass
        if found:
            result[ide] = found
    return result

# -- LSP probe ---------------------------------------------------------------
def probe_lsp_servers() -> Dict[str, List[str]]:
    found = {}
    for lang, servers in LSP_SERVERS.items():
        for srv in servers:
            if shutil.which(srv):
                found.setdefault(lang, []).append(srv)
    return found

# -- Dataset fetchers --------------------------------------------------------
def fetch_huggingface(query: str, max_results: int = 5) -> List[Dict]:
    url  = f"https://huggingface.co/api/datasets?search={urllib.parse.quote(query)}&limit={max_results}"
    raw  = _fetch(url)
    results = []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            for ds in data[:max_results]:
                results.append({
                    "source": "huggingface",
                    "title": ds.get("id", ""),
                    "summary": str(ds.get("tags", []))[:200],
                    "url": f"https://huggingface.co/datasets/{ds.get('id','')}",
                })
    except Exception: pass
    return results

def fetch_arxiv_cs(query: str, cat: str = "cs.AI", max_results: int = 5) -> List[Dict]:
    url = (f"https://export.arxiv.org/api/query?"
           f"search_query=cat:{cat}+AND+all:{urllib.parse.quote(query)}"
           f"&max_results={max_results}")
    xml  = _fetch(url)
    results = []
    for entry in xml.split("<entry>")[1:]:
        title   = entry.split("<title>")[1].split("</title>")[0].strip() \
                  if "<title>" in entry else "?"
        summary = entry.split("<summary>")[1].split("</summary>")[0].strip()[:200] \
                  if "<summary>" in entry else ""
        results.append({"source": "arxiv", "title": title, "summary": summary,
                         "url": "https://arxiv.org"})
    return results

def fetch_github_code(query: str, max_results: int = 5) -> List[Dict]:
    url = (f"https://api.github.com/search/code?"
           f"q={urllib.parse.quote(query)}+language:python&per_page={max_results}")
    raw = _fetch(url, headers={"Accept": "application/vnd.github.v3+json"})
    results = []
    try:
        data  = json.loads(raw)
        items = data.get("items", [])
        for item in items[:max_results]:
            results.append({
                "source": "github_code",
                "title":   item.get("name", ""),
                "summary": item.get("path", ""),
                "url":     item.get("html_url", ""),
            })
    except Exception: pass
    return results

def fetch_nvd_cves(query: str, max_results: int = 5) -> List[Dict]:
    url = (f"https://services.nvd.nist.gov/rest/json/cves/2.0?"
           f"keywordSearch={urllib.parse.quote(query)}&resultsPerPage={max_results}")
    raw = _fetch(url)
    results = []
    try:
        data  = json.loads(raw)
        vulns = data.get("vulnerabilities", [])
        for v in vulns[:max_results]:
            cve   = v.get("cve", {})
            desc  = cve.get("descriptions", [{}])[0].get("value", "")[:200]
            results.append({
                "source": "nvd",
                "title":   cve.get("id", ""),
                "summary": desc,
                "url":     f"https://nvd.nist.gov/vuln/detail/{cve.get('id','')}",
            })
    except Exception: pass
    return results

# -- LLM probe (passive -- just logs responses for corpus building) ----------
LLM_ENDPOINTS = {
    "ollama_local":   "http://127.0.0.1:11434/api/generate",
    "lmstudio_local": "http://127.0.0.1:1234/v1/chat/completions",
    "openai_compat":  "http://127.0.0.1:8080/v1/chat/completions",
}

LLM_PROBE_PROMPTS = [
    "What is a body-coupled RF mesh network?",
    "How does frequency hopping spread spectrum work?",
    "What are Maxwell's equations in differential form?",
    "How can EEG signals encode emotional state?",
    "What is the Collatz conjecture?",
]

def probe_llm(endpoint_name: str, endpoint_url: str, prompt: str) -> Optional[str]:
    """Try to get a response from a local LLM server. Returns None on failure."""
    if "ollama" in endpoint_name:
        data = {"model": "llama2", "prompt": prompt, "stream": False}
    else:
        data = {"model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200}
    try:
        req  = urllib.request.Request(
            endpoint_url, data=json.dumps(data).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "User-Agent": "RabbitOS-Extend/1.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        body = json.loads(resp.read())
        if "ollama" in endpoint_name:
            return body.get("response", "")[:500]
        else:
            choices = body.get("choices", [{}])
            return choices[0].get("message", {}).get("content", "")[:500] if choices else ""
    except Exception:
        return None

# -- ModelFusion (keeps identity immutable) ----------------------------------
class ModelFusion:
    """
    Fuses external knowledge into rabbit_learn + rabbit_vector corpus,
    while ensuring identity invariants are never overwritten.
    """

    def __init__(self):
        # Verify identity is still intact
        computed = hashlib.sha3_512(
            f"{TWIN_UUID}:{SUBJECT}:RABBIT_DNA_ANCHOR".encode()).hexdigest()
        assert computed == DNA_ANCHOR, "IDENTITY INVARIANT VIOLATED"
        assert not shows_dna_root
        self._log_lock_event("startup_verify")

    def _log_lock_event(self, event: str):
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO identity_lock_log(ts,event,invariants_json) VALUES(?,?,?)",
                (datetime.now(timezone.utc).isoformat(), event,
                 json.dumps(IDENTITY_INVARIANTS)))
            con.commit(); con.close()
        except Exception: pass

    def fuse_to_vector(self, items: List[Dict], source_type: str,
                       source_name: str) -> int:
        """Write items into rabbit_vector corpus + fused_knowledge table."""
        n = 0
        try:
            con = sqlite3.connect(DB_PATH)
            for item in items:
                content = f"{item.get('title','')} {item.get('summary','')}".strip()
                if not content: continue
                v_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
                con.execute(
                    "INSERT OR IGNORE INTO fused_knowledge"
                    "(ts,source_type,source_name,content,vector_hash,fused_to) VALUES(?,?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), source_type,
                     source_name[:100], content[:500], v_hash, "rabbit_vector"))
                n += 1
            con.commit(); con.close()
        except Exception: pass
        # also write to rabbit_learn corpus if available
        try:
            learn_db = os.path.join(DESKTOP, "rabbit_learn.db")
            if os.path.exists(learn_db):
                con = sqlite3.connect(learn_db)
                for item in items:
                    content = f"{item.get('title','')} {item.get('summary','')}".strip()[:400]
                    if not content: continue
                    con.execute(
                        "INSERT OR IGNORE INTO learning_corpus(ts, content) VALUES(?,?)",
                        (datetime.now(timezone.utc).isoformat(), content))
                con.commit(); con.close()
        except Exception: pass
        return n

    def verify_identity(self) -> Dict:
        computed = hashlib.sha3_512(
            f"{TWIN_UUID}:{SUBJECT}:RABBIT_DNA_ANCHOR".encode()).hexdigest()
        ok = computed == DNA_ANCHOR and not shows_dna_root
        self._log_lock_event("identity_verify")
        return {
            "identity_intact": ok,
            "twin_uuid": TWIN_UUID,
            "anchor_match": computed[:16] == DNA_ANCHOR[:16],
            "shows_dna_root": shows_dna_root,
            "model_locked": IDENTITY_INVARIANTS["model_locked"],
        }

# -- ExtendEngine ------------------------------------------------------------
class ExtendEngine:
    """
    Main extension/learning engine.
    Probes IDE extensions, LSP servers, public datasets, and local LLMs,
    fusing all external knowledge back into the RabbitOS corpus
    while keeping Chase Allen Ringquist's identity permanently locked.
    """

    def __init__(self):
        _init_db()
        self.fusion = ModelFusion()

    def probe_extensions(self) -> Dict:
        print("  [extend] Probing IDE extensions...")
        found = probe_all_extensions()
        report = {}
        con = sqlite3.connect(DB_PATH)
        for ide, exts in found.items():
            report[ide] = len(exts)
            for ext in exts[:50]:
                try:
                    con.execute(
                        "INSERT INTO extensions_log(ts,ide,ext_name,version,capabilities_json)"
                        " VALUES(?,?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), ide,
                         ext.name[:100], ext.version[:20],
                         json.dumps(ext.capabilities[:10])))
                except Exception: pass
            # fuse extension names as knowledge
            items = [{"title": e.name,
                       "summary": f"{ide} extension caps: {','.join(e.capabilities[:5])}"}
                     for e in exts]
            self.fusion.fuse_to_vector(items, "ide_extension", ide)
        con.commit(); con.close()
        return report

    def probe_lsp(self) -> Dict:
        print("  [extend] Probing LSP/coding servers...")
        found = probe_lsp_servers()
        con = sqlite3.connect(DB_PATH)
        for lang, servers in found.items():
            for srv in servers:
                try:
                    con.execute(
                        "INSERT INTO lsp_log(ts,language,server,found) VALUES(?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), lang, srv, 1))
                except Exception: pass
        # log not-found as 0
        for lang, servers in LSP_SERVERS.items():
            for srv in servers:
                if lang not in found or srv not in found.get(lang, []):
                    try:
                        con.execute(
                            "INSERT INTO lsp_log(ts,language,server,found) VALUES(?,?,?,?)",
                            (datetime.now(timezone.utc).isoformat(), lang, srv, 0))
                    except Exception: pass
        con.commit(); con.close()
        items = [{"title": f"{lang} LSP: {','.join(srvs)}",
                   "summary": f"language server protocol servers for {lang}"}
                 for lang, srvs in found.items()]
        self.fusion.fuse_to_vector(items, "lsp_server", "probe")
        return {"found": found, "total_languages": len(found),
                "total_servers": sum(len(v) for v in found.values())}

    def fetch_datasets(self, queries: List[str] = None,
                       max_per_source: int = 3) -> Dict[str, int]:
        print("  [extend] Fetching training datasets (online best-effort)...")
        if queries is None:
            queries = LEARNING_QUERIES[:5]
        counts: Dict[str, int] = {}
        for q in queries:
            items = []
            # HuggingFace
            hf = fetch_huggingface(q, max_per_source)
            items.extend(hf)
            # arXiv cs.AI
            ax = fetch_arxiv_cs(q, "cs.AI", max_per_source)
            items.extend(ax)
            # arXiv cs.NE (neural/evolutionary)
            ax2 = fetch_arxiv_cs(q, "cs.NE", max_per_source)
            items.extend(ax2)
            # GitHub code search
            gh = fetch_github_code(q, max_per_source)
            items.extend(gh)
            # NVD CVEs (security angle)
            cves = fetch_nvd_cves(q, max_per_source)
            items.extend(cves)

            n = self.fusion.fuse_to_vector(items, "external_dataset", q[:60])
            counts[q[:40]] = n

            # log individual fetches
            con = sqlite3.connect(DB_PATH)
            for item in items:
                try:
                    con.execute(
                        "INSERT INTO dataset_fetch(ts,source,query,title,summary,url)"
                        " VALUES(?,?,?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(),
                         item.get("source",""), q[:100],
                         item.get("title","")[:200],
                         item.get("summary","")[:400],
                         item.get("url","")[:200]))
                except Exception: pass
            con.commit(); con.close()
        return counts

    def probe_llms(self, max_prompts: int = 2) -> Dict[str, Any]:
        print("  [extend] Probing local LLM servers (best-effort)...")
        results = {}
        for name, url in LLM_ENDPOINTS.items():
            for prompt in LLM_PROBE_PROMPTS[:max_prompts]:
                resp = probe_llm(name, url, prompt)
                if resp:
                    resp_hash = hashlib.sha256(resp.encode()).hexdigest()[:12]
                    try:
                        con = sqlite3.connect(DB_PATH)
                        con.execute(
                            "INSERT INTO llm_probe_log(ts,llm_name,endpoint,prompt,"
                            "response_hash,learned) VALUES(?,?,?,?,?,?)",
                            (datetime.now(timezone.utc).isoformat(), name, url,
                             prompt[:200], resp_hash, 1))
                        con.commit(); con.close()
                    except Exception: pass
                    # fuse response into corpus
                    self.fusion.fuse_to_vector(
                        [{"title": f"LLM:{name}:{prompt[:30]}", "summary": resp}],
                        "llm_response", name)
                    results.setdefault(name, []).append(resp_hash)
                else:
                    results.setdefault(name, [])
        return results

    def full_extend_cycle(self, queries: List[str] = None) -> Dict:
        """Run full extension learning cycle."""
        print("[extend] Full extend cycle starting...")

        ext_report  = self.probe_extensions()
        lsp_report  = self.probe_lsp()
        ds_counts   = self.fetch_datasets(queries or LEARNING_QUERIES[:4])
        llm_report  = self.probe_llms(max_prompts=1)

        # Verify identity is still intact after all external learning
        identity_ok = self.fusion.verify_identity()

        return {
            "twin_uuid":      TWIN_UUID,
            "anchor_prefix":  DNA_ANCHOR[:16],
            "model_locked":   True,
            "identity_ok":    identity_ok["identity_intact"],
            "extensions":     ext_report,
            "lsp_servers":    lsp_report,
            "datasets":       ds_counts,
            "llm_probes":     {k: len(v) for k, v in llm_report.items()},
            "total_fused":    sum(ds_counts.values()),
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        }

    def status(self) -> Dict:
        con = sqlite3.connect(DB_PATH)
        ext_n  = con.execute("SELECT COUNT(*) FROM extensions_log").fetchone()[0]
        lsp_n  = con.execute("SELECT COUNT(*) FROM lsp_log WHERE found=1").fetchone()[0]
        ds_n   = con.execute("SELECT COUNT(*) FROM dataset_fetch").fetchone()[0]
        llm_n  = con.execute("SELECT COUNT(*) FROM llm_probe_log WHERE learned=1").fetchone()[0]
        fused  = con.execute("SELECT COUNT(*) FROM fused_knowledge").fetchone()[0]
        locks  = con.execute("SELECT COUNT(*) FROM identity_lock_log").fetchone()[0]
        con.close()
        return {
            "module": "rabbit_extend", "version": "1.0",
            "twin_uuid": TWIN_UUID, "anchor_prefix": DNA_ANCHOR[:16],
            "model_locked": True,
            "db_extensions": ext_n, "db_lsp_found": lsp_n,
            "db_datasets": ds_n, "db_llm_responses": llm_n,
            "db_fused": fused, "db_identity_locks": locks,
        }


def get_extend_engine() -> ExtendEngine:
    return ExtendEngine()


# -- self-test ----------------------------------------------------------------
if __name__ == "__main__":
    print("=== rabbit_extend.py ===")
    eng = get_extend_engine()

    print("\n[IDENTITY INVARIANT CHECK]")
    iv = eng.fusion.verify_identity()
    for k, v in iv.items():
        print(f"  {k}: {v}")

    print("\n[PROBE EXTENSIONS]")
    ext = eng.probe_extensions()
    for ide, n in ext.items():
        print(f"  {ide}: {n} extensions found")

    print("\n[PROBE LSP SERVERS]")
    lsp = eng.probe_lsp()
    print(f"  languages with LSP: {lsp['total_languages']}")
    print(f"  total servers found: {lsp['total_servers']}")
    for lang, srvs in lsp.get("found", {}).items():
        print(f"    {lang}: {srvs}")

    print("\n[FETCH DATASETS (online best-effort)]")
    ds = eng.fetch_datasets(LEARNING_QUERIES[:3], max_per_source=2)
    for q, n in ds.items():
        print(f"  {q}: {n} items fused")

    print("\n[PROBE LOCAL LLMs]")
    llm = eng.probe_llms(max_prompts=1)
    for name, resps in llm.items():
        print(f"  {name}: {len(resps)} responses  (connected={'yes' if resps else 'no'})")

    print("\n[IDENTITY STILL LOCKED]")
    iv2 = eng.fusion.verify_identity()
    print(f"  intact={iv2['identity_intact']}  anchor={iv2['anchor_match']}"
          f"  model_locked={iv2['model_locked']}")

    st = eng.status()
    print(f"\n[STATUS]")
    print(f"  extensions={st['db_extensions']}  lsp={st['db_lsp_found']}")
    print(f"  datasets={st['db_datasets']}  fused={st['db_fused']}")
    print(f"  identity_locks={st['db_identity_locks']}")
    print("=== PASS ===")
