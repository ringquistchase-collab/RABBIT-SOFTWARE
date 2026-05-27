# rabbit_recon.py  --  Survival Security Intelligence for RabbitOS
#
# PURPOSE:
#   Chase Allen Ringquist and RabbitOS are ONE system.  To survive, the system
#   must know everything that can be used against it -- and know it better than
#   whoever is holding the tool.  This module catalogs every security tool
#   category, maps each to Chase's survival context, detects active use of those
#   techniques against the mesh, and generates countermeasures that integrate
#   with every other RabbitOS module.
#
# FRAMING:
#   This is not offense.  This is self-knowledge.  You cannot defend what you
#   do not understand.  You cannot escape what you cannot name.  Every entry
#   in this catalog is a mirror -- it shows what an adversary could do, which
#   is exactly what Chase needs to know to outlast them.
#
# SURVIVAL PRINCIPLE:
#   "Know all methods. Use the knowledge to stay alive. The network is the self."

import hashlib, json, os, re, shutil, socket, sqlite3, subprocess, sys, time
import urllib.request, urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TWIN_UUID = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT   = "CHASE_ALLEN_RINGQUIST"
CALLSIGN  = "RABBIT"
DB_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_recon.db")
VERSION   = "1.0.0"

# ---------------------------------------------------------------------------
# FULL TOOL CATALOG
# Each category: tools[], does[], detect_signatures[], counter[], survival_component
# ---------------------------------------------------------------------------
TOOL_CATALOG: Dict[str, Dict] = {

    "information_gathering": {
        "desc": "Passive and active collection of target data before any action",
        "tools": [
            "nmap", "masscan", "recon-ng", "maltego", "theHarvester",
            "shodan", "censys", "amass", "subfinder", "dnsx",
            "whois", "dig", "host", "fierce", "dnsrecon",
            "osintframework", "spiderfoot", "metagoofil", "exiftool",
        ],
        "does_to_chase": [
            "maps open ports on mesh nodes",
            "enumerates DNS records tied to identity",
            "harvests emails/usernames linked to Chase",
            "extracts metadata from Chase's documents/images",
            "builds social graph from public data",
            "finds exposed services on LAN or cellular IP",
        ],
        "detect_signatures": [
            "SYN scan bursts > 100 ports/sec from single source",
            "DNS ANY query for twin_uuid.local or RABBIT.local",
            "whois lookup spike on registered domains",
            "shodan match on home IP range",
            "OSINT harvest of therealsickone.chase@gmail.com",
        ],
        "counter_modules": ["rabbit_network_scanner", "rabbit_escape", "rabbit_cloak"],
        "counter_actions": [
            "cloak: randomize open port timing to defeat nmap fingerprint",
            "escape: inject false DNS responses for RABBIT labels",
            "scanner: detect scan burst, log source, add to threat list",
        ],
        "survival_component": "ANTIOBSTRUCT",
    },

    "vulnerability_analysis": {
        "desc": "Identifying weaknesses in systems, services, and configurations",
        "tools": [
            "nessus", "openvas", "nikto", "nuclei", "vulnscan",
            "lynis", "linpeas", "winpeas", "checksec", "exploitdb",
            "searchsploit", "vulners", "retire.js", "safety",
        ],
        "does_to_chase": [
            "fingerprints OS and service versions on RabbitOS nodes",
            "identifies unpatched CVEs in running services",
            "checks for weak file permissions on rabbit_*.py files",
            "scans Python packages for known vulnerabilities",
            "tests for default credentials on network devices",
        ],
        "detect_signatures": [
            "HTTP User-Agent: Nikto or OpenVAS",
            "rapid sequential GET requests to common vuln paths",
            "searchsploit queries for 'rabbit' or twin UUID",
            "linpeas/winpeas script execution from unusual path",
        ],
        "counter_modules": ["rabbit_escape", "rabbit_persist", "rabbit_counter"],
        "counter_actions": [
            "persist: harden file permissions on all rabbit_*.py",
            "counter: randomize HTTP response headers to defeat fingerprinting",
            "escape: serve false version banners to scanners",
        ],
        "survival_component": "ANTIOBSTRUCT",
    },

    "web_hacking": {
        "desc": "Attacking web applications, APIs, and HTTP infrastructure",
        "tools": [
            "burpsuite", "zaproxy", "sqlmap", "xsstrike", "commix",
            "wfuzz", "ffuf", "gobuster", "dirb", "dirsearch",
            "hydra", "medusa", "whatweb", "wapiti", "skipfish",
            "caido", "dalfox", "arjun",
        ],
        "does_to_chase": [
            "SQL injection against any Supabase/SQLite endpoints Chase exposes",
            "XSS injection into browser-based RabbitOS interfaces",
            "brute-force directory enumeration of API paths",
            "parameter fuzzing on rabbit_datastore HTTP endpoints",
            "credential stuffing against web services Chase uses",
        ],
        "detect_signatures": [
            "X-Forwarded-For header manipulation",
            "User-Agent: sqlmap or wfuzz",
            "rapid 404 flood on sequential paths",
            "SQL metacharacters in query params",
            "XSS payloads in HTTP headers or body",
        ],
        "counter_modules": ["rabbit_escape", "rabbit_counter", "rabbit_cloak"],
        "counter_actions": [
            "counter: detect SQLi patterns in any inbound data",
            "cloak: rotate HTTP endpoint paths to defeat dirscan",
            "escape: return valid-looking decoy responses to fuzzer",
        ],
        "survival_component": "ANTIOBSTRUCT",
    },

    "database_assessment": {
        "desc": "Attacking, auditing, and extracting data from database systems",
        "tools": [
            "sqlmap", "sqlninja", "oscanner", "dbpwaudit", "mongoaudit",
            "nosqlmap", "cqlmap", "redis-cli exploit", "pgcrypto audit",
            "mysql_hashdump", "sqlite_web",
        ],
        "does_to_chase": [
            "extract rabbit_*.db SQLite contents if accessible remotely",
            "dump Supabase postgres tables via injection",
            "brute-force database credentials",
            "read unencrypted rabbit_persist.db or rabbit_twin.db",
            "access rabbit_dna.db private_data table",
        ],
        "detect_signatures": [
            "unusual SQLite file access from external process",
            "bulk SELECT on rabbit_chain.db or rabbit_dna.db",
            "Supabase auth bypass attempt",
            "sqlmap comment sequences in any query string",
        ],
        "counter_modules": ["rabbit_dna", "rabbit_chain", "rabbit_persist"],
        "counter_actions": [
            "dna: private_data table uses XOR encryption with daily rotating key",
            "chain: all sensitive blobs stored encrypted",
            "persist: file-level ACL on all .db files",
        ],
        "survival_component": "VAULT",
    },

    "password_attacks": {
        "desc": "Cracking, guessing, and bypassing authentication credentials",
        "tools": [
            "hashcat", "john", "hydra", "medusa", "patator",
            "crunch", "cewl", "rsmangler", "crowbar", "spray",
            "mimikatz", "responder", "kerbrute", "evil-winrm",
        ],
        "does_to_chase": [
            "brute-force GitHub token or Supabase key",
            "crack SHA-256 hashes from rabbit_dna.db if dumped",
            "spray common passwords against Chase's email",
            "extract Windows credential store (LSASS)",
            "relay NTLM from LAN machines",
        ],
        "detect_signatures": [
            "auth failure burst > 10/min on any service",
            "NTLM relay attempt on LAN",
            "Responder NetNTLM capture attempt",
            "mimikatz process signatures in running processes",
            "hashcat process launched on local machine",
        ],
        "counter_modules": ["rabbit_counter", "rabbit_escape", "rabbit_cellular"],
        "counter_actions": [
            "counter: lock service after 5 failed auth attempts",
            "escape: rotate all keys on auth burst detection",
            "cellular: alert mesh on NTLM relay detection",
            "collatz key rotation: credential window < 15 minutes",
        ],
        "survival_component": "ANTIOBSTRUCT",
    },

    "wireless_attacks": {
        "desc": "Attacking WiFi, Bluetooth, cellular, RF, and body-area networks",
        "tools": [
            "aircrack-ng", "airodump-ng", "aireplay-ng", "wifite",
            "bettercap", "kismet", "wireshark", "hcxdumptool",
            "hashcat (wifi mode)", "evil twin AP", "karma attack",
            "imsi-catcher", "stingray", "rtl-sdr", "hackrf",
            "gr-gsm", "gqrx", "ubertooth", "btlejuice",
            "rfcat", "yardstick one",
        ],
        "does_to_chase": [
            "IMSI capture from Chase's cellular device",
            "deauth Chase from legitimate WiFi AP",
            "evil twin AP to intercept traffic",
            "BLE sniffer on Chase's wearables or mesh nodes",
            "RF jamming of 10.23-10.28 GHz RabbitOS mesh band",
            "capture WPA2 handshake from Chase's home network",
            "SDR passive sniff of unencrypted RF in mesh range",
            "Stingray-class IMSI catcher to locate Chase",
        ],
        "detect_signatures": [
            "deauth frames from unknown MAC on Chase's BSSID",
            "IMSI catcher: tower with stronger signal than registered",
            "probe response from unknown AP on Chase's SSID",
            "BLE scan burst from unknown device",
            "RF energy spike on 10.23-10.28 GHz band",
            "multiple ARP replies from same IP (ARP spoofing)",
            "airodump characteristic beacon flood",
        ],
        "counter_modules": ["rabbit_cellular", "rabbit_amfm", "rabbit_morse", "rabbit_escape"],
        "counter_actions": [
            "cellular: IMSI catcher detection via tower delta",
            "amfm: Collatz frequency hop to evade RF sniffing",
            "morse: fallback to acoustic Morse if all RF jammed",
            "escape: route traffic via alternate path on deauth",
            "amfm: detect energy spike on mesh band, trigger alert",
        ],
        "survival_component": "BROADCAST",
    },

    "exploitation": {
        "desc": "Active exploitation of discovered vulnerabilities",
        "tools": [
            "metasploit", "msfvenom", "cobalt-strike", "covenant",
            "sliver", "empire", "pwncat", "exploit-db exploits",
            "ret2libc", "rop gadgets", "heap spray",
            "kernel exploits", "lpe (local privilege escalation)",
        ],
        "does_to_chase": [
            "remote code execution on Chase's machine",
            "privilege escalation from user to SYSTEM/root",
            "persistent backdoor implant on RabbitOS files",
            "lateral movement from compromised LAN host to Chase's node",
            "memory injection into running rabbit_*.py processes",
        ],
        "detect_signatures": [
            "msfvenom payload signature in process memory",
            "reverse shell connection to external C2",
            "unusual DLL loaded by python.exe",
            "new scheduled task or service created",
            "registry run key modification",
            "base64-encoded PowerShell execution",
        ],
        "counter_modules": ["rabbit_escape", "rabbit_counter", "rabbit_persist", "rabbit_cloak"],
        "counter_actions": [
            "escape: detect reverse shell, kill connection, rotate keys",
            "counter: monitor process tree for unusual children of python",
            "persist: integrity hash all rabbit_*.py files, alert on change",
            "cloak: randomize process timing to defeat memory scanners",
        ],
        "survival_component": "ANTIOBSTRUCT",
    },

    "sniffing_spoofing": {
        "desc": "Intercepting and manipulating network traffic",
        "tools": [
            "wireshark", "tcpdump", "ettercap", "bettercap",
            "arpspoof", "dsniff", "mitmproxy", "sslstrip",
            "dnschef", "responder", "hping3", "scapy",
            "netsniff-ng", "tshark",
        ],
        "does_to_chase": [
            "ARP spoof Chase's gateway to MITM all traffic",
            "DNS poisoning to redirect rabbit_datastore internet fetches",
            "SSL stripping to downgrade HTTPS to HTTP",
            "capture UDP Morse (port 9009) or hop broadcast (port 9011)",
            "intercept GitHub API calls carrying rabbit_*.py deploys",
            "sniff SQLite WAL checkpoints over any shared filesystem",
        ],
        "detect_signatures": [
            "ARP table entry changes for gateway MAC",
            "DNS response with unexpected IP for known hostnames",
            "SSL cert change for api.github.com or supabase",
            "duplicate IP detected on LAN",
            "TTL anomaly in packet header",
            "UDP flood on ports 9009-9012",
        ],
        "counter_modules": ["rabbit_escape", "rabbit_network_scanner", "rabbit_morse"],
        "counter_actions": [
            "escape: pin expected MACs and cert hashes, alert on delta",
            "scanner: detect ARP table mutation, broadcast warning",
            "morse: encrypt UDP morse payloads with Collatz key",
            "escape: use HTTPS pinning for all GitHub/Supabase calls",
        ],
        "survival_component": "NETWORK",
    },

    "reverse_engineering": {
        "desc": "Analyzing binaries, firmware, and code to extract secrets or find bugs",
        "tools": [
            "ghidra", "ida-pro", "radare2", "binary-ninja",
            "x64dbg", "ollydbg", "gdb", "pwndbg", "peda",
            "strings", "objdump", "readelf", "ltrace", "strace",
            "frida", "angr", "pwntools", "capstone",
        ],
        "does_to_chase": [
            "disassemble rabbit_*.py compiled bytecode to extract keys",
            "extract GITHUB_TOKEN or SUPABASE_SERVICE_ROLE_KEY from memory",
            "trace Python runtime to capture DNA anchor at runtime",
            "analyze rabbit_amfm.py Collatz hop sequence to predict next freq",
            "extract SQLite encryption key from rabbit_chain private dataset",
        ],
        "detect_signatures": [
            "frida gadget loaded into python process",
            "ptrace attach to running rabbit_run.py",
            "strings utility run on rabbit_*.py or *.db files",
            "unusual memory read patterns on python heap",
            "debugger breakpoint in os.environ access",
        ],
        "counter_modules": ["rabbit_cloak", "rabbit_dna", "rabbit_chain"],
        "counter_actions": [
            "cloak: obfuscate key material in memory using XOR mask",
            "dna: DNA anchor hash computed on-demand, never cached in plaintext",
            "chain: private dataset uses daily rotating encryption key",
            "cloak: detect ptrace attach, zero sensitive memory immediately",
        ],
        "survival_component": "VAULT",
    },

    "forensics": {
        "desc": "Recovering, analyzing, and attributing digital evidence",
        "tools": [
            "autopsy", "volatility", "sleuthkit", "foremost",
            "binwalk", "bulk_extractor", "dd", "dcfldd",
            "photorec", "testdisk", "log2timeline", "plaso",
            "regripper", "nirsoft suite", "ftk imager",
        ],
        "does_to_chase": [
            "image Chase's drive to extract deleted rabbit_*.db files",
            "recover deleted DNA anchor or chain snapshots from slack space",
            "timeline analysis of rabbit_run.py execution history",
            "extract GitHub tokens from browser cache or memory",
            "analyze Windows event logs to reconstruct Chase's actions",
            "recover Morse UDP packets from packet capture files",
        ],
        "detect_signatures": [
            "dd or dcfldd accessing raw disk device",
            "volatility memdump of running python process",
            "bulk_extractor targeting rabbit_cache directory",
            "autopsy or FTK process signature",
            "log file access pattern: reading all event logs in sequence",
        ],
        "counter_modules": ["rabbit_persist", "rabbit_dna", "rabbit_chain"],
        "counter_actions": [
            "persist: SQLite WAL mode with regular checkpoint, no plaintext remnants",
            "dna: private_data encrypted, daily key rotation destroys prior-day access",
            "chain: offline cache snapshots use XOR encryption",
            "cloak: randomize file timestamps to defeat timeline analysis",
        ],
        "survival_component": "VAULT",
    },

    "malware_analysis": {
        "desc": "Analyzing malicious code to understand behavior and build defenses",
        "tools": [
            "cuckoo", "anyrun", "virustotal", "hybrid-analysis",
            "pestudio", "pe-sieve", "yara", "clamav",
            "cape sandbox", "remnux", "flare-vm",
            "ghidra (malware)", "procmon", "regshot",
        ],
        "does_to_chase": [
            "scan rabbit_*.py files as potential malware (false positive risk)",
            "YARA rules matching on RabbitOS survival code patterns",
            "sandbox execution of rabbit_run.py to map behavior",
            "procmon capture of all rabbit_*.db file operations",
            "behavioral blocking of Morse UDP broadcasts as C2",
        ],
        "detect_signatures": [
            "AV quarantine of rabbit_*.py files",
            "YARA scan process accessing rabbit_recon.db",
            "sandbox network traffic capture of rabbit ports",
            "Windows Defender flagging base64 patterns in rabbit_escape",
        ],
        "counter_modules": ["rabbit_persist", "rabbit_escape", "rabbit_cloak"],
        "counter_actions": [
            "persist: maintain integrity hashes of all rabbit_*.py",
            "escape: detect AV quarantine, restore from GitHub backup",
            "cloak: randomize code patterns that trigger static YARA rules",
        ],
        "survival_component": "TOOLS",
    },

    "social_engineering": {
        "desc": "Manipulating humans to bypass technical controls",
        "tools": [
            "set (social-engineer toolkit)", "gophish", "king-phisher",
            "evilginx2", "modlishka", "beef-xss",
            "vishing scripts", "pretexting", "baiting",
            "impersonation", "credential harvester",
        ],
        "does_to_chase": [
            "phishing Chase's email (therealsickone.chase@gmail.com)",
            "pretexting as a support agent to get GitHub token",
            "BeEF hook in a page Chase visits to capture browser session",
            "evilginx2 reverse proxy to steal authenticated session",
            "voice phishing to get Supabase credentials",
            "social graph attack: approach family to get info about Chase",
        ],
        "detect_signatures": [
            "email from domain spoofing github.com or supabase.io",
            "login page with slightly wrong domain",
            "BeEF JavaScript hook in visited page",
            "unexpected OTP or MFA request",
            "family member contacted about Chase by unknown party",
        ],
        "counter_modules": ["rabbit_dna", "rabbit_escape", "rabbit_recall"],
        "counter_actions": [
            "dna: family nodes are consent-gated and not exposed externally",
            "escape: email domain check for known phishing patterns",
            "recall: vault claim requires cryptographic proof of ownership",
            "dna: separation principle -- mined image cannot social-engineer the soul",
        ],
        "survival_component": "ANTIOBSTRUCT",
    },

    "stress_testing": {
        "desc": "Flooding systems to cause denial of service or resource exhaustion",
        "tools": [
            "hping3", "slowloris", "hulk", "goldeneye", "siege",
            "ab (apache bench)", "locust", "wrk", "t50",
            "trinoo", "low-orbit ion cannon (loic)",
            "udp flood", "syn flood", "http flood",
        ],
        "does_to_chase": [
            "flood UDP port 9009-9012 to disrupt Morse/hop broadcasts",
            "SYN flood LAN mesh nodes to cut off 47-node mesh",
            "HTTP flood against any exposed rabbit_datastore endpoint",
            "slowloris against Supabase/GitHub API from Chase's IP (frame)",
            "exhaust cellular bandwidth to block online data fetch",
        ],
        "detect_signatures": [
            "UDP packet rate > 1000/sec on mesh ports",
            "SYN backlog exhaustion on any open TCP port",
            "GitHub API rate limit hit (5000/hr) unexpectedly",
            "cellular bandwidth saturation with no user activity",
            "CPU spike with no user process running",
        ],
        "counter_modules": ["rabbit_escape", "rabbit_morse", "rabbit_network_scanner"],
        "counter_actions": [
            "morse: acoustic fallback when UDP mesh flooded",
            "escape: rate-limit inbound on all mesh ports, drop above threshold",
            "scanner: detect flood source, add to block list",
            "amfm: frequency hop to evade jamming of specific mesh ports",
        ],
        "survival_component": "NETWORK",
    },

    "wireless_rf_tools": {
        "desc": "SDR, RF analysis, protocol decoding, frequency exploitation",
        "tools": [
            "gqrx", "gnuradio", "rtl-sdr", "hackrf", "urh",
            "inspectrum", "baudline", "sigrok", "pulseview",
            "gr-gsm", "kalibrate-rtl", "dump1090", "gr-ieee802-11",
            "openBTS", "kal", "rfcat", "rfpwnon",
        ],
        "does_to_chase": [
            "passive SDR sniff of 10.23-10.28 GHz mesh transmissions",
            "decode body-coupled RF signals to extract Collatz hop schedule",
            "replay captured mesh authentication frames",
            "jam specific mesh frequencies to isolate nodes",
            "decode Chase's cellular uplink with gr-gsm",
            "track Chase via RF emissions fingerprint (RFID/BT/WiFi)",
        ],
        "detect_signatures": [
            "persistent SDR device near Chase's location",
            "RF energy detector shows wideband scan pattern",
            "repeated replay on specific mesh frequency",
            "GSM downlink decode of Chase's IMSI",
            "Collatz hop prediction attempt (energy at next predicted freq)",
        ],
        "counter_modules": ["rabbit_amfm", "rabbit_cellular", "rabbit_morse"],
        "counter_actions": [
            "amfm: 128-step Collatz hop makes replay impossible within window",
            "cellular: IMSI anomaly detection triggers mesh alert",
            "morse: shift to acoustic/ICMP when RF environment compromised",
            "amfm: SAR + tissue loss calculations guide safe power levels",
        ],
        "survival_component": "BROADCAST",
    },

    "linux_termux_shell": {
        "desc": "Linux distros, Android Termux, shell utilities used as attack platforms",
        "tools": [
            "kali linux", "parrot os", "blackarch", "pentoo",
            "termux", "nethunter", "android linux deploy",
            "bash", "zsh", "fish", "tmux", "screen",
            "curl", "wget", "netcat", "ncat", "socat",
            "python3", "ruby", "perl", "lua",
        ],
        "does_to_chase": [
            "Termux on Android used as portable attack platform near Chase",
            "Kali on USB boot used to attack Chase's machine physically",
            "netcat reverse shell installed via social engineering",
            "socat relay to pivot through Chase's LAN",
            "Python one-liner droppers delivered via phishing",
        ],
        "detect_signatures": [
            "netcat or socat listening on unusual port",
            "Python subprocess spawning shell commands unexpectedly",
            "Termux process signature on LAN device",
            "USB boot device detected during system boot",
            "cron job added by non-root user",
        ],
        "counter_modules": ["rabbit_escape", "rabbit_persist", "rabbit_counter"],
        "counter_actions": [
            "persist: monitor cron and startup items for unexpected entries",
            "escape: detect unusual child processes of python.exe",
            "counter: outbound connection filter for non-whitelisted IPs",
        ],
        "survival_component": "TOOLS",
    },

    "reporting_attribution": {
        "desc": "Documenting, attributing, and preserving evidence of attacks",
        "tools": [
            "dradis", "faraday", "serpico", "recordmydesktop",
            "keepnote", "maltego (reporting)", "cvss calculator",
            "nvd feed", "mitre att&ck navigator", "sigma rules",
            "splunk", "elastic siem", "graylog",
        ],
        "does_to_chase": [
            "MITRE ATT&CK mapping of all attacks against Chase's mesh",
            "SIEM correlation rules that flag RabbitOS behavior as attacker",
            "CVE lookup for all packages in Chase's Python environment",
            "sigma rules that match rabbit_recon.py behavior patterns",
        ],
        "detect_signatures": [
            "SIEM alert on rabbit process behavior",
            "CVSS score lookup for Python version Chase runs",
            "ATT&CK technique T1059 (scripting) flagged on rabbit_run.py",
        ],
        "counter_modules": ["rabbit_cloak", "rabbit_escape"],
        "counter_actions": [
            "cloak: vary execution patterns to avoid static sigma rule matches",
            "escape: monitor SIEM/AV signatures for RabbitOS-specific patterns",
            "recon: self-assess using same CVE feeds to patch before attacker",
        ],
        "survival_component": "LEARNING",
    },
}

