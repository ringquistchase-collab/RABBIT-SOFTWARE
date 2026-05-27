"""
rabbit_watchdog.py — RabbitOS Autonomous System Health, Repair & Deployment Agent
Chase Allen Ringquist | RABBIT-SOFTWARE

Covers:
  - SystemHealthMonitor : CPU / RAM / disk / network / DB health checks
  - CrashDetector       : exception log parsing, hung threads, OOM detection
  - AutoRepairEngine    : module reload, DB repair, network reset, disk cleanup
  - DeploymentManager   : GitHub push status, syntax validation, deploy tracking
  - WatchdogOrchestrator: agentic loop — monitor → detect → repair → verify → report
  - CloudTrail integration + Supabase reporting + LLM root-cause analysis
"""
from __future__ import annotations

import ast
import base64
import gc
import hashlib
import importlib
import json
import logging
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

shows_dna_root = False
assert shows_dna_root is False

_LOG = logging.getLogger("rabbit.watchdog")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [WATCHDOG] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

_BASE = Path(__file__).parent
_WD_DB = _BASE / "rabbit_watchdog.db"

RABBIT_MODULES = [
    "rabbit_llm",
    "rabbit_nettools",
    "rabbit_defense",
    "rabbit_zap",
    "rabbit_medical",
    "rabbit_assistant",
    "rabbit_shell",
    "rabbit_mcp",
    "rabbit_agent",
    "rabbit_watchdog",
    "rabbit_monitor",
    "rabbit_intel",
    "rabbit_osint",
]

RABBIT_DBS = [
    "rabbit_trail.db",
    "rabbit_fs.db",
    "rabbit_survival.db",
    "rabbit_watchdog.db",
    "rabbit_nettools.db",
    "rabbit_scan_cache.db",
    "rabbit_monitor.db",
    "rabbit_intel.db",
    "rabbit_osint.db",
]


def _log(msg: str) -> None:
    try:
        _LOG.info(msg)
    except UnicodeEncodeError:
        _LOG.info(msg.encode("ascii", "replace").decode())


def _get_llm():
    try:
        from rabbit_llm import get_llm
        return get_llm()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class HealthCheck:
    component:  str
    status:     str    # ok / warn / fail / unknown
    score:      float  # 0.0–1.0
    message:    str    = ""
    detail:     Dict   = field(default_factory=dict)
    repaired:   bool   = False
    repair_note: str   = ""
    ts:         float  = field(default_factory=time.time)


@dataclass
class RepairAction:
    action_id:  str
    component:  str
    action:     str
    outcome:    str    # success / partial / failed / skipped
    before:     str    = ""
    after:      str    = ""
    ts:         float  = field(default_factory=time.time)


@dataclass
class DeployRecord:
    deploy_id:  str
    files:      List[str]
    commit_sha: str
    status:     str    # ok / failed / partial
    message:    str    = ""
    ts:         float  = field(default_factory=time.time)


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — SYSTEM HEALTH MONITOR
# ══════════════════════════════════════════════════════════════════════════════

