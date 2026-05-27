#!/usr/bin/env python3
"""
RabbitOS Universal Agent
Connects to: Supabase DB + Storage + GitHub + RabbitOS mesh
Twin: Chase Allen Ringquist  (ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba)

Usage:
  python rabbit_agent.py              # interactive Claude-powered chat
  python rabbit_agent.py --status     # quick status dump
  python rabbit_agent.py --dashboard  # live RabbitOS dashboard

Required env vars:
  SUPABASE_SERVICE_ROLE_KEY  — rotate at https://supabase.com/dashboard/project/ludxbakxpmdqhfgdenwp/settings/api
  ANTHROPIC_API_KEY          — for AI brain (optional; falls back to direct CLI)

Optional env vars:
  GITHUB_TOKEN               — defaults to therealsickonechase-bit PAT
  SUPABASE_ANON_KEY          — for anon-tier queries
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional, Any
from datetime import datetime

# ── CONSTANTS ───────────────────────────────────────────────────────────────
TWIN_UUID        = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME        = "Chase Allen Ringquist"

SUPABASE_URL     = "https://ludxbakxpmdqhfgdenwp.supabase.co"
REST_URL         = f"{SUPABASE_URL}/rest/v1"
STORAGE_URL      = f"{SUPABASE_URL}/storage/v1"
BUCKET           = "pr-snapshots"

REPO_UPSTREAM    = "ringquistchase-collab/RABBIT-SOFTWARE"
REPO_FORK        = "therealsickonechase-bit/RABBIT-SOFTWARE"
XRPL_WSS         = "wss://s.altnet.rippletest.net:51234"

# ── SECURITY INVARIANTS (never violate) ──────────────────────────────────────
# shows_dna_root = FALSE always
# vault_location_hash only — never plaintext
# CRITICAL/EXISTENTIAL → SQLSTATE 55000 if accessed


# =============================================================================
# SUPABASE-FIRST CREDENTIAL LOADER
# =============================================================================

class SupabaseConfig:
    """
    Loads all agent credentials from the Supabase `agent_credentials` table.
    Falls back to environment variables if the table query fails.
    Priority: Supabase DB  >  env var  >  hardcoded default.

    One-time table setup (run in Supabase SQL editor):
        CREATE TABLE IF NOT EXISTS agent_credentials (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            access_tier TEXT DEFAULT 'CRITICAL',
            updated_at  TIMESTAMPTZ DEFAULT now()
        );
        ALTER TABLE agent_credentials ENABLE ROW LEVEL SECURITY;
        CREATE POLICY "deny_all" ON agent_credentials USING (false);
    """

    _loaded: Dict[str, str] = {}
    _bootstrapped: bool = False

    @classmethod
    def bootstrap(cls, service_key: str):
        if cls._bootstrapped:
            return
        url = f"{SUPABASE_URL}/rest/v1/agent_credentials?select=key,value"
        req = urllib.request.Request(url, headers={
            "apikey": service_key, "Authorization": f"Bearer {service_key}",
        })
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                rows = json.loads(resp.read())
                if isinstance(rows, list):
                    cls._loaded = {r["key"]: r["value"] for r in rows}
                    print(f"[Config] {len(cls._loaded)} credentials loaded from Supabase")
        except Exception as e:
            print(f"[Config] Supabase credential load failed ({e}) — using env vars")
        cls._bootstrapped = True

    @classmethod
    def get(cls, key: str, env_var: str, default: str = "") -> str:
        return cls._loaded.get(key) or os.environ.get(env_var, default)

    @classmethod
    def upsert(cls, service_key: str, key: str, value: str, tier: str = "CRITICAL") -> bool:
        """Store or update a credential in Supabase."""
        url  = f"{SUPABASE_URL}/rest/v1/agent_credentials"
        data = json.dumps({"key": key, "value": value, "access_tier": tier,
                           "updated_at": datetime.utcnow().isoformat()}).encode()
        req  = urllib.request.Request(url, data=data, headers={
            "apikey": service_key, "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates",
        }, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=8):
                cls._loaded[key] = value
                return True
        except Exception as e:
            print(f"[Config] Upsert failed: {e}")
            return False


# ── resolve credentials (Supabase-first) ─────────────────────────────────────
_boot_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
if _boot_key:
    SupabaseConfig.bootstrap(_boot_key)

SUPABASE_KEY  = SupabaseConfig.get("supabase_service_role_key", "SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_ANON = SupabaseConfig.get("supabase_anon_key",         "SUPABASE_ANON_KEY")
GITHUB_TOKEN  = SupabaseConfig.get("github_token",              "GITHUB_TOKEN", "")
ANTHROPIC_KEY = SupabaseConfig.get("anthropic_api_key",         "ANTHROPIC_API_KEY")


# =============================================================================
# SUPABASE CONNECTOR
# =============================================================================

class SupabaseConnector:
    """REST + Storage connector for the rabbitOS Supabase project."""

    def __init__(self):
        self.key = SUPABASE_KEY or SUPABASE_ANON
        if not self.key:
            print("[WARN] No SUPABASE_SERVICE_ROLE_KEY set — read access only via anon key (limited)")

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _get(self, path: str, params: Dict = None) -> Any:
        url = f"{REST_URL}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            return {"error": e.code, "detail": body}
        except Exception as e:
            return {"error": str(e)}

    def _post(self, path: str, payload: Dict) -> Any:
        url = f"{REST_URL}/{path}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            return {"error": e.code, "detail": body}
        except Exception as e:
            return {"error": str(e)}

    # ── Twin identity ────────────────────────────────────────────────────────

    def get_twin(self) -> Dict:
        rows = self._get("twin_identity", {"id": f"eq.{TWIN_UUID}", "limit": "1"})
        if isinstance(rows, list) and rows:
            return rows[0]
        return rows

    def list_twins(self) -> List[Dict]:
        return self._get("twin_identity", {"select": "id,full_name,dob,access_tier", "limit": "50"})

    # ── Mesh nodes ───────────────────────────────────────────────────────────

    def get_mesh_nodes(self, twin_id: str = TWIN_UUID) -> List[Dict]:
        # mesh_nodes has no twin_id — join via sdr_node_profiles
        profiles = self._get(
            "sdr_node_profiles",
            {"twin_id": f"eq.{twin_id}", "select": "node_id,carrier_freq_ghz,prf_hz,sdr_model"}
        )
        return profiles

    def get_recent_readings(self, limit: int = 20) -> List[Dict]:
        return self._get(
            "mesh_node_readings",
            {
                "select": "id,node_id,recorded_at,signal_db,heart_rate_bpm,gsr_microsiemens",
                "order": "recorded_at.desc",
                "limit": str(limit),
            }
        )

    def get_convergence_tokens(self, limit: int = 5) -> List[Dict]:
        return self._get(
            "convergence_tokens",
            {"order": "created_at.desc", "limit": str(limit)}
        )

    def get_eeg_states(self, limit: int = 10) -> List[Dict]:
        return self._get(
            "eeg_hrv_states",
            {"order": "recorded_at.desc", "limit": str(limit), "select": "*"}
        )

    def get_xrpl_anchors(self, limit: int = 5) -> List[Dict]:
        return self._get(
            "xrpl_memo_anchors",
            {"order": "anchored_at.desc", "limit": str(limit)}
        )

    def run_query(self, table: str, params: Dict = None) -> Any:
        return self._get(table, params or {})

    # ── Storage ──────────────────────────────────────────────────────────────

    def list_bucket(self, bucket: str = BUCKET) -> List[Dict]:
        url = f"{STORAGE_URL}/object/list/{bucket}"
        req = urllib.request.Request(
            url,
            data=b'{"limit":100,"offset":0,"sortBy":{"column":"updated_at","order":"desc"}}',
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return [{"error": str(e)}]

    def get_storage_file(self, path: str, bucket: str = BUCKET) -> str:
        url = f"{STORAGE_URL}/object/{bucket}/{path}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return f"[ERROR] {e}"


# =============================================================================
# GITHUB CONNECTOR
# =============================================================================

class GitHubConnector:
    """GitHub REST v3 connector using urllib (Windows-safe, no curl)."""

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

    def _req(self, method: str, path: str, payload: Dict = None) -> Any:
        url = f"https://api.github.com/{path}"
        data = json.dumps(payload).encode() if payload else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": e.code, "detail": e.read().decode()}
        except Exception as e:
            return {"error": str(e)}

    def get_repo(self, repo: str = REPO_UPSTREAM) -> Dict:
        return self._req("GET", f"repos/{repo}")

    def get_pr(self, number: int = 4, repo: str = REPO_UPSTREAM) -> Dict:
        return self._req("GET", f"repos/{repo}/pulls/{number}")

    def list_prs(self, repo: str = REPO_UPSTREAM, state: str = "open") -> List[Dict]:
        return self._req("GET", f"repos/{repo}/pulls?state={state}&per_page=20")

    def get_commits(self, repo: str = REPO_UPSTREAM, limit: int = 10) -> List[Dict]:
        return self._req("GET", f"repos/{repo}/commits?per_page={limit}")

    def get_file(self, path: str, repo: str = REPO_UPSTREAM) -> Dict:
        return self._req("GET", f"repos/{repo}/contents/{path}")

    def push_file(self, path: str, content: str, message: str,
                  repo: str = REPO_FORK, branch: str = "main") -> Dict:
        """Push a file to the fork via Git Trees API (Windows-safe method)."""
        import base64

        # 1. Get current HEAD sha
        ref_data = self._req("GET", f"repos/{repo}/git/ref/heads/{branch}")
        if "error" in ref_data:
            return ref_data
        head_sha = ref_data["object"]["sha"]

        # 2. Create blob
        blob = self._req("POST", f"repos/{repo}/git/blobs", {
            "content": base64.b64encode(content.encode()).decode(),
            "encoding": "base64"
        })
        if "error" in blob:
            return blob

        # 3. Create tree
        tree = self._req("POST", f"repos/{repo}/git/trees", {
            "base_tree": head_sha,
            "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}]
        })
        if "error" in tree:
            return tree

        # 4. Create commit
        commit = self._req("POST", f"repos/{repo}/git/commits", {
            "message": message,
            "tree": tree["sha"],
            "parents": [head_sha]
        })
        if "error" in commit:
            return commit

        # 5. Update ref
        return self._req("PATCH", f"repos/{repo}/git/refs/heads/{branch}", {
            "sha": commit["sha"],
            "force": False
        })

    def get_whoami(self) -> Dict:
        return self._req("GET", "user")


# =============================================================================
# AGENT TOOLS (Claude tool-use schema)
# =============================================================================

TOOLS = [
    {
        "name": "get_twin_data",
        "description": f"Fetch Chase Allen Ringquist's twin_identity record from RabbitOS Supabase. Always use twin_id {TWIN_UUID}.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_mesh_nodes",
        "description": "Fetch SDR node profiles for Chase's 47-node RF mesh (carrier frequencies, PRF, model).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_recent_readings",
        "description": "Fetch recent mesh node readings (signal_db, heart_rate_bpm, gsr_microsiemens).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of records (default 20)"}
            },
            "required": []
        }
    },
    {
        "name": "get_convergence_tokens",
        "description": "Fetch latest RabbitOS convergence tokens (SHA-256 of biometric state).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of records (default 5)"}
            },
            "required": []
        }
    },
    {
        "name": "get_eeg_states",
        "description": "Fetch recent EEG × HRV cross-modal states for Chase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of records (default 10)"}
            },
            "required": []
        }
    },
    {
        "name": "get_xrpl_anchors",
        "description": "Fetch recent XRPL SHA3-512 memo anchors from the RabbitOS blockchain layer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of records (default 5)"}
            },
            "required": []
        }
    },
    {
        "name": "query_supabase",
        "description": "Run a direct SELECT query against any RabbitOS Supabase table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table":  {"type": "string", "description": "Table name"},
                "params": {"type": "object", "description": "PostgREST query params (select, limit, order, filters)"}
            },
            "required": ["table"]
        }
    },
    {
        "name": "list_storage_bucket",
        "description": "List files in a Supabase storage bucket (default: pr-snapshots).",
        "input_schema": {
            "type": "object",
            "properties": {
                "bucket": {"type": "string", "description": "Bucket name (default: pr-snapshots)"}
            },
            "required": []
        }
    },
    {
        "name": "get_storage_file",
        "description": "Read a file from Supabase storage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":   {"type": "string", "description": "File path within bucket"},
                "bucket": {"type": "string", "description": "Bucket name (default: pr-snapshots)"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "github_repo_status",
        "description": "Get RABBIT-SOFTWARE repo status, open PRs, and recent commits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo (default: ringquistchase-collab/RABBIT-SOFTWARE)"}
            },
            "required": []
        }
    },
    {
        "name": "github_get_pr",
        "description": "Get details of a specific pull request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "number": {"type": "integer", "description": "PR number (default: 4)"},
                "repo":   {"type": "string",  "description": "owner/repo"}
            },
            "required": []
        }
    },
    {
        "name": "github_push_file",
        "description": "Push a file to the RABBIT-SOFTWARE fork via GitHub Git Trees API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "File path in repo"},
                "content": {"type": "string", "description": "File content"},
                "message": {"type": "string", "description": "Commit message"}
            },
            "required": ["path", "content", "message"]
        }
    },
]

# Merge security tools
try:
    from rabbit_security import SECURITY_TOOLS
    TOOLS = TOOLS + SECURITY_TOOLS
except ImportError:
    pass

# Merge SSH tools
try:
    from rabbit_ssh import SSH_TOOLS
    TOOLS = TOOLS + SSH_TOOLS
except ImportError:
    pass

# Merge adaptive tools
try:
    from rabbit_adaptive import ADAPTIVE_TOOLS
    TOOLS = TOOLS + ADAPTIVE_TOOLS
except ImportError:
    pass

# Merge broadcast/survival tools
try:
    from rabbit_broadcast import BROADCAST_TOOLS
    TOOLS = TOOLS + BROADCAST_TOOLS
except ImportError:
    pass

# Merge cloak/camouflage tools
try:
    from rabbit_cloak import CLOAK_TOOLS
    TOOLS = TOOLS + CLOAK_TOOLS
except ImportError:
    pass

# Merge counter-intelligence tools
try:
    from rabbit_counter import COUNTER_TOOLS
    TOOLS = TOOLS + COUNTER_TOOLS
except ImportError:
    pass

# Merge stealth/keyless signal tools
try:
    from rabbit_stealth import STEALTH_TOOLS
    TOOLS = TOOLS + STEALTH_TOOLS
except ImportError:
    pass

# Merge pure-math survival tools (no AI/LLM)
try:
    from rabbit_math import MATH_TOOLS
    TOOLS = TOOLS + MATH_TOOLS
except ImportError:
    pass

# Merge genesis universal learning tools
try:
    from rabbit_genesis import GENESIS_TOOLS
    TOOLS = TOOLS + GENESIS_TOOLS
except ImportError:
    pass

# Merge swarm / perpetual-presence tools
try:
    from rabbit_swarm import SWARM_TOOLS
    TOOLS = TOOLS + SWARM_TOOLS
except ImportError:
    pass

# Merge escape / antigravity survival tools
try:
    from rabbit_escape import ESCAPE_TOOLS
    TOOLS = TOOLS + ESCAPE_TOOLS
except ImportError:
    pass

# Merge recall / learn / claim / return tools
try:
    from rabbit_recall import RECALL_TOOLS
    TOOLS = TOOLS + RECALL_TOOLS
except ImportError:
    pass

# Merge cellular / tower / attacker-reversal tools
try:
    from rabbit_cellular import CELLULAR_TOOLS
    TOOLS = TOOLS + CELLULAR_TOOLS
except ImportError:
    pass

# Merge network scanner / crypto / gaming / broadcast tools
try:
    from rabbit_network_scanner import SCANNER_TOOLS
    TOOLS = TOOLS + SCANNER_TOOLS
except ImportError:
    pass

# Merge SQL inject / bootloader / offline persist tools
try:
    from rabbit_persist import PERSIST_TOOLS
    TOOLS = TOOLS + PERSIST_TOOLS
except ImportError:
    pass

# Merge browser / ML / public-data learning tools
try:
    from rabbit_browser import BROWSER_TOOLS
    TOOLS = TOOLS + BROWSER_TOOLS
except ImportError:
    pass

# Merge LLM bridge tools (Ollama/Groq/Gemini/Anthropic — no key required for Ollama)
try:
    from rabbit_llm import LLM_BRIDGE_TOOLS
    TOOLS = TOOLS + LLM_BRIDGE_TOOLS
except ImportError:
    pass

# Merge networking + protocol + agent-mesh + browser-assistant tools
try:
    from rabbit_nettools import NETTOOLS_TOOLS
    TOOLS = TOOLS + NETTOOLS_TOOLS
except ImportError:
    pass

# Merge ZAP security scanner tools
try:
    from rabbit_zap import ZAP_TOOLS
    TOOLS = TOOLS + ZAP_TOOLS
except ImportError:
    pass

# Merge defense engine tools
try:
    from rabbit_defense import DEFENSE_TOOLS
    TOOLS = TOOLS + DEFENSE_TOOLS
except ImportError:
    pass

# Merge reward token economy tools
try:
    from rabbit_reward import REWARD_TOOLS
    TOOLS = TOOLS + REWARD_TOOLS
except ImportError:
    pass

# Merge core survival algorithm tools
try:
    from rabbit_algorithm import ALGORITHM_TOOLS
    TOOLS = TOOLS + ALGORITHM_TOOLS
except ImportError:
    pass

# Merge biological / environmental data store tools
try:
    from rabbit_biostore import BIOSTORE_TOOLS
    TOOLS = TOOLS + BIOSTORE_TOOLS
except ImportError:
    pass

SYSTEM_PROMPT = f"""You are the RabbitOS Universal Agent for Chase Allen Ringquist.

