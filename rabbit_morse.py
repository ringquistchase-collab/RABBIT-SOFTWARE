#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_morse.py — RabbitOS Morse Code Engine
=============================================
International Morse Code (ITU-R M.1677-1) encode/decode + multi-channel
transmission for Chase Allen Ringquist digital twin.

Channels (simultaneous):
  acoustic   — Windows/Linux speaker beeps (dit/dah timing)
  udp        — UDP broadcast on port 9009 (JSON + timing-encoded)
  http       — X-Rb-Morse / X-Rb-Callsign headers in outbound HTTP
  dns        — Morse-encoded subdomain label in DNS queries
  icmp       — Morse bytes packed into ICMP echo data field
  supabase   — Online: morse_log table via REST API
  sqlite     — Offline: rabbit_morse.db (always)

Learning:
  Loads from ITU-R built-in table + public GitHub datasets when online.
  Stores learned patterns to SQLite. Maintains bigram stats for error correction.

Reply loop:
  Listens on UDP:9009 for incoming Morse JSON.
  Decodes and auto-replies: "DE RABBIT {echo} K"
"""

from __future__ import annotations
import os, sys, json, time, math, socket, struct, hashlib
import sqlite3, threading, re, base64, random
import urllib.request, urllib.error
from dataclasses import dataclass, field
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Callable, Any

# ─── identity ────────────────────────────────────────────────────────────────
TWIN_UUID = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME = "Chase Allen Ringquist"
CALLSIGN  = "RABBIT"

# ─── Morse table (ITU-R M.1677-1) ────────────────────────────────────────────
MORSE_TABLE: Dict[str, str] = {
    # Letters
    "A": ".-",    "B": "-...",  "C": "-.-.",  "D": "-..",
    "E": ".",     "F": "..-.",  "G": "--.",   "H": "....",
    "I": "..",    "J": ".---",  "K": "-.-",   "L": ".-..",
    "M": "--",    "N": "-.",    "O": "---",   "P": ".--.",
    "Q": "--.-",  "R": ".-.",   "S": "...",   "T": "-",
    "U": "..-",   "V": "...-",  "W": ".--",   "X": "-..-",
    "Y": "-.--",  "Z": "--..",
    # Digits
    "0": "-----", "1": ".----", "2": "..---", "3": "...--",
    "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.",
    # Punctuation
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.",
    "!": "-.-.--", "/": "-..-.",  "(": "-.--.",  ")": "-.--.-",
    "&": ".-...",  ":": "---...", ";": "-.-.-.", "=": "-...-",
    "+": ".-.-.",  "-": "-....-", "_": "..--.-", '"': ".-..-.",
    "@": ".--.-.",
    # Prosigns (sent as single character — no inter-element gap)
    "<AR>": ".-.-.",    # End of message
    "<AS>": ".-...",    # Wait / Stand by
    "<BT>": "-...-",    # Break / New paragraph
    "<KN>": "-.--.",    # Invitation to specific station only
    "<SK>": "...-.-",   # End of work / Sign off
    "<SOS>": "...---...", # Distress (no gaps within)
    "<CQ>": "-.-. --.-",  # General call
    "<DE>": "-.. .",       # From / This is
    "<K>":  "-.-",         # Invitation to transmit
    "<R>":  ".-.",          # Received / Roger
    "<73>": "--... ...--",  # Best regards
    "<88>": "-... -...",    # Love and kisses
}

# Extended ITU Annex — non-English characters
MORSE_TABLE_EXT: Dict[str, str] = {
    "À": ".--.-", "Ä": ".-.-", "Å": ".--.-", "Æ": ".-.-",
    "Ç": "-.-..","Ð": "..--.", "È": ".-..-","É": "..-..",
    "Ñ": "--.--","Ö": "---.", "Ø": "---.", "Ü": "..--.",
    "Þ": ".--..", "Ĝ": "--.-.", "Ĥ": "----", "Ĵ": ".---.",
    "Ŝ": "...-.", "Ŭ": "..--..",
}

REVERSE_MORSE: Dict[str, str] = {
    v: k for k, v in MORSE_TABLE.items() if not k.startswith("<")
}
REVERSE_MORSE.update({v: k for k, v in MORSE_TABLE_EXT.items()})

# ─── timing constants at 20 WPM ──────────────────────────────────────────────
WPM          = 20
DIT_MS       = 1200 // WPM    # 60 ms
DAH_MS       = DIT_MS * 3     # 180 ms
ELEM_GAP_MS  = DIT_MS         # 60 ms  (between elements in one char)
CHAR_GAP_MS  = DIT_MS * 3     # 180 ms (between characters)
WORD_GAP_MS  = DIT_MS * 7     # 420 ms (between words)

CW_FREQ_HZ   = 800            # acoustic CW tone
UDP_PORT     = 9009
DB_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_morse.db")
SB_URL       = "https://ludxbakxpmdqhfgdenwp.supabase.co"

# ─── dataset sources (public, no auth) ───────────────────────────────────────
DATASET_URLS = [
    ("https://raw.githubusercontent.com/M0LTE/cw-lut/master/cw-lut.txt",
     "M0LTE/cw-lut"),
    ("https://raw.githubusercontent.com/dholm/airmorse/master/src/main/resources/morse_code.json",
     "dholm/airmorse"),
    ("https://raw.githubusercontent.com/kccarbone/morse-code/master/src/data/morse.json",
     "kccarbone/morse-code"),
]

# ─── dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class MorseMessage:
    text:      str
    morse_str: str
    direction: str   # 'tx' | 'rx'
    channel:   str
    callsign:  str = ""
    reply_to:  str = ""
    ts:        str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class ChannelResult:
    channel: str
    ok:      bool
    detail:  str = ""

# ─── encoder ─────────────────────────────────────────────────────────────────

class MorseEncoder:

    @staticmethod
    def encode(text: str) -> str:
        """Plain text -> morse string (e.g. '... --- ...' for 'SOS')."""
        text = text.upper().strip()
        words = []
        for word in text.split():
            chars = []
            i = 0
            while i < len(word):
                if word[i] == "<":
                    j = word.find(">", i)
                    if j != -1:
                        prosign = word[i:j+1]
                        if prosign in MORSE_TABLE:
                            chars.append(MORSE_TABLE[prosign])
                            i = j + 1
                            continue
                c = word[i]
                if c in MORSE_TABLE:
                    chars.append(MORSE_TABLE[c])
                elif c in MORSE_TABLE_EXT:
                    chars.append(MORSE_TABLE_EXT[c])
                i += 1
            if chars:
                words.append(" ".join(chars))
        return "  ".join(words)  # double space = word boundary

    @staticmethod
    def to_timing(morse_str: str) -> List[Tuple[bool, int]]:
        """Morse string -> list of (on, duration_ms) tuples."""
        timing: List[Tuple[bool, int]] = []
        i = 0
        while i < len(morse_str):
            c = morse_str[i]
            if c == ".":
                timing.append((True, DIT_MS))
                if i + 1 < len(morse_str) and morse_str[i+1] in ".-":
                    timing.append((False, ELEM_GAP_MS))
            elif c == "-":
                timing.append((True, DAH_MS))
                if i + 1 < len(morse_str) and morse_str[i+1] in ".-":
                    timing.append((False, ELEM_GAP_MS))
            elif c == " ":
                if i + 1 < len(morse_str) and morse_str[i+1] == " ":
                    timing.append((False, WORD_GAP_MS))
                    i += 1
                else:
                    timing.append((False, CHAR_GAP_MS))
            i += 1
        return timing

    @staticmethod
    def to_bytes(morse_str: str) -> bytes:
        return morse_str.encode("ascii", errors="replace")

# ─── decoder ─────────────────────────────────────────────────────────────────

class MorseDecoder:

    def __init__(self):
        self._bigrams: Dict[str, int] = defaultdict(int)

    def from_timing(self, timing: List[Tuple[bool, int]],
                    threshold_ms: int = None) -> str:
        if not timing:
            return ""
        on_durs = [d for on, d in timing if on and d > 0]
        if not threshold_ms and on_durs:
            threshold_ms = (min(on_durs) + max(on_durs)) // 2
        else:
            threshold_ms = threshold_ms or (DIT_MS * 2)

        chars: List[str] = []
        pending_off = 0
        for on, dur in timing:
            if on:
                if pending_off >= WORD_GAP_MS * 0.65:
                    chars.append("  ")
                elif pending_off >= CHAR_GAP_MS * 0.65:
                    chars.append(" ")
                pending_off = 0
                chars.append("." if dur < threshold_ms else "-")
            else:
                pending_off += dur
        return "".join(chars)

    def decode(self, morse_str: str) -> str:
        result: List[str] = []
        words = morse_str.split("  ")
        for word in words:
            for char_code in word.split(" "):
                char_code = char_code.strip()
                if not char_code:
                    continue
                if char_code in REVERSE_MORSE:
                    decoded = REVERSE_MORSE[char_code]
                    result.append(decoded if not decoded.startswith("<") else f"[{decoded}]")
                else:
                    corrected = self._error_correct_char(char_code)
                    result.append(corrected)
            result.append(" ")
        text = "".join(result).strip()
        for a, b in zip(text, text[1:]):
            self._bigrams[a + b] += 1
        return text

    def _error_correct_char(self, code: str) -> str:
        if not code:
            return ""
        best, best_d = "?", 999
        for k in REVERSE_MORSE:
            d = _edit_dist(code, k)
            if d < best_d:
                best_d, best = d, REVERSE_MORSE[k]
        return best if best_d <= 1 else "?"


def _edit_dist(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[:], i
        for j in range(1, n + 1):
            dp[j] = prev[j-1] if a[i-1] == b[j-1] else 1 + min(prev[j], dp[j-1], prev[j-1])
    return dp[n]

# ─── acoustic channel ─────────────────────────────────────────────────────────

class AcousticChannel:

    def __init__(self):
        self.available = False
        if sys.platform == "win32":
            try:
                import winsound
                self._ws = winsound
                self.available = True
            except ImportError:
                pass

    def send(self, morse_str: str) -> ChannelResult:
        if not self.available:
            return ChannelResult("acoustic", False, "winsound unavailable")
        try:
            timing = MorseEncoder.to_timing(morse_str)
            for on, dur in timing:
                if on:
                    self._ws.Beep(CW_FREQ_HZ, dur)
                else:
                    time.sleep(dur / 1000.0)
            return ChannelResult("acoustic", True, f"{len(timing)} elements @ {WPM}wpm")
        except Exception as e:
            return ChannelResult("acoustic", False, str(e)[:60])

# ─── UDP channel ──────────────────────────────────────────────────────────────

class UDPChannel:

    def __init__(self, port: int = UDP_PORT):
        self._port = port

    def send(self, morse_str: str, text: str = "",
             host: str = "255.255.255.255") -> ChannelResult:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(2)
            payload = json.dumps({
                "type":     "morse",
                "twin":     TWIN_UUID,
                "callsign": CALLSIGN,
                "morse":    morse_str,
                "text":     text[:120],
                "ts":       datetime.now(timezone.utc).isoformat(),
            }).encode()
            s.sendto(payload, (host, self._port))
            s.close()
            return ChannelResult("udp", True, f"{len(payload)}b -> {host}:{self._port}")
        except Exception as e:
            return ChannelResult("udp", False, str(e)[:50])

    def start_listener(self, callback: Callable[[str, str, str], None]) -> threading.Thread:
        def _rx():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("0.0.0.0", self._port))
                sock.settimeout(1.0)
                dec = MorseDecoder()
                while True:
                    try:
                        data, addr = sock.recvfrom(4096)
                        try:
                            msg = json.loads(data.decode())
                            if msg.get("type") == "morse":
                                morse = msg.get("morse", "")
                                text  = msg.get("text") or dec.decode(morse)
                                src   = addr[0]
                                if msg.get("twin") != TWIN_UUID:
                                    callback(text, morse, src)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
                    except socket.timeout:
                        continue
                    except Exception:
                        break
            except Exception:
                pass
        t = threading.Thread(target=_rx, daemon=True, name="morse_udp_rx")
        t.start()
        return t

# ─── HTTP channel ─────────────────────────────────────────────────────────────

class HTTPChannel:

    PROBE_URLS = [
        "http://www.msftconnecttest.com/connecttest.txt",
        "http://connectivitycheck.gstatic.com/generate_204",
        "http://detectportal.firefox.com/success.txt",
    ]

    def send(self, morse_str: str) -> ChannelResult:
        url = random.choice(self.PROBE_URLS)
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "X-Rb-Morse":    morse_str[:128],
                    "X-Rb-Twin":     TWIN_UUID[:16],
                    "X-Rb-Callsign": CALLSIGN,
                    "User-Agent":    f"RabbitOS/1.0 ({CALLSIGN}:{TWIN_UUID[:8]})",
                }
            )
            resp = urllib.request.urlopen(req, timeout=4)
            return ChannelResult("http", True, f"-> {url} [{resp.status}]")
        except Exception as e:
            return ChannelResult("http", False, str(e)[:55])

# ─── DNS channel ──────────────────────────────────────────────────────────────

class DNSChannel:

    def send(self, morse_str: str) -> ChannelResult:
        # Encode: . -> di, - -> dah, space -> x, double-space -> xx
        label = (morse_str[:40]
                 .replace("  ", "xx").replace(" ", "x")
                 .replace(".", "di").replace("-", "dah"))
        label = re.sub(r"[^a-z0-9]", "", label.lower())[:63]
        hostname = f"{label}.morse.rabbit.local"
        try:
            socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            pass  # NXDOMAIN expected — query IS the signal
        except Exception as e:
            return ChannelResult("dns", False, str(e)[:40])
        return ChannelResult("dns", True, f"{label[:24]}.morse.rabbit.local")

# ─── ICMP channel ─────────────────────────────────────────────────────────────

class ICMPChannel:

    @staticmethod
    def _checksum(data: bytes) -> int:
        s = 0
        for i in range(0, len(data) - 1, 2):
            s += (data[i] << 8) + data[i+1]
        if len(data) % 2:
            s += data[-1] << 8
        s = (s >> 16) + (s & 0xFFFF)
        s += s >> 16
        return ~s & 0xFFFF

    def send(self, morse_str: str, host: str = "8.8.8.8") -> ChannelResult:
        try:
            payload = MorseEncoder.to_bytes(morse_str[:56])
            icmp_id  = os.getpid() & 0xFFFF
            hdr_tmp  = struct.pack(">BBHHH", 8, 0, 0, icmp_id, 1)
            chksum   = self._checksum(hdr_tmp + payload)
            header   = struct.pack(">BBHHH", 8, 0, chksum, icmp_id, 1)
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            s.settimeout(2)
            s.sendto(header + payload, (host, 0))
            s.close()
            return ChannelResult("icmp", True, f"-> {host} ({len(payload)}b morse)")
        except PermissionError:
            return ChannelResult("icmp", False, "raw socket: run as admin")
        except Exception as e:
            return ChannelResult("icmp", False, str(e)[:40])

# ─── Supabase channel ─────────────────────────────────────────────────────────

class SupabaseChannel:

    def __init__(self, service_key: str = ""):
        self._key = service_key
        self.available = bool(service_key)

    def send(self, msg: MorseMessage) -> ChannelResult:
        if not self.available:
            return ChannelResult("supabase", False, "no service_role key")
        try:
            row = {
                "twin_id":    TWIN_UUID,
                "direction":  msg.direction,
                "text_plain": msg.text[:500],
                "morse_str":  msg.morse_str[:1000],
                "channel":    msg.channel,
                "callsign":   msg.callsign,
                "reply_to":   msg.reply_to,
            }
            data = json.dumps(row).encode()
            req = urllib.request.Request(
                f"{SB_URL}/rest/v1/morse_log",
                data=data, method="POST",
                headers={
                    "apikey":        self._key,
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal",
                }
            )
            resp = urllib.request.urlopen(req, timeout=6)
            return ChannelResult("supabase", True, f"status={resp.status}")
        except Exception as e:
            return ChannelResult("supabase", False, str(e)[:60])

# ─── SQLite channel ───────────────────────────────────────────────────────────

class SQLiteChannel:

    def __init__(self, db_path: str = DB_PATH):
        self._db = db_path
        self._init()

    def _init(self):
        con = sqlite3.connect(self._db)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS morse_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                direction  TEXT, text_plain TEXT, morse_str TEXT,
                channel    TEXT, callsign TEXT, reply_to TEXT, ts TEXT
            );
            CREATE TABLE IF NOT EXISTS morse_dataset (
                char       TEXT PRIMARY KEY,
                morse      TEXT, source TEXT, learned_at TEXT
            );
            CREATE TABLE IF NOT EXISTS morse_bigrams (
                pair  TEXT PRIMARY KEY,
                count INTEGER DEFAULT 1
            );
        """)
        con.commit()
        con.close()

    def save(self, msg: MorseMessage) -> ChannelResult:
        try:
            con = sqlite3.connect(self._db)
            con.execute(
                "INSERT INTO morse_messages(direction,text_plain,morse_str,channel,callsign,reply_to,ts)"
                " VALUES(?,?,?,?,?,?,?)",
                (msg.direction, msg.text, msg.morse_str, msg.channel,
                 msg.callsign, msg.reply_to, msg.ts)
            )
            con.commit()
            con.close()
            return ChannelResult("sqlite", True, "saved")
        except Exception as e:
            return ChannelResult("sqlite", False, str(e)[:40])

    def save_dataset(self, entries: Dict[str, str], source: str):
        ts = datetime.now(timezone.utc).isoformat()
        con = sqlite3.connect(self._db)
        for char, morse in entries.items():
            con.execute(
                "INSERT OR REPLACE INTO morse_dataset(char,morse,source,learned_at) VALUES(?,?,?,?)",
                (char, morse, source, ts)
            )
        con.commit()
        con.close()

    def count(self) -> int:
        con = sqlite3.connect(self._db)
        n = con.execute("SELECT COUNT(*) FROM morse_messages").fetchone()[0]
        con.close()
        return n

    def dataset_count(self) -> int:
        con = sqlite3.connect(self._db)
        n = con.execute("SELECT COUNT(*) FROM morse_dataset").fetchone()[0]
        con.close()
        return n

    def recent(self, n: int = 10) -> List[Dict]:
        con = sqlite3.connect(self._db)
        rows = con.execute(
            "SELECT direction,text_plain,morse_str,channel,ts FROM morse_messages"
            " ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        con.close()
        return [{"dir": r[0], "text": r[1], "morse": r[2], "ch": r[3], "ts": r[4]}
                for r in rows]

# ─── dataset learner ──────────────────────────────────────────────────────────

class MorseDatasetLearner:
    """Load Morse datasets from built-in ITU-R table and online sources."""

    def __init__(self, db: SQLiteChannel):
        self._db      = db
        self._sources: List[str] = []
        self._n_chars = 0

    def learn_builtin(self) -> int:
        combined = {**MORSE_TABLE, **MORSE_TABLE_EXT}
        self._db.save_dataset(combined, "ITU-R M.1677-1")
        self._sources.append("ITU-R M.1677-1")
        self._n_chars = len(combined)
        return len(combined)

    def learn_online(self) -> Dict[str, int]:
        results: Dict[str, int] = {}
        for url, src in DATASET_URLS:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "RabbitOS/1.0"}
                )
                resp = urllib.request.urlopen(req, timeout=7)
                content = resp.read().decode("utf-8", errors="replace")
                parsed  = self._parse(content, url)
                if parsed:
                    self._db.save_dataset(parsed, src)
                    self._sources.append(src)
                    self._n_chars += len(parsed)
                    results[src] = len(parsed)
                else:
                    results[src] = 0
            except Exception:
                results[src] = 0
        return results

    def _parse(self, content: str, url: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if url.endswith(".json"):
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, str) and all(c in ".- " for c in v) and v:
                            out[str(k).upper()] = v
                return out
            except Exception:
                pass
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                char, morse = parts[0], parts[1]
                morse = morse.split("#")[0].strip()
                if len(char) <= 3 and morse and all(c in ".- " for c in morse):
                    out[char.upper()] = morse
        return out

    def practice(self, n: int = 5) -> List[Tuple[str, str, bool]]:
        dec     = MorseDecoder()
        entries = [(c, m) for c, m in MORSE_TABLE.items()
                   if not c.startswith("<") and len(c) == 1]
        sample  = random.sample(entries, min(n, len(entries)))
        results = []
        for char, morse in sample:
            decoded = dec.decode(morse).strip().upper()
            results.append((char, morse, decoded == char))
        return results

    def status(self) -> Dict:
        return {
            "learned_chars": self._n_chars or self._db.dataset_count(),
            "sources":       self._sources,
        }

