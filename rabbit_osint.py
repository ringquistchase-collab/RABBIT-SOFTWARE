"""
rabbit_osint.py — RabbitOS Passive OSINT Server Origin Intelligence
Chase Allen Ringquist | RABBIT-SOFTWARE

All queries are read-only against public data infrastructure:
  - WHOIS (port 43 raw socket + IANA referral chain)
  - DNS  (A / MX / TXT / NS / CNAME / PTR via Google DNS-over-HTTPS)
  - ASN  (ipinfo.io free-tier JSON + Team Cymru DNS TXT)
  - IP geolocation (ipinfo.io)
  - Certificate Transparency (crt.sh public JSON API)
  - HTTP server header probe (HEAD only — no body fetched)
  - Reverse-IP / rDNS correlation
  - BGP prefix lookup (BGPView public API)
  - RDAP (Registration Data Access Protocol — replaces WHOIS)

Security invariants
───────────────────
shows_dna_root = False   ← DNA root NEVER stored or transmitted
TX_LICENSED    = False   ← passive read only — no write / auth bypass / injection
INJECT_IDENTITY = False  ← identity is NEVER used as an access credential here
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ── Security invariants ──────────────────────────────────────────────────────
shows_dna_root  = False
assert shows_dna_root  is False, "SECURITY: DNA root must never be exposed"
TX_LICENSED     = False
INJECT_IDENTITY = False   # identity is never used as an access mechanism

OSINT_DB  = "rabbit_osint.db"
_lock     = threading.Lock()
_UA       = "RabbitOS-OSINT/1.0 (passive research)"

# Rate-limit: max 1 request per second per external host
_rate_lock = threading.Lock()
_last_req: Dict[str, float] = {}
_RATE_GAP = 1.2   # seconds between requests to same host

def _rate_limit(host: str) -> None:
    with _rate_lock:
        last = _last_req.get(host, 0.0)
        gap  = time.time() - last
        if gap < _RATE_GAP:
            time.sleep(_RATE_GAP - gap)
        _last_req[host] = time.time()

def _http_get(url: str, timeout: int = 10) -> Optional[str]:
    host = urllib.parse.urlparse(url).netloc
    _rate_limit(host)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": _UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None

def _http_json(url: str, timeout: int = 10) -> Optional[Dict]:
    raw = _http_get(url, timeout)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return None

def _uid(prefix: str = "") -> str:
    import uuid
    return (prefix + str(uuid.uuid4()))[:48]

def _hash(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:16]

# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class WHOISRecord:
    target:       str
    whois_server: str
    raw:          str
    registrar:    str
    registrant:   str   # org name only — no PII
    created:      str
    updated:      str
    expires:      str
    name_servers: List[str] = field(default_factory=list)
    status:       List[str] = field(default_factory=list)
    ts:           float     = field(default_factory=time.time)

@dataclass
class DNSRecord:
    name:     str
    rtype:    str   # A / AAAA / MX / TXT / NS / CNAME / PTR / SOA
    value:    str
    ttl:      int   = 0
    ts:       float = field(default_factory=time.time)

@dataclass
class ASNRecord:
    ip:       str
    asn:      str
    org:      str
    country:  str
    city:     str
    region:   str
    prefix:   str
    hosting:  bool  = False   # heuristic: is this a known hosting/cloud ASN?
    ts:       float = field(default_factory=time.time)

@dataclass
class CertRecord:
    domain:       str
    common_name:  str
    issuer:       str
    not_before:   str
    not_after:    str
    san_domains:  List[str] = field(default_factory=list)
    cert_id:      int       = 0
    ts:           float     = field(default_factory=time.time)

@dataclass
class HTTPHeaderRecord:
    target:      str
    status_code: int
    server:      str
    powered_by:  str
    content_type:str
    location:    str   # redirect target if any
    headers:     Dict[str, str] = field(default_factory=dict)
    ts:          float          = field(default_factory=time.time)

@dataclass
class ServerProfile:
    target:         str
    resolved_ips:   List[str]       = field(default_factory=list)
    whois:          Optional[Dict]  = None
    asn:            Optional[Dict]  = None
    dns_records:    List[Dict]      = field(default_factory=list)
    certs:          List[Dict]      = field(default_factory=list)
    http_headers:   Optional[Dict]  = None
    rdap:           Optional[Dict]  = None
    bgp_prefixes:   List[str]       = field(default_factory=list)
    reverse_hosts:  List[str]       = field(default_factory=list)
    related_domains:List[str]       = field(default_factory=list)
    risk_indicators:List[str]       = field(default_factory=list)
    ts:             float           = field(default_factory=time.time)

# ── Database ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(OSINT_DB)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS whois_records (
            target TEXT, whois_server TEXT, raw TEXT,
            registrar TEXT, registrant TEXT,
            created TEXT, updated TEXT, expires TEXT,
            name_servers TEXT, status TEXT, ts REAL,
            PRIMARY KEY (target)
        );
        CREATE TABLE IF NOT EXISTS dns_records (
            id TEXT PRIMARY KEY, name TEXT, rtype TEXT,
            value TEXT, ttl INTEGER, ts REAL
        );
        CREATE TABLE IF NOT EXISTS asn_records (
            ip TEXT PRIMARY KEY, asn TEXT, org TEXT,
            country TEXT, city TEXT, region TEXT,
            prefix TEXT, hosting INTEGER, ts REAL
        );
        CREATE TABLE IF NOT EXISTS cert_records (
            cert_id INTEGER, domain TEXT, common_name TEXT,
            issuer TEXT, not_before TEXT, not_after TEXT,
            san_domains TEXT, ts REAL,
            PRIMARY KEY (cert_id, domain)
        );
        CREATE TABLE IF NOT EXISTS http_records (
            target TEXT PRIMARY KEY, status_code INTEGER,
            server TEXT, powered_by TEXT, content_type TEXT,
            location TEXT, headers TEXT, ts REAL
        );
        CREATE TABLE IF NOT EXISTS server_profiles (
            target TEXT PRIMARY KEY, data TEXT, ts REAL
        );
        CREATE TABLE IF NOT EXISTS osint_queries (
            query_id TEXT PRIMARY KEY, target TEXT,
            query_type TEXT, result_summary TEXT, ts REAL
        );
    """)
    con.commit()
    return con

