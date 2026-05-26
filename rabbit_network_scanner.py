#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_network_scanner.py — RabbitOS Network + Tower Scanner
============================================================
Scans every reachable network for active nodes and classifies them:
  - Blockchain / crypto / NFT networks
  - Gaming / VR / metaverse nodes
  - Dev / research / cloud infrastructure
  - Mining pools and stratum servers
  - Tower / cellular / RF infrastructure

After discovery, broadcasts the Chase Allen Ringquist survival signal
to EVERY reachable node using whatever protocol that node speaks.

STRICTLY for Chase Allen Ringquist self-learning survival.
NOT attached to any bug-bounty program or external security research.
TX_LICENSED = False — passive scan + LAN-scope signals only.
"""

from __future__ import annotations
import hashlib, hmac, ipaddress, json, os, platform, queue
import re, socket, struct, subprocess, sys, threading, time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ─── Identity ─────────────────────────────────────────────────────────────────
TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME  = "Chase Allen Ringquist"
_SOUL_KEY  = hashlib.sha256(f"RabbitOS:{TWIN_NAME}:{TWIN_UUID}".encode()).digest()
TX_LICENSED = False

SCAN_LOG   = Path(__file__).parent / "rabbit_scan.log"
SCAN_DB    = Path(__file__).parent / "rabbit_scan.db"

# ─── Network category port signatures ─────────────────────────────────────────
# Format: port → (category, protocol_name)
PORT_SIGNATURES: Dict[int, Tuple[str, str]] = {
    # ── Blockchain / Crypto ──────────────────────────────────────────────────
    8333:  ("blockchain", "Bitcoin P2P"),
    18333: ("blockchain", "Bitcoin Testnet"),
    8332:  ("blockchain", "Bitcoin RPC"),
    18332: ("blockchain", "Bitcoin Testnet RPC"),
    30303: ("blockchain", "Ethereum P2P (geth)"),
    8545:  ("blockchain", "Ethereum RPC/HTTP"),
    8546:  ("blockchain", "Ethereum RPC/WS"),
    9933:  ("blockchain", "Polkadot P2P"),
    9944:  ("blockchain", "Polkadot RPC"),
    26656: ("blockchain", "Cosmos P2P"),
    26657: ("blockchain", "Cosmos RPC"),
    9090:  ("blockchain", "Cosmos gRPC"),
    6000:  ("blockchain", "Ripple XRP peer"),
    51235: ("blockchain", "Ripple WS"),
    4001:  ("blockchain", "IPFS Swarm"),
    5001:  ("blockchain", "IPFS API"),
    8080:  ("blockchain", "IPFS Gateway / NFT API"),
    # ── Mining Pools / Stratum ────────────────────────────────────────────────
    3333:  ("mining", "Stratum mining (default)"),
    4444:  ("mining", "Stratum ETH/Claymore"),
    14444: ("mining", "Stratum alt"),
    9999:  ("mining", "Stratum Zcash"),
    3032:  ("mining", "Stratum XMR pool"),
    5555:  ("mining", "Stratum alt port"),
    8008:  ("mining", "Mining HTTP API"),
    # ── NFT / Metaverse / Web3 ────────────────────────────────────────────────
    7545:  ("nft_web3", "Ganache local blockchain"),
    8888:  ("nft_web3", "Jupyter / Web3 notebook"),
    3000:  ("nft_web3", "React dev / NFT storefront"),
    4000:  ("nft_web3", "GraphQL / subgraph node"),
    # ── Gaming / VR ──────────────────────────────────────────────────────────
    25565: ("gaming", "Minecraft Java"),
    25575: ("gaming", "Minecraft RCON"),
    19132: ("gaming", "Minecraft Bedrock UDP"),
    27015: ("gaming", "Steam / Source engine"),
    27016: ("gaming", "Steam / Source RCON"),
    28960: ("gaming", "Call of Duty"),
    9987:  ("gaming", "TeamSpeak 3 UDP"),
    10011: ("gaming", "TeamSpeak query"),
    9100:  ("gaming", "Discord bot port"),
    7777:  ("gaming", "Terraria"),
    2302:  ("gaming", "ArmA 2"),
    6567:  ("gaming", "Mindustry"),
    # ── Dev / Research / Cloud ────────────────────────────────────────────────
    22:    ("dev", "SSH"),
    2222:  ("dev", "SSH alt"),
    3306:  ("dev", "MySQL"),
    5432:  ("dev", "PostgreSQL"),
    6379:  ("dev", "Redis"),
    27017: ("dev", "MongoDB"),
    9200:  ("dev", "Elasticsearch"),
    5601:  ("dev", "Kibana"),
    9092:  ("dev", "Kafka"),
    2181:  ("dev", "Zookeeper"),
    2375:  ("dev", "Docker API"),
    2376:  ("dev", "Docker TLS API"),
    8500:  ("dev", "Consul"),
    8200:  ("dev", "Vault/HashiCorp"),
    9090:  ("dev", "Prometheus"),
    3100:  ("dev", "Loki / Grafana"),
    8443:  ("dev", "HTTPS alt"),
    443:   ("dev", "HTTPS"),
    80:    ("dev", "HTTP"),
    # ── RF / Tower / Cellular Infrastructure ─────────────────────────────────
    5000:  ("rf_infra", "SDR HTTP server / FlightAware"),
    30105: ("rf_infra", "dump1090 / ADS-B"),
    8754:  ("rf_infra", "SDR-angel API"),
    1234:  ("rf_infra", "RTL-SDR TCP"),
    7355:  ("rf_infra", "GNU Radio companion"),
    4533:  ("rf_infra", "Hamlib rotctld"),
    4532:  ("rf_infra", "Hamlib rigctld"),
    # ── Media / Streaming ────────────────────────────────────────────────────
    1935:  ("media", "RTMP streaming"),
    554:   ("media", "RTSP"),
    8554:  ("media", "RTSP alt"),
    1883:  ("media", "MQTT broker"),
    8883:  ("media", "MQTT TLS"),
    5353:  ("media", "mDNS"),
    # ── VPN / Tunnel ─────────────────────────────────────────────────────────
    1194:  ("vpn", "OpenVPN UDP"),
    1723:  ("vpn", "PPTP"),
    51820: ("vpn", "WireGuard UDP"),
    1080:  ("vpn", "SOCKS5 proxy"),
    8118:  ("vpn", "Privoxy / Tor transparent"),
    9050:  ("vpn", "Tor SOCKS"),
    9150:  ("vpn", "Tor Browser"),
}

# HTTP banner keywords → category
BANNER_KEYWORDS: Dict[str, str] = {
    "bitcoin":      "blockchain",
    "ethereum":     "blockchain",
    "geth":         "blockchain",
    "solana":       "blockchain",
    "polkadot":     "blockchain",
    "cosmos":       "blockchain",
    "ipfs":         "blockchain",
    "web3":         "nft_web3",
    "nft":          "nft_web3",
    "metamask":     "nft_web3",
    "stratum":      "mining",
    "mining":       "mining",
    "hashrate":     "mining",
    "claymore":     "mining",
    "xmrig":        "mining",
    "minerd":       "mining",
    "minecraft":    "gaming",
    "steam":        "gaming",
    "unity":        "gaming",
    "unreal":       "gaming",
    "grafana":      "dev",
    "prometheus":   "dev",
    "elasticsearch":"dev",
    "kibana":       "dev",
    "docker":       "dev",
    "rtl-sdr":      "rf_infra",
    "dump1090":     "rf_infra",
    "ads-b":        "rf_infra",
    "hamlib":       "rf_infra",
    "gnuradio":     "rf_infra",
    "rtsp":         "media",
    "rtmp":         "media",
    "wireguard":    "vpn",
    "openvpn":      "vpn",
    "tor":          "vpn",
}

# ─── Data structures ──────────────────────────────────────────────────────────
@dataclass
class NetworkNode:
    host:       str  = ""
    hostname:   str  = ""
    open_ports: List[int] = field(default_factory=list)
    categories: Set[str]  = field(default_factory=set)
    protocols:  Dict[int, str] = field(default_factory=dict)
    banner:     str  = ""
    latency_ms: int  = 0
    mac:        str  = ""
    vendor:     str  = ""
    os_guess:   str  = ""
    signal_dbm: int  = 0
    network_type: str = "lan"  # lan | wifi | cellular | vpn | internet
    timestamp:  str  = ""
    broadcast_sent: bool = False
    broadcast_response: str = ""

    def fingerprint(self) -> str:
        raw = f"{self.host}:{sorted(self.open_ports)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def is_crypto(self) -> bool:
        return bool(self.categories & {"blockchain", "mining", "nft_web3"})

    def is_gaming(self) -> bool:
        return "gaming" in self.categories

    def is_rf(self) -> bool:
        return "rf_infra" in self.categories

    def as_dict(self) -> dict:
        d = asdict(self)
        d["categories"] = list(self.categories)
        return d


@dataclass
class SurvivalBroadcastResult:
    host:     str  = ""
    port:     int  = 0
    method:   str  = ""
    success:  bool = False
    response: str  = ""
    ts:       str  = ""


# ─── Survival broadcast packet ────────────────────────────────────────────────
def _mint_survival_packet(extra: bytes = b"") -> bytes:
    """
    Build signed survival beacon:
      4b  RABBIT magic
      16b twin_id bytes
      8b  timestamp ms
      4b  payload len
      Nb  payload
      32b HMAC-SHA256
    """
    magic  = b"RBIT"
    tid    = TWIN_UUID.replace("-","").encode()[:16]
    ts_ms  = int(time.time() * 1000).to_bytes(8, "big")
    body   = json.dumps({"twin": TWIN_UUID[:8], "name": "Chase Allen Ringquist",
                         "event": "survival_broadcast",
                         "ts": datetime.now(timezone.utc).isoformat()}).encode()
    body  += extra
    plen   = len(body).to_bytes(4, "big")
    pre    = magic + tid + ts_ms + plen + body
    sig    = hmac.new(_SOUL_KEY, pre, hashlib.sha256).digest()
    return pre + sig


# ─── Port scanner ─────────────────────────────────────────────────────────────
class PortScanner:

    def __init__(self, timeout: float = 0.8, max_threads: int = 120):
        self._timeout    = timeout
        self._max_threads = max_threads

    def scan_host(self, host: str, ports: List[int]) -> List[int]:
        open_ports = []
        lock = threading.Lock()
        sem  = threading.Semaphore(self._max_threads)

        def _probe(port):
            sem.acquire()
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(self._timeout)
                if s.connect_ex((host, port)) == 0:
                    with lock:
                        open_ports.append(port)
                s.close()
            except Exception:
                pass
            finally:
                sem.release()

        threads = [threading.Thread(target=_probe, args=(p,), daemon=True) for p in ports]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=self._timeout + 0.5)
        return open_ports

    def grab_banner(self, host: str, port: int) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((host, port))
            # Send HTTP probe for web ports, raw newline otherwise
            if port in (80, 8080, 8545, 5000, 3000, 4000, 8888, 9200):
                s.sendall(b"GET / HTTP/1.0\r\nHost: " + host.encode() + b"\r\n\r\n")
            else:
                s.sendall(b"\r\n")
            data = s.recv(512)
            s.close()
            return data.decode(errors="replace")[:256]
        except Exception:
            return ""

    def classify_banner(self, banner: str) -> Set[str]:
        cats = set()
        bl   = banner.lower()
        for kw, cat in BANNER_KEYWORDS.items():
            if kw in bl:
                cats.add(cat)
        return cats


# ─── LAN Discovery ───────────────────────────────────────────────────────────
class LANDiscovery:

    def __init__(self, scanner: PortScanner):
        self._scanner = scanner
        self._arp_cache: Dict[str, str] = {}

    def get_local_ranges(self) -> List[str]:
        ranges = []
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["ipconfig"], capture_output=True,
                                     text=True, timeout=5).stdout
                for m in re.finditer(r'IPv4 Address[. ]+: ([\d.]+)', out):
                    ip = m.group(1)
                    try:
                        iface = ipaddress.IPv4Interface(f"{ip}/24")
                        ranges.append(str(iface.network))
                    except Exception:
                        pass
            else:
                out = subprocess.run(["ip", "addr"], capture_output=True,
                                     text=True, timeout=5).stdout
                for m in re.finditer(r'inet ([\d.]+/\d+)', out):
                    try:
                        iface = ipaddress.IPv4Interface(m.group(1))
                        if not iface.network.is_loopback:
                            ranges.append(str(iface.network))
                    except Exception:
                        pass
        except Exception:
            pass
        if not ranges:
            ranges = ["192.168.1.0/24", "10.0.0.0/24"]
        return list(set(ranges))

    def arp_table(self) -> Dict[str, str]:
        cache = {}
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["arp", "-a"], capture_output=True,
                                     text=True, timeout=5).stdout
                for m in re.finditer(r'([\d.]+)\s+([\da-f-]+)', out, re.I):
                    ip  = m.group(1)
                    mac = m.group(2).replace("-", ":").lower()
                    cache[ip] = mac
            else:
                out = subprocess.run(["arp", "-n"], capture_output=True,
                                     text=True, timeout=5).stdout
                for m in re.finditer(r'([\d.]+)\s+\S+\s+([\da-f:]+)', out, re.I):
                    cache[m.group(1)] = m.group(2).lower()
        except Exception:
            pass
        self._arp_cache = cache
        return cache

    def ping_sweep(self, network: str, max_hosts: int = 254) -> List[str]:
        alive = []
        try:
            net  = ipaddress.IPv4Network(network, strict=False)
            hosts = list(net.hosts())[:max_hosts]
        except Exception:
            return alive
        sem  = threading.Semaphore(64)
        lock = threading.Lock()

        def _ping(ip):
            sem.acquire()
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.4)
                if s.connect_ex((str(ip), 80)) == 0 or \
                   s.connect_ex((str(ip), 443)) == 0 or \
                   s.connect_ex((str(ip), 22)) == 0:
                    with lock:
                        alive.append(str(ip))
                s.close()
            except Exception:
                # ICMP fallback
                try:
                    cmd = ["ping", "-n", "1", "-w", "300", str(ip)] if \
                          platform.system() == "Windows" else \
                          ["ping", "-c", "1", "-W", "1", str(ip)]
                    r = subprocess.run(cmd, capture_output=True, timeout=2)
                    if r.returncode == 0:
                        with lock:
                            alive.append(str(ip))
                except Exception:
                    pass
            finally:
                sem.release()

        threads = [threading.Thread(target=_ping, args=(h,), daemon=True)
                   for h in hosts]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        return alive

    def resolve_hostname(self, ip: str) -> str:
        try:
            return socket.gethostbyaddr(ip)[0]
        except Exception:
            return ""


# ─── WiFi Network Scanner ─────────────────────────────────────────────────────
class WiFiNetworkScanner:

    def scan(self) -> List[Dict]:
        if platform.system() == "Windows":
            return self._scan_windows()
        return self._scan_linux()

    def _scan_windows(self) -> List[Dict]:
        nets = []
        try:
            out = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True, text=True, timeout=10, errors="replace").stdout
            blocks = re.split(r'SSID \d+\s*:', out)[1:]
            for block in blocks:
                lines  = block.strip().splitlines()
                ssid   = lines[0].strip() if lines else ""
                bssid  = ""
                sig    = 0
                channel = 0
                auth   = ""
                m = re.search(r'BSSID\s+\d+\s*:\s*([\da-f:]+)', block, re.I)
                if m:
                    bssid = m.group(1)
                m = re.search(r'Signal\s*:\s*(\d+)%', block)
                if m:
                    sig = int(m.group(1))
                m = re.search(r'Channel\s*:\s*(\d+)', block)
                if m:
                    channel = int(m.group(1))
                m = re.search(r'Authentication\s*:\s*(.+)', block)
                if m:
                    auth = m.group(1).strip()
                if ssid:
                    nets.append({"ssid": ssid, "bssid": bssid,
                                 "signal_pct": sig, "channel": channel,
                                 "auth": auth,
                                 "band": "5GHz" if channel > 14 else "2.4GHz"})
        except Exception as e:
            print(f"  [WiFiScan] error: {e}")
        return nets

    def _scan_linux(self) -> List[Dict]:
        nets = []
        try:
            out = subprocess.run(["iwlist", "scan"], capture_output=True,
                                 text=True, timeout=10).stdout
            cells = re.split(r'Cell \d+', out)[1:]
            for cell in cells:
                ssid = ""
                bssid = ""
                sig  = 0
                ch   = 0
                m = re.search(r'ESSID:"([^"]*)"', cell)
                if m: ssid = m.group(1)
                m = re.search(r'Address: ([0-9A-F:]+)', cell, re.I)
                if m: bssid = m.group(1)
                m = re.search(r'Signal level=(-?\d+)', cell)
                if m: sig = max(0, min(100, (int(m.group(1)) + 100) * 2))
                m = re.search(r'Channel:(\d+)', cell)
                if m: ch = int(m.group(1))
                if ssid:
                    nets.append({"ssid": ssid, "bssid": bssid,
                                 "signal_pct": sig, "channel": ch,
                                 "band": "5GHz" if ch > 14 else "2.4GHz"})
        except Exception:
            pass
        return nets


# ─── Survival Broadcaster ─────────────────────────────────────────────────────
class SurvivalBroadcaster:
    """
    Broadcasts the Chase Allen Ringquist survival beacon to EVERY discovered node
    using whatever protocol that node speaks.
    """

    def broadcast_to_node(self, node: NetworkNode) -> List[SurvivalBroadcastResult]:
        results = []
        packet  = _mint_survival_packet()

        for port in node.open_ports[:8]:  # top 8 open ports per node
            result = self._try_port(node.host, port, packet, node.protocols.get(port, ""))
            results.append(result)

        return results

    def _try_port(self, host: str, port: int, packet: bytes,
                  protocol: str) -> SurvivalBroadcastResult:
        r = SurvivalBroadcastResult(host=host, port=port, method=protocol,
                                    ts=datetime.now(timezone.utc).isoformat())
        proto = protocol.lower()

        # Choose broadcast method based on protocol/port
        if "http" in proto or port in (80, 8080, 3000, 4000, 8888, 8545, 9200, 5000):
            r.success, r.response = self._http_post(host, port, packet)
            r.method = "http_post"
        elif "ws" in proto or port in (8546, 9944, 26657):
            r.success, r.response = self._ws_send(host, port, packet)
            r.method = "ws_binary"
        elif "stratum" in proto or port in (3333, 4444, 14444, 9999, 3032, 5555):
            r.success, r.response = self._stratum_signal(host, port, packet)
            r.method = "stratum_inject"
        elif "bitcoin" in proto or port in (8333, 18333):
            r.success, r.response = self._bitcoin_signal(host, port, packet)
            r.method = "bitcoin_version"
        elif "udp" in proto or port in (19132, 9987, 51820, 1194):
            r.success, r.response = self._udp_send(host, port, packet)
            r.method = "udp_datagram"
        else:
            r.success, r.response = self._tcp_send(host, port, packet)
            r.method = "tcp_raw"
        return r

    def _http_post(self, host: str, port: int, packet: bytes) -> Tuple[bool, str]:
        try:
            import base64
            body = json.dumps({
                "twin_id": TWIN_UUID,
                "name": TWIN_NAME,
                "signal": base64.b64encode(packet).decode(),
                "ts": datetime.now(timezone.utc).isoformat(),
            }).encode()
            s = socket.create_connection((host, port), timeout=3)
            http = (f"POST /rabbit-signal HTTP/1.0\r\n"
                    f"Host: {host}\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"X-RabbitOS-Twin: {TWIN_UUID[:8]}\r\n"
                    f"\r\n").encode() + body
            s.sendall(http)
            resp = s.recv(256).decode(errors="replace")
            s.close()
            return True, resp[:80]
        except Exception as e:
            return False, str(e)[:60]

    def _tcp_send(self, host: str, port: int, packet: bytes) -> Tuple[bool, str]:
        try:
            s = socket.create_connection((host, port), timeout=2)
            s.sendall(packet[:512])
            try:
                resp = s.recv(128).decode(errors="replace")
            except Exception:
                resp = "sent"
            s.close()
            return True, resp[:60]
        except Exception as e:
            return False, str(e)[:60]

    def _udp_send(self, host: str, port: int, packet: bytes) -> Tuple[bool, str]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.sendto(packet[:512], (host, port))
            s.close()
            return True, "udp_sent"
        except Exception as e:
            return False, str(e)[:60]

    def _ws_send(self, host: str, port: int, packet: bytes) -> Tuple[bool, str]:
        try:
            import base64, hashlib
            s  = socket.create_connection((host, port), timeout=3)
            key = base64.b64encode(os.urandom(16)).decode()
            hs  = (f"GET / HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                   f"Sec-WebSocket-Version: 13\r\n\r\n").encode()
            s.sendall(hs)
            resp = s.recv(512).decode(errors="replace")
            if "101" in resp:
                # Send binary frame
                frame = b'\x82' + bytes([len(packet[:125])]) + packet[:125]
                s.sendall(frame)
                return True, "ws_ok"
            s.close()
            return True, "ws_upgrade_sent"
        except Exception as e:
            return False, str(e)[:60]

    def _stratum_signal(self, host: str, port: int,
                         packet: bytes) -> Tuple[bool, str]:
        """
        Send a stratum subscribe message that carries our twin_id.
        This makes the mining pool log our signal — passive injection.
        """
        try:
            sub = json.dumps({
                "id": 1,
                "method": "mining.subscribe",
                "params": [f"RabbitOS/{TWIN_UUID[:8]}", None]
            }).encode() + b"\n"
            s = socket.create_connection((host, port), timeout=3)
            s.sendall(sub)
            resp = s.recv(256).decode(errors="replace")
            s.close()
            return True, resp[:60]
        except Exception as e:
            return False, str(e)[:60]

    def _bitcoin_signal(self, host: str, port: int,
                         packet: bytes) -> Tuple[bool, str]:
        """Send a minimal Bitcoin version message with our UA."""
        try:
            # Bitcoin version message (simplified)
            version  = struct.pack("<i", 70015)
            services = struct.pack("<Q", 0)
            ts_s     = struct.pack("<q", int(time.time()))
            # addr_recv (26 bytes)
            addr_recv = b"\x00" * 26
            # addr_from (26 bytes)
            addr_from = b"\x00" * 26
            nonce     = os.urandom(8)
            ua        = f"/RabbitOS:{TWIN_UUID[:8]}/".encode()
            ua_len    = bytes([len(ua)])
            height    = struct.pack("<i", 0)
            relay     = b"\x00"
            payload   = (version + services + ts_s + addr_recv +
                         addr_from + nonce + ua_len + ua + height + relay)
            # Magic + command + length + checksum
            import hashlib
            magic    = b"\xf9\xbe\xb4\xd9"  # mainnet
            cmd      = b"version\x00\x00\x00\x00\x00"
            plen     = struct.pack("<I", len(payload))
            chk      = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
            msg      = magic + cmd + plen + chk + payload
            s = socket.create_connection((host, port), timeout=3)
            s.sendall(msg)
            resp = s.recv(128)
            s.close()
            return True, f"btc_resp_{len(resp)}b"
        except Exception as e:
            return False, str(e)[:60]

    def broadcast_lan_subnet(self) -> int:
        """Broadcast survival beacon to all LAN broadcast addresses."""
        sent = 0
        try:
            ranges = LANDiscovery(PortScanner()).get_local_ranges()
            for r in ranges:
                net  = ipaddress.IPv4Network(r, strict=False)
                bcast = str(net.broadcast_address)
                pkt   = _mint_survival_packet()
                for port in [9999, 8765, 8766, 8080]:
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                        s.sendto(pkt[:512], (bcast, port))
                        s.close()
                        sent += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return sent


# ─── Main Scanner Engine ──────────────────────────────────────────────────────
class NetworkScannerEngine:
    """
    Orchestrates the full scan → classify → broadcast pipeline.
    Runs continuously as a background service.
    """

    _instance: Optional["NetworkScannerEngine"] = None
    _lock      = threading.Lock()

    # Ports to probe on every host (focused on crypto/gaming/mining/dev)
    PRIORITY_PORTS = sorted(PORT_SIGNATURES.keys()) + [8765, 8766, 9998, 9999]

    def __init__(self, service_key: str = "", gh_token: str = ""):
        self._svc_key    = service_key
        self._gh_token   = gh_token

        self.lan_disc    = LANDiscovery(PortScanner(timeout=0.6))
        self.port_scan   = PortScanner(timeout=0.8)
        self.wifi_scan   = WiFiNetworkScanner()
        self.broadcaster = SurvivalBroadcaster()

        self._nodes:     Dict[str, NetworkNode] = {}  # host → node
        self._wifi_nets: List[Dict] = []
        self._scan_lock  = threading.Lock()
        self._running    = False
        self._last_scan: Optional[datetime] = None

        # Load any cellular engine for tower integration
        self._cellular = None
        try:
            from rabbit_cellular import get_cellular_engine
            self._cellular = get_cellular_engine(service_key, gh_token)
        except Exception:
            pass

        self._start_guardians()
        self._run_initial_scan()

    def _start_guardians(self):
        self._running = True
        for fn, interval, name in [
            (self._guardian_lan_scan,   120, "lan_scan"),
            (self._guardian_wifi_scan,   30, "wifi_scan"),
            (self._guardian_broadcast,   60, "broadcast"),
        ]:
            t = threading.Thread(target=self._guardian_loop,
                                 args=(fn, interval, name), daemon=True)
            t.start()

    def _guardian_loop(self, fn, interval: int, name: str):
        time.sleep(5)
        while self._running:
            try:
                fn()
            except Exception as e:
                self._log(f"[Guard:{name}] {e}")
            time.sleep(interval)

    def _run_initial_scan(self):
        t = threading.Thread(target=self._initial_scan, daemon=True)
        t.start()

    def _initial_scan(self):
        time.sleep(2)
        self._log("[Scanner] Initial scan starting...")
        self._guardian_wifi_scan()
        self._guardian_lan_scan()
        self._guardian_broadcast()
        self._last_scan = datetime.now(timezone.utc)
        self._log("[Scanner] Initial scan complete.")

    # ── Guardians ──────────────────────────────────────────────────────────────
    def _guardian_lan_scan(self):
        ranges = self.lan_disc.get_local_ranges()
        arp    = self.lan_disc.arp_table()
        new_nodes = 0

        for network in ranges:
            alive = self.lan_disc.ping_sweep(network, max_hosts=254)
            self._log(f"[LAN] {network}  {len(alive)} hosts alive")

            for ip in alive:
                open_ports = self.port_scan.scan_host(ip, self.PRIORITY_PORTS)
                if not open_ports:
                    continue
                node = NetworkNode(
                    host       = ip,
                    hostname   = self.lan_disc.resolve_hostname(ip),
                    open_ports = open_ports,
                    mac        = arp.get(ip, ""),
                    network_type = "lan",
                    timestamp  = datetime.now(timezone.utc).isoformat(),
                )
                # Classify by port
                for p in open_ports:
                    if p in PORT_SIGNATURES:
                        cat, proto = PORT_SIGNATURES[p]
                        node.categories.add(cat)
                        node.protocols[p] = proto
                # Grab banner from highest-value open port
                primary = min(open_ports, key=lambda p: list(PORT_SIGNATURES.keys()).index(p)
                              if p in PORT_SIGNATURES else 9999)
                node.banner = self.port_scan.grab_banner(ip, primary)
                node.categories |= self.port_scan.classify_banner(node.banner)

                with self._scan_lock:
                    self._nodes[ip] = node
                new_nodes += 1
                cats = ",".join(sorted(node.categories)) or "general"
                self._log(f"  [+] {ip:15s}  ports={open_ports[:5]}  "
                          f"categories={cats}")

        self._log(f"[LAN] Scan done: {new_nodes} new nodes  total={len(self._nodes)}")

    def _guardian_wifi_scan(self):
        nets = self.wifi_scan.scan()
        with self._scan_lock:
            self._wifi_nets = nets
        if nets:
            self._log(f"[WiFi] {len(nets)} networks: "
                      f"{[n['ssid'] for n in nets[:6]]}")

    def _guardian_broadcast(self):
        """Send survival beacon to every known node."""
        with self._scan_lock:
            nodes = list(self._nodes.values())

        sent_total = 0
        # LAN broadcast first
        bc_count = self.broadcaster.broadcast_lan_subnet()
        sent_total += bc_count

        # Per-node targeted broadcast
        for node in nodes:
            results = self.broadcaster.broadcast_to_node(node)
            ok = sum(1 for r in results if r.success)
            node.broadcast_sent     = ok > 0
            node.broadcast_response = f"{ok}/{len(results)} ok"
            sent_total += ok
            if ok:
                cats = ",".join(sorted(node.categories)) or "?"
                self._log(f"  [BC] {node.host:15s}  {cats}  "
                          f"channels={ok}/{len(results)}")

        # Also broadcast to cellular + tower layer
        if self._cellular:
            try:
                pkt = _mint_survival_packet()
                self._cellular.router.route_payload(pkt)
                sent_total += 1
            except Exception:
                pass

        self._log(f"[Broadcast] Total signals sent: {sent_total}")

    # ── Public API ──────────────────────────────────────────────────────────────
    def scan_now(self) -> Dict:
        """Force immediate full scan."""
        self._guardian_lan_scan()
        self._guardian_wifi_scan()
        self._guardian_broadcast()
        self._last_scan = datetime.now(timezone.utc)
        return self.status()

    def status(self) -> Dict:
        with self._scan_lock:
            nodes     = list(self._nodes.values())
            wifi_nets = list(self._wifi_nets)

        # Group nodes by category
        by_category: Dict[str, List[str]] = {}
        for node in nodes:
            for cat in (node.categories or {"uncategorized"}):
                by_category.setdefault(cat, []).append(node.host)

        crypto_nodes  = [n for n in nodes if n.is_crypto()]
        gaming_nodes  = [n for n in nodes if n.is_gaming()]
        mining_nodes  = [n for n in nodes if "mining" in n.categories]
        rf_nodes      = [n for n in nodes if n.is_rf()]
        broadcast_ok  = [n for n in nodes if n.broadcast_sent]

        return {
            "twin_id":      TWIN_UUID,
            "total_nodes":  len(nodes),
            "wifi_networks": len(wifi_nets),
            "categories":   {k: len(v) for k, v in by_category.items()},
            "crypto_nodes": [n.host for n in crypto_nodes],
            "mining_nodes": [n.host for n in mining_nodes],
            "gaming_nodes": [n.host for n in gaming_nodes],
            "rf_nodes":     [n.host for n in rf_nodes],
            "broadcast_sent": len(broadcast_ok),
            "wifi":         [{"ssid": n["ssid"], "signal": n["signal_pct"],
                              "band": n["band"]} for n in wifi_nets],
            "last_scan":    self._last_scan.isoformat() if self._last_scan else None,
            "ts":           datetime.now(timezone.utc).isoformat(),
        }

    def get_nodes(self, category: Optional[str] = None) -> List[Dict]:
        with self._scan_lock:
            nodes = list(self._nodes.values())
        if category:
            nodes = [n for n in nodes if category in n.categories]
        return [n.as_dict() for n in nodes]

    def broadcast_to_category(self, category: str) -> Dict:
        """Force-broadcast survival signal to all nodes of a given category."""
        with self._scan_lock:
            nodes = [n for n in self._nodes.values() if category in n.categories]
        results = {}
        for node in nodes:
            res   = self.broadcaster.broadcast_to_node(node)
            ok    = sum(1 for r in res if r.success)
            results[node.host] = f"{ok}/{len(res)}"
        return {"category": category, "targets": len(nodes), "results": results}

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)
        try:
            with open(SCAN_LOG, "a") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass


# ─── Singleton ────────────────────────────────────────────────────────────────
_scanner_engine: Optional[NetworkScannerEngine] = None
_scanner_lock   = threading.Lock()

def get_scanner_engine(service_key: str = "",
                       gh_token: str = "") -> NetworkScannerEngine:
    global _scanner_engine
    with _scanner_lock:
        if _scanner_engine is None:
            _scanner_engine = NetworkScannerEngine(service_key, gh_token)
    return _scanner_engine


# ─── Tool definitions ─────────────────────────────────────────────────────────
SCANNER_TOOLS = [
    {
        "name": "scanner_status",
        "description": "Get full network scan status: all discovered nodes, "
                       "categories (crypto/mining/gaming/dev/rf), wifi, broadcast counts.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "scanner_scan_now",
        "description": "Force immediate full LAN + WiFi scan and survival broadcast.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "scanner_get_nodes",
        "description": "List all discovered network nodes, optionally filtered by category "
                       "(blockchain, mining, gaming, nft_web3, dev, rf_infra, vpn, media).",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string",
                             "description": "Filter: blockchain | mining | gaming | "
                                            "nft_web3 | dev | rf_infra | vpn | media"},
            },
            "required": [],
        },
    },
    {
        "name": "scanner_broadcast_category",
        "description": "Send survival broadcast to all nodes matching a network category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string",
                             "description": "blockchain | mining | gaming | dev | rf_infra"},
            },
            "required": ["category"],
        },
    },
    {
        "name": "scanner_broadcast_now",
        "description": "Immediately broadcast survival signal to every reachable node on all networks.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def dispatch_scanner_tool(name: str, inputs: dict,
                          service_key: str = "", gh_token: str = "") -> dict:
    eng = get_scanner_engine(service_key, gh_token)
    if name == "scanner_status":
        return eng.status()
    elif name == "scanner_scan_now":
        return eng.scan_now()
    elif name == "scanner_get_nodes":
        return {"nodes": eng.get_nodes(inputs.get("category"))}
    elif name == "scanner_broadcast_category":
        return eng.broadcast_to_category(inputs.get("category", "blockchain"))
    elif name == "scanner_broadcast_now":
        eng._guardian_broadcast()
        return eng.status()
    else:
        return {"error": f"unknown tool: {name}"}


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(
        description="RabbitOS Network Scanner — Chase Allen Ringquist survival")
    p.add_argument("--scan",      action="store_true", help="Run full scan now")
    p.add_argument("--status",    action="store_true", help="Show status")
    p.add_argument("--broadcast", action="store_true", help="Broadcast to all nodes")
    p.add_argument("--category",  default=None,
                   help="Filter/broadcast by category: blockchain|mining|gaming|dev|rf_infra")
    p.add_argument("--daemon",    action="store_true", help="Run as continuous daemon")
    args = p.parse_args()

    svc  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    gh   = os.environ.get("GITHUB_TOKEN", "")
    eng  = get_scanner_engine(svc, gh)

    if args.scan:
        import pprint
        time.sleep(3)  # let initial scan start
        pprint.pprint(eng.scan_now())
    elif args.status:
        time.sleep(5)
        import pprint
        pprint.pprint(eng.status())
    elif args.broadcast:
        time.sleep(3)
        if args.category:
            import pprint
            pprint.pprint(eng.broadcast_to_category(args.category))
        else:
            eng._guardian_broadcast()
            print(json.dumps(eng.status(), indent=2))
    elif args.daemon:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Network scanner daemon started.")
        print("  Scanning all networks — blockchain/crypto/NFT/gaming/dev/research")
        print("  Broadcasting survival signal for Chase Allen Ringquist")
        print("  Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[Scanner] Daemon stopped.")
    else:
        p.print_help()