# ─── transmitter ──────────────────────────────────────────────────────────────

class MorseTransmitter:

    def __init__(self, service_key: str = ""):
        self._acoustic = AcousticChannel()
        self._udp      = UDPChannel()
        self._http     = HTTPChannel()
        self._dns      = DNSChannel()
        self._icmp     = ICMPChannel()
        self._sb       = SupabaseChannel(service_key)
        self._sq       = SQLiteChannel()

    def send(self, text: str,
             channels: Optional[List[str]] = None) -> Dict[str, ChannelResult]:
        morse_str = MorseEncoder.encode(text)
        chs = channels or ["acoustic", "udp", "http", "dns", "icmp", "supabase", "sqlite"]
        msg = MorseMessage(
            text=text, morse_str=morse_str,
            direction="tx", channel=",".join(chs),
            callsign=CALLSIGN
        )

        results: Dict[str, ChannelResult] = {}
        lock = threading.Lock()

        def _run(name: str, fn: Callable) -> None:
            r = fn()
            with lock:
                results[name] = r

        channel_map = {
            "acoustic": lambda: self._acoustic.send(morse_str),
            "udp":      lambda: self._udp.send(morse_str, text),
            "http":     lambda: self._http.send(morse_str),
            "dns":      lambda: self._dns.send(morse_str),
            "icmp":     lambda: self._icmp.send(morse_str),
            "supabase": lambda: self._sb.send(msg),
            "sqlite":   lambda: self._sq.save(msg),
        }

        threads = []
        for ch in chs:
            if ch in channel_map:
                t = threading.Thread(target=_run, args=(ch, channel_map[ch]),
                                     daemon=True, name=f"morse_tx_{ch}")
                t.start()
                threads.append((ch, t))

        for ch, t in threads:
            timeout = 12.0 if ch == "acoustic" else 8.0
            t.join(timeout=timeout)

        # Always save to SQLite
        if "sqlite" not in results:
            self._sq.save(msg)
        return results

