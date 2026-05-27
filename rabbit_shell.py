"""
rabbit_shell.py — RabbitOS Shell Integration
Chase Allen Ringquist | RABBIT-SOFTWARE

Covers:
  - PowerShell (Windows) — full command execution + pipeline
  - Bash/sh (Linux/macOS/Android-Termux)
  - Google Cloud Shell (gcloud CLI integration)
  - Cross-platform shell abstraction
  - AI-assisted command generation via rabbit_llm
  - ML/Deep Learning model management (Ollama + HuggingFace + gcloud AI)
  - Server-to-server communication (gRPC-style JSON + WebSocket)
  - Learned command history (SQLite) — improves suggestions over time
  - Shell coding agent: natural language -> shell command
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import queue
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

shows_dna_root = False
assert shows_dna_root is False

_LOG = logging.getLogger("rabbit.shell")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [SHELL] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)


def _log(msg: str) -> None:
    try:
        _LOG.info(msg)
    except UnicodeEncodeError:
        _LOG.info(msg.encode("ascii", "replace").decode("ascii"))


def _get_llm():
    try:
        from rabbit_llm import get_llm
        return get_llm()
    except Exception as exc:
        _log(f"LLM init: {exc}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — SHELL RESULT + EXECUTION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ShellResult:
    command: str
    shell_type: str       # powershell / bash / cmd / gcloud / python
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    ts: float = field(default_factory=time.time)
    ai_interpretation: str = ""
    learned: bool = False


class ShellExecutor:
    """
    Cross-platform shell executor. Auto-detects best shell for platform.
    Runs commands safely with timeout, captures stdout/stderr.
    """

    MAX_OUTPUT = 64 * 1024   # 64 kB cap
    DEFAULT_TIMEOUT = 60

    def __init__(self) -> None:
        self._platform = platform.system()
        self._default_shell = self._detect_shell()
        self._history: deque = deque(maxlen=2000)
        self._lock = threading.Lock()

    def _detect_shell(self) -> str:
        if self._platform == "Windows":
            return "powershell"
        if shutil.which("bash"):
            return "bash"
        if shutil.which("sh"):
            return "sh"
        return "python"

    def _build_cmd(self, command: str, shell_type: str) -> List[str]:
        if shell_type == "powershell":
            return ["powershell", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-Command", command]
        elif shell_type in ("bash", "sh"):
            shell = shutil.which(shell_type) or "/bin/sh"
            return [shell, "-c", command]
        elif shell_type == "cmd":
            return ["cmd.exe", "/C", command]
        elif shell_type == "python":
            return [sys.executable, "-c", command]
        elif shell_type == "gcloud":
            gcloud = shutil.which("gcloud") or "gcloud"
            return [gcloud] + command.split()
        else:
            return command.split()

    def run(self, command: str,
             shell_type: Optional[str] = None,
             timeout: int = DEFAULT_TIMEOUT,
             cwd: Optional[str] = None,
             env: Optional[Dict] = None,
             ai_interpret: bool = False) -> ShellResult:

        stype = shell_type or self._default_shell
        cmd   = self._build_cmd(command, stype)
        t0    = time.time()

        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=timeout,
                cwd=cwd, env=env,
                encoding="utf-8", errors="replace",
            )
            stdout = proc.stdout[:self.MAX_OUTPUT]
            stderr = proc.stderr[:self.MAX_OUTPUT]
            rc     = proc.returncode
        except subprocess.TimeoutExpired:
            stdout, stderr, rc = "", "Timeout expired", -1
        except FileNotFoundError:
            stdout, stderr, rc = "", f"Shell not found: {cmd[0]}", -127
        except Exception as exc:
            stdout, stderr, rc = "", str(exc), -1

        result = ShellResult(
            command=command, shell_type=stype,
            exit_code=rc, stdout=stdout, stderr=stderr,
            duration_ms=round((time.time() - t0) * 1000, 2),
        )

        if ai_interpret and (stdout or stderr):
            result.ai_interpretation = self._interpret(result)

        with self._lock:
            self._history.append(result)

        return result

    def _interpret(self, result: ShellResult) -> str:
        llm = _get_llm()
        if llm is None:
            return ""
        prompt = (
            f"Interpret this shell command result:\n"
            f"Command: {result.command}\n"
            f"Exit code: {result.exit_code}\n"
            f"Output: {result.stdout[:2000]}\n"
            f"Errors: {result.stderr[:500]}\n\n"
            f"Provide: (1) What happened, (2) Any errors and their meaning, "
            f"(3) Next suggested steps."
        )
        try:
            return llm.simple_ask(prompt)
        except Exception:
            return ""

    def run_pipeline(self, commands: List[str],
                      shell_type: Optional[str] = None) -> List[ShellResult]:
        results = []
        prev_output = ""
        for cmd in commands:
            if prev_output:
                # Pipe previous output as stdin via shell
                full_cmd = f"echo {repr(prev_output)} | {cmd}"
            else:
                full_cmd = cmd
            r = self.run(full_cmd, shell_type=shell_type)
            results.append(r)
            prev_output = r.stdout
        return results

    def history(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            return [asdict(r) for r in list(self._history)[-limit:]]


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — POWERSHELL INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

class PowerShellIntegration:
    """
    Full PowerShell integration: cmdlets, pipelines, modules, remoting.
    Also supports PowerShell Core (pwsh) on Linux/macOS.
    """

    def __init__(self, executor: ShellExecutor) -> None:
        self._exe = executor
        self._pwsh = self._detect_pwsh()

    def _detect_pwsh(self) -> str:
        for candidate in ["pwsh", "powershell"]:
            if shutil.which(candidate):
                return candidate
        return "powershell"

    def run_cmdlet(self, cmdlet: str, params: Optional[Dict] = None,
                    timeout: int = 60) -> ShellResult:
        cmd = cmdlet
        if params:
            for k, v in params.items():
                if isinstance(v, bool):
                    if v:
                        cmd += f" -{k}"
                elif isinstance(v, (int, float)):
                    cmd += f" -{k} {v}"
                else:
                    cmd += f" -{k} '{v}'"
        return self._exe.run(cmd, shell_type="powershell", timeout=timeout)

    def get_process_list(self) -> ShellResult:
        return self._exe.run(
            "Get-Process | Select-Object Name,Id,CPU,WorkingSet64 | ConvertTo-Json",
            shell_type="powershell")

    def get_service_list(self) -> ShellResult:
        return self._exe.run(
            "Get-Service | Where-Object {$_.Status -eq 'Running'} | "
            "Select-Object Name,Status,DisplayName | ConvertTo-Json",
            shell_type="powershell")

    def get_network_adapters(self) -> ShellResult:
        return self._exe.run(
            "Get-NetAdapter | Select-Object Name,Status,MacAddress,LinkSpeed | ConvertTo-Json",
            shell_type="powershell")

    def get_disk_info(self) -> ShellResult:
        return self._exe.run(
            "Get-PSDrive | Where-Object {$_.Provider -like '*FileSystem*'} | "
            "Select-Object Name,Used,Free | ConvertTo-Json",
            shell_type="powershell")

    def get_hotfixes(self) -> ShellResult:
        return self._exe.run(
            "Get-HotFix | Select-Object HotFixID,InstalledOn | Sort-Object InstalledOn -Desc | "
            "Select-Object -First 20 | ConvertTo-Json",
            shell_type="powershell")

    def run_remoting(self, computer: str, command: str,
                      credential: Optional[str] = None) -> ShellResult:
        if credential:
            full_cmd = (f"Invoke-Command -ComputerName '{computer}' "
                        f"-Credential '{credential}' "
                        f"-ScriptBlock {{ {command} }}")
        else:
            full_cmd = (f"Invoke-Command -ComputerName '{computer}' "
                        f"-ScriptBlock {{ {command} }}")
        return self._exe.run(full_cmd, shell_type="powershell", timeout=120)

    def install_module(self, module_name: str) -> ShellResult:
        return self._exe.run(
            f"Install-Module -Name '{module_name}' -Scope CurrentUser -Force -AllowClobber",
            shell_type="powershell", timeout=180)

    def get_event_log(self, log_name: str = "System",
                       max_events: int = 20) -> ShellResult:
        return self._exe.run(
            f"Get-WinEvent -LogName '{log_name}' -MaxEvents {max_events} "
            f"| Select-Object TimeCreated,Id,LevelDisplayName,Message "
            f"| ConvertTo-Json",
            shell_type="powershell", timeout=30)


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — GOOGLE CLOUD SHELL INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

class GCloudIntegration:
    """
    Google Cloud Shell / gcloud CLI integration.
    Manages: auth, compute, storage, AI Platform, Cloud Run, BigQuery.
    Falls back to REST API when gcloud CLI is not installed.
    """

    GCLOUD_API = "https://cloudresourcemanager.googleapis.com/v1"
    AI_API     = "https://us-central1-aiplatform.googleapis.com/v1"

    def __init__(self, executor: ShellExecutor) -> None:
        self._exe     = executor
        self._gcloud  = shutil.which("gcloud") or ""
        self._project: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        self._token:   str = os.environ.get("GOOGLE_ACCESS_TOKEN", "")

    @property
    def available(self) -> bool:
        return bool(self._gcloud)

    def auth_status(self) -> ShellResult:
        return self._exe.run("auth list --format=json", shell_type="gcloud")

    def set_project(self, project_id: str) -> ShellResult:
        self._project = project_id
        return self._exe.run(
            f"config set project {project_id}", shell_type="gcloud")

    def list_instances(self, zone: str = "") -> ShellResult:
        cmd = "compute instances list --format=json"
        if zone:
            cmd += f" --zones={zone}"
        return self._exe.run(cmd, shell_type="gcloud")

    def list_buckets(self) -> ShellResult:
        return self._exe.run("storage buckets list --format=json", shell_type="gcloud")

    def upload_to_gcs(self, local_path: str, gcs_uri: str) -> ShellResult:
        return self._exe.run(
            f"storage cp '{local_path}' '{gcs_uri}'",
            shell_type="gcloud", timeout=300)

    def run_cloud_shell_command(self, command: str) -> ShellResult:
        """Execute a command in Google Cloud Shell context."""
        if self._gcloud:
            return self._exe.run(
                f"cloud-shell ssh --command='{command}'",
                shell_type="gcloud", timeout=120)
        return ShellResult(command=command, shell_type="gcloud",
                            exit_code=-1, stdout="", stderr="gcloud not installed",
                            duration_ms=0.0)

    def ai_platform_predict(self, endpoint_id: str, instances: List[Dict],
                             region: str = "us-central1") -> Dict[str, Any]:
        """Call Vertex AI endpoint for predictions."""
        if self._gcloud:
            instances_json = json.dumps({"instances": instances})
            r = self._exe.run(
                f"ai endpoints predict {endpoint_id} "
                f"--region={region} "
                f"--json-request='{instances_json}'",
                shell_type="gcloud", timeout=60)
            try:
                return json.loads(r.stdout)
            except Exception:
                return {"error": r.stderr, "stdout": r.stdout}

        # REST fallback
        if self._token and self._project:
            url = (f"{self.AI_API}/projects/{self._project}/"
                   f"locations/{region}/endpoints/{endpoint_id}:predict")
            data = json.dumps({"instances": instances}).encode()
            req  = urllib.request.Request(url, data=data, method="POST",
                   headers={
                       "Authorization": f"Bearer {self._token}",
                       "Content-Type": "application/json",
                   })
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except Exception as exc:
                return {"error": str(exc)}

        return {"error": "gcloud not available and no access token set"}

    def deploy_cloud_run(self, service_name: str, image: str,
                          region: str = "us-central1") -> ShellResult:
        return self._exe.run(
            f"run deploy {service_name} --image={image} "
            f"--region={region} --platform=managed --allow-unauthenticated",
            shell_type="gcloud", timeout=300)

    def bigquery_query(self, sql: str) -> ShellResult:
        safe_sql = sql.replace("'", "\\'")
        return self._exe.run(
            f"bq query --use_legacy_sql=false --format=json '{safe_sql}'",
            shell_type="gcloud", timeout=120)


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — ML / DEEP LEARNING MODEL MANAGER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MLModel:
    model_id: str
    name: str
    framework: str    # ollama / huggingface / tensorflow / pytorch / vertex / openai
    size_gb: float
    context_length: int
    capabilities: List[str]
    local: bool
    endpoint: str
    status: str       # ready / loading / unavailable


class MLModelManager:
    """
    Manages local and remote ML models. Integrates:
    - Ollama (local)
    - HuggingFace (API + local)
    - TensorFlow SavedModel (local)
    - PyTorch (local)
    - Google Vertex AI (cloud)
    - OpenAI-compatible endpoints
    """

    OLLAMA_API  = "http://127.0.0.1:11434"
    HF_API      = "https://api-inference.huggingface.co"

    def __init__(self, executor: ShellExecutor) -> None:
        self._exe    = executor
        self._models: Dict[str, MLModel] = {}
        self._lock   = threading.Lock()

    def _get(self, url: str, headers: Optional[Dict] = None,
              timeout: int = 10) -> Dict:
        try:
            req = urllib.request.Request(
                url, headers=headers or {"User-Agent": "RabbitOS"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as exc:
            return {"error": str(exc)}

    def _post(self, url: str, data: Dict,
               headers: Optional[Dict] = None, timeout: int = 30) -> Dict:
        hdrs = {"Content-Type": "application/json",
                "User-Agent": "RabbitOS"}
        if headers:
            hdrs.update(headers)
        try:
            payload = json.dumps(data).encode()
            req = urllib.request.Request(url, data=payload,
                                          method="POST", headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as exc:
            return {"error": str(exc)}

    def list_ollama(self) -> List[MLModel]:
        data = self._get(f"{self.OLLAMA_API}/api/tags")
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size = m.get("size", 0) / 1e9
            mm = MLModel(
                model_id=f"ollama:{name}",
                name=name, framework="ollama",
                size_gb=round(size, 2),
                context_length=m.get("details", {}).get("parameter_size", 0),
                capabilities=["text", "chat"],
                local=True,
                endpoint=self.OLLAMA_API,
                status="ready",
            )
            models.append(mm)
            with self._lock:
                self._models[mm.model_id] = mm
        return models

    def pull_ollama(self, model_name: str) -> ShellResult:
        return self._exe.run(f"ollama pull {model_name}",
                              shell_type=self._exe._default_shell,
                              timeout=600)

    def ollama_generate(self, model: str, prompt: str) -> str:
        data = self._post(f"{self.OLLAMA_API}/api/generate",
                          {"model": model, "prompt": prompt, "stream": False})
        return data.get("response", str(data))

    def huggingface_inference(self, model_id: str, inputs: str,
                               hf_token: str = "") -> Dict:
        url  = f"{self.HF_API}/models/{model_id}"
        hdrs = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
        return self._post(url, {"inputs": inputs}, headers=hdrs)

    def tensorflow_predict(self, model_path: str, input_data: Any) -> Dict:
        try:
            import tensorflow as tf  # type: ignore
            model = tf.saved_model.load(model_path)
            result = model(input_data)
            return {"result": str(result)}
        except ImportError:
            return {"error": "TensorFlow not installed"}
        except Exception as exc:
            return {"error": str(exc)}

    def pytorch_inference(self, model_path: str, input_json: str) -> Dict:
        try:
            import torch  # type: ignore
            model = torch.jit.load(model_path)
            model.eval()
            inp = torch.tensor(json.loads(input_json))
            with torch.no_grad():
                out = model(inp)
            return {"output": out.tolist()}
        except ImportError:
            return {"error": "PyTorch not installed"}
        except Exception as exc:
            return {"error": str(exc)}

    def list_all(self) -> List[Dict]:
        self.list_ollama()
        with self._lock:
            return [asdict(m) for m in self._models.values()]

    def status_all(self) -> Dict[str, Any]:
        models = self.list_all()
        return {
            "total": len(models),
            "ollama": [m for m in models if m["framework"] == "ollama"],
            "local": [m for m in models if m["local"]],
        }


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — SERVER-TO-SERVER COMMUNICATION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class S2SMessage:
    msg_id: str
    from_node: str
    to_node: str
    topic: str
    payload: Dict
    ts: float
    signature: str = ""


class ServerToServer:
    """
    JSON + HMAC-signed server-to-server communication.
    Supports: direct HTTP POST, WebSocket relay, UDP broadcast.
    Enables AI model nodes to communicate learned state.
    """

    HMAC_KEY = os.environ.get("RABBITOS_S2S_KEY",
                               hashlib.sha256(b"RabbitOS-S2S-default").hexdigest())

    def __init__(self, node_id: str = "local",
                  trail: Optional[Any] = None) -> None:
        self._node_id = node_id
        self._trail   = trail
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._inbox: deque = deque(maxlen=1000)

    def _sign(self, payload_json: str) -> str:
        import hmac as _hmac, hashlib as _hash
        return _hmac.new(
            self.HMAC_KEY.encode(),
            payload_json.encode(),
            _hash.sha256).hexdigest()

    def _verify(self, payload_json: str, sig: str) -> bool:
        import hmac as _hmac
        expected = self._sign(payload_json)
        return _hmac.compare_digest(expected, sig)

    def create_message(self, to_node: str, topic: str,
                        payload: Dict) -> S2SMessage:
        msg_id = hashlib.sha256(
            f"{time.time()}{self._node_id}{os.urandom(4).hex()}".encode()
        ).hexdigest()[:16]
        payload_json = json.dumps(payload, sort_keys=True)
        sig = self._sign(payload_json)
        return S2SMessage(
            msg_id=msg_id, from_node=self._node_id,
            to_node=to_node, topic=topic,
            payload=payload, ts=time.time(), signature=sig,
        )

    def send_http(self, msg: S2SMessage, endpoint: str) -> Dict[str, Any]:
        data = json.dumps(asdict(msg)).encode()
        req  = urllib.request.Request(endpoint, data=data, method="POST",
               headers={"Content-Type": "application/json",
                        "X-RabbitOS-Node": self._node_id,
                        "User-Agent": "RabbitOS-S2S/1.0"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = json.loads(r.read())
            return {"ok": True, "response": resp,
                    "ms": round((time.time() - t0) * 1000, 2)}
        except Exception as exc:
            return {"ok": False, "error": str(exc),
                    "ms": round((time.time() - t0) * 1000, 2)}

    def send_udp(self, msg: S2SMessage, host: str, port: int) -> bool:
        try:
            data = json.dumps(asdict(msg)).encode()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(data, (host, port))
            s.close()
            return True
        except Exception:
            return False

    def receive(self, raw_json: str) -> Optional[S2SMessage]:
        try:
            d = json.loads(raw_json)
            payload_json = json.dumps(d.get("payload", {}), sort_keys=True)
            if not self._verify(payload_json, d.get("signature", "")):
                _log("S2S: invalid signature rejected")
                return None
            msg = S2SMessage(**d)
            self._inbox.append(msg)
            for handler in self._handlers.get(msg.topic, []):
                try:
                    handler(msg)
                except Exception as exc:
                    _log(f"S2S handler error: {exc}")
            return msg
        except Exception as exc:
            _log(f"S2S receive error: {exc}")
            return None

    def register_handler(self, topic: str, fn: Callable) -> None:
        self._handlers[topic].append(fn)

    def broadcast_ai_state(self, model_id: str, state: Dict,
                             targets: List[Tuple[str, int]]) -> List[bool]:
        msg = self.create_message("broadcast", "ai_state_sync", {
            "model_id": model_id, "state": state})
        results = []
        for host, port in targets:
            results.append(self.send_udp(msg, host, port))
        return results

    def get_inbox(self, limit: int = 50) -> List[Dict]:
        return [asdict(m) for m in list(self._inbox)[-limit:]]


# ══════════════════════════════════════════════════════════════════════════════
# PART 6 — LEARNED COMMAND HISTORY + AI SHELL AGENT
# ══════════════════════════════════════════════════════════════════════════════

_SHELL_DB = os.path.join(os.path.dirname(__file__), "rabbit_shell.db")


class ShellLearner:
    """
    SQLite-backed command history that improves over time.
    Tracks: command, shell type, success rate, AI suggestions.
    """

    def __init__(self, db_path: str = _SHELL_DB) -> None:
        self._db = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db, timeout=10, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS shell_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, command TEXT, shell_type TEXT,
                    exit_code INTEGER, duration_ms REAL,
                    success INTEGER, natural_language TEXT
                );
                CREATE TABLE IF NOT EXISTS shell_patterns (
                    pattern TEXT PRIMARY KEY,
                    shell_type TEXT,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_used REAL
                );
            """)

    def record(self, result: ShellResult, nl_query: str = "") -> None:
        success = 1 if result.exit_code == 0 else 0
        with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO shell_history VALUES (NULL,?,?,?,?,?,?,?)",
                    (result.ts, result.command, result.shell_type,
                     result.exit_code, result.duration_ms,
                     success, nl_query)
                )
                # Update pattern table
                pattern = re.sub(r"['\"][^'\"]*['\"]", "<ARG>", result.command)
                pattern = re.sub(r"\b\d+\b", "<N>", pattern)[:200]
                c.execute("""
                    INSERT INTO shell_patterns (pattern, shell_type, success_count,
                        fail_count, last_used)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(pattern) DO UPDATE SET
                        success_count = success_count + ?,
                        fail_count    = fail_count + ?,
                        last_used     = ?
                """, (pattern, result.shell_type,
                      success, 1 - success, time.time(),
                      success, 1 - success, time.time()))

    def suggest(self, query: str, limit: int = 5) -> List[str]:
        """Return historically successful commands matching the query."""
        tokens = query.lower().split()
        with self._lock:
            with self._conn() as c:
                rows = c.execute(
                    "SELECT command FROM shell_history "
                    "WHERE success=1 ORDER BY ts DESC LIMIT 500"
                ).fetchall()
        results = []
        for (cmd,) in rows:
            if any(t in cmd.lower() for t in tokens):
                if cmd not in results:
                    results.append(cmd)
        return results[:limit]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            with self._conn() as c:
                total = c.execute(
                    "SELECT COUNT(*) FROM shell_history").fetchone()[0]
                success = c.execute(
                    "SELECT COUNT(*) FROM shell_history WHERE success=1"
                ).fetchone()[0]
                top_patterns = c.execute(
                    "SELECT pattern, success_count FROM shell_patterns "
                    "ORDER BY success_count DESC LIMIT 10"
                ).fetchall()
        return {
            "total_commands": total,
            "success_rate": round(success / max(total, 1) * 100, 1),
            "top_patterns": [{"pattern": p, "count": n}
                              for p, n in top_patterns],
        }


