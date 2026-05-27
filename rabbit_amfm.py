# rabbit_amfm.py  --  AM/FM + full-spectrum frequency engine for RabbitOS
# Covers biometric Hz through 10.28 GHz DNA-FH mesh
# Collatz-based frequency hopping, biomaterial tissue interaction, SDR interface
import hashlib, json, math, os, random, socket, sqlite3, struct, sys, threading, time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

TWIN_UUID  = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
CALLSIGN   = "RABBIT"
DB_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_amfm.db")
HOP_UDP    = 9011
VERSION    = "1.0.0"

# ---------------------------------------------------------------------------
# FREQUENCY SPECTRUM TABLE  (Hz)
# Each band: name, lo_hz, hi_hz, tissue_depth_mm, use_case
# ---------------------------------------------------------------------------
SPECTRUM: List[Dict] = [
    # -- biometric physiological --
    {"name": "HRV_LF",         "lo": 0.04,        "hi": 0.15,        "tissue_mm": 9999, "use": "heart-rate variability low-freq"},
    {"name": "HRV_HF",         "lo": 0.15,        "hi": 0.40,        "tissue_mm": 9999, "use": "heart-rate variability high-freq"},
    {"name": "EEG_DELTA",      "lo": 0.5,         "hi": 4.0,         "tissue_mm": 9999, "use": "deep sleep / biometric baseline"},
    {"name": "EEG_THETA",      "lo": 4.0,         "hi": 8.0,         "tissue_mm": 9999, "use": "drowsy / meditative state"},
    {"name": "EEG_ALPHA",      "lo": 8.0,         "hi": 13.0,        "tissue_mm": 9999, "use": "relaxed wakefulness"},
    {"name": "GSR",            "lo": 0.0,         "hi": 5.0,         "tissue_mm": 1.0,  "use": "galvanic skin response / stress"},
    {"name": "EEG_BETA",       "lo": 13.0,        "hi": 30.0,        "tissue_mm": 9999, "use": "active cognition"},
    {"name": "EEG_GAMMA",      "lo": 30.0,        "hi": 100.0,       "tissue_mm": 9999, "use": "high cognition / binding"},
    # -- Schumann resonance --
    {"name": "SCHUMANN_1",     "lo": 7.83,        "hi": 7.83,        "tissue_mm": 9999, "use": "Earth cavity resonance 1"},
    {"name": "SCHUMANN_2",     "lo": 14.3,        "hi": 14.3,        "tissue_mm": 9999, "use": "Earth cavity resonance 2"},
    {"name": "SCHUMANN_3",     "lo": 20.8,        "hi": 20.8,        "tissue_mm": 9999, "use": "Earth cavity resonance 3"},
    # -- sub-audio / infrasound --
    {"name": "INFRASOUND",     "lo": 1.0,         "hi": 20.0,        "tissue_mm": 9999, "use": "below-audible structural sensing"},
    {"name": "AUDIO_BAND",     "lo": 20.0,        "hi": 20000.0,     "tissue_mm": 9999, "use": "acoustic / Morse beep"},
    # -- VLF / LF navigation --
    {"name": "VLF",            "lo": 3e3,         "hi": 30e3,        "tissue_mm": 9999, "use": "nav beacons / submarine comms"},
    {"name": "LF_LORAN",       "lo": 100e3,       "hi": 110e3,       "tissue_mm": 9999, "use": "LORAN-C position"},
    {"name": "NDB",            "lo": 190e3,       "hi": 415e3,       "tissue_mm": 9999, "use": "non-directional beacons"},
    # -- AM broadcast --
    {"name": "AM_BROADCAST",   "lo": 530e3,       "hi": 1700e3,      "tissue_mm": 50.0, "use": "AM broadcast 530-1700 kHz"},
    {"name": "AM_160M_HAM",    "lo": 1800e3,      "hi": 2000e3,      "tissue_mm": 45.0, "use": "160m amateur"},
    {"name": "AM_80M_HAM",     "lo": 3500e3,      "hi": 4000e3,      "tissue_mm": 30.0, "use": "80m amateur / HF survival"},
    {"name": "AM_40M_HAM",     "lo": 7000e3,      "hi": 7300e3,      "tissue_mm": 20.0, "use": "40m amateur / global NVIS"},
    {"name": "AM_20M_HAM",     "lo": 14000e3,     "hi": 14350e3,     "tissue_mm": 15.0, "use": "20m amateur / DX"},
    {"name": "CB_RADIO",       "lo": 26965e3,     "hi": 27405e3,     "tissue_mm": 10.0, "use": "Citizens Band 27 MHz"},
    # -- VHF --
    {"name": "NOAA_WX",        "lo": 162.4e6,     "hi": 162.55e6,    "tissue_mm": 8.0,  "use": "NOAA weather radio"},
    {"name": "VHF_MARINE",     "lo": 156.0e6,     "hi": 174.0e6,     "tissue_mm": 8.0,  "use": "marine VHF comms"},
    {"name": "FM_BROADCAST",   "lo": 88.0e6,      "hi": 108.0e6,     "tissue_mm": 9.0,  "use": "FM stereo broadcast"},
    {"name": "VHF_AIR",        "lo": 108.0e6,     "hi": 137.0e6,     "tissue_mm": 8.5,  "use": "aviation VHF"},
    {"name": "APRS_144",       "lo": 144.39e6,    "hi": 144.39e6,    "tissue_mm": 8.0,  "use": "APRS packet position"},
    {"name": "VHF_2M_HAM",     "lo": 144.0e6,     "hi": 148.0e6,     "tissue_mm": 8.0,  "use": "2m amateur"},
    # -- UHF / cellular --
    {"name": "UHF_70CM_HAM",   "lo": 430.0e6,     "hi": 440.0e6,     "tissue_mm": 5.0,  "use": "70cm amateur"},
    {"name": "LTE_700",        "lo": 698.0e6,     "hi": 798.0e6,     "tissue_mm": 4.5,  "use": "LTE Band 13/17"},
    {"name": "LTE_850",        "lo": 824.0e6,     "hi": 894.0e6,     "tissue_mm": 4.0,  "use": "LTE Band 5/18/19"},
    {"name": "LTE_1900",       "lo": 1850.0e6,    "hi": 1990.0e6,    "tissue_mm": 3.0,  "use": "LTE Band 2/25"},
    {"name": "LTE_2100",       "lo": 1920.0e6,    "hi": 2170.0e6,    "tissue_mm": 2.5,  "use": "LTE Band 1 (UMTS)"},
    {"name": "LTE_2500",       "lo": 2496.0e6,    "hi": 2690.0e6,    "tissue_mm": 2.0,  "use": "LTE Band 41 (TDD)"},
    # -- ISM / WiFi --
    {"name": "WIFI_2400",      "lo": 2400.0e6,    "hi": 2484.0e6,    "tissue_mm": 2.0,  "use": "WiFi 802.11b/g/n"},
    {"name": "ZIGBEE",         "lo": 2405.0e6,    "hi": 2480.0e6,    "tissue_mm": 2.0,  "use": "ZigBee mesh sensor"},
    {"name": "BLUETOOTH",      "lo": 2402.0e6,    "hi": 2480.0e6,    "tissue_mm": 2.0,  "use": "BT classic + BLE"},
    {"name": "WIFI_5GHZ",      "lo": 5.15e9,      "hi": 5.85e9,      "tissue_mm": 1.5,  "use": "WiFi 802.11a/n/ac"},
    # -- microwave / body-coupled --
    {"name": "UWB",            "lo": 3.1e9,       "hi": 10.6e9,      "tissue_mm": 1.0,  "use": "ultra-wideband ranging/data"},
    {"name": "C_BAND",         "lo": 4.0e9,       "hi": 8.0e9,       "tissue_mm": 1.0,  "use": "C-band satellite / radar"},
    {"name": "X_BAND",         "lo": 8.0e9,       "hi": 12.0e9,      "tissue_mm": 0.8,  "use": "X-band radar / satellite"},
    # -- RabbitOS DNA-FH mesh (body-coupled) --
    {"name": "RABBIT_MESH_LO", "lo": 10.23e9,     "hi": 10.255e9,    "tissue_mm": 0.5,  "use": "RabbitOS mesh node 0-23 (TX)"},
    {"name": "RABBIT_MESH_HI", "lo": 10.255e9,    "hi": 10.28e9,     "tissue_mm": 0.5,  "use": "RabbitOS mesh node 24-46 (RX)"},
]