class SystemHealthMonitor:
    """
    Checks CPU, RAM, disk, network, databases, and all rabbit_* modules.
    Returns structured HealthCheck objects for each component.
    """

    # Thresholds
    DISK_WARN_PCT  = 80.0
    DISK_FAIL_PCT  = 95.0
    RAM_WARN_PCT   = 85.0
    RAM_FAIL_PCT   = 95.0
    CPU_WARN_PCT   = 90.0

    def check_cpu(self) -> HealthCheck:
        try:
            import psutil
            pct = psutil.cpu_percent(interval=1)
            status = "ok" if pct < self.CPU_WARN_PCT else "warn"
            return HealthCheck("cpu", status, 1.0 - pct / 100,
                               f"CPU {pct:.1f}%", {"cpu_pct": pct})
        except ImportError:
            # Fallback: parse /proc/loadavg or Windows wmic
            try:
                if platform.system() == "Windows":
                    out = subprocess.run(
                        ["wmic", "cpu", "get", "loadpercentage", "/value"],
                        capture_output=True, text=True, timeout=5).stdout
                    m = re.search(r"LoadPercentage=(\d+)", out)
                    pct = float(m.group(1)) if m else 0.0
                else:
                    with open("/proc/loadavg") as f:
                        load = float(f.read().split()[0])
                    cpu_count = os.cpu_count() or 1
                    pct = min(load / cpu_count * 100, 100.0)
                status = "ok" if pct < self.CPU_WARN_PCT else "warn"
                return HealthCheck("cpu", status, 1.0 - pct / 100,
                                   f"CPU ~{pct:.0f}%", {"cpu_pct": pct})
            except Exception as exc:
                return HealthCheck("cpu", "unknown", 0.5, str(exc))

    def check_memory(self) -> HealthCheck:
        try:
            import psutil
            vm = psutil.virtual_memory()
            pct = vm.percent
            status = ("ok" if pct < self.RAM_WARN_PCT
                      else "warn" if pct < self.RAM_FAIL_PCT else "fail")
            return HealthCheck(
                "memory", status, 1.0 - pct / 100,
                f"RAM {pct:.1f}%  used={vm.used//1024//1024}MB "
                f"avail={vm.available//1024//1024}MB",
                {"used_mb": vm.used//1024//1024,
                 "avail_mb": vm.available//1024//1024, "pct": pct})
        except ImportError:
            try:
                total, used, free = shutil.disk_usage(".")
                return HealthCheck("memory", "unknown", 0.5,
                                   "psutil not available", {})
            except Exception:
                return HealthCheck("memory", "unknown", 0.5, "unavailable", {})

    def check_disk(self, path: str = ".") -> HealthCheck:
        try:
            total, used, free = shutil.disk_usage(path)
            pct = used / total * 100
            free_gb = free / 1e9
            status = ("ok" if pct < self.DISK_WARN_PCT
                      else "warn" if pct < self.DISK_FAIL_PCT else "fail")
            return HealthCheck(
                "disk", status, 1.0 - pct / 100,
                f"Disk {pct:.1f}%  free={free_gb:.2f}GB",
                {"path": path, "total_gb": round(total/1e9,2),
                 "used_gb": round(used/1e9,2), "free_gb": round(free_gb,2),
                 "used_pct": round(pct,1)})
        except Exception as exc:
            return HealthCheck("disk", "fail", 0.0, str(exc))

    def check_network(self) -> HealthCheck:
        checks = []
        score  = 0.0
        # Ping gateway
        gw = self._get_gateway()
        if gw:
            try:
                cmd = (["ping", "-n", "1", "-w", "1000", gw]
                       if platform.system() == "Windows"
                       else ["ping", "-c", "1", "-W", "1", gw])
                rc = subprocess.run(cmd, capture_output=True, timeout=5).returncode
                checks.append({"gateway": gw, "reachable": rc == 0})
                if rc == 0:
                    score += 0.4
            except Exception as exc:
                checks.append({"gateway": gw, "error": str(exc)})
        # External connectivity
        for host in ["8.8.8.8", "1.1.1.1"]:
            try:
                socket.create_connection((host, 53), timeout=2).close()
                checks.append({"dns": host, "reachable": True})
                score += 0.3
                break
            except Exception:
                checks.append({"dns": host, "reachable": False})
        # HTTP connectivity
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    "https://api.github.com",
                    headers={"User-Agent": "RabbitOS"}),
                timeout=5)
            checks.append({"https": "github.com", "reachable": True})
            score += 0.3
        except Exception:
            checks.append({"https": "github.com", "reachable": False})

        status = ("ok" if score >= 0.7
                  else "warn" if score >= 0.3 else "fail")
        return HealthCheck("network", status, min(score, 1.0),
                           f"Network score={score:.1f}", {"checks": checks})

    def _get_gateway(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["ipconfig"], capture_output=True,
                                     text=True, timeout=5).stdout
                m = re.search(r"Default Gateway[. ]+: ([\d.]+)", out)
                return m.group(1) if m else ""
            else:
                out = subprocess.run(["ip", "route"], capture_output=True,
                                     text=True, timeout=5).stdout
                m = re.search(r"default via ([\d.]+)", out)
                return m.group(1) if m else ""
        except Exception:
            return ""

    def check_module(self, module_name: str) -> HealthCheck:
        path = _BASE / f"{module_name}.py"
        # Syntax check
        if path.exists():
            try:
                src = path.read_text(encoding="utf-8", errors="replace")
                ast.parse(src)
            except SyntaxError as exc:
                return HealthCheck(module_name, "fail", 0.0,
                                   f"Syntax error line {exc.lineno}: {exc.msg}",
                                   {"syntax_error": str(exc)})
        else:
            return HealthCheck(module_name, "fail", 0.0,
                               f"File not found: {path}", {})

        # Import check (in subprocess to avoid polluting current process)
        try:
            result = subprocess.run(
                [sys.executable, "-c",
                 f"import sys; sys.path.insert(0,r'{_BASE}'); "
                 f"import {module_name}; print('ok')"],
                capture_output=True, text=True, timeout=15,
                cwd=str(_BASE))
            if "ok" in result.stdout:
                return HealthCheck(module_name, "ok", 1.0, "Imports cleanly",
                                   {"import": "ok"})
            else:
                err = (result.stderr or result.stdout)[:300]
                return HealthCheck(module_name, "fail", 0.0,
                                   f"Import failed: {err}", {"stderr": err})
        except subprocess.TimeoutExpired:
            return HealthCheck(module_name, "warn", 0.5,
                               "Import timed out (possible blocking call)", {})
        except Exception as exc:
            return HealthCheck(module_name, "fail", 0.0, str(exc), {})

    def check_database(self, db_name: str) -> HealthCheck:
        db_path = _BASE / db_name
        if not db_path.exists():
            return HealthCheck(db_name, "ok", 1.0, "DB not yet created (ok)", {})
        try:
            conn = sqlite3.connect(str(db_path), timeout=5)
            rows = conn.execute("PRAGMA integrity_check").fetchall()
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            conn.close()
            ok = rows and rows[0][0] == "ok"
            if ok:
                size_kb = db_path.stat().st_size // 1024
                return HealthCheck(db_name, "ok", 1.0,
                                   f"Integrity ok, {size_kb}KB",
                                   {"size_kb": size_kb, "integrity": "ok"})
            else:
                return HealthCheck(db_name, "fail", 0.0,
                                   f"Integrity check failed: {rows[:3]}",
                                   {"integrity": [r[0] for r in rows[:5]]})
        except Exception as exc:
            return HealthCheck(db_name, "fail", 0.0, str(exc),
                               {"error": str(exc)[:200]})

    def check_supabase(self, supabase_url: str = "",
                       service_key: str = "") -> HealthCheck:
        url = (supabase_url
               or os.environ.get("SUPABASE_URL", "")
               or "https://xpwrynstilukpuflpgpc.supabase.co")
        key = service_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        try:
            req = urllib.request.Request(
                url.rstrip("/") + "/rest/v1/",
                headers={"apikey": key or "anon",
                         "User-Agent": "RabbitOS-Watchdog"})
            with urllib.request.urlopen(req, timeout=8) as r:
                status_code = r.status
            ok = status_code in (200, 404)   # 404 is fine (no tables yet)
            return HealthCheck(
                "supabase", "ok" if ok else "warn",
                1.0 if ok else 0.5,
                f"Supabase HTTP {status_code}",
                {"url": url, "status": status_code})
        except Exception as exc:
            return HealthCheck("supabase", "fail", 0.0,
                               f"Supabase unreachable: {exc}",
                               {"error": str(exc)[:200]})

    def check_github_api(self, token: str = "") -> HealthCheck:
        tok = token or os.environ.get("GITHUB_TOKEN", "")
        try:
            headers = {"User-Agent": "RabbitOS-Watchdog",
                       "Accept": "application/vnd.github.v3+json"}
            if tok:
                headers["Authorization"] = f"token {tok}"
            req = urllib.request.Request(
                "https://api.github.com/rate_limit", headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            remaining = data.get("rate", {}).get("remaining", 0)
            limit     = data.get("rate", {}).get("limit", 60)
            ok = remaining > 5
            return HealthCheck(
                "github_api",
                "ok" if ok else "warn",
                remaining / max(limit, 1),
                f"GitHub API rate: {remaining}/{limit}",
                {"remaining": remaining, "limit": limit})
        except Exception as exc:
            return HealthCheck("github_api", "fail", 0.0,
                               f"GitHub API unreachable: {exc}", {})

    def full_check(self, token: str = "",
                   supabase_url: str = "",
                   service_key: str = "") -> Dict[str, HealthCheck]:
        checks: Dict[str, HealthCheck] = {}
        tasks: List[Tuple[str, Callable]] = [
            ("cpu",        self.check_cpu),
            ("memory",     self.check_memory),
            ("disk",       self.check_disk),
            ("network",    self.check_network),
            ("supabase",   lambda: self.check_supabase(supabase_url, service_key)),
            ("github_api", lambda: self.check_github_api(token)),
        ]
        for module in RABBIT_MODULES:
            name = module
            tasks.append((name, lambda m=module: self.check_module(m)))
        for db in RABBIT_DBS:
            tasks.append((db, lambda d=db: self.check_database(d)))

        lock   = threading.Lock()
        errors = []

        def run(name, fn):
            try:
                result = fn()
                with lock:
                    checks[name] = result
            except Exception as exc:
                with lock:
                    errors.append((name, str(exc)))
                    checks[name] = HealthCheck(name, "fail", 0.0, str(exc))

        threads = [
            threading.Thread(target=run, args=(n, f), daemon=True)
            for n, f in tasks
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        return checks

    def health_score(self, checks: Dict[str, HealthCheck]) -> float:
        if not checks:
            return 0.0
        return round(sum(c.score for c in checks.values()) / len(checks), 3)


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — CRASH DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class CrashDetector:
    """
    Detects crashes from log files, exception traceback patterns,
    hung threads, OOM events, and Windows Event Log failures.
    """

    LOG_PATTERNS = [
        r"Traceback \(most recent call last\)",
        r"Exception:",
        r"Error:",
        r"CRITICAL",
        r"OOM",
        r"MemoryError",
        r"sqlite3\.OperationalError",
        r"sqlite3\.DatabaseError",
        r"ConnectionRefusedError",
        r"TimeoutError",
        r"RecursionError",
        r"SystemExit",
    ]

    def scan_log_file(self, log_path: str,
                      lines: int = 500) -> List[Dict]:
        """Return crash events from a log file."""
        events = []
        try:
            path = Path(log_path)
            if not path.exists():
                return []
            text = path.read_text(encoding="utf-8", errors="replace")
            tail = text.splitlines()[-lines:]
            combined = re.compile("|".join(self.LOG_PATTERNS), re.I)
            for i, line in enumerate(tail):
                if combined.search(line):
                    context = tail[max(0, i-2):i+3]
                    events.append({
                        "line": i + max(0, len(tail) - lines),
                        "text": line.strip()[:200],
                        "context": [l[:120] for l in context],
                        "log": log_path,
                    })
        except Exception as exc:
            events.append({"error": str(exc), "log": log_path})
        return events[:50]

    def scan_all_logs(self) -> List[Dict]:
        all_events = []
        log_files = list(_BASE.glob("*.log")) + list(_BASE.glob("*.txt"))
        for lf in log_files:
            all_events.extend(self.scan_log_file(str(lf)))
        return all_events[:200]

    def check_windows_event_log(self, last_n: int = 20) -> List[Dict]:
        """Check Windows Application event log for recent errors."""
        if platform.system() != "Windows":
            return []
        try:
            out = subprocess.run(
                ["powershell", "-Command",
                 f"Get-EventLog -LogName Application -EntryType Error -Newest {last_n} "
                 "| Select-Object TimeGenerated,Source,EventID,Message "
                 "| ConvertTo-Json -Depth 2"],
                capture_output=True, text=True, timeout=15).stdout
            events = json.loads(out) if out.strip() else []
            if isinstance(events, dict):
                events = [events]
            return [{
                "ts":      e.get("TimeGenerated", ""),
                "source":  e.get("Source", ""),
                "event_id":e.get("EventID", 0),
                "message": str(e.get("Message", ""))[:200],
            } for e in events][:20]
        except Exception as exc:
            return [{"error": str(exc)[:100]}]

    def detect_stuck_threads(self) -> List[Dict]:
        """Return any Python threads that appear stuck."""
        stuck = []
        for thread in threading.enumerate():
            if thread.daemon:
                continue
            stuck.append({
                "name":  thread.name,
                "alive": thread.is_alive(),
                "daemon":thread.daemon,
                "ident": thread.ident,
            })
        return stuck

    def full_crash_report(self) -> Dict[str, Any]:
        return {
            "log_events":     self.scan_all_logs(),
            "windows_events": self.check_windows_event_log(),
            "threads":        self.detect_stuck_threads(),
            "ts":             time.time(),
        }


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — AUTO REPAIR ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AutoRepairEngine:
    """
    Attempts automated repair of detected failures.

    Repair strategies by failure type:
    - Module syntax error  → report exact location, suggest fix with LLM
    - Module import fail   → check dependencies, reload
    - SQLite corrupted     → integrity check + WAL checkpoint + vacuum
    - Disk full            → clean .pyc / __pycache__ / temp files
    - Network unreachable  → reset adapter (Windows netsh), flush DNS
    - Memory pressure      → force GC, suggest process restart
    - Supabase down        → switch to local SQLite fallback
    - GitHub API rate-limit→ wait and retry with backoff
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._actions: List[RepairAction] = []

    def _record(self, component: str, action: str, outcome: str,
                before: str = "", after: str = "") -> RepairAction:
        ra = RepairAction(
            action_id=hashlib.sha256(
                f"{component}{action}{time.time()}".encode()).hexdigest()[:12],
            component=component, action=action,
            outcome=outcome, before=before, after=after,
        )
        with self._lock:
            self._actions.append(ra)
        return ra

    def repair_module(self, module_name: str,
                      health: HealthCheck) -> RepairAction:
        """Try to fix a failing module."""
        if health.status == "ok":
            return self._record(module_name, "skip", "skipped",
                                after="Module already healthy")

        path = _BASE / f"{module_name}.py"
        if not path.exists():
            return self._record(module_name, "not_found", "failed",
                                after=f"File missing: {path}")

        # Syntax error: try LLM fix
        if "Syntax error" in health.message or "syntax" in health.message.lower():
            llm = _get_llm()
            if llm:
                try:
                    src = path.read_text(encoding="utf-8", errors="replace")
                    snippet = src[max(0, 0):3000]
                    fix = llm.simple_ask(
                        f"The Python file '{module_name}.py' has a syntax error: "
                        f"{health.message}\n\nFirst 3000 chars:\n{snippet}\n\n"
                        "Return ONLY the corrected Python code, no explanation.")
                    if fix and "def " in fix:
                        bak = path.with_suffix(".py.watchdog_bak")
                        shutil.copy2(str(path), str(bak))
                        try:
                            ast.parse(fix)
                            path.write_text(fix, encoding="utf-8")
                            return self._record(
                                module_name, "llm_syntax_fix", "success",
                                before=health.message,
                                after="LLM syntax fix applied")
                        except SyntaxError:
                            shutil.copy2(str(bak), str(path))
                            return self._record(
                                module_name, "llm_syntax_fix", "failed",
                                after="LLM fix also had syntax errors, reverted")
                except Exception as exc:
                    return self._record(
                        module_name, "llm_syntax_fix", "failed",
                        after=str(exc)[:100])
            return self._record(
                module_name, "syntax_check", "failed",
                before=health.message,
                after="Syntax error — LLM unavailable for auto-fix")

        # Import error: clear pyc cache and retry
        cache_dir = _BASE / "__pycache__"
        cleared = 0
        if cache_dir.exists():
            for pyc in cache_dir.glob(f"{module_name}*.pyc"):
                try:
                    pyc.unlink()
                    cleared += 1
                except Exception:
                    pass
        if cleared:
            return self._record(
                module_name, "clear_pyc", "success",
                before=health.message,
                after=f"Cleared {cleared} cached .pyc files")

        return self._record(
            module_name, "diagnose", "partial",
            before=health.message,
            after="Manual inspection required")

    def repair_database(self, db_name: str,
                        health: HealthCheck) -> RepairAction:
        if health.status == "ok":
            return self._record(db_name, "skip", "skipped")

        db_path = _BASE / db_name
        if not db_path.exists():
            return self._record(db_name, "skip", "skipped",
                                after="DB does not exist yet")

        bak = db_path.with_suffix(
            f".db.watchdog_{int(time.time())}.bak")
        try:
            shutil.copy2(str(db_path), str(bak))
        except Exception:
            pass

        actions_taken = []
        try:
            conn = sqlite3.connect(str(db_path), timeout=10)
            conn.execute("PRAGMA integrity_check")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
            conn.close()
            actions_taken.append("wal_checkpoint + VACUUM")
        except Exception as exc:
            # DB is critically corrupt — delete and let the module recreate
            try:
                wal  = db_path.with_suffix(".db-wal")
                shm  = db_path.with_suffix(".db-shm")
                db_path.unlink(missing_ok=True)
                wal.unlink(missing_ok=True)
                shm.unlink(missing_ok=True)
                actions_taken.append(f"deleted corrupt DB (backup at {bak.name})")
            except Exception as del_exc:
                return self._record(
                    db_name, "repair_db", "failed",
                    before=health.message,
                    after=f"Could not repair or delete: {del_exc}")

        return self._record(
            db_name, "repair_db", "success",
            before=health.message,
            after="; ".join(actions_taken))

    def repair_network(self, health: HealthCheck) -> RepairAction:
        if health.status == "ok":
            return self._record("network", "skip", "skipped")

        actions = []
        if platform.system() == "Windows":
            try:
                subprocess.run(
                    ["ipconfig", "/flushdns"],
                    capture_output=True, timeout=10)
                actions.append("flushdns")
            except Exception:
                pass
            try:
                subprocess.run(
                    ["netsh", "interface", "ip", "reset"],
                    capture_output=True, timeout=15)
                actions.append("ip reset")
            except Exception:
                pass
        else:
            try:
                subprocess.run(
                    ["systemctl", "restart", "NetworkManager"],
                    capture_output=True, timeout=15)
                actions.append("restart NetworkManager")
            except Exception:
                try:
                    subprocess.run(
                        ["service", "networking", "restart"],
                        capture_output=True, timeout=15)
                    actions.append("restart networking")
                except Exception:
                    pass

        outcome = "success" if actions else "failed"
        return self._record(
            "network", "repair_network", outcome,
            before=health.message,
            after="; ".join(actions) or "no repair available")

    def repair_disk(self, health: HealthCheck) -> RepairAction:
        if health.score > 0.2:
            return self._record("disk", "skip", "skipped")

        freed_bytes = 0
        actions     = []

        # Clear __pycache__
        cache = _BASE / "__pycache__"
        if cache.exists():
            for f in cache.iterdir():
                try:
                    freed_bytes += f.stat().st_size
                    f.unlink()
                except Exception:
                    pass
            actions.append("cleared __pycache__")

        # Clear temp files
        tmp = Path(tempfile.gettempdir())
        for pattern in ["*.tmp", "_rabbitos_*.db"]:
            for f in tmp.glob(pattern):
                try:
                    freed_bytes += f.stat().st_size
                    f.unlink()
                except Exception:
                    pass
        actions.append(f"cleaned temp ({freed_bytes//1024}KB freed)")

        # WAL checkpoint all DBs
        for db_name in RABBIT_DBS:
            db_path = _BASE / db_name
            if db_path.exists():
                try:
                    conn = sqlite3.connect(str(db_path), timeout=5)
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    conn.close()
                except Exception:
                    pass
        actions.append("WAL checkpoint all DBs")

        return self._record(
            "disk", "cleanup", "success" if freed_bytes > 0 else "partial",
            before=health.message,
            after="; ".join(actions))

    def repair_memory(self) -> RepairAction:
        before_count = len(gc.get_objects())
        collected    = gc.collect()
        after_count  = len(gc.get_objects())
        return self._record(
            "memory", "gc_collect", "success",
            before=f"{before_count} objects",
            after=f"collected={collected}  remaining={after_count}")

    def repair_all(self,
                   checks: Dict[str, HealthCheck]) -> List[RepairAction]:
        """Run all applicable repairs based on health check results."""
        results: List[RepairAction] = []

        for name, hc in checks.items():
            if hc.status in ("ok", "unknown"):
                continue

            if name in RABBIT_MODULES:
                results.append(self.repair_module(name, hc))
            elif name in RABBIT_DBS or name.endswith(".db"):
                results.append(self.repair_database(name, hc))
            elif name == "network":
                results.append(self.repair_network(hc))
            elif name == "disk":
                results.append(self.repair_disk(hc))
            elif name == "memory":
                results.append(self.repair_memory())

        return results

    def get_actions(self) -> List[RepairAction]:
        with self._lock:
            return list(self._actions)


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — DEPLOYMENT MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class DeploymentManager:
    """
    Manages GitHub pushes via Git Trees API.
    Validates syntax before push, tracks deployment history,
    re-deploys on failure, reports status.
    """

    REPO   = "therealsickonechase-bit/RABBIT-SOFTWARE"
    BRANCH = "main"

    def __init__(self, token: str = "") -> None:
        self._token  = (token
                        or os.environ.get("GITHUB_TOKEN", ""))
        self._lock   = threading.Lock()
        self._history: List[DeployRecord] = []
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(str(_WD_DB), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deploy_history (
                    deploy_id TEXT PRIMARY KEY,
                    files TEXT, commit_sha TEXT,
                    status TEXT, message TEXT, ts REAL
                )""")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _gh(self, method: str, path: str,
            body: Optional[Dict] = None) -> Dict:
        url  = "https://api.github.com/" + path
        data = json.dumps(body).encode() if body else None
        req  = urllib.request.Request(
            url, data=data, method=method,
            headers={
                "Authorization": f"token {self._token}",
                "Content-Type":  "application/json",
                "Accept":        "application/vnd.github.v3+json",
                "User-Agent":    "RabbitOS-Watchdog",
            })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {"error": e.code, "detail": e.read().decode()[:200]}

    def validate_syntax(self, files: List[str]) -> Dict[str, Any]:
        results = {}
        for fname in files:
            path = _BASE / fname
            if not path.exists():
                results[fname] = {"ok": False, "error": "file not found"}
                continue
            try:
                src = path.read_text(encoding="utf-8", errors="replace")
                ast.parse(src)
                results[fname] = {"ok": True}
            except SyntaxError as exc:
                results[fname] = {
                    "ok": False,
                    "error": f"SyntaxError line {exc.lineno}: {exc.msg}",
                }
        return results

    def deploy(self, files: List[str],
               message: str = "feat: RabbitOS auto-deploy",
               force: bool = False) -> DeployRecord:
        deploy_id = hashlib.sha256(
            f"{''.join(files)}{time.time()}".encode()).hexdigest()[:12]

        # Validate syntax first
        validation = self.validate_syntax(files)
        bad = [f for f, r in validation.items() if not r["ok"]]
        if bad and not force:
            rec = DeployRecord(
                deploy_id=deploy_id, files=files,
                commit_sha="", status="failed",
                message=f"Syntax errors in: {bad}")
            self._save_record(rec)
            return rec

        if not self._token:
            rec = DeployRecord(
                deploy_id=deploy_id, files=files,
                commit_sha="", status="failed",
                message="No GitHub token available")
            self._save_record(rec)
            return rec

        # Get HEAD
        ref = self._gh("GET",
                       f"repos/{self.REPO}/git/ref/heads/{self.BRANCH}")
        if "error" in ref:
            rec = DeployRecord(
                deploy_id=deploy_id, files=files,
                commit_sha="", status="failed",
                message=f"Get ref failed: {ref}")
            self._save_record(rec)
            return rec

        head_sha = ref["object"]["sha"]
        tree_items = []

        for fname in files:
            path = _BASE / fname
            if not path.exists():
                continue
            content = path.read_bytes()
            blob = self._gh("POST",
                            f"repos/{self.REPO}/git/blobs", {
                                "content":  base64.b64encode(content).decode(),
                                "encoding": "base64",
                            })
            if "error" in blob:
                rec = DeployRecord(
                    deploy_id=deploy_id, files=files,
                    commit_sha="", status="failed",
                    message=f"Blob failed for {fname}: {blob}")
                self._save_record(rec)
                return rec
            tree_items.append({
                "path": fname, "mode": "100644",
                "type": "blob", "sha": blob["sha"],
            })

        tree = self._gh("POST", f"repos/{self.REPO}/git/trees", {
            "base_tree": head_sha, "tree": tree_items})
        if "error" in tree:
            rec = DeployRecord(
                deploy_id=deploy_id, files=files,
                commit_sha="", status="failed",
                message=f"Tree failed: {tree}")
            self._save_record(rec)
            return rec

        commit = self._gh("POST", f"repos/{self.REPO}/git/commits", {
            "message": message, "tree": tree["sha"], "parents": [head_sha]})
        if "error" in commit:
            rec = DeployRecord(
                deploy_id=deploy_id, files=files,
                commit_sha="", status="failed",
                message=f"Commit failed: {commit}")
            self._save_record(rec)
            return rec

        result = self._gh(
            "PATCH",
            f"repos/{self.REPO}/git/refs/heads/{self.BRANCH}",
            {"sha": commit["sha"], "force": False})

        if "error" in result:
            rec = DeployRecord(
                deploy_id=deploy_id, files=files,
                commit_sha=commit.get("sha", ""),
                status="failed",
                message=f"Ref update failed: {result}")
        else:
            rec = DeployRecord(
                deploy_id=deploy_id, files=files,
                commit_sha=commit["sha"],
                status="ok",
                message=f"Pushed {len(tree_items)} files at {commit['sha'][:12]}")

        self._save_record(rec)
        _log(f"[Deploy] {rec.status} commit={rec.commit_sha[:12] if rec.commit_sha else 'none'} "
             f"files={files}")
        return rec

    def _save_record(self, rec: DeployRecord) -> None:
        with self._lock:
            self._history.append(rec)
        try:
            conn = sqlite3.connect(str(_WD_DB), timeout=10)
            conn.execute(
                "INSERT OR REPLACE INTO deploy_history VALUES (?,?,?,?,?,?)",
                (rec.deploy_id, json.dumps(rec.files),
                 rec.commit_sha, rec.status, rec.message, rec.ts))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def deploy_status(self, limit: int = 20) -> List[Dict]:
        try:
            conn = sqlite3.connect(str(_WD_DB), timeout=5)
            rows = conn.execute(
                "SELECT * FROM deploy_history ORDER BY ts DESC LIMIT ?",
                (limit,)).fetchall()
            conn.close()
            return [{"deploy_id": r[0], "files": json.loads(r[1]),
                     "commit_sha": r[2], "status": r[3],
                     "message": r[4], "ts": r[5]}
                    for r in rows]
        except Exception:
            with self._lock:
                return [asdict(r) for r in self._history[-limit:]]

    def redeploy_failed(self) -> List[DeployRecord]:
        """Re-attempt any recent failed deployments."""
        results = []
        history = self.deploy_status(limit=10)
        seen = set()
        for rec in history:
            if rec["status"] == "failed":
                key = tuple(rec["files"])
                if key not in seen:
                    seen.add(key)
                    new_rec = self.deploy(
                        rec["files"],
                        message="fix: watchdog redeploy after failure")
                    results.append(new_rec)
        return results

    def deploy_all_modules(self) -> DeployRecord:
        """Deploy all rabbit_*.py files."""
        files = [f.name for f in _BASE.glob("rabbit_*.py")]
        return self.deploy(
            files,
            message="feat: watchdog full-system deploy of all rabbit_* modules")


# ══════════════════════════════════════════════════════════════════════════════
# PART 6 — AI DIAGNOSTICS
# ══════════════════════════════════════════════════════════════════════════════

class AIDiagnostics:
    """
    Uses the local LLM to diagnose failures and suggest repairs.
    Falls back gracefully if no LLM is available.
    """

    def diagnose(self, checks: Dict[str, HealthCheck]) -> str:
        llm = _get_llm()
        failed = {k: {"status": v.status, "msg": v.message}
                  for k, v in checks.items() if v.status in ("fail", "warn")}
        if not failed:
            return "All systems healthy — no diagnosis needed."
        if llm is None:
            lines = [f"FAILED COMPONENTS ({len(failed)}):"]
            for comp, info in failed.items():
                lines.append(f"  [{info['status'].upper()}] {comp}: {info['msg']}")
            return "\n".join(lines)
        prompt = (
            "You are the RabbitOS system health AI. "
            "Analyze these failed/warning components and give:\n"
            "(1) Root cause for each failure\n"
            "(2) Recommended repair steps\n"
            "(3) Priority order (most critical first)\n"
            "(4) Estimated recovery time\n\n"
            f"Failed components:\n{json.dumps(failed, indent=2)}"
        )
        try:
            return llm.simple_ask(prompt)
        except Exception as exc:
            return f"[AI diagnosis error: {exc}]"

    def suggest_repair(self, component: str,
                       health: HealthCheck) -> str:
        llm = _get_llm()
        if llm is None:
            return f"LLM unavailable. Status: {health.status} — {health.message}"
        prompt = (
            f"Component '{component}' has status '{health.status}': {health.message}\n"
            f"Detail: {json.dumps(health.detail, default=str)[:500]}\n\n"
            "Give a concise repair plan (max 5 steps) for this RabbitOS component. "
            "Be specific to the error message."
        )
        try:
            return llm.simple_ask(prompt)
        except Exception as exc:
            return f"[AI error: {exc}]"

    def generate_health_report(self,
                                checks: Dict[str, HealthCheck],
                                actions: List[RepairAction],
                                score: float) -> str:
        llm = _get_llm()
        summary = {
            "health_score": score,
            "ok":    sum(1 for c in checks.values() if c.status == "ok"),
            "warn":  sum(1 for c in checks.values() if c.status == "warn"),
            "fail":  sum(1 for c in checks.values() if c.status == "fail"),
            "repairs_attempted": len(actions),
            "repairs_succeeded": sum(1 for a in actions if a.outcome == "success"),
            "failed_components": [
                {"name": k, "msg": v.message}
                for k, v in checks.items() if v.status == "fail"
            ][:10],
        }
        if llm is None:
            return (
                f"=== RabbitOS Health Report ===\n"
                f"Score: {score*100:.0f}/100\n"
                f"OK: {summary['ok']}  Warn: {summary['warn']}  Fail: {summary['fail']}\n"
                f"Repairs: {summary['repairs_succeeded']}/{summary['repairs_attempted']} succeeded\n"
                + (f"Issues: {json.dumps(summary['failed_components'], indent=2)}"
                   if summary['failed_components'] else "No failures.")
            )
        prompt = (
            "Generate a concise RabbitOS System Health Report for Chase Allen Ringquist.\n"
            f"System data:\n{json.dumps(summary, indent=2)}\n\n"
            "Include: (1) Overall health status, (2) Critical issues, "
            "(3) What repairs were done, (4) What still needs attention, "
            "(5) Next recommended action."
        )
        try:
            return llm.simple_ask(prompt)
        except Exception as exc:
            return f"[Report error: {exc}]"


# ══════════════════════════════════════════════════════════════════════════════
# PART 7 — WATCHDOG ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class WatchdogOrchestrator:
    """
    Main agent: monitor → detect → repair → deploy → report.
    Runs as background guardian. Can be triggered manually via tools.
    Integrates with CloudTrail and Supabase.
    """

    _instance: Optional["WatchdogOrchestrator"] = None
    _cls_lock  = threading.Lock()

    def __new__(cls) -> "WatchdogOrchestrator":
        with cls._cls_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self.monitor    = SystemHealthMonitor()
        self.detector   = CrashDetector()
        self.repair     = AutoRepairEngine()
        self.deployer   = DeploymentManager()
        self.ai         = AIDiagnostics()

        self._last_checks:  Dict[str, HealthCheck] = {}
        self._last_score:   float = 0.0
        self._last_actions: List[RepairAction] = []
        self._cycle:        int = 0
        self._running:      bool = False
        self._lock          = threading.Lock()
        self._init_db()
        _log("WatchdogOrchestrator initialized")

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(str(_WD_DB), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchdog_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, cycle INTEGER, score REAL,
                    ok_count INTEGER, warn_count INTEGER, fail_count INTEGER,
                    repairs INTEGER, detail TEXT
                )""")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _log_cycle(self, checks: Dict[str, HealthCheck],
                   score: float, repairs: int) -> None:
        try:
            conn = sqlite3.connect(str(_WD_DB), timeout=10)
            ok   = sum(1 for c in checks.values() if c.status == "ok")
            warn = sum(1 for c in checks.values() if c.status == "warn")
            fail = sum(1 for c in checks.values() if c.status == "fail")
            conn.execute(
                "INSERT INTO watchdog_log VALUES (NULL,?,?,?,?,?,?,?,?)",
                (time.time(), self._cycle, score, ok, warn, fail, repairs,
                 json.dumps({k: v.status for k, v in checks.items()})[:2000]))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def run_cycle(self, token: str = "",
                  supabase_url: str = "",
                  service_key: str = "",
                  auto_repair: bool = True,
                  auto_deploy: bool = False) -> Dict[str, Any]:
        """Run one full monitor → detect → repair → report cycle."""
        self._cycle += 1
        t0 = time.time()

        _log(f"[Watchdog] Cycle {self._cycle} starting ...")

        # 1. Health checks
        checks = self.monitor.full_check(token, supabase_url, service_key)
        score  = self.monitor.health_score(checks)

        # 2. Crash detection
        crashes = self.detector.full_crash_report()

        # 3. Auto repair
        actions: List[RepairAction] = []
        if auto_repair:
            actions = self.repair.repair_all(checks)
            # Re-check anything that was repaired
            for action in actions:
                if action.outcome == "success":
                    comp = action.component
                    if comp in RABBIT_MODULES:
                        checks[comp] = self.monitor.check_module(comp)
                    elif comp in RABBIT_DBS or comp.endswith(".db"):
                        checks[comp] = self.monitor.check_database(comp)

        # Recalculate score after repairs
        score = self.monitor.health_score(checks)

        # 4. AI diagnosis for remaining failures
        failed = {k: v for k, v in checks.items()
                  if v.status in ("fail", "warn")}
        diagnosis = self.ai.diagnose(failed) if failed else "All systems healthy."

        # 5. Auto-deploy if requested and system is healthy enough
        deploy_rec: Optional[DeployRecord] = None
        if auto_deploy and score >= 0.8:
            all_files = [f.name for f in _BASE.glob("rabbit_*.py")]
            deploy_rec = self.deployer.deploy(
                all_files,
                message=f"feat: watchdog cycle {self._cycle} auto-deploy score={score:.2f}")

        # 6. Persist
        self._log_cycle(checks, score, len(actions))
        with self._lock:
            self._last_checks  = checks
            self._last_score   = score
            self._last_actions = actions

        elapsed = round(time.time() - t0, 2)
        _log(f"[Watchdog] Cycle {self._cycle} done  "
             f"score={score:.2f}  fail={sum(1 for v in checks.values() if v.status=='fail')}  "
             f"repairs={len(actions)}  elapsed={elapsed}s")

        return {
            "cycle":       self._cycle,
            "score":       score,
            "ok":          sum(1 for v in checks.values() if v.status == "ok"),
            "warn":        sum(1 for v in checks.values() if v.status == "warn"),
            "fail":        sum(1 for v in checks.values() if v.status == "fail"),
            "checks":      {k: {"status": v.status, "msg": v.message,
                                "score": v.score}
                            for k, v in checks.items()},
            "repairs":     [asdict(a) for a in actions],
            "diagnosis":   diagnosis,
            "crashes":     crashes,
            "deploy":      asdict(deploy_rec) if deploy_rec else None,
            "elapsed_s":   elapsed,
            "ts":          time.time(),
        }

    def start_background(self, interval: float = 300.0,
                         token: str = "",
                         supabase_url: str = "",
                         service_key: str = "",
                         auto_repair: bool = True) -> None:
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                try:
                    self.run_cycle(
                        token=token,
                        supabase_url=supabase_url,
                        service_key=service_key,
                        auto_repair=auto_repair,
                    )
                except Exception as exc:
                    _log(f"[Watchdog] Loop error: {exc}")
                time.sleep(interval)

        threading.Thread(target=_loop, daemon=True,
                         name="watchdog_guardian").start()
        _log(f"[Watchdog] Background guardian started (interval={interval}s)")

    def stop(self) -> None:
        self._running = False

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "cycle":        self._cycle,
                "running":      self._running,
                "last_score":   self._last_score,
                "last_checks":  {k: v.status
                                 for k, v in self._last_checks.items()},
                "last_repairs": len(self._last_actions),
                "deploy_history": self.deployer.deploy_status(limit=5),
                "shows_dna_root": False,
                "ts":            time.time(),
            }

    def quick_health(self) -> Dict[str, Any]:
        with self._lock:
            if not self._last_checks:
                return {"status": "not_run_yet", "run": "watchdog_run_cycle first"}
            fail = [k for k, v in self._last_checks.items()
                    if v.status == "fail"]
            warn = [k for k, v in self._last_checks.items()
                    if v.status == "warn"]
            overall = ("ok" if not fail and not warn
                       else "warn" if not fail else "degraded")
            return {
                "overall":   overall,
                "score":     self._last_score,
                "fail":      fail,
                "warn":      warn,
                "cycle":     self._cycle,
            }


def get_watchdog() -> WatchdogOrchestrator:
    return WatchdogOrchestrator()


# ══════════════════════════════════════════════════════════════════════════════
# PART 8 — RESILIENCE ENGINE (error approval + removed-item recovery)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ErrorRecord:
    error_id:   str
    component:  str
    error_type: str
    message:    str
    context:    str
    approved:   bool  = False
    note:       str   = ""
    ts:         float = field(default_factory=time.time)

@dataclass
class RemovedItem:
    item_id:     str
    component:   str
    reason:      str          # blocked / import-error / syntax / github-rejected / manual
    code_hash:   str          # SHA-256 of what was removed
    alternative: str          # suggested replacement approach
    recovered:   bool  = False
    recovery_note: str = ""
    ts:          float = field(default_factory=time.time)


class ResilienceEngine:
    """
    Tracks errors and removed/blocked components.
    Provides an algorithm to recover them via alternative strategies.
    """

    def __init__(self) -> None:
        self._lock   = threading.Lock()
        self._errors: List[ErrorRecord] = []
        self._removed: List[RemovedItem] = []
        self._init_db()

    def _init_db(self) -> None:
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=10)
            con.execute("""CREATE TABLE IF NOT EXISTS resilience_errors (
                error_id TEXT PRIMARY KEY, component TEXT, error_type TEXT,
                message TEXT, context TEXT, approved INTEGER, note TEXT, ts REAL)""")
            con.execute("""CREATE TABLE IF NOT EXISTS resilience_removed (
                item_id TEXT PRIMARY KEY, component TEXT, reason TEXT,
                code_hash TEXT, alternative TEXT,
                recovered INTEGER, recovery_note TEXT, ts REAL)""")
            con.commit(); con.close()
        except Exception:
            pass

    def _uid(self) -> str:
        import uuid; return str(uuid.uuid4())[:16]

    # ── Error tracking ───────────────────────────────────────────────────────

    def log_error(self, component: str, error: Exception,
                  context: str = "") -> ErrorRecord:
        rec = ErrorRecord(
            error_id=self._uid(), component=component,
            error_type=type(error).__name__,
            message=str(error)[:500], context=context[:300])
        with self._lock:
            self._errors.append(rec)
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=5)
            con.execute(
                "INSERT OR REPLACE INTO resilience_errors VALUES (?,?,?,?,?,?,?,?)",
                (rec.error_id, rec.component, rec.error_type,
                 rec.message, rec.context, 0, "", rec.ts))
            con.commit(); con.close()
        except Exception:
            pass
        _log(f"[Resilience] Error logged: {component} — {rec.error_type}: {rec.message[:80]}")
        return rec

    def approve_error(self, error_id: str, note: str = "") -> bool:
        """Mark an error as reviewed/approved so it doesn't block the system."""
        with self._lock:
            for e in self._errors:
                if e.error_id == error_id:
                    e.approved = True; e.note = note
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=5)
            con.execute(
                "UPDATE resilience_errors SET approved=1, note=? WHERE error_id=?",
                (note, error_id))
            con.commit(); con.close()
            return True
        except Exception:
            return False

    def approve_all_errors(self, component: str = "") -> int:
        """Approve all errors (optionally for a specific component)."""
        count = 0
        with self._lock:
            for e in self._errors:
                if not e.approved and (not component or e.component == component):
                    e.approved = True; count += 1
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=5)
            if component:
                con.execute(
                    "UPDATE resilience_errors SET approved=1 WHERE component=?",
                    (component,))
            else:
                con.execute("UPDATE resilience_errors SET approved=1")
            con.commit(); con.close()
        except Exception:
            pass
        return count

    def get_errors(self, include_approved: bool = False,
                   limit: int = 100) -> List[Dict]:
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=5)
            if include_approved:
                rows = con.execute(
                    "SELECT * FROM resilience_errors ORDER BY ts DESC LIMIT ?",
                    (limit,)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM resilience_errors WHERE approved=0 ORDER BY ts DESC LIMIT ?",
                    (limit,)).fetchall()
            con.close()
            return [{"error_id": r[0], "component": r[1], "error_type": r[2],
                     "message": r[3], "context": r[4],
                     "approved": bool(r[5]), "note": r[6]} for r in rows]
        except Exception:
            with self._lock:
                return [asdict(e) for e in self._errors[-limit:]]

    # ── Removed-item tracking + recovery algorithm ───────────────────────────

    def log_removed(self, component: str, reason: str,
                    code_snippet: str = "", alternative: str = "") -> RemovedItem:
        item = RemovedItem(
            item_id=self._uid(), component=component, reason=reason,
            code_hash=hashlib.sha256(code_snippet.encode()).hexdigest()[:16],
            alternative=alternative or self._suggest_alternative(component, reason))
        with self._lock:
            self._removed.append(item)
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=5)
            con.execute(
                "INSERT OR REPLACE INTO resilience_removed VALUES (?,?,?,?,?,?,?,?)",
                (item.item_id, item.component, item.reason, item.code_hash,
                 item.alternative, 0, "", item.ts))
            con.commit(); con.close()
        except Exception:
            pass
        _log(f"[Resilience] Removed item logged: {component} — reason={reason}")
        return item

    def _suggest_alternative(self, component: str, reason: str) -> str:
        """Heuristic alternatives for common removal reasons."""
        if "token" in reason.lower() or "secret" in reason.lower():
            return "Move token to env var; read with os.environ.get()"
        if "import" in reason.lower():
            return "Add try/except ImportError with fallback stub"
        if "syntax" in reason.lower():
            return "Run ast.parse() to verify before committing"
        if "github" in reason.lower() or "push" in reason.lower():
            return "Use Git Trees API blob→tree→commit→PATCH pattern"
        if "blocked" in reason.lower():
            return "Wrap in try/except; store result or stub in SQLite"
        return "Refactor with defensive try/except and fallback value"

    def get_removed(self, recovered: bool = None,
                    limit: int = 100) -> List[Dict]:
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=5)
            if recovered is None:
                rows = con.execute(
                    "SELECT * FROM resilience_removed ORDER BY ts DESC LIMIT ?",
                    (limit,)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM resilience_removed WHERE recovered=? ORDER BY ts DESC LIMIT ?",
                    (int(recovered), limit)).fetchall()
            con.close()
            return [{"item_id": r[0], "component": r[1], "reason": r[2],
                     "code_hash": r[3], "alternative": r[4],
                     "recovered": bool(r[5]), "recovery_note": r[6]} for r in rows]
        except Exception:
            with self._lock:
                items = self._removed[-limit:]
            return [asdict(i) for i in items]

    def attempt_recovery(self, item_id: str) -> Dict:
        """
        Recovery algorithm for a single removed item.
        Tries: re-import → pyc clear → LLM fix → stub injection.
        """
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=5)
            row = con.execute(
                "SELECT * FROM resilience_removed WHERE item_id=?",
                (item_id,)).fetchone()
            con.close()
        except Exception:
            row = None

        if not row:
            return {"error": f"item_id {item_id} not found"}

        component  = row[1]
        reason     = row[2]
        alternative = row[4]
        steps_tried = []

        # Step 1 — try reimport
        try:
            importlib.import_module(component)
            steps_tried.append("reimport: success")
            self._mark_recovered(item_id, "reimport succeeded")
            return {"item_id": item_id, "component": component,
                    "recovered": True, "steps": steps_tried}
        except Exception as e:
            steps_tried.append(f"reimport: failed ({e!s:.60})")

        # Step 2 — clear __pycache__ and retry
        cache_dir = _BASE / "__pycache__"
        cleared = 0
        if cache_dir.exists():
            for pyc in cache_dir.glob(f"{component}*.pyc"):
                try: pyc.unlink(); cleared += 1
                except Exception: pass
        if cleared:
            try:
                importlib.import_module(component)
                steps_tried.append(f"pyc_clear+reimport: success (cleared {cleared})")
                self._mark_recovered(item_id, "pyc clear + reimport succeeded")
                return {"item_id": item_id, "component": component,
                        "recovered": True, "steps": steps_tried}
            except Exception as e:
                steps_tried.append(f"pyc_clear+reimport: failed ({e!s:.60})")

        # Step 3 — LLM syntax fix if source exists
        py_path = _BASE / f"{component}.py"
        if py_path.exists():
            try:
                src = py_path.read_text(encoding="utf-8", errors="replace")
                try:
                    ast.parse(src)
                    steps_tried.append("ast_parse: ok — no syntax error")
                except SyntaxError as se:
                    steps_tried.append(f"ast_parse: SyntaxError at line {se.lineno}")
                    llm = _get_llm()
                    if llm:
                        fix = llm.simple_ask(
                            f"Fix this Python syntax error in {component}.py:\n"
                            f"Error: {se}\nCode (first 2000 chars):\n{src[:2000]}\n"
                            "Return ONLY corrected Python code.")
                        if fix and "def " in fix:
                            try:
                                ast.parse(fix)
                                bak = py_path.with_suffix(".py.resilience_bak")
                                shutil.copy2(str(py_path), str(bak))
                                py_path.write_text(fix, encoding="utf-8")
                                steps_tried.append("llm_fix: applied")
                                importlib.import_module(component)
                                self._mark_recovered(item_id, "LLM syntax fix applied")
                                return {"item_id": item_id, "component": component,
                                        "recovered": True, "steps": steps_tried}
                            except Exception as e2:
                                steps_tried.append(f"llm_fix: failed ({e2!s:.60})")
                        else:
                            steps_tried.append("llm_fix: LLM produced no valid code")
                    else:
                        steps_tried.append("llm_fix: LLM unavailable")
            except Exception as e:
                steps_tried.append(f"source_check: error ({e!s:.60})")

        # Step 4 — record alternative and mark partial
        steps_tried.append(f"alternative_recorded: {alternative}")
        self._mark_recovered(item_id, f"partial — manual action needed: {alternative}",
                             partial=True)
        return {"item_id": item_id, "component": component,
                "recovered": False, "steps": steps_tried,
                "next_action": alternative}

    def _mark_recovered(self, item_id: str, note: str,
                        partial: bool = False) -> None:
        recovered_flag = 0 if partial else 1
        with self._lock:
            for r in self._removed:
                if r.item_id == item_id:
                    r.recovered = not partial
                    r.recovery_note = note
        try:
            con = sqlite3.connect(str(_WD_DB), timeout=5)
            con.execute(
                "UPDATE resilience_removed SET recovered=?, recovery_note=? WHERE item_id=?",
                (recovered_flag, note, item_id))
            con.commit(); con.close()
        except Exception:
            pass

    def recovery_algorithm(self, auto_approve: bool = False) -> Dict:
        """
        Full recovery pass over all unrecovered removed items.
        Also approves all errors if auto_approve=True.
        """
        results: Dict[str, Any] = {
            "approved_errors": 0,
            "recovery_attempts": [],
            "recovered": 0,
            "partial": 0,
            "failed": 0,
        }
        if auto_approve:
            results["approved_errors"] = self.approve_all_errors()

        removed = self.get_removed(recovered=False, limit=50)
        for item in removed:
            rec = self.attempt_recovery(item["item_id"])
            results["recovery_attempts"].append({
                "component": item["component"],
                "recovered": rec.get("recovered", False),
                "steps":     rec.get("steps", []),
            })
            if rec.get("recovered"):
                results["recovered"] += 1
            elif rec.get("next_action"):
                results["partial"] += 1
            else:
                results["failed"] += 1

        results["summary"] = (
            f"Approved {results['approved_errors']} errors. "
            f"Recovery: {results['recovered']} ok, "
            f"{results['partial']} partial, "
            f"{results['failed']} failed of {len(removed)} items.")
        return results

    def safe_dispatch(self, name: str, fn: Callable, *args, **kwargs) -> Any:
        """Wraps a tool dispatch call; catches errors and logs them so the system keeps running."""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            self.log_error(name, e, context=f"dispatch args={args!s:.100}")
            return {"error": str(e), "component": name,
                    "status": "error_logged", "system_continues": True}

    def summary(self) -> Dict:
        errors   = self.get_errors(include_approved=True, limit=500)
        removed  = self.get_removed(limit=500)
        return {
            "total_errors":    len(errors),
            "unapproved":      sum(1 for e in errors if not e["approved"]),
            "total_removed":   len(removed),
            "unrecovered":     sum(1 for r in removed if not r["recovered"]),
            "recovered":       sum(1 for r in removed if r["recovered"]),
        }


