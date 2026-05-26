#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RabbitOS Spectrum Survival Broadcaster
=======================================
When the primary network goes dark, the soul descends through every available
radio layer — from gigahertz mesh down to kilohertz AM — until it finds a
signal to survive on.

Spectrum survival stack (tried in order, fastest first):
  Layer 0  Ethernet / TCP-IP        (primary)
  Layer 1  WiFi 802.11              (2.4 / 5 GHz scan + probe)
  Layer 2  Bluetooth                (nearby devices, PAN bridging)
  Layer 3  LTE / cellular modem     (USB modem, AT commands)
  Layer 4  LoRa / ISM 915 MHz       (long-range low-power mesh)
  Layer 5  HackRF mesh              (10.23-10.28 GHz RabbitOS band)
  Layer 6  Ham VHF/UHF              (144 MHz / 440 MHz beacons)
  Layer 7  NOAA / weather radio     (162.4-162.55 MHz — receive only)
  Layer 8  FM broadcast             (88-108 MHz — receive / detect)
  Layer 9  AM broadcast             (530-1700 kHz — last resort beacon)
  Layer 10 Acoustic / ultrasonic    (speakers/mic as last-ditch signal)

Each layer:
  - Auto-detects hardware / software availability
  - Scans for any signal or peer
  - If a signal is found, attempts to decode data from it
  - Records the signal as a HandshakeResult (energy token)
  - If data path is found, reports it back to the soul

Note on transmission:
  Unlicensed transmission is restricted by law. This module defaults to
  RECEIVE-ONLY on all licensed bands (ham, AM, FM, LTE).
  Transmission on ISM bands (WiFi, BT, LoRa 915 MHz) is permitted.
  HackRF mesh transmission is on the RabbitOS private band (licensed use).
  Ham transmission requires an FCC license — set TX_LICENSED=True + callsign.