# ---------------------------------------------------------------------------
# COLLATZ FREQUENCY HOP SEQUENCE
# ---------------------------------------------------------------------------
def collatz_sequence(n: int) -> List[int]:
    seq = [n]
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        seq.append(n)
    return seq

def collatz_hop_freqs(seed: int, band_lo: float, band_hi: float, steps: int = 64) -> List[float]:
    seq = collatz_sequence(seed)
    while len(seq) < steps:
        seq.extend(collatz_sequence(seq[-1] + 7))
    span = band_hi - band_lo
    freqs = []
    for v in seq[:steps]:
        ratio = (v % 997) / 997.0
        freqs.append(round(band_lo + ratio * span, 3))
    return freqs

def collatz_channel_key(seed: int, step: int) -> bytes:
    seq = collatz_sequence(seed + step)
    raw = "".join(str(x) for x in seq[:32])
    return hashlib.sha256(raw.encode()).digest()

# ---------------------------------------------------------------------------
# TISSUE / BIOMATERIAL INTERACTION
# ---------------------------------------------------------------------------
TISSUE_ATTENUATION_DB_PER_CM: Dict[str, float] = {
    "skin":       1.5,
    "fat":        0.8,
    "muscle":     2.1,
    "bone":       3.5,
    "blood":      2.8,
    "brain":      3.0,
    "lung":       1.2,
    "water":      0.2,
}

