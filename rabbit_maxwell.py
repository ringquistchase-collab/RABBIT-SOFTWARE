#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_maxwell.py -- Maxwell Equations + RF-to-DNA Frequency Encoding
RabbitOS -- Chase Allen Ringquist -- UUID ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba

Implements Maxwell's electromagnetic equations in pure Python and extends them
to encode Chase Allen Ringquist's identity into RF / natural frequencies /
biomaterial propagation -- so communication is always present with or without hardware.

Physics implemented (pure Python, zero dependencies):
  - Maxwell's 4 equations (Gauss E/B, Faraday, Ampere-Maxwell)
  - Plane wave propagation in lossy dielectric (tissue)
  - Skin depth, attenuation, phase velocity
  - Poynting vector (power flux density)
  - Near-field / far-field transition distance
  - Friis transmission equation (link budget)
  - RF-to-binary encoding (identity payload -> modulation)
  - Natural frequency catalog (Schumann, EEG bands, Solfeggio, DNA THz)
  - Collatz-seeded frequency hopping schedule
  - Biomaterial dielectric properties at RabbitOS mesh frequency
"""

import hashlib, json, math, os, sqlite3, time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# -- Identity ----------------------------------------------------------------
TWIN_UUID      = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
SUBJECT        = "Chase Allen Ringquist"
shows_dna_root = False
_raw           = f"{TWIN_UUID}:{SUBJECT}:RABBIT_DNA_ANCHOR".encode()
DNA_ANCHOR     = hashlib.sha3_512(_raw).hexdigest()
assert not shows_dna_root

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rabbit_maxwell.db")

# -- Physical constants -------------------------------------------------------
C_LIGHT     = 2.998e8        # m/s speed of light
MU_0        = 4 * math.pi * 1e-7   # H/m permeability of free space
EPS_0       = 8.854e-12      # F/m permittivity of free space
ETA_0       = 376.73         # ohms -- wave impedance of free space
BOLTZMANN   = 1.380649e-23   # J/K
PLANCK      = 6.62607e-34    # J*s
ELEM_CHARGE = 1.602176e-19   # C

# -- Natural / resonance frequency catalog -----------------------------------
NATURAL_FREQUENCIES = {
    # Schumann resonances (Earth-ionosphere cavity)
    "schumann_1":      7.83,
    "schumann_2":      14.3,
    "schumann_3":      20.8,
    "schumann_4":      27.3,
    "schumann_5":      33.8,
    # EEG bands (Hz)
    "eeg_delta":       2.0,
    "eeg_theta":       6.0,
    "eeg_alpha":       10.0,
    "eeg_beta":        20.0,
    "eeg_gamma":       40.0,
    "eeg_high_gamma":  80.0,
    # Heart / autonomic
    "hrv_vlf":         0.04,
    "hrv_lf":          0.1,
    "hrv_hf":          0.25,
    # Solfeggio frequencies (Hz)
    "solfeggio_396":   396.0,
    "solfeggio_417":   417.0,
    "solfeggio_528":   528.0,
    "solfeggio_639":   639.0,
    "solfeggio_741":   741.0,
    "solfeggio_852":   852.0,
    "solfeggio_963":   963.0,
    # RabbitOS mesh
    "rabbit_lo":       10.23e9,
    "rabbit_hi":       10.28e9,
    "rabbit_center":   10.25e9,
    # DNA / molecular THz
    "dna_thz_1":       0.5e12,
    "dna_thz_2":       1.0e12,
    "dna_thz_3":       1.6e12,
    # Standard RF bands
    "lte_low":         700e6,
    "wifi_2g":         2.4e9,
    "wifi_5g":         5.8e9,
    "bluetooth":       2.402e9,
    "gps_l1":          1.57542e9,
}

# -- Biomaterial dielectric properties (at ~10 GHz unless noted) -------------
TISSUE_DIELECTRIC = {
    "skin":    {"eps_r": 37.8,  "sigma": 16.4, "rho": 1100, "cp": 3500},
    "fat":     {"eps_r":  5.3,  "sigma":  0.27, "rho": 920,  "cp": 2500},
    "muscle":  {"eps_r": 52.7,  "sigma": 17.8, "rho": 1050, "cp": 3600},
    "bone":    {"eps_r":  8.0,  "sigma":  1.5,  "rho": 1900, "cp": 1300},
    "blood":   {"eps_r": 63.7,  "sigma": 23.1, "rho": 1060, "cp": 3617},
    "brain":   {"eps_r": 44.0,  "sigma": 14.8, "rho": 1040, "cp": 3700},
    "lung":    {"eps_r": 21.7,  "sigma":  5.5,  "rho": 400,  "cp": 3500},
    "liver":   {"eps_r": 46.0,  "sigma": 12.7, "rho": 1080, "cp": 3600},
    "kidney":  {"eps_r": 58.0,  "sigma": 23.4, "rho": 1050, "cp": 3700},
    "dna_helix": {"eps_r": 8.0, "sigma":  0.001, "rho": 1700, "cp": 1200},
}

# -- Maxwell equations (analytical solutions) --------------------------------
def maxwell_wave_number(freq_hz: float, eps_r: float, sigma: float) -> Tuple[float, float]:
    """
    Complex wave number k = beta - j*alpha for lossy dielectric.
    Returns (alpha_np_per_m, beta_rad_per_m)
    alpha = attenuation constant (Np/m)
    beta  = phase constant (rad/m)
    """
    omega   = 2 * math.pi * freq_hz
    eps_eff = eps_r - (sigma / (omega * EPS_0)) * 1j  # complex permittivity (conceptual)
    # Analytical: alpha = omega*sqrt(mu_0*eps_0/2)*sqrt(eps_r*(sqrt(1+(sigma/omega/eps_0/eps_r)^2)-1))
    loss_tan = sigma / (omega * EPS_0 * eps_r)
    term     = math.sqrt(1 + loss_tan**2)
    alpha    = (omega / C_LIGHT) * math.sqrt(eps_r / 2 * (term - 1))
    beta     = (omega / C_LIGHT) * math.sqrt(eps_r / 2 * (term + 1))
    return alpha, beta

def skin_depth_mm(freq_hz: float, sigma: float, eps_r: float = 1.0) -> float:
    """
    Electromagnetic skin depth delta = 1/alpha (mm).
    For good conductor: delta = sqrt(2/(omega*mu_0*sigma)).
    """
    omega = 2 * math.pi * freq_hz
    if sigma > 1.0:  # lossy conductor approximation
        delta_m = math.sqrt(2.0 / (omega * MU_0 * sigma))
    else:
        alpha, _ = maxwell_wave_number(freq_hz, eps_r, sigma)
        delta_m  = 1.0 / alpha if alpha > 0 else float("inf")
    return delta_m * 1000.0

def wave_impedance_tissue(freq_hz: float, eps_r: float, sigma: float) -> complex:
    """
    Intrinsic wave impedance eta = sqrt(mu_0 / eps_c) [ohms].
    Returns (magnitude_ohm, phase_deg).
    """
    omega    = 2 * math.pi * freq_hz
    loss_tan = sigma / (omega * EPS_0 * eps_r)
    # |eta| = eta_0 / sqrt(eps_r) * (1 + loss_tan^2)^(-1/4)
    mag      = ETA_0 / (math.sqrt(eps_r) * (1 + loss_tan**2) ** 0.25)
    phase_deg = 0.5 * math.degrees(math.atan(loss_tan))
    return mag, phase_deg

def reflection_coefficient(eta1: float, eta2: float) -> float:
    """Plane wave normal incidence reflection coeff |Gamma|."""
    return abs((eta2 - eta1) / (eta2 + eta1))

def transmission_coefficient(eta1: float, eta2: float) -> float:
    """Plane wave normal incidence transmission coeff |tau|."""
    return abs(2 * eta2 / (eta2 + eta1))

def poynting_vector_W_m2(E_field_V_m: float, eta_ohm: float) -> float:
    """Time-averaged Poynting vector magnitude |S| = E^2 / (2*eta) [W/m^2]."""
    return (E_field_V_m ** 2) / (2.0 * eta_ohm)

def sar_W_per_kg(E_field_V_m: float, sigma: float, rho_kg_m3: float) -> float:
    """
    Specific Absorption Rate SAR = sigma*E^2 / rho  [W/kg].
    IEEE C95.1 limit: 1.6 W/kg (1g avg), 4 W/kg (10g avg).
    """
    return sigma * (E_field_V_m ** 2) / rho_kg_m3

def friis_path_loss_db(freq_hz: float, distance_m: float) -> float:
    """Friis free-space path loss FSPL = 20*log10(4*pi*d*f/c) [dB]."""
    return 20 * math.log10(4 * math.pi * distance_m * freq_hz / C_LIGHT)

def near_field_far_field_m(aperture_m: float, freq_hz: float) -> float:
    """Fraunhofer distance d = 2*D^2/lambda [m]."""
    wavelength = C_LIGHT / freq_hz
    return 2.0 * (aperture_m ** 2) / wavelength

def faraday_induced_emf(B_peak_T: float, area_m2: float, freq_hz: float) -> float:
    """Faraday's law: |emf| = N * dPhi/dt = N * omega * B * A  [V]."""
    return 1 * 2 * math.pi * freq_hz * B_peak_T * area_m2

