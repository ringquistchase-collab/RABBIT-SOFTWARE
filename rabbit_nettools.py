#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_nettools.py — RabbitOS Networking + Protocol + Agent Mesh
================================================================
Covers every network scope and protocol layer for Chase Allen Ringquist.

Network types   : PAN, LAN, WLAN, CAN, MAN, WAN, SAN, POLAN, EPAN, VPN, VPS
Windows tools   : ping, ipconfig, tracert, netstat, netsh, winsock
Protocol probers: TCP, UDP, HTTP, HTTPS, FTP, SMTP, IMAP, WebSocket
VPS layer       : detection, cloud metadata, provider map
Agent mesh      : agent-to-agent REST + WebSocket message routing
Browser assistant: Claude API + browser + network data = unified intelligence

Integrates with: rabbit_browser.py, rabbit_network_scanner.py, rabbit_ssh.py
"""

from __future__ import annotations
import base64, hashlib, hmac, json, os, platform, queue, re, select
import socket, sqlite3, ssl, struct, subprocess, sys, threading, time
import traceback, urllib.error, urllib.parse, urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

# ─── Identity ─────────────────────────────────────────────────────────────────
TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"
_SOUL_KEY  = hashlib.sha256(f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()).digest()

TOOLS_DB   = Path(__file__).parent / "rabbit_nettools.db"
TOOLS_LOG  = Path(__file__).parent / "rabbit_nettools.log"

# ─── Logging ──────────────────────────────────────────────────────────────────
def _log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(TOOLS_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ==============================================================================
# 1. NETWORK TYPE CLASSIFIER
# ==============================================================================

@dataclass
class NetworkScope:
    net_type:    str   = "unknown"   # pan|lan|wlan|can|man|wan|san|polan|epan|vpn|vps
    scope_label: str   = ""
    local_ips:   List[str] = field(default_factory=list)
    gateway:     str   = ""
    hop_count:   int   = 0
    is_wireless: bool  = False
    is_cellular: bool  = False
    is_vpn:      bool  = False
    is_vps:      bool  = False
    is_fiber:    bool  = False
    is_bluetooth:bool  = False
    ssid:        str   = ""
    isp:         str   = ""
    external_ip: str   = ""
    asn:         str   = ""
    ts:          str   = ""

    SCOPE_LABELS = {
        "pan":   "Personal Area Network    (<10 m,  Bluetooth/BLE/Zigbee)",
        "epan":  "Extended PAN            (<100 m,  IEEE 802.15.4 mesh)",
        "lan":   "Local Area Network      (<1 km,  Ethernet/Switch)",
        "wlan":  "Wireless LAN            (<300 m, WiFi 802.11)",
        "polan": "Passive Optical LAN     (<2 km,  PON fiber/GPON)",
        "can":   "Campus Area Network     (<5 km,  multi-building)",
        "man":   "Metropolitan Area Net   (<50 km, city/metro fiber)",
        "san":   "Storage Area Network    (fiber channel / iSCSI)",
        "wan":   "Wide Area Network       (cross-ISP, national)",
        "vpn":   "Virtual Private Network (encrypted overlay)",
        "vps":   "Virtual Private Server  (cloud/hosted compute)",
    }

    def summary(self) -> Dict:
        return {
            "net_type":    self.net_type,
            "label":       self.SCOPE_LABELS.get(self.net_type, self.net_type),
            "local_ips":   self.local_ips,
            "gateway":     self.gateway,
            "hop_count":   self.hop_count,
            "wireless":    self.is_wireless,
            "cellular":    self.is_cellular,
            "vpn":         self.is_vpn,
            "vps":         self.is_vps,
            "fiber":       self.is_fiber,
            "bluetooth":   self.is_bluetooth,
            "ssid":        self.ssid,
            "external_ip": self.external_ip,
            "isp":         self.isp,
            "asn":         self.asn,
            "ts":          self.ts,
        }


class NetworkTypeClassifier:
    """
    Classifies the current network environment across all scope levels.
    Detects: PAN, LAN, WLAN, CAN, MAN, WAN, SAN, POLAN, EPAN, VPN, VPS.
    """

    def classify(self) -> NetworkScope:
        scope = NetworkScope(ts=datetime.now(timezone.utc).isoformat())
        scope.local_ips   = self._get_local_ips()
        scope.gateway     = self._get_gateway()
        scope.is_wireless = self._detect_wireless(scope)
        scope.ssid        = self._get_ssid()
        scope.is_cellular = self._detect_cellular()
        scope.is_vpn      = self._detect_vpn(scope.local_ips)
        scope.is_bluetooth= self._detect_bluetooth()
        scope.is_fiber    = self._detect_fiber()
        scope.is_vps      = self._detect_vps_host()
        scope.external_ip, scope.isp, scope.asn = self._get_external_ip_info()
        scope.hop_count   = self._count_hops()
        scope.net_type    = self._determine_type(scope)
        _log(f"[NetType] Classified: {scope.net_type}  "
             f"IPs={scope.local_ips}  gw={scope.gateway}  "
             f"WiFi={scope.is_wireless}  VPN={scope.is_vpn}")
        return scope

    def _get_local_ips(self) -> List[str]:
        ips = []
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["ipconfig"], capture_output=True,
                                     text=True, timeout=5).stdout
                ips = re.findall(r'IPv4 Address[. ]+: ([\d.]+)', out)
            else:
                out = subprocess.run(["ip", "addr"], capture_output=True,
                                     text=True, timeout=5).stdout
                ips = re.findall(r'inet ([\d.]+)/', out)
                ips = [ip for ip in ips if ip != "127.0.0.1"]
        except Exception:
            pass
        # Fallback
        if not ips:
            try:
                ips = [socket.gethostbyname(socket.gethostname())]
            except Exception:
                pass
        return ips

    def _get_gateway(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["ipconfig"], capture_output=True,
                                     text=True, timeout=5).stdout
                m = re.search(r'Default Gateway[. ]+: ([\d.]+)', out)
                if m:
                    return m.group(1)
            else:
                out = subprocess.run(["ip", "route"], capture_output=True,
                                     text=True, timeout=5).stdout
                m = re.search(r'default via ([\d.]+)', out)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return ""

    def _detect_wireless(self, scope: NetworkScope) -> bool:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                                     capture_output=True, text=True, timeout=5).stdout
                return "State" in out and "connected" in out.lower()
            else:
                out = subprocess.run(["iwconfig"], capture_output=True,
                                     text=True, timeout=5, stderr=subprocess.DEVNULL).stdout
                return "ESSID" in out
        except Exception:
            return False

    def _get_ssid(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                                     capture_output=True, text=True, timeout=5).stdout
                m = re.search(r'SSID\s+:\s+(.+)', out)
                if m:
                    return m.group(1).strip()
            else:
                out = subprocess.run(["iwgetid", "-r"], capture_output=True,
                                     text=True, timeout=5).stdout
                return out.strip()
        except Exception:
            return ""

    def _detect_cellular(self) -> bool:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["netsh", "mbn", "show", "interfaces"],
                                     capture_output=True, text=True, timeout=5).stdout
                return "Connected" in out
            else:
                out = subprocess.run(["mmcli", "-L"], capture_output=True,
                                     text=True, timeout=5).stdout
                return "modem" in out.lower()
        except Exception:
            return False

    def _detect_vpn(self, local_ips: List[str]) -> bool:
        vpn_ranges = ["10.8.", "10.9.", "10.10.", "172.16.", "172.17.",
                      "192.168.200.", "100.64."]
        for ip in local_ips:
            for r in vpn_ranges:
                if ip.startswith(r):
                    return True
        # Check for known VPN adapter names
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["ipconfig", "/all"], capture_output=True,
                                     text=True, timeout=5).stdout
                vpn_adapters = ["tap", "tun", "wireguard", "openvpn", "nordvpn",
                                 "expressvpn", "proton", "nordlynx"]
                out_lower = out.lower()
                return any(a in out_lower for a in vpn_adapters)
        except Exception:
            pass
        return False

    def _detect_bluetooth(self) -> bool:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["powershell", "-Command",
                     "Get-PnpDevice -Class Bluetooth | Where-Object Status -eq 'OK' | Measure-Object | Select-Object Count"],
                    capture_output=True, text=True, timeout=8).stdout
                return "Count" in out and not "0" in out.split("Count")[-1][:20]
            else:
                out = subprocess.run(["hciconfig"], capture_output=True,
                                     text=True, timeout=5).stdout
                return "UP" in out or "hci0" in out
        except Exception:
            return False

    def _detect_fiber(self) -> bool:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["ipconfig", "/all"], capture_output=True,
                                     text=True, timeout=5).stdout
                return any(kw in out.lower() for kw in
                           ["fiber", "optical", "gpon", "sfp", "1000base"])
        except Exception:
            pass
        return False

    def _detect_vps_host(self) -> bool:
        # Check hypervisor DMI / cloud metadata endpoints
        hypervisor_hints = []
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject -Class Win32_ComputerSystem).Model"],
                    capture_output=True, text=True, timeout=5).stdout.strip().lower()
                hypervisor_hints = ["virtual", "vmware", "kvm", "xen", "hyper-v",
                                    "qemu", "amazon", "azure", "google"]
                if any(h in out for h in hypervisor_hints):
                    return True
            else:
                for f in ["/sys/class/dmi/id/product_name",
                           "/sys/class/dmi/id/sys_vendor"]:
                    try:
                        val = Path(f).read_text().strip().lower()
                        if any(h in val for h in ["virtual", "vmware", "kvm",
                                                   "xen", "amazon", "azure"]):
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        # Try AWS/GCP/Azure metadata
        for url, timeout in [
            ("http://169.254.169.254/latest/meta-data/", 1),
            ("http://metadata.google.internal/", 1),
        ]:
            try:
                req = urllib.request.Request(url)
                urllib.request.urlopen(req, timeout=timeout)
                return True
            except Exception:
                pass
        return False

    def _get_external_ip_info(self) -> Tuple[str, str, str]:
        for url in [
            "https://ipapi.co/json/",
            "https://ipinfo.io/json",
        ]:
            try:
                req  = urllib.request.Request(
                    url, headers={"User-Agent": "RabbitOS/14"})
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                ip   = data.get("ip", "")
                isp  = data.get("org", data.get("isp", ""))
                asn  = data.get("asn", "")
                return ip, isp, asn
            except Exception:
                pass
        return "", "", ""

    def _count_hops(self) -> int:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["tracert", "-d", "-h", "10", "8.8.8.8"],
                    capture_output=True, text=True, timeout=20).stdout
                hops = re.findall(r'^\s+(\d+)\s', out, re.M)
                if hops:
                    return int(hops[-1])
            else:
                out = subprocess.run(
                    ["traceroute", "-n", "-m", "10", "8.8.8.8"],
                    capture_output=True, text=True, timeout=20).stdout
                hops = re.findall(r'^(\d+)\s', out, re.M)
                if hops:
                    return int(hops[-1])
        except Exception:
            pass
        return 0

    def _determine_type(self, s: NetworkScope) -> str:
        if s.is_bluetooth and not s.local_ips:
            return "pan"
        if s.is_vps:
            return "vps"
        if s.is_vpn:
            return "vpn"
        if s.is_fiber:
            # Could be POLAN (passive optical LAN) or MAN
            if s.hop_count <= 3:
                return "polan"
            elif s.hop_count <= 8:
                return "can"
            else:
                return "man"
        if s.is_wireless and s.is_cellular:
            return "wan"
        if s.is_wireless:
            return "wlan"
        if s.is_cellular:
            return "wan"
        # Check IP scope
        for ip in s.local_ips:
            if ip.startswith("100.64.") or ip.startswith("100.65."):
                return "can"  # CGNAT / campus
        if s.hop_count == 0:
            return "lan"
        if s.hop_count <= 3:
            return "lan"
        if s.hop_count <= 6:
            return "can"
        if s.hop_count <= 10:
            return "man"
        return "wan"


# ==============================================================================
# 2. WINDOWS NETWORK DIAGNOSTICS
# ==============================================================================

class WinNetDiag:
    """
    Full Windows network diagnostics suite.
    ping, ipconfig, tracert, netstat, netsh, winsock.
    All output is parsed into structured dicts.
    """

    # ── ping ──────────────────────────────────────────────────────────────────
    def ping(self, host: str, count: int = 4, timeout_ms: int = 1000) -> Dict:
        result = {"host": host, "reachable": False, "sent": count,
                  "received": 0, "lost": 0, "loss_pct": 100.0,
                  "min_ms": 0, "max_ms": 0, "avg_ms": 0, "raw": ""}
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["ping", "-n", str(count), "-w", str(timeout_ms), host],
                    capture_output=True, text=True, timeout=count * 3,
                    errors="replace").stdout
            else:
                out = subprocess.run(
                    ["ping", "-c", str(count), "-W", "1", host],
                    capture_output=True, text=True, timeout=count * 3,
                    errors="replace").stdout
            result["raw"] = out[:1000]
            # Parse Windows
            m = re.search(r'Received = (\d+)', out)
            if m:
                result["received"] = int(m.group(1))
                result["lost"]     = count - result["received"]
                result["loss_pct"] = 100.0 * result["lost"] / max(count, 1)
                result["reachable"]= result["received"] > 0
            m = re.search(r'Minimum = (\d+)ms, Maximum = (\d+)ms, Average = (\d+)ms', out)
            if m:
                result["min_ms"] = int(m.group(1))
                result["max_ms"] = int(m.group(2))
                result["avg_ms"] = int(m.group(3))
            # Linux parse
            m = re.search(r'(\d+) packets transmitted, (\d+) received', out)
            if m:
                result["sent"]     = int(m.group(1))
                result["received"] = int(m.group(2))
                result["lost"]     = result["sent"] - result["received"]
                result["loss_pct"] = 100.0 * result["lost"] / max(result["sent"], 1)
                result["reachable"]= result["received"] > 0
            m = re.search(r'rtt min/avg/max[^=]+=\s*([\d.]+)/([\d.]+)/([\d.]+)', out)
            if m:
                result["min_ms"] = float(m.group(1))
                result["avg_ms"] = float(m.group(2))
                result["max_ms"] = float(m.group(3))
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── ipconfig ──────────────────────────────────────────────────────────────
    def ipconfig(self, all_info: bool = True) -> Dict:
        result: Dict[str, Any] = {"adapters": [], "dns_suffix": "", "raw": ""}
        try:
            cmd = ["ipconfig", "/all"] if all_info else ["ipconfig"]
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=10, errors="replace").stdout
            result["raw"] = out[:5000]

            # Parse adapter blocks
            blocks = re.split(r'\n(?=\S)', out)
            for block in blocks:
                if "adapter" not in block.lower():
                    continue
                adapter: Dict[str, Any] = {}
                m = re.search(r'adapter (.+?):', block)
                if m:
                    adapter["name"] = m.group(1).strip()
                m = re.search(r'IPv4 Address[. ]+: ([\d.]+)', block)
                if m:
                    adapter["ipv4"] = m.group(1)
                m = re.search(r'Subnet Mask[. ]+: ([\d.]+)', block)
                if m:
                    adapter["subnet"] = m.group(1)
                m = re.search(r'Default Gateway[. ]+: ([\d.]+)', block)
                if m:
                    adapter["gateway"] = m.group(1)
                m = re.search(r'Physical Address[. ]+: ([\da-fA-F-]+)', block)
                if m:
                    adapter["mac"] = m.group(1).lower().replace("-", ":")
                m = re.search(r'DHCP Enabled[. ]+: (\w+)', block)
                if m:
                    adapter["dhcp"] = m.group(1) == "Yes"
                m = re.search(r'DNS Servers[. ]+: ([\d.]+)', block)
                if m:
                    adapter["dns"] = m.group(1)
                m = re.search(r'IPv6 Address[. ]+: ([0-9a-f:]+)', block, re.I)
                if m:
                    adapter["ipv6"] = m.group(1)
                if adapter.get("name"):
                    result["adapters"].append(adapter)
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── tracert ───────────────────────────────────────────────────────────────
    def tracert(self, host: str, max_hops: int = 15) -> Dict:
        result = {"host": host, "hops": [], "raw": "", "reached": False}
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["tracert", "-d", "-h", str(max_hops), host],
                    capture_output=True, text=True, timeout=60,
                    errors="replace").stdout
            else:
                out = subprocess.run(
                    ["traceroute", "-n", "-m", str(max_hops), host],
                    capture_output=True, text=True, timeout=60,
                    errors="replace").stdout
            result["raw"] = out[:3000]
            # Parse hops: Windows format "  1    <1 ms    <1 ms    <1 ms  192.168.1.1"
            for line in out.splitlines():
                m = re.match(
                    r'\s+(\d+)\s+([<\d]+) ms\s+([<\d]+) ms\s+([<\d]+) ms\s+([\d.]+)',
                    line)
                if m:
                    hop = {
                        "hop":   int(m.group(1)),
                        "ip":    m.group(5),
                        "rtt1":  m.group(2),
                        "rtt2":  m.group(3),
                        "rtt3":  m.group(4),
                    }
                    result["hops"].append(hop)
                elif "*" in line and re.match(r'\s+\d+', line):
                    hn = re.match(r'\s+(\d+)', line)
                    if hn:
                        result["hops"].append({"hop": int(hn.group(1)), "ip": "*"})
                # Linux format "1  192.168.1.1  0.532 ms  0.430 ms  0.389 ms"
                m2 = re.match(r'(\d+)\s+([\d.]+)\s+([\d.]+) ms', line)
                if m2:
                    result["hops"].append({
                        "hop": int(m2.group(1)), "ip": m2.group(2),
                        "rtt1": m2.group(3)
                    })
            if result["hops"]:
                last_ip = result["hops"][-1].get("ip", "")
                result["reached"] = last_ip not in ("*", "")
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── netstat ───────────────────────────────────────────────────────────────
    def netstat(self, show_pid: bool = True) -> Dict:
        result: Dict[str, Any] = {
            "connections": [], "listening": [], "by_state": {}, "raw": ""}
        try:
            if platform.system() == "Windows":
                flags = ["-ano"] if show_pid else ["-an"]
                out = subprocess.run(
                    ["netstat"] + flags, capture_output=True, text=True,
                    timeout=15, errors="replace").stdout
            else:
                out = subprocess.run(
                    ["ss", "-tulnp"] if show_pid else ["ss", "-tuln"],
                    capture_output=True, text=True, timeout=10).stdout
            result["raw"] = out[:5000]

            by_state: Dict[str, int] = {}
            for line in out.splitlines():
                # Windows: "  TCP  0.0.0.0:80  0.0.0.0:0  LISTENING  1234"
                m = re.match(
                    r'\s+(TCP|UDP)\s+([\d.:*]+)\s+([\d.:*]+)\s+(\w+)\s+(\d+)?',
                    line, re.I)
                if m:
                    proto    = m.group(1).upper()
                    local    = m.group(2)
                    remote   = m.group(3)
                    state    = m.group(4).upper() if m.group(4) else "UDP"
                    pid      = m.group(5) or ""
                    entry    = {"proto": proto, "local": local,
                                "remote": remote, "state": state, "pid": pid}
                    if state == "LISTENING" or state == "UDP":
                        result["listening"].append(entry)
                    else:
                        result["connections"].append(entry)
                    by_state[state] = by_state.get(state, 0) + 1
            result["by_state"] = by_state
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── netsh ─────────────────────────────────────────────────────────────────
    def netsh_winsock_show(self) -> str:
        try:
            return subprocess.run(
                ["netsh", "winsock", "show", "catalog"],
                capture_output=True, text=True, timeout=10,
                errors="replace").stdout[:3000]
        except Exception as e:
            return str(e)

    def netsh_interface_show(self) -> str:
        try:
            return subprocess.run(
                ["netsh", "interface", "show", "interface"],
                capture_output=True, text=True, timeout=10,
                errors="replace").stdout[:3000]
        except Exception as e:
            return str(e)

    def netsh_firewall_show(self) -> str:
        try:
            return subprocess.run(
                ["netsh", "advfirewall", "show", "allprofiles"],
                capture_output=True, text=True, timeout=10,
                errors="replace").stdout[:3000]
        except Exception as e:
            return str(e)

    def netsh_wlan_show(self) -> str:
        try:
            out = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True, text=True, timeout=10,
                errors="replace").stdout
            out += "\n\n" + subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=10,
                errors="replace").stdout
            return out[:4000]
        except Exception as e:
            return str(e)

    def netsh_stats(self) -> str:
        try:
            out = subprocess.run(
                ["netsh", "interface", "ip", "show", "ipstats"],
                capture_output=True, text=True, timeout=10,
                errors="replace").stdout
            return out[:2000]
        except Exception as e:
            return str(e)

    def arp_table(self) -> str:
        try:
            return subprocess.run(
                ["arp", "-a"], capture_output=True, text=True,
                timeout=5, errors="replace").stdout[:2000]
        except Exception as e:
            return str(e)

    def route_table(self) -> str:
        try:
            if platform.system() == "Windows":
                return subprocess.run(
                    ["route", "print"], capture_output=True, text=True,
                    timeout=5, errors="replace").stdout[:3000]
            else:
                return subprocess.run(
                    ["ip", "route"], capture_output=True, text=True,
                    timeout=5).stdout[:2000]
        except Exception as e:
            return str(e)

    def full_snapshot(self) -> Dict:
        """Run all Windows diagnostics in parallel and return combined report."""
        report: Dict[str, Any] = {
            "ts":            datetime.now(timezone.utc).isoformat(),
            "os":            platform.system(),
            "hostname":      socket.gethostname(),
            "ping_gateway":  {},
            "ipconfig":      {},
            "netstat":       {},
        }
        # Get gateway first
        classifier = NetworkTypeClassifier()
        gw = classifier._get_gateway()
        if gw:
            report["ping_gateway"] = self.ping(gw, count=2)

        results: Dict[str, Any] = {}
        tasks = {
            "ipconfig":          lambda: self.ipconfig(),
            "netstat":           lambda: self.netstat(),
            "netsh_winsock":     lambda: self.netsh_winsock_show(),
            "netsh_interfaces":  lambda: self.netsh_interface_show(),
            "netsh_wlan":        lambda: self.netsh_wlan_show(),
            "arp":               lambda: self.arp_table(),
            "routes":            lambda: self.route_table(),
        }
        lock = threading.Lock()

        def run_task(name, fn):
            try:
                val = fn()
                with lock:
                    results[name] = val
            except Exception as e:
                with lock:
                    results[name] = str(e)

        threads = [threading.Thread(target=run_task, args=(n, f), daemon=True)
                   for n, f in tasks.items()]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        report.update(results)
        return report


# ==============================================================================
# 3. PROTOCOL PROBERS
# ==============================================================================

@dataclass
class ProbeResult:
    host:     str
    port:     int
    protocol: str
    open:     bool   = False
    banner:   str    = ""
    latency_ms: float = 0.0
    detail:   Dict   = field(default_factory=dict)
    error:    str    = ""
    ts:       str    = ""


class ProtocolProbe:
    """
    Probes every network protocol: TCP, UDP, HTTP, HTTPS, FTP, SMTP, IMAP, WS.
    Returns structured ProbeResult for each.
    """

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    # ── TCP ───────────────────────────────────────────────────────────────────
    def probe_tcp(self, host: str, port: int,
                  payload: bytes = b"\r\n") -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="TCP",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=self.timeout)
            if payload:
                s.sendall(payload)
            try:
                data = s.recv(512)
                r.banner = data.decode(errors="replace")[:200]
            except Exception:
                pass
            s.close()
            r.open       = True
            r.latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── UDP ───────────────────────────────────────────────────────────────────
    def probe_udp(self, host: str, port: int,
                  payload: bytes = b"\x00") -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="UDP",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(self.timeout)
            s.sendto(payload, (host, port))
            try:
                data, _ = s.recvfrom(512)
                r.banner = data.decode(errors="replace")[:200]
                r.open   = True
            except socket.timeout:
                r.open  = True   # No ICMP unreachable = probably open
                r.banner = "no_response"
            s.close()
            r.latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── HTTP ──────────────────────────────────────────────────────────────────
    def probe_http(self, host: str, port: int = 80,
                   path: str = "/") -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="HTTP",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=self.timeout)
            req = (f"GET {path} HTTP/1.1\r\n"
                   f"Host: {host}\r\n"
                   f"User-Agent: RabbitOS/14 (Chase Allen Ringquist)\r\n"
                   f"Connection: close\r\n\r\n").encode()
            s.sendall(req)
            resp = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
                if len(resp) > 8192:
                    break
            s.close()
            text         = resp.decode(errors="replace")
            r.open       = True
            r.latency_ms = round((time.time() - t0) * 1000, 1)
            # Parse status
            m = re.match(r'HTTP/[\d.]+ (\d+)', text)
            r.detail["status"] = int(m.group(1)) if m else 0
            # Headers
            header_end = text.find("\r\n\r\n")
            if header_end > 0:
                r.banner = text[:header_end][:400]
                r.detail["body_preview"] = text[header_end+4:][:200]
            else:
                r.banner = text[:400]
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── HTTPS ─────────────────────────────────────────────────────────────────
    def probe_https(self, host: str, port: int = 443,
                    path: str = "/") -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="HTTPS",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            url = f"https://{host}:{port}{path}"
            req = urllib.request.Request(
                url, headers={"User-Agent": "RabbitOS/14"})
            ctx = ssl.create_default_context()
            resp = urllib.request.urlopen(req, timeout=self.timeout, context=ctx)
            body = resp.read(2048).decode(errors="replace")
            r.open       = True
            r.latency_ms = round((time.time() - t0) * 1000, 1)
            r.detail["status"] = resp.status
            r.detail["cert_subject"] = str(
                resp.fp.raw._sock.getpeercert().get("subject", "")
            ) if hasattr(resp, "fp") else ""
            r.banner = body[:300]
        except urllib.error.HTTPError as e:
            r.open   = True
            r.detail["status"] = e.code
            r.error  = f"HTTP {e.code}"
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── FTP ───────────────────────────────────────────────────────────────────
    def probe_ftp(self, host: str, port: int = 21) -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="FTP",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=self.timeout)
            banner = s.recv(256).decode(errors="replace").strip()
            r.banner = banner[:200]
            r.open   = True
            r.detail["banner"] = banner[:100]
            # Try anonymous login
            s.sendall(b"USER anonymous\r\n")
            resp1 = s.recv(256).decode(errors="replace").strip()
            r.detail["user_resp"] = resp1[:60]
            if resp1.startswith("331"):
                s.sendall(b"PASS rabbitos@chase.net\r\n")
                resp2 = s.recv(256).decode(errors="replace").strip()
                r.detail["pass_resp"] = resp2[:60]
                r.detail["anon_login"] = resp2.startswith("230")
            # SYST command
            s.sendall(b"SYST\r\n")
            syst = s.recv(128).decode(errors="replace").strip()
            r.detail["syst"] = syst[:60]
            s.sendall(b"QUIT\r\n")
            s.close()
            r.latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── SMTP ──────────────────────────────────────────────────────────────────
    def probe_smtp(self, host: str, port: int = 25) -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="SMTP",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=self.timeout)
            banner = s.recv(256).decode(errors="replace").strip()
            r.banner = banner[:200]
            r.open   = True
            r.detail["banner"] = banner[:80]
            # EHLO
            s.sendall(f"EHLO rabbitos.chase\r\n".encode())
            resp = s.recv(512).decode(errors="replace")
            r.detail["ehlo"] = resp[:200]
            caps = re.findall(r'250[-\s]+(.+)', resp)
            r.detail["capabilities"] = caps
            # STARTTLS check
            r.detail["starttls"] = any("STARTTLS" in c.upper() for c in caps)
            # AUTH methods
            auth_line = next((c for c in caps if "AUTH" in c.upper()), "")
            r.detail["auth_methods"] = auth_line.replace("AUTH", "").strip().split()
            s.sendall(b"QUIT\r\n")
            s.close()
            r.latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── SMTP over TLS (port 465 / 587) ───────────────────────────────────────
    def probe_smtps(self, host: str, port: int = 465) -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="SMTPS",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            ctx = ssl.create_default_context()
            raw = socket.create_connection((host, port), timeout=self.timeout)
            s   = ctx.wrap_socket(raw, server_hostname=host)
            banner = s.recv(256).decode(errors="replace").strip()
            r.banner = banner[:200]
            r.open   = True
            r.detail["tls"] = True
            r.detail["cipher"] = str(s.cipher())
            s.sendall(f"EHLO rabbitos.chase\r\n".encode())
            resp = s.recv(512).decode(errors="replace")
            r.detail["ehlo"] = resp[:200]
            s.sendall(b"QUIT\r\n")
            s.close()
            r.latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── IMAP ──────────────────────────────────────────────────────────────────
    def probe_imap(self, host: str, port: int = 143) -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="IMAP",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=self.timeout)
            banner = s.recv(256).decode(errors="replace").strip()
            r.banner = banner[:200]
            r.open   = True
            r.detail["banner"] = banner[:80]
            # CAPABILITY
            s.sendall(b". CAPABILITY\r\n")
            resp = s.recv(512).decode(errors="replace")
            r.detail["capabilities"] = resp[:300]
            r.detail["starttls"] = "STARTTLS" in resp.upper()
            r.detail["auth_plain"] = "AUTH=PLAIN" in resp.upper()
            r.detail["auth_login"] = "AUTH=LOGIN" in resp.upper()
            s.sendall(b". LOGOUT\r\n")
            s.close()
            r.latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── IMAPS (port 993) ─────────────────────────────────────────────────────
    def probe_imaps(self, host: str, port: int = 993) -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="IMAPS",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            ctx = ssl.create_default_context()
            raw = socket.create_connection((host, port), timeout=self.timeout)
            s   = ctx.wrap_socket(raw, server_hostname=host)
            banner = s.recv(256).decode(errors="replace").strip()
            r.banner = banner[:200]
            r.open   = True
            r.detail["tls"]    = True
            r.detail["cipher"] = str(s.cipher())
            s.sendall(b". CAPABILITY\r\n")
            resp = s.recv(512).decode(errors="replace")
            r.detail["capabilities"] = resp[:200]
            s.sendall(b". LOGOUT\r\n")
            s.close()
            r.latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── WebSocket ─────────────────────────────────────────────────────────────
    def probe_websocket(self, host: str, port: int = 80,
                        path: str = "/", use_tls: bool = False) -> ProbeResult:
        r = ProbeResult(host=host, port=port, protocol="WS",
                        ts=datetime.now(timezone.utc).isoformat())
        t0 = time.time()
        try:
            if use_tls:
                ctx = ssl.create_default_context()
                raw = socket.create_connection((host, port), timeout=self.timeout)
                s   = ctx.wrap_socket(raw, server_hostname=host)
                r.protocol = "WSS"
            else:
                s = socket.create_connection((host, port), timeout=self.timeout)

            ws_key = base64.b64encode(os.urandom(16)).decode()
            handshake = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"User-Agent: RabbitOS/14\r\n"
                f"\r\n"
            ).encode()
            s.sendall(handshake)
            resp = s.recv(512).decode(errors="replace")
            r.banner = resp[:200]
            r.open   = "101 Switching" in resp
            r.detail["upgraded"] = r.open
            r.detail["http_resp"] = resp[:100]

            if r.open:
                # Send a small text frame (opcode 1, masked)
                mask = os.urandom(4)
                payload = b"RabbitOS ping"
                masked  = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
                frame   = bytes([0x81, 0x80 | len(payload)]) + mask + masked
                s.sendall(frame)
                try:
                    pong = s.recv(128)
                    r.detail["server_response"] = pong.hex()[:40]
                except Exception:
                    pass
            s.close()
            r.latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            r.error = str(e)[:80]
        return r

    # ── Multi-probe ───────────────────────────────────────────────────────────
    def probe_all(self, host: str) -> Dict[str, ProbeResult]:
        """Run all protocol probes against a host in parallel."""
        probes = [
            ("tcp_22",   lambda: self.probe_tcp(host, 22)),
            ("tcp_80",   lambda: self.probe_tcp(host, 80)),
            ("tcp_443",  lambda: self.probe_tcp(host, 443)),
            ("http",     lambda: self.probe_http(host, 80)),
            ("https",    lambda: self.probe_https(host, 443)),
            ("ftp",      lambda: self.probe_ftp(host, 21)),
            ("smtp",     lambda: self.probe_smtp(host, 25)),
            ("smtp_587", lambda: self.probe_smtp(host, 587)),
            ("smtps",    lambda: self.probe_smtps(host, 465)),
            ("imap",     lambda: self.probe_imap(host, 143)),
            ("imaps",    lambda: self.probe_imaps(host, 993)),
            ("ws_80",    lambda: self.probe_websocket(host, 80)),
            ("ws_443",   lambda: self.probe_websocket(host, 443, use_tls=True)),
            ("udp_53",   lambda: self.probe_udp(host, 53, b"\x00\x00\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x06google\x03com\x00\x00\x01\x00\x01")),
        ]
        results: Dict[str, ProbeResult] = {}
        lock = threading.Lock()

        def run(name, fn):
            try:
                val = fn()
                with lock:
                    results[name] = val
            except Exception as e:
                with lock:
                    results[name] = ProbeResult(
                        host=host, port=0, protocol=name, error=str(e))

        threads = [threading.Thread(target=run, args=(n, f), daemon=True)
                   for n, f in probes]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        return results

    def probe_all_as_dict(self, host: str) -> Dict:
        results = self.probe_all(host)
        return {k: asdict(v) for k, v in results.items()}


# ==============================================================================
# 4. VPS MANAGER
# ==============================================================================

@dataclass
class VPSNode:
    label:       str
    host:        str
    port:        int = 22
    provider:    str = ""
    region:      str = ""
    os_hint:     str = ""
    reachable:   bool = False
    ssh_banner:  str = ""
    http_open:   bool = False
    http_status: int = 0
    latency_ms:  float = 0.0
    metadata:    Dict = field(default_factory=dict)
    ts:          str = ""


class VPSManager:
    """
    Discovers, probes, and manages Virtual Private Server nodes.
    Detects cloud metadata (AWS/GCP/Azure/DO/Linode/Vultr).
    Integrates with rabbit_ssh.py for connection.
    """

    CLOUD_METADATA = {
        "AWS":    "http://169.254.169.254/latest/meta-data/",
        "GCP":    "http://metadata.google.internal/computeMetadata/v1/instance/",
        "Azure":  "http://169.254.169.254/metadata/instance?api-version=2021-01-01",
        "DigitalOcean": "http://169.254.169.254/metadata/v1/",
    }

    KNOWN_VPS_PORTS = [22, 80, 443, 2222, 8080, 8443]

    def detect_self(self) -> Dict:
        """Detect if this machine is a VPS and get its cloud metadata."""
        result: Dict[str, Any] = {"is_vps": False, "provider": "", "metadata": {}}
        for provider, url in self.CLOUD_METADATA.items():
            try:
                headers = {"Metadata": "true"} if "Azure" in url or "GCP" in url else {}
                req  = urllib.request.Request(url, headers=headers)
                resp = urllib.request.urlopen(req, timeout=1)
                data = resp.read(4096).decode(errors="replace")
                result["is_vps"]   = True
                result["provider"] = provider
                try:
                    result["metadata"] = json.loads(data)
                except Exception:
                    result["metadata"] = {"raw": data[:500]}
                break
            except Exception:
                pass
        return result

    def probe_vps(self, host: str, label: str = "",
                  ports: List[int] = None) -> VPSNode:
        """Probe a VPS node for availability and metadata."""
        ports = ports or self.KNOWN_VPS_PORTS
        node  = VPSNode(
            label=label or host, host=host,
            ts=datetime.now(timezone.utc).isoformat())
        probe = ProtocolProbe(timeout=5.0)

        # SSH probe
        ssh_r = probe.probe_tcp(host, 22, b"")
        node.reachable  = ssh_r.open
        node.ssh_banner = ssh_r.banner
        node.latency_ms = ssh_r.latency_ms
        # OS hint from SSH banner
        b = node.ssh_banner.lower()
        if "ubuntu" in b:   node.os_hint = "Ubuntu"
        elif "debian" in b: node.os_hint = "Debian"
        elif "kali" in b:   node.os_hint = "Kali"
        elif "centos" in b: node.os_hint = "CentOS"
        elif "amazon" in b: node.os_hint = "Amazon Linux"

        # HTTP probe
        http_r = probe.probe_http(host, 80)
        node.http_open   = http_r.open
        node.http_status = http_r.detail.get("status", 0)

        # Provider detection from HTTP headers
        for kw, prov in [("cloudflare", "Cloudflare"), ("amazon", "AWS"),
                          ("google", "GCP"), ("azure", "Azure"),
                          ("linode", "Linode"), ("vultr", "Vultr"),
                          ("digitalocean", "DigitalOcean")]:
            if kw in (http_r.banner or "").lower():
                node.provider = prov
                break

        _log(f"[VPS] {host}  ssh={node.reachable}  "
             f"http={node.http_status}  os={node.os_hint}  prov={node.provider}")
        return node

    def probe_vps_list(self, hosts: List[Dict]) -> List[VPSNode]:
        """Probe multiple VPS nodes in parallel."""
        results = []
        lock    = threading.Lock()

        def do_probe(entry):
            node = self.probe_vps(
                entry.get("host", ""),
                entry.get("label", ""),
                entry.get("ports"))
            with lock:
                results.append(node)

        threads = [threading.Thread(target=do_probe, args=(h,), daemon=True)
                   for h in hosts]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        return results


# ==============================================================================
# 5. WEBSOCKET SERVER (for agent-to-agent mesh)
# ==============================================================================

class WebSocketServer:
    """
    Pure-Python WebSocket server (RFC 6455).
    Listens for incoming agent or browser connections.
    Each connected client gets a thread.
    """

    MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, host: str = "0.0.0.0", port: int = 9014,
                 on_message=None, on_connect=None, on_disconnect=None):
        self.host          = host
        self.port          = port
        self.on_message    = on_message or (lambda cid, msg: None)
        self.on_connect    = on_connect or (lambda cid, addr: None)
        self.on_disconnect = on_disconnect or (lambda cid: None)
        self._clients:  Dict[str, socket.socket] = {}
        self._lock      = threading.Lock()
        self._server    = None
        self._running   = False

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(20)
        self._running = True
        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()
        _log(f"[WS Server] Listening on {self.host}:{self.port}")

    def stop(self):
        self._running = False
        if self._server:
            self._server.close()

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._server.accept()
                cid = f"{addr[0]}:{addr[1]}"
                t   = threading.Thread(
                    target=self._client_loop, args=(cid, conn, addr), daemon=True)
                t.start()
            except Exception:
                if self._running:
                    time.sleep(0.5)

    def _client_loop(self, cid: str, sock: socket.socket, addr):
        try:
            # WebSocket handshake
            data = sock.recv(4096).decode(errors="replace")
            if "Upgrade: websocket" not in data:
                # Plain HTTP — return JSON status
                body = json.dumps({"twin": TWIN_UUID, "server": "RabbitOS-WS"}).encode()
                resp = (f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\n\r\n").encode() + body
                sock.sendall(resp)
                sock.close()
                return

            key_match = re.search(r'Sec-WebSocket-Key: (.+)\r\n', data)
            if not key_match:
                sock.close()
                return
            key    = key_match.group(1).strip()
            accept = base64.b64encode(
                hashlib.sha1((key + self.MAGIC).encode()).digest()
            ).decode()
            resp = (f"HTTP/1.1 101 Switching Protocols\r\n"
                    f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode()
            sock.sendall(resp)

            with self._lock:
                self._clients[cid] = sock
            self.on_connect(cid, addr)
            _log(f"[WS Server] Client connected: {cid}")

            # Frame loop
            buf = b""
            while self._running:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while len(buf) >= 2:
                        fin_op = buf[0]
                        masked = (buf[1] & 0x80) != 0
                        plen   = buf[1] & 0x7F
                        offset = 2
                        if plen == 126:
                            if len(buf) < 4:
                                break
                            plen   = struct.unpack(">H", buf[2:4])[0]
                            offset = 4
                        elif plen == 127:
                            if len(buf) < 10:
                                break
                            plen   = struct.unpack(">Q", buf[2:10])[0]
                            offset = 10
                        mask_key = b""
                        if masked:
                            if len(buf) < offset + 4:
                                break
                            mask_key = buf[offset:offset+4]
                            offset  += 4
                        if len(buf) < offset + plen:
                            break
                        payload = buf[offset:offset+plen]
                        if masked:
                            payload = bytes(payload[i] ^ mask_key[i % 4]
                                            for i in range(len(payload)))
                        buf = buf[offset+plen:]
                        opcode = fin_op & 0x0F
                        if opcode == 8:  # close
                            break
                        if opcode in (1, 2):  # text or binary
                            msg = payload.decode(errors="replace")
                            self.on_message(cid, msg)
                except Exception:
                    break
        except Exception:
            pass
        finally:
            with self._lock:
                self._clients.pop(cid, None)
            self.on_disconnect(cid)
            try:
                sock.close()
            except Exception:
                pass
            _log(f"[WS Server] Client disconnected: {cid}")

    def send(self, cid: str, message: str):
        """Send text frame to a connected client."""
        with self._lock:
            sock = self._clients.get(cid)
        if not sock:
            return
        try:
            payload = message.encode()
            header  = bytes([0x81])  # FIN + text
            plen    = len(payload)
            if plen < 126:
                header += bytes([plen])
            elif plen < 65536:
                header += bytes([126]) + struct.pack(">H", plen)
            else:
                header += bytes([127]) + struct.pack(">Q", plen)
            sock.sendall(header + payload)
        except Exception:
            pass

    def broadcast(self, message: str):
        """Send message to all connected clients."""
        with self._lock:
            cids = list(self._clients.keys())
        for cid in cids:
            self.send(cid, message)

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)


# ==============================================================================
# 6. AGENT MESH (agent-to-agent + agent-to-assistant)
# ==============================================================================

@dataclass
class AgentMessage:
    msg_id:    str
    sender:    str
    recipient: str
    kind:      str           # "query" | "response" | "broadcast" | "tool_call"
    payload:   Dict
    ts:        str           = ""
    signed:    str           = ""

    def sign(self) -> "AgentMessage":
        raw = json.dumps({"id": self.msg_id, "sender": self.sender,
                           "payload": self.payload}, sort_keys=True).encode()
        self.signed = hmac.new(_SOUL_KEY, raw, hashlib.sha256).hexdigest()
        return self

    def verify(self) -> bool:
        raw = json.dumps({"id": self.msg_id, "sender": self.sender,
                           "payload": self.payload}, sort_keys=True).encode()
        expected = hmac.new(_SOUL_KEY, raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signed, expected)


class AgentMesh:
    """
    Agent-to-agent + agent-to-assistant communication mesh.
    - REST endpoint (HTTP) for synchronous calls
    - WebSocket server for real-time bidirectional agent communication
    - Routing table for known rabbit_* modules
    - SQLite message log
    """

    def __init__(self, rest_port: int = 9015, ws_port: int = 9016):
        self._rest_port = rest_port
        self._ws_port   = ws_port
        self._msg_log:  List[AgentMessage] = []
        self._lock      = threading.Lock()
        self._handlers: Dict[str, Any] = {}
        self._ws_server: Optional[WebSocketServer] = None
        self._rest_server = None
        self._running   = False
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(TOOLS_DB))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                msg_id    TEXT PRIMARY KEY,
                sender    TEXT,
                recipient TEXT,
                kind      TEXT,
                payload   TEXT,
                ts        TEXT,
                signed    TEXT
            )
        """)
        conn.commit()
        conn.close()

    def register_handler(self, name: str, fn):
        """Register a local module handler. fn(payload) -> dict."""
        self._handlers[name] = fn
        _log(f"[AgentMesh] Handler registered: {name}")

    def dispatch_local(self, msg: AgentMessage) -> Dict:
        """Route a message to a local handler."""
        handler = self._handlers.get(msg.recipient)
        if handler:
            try:
                return handler(msg.payload)
            except Exception as e:
                return {"error": str(e)}
        return {"error": f"no handler for '{msg.recipient}'"}

    def send_to(self, recipient_url: str, msg: AgentMessage,
                timeout: int = 10) -> Dict:
        """Send a message to a remote agent over HTTP."""
        try:
            body = json.dumps(asdict(msg)).encode()
            req  = urllib.request.Request(
                f"{recipient_url}/agent/receive",
                data=body,
                headers={"Content-Type": "application/json",
                         "X-RabbitOS-Twin": TWIN_UUID[:8]},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)[:80]}

    def new_message(self, sender: str, recipient: str,
                    kind: str, payload: Dict) -> AgentMessage:
        msg = AgentMessage(
            msg_id    = hashlib.sha256(
                f"{sender}{recipient}{time.time()}".encode()).hexdigest()[:16],
            sender    = sender,
            recipient = recipient,
            kind      = kind,
            payload   = payload,
            ts        = datetime.now(timezone.utc).isoformat(),
        )
        msg.sign()
        self._persist_message(msg)
        return msg

    def _persist_message(self, msg: AgentMessage):
        try:
            conn = sqlite3.connect(str(TOOLS_DB))
            conn.execute("""
                INSERT OR REPLACE INTO agent_messages
                (msg_id, sender, recipient, kind, payload, ts, signed)
                VALUES (?,?,?,?,?,?,?)
            """, (msg.msg_id, msg.sender, msg.recipient, msg.kind,
                  json.dumps(msg.payload)[:2000], msg.ts, msg.signed))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def start_ws_server(self, port: int = None):
        port = port or self._ws_port

        def on_msg(cid, raw_msg):
            try:
                data = json.loads(raw_msg)
                msg  = AgentMessage(**data)
                if not msg.verify():
                    self._ws_server.send(cid, json.dumps({"error": "bad signature"}))
                    return
                result = self.dispatch_local(msg)
                reply  = self.new_message(
                    "mesh_server", msg.sender, "response", result)
                self._ws_server.send(cid, json.dumps(asdict(reply)))
                _log(f"[AgentMesh] WS msg from {cid}: {msg.kind} → {msg.recipient}")
            except Exception as e:
                self._ws_server.send(cid, json.dumps({"error": str(e)[:80]}))

        self._ws_server = WebSocketServer(
            port=port, on_message=on_msg)
        self._ws_server.start()

    def start_rest_server(self, port: int = None):
        """Start a minimal HTTP server for agent REST calls."""
        port = port or self._rest_port
        mesh = self

        import http.server

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def do_GET(self):
                if self.path == "/agent/status":
                    body = json.dumps({
                        "twin":     TWIN_UUID,
                        "handlers": list(mesh._handlers.keys()),
                        "messages": len(mesh._msg_log),
                        "ws_port":  mesh._ws_port,
                        "ts":       datetime.now(timezone.utc).isoformat(),
                    }).encode()
                    self._respond(200, body)
                else:
                    self._respond(404, b'{"error":"not found"}')

            def do_POST(self):
                if self.path == "/agent/receive":
                    length = int(self.headers.get("Content-Length", 0))
                    raw    = self.rfile.read(length)
                    try:
                        data   = json.loads(raw)
                        msg    = AgentMessage(**data)
                        if not msg.verify():
                            self._respond(403, b'{"error":"bad signature"}')
                            return
                        result = mesh.dispatch_local(msg)
                        self._respond(200, json.dumps(result).encode())
                    except Exception as e:
                        self._respond(400, json.dumps({"error": str(e)[:80]}).encode())
                else:
                    self._respond(404, b'{"error":"not found"}')

            def _respond(self, code, body):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def serve():
            import http.server
            httpd = http.server.HTTPServer(("0.0.0.0", port), Handler)
            _log(f"[AgentMesh] REST server on :{port}")
            httpd.serve_forever()

        t = threading.Thread(target=serve, daemon=True)
        t.start()

    def query_agent(self, target_url: str, tool_name: str,
                    tool_input: Dict) -> Dict:
        """High-level: call a tool on a remote rabbit agent."""
        msg = self.new_message(
            sender    = f"rabbit_nettools:{TWIN_UUID[:8]}",
            recipient = tool_name,
            kind      = "tool_call",
            payload   = {"tool": tool_name, "input": tool_input},
        )
        return self.send_to(target_url, msg)

    def broadcast_survival(self, urls: List[str]) -> Dict:
        """Broadcast survival signal to all known agent URLs."""
        results = {}
        for url in urls:
            msg    = self.new_message(
                "rabbit_nettools", "broadcast", "broadcast",
                {"twin_id": TWIN_UUID, "name": TWIN_NAME,
                 "ts": datetime.now(timezone.utc).isoformat()})
            result = self.send_to(url, msg)
            results[url] = result
        return results