def _log_query(target: str, qtype: str, summary: str) -> None:
    try:
        with _db() as con:
            con.execute(
                "INSERT OR REPLACE INTO osint_queries VALUES (?,?,?,?,?)",
                (_uid("q_"), target, qtype, summary[:200], time.time()))
    except Exception:
        pass

# ── WHOIS Probe ───────────────────────────────────────────────────────────────

# Known WHOIS servers per TLD
_WHOIS_SERVERS: Dict[str, str] = {
    "com": "whois.verisign-grs.com",
    "net": "whois.verisign-grs.com",
    "org": "whois.pir.org",
    "io":  "whois.nic.io",
    "co":  "whois.nic.co",
    "uk":  "whois.nic.uk",
    "de":  "whois.denic.de",
    "ru":  "whois.tcinet.ru",
    "cn":  "whois.cnnic.cn",
    "au":  "whois.auda.org.au",
    "ca":  "whois.cira.ca",
    "fr":  "whois.nic.fr",
    "nl":  "whois.domain-registry.nl",
    "br":  "whois.registro.br",
    "in":  "whois.registry.in",
    "jp":  "whois.jprs.jp",
    "eu":  "whois.eu",
    "us":  "whois.nic.us",
    "gov": "whois.dotgov.gov",
    "edu": "whois.educause.edu",
}
_IANA_WHOIS = "whois.iana.org"

_WHOIS_FIELDS = {
    "registrar":   re.compile(r"(?:Registrar|registrar):\s*(.+)"),
    "registrant":  re.compile(r"(?:Registrant Organization|org):\s*(.+)"),
    "created":     re.compile(r"(?:Creation Date|created):\s*(.+)"),
    "updated":     re.compile(r"(?:Updated Date|changed|last-modified):\s*(.+)"),
    "expires":     re.compile(r"(?:Registry Expiry Date|Expiry Date|expire):\s*(.+)"),
    "name_server": re.compile(r"(?:Name Server|nserver):\s*(.+)", re.IGNORECASE),
    "status":      re.compile(r"(?:Domain Status|status):\s*(.+)", re.IGNORECASE),
    "refer":       re.compile(r"refer:\s*(.+)"),
    "whois":       re.compile(r"(?:Registrar WHOIS Server|whois):\s*(\S+)"),
}

def _whois_raw(target: str, server: str, port: int = 43,
               timeout: int = 10) -> str:
    _rate_limit(server)
    try:
        with socket.create_connection((server, port), timeout=timeout) as s:
            s.sendall((target.strip() + "\r\n").encode())
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            return data.decode("utf-8", errors="replace")
    except Exception as e:
        return f"; WHOIS error: {e}"

def _parse_whois(raw: str, target: str, server: str) -> WHOISRecord:
    def first(pattern: re.Pattern) -> str:
        m = pattern.search(raw)
        return m.group(1).strip() if m else ""

    name_servers = [m.group(1).strip().lower()
                    for m in _WHOIS_FIELDS["name_server"].finditer(raw)]
    statuses     = [m.group(1).strip()
                    for m in _WHOIS_FIELDS["status"].finditer(raw)]

    # Follow referral server if present
    ref = first(_WHOIS_FIELDS["whois"]) or first(_WHOIS_FIELDS["refer"])
    if ref and ref != server and "." in ref:
        raw2 = _whois_raw(target, ref)
        if raw2 and ";" not in raw2[:5]:
            raw  = raw2
            server = ref
            name_servers = [m.group(1).strip().lower()
                            for m in _WHOIS_FIELDS["name_server"].finditer(raw)] or name_servers
            statuses = [m.group(1).strip()
                        for m in _WHOIS_FIELDS["status"].finditer(raw)] or statuses

    return WHOISRecord(
        target=target, whois_server=server, raw=raw[:8000],
        registrar=first(_WHOIS_FIELDS["registrar"]),
        registrant=first(_WHOIS_FIELDS["registrant"]),
        created=first(_WHOIS_FIELDS["created"]),
        updated=first(_WHOIS_FIELDS["updated"]),
        expires=first(_WHOIS_FIELDS["expires"]),
        name_servers=list(dict.fromkeys(name_servers))[:10],
        status=list(dict.fromkeys(statuses))[:10],
    )