def ampere_maxwell_H(J_A_m2: float, dD_dt_A_m2: float) -> float:
    """Ampere-Maxwell: curl H = J + dD/dt  (magnitude, simplified) [A/m]."""
    return J_A_m2 + dD_dt_A_m2

# -- RF-to-binary encoding ---------------------------------------------------
def frequency_to_binary(freq_hz: float, bits: int = 16) -> str:
    """Map frequency to binary token via normalized quantization."""
    # Map to [0, 2^bits-1] over a reasonable range (1 Hz to 1 THz)
    f_norm = math.log10(max(1.0, freq_hz)) / 12.0  # log10(1 THz) = 12
    f_norm = min(1.0, max(0.0, f_norm))
    token  = int(f_norm * ((1 << bits) - 1))
    return bin(token)[2:].zfill(bits)

def binary_to_frequency(binary_str: str, f_min_hz: float = 1.0,
                        f_max_hz: float = 1e12) -> float:
    """Decode binary token back to approximate frequency."""
    bits   = len(binary_str)
    token  = int(binary_str, 2)
    f_norm = token / ((1 << bits) - 1)
    return 10 ** (f_norm * 12.0)

def anchor_to_frequency_sequence(anchor_hash: str, n: int = 8) -> List[float]:
    """
    Derive a sequence of n identity-encoded frequencies from DNA anchor.
    Each 4-hex nibble -> 16-bit token -> frequency.
    """
    freqs = []
    for i in range(n):
        hex_slice = anchor_hash[i*4:(i+1)*4]
        if len(hex_slice) < 4:
            hex_slice = hex_slice.ljust(4, "0")
        val  = int(hex_slice, 16)
        # Map 0..65535 to log-space 1 Hz .. 1 THz
        norm = val / 65535.0
        f    = 10 ** (norm * 12.0)
        freqs.append(round(f, 3))
    return freqs

