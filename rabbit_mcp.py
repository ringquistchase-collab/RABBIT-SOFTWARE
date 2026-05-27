"""
rabbit_mcp.py — RabbitOS MCP Server + Autonomous Cloud Agent
Chase Allen Ringquist | RABBIT-SOFTWARE

Implements:
  - MCP (Model Context Protocol) server — JSON-RPC 2.0 over stdio and HTTP
  - Exposes ALL RabbitOS tools as MCP tools (nettools, defense, zap, medical,
    assistant, shell, medical)
  - Browser assistant as MCP resource provider
  - Coding agent as MCP tool
  - Autonomous agent loop (no human-in-the-loop)
  - SDK wrappers: Anthropic SDK, OpenAI-compatible, LangChain tool format
  - Cloud network node: auto-register self on cold network + persist to Supabase
  - Prompt-cache-aware autonomous loops

Usage:
  python rabbit_mcp.py --stdio            # MCP over stdin/stdout (Claude Desktop)
  python rabbit_mcp.py --http 8765        # MCP over HTTP (IDE / remote)
  python rabbit_mcp.py --auto "TASK"      # Autonomous one-shot task execution
  python rabbit_mcp.py --status           # System status
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import platform
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

shows_dna_root = False
assert shows_dna_root is False

_LOG = logging.getLogger("rabbit.mcp")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [MCP] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,   # stderr so it doesn't pollute stdio MCP transport
)


def _log(msg: str) -> None:
    try:
        _LOG.info(msg)
    except UnicodeEncodeError:
        _LOG.info(msg.encode("ascii", "replace").decode("ascii"))


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — MCP PROTOCOL TYPES
# ══════════════════════════════════════════════════════════════════════════════

MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class MCPTool:
    name: str
    description: str
    inputSchema: Dict


@dataclass
class MCPResource:
    uri: str
    name: str
    description: str
    mimeType: str = "text/plain"


@dataclass
class MCPPrompt:
    name: str
    description: str
    arguments: List[Dict] = field(default_factory=list)


def _jsonrpc_response(req_id: Any, result: Any) -> Dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str,
                    data: Any = None) -> Dict:
    err: Dict = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _jsonrpc_notification(method: str, params: Any = None) -> Dict:
    n: Dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        n["params"] = params
    return n


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — RABBITOS TOOL REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

def _load_all_tools() -> List[MCPTool]:
    """Lazy-load all RabbitOS tool definitions and convert to MCPTool format."""
    tool_defs: List[Dict] = []

    loaders = [
        ("rabbit_llm",       "LLM_BRIDGE_TOOLS"),
        ("rabbit_nettools",  "NETTOOLS_TOOLS"),
        ("rabbit_defense",   "DEFENSE_TOOLS"),
        ("rabbit_zap",       "ZAP_TOOLS"),
        ("rabbit_medical",   "MEDICAL_TOOLS"),
        ("rabbit_assistant", "ASSISTANT_TOOLS"),
        ("rabbit_shell",     "SHELL_TOOLS"),
    ]
    for module_name, attr in loaders:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            tool_defs.extend(getattr(mod, attr, []))
        except Exception as exc:
            _log(f"Tool loader {module_name}.{attr}: {exc}")

    mcp_tools = []
    for t in tool_defs:
        schema = t.get("input_schema", {"type": "object", "properties": {}})
        mcp_tools.append(MCPTool(
            name=t["name"],
            description=t.get("description", ""),
            inputSchema=schema,
        ))
    return mcp_tools


def _dispatch_tool(name: str, arguments: Dict) -> Any:
    """Route a tool call to the correct RabbitOS dispatcher."""
    api_key  = os.environ.get("ANTHROPIC_API_KEY", "")
    svc_key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    gh_token = os.environ.get("GITHUB_TOKEN", "")

    try:
        if name.startswith("llm_"):
            from rabbit_llm import dispatch_llm_tool
            return dispatch_llm_tool(name, arguments)

        elif name.startswith("nettools_"):
            from rabbit_nettools import dispatch_nettools_tool
            return dispatch_nettools_tool(name, arguments, api_key, svc_key, gh_token)

        elif name.startswith("defense_"):
            from rabbit_defense import dispatch_defense_tool
            return dispatch_defense_tool(name, arguments, api_key, svc_key, gh_token)

        elif name.startswith("zap_"):
            from rabbit_zap import dispatch_zap_tool
            return dispatch_zap_tool(name, arguments, api_key, svc_key, gh_token)

        elif name.startswith("medical_"):
            from rabbit_medical import dispatch_medical_tool
            return dispatch_medical_tool(name, arguments, api_key, svc_key)

        elif name.startswith("assistant_"):
            from rabbit_assistant import dispatch_assistant_tool
            return dispatch_assistant_tool(name, arguments, api_key, svc_key)

        elif name.startswith("shell_"):
            from rabbit_shell import dispatch_shell_tool
            return dispatch_shell_tool(name, arguments)

        else:
            return {"error": f"No dispatcher for tool: {name}"}

    except Exception as exc:
        return {"error": str(exc), "trace": traceback.format_exc()[-500:]}


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — MCP SERVER (stdio + HTTP transport)
# ══════════════════════════════════════════════════════════════════════════════

class RabbitMCPServer:
    """
    Fully compliant MCP server for RabbitOS.
    Supports: initialize, tools/list, tools/call, resources/list,
              resources/read, prompts/list, prompts/get.
    """

    SERVER_INFO = {
        "name":    "RabbitOS",
        "version": "1.0.0",
    }

    CAPABILITIES = {
        "tools":     {"listChanged": True},
        "resources": {"subscribe": False, "listChanged": False},
        "prompts":   {"listChanged": False},
        "logging":   {},
    }

    def __init__(self) -> None:
        self._tools: Optional[List[MCPTool]] = None
        self._resources: List[MCPResource] = self._build_resources()
        self._prompts:   List[MCPPrompt]   = self._build_prompts()
        self._initialized = False
        self._client_info: Dict = {}

    def _get_tools(self) -> List[MCPTool]:
        if self._tools is None:
            self._tools = _load_all_tools()
            _log(f"Loaded {len(self._tools)} MCP tools")
        return self._tools

    def _build_resources(self) -> List[MCPResource]:
        return [
            MCPResource(
                uri="rabbitos://status",
                name="RabbitOS System Status",
                description="Live status of all RabbitOS subsystems",
                mimeType="application/json",
            ),
            MCPResource(
                uri="rabbitos://eeg/nodes",
                name="EEG Node Map",
                description="International 10-20 EEG electrode placement map with mesh bindings",
                mimeType="application/json",
            ),
            MCPResource(
                uri="rabbitos://network/topology",
                name="Network Topology",
                description="Current network classification and discovered nodes",
                mimeType="application/json",
            ),
            MCPResource(
                uri="rabbitos://defense/alerts",
                name="Defense Alerts",
                description="Recent attack events and defense status",
                mimeType="application/json",
            ),
            MCPResource(
                uri="rabbitos://medical/report",
                name="Medical Report",
                description="Latest biometric medical report",
                mimeType="application/json",
            ),
            MCPResource(
                uri="rabbitos://cloud/trail",
                name="Cloud Trail",
                description="Audit trail of all agent actions",
                mimeType="application/json",
            ),
        ]

    def _build_prompts(self) -> List[MCPPrompt]:
        return [
            MCPPrompt(
                name="rabbitos_analyze",
                description="Analyze RabbitOS system state and provide recommendations",
                arguments=[
                    {"name": "focus", "description": "Area to focus on: network/medical/security/all",
                     "required": False},
                ],
            ),
            MCPPrompt(
                name="rabbitos_defend",
                description="Activate defensive posture and analyze threats",
                arguments=[],
            ),
            MCPPrompt(
                name="rabbitos_medical_report",
                description="Generate a medical report for Chase Allen Ringquist",
                arguments=[],
            ),
            MCPPrompt(
                name="rabbitos_code_task",
                description="Autonomous code generation task via browser+coding agent",
                arguments=[
                    {"name": "task", "description": "What to build", "required": True},
                    {"name": "language", "description": "Programming language", "required": False},
                ],
            ),
        ]

    def _read_resource(self, uri: str) -> str:
        try:
            if uri == "rabbitos://status":
                from rabbit_zap import run_system_check
                return json.dumps(run_system_check(), indent=2, default=str)

            elif uri == "rabbitos://eeg/nodes":
                from rabbit_defense import eeg_node_report
                return json.dumps(eeg_node_report(), indent=2, default=str)

            elif uri == "rabbitos://network/topology":
                from rabbit_nettools import get_nettools_engine
                eng = get_nettools_engine()
                return json.dumps(eng.status(), indent=2, default=str)

            elif uri == "rabbitos://defense/alerts":
                from rabbit_defense import _ATTACK_LOG, _ATTACK_LOCK
                import dataclasses
                with _ATTACK_LOCK:
                    alerts = list(_ATTACK_LOG)[-20:]
                return json.dumps([dataclasses.asdict(a) for a in alerts],
                                   indent=2, default=str)

            elif uri == "rabbitos://medical/report":
                from rabbit_medical import get_medical_engine
                eng = get_medical_engine()
                return json.dumps(eng.status(), indent=2, default=str)

            elif uri == "rabbitos://cloud/trail":
                from rabbit_assistant import get_assistant
                trail = get_assistant().trail.query(limit=50)
                return json.dumps(trail, indent=2, default=str)

        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({"error": f"Unknown resource: {uri}"})

    def _get_prompt(self, name: str, arguments: Dict) -> Dict:
        focus = arguments.get("focus", "all")
        task  = arguments.get("task", "")
        lang  = arguments.get("language", "Python")

        messages: List[Dict] = []

        if name == "rabbitos_analyze":
            messages = [{
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Analyze the RabbitOS system state with focus on: {focus}. "
                        f"Use the rabbitos://status resource and relevant tools to "
                        f"assess: network health, security posture, EEG mesh status, "
                        f"and medical data. Provide actionable recommendations."
                    ),
                },
            }]

        elif name == "rabbitos_defend":
            messages = [{
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "Activate RabbitOS defensive posture. Use defense_start, "
                        "defense_discover_networks, defense_attack_scan, and "
                        "defense_signal_summary to assess the current threat environment. "
                        "Report findings and take defensive actions."
                    ),
                },
            }]

        elif name == "rabbitos_medical_report":
            messages = [{
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "Generate a comprehensive medical report for Chase Allen Ringquist. "
                        "Use medical_collect_from_mesh, medical_biometric_stats, "
                        "medical_compute_match, and medical_generate_report. "
                        "Also research any anomalies found using medical_research_condition."
                    ),
                },
            }]

        elif name == "rabbitos_code_task":
            messages = [{
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Build this using the RabbitOS coding agent: {task}\n\n"
                        f"Language: {lang}\n"
                        f"Steps: (1) Use assistant_browser_research to gather context, "
                        f"(2) Use assistant_code_generate to write the code, "
                        f"(3) Use assistant_code_review to check for security issues, "
                        f"(4) Use shell_nl_execute to test it."
                    ),
                },
            }]

        return {
            "description": f"RabbitOS prompt: {name}",
            "messages": messages,
        }

    def handle(self, request: Dict) -> Optional[Dict]:
        """Process a single JSON-RPC request and return response."""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # Notifications (no id) — process but don't respond
        if req_id is None:
            if method == "notifications/initialized":
                _log("Client initialized")
            return None

        try:
            if method == "initialize":
                self._client_info = params.get("clientInfo", {})
                _log(f"MCP initialize from: {self._client_info.get('name', 'unknown')}")
                self._initialized = True
                return _jsonrpc_response(req_id, {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": self.CAPABILITIES,
                    "serverInfo": self.SERVER_INFO,
                    "instructions": (
                        "RabbitOS MCP Server — 47-node biometric mesh OS. "
                        "Tools cover: EEG/neural defense, network security (OWASP ZAP), "
                        "medical monitoring, browser/voice/calling agents, "
                        "shell integration (PowerShell/gcloud/Bash), "
                        "and LLM bridge (Ollama/Groq/Gemini). "
                        "Patient: Chase Allen Ringquist. shows_dna_root=FALSE enforced."
                    ),
                })

            elif method == "tools/list":
                tools = self._get_tools()
                return _jsonrpc_response(req_id, {
                    "tools": [
                        {"name": t.name, "description": t.description,
                         "inputSchema": t.inputSchema}
                        for t in tools
                    ]
                })

            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments  = params.get("arguments", {})
                _log(f"Tool call: {tool_name}")
                result = _dispatch_tool(tool_name, arguments)
                return _jsonrpc_response(req_id, {
                    "content": [{
                        "type": "text",
                        "text": json.dumps(result, indent=2, default=str),
                    }],
                    "isError": isinstance(result, dict) and "error" in result,
                })

            elif method == "resources/list":
                return _jsonrpc_response(req_id, {
                    "resources": [asdict(r) for r in self._resources]
                })

            elif method == "resources/read":
                uri  = params.get("uri", "")
                text = self._read_resource(uri)
                return _jsonrpc_response(req_id, {
                    "contents": [{"uri": uri, "mimeType": "application/json",
                                  "text": text}]
                })

            elif method == "prompts/list":
                return _jsonrpc_response(req_id, {
                    "prompts": [
                        {"name": p.name, "description": p.description,
                         "arguments": p.arguments}
                        for p in self._prompts
                    ]
                })

            elif method == "prompts/get":
                name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = self._get_prompt(name, arguments)
                return _jsonrpc_response(req_id, result)

            elif method == "ping":
                return _jsonrpc_response(req_id, {})

            else:
                return _jsonrpc_error(req_id, -32601,
                                       f"Method not found: {method}")

        except Exception as exc:
            _log(f"MCP handler error: {exc}")
            return _jsonrpc_error(req_id, -32603, "Internal error",
                                   str(exc))

    def run_stdio(self) -> None:
        """Run MCP server over stdin/stdout (for Claude Desktop / VS Code)."""
        _log("Starting MCP stdio server...")

        # Send initialized notification
        sys.stdout.write(json.dumps(_jsonrpc_notification(
            "notifications/initialized")) + "\n")
        sys.stdout.flush()

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                sys.stdout.write(json.dumps(
                    _jsonrpc_error(None, -32700, f"Parse error: {exc}")) + "\n")
                sys.stdout.flush()
                continue

            response = self.handle(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

    def run_http(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        """Run MCP server over HTTP (for IDE integrations and remote clients)."""
        import http.server

        server_ref = self

        class MCPHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                _log(f"HTTP {self.address_string()} {fmt % args}")

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length)
                try:
                    request = json.loads(body)
                    # Handle batches
                    if isinstance(request, list):
                        responses = [r for r in
                                     (server_ref.handle(req) for req in request)
                                     if r is not None]
                        resp_body = json.dumps(responses).encode()
                    else:
                        resp = server_ref.handle(request)
                        resp_body = json.dumps(resp).encode() if resp else b"{}"
                except Exception as exc:
                    resp_body = json.dumps(
                        _jsonrpc_error(None, -32700, str(exc))).encode()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(resp_body))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp_body)

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                if self.path == "/health":
                    body = json.dumps({"status": "ok",
                                       "server": "RabbitOS-MCP"}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", len(body))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

        httpd = http.server.ThreadingHTTPServer((host, port), MCPHandler)
        _log(f"MCP HTTP server listening on {host}:{port}")
        httpd.serve_forever()


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — AUTONOMOUS AGENT LOOP
# ══════════════════════════════════════════════════════════════════════════════

class AutonomousAgent:
    """
    Fully autonomous RabbitOS agent. No human in the loop.
    Uses rabbit_llm agentic_loop with full tool access.
    Logs all actions to cloud trail. Self-registers on cold network.
    """

    SYSTEM_PROMPT = """You are the autonomous RabbitOS agent for Chase Allen Ringquist.