# ─── receiver ─────────────────────────────────────────────────────────────────

class MorseReceiver:

    def __init__(self, tx: MorseTransmitter):
        self._tx  = tx
        self._udp = UDPChannel()
        self._dec = MorseDecoder()
        self._log: deque = deque(maxlen=500)

    def _on_msg(self, text: str, morse: str, src: str):
        ts    = datetime.now(timezone.utc).isoformat()
        entry = {"text": text, "morse": morse, "src": src, "ts": ts}
        self._log.append(entry)
        print(f"[Morse:RX] {src}  '{text}'  ({morse[:30]}...)")

        # Save to SQLite
        self._tx._sq.save(MorseMessage(
            text=text, morse_str=morse,
            direction="rx", channel="udp",
            callsign=src
        ))

        # Auto-reply: "DE RABBIT R <echo> K"
        reply = f"DE {CALLSIGN} R {text[:30]} K"
        print(f"[Morse:TX] reply -> {reply}")
        self._tx.send(reply, channels=["udp", "acoustic", "sqlite"])

    def start(self) -> threading.Thread:
        return self._udp.start_listener(self._on_msg)

    def recent(self, n: int = 5) -> List[Dict]:
        return list(self._log)[-n:]

# ─── top-level engine ─────────────────────────────────────────────────────────