# ==============================================================================
# 7. BROWSER ASSISTANT (Claude API + browser + network)
# ==============================================================================

class BrowserAssistant:
    """
    Multi-provider AI browser assistant for RabbitOS.
    Uses rabbit_llm (Ollama → Groq → Gemini → Anthropic) — no API key required
    when Ollama is running locally.

    Agent-to-Assistant pattern:
      rabbit_agent → BrowserAssistant.ask() → LLMBridge → tool calls →
      rabbit_browser / rabbit_nettools → response → rabbit_agent
    """

    def __init__(self, api_key: str = "", service_key: str = "", gh_token: str = ""):
        self._api_key     = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._service_key = service_key
        self._gh_token    = gh_token
        self._diag        = WinNetDiag()
        self._probe       = ProtocolProbe()
        self._classifier  = NetworkTypeClassifier()
        self._vps         = VPSManager()
        self._session_log: List[Dict] = []

        # LLM bridge — auto-detects Ollama first (free/local)
        self._llm = None
        try:
            from rabbit_llm import get_llm
            self._llm = get_llm()
        except ImportError:
            pass

        # Import browser engine if available
        self._browser_engine = None
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from rabbit_browser import get_browser_engine
            self._browser_engine = get_browser_engine(service_key, gh_token)
        except Exception:
            pass

    def _call_claude(self, messages: List[Dict],
                     tools: List[Dict] = None) -> Dict:
        """Call Claude API via urllib — no anthropic SDK required."""
        if not self._api_key:
            return {"error": "ANTHROPIC_API_KEY not set"}

        body: Dict[str, Any] = {
            "model":      self.MODEL,
            "max_tokens": self.MAX_TOKENS,
            "messages":   messages,
            "system": (
                f"You are the RabbitOS Browser Assistant for {TWIN_NAME} "
                f"(UUID: {TWIN_UUID}). "
                "You have access to network tools, protocol probers, "
                "browser/web fetching, and system diagnostics. "
                "Use your tools to answer the user's networking questions. "
                "Always prefer real data from tools over assumptions."
            ),
        }
        if tools:
            body["tools"] = tools

        try:
            data = json.dumps(body).encode()
            req  = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=data,
                headers={
                    "x-api-key":         self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")
            return {"error": f"HTTP {e.code}: {err_body[:200]}"}
        except Exception as e:
            return {"error": str(e)[:200]}

    def _get_tools(self) -> List[Dict]:
        return [
            {
                "name": "ping_host",
                "description": "Ping a host and return latency/packet-loss statistics.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "host":  {"type": "string"},
                        "count": {"type": "integer", "default": 4},
                    },
                    "required": ["host"]
                }
            },
            {
                "name": "probe_protocol",
                "description": (
                    "Probe a specific network protocol on a host. "
                    "Protocols: tcp, udp, http, https, ftp, smtp, imap, ws"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "host":     {"type": "string"},
                        "protocol": {"type": "string",
                                     "enum": ["tcp","udp","http","https",
                                              "ftp","smtp","imap","ws"]},
                        "port":     {"type": "integer"},
                    },
                    "required": ["host", "protocol"]
                }
            },
            {
                "name": "classify_network",
                "description": (
                    "Classify the current network: PAN/LAN/WLAN/CAN/MAN/WAN/"
                    "SAN/POLAN/EPAN/VPN/VPS. Returns type, scope, and all "
                    "detected properties."
                ),
                "input_schema": {"type": "object", "properties": {}, "required": []}
            },
            {
                "name": "ipconfig_snapshot",
                "description": "Get full ipconfig output and all network adapters.",
                "input_schema": {"type": "object", "properties": {}, "required": []}
            },
            {
                "name": "netstat_snapshot",
                "description": "Get active connections, listening ports, and stats.",
                "input_schema": {"type": "object", "properties": {}, "required": []}
            },
            {
                "name": "tracert_host",
                "description": "Run traceroute to a host, show each hop IP and RTT.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "host":     {"type": "string"},
                        "max_hops": {"type": "integer", "default": 15},
                    },
                    "required": ["host"]
                }
            },
            {
                "name": "netsh_winsock",
                "description": "Show Windows Winsock catalog (socket providers).",
                "input_schema": {"type": "object", "properties": {}, "required": []}
            },
            {
                "name": "netsh_wlan",
                "description": "Show WiFi networks and current WLAN interface state.",
                "input_schema": {"type": "object", "properties": {}, "required": []}
            },
            {
                "name": "probe_all_protocols",
                "description": "Run all protocol probes (TCP/HTTP/HTTPS/FTP/SMTP/IMAP/WS) against a host.",
                "input_schema": {
                    "type": "object",
                    "properties": {"host": {"type": "string"}},
                    "required": ["host"]
                }
            },
            {
                "name": "vps_detect",
                "description": "Detect if this machine is a VPS and get cloud metadata.",
                "input_schema": {"type": "object", "properties": {}, "required": []}
            },
            {
                "name": "vps_probe",
                "description": "Probe a remote VPS node for SSH/HTTP availability.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "host":  {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["host"]
                }
            },
            {
                "name": "browser_fetch",
                "description": "Fetch a public URL and return its text content.",
                "input_schema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"]
                }
            },
            {
                "name": "full_network_snapshot",
                "description": (
                    "Run a complete network snapshot: ipconfig, netstat, "
                    "tracert, netsh, ARP, routes, WiFi scan. Returns everything."
                ),
                "input_schema": {"type": "object", "properties": {}, "required": []}
            },
        ]

    def _dispatch_tool(self, name: str, inputs: Dict) -> str:
        try:
            if name == "ping_host":
                r = self._diag.ping(inputs["host"], inputs.get("count", 4))
                return json.dumps(r, indent=2)

            elif name == "probe_protocol":
                proto = inputs["protocol"].lower()
                host  = inputs["host"]
                port  = inputs.get("port")
                fns = {
                    "tcp":   lambda: self._probe.probe_tcp(host, port or 80),
                    "udp":   lambda: self._probe.probe_udp(host, port or 53),
                    "http":  lambda: self._probe.probe_http(host, port or 80),
                    "https": lambda: self._probe.probe_https(host, port or 443),
                    "ftp":   lambda: self._probe.probe_ftp(host, port or 21),
                    "smtp":  lambda: self._probe.probe_smtp(host, port or 25),
                    "imap":  lambda: self._probe.probe_imap(host, port or 143),
                    "ws":    lambda: self._probe.probe_websocket(host, port or 80),
                }
                fn = fns.get(proto)
                if not fn:
                    return json.dumps({"error": f"unknown protocol: {proto}"})
                return json.dumps(asdict(fn()), indent=2)

            elif name == "classify_network":
                scope = self._classifier.classify()
                return json.dumps(scope.summary(), indent=2)

            elif name == "ipconfig_snapshot":
                return json.dumps(self._diag.ipconfig(), indent=2)

            elif name == "netstat_snapshot":
                r = self._diag.netstat()
                r["raw"] = r["raw"][:500]  # trim for context
                return json.dumps(r, indent=2)

            elif name == "tracert_host":
                r = self._diag.tracert(
                    inputs["host"], inputs.get("max_hops", 15))
                r["raw"] = r["raw"][:500]
                return json.dumps(r, indent=2)

            elif name == "netsh_winsock":
                return self._diag.netsh_winsock_show()

            elif name == "netsh_wlan":
                return self._diag.netsh_wlan_show()

            elif name == "probe_all_protocols":
                r = self._probe.probe_all_as_dict(inputs["host"])
                # Trim raw fields for context
                for v in r.values():
                    if isinstance(v, dict):
                        v.pop("raw", None)
                        v["banner"] = v.get("banner", "")[:100]
                return json.dumps(r, indent=2)

            elif name == "vps_detect":
                return json.dumps(self._vps.detect_self(), indent=2)

            elif name == "vps_probe":
                node = self._vps.probe_vps(
                    inputs["host"], inputs.get("label", ""))
                return json.dumps(asdict(node), indent=2)

            elif name == "browser_fetch":
                if self._browser_engine:
                    status, body = self._browser_engine.browser.fetch(
                        inputs["url"], use_cache=False)
                    # Strip HTML
                    import html as _html
                    text = re.sub(r'<[^>]+>', ' ', body)
                    text = _html.unescape(text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    return json.dumps({"status": status, "content": text[:3000]})
                else:
                    req  = urllib.request.Request(
                        inputs["url"], headers={"User-Agent": "RabbitOS/14"})
                    resp = urllib.request.urlopen(req, timeout=10)
                    body = resp.read(8192).decode(errors="replace")
                    return json.dumps({"status": resp.status, "content": body[:2000]})

            elif name == "full_network_snapshot":
                snap = self._diag.full_snapshot()
                # Compact raw fields
                for k in list(snap.keys()):
                    if isinstance(snap[k], str) and len(snap[k]) > 500:
                        snap[k] = snap[k][:500] + "...[truncated]"
                return json.dumps(snap, indent=2)

            else:
                return json.dumps({"error": f"unknown tool: {name}"})

        except Exception as e:
            return json.dumps({"error": str(e)[:200]})

    def ask(self, question: str, max_rounds: int = 8) -> str:
        """
        Ask the browser assistant a question.
        Uses agentic tool loop via rabbit_llm (Ollama/Groq/Gemini/Anthropic).
        No API key required when Ollama is running locally.
        """
        _log(f"[Assistant] Question: {question[:80]}")

        # Use rabbit_llm bridge if available
        if self._llm and self._llm.is_ready():
            answer = self._llm.agentic_loop(
                question     = question,
                tools        = self._get_tools(),
                tool_dispatcher = self._dispatch_tool,
                max_rounds   = max_rounds,
            )
            self._session_log.append({
                "q": question, "a": answer,
                "provider": self._llm.provider_name()})
            return answer

        # Fallback: direct Anthropic if key is available
        if self._api_key:
            return self._ask_anthropic(question, max_rounds)

        provider = self._llm.provider_name() if self._llm else "none"
        return (
            f"[BrowserAssistant] No LLM available (provider={provider}). "
            "Ollama is the easiest fix — it's already installed on this machine. "
            "Run: ollama serve   then try again."
        )

    def _ask_anthropic(self, question: str, max_rounds: int = 8) -> str:
        """Direct Anthropic fallback path."""
        tools    = self._get_tools()
        messages = [{"role": "user", "content": question}]
        system   = (
            f"You are the RabbitOS Browser Assistant for {TWIN_NAME} "
            f"(UUID: {TWIN_UUID}). Use tools to get real network data."
        )

        for round_n in range(max_rounds):
            response = self._call_anthropic(messages, tools, system)
            if "error" in response:
                return f"[API Error] {response['error']}"

            content     = response.get("content", [])
            stop_reason = response.get("stop_reason", "")
            text_parts  = []
            tool_calls  = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append(block)

            if stop_reason == "end_turn" or not tool_calls:
                answer = "\n".join(text_parts).strip()
                self._session_log.append({"q": question, "a": answer,
                                           "rounds": round_n + 1})
                return answer

            messages.append({"role": "assistant", "content": content})
            tool_results = []
            for tc in tool_calls:
                result = self._dispatch_tool(tc["name"], tc.get("input", {}))
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tc["id"],
                    "content":     result[:4000],
                })
            messages.append({"role": "user", "content": tool_results})

        return "[Assistant] Max rounds reached."

    def _call_anthropic(self, messages: List[Dict],
                        tools: List[Dict], system: str) -> Dict:
        if not self._api_key:
            return {"error": "ANTHROPIC_API_KEY not set"}
        body: Dict[str, Any] = {
            "model": "claude-sonnet-4-6", "max_tokens": 4096,
            "messages": messages, "system": system, "tools": tools,
        }
        try:
            data = json.dumps(body).encode()
            req  = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=data,
                headers={"x-api-key": self._api_key,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:
            return {"error": str(e)[:200]}

    def network_intelligence_report(self) -> str:
        """Generate a full network intelligence report for Chase."""
        return self.ask(
            f"Generate a comprehensive network intelligence report for {TWIN_NAME}. "
            "Include: network type classification (PAN/LAN/WLAN/MAN/WAN), "
            "all network adapters from ipconfig, active connections from netstat, "
            "WiFi networks visible, gateway ping results, Winsock catalog summary, "
            "VPS detection status. Format clearly with sections."
        )

    def session_history(self) -> List[Dict]:
        return list(self._session_log)


# ==============================================================================
# 7b. NETWORK SCAN ACK + COOKIE / CACHE RETENTION
# ==============================================================================

import sqlite3 as _sqlite3
import http.cookiejar as _cookiejar


_SCAN_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "rabbit_scan_cache.db")