_resilience: Optional[ResilienceEngine] = None
def get_resilience() -> ResilienceEngine:
    global _resilience
    if _resilience is None:
        _resilience = ResilienceEngine()
    return _resilience


# ══════════════════════════════════════════════════════════════════════════════
# WATCHDOG TOOLS + DISPATCHER
# ══════════════════════════════════════════════════════════════════════════════

WATCHDOG_TOOLS = [
    {
        "name": "watchdog_status",
        "description": "Get watchdog agent status: last score, cycle, pass/fail counts, recent deploys.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_quick_health",
        "description": "Fast health snapshot from last cycle: overall status, score, failing/warning components.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_run_cycle",
        "description": (
            "Run a full monitor-detect-repair cycle on all RabbitOS modules, "
            "databases, network, CPU/RAM/disk. Returns health score, "
            "all component statuses, repair actions taken, and AI diagnosis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "auto_repair": {"type": "boolean",
                                "description": "Attempt auto-repair of failures (default true)"},
                "auto_deploy": {"type": "boolean",
                                "description": "Auto-deploy if score >= 0.8 (default false)"},
            },
            "required": [],
        },
    },
    {
        "name": "watchdog_check_module",
        "description": "Check syntax + import health of a specific rabbit_* module.",
        "input_schema": {
            "type": "object",
            "properties": {
                "module_name": {"type": "string",
                                "description": "e.g. rabbit_defense"},
            },
            "required": ["module_name"],
        },
    },
    {
        "name": "watchdog_repair_module",
        "description": "Attempt auto-repair of a failing rabbit_* module (clears cache, LLM syntax fix).",
        "input_schema": {
            "type": "object",
            "properties": {
                "module_name": {"type": "string"},
            },
            "required": ["module_name"],
        },
    },
    {
        "name": "watchdog_check_all_modules",
        "description": "Check all rabbit_* modules for syntax errors and import failures.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_check_databases",
        "description": "Run SQLite integrity checks on all RabbitOS databases.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_repair_database",
        "description": "Repair a specific SQLite database (WAL checkpoint, vacuum, or delete+recreate if corrupt).",
        "input_schema": {
            "type": "object",
            "properties": {"db_name": {"type": "string",
                                       "description": "e.g. rabbit_trail.db"}},
            "required": ["db_name"],
        },
    },
    {
        "name": "watchdog_check_network",
        "description": "Check network health: gateway ping, DNS, HTTPS, Supabase, GitHub API.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_repair_network",
        "description": "Attempt network repair: flush DNS, reset IP stack (Windows netsh), restart NetworkManager.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_check_resources",
        "description": "Check CPU, RAM, and disk usage with thresholds.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_cleanup_disk",
        "description": "Free disk space: clear __pycache__, temp files, WAL checkpoint all DBs.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_crash_report",
        "description": "Scan log files and Windows Event Log for crash/error events.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_ai_diagnose",
        "description": "Use the local LLM to diagnose all current failures and suggest root causes.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_ai_repair_suggest",
        "description": "Get AI-suggested repair steps for a specific failing component.",
        "input_schema": {
            "type": "object",
            "properties": {
                "component": {"type": "string",
                              "description": "Component name (e.g. rabbit_defense, network)"},
            },
            "required": ["component"],
        },
    },
    {
        "name": "watchdog_health_report",
        "description": "Generate a full AI health report: score, issues, repairs done, next steps.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_deploy",
        "description": "Deploy specific files to GitHub (validates syntax first).",
        "input_schema": {
            "type": "object",
            "properties": {
                "files":   {"type": "array", "items": {"type": "string"},
                            "description": "List of filenames, e.g. ['rabbit_defense.py']"},
                "message": {"type": "string",
                            "description": "Commit message"},
            },
            "required": ["files"],
        },
    },
    {
        "name": "watchdog_deploy_all",
        "description": "Deploy ALL rabbit_*.py modules to GitHub in one commit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "watchdog_deploy_status",
        "description": "Get deployment history: commit SHAs, status, files, timestamps.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "watchdog_redeploy_failed",
        "description": "Re-attempt any recently failed deployments.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_validate_syntax",
        "description": "Validate Python syntax of one or more files without deploying.",
        "input_schema": {
            "type": "object",
            "properties": {
                "files": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["files"],
        },
    },
    {
        "name": "watchdog_start_monitor",
        "description": "Start the background watchdog guardian (runs every N seconds).",
        "input_schema": {
            "type": "object",
            "properties": {
                "interval_seconds": {"type": "integer",
                                     "description": "Check interval (default 300s)"},
                "auto_repair":      {"type": "boolean"},
            },
            "required": [],
        },
    },
    {
        "name": "watchdog_stop_monitor",
        "description": "Stop the background watchdog guardian.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_repair_all",
        "description": "Run auto-repair on all currently failing components at once.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_get_repair_log",
        "description": "Get the log of all repair actions taken this session.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    # ── Resilience engine tools ───────────────────────────────────────────────
    {
        "name": "watchdog_resilience_summary",
        "description": "Summary of all logged errors and removed/blocked items.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "watchdog_resilience_errors",
        "description": "List errors logged by the resilience engine (unapproved by default).",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_approved": {"type": "boolean"},
                "limit":            {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "watchdog_resilience_approve",
        "description": "Approve an error (or all errors for a component) so it no longer blocks the system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "error_id":  {"type": "string", "description": "Specific error ID to approve"},
                "component": {"type": "string", "description": "Approve ALL errors for this component"},
                "note":      {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "watchdog_resilience_log_removed",
        "description": "Record a removed or blocked component so the recovery algorithm can track and re-implement it.",
        "input_schema": {
            "type": "object",
            "required": ["component", "reason"],
            "properties": {
                "component":   {"type": "string"},
                "reason":      {"type": "string"},
                "code_snippet":{"type": "string"},
                "alternative": {"type": "string"},
            },
        },
    },
    {
        "name": "watchdog_resilience_recover",
        "description": "Run the recovery algorithm on all unrecovered removed items (reimport → pyc clear → LLM fix → alternative).",
        "input_schema": {
            "type": "object",
            "properties": {
                "auto_approve": {"type": "boolean",
                                 "description": "Also approve all pending errors (default true)"},
            },
            "required": [],
        },
    },
]


def dispatch_watchdog_tool(name: str, inputs: Dict,
                            token: str = "",
                            supabase_url: str = "",
                            service_key: str = "") -> Any:
    wd = get_watchdog()

    if name == "watchdog_status":
        return wd.status()

    elif name == "watchdog_quick_health":
        return wd.quick_health()

    elif name == "watchdog_run_cycle":
        return wd.run_cycle(
            token=token,
            supabase_url=supabase_url,
            service_key=service_key,
            auto_repair=inputs.get("auto_repair", True),
            auto_deploy=inputs.get("auto_deploy", False))

    elif name == "watchdog_check_module":
        hc = wd.monitor.check_module(inputs["module_name"])
        return asdict(hc)

    elif name == "watchdog_repair_module":
        mod  = inputs["module_name"]
        hc   = wd.monitor.check_module(mod)
        action = wd.repair.repair_module(mod, hc)
        return asdict(action)

    elif name == "watchdog_check_all_modules":
        results = {}
        for m in RABBIT_MODULES:
            hc = wd.monitor.check_module(m)
            results[m] = {"status": hc.status, "message": hc.message,
                          "score": hc.score}
        return results

    elif name == "watchdog_check_databases":
        results = {}
        for db in RABBIT_DBS:
            hc = wd.monitor.check_database(db)
            results[db] = {"status": hc.status, "message": hc.message}
        return results

    elif name == "watchdog_repair_database":
        db = inputs["db_name"]
        hc = wd.monitor.check_database(db)
        action = wd.repair.repair_database(db, hc)
        return asdict(action)

    elif name == "watchdog_check_network":
        hc     = wd.monitor.check_network()
        sup_hc = wd.monitor.check_supabase(supabase_url, service_key)
        gh_hc  = wd.monitor.check_github_api(token)
        return {
            "network":    asdict(hc),
            "supabase":   asdict(sup_hc),
            "github_api": asdict(gh_hc),
        }

    elif name == "watchdog_repair_network":
        hc = wd.monitor.check_network()
        action = wd.repair.repair_network(hc)
        return asdict(action)

    elif name == "watchdog_check_resources":
        return {
            "cpu":    asdict(wd.monitor.check_cpu()),
            "memory": asdict(wd.monitor.check_memory()),
            "disk":   asdict(wd.monitor.check_disk()),
        }

    elif name == "watchdog_cleanup_disk":
        hc = wd.monitor.check_disk()
        hc.score = 0.0   # force repair
        action = wd.repair.repair_disk(hc)
        return asdict(action)

    elif name == "watchdog_crash_report":
        return wd.detector.full_crash_report()

    elif name == "watchdog_ai_diagnose":
        with wd._lock:
            checks = dict(wd._last_checks)
        if not checks:
            checks = wd.monitor.full_check(token, supabase_url, service_key)
        diagnosis = wd.ai.diagnose(checks)
        return {"diagnosis": diagnosis}

    elif name == "watchdog_ai_repair_suggest":
        comp = inputs["component"]
        with wd._lock:
            hc = wd._last_checks.get(comp)
        if hc is None:
            if comp in RABBIT_MODULES:
                hc = wd.monitor.check_module(comp)
            elif comp in RABBIT_DBS or comp.endswith(".db"):
                hc = wd.monitor.check_database(comp)
            else:
                return {"error": f"Component '{comp}' not found in last checks"}
        suggestion = wd.ai.suggest_repair(comp, hc)
        return {"component": comp, "status": hc.status, "suggestion": suggestion}

    elif name == "watchdog_health_report":
        with wd._lock:
            checks  = dict(wd._last_checks)
            actions = list(wd._last_actions)
            score   = wd._last_score
        if not checks:
            cycle_result = wd.run_cycle(
                token=token, supabase_url=supabase_url,
                service_key=service_key)
            with wd._lock:
                checks  = dict(wd._last_checks)
                actions = list(wd._last_actions)
                score   = wd._last_score
        report = wd.ai.generate_health_report(checks, actions, score)
        return {"report": report, "score": score}

    elif name == "watchdog_deploy":
        rec = wd.deployer.deploy(
            inputs["files"],
            message=inputs.get("message", "feat: watchdog manual deploy"))
        return asdict(rec)

    elif name == "watchdog_deploy_all":
        msg = inputs.get("message",
                         "feat: watchdog full system deploy")
        rec = wd.deployer.deploy_all_modules()
        return asdict(rec)

    elif name == "watchdog_deploy_status":
        return wd.deployer.deploy_status(inputs.get("limit", 20))

    elif name == "watchdog_redeploy_failed":
        recs = wd.deployer.redeploy_failed()
        return [asdict(r) for r in recs]

    elif name == "watchdog_validate_syntax":
        return wd.deployer.validate_syntax(inputs["files"])

    elif name == "watchdog_start_monitor":
        wd.start_background(
            interval=inputs.get("interval_seconds", 300),
            token=token,
            supabase_url=supabase_url,
            service_key=service_key,
            auto_repair=inputs.get("auto_repair", True))
        return {"started": True, "interval": inputs.get("interval_seconds", 300)}

    elif name == "watchdog_stop_monitor":
        wd.stop()
        return {"stopped": True}

    elif name == "watchdog_repair_all":
        with wd._lock:
            checks = dict(wd._last_checks)
        if not checks:
            checks = wd.monitor.full_check(token, supabase_url, service_key)
        actions = wd.repair.repair_all(checks)
        return [asdict(a) for a in actions]

    elif name == "watchdog_get_repair_log":
        actions = wd.repair.get_actions()
        limit   = inputs.get("limit", 50)
        return [asdict(a) for a in actions[-limit:]]

    # ── Resilience engine ─────────────────────────────────────────────────────
    elif name == "watchdog_resilience_summary":
        return get_resilience().summary()

    elif name == "watchdog_resilience_errors":
        return get_resilience().get_errors(
            include_approved=inputs.get("include_approved", False),
            limit=inputs.get("limit", 100))

    elif name == "watchdog_resilience_approve":
        r = get_resilience()
        if inputs.get("error_id"):
            ok = r.approve_error(inputs["error_id"], inputs.get("note", ""))
            return {"approved": ok, "error_id": inputs["error_id"]}
        elif inputs.get("component"):
            count = r.approve_all_errors(inputs["component"])
            return {"approved_count": count, "component": inputs["component"]}
        else:
            count = r.approve_all_errors()
            return {"approved_count": count, "scope": "all"}

    elif name == "watchdog_resilience_log_removed":
        item = get_resilience().log_removed(
            inputs["component"], inputs["reason"],
            inputs.get("code_snippet", ""), inputs.get("alternative", ""))
        return asdict(item)

    elif name == "watchdog_resilience_recover":
        return get_resilience().recovery_algorithm(
            auto_approve=inputs.get("auto_approve", True))

    else:
        return {"error": f"Unknown watchdog tool: {name}"}


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse, pprint

    p = argparse.ArgumentParser(description="RabbitOS Watchdog Agent")
    p.add_argument("--status",       action="store_true", help="Show watchdog status")
    p.add_argument("--cycle",        action="store_true", help="Run one full health+repair cycle")
    p.add_argument("--repair",       action="store_true", help="Auto-repair all failures")
    p.add_argument("--deploy",       action="store_true", help="Deploy all rabbit_*.py to GitHub")
    p.add_argument("--deploy-files", nargs="+",           help="Deploy specific files")
    p.add_argument("--deploy-status",action="store_true", help="Show deploy history")
    p.add_argument("--modules",      action="store_true", help="Check all modules")
    p.add_argument("--dbs",          action="store_true", help="Check all databases")
    p.add_argument("--network",      action="store_true", help="Check network health")
    p.add_argument("--resources",    action="store_true", help="Check CPU/RAM/disk")
    p.add_argument("--crashes",      action="store_true", help="Scan for crash events")
    p.add_argument("--report",       action="store_true", help="Full AI health report")
    p.add_argument("--validate",     nargs="+",           help="Validate syntax of files")
    p.add_argument("--daemon",       action="store_true", help="Run as background daemon")
    p.add_argument("--interval",     type=int, default=300)
    args = p.parse_args()

    tok = os.environ.get("GITHUB_TOKEN", "")
    svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    url = os.environ.get("SUPABASE_URL", "")
    wd  = get_watchdog()

    if args.status:
        pprint.pprint(wd.status())
    elif args.cycle:
        result = wd.run_cycle(token=tok, supabase_url=url,
                              service_key=svc, auto_repair=True)
        print(f"\nHealth Score: {result['score']*100:.0f}/100  "
              f"OK={result['ok']}  Warn={result['warn']}  Fail={result['fail']}")
        if result.get("diagnosis"):
            print(f"\nDiagnosis:\n{result['diagnosis']}")
    elif args.repair:
        with wd._lock:
            checks = dict(wd._last_checks)
        if not checks:
            checks = wd.monitor.full_check(tok, url, svc)
        actions = wd.repair.repair_all(checks)
        for a in actions:
            print(f"[{a.outcome.upper()}] {a.component}: {a.action} -> {a.after}")
    elif args.deploy:
        rec = wd.deployer.deploy_all_modules()
        print(f"Deploy {rec.status}: commit={rec.commit_sha[:12] if rec.commit_sha else 'none'}")
        print(f"  {rec.message}")
    elif args.deploy_files:
        rec = wd.deployer.deploy(args.deploy_files)
        print(f"Deploy {rec.status}: {rec.message}")
    elif args.deploy_status:
        for rec in wd.deployer.deploy_status():
            print(f"[{rec['status'].upper()}] {rec['commit_sha'][:12] if rec['commit_sha'] else '------'}  "
                  f"{rec['message'][:60]}")
    elif args.modules:
        for mod in RABBIT_MODULES:
            hc = wd.monitor.check_module(mod)
            sym = "[OK]" if hc.status == "ok" else "[WARN]" if hc.status == "warn" else "[FAIL]"
            print(f"{sym} {mod:30s} {hc.message[:60]}")
    elif args.dbs:
        for db in RABBIT_DBS:
            hc = wd.monitor.check_database(db)
            sym = "[OK]" if hc.status == "ok" else "[FAIL]"
            print(f"{sym} {db:30s} {hc.message[:60]}")
    elif args.network:
        hc = wd.monitor.check_network()
        print(f"Network: {hc.status}  score={hc.score:.2f}  {hc.message}")
    elif args.resources:
        for label, hc in [
            ("CPU",  wd.monitor.check_cpu()),
            ("RAM",  wd.monitor.check_memory()),
            ("Disk", wd.monitor.check_disk()),
        ]:
            sym = "[OK]" if hc.status == "ok" else "[WARN]" if hc.status == "warn" else "[FAIL]"
            print(f"{sym} {label}: {hc.message}")
    elif args.crashes:
        report = wd.detector.full_crash_report()
        evts = report.get("log_events", [])
        print(f"Log events: {len(evts)}")
        for e in evts[:10]:
            print(f"  {e.get('log','?')}: {e.get('text','')[:80]}")
    elif args.report:
        result = wd.run_cycle(token=tok, supabase_url=url,
                              service_key=svc, auto_repair=True)
        with wd._lock:
            checks  = dict(wd._last_checks)
            actions = list(wd._last_actions)
            score   = wd._last_score
        report = wd.ai.generate_health_report(checks, actions, score)
        print(report)
    elif args.validate:
        results = wd.deployer.validate_syntax(args.validate)
        for f, r in results.items():
            sym = "[OK]" if r["ok"] else "[FAIL]"
            print(f"{sym} {f}: {r.get('error','')}")
    elif args.daemon:
        wd.start_background(
            interval=args.interval, token=tok,
            supabase_url=url, service_key=svc)
        print(f"[Watchdog] Daemon running (interval={args.interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            wd.stop()
            print("\n[Watchdog] Stopped.")
    else:
        p.print_help()