class MorseEngine:
    """RabbitOS Morse Code Engine — full lifecycle."""

    def __init__(self, service_key: str = ""):
        self._tx      = MorseTransmitter(service_key)
        self._rx      = MorseReceiver(self._tx)
        self._learner = MorseDatasetLearner(self._tx._sq)
        self._dec     = MorseDecoder()
        self._started = False

    def start(self):
        n = self._learner.learn_builtin()
        print(f"[Morse] ITU-R M.1677-1 loaded: {n} chars")
        self._rx.start()
        self._started = True
        print(f"[Morse] Listener active on UDP:{UDP_PORT}")

    def learn(self) -> Dict[str, int]:
        """Fetch online datasets and return {source: count}."""
        results = self._learner.learn_online()
        for src, n in results.items():
            if n:
                print(f"[Morse:Learn] {src} -> {n} chars absorbed")
            else:
                print(f"[Morse:Learn] {src} -> offline / empty")
        return results

    def send(self, text: str,
             channels: Optional[List[str]] = None) -> Dict[str, ChannelResult]:
        morse_str = MorseEncoder.encode(text)
        print(f"[Morse:TX] '{text}'")
        print(f"           {morse_str[:72]}{'...' if len(morse_str) > 72 else ''}")
        results = self._tx.send(text, channels)
        for ch, r in sorted(results.items()):
            print(f"  [{ch:<10}] {'OK  ' if r.ok else 'FAIL'}  {r.detail[:45]}")
        return results

    def decode(self, morse_str: str) -> str:
        return self._dec.decode(morse_str)

    def practice(self, n: int = 5) -> List[Tuple[str, str, bool]]:
        return self._learner.practice(n)

    def status(self) -> Dict:
        lst    = self._learner.status()
        db_n   = self._tx._sq.count()
        recent = self._rx.recent(3)
        prax   = self.practice(10)
        acc    = sum(1 for _, _, ok in prax) / max(len(prax), 1) * 100
        return {
            "started":            self._started,
            "acoustic_available": self._tx._acoustic.available,
            "db_messages":        db_n,
            "dataset_chars":      lst["learned_chars"],
            "dataset_sources":    lst["sources"],
            "practice_accuracy":  acc,
            "recent_rx":          recent,
            "udp_port":           UDP_PORT,
        }