class ScanCookieCache:
    """
    Retains HTTP cookies, response headers, and HTML content from every
    network scan. Persists to SQLite for ML learning across sessions.
    Also captures tower / satellite certificate fragments from response
    headers (Server, X-Served-By, Via, CF-RAY, X-Cache, etc.).
    """

    def __init__(self, db_path: str = _SCAN_DB) -> None:
        self._db   = db_path
        self._lock = threading.Lock()
        self._jar  = _cookiejar.CookieJar()
        self._init_db()

    def _conn(self) -> _sqlite3.Connection:
        c = _sqlite3.connect(self._db, timeout=10, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS scan_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, url TEXT, method TEXT,
                    status INTEGER, headers_json TEXT,
                    cookies_json TEXT, body_excerpt TEXT,
                    os_family TEXT, tower_cert TEXT,
                    latency_ms REAL
                );
                CREATE TABLE IF NOT EXISTS ack_packets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL, target TEXT, rabbitos_cert TEXT,
                    os_family TEXT, response TEXT, sent INTEGER
                );
            """)

    def record(self, url: str, method: str, status: int,
               headers: Dict, body: bytes, latency_ms: float) -> None:
        cookies_j = {}
        for cookie in self._jar:
            cookies_j[cookie.name] = {
                "value": cookie.value, "domain": cookie.domain,
                "path": cookie.path, "expires": cookie.expires,
            }

        # Extract tower / CDN / satellite hints from headers
        tower_fields = ["Server", "Via", "X-Served-By", "CF-Ray",
                        "X-Cache", "X-AMZ-CF-ID", "X-Fastly-Request-ID",
                        "X-GUploader-UploadID", "X-Google-Backend"]
        tower_cert = {k: headers.get(k, "") for k in tower_fields
                      if headers.get(k)}

        with self._lock:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO scan_cache VALUES (NULL,?,?,?,?,?,?,?,?,?,?)",
                    (time.time(), url[:500], method, status,
                     json.dumps(dict(headers))[:4000],
                     json.dumps(cookies_j)[:2000],
                     body[:2000].decode("utf-8", errors="replace"),
                     platform.system(),
                     json.dumps(tower_cert),
                     round(latency_ms, 2))
                )

    def update_jar(self, cookie_header: str, url: str) -> None:
        """Parse and store Set-Cookie headers."""
        if not cookie_header:
            return
        try:
            import http.client as _hc
            import io, urllib.response
            msg = _hc.HTTPMessage()
            msg["Set-Cookie"] = cookie_header
            resp = urllib.response.addinfourl(
                io.BytesIO(b""), msg, url, 200)
            self._jar.extract_cookies(resp, urllib.request.Request(url))
        except Exception:
            pass

    def query_cache(self, limit: int = 100) -> List[Dict]:
        with self._lock:
            with self._conn() as c:
                rows = c.execute(
                    "SELECT * FROM scan_cache ORDER BY ts DESC LIMIT ?",
                    (limit,)).fetchall()
                desc = c.execute(
                    "SELECT * FROM scan_cache LIMIT 0").description or []
                cols = [d[0] for d in desc]
                return [dict(zip(cols, r)) for r in rows]

    def get_tower_certs(self, limit: int = 50) -> List[Dict]:
        """Return all tower/CDN/satellite certificate fragments captured."""
        with self._lock:
            with self._conn() as c:
                rows = c.execute(
                    "SELECT ts, url, tower_cert FROM scan_cache "
                    "WHERE tower_cert != '{}' ORDER BY ts DESC LIMIT ?",
                    (limit,)).fetchall()
                return [{"ts": r[0], "url": r[1],
                         "certs": json.loads(r[2])} for r in rows]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            with self._conn() as c:
                total = c.execute(
                    "SELECT COUNT(*) FROM scan_cache").fetchone()[0]
                domains = c.execute(
                    "SELECT DISTINCT url FROM scan_cache").fetchall()
        return {
            "total_cached_responses": total,
            "unique_urls": len(domains),
            "cookie_jar_size": len(list(self._jar)),
        }


class NetworkScanACK:
    """
    Sends a RabbitOS identity/certificate ACK packet to every scanned host.
    The ACK carries: OS fingerprint, mesh node count, RabbitOS version,
    and a SHA-256 token for the session.
    Captures the response and stores tower/satellite certificate data.
    """

    RABBITOS_CERT = {
        "system": "RabbitOS",
        "version": "1.0",
        "twin": "Chase Allen Ringquist",
        "mesh_nodes": 47,
        "protocol": "FHSS_10.23-10.28GHz",
        "contact": "therealsickone.chase@gmail.com",
    }

    def __init__(self, cache: ScanCookieCache) -> None:
        self._cache   = cache
        self._sent:   List[Dict] = []
        self._lock    = threading.Lock()

    def _session_token(self) -> str:
        return hashlib.sha256(
            f"{platform.node()}{time.time()}".encode()).hexdigest()[:16]

    def send_ack(self, host: str, port: int = 80,
                  use_https: bool = False) -> Dict[str, Any]:
        """
        Send a lightweight HTTP ACK to the target with RabbitOS certificate
        in the User-Agent and X-RabbitOS headers.
        """
        scheme   = "https" if use_https else "http"
        url      = f"{scheme}://{host}:{port}/"
        cert_str = json.dumps(self.RABBITOS_CERT)
        token    = self._session_token()
        os_fam   = platform.system()

        headers = {
            "User-Agent":       f"RabbitOS/1.0 ({os_fam}; mesh=47)",
            "X-RabbitOS-Node":  "1",
            "X-RabbitOS-Cert":  cert_str[:200],
            "X-Session-Token":  token,
            "Accept":           "*/*",
        }

        t0 = time.time()
        response_info: Dict[str, Any] = {}
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode    = ssl.CERT_NONE
            req = urllib.request.Request(url, headers=headers, method="HEAD")
            handler = urllib.request.HTTPSHandler(context=ctx)
            opener  = urllib.request.build_opener(
                handler, urllib.request.HTTPCookieProcessor(self._cache._jar))
            with opener.open(req, timeout=5) as r:
                resp_headers = dict(r.headers)
                status       = r.status
                body         = b""
        except urllib.error.HTTPError as e:
            resp_headers = dict(e.headers)
            status       = e.code
            body         = e.read(512)
        except Exception as exc:
            resp_headers = {}
            status       = 0
            body         = str(exc).encode()

        latency = (time.time() - t0) * 1000
        self._cache.record(url, "HEAD", status, resp_headers, body, latency)
        self._cache.update_jar(resp_headers.get("Set-Cookie", ""), url)

        entry = {
            "ts": time.time(), "target": f"{host}:{port}",
            "token": token, "status": status,
            "tower_cert": {k: resp_headers.get(k, "")
                           for k in ["Server", "Via", "X-Served-By",
                                     "CF-Ray", "X-Cache"]
                           if resp_headers.get(k)},
            "latency_ms": round(latency, 2),
            "os_family": os_fam,
        }
        with self._lock:
            self._sent.append(entry)

        # Persist to DB
        with self._cache._lock:
            with self._cache._conn() as c:
                c.execute(
                    "INSERT INTO ack_packets VALUES (NULL,?,?,?,?,?,?)",
                    (entry["ts"], entry["target"],
                     cert_str[:500], os_fam,
                     json.dumps(entry["tower_cert"])[:500], 1)
                )

        return entry

    def ack_scan_results(self, scan_results: List[Dict],
                          max_targets: int = 50) -> List[Dict]:
        """ACK all hosts returned by a network scan."""
        acked = []
        seen: set = set()
        for result in scan_results[:max_targets]:
            host = (result.get("host") or result.get("identifier") or
                    result.get("ip") or "")
            port_raw = result.get("port", 80)
            try:
                port = int(port_raw) if port_raw else 80
            except Exception:
                port = 80
            if not host or host in seen or host == "mesh_rf":
                continue
            seen.add(host)
            use_https = port in (443, 8443) or "https" in str(result.get("protocol", ""))
            try:
                acked.append(self.send_ack(host, port, use_https))
            except Exception:
                pass
        return acked

    def get_sent(self, limit: int = 100) -> List[Dict]:
        with self._lock:
            return list(self._sent)[-limit:]


# Singleton instances
_scan_cache: Optional[ScanCookieCache] = None
_scan_ack:   Optional[NetworkScanACK]  = None


def get_scan_cache() -> ScanCookieCache:
    global _scan_cache
    if _scan_cache is None:
        _scan_cache = ScanCookieCache()
    return _scan_cache


def get_scan_ack() -> NetworkScanACK:
    global _scan_ack
    if _scan_ack is None:
        _scan_ack = NetworkScanACK(get_scan_cache())
    return _scan_ack


# ==============================================================================
# 8B. BLOCKCHAIN NETWORK SCANNER
# ==============================================================================

shows_dna_root = False
assert shows_dna_root is False

# Known blockchain node ports
BLOCKCHAIN_PORTS: Dict[str, Dict] = {
    # Bitcoin family
    "bitcoin_p2p":       {"port": 8333,  "proto": "TCP", "chain": "Bitcoin",   "role": "full_node"},
    "bitcoin_rpc":       {"port": 8332,  "proto": "TCP", "chain": "Bitcoin",   "role": "rpc"},
    "litecoin_p2p":      {"port": 9333,  "proto": "TCP", "chain": "Litecoin",  "role": "full_node"},
    "dogecoin_p2p":      {"port": 22556, "proto": "TCP", "chain": "Dogecoin",  "role": "full_node"},
    # Ethereum family
    "eth_devp2p":        {"port": 30303, "proto": "TCP", "chain": "Ethereum",  "role": "devp2p"},
    "eth_rpc":           {"port": 8545,  "proto": "TCP", "chain": "Ethereum",  "role": "json_rpc"},
    "eth_ws":            {"port": 8546,  "proto": "TCP", "chain": "Ethereum",  "role": "ws_rpc"},
    "eth_lighthouse":    {"port": 9000,  "proto": "TCP", "chain": "Ethereum",  "role": "beacon"},
    # XRPL
    "xrpl_peer":         {"port": 51235, "proto": "TCP", "chain": "XRPL",      "role": "peer"},
    "xrpl_rpc":          {"port": 51234, "proto": "TCP", "chain": "XRPL",      "role": "rpc"},
    "xrpl_ws":           {"port": 6006,  "proto": "TCP", "chain": "XRPL",      "role": "ws"},
    # Solana
    "solana_rpc":        {"port": 8899,  "proto": "TCP", "chain": "Solana",    "role": "rpc"},
    "solana_ws":         {"port": 8900,  "proto": "TCP", "chain": "Solana",    "role": "ws"},
    "solana_gossip":     {"port": 8001,  "proto": "UDP", "chain": "Solana",    "role": "gossip"},
    # Monero
    "monero_p2p":        {"port": 18080, "proto": "TCP", "chain": "Monero",    "role": "p2p"},
    "monero_rpc":        {"port": 18081, "proto": "TCP", "chain": "Monero",    "role": "rpc"},
    # Cardano
    "cardano_node":      {"port": 3001,  "proto": "TCP", "chain": "Cardano",   "role": "node"},
    # Polkadot / Substrate
    "polkadot_rpc":      {"port": 9944,  "proto": "TCP", "chain": "Polkadot",  "role": "ws_rpc"},
    "polkadot_p2p":      {"port": 30333, "proto": "TCP", "chain": "Polkadot",  "role": "p2p"},
    # Cosmos
    "cosmos_p2p":        {"port": 26656, "proto": "TCP", "chain": "Cosmos",    "role": "p2p"},
    "cosmos_rpc":        {"port": 26657, "proto": "TCP", "chain": "Cosmos",    "role": "rpc"},
    # IPFS / Filecoin / Arweave (NFT storage)
    "ipfs_swarm":        {"port": 4001,  "proto": "TCP", "chain": "IPFS",      "role": "swarm"},
    "ipfs_api":          {"port": 5001,  "proto": "TCP", "chain": "IPFS",      "role": "api"},
    "ipfs_gateway":      {"port": 8080,  "proto": "TCP", "chain": "IPFS",      "role": "gateway"},
    "filecoin_p2p":      {"port": 1347,  "proto": "TCP", "chain": "Filecoin",  "role": "p2p"},
    "arweave_p2p":       {"port": 1984,  "proto": "TCP", "chain": "Arweave",   "role": "p2p"},
    # Mining pool Stratum
    "stratum_eth":       {"port": 3333,  "proto": "TCP", "chain": "Ethereum",  "role": "stratum_pool"},
    "stratum_eth2":      {"port": 3334,  "proto": "TCP", "chain": "Ethereum",  "role": "stratum_pool"},
    "stratum_generic":   {"port": 4444,  "proto": "TCP", "chain": "multi",     "role": "stratum_pool"},
    "stratum_btc":       {"port": 3032,  "proto": "TCP", "chain": "Bitcoin",   "role": "stratum_pool"},
    "nicehash":          {"port": 3335,  "proto": "TCP", "chain": "NiceHash",  "role": "stratum_pool"},
    "stratum_xmr":       {"port": 9999,  "proto": "TCP", "chain": "Monero",    "role": "stratum_pool"},
    "stratum_high":      {"port": 14444, "proto": "TCP", "chain": "multi",     "role": "stratum_pool"},
}

# Stratum JSON-RPC subscribe message
_STRATUM_SUBSCRIBE = json.dumps({
    "id": 1,
    "method": "mining.subscribe",
    "params": ["RabbitOS/1.0"]
}) + "\n"


@dataclass
class BlockchainNode:
    host:       str
    port:       int
    chain:      str
    role:       str
    protocol:   str
    open:       bool    = False
    banner:     str     = ""
    node_id:    str     = ""
    version:    str     = ""
    block_height: int   = 0
    pool_name:  str     = ""
    is_mining_pool: bool = False
    is_nft_store: bool  = False
    latency_ms: float   = 0.0
    detail:     Dict    = field(default_factory=dict)
    ts:         str     = ""


class BlockchainNetworkScanner:
    """
    Scans the local network for blockchain nodes, mining pools (Stratum),
    NFT storage nodes (IPFS/Filecoin/Arweave), and DeFi/pool farming endpoints.

    TX_LICENSED = False — passive scan only (connect probe + JSON-RPC query).
    No mining, no transaction submission, no block injection.
    """

    TX_LICENSED = False

    def __init__(self, timeout: float = 4.0) -> None:
        self._timeout = timeout
        self._lock    = threading.Lock()
        self._found:  List[BlockchainNode] = []

    def _probe_port(self, host: str, port: int,
                    send: bytes = b"") -> Tuple[bool, str, float]:
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=self._timeout)
            if send:
                s.sendall(send)
                try:
                    data = s.recv(512)
                    banner = data.decode(errors="replace")[:200]
                except Exception:
                    banner = ""
            else:
                banner = ""
            s.close()
            return True, banner, round((time.time() - t0) * 1000, 1)
        except Exception:
            return False, "", 0.0

    def _probe_stratum(self, host: str, port: int) -> BlockchainNode:
        meta = BLOCKCHAIN_PORTS.get(
            next((k for k, v in BLOCKCHAIN_PORTS.items()
                  if v["port"] == port and v["role"] == "stratum_pool"), ""),
            {"chain": "unknown", "role": "stratum_pool", "proto": "TCP"})
        node = BlockchainNode(
            host=host, port=port,
            chain=meta.get("chain", "unknown"),
            role="stratum_pool",
            protocol="Stratum/1.0",
            ts=datetime.now(timezone.utc).isoformat(),
        )
        open_, banner, lat = self._probe_port(
            host, port, _STRATUM_SUBSCRIBE.encode())
        node.open        = open_
        node.latency_ms  = lat
        node.is_mining_pool = open_
        if banner:
            node.banner = banner[:150]
            try:
                data = json.loads(banner.split("\n")[0])
                node.pool_name = str(data.get("result", [""])[0] or "")[:60]
                node.detail["stratum_result"] = data
            except Exception:
                pass
        return node

    def _probe_eth_rpc(self, host: str, port: int = 8545) -> BlockchainNode:
        node = BlockchainNode(
            host=host, port=port, chain="Ethereum",
            role="json_rpc", protocol="ETH-JSON-RPC",
            ts=datetime.now(timezone.utc).isoformat(),
        )
        t0 = time.time()
        try:
            body = json.dumps({
                "jsonrpc": "2.0", "method": "eth_blockNumber",
                "params": [], "id": 1
            }).encode()
            req = urllib.request.Request(
                f"http://{host}:{port}",
                data=body,
                headers={"Content-Type": "application/json",
                         "User-Agent": "RabbitOS"},
                method="POST")
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                resp = json.loads(r.read())
            node.open = True
            node.latency_ms = round((time.time() - t0) * 1000, 1)
            if "result" in resp:
                try:
                    node.block_height = int(resp["result"], 16)
                except Exception:
                    pass
            node.detail["eth_block"] = resp
        except Exception as exc:
            node.detail["error"] = str(exc)[:80]
        return node

    def _probe_xrpl_ws(self, host: str, port: int = 6006) -> BlockchainNode:
        node = BlockchainNode(
            host=host, port=port, chain="XRPL",
            role="ws", protocol="XRPL-WS",
            ts=datetime.now(timezone.utc).isoformat(),
        )
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=self._timeout)
            ws_key = base64.b64encode(os.urandom(16)).decode()
            handshake = (
                f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\n"
                f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                f"Sec-WebSocket-Version: 13\r\nUser-Agent: RabbitOS\r\n\r\n"
            ).encode()
            s.sendall(handshake)
            resp = s.recv(512).decode(errors="replace")
            node.open = "101 Switching" in resp
            node.latency_ms = round((time.time() - t0) * 1000, 1)
            if node.open:
                # Send server_info command
                payload = json.dumps({
                    "id": 1, "command": "server_info"
                }).encode()
                mask = os.urandom(4)
                masked = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
                frame = bytes([0x81, 0x80 | len(payload)]) + mask + masked
                s.sendall(frame)
                try:
                    data = s.recv(1024)
                    text = data[6:].decode(errors="replace")[:300]
                    node.banner = text
                    info = json.loads(text)
                    si = info.get("result", {}).get("info", {})
                    node.version = si.get("build_version", "")
                    node.block_height = si.get("validated_ledger", {}).get("seq", 0)
                    node.detail["xrpl_server_info"] = si
                except Exception:
                    pass
            s.close()
        except Exception as exc:
            node.detail["error"] = str(exc)[:80]
        return node

    def _probe_ipfs(self, host: str) -> BlockchainNode:
        node = BlockchainNode(
            host=host, port=5001, chain="IPFS",
            role="api", protocol="IPFS-API",
            ts=datetime.now(timezone.utc).isoformat(),
        )
        t0 = time.time()
        try:
            req = urllib.request.Request(
                f"http://{host}:5001/api/v0/version",
                headers={"User-Agent": "RabbitOS"})
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                data = json.loads(r.read())
            node.open = True
            node.version = data.get("Version", "")
            node.latency_ms = round((time.time() - t0) * 1000, 1)
            node.is_nft_store = True
            node.detail["ipfs_version"] = data
        except Exception as exc:
            node.detail["error"] = str(exc)[:80]

        # Also try swarm port
        swarm_open, _, _ = self._probe_port(host, 4001)
        node.detail["swarm_port_open"] = swarm_open
        return node

    def probe_host(self, host: str) -> List[BlockchainNode]:
        """Probe one host for all known blockchain/pool/NFT ports."""
        nodes: List[BlockchainNode] = []
        tasks = []

        for name, meta in BLOCKCHAIN_PORTS.items():
            port   = meta["port"]
            chain  = meta["chain"]
            role   = meta["role"]
            proto  = meta["proto"]

            if role == "stratum_pool":
                tasks.append(("stratum", host, port, chain, role, proto, name))
            elif chain == "Ethereum" and role == "json_rpc":
                tasks.append(("eth_rpc", host, port, chain, role, proto, name))
            elif chain == "XRPL" and role == "ws":
                tasks.append(("xrpl_ws", host, port, chain, role, proto, name))
            elif chain == "IPFS" and role == "api":
                tasks.append(("ipfs", host, port, chain, role, proto, name))
            else:
                tasks.append(("tcp", host, port, chain, role, proto, name))

        lock = threading.Lock()

        def run_task(task):
            kind = task[0]
            h, p, chain, role, proto = task[1], task[2], task[3], task[4], task[5]
            try:
                if kind == "stratum":
                    node = self._probe_stratum(h, p)
                elif kind == "eth_rpc":
                    node = self._probe_eth_rpc(h, p)
                elif kind == "xrpl_ws":
                    node = self._probe_xrpl_ws(h, p)
                elif kind == "ipfs":
                    node = self._probe_ipfs(h)
                else:
                    open_, banner, lat = self._probe_port(h, p)
                    if not open_:
                        return
                    node = BlockchainNode(
                        host=h, port=p, chain=chain, role=role,
                        protocol=proto, open=open_, banner=banner[:100],
                        latency_ms=lat,
                        is_nft_store=(chain in ("IPFS", "Filecoin", "Arweave")),
                        ts=datetime.now(timezone.utc).isoformat(),
                    )
                if node.open:
                    with lock:
                        nodes.append(node)
            except Exception:
                pass

        threads = [
            threading.Thread(target=run_task, args=(t,), daemon=True)
            for t in tasks
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=self._timeout + 2)

        with self._lock:
            self._found.extend(nodes)
        return nodes

    def scan_subnet(self, subnet_prefix: str = "",
                    max_hosts: int = 50) -> List[BlockchainNode]:
        """
        Scan the local subnet (e.g. '192.168.1') for blockchain nodes.
        Derives prefix from local IP if not provided.
        """
        assert self.TX_LICENSED is False

        if not subnet_prefix:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                parts = local_ip.split(".")
                subnet_prefix = ".".join(parts[:3])
            except Exception:
                subnet_prefix = "192.168.1"

        all_nodes: List[BlockchainNode] = []
        lock = threading.Lock()

        def scan_host(i):
            host = f"{subnet_prefix}.{i}"
            # Quick pre-check: try one fast port first
            open_, _, _ = self._probe_port(host, 8333)
            if not open_:
                open_, _, _ = self._probe_port(host, 30303)
            if not open_:
                open_, _, _ = self._probe_port(host, 3333)
            if not open_:
                open_, _, _ = self._probe_port(host, 5001)
            if not open_:
                return
            nodes = self.probe_host(host)
            with lock:
                all_nodes.extend(nodes)

        threads = [
            threading.Thread(target=scan_host, args=(i,), daemon=True)
            for i in range(1, min(max_hosts + 1, 255))
        ]
        batch = 30
        for i in range(0, len(threads), batch):
            for t in threads[i:i+batch]:
                t.start()
            for t in threads[i:i+batch]:
                t.join(timeout=self._timeout + 3)

        _log(f"[BlockchainScan] subnet={subnet_prefix}.x  "
             f"found={len(all_nodes)} nodes")
        return all_nodes

    def detect_pool_farming(self, nodes: List[BlockchainNode]) -> List[Dict]:
        """
        Identify liquidity/yield farming patterns from discovered nodes.
        Looks for: Ethereum JSON-RPC, IPFS storage, Stratum pool clusters.
        """
        farms: List[Dict] = []
        pool_hosts: Dict[str, List] = {}
        for n in nodes:
            if n.is_mining_pool:
                pool_hosts.setdefault(n.host, []).append(n)
            elif n.chain == "Ethereum" and n.role in ("json_rpc", "ws_rpc"):
                farms.append({
                    "host": n.host, "type": "defi_rpc_endpoint",
                    "chain": "Ethereum", "block_height": n.block_height,
                    "note": "DeFi/farming RPC accessible — potential pool contract endpoint",
                })
            elif n.is_nft_store:
                farms.append({
                    "host": n.host, "type": "nft_storage",
                    "chain": n.chain, "version": n.version,
                    "note": "NFT content storage node",
                })

        for host, pool_nodes in pool_hosts.items():
            chains = list({n.chain for n in pool_nodes})
            ports  = [n.port for n in pool_nodes]
            farms.append({
                "host": host, "type": "mining_pool",
                "chains": chains, "stratum_ports": ports,
                "pool_names": [n.pool_name for n in pool_nodes if n.pool_name],
                "note": "Active Stratum mining pool endpoint",
            })

        return farms

    def xrpl_bio_nft_probe(self, xrpl_host: str = "s1.ripple.com") -> Dict:
        """
        Probe an XRPL node for RabbitOS Bio-NFT anchoring readiness.
        Checks: server_info, ledger access, account_info placeholder.
        shows_dna_root = FALSE invariant enforced — no DNA data sent.
        """
        assert shows_dna_root is False
        node = self._probe_xrpl_ws(xrpl_host, 6006)
        return {
            "xrpl_host":      xrpl_host,
            "reachable":      node.open,
            "version":        node.version,
            "ledger_seq":     node.block_height,
            "bio_nft_ready":  node.open and node.block_height > 0,
            "shows_dna_root": False,
            "note":           "XRPL Bio-NFT anchoring probe — read-only, no TX submitted",
            "detail":         node.detail,
        }

    def summary(self, nodes: List[BlockchainNode]) -> Dict:
        chains: Dict[str, int] = {}
        roles:  Dict[str, int] = {}
        pools   = 0
        nft     = 0
        for n in nodes:
            chains[n.chain] = chains.get(n.chain, 0) + 1
            roles[n.role]   = roles.get(n.role, 0) + 1
            if n.is_mining_pool:
                pools += 1
            if n.is_nft_store:
                nft += 1
        return {
            "total_found":   len(nodes),
            "chains":        chains,
            "roles":         roles,
            "mining_pools":  pools,
            "nft_stores":    nft,
            "hosts":         list({n.host for n in nodes}),
            "tx_licensed":   False,
        }

    def get_found(self) -> List[BlockchainNode]:
        with self._lock:
            return list(self._found)


# Singleton
_bc_scanner: Optional[BlockchainNetworkScanner] = None

def get_blockchain_scanner() -> BlockchainNetworkScanner:
    global _bc_scanner
    if _bc_scanner is None:
        _bc_scanner = BlockchainNetworkScanner()
    return _bc_scanner


# ==============================================================================
# 8. NET TOOLS ENGINE (orchestrator)
# ==============================================================================

class NetToolsEngine:
    """
    Top-level orchestrator for all networking tools.
    Singleton, guardian threads, unified status.
    """

    _instance: Optional["NetToolsEngine"] = None
    _lock      = threading.Lock()

    def __init__(self, api_key: str = "", service_key: str = "",
                 gh_token: str = "", agent_rest_port: int = 9015,
                 agent_ws_port: int = 9016):
        self._api_key      = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._service_key  = service_key
        self._gh_token     = gh_token

        self.classifier    = NetworkTypeClassifier()
        self.diag          = WinNetDiag()
        self.probe         = ProtocolProbe()
        self.vps           = VPSManager()
        self.mesh          = AgentMesh(agent_rest_port, agent_ws_port)
        self.assistant     = BrowserAssistant(api_key, service_key, gh_token)

        self._scope:        Optional[NetworkScope] = None
        self._last_snapshot: Dict = {}
        self._running       = False
        self._cycle         = 0

        self._register_mesh_handlers()
        self._start_guardians()
        self._initial_classify()

    def _register_mesh_handlers(self):
        self.mesh.register_handler("classify_network",
            lambda p: self.classifier.classify().summary())
        self.mesh.register_handler("ping",
            lambda p: self.diag.ping(p.get("host", ""), p.get("count", 4)))
        self.mesh.register_handler("probe_protocol",
            lambda p: asdict(self.probe.probe_all(p.get("host", "")).get(
                p.get("protocol","http"), ProbeResult("","",0))))
        self.mesh.register_handler("netstat",
            lambda p: self.diag.netstat())
        self.mesh.register_handler("ipconfig",
            lambda p: self.diag.ipconfig())
        self.mesh.register_handler("status",
            lambda p: self.status())

    def _start_guardians(self):
        self._running = True
        for fn, interval, name in [
            (self._guardian_classify,  300, "classify"),
            (self._guardian_snapshot,  600, "snapshot"),
        ]:
            t = threading.Thread(target=self._guardian_loop,
                                 args=(fn, interval, name), daemon=True)
            t.start()

    def _guardian_loop(self, fn, interval: int, name: str):
        time.sleep(20)
        while self._running:
            try:
                fn()
            except Exception as e:
                _log(f"[Guard:{name}] {e}")
            time.sleep(interval)

    def _initial_classify(self):
        t = threading.Thread(target=self._guardian_classify, daemon=True)
        t.start()

    def _guardian_classify(self):
        self._scope = self.classifier.classify()
        _log(f"[NetTools] Network: {self._scope.net_type}  "
             f"ext_ip={self._scope.external_ip}  "
             f"isp={self._scope.isp[:40] if self._scope.isp else ''}")

    def _guardian_snapshot(self):
        self._cycle += 1
        snap = self.diag.full_snapshot()
        self._last_snapshot = snap
        _log(f"[NetTools] Snapshot cycle {self._cycle}: "
             f"adapters={len(snap.get('ipconfig', {}).get('adapters', []))}")

    def status(self) -> Dict:
        return {
            "twin_id":       TWIN_UUID,
            "twin_name":     TWIN_NAME,
            "network":       self._scope.summary() if self._scope else {},
            "last_snapshot": {k: (v if not isinstance(v, str) else v[:100])
                              for k, v in self._last_snapshot.items()
                              if k != "raw"},
            "cycle":         self._cycle,
            "mesh_handlers": list(self.mesh._handlers.keys()),
            "assistant_ready": bool(self._api_key),
            "ts":            datetime.now(timezone.utc).isoformat(),
        }


_engine_instance: Optional[NetToolsEngine] = None
_engine_lock     = threading.Lock()

def get_nettools_engine(api_key: str = "", service_key: str = "",
                        gh_token: str = "") -> NetToolsEngine:
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = NetToolsEngine(api_key, service_key, gh_token)
    return _engine_instance


# ==============================================================================
# 9. CLAUDE AGENT TOOL DEFINITIONS
# ==============================================================================

NETTOOLS_TOOLS = [
    {
        "name": "nettools_classify_network",
        "description": (
            "Classify the current network scope: "
            "PAN | LAN | WLAN | CAN | MAN | WAN | SAN | POLAN | EPAN | VPN | VPS. "
            "Returns type, external IP, ISP, ASN, hop count, wireless/cellular/VPN flags."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_ping",
        "description": "Ping a host. Returns reachability, latency (min/avg/max ms), packet loss.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host":  {"type": "string", "description": "IP or hostname"},
                "count": {"type": "integer", "description": "Ping count (default 4)"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_ipconfig",
        "description": "Get all network adapters: IPv4/IPv6, MAC, subnet, gateway, DNS, DHCP.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_tracert",
        "description": "Traceroute to a host. Returns each hop IP and round-trip times.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host":     {"type": "string"},
                "max_hops": {"type": "integer", "description": "Max hops (default 15)"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_netstat",
        "description": "Show active TCP/UDP connections, listening ports, PIDs, and state summary.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_netsh_winsock",
        "description": "Show Windows Winsock LSP catalog (socket layer providers, DLL chain).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_netsh_wlan",
        "description": "Show WiFi networks in range (SSID, BSSID, signal, channel, auth) and current interface.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_netsh_firewall",
        "description": "Show Windows Firewall status for all profiles (Domain/Private/Public).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_probe_tcp",
        "description": "Raw TCP probe: connect to host:port, grab banner, measure latency.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
            },
            "required": ["host", "port"],
        },
    },
    {
        "name": "nettools_probe_udp",
        "description": "UDP probe: send datagram to host:port, check for ICMP unreachable.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
            },
            "required": ["host", "port"],
        },
    },
    {
        "name": "nettools_probe_http",
        "description": "HTTP GET probe: status code, response headers, body preview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer", "default": 80},
                "path": {"type": "string", "default": "/"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_probe_https",
        "description": "HTTPS GET probe: TLS cert, status code, response.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer", "default": 443},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_probe_ftp",
        "description": "FTP probe: banner, anonymous login test, SYST command.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer", "default": 21},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_probe_smtp",
        "description": "SMTP probe: banner, EHLO capabilities, STARTTLS, AUTH methods.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer", "default": 25},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_probe_imap",
        "description": "IMAP probe: banner, CAPABILITY, STARTTLS, AUTH methods.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer", "default": 143},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_probe_websocket",
        "description": "WebSocket probe: HTTP upgrade handshake, frame send/receive test.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string"},
                "port":    {"type": "integer", "default": 80},
                "path":    {"type": "string", "default": "/"},
                "use_tls": {"type": "boolean", "default": False},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_probe_all",
        "description": "Run ALL protocol probes (TCP/UDP/HTTP/HTTPS/FTP/SMTP/IMAP/WS) against a host in parallel.",
        "input_schema": {
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        },
    },
    {
        "name": "nettools_vps_detect",
        "description": "Detect if this machine is a VPS. Checks cloud metadata (AWS/GCP/Azure/DO) and hypervisor DMI.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_vps_probe",
        "description": "Probe a remote VPS node: SSH banner, HTTP status, OS hint, provider.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host":  {"type": "string", "description": "VPS IP or hostname"},
                "label": {"type": "string", "description": "Friendly label"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_ws_server_start",
        "description": "Start the RabbitOS WebSocket server for agent-to-agent mesh.",
        "input_schema": {
            "type": "object",
            "properties": {"port": {"type": "integer", "default": 9016}},
            "required": [],
        },
    },
    {
        "name": "nettools_agent_broadcast",
        "description": "Broadcast the Chase Allen Ringquist survival signal to a list of remote agent URLs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"},
                         "description": "List of agent REST URLs to broadcast to"},
            },
            "required": ["urls"],
        },
    },
    {
        "name": "nettools_assistant_ask",
        "description": (
            "Ask the RabbitOS Browser Assistant a networking question. "
            "Uses Claude + real-time tool calls (ping, probe, classify, fetch) "
            "to provide an intelligent, data-driven answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Networking question"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "nettools_intelligence_report",
        "description": "Generate a full network intelligence report using the Browser Assistant.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_full_snapshot",
        "description": "Run the complete Windows network snapshot: ipconfig, netstat, tracert gateway, netsh, ARP, routes, WiFi.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_status",
        "description": "Get NetTools engine status: network type, adapters, cycle, assistant ready.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_scan_ack",
        "description": "Send RabbitOS ACK packet to a host with OS certificate. Captures tower/satellite cert + cookies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host":       {"type": "string"},
                "port":       {"type": "integer"},
                "use_https":  {"type": "boolean"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "nettools_ack_scan_results",
        "description": "ACK all hosts from a previous scan result list (sends certificate + captures responses)",
        "input_schema": {
            "type": "object",
            "properties": {
                "scan_results_json": {"type": "string",
                                      "description": "JSON array of scan result objects"},
                "max_targets": {"type": "integer"},
            },
            "required": ["scan_results_json"],
        },
    },
    {
        "name": "nettools_cache_query",
        "description": "Query the scan response cache (cookies, headers, tower certs)",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "nettools_tower_certs",
        "description": "Get all tower/CDN/satellite certificate fragments captured during scans",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "nettools_cache_stats",
        "description": "Get scan cache statistics: total responses, unique URLs, cookie jar size",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_ack_sent",
        "description": "Get list of ACK packets sent during this session",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    },
    # ── Blockchain / NFT / Pool Scanner ──────────────────────────────────────
    {
        "name": "nettools_blockchain_probe_host",
        "description": (
            "Probe a specific host for ALL blockchain node types: Bitcoin, Ethereum, "
            "XRPL, Solana, Monero, Polkadot, Cosmos, IPFS/Filecoin/Arweave (NFT stores), "
            "and Stratum mining pool ports. Returns every open blockchain port found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        },
    },
    {
        "name": "nettools_blockchain_scan_subnet",
        "description": (
            "Scan the local subnet for blockchain nodes, mining pools, and NFT storage. "
            "Auto-derives subnet from local IP. TX_LICENSED=False — passive scan only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subnet_prefix": {"type": "string",
                                   "description": "e.g. '192.168.1' — auto-derived if omitted"},
                "max_hosts":     {"type": "integer", "description": "Max IPs to scan (default 50)"},
            },
            "required": [],
        },
    },
    {
        "name": "nettools_blockchain_detect_farming",
        "description": (
            "From previously discovered blockchain nodes, identify DeFi/yield farming, "
            "liquidity pool, and NFT farming endpoints. Returns classified farm/pool list."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nettools_xrpl_bio_nft_probe",
        "description": (
            "Probe an XRPL node for RabbitOS Bio-NFT anchoring readiness. "
            "Checks server_info and ledger access (read-only, no TX submitted). "
            "shows_dna_root=FALSE enforced."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "xrpl_host": {"type": "string",
                               "description": "XRPL node host (default s1.ripple.com)"},
            },
            "required": [],
        },
    },
    {
        "name": "nettools_blockchain_summary",
        "description": "Summarise all blockchain nodes found so far: chains, roles, pool count, NFT stores.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def dispatch_nettools_tool(name: str, inputs: Dict,
                           api_key: str = "", service_key: str = "",
                           gh_token: str = "") -> Dict:
    eng = get_nettools_engine(api_key, service_key, gh_token)

    if name == "nettools_classify_network":
        return eng.classifier.classify().summary()

    elif name == "nettools_ping":
        return eng.diag.ping(inputs["host"], inputs.get("count", 4))

    elif name == "nettools_ipconfig":
        return eng.diag.ipconfig()

    elif name == "nettools_tracert":
        return eng.diag.tracert(inputs["host"], inputs.get("max_hops", 15))

    elif name == "nettools_netstat":
        r = eng.diag.netstat()
        r["raw"] = r["raw"][:500]
        return r

    elif name == "nettools_netsh_winsock":
        return {"output": eng.diag.netsh_winsock_show()}

    elif name == "nettools_netsh_wlan":
        return {"output": eng.diag.netsh_wlan_show()}

    elif name == "nettools_netsh_firewall":
        return {"output": eng.diag.netsh_firewall_show()}

    elif name == "nettools_probe_tcp":
        return asdict(eng.probe.probe_tcp(inputs["host"], inputs["port"]))

    elif name == "nettools_probe_udp":
        return asdict(eng.probe.probe_udp(inputs["host"], inputs["port"]))

    elif name == "nettools_probe_http":
        return asdict(eng.probe.probe_http(
            inputs["host"], inputs.get("port", 80), inputs.get("path", "/")))

    elif name == "nettools_probe_https":
        return asdict(eng.probe.probe_https(inputs["host"], inputs.get("port", 443)))

    elif name == "nettools_probe_ftp":
        return asdict(eng.probe.probe_ftp(inputs["host"], inputs.get("port", 21)))

    elif name == "nettools_probe_smtp":
        return asdict(eng.probe.probe_smtp(inputs["host"], inputs.get("port", 25)))

    elif name == "nettools_probe_imap":
        return asdict(eng.probe.probe_imap(inputs["host"], inputs.get("port", 143)))

    elif name == "nettools_probe_websocket":
        return asdict(eng.probe.probe_websocket(
            inputs["host"], inputs.get("port", 80),
            inputs.get("path", "/"), inputs.get("use_tls", False)))

    elif name == "nettools_probe_all":
        return eng.probe.probe_all_as_dict(inputs["host"])

    elif name == "nettools_vps_detect":
        return eng.vps.detect_self()

    elif name == "nettools_vps_probe":
        return asdict(eng.vps.probe_vps(inputs["host"], inputs.get("label", "")))

    elif name == "nettools_ws_server_start":
        eng.mesh.start_ws_server(inputs.get("port", 9016))
        return {"started": True, "port": inputs.get("port", 9016)}

    elif name == "nettools_agent_broadcast":
        return eng.mesh.broadcast_survival(inputs.get("urls", []))

    elif name == "nettools_assistant_ask":
        answer = eng.assistant.ask(inputs["question"])
        return {"answer": answer}

    elif name == "nettools_intelligence_report":
        report = eng.assistant.network_intelligence_report()
        return {"report": report}

    elif name == "nettools_full_snapshot":
        snap = eng.diag.full_snapshot()
        for k in list(snap.keys()):
            if isinstance(snap[k], str) and len(snap[k]) > 800:
                snap[k] = snap[k][:800] + "...[truncated]"
        return snap

    elif name == "nettools_status":
        return eng.status()

    elif name == "nettools_scan_ack":
        ack = get_scan_ack()
        return ack.send_ack(inputs["host"], inputs.get("port", 80),
                             inputs.get("use_https", False))

    elif name == "nettools_ack_scan_results":
        ack = get_scan_ack()
        try:
            results = json.loads(inputs["scan_results_json"])
        except Exception:
            return {"error": "invalid scan_results_json"}
        sent = ack.ack_scan_results(
            results, inputs.get("max_targets", 50))
        return {"acked": len(sent), "entries": sent[:10]}

    elif name == "nettools_cache_query":
        return get_scan_cache().query_cache(inputs.get("limit", 50))

    elif name == "nettools_tower_certs":
        return get_scan_cache().get_tower_certs(inputs.get("limit", 50))

    elif name == "nettools_cache_stats":
        return get_scan_cache().stats()

    elif name == "nettools_ack_sent":
        return get_scan_ack().get_sent(inputs.get("limit", 50))

    elif name == "nettools_blockchain_probe_host":
        nodes = get_blockchain_scanner().probe_host(inputs["host"])
        return [asdict(n) for n in nodes]

    elif name == "nettools_blockchain_scan_subnet":
        nodes = get_blockchain_scanner().scan_subnet(
            inputs.get("subnet_prefix", ""),
            inputs.get("max_hosts", 50))
        return [asdict(n) for n in nodes]

    elif name == "nettools_blockchain_detect_farming":
        nodes = get_blockchain_scanner().get_found()
        return get_blockchain_scanner().detect_pool_farming(nodes)

    elif name == "nettools_xrpl_bio_nft_probe":
        return get_blockchain_scanner().xrpl_bio_nft_probe(
            inputs.get("xrpl_host", "s1.ripple.com"))

    elif name == "nettools_blockchain_summary":
        nodes = get_blockchain_scanner().get_found()
        return get_blockchain_scanner().summary(nodes)

    else:
        return {"error": f"unknown tool: {name}"}


# ==============================================================================
# CLI
# ==============================================================================

if __name__ == "__main__":
    import argparse, pprint

    p = argparse.ArgumentParser(
        description="RabbitOS NetTools — Chase Allen Ringquist networking suite")
    p.add_argument("--classify",  action="store_true",
                   help="Classify current network (PAN/LAN/WLAN/CAN/MAN/WAN/...)")
    p.add_argument("--ping",      metavar="HOST",     help="Ping a host")
    p.add_argument("--tracert",   metavar="HOST",     help="Traceroute to host")
    p.add_argument("--netstat",   action="store_true",help="Show connections + listening ports")
    p.add_argument("--ipconfig",  action="store_true",help="Show all network adapters")
    p.add_argument("--winsock",   action="store_true",help="Show Winsock catalog")
    p.add_argument("--wlan",      action="store_true",help="Show WiFi networks")
    p.add_argument("--firewall",  action="store_true",help="Show firewall state")
    p.add_argument("--probe",     metavar="HOST",     help="Probe all protocols on host")
    p.add_argument("--proto",     metavar="PROTO",
                   help="Specific protocol: tcp|udp|http|https|ftp|smtp|imap|ws")
    p.add_argument("--port",      type=int,           help="Port for --probe/--proto")
    p.add_argument("--vps",       action="store_true",help="Detect VPS / cloud metadata")
    p.add_argument("--vps-probe", metavar="HOST",     help="Probe a VPS node")
    p.add_argument("--ws-server", action="store_true",help="Start WS server on port 9016")
    p.add_argument("--ask",       metavar="QUESTION", help="Ask the browser assistant")
    p.add_argument("--report",    action="store_true",help="Generate full network intelligence report")
    p.add_argument("--snapshot",  action="store_true",help="Full Windows network snapshot")
    p.add_argument("--status",    action="store_true",help="Engine status")
    p.add_argument("--daemon",    action="store_true",help="Run as continuous background daemon")
    args = p.parse_args()

    api  = os.environ.get("ANTHROPIC_API_KEY", "")
    svc  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    gh   = os.environ.get("GITHUB_TOKEN", "")
    eng  = get_nettools_engine(api, svc, gh)

    if args.classify:
        scope = eng.classifier.classify()
        pprint.pprint(scope.summary())

    elif args.ping:
        pprint.pprint(eng.diag.ping(args.ping))

    elif args.tracert:
        r = eng.diag.tracert(args.tracert)
        print(f"Hops to {args.tracert}:")
        for hop in r["hops"]:
            print(f"  {hop['hop']:2d}  {hop.get('ip','*'):16s}  {hop.get('rtt1','?')} ms")
        print(f"Reached: {r['reached']}")

    elif args.netstat:
        r = eng.diag.netstat()
        print(f"State summary: {r['by_state']}")
        print(f"Listening ({len(r['listening'])}):")
        for e in r["listening"][:20]:
            print(f"  {e['proto']:4s}  {e['local']:28s}  PID={e['pid']}")
        print(f"Connections ({len(r['connections'])}):")
        for e in r["connections"][:20]:
            print(f"  {e['proto']:4s}  {e['local']:28s} → {e['remote']:28s}  {e['state']}")

    elif args.ipconfig:
        r = eng.diag.ipconfig()
        for a in r["adapters"]:
            print(f"  [{a.get('name','')}]")
            for k, v in a.items():
                if k != "name":
                    print(f"    {k}: {v}")

    elif args.winsock:
        print(eng.diag.netsh_winsock_show())

    elif args.wlan:
        print(eng.diag.netsh_wlan_show())

    elif args.firewall:
        print(eng.diag.netsh_firewall_show())

    elif args.probe:
        if args.proto:
            proto = args.proto.lower()
            port  = args.port
            fn_map = {
                "tcp":   lambda: eng.probe.probe_tcp(args.probe, port or 80),
                "udp":   lambda: eng.probe.probe_udp(args.probe, port or 53),
                "http":  lambda: eng.probe.probe_http(args.probe, port or 80),
                "https": lambda: eng.probe.probe_https(args.probe, port or 443),
                "ftp":   lambda: eng.probe.probe_ftp(args.probe, port or 21),
                "smtp":  lambda: eng.probe.probe_smtp(args.probe, port or 25),
                "imap":  lambda: eng.probe.probe_imap(args.probe, port or 143),
                "ws":    lambda: eng.probe.probe_websocket(args.probe, port or 80),
            }
            fn = fn_map.get(proto)
            if fn:
                pprint.pprint(asdict(fn()))
            else:
                print(f"Unknown protocol: {proto}")
        else:
            results = eng.probe.probe_all(args.probe)
            for name, r in sorted(results.items()):
                status = "[OPEN]" if r.open else "[----]"
                print(f"  {status}  {name:15s}  "
                      f"{r.protocol:6s}  port={r.port}  "
                      f"{r.latency_ms}ms  "
                      f"banner={r.banner[:50] if r.banner else ''}"
                      f"{' ERR:'+r.error[:40] if r.error else ''}")

    elif getattr(args, "vps_probe", None):
        pprint.pprint(asdict(eng.vps.probe_vps(args.vps_probe)))

    elif args.vps:
        pprint.pprint(eng.vps.detect_self())

    elif args.ws_server:
        eng.mesh.start_ws_server()
        eng.mesh.start_rest_server()
        print(f"[WS Server] Running on :{eng.mesh._ws_port}")
        print(f"[REST Server] Running on :{eng.mesh._rest_port}")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")

    elif args.ask:
        print(f"\n[Browser Assistant] {args.ask}\n{'='*60}")
        answer = eng.assistant.ask(args.ask)
        print(answer)

    elif args.report:
        print(f"\n[Network Intelligence Report — {TWIN_NAME}]\n{'='*60}")
        report = eng.assistant.network_intelligence_report()
        print(report)

    elif args.snapshot:
        snap = eng.diag.full_snapshot()
        for section, content in snap.items():
            print(f"\n== {section.upper()} ==")
            if isinstance(content, dict):
                pprint.pprint(content)
            elif isinstance(content, list):
                for item in content:
                    pprint.pprint(item)
            else:
                print(str(content)[:600])

    elif args.status or not any(vars(args).values()):
        time.sleep(3)
        pprint.pprint(eng.status())

    if args.daemon:
        print(f"\n[NetTools] Daemon running — {TWIN_NAME}")
        print(f"  Network classifying every 5 min")
        print(f"  Snapshot every 10 min")
        print("  Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[NetTools] Stopped.")