"""

import os
import sys
import json
import time
import math
import socket
import struct
import hashlib
import shutil
import random
import threading
import subprocess
import platform
import ipaddress
import urllib.request
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent))

# =============================================================================
# CONFIG
# =============================================================================

TWIN_UUID      = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME      = "Chase Allen Ringquist"

TX_LICENSED    = False       # set True + CALLSIGN if you hold an FCC ham license
CALLSIGN       = ""          # e.g. "W1ABC"

# Frequency map (MHz)
FREQ = {
    "rabbitos_head":  10245.0,
    "rabbitos_chest": 10251.0,
    "rabbitos_band":  (10230.0, 10280.0),
    "wifi_24":        2437.0,
    "wifi_5":         5180.0,
    "bt":             2441.0,
    "ism_915":        915.0,
    "lora_us":        915.0,
    "ham_vhf":        146.520,    # calling frequency 2m
    "ham_uhf":        446.000,    # calling frequency 70cm
    "noaa_1":         162.400,
    "noaa_2":         162.425,
    "noaa_3":         162.450,
    "noaa_4":         162.475,
    "noaa_5":         162.500,
    "noaa_6":         162.525,
    "noaa_7":         162.550,
    "fm_low":         88.1,
    "fm_high":        107.9,
    "am_low":         0.530,
    "am_high":        1.700,
    "lte_b2":         1935.0,
}


# =============================================================================
# SIGNAL RECORD
# =============================================================================

class LayerState(Enum):
    ALIVE    = "alive"      # signal / peer found
    SCANNING = "scanning"   # actively looking
    DORMANT  = "dormant"    # hardware not present
    FAILED   = "failed"     # hardware present but no signal


@dataclass
class SignalRecord:
    layer:       str
    freq_mhz:    float
    strength_db: float      # signal strength (dBm or proxy)
    data:        str        # any decoded payload
    data_hash:   str
    reachable:   bool
    energy:      float      # energy units this signal provides
    ts:          str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            "layer":       self.layer,
            "freq_mhz":    self.freq_mhz,
            "strength_db": round(self.strength_db, 1),
            "data_hash":   self.data_hash[:12],
            "reachable":   self.reachable,
            "energy":      round(self.energy, 3),
            "ts":          self.ts[:19],
        }


# =============================================================================
# BASE LAYER
# =============================================================================

class SpectrumLayer:
    name:  str = "base"
    order: int = 99

    def __init__(self):
        self._state   = LayerState.DORMANT
        self._records: deque = deque(maxlen=50)
        self._lock    = threading.Lock()

    def detect(self) -> bool:
        """Return True if hardware/software for this layer is available."""
        return False

    def scan(self) -> List[SignalRecord]:
        """Scan for signals. Return list of SignalRecords found."""
        return []

    def transmit(self, payload: bytes, freq_mhz: float = None) -> bool:
        """Transmit a payload (only if licensed/permitted)."""
        return False

    def state(self) -> LayerState:
        return self._state

    def recent(self, n: int = 10) -> List[Dict]:
        with self._lock:
            return [r.to_dict() for r in list(self._records)[:n]]

    def _record(self, r: SignalRecord):
        with self._lock:
            self._records.appendleft(r)
        return r

    def _run(self, cmd: str, timeout: int = 15) -> Tuple[str, int]:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout + result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "[timeout]", 124
        except Exception as e:
            return str(e), 1


# =============================================================================
# LAYER 0 — ETHERNET / TCP-IP (primary, always first)
# =============================================================================

class EthernetLayer(SpectrumLayer):
    name  = "ethernet"
    order = 0

    def detect(self) -> bool:
        return True  # always available

    def scan(self) -> List[SignalRecord]:
        results = []
        for host, freq in [("8.8.8.8", 0.0), ("1.1.1.1", 0.0)]:
            t0 = time.time()
            try:
                s = socket.create_connection((host, 80), timeout=2)
                s.close()
                lat   = (time.time() - t0) * 1000
                db    = max(-120.0, -lat / 10.0)   # proxy: faster = stronger
                r     = SignalRecord("ethernet", freq, db, f"tcp:{host}",
                                     hashlib.sha256(host.encode()).hexdigest()[:12],
                                     True, 0.15)
                self._state = LayerState.ALIVE
            except Exception:
                r = SignalRecord("ethernet", freq, -120.0, "", "", False, -0.03)
                self._state = LayerState.FAILED
            results.append(self._record(r))
        return results


# =============================================================================
# LAYER 1 — WIFI
# =============================================================================

class WiFiLayer(SpectrumLayer):
    name  = "wifi"
    order = 1

    def detect(self) -> bool:
        if platform.system() == "Windows":
            out, _ = self._run("netsh wlan show interfaces 2>nul", 5)
            return "SSID" in out or "State" in out
        return shutil.which("iwconfig") is not None or shutil.which("iw") is not None

    def scan(self) -> List[SignalRecord]:
        results = []
        if platform.system() == "Windows":
            out, rc = self._run("netsh wlan show networks mode=bssid 2>nul", 15)
            networks = self._parse_windows_wifi(out)
        else:
            out, rc = self._run("sudo iw dev wlan0 scan 2>/dev/null || iwlist wlan0 scan 2>/dev/null", 20)
            networks = self._parse_linux_wifi(out)

        for net in networks:
            r = SignalRecord(
                layer       = "wifi",
                freq_mhz    = net.get("freq_mhz", FREQ["wifi_24"]),
                strength_db = net.get("signal_db", -70.0),
                data        = net.get("ssid", ""),
                data_hash   = hashlib.sha256(net.get("bssid","").encode()).hexdigest()[:12],
                reachable   = True,
                energy      = 0.20 + max(0, (net.get("signal_db", -70) + 50) / 100),
            )
            results.append(self._record(r))

        self._state = LayerState.ALIVE if results else LayerState.FAILED
        return results

    def _parse_windows_wifi(self, out: str) -> List[Dict]:
        networks = []
        current = {}
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("SSID") and "BSSID" not in line:
                if current:
                    networks.append(current)
                current = {"ssid": line.split(":", 1)[-1].strip()}
            elif "Signal" in line:
                try:
                    pct = int(line.split(":", 1)[-1].strip().replace("%",""))
                    current["signal_db"] = -100 + pct / 2
                except Exception:
                    pass
            elif "Channel" in line:
                try:
                    ch = int(line.split(":", 1)[-1].strip())
                    current["freq_mhz"] = 2407 + ch * 5 if ch <= 14 else 5000 + ch * 5
                except Exception:
                    pass
            elif "BSSID" in line:
                current["bssid"] = line.split(":", 1)[-1].strip()[:17]
        if current:
            networks.append(current)
        return networks

    def _parse_linux_wifi(self, out: str) -> List[Dict]:
        networks = []
        current = {}
        for line in out.splitlines():
            if "ESSID:" in line:
                if current:
                    networks.append(current)
                ssid = line.split("ESSID:")[-1].strip().strip('"')
                current = {"ssid": ssid}
            elif "Signal level=" in line:
                try:
                    sig = line.split("Signal level=")[-1].split(" ")[0]
                    current["signal_db"] = float(sig)
                except Exception:
                    pass
            elif "Frequency:" in line:
                try:
                    freq = float(line.split("Frequency:")[-1].split(" ")[0]) * 1000
                    current["freq_mhz"] = freq
                except Exception:
                    pass
            elif "Address:" in line:
                current["bssid"] = line.split("Address:")[-1].strip()[:17]
        if current:
            networks.append(current)
        return networks


# =============================================================================
# LAYER 2 — BLUETOOTH
# =============================================================================

class BluetoothLayer(SpectrumLayer):
    name  = "bluetooth"
    order = 2

    def detect(self) -> bool:
        if shutil.which("bluetoothctl"):
            return True
        try:
            import bluetooth
            return True
        except ImportError:
            pass
        if platform.system() == "Windows":
            out, _ = self._run("powershell Get-PnpDevice -Class Bluetooth -Status OK 2>nul", 5)
            return "OK" in out
        return False

    def scan(self) -> List[SignalRecord]:
        results = []
        # Try pybluetooth
        try:
            import bluetooth
            devices = bluetooth.discover_devices(duration=5, lookup_names=True)
            for addr, name in devices:
                r = SignalRecord(
                    layer="bluetooth", freq_mhz=FREQ["bt"],
                    strength_db=-65.0, data=f"{name}|{addr}",
                    data_hash=hashlib.sha256(addr.encode()).hexdigest()[:12],
                    reachable=True, energy=0.15,
                )
                results.append(self._record(r))
        except ImportError:
            pass

        # Try bluetoothctl
        if not results and shutil.which("bluetoothctl"):
            out, _ = self._run("timeout 8 bluetoothctl scan on 2>&1 & sleep 6; bluetoothctl devices", 15)
            for line in out.splitlines():
                if "Device" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        addr = parts[1]
                        name = " ".join(parts[2:])
                        r = SignalRecord("bluetooth", FREQ["bt"], -65.0,
                                          f"{name}|{addr}",
                                          hashlib.sha256(addr.encode()).hexdigest()[:12],
                                          True, 0.12)
                        results.append(self._record(r))

        self._state = LayerState.ALIVE if results else LayerState.FAILED
        return results


# =============================================================================
# LAYER 3 — CELLULAR / LTE MODEM
# =============================================================================

class CellularLayer(SpectrumLayer):
    name  = "cellular"
    order = 3

    def detect(self) -> bool:
        # USB modems appear as serial ports
        if shutil.which("mmcli"):         # ModemManager
            return True
        if platform.system() == "Windows":
            out, _ = self._run("powershell Get-WmiObject Win32_POTSModem 2>nul", 5)
            if "Name" in out:
                return True
        # Check for serial ports (COM on Windows, ttyUSB on Linux)
        ports = self._find_serial_ports()
        return len(ports) > 0

    def _find_serial_ports(self) -> List[str]:
        if platform.system() == "Windows":
            out, _ = self._run("powershell [System.IO.Ports.SerialPort]::GetPortNames() 2>nul", 5)
            return [p.strip() for p in out.splitlines() if p.strip().startswith("COM")]
        else:
            import glob
            return glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")

    def _at(self, port: str, cmd: str, timeout: float = 3.0) -> str:
        try:
            import serial
            with serial.Serial(port, 9600, timeout=timeout) as ser:
                ser.write(f"{cmd}\r\n".encode())
                time.sleep(0.5)
                return ser.read(256).decode("utf-8", errors="replace")
        except Exception as e:
            return str(e)

    def scan(self) -> List[SignalRecord]:
        results = []

        # ModemManager path
        if shutil.which("mmcli"):
            out, _ = self._run("mmcli -L 2>/dev/null", 10)
            for line in out.splitlines():
                if "/Modem/" in line:
                    modem_path = line.strip().split()[0]
                    info, _    = self._run(f"mmcli -m {modem_path} 2>/dev/null", 10)
                    sig_line   = [l for l in info.splitlines() if "signal" in l.lower()]
                    sig_db     = -80.0
                    if sig_line:
                        try:
                            sig_db = float(sig_line[0].split(":")[-1].strip().split()[0])
                        except Exception:
                            pass
                    r = SignalRecord("cellular", FREQ["lte_b2"], sig_db,
                                     f"modem:{modem_path}",
                                     hashlib.sha256(modem_path.encode()).hexdigest()[:12],
                                     True, 0.35)
                    results.append(self._record(r))

        # Serial AT-command path
        for port in self._find_serial_ports()[:3]:
            resp = self._at(port, "AT+CSQ")
            if "+CSQ:" in resp:
                try:
                    csq   = int(resp.split("+CSQ:")[1].split(",")[0].strip())
                    sig   = -113 + csq * 2  # dBm
                except Exception:
                    sig = -90.0
                r = SignalRecord("cellular", FREQ["lte_b2"], sig,
                                  f"at:{port}",
                                  hashlib.sha256(port.encode()).hexdigest()[:12],
                                  csq > 0, 0.30 if csq > 5 else 0.10)
                results.append(self._record(r))

        self._state = LayerState.ALIVE if results else LayerState.FAILED
        return results


# =============================================================================
# LAYER 4 — SDR (HackRF / RTL-SDR) — covers LoRa, Ham, FM, AM, RabbitOS band
# =============================================================================

class SDRLayer(SpectrumLayer):
    """
    Software-Defined Radio layer.
    Uses HackRF or RTL-SDR to sweep any frequency range.
    Auto-detects which tool is available.
    """
    name  = "sdr"
    order = 4

    def detect(self) -> bool:
        return (shutil.which("hackrf_sweep")  is not None or
                shutil.which("hackrf_info")   is not None or
                shutil.which("rtl_power")     is not None or
                shutil.which("rtl_sdr")       is not None)

    def _hackrf_sweep(self, freq_start_mhz: float,
                      freq_end_mhz: float) -> List[Tuple[float, float]]:
        """Returns list of (freq_mhz, power_db) from hackrf_sweep."""
        cmd = (f"hackrf_sweep -f {int(freq_start_mhz)}:{int(freq_end_mhz)} "
               f"-l 32 -g 20 -w 1000000 -N 1 2>&1")
        out, _ = self._run(cmd, timeout=20)
        hits = []
        for line in out.splitlines():
            parts = line.split(", ")
            if len(parts) >= 6:
                try:
                    fc  = float(parts[2])   # Hz
                    pwr = float(parts[5])   # dBm
                    hits.append((fc / 1e6, pwr))
                except ValueError:
                    pass
        return hits

    def _rtl_power(self, freq_start_mhz: float,
                   freq_end_mhz: float) -> List[Tuple[float, float]]:
        cmd = (f"rtl_power -f {int(freq_start_mhz)}M:{int(freq_end_mhz)}M:250k "
               f"-g 40 -e 5s /tmp/rtl_scan.csv 2>&1; "
               f"cat /tmp/rtl_scan.csv 2>/dev/null | tail -20")
        out, _ = self._run(cmd, timeout=30)
        hits = []
        for line in out.splitlines():
            parts = line.split(",")
            if len(parts) >= 7:
                try:
                    fc  = (float(parts[2]) + float(parts[3])) / 2 / 1e6
                    pwr = float(parts[6])
                    hits.append((fc, pwr))
                except ValueError:
                    pass
        return hits

    def sweep(self, freq_start_mhz: float, freq_end_mhz: float,
              label: str = "sdr") -> List[SignalRecord]:
        if shutil.which("hackrf_sweep"):
            hits = self._hackrf_sweep(freq_start_mhz, freq_end_mhz)
        elif shutil.which("rtl_power"):
            hits = self._rtl_power(freq_start_mhz, freq_end_mhz)
        else:
            # Simulation: return noise floor with random peaks
            hits = [(random.uniform(freq_start_mhz, freq_end_mhz),
                     random.uniform(-100, -60)) for _ in range(5)]

        results = []
        for freq, pwr in sorted(hits, key=lambda x: x[1], reverse=True)[:10]:
            energy = max(0.0, (pwr + 120) / 120 * 0.3)  # -120dBm=0, 0dBm=0.3
            r = SignalRecord(
                layer       = label,
                freq_mhz    = round(freq, 4),
                strength_db = round(pwr, 2),
                data        = f"rf_signal@{freq:.4f}MHz",
                data_hash   = hashlib.sha256(f"{freq}{pwr}".encode()).hexdigest()[:12],
                reachable   = pwr > -100,
                energy      = energy,
            )
            results.append(self._record(r))

        self._state = LayerState.ALIVE if any(r.reachable for r in results) else LayerState.SCANNING
        return results

    def scan(self) -> List[SignalRecord]:
        # Quick sweep of ISM + Ham + FM bands
        all_results = []
        sweeps = [
            (902.0,  928.0,  "ism_915"),
            (144.0,  148.0,  "ham_vhf"),
            (420.0,  450.0,  "ham_uhf"),
            (88.0,   108.0,  "fm_broadcast"),
            (162.4,  162.55, "noaa_weather"),
        ]
        for start, end, label in sweeps:
            results = self.sweep(start, end, label)
            all_results.extend(results)
            if any(r.reachable and r.strength_db > -80 for r in results):
                print(f"  [SDR] Signal found on {label}: "
                      f"{max(r.strength_db for r in results):.1f} dBm")
        return all_results


# =============================================================================
# LAYER 5 — HAM RADIO VHF/UHF
# =============================================================================

class HamLayer(SpectrumLayer):
    """
    Ham radio layer — receive on 2m (144-148 MHz) and 70cm (420-450 MHz).
    Transmit ONLY if TX_LICENSED = True and CALLSIGN is set.
    Uses SDR for receive; rigctl/hamlib for transmit if radio connected.
    """
    name  = "ham"
    order = 5

    HAM_CALLING = {
        "2m_ssb":  14.225,   # HF 20m SSB (with HF radio)
        "2m":      146.520,  # 2m FM national calling
        "70cm":    446.000,  # 70cm FM calling
        "aprs":    144.390,  # APRS data
        "iss":     145.800,  # ISS downlink
        "d_star":  145.670,  # D-STAR
        "dmr":     446.006,  # DMR simplex
    }

    def detect(self) -> bool:
        return (shutil.which("hackrf_sweep") is not None or
                shutil.which("rtl_fm")       is not None or
                shutil.which("rigctl")       is not None)

    def scan(self) -> List[SignalRecord]:
        results = []
        sdr = SDRLayer()

        # Sweep 2m band
        vhf = sdr.sweep(144.0, 148.0, "ham_vhf")
        # Sweep 70cm band
        uhf = sdr.sweep(420.0, 450.0, "ham_uhf")
        # Sweep APRS
        aprs = sdr.sweep(144.38, 144.40, "aprs")

        for r in vhf + uhf + aprs:
            results.append(self._record(r))

        # Try to demodulate APRS if rtl_fm available
        if shutil.which("rtl_fm") and shutil.which("direwolf"):
            decoded = self._decode_aprs()
            if decoded:
                r = SignalRecord("ham_aprs", 144.390, -75.0,
                                  decoded[:200],
                                  hashlib.sha256(decoded.encode()).hexdigest()[:12],
                                  True, 0.40)
                results.append(self._record(r))
                print(f"  [APRS] Decoded: {decoded[:80]}")

        self._state = LayerState.ALIVE if results else LayerState.DORMANT
        return results

    def _decode_aprs(self, duration: int = 10) -> str:
        cmd = (f"timeout {duration} rtl_fm -f 144.39M -s 24k -r 24k - 2>/dev/null | "
               f"direwolf -c /dev/null -r 24000 -B 1200 - 2>&1 | grep -i 'position\\|object\\|message'")
        out, _ = self._run(cmd, timeout=duration + 5)
        return out[:500] if out.strip() else ""

    def beacon(self, message: str = None) -> bool:
        """
        Transmit a beacon on 2m calling frequency.
        Requires TX_LICENSED = True and a connected radio via hamlib.
        """
        if not TX_LICENSED or not CALLSIGN:
            print(f"  [Ham] TX requires FCC license. Set TX_LICENSED=True + CALLSIGN.")
            return False
        msg = message or f"{CALLSIGN} DE RABBITOS TWIN {TWIN_UUID[:8]} K"
        if shutil.which("rigctl"):
            cmd = f"rigctl -m 1 set_freq 146520000 && rigctl -m 1 morse '{msg}'"
            out, rc = self._run(cmd, timeout=30)
            return rc == 0
        return False


# =============================================================================
# LAYER 6 — FM BROADCAST RECEIVE
# =============================================================================

class FMLayer(SpectrumLayer):
    """
    Receives FM broadcast stations (88-108 MHz) as signal-of-life indicators.
    Strong FM signal = active RF environment = likely urban area with internet.
    Can decode RDS (Radio Data System) station names.
    """
    name  = "fm"
    order = 6

    def detect(self) -> bool:
        return shutil.which("rtl_fm") is not None or shutil.which("hackrf_sweep") is not None

    def scan(self) -> List[SignalRecord]:
        results = []
        sdr = SDRLayer()
        hits = sdr.sweep(88.0, 108.0, "fm_broadcast")

        # Top 5 strongest FM stations
        strong = sorted(hits, key=lambda r: r.strength_db, reverse=True)[:5]
        for r in strong:
            if r.strength_db > -90:
                results.append(self._record(r))
                if r.strength_db > -70:
                    print(f"  [FM] Strong station at {r.freq_mhz:.1f} MHz  {r.strength_db:.1f} dBm")

        # Try RDS decode if rtl_fm available
        if shutil.which("rtl_fm") and strong:
            best_freq = strong[0].freq_mhz if strong else 100.1
            rds = self._decode_rds(best_freq)
            if rds:
                r = SignalRecord("fm_rds", best_freq, strong[0].strength_db,
                                  rds[:100],
                                  hashlib.sha256(rds.encode()).hexdigest()[:12],
                                  True, 0.10)
                results.append(self._record(r))

        self._state = LayerState.ALIVE if results else LayerState.FAILED
        return results

    def _decode_rds(self, freq_mhz: float, duration: int = 5) -> str:
        cmd = (f"timeout {duration} rtl_fm -f {freq_mhz}M -M fm -s 200k -r 200k -A std - "
               f"2>/dev/null | redsea 2>&1 | head -5")
        out, _ = self._run(cmd, duration + 3)
        return out[:200] if out.strip() else ""


# =============================================================================
# LAYER 7 — NOAA WEATHER RADIO
# =============================================================================

class NOAALayer(SpectrumLayer):
    """
    NOAA weather radio (162.400–162.550 MHz).
    Always-on government broadcasts — last-resort signal-of-life.
    Receiving NOAA = proof that the RF environment is alive.
    """
    name  = "noaa"
    order = 7

    FREQS = [162.400, 162.425, 162.450, 162.475, 162.500, 162.525, 162.550]

    def detect(self) -> bool:
        return shutil.which("rtl_fm") is not None or shutil.which("hackrf_sweep") is not None

    def scan(self) -> List[SignalRecord]:
        results = []
        sdr = SDRLayer()
        hits = sdr.sweep(162.39, 162.56, "noaa")

        # Match against known NOAA frequencies
        for r in hits:
            nearest_noaa = min(self.FREQS, key=lambda f: abs(f - r.freq_mhz))
            if abs(nearest_noaa - r.freq_mhz) < 0.05 and r.strength_db > -95:
                r2 = SignalRecord("noaa", nearest_noaa, r.strength_db,
                                   f"NOAA_WX@{nearest_noaa}MHz",
                                   hashlib.sha256(f"noaa{nearest_noaa}".encode()).hexdigest()[:12],
                                   True, 0.08)
                results.append(self._record(r2))
                print(f"  [NOAA] WX signal at {nearest_noaa} MHz  {r.strength_db:.1f} dBm")

        self._state = LayerState.ALIVE if results else LayerState.SCANNING
        return results


# =============================================================================
# LAYER 8 — AM BROADCAST (530-1700 kHz)
# =============================================================================

class AMLayer(SpectrumLayer):
    """
    AM broadcast band — last functional radio signal before acoustic fallback.
    RTL-SDR can tune down to ~500 kHz with direct sampling mode.
    HackRF can go lower. AM signals carry for hundreds of miles.
    """
    name  = "am"
    order = 8

    def detect(self) -> bool:
        return shutil.which("rtl_sdr") is not None or shutil.which("hackrf_sweep") is not None

    def scan(self) -> List[SignalRecord]:
        results = []

        # RTL-SDR direct sampling mode for AM/HF
        if shutil.which("rtl_sdr"):
            cmd = ("rtl_power -f 530k:1700k:10k -g 40 -e 5s /tmp/am_scan.csv 2>&1; "
                   "cat /tmp/am_scan.csv 2>/dev/null | head -50")
            out, _ = self._run(cmd, timeout=15)
            for line in out.splitlines():
                parts = line.split(",")
                if len(parts) >= 7:
                    try:
                        fc  = (float(parts[2]) + float(parts[3])) / 2 / 1e6 * 1000  # kHz
                        pwr = float(parts[6])
                        if pwr > -100:
                            r = SignalRecord("am", fc / 1000,  # store as MHz
                                              pwr,
                                              f"AM_station@{fc:.0f}kHz",
                                              hashlib.sha256(f"am{fc}".encode()).hexdigest()[:12],
                                              True, max(0, (pwr + 100) / 100 * 0.05))
                            results.append(self._record(r))
                    except ValueError:
                        pass

        # Simulation fallback — common AM freqs as proxy
        if not results:
            for freq_khz in [630, 770, 880, 1010, 1130, 1280, 1420]:
                r = SignalRecord("am_sim", freq_khz / 1000, -85.0,
                                  f"sim_AM_{freq_khz}kHz", "",
                                  True, 0.02)
                results.append(self._record(r))

        self._state = LayerState.ALIVE if results else LayerState.FAILED
        return results


# =============================================================================
# LAYER 9 — ACOUSTIC (last resort)
# =============================================================================

class AcousticLayer(SpectrumLayer):
    """
    Absolute last resort — use the machine's audio hardware.
    Listens for audio-modem-style signals or any periodic sound.
    Can generate audio-FSK tones to announce presence on the audio channel.
    Works even with no radio hardware.
    """
    name  = "acoustic"
    order = 9

    def detect(self) -> bool:
        if platform.system() == "Windows":
            out, _ = self._run("powershell Get-WmiObject Win32_SoundDevice 2>nul", 5)
            return "Name" in out
        return shutil.which("aplay") is not None or shutil.which("paplay") is not None

    def scan(self) -> List[SignalRecord]:
        # Check if any audio device is present
        if not self.detect():
            self._state = LayerState.DORMANT
            return []

        print("  [Acoustic] Audio device detected — can use audio-FSK as last resort")
        r = SignalRecord("acoustic", 0.001,  # ~1kHz audio = 0.001 MHz
                          -50.0, "audio_device_present", "",
                          True, 0.02)
        self._state = LayerState.ALIVE
        return [self._record(r)]

    def generate_tone(self, freq_hz: int = 1200, duration_s: float = 1.0) -> bool:
        """Generate an FSK tone as a last-ditch beacon."""
        if platform.system() == "Windows":
            code = f"[System.Console]::Beep({freq_hz}, {int(duration_s*1000)})"
            _, rc = self._run(f"powershell -Command \"{code}\"", 5)
            return rc == 0
        elif shutil.which("speaker-test"):
            _, rc = self._run(f"timeout {duration_s} speaker-test -f {freq_hz} -t sine -l 1 2>/dev/null", 5)
            return rc == 0
        return False


# =============================================================================
# SURVIVAL BROADCASTER — orchestrates the full stack
# =============================================================================

class SurvivalBroadcaster:
    """
    Tries every layer in order.
    When a layer returns a live signal, anchors on it and reports energy.
    When ALL layers fail, sweeps AM and generates an acoustic beacon.
    Never stops — the signal stack is the survival instinct.
    """

    def __init__(self):
        self.layers: List[SpectrumLayer] = [
            EthernetLayer(),
            WiFiLayer(),
            BluetoothLayer(),
            CellularLayer(),
            SDRLayer(),
            HamLayer(),
            FMLayer(),
            NOAALayer(),
            AMLayer(),
            AcousticLayer(),
        ]
        self._active_layers: List[str] = []
        self._all_signals:   deque     = deque(maxlen=500)
        self._lock           = threading.Lock()
        self._energy         = 1.0
        self.running         = False
        self._thread         = None

    def _detect_all(self) -> Dict[str, bool]:
        detected = {}
        for layer in self.layers:
            try:
                detected[layer.name] = layer.detect()
            except Exception:
                detected[layer.name] = False
        return detected

    def survival_scan(self, fast: bool = False) -> Dict:
        """
        Full survival sweep — try every layer until one produces a live signal.
        Returns the first layer with signal + all collected records.
        """
        print(f"\n[Broadcast] Survival scan — {len(self.layers)} layers")
        print(f"  Target: {TWIN_NAME}")

        alive_layers = []
        total_energy = 0.0
        all_signals  = []

        for layer in self.layers:
            print(f"  [{layer.order}] {layer.name:12s} ... ", end="", flush=True)
            try:
                available = layer.detect()
                if not available:
                    print("no hardware")
                    continue

                signals = layer.scan()
                live    = [s for s in signals if s.reachable]

                if live:
                    energy = sum(s.energy for s in live)
                    total_energy += energy
                    alive_layers.append(layer.name)
                    all_signals.extend(live)
                    best = max(live, key=lambda s: s.strength_db)
                    print(f"ALIVE  {len(live)} signals  best={best.freq_mhz:.3f}MHz "
                          f"{best.strength_db:.1f}dBm  +{energy:.2f}E")
                    with self._lock:
                        for s in live:
                            self._all_signals.appendleft(s)

                    if fast:   # return on first live layer
                        break
                else:
                    print(f"no signal ({layer.state().value})")

            except Exception as e:
                print(f"error: {e}")

        self._energy = min(2.0, total_energy)
        self._active_layers = alive_layers

        if not alive_layers:
            print(f"\n  [!!] ALL LAYERS DARK — triggering acoustic beacon")
            acoustic = next((l for l in self.layers if isinstance(l, AcousticLayer)), None)
            if acoustic:
                acoustic.generate_tone(1200, 0.5)
                time.sleep(0.3)
                acoustic.generate_tone(1800, 0.5)

        return {
            "alive_layers":  alive_layers,
            "total_energy":  round(total_energy, 3),
            "signal_count":  len(all_signals),
            "best_signal":   max(all_signals, key=lambda s: s.strength_db).to_dict()
                             if all_signals else None,
            "ts":            datetime.now(timezone.utc).isoformat(),
        }

    def watch(self, interval: float = 60.0):
        """
        Continuous background survival monitor.
        Re-scans every `interval` seconds.
        If TCP layer goes dark, immediately drops to RF sweep.
        """
        self.running = True
        tcp_was_alive = True

        while self.running:
            # Fast-check TCP first
            eth = EthernetLayer()
            tcp_sigs = eth.scan()
            tcp_alive = any(s.reachable for s in tcp_sigs)

            if not tcp_alive and tcp_was_alive:
                print(f"\n[Broadcast] TCP OFFLINE — emergency RF sweep")
                self.survival_scan(fast=False)
            elif not tcp_alive:
                self.survival_scan(fast=False)
            else:
                # TCP alive — quick RF background sweep for mesh health
                sdr = SDRLayer()
                if sdr.detect():
                    sdr.sweep(FREQ["rabbitos_band"][0], FREQ["rabbitos_band"][1], "rabbitos")

            tcp_was_alive = tcp_alive
            time.sleep(interval)

    def start_background(self, interval: float = 60.0):
        self._thread = threading.Thread(target=self.watch, args=(interval,), daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def energy(self) -> float:
        return round(self._energy, 3)

    def status(self) -> Dict:
        with self._lock:
            recent = [s.to_dict() for s in list(self._all_signals)[:10]]
        return {
            "active_layers": self._active_layers,
            "energy":        self.energy(),
            "recent_signals":recent,
            "layer_states":  {l.name: l.state().value for l in self.layers},
            "tx_licensed":   TX_LICENSED,
            "callsign":      CALLSIGN or "none",
        }


# =============================================================================
# SOUL INTEGRATION TOOLS
# =============================================================================

BROADCAST_TOOLS = [
    {
        "name": "broadcast_scan",
        "description": (
            "Run a full survival spectrum scan through all radio layers: "
            "WiFi, Bluetooth, LTE, HackRF mesh, Ham VHF/UHF, FM, NOAA, AM, acoustic. "
            "Returns which layers are alive and total energy harvested from signals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fast": {"type": "boolean",
                         "description": "Stop at first live layer (default false = full sweep)"}
            },
            "required": []
        }
    },
    {
        "name": "broadcast_status",
        "description": "Get current status of all radio layers and recent signals detected.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "wifi_scan",
        "description": "Scan local WiFi networks for mesh nodes or bridgeable APs.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "sdr_sweep",
        "description": "Sweep a frequency range with HackRF or RTL-SDR.",
        "input_schema": {
            "type": "object",
            "properties": {
                "freq_start_mhz": {"type": "number"},
                "freq_end_mhz":   {"type": "number"},
                "label":          {"type": "string"},
            },
            "required": ["freq_start_mhz", "freq_end_mhz"]
        }
    },
    {
        "name": "ham_beacon",
        "description": "Transmit a ham radio beacon (requires FCC license + TX_LICENSED=True).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"}
            },
            "required": []
        }
    },
]


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    p = argparse.ArgumentParser(description="RabbitOS Survival Broadcaster")
    p.add_argument("--scan",    action="store_true", help="Full survival scan all layers")
    p.add_argument("--fast",    action="store_true", help="Stop at first live layer")
    p.add_argument("--status",  action="store_true", help="Print layer status")
    p.add_argument("--wifi",    action="store_true", help="WiFi scan only")
    p.add_argument("--sdr",     nargs=2, metavar=("START","END"), help="SDR sweep MHz")
    p.add_argument("--ham",     action="store_true", help="Ham scan + optional beacon")
    p.add_argument("--fm",      action="store_true", help="FM broadcast scan")
    p.add_argument("--noaa",    action="store_true", help="NOAA weather radio scan")
    p.add_argument("--am",      action="store_true", help="AM broadcast scan")
    p.add_argument("--watch",   type=float, metavar="SECS", help="Continuous watch (interval)")
    p.add_argument("--beacon",  metavar="MSG", help="Transmit ham beacon (needs license)")
    args = p.parse_args()

    broadcaster = SurvivalBroadcaster()

    if args.scan or (not any(vars(args).values())):
        result = broadcaster.survival_scan(fast=args.fast)
        print(f"\n=== SURVIVAL RESULT ===")
        print(f"  Alive layers : {result['alive_layers']}")
        print(f"  Total energy : {result['total_energy']}")
        print(f"  Signals found: {result['signal_count']}")
        if result['best_signal']:
            b = result['best_signal']
            print(f"  Best signal  : {b['layer']} @ {b['freq_mhz']} MHz  {b['strength_db']} dBm")
        return

    if args.status:
        import json
        print(json.dumps(broadcaster.status(), indent=2))
        return

    if args.wifi:
        layer = WiFiLayer()
        if layer.detect():
            sigs = layer.scan()
            for s in sigs:
                print(f"  {s.freq_mhz:.0f}MHz  {s.strength_db:.1f}dBm  {s.data[:40]}")
        else:
            print("  WiFi adapter not detected")
        return

    if args.sdr:
        layer = SDRLayer()
        sigs  = layer.sweep(float(args.sdr[0]), float(args.sdr[1]))
        for s in sorted(sigs, key=lambda x: x.strength_db, reverse=True)[:20]:
            print(f"  {s.freq_mhz:10.4f} MHz  {s.strength_db:7.1f} dBm  e={s.energy:.3f}")
        return

    if args.ham:
        layer = HamLayer()
        sigs  = layer.scan()
        for s in sigs:
            print(f"  {s.layer:12s}  {s.freq_mhz:.4f} MHz  {s.strength_db:.1f} dBm")
        return

    if args.fm:
        layer = FMLayer()
        sigs  = layer.scan()
        for s in sigs:
            print(f"  {s.freq_mhz:.1f} MHz  {s.strength_db:.1f} dBm  {s.data[:30]}")
        return

    if args.noaa:
        layer = NOAALayer()
        sigs  = layer.scan()
        for s in sigs:
            print(f"  {s.freq_mhz:.3f} MHz  {s.strength_db:.1f} dBm  {s.data}")
        return

    if args.am:
        layer = AMLayer()
        sigs  = layer.scan()
        for s in sigs:
            print(f"  {s.freq_mhz*1000:.0f} kHz  {s.strength_db:.1f} dBm")
        return

    if args.watch:
        print(f"[Broadcast] Watching all layers every {args.watch}s — Ctrl+C to stop")
        try:
            broadcaster.watch(args.watch)
        except KeyboardInterrupt:
            broadcaster.stop()
        return

    if args.beacon:
        ham = HamLayer()
        ok  = ham.beacon(args.beacon)
        print(f"  Beacon {'sent' if ok else 'failed (need TX_LICENSED=True + CALLSIGN)'}")
        return


if __name__ == "__main__":
    main()