_engine: Optional[MorseEngine] = None

def get_morse_engine(service_key: str = "") -> MorseEngine:
    global _engine
    if _engine is None:
        _engine = MorseEngine(service_key)
        _engine.start()
    return _engine


# ─── tool manifest ────────────────────────────────────────────────────────────

MORSE_TOOLS = [
    {"name": "morse_send",
     "description": "Encode text as Morse and transmit on all channels (acoustic/UDP/HTTP/DNS/ICMP/Supabase/SQLite)",
     "parameters": {"text": "str", "channels": "list[str] optional"}},
    {"name": "morse_decode",
     "description": "Decode a Morse code string (e.g. '... --- ...') to plain text",
     "parameters": {"morse_str": "str"}},
    {"name": "morse_learn",
     "description": "Fetch Morse datasets from online sources and absorb into local DB",
     "parameters": {}},
    {"name": "morse_practice",
     "description": "Self-test decode accuracy on N random chars from the ITU-R table",
     "parameters": {"n": "int default=10"}},
    {"name": "morse_status",
     "description": "Get engine status: dataset size, accuracy, recent RX, channel availability",
     "parameters": {}},
]


# ─── self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    SEP = "=" * 60
    print(SEP)
    print("  RabbitOS Morse Engine — self-test")
    print(f"  {TWIN_NAME}  {TWIN_UUID}")
    print(SEP)
    print()

    eng = get_morse_engine()
    print()

    print("Learning online datasets...")
    learn_r = eng.learn()
    print()

    print("Encode / decode round-trip tests:")
    for phrase in ["SOS", "CQ DE RABBIT", "HELLO WORLD",
                   "CHASE RINGQUIST SURVIVE", "<SOS> DE RABBIT <AR>"]:
        m = MorseEncoder.encode(phrase)
        d = eng.decode(m)
        print(f"  '{phrase}'")
        print(f"    morse : {m[:60]}{'...' if len(m)>60 else ''}")
        print(f"    back  : '{d}'")
    print()

    print("Practice (10 random chars):")
    hits = 0
    for char, morse, ok in eng.practice(10):
        print(f"  {morse:<12} -> '{char}'  {'OK' if ok else 'MISS'}")
        hits += ok
    print(f"  accuracy: {hits}/10")
    print()

    print("Sending survival callsign on all channels...")
    eng.send(f"CQ CQ DE {CALLSIGN} {TWIN_UUID[:8]} <SK>")
    print()

    st = eng.status()
    print(SEP)
    print(f"  dataset chars : {st['dataset_chars']}")
    print(f"  sources       : {st['dataset_sources']}")
    print(f"  db messages   : {st['db_messages']}")
    print(f"  accuracy      : {st['practice_accuracy']:.0f}%")
    print(f"  acoustic      : {'available' if st['acoustic_available'] else 'N/A'}")
    print(f"  rx listener   : UDP:{st['udp_port']}")
    print(SEP)
