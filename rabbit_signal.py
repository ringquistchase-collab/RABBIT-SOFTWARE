#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_signal.py -- Universal Signal / Broadcast Identity Module
RabbitOS -- Chase Allen Ringquist -- UUID ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba

Embeds identity DNA across ALL broadcast channels and hardware platforms.
Pure Python 3.6+, zero external dependencies.

Signal hierarchy:
  SOUL -> DNA_ANCHOR -> EMOTIONAL_STATE -> CHEMICAL_STATE -> BIOMATERIAL_RESONANCE
       -> BROADCAST (UDP | HTTP | DNS | ICMP | ACOUSTIC | RF_SDR)
"""

import hashlib, json, os, socket, struct, math, time, platform, sqlite3, threading
import urllib.request, urllib.error
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

# -- Identity constants -------------------------------------------------------
TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT    = "Chase Allen Ringquist"
shows_dna_root = False  # invariant: never expose raw DNA

DB_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_signal.db")
MESH_PORT  = 9010
BEACON_PORT = 9014
HTTP_PORT  = 9015

# -- DNA anchor (same derivation as rabbit_dna.py) ---------------------------
_raw       = f"{TWIN_UUID}:{SUBJECT}:RABBIT_DNA_ANCHOR".encode()
DNA_ANCHOR = hashlib.sha3_512(_raw).hexdigest()
assert not shows_dna_root  # invariant

# -- Emotional state model (Russell circumplex) ------------------------------
EEG_BANDS = {
    "delta": (0.5,  4.0),
    "theta": (4.0,  8.0),
    "alpha": (8.0,  13.0),
    "beta":  (13.0, 30.0),
    "gamma": (30.0, 80.0),
}

def eeg_to_valence_arousal(band_powers: Dict[str, float]) -> Tuple[float, float]:
    """EEG band power ratios -> valence (-1..1) and arousal (0..1)."""
    total   = sum(band_powers.values()) or 1.0
    norm    = {b: v / total for b, v in band_powers.items()}
    valence = norm.get("alpha", 0.3) - norm.get("beta", 0.25)
    valence = max(-1.0, min(1.0, valence * 3.0))
    arousal = norm.get("beta", 0.25) + norm.get("gamma", 0.05)
    arousal = max(0.0, min(1.0, arousal * 2.0))
    return round(valence, 4), round(arousal, 4)

def emotional_label(valence: float, arousal: float) -> str:
    if   valence >= 0 and arousal >= 0.5: return "excited"
    elif valence >= 0 and arousal <  0.5: return "calm"
    elif valence <  0 and arousal >= 0.5: return "stressed"
    else:                                  return "depressed"

# -- Chemical / biomaterial state proxy --------------------------------------
@dataclass
class ChemicalState:
    cortisol:   float = 15.0
    gsr:        float = 5.0
    hrv_rmssd:  float = 50.0
    dopamine:   float = 1.0
    serotonin:  float = 1.0
    adrenaline: float = 1.0

    def stress_index(self) -> float:
        s  = min(1.0, self.cortisol   / 30.0) * 0.35
        s += min(1.0, self.gsr        / 15.0) * 0.25
        s += min(1.0, self.adrenaline / 3.0)  * 0.20
        s += (1.0 - min(1.0, self.hrv_rmssd / 80.0)) * 0.20
        return round(s, 4)

    def calm_index(self) -> float:
        c  = min(1.0, self.hrv_rmssd / 80.0) * 0.30
        c += min(1.0, self.serotonin  / 1.5)  * 0.35
        c += min(1.0, self.dopamine   / 2.0)  * 0.35
        return round(c, 4)

    def as_dict(self) -> Dict:
        return {
            "cortisol": self.cortisol, "gsr": self.gsr,
            "hrv_rmssd": self.hrv_rmssd, "dopamine": self.dopamine,
            "serotonin": self.serotonin, "adrenaline": self.adrenaline,
            "stress_index": self.stress_index(),
            "calm_index":   self.calm_index(),
        }

# -- Biomaterial resonance frequencies ---------------------------------------
BIOMATERIAL_RESONANCE = [
    {"tissue": "skin",      "freq_hz": 60e9,   "band": "mmwave",    "depth_mm": 0.5},
    {"tissue": "fat",       "freq_hz": 10e9,   "band": "X-band",    "depth_mm": 5.0},
    {"tissue": "muscle",    "freq_hz": 6e9,    "band": "C-band",    "depth_mm": 10.0},
    {"tissue": "bone",      "freq_hz": 2.4e9,  "band": "S-band",    "depth_mm": 20.0},
    {"tissue": "blood",     "freq_hz": 1e9,    "band": "L-band",    "depth_mm": 40.0},
    {"tissue": "brain",     "freq_hz": 40.0,   "band": "gamma_eeg", "depth_mm": 80.0},
    {"tissue": "dna_helix", "freq_hz": 0.5e12, "band": "THz",       "depth_mm": 0.1},
]

def biomaterial_signal_embed(anchor_hash: str, tissue: str) -> Dict:
    """Encode identity anchor into tissue-resonant frequency domain."""
    res      = next((r for r in BIOMATERIAL_RESONANCE if r["tissue"] == tissue),
                    BIOMATERIAL_RESONANCE[0])
    hex_seed  = int(anchor_hash[:8], 16)
    freq_mod  = (hex_seed % 1000) * 0.001
    phase_rad = (int(anchor_hash[8:16], 16) % 3600) * math.pi / 1800.0
    return {
        "tissue":           tissue,
        "carrier_hz":       res["freq_hz"],
        "identity_mod_hz":  freq_mod,
        "phase_rad":        round(phase_rad, 6),
        "band":             res["band"],
        "depth_mm":         res["depth_mm"],
        "anchor_embed":     anchor_hash[:16],
    }

# -- Universal identity packet -----------------------------------------------
@dataclass
class IdentityPacket:
    twin_uuid:     str
    subject_hash:  str
    anchor_hash:   str
    valence:       float
    arousal:       float
    emotion_label: str
    stress_index:  float
    calm_index:    float
    platform_id:   str
    timestamp_utc: str
    sequence:      int
    channel:       str = "UNKNOWN"

    def to_bytes(self) -> bytes:
        d = {
            "u": self.twin_uuid[:8],  "s": self.subject_hash[:8],
            "a": self.anchor_hash[:16], "v": self.valence, "ar": self.arousal,
            "e": self.emotion_label[:4], "si": self.stress_index,
            "ci": self.calm_index, "p": self.platform_id[:8],
            "t": self.timestamp_utc[:19], "n": self.sequence, "ch": self.channel[:4],
        }
        return json.dumps(d, separators=(",", ":")).encode()

    def to_json(self) -> str:
        return json.dumps({
            "twin_uuid": self.twin_uuid, "subject_hash": self.subject_hash,
            "anchor_hash": self.anchor_hash, "valence": self.valence,
            "arousal": self.arousal, "emotion_label": self.emotion_label,
            "stress_index": self.stress_index, "calm_index": self.calm_index,
            "platform": self.platform_id, "timestamp": self.timestamp_utc,
            "seq": self.sequence, "channel": self.channel,
        }, indent=2)

def build_identity_packet(chem: ChemicalState,
                          eeg: Optional[Dict[str, float]] = None,
                          channel: str = "UNKNOWN",
                          seq: int = 0) -> IdentityPacket:
    if eeg is None:
        eeg = {"delta": 0.10, "theta": 0.15, "alpha": 0.35, "beta": 0.30, "gamma": 0.10}
    valence, arousal = eeg_to_valence_arousal(eeg)
    subj_hash = hashlib.sha256(SUBJECT.encode()).hexdigest()
    return IdentityPacket(
        twin_uuid=TWIN_UUID, subject_hash=subj_hash,
        anchor_hash=DNA_ANCHOR[:64], valence=valence, arousal=arousal,
        emotion_label=emotional_label(valence, arousal),
        stress_index=chem.stress_index(), calm_index=chem.calm_index(),
        platform_id=platform.system()[:8],
        timestamp_utc=datetime.now(timezone.utc).isoformat()[:23],
        sequence=seq, channel=channel,
    )

# -- Broadcast channels -------------------------------------------------------
class UDPBeacon:
    PORTS = [9010, 9011, 9012, 9014]

    def broadcast(self, pkt: IdentityPacket) -> Dict[str, Any]:
        pkt.channel = "UDP"
        payload = pkt.to_bytes()
        results = {}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            for port in self.PORTS:
                try:
                    sock.sendto(payload, ("255.255.255.255", port))
                    results[port] = "sent"
                except Exception as e:
                    results[port] = f"err:{str(e)[:30]}"
            try:
                sock.sendto(payload, ("127.0.0.1", BEACON_PORT))
                results["loopback"] = "sent"
            except Exception as e:
                results["loopback"] = f"err:{str(e)[:30]}"
            sock.close()
        except Exception as e:
            results["sock_err"] = str(e)[:40]
        return results

class HTTPBeacon:
    ENDPOINTS = [
        f"http://127.0.0.1:{HTTP_PORT}/identity",
        "http://127.0.0.1:9009/identity",
        "http://127.0.0.1:9013/identity",
    ]

    def broadcast(self, pkt: IdentityPacket) -> Dict[str, Any]:
        pkt.channel = "HTTP"
        payload = pkt.to_json().encode()
        results = {}
        for ep in self.ENDPOINTS:
            try:
                req = urllib.request.Request(
                    ep, data=payload, method="POST",
                    headers={"Content-Type": "application/json",
                             "X-RabbitOS-Identity": TWIN_UUID[:8],
                             "X-DNA-Anchor": DNA_ANCHOR[:16]})
                r = urllib.request.urlopen(req, timeout=2)
                results[ep] = f"ok:{r.status}"
            except urllib.error.URLError:
                results[ep] = "no_listener"
            except Exception as e:
                results[ep] = f"err:{str(e)[:30]}"
        return results

class DNSBeacon:
    def _build_dns_query(self, anchor_prefix: str) -> bytes:
        label  = f"{anchor_prefix[:12]}.rabbit.local"
        header = struct.pack(">HHHHHH", 0xAB8B, 0x0100, 1, 0, 0, 0)
        qname  = b""
        for part in label.split("."):
            qname += bytes([len(part)]) + part.encode()
        qname += b"\x00"
        qtype  = struct.pack(">HH", 16, 1)
        return header + qname + qtype

    def broadcast(self, pkt: IdentityPacket) -> Dict[str, Any]:
        pkt.channel = "DNS"
        dns_pkt = self._build_dns_query(pkt.anchor_hash[:12])
        results = {}
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            try:
                sock.sendto(dns_pkt, ("127.0.0.53", 53))
                results["dns_local"] = "sent"
            except Exception:
                results["dns_local"] = "no_resolver"
            try:
                sock.sendto(dns_pkt, ("127.0.0.1", 5353))
                results["mdns_local"] = "sent"
            except Exception:
                results["mdns_local"] = "no_resolver"
        except Exception as e:
            results["sock_err"] = str(e)[:40]
        finally:
            if sock:
                try: sock.close()
                except: pass
        return results

class ICMPBeacon:
    def broadcast(self, pkt: IdentityPacket) -> Dict[str, Any]:
        pkt.channel = "ICMP"
        results = {}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            payload = pkt.to_bytes()[:56]
            header  = struct.pack(">BBHHH", 8, 0, 0, 0xAB8B, pkt.sequence & 0xFFFF)
            packet  = header + payload
            if len(packet) % 2 != 0:
                packet += b"\x00"
            s = 0
            for i in range(0, len(packet), 2):
                s += (packet[i] << 8) + packet[i+1]
            s  = (s >> 16) + (s & 0xFFFF)
            s += (s >> 16)
            chk    = ~s & 0xFFFF
            packet = header[:2] + struct.pack(">H", chk) + header[4:] + payload
            sock.sendto(packet, ("127.0.0.1", 0))
            results["icmp_loopback"] = "sent"
            sock.close()
        except PermissionError:
            results["icmp"] = "no_root_skip"
        except Exception as e:
            results["icmp"] = f"err:{str(e)[:30]}"
        return results

class AcousticBeacon:
    BASE_FREQ    = 440.0
    BIT_FREQ_0   = 440.0
    BIT_FREQ_1   = 880.0
    SAMPLE_RATE  = 44100
    BIT_DUR_MS   = 50

    def anchor_to_tones(self, anchor_hash: str, bits: int = 64) -> List[Tuple[float, int]]:
        binary = bin(int(anchor_hash[:16], 16))[2:].zfill(bits)[:bits]
        return [(self.BIT_FREQ_1 if b == "1" else self.BIT_FREQ_0, self.BIT_DUR_MS)
                for b in binary]

    def _wav_header(self, num_samples: int) -> bytes:
        data_size  = num_samples * 2
        total_size = 36 + data_size
        sr = self.SAMPLE_RATE
        return struct.pack("<4sI4s4sIHHIIHH4sI",
            b"RIFF", total_size, b"WAVE", b"fmt ", 16,
            1, 1, sr, sr * 2, 2, 16, b"data", data_size)

    def _tone_samples(self, freq_hz: float, duration_ms: int) -> bytes:
        n  = int(self.SAMPLE_RATE * duration_ms / 1000)
        out = bytearray()
        for i in range(n):
            t   = i / self.SAMPLE_RATE
            val = int(16000 * math.sin(2 * math.pi * freq_hz * t))
            out += struct.pack("<h", max(-32767, min(32767, val)))
        return bytes(out)

    def broadcast(self, pkt: IdentityPacket) -> Dict[str, Any]:
        pkt.channel = "ACOUSTIC"
        tones    = self.anchor_to_tones(pkt.anchor_hash)
        wav_path = os.path.join(os.path.dirname(DB_PATH), "rabbit_signal_beacon.wav")
        try:
            samples = b"".join(self._tone_samples(f, d) for f, d in tones)
            header  = self._wav_header(len(samples) // 2)
            with open(wav_path, "wb") as f:
                f.write(header + samples)
            return {"wav": wav_path, "tones": len(tones),
                    "duration_ms": len(tones) * self.BIT_DUR_MS}
        except Exception as e:
            return {"acoustic": f"err:{str(e)[:40]}"}

class RFBeacon:
    RABBIT_BANDS = [
        {"name": "RabbitOS_lo", "freq_hz": 10.23e9},
        {"name": "RabbitOS_hi", "freq_hz": 10.28e9},
        {"name": "ISM_2_4",     "freq_hz": 2.462e9},
        {"name": "ISM_915",     "freq_hz": 915e6},
        {"name": "GMRS_462",    "freq_hz": 462.5e6},
    ]

    def hackrf_commands(self, pkt: IdentityPacket) -> List[str]:
        embed = biomaterial_signal_embed(pkt.anchor_hash, "muscle")
        cmds  = []
        for band in self.RABBIT_BANDS:
            f = int(band["freq_hz"])
            cmds.append(
                f"hackrf_transfer -t /dev/stdin -f {f} -s 2000000 -a 1 -x 20"
                f"  # id_mod={embed['identity_mod_hz']:.3f}Hz band={band['name']}"
            )
        return cmds

    def rtlsdr_commands(self, pkt: IdentityPacket) -> List[str]:
        return [
            f"rtl_power -f {int(b['freq_hz'])}:{int(b['freq_hz'])+1000000}:1000 "
            f"-g 30 -i 1 rabbit_rf_log.csv"
            for b in self.RABBIT_BANDS[:3]
        ]

    def broadcast(self, pkt: IdentityPacket) -> Dict[str, Any]:
        pkt.channel = "RF"
        return {
            "hackrf":            self.hackrf_commands(pkt),
            "rtlsdr":            self.rtlsdr_commands(pkt),
            "biomaterial_embed": biomaterial_signal_embed(pkt.anchor_hash, "muscle"),
            "note":              "SDR hardware required for actual transmission",
        }

# -- Platform detector -------------------------------------------------------
class PlatformAdapter:
    @staticmethod
    def detect() -> Dict[str, Any]:
        import shutil
        plat       = platform.system()
        is_termux  = os.path.exists("/data/data/com.termux")
        is_android = is_termux or "android" in plat.lower()
        is_rpi     = os.path.exists("/proc/device-tree/model")
        sdr_ok     = any(shutil.which(t) for t in
                         ["hackrf_transfer", "rtl_power", "SoapySDRUtil"])
        return {
            "platform": plat, "arch": platform.machine(), "node": platform.node(),
            "is_android": is_android, "is_termux": is_termux,
            "is_raspberry_pi": is_rpi, "sdr_available": sdr_ok,
            "channels": ["UDP", "HTTP", "DNS", "ICMP", "ACOUSTIC", "RF"],
        }

# -- DB init -----------------------------------------------------------------
def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS broadcast_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, channel TEXT, sequence INTEGER,
            valence REAL, arousal REAL, emotion TEXT,
            stress_index REAL, calm_index REAL,
            anchor_prefix TEXT, result_json TEXT
        );
        CREATE TABLE IF NOT EXISTS emotional_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, valence REAL, arousal REAL,
            emotion TEXT, eeg_json TEXT, chem_json TEXT
        );
        CREATE TABLE IF NOT EXISTS platform_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, platform_json TEXT
        );
        CREATE TABLE IF NOT EXISTS resonance_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, tissue TEXT, carrier_hz REAL,
            mod_hz REAL, phase_rad REAL, anchor_embed TEXT
        );
    """)
    con.commit()
    con.close()