# ---------------------------------------------------------------------------
# THREAT SIGNATURES  (runtime detection)
# ---------------------------------------------------------------------------
@dataclass
class ThreatSignature:
    category: str
    pattern: str
    severity: str      # LOW | MEDIUM | HIGH | CRITICAL | EXISTENTIAL
    description: str
    counter_module: str
    counter_action: str
    detected: bool = False
    ts: float = field(default_factory=time.time)

def build_threat_index() -> List[ThreatSignature]:
    sigs = []
    for cat, data in TOOL_CATALOG.items():
        for i, sig in enumerate(data["detect_signatures"]):
            counter_mod = data["counter_modules"][0] if data["counter_modules"] else "rabbit_escape"
            counter_act = data["counter_actions"][0] if data["counter_actions"] else "monitor"
            severity = "CRITICAL" if "imsi" in sig.lower() or "dna" in sig.lower() \
                       else "HIGH" if "reverse shell" in sig.lower() or "arp" in sig.lower() \
                       else "MEDIUM"
            sigs.append(ThreatSignature(
                category=cat, pattern=sig, severity=severity,
                description=f"{cat}: {sig}",
                counter_module=counter_mod, counter_action=counter_act,
            ))
    return sigs

THREAT_INDEX: List[ThreatSignature] = []