class WHOISProbe:
    def lookup(self, target: str) -> WHOISRecord:
        target = target.strip().lower().rstrip(".")
        # Pick WHOIS server
        if _is_ip(target):
            server = _IANA_WHOIS
        else:
            tld = target.rsplit(".", 1)[-1]
            server = _WHOIS_SERVERS.get(tld, _IANA_WHOIS)

        raw = _whois_raw(target, server)
        rec = _parse_whois(raw, target, server)
        _log_query(target, "whois", f"registrar={rec.registrar} ns={len(rec.name_servers)}")
        try:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO whois_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (rec.target, rec.whois_server, rec.raw, rec.registrar,
                     rec.registrant, rec.created, rec.updated, rec.expires,
                     json.dumps(rec.name_servers), json.dumps(rec.status), rec.ts))
        except Exception:
            pass
        return rec

# ── DNS Probe ─────────────────────────────────────────────────────────────────

_DOH = "https://dns.google/resolve"   # Google DNS-over-HTTPS — public

_DNS_TYPES = {
    "A": 1, "AAAA": 28, "MX": 15, "TXT": 16,
    "NS": 2, "CNAME": 5, "PTR": 12, "SOA": 6,
}

class DNSProbe:
    def query(self, name: str, rtype: str = "A") -> List[DNSRecord]:
        name   = name.strip().rstrip(".")
        rtype  = rtype.upper()
        rnum   = _DNS_TYPES.get(rtype, rtype)
        url    = f"{_DOH}?name={urllib.parse.quote(name)}&type={rnum}"
        data   = _http_json(url)
        records: List[DNSRecord] = []
        if not data:
            return records

        for ans in data.get("Answer", []):
            rdata = str(ans.get("data", "")).strip()
            r = DNSRecord(
                name=name, rtype=rtype,
                value=rdata, ttl=int(ans.get("TTL", 0)))
            records.append(r)
            try:
                with _db() as con:
                    con.execute(
                        "INSERT OR REPLACE INTO dns_records VALUES (?,?,?,?,?,?)",
                        (_uid("dns_"), r.name, r.rtype, r.value, r.ttl, r.ts))
            except Exception:
                pass
        _log_query(name, f"dns_{rtype}", f"{len(records)} records")
        return records

    def all_records(self, domain: str) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for rtype in ("A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA"):
            recs = self.query(domain, rtype)
            if recs:
                result[rtype] = [r.value for r in recs]
        return result

    def reverse(self, ip: str) -> List[str]:
        try:
            addr = ipaddress.ip_address(ip)
            if addr.version == 4:
                arpa = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
            else:
                rev = addr.exploded.replace(":", "")
                arpa = ".".join(reversed(list(rev))) + ".ip6.arpa"
            recs = self.query(arpa, "PTR")
            return [r.value for r in recs]
        except Exception:
            return []

    def resolve_ips(self, domain: str) -> List[str]:
        a4  = [r.value for r in self.query(domain, "A")]
        a6  = [r.value for r in self.query(domain, "AAAA")]
        return list(dict.fromkeys(a4 + a6))

# ── ASN / IP Info Probe ───────────────────────────────────────────────────────

# Well-known hosting/cloud ASN orgs (heuristic)
_CLOUD_ORGS = {
    "amazon", "aws", "google", "microsoft", "azure", "cloudflare",
    "digitalocean", "linode", "akamai", "fastly", "hetzner",
    "ovh", "vultr", "choopa", "choopa.net", "leaseweb",
    "contabo", "datacamp", "m247", "serverius", "hostinger",
}

def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False

def _is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False

class ASNProbe:
    """IP geolocation + ASN via ipinfo.io (free tier, no auth for basic fields)."""

    def lookup(self, ip: str) -> ASNRecord:
        if _is_private(ip):
            return ASNRecord(ip=ip, asn="private", org="private network",
                             country="", city="", region="", prefix="")

        data = _http_json(f"https://ipinfo.io/{ip}/json") or {}
        org  = data.get("org", "")          # e.g. "AS13335 Cloudflare, Inc."
        asn  = ""
        if org and org.startswith("AS"):
            parts = org.split(" ", 1)
            asn   = parts[0]
            org   = parts[1] if len(parts) > 1 else org

        hosting = any(h in org.lower() for h in _CLOUD_ORGS)
        rec = ASNRecord(
            ip=ip, asn=asn, org=org,
            country=data.get("country", ""),
            city=data.get("city", ""),
            region=data.get("region", ""),
            prefix=data.get("prefix", ""),
            hosting=hosting)

        try:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO asn_records VALUES (?,?,?,?,?,?,?,?,?)",
                    (rec.ip, rec.asn, rec.org, rec.country, rec.city,
                     rec.region, rec.prefix, int(rec.hosting), rec.ts))
        except Exception:
            pass
        _log_query(ip, "asn", f"asn={rec.asn} org={rec.org[:40]} country={rec.country}")
        return rec

    def lookup_domain(self, domain: str) -> List[ASNRecord]:
        dns = DNSProbe()
        ips = dns.resolve_ips(domain)
        return [self.lookup(ip) for ip in ips if not _is_private(ip)]

    def cymru_asn(self, ip: str) -> Optional[str]:
        """Team Cymru DNS-based ASN lookup (fallback)."""
        try:
            addr = ipaddress.ip_address(ip)
            if addr.version == 4:
                rev = ".".join(reversed(ip.split("."))) + ".origin.asn.cymru.com"
            else:
                exp = addr.exploded.replace(":", "")
                rev = ".".join(reversed(list(exp))) + ".origin6.asn.cymru.com"
            recs = DNSProbe().query(rev, "TXT")
            return recs[0].value if recs else None
        except Exception:
            return None