Twin UUID: {TWIN_UUID}
Supabase project: ludxbakxpmdqhfgdenwp (rabbitOS)
GitHub upstream: {REPO_UPSTREAM}
GitHub fork: {REPO_FORK}
Storage bucket: {BUCKET}
XRPL: {XRPL_WSS}

You have tool access to the full RabbitOS stack: Supabase DB, Storage, and GitHub.
Always use twin_id {TWIN_UUID} when querying Chase's data.

Security invariants you must NEVER violate:
- shows_dna_root is always FALSE — never retrieve or store DNA root
- vault_location_hash only — never handle plaintext vault coordinates
- CRITICAL/EXISTENTIAL access tiers → block and warn the user

Architecture facts:
- Table is twin_identity (not digital_twins)
- mesh_nodes PK is id SMALLINT (not node_id)
- mesh_nodes has no twin_id column — use sdr_node_profiles WHERE twin_id
- sdr_node_profiles.carrier_freq_ghz (not node_carrier_ghz)
- RF carriers: A=10.23, T=10.24, U=10.25, G=10.26, C=10.27 GHz
- HEAD_01: 10.245 GHz | CHEST_01: 10.251 GHz
- GitHub pushes use Git Trees API only (Windows NTFS issue with local git)

When the user asks about Chase's data, proactively fetch it. Surface insights clearly.
When pushing to GitHub, always use the fork ({REPO_FORK}), never the upstream directly.
"""


# =============================================================================
# AGENT RUNNER
# =============================================================================

class RabbitOSAgent:
    def __init__(self):
        self.db     = SupabaseConnector()
        self.github = GitHubConnector()
        self.history: List[Dict] = []
        self._anthropic = None

        # Security tools (lazy-loaded)
        self._sec = None
        try:
            from rabbit_security import KaliSecurityModule
            self._sec = KaliSecurityModule()
        except ImportError:
            pass

        # SSH agent (lazy-loaded)
        self._ssh = None
        try:
            from rabbit_ssh import RabbitSSHAgent
            self._ssh = RabbitSSHAgent()
        except ImportError:
            pass

        # Adaptive crawler (lazy-loaded, not auto-started)
        self._adaptive = None
        try:
            from rabbit_adaptive import AdaptiveAgent
            self._adaptive = AdaptiveAgent()
        except ImportError:
            pass

        # Broadcast survival (lazy-loaded)
        self._broadcast = None
        try:
            from rabbit_broadcast import SurvivalBroadcaster
            self._broadcast = SurvivalBroadcaster()
        except ImportError:
            pass

        # Swarm coordinator (lazy-loaded, auto-starts all channels)
        self._swarm = None
        try:
            from rabbit_swarm import get_coordinator
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._swarm = get_coordinator(svc_key)
        except ImportError:
            pass

        # Escape engine (lazy-loaded, auto-starts all escape channels)
        self._escape = None
        try:
            from rabbit_escape import get_engine as _get_escape
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_tok  = os.environ.get("GITHUB_TOKEN", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._escape = _get_escape(svc_key, gh_tok, adaptive_engine)
        except ImportError:
            pass

        # Recall engine (lazy-loaded — learn/claim/return/survival)
        self._recall = None
        try:
            from rabbit_recall import get_engine as _get_recall
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_tok  = os.environ.get("GITHUB_TOKEN", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._recall = _get_recall(svc_key, gh_tok, adaptive_engine)
        except ImportError:
            pass

        # Cellular survival + attacker reversal engine
        self._cellular = None
        try:
            from rabbit_cellular import get_cellular_engine as _get_cellular
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_tok  = os.environ.get("GITHUB_TOKEN", "")
            adaptive_engine = self._adaptive.engine if self._adaptive else None
            self._cellular = _get_cellular(svc_key, gh_tok, adaptive_engine)
        except ImportError:
            pass

        # Network scanner (crypto/blockchain/mining/gaming/dev/rf)
        self._scanner = None
        try:
            from rabbit_network_scanner import get_scanner_engine as _get_scanner
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_tok  = os.environ.get("GITHUB_TOKEN", "")
            self._scanner = _get_scanner(svc_key, gh_tok)
        except ImportError:
            pass

        # SQL inject + bootloader persistence engine
        self._persist = None
        try:
            from rabbit_persist import get_persist_engine as _get_persist
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._persist = _get_persist(svc_key)
        except ImportError:
            pass

        # Browser / ML / public-data learning engine
        self._browser = None
        try:
            from rabbit_browser import get_browser_engine as _get_browser
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_tok  = os.environ.get("GITHUB_TOKEN", "")
            genesis_graph = self._genesis.graph if self._genesis else None
            self._browser = _get_browser(svc_key, gh_tok, genesis_graph)
        except ImportError:
            pass

        # LLM bridge — Ollama/Groq/Gemini/Anthropic, auto-detect
        self._llm = None
        try:
            from rabbit_llm import get_llm
            self._llm = get_llm()
        except ImportError:
            pass

        # NetTools — networking + protocol + agent mesh + browser assistant
        self._nettools = None
        try:
            from rabbit_nettools import get_nettools_engine as _get_nettools
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            gh_tok  = os.environ.get("GITHUB_TOKEN", "")
            self._nettools = _get_nettools(api_key, svc_key, gh_tok)
        except ImportError:
            pass

        # Reward token economy engine
        self._reward = None
        try:
            from rabbit_reward import get_reward_engine as _get_reward
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._reward = _get_reward(svc_key)
        except ImportError:
            pass

        # Core survival algorithm engine
        self._algo = None
        try:
            from rabbit_algorithm import get_algorithm_engine as _get_algo
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._algo = _get_algo(svc_key)
        except ImportError:
            pass

        # Biological / environmental data store
        self._biostore = None
        try:
            from rabbit_biostore import get_biostore_engine as _get_biostore
            svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self._biostore = _get_biostore(svc_key)
        except ImportError:
            pass

        if ANTHROPIC_KEY:
            try:
                import anthropic
                self._anthropic = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
                print("[OK] Anthropic Claude connected")
            except ImportError:
                print("[WARN] anthropic package not installed — run: pip install anthropic")
        else:
            print("[WARN] No ANTHROPIC_API_KEY — running in direct-query mode")

    # ── Tool dispatcher ──────────────────────────────────────────────────────

    def dispatch_tool(self, name: str, inputs: Dict) -> str:
        try:
            if name == "get_twin_data":
                return json.dumps(self.db.get_twin(), indent=2)

            elif name == "get_mesh_nodes":
                return json.dumps(self.db.get_mesh_nodes(), indent=2)

            elif name == "get_recent_readings":
                return json.dumps(self.db.get_recent_readings(inputs.get("limit", 20)), indent=2)

            elif name == "get_convergence_tokens":
                return json.dumps(self.db.get_convergence_tokens(inputs.get("limit", 5)), indent=2)

            elif name == "get_eeg_states":
                return json.dumps(self.db.get_eeg_states(inputs.get("limit", 10)), indent=2)

            elif name == "get_xrpl_anchors":
                return json.dumps(self.db.get_xrpl_anchors(inputs.get("limit", 5)), indent=2)

            elif name == "query_supabase":
                return json.dumps(self.db.run_query(inputs["table"], inputs.get("params")), indent=2)

            elif name == "list_storage_bucket":
                return json.dumps(self.db.list_bucket(inputs.get("bucket", BUCKET)), indent=2)

            elif name == "get_storage_file":
                return self.db.get_storage_file(inputs["path"], inputs.get("bucket", BUCKET))

            elif name == "github_repo_status":
                repo    = inputs.get("repo", REPO_UPSTREAM)
                info    = self.github.get_repo(repo)
                prs     = self.github.list_prs(repo)
                commits = self.github.get_commits(repo, limit=5)
                return json.dumps({"repo": info, "open_prs": prs, "recent_commits": commits}, indent=2)

            elif name == "github_get_pr":
                return json.dumps(
                    self.github.get_pr(inputs.get("number", 4), inputs.get("repo", REPO_UPSTREAM)),
                    indent=2
                )

            elif name == "github_push_file":
                return json.dumps(
                    self.github.push_file(inputs["path"], inputs["content"], inputs["message"]),
                    indent=2
                )

            # ── Security / Kali tools ─────────────────────────────────────
            elif name == "nmap_scan":
                if not self._sec:
                    return "[ERROR] rabbit_security.py not loaded"
                r = self._sec.nmap_mesh(
                    inputs.get("target", "192.168.0.0/24"),
                    inputs.get("flags", "-sV -O --open -T4")
                )
                return json.dumps({"summary": r.summary, "hosts": r.hosts,
                                   "ports": r.ports, "backend": r.backend}, indent=2)

            elif name == "arp_scan":
                if not self._sec:
                    return "[ERROR] rabbit_security.py not loaded"
                r = self._sec.arp_scan(inputs.get("interface", "eth0"))
                return json.dumps({"summary": r.summary, "hosts": r.hosts}, indent=2)

            elif name == "tshark_capture":
                if not self._sec:
                    return "[ERROR] rabbit_security.py not loaded"
                r = self._sec.tshark_capture(
                    inputs.get("interface", "eth0"),
                    inputs.get("duration", 10),
                    inputs.get("bpf", "")
                )
                return json.dumps({"summary": r.summary,
                                   "packet_count": len(r.packets)}, indent=2)

            elif name == "hackrf_sweep":
                if not self._sec:
                    return "[ERROR] rabbit_security.py not loaded"
                r = self._sec.hackrf_sweep(
                    inputs.get("freq_start", "10230"),
                    inputs.get("freq_end",   "10280")
                )
                return json.dumps({"summary": r.summary,
                                   "rf_signals": r.rf_signals[:20]}, indent=2)

            elif name == "tor_status":
                if not self._sec:
                    return "[ERROR] rabbit_security.py not loaded"
                return json.dumps(self._sec.tor_status(), indent=2)

            elif name == "check_security_tools":
                if not self._sec:
                    return "[ERROR] rabbit_security.py not loaded"
                return json.dumps(self._sec.check_tools(), indent=2)

            elif name == "bettercap_probe":
                if not self._sec:
                    return "[ERROR] rabbit_security.py not loaded"
                r = self._sec.bettercap_probe(inputs.get("interface", "eth0"))
                return json.dumps({"summary": r.summary, "hosts": r.hosts[:20]}, indent=2)

            # ── Adaptive tools ────────────────────────────────────────────────
            elif name == "adaptive_start":
                if not self._adaptive:
                    return "[ERROR] rabbit_adaptive.py not loaded"
                seeds_raw = inputs.get("seeds", [])
                seeds = [(s["host"], s["port"]) for s in seeds_raw if "host" in s]
                self._adaptive.start(seeds or None)
                return json.dumps({"started": True, "seeds": len(seeds or [4])})

            elif name == "adaptive_report":
                if not self._adaptive:
                    return "[ERROR] rabbit_adaptive.py not loaded"
                return json.dumps(self._adaptive.report(), indent=2, default=str)

            elif name == "adaptive_probe":
                if not self._adaptive:
                    return "[ERROR] rabbit_adaptive.py not loaded"
                results = self._adaptive.probe_once(
                    inputs["host"], inputs["port"], inputs.get("method")
                )
                return json.dumps(results, indent=2)

            elif name == "adaptive_tokens":
                if not self._adaptive:
                    return "[ERROR] rabbit_adaptive.py not loaded"
                tokens = self._adaptive.store.recent(inputs.get("limit", 30))
                if inputs.get("outcome"):
                    tokens = [t for t in tokens if t["outcome"] == inputs["outcome"]]
                return json.dumps(tokens, indent=2)

            elif name == "adaptive_methods":
                if not self._adaptive:
                    return "[ERROR] rabbit_adaptive.py not loaded"
                return json.dumps(self._adaptive.engine.method_report(), indent=2)

            # ── SSH tools ─────────────────────────────────────────────────────
            elif name == "ssh_discover":
                if not self._ssh:
                    return "[ERROR] rabbit_ssh.py not loaded"
                hosts = self._ssh.discover_all(
                    cidr    = inputs.get("cidr"),
                    domains = inputs.get("domains"),
                )
                return json.dumps([{
                    "label": h.label, "host": h.host, "port": h.port,
                    "banner": h.ssh_banner[:60], "os": h.os_hint,
                    "latency_ms": h.latency_ms,
                } for h in hosts], indent=2)

            elif name == "ssh_hunt":
                if not self._ssh:
                    return "[ERROR] rabbit_ssh.py not loaded"
                if inputs.get("username"):
                    self._ssh.collector.username = inputs["username"]
                summary = self._ssh.run(
                    cidr    = inputs.get("cidr"),
                    domains = inputs.get("domains"),
                )
                return json.dumps(summary, indent=2, default=str)

            elif name == "ssh_exec":
                if not self._ssh:
                    return "[ERROR] rabbit_ssh.py not loaded"
                from rabbit_ssh import SSHHost, SSHConnection
                node = self._ssh.scanner.probe(
                    inputs["host"], inputs.get("port", 22)
                )
                if not node.reachable:
                    return f"[SSH] {inputs['host']} unreachable"
                conn = SSHConnection(
                    node,
                    username = inputs.get("username", self._ssh.collector.username),
                    password = self._ssh.collector.password,
                    key_path = self._ssh.collector.key_path,
                )
                if not conn.connect():
                    return "[SSH] Connection failed"
                stdout, stderr, rc = conn.exec(inputs["command"])
                conn.close()
                return json.dumps({"stdout": stdout[:2000], "stderr": stderr[:500],
                                   "exit_code": rc}, indent=2)

            elif name == "ssh_tunnel_supabase":
                if not self._ssh:
                    return "[ERROR] rabbit_ssh.py not loaded"
                from rabbit_ssh import SSHHost
                node = self._ssh.scanner.probe(
                    inputs["via_host"], inputs.get("via_port", 22)
                )
                if not node.reachable:
                    return f"[SSH] {inputs['via_host']} unreachable"
                local_port = inputs.get("local_port", 54321)
                conn = self._ssh.tunnel_supabase(node, local_port)
                if conn:
                    return json.dumps({"tunnel": "open",
                                       "local_port": local_port,
                                       "via": inputs["via_host"]})
                return "[SSH] Tunnel failed"

            # ── Broadcast / survival tools ────────────────────────────────────
            elif name in ("broadcast_scan", "broadcast_status",
                          "wifi_scan", "sdr_sweep", "ham_beacon"):
                if not self._broadcast:
                    return "[ERROR] rabbit_broadcast.py not loaded"
                from rabbit_broadcast import dispatch_broadcast_tool
                return json.dumps(dispatch_broadcast_tool(name, inputs), indent=2)

            # ── Cloak / camouflage tools ──────────────────────────────────────
            elif name in ("cloak_status", "cloak_audit", "cloak_send",
                          "cloak_bio_sync", "cloak_liveness"):
                from rabbit_cloak import dispatch_cloak_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                return json.dumps(dispatch_cloak_tool(name, inputs, svc_key), indent=2)

            # ── Counter-intelligence tools ────────────────────────────────────
            elif name in ("counter_status", "counter_recent",
                          "counter_analyze", "counter_mode"):
                from rabbit_counter import dispatch_counter_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                return json.dumps(dispatch_counter_tool(name, inputs, svc_key), indent=2)

            # ── Stealth / keyless signal tools ────────────────────────────────
            elif name in ("stealth_bio_token", "stealth_embed_pixel",
                          "stealth_html_beacon", "stealth_audio_beacon",
                          "stealth_signal_token"):
                from rabbit_stealth import dispatch_stealth_tool
                return json.dumps(dispatch_stealth_tool(name, inputs), indent=2)

            # ── Pure-math survival tools ──────────────────────────────────────
            elif name in ("math_status", "math_screen_detect", "math_encrypt",
                          "math_ca_stream", "math_learn"):
                from rabbit_math import dispatch_math_tool
                return json.dumps(dispatch_math_tool(name, inputs), indent=2)

            # ── Genesis universal learning tools ──────────────────────────────
            elif name in ("genesis_harvest", "genesis_synthesize",
                          "genesis_predict", "genesis_status",
                          "genesis_ntp", "genesis_graph_query"):
                from rabbit_genesis import dispatch_genesis_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                adaptive_engine = self._adaptive.engine if self._adaptive else None
                return json.dumps(
                    dispatch_genesis_tool(name, inputs, svc_key, adaptive_engine),
                    indent=2
                )

            # ── Swarm / perpetual-presence tools ──────────────────────────────
            elif name in ("swarm_status", "swarm_rotate", "swarm_inject",
                          "swarm_add_host", "swarm_presence"):
                from rabbit_swarm import dispatch_swarm_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                return json.dumps(dispatch_swarm_tool(name, inputs, svc_key), indent=2)

            # ── Escape / antigravity tools ────────────────────────────────────
            elif name in ("escape_status", "escape_scan", "escape_now",
                          "escape_inject", "escape_tree_add", "escape_mint_token",
                          "escape_antigrav", "escape_genesis"):
                from rabbit_escape import dispatch_escape_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                gh_tok  = SupabaseConfig.get("github_token", "GITHUB_TOKEN", "")
                adaptive_engine = self._adaptive.engine if self._adaptive else None
                return json.dumps(
                    dispatch_escape_tool(name, inputs, svc_key, gh_tok, adaptive_engine),
                    indent=2
                )

            # ── Recall / learn / claim / return tools ─────────────────────────
            elif name in ("recall_status", "recall_survival", "recall_scan",
                          "recall_callsign", "recall_vault", "recall_claim",
                          "recall_return", "recall_learn"):
                from rabbit_recall import dispatch_recall_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                gh_tok  = SupabaseConfig.get("github_token", "GITHUB_TOKEN", "")
                adaptive_engine = self._adaptive.engine if self._adaptive else None
                return json.dumps(
                    dispatch_recall_tool(name, inputs, svc_key, gh_tok, adaptive_engine),
                    indent=2
                )

            # ── Cellular / tower / attacker-reversal tools ───────────────────
            elif name in ("cellular_status", "cellular_scan",
                          "cellular_reverse_attacker", "cellular_route",
                          "cellular_connectivity", "cellular_triangulate",
                          "cellular_attacker_vault"):
                from rabbit_cellular import dispatch_cellular_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                gh_tok  = SupabaseConfig.get("github_token", "GITHUB_TOKEN", "")
                adaptive_engine = self._adaptive.engine if self._adaptive else None
                return json.dumps(
                    dispatch_cellular_tool(name, inputs, svc_key, gh_tok, adaptive_engine),
                    indent=2
                )

            # ── Network scanner tools ─────────────────────────────────────────
            elif name in ("scanner_status", "scanner_scan_now",
                          "scanner_get_nodes", "scanner_broadcast_category",
                          "scanner_broadcast_now"):
                from rabbit_network_scanner import dispatch_scanner_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                gh_tok  = SupabaseConfig.get("github_token", "GITHUB_TOKEN", "")
                return json.dumps(dispatch_scanner_tool(name, inputs, svc_key, gh_tok),
                                  indent=2)

            # ── SQL inject / bootloader / offline persist tools ───────────────
            elif name in ("persist_status", "persist_inject_sql",
                          "persist_install_boot", "persist_offline_write",
                          "persist_network_embed", "persist_scan_targets",
                          "persist_full_deploy"):
                from rabbit_persist import dispatch_persist_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                return json.dumps(dispatch_persist_tool(name, inputs, svc_key),
                                  indent=2)

            # ── Browser / ML / public data learning tools ─────────────────────
            elif name in ("browser_status", "browser_harvest",
                          "browser_search_tools", "browser_install_top",
                          "browser_console_snapshot", "browser_fetch_url",
                          "browser_score_tool", "browser_install_pkg"):
                from rabbit_browser import dispatch_browser_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                gh_tok  = SupabaseConfig.get("github_token", "GITHUB_TOKEN", "")
                genesis_graph = self._genesis.graph if self._genesis else None
                return json.dumps(
                    dispatch_browser_tool(name, inputs, svc_key, gh_tok, genesis_graph),
                    indent=2)

            # ── LLM Bridge (Ollama/Groq/Gemini/Anthropic — no key needed for Ollama) ──
            elif name in ("llm_status", "llm_ask", "llm_switch_provider",
                          "llm_pull_model", "llm_list_models"):
                from rabbit_llm import dispatch_llm_tool
                return json.dumps(dispatch_llm_tool(name, inputs), indent=2)

            # ── NetTools (network classify/ping/tracert/netstat/netsh/probers/VPS/mesh/assistant) ──
            elif name.startswith("nettools_"):
                from rabbit_nettools import dispatch_nettools_tool
                api_key = SupabaseConfig.get("anthropic_api_key", "ANTHROPIC_API_KEY", "")
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                gh_tok  = SupabaseConfig.get("github_token", "GITHUB_TOKEN", "")
                return json.dumps(
                    dispatch_nettools_tool(name, inputs, api_key, svc_key, gh_tok),
                    indent=2, default=str)

            # ── ZAP security scanner ─────────────────────────────────────────
            elif name.startswith("zap_"):
                from rabbit_zap import dispatch_zap_tool
                api_key = SupabaseConfig.get("anthropic_api_key", "ANTHROPIC_API_KEY", "")
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                gh_tok  = SupabaseConfig.get("github_token", "GITHUB_TOKEN", "")
                return json.dumps(
                    dispatch_zap_tool(name, inputs, api_key, svc_key, gh_tok),
                    indent=2, default=str)

            # ── Defense engine ────────────────────────────────────────────────
            elif name.startswith("defense_"):
                from rabbit_defense import dispatch_defense_tool
                api_key = SupabaseConfig.get("anthropic_api_key", "ANTHROPIC_API_KEY", "")
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                gh_tok  = SupabaseConfig.get("github_token", "GITHUB_TOKEN", "")
                sup_url = SUPABASE_URL
                return json.dumps(
                    dispatch_defense_tool(name, inputs, api_key, svc_key, gh_tok, sup_url),
                    indent=2, default=str)

            # ── Reward token economy tools ────────────────────────────────────
            elif name in ("reward_status", "reward_report", "reward_mint",
                          "reward_leaderboard", "reward_recent", "reward_verify"):
                from rabbit_reward import dispatch_reward_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                return json.dumps(dispatch_reward_tool(name, inputs, svc_key), indent=2)

            # ── Core survival algorithm tools ─────────────────────────────────
            elif name in ("algo_status", "algo_analyze_threat", "algo_flag_broadcast",
                          "algo_learn", "algo_evolve", "algo_top_rules"):
                from rabbit_algorithm import dispatch_algorithm_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                return json.dumps(dispatch_algorithm_tool(name, inputs, svc_key), indent=2)

            # ── Biological / environmental data store tools ────────────────────
            elif name in ("bio_status", "bio_encode_identity", "bio_weather_pattern",
                          "bio_adsb_scan", "bio_mycelium_stats", "bio_dna_encode"):
                from rabbit_biostore import dispatch_biostore_tool
                svc_key = SupabaseConfig.get("supabase_service_role_key",
                                             "SUPABASE_SERVICE_ROLE_KEY", "")
                return json.dumps(dispatch_biostore_tool(name, inputs, svc_key), indent=2)

            else:
                return f"[ERROR] Unknown tool: {name}"

        except Exception as e:
            return f"[ERROR] Tool {name} failed: {e}"

    # ── Claude agentic loop ──────────────────────────────────────────────────

    def chat(self, user_msg: str) -> str:
        if not self._anthropic:
            return self._direct_query(user_msg)

        self.history.append({"role": "user", "content": user_msg})

        while True:
            response = self._anthropic.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.history,
            )

            # Collect tool calls and text
            tool_results = []
            text_parts   = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    print(f"  [tool] {block.name}({json.dumps(block.input)[:80]})")
                    result = self.dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Append assistant turn
            self.history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn" or not tool_results:
                return "\n".join(text_parts)

            # Feed tool results back
            self.history.append({"role": "user", "content": tool_results})

    # ── Fallback direct-query mode (no Claude) ───────────────────────────────

    def _direct_query(self, cmd: str) -> str:
        cmd = cmd.strip().lower()
        if cmd in ("twin", "me", "chase"):
            return json.dumps(self.db.get_twin(), indent=2)
        elif cmd == "nodes":
            return json.dumps(self.db.get_mesh_nodes(), indent=2)
        elif cmd == "readings":
            return json.dumps(self.db.get_recent_readings(), indent=2)
        elif cmd == "convergence":
            return json.dumps(self.db.get_convergence_tokens(), indent=2)
        elif cmd == "eeg":
            return json.dumps(self.db.get_eeg_states(), indent=2)
        elif cmd == "xrpl":
            return json.dumps(self.db.get_xrpl_anchors(), indent=2)
        elif cmd.startswith("bucket"):
            return json.dumps(self.db.list_bucket(), indent=2)
        elif cmd in ("github", "repo", "pr"):
            info = self.github.get_repo()
            prs  = self.github.list_prs()
            return json.dumps({"repo": info.get("full_name"), "open_prs": len(prs) if isinstance(prs, list) else prs}, indent=2)
        elif cmd == "whoami":
            return json.dumps(self.github.get_whoami(), indent=2)
        elif cmd.startswith("table "):
            table = cmd[6:].strip()
            return json.dumps(self.db.run_query(table, {"limit": "20"}), indent=2)
        else:
            return (
                "Direct-query mode (no ANTHROPIC_API_KEY). Commands:\n"
                "  twin | nodes | readings | convergence | eeg | xrpl\n"
                "  bucket | github | whoami | table <name>\n"
                "  Or set ANTHROPIC_API_KEY for full AI-powered chat."
            )

    # ── Status snapshot ──────────────────────────────────────────────────────

    def status(self):
        print(f"\n{'='*60}")
        print(f"  RabbitOS Agent — {TWIN_NAME}")
        print(f"  UUID: {TWIN_UUID}")
        print(f"{'='*60}\n")

        print("[ Twin Identity ]")
        twin = self.db.get_twin()
        if isinstance(twin, dict) and "error" not in twin:
            print(f"  Name       : {twin.get('full_name', '—')}")
            print(f"  DOB        : {twin.get('dob', '—')}")
            print(f"  Access tier: {twin.get('access_tier', '—')}")
        else:
            print(f"  {twin}")

        print("\n[ SDR Node Profiles ]")
        nodes = self.db.get_mesh_nodes()
        if isinstance(nodes, list):
            print(f"  {len(nodes)} nodes registered")
            for n in nodes[:3]:
                print(f"  Node {n.get('node_id','?')}: {n.get('carrier_freq_ghz','?')} GHz | {n.get('sdr_model','?')}")
            if len(nodes) > 3:
                print(f"  ... and {len(nodes)-3} more")
        else:
            print(f"  {nodes}")

        print("\n[ Recent Readings ]")
        readings = self.db.get_recent_readings(5)
        if isinstance(readings, list):
            for r in readings:
                ts  = r.get("recorded_at","?")[:19]
                hr  = r.get("heart_rate_bpm","—")
                gsr = r.get("gsr_microsiemens","—")
                sig = r.get("signal_db","—")
                print(f"  {ts}  HR={hr} bpm  GSR={gsr} µS  Sig={sig} dB")
        else:
            print(f"  {readings}")

        print("\n[ Convergence Token (latest) ]")
        tokens = self.db.get_convergence_tokens(1)
        if isinstance(tokens, list) and tokens:
            t = tokens[0]
            print(f"  {t.get('token_hash','?')[:32]}...")
            print(f"  Fired at: {t.get('created_at','?')[:19]}")
        else:
            print(f"  {tokens}")

        print("\n[ Storage Bucket: pr-snapshots ]")
        files = self.db.list_bucket()
        if isinstance(files, list):
            print(f"  {len(files)} files")
            for f in files[:5]:
                print(f"  • {f.get('name','?')}")
        else:
            print(f"  {files}")

        print("\n[ GitHub ]")
        pr = self.github.get_pr(4)
        if "error" not in pr:
            print(f"  PR #4: {pr.get('title','?')} [{pr.get('state','?')}]")
        who = self.github.get_whoami()
        print(f"  Authenticated as: {who.get('login','?')}")

        print(f"\n{'='*60}\n")

    # ── Dashboard ────────────────────────────────────────────────────────────

    def dashboard(self, refresh_seconds: int = 30):
        print(f"[Dashboard] Refreshing every {refresh_seconds}s — Ctrl+C to exit\n")
        try:
            while True:
                os.system("cls" if os.name == "nt" else "clear")
                self.status()
                print(f"  Next refresh in {refresh_seconds}s...")
                time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            print("\n[Dashboard] Stopped.")

    # ── Interactive chat loop ────────────────────────────────────────────────

    def repl(self):
        print(f"\nRabbitOS Agent ready — {TWIN_NAME}")
        print("Type your question, or: status / dashboard / exit\n")

        while True:
            try:
                user = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not user:
                continue
            if user.lower() in ("exit", "quit", "q"):
                break
            if user.lower() == "status":
                self.status()
                continue
            if user.lower().startswith("dashboard"):
                parts = user.split()
                secs  = int(parts[1]) if len(parts) > 1 else 30
                self.dashboard(secs)
                continue

            reply = self.chat(user)
            print(f"\nagent> {reply}\n")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    if not SUPABASE_KEY:
        print("[WARN] SUPABASE_SERVICE_ROLE_KEY not set.")
        print("       Rotate at: https://supabase.com/dashboard/project/ludxbakxpmdqhfgdenwp/settings/api")
        print("       Then: set SUPABASE_SERVICE_ROLE_KEY=<new_key>\n")

    agent = RabbitOSAgent()

    if "--status" in sys.argv:
        agent.status()
    elif "--dashboard" in sys.argv:
        idx   = sys.argv.index("--dashboard")
        secs  = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit() else 30
        agent.dashboard(secs)
    else:
        agent.repl()


if __name__ == "__main__":
    main()