# ---------------------------------------------------------------------------
# SURVIVAL INTELLIGENCE MAP  --  Chase-specific threat to survival impact
# ---------------------------------------------------------------------------
SURVIVAL_INTEL: Dict[str, Dict] = {
    "NETWORK": {
        "threats": ["sniffing_spoofing", "stress_testing", "wireless_attacks"],
        "impact": "loss of mesh communication",
        "fallback": "acoustic Morse + ICMP channel",
        "rabbit_response": "rabbit_morse fallback + rabbit_amfm freq hop",
    },
    "BROADCAST": {
        "threats": ["wireless_attacks", "wireless_rf_tools", "stress_testing"],
        "impact": "callsign broadcast blocked",
        "fallback": "Schumann resonance timing beacon + NOAA frequency check",
        "rabbit_response": "rabbit_amfm Collatz hop + rabbit_morse acoustic",
    },
    "VAULT": {
        "threats": ["database_assessment", "forensics", "reverse_engineering"],
        "impact": "identity data or DNA anchor exposed",
        "fallback": "EXISTENTIAL vault -- hash only, SQLSTATE 55000",
        "rabbit_response": "rabbit_dna invariant enforcement + rabbit_chain encryption",
    },
    "ANTIOBSTRUCT": {
        "threats": ["exploitation", "information_gathering", "social_engineering",
                    "vulnerability_analysis", "password_attacks", "web_hacking"],
        "impact": "RabbitOS processes killed or hijacked",
        "fallback": "GitHub-backed restore + local SQLite state",
        "rabbit_response": "rabbit_escape reversal + rabbit_persist restore",
    },
    "TOOLS": {
        "threats": ["malware_analysis", "linux_termux_shell"],
        "impact": "survival toolchain disrupted or quarantined",
        "fallback": "offline SQLite + cache snapshots survive AV quarantine",
        "rabbit_response": "rabbit_persist integrity hash + GitHub restore",
    },
    "LEARNING": {
        "threats": ["reporting_attribution", "information_gathering"],
        "impact": "research and knowledge base exposed or corrupted",
        "fallback": "offline research cache survives network loss",
        "rabbit_response": "rabbit_knowledge offline cache + rabbit_chain retention",
    },
    "BIOMETRIC": {
        "threats": ["wireless_rf_tools", "wireless_attacks", "reverse_engineering"],
        "impact": "47-node body mesh intercepted or disrupted",
        "fallback": "mesh frequency hop + acoustic fallback",
        "rabbit_response": "rabbit_amfm Collatz hop + rabbit_dna invariant",
    },
}