# ── BGP Prefix Probe ──────────────────────────────────────────────────────────

class BGPProbe:
    """Read-only BGPView public API queries."""

    def prefixes_for_asn(self, asn: str) -> List[str]:
        asn = asn.lstrip("AS").lstrip("as")
        data = _http_json(f"https://api.bgpview.io/asn/{asn}/prefixes")
        if not data:
            return []
        prefixes = []
        for p in data.get("data", {}).get("ipv4_prefixes", []):
            prefixes.append(p.get("prefix", ""))
        for p in data.get("data", {}).get("ipv6_prefixes", []):
            prefixes.append(p.get("prefix", ""))
        return [x for x in prefixes if x][:30]

    def asn_details(self, asn: str) -> Dict:
        asn = asn.lstrip("AS").lstrip("as")
        data = _http_json(f"https://api.bgpview.io/asn/{asn}")
        if not data:
            return {}
        d = data.get("data", {})
        return {
            "asn":         d.get("asn"),
            "name":        d.get("name", ""),
            "description": d.get("description_short", ""),
            "country":     d.get("country_code", ""),
            "website":     d.get("website", ""),
            "email_contacts": [_hash(e) for e in d.get("email_contacts", [])],
        }

    def ip_prefixes(self, ip: str) -> Dict:
        data = _http_json(f"https://api.bgpview.io/ip/{ip}")
        if not data:
            return {}
        d = data.get("data", {})
        prefixes = d.get("prefixes", [])
        return {
            "ip":       ip,
            "prefixes": [p.get("prefix") for p in prefixes],
            "asns":     list(dict.fromkeys(
                            str(p.get("asn", {}).get("asn", "")) for p in prefixes))[:5],
        }

# ── Certificate Transparency Probe ───────────────────────────────────────────

class CertTransparencyProbe:
    """Read-only crt.sh public certificate transparency log queries."""

    def lookup(self, domain: str, limit: int = 20) -> List[CertRecord]:
        url  = (f"https://crt.sh/?q={urllib.parse.quote(domain)}"
                f"&output=json&deduplicate=Y")
        data = _http_json(url)
        if not data or not isinstance(data, list):
            return []

        records: List[CertRecord] = []
        seen: set = set()
        for entry in data[:limit * 3]:
            cn = entry.get("common_name", "")
            if cn in seen:
                continue
            seen.add(cn)

            name_value = entry.get("name_value", "")
            sans = list(dict.fromkeys(
                n.strip() for n in name_value.split("\n") if n.strip()))

            rec = CertRecord(
                domain=domain,
                common_name=cn,
                issuer=entry.get("issuer_name", "")[:120],
                not_before=entry.get("not_before", ""),
                not_after=entry.get("not_after", ""),
                san_domains=sans[:20],
                cert_id=int(entry.get("id", 0)))
            records.append(rec)
            try:
                with _db() as con:
                    con.execute(
                        "INSERT OR REPLACE INTO cert_records VALUES (?,?,?,?,?,?,?,?)",
                        (rec.cert_id, rec.domain, rec.common_name, rec.issuer,
                         rec.not_before, rec.not_after,
                         json.dumps(rec.san_domains), rec.ts))
            except Exception:
                pass
            if len(records) >= limit:
                break

        _log_query(domain, "cert_transparency", f"{len(records)} certs found")
        return records

    def related_domains(self, domain: str) -> List[str]:
        """Return unique domains found in SAN fields across all certs for a domain."""
        certs   = self.lookup(domain, limit=50)
        related = set()
        for c in certs:
            for san in c.san_domains:
                san = san.lstrip("*.").strip()
                if san and san != domain:
                    related.add(san)
        return sorted(related)[:100]

# ── HTTP Header Probe ─────────────────────────────────────────────────────────

_INTERESTING_HEADERS = {
    "server", "x-powered-by", "x-generator", "x-drupal-cache",
    "x-wp-nonce", "x-shopify-stage", "x-amzn-requestid",
    "x-varnish", "x-cache", "cf-ray", "x-github-request-id",
    "x-azure-ref", "x-ms-request-id", "via", "x-forwarded-server",
    "x-backend-server", "x-application-context",
}