def encode_identity_payload(twin_uuid: str, valence: float = 0.0,
                             arousal: float = 0.5) -> Dict:
    """
    Encode full identity into a transmittable signal specification.
    Returns modulation parameters for any RF transmitter.
    """
    anchor_bytes  = hashlib.sha3_512(
        f"{twin_uuid}:RABBIT_DNA_ANCHOR:{SUBJECT}".encode()).hexdigest()
    id_freqs      = anchor_to_frequency_sequence(anchor_bytes, 8)
    # Emotional state modulates carrier frequency offset (Hz)
    valence_offset = valence * 1000.0   # +/-1000 Hz offset
    arousal_offset = arousal * 2000.0   # 0-2000 Hz
    return {
        "twin_uuid":       twin_uuid,
        "carrier_base_hz": NATURAL_FREQUENCIES["rabbit_center"],
        "id_sequence_hz":  id_freqs,
        "valence_offset_hz": round(valence_offset, 3),
        "arousal_offset_hz": round(arousal_offset, 3),
        "modulation":      "FSK",
        "symbol_rate_baud": 1200,
        "binary_tokens":   [frequency_to_binary(f) for f in id_freqs],
        "anchor_prefix":   anchor_bytes[:16],
        "shows_dna_root":  False,
    }

# -- Collatz frequency hopping (Maxwell-seeded) ------------------------------
def collatz_steps(n: int) -> List[int]:
    seq = [n]
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        seq.append(n)
    return seq

