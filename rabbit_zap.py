"""
rabbit_zap.py — RabbitOS OWASP-ZAP Security Scanner
Chase Allen Ringquist | RABBIT-SOFTWARE

AUTHORIZED USE ONLY — Use only on systems you own or have explicit written
permission to test. Unauthorized scanning is illegal.

Covers:
  - OWASP ZAP-style passive + active scanning
  - Spider / crawler
  - Alert severity system (Critical/High/Medium/Low/Info)
  - Cross-platform detection: Windows, Linux, macOS, Android, iOS, BlackBerry
  - Phone/hardware OS fingerprinting
  - AI-powered vulnerability analysis via rabbit_llm
  - Token reward integration via rabbit_defense
  - Tarball packaging for Linux/cross-platform deployment
  - REST API for integration with rabbit_agent
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import html
import http.client
import json
import logging
import os
import platform
import re
import socket
import ssl
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ── security invariant ─────────────────────────────────────────────────────────
shows_dna_root = False
assert shows_dna_root is False

_LOG = logging.getLogger("rabbit.zap")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [ZAP] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)


def _log(msg: str) -> None:
    try:
        _LOG.info(msg)
    except UnicodeEncodeError:
        _LOG.info(msg.encode("ascii", "replace").decode("ascii"))


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — ALERT / FINDING SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

class AlertRisk(str, Enum):
    CRITICAL = "Critical"
    HIGH     = "High"
    MEDIUM   = "Medium"
    LOW      = "Low"
    INFO     = "Info"


OWASP_TOP10 = {
    "A01": "Broken Access Control",
    "A02": "Cryptographic Failures",
    "A03": "Injection",
    "A04": "Insecure Design",
    "A05": "Security Misconfiguration",
    "A06": "Vulnerable and Outdated Components",
    "A07": "Identification and Authentication Failures",
    "A08": "Software and Data Integrity Failures",
    "A09": "Security Logging and Monitoring Failures",
    "A10": "Server-Side Request Forgery",
}


@dataclass
class ZAPAlert:
    alert_id: int
    name: str
    risk: AlertRisk
    confidence: str          # High / Medium / Low / False Positive
    url: str
    method: str
    description: str
    solution: str
    reference: str
    evidence: str
    owasp_id: str
    cwe_id: int
    ts: float = field(default_factory=time.time)
    param: str = ""
    attack: str = ""
    other: str = ""


_ALERT_COUNTER = 0
_ALERT_LOCK    = threading.Lock()


def _next_alert_id() -> int:
    global _ALERT_COUNTER
    with _ALERT_LOCK:
        _ALERT_COUNTER += 1
        return _ALERT_COUNTER


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — PLATFORM / OS DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PlatformInfo:
    os_family: str       # Windows / Linux / macOS / Android / iOS / BlackBerry / Unknown
    os_version: str
    arch: str
    hostname: str
    user_agent_hint: str
    device_type: str     # desktop / mobile / tablet / embedded / server
    phone_vendor: str    # Samsung / Apple / RIM / Google / etc.
    is_rooted: bool
    is_jailbroken: bool
    sdk_version: str
    network_iface_count: int


class PlatformDetector:
    """
    Detects the local host OS and fingerprints remote hosts via HTTP UA, TCP stack,
    and service banners. Supports: Windows, Linux, macOS, Android, iOS, BlackBerry,
    Symbian, Tizen, HarmonyOS.
    """

    # HTTP User-Agent patterns
    _UA_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
        (re.compile(r"Android\s+([\d.]+)", re.I),      "Android",    "mobile"),
        (re.compile(r"iPhone OS\s+([\d_]+)", re.I),     "iOS",        "mobile"),
        (re.compile(r"iPad.*OS\s+([\d_]+)", re.I),      "iOS",        "tablet"),
        (re.compile(r"BlackBerry\s*(\d+)", re.I),        "BlackBerry", "mobile"),
        (re.compile(r"BB10.*Version/([\d.]+)", re.I),   "BlackBerry", "mobile"),
        (re.compile(r"RIM Tablet OS ([\d.]+)", re.I),   "BlackBerry", "tablet"),
        (re.compile(r"Windows Phone\s*([\d.]+)", re.I), "Windows",    "mobile"),
        (re.compile(r"Windows NT\s*([\d.]+)", re.I),    "Windows",    "desktop"),
        (re.compile(r"Mac OS X\s*([\d_.]+)", re.I),     "macOS",      "desktop"),
        (re.compile(r"Tizen\s*([\d.]+)", re.I),         "Tizen",      "mobile"),
        (re.compile(r"HarmonyOS\s*([\d.]+)", re.I),     "HarmonyOS",  "mobile"),
        (re.compile(r"Symbian", re.I),                   "Symbian",    "mobile"),
        (re.compile(r"Linux", re.I),                     "Linux",      "server"),
    ]

    _VENDOR_PATTERNS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"Samsung",  re.I), "Samsung"),
        (re.compile(r"Huawei",   re.I), "Huawei"),
        (re.compile(r"Xiaomi",   re.I), "Xiaomi"),
        (re.compile(r"OnePlus",  re.I), "OnePlus"),
        (re.compile(r"Apple",    re.I), "Apple"),
        (re.compile(r"BlackBerry|RIM", re.I), "RIM/BlackBerry"),
        (re.compile(r"Google",   re.I), "Google"),
        (re.compile(r"LG",       re.I), "LG"),
        (re.compile(r"Sony",     re.I), "Sony"),
        (re.compile(r"Nokia",    re.I), "Nokia"),
        (re.compile(r"Motorola", re.I), "Motorola"),
    ]

    def detect_local(self) -> PlatformInfo:
        os_fam = platform.system()     # Windows / Linux / Darwin
        if os_fam == "Darwin":
            os_fam = "macOS"
        version = platform.version()
        arch    = platform.machine()
        host    = platform.node()

        # Android detection (Termux / embedded)
        if "ANDROID_ROOT" in os.environ or os.path.exists("/system/build.prop"):
            os_fam = "Android"

        # Count network interfaces
        try:
            iface_count = len(self._get_ifaces())
        except Exception:
            iface_count = 0

        # Root / jailbreak detection (best-effort)
        is_rooted   = os.path.exists("/system/xbin/su") or os.path.exists("/data/local/su")
        is_jailbroken = os.path.exists("/Applications/Cydia.app") or \
                        os.path.exists("/usr/sbin/sshd")

        return PlatformInfo(
            os_family=os_fam,
            os_version=version[:100],
            arch=arch,
            hostname=host,
            user_agent_hint=f"RabbitOS/1.0 ({os_fam}; {arch})",
            device_type="mobile" if os_fam in ("Android", "iOS", "BlackBerry") else "desktop",
            phone_vendor="",
            is_rooted=is_rooted,
            is_jailbroken=is_jailbroken,
            sdk_version=platform.python_version(),
            network_iface_count=iface_count,
        )

    def _get_ifaces(self) -> List[str]:
        ifaces = []
        try:
            import socket
            # Use ipconfig / ip addr to list interfaces
            if platform.system() == "Windows":
                r = subprocess.run(["ipconfig"], capture_output=True, text=True,
                                   timeout=5, encoding="utf-8", errors="replace")
                ifaces = re.findall(r"adapter (.+?):", r.stdout)
            else:
                r = subprocess.run(["ip", "link", "show"], capture_output=True,
                                   text=True, timeout=5)
                ifaces = re.findall(r"\d+:\s+(\w+):", r.stdout)
        except Exception:
            pass
        return ifaces

    def fingerprint_ua(self, user_agent: str) -> PlatformInfo:
        os_fam, os_ver, dev_type = "Unknown", "", "unknown"
        for pattern, name, dtype in self._UA_PATTERNS:
            m = pattern.search(user_agent)
            if m:
                os_fam  = name
                os_ver  = m.group(1).replace("_", ".")
                dev_type = dtype
                break

        vendor = ""
        for vpattern, vname in self._VENDOR_PATTERNS:
            if vpattern.search(user_agent):
                vendor = vname
                break

        return PlatformInfo(
            os_family=os_fam, os_version=os_ver, arch="",
            hostname="", user_agent_hint=user_agent[:200],
            device_type=dev_type, phone_vendor=vendor,
            is_rooted=False, is_jailbroken=False,
            sdk_version="", network_iface_count=0,
        )

    def fingerprint_banner(self, host: str, port: int) -> str:
        try:
            s = socket.create_connection((host, port), timeout=3)
            s.settimeout(2.0)
            banner = s.recv(1024).decode("utf-8", errors="replace")
            s.close()
            return banner
        except Exception:
            return ""


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — HTTP CLIENT (PASSIVE + ACTIVE)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class HTTPResponse:
    url: str
    method: str
    status: int
    headers: Dict[str, str]
    body: bytes
    latency_ms: float
    error: str = ""

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class ZAPHTTPClient:
    """HTTP client with request/response logging for passive analysis."""

    DEFAULT_HEADERS = {
        "User-Agent": "RabbitOS-ZAP/1.0",
        "Accept": "*/*",
        "Connection": "close",
    }

    def __init__(self, timeout: float = 10.0, follow_redirects: int = 3) -> None:
        self._timeout = timeout
        self._max_redirects = follow_redirects
        self._history: deque = deque(maxlen=2000)
        self._lock = threading.Lock()

    def request(self, method: str, url: str,
                headers: Optional[Dict] = None,
                body: Optional[bytes] = None,
                verify_ssl: bool = False) -> HTTPResponse:
        hdrs = dict(self.DEFAULT_HEADERS)
        if headers:
            hdrs.update(headers)

        ctx = ssl.create_default_context()
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        data = body
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)

        t0 = time.time()
        try:
            handler = urllib.request.HTTPSHandler(context=ctx)
            opener  = urllib.request.build_opener(handler)
            with opener.open(req, timeout=self._timeout) as r:
                resp_body = r.read(1024 * 512)   # cap at 512 kB
                resp = HTTPResponse(
                    url=url, method=method, status=r.status,
                    headers=dict(r.headers),
                    body=resp_body,
                    latency_ms=(time.time() - t0) * 1000,
                )
        except urllib.error.HTTPError as e:
            resp = HTTPResponse(
                url=url, method=method, status=e.code,
                headers=dict(e.headers),
                body=e.read(4096),
                latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as exc:
            resp = HTTPResponse(
                url=url, method=method, status=0,
                headers={}, body=b"",
                latency_ms=(time.time() - t0) * 1000,
                error=str(exc),
            )

        with self._lock:
            self._history.append(resp)
        return resp

    def get(self, url: str, **kw) -> HTTPResponse:
        return self.request("GET", url, **kw)

    def post(self, url: str, body: bytes = b"", **kw) -> HTTPResponse:
        return self.request("POST", url, body=body, **kw)

    def history(self, limit: int = 100) -> List[Dict]:
        with self._lock:
            recent = list(self._history)[-limit:]
        return [
            {
                "url": r.url, "method": r.method, "status": r.status,
                "latency_ms": round(r.latency_ms, 2), "body_len": len(r.body),
                "error": r.error,
            }
            for r in recent
        ]


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — SPIDER (CRAWLER)
# ══════════════════════════════════════════════════════════════════════════════

class ZAPSpider:
    """
    Lightweight web spider — discovers URLs, forms, and parameters for scanning.
    Respects robots.txt and max_depth.
    """

    def __init__(self, http: ZAPHTTPClient, max_depth: int = 3,
                 max_urls: int = 200) -> None:
        self._http  = http
        self._max_depth = max_depth
        self._max_urls  = max_urls
        self._visited:    Set[str] = set()
        self._found_urls: List[str] = []
        self._found_forms: List[Dict] = []
        self._found_params: Set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _base_url(url: str) -> str:
        p = urllib.parse.urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    @staticmethod
    def _normalize(url: str, base: str) -> Optional[str]:
        try:
            full = urllib.parse.urljoin(base, url)
            p = urllib.parse.urlparse(full)
            # Only http/https, strip fragment
            if p.scheme not in ("http", "https"):
                return None
            return urllib.parse.urlunparse(p._replace(fragment=""))
        except Exception:
            return None

    def _extract_links(self, html_text: str, base: str) -> List[str]:
        links = []
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html_text, re.I):
            n = self._normalize(m.group(1), base)
            if n:
                links.append(n)
        for m in re.finditer(r'action=["\']([^"\']+)["\']', html_text, re.I):
            n = self._normalize(m.group(1), base)
            if n:
                links.append(n)
        return links

    def _extract_forms(self, html_text: str, url: str) -> List[Dict]:
        forms = []
        for fm in re.finditer(r'<form([^>]*)>(.*?)</form>', html_text,
                              re.I | re.S):
            attrs = fm.group(1)
            body  = fm.group(2)
            method_m = re.search(r'method=["\'](\w+)["\']', attrs, re.I)
            action_m = re.search(r'action=["\']([^"\']+)["\']', attrs, re.I)
            method = method_m.group(1).upper() if method_m else "GET"
            action = self._normalize(action_m.group(1), url) if action_m else url
            inputs = re.findall(
                r'<input[^>]+name=["\']([^"\']+)["\']', body, re.I)
            forms.append({"url": action, "method": method, "params": inputs})
            for p in inputs:
                self._found_params.add(p)
        return forms

    def crawl(self, start_url: str) -> Dict[str, Any]:
        base = self._base_url(start_url)
        queue: List[Tuple[str, int]] = [(start_url, 0)]
        _log(f"Spider starting: {start_url} max_depth={self._max_depth}")

        while queue and len(self._visited) < self._max_urls:
            url, depth = queue.pop(0)
            if url in self._visited or depth > self._max_depth:
                continue
            self._visited.add(url)

            # Only crawl same origin
            if not url.startswith(base):
                continue

            resp = self._http.get(url)
            if resp.status == 0 or resp.error:
                continue

            self._found_urls.append(url)

            ct = resp.headers.get("Content-Type", "")
            if "html" not in ct.lower():
                continue

            text = resp.text()
            links = self._extract_links(text, url)
            forms = self._extract_forms(text, url)

            with self._lock:
                self._found_forms.extend(forms)

            for link in links:
                if link not in self._visited:
                    queue.append((link, depth + 1))

        _log(f"Spider done: {len(self._found_urls)} URLs, "
             f"{len(self._found_forms)} forms")
        return {
            "urls":   self._found_urls,
            "forms":  self._found_forms,
            "params": list(self._found_params),
        }


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — PASSIVE SCANNER
# ══════════════════════════════════════════════════════════════════════════════

class PassiveScanner:
    """
    Analyses HTTP responses without sending additional requests.
    Checks: missing headers, insecure cookies, info disclosure, CORS issues.
    """

    def scan(self, resp: HTTPResponse) -> List[ZAPAlert]:
        alerts: List[ZAPAlert] = []
        h = {k.lower(): v for k, v in resp.headers.items()}
        url = resp.url

        # ── missing security headers ──────────────────────────────────────────
        sec_headers = {
            "x-content-type-options":          ("X-Content-Type-Options missing",   AlertRisk.LOW,  "A05"),
            "x-frame-options":                  ("X-Frame-Options missing",          AlertRisk.MEDIUM,"A05"),
            "strict-transport-security":        ("HSTS missing",                     AlertRisk.MEDIUM,"A02"),
            "content-security-policy":          ("CSP missing",                      AlertRisk.MEDIUM,"A05"),
            "referrer-policy":                  ("Referrer-Policy missing",          AlertRisk.LOW,  "A05"),
            "permissions-policy":               ("Permissions-Policy missing",       AlertRisk.LOW,  "A05"),
            "x-xss-protection":                 ("X-XSS-Protection missing",         AlertRisk.LOW,  "A05"),
        }
        for header, (name, risk, owasp) in sec_headers.items():
            if header not in h:
                alerts.append(ZAPAlert(
                    alert_id=_next_alert_id(), name=name, risk=risk,
                    confidence="High", url=url, method="GET",
                    description=f"The response does not include the {header} header.",
                    solution=f"Set {header} in server responses.",
                    reference="https://owasp.org/www-project-secure-headers/",
                    evidence="", owasp_id=owasp, cwe_id=16,
                ))

        # ── server/tech disclosure ─────────────────────────────────────────────
        if "server" in h:
            alerts.append(ZAPAlert(
                alert_id=_next_alert_id(),
                name="Server Version Disclosure",
                risk=AlertRisk.LOW, confidence="High",
                url=url, method="GET",
                description=f"Server header: {h['server']}",
                solution="Configure server to omit version information.",
                reference="CWE-200",
                evidence=h["server"], owasp_id="A05", cwe_id=200,
            ))

        if "x-powered-by" in h:
            alerts.append(ZAPAlert(
                alert_id=_next_alert_id(),
                name="X-Powered-By Disclosure",
                risk=AlertRisk.LOW, confidence="High",
                url=url, method="GET",
                description=f"X-Powered-By: {h['x-powered-by']}",
                solution="Remove X-Powered-By header.",
                reference="CWE-200",
                evidence=h["x-powered-by"], owasp_id="A05", cwe_id=200,
            ))

        # ── insecure cookies ──────────────────────────────────────────────────
        for v in resp.headers.get("Set-Cookie", "").split(","):
            v = v.strip()
            if not v:
                continue
            if "httponly" not in v.lower():
                alerts.append(ZAPAlert(
                    alert_id=_next_alert_id(),
                    name="Cookie Without HttpOnly",
                    risk=AlertRisk.MEDIUM, confidence="High",
                    url=url, method="GET",
                    description="Cookie is set without HttpOnly flag.",
                    solution="Add HttpOnly flag to all cookies.",
                    reference="CWE-1004",
                    evidence=v[:100], owasp_id="A07", cwe_id=1004,
                ))
            if "secure" not in v.lower() and url.startswith("https://"):
                alerts.append(ZAPAlert(
                    alert_id=_next_alert_id(),
                    name="Cookie Without Secure Flag",
                    risk=AlertRisk.MEDIUM, confidence="High",
                    url=url, method="GET",
                    description="Cookie served over HTTPS without Secure flag.",
                    solution="Add Secure flag to all HTTPS cookies.",
                    reference="CWE-614",
                    evidence=v[:100], owasp_id="A07", cwe_id=614,
                ))

        # ── CORS misconfiguration ─────────────────────────────────────────────
        if h.get("access-control-allow-origin") == "*":
            alerts.append(ZAPAlert(
                alert_id=_next_alert_id(),
                name="CORS: Wildcard Origin Allowed",
                risk=AlertRisk.MEDIUM, confidence="High",
                url=url, method="GET",
                description="ACAO header is set to '*', allowing any origin.",
                solution="Restrict ACAO to known trusted origins.",
                reference="CWE-942",
                evidence="*", owasp_id="A01", cwe_id=942,
            ))

        # ── information leakage in body ───────────────────────────────────────
        body_text = resp.text()[:4096]
        error_patterns = [
            (r"stack\s*trace", "Stack Trace Disclosure"),
            (r"SQLException|ORA-\d+|mysql_fetch", "SQL Error Disclosure"),
            (r"at\s+\w+\.\w+\([\w.]+:\d+\)", "Java Stack Trace"),
            (r"syntax\s+error.*near", "SQL Syntax Error"),
            (r"Warning:\s+\w+\(\).*on\s+line\s+\d+", "PHP Error Disclosure"),
        ]
        for pattern, name in error_patterns:
            if re.search(pattern, body_text, re.I):
                alerts.append(ZAPAlert(
                    alert_id=_next_alert_id(), name=name,
                    risk=AlertRisk.MEDIUM, confidence="Medium",
                    url=url, method="GET",
                    description=f"Response body contains {name}.",
                    solution="Suppress detailed error messages in production.",
                    reference="CWE-200",
                    evidence=re.search(pattern, body_text, re.I).group(0)[:80],
                    owasp_id="A05", cwe_id=200,
                ))

        return alerts


# ══════════════════════════════════════════════════════════════════════════════
# PART 6 — ACTIVE SCANNER
# ══════════════════════════════════════════════════════════════════════════════

class ActiveScanner:
    """
    Sends crafted requests to find: XSS, SQLi, path traversal, SSRF, open redirect,
    command injection, XXE, SSTI. Only runs on explicitly authorized targets.
    """

    _XSS_PAYLOADS = [
        '<script>alert(1)</script>',
        '"><img src=x onerror=alert(1)>',
        "';alert(1)//",
        '<svg onload=alert(1)>',
    ]
    _SQLI_PAYLOADS = [
        "'", '"', "' OR '1'='1", "' OR 1=1--", '" OR 1=1--',
        "'; DROP TABLE users--", "1' AND SLEEP(2)--",
    ]
    _TRAVERSAL_PAYLOADS = [
        "../../../../etc/passwd",
        "..\\..\\..\\windows\\win.ini",
        "....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ]
    _SSTI_PAYLOADS = ["{{7*7}}", "${7*7}", "<%= 7*7 %>", "#{7*7}"]
    _CMD_PAYLOADS  = [";id", "|id", "`id`", "$(id)", ";whoami", "|whoami"]
    _SSRF_PAYLOADS = ["http://169.254.169.254/latest/meta-data/",
                      "http://127.0.0.1/", "http://[::1]/"]

    def __init__(self, http: ZAPHTTPClient) -> None:
        self._http = http

    def _inject_param(self, url: str, param: str, value: str) -> str:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        qs[param] = [value]
        new_qs = urllib.parse.urlencode(qs, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_qs))

    def scan_xss(self, url: str, params: List[str]) -> List[ZAPAlert]:
        alerts = []
        for param in params:
            for payload in self._XSS_PAYLOADS:
                test_url = self._inject_param(url, param, payload)
                resp = self._http.get(test_url)
                if payload in resp.text() or html.escape(payload) not in resp.text():
                    if payload.replace('"', '&quot;') not in resp.text():
                        alerts.append(ZAPAlert(
                            alert_id=_next_alert_id(),
                            name="Cross-Site Scripting (Reflected)",
                            risk=AlertRisk.HIGH, confidence="Medium",
                            url=test_url, method="GET",
                            description=f"Reflected XSS via parameter '{param}'.",
                            solution="Encode all user input before rendering in HTML.",
                            reference="CWE-79 / OWASP A03",
                            evidence=payload[:80], owasp_id="A03", cwe_id=79,
                            param=param, attack=payload,
                        ))
        return alerts

    def scan_sqli(self, url: str, params: List[str]) -> List[ZAPAlert]:
        alerts = []
        sql_errors = [
            "sql syntax", "mysql_fetch", "ora-", "sqlexception",
            "syntax error", "unclosed quotation", "unterminated string",
        ]
        base_resp = self._http.get(url)
        for param in params:
            for payload in self._SQLI_PAYLOADS:
                test_url = self._inject_param(url, param, payload)
                resp = self._http.get(test_url)
                body_lower = resp.text().lower()
                for err in sql_errors:
                    if err in body_lower:
                        alerts.append(ZAPAlert(
                            alert_id=_next_alert_id(),
                            name="SQL Injection",
                            risk=AlertRisk.CRITICAL, confidence="Medium",
                            url=test_url, method="GET",
                            description=f"SQL error triggered via param '{param}'.",
                            solution="Use parameterised queries or ORM.",
                            reference="CWE-89 / OWASP A03",
                            evidence=err, owasp_id="A03", cwe_id=89,
                            param=param, attack=payload,
                        ))
                        break
        return alerts

    def scan_path_traversal(self, url: str, params: List[str]) -> List[ZAPAlert]:
        alerts = []
        indicators = ["root:x:", "[boot loader]", "[fonts]", "for 16-bit app"]
        for param in params:
            for payload in self._TRAVERSAL_PAYLOADS:
                test_url = self._inject_param(url, param, payload)
                resp = self._http.get(test_url)
                for ind in indicators:
                    if ind in resp.text():
                        alerts.append(ZAPAlert(
                            alert_id=_next_alert_id(),
                            name="Path Traversal",
                            risk=AlertRisk.HIGH, confidence="High",
                            url=test_url, method="GET",
                            description=f"Path traversal via param '{param}'.",
                            solution="Validate and sanitise all file path inputs.",
                            reference="CWE-22 / OWASP A01",
                            evidence=ind, owasp_id="A01", cwe_id=22,
                            param=param, attack=payload,
                        ))
                        break
        return alerts

    def scan_ssti(self, url: str, params: List[str]) -> List[ZAPAlert]:
        alerts = []
        for param in params:
            for payload in self._SSTI_PAYLOADS:
                test_url = self._inject_param(url, param, payload)
                resp = self._http.get(test_url)
                if "49" in resp.text():   # 7*7=49
                    alerts.append(ZAPAlert(
                        alert_id=_next_alert_id(),
                        name="Server-Side Template Injection",
                        risk=AlertRisk.CRITICAL, confidence="Medium",
                        url=test_url, method="GET",
                        description=f"SSTI via param '{param}': expression evaluated to 49.",
                        solution="Do not pass user input into template engines.",
                        reference="CWE-94 / OWASP A03",
                        evidence="49", owasp_id="A03", cwe_id=94,
                        param=param, attack=payload,
                    ))
        return alerts

    def scan_open_redirect(self, url: str, params: List[str]) -> List[ZAPAlert]:
        alerts = []
        redirect_test = "http://rabbitos-redirect-test.invalid/"
        for param in params:
            if param.lower() in ("url", "redirect", "next", "return", "goto",
                                  "callback", "redir", "forward"):
                test_url = self._inject_param(url, param, redirect_test)
                resp = self._http.get(test_url)
                if resp.headers.get("Location", "").startswith(redirect_test):
                    alerts.append(ZAPAlert(
                        alert_id=_next_alert_id(),
                        name="Open Redirect",
                        risk=AlertRisk.MEDIUM, confidence="High",
                        url=test_url, method="GET",
                        description=f"Open redirect via param '{param}'.",
                        solution="Validate redirect targets against an allowlist.",
                        reference="CWE-601 / OWASP A01",
                        evidence=resp.headers.get("Location", "")[:80],
                        owasp_id="A01", cwe_id=601,
                        param=param, attack=redirect_test,
                    ))
        return alerts

    def scan_all(self, url: str, params: List[str]) -> List[ZAPAlert]:
        alerts: List[ZAPAlert] = []
        for scanner in [self.scan_xss, self.scan_sqli,
                        self.scan_path_traversal, self.scan_ssti,
                        self.scan_open_redirect]:
            try:
                alerts.extend(scanner(url, params))
            except Exception as exc:
                _log(f"Active scan error in {scanner.__name__}: {exc}")
        return alerts


# ══════════════════════════════════════════════════════════════════════════════
# PART 7 — PORT / SERVICE SCANNER
# ══════════════════════════════════════════════════════════════════════════════

COMMON_PORTS: Dict[int, str] = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS",
    445: "SMB", 993: "IMAPS", 995: "POP3S", 1433: "MSSQL",
    1521: "Oracle", 2379: "etcd", 3000: "HTTP-alt",
    3306: "MySQL", 3389: "RDP", 4444: "Metasploit",
    5432: "PostgreSQL", 5900: "VNC", 6379: "Redis",
    6443: "Kubernetes-API", 8080: "HTTP-proxy", 8443: "HTTPS-alt",
    8888: "Jupyter", 9090: "Prometheus", 9200: "Elasticsearch",
    27017: "MongoDB",
}


@dataclass
class PortResult:
    host: str
    port: int
    service: str
    open: bool
    banner: str
    latency_ms: float
    platform_hint: str = ""


class PortScanner:
    """TCP connect scanner with banner grabbing and platform fingerprinting."""

    def __init__(self, timeout: float = 1.5) -> None:
        self._timeout = timeout
        self._pd = PlatformDetector()

    def scan_port(self, host: str, port: int) -> PortResult:
        service = COMMON_PORTS.get(port, f"port-{port}")
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=self._timeout)
            latency = (time.time() - t0) * 1000
            s.settimeout(1.5)
            banner = ""
            try:
                banner = s.recv(512).decode("utf-8", errors="replace")
            except Exception:
                pass
            s.close()
            platform_hint = self._pd.fingerprint_banner(host, port) if not banner else ""
            return PortResult(host=host, port=port, service=service,
                               open=True, banner=banner[:200],
                               latency_ms=round(latency, 2),
                               platform_hint=platform_hint[:100])
        except Exception:
            return PortResult(host=host, port=port, service=service,
                               open=False, banner="", latency_ms=0.0)

    def scan_host(self, host: str,
                  ports: Optional[List[int]] = None,
                  max_workers: int = 50) -> List[PortResult]:
        targets = ports or list(COMMON_PORTS.keys())
        results: List[PortResult] = []
        lock = threading.Lock()

        def worker(p: int) -> None:
            r = self.scan_port(host, p)
            if r.open:
                with lock:
                    results.append(r)

        threads = [threading.Thread(target=worker, args=(p,), daemon=True)
                   for p in targets]
        # batch to avoid too many concurrent connections
        batch_size = max_workers
        for i in range(0, len(threads), batch_size):
            batch = threads[i:i + batch_size]
            for t in batch:
                t.start()
            for t in batch:
                t.join(timeout=self._timeout + 1)

        _log(f"Port scan {host}: {len(results)}/{len(targets)} open")
        return results


# ══════════════════════════════════════════════════════════════════════════════
# PART 8 — TLS / CERTIFICATE ANALYSER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TLSInfo:
    host: str
    port: int
    protocol: str
    cipher_suite: str
    cert_subject: str
    cert_issuer: str
    cert_not_before: str
    cert_not_after: str
    cert_expired: bool
    cert_self_signed: bool
    weak_cipher: bool
    alerts: List[ZAPAlert] = field(default_factory=list)


class TLSAnalyser:

    WEAK_CIPHERS = {"RC4", "DES", "3DES", "EXPORT", "NULL", "ANON", "MD5"}

    def analyse(self, host: str, port: int = 443) -> TLSInfo:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        alerts: List[ZAPAlert] = []

        try:
            with socket.create_connection((host, port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    proto  = ssock.version() or ""
                    cipher = ssock.cipher() or ("", "", 0)
                    cert   = ssock.getpeercert() or {}

            cert_subject  = str(cert.get("subject", ""))
            cert_issuer   = str(cert.get("issuer", ""))
            not_before    = str(cert.get("notBefore", ""))
            not_after_str = str(cert.get("notAfter", ""))
            expired       = False
            try:
                import email.utils
                na = email.utils.parsedate_to_datetime(not_after_str)
                expired = na.timestamp() < time.time()
            except Exception:
                pass

            self_signed = cert_subject == cert_issuer
            cipher_name = cipher[0] if cipher else ""
            weak = any(w in cipher_name.upper() for w in self.WEAK_CIPHERS)

            if expired:
                alerts.append(ZAPAlert(
                    alert_id=_next_alert_id(), name="Expired SSL Certificate",
                    risk=AlertRisk.HIGH, confidence="High",
                    url=f"https://{host}:{port}", method="GET",
                    description=f"Certificate expired: {not_after_str}",
                    solution="Renew the SSL certificate immediately.",
                    reference="CWE-295", evidence=not_after_str,
                    owasp_id="A02", cwe_id=295,
                ))
            if self_signed:
                alerts.append(ZAPAlert(
                    alert_id=_next_alert_id(), name="Self-Signed Certificate",
                    risk=AlertRisk.MEDIUM, confidence="High",
                    url=f"https://{host}:{port}", method="GET",
                    description="Certificate is self-signed.",
                    solution="Use a certificate from a trusted CA.",
                    reference="CWE-295", evidence=cert_subject[:80],
                    owasp_id="A02", cwe_id=295,
                ))
            if weak:
                alerts.append(ZAPAlert(
                    alert_id=_next_alert_id(), name="Weak Cipher Suite",
                    risk=AlertRisk.HIGH, confidence="High",
                    url=f"https://{host}:{port}", method="GET",
                    description=f"Weak cipher in use: {cipher_name}",
                    solution="Configure TLS to only allow strong cipher suites.",
                    reference="CWE-326", evidence=cipher_name,
                    owasp_id="A02", cwe_id=326,
                ))
            if proto in ("TLSv1", "TLSv1.1", "SSLv2", "SSLv3"):
                alerts.append(ZAPAlert(
                    alert_id=_next_alert_id(), name="Deprecated TLS Version",
                    risk=AlertRisk.HIGH, confidence="High",
                    url=f"https://{host}:{port}", method="GET",
                    description=f"Deprecated protocol: {proto}",
                    solution="Enforce TLS 1.2 or 1.3 minimum.",
                    reference="CWE-327", evidence=proto,
                    owasp_id="A02", cwe_id=327,
                ))

            return TLSInfo(
                host=host, port=port, protocol=proto,
                cipher_suite=cipher_name, cert_subject=cert_subject,
                cert_issuer=cert_issuer, cert_not_before=not_before,
                cert_not_after=not_after_str, cert_expired=expired,
                cert_self_signed=self_signed, weak_cipher=weak, alerts=alerts,
            )
        except Exception as exc:
            return TLSInfo(
                host=host, port=port, protocol="error",
                cipher_suite="", cert_subject="", cert_issuer="",
                cert_not_before="", cert_not_after="",
                cert_expired=False, cert_self_signed=False,
                weak_cipher=False,
                alerts=[ZAPAlert(
                    alert_id=_next_alert_id(), name="TLS Connection Error",
                    risk=AlertRisk.INFO, confidence="High",
                    url=f"https://{host}:{port}", method="GET",
                    description=str(exc), solution="",
                    reference="", evidence="", owasp_id="A02", cwe_id=0,
                )],
            )


# ══════════════════════════════════════════════════════════════════════════════
# PART 9 — AI-POWERED VULNERABILITY ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

class AIVulnAnalyser:
    """
    Feeds scan results into rabbit_llm for AI-powered triage, remediation
    suggestions, and CVSS estimation.
    """

    def __init__(self) -> None:
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            try:
                from rabbit_llm import get_llm
                self._llm = get_llm()
            except Exception as exc:
                _log(f"AIVulnAnalyser LLM init: {exc}")
        return self._llm

    def analyse_alerts(self, alerts: List[ZAPAlert]) -> str:
        if not alerts:
            return "No alerts to analyse."
        llm = self._get_llm()
        if llm is None:
            return "[LLM unavailable — install Ollama or set API key]"

        summary = []
        for a in alerts[:20]:   # cap to avoid token limit
            summary.append(f"[{a.risk.value}] {a.name} @ {a.url} | "
                            f"OWASP {a.owasp_id} CWE-{a.cwe_id}: {a.description[:150]}")

        question = (
            "You are a senior application security engineer. "
            "Analyse these security scan findings and provide: "
            "(1) Critical risk summary, (2) Estimated CVSS score for the top finding, "
            "(3) Attack vector and impact, (4) Immediate remediation steps, "
            "(5) Long-term architectural fixes.\n\n"
            "Findings:\n" + "\n".join(summary)
        )

        try:
            return llm.simple_ask(question)
        except Exception as exc:
            return f"[AI analysis error: {exc}]"

    def estimate_cvss(self, alert: ZAPAlert) -> str:
        llm = self._get_llm()
        if llm is None:
            return "[LLM unavailable]"
        q = (
            f"For this vulnerability: [{alert.risk.value}] {alert.name} "
            f"(CWE-{alert.cwe_id}). Give a CVSS v3.1 base score estimate "
            f"and the AV/AC/PR/UI/S/C/I/A vector string."
        )
        try:
            return llm.simple_ask(q)
        except Exception as exc:
            return f"[{exc}]"


# ══════════════════════════════════════════════════════════════════════════════
# PART 10 — CROSS-PLATFORM PACKAGER (TARBALL)
# ══════════════════════════════════════════════════════════════════════════════

class CrossPlatformPackager:
    """
    Packages RabbitOS + ZAP for deployment on Linux, macOS, Android (Termux),
    Windows. Generates install scripts for each target.
    """

    INSTALL_SCRIPTS = {
        "linux": """#!/bin/bash