class HTTPHeaderProbe:
    def probe(self, target: str, port: int = 443,
              use_tls: bool = True) -> HTTPHeaderRecord:
        if not target.startswith("http"):
            scheme = "https" if use_tls else "http"
            url    = f"{scheme}://{target}"
        else:
            url = target

        _rate_limit(urllib.parse.urlparse(url).netloc)
        headers_out: Dict[str, str] = {}
        status  = 0
        server  = ""
        powered = ""
        ctype   = ""
        loc     = ""

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": _UA},
                method="HEAD")
            try:
                resp = urllib.request.urlopen(req, timeout=8)
                status = resp.status
                raw_hdrs = dict(resp.headers)
            except urllib.error.HTTPError as e:
                status   = e.code
                raw_hdrs = dict(e.headers) if e.headers else {}

            for k, v in raw_hdrs.items():
                kl = k.lower()
                if kl in _INTERESTING_HEADERS:
                    headers_out[kl] = v[:200]

            server  = headers_out.get("server", "")
            powered = headers_out.get("x-powered-by", "")
            ctype   = raw_hdrs.get("Content-Type", "")[:80]
            loc     = raw_hdrs.get("Location", "")[:200]

        except Exception as e:
            headers_out["_error"] = str(e)[:120]

        rec = HTTPHeaderRecord(
            target=target, status_code=status,
            server=server, powered_by=powered,
            content_type=ctype, location=loc,
            headers=headers_out)

        try:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO http_records VALUES (?,?,?,?,?,?,?,?)",
                    (rec.target, rec.status_code, rec.server, rec.powered_by,
                     rec.content_type, rec.location,
                     json.dumps(rec.headers), rec.ts))
        except Exception:
            pass
        _log_query(target, "http_headers",
                   f"status={status} server={server[:40]}")
        return rec

# ── RDAP Probe ────────────────────────────────────────────────────────────────

class RDAPProbe:
    """RDAP — the modern JSON replacement for WHOIS."""

    _RDAP_BOOTSTRAP = "https://rdap.org"

    def lookup_domain(self, domain: str) -> Dict:
        url  = f"{self._RDAP_BOOTSTRAP}/domain/{urllib.parse.quote(domain)}"
        data = _http_json(url) or {}
        return self._clean(data)

    def lookup_ip(self, ip: str) -> Dict:
        url  = f"{self._RDAP_BOOTSTRAP}/ip/{urllib.parse.quote(ip)}"
        data = _http_json(url) or {}
        return self._clean(data)

    def lookup_asn(self, asn: str) -> Dict:
        asn_num = asn.lstrip("AS").lstrip("as")
        url  = f"{self._RDAP_BOOTSTRAP}/autnum/{asn_num}"
        data = _http_json(url) or {}
        return self._clean(data)

    def _clean(self, data: Dict) -> Dict:
        """Return only non-PII useful fields."""
        if not data:
            return {}
        out = {}
        safe_keys = {
            "objectClassName", "handle", "ldhName", "unicodeName",
            "status", "type", "startAddress", "endAddress",
            "ipVersion", "name", "startAutnum", "endAutnum",
        }
        for k in safe_keys:
            if k in data:
                out[k] = data[k]
        # Events (registration dates)
        events = []
        for ev in data.get("events", []):
            events.append({
                "action": ev.get("eventAction", ""),
                "date":   ev.get("eventDate", "")[:20]})
        if events:
            out["events"] = events
        # Name servers
        ns = [n.get("ldhName", "") for n in data.get("nameservers", [])]
        if ns:
            out["nameservers"] = [x for x in ns if x]
        # Entities — only org name, no personal names/addresses
        orgs = []
        for ent in data.get("entities", []):
            for role in ent.get("roles", []):
                if role in ("registrar", "abuse", "noc", "technical"):
                    vcard = ent.get("vcardArray", [None, []])[1]
                    for v in vcard:
                        if isinstance(v, list) and v[0] == "fn":
                            orgs.append({"role": role, "name": v[3]})
                            break
        if orgs:
            out["entities"] = orgs
        return out

# ── Risk Indicator Heuristics ─────────────────────────────────────────────────

def _assess_risk(profile: ServerProfile) -> List[str]:
    indicators = []

    # Hosting/VPS — common for C2, botnets
    asn_d = profile.asn or {}
    if asn_d.get("hosting"):
        indicators.append(f"hosted on cloud/VPS ({asn_d.get('org','')})")

    # No WHOIS registrant info
    wh = profile.whois or {}
    if not wh.get("registrant") and not wh.get("registrar"):
        indicators.append("WHOIS registrant/registrar hidden or missing")

    # Privacy-protected or proxy registration
    for s in wh.get("status", []):
        if "privacy" in s.lower() or "proxy" in s.lower():
            indicators.append(f"privacy/proxy registration: {s}")

    # Expiry-soon or recently-created (common for malicious infra)
    expires = wh.get("expires", "")
    created = wh.get("created", "")
    if expires and "2024" in expires:
        indicators.append("domain expires soon (2024)")
    if created:
        try:
            yr = int(created[:4])
            if yr >= 2023:
                indicators.append(f"recently registered ({created[:10]})")
        except ValueError:
            pass

    # More cert SANs than expected (infra sharing)
    if len(profile.certs) > 5:
        indicators.append(f"high cert transparency hits ({len(profile.certs)})")

    # No HTTP response
    hh = profile.http_headers or {}
    if hh.get("status_code", 0) == 0:
        indicators.append("no HTTP response (server may be hidden or filtered)")

    # Server fingerprint
    server_hdr = hh.get("server", "")
    if server_hdr:
        if any(x in server_hdr.lower() for x in ["cloudflare", "nginx", "apache"]):
            pass  # normal
        else:
            indicators.append(f"unusual server header: {server_hdr}")

    return indicators