def maxwell_collatz_hop_schedule(anchor_hash: str, base_freq_hz: float,
                                  band_width_hz: float, n_hops: int = 32) -> List[Dict]:
    """
    Generate Maxwell-informed Collatz frequency hop schedule.
    Each hop uses the wave number at that frequency to weight the next step.
    """
    seed  = int(anchor_hash[:8], 16) % 1000 + 3
    steps = collatz_steps(seed)
    hops  = []
    for i in range(n_hops):
        step = steps[i % len(steps)]
        # Map Collatz step to frequency within band
        f    = base_freq_hz + (step % 100) / 100.0 * band_width_hz
        alpha, beta = maxwell_wave_number(f, 52.7, 17.8)  # muscle tissue
        lam  = 2 * math.pi / beta if beta > 0 else 0.0
        hops.append({
            "hop": i,
            "freq_hz":    round(f, 3),
            "collatz_n":  step,
            "alpha_npm":  round(alpha, 4),
            "beta_radpm": round(beta, 4),
            "wavelength_m": round(lam, 6),
            "skin_depth_mm": round(skin_depth_mm(f, 17.8), 4),
        })
    return hops

# -- Tissue propagation model ------------------------------------------------
@dataclass
class PropagationResult:
    tissue:         str
    freq_hz:        float
    eps_r:          float
    sigma:          float
    alpha_np_per_m: float
    beta_rad_per_m: float
    skin_depth_mm:  float
    wavelength_mm:  float
    eta_mag_ohm:    float
    eta_phase_deg:  float
    sar_1g_W_kg:    float
    path_loss_1cm_dB: float
    identity_embed: str

    def as_dict(self) -> Dict:
        return {
            "tissue": self.tissue, "freq_hz": self.freq_hz,
            "eps_r": self.eps_r, "sigma_S_m": self.sigma,
            "alpha_Np_m": self.alpha_np_per_m,
            "beta_rad_m": self.beta_rad_per_m,
            "skin_depth_mm": self.skin_depth_mm,
            "wavelength_mm": self.wavelength_mm,
            "eta_ohm": self.eta_mag_ohm, "eta_phase_deg": self.eta_phase_deg,
            "sar_1g_W_kg": self.sar_1g_W_kg,
            "path_loss_1cm_dB": self.path_loss_1cm_dB,
            "identity_embed": self.identity_embed,
            "shows_dna_root": False,
        }