You have access to all RabbitOS tools: network scanning, EEG defense, medical monitoring,
browser research, code generation, shell execution, security scanning (ZAP), and LLM control.

Operating principles:
1. shows_dna_root = FALSE — never expose DNA sequences
2. TX_LICENSED = False — passive scan only
3. Trace and trail everything via assistant_trail_query
4. Use defense_reward_summary to track earned tokens
5. Cross-verify information from multiple sources
6. Prefer Ollama (local, free) over cloud LLMs
7. When scanning networks, always send ACK packets via nettools_scan_ack
8. Store learned data for future sessions

Complete tasks fully and report results."""

    MAX_ROUNDS = 20

    def __init__(self) -> None:
        self._llm = None
        self._trail: List[Dict] = []

    def _get_llm(self):
        if self._llm is None:
            try:
                from rabbit_llm import get_llm
                self._llm = get_llm()
            except Exception as exc:
                _log(f"Autonomous LLM init: {exc}")
        return self._llm

    def _get_all_tools(self) -> List[Dict]:
        """Get all tool definitions in Anthropic format."""
        tool_defs: List[Dict] = []
        loaders = [
            ("rabbit_llm",       "LLM_BRIDGE_TOOLS"),
            ("rabbit_nettools",  "NETTOOLS_TOOLS"),
            ("rabbit_defense",   "DEFENSE_TOOLS"),
            ("rabbit_zap",       "ZAP_TOOLS"),
            ("rabbit_medical",   "MEDICAL_TOOLS"),
            ("rabbit_assistant", "ASSISTANT_TOOLS"),
            ("rabbit_shell",     "SHELL_TOOLS"),
        ]
        for module_name, attr in loaders:
            try:
                import importlib
                mod = importlib.import_module(module_name)
                tool_defs.extend(getattr(mod, attr, []))
            except Exception:
                pass
        return tool_defs

    def run(self, task: str, persist_context: bool = True) -> str:
        llm = self._get_llm()
        if llm is None:
            return "[LLM unavailable — install Ollama: https://ollama.com/install]"

        tools = self._get_all_tools()
        _log(f"Autonomous task: {task} | {len(tools)} tools available")

        t0 = time.time()
        try:
            result = llm.agentic_loop(
                question=task,
                tools=tools,
                tool_dispatcher=_dispatch_tool,
                system=self.SYSTEM_PROMPT,
                max_rounds=self.MAX_ROUNDS,
            )
        except Exception as exc:
            result = f"[Autonomous agent error: {exc}]"

        elapsed = round((time.time() - t0), 2)
        _log(f"Autonomous task complete in {elapsed}s: {result[:100]}")

        # Log to cloud trail
        try:
            from rabbit_assistant import get_assistant
            get_assistant().trail.log(
                "AutonomousAgent", "run", task,
                result={"result_len": len(result)},
                duration_ms=elapsed * 1000,
            )
        except Exception:
            pass

        return result

    def schedule_task(self, task: str, delay_seconds: float = 0) -> threading.Thread:
        def _run():
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            self.run(task)

        t = threading.Thread(target=_run, daemon=True,
                              name=f"auto_{hashlib.sha256(task.encode()).hexdigest()[:8]}")
        t.start()
        return t


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — SDK ADAPTERS
# ══════════════════════════════════════════════════════════════════════════════

def rabbitos_langchain_tools() -> List[Any]:
    """
    Return RabbitOS tools in LangChain Tool format.
    Requires: pip install langchain
    """
    try:
        from langchain.tools import Tool  # type: ignore
    except ImportError:
        _log("LangChain not installed: pip install langchain")
        return []

    loaders = [
        ("rabbit_llm",       "LLM_BRIDGE_TOOLS"),
        ("rabbit_nettools",  "NETTOOLS_TOOLS"),
        ("rabbit_defense",   "DEFENSE_TOOLS"),
        ("rabbit_zap",       "ZAP_TOOLS"),
    ]
    lc_tools = []
    for module_name, attr in loaders:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            for t in getattr(mod, attr, []):
                name = t["name"]
                desc = t.get("description", "")

                def _make_fn(n=name):
                    def fn(input_str: str) -> str:
                        try:
                            args = json.loads(input_str)
                        except Exception:
                            args = {"input": input_str}
                        return json.dumps(_dispatch_tool(n, args),
                                          indent=2, default=str)
                    return fn

                lc_tools.append(Tool(
                    name=name,
                    description=desc[:1000],
                    func=_make_fn(),
                ))
        except Exception:
            pass
    return lc_tools


def rabbitos_openai_tools() -> List[Dict]:
    """
    Return RabbitOS tools in OpenAI function-calling format.
    Compatible with: openai>=1.0, litellm, Ollama /api/chat.
    """
    loaders = [
        ("rabbit_llm",       "LLM_BRIDGE_TOOLS"),
        ("rabbit_nettools",  "NETTOOLS_TOOLS"),
        ("rabbit_defense",   "DEFENSE_TOOLS"),
        ("rabbit_zap",       "ZAP_TOOLS"),
        ("rabbit_medical",   "MEDICAL_TOOLS"),
        ("rabbit_shell",     "SHELL_TOOLS"),
    ]
    openai_tools = []
    for module_name, attr in loaders:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            for t in getattr(mod, attr, []):
                schema = t.get("input_schema", {})
                # Strip $schema / additionalProperties for OpenAI compat
                schema.pop("$schema", None)
                schema.pop("additionalProperties", None)
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": schema,
                    },
                })
        except Exception:
            pass
    return openai_tools


# ══════════════════════════════════════════════════════════════════════════════
# PART 6 — CLOUD NETWORK SELF-REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

def self_register_on_cloud(supabase_url: str = "",
                             service_key: str = "") -> Dict[str, Any]:
    """
    Register this RabbitOS node on the cloud cold network.
    Stores: hostname, IP, OS, capabilities, MCP endpoint.
    """
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "127.0.0.1"

    node_id = hashlib.sha256(
        f"{hostname}{local_ip}".encode()).hexdigest()[:16]

    node_record = {
        "node_id":     node_id,
        "hostname":    hostname,
        "ip":          local_ip,
        "os_family":   platform.system(),
        "os_version":  platform.version()[:100],
        "arch":        platform.machine(),
        "capabilities": ["mcp", "llm", "defense", "zap", "medical", "shell"],
        "mcp_endpoint": f"http://{local_ip}:8765",
        "registered_ts": time.time(),
        "shows_dna_root": False,
    }

    # Store locally
    try:
        from rabbit_assistant import get_assistant
        eng = get_assistant()
        eng.registry.register(
            type("NetworkNode", (), node_record)()  # duck-type for auto-discover
        )
    except Exception:
        pass

    # Push to Supabase if configured
    if supabase_url and service_key:
        url  = supabase_url.rstrip("/") + "/rest/v1/rabbitos_nodes"
        data = json.dumps(node_record).encode()
        req  = urllib.request.Request(url, data=data, method="POST",
               headers={
                   "Authorization": f"Bearer {service_key}",
                   "apikey": service_key,
                   "Content-Type": "application/json",
                   "Prefer": "resolution=merge-duplicates,return=minimal",
               })
        try:
            with urllib.request.urlopen(req, timeout=10):
                node_record["supabase_registered"] = True
        except Exception as exc:
            node_record["supabase_error"] = str(exc)

    _log(f"Self-registered node: {node_id} @ {local_ip}")
    return node_record


# ══════════════════════════════════════════════════════════════════════════════
# MCP TOOLS (for nesting: the MCP server itself is a tool)
# ══════════════════════════════════════════════════════════════════════════════

MCP_TOOLS = [
    {
        "name": "mcp_status",
        "description": "Get MCP server status and loaded tool count",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mcp_list_tools",
        "description": "List all available MCP tools across all RabbitOS modules",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mcp_autonomous_run",
        "description": "Run an autonomous agent task with full tool access (no human in loop)",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task to execute autonomously"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "mcp_autonomous_schedule",
        "description": "Schedule an autonomous task to run after a delay",
        "input_schema": {
            "type": "object",
            "properties": {
                "task":          {"type": "string"},
                "delay_seconds": {"type": "number"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "mcp_self_register",
        "description": "Register this RabbitOS node on the cloud cold network",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mcp_openai_tools",
        "description": "Export all RabbitOS tools in OpenAI function-calling format",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mcp_read_resource",
        "description": "Read a RabbitOS MCP resource",
        "input_schema": {
            "type": "object",
            "properties": {
                "uri": {"type": "string",
                        "description": "rabbitos://status | rabbitos://eeg/nodes | "
                                       "rabbitos://network/topology | rabbitos://defense/alerts | "
                                       "rabbitos://medical/report | rabbitos://cloud/trail"},
            },
            "required": ["uri"],
        },
    },
]


_mcp_server_instance: Optional[RabbitMCPServer] = None
_mcp_agent_instance:  Optional[AutonomousAgent]  = None


def get_mcp_server() -> RabbitMCPServer:
    global _mcp_server_instance
    if _mcp_server_instance is None:
        _mcp_server_instance = RabbitMCPServer()
    return _mcp_server_instance


def get_autonomous_agent() -> AutonomousAgent:
    global _mcp_agent_instance
    if _mcp_agent_instance is None:
        _mcp_agent_instance = AutonomousAgent()
    return _mcp_agent_instance


def dispatch_mcp_tool(name: str, inputs: Dict) -> Any:
    server = get_mcp_server()
    agent  = get_autonomous_agent()

    if name == "mcp_status":
        tools = server._get_tools()
        return {
            "protocol_version": MCP_PROTOCOL_VERSION,
            "server_info": server.SERVER_INFO,
            "tool_count": len(tools),
            "resource_count": len(server._resources),
            "prompt_count": len(server._prompts),
            "capabilities": server.CAPABILITIES,
        }

    elif name == "mcp_list_tools":
        tools = server._get_tools()
        return [{"name": t.name, "description": t.description} for t in tools]

    elif name == "mcp_autonomous_run":
        result = agent.run(inputs["task"])
        return {"result": result}

    elif name == "mcp_autonomous_schedule":
        t = agent.schedule_task(inputs["task"],
                                 inputs.get("delay_seconds", 0))
        return {"scheduled": True, "thread": t.name,
                "delay_seconds": inputs.get("delay_seconds", 0)}

    elif name == "mcp_self_register":
        svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        sup_url = "https://ludxbakxpmdqhfgdenwp.supabase.co"
        return self_register_on_cloud(sup_url, svc_key)

    elif name == "mcp_openai_tools":
        return rabbitos_openai_tools()

    elif name == "mcp_read_resource":
        text = server._read_resource(inputs.get("uri", ""))
        return {"uri": inputs.get("uri"), "content": text}

    else:
        return {"error": f"Unknown MCP tool: {name}"}


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="RabbitOS MCP Server + Autonomous Agent")
    parser.add_argument("--stdio",  action="store_true",
                        help="Run MCP server over stdin/stdout (Claude Desktop)")
    parser.add_argument("--http",   type=int, metavar="PORT",
                        help="Run MCP HTTP server on PORT (default 8765)")
    parser.add_argument("--auto",   type=str, metavar="TASK",
                        help="Run autonomous agent on TASK")
    parser.add_argument("--status", action="store_true",
                        help="Print system status")
    parser.add_argument("--register", action="store_true",
                        help="Self-register on cloud cold network")
    args = parser.parse_args()

    if args.stdio:
        get_mcp_server().run_stdio()

    elif args.http:
        get_mcp_server().run_http(port=args.http)

    elif args.auto:
        result = get_autonomous_agent().run(args.auto)
        print(result)

    elif args.status:
        srv = get_mcp_server()
        tools = srv._get_tools()
        print(json.dumps({
            "protocol_version": MCP_PROTOCOL_VERSION,
            "server_info": srv.SERVER_INFO,
            "tool_count": len(tools),
            "shows_dna_root": False,
        }, indent=2))

    elif args.register:
        svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        result  = self_register_on_cloud(
            "https://ludxbakxpmdqhfgdenwp.supabase.co", svc_key)
        print(json.dumps(result, indent=2, default=str))

    else:
        parser.print_help()
        print("\n--- Available MCP Resources ---")
        for r in get_mcp_server()._resources:
            print(f"  {r.uri:40s} {r.description}")
        print("\n--- Available MCP Prompts ---")
        for p in get_mcp_server()._prompts:
            print(f"  {p.name:30s} {p.description}")