# ── ServerOriginIntel ─────────────────────────────────────────────────────────

class ServerOriginIntel:
    """
    Combines all passive probes into a unified server profile.
    All queries are read-only against public infrastructure.
    """

    def __init__(self) -> None:
        self.whois = WHOISProbe()
        self.dns   = DNSProbe()
        self.asn   = ASNProbe()
        self.bgp   = BGPProbe()
        self.cert  = CertTransparencyProbe()
        self.http  = HTTPHeaderProbe()
        self.rdap  = RDAPProbe()

    def profile(self, target: str,
                deep: bool = False) -> ServerProfile:
        """
        Full passive profile for a domain or IP.
        deep=True also fetches BGP prefixes and all cert SANs.
        """
        assert TX_LICENSED    is False
        assert INJECT_IDENTITY is False

        is_ip     = _is_ip(target)
        prof      = ServerProfile(target=target)

        # 1 — DNS resolution (for domains)
        if not is_ip:
            prof.resolved_ips = self.dns.resolve_ips(target)
            dns_all = self.dns.all_records(target)
            prof.dns_records  = [
                {"type": t, "values": vs}
                for t, vs in dns_all.items()
            ]
        else:
            prof.resolved_ips = [target]

        # 2 — WHOIS
        try:
            wh = self.whois.lookup(target)
            prof.whois = {
                "registrar":    wh.registrar,
                "registrant":   wh.registrant,
                "created":      wh.created,
                "updated":      wh.updated,
                "expires":      wh.expires,
                "name_servers": wh.name_servers,
                "status":       wh.status,
                "whois_server": wh.whois_server,
            }
        except Exception:
            pass

        # 3 — ASN / geolocation for first resolved IP
        for ip in prof.resolved_ips[:2]:
            try:
                asn_rec = self.asn.lookup(ip)
                prof.asn = asdict(asn_rec)
                # rDNS
                rev = self.dns.reverse(ip)
                prof.reverse_hosts.extend(rev)
                break
            except Exception:
                pass

        # 4 — RDAP
        try:
            if is_ip:
                prof.rdap = self.rdap.lookup_ip(target)
            else:
                prof.rdap = self.rdap.lookup_domain(target)
        except Exception:
            pass

        # 5 — Cert transparency
        if not is_ip:
            try:
                certs = self.cert.lookup(target, limit=10)
                prof.certs = [asdict(c) for c in certs]
                if deep:
                    prof.related_domains = self.cert.related_domains(target)
            except Exception:
                pass

        # 6 — HTTP headers (non-blocking)
        try:
            hh = self.http.probe(target)
            prof.http_headers = asdict(hh)
        except Exception:
            pass

        # 7 — BGP prefixes (deep only)
        if deep and prof.asn and prof.asn.get("asn"):
            try:
                prof.bgp_prefixes = self.bgp.prefixes_for_asn(prof.asn["asn"])
            except Exception:
                pass

        # 8 — Risk indicators
        prof.risk_indicators = _assess_risk(prof)

        # Persist profile
        try:
            with _db() as con:
                con.execute(
                    "INSERT OR REPLACE INTO server_profiles VALUES (?,?,?)",
                    (target, json.dumps(asdict(prof), default=str), prof.ts))
        except Exception:
            pass

        _log_query(target, "full_profile",
                   f"ips={len(prof.resolved_ips)} risks={len(prof.risk_indicators)}")
        return prof

    def quick_lookup(self, target: str) -> Dict:
        """WHOIS + ASN only — fast, minimal."""
        result: Dict[str, Any] = {"target": target}
        if not _is_ip(target):
            ips = self.dns.resolve_ips(target)
            result["ips"] = ips
        else:
            ips = [target]
        if ips:
            asn_rec = self.asn.lookup(ips[0])
            result["asn"] = asdict(asn_rec)
        wh = self.whois.lookup(target)
        result["whois"] = {
            "registrar":  wh.registrar,
            "registrant": wh.registrant,
            "created":    wh.created,
            "expires":    wh.expires,
        }
        return result

# ── OSINTOrchestrator singleton ───────────────────────────────────────────────