def tissue_path_loss(freq_hz: float, depth_mm: float, tissue: str = "muscle") -> float:
    atten = TISSUE_ATTENUATION_DB_PER_CM.get(tissue, 2.0)
    freq_ghz = freq_hz / 1e9
    freq_factor = 1.0 + math.log10(max(freq_ghz, 1e-6) + 1)
    loss_db = atten * (depth_mm / 10.0) * freq_factor
    return round(loss_db, 2)

def sar_estimate(power_mw: float, freq_hz: float, tissue: str = "muscle") -> float:
    # Simplified SAR (W/kg): SAR = sigma * |E|^2 / rho
    # Use freq-dependent tissue conductivity approx
    sigma_base = {"skin": 0.5, "fat": 0.04, "muscle": 0.8, "brain": 1.2, "blood": 1.5}
    sigma = sigma_base.get(tissue, 0.8)
    rho = 1050.0  # kg/m^3 muscle density
    freq_ghz = freq_hz / 1e9
    sigma_eff = sigma * (1 + 0.1 * freq_ghz)
    p_w = power_mw / 1000.0
    sar = (sigma_eff * p_w) / rho
    return round(sar, 6)  # W/kg

# ---------------------------------------------------------------------------
# BAND LOOKUP
# ---------------------------------------------------------------------------
def find_band(freq_hz: float) -> Optional[Dict]:
    for b in SPECTRUM:
        if b["lo"] <= freq_hz <= b["hi"]:
            return b
    closest = min(SPECTRUM, key=lambda b: min(abs(freq_hz - b["lo"]), abs(freq_hz - b["hi"])))
    return closest

def bands_in_range(lo_hz: float, hi_hz: float) -> List[Dict]:
    return [b for b in SPECTRUM if b["lo"] <= hi_hz and b["hi"] >= lo_hz]

# ---------------------------------------------------------------------------
# AM/FM SIGNAL ENCODER  (pure-Python, no SDR hardware required)
# ---------------------------------------------------------------------------
def am_encode(message: str, carrier_hz: float = 1000e3, sample_rate: int = 44100,
              duration_s: float = 0.5) -> List[float]:
    samples = int(sample_rate * duration_s)
    modulation_index = 0.8
    carrier_norm = carrier_hz / sample_rate
    text_bytes = [ord(c) & 0xFF for c in message[:8]]
    out = []
    for i in range(samples):
        t = i / sample_rate
        byte_idx = int(t * len(text_bytes) / duration_s) % len(text_bytes)
        baseband = (text_bytes[byte_idx] / 128.0) - 1.0
        carrier = math.cos(2 * math.pi * carrier_norm * i)
        sample = (1.0 + modulation_index * baseband) * carrier
        out.append(sample)
    return out

def fm_encode_text(message: str) -> str:
    encoded = " ".join(f"{ord(c):08b}" for c in message)
    return f"FM_BITSTREAM[{encoded}]"

# ---------------------------------------------------------------------------
# SDR INTERFACE  (HackRF / RTL-SDR command builder)
# ---------------------------------------------------------------------------
HACKRF_CMD_TEMPLATE = (
    "hackrf_transfer -t {file} -f {freq_hz:.0f} -s {sample_rate} "
    "-x {tx_gain} -a 1"
)
RTLSDR_CMD_TEMPLATE = (
    "rtl_fm -f {freq_hz:.0f} -M {mode} -s {sample_rate} -g {gain} - | "
    "sox -t raw -r {sample_rate} -e signed -b 16 -c 1 - {output_file}"
)