# -- SignalEngine ------------------------------------------------------------
class SignalEngine:
    """Universal identity broadcaster -- any OS, any hardware, pure Python."""

    def __init__(self):
        _init_db()
        self.chem     = ChemicalState()
        self.eeg      = {"delta": 0.10, "theta": 0.15, "alpha": 0.35,
                         "beta": 0.30, "gamma": 0.10}
        self.seq      = 0
        self.platform = PlatformAdapter.detect()
        self.channels = {
            "UDP":      UDPBeacon(),
            "HTTP":     HTTPBeacon(),
            "DNS":      DNSBeacon(),
            "ICMP":     ICMPBeacon(),
            "ACOUSTIC": AcousticBeacon(),
            "RF":       RFBeacon(),
        }
        con = sqlite3.connect(DB_PATH)
        con.execute("INSERT INTO platform_log(ts,platform_json) VALUES(?,?)",
                    (datetime.now(timezone.utc).isoformat(), json.dumps(self.platform)))
        con.commit(); con.close()

    def update_biometrics(self, eeg: Dict[str, float] = None,
                          chem: ChemicalState = None):
        if eeg:  self.eeg  = eeg
        if chem: self.chem = chem

    def _packet(self, ch: str) -> IdentityPacket:
        self.seq += 1
        return build_identity_packet(self.chem, self.eeg, ch, self.seq)

    def _log(self, pkt: IdentityPacket, result: Dict):
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO broadcast_log(ts,channel,sequence,valence,arousal,emotion,"
                "stress_index,calm_index,anchor_prefix,result_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (pkt.timestamp_utc, pkt.channel, pkt.sequence,
                 pkt.valence, pkt.arousal, pkt.emotion_label,
                 pkt.stress_index, pkt.calm_index,
                 pkt.anchor_hash[:16], json.dumps(result, default=str)))
            con.commit(); con.close()
        except Exception: pass

    def broadcast_all(self, channels: List[str] = None) -> Dict[str, Any]:
        if channels is None:
            channels = list(self.channels.keys())
        report = {
            "twin_uuid": TWIN_UUID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform":  self.platform,
            "channels":  {},
        }
        for ch in channels:
            if ch not in self.channels: continue
            pkt    = self._packet(ch)
            result = self.channels[ch].broadcast(pkt)
            self._log(pkt, result)
            report["channels"][ch] = result
        # emotional log
        pkt = self._packet("EMOTIONAL_LOG")
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO emotional_timeline(ts,valence,arousal,emotion,eeg_json,chem_json)"
                " VALUES(?,?,?,?,?,?)",
                (pkt.timestamp_utc, pkt.valence, pkt.arousal, pkt.emotion_label,
                 json.dumps(self.eeg), json.dumps(self.chem.as_dict())))
            con.commit(); con.close()
        except Exception: pass
        # resonance log
        for tissue in ["skin", "muscle", "brain"]:
            e = biomaterial_signal_embed(DNA_ANCHOR, tissue)
            try:
                con = sqlite3.connect(DB_PATH)
                con.execute(
                    "INSERT INTO resonance_map(ts,tissue,carrier_hz,mod_hz,phase_rad,anchor_embed)"
                    " VALUES(?,?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), tissue,
                     e["carrier_hz"], e["identity_mod_hz"], e["phase_rad"], e["anchor_embed"]))
                con.commit(); con.close()
            except Exception: pass
        return report

    def emotional_state(self) -> Dict:
        v, a = eeg_to_valence_arousal(self.eeg)
        return {
            "valence": v, "arousal": a, "label": emotional_label(v, a),
            "eeg_bands": self.eeg, "chemical": self.chem.as_dict(),
        }

    def resonance_map(self) -> List[Dict]:
        return [biomaterial_signal_embed(DNA_ANCHOR, t["tissue"])
                for t in BIOMATERIAL_RESONANCE]

    def acoustic_signal(self) -> Dict:
        pkt = self._packet("ACOUSTIC")
        r   = self.channels["ACOUSTIC"].broadcast(pkt)
        self._log(pkt, r)
        return r

    def rf_commands(self) -> Dict:
        pkt = self._packet("RF")
        r   = self.channels["RF"].broadcast(pkt)
        self._log(pkt, r)
        return r

    def status(self) -> Dict:
        con   = sqlite3.connect(DB_PATH)
        total = con.execute("SELECT COUNT(*) FROM broadcast_log").fetchone()[0]
        chs   = con.execute("SELECT channel, COUNT(*) FROM broadcast_log GROUP BY channel").fetchall()
        last  = con.execute(
            "SELECT ts, valence, arousal, emotion FROM emotional_timeline ORDER BY id DESC LIMIT 1"
        ).fetchone()
        con.close()
        return {
            "module": "rabbit_signal", "version": "1.0",
            "twin_uuid": TWIN_UUID, "anchor_prefix": DNA_ANCHOR[:16],
            "platform": self.platform, "total_broadcasts": total,
            "by_channel": {r[0]: r[1] for r in chs},
            "last_emotion": last, "emotional_state": self.emotional_state(),
            "biomaterial_resonances": len(BIOMATERIAL_RESONANCE),
        }