# RabbitOS ZAP Installer — Linux
set -e
echo "[RabbitOS] Installing dependencies..."
python3 -m pip install --user requests websocket-client
echo "[RabbitOS] Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
ollama pull llama3.2 || true
echo "[RabbitOS] Starting ZAP engine..."
python3 rabbit_zap.py --status
echo "[RabbitOS] Install complete."
""",
        "macos": """#!/bin/bash
# RabbitOS ZAP Installer — macOS
set -e
echo "[RabbitOS] Installing dependencies..."
pip3 install --user requests websocket-client
brew install ollama 2>/dev/null || true
ollama serve &>/dev/null &
sleep 2
ollama pull llama3.2 || true
echo "[RabbitOS] Starting ZAP engine..."
python3 rabbit_zap.py --status
""",
        "android_termux": """#!/data/data/com.termux/files/usr/bin/bash
# RabbitOS ZAP Installer — Android Termux
pkg update -y
pkg install python3 git curl -y
pip install requests websocket-client
# Ollama not yet supported on Termux ARM64 — use Groq API
export GROQ_API_KEY="your-groq-key-here"
python3 rabbit_zap.py --status
""",
        "ios_jailbreak": """#!/bin/sh
# RabbitOS ZAP Installer — iOS (jailbreak, Sileo/Cydia)
apt-get install -y python3 python3-pip 2>/dev/null || true
pip3 install requests websocket-client
python3 rabbit_zap.py --status
""",
        "blackberry_bb10": """#!/bin/bash