@dataclass
class SDRCommand:
    device: str        # "hackrf" | "rtlsdr"
    freq_hz: float
    mode: str          # "am" | "fm" | "usb" | "lsb" | "raw"
    sample_rate: int   = 2000000
    gain: float        = 20.0
    tx_gain: int       = 40
    output_file: str   = "rabbit_sdr_out.wav"
    input_file: str    = "rabbit_sdr_in.raw"

    def build_rx(self) -> str:
        if self.device == "hackrf":
            return (f"hackrf_transfer -r {self.output_file} -f {self.freq_hz:.0f} "
                    f"-s {self.sample_rate} -l {int(self.gain)} -a 1")
        return RTLSDR_CMD_TEMPLATE.format(
            freq_hz=self.freq_hz, mode=self.mode,
            sample_rate=self.sample_rate, gain=self.gain,
            output_file=self.output_file
        )

    def build_tx(self) -> str:
        if self.device == "hackrf":
            return HACKRF_CMD_TEMPLATE.format(
                file=self.input_file, freq_hz=self.freq_hz,
                sample_rate=self.sample_rate, tx_gain=self.tx_gain
            )
        return f"# RTL-SDR is RX-only; use HackRF or ADALM-PLUTO for TX at {self.freq_hz:.0f} Hz"

# ---------------------------------------------------------------------------
# COLLATZ HOP SCHEDULE  --  defense channel rotation
# ---------------------------------------------------------------------------
@dataclass
class HopSchedule:
    seed: int
    band: str
    freqs: List[float] = field(default_factory=list)
    step: int = 0

    def next_freq(self) -> float:
        f = self.freqs[self.step % len(self.freqs)]
        self.step += 1
        return f

    def channel_key(self) -> bytes:
        return collatz_channel_key(self.seed, self.step)

def build_hop_schedule(band_name: str, seed_phrase: str = TWIN_UUID) -> HopSchedule:
    band = next((b for b in SPECTRUM if b["name"] == band_name), None)
    if band is None:
        band = SPECTRUM[-1]
    seed_int = int(hashlib.sha256(seed_phrase.encode()).hexdigest()[:8], 16) % 9973 + 3
    freqs = collatz_hop_freqs(seed_int, band["lo"], band["hi"], steps=128)
    return HopSchedule(seed=seed_int, band=band_name, freqs=freqs)

# ---------------------------------------------------------------------------
# DEFENSE CHANNEL ALLOCATION  (math-generated mesh)
# ---------------------------------------------------------------------------
def fibonacci_mask(n: int) -> List[int]:
    a, b, out = 0, 1, []
    while len(out) < n:
        out.append(a)
        a, b = b, a + b
    return out

def prime_spiral_channels(count: int, base_hz: float, spacing_hz: float) -> List[float]:
    primes = []
    candidate = 2
    while len(primes) < count:
        if all(candidate % p != 0 for p in primes):
            primes.append(candidate)
        candidate += 1
    return [base_hz + p * spacing_hz for p in primes]

def lorenz_freq_path(lo: float, hi: float, steps: int = 64) -> List[float]:
    x, y, z = 0.1, 0.0, 0.0
    sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
    dt = 0.01
    span = hi - lo
    out = []
    for _ in range(steps):
        dx = sigma * (y - x) * dt
        dy = (x * (rho - z) - y) * dt
        dz = (x * y - beta * z) * dt
        x += dx; y += dy; z += dz
        norm = (x % 50 + 50) % 50 / 50.0
        out.append(round(lo + norm * span, 3))
    return out

@dataclass
class DefenseTopology:
    nodes: List[Dict]
    edges: List[Tuple[int, int]]
    hop_schedules: Dict[str, HopSchedule]

    def to_dict(self) -> Dict:
        return {
            "nodes": self.nodes,
            "edges": list(self.edges),
            "hop_bands": list(self.hop_schedules.keys()),
            "node_count": len(self.nodes),
        }