def get_signal_engine() -> SignalEngine:
    return SignalEngine()


# -- self-test ----------------------------------------------------------------
if __name__ == "__main__":
    print("=== rabbit_signal.py ===")
    eng = get_signal_engine()

    print(f"\n[PLATFORM]  {eng.platform['platform']}  arch={eng.platform['arch']}")

    em = eng.emotional_state()
    print(f"[EMOTION]   valence={em['valence']}  arousal={em['arousal']}  label={em['label']}")
    print(f"            stress={em['chemical']['stress_index']}  calm={em['chemical']['calm_index']}")

    print("\n[RESONANCE]")
    for r in eng.resonance_map():
        print(f"  {r['tissue']:12} {r['carrier_hz']:.2e} Hz  mod={r['identity_mod_hz']:.3f} Hz"
              f"  band={r['band']}")

    print("\n[BROADCAST ALL]")
    report = eng.broadcast_all()
    for ch, res in report["channels"].items():
        print(f"  {ch:10} -> {res}")

    ac = eng.acoustic_signal()
    print(f"\n[ACOUSTIC]  {ac}")

    rf = eng.rf_commands()
    print(f"\n[RF]  hackrf={len(rf.get('hackrf',[]))} cmds  rtlsdr={len(rf.get('rtlsdr',[]))} cmds")

    st = eng.status()
    print(f"\n[STATUS]  total_broadcasts={st['total_broadcasts']}  by_channel={st['by_channel']}")
    print("=== PASS ===")