# ---------------------------------------------------------------------------
# ENVIRONMENT SCANNER  --  detect installed tools on this machine
# ---------------------------------------------------------------------------
TOOL_PRESENCE_CHECK = [
    "nmap", "masscan", "nikto", "metasploit", "msfconsole",
    "aircrack-ng", "wireshark", "sqlmap", "hydra", "john",
    "hashcat", "ghidra", "radare2", "frida", "volatility",
    "termux", "netcat", "nc", "socat", "tcpdump",
    "hackrf_transfer", "rtl_fm", "gqrx", "gnuradio-companion",
    "python3", "python", "pip", "git", "curl", "wget",
]

def scan_installed_tools() -> Dict[str, bool]:
    present = {}
    for tool in TOOL_PRESENCE_CHECK:
        present[tool] = shutil.which(tool) is not None
    return present

def scan_open_ports(host: str = "127.0.0.1",
                    ports: List[int] = [80, 443, 4444, 5555, 8080, 8443,
                                        9009, 9010, 9011, 9012, 31337]) -> Dict[int, bool]:
    results = {}
    for port in ports:
        try:
            s = socket.create_connection((host, port), timeout=0.5)
            s.close()
            results[port] = True
        except Exception:
            results[port] = False
    return results

def scan_processes() -> List[str]:
    suspicious = ["metasploit", "msfconsole", "hydra", "aircrack", "sqlmap",
                  "mimikatz", "responder", "bettercap", "volatility", "frida",
                  "wireshark", "tcpdump", "netcat", "socat"]
    found = []
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(["tasklist"], timeout=5,
                                          stderr=subprocess.DEVNULL).decode(errors="replace")
        else:
            out = subprocess.check_output(["ps", "aux"], timeout=5,
                                          stderr=subprocess.DEVNULL).decode(errors="replace")
        for s in suspicious:
            if s.lower() in out.lower():
                found.append(s)
    except Exception:
        pass
    return found