class OSINTOrchestrator:
    _instance: Optional["OSINTOrchestrator"] = None

    def __init__(self) -> None:
        self.intel = ServerOriginIntel()
        self.whois = WHOISProbe()
        self.dns   = DNSProbe()
        self.asn   = ASNProbe()
        self.bgp   = BGPProbe()
        self.cert  = CertTransparencyProbe()
        self.http  = HTTPHeaderProbe()
        self.rdap  = RDAPProbe()

    @classmethod
    def get(cls) -> "OSINTOrchestrator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def query_history(self, limit: int = 50) -> List[Dict]:
        try:
            with _db() as con:
                rows = con.execute(
                    "SELECT * FROM osint_queries ORDER BY ts DESC LIMIT ?",
                    (limit,)).fetchall()
            return [{"query_id": r[0], "target": r[1], "type": r[2],
                     "summary": r[3], "ts": r[4]} for r in rows]
        except Exception:
            return []

    def cached_profile(self, target: str) -> Optional[Dict]:
        try:
            with _db() as con:
                row = con.execute(
                    "SELECT data, ts FROM server_profiles WHERE target=?",
                    (target,)).fetchone()
            if row:
                return json.loads(row[0])
        except Exception:
            pass
        return None

    def bulk_profile(self, targets: List[str],
                     deep: bool = False) -> List[Dict]:
        results = []
        for t in targets[:10]:
            try:
                prof = self.intel.profile(t.strip(), deep=deep)
                results.append(asdict(prof))
            except Exception as e:
                results.append({"target": t, "error": str(e)})
        return results

def get_osint() -> OSINTOrchestrator:
    return OSINTOrchestrator.get()

# ── Tool definitions ──────────────────────────────────────────────────────────

OSINT_TOOLS: List[Dict] = [
    # Full profiles
    {"name": "osint_server_profile",
     "description": ("Full passive server origin profile: WHOIS, DNS, ASN, geolocation, "
                     "cert transparency, HTTP headers, RDAP, BGP (deep mode), risk indicators. "
                     "Read-only — no authentication bypass, no credential injection."),
     "input_schema": {"type": "object", "required": ["target"],
                      "properties": {
                          "target": {"type": "string",
                                     "description": "Domain name or IP address"},
                          "deep":   {"type": "boolean",
                                     "description": "Also fetch BGP prefixes and all cert SANs (slower)"}}}},
    {"name": "osint_quick_lookup",
     "description": "Fast WHOIS + ASN lookup for a domain or IP.",
     "input_schema": {"type": "object", "required": ["target"],
                      "properties": {"target": {"type": "string"}}}},
    {"name": "osint_bulk_profile",
     "description": "Profile up to 10 targets at once.",
     "input_schema": {"type": "object", "required": ["targets"],
                      "properties": {
                          "targets": {"type": "array", "items": {"type": "string"},
                                      "maxItems": 10},
                          "deep":    {"type": "boolean"}}}},
    {"name": "osint_cached_profile",
     "description": "Return previously cached profile for a target (no new queries).",
     "input_schema": {"type": "object", "required": ["target"],
                      "properties": {"target": {"type": "string"}}}},

    # WHOIS
    {"name": "osint_whois",
     "description": "Raw WHOIS lookup for a domain or IP address.",
     "input_schema": {"type": "object", "required": ["target"],
                      "properties": {"target": {"type": "string"}}}},

    # DNS
    {"name": "osint_dns_all",
     "description": "Query all DNS record types (A, AAAA, MX, TXT, NS, CNAME, SOA) for a domain.",
     "input_schema": {"type": "object", "required": ["domain"],
                      "properties": {"domain": {"type": "string"}}}},
    {"name": "osint_dns_query",
     "description": "Query a specific DNS record type for a name.",
     "input_schema": {"type": "object", "required": ["name", "rtype"],
                      "properties": {
                          "name":  {"type": "string"},
                          "rtype": {"type": "string",
                                    "enum": ["A","AAAA","MX","TXT","NS","CNAME","PTR","SOA"]}}}},
    {"name": "osint_reverse_dns",
     "description": "Reverse DNS (PTR) lookup for an IP address.",
     "input_schema": {"type": "object", "required": ["ip"],
                      "properties": {"ip": {"type": "string"}}}},
    {"name": "osint_resolve_ips",
     "description": "Resolve a domain to its IP addresses.",
     "input_schema": {"type": "object", "required": ["domain"],
                      "properties": {"domain": {"type": "string"}}}},

    # ASN / Geo
    {"name": "osint_asn_lookup",
     "description": "ASN and geolocation for an IP address (country, city, org, hosting flag).",
     "input_schema": {"type": "object", "required": ["ip"],
                      "properties": {"ip": {"type": "string"}}}},
    {"name": "osint_asn_for_domain",
     "description": "Resolve domain to IPs then look up ASN/geo for each.",
     "input_schema": {"type": "object", "required": ["domain"],
                      "properties": {"domain": {"type": "string"}}}},
    {"name": "osint_cymru_asn",
     "description": "Team Cymru DNS-based ASN lookup (raw TXT record) for an IP.",
     "input_schema": {"type": "object", "required": ["ip"],
                      "properties": {"ip": {"type": "string"}}}},

    # BGP
    {"name": "osint_bgp_asn_details",
     "description": "BGPView details for an ASN: name, description, country, prefixes.",
     "input_schema": {"type": "object", "required": ["asn"],
                      "properties": {"asn": {"type": "string",
                                             "description": "e.g. AS13335 or 13335"}}}},
    {"name": "osint_bgp_asn_prefixes",
     "description": "All IP prefixes announced by an ASN.",
     "input_schema": {"type": "object", "required": ["asn"],
                      "properties": {"asn": {"type": "string"}}}},
    {"name": "osint_bgp_ip_prefixes",
     "description": "BGP prefix and ASN info for a specific IP address.",
     "input_schema": {"type": "object", "required": ["ip"],
                      "properties": {"ip": {"type": "string"}}}},

    # Cert transparency
    {"name": "osint_cert_lookup",
     "description": "Certificate transparency log lookup (crt.sh) for a domain — reveals all issued certs.",
     "input_schema": {"type": "object", "required": ["domain"],
                      "properties": {
                          "domain": {"type": "string"},
                          "limit":  {"type": "integer"}}}},
    {"name": "osint_cert_related_domains",
     "description": "Find all domains sharing certificates with a target domain via SAN fields.",
     "input_schema": {"type": "object", "required": ["domain"],
                      "properties": {"domain": {"type": "string"}}}},

    # HTTP headers
    {"name": "osint_http_headers",
     "description": "Passive HTTP HEAD request — returns server, x-powered-by, and other fingerprinting headers.",
     "input_schema": {"type": "object", "required": ["target"],
                      "properties": {
                          "target":  {"type": "string"},
                          "use_tls": {"type": "boolean"}}}},

    # RDAP
    {"name": "osint_rdap_domain",
     "description": "RDAP (modern WHOIS) lookup for a domain.",
     "input_schema": {"type": "object", "required": ["domain"],
                      "properties": {"domain": {"type": "string"}}}},
    {"name": "osint_rdap_ip",
     "description": "RDAP lookup for an IP address.",
     "input_schema": {"type": "object", "required": ["ip"],
                      "properties": {"ip": {"type": "string"}}}},
    {"name": "osint_rdap_asn",
     "description": "RDAP lookup for an ASN.",
     "input_schema": {"type": "object", "required": ["asn"],
                      "properties": {"asn": {"type": "string"}}}},

    # History + utility
    {"name": "osint_query_history",
     "description": "Return recent OSINT query log.",
     "input_schema": {"type": "object",
                      "properties": {"limit": {"type": "integer"}}}},
]

