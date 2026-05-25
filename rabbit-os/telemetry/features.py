"""
Feature extraction from raw telemetry payloads (sensor/spectrum/EEG).
"""
from __future__ import annotations
import math
from typing import Any, Dict, List


def extract_features(payload: Dict[str, Any]) -> Dict[str, float]:
    features: Dict[str, float] = {}

    if "value" in payload:
        features["raw_value"] = float(payload["value"])

    if "power_dbm" in payload:
        features["power_dbm"]    = float(payload["power_dbm"])
        features["power_linear"] = 10 ** (float(payload["power_dbm"]) / 10)

    if "frequency_mhz" in payload:
        features["frequency_mhz"] = float(payload["frequency_mhz"])

    if "peaks" in payload and payload["peaks"]:
        peaks = [float(p) for p in payload["peaks"] if p is not None]
        if peaks:
            features["peak_count"] = float(len(peaks))
            features["peak_max"]   = max(peaks)
            features["peak_mean"]  = sum(peaks) / len(peaks)

    if "eeg" in payload:
        eeg = payload["eeg"]
        if isinstance(eeg, list):
            vals = [float(v) for v in eeg if v is not None]
            if vals:
                mean = sum(vals) / len(vals)
                variance = sum((v - mean) ** 2 for v in vals) / len(vals)
                features["eeg_mean"]   = round(mean, 6)
                features["eeg_std"]    = round(math.sqrt(variance), 6)
                features["eeg_min"]    = min(vals)
                features["eeg_max"]    = max(vals)

    return features


def band_power(signal: List[float], band: str) -> float:
    BANDS = {
        "delta": (0.5, 4),
        "theta": (4, 8),
        "alpha": (8, 13),
        "beta":  (13, 30),
        "gamma": (30, 100),
    }
    lo, hi = BANDS.get(band, (0, 1))
    n = len(signal)
    if n == 0:
        return 0.0
    chunk = signal[int(lo):int(hi)] if int(hi) <= n else signal[int(lo):]
    return sum(v ** 2 for v in chunk) / max(len(chunk), 1)