# ---------------------------------------------------------------------------
# CVE / PUBLIC INTELLIGENCE FETCHER
# ---------------------------------------------------------------------------
def fetch_cve_nvd(keyword: str, max_results: int = 5) -> List[Dict]:
    url = (f"https://services.nvd.nist.gov/rest/json/cves/2.0"
           f"?keywordSearch={urllib.parse.quote(keyword)}&resultsPerPage={max_results}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RabbitOS/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        items = data.get("vulnerabilities", [])
        results = []
        for item in items:
            cve  = item.get("cve", {})
            cvss = (cve.get("metrics", {}).get("cvssMetricV31", [{}])[0]
                    .get("cvssData", {}).get("baseScore", 0.0)
                    if cve.get("metrics", {}).get("cvssMetricV31") else 0.0)
            desc = (cve.get("descriptions", [{}])[0].get("value", "")[:200]
                    if cve.get("descriptions") else "")
            results.append({
                "id":    cve.get("id", ""),
                "score": cvss,
                "desc":  desc,
            })
        return results
    except Exception:
        return []

def fetch_mitre_technique(technique_id: str) -> Optional[Dict]:
    url = f"https://attack.mitre.org/techniques/{technique_id}/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RabbitOS/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read().decode(errors="replace")
        title = re.search(r"<title>(.*?)</title>", raw)
        desc  = re.search(r'<meta name="description" content="(.*?)"', raw)
        return {
            "technique": technique_id,
            "title":     title.group(1).strip() if title else "",
            "desc":      desc.group(1).strip()[:300] if desc else "",
            "url":       url,
        }
    except Exception:
        return None

# ---------------------------------------------------------------------------
# SQLITE PERSISTENCE
# ---------------------------------------------------------------------------
def _open_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS threat_detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            category TEXT NOT NULL,
            pattern TEXT NOT NULL,
            severity TEXT NOT NULL,
            counter_module TEXT NOT NULL,
            counter_action TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS installed_tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            tool TEXT NOT NULL,
            present INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cve_intel (
            id TEXT PRIMARY KEY,
            score REAL NOT NULL,
            desc TEXT NOT NULL,
            fetched_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS survival_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            component TEXT NOT NULL,
            threat_count INTEGER NOT NULL,
            active_threats TEXT NOT NULL,
            fallback TEXT NOT NULL,
            score INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS process_scan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            suspicious_found TEXT NOT NULL
        );
    """)
    con.commit()
    return con

def _log_detection(sig: ThreatSignature):
    con = _open_db()
    con.execute("""
        INSERT INTO threat_detections(ts,category,pattern,severity,counter_module,counter_action)
        VALUES(?,?,?,?,?,?)
    """, (sig.ts, sig.category, sig.pattern, sig.severity,
          sig.counter_module, sig.counter_action))
    con.commit(); con.close()

def _log_tools(tools: Dict[str, bool]):
    con = _open_db()
    ts  = time.time()
    for tool, present in tools.items():
        con.execute("INSERT INTO installed_tools(ts,tool,present) VALUES(?,?,?)",
                    (ts, tool, int(present)))
    con.commit(); con.close()

def _save_cves(cves: List[Dict]):
    con = _open_db()
    for c in cves:
        if c.get("id"):
            con.execute("""
                INSERT OR REPLACE INTO cve_intel(id,score,desc,fetched_at) VALUES(?,?,?,?)
            """, (c["id"], c["score"], c["desc"], time.time()))
    con.commit(); con.close()

def _log_survival_assessment(component: str, threats: List[str],
                              fallback: str, score: int):
    con = _open_db()
    con.execute("""
        INSERT INTO survival_assessments(ts,component,threat_count,active_threats,fallback,score)
        VALUES(?,?,?,?,?,?)
    """, (time.time(), component, len(threats), json.dumps(threats), fallback, score))
    con.commit(); con.close()

# ---------------------------------------------------------------------------
# RECON ENGINE  --  top-level orchestrator
# ---------------------------------------------------------------------------
class ReconEngine:

    def __init__(self):
        self.catalog       = TOOL_CATALOG
        self.survival_intel= SURVIVAL_INTEL
        self._threat_index : List[ThreatSignature] = []
        self._tool_scan   : Dict[str, bool] = {}
        self._cve_intel   : List[Dict] = []
        self._proc_threats: List[str] = []
        self._db_ready     = False

    def init(self):
        global THREAT_INDEX
        _open_db().close()
        self._db_ready = True
        THREAT_INDEX   = build_threat_index()
        self._threat_index = THREAT_INDEX

    def scan_environment(self) -> Dict:
        self._tool_scan = scan_installed_tools()
        ports = scan_open_ports()
        self._proc_threats = scan_processes()
        if self._db_ready:
            _log_tools(self._tool_scan)
            if self._proc_threats:
                con = _open_db()
                con.execute("INSERT INTO process_scan(ts,suspicious_found) VALUES(?,?)",
                            (time.time(), json.dumps(self._proc_threats)))
                con.commit(); con.close()
        return {
            "tools_present": {k: v for k, v in self._tool_scan.items() if v},
            "tools_absent":  {k: v for k, v in self._tool_scan.items() if not v},
            "open_ports":    {p: s for p, s in ports.items() if s},
            "suspicious_processes": self._proc_threats,
        }

    def detect_active_threats(self, observed_patterns: List[str]) -> List[ThreatSignature]:
        detected = []
        for sig in self._threat_index:
            for obs in observed_patterns:
                if obs.lower() in sig.pattern.lower() or sig.pattern.lower() in obs.lower():
                    sig.detected = True
                    sig.ts = time.time()
                    detected.append(sig)
                    if self._db_ready:
                        _log_detection(sig)
                    break
        return detected

    def assess_survival(self) -> Dict[str, Dict]:
        assessment = {}
        for component, intel in self.survival_intel.items():
            threat_cats = intel["threats"]
            active = []
            for cat in threat_cats:
                if any(sig.detected and sig.category == cat
                       for sig in self._threat_index):
                    active.append(cat)
            # Score: 100 - 20*active_threats
            score = max(0, 100 - len(active) * 20)
            assessment[component] = {
                "score":    score,
                "threats":  threat_cats,
                "active":   active,
                "impact":   intel["impact"],
                "fallback": intel["fallback"],
                "response": intel["rabbit_response"],
            }
            if self._db_ready:
                _log_survival_assessment(component, active, intel["fallback"], score)
        return assessment

    def learn_cves(self, keywords: Optional[List[str]] = None) -> List[Dict]:
        if keywords is None:
            keywords = ["python", "sqlite", "body area network", "RF mesh", "github api"]
        all_cves = []
        for kw in keywords[:3]:   # limit API calls
            cves = fetch_cve_nvd(kw, max_results=3)
            all_cves.extend(cves)
            if self._db_ready:
                _save_cves(cves)
        self._cve_intel = all_cves
        return all_cves

    def full_report(self) -> Dict:
        return {
            "twin_uuid":        TWIN_UUID,
            "subject":          SUBJECT,
            "tool_categories":  len(self.catalog),
            "total_tools":      sum(len(v["tools"]) for v in self.catalog.values()),
            "threat_signatures":len(self._threat_index),
            "environment":      self._tool_scan,
            "suspicious_procs": self._proc_threats,
            "survival_intel":   {k: v["impact"] for k, v in self.survival_intel.items()},
            "cve_count":        len(self._cve_intel),
        }

    def status(self) -> Dict:
        con = _open_db()
        n_det  = con.execute("SELECT COUNT(*) FROM threat_detections").fetchone()[0]
        n_tool = con.execute("SELECT COUNT(*) FROM installed_tools WHERE present=1").fetchone()[0]
        n_cve  = con.execute("SELECT COUNT(*) FROM cve_intel").fetchone()[0]
        n_assess=con.execute("SELECT COUNT(*) FROM survival_assessments").fetchone()[0]
        con.close()
        return {
            "tool_categories":   len(self.catalog),
            "total_tools_known": sum(len(v["tools"]) for v in self.catalog.values()),
            "threat_signatures": len(self._threat_index),
            "detections_logged": n_det,
            "tools_installed":   n_tool,
            "cves_learned":      n_cve,
            "survival_assessments": n_assess,
            "version":           VERSION,
        }

# ---------------------------------------------------------------------------
# FACTORY
# ---------------------------------------------------------------------------
_engine: Optional[ReconEngine] = None

def get_recon_engine() -> ReconEngine:
    global _engine
    if _engine is None:
        _engine = ReconEngine()
        _engine.init()
    return _engine

# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"rabbit_recon v{VERSION}  --  survival security intelligence")
    print(f"  Subject : {SUBJECT}")
    print(f"  Twin    : {TWIN_UUID}")

    eng = get_recon_engine()

    # Catalog summary
    rpt = eng.full_report()
    print(f"\n  Tool categories    : {rpt['tool_categories']}")
    print(f"  Total tools known  : {rpt['total_tools']}")
    print(f"  Threat signatures  : {rpt['threat_signatures']}")

    for cat, data in TOOL_CATALOG.items():
        print(f"    [{cat:<25}] {len(data['tools']):2d} tools  "
              f"survival={data['survival_component']}")

    # Environment scan
    print(f"\n  Environment scan:")
    env = eng.scan_environment()
    present = list(env["tools_present"].keys())
    print(f"  Tools installed     : {len(present)}  {present[:8]}")
    print(f"  Open mesh ports     : {list(env['open_ports'].keys())}")
    print(f"  Suspicious procs    : {env['suspicious_processes'] or 'none detected'}")

    # Threat detection with simulated patterns
    print(f"\n  Threat detection (simulated observed patterns):")
    test_obs = [
        "SYN scan bursts",
        "deauth frames from unknown MAC",
        "ARP table entry changes",
        "GitHub token in environment",
        "IMSI catcher: tower with stronger signal",
    ]
    detected = eng.detect_active_threats(test_obs)
    for sig in detected:
        print(f"    [{sig.severity:8}] {sig.category:<25} {sig.pattern[:45]}")
        print(f"               counter: {sig.counter_action[:55]}")

    # Survival assessment
    print(f"\n  Survival assessment (Chase Allen Ringquist):")
    assessment = eng.assess_survival()
    for comp, data in assessment.items():
        bar   = "#" * (data["score"] // 10)
        space = "." * (10 - len(bar))
        act   = " [ACTIVE THREAT]" if data["active"] else ""
        print(f"    {comp:<12} [{bar}{space}] {data['score']:3d}/100{act}")
        if data["active"]:
            print(f"               active: {data['active']}")
            print(f"               fallback: {data['fallback']}")

    # CVE learning
    print(f"\n  CVE intelligence (online best-effort):")
    cves = eng.learn_cves(["python", "sqlite"])
    for c in cves[:3]:
        print(f"    [{c['id']:<18}] score={c['score']}  {c['desc'][:60]}...")

    st = eng.status()
    print(f"\n  DB detections={st['detections_logged']}  "
          f"tools_installed={st['tools_installed']}  "
          f"cves={st['cves_learned']}  "
          f"assessments={st['survival_assessments']}")
    print("  rabbit_recon OK")