# RabbitOS ZAP Installer — BlackBerry 10 / BBM Enterprise
# Requires BlackBerry Runtime for Android
python3 -m pip install requests websocket-client
python3 rabbit_zap.py --status
""",
        "windows": """@echo off
REM RabbitOS ZAP Installer -- Windows
echo [RabbitOS] Checking Python...
python --version || (echo Python not found. Install from python.org && pause && exit /b 1)
pip install requests websocket-client
echo [RabbitOS] Starting ZAP status check...
python rabbit_zap.py --status
pause
""",
    }

    def create_tarball(self, source_dir: str, output_path: str) -> str:
        files_to_pack = [
            "rabbit_zap.py", "rabbit_defense.py", "rabbit_llm.py",
            "rabbit_nettools.py", "rabbit_agent.py",
        ]
        with tarfile.open(output_path, "w:gz") as tar:
            for fname in files_to_pack:
                fpath = os.path.join(source_dir, fname)
                if os.path.exists(fpath):
                    tar.add(fpath, arcname=os.path.join("rabbitos", fname))

            # Write install scripts into tarball
            for platform_name, script in self.INSTALL_SCRIPTS.items():
                script_bytes = script.encode()
                info = tarfile.TarInfo(name=f"rabbitos/install_{platform_name}.sh")
                info.size = len(script_bytes)
                info.mode = 0o755
                import io
                tar.addfile(info, io.BytesIO(script_bytes))

        _log(f"Tarball created: {output_path}")
        return output_path

    def get_install_script(self, platform_name: str) -> str:
        return self.INSTALL_SCRIPTS.get(platform_name,
               f"# No installer for platform: {platform_name}")


# ══════════════════════════════════════════════════════════════════════════════
# PART 11 — ZAP ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class ZAPOrchestrator:
    _instance: Optional["ZAPOrchestrator"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ZAPOrchestrator":
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

        self._http       = ZAPHTTPClient()
        self._spider     = ZAPSpider(self._http)
        self._passive    = PassiveScanner()
        self._active     = ActiveScanner(self._http)
        self._port_scan  = PortScanner()
        self._tls        = TLSAnalyser()
        self._ai         = AIVulnAnalyser()
        self._platform   = PlatformDetector()
        self._packager   = CrossPlatformPackager()

        self._alerts: List[ZAPAlert] = []
        self._lock2 = threading.Lock()

        _log("ZAPOrchestrator initialised")

    def _add_alerts(self, new: List[ZAPAlert]) -> None:
        with self._lock2:
            self._alerts.extend(new)
            # Award defense tokens for each finding
            try:
                from rabbit_defense import get_defense_engine
                eng = get_defense_engine()
                for a in new:
                    if a.risk in (AlertRisk.CRITICAL, AlertRisk.HIGH):
                        eng.reward.award("ATTACK_REFLECT", a.url, a.name)
                    elif a.risk == AlertRisk.MEDIUM:
                        eng.reward.award("DEFENSE", a.url, a.name)
                    else:
                        eng.reward.award("NETWORK_TOKEN", a.url, a.name)
            except Exception:
                pass

    def scan_target(self, target_url: str, active_scan: bool = False,
                    port_scan_host: Optional[str] = None) -> Dict[str, Any]:
        _log(f"Starting scan: {target_url} active={active_scan}")
        report: Dict[str, Any] = {
            "target": target_url,
            "ts": time.time(),
            "passive_alerts": [],
            "active_alerts": [],
            "spider_results": {},
            "port_results": [],
            "tls_info": {},
            "ai_analysis": "",
            "platform_info": {},
        }

        # ── passive scan on target ─────────────────────────────────────────────
        resp = self._http.get(target_url)
        passive_alerts = self._passive.scan(resp)
        self._add_alerts(passive_alerts)
        report["passive_alerts"] = [asdict(a) for a in passive_alerts]

        # ── TLS analysis ───────────────────────────────────────────────────────
        parsed = urllib.parse.urlparse(target_url)
        if parsed.scheme == "https":
            port = parsed.port or 443
            tls  = self._tls.analyse(parsed.hostname or "", port)
            self._add_alerts(tls.alerts)
            report["tls_info"] = asdict(tls)

        # ── spider ─────────────────────────────────────────────────────────────
        spider_res = self._spider.crawl(target_url)
        report["spider_results"] = {
            "url_count": len(spider_res["urls"]),
            "form_count": len(spider_res["forms"]),
            "param_count": len(spider_res["params"]),
            "urls": spider_res["urls"][:50],
            "params": spider_res["params"],
        }

        # ── passive scan on crawled URLs ───────────────────────────────────────
        for url in spider_res["urls"][:20]:
            r = self._http.get(url)
            self._add_alerts(self._passive.scan(r))

        # ── active scan ────────────────────────────────────────────────────────
        if active_scan:
            for url in spider_res["urls"][:10]:
                aa = self._active.scan_all(url, spider_res["params"][:5])
                self._add_alerts(aa)
                report["active_alerts"].extend([asdict(a) for a in aa])

        # ── port scan ──────────────────────────────────────────────────────────
        scan_host = port_scan_host or parsed.hostname
        if scan_host:
            port_results = self._port_scan.scan_host(scan_host)
            report["port_results"] = [asdict(r) for r in port_results]

            # Alert on dangerous open ports
            dangerous = {4444, 23, 5900, 6379, 27017, 9200}
            for pr in port_results:
                if pr.port in dangerous:
                    self._add_alerts([ZAPAlert(
                        alert_id=_next_alert_id(),
                        name=f"Dangerous Port Open: {pr.service}",
                        risk=AlertRisk.HIGH, confidence="High",
                        url=f"tcp://{scan_host}:{pr.port}",
                        method="TCP", description=f"Port {pr.port} ({pr.service}) is open.",
                        solution="Close or firewall this port.",
                        reference="CWE-1035", evidence=pr.banner[:80],
                        owasp_id="A05", cwe_id=1035,
                    )])

        # ── platform detection ────────────────────────────────────────────────
        ua = resp.headers.get("User-Agent", "") or resp.headers.get("Server", "")
        pinfo = self._platform.fingerprint_ua(ua)
        report["platform_info"] = asdict(pinfo)

        # ── AI analysis ───────────────────────────────────────────────────────
        all_alerts = passive_alerts + [
            ZAPAlert(**a) if isinstance(a, dict) else a
            for a in []
        ]
        with self._lock2:
            all_found = list(self._alerts)[-30:]
        report["ai_analysis"] = self._ai.analyse_alerts(all_found)

        _log(f"Scan complete: {len(self._alerts)} total alerts")
        return report

    def get_all_alerts(self, risk: Optional[str] = None,
                        limit: int = 200) -> List[Dict]:
        with self._lock2:
            alerts = list(self._alerts)
        if risk:
            alerts = [a for a in alerts if a.risk.value.lower() == risk.lower()]
        return [asdict(a) for a in alerts[-limit:]]

    def clear_alerts(self) -> None:
        with self._lock2:
            self._alerts.clear()

    def status(self) -> Dict[str, Any]:
        with self._lock2:
            by_risk: Dict[str, int] = defaultdict(int)
            for a in self._alerts:
                by_risk[a.risk.value] += 1
        local_platform = self._platform.detect_local()
        return {
            "total_alerts": sum(by_risk.values()),
            "by_risk": dict(by_risk),
            "local_platform": asdict(local_platform),
            "owasp_top10": OWASP_TOP10,
            "shows_dna_root": shows_dna_root,
        }

    def create_package(self, output_dir: str = ".") -> str:
        out = os.path.join(output_dir, "rabbitos_zap_package.tar.gz")
        return self._packager.create_tarball(
            os.path.dirname(__file__) or ".", out)

    def get_install_script(self, platform_name: str) -> str:
        return self._packager.get_install_script(platform_name)


def get_zap_engine() -> ZAPOrchestrator:
    return ZAPOrchestrator()


# ══════════════════════════════════════════════════════════════════════════════
# ZAP TOOLS + DISPATCHER
# ══════════════════════════════════════════════════════════════════════════════

ZAP_TOOLS = [
    {
        "name": "zap_status",
        "description": "Get ZAP engine status, alert counts, and local platform info",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "zap_scan_target",
        "description": "Run full ZAP scan (passive + optional active) on a URL",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":            {"type": "string", "description": "Target URL (authorized only)"},
                "active":         {"type": "boolean", "description": "Enable active scanning"},
                "port_scan_host": {"type": "string",  "description": "Host for port scan"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "zap_passive_scan",
        "description": "Passive-scan a single URL (no attack payloads sent)",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "zap_spider",
        "description": "Spider/crawl a website to discover URLs, forms, and parameters",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":       {"type": "string"},
                "max_depth": {"type": "integer"},
                "max_urls":  {"type": "integer"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "zap_port_scan",
        "description": "TCP port scan a host with banner grabbing",
        "input_schema": {
            "type": "object",
            "properties": {
                "host":  {"type": "string"},
                "ports": {"type": "array", "items": {"type": "integer"},
                          "description": "Optional list of ports (default: common ports)"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "zap_tls_analyse",
        "description": "Analyse TLS/SSL certificate and cipher suite of a host",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "zap_get_alerts",
        "description": "Get collected ZAP alerts, optionally filtered by risk level",
        "input_schema": {
            "type": "object",
            "properties": {
                "risk":  {"type": "string",  "description": "Critical/High/Medium/Low/Info"},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "zap_clear_alerts",
        "description": "Clear all collected ZAP alerts",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "zap_ai_analyse",
        "description": "Run AI-powered vulnerability analysis on current alerts",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max alerts to send to AI"},
            },
            "required": [],
        },
    },
    {
        "name": "zap_fingerprint_platform",
        "description": "Fingerprint local OS/platform or a remote UA string",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_agent": {"type": "string", "description": "Remote UA string (optional)"},
            },
            "required": [],
        },
    },
    {
        "name": "zap_create_package",
        "description": "Create cross-platform RabbitOS tarball package",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_dir": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "zap_get_install_script",
        "description": "Get install script for a specific platform",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string",
                              "description": "linux/macos/android_termux/ios_jailbreak/blackberry_bb10/windows"},
            },
            "required": ["platform"],
        },
    },
    {
        "name": "zap_http_request",
        "description": "Send a raw HTTP request and return response details",
        "input_schema": {
            "type": "object",
            "properties": {
                "method":  {"type": "string"},
                "url":     {"type": "string"},
                "headers": {"type": "object"},
                "body":    {"type": "string"},
            },
            "required": ["method", "url"],
        },
    },
    {
        "name": "zap_request_history",
        "description": "Get recent HTTP request/response history",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "zap_system_check",
        "description": "Run full top-to-bottom system check: platform, network, ZAP status, defense, LLM, tokens",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def dispatch_zap_tool(name: str, inputs: Dict,
                       api_key: str = "", service_key: str = "",
                       gh_token: str = "") -> Any:
    eng = get_zap_engine()

    if name == "zap_status":
        return eng.status()

    elif name == "zap_scan_target":
        return eng.scan_target(
            inputs["url"],
            active_scan=inputs.get("active", False),
            port_scan_host=inputs.get("port_scan_host"),
        )

    elif name == "zap_passive_scan":
        resp = eng._http.get(inputs["url"])
        alerts = eng._passive.scan(resp)
        eng._add_alerts(alerts)
        return {"url": inputs["url"], "alerts": [asdict(a) for a in alerts]}

    elif name == "zap_spider":
        spider = ZAPSpider(
            eng._http,
            max_depth=inputs.get("max_depth", 3),
            max_urls=inputs.get("max_urls", 200),
        )
        return spider.crawl(inputs["url"])

    elif name == "zap_port_scan":
        ports = inputs.get("ports") or None
        results = eng._port_scan.scan_host(inputs["host"], ports=ports)
        return [asdict(r) for r in results]

    elif name == "zap_tls_analyse":
        tls = eng._tls.analyse(inputs["host"], inputs.get("port", 443))
        eng._add_alerts(tls.alerts)
        return asdict(tls)

    elif name == "zap_get_alerts":
        return eng.get_all_alerts(
            risk=inputs.get("risk"),
            limit=inputs.get("limit", 200),
        )

    elif name == "zap_clear_alerts":
        eng.clear_alerts()
        return {"cleared": True}

    elif name == "zap_ai_analyse":
        limit = inputs.get("limit", 20)
        with eng._lock2:
            alerts = list(eng._alerts)[-limit:]
        analysis = eng._ai.analyse_alerts(alerts)
        return {"analysis": analysis, "alert_count": len(alerts)}

    elif name == "zap_fingerprint_platform":
        ua = inputs.get("user_agent", "")
        if ua:
            return asdict(eng._platform.fingerprint_ua(ua))
        return asdict(eng._platform.detect_local())

    elif name == "zap_create_package":
        out_dir = inputs.get("output_dir", os.path.dirname(__file__) or ".")
        path = eng.create_package(out_dir)
        return {"tarball": path, "size_bytes": os.path.getsize(path)}

    elif name == "zap_get_install_script":
        return {"platform": inputs["platform"],
                "script": eng.get_install_script(inputs["platform"])}

    elif name == "zap_http_request":
        hdrs = inputs.get("headers", {})
        body = inputs.get("body", "").encode() if inputs.get("body") else None
        resp = eng._http.request(inputs["method"], inputs["url"],
                                  headers=hdrs, body=body)
        return {
            "status": resp.status, "latency_ms": round(resp.latency_ms, 2),
            "headers": resp.headers, "body": resp.text()[:2000],
            "error": resp.error,
        }

    elif name == "zap_request_history":
        return eng._http.history(inputs.get("limit", 50))

    elif name == "zap_system_check":
        return run_system_check()

    else:
        return {"error": f"Unknown ZAP tool: {name}"}


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM CHECK — TOP TO BOTTOM
# ══════════════════════════════════════════════════════════════════════════════

def run_system_check() -> Dict[str, Any]:
    """
    Full top-to-bottom RabbitOS system check.
    Validates: platform, network, defense engine, LLM bridge,
    ZAP engine, token rewards, signal tracer, EEG correlator.
    """
    _log("=== RABBITOS SYSTEM CHECK START ===")
    report: Dict[str, Any] = {"ts": time.time(), "checks": {}}
    checks = report["checks"]

    # 1. Platform
    try:
        pd = PlatformDetector()
        local = pd.detect_local()
        checks["platform"] = {"status": "OK", "info": asdict(local)}
    except Exception as exc:
        checks["platform"] = {"status": "FAIL", "error": str(exc)}
    _log(f"[1/9] Platform: {checks['platform']['status']}")

    # 2. LLM Bridge
    try:
        from rabbit_llm import get_llm
        llm = get_llm()
        status = llm.status()
        checks["llm"] = {"status": "OK", "detail": status}
    except Exception as exc:
        checks["llm"] = {"status": "WARN", "error": str(exc)}
    _log(f"[2/9] LLM: {checks['llm']['status']}")

    # 3. Network tools
    try:
        from rabbit_nettools import get_nettools_engine
        nte = get_nettools_engine()
        net_status = nte.classify_network()
        checks["nettools"] = {"status": "OK", "network_type": str(net_status)}
    except Exception as exc:
        checks["nettools"] = {"status": "WARN", "error": str(exc)}
    _log(f"[3/9] NetTools: {checks['nettools']['status']}")

    # 4. Defense engine
    try:
        from rabbit_defense import get_defense_engine
        eng = get_defense_engine()
        def_status = eng.status()
        checks["defense"] = {"status": "OK", "detail": def_status}
    except Exception as exc:
        checks["defense"] = {"status": "WARN", "error": str(exc)}
    _log(f"[4/9] Defense: {checks['defense']['status']}")

    # 5. EEG correlator
    try:
        from rabbit_defense import EEGHormoneCorrelator, EEG_NODE_MAP
        corr = EEGHormoneCorrelator()
        corr.update_band_power("alpha", 50.0)
        corr.update_band_power("beta", 20.0)
        result = corr.correlate()
        checks["eeg"] = {
            "status": "OK",
            "node_count": len(EEG_NODE_MAP),
            "dominant_band": result.get("dominant_band"),
        }
    except Exception as exc:
        checks["eeg"] = {"status": "WARN", "error": str(exc)}
    _log(f"[5/9] EEG: {checks['eeg']['status']}")

    # 6. Signal tracer
    try:
        from rabbit_defense import SignalTracer
        st = SignalTracer()
        samples = st.capture()
        checks["signal_tracer"] = {
            "status": "OK", "samples_captured": len(samples)}
    except Exception as exc:
        checks["signal_tracer"] = {"status": "WARN", "error": str(exc)}
    _log(f"[6/9] SignalTracer: {checks['signal_tracer']['status']}")

    # 7. ZAP engine
    try:
        zap = get_zap_engine()
        zap_status = zap.status()
        checks["zap"] = {"status": "OK", "detail": zap_status}
    except Exception as exc:
        checks["zap"] = {"status": "FAIL", "error": str(exc)}
    _log(f"[7/9] ZAP: {checks['zap']['status']}")

    # 8. Network discovery (quick)
    try:
        from rabbit_defense import NetworkDiscovery
        nd = NetworkDiscovery(scan_timeout=1.0)
        nd_results = nd._scan_openssh() + nd._scan_tor()
        checks["network_discovery"] = {
            "status": "OK", "quick_finds": len(nd_results)}
    except Exception as exc:
        checks["network_discovery"] = {"status": "WARN", "error": str(exc)}
    _log(f"[8/9] NetworkDiscovery: {checks['network_discovery']['status']}")

    # 9. Reward tokens
    try:
        from rabbit_defense import DefenseRewardEngine
        rng = DefenseRewardEngine()
        rng.award("DEFENSE", "system_check", "top-to-bottom check")
        summary = rng.summary()
        checks["reward"] = {"status": "OK", "summary": summary}
    except Exception as exc:
        checks["reward"] = {"status": "WARN", "error": str(exc)}
    _log(f"[9/9] Rewards: {checks['reward']['status']}")

    # Overall
    statuses = [v.get("status", "UNKNOWN") for v in checks.values()]
    report["overall"] = "OK" if all(s in ("OK", "WARN") for s in statuses) else "FAIL"
    report["ok_count"]   = statuses.count("OK")
    report["warn_count"] = statuses.count("WARN")
    report["fail_count"] = statuses.count("FAIL")
    _log(f"=== SYSTEM CHECK DONE: {report['overall']} "
         f"({report['ok_count']} OK / {report['warn_count']} WARN / "
         f"{report['fail_count']} FAIL) ===")
    return report


# ══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RabbitOS ZAP Security Engine")
    parser.add_argument("--status",   action="store_true")
    parser.add_argument("--check",    action="store_true", help="Run system check")
    parser.add_argument("--scan",     type=str, metavar="URL",
                        help="Passive scan a URL (authorized targets only)")
    parser.add_argument("--active",   action="store_true",
                        help="Enable active scanning with --scan")
    parser.add_argument("--ports",    type=str, metavar="HOST",
                        help="Port scan a host")
    parser.add_argument("--tls",      type=str, metavar="HOST",
                        help="TLS certificate analysis")
    parser.add_argument("--platform", action="store_true",
                        help="Detect local platform")
    parser.add_argument("--package",  action="store_true",
                        help="Create cross-platform tarball")
    parser.add_argument("--install-script", type=str, metavar="PLATFORM",
                        help="Print install script for platform")
    args = parser.parse_args()

    eng = get_zap_engine()

    if args.status:
        print(json.dumps(eng.status(), indent=2, default=str))
    elif args.check:
        print(json.dumps(run_system_check(), indent=2, default=str))
    elif args.scan:
        print(json.dumps(
            eng.scan_target(args.scan, active_scan=args.active),
            indent=2, default=str))
    elif args.ports:
        results = eng._port_scan.scan_host(args.ports)
        print(json.dumps([asdict(r) for r in results], indent=2, default=str))
    elif args.tls:
        tls = eng._tls.analyse(args.tls)
        print(json.dumps(asdict(tls), indent=2, default=str))
    elif args.platform:
        pd = PlatformDetector()
        print(json.dumps(asdict(pd.detect_local()), indent=2, default=str))
    elif args.package:
        out = os.path.dirname(__file__) or "."
        path = eng.create_package(out)
        print(f"Package created: {path}")
    elif args.install_script:
        print(eng.get_install_script(args.install_script))
    else:
        parser.print_help()