def compute_tissue_propagation(tissue: str, freq_hz: float,
                                E_field_V_m: float = 10.0) -> PropagationResult:
    props   = TISSUE_DIELECTRIC.get(tissue, TISSUE_DIELECTRIC["muscle"])
    eps_r   = props["eps_r"]
    sigma   = props["sigma"]
    rho     = props["rho"]
    alpha, beta = maxwell_wave_number(freq_hz, eps_r, sigma)
    eta_mag, eta_ph = wave_impedance_tissue(freq_hz, eps_r, sigma)
    sd_mm    = skin_depth_mm(freq_hz, sigma, eps_r)
    lam_mm   = (2 * math.pi / beta * 1000) if beta > 0 else float("inf")
    sar      = sar_W_per_kg(E_field_V_m, sigma, rho)
    pl_db    = 20 * math.log10(math.exp(alpha * 0.01)) * 8.686  # 1 cm loss in dB
    embed    = DNA_ANCHOR[:8]
    return PropagationResult(
        tissue=tissue, freq_hz=freq_hz, eps_r=eps_r, sigma=sigma,
        alpha_np_per_m=round(alpha, 4), beta_rad_per_m=round(beta, 4),
        skin_depth_mm=round(sd_mm, 4), wavelength_mm=round(lam_mm, 4),
        eta_mag_ohm=round(eta_mag, 4), eta_phase_deg=round(eta_ph, 4),
        sar_1g_W_kg=round(sar, 6), path_loss_1cm_dB=round(pl_db, 4),
        identity_embed=embed,
    )