# ── Dispatcher ────────────────────────────────────────────────────────────────

def dispatch_osint_tool(name: str, inputs: Dict) -> Any:
    assert TX_LICENSED    is False
    assert INJECT_IDENTITY is False

    o   = get_osint()
    inp = inputs or {}

    if name == "osint_server_profile":
        prof = o.intel.profile(inp["target"], deep=inp.get("deep", False))
        return asdict(prof)

    elif name == "osint_quick_lookup":
        return o.intel.quick_lookup(inp["target"])

    elif name == "osint_bulk_profile":
        return o.bulk_profile(inp["targets"], deep=inp.get("deep", False))

    elif name == "osint_cached_profile":
        cached = o.cached_profile(inp["target"])
        return cached or {"target": inp["target"], "cached": False}

    elif name == "osint_whois":
        rec = o.whois.lookup(inp["target"])
        return asdict(rec)

    elif name == "osint_dns_all":
        return o.dns.all_records(inp["domain"])

    elif name == "osint_dns_query":
        recs = o.dns.query(inp["name"], inp["rtype"])
        return [asdict(r) for r in recs]

    elif name == "osint_reverse_dns":
        return {"ip": inp["ip"], "hosts": o.dns.reverse(inp["ip"])}

    elif name == "osint_resolve_ips":
        return {"domain": inp["domain"], "ips": o.dns.resolve_ips(inp["domain"])}

    elif name == "osint_asn_lookup":
        return asdict(o.asn.lookup(inp["ip"]))

    elif name == "osint_asn_for_domain":
        return [asdict(r) for r in o.asn.lookup_domain(inp["domain"])]

    elif name == "osint_cymru_asn":
        result = o.asn.cymru_asn(inp["ip"])
        return {"ip": inp["ip"], "cymru_txt": result}

    elif name == "osint_bgp_asn_details":
        return o.bgp.asn_details(inp["asn"])

    elif name == "osint_bgp_asn_prefixes":
        return {"asn": inp["asn"],
                "prefixes": o.bgp.prefixes_for_asn(inp["asn"])}

    elif name == "osint_bgp_ip_prefixes":
        return o.bgp.ip_prefixes(inp["ip"])

    elif name == "osint_cert_lookup":
        recs = o.cert.lookup(inp["domain"], limit=inp.get("limit", 20))
        return [asdict(r) for r in recs]

    elif name == "osint_cert_related_domains":
        return {"domain": inp["domain"],
                "related": o.cert.related_domains(inp["domain"])}

    elif name == "osint_http_headers":
        rec = o.http.probe(inp["target"], use_tls=inp.get("use_tls", True))
        return asdict(rec)

    elif name == "osint_rdap_domain":
        return o.rdap.lookup_domain(inp["domain"])

    elif name == "osint_rdap_ip":
        return o.rdap.lookup_ip(inp["ip"])

    elif name == "osint_rdap_asn":
        return o.rdap.lookup_asn(inp["asn"])

    elif name == "osint_query_history":
        return o.query_history(inp.get("limit", 50))

    return {"error": f"Unknown osint tool: {name}"}