class ShellCodingAgent:
    """
    Translates natural language to shell commands, executes them,
    learns from results, and uses AI to improve over time.
    """

    SYSTEM_PROMPT = (
        "You are a RabbitOS shell coding agent. "
        "Generate shell commands for the target OS. "
        "For Windows: use PowerShell. For Linux/macOS: use bash. "
        "Return ONLY the command on the first line, then optionally "
        "a brief explanation on subsequent lines. "
        "Never use destructive or irreversible commands without explicit confirmation."
    )

    def __init__(self, executor: ShellExecutor,
                  learner: ShellLearner) -> None:
        self._exe     = executor
        self._learner = learner
        self._llm     = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = _get_llm()
        return self._llm

    def nl_to_command(self, natural_language: str,
                       target_os: str = "") -> Tuple[str, str]:
        """Returns (command, explanation)."""
        llm = self._get_llm()
        if llm is None:
            return ("", "[LLM unavailable]")

        # Check history first
        suggestions = self._learner.suggest(natural_language, limit=3)
        context = ""
        if suggestions:
            context = "Previously successful commands:\n" + "\n".join(suggestions) + "\n\n"

        os_hint = target_os or platform.system()
        prompt = (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"Target OS: {os_hint}\n"
            f"{context}"
            f"Task: {natural_language}"
        )
        try:
            resp = llm.simple_ask(prompt)
        except Exception as exc:
            return ("", f"[error: {exc}]")

        lines = resp.strip().splitlines()
        command = lines[0].strip() if lines else ""
        explanation = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        # Remove code fences if present
        command = re.sub(r"^```\w*\n?", "", command).rstrip("`").strip()
        return (command, explanation)

    def execute_nl(self, natural_language: str,
                    dry_run: bool = False,
                    confirm_dangerous: bool = True) -> Dict[str, Any]:
        command, explanation = self.nl_to_command(natural_language)
        if not command:
            return {"error": "Could not generate command", "explanation": explanation}

        # Safety check for dangerous operations
        danger_words = ["rm -rf", "del /f", "format", "fdisk",
                        "DROP TABLE", "DELETE FROM", "> /dev/sda"]
        is_dangerous = any(dw.lower() in command.lower() for dw in danger_words)
        if is_dangerous and confirm_dangerous:
            return {
                "command": command,
                "explanation": explanation,
                "status": "REQUIRES_CONFIRMATION",
                "dangerous": True,
                "message": "This command is potentially destructive. "
                           "Set confirm_dangerous=False to execute.",
            }

        if dry_run:
            return {"command": command, "explanation": explanation,
                    "status": "DRY_RUN"}

        result = self._exe.run(command, ai_interpret=True)
        self._learner.record(result, nl_query=natural_language)
        return {
            "nl_query": natural_language,
            "command": command,
            "explanation": explanation,
            "exit_code": result.exit_code,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:1000],
            "duration_ms": result.duration_ms,
            "ai_interpretation": result.ai_interpretation,
        }

    def refine_command(self, command: str, error: str) -> str:
        llm = self._get_llm()
        if llm is None:
            return command
        prompt = (
            f"This command failed:\n{command}\n\n"
            f"Error:\n{error}\n\n"
            f"Provide a corrected version. Return only the fixed command."
        )
        try:
            resp = llm.simple_ask(prompt)
            return resp.strip().splitlines()[0].strip()
        except Exception:
            return command