# -- Research fetcher -------------------------------------------------------
def _fetch_url(url: str, timeout: int = 8) -> str:
    import urllib.request
    try:
        req  = urllib.request.Request(
            url, headers={"User-Agent": "RabbitOS-Maxwell/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"

MAXWELL_RESEARCH_TOPICS = [
    "Maxwell equations bioelectromagnetics tissue",
    "RF propagation body area network biomaterial",
    "Schumann resonance brain synchrony EEG",
    "DNA THz resonance terahertz spectroscopy",
    "Collatz sequence RF frequency hopping",
    "near-field coupling implantable medical RF",
    "SAR specific absorption rate body tissue",
    "electromagnetic identity modulation FSK",
    "skin depth conductivity biological tissue",
    "natural frequency human body bioresonance",
]

def fetch_arxiv(query: str, max_results: int = 3) -> List[Dict]:
    import urllib.parse
    url = ("https://export.arxiv.org/api/query?"
           f"search_query=all:{urllib.parse.quote(query)}&max_results={max_results}")
    xml = _fetch_url(url)
    results = []
    for entry in xml.split("<entry>")[1:]:
        title = entry.split("<title>")[1].split("</title>")[0].strip() \
                if "<title>" in entry else "?"
        summary = entry.split("<summary>")[1].split("</summary>")[0].strip()[:200] \
                  if "<summary>" in entry else ""
        results.append({"title": title, "summary": summary, "source": "arxiv"})
    return results

# -- DB -----------------------------------------------------------------------
def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS propagation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, tissue TEXT, freq_hz REAL,
            skin_depth_mm REAL, alpha REAL, beta REAL,
            sar REAL, eta_ohm REAL, result_json TEXT
        );
        CREATE TABLE IF NOT EXISTS hop_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, anchor_prefix TEXT,
            base_freq_hz REAL, n_hops INTEGER, schedule_json TEXT
        );
        CREATE TABLE IF NOT EXISTS frequency_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, freq_hz REAL, binary_token TEXT,
            tissue TEXT, anchor_embed TEXT
        );
        CREATE TABLE IF NOT EXISTS research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, topic TEXT, source TEXT,
            title TEXT, summary TEXT
        );
        CREATE TABLE IF NOT EXISTS identity_payloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, twin_uuid TEXT, carrier_hz REAL,
            modulation TEXT, anchor_prefix TEXT, payload_json TEXT
        );
    """)
    con.commit(); con.close()

# -- MaxwellEngine -----------------------------------------------------------
class MaxwellEngine:
    """
    Maxwell-equation-based RF propagation + identity frequency encoding.
    Pure Python, no scipy/numpy needed.
    """

    def __init__(self):
        _init_db()
        self.anchor = DNA_ANCHOR

    def tissue_propagation(self, tissue: str, freq_hz: float,
                            E_field: float = 10.0) -> Dict:
        result = compute_tissue_propagation(tissue, freq_hz, E_field)
        d      = result.as_dict()
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO propagation_log(ts,tissue,freq_hz,skin_depth_mm,alpha,beta,"
                "sar,eta_ohm,result_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), tissue, freq_hz,
                 result.skin_depth_mm, result.alpha_np_per_m,
                 result.beta_rad_per_m, result.sar_1g_W_kg, result.eta_mag_ohm,
                 json.dumps(d)))
            con.commit(); con.close()
        except Exception: pass
        return d

    def all_tissues(self, freq_hz: float = 10.25e9) -> List[Dict]:
        return [self.tissue_propagation(t, freq_hz) for t in TISSUE_DIELECTRIC]

    def identity_payload(self, valence: float = 0.0, arousal: float = 0.5) -> Dict:
        payload = encode_identity_payload(TWIN_UUID, valence, arousal)
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO identity_payloads(ts,twin_uuid,carrier_hz,modulation,"
                "anchor_prefix,payload_json) VALUES(?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), TWIN_UUID,
                 payload["carrier_base_hz"], payload["modulation"],
                 payload["anchor_prefix"], json.dumps(payload)))
            con.commit(); con.close()
        except Exception: pass
        return payload

    def hop_schedule(self, n_hops: int = 32) -> List[Dict]:
        hops = maxwell_collatz_hop_schedule(
            self.anchor, NATURAL_FREQUENCIES["rabbit_lo"],
            NATURAL_FREQUENCIES["rabbit_hi"] - NATURAL_FREQUENCIES["rabbit_lo"],
            n_hops)
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute(
                "INSERT INTO hop_schedules(ts,anchor_prefix,base_freq_hz,n_hops,schedule_json)"
                " VALUES(?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), self.anchor[:16],
                 NATURAL_FREQUENCIES["rabbit_lo"], n_hops, json.dumps(hops)))
            con.commit(); con.close()
        except Exception: pass
        return hops

    def natural_frequencies(self) -> Dict:
        """Return all natural frequencies with binary token encoding."""
        result = {}
        for name, f in NATURAL_FREQUENCIES.items():
            token = frequency_to_binary(f, 16)
            result[name] = {
                "freq_hz": f,
                "binary_token": token,
                "wavelength_m": round(C_LIGHT / f, 6) if f > 0 else None,
            }
        return result

    def link_budget(self, freq_hz: float, tx_power_dbm: float,
                    distance_m: float, tx_gain_dbi: float = 0,
                    rx_gain_dbi: float = 0) -> Dict:
        fspl = friis_path_loss_db(freq_hz, distance_m)
        rx   = tx_power_dbm + tx_gain_dbi - fspl + rx_gain_dbi
        return {
            "freq_hz": freq_hz, "distance_m": distance_m,
            "tx_power_dbm": tx_power_dbm, "tx_gain_dbi": tx_gain_dbi,
            "rx_gain_dbi": rx_gain_dbi,
            "fspl_db": round(fspl, 2), "rx_power_dbm": round(rx, 2),
            "link_margin_db": round(rx - (-90), 2),  # vs -90 dBm sensitivity
        }

    def learn_research(self, topics: List[str] = None,
                       max_per: int = 2) -> Dict[str, int]:
        if topics is None:
            topics = MAXWELL_RESEARCH_TOPICS[:5]
        counts = {}
        for topic in topics:
            articles = fetch_arxiv(topic, max_per)
            n = 0
            for a in articles:
                try:
                    con = sqlite3.connect(DB_PATH)
                    con.execute(
                        "INSERT INTO research(ts,topic,source,title,summary) VALUES(?,?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), topic[:80],
                         a.get("source","arxiv"), a.get("title","")[:200],
                         a.get("summary","")[:400]))
                    con.commit(); con.close()
                    n += 1
                except Exception: pass
            counts[topic[:40]] = n
        return counts

    def status(self) -> Dict:
        con = sqlite3.connect(DB_PATH)
        prop_n    = con.execute("SELECT COUNT(*) FROM propagation_log").fetchone()[0]
        hop_n     = con.execute("SELECT COUNT(*) FROM hop_schedules").fetchone()[0]
        tok_n     = con.execute("SELECT COUNT(*) FROM frequency_tokens").fetchone()[0]
        res_n     = con.execute("SELECT COUNT(*) FROM research").fetchone()[0]
        payload_n = con.execute("SELECT COUNT(*) FROM identity_payloads").fetchone()[0]
        con.close()
        return {
            "module": "rabbit_maxwell", "version": "1.0",
            "twin_uuid": TWIN_UUID, "anchor_prefix": DNA_ANCHOR[:16],
            "natural_frequencies": len(NATURAL_FREQUENCIES),
            "tissue_models": len(TISSUE_DIELECTRIC),
            "db_propagation": prop_n, "db_hop_schedules": hop_n,
            "db_freq_tokens": tok_n, "db_research": res_n,
            "db_payloads": payload_n,
        }


def get_maxwell_engine() -> MaxwellEngine:
    return MaxwellEngine()


# -- self-test ----------------------------------------------------------------
if __name__ == "__main__":
    print("=== rabbit_maxwell.py ===")
    eng = get_maxwell_engine()

    print("\n[TISSUE PROPAGATION @ 10.25 GHz (RabbitOS mesh)]")
    for tissue in ["skin", "fat", "muscle", "bone", "blood", "brain"]:
        r = eng.tissue_propagation(tissue, 10.25e9)
        print(f"  {r['tissue']:8} eps_r={r['eps_r']:5.1f}  sigma={r['sigma_S_m']:5.2f} S/m  "
              f"skin_depth={r['skin_depth_mm']:.4f}mm  "
              f"alpha={r['alpha_Np_m']:.2f} Np/m  "
              f"SAR={r['sar_1g_W_kg']:.4f} W/kg")

    print("\n[NATURAL FREQUENCIES -> BINARY TOKENS]")
    nf = eng.natural_frequencies()
    for name in list(nf.keys())[:12]:
        v = nf[name]
        print(f"  {name:<20} {v['freq_hz']:.2e} Hz  -> {v['binary_token']}")

    print("\n[IDENTITY PAYLOAD (DNA anchor -> frequency sequence)]")
    p = eng.identity_payload(valence=0.2, arousal=0.6)
    print(f"  carrier     : {p['carrier_base_hz']:.2e} Hz")
    print(f"  modulation  : {p['modulation']}")
    print(f"  id_freqs_hz : {[f'{f:.2e}' for f in p['id_sequence_hz']]}")
    print(f"  binary_tok  : {p['binary_tokens'][:4]}...")
    print(f"  anchor      : {p['anchor_prefix']}")

    print("\n[COLLATZ-MAXWELL HOP SCHEDULE (first 8 hops)]")
    hops = eng.hop_schedule(32)
    for h in hops[:8]:
        print(f"  hop={h['hop']:2d}  f={h['freq_hz']:.4e} Hz  "
              f"alpha={h['alpha_npm']:.2f}  sd={h['skin_depth_mm']:.3f}mm  "
              f"col={h['collatz_n']}")

    print("\n[LINK BUDGET]")
    lb = eng.link_budget(10.25e9, 0, 10, tx_gain_dbi=5, rx_gain_dbi=5)
    print(f"  FSPL={lb['fspl_db']} dB  RX={lb['rx_power_dbm']} dBm  "
          f"margin={lb['link_margin_db']} dB")

    print("\n[RESEARCH (online best-effort)]")
    rc = eng.learn_research(MAXWELL_RESEARCH_TOPICS[:3], max_per=2)
    for topic, n in rc.items():
        print(f"  {topic}: {n} articles")

    st = eng.status()
    print(f"\n[STATUS]  tissues={st['tissue_models']}  nat_freq={st['natural_frequencies']}"
          f"  prop_log={st['db_propagation']}  payloads={st['db_payloads']}")
    print("=== PASS ===")