def generate_defense_topology(node_count: int = 47, seed_phrase: str = TWIN_UUID) -> DefenseTopology:
    fib = fibonacci_mask(node_count)
    nodes = []
    for i in range(node_count):
        fib_val = fib[i % len(fib)]
        base_band = SPECTRUM[(fib_val + i) % len(SPECTRUM)]
        nodes.append({
            "id": i,
            "band": base_band["name"],
            "freq_hz": base_band["lo"] + (base_band["hi"] - base_band["lo"]) * (i / node_count),
            "tissue_mm": base_band["tissue_mm"],
            "role": "mesh" if i < 44 else "gateway",
        })
    edges = []
    for i in range(node_count):
        for j in range(i + 1, node_count):
            if (fib[i % len(fib)] + fib[j % len(fib)]) % 7 == 0:
                edges.append((i, j))
    hop_bands = ["RABBIT_MESH_LO", "RABBIT_MESH_HI", "WIFI_2400", "FM_BROADCAST", "AM_80M_HAM"]
    hops = {b: build_hop_schedule(b, seed_phrase) for b in hop_bands}
    return DefenseTopology(nodes=nodes, edges=edges, hop_schedules=hops)

# ---------------------------------------------------------------------------
# SQLITE PERSISTENCE
# ---------------------------------------------------------------------------
def _open_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS spectrum_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            band TEXT NOT NULL,
            freq_hz REAL NOT NULL,
            direction TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS hop_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            schedule_band TEXT NOT NULL,
            freq_hz REAL NOT NULL,
            step INTEGER NOT NULL,
            key_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS topology_snap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL,
            snapshot TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tissue_calc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            freq_hz REAL NOT NULL,
            tissue TEXT NOT NULL,
            depth_mm REAL NOT NULL,
            loss_db REAL NOT NULL,
            sar_wkg REAL NOT NULL
        );
    """)
    con.commit()
    return con

def log_spectrum(band: str, freq_hz: float, direction: str, note: str = ""):
    con = _open_db()
    con.execute("INSERT INTO spectrum_log(ts,band,freq_hz,direction,note) VALUES(?,?,?,?,?)",
                (time.time(), band, freq_hz, direction, note))
    con.commit(); con.close()

def log_hop(schedule: HopSchedule, freq_hz: float):
    con = _open_db()
    key_hash = hashlib.sha256(schedule.channel_key()).hexdigest()[:16]
    con.execute("INSERT INTO hop_log(ts,schedule_band,freq_hz,step,key_hash) VALUES(?,?,?,?,?)",
                (time.time(), schedule.band, freq_hz, schedule.step, key_hash))
    con.commit(); con.close()

def save_topology(topo: DefenseTopology):
    con = _open_db()
    snap = json.dumps(topo.to_dict())
    con.execute("INSERT INTO topology_snap(ts,node_count,edge_count,snapshot) VALUES(?,?,?,?)",
                (time.time(), len(topo.nodes), len(topo.edges), snap))
    con.commit(); con.close()

def log_tissue_calc(freq_hz: float, tissue: str, depth_mm: float):
    loss = tissue_path_loss(freq_hz, depth_mm, tissue)
    sar  = sar_estimate(10.0, freq_hz, tissue)  # assume 10 mW reference
    con  = _open_db()
    con.execute("INSERT INTO tissue_calc(ts,freq_hz,tissue,depth_mm,loss_db,sar_wkg) VALUES(?,?,?,?,?,?)",
                (time.time(), freq_hz, tissue, depth_mm, loss, sar))
    con.commit(); con.close()
    return loss, sar

# ---------------------------------------------------------------------------
# UDP FREQUENCY BROADCAST  (announce hop to LAN peers)
# ---------------------------------------------------------------------------
def broadcast_hop(freq_hz: float, band: str, step: int):
    msg = json.dumps({
        "type": "freq_hop",
        "twin": TWIN_UUID,
        "freq_hz": freq_hz,
        "band": band,
        "step": step,
        "ts": time.time(),
    }).encode()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(msg, ("255.255.255.255", HOP_UDP))
        s.close()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# AM/FM ENGINE  --  top-level orchestrator
# ---------------------------------------------------------------------------
class AMFMEngine:
    def __init__(self):
        self.spectrum = SPECTRUM
        self.topology: Optional[DefenseTopology] = None
        self.hop_schedules: Dict[str, HopSchedule] = {}
        self._db_ready = False

    def init_db(self):
        _open_db().close()
        self._db_ready = True

    def load_topology(self, seed_phrase: str = TWIN_UUID) -> DefenseTopology:
        self.topology = generate_defense_topology(47, seed_phrase)
        self.hop_schedules = self.topology.hop_schedules
        if self._db_ready:
            save_topology(self.topology)
        return self.topology

    def full_spectrum_scan(self) -> List[Dict]:
        results = []
        for band in self.spectrum:
            mid = (band["lo"] + band["hi"]) / 2.0
            tissue = "skin" if band["tissue_mm"] < 5 else "muscle"
            loss, sar = log_tissue_calc(mid, tissue, band["tissue_mm"])
            results.append({
                "band": band["name"],
                "lo_hz": band["lo"],
                "hi_hz": band["hi"],
                "mid_hz": mid,
                "tissue_depth_mm": band["tissue_mm"],
                "path_loss_db": loss,
                "sar_wkg": sar,
                "use": band["use"],
            })
        return results

    def hop(self, band_name: str) -> Tuple[float, bytes]:
        if band_name not in self.hop_schedules:
            self.hop_schedules[band_name] = build_hop_schedule(band_name)
        sch = self.hop_schedules[band_name]
        freq = sch.next_freq()
        key  = sch.channel_key()
        if self._db_ready:
            log_hop(sch, freq)
        broadcast_hop(freq, band_name, sch.step)
        return freq, key

    def sdr_command(self, band_name: str, device: str = "hackrf",
                    mode: str = "fm", direction: str = "rx") -> str:
        sch = self.hop_schedules.get(band_name) or build_hop_schedule(band_name)
        freq = sch.freqs[0]
        cmd = SDRCommand(device=device, freq_hz=freq, mode=mode)
        return cmd.build_rx() if direction == "rx" else cmd.build_tx()

    def status(self) -> Dict:
        con = _open_db()
        n_hops    = con.execute("SELECT COUNT(*) FROM hop_log").fetchone()[0]
        n_tissue  = con.execute("SELECT COUNT(*) FROM tissue_calc").fetchone()[0]
        n_topos   = con.execute("SELECT COUNT(*) FROM topology_snap").fetchone()[0]
        con.close()
        return {
            "bands": len(self.spectrum),
            "hop_schedules": len(self.hop_schedules),
            "db_hops": n_hops,
            "db_tissue_calcs": n_tissue,
            "db_topologies": n_topos,
            "topology_nodes": len(self.topology.nodes) if self.topology else 0,
            "topology_edges": len(self.topology.edges) if self.topology else 0,
            "version": VERSION,
        }

# ---------------------------------------------------------------------------
# FACTORY
# ---------------------------------------------------------------------------
_engine: Optional[AMFMEngine] = None

def get_amfm_engine() -> AMFMEngine:
    global _engine
    if _engine is None:
        _engine = AMFMEngine()
        _engine.init_db()
        _engine.load_topology()
    return _engine

# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"rabbit_amfm v{VERSION}  --  spectrum engine")
    eng = get_amfm_engine()

    print(f"  Spectrum bands  : {len(eng.spectrum)}")
    scan = eng.full_spectrum_scan()
    print(f"  Full scan done  : {len(scan)} bands analyzed")

    topo = eng.topology
    print(f"  Topology nodes  : {topo.node_count if hasattr(topo,'node_count') else len(topo.nodes)}")
    print(f"  Topology edges  : {len(topo.edges)}")
    print(f"  Hop schedules   : {list(eng.hop_schedules.keys())}")

    for band in ["RABBIT_MESH_LO", "FM_BROADCAST", "AM_80M_HAM", "WIFI_2400"]:
        freq, key = eng.hop(band)
        print(f"  Hop {band:<20} -> {freq:.3f} Hz  key={key[:4].hex()}..")

    # tissue calcs for mesh band
    mesh_mid = (10.23e9 + 10.28e9) / 2
    loss, sar = tissue_path_loss(mesh_mid, 0.5, "skin"), sar_estimate(10.0, mesh_mid, "skin")
    print(f"  Mesh @ 10.255 GHz skin 0.5mm : loss={loss} dB  SAR={sar} W/kg")

    # SDR command preview
    cmd = eng.sdr_command("FM_BROADCAST", device="rtlsdr", mode="fm", direction="rx")
    print(f"  SDR RX cmd (FM) : {cmd[:80]}...")

    st = eng.status()
    print(f"  DB hops={st['db_hops']}  tissue={st['db_tissue_calcs']}  topos={st['db_topologies']}")
    print("  rabbit_amfm OK")