# ══════════════════════════════════════════════════════════════════════════════
# PART 7 — SHELL ORCHESTRATOR SINGLETON
# ══════════════════════════════════════════════════════════════════════════════

class ShellOrchestrator:
    _instance: Optional["ShellOrchestrator"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ShellOrchestrator":
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self.executor  = ShellExecutor()
        self.pwsh      = PowerShellIntegration(self.executor)
        self.gcloud    = GCloudIntegration(self.executor)
        self.ml        = MLModelManager(self.executor)
        self.s2s       = ServerToServer(node_id=socket.gethostname())
        self.learner   = ShellLearner()
        self.agent     = ShellCodingAgent(self.executor, self.learner)
        _log("ShellOrchestrator initialised")

    def status(self) -> Dict[str, Any]:
        return {
            "platform": platform.system(),
            "default_shell": self.executor._default_shell,
            "pwsh_binary": self.pwsh._pwsh,
            "gcloud_available": self.gcloud.available,
            "ml_models": len(self.ml._models),
            "learned_commands": self.learner.stats().get("total_commands", 0),
            "shell_success_rate": self.learner.stats().get("success_rate", 0),
        }


def get_shell_engine() -> ShellOrchestrator:
    return ShellOrchestrator()


# ══════════════════════════════════════════════════════════════════════════════
# SHELL TOOLS + DISPATCHER
# ══════════════════════════════════════════════════════════════════════════════

SHELL_TOOLS = [
    {
        "name": "shell_status",
        "description": "Get shell integration status: platform, shells, gcloud, ML models",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "shell_run",
        "description": "Execute a shell command on the local system",
        "input_schema": {
            "type": "object",
            "properties": {
                "command":    {"type": "string"},
                "shell_type": {"type": "string",
                               "description": "powershell/bash/sh/cmd/gcloud/python"},
                "timeout":    {"type": "integer"},
                "interpret":  {"type": "boolean", "description": "AI-interpret output"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "shell_pipeline",
        "description": "Run a sequence of shell commands as a pipeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "commands":   {"type": "array", "items": {"type": "string"}},
                "shell_type": {"type": "string"},
            },
            "required": ["commands"],
        },
    },
    {
        "name": "shell_history",
        "description": "Get recent shell command history",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "shell_nl_execute",
        "description": "Translate natural language to shell command and execute it",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":     {"type": "string", "description": "Natural language task"},
                "dry_run":   {"type": "boolean"},
                "target_os": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "shell_nl_to_command",
        "description": "Translate natural language to shell command (no execution)",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":     {"type": "string"},
                "target_os": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "shell_suggest",
        "description": "Suggest shell commands from learned history matching a query",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "shell_learner_stats",
        "description": "Get shell command learning statistics",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "shell_powershell_processes",
        "description": "List running Windows processes via PowerShell",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "shell_powershell_services",
        "description": "List running Windows services via PowerShell",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "shell_powershell_network",
        "description": "Get network adapter info via PowerShell",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "shell_powershell_eventlog",
        "description": "Get Windows event log via PowerShell",
        "input_schema": {
            "type": "object",
            "properties": {
                "log_name":   {"type": "string"},
                "max_events": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "shell_gcloud_auth",
        "description": "Check Google Cloud authentication status",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "shell_gcloud_run",
        "description": "Run a raw gcloud CLI command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "gcloud subcommand"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "shell_gcloud_shell",
        "description": "Execute a command in Google Cloud Shell context",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "shell_ml_list",
        "description": "List all available ML models (Ollama + HuggingFace + cloud)",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "shell_ml_pull",
        "description": "Pull/download a model via Ollama",
        "input_schema": {
            "type": "object",
            "properties": {"model": {"type": "string"}},
            "required": ["model"],
        },
    },
    {
        "name": "shell_ml_generate",
        "description": "Generate text using a local Ollama model",
        "input_schema": {
            "type": "object",
            "properties": {
                "model":  {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["model", "prompt"],
        },
    },
    {
        "name": "shell_ml_huggingface",
        "description": "Run inference on a HuggingFace model",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string"},
                "inputs":   {"type": "string"},
                "hf_token": {"type": "string"},
            },
            "required": ["model_id", "inputs"],
        },
    },
    {
        "name": "shell_s2s_send",
        "description": "Send a server-to-server message to another RabbitOS node",
        "input_schema": {
            "type": "object",
            "properties": {
                "to_node":  {"type": "string"},
                "topic":    {"type": "string"},
                "payload":  {"type": "object"},
                "endpoint": {"type": "string", "description": "HTTP endpoint or host:port for UDP"},
                "protocol": {"type": "string", "description": "http or udp"},
            },
            "required": ["to_node", "topic", "payload"],
        },
    },
    {
        "name": "shell_s2s_inbox",
        "description": "Get received server-to-server messages",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "shell_s2s_broadcast_ai",
        "description": "Broadcast AI model state to all mesh nodes",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string"},
                "state":    {"type": "object"},
                "targets":  {"type": "array", "items": {"type": "string"},
                              "description": "List of 'host:port' strings"},
            },
            "required": ["model_id", "state"],
        },
    },
]


def dispatch_shell_tool(name: str, inputs: Dict) -> Any:
    eng = get_shell_engine()

    if name == "shell_status":
        return eng.status()

    elif name == "shell_run":
        r = eng.executor.run(
            inputs["command"],
            shell_type=inputs.get("shell_type"),
            timeout=inputs.get("timeout", 60),
            ai_interpret=inputs.get("interpret", False),
        )
        eng.learner.record(r)
        return asdict(r)

    elif name == "shell_pipeline":
        results = eng.executor.run_pipeline(
            inputs["commands"],
            shell_type=inputs.get("shell_type"),
        )
        for r in results:
            eng.learner.record(r)
        return [asdict(r) for r in results]

    elif name == "shell_history":
        return eng.executor.history(inputs.get("limit", 50))

    elif name == "shell_nl_execute":
        return eng.agent.execute_nl(
            inputs["query"],
            dry_run=inputs.get("dry_run", False),
            confirm_dangerous=True,
        )

    elif name == "shell_nl_to_command":
        cmd, expl = eng.agent.nl_to_command(
            inputs["query"], inputs.get("target_os", ""))
        return {"command": cmd, "explanation": expl}

    elif name == "shell_suggest":
        return {"suggestions": eng.learner.suggest(inputs["query"])}

    elif name == "shell_learner_stats":
        return eng.learner.stats()

    elif name == "shell_powershell_processes":
        return asdict(eng.pwsh.get_process_list())

    elif name == "shell_powershell_services":
        return asdict(eng.pwsh.get_service_list())

    elif name == "shell_powershell_network":
        return asdict(eng.pwsh.get_network_adapters())

    elif name == "shell_powershell_eventlog":
        r = eng.pwsh.get_event_log(
            log_name=inputs.get("log_name", "System"),
            max_events=inputs.get("max_events", 20),
        )
        return asdict(r)

    elif name == "shell_gcloud_auth":
        return asdict(eng.gcloud.auth_status())

    elif name == "shell_gcloud_run":
        return asdict(eng.executor.run(inputs["command"], shell_type="gcloud"))

    elif name == "shell_gcloud_shell":
        return asdict(eng.gcloud.run_cloud_shell_command(inputs["command"]))

    elif name == "shell_ml_list":
        return eng.ml.list_all()

    elif name == "shell_ml_pull":
        return asdict(eng.ml.pull_ollama(inputs["model"]))

    elif name == "shell_ml_generate":
        return {"response": eng.ml.ollama_generate(inputs["model"], inputs["prompt"])}

    elif name == "shell_ml_huggingface":
        return eng.ml.huggingface_inference(
            inputs["model_id"], inputs["inputs"],
            inputs.get("hf_token", ""),
        )

    elif name == "shell_s2s_send":
        msg = eng.s2s.create_message(
            inputs["to_node"], inputs["topic"], inputs["payload"])
        protocol = inputs.get("protocol", "http")
        if protocol == "udp":
            host_port = inputs.get("endpoint", "")
            if ":" in host_port:
                h, _, p = host_port.rpartition(":")
                ok = eng.s2s.send_udp(msg, h, int(p))
                return {"sent": ok}
            return {"error": "endpoint must be host:port for UDP"}
        else:
            return eng.s2s.send_http(msg, inputs.get("endpoint", ""))

    elif name == "shell_s2s_inbox":
        return eng.s2s.get_inbox(inputs.get("limit", 50))

    elif name == "shell_s2s_broadcast_ai":
        targets_raw = inputs.get("targets", [])
        targets = []
        for t in targets_raw:
            h, _, p = t.rpartition(":")
            if h and p.isdigit():
                targets.append((h, int(p)))
        results = eng.s2s.broadcast_ai_state(
            inputs["model_id"], inputs["state"], targets)
        return {"sent_count": sum(results), "total": len(results)}

    else:
        return {"error": f"Unknown shell tool: {name}"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RabbitOS Shell Integration")
    parser.add_argument("--status",  action="store_true")
    parser.add_argument("--run",     type=str, metavar="CMD")
    parser.add_argument("--nl",      type=str, metavar="QUERY",
                        help="Natural language -> command -> execute")
    parser.add_argument("--shell",   type=str, default=None,
                        help="Shell type: powershell/bash/gcloud")
    parser.add_argument("--ml",      action="store_true", help="List ML models")
    args = parser.parse_args()

    eng = get_shell_engine()
    if args.status:
        print(json.dumps(eng.status(), indent=2, default=str))
    elif args.run:
        r = eng.executor.run(args.run, shell_type=args.shell, ai_interpret=True)
        print(f"Exit: {r.exit_code}\n{r.stdout}\n{r.stderr}")
        if r.ai_interpretation:
            print(f"\nAI: {r.ai_interpretation}")
    elif args.nl:
        result = eng.agent.execute_nl(args.nl, dry_run=True)
        print(json.dumps(result, indent=2, default=str))
    elif args.ml:
        models = eng.ml.list_all()
        print(json.dumps(models, indent=2, default=str))
    else:
        parser.print_help()
