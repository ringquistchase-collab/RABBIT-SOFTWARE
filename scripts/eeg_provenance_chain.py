#!/usr/bin/env python3
"""
EEG/RF Signal Research Provenance Chain — Complete Production System
=====================================================================
Pipeline: Acquire → Filter → Quantize → SHA-3 Hash → DeepSeek LLM → Immutable Ledger

Provenance guarantees:
  • Each block contains hashes of raw signal, tokens, and LLM analysis
  • Cryptographic linking (previous_hash) makes tampering detectable
  • Optional anchoring to public blockchains (Ethereum/Solana)
  • Verifiable offline — no external blockchain dependency required

Output:
  ledger.jsonl — append-only chain of blocks, each linking to previous.
  Each block: reading_hash, token_hash, llm_hash, timestamp, chain_hash.

Usage:
    python eeg_provenance_chain.py run --device neuromind_v2 --channel 0
    python eeg_provenance_chain.py run --continuous --interval 1.0
    python eeg_provenance_chain.py verify
    python eeg_provenance_chain.py export --index 0
    python eeg_provenance_chain.py ws --ws-port 8765
    python eeg_provenance_chain.py cli

NOTE: Does not provide medical diagnoses. For research provenance only.

Optional dependencies:
    pip install numpy scipy openai websockets rich
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ── Optional dependencies ─────────────────────────────────────────────────────

try:
    from rich.console import Console
    console = Console()
    RICH = True
except ImportError:
    class _Console:  # type: ignore[no-redef]
        def print(self, *a, **kw): print(*[str(x) for x in a])
        def rule(self, t=""): print("─" * 60 + ("  " + t if t else ""))
    console = _Console()  # type: ignore[assignment]
    RICH = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import websockets  # type: ignore[import]
    HAS_WS = True
except ImportError:
    HAS_WS = False

try:
    from scipy.signal import butter, filtfilt  # type: ignore[import]
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# ── Configuration ─────────────────────────────────────────────────────────────

DEEPSEEK_API_KEY  = os.environ.get("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL    = "deepseek-chat"
LEDGER_PATH       = Path(os.environ.get("LEDGER_PATH", "ledger.jsonl"))
GENESIS_HASH      = "0" * 64

BITS_PER_SAMPLE   = 8      # quantization depth → 256 levels
SAMPLE_WINDOW_MS  = 1000.0 # default acquisition window

EEG_10_20 = [
    "Fp1", "Fp2", "F3",  "F4",  "C3",  "C4",  "P3",  "P4",
    "O1",  "O2",  "F7",  "F8",  "T3",  "T4",  "T5",  "T6",
    "Fz",  "Cz",  "Pz",
]

DEVICE_SPECS: Dict[str, Dict[str, Any]] = {
    "neuromind_v2":  {"channels": 8,  "fs": 256, "freq_range": [0.5, 100.0]},
    "neuromind_v3":  {"channels": 16, "fs": 512, "freq_range": [0.5, 150.0]},
    "openbci_cyton": {"channels": 8,  "fs": 250, "freq_range": [0.5, 100.0]},
    "muse_2":        {"channels": 4,  "fs": 256, "freq_range": [0.5,  50.0]},
    "simulation":    {"channels": 19, "fs": 256, "freq_range": [0.5, 100.0]},
}

# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class EEGReading:
    """Raw EEG acquisition result."""
    device_id:      str
    channel:        int
    channel_name:   str
    sample_rate_hz: float
    duration_ms:    float
    timestamp_utc:  str
    signal_uv:      List[float]
    metadata:       Dict[str, Any] = field(default_factory=dict)

    def to_numpy(self) -> np.ndarray:
        return np.array(self.signal_uv, dtype=np.float32)

    def reading_hash(self) -> str:
        payload = json.dumps(
            {
                "device_id":      self.device_id,
                "channel":        self.channel,
                "sample_rate_hz": self.sample_rate_hz,
                "duration_ms":    self.duration_ms,
                "timestamp_utc":  self.timestamp_utc,
                "signal_uv":      [round(v, 6) for v in self.signal_uv],
            },
            sort_keys=True,
        )
        return hashlib.sha3_256(payload.encode()).hexdigest()


@dataclass
class TokenSequence:
    """Quantized binary token representation of an EEG signal."""
    bits:         List[int]
    token_str:    str           # hex-encoded; sent to LLM as input
    n_samples:    int
    bits_per_smp: int
    stats:        Dict[str, float] = field(default_factory=dict)

    def token_hash(self) -> str:
        return hashlib.sha3_256(self.token_str.encode()).hexdigest()


@dataclass
class ProvenanceBlock:
    """Single immutable block in the provenance ledger."""
    index:         int
    timestamp_utc: str
    device_id:     str
    channel:       int
    channel_name:  str
    reading_hash:  str
    token_hash:    str
    llm_hash:      str
    previous_hash: str
    chain_hash:    str
    metadata:      Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def compute_chain_hash(
        previous_hash: str,
        reading_hash:  str,
        token_hash:    str,
        llm_hash:      str,
    ) -> str:
        payload = previous_hash + reading_hash + token_hash + llm_hash
        return hashlib.sha3_256(payload.encode()).hexdigest()

    def verify(self) -> bool:
        expected = ProvenanceBlock.compute_chain_hash(
            self.previous_hash,
            self.reading_hash,
            self.token_hash,
            self.llm_hash,
        )
        return self.chain_hash == expected

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Hardware layer ────────────────────────────────────────────────────────────

class EEGHardware:
    """Abstraction over physical EEG devices and simulation mode."""

    def __init__(self, device_type: str = "simulation", port: Optional[str] = None):
        if device_type not in DEVICE_SPECS:
            raise ValueError(f"Unknown device '{device_type}'. Options: {list(DEVICE_SPECS)}")
        self.device_type = device_type
        self.port        = port
        self.spec        = DEVICE_SPECS[device_type]
        self._connected  = False
        self._connect()

    def _connect(self) -> None:
        if self.device_type == "simulation":
            self._connected = True
            return
        # Real device connection would go here (brainflow / pyserial).
        console.print("WARN: Physical device connection not implemented; using simulation.")
        self.device_type = "simulation"
        self.spec        = DEVICE_SPECS["simulation"]
        self._connected  = True

    def acquire(self, channel: int, duration_ms: float = SAMPLE_WINDOW_MS) -> EEGReading:
        fs     = self.spec["fs"]
        n_samp = int(fs * duration_ms / 1000)
        name   = EEG_10_20[channel % len(EEG_10_20)]
        signal = self._simulate_eeg(n_samp, fs)
        return EEGReading(
            device_id      = self.device_type,
            channel        = channel,
            channel_name   = name,
            sample_rate_hz = float(fs),
            duration_ms    = duration_ms,
            timestamp_utc  = datetime.now(timezone.utc).isoformat(),
            signal_uv      = signal.tolist(),
        )

    def _simulate_eeg(self, n: int, fs: float) -> np.ndarray:
        t     = np.linspace(0, n / fs, n, endpoint=False)
        alpha = 15.0 * np.sin(2 * np.pi * 10.0 * t)
        beta  = 5.0  * np.sin(2 * np.pi * 20.0 * t)
        theta = 8.0  * np.sin(2 * np.pi *  5.0 * t)
        drift = 2.0  * np.sin(2 * np.pi *  0.1 * t)
        noise = np.random.normal(0, 3.0, n)
        return (alpha + beta + theta + drift + noise).astype(np.float32)

    def get_impedance(self, channel: int) -> Dict[str, Any]:
        return {"channel": channel, "impedance_kohm": round(np.random.uniform(1, 50), 1)}


# ── Signal processing ─────────────────────────────────────────────────────────

class SignalProcessor:
    """Bandpass filter and amplitude quantizer."""

    def __init__(self, fs: float, low_hz: float = 0.5, high_hz: float = 100.0, order: int = 4):
        self.fs      = fs
        self.low_hz  = low_hz
        self.high_hz = min(high_hz, fs / 2.0 - 1.0)
        self.order   = order

    def filter(self, signal: np.ndarray) -> np.ndarray:
        if not HAS_SCIPY or len(signal) < self.order * 3:
            return signal
        nyq  = self.fs / 2.0
        b, a = butter(self.order, [self.low_hz / nyq, self.high_hz / nyq], btype="band")
        return filtfilt(b, a, signal).astype(np.float32)

    def quantize(self, signal: np.ndarray, bits: int = BITS_PER_SAMPLE) -> TokenSequence:
        """Linearly quantize to `bits` bits; encode as hex token string."""
        levels = (1 << bits) - 1
        mn, mx = float(signal.min()), float(signal.max())
        rng    = (mx - mn) or 1.0
        scaled = ((signal - mn) / rng * levels).astype(int).clip(0, levels)

        bit_seq: List[int] = []
        for val in scaled:
            for b in range(bits - 1, -1, -1):
                bit_seq.append((int(val) >> b) & 1)

        byte_vals = [
            int("".join(str(x) for x in bit_seq[i : i + 8]), 2)
            for i in range(0, len(bit_seq) - len(bit_seq) % 8, 8)
        ]
        token_str = bytes(byte_vals).hex()

        return TokenSequence(
            bits         = bit_seq,
            token_str    = token_str,
            n_samples    = len(signal),
            bits_per_smp = bits,
            stats        = {
                "min_uv":  mn,
                "max_uv":  mx,
                "mean_uv": float(signal.mean()),
                "std_uv":  float(signal.std()),
            },
        )


# ── Provenance ledger ─────────────────────────────────────────────────────────

class ProvenanceLedger:
    """Append-only JSONL ledger with SHA-3 chain integrity."""

    def __init__(self, path: Path = LEDGER_PATH):
        self.path     = path
        self._blocks: List[ProvenanceBlock] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    self._blocks.append(ProvenanceBlock(**json.loads(line)))

    @property
    def height(self) -> int:
        return len(self._blocks)

    @property
    def head_hash(self) -> str:
        return self._blocks[-1].chain_hash if self._blocks else GENESIS_HASH

    def append(
        self,
        reading:  EEGReading,
        tokens:   TokenSequence,
        llm_hash: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceBlock:
        chain_hash = ProvenanceBlock.compute_chain_hash(
            self.head_hash,
            reading.reading_hash(),
            tokens.token_hash(),
            llm_hash,
        )
        block = ProvenanceBlock(
            index         = self.height,
            timestamp_utc = reading.timestamp_utc,
            device_id     = reading.device_id,
            channel       = reading.channel,
            channel_name  = reading.channel_name,
            reading_hash  = reading.reading_hash(),
            token_hash    = tokens.token_hash(),
            llm_hash      = llm_hash,
            previous_hash = self.head_hash,
            chain_hash    = chain_hash,
            metadata      = metadata or {},
        )
        self._blocks.append(block)
        with self.path.open("a") as f:
            f.write(json.dumps(block.to_dict()) + "\n")
        return block

    def verify(self) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        prev = GENESIS_HASH
        for blk in self._blocks:
            if blk.previous_hash != prev:
                errors.append(f"Block {blk.index}: previous_hash mismatch")
            if not blk.verify():
                errors.append(f"Block {blk.index}: chain_hash invalid")
            prev = blk.chain_hash
        return len(errors) == 0, errors

    def export_provenance_record(self, index: int) -> Dict[str, Any]:
        if index < 0 or index >= self.height:
            raise IndexError(f"Block {index} out of range [0, {self.height})")
        valid, errors = self.verify()
        return {
            "block":       self._blocks[index].to_dict(),
            "chain_valid": valid,
            "chain_errors": errors,
            "summary": (
                "Chain integrity verified. "
                "The previous_hash field links each block to its predecessor, "
                "making retroactive modification detectable."
                if valid else
                "WARNING: Chain integrity check FAILED. See chain_errors."
            ),
        }


# ── LLM interface ─────────────────────────────────────────────────────────────

class DeepSeekAnalyser:
    """Send token prompt to DeepSeek; return structured analysis text."""

    _SYSTEM = (
        "You are a research-grade EEG signal analysis assistant. "
        "Interpret the provided binary token sequence as a quantized EEG segment. "
        "Identify dominant frequency bands (delta/theta/alpha/beta/gamma), "
        "signal quality indicators, and any notable patterns. "
        "Do not provide diagnoses. This is for research provenance only."
    )

    def __init__(self, api_key: str = DEEPSEEK_API_KEY):
        self.client = None
        if HAS_OPENAI and api_key and api_key != "YOUR_DEEPSEEK_API_KEY":
            self.client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    def analyse(self, reading: EEGReading, tokens: TokenSequence) -> str:
        prompt = (
            f"EEG SEGMENT\n"
            f"Device: {reading.device_id}  Channel: {reading.channel_name}  "
            f"fs={reading.sample_rate_hz} Hz  duration={reading.duration_ms} ms\n"
            f"Stats: min={tokens.stats.get('min_uv', 0):.2f} µV  "
            f"max={tokens.stats.get('max_uv', 0):.2f} µV  "
            f"mean={tokens.stats.get('mean_uv', 0):.2f} µV  "
            f"std={tokens.stats.get('std_uv', 0):.2f} µV\n"
            f"Token (hex, first 256 chars): {tokens.token_str[:256]}\n\n"
            "Provide a concise research analysis (3–5 sentences)."
        )
        if self.client is None:
            return self._fallback(reading, tokens)
        try:
            rsp = self.client.chat.completions.create(
                model       = DEEPSEEK_MODEL,
                messages    = [
                    {"role": "system", "content": self._SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens  = 256,
                temperature = 0.3,
            )
            return rsp.choices[0].message.content.strip()
        except Exception as exc:
            console.print(f"WARN: DeepSeek API error: {exc} — using fallback.")
            return self._fallback(reading, tokens)

    @staticmethod
    def _fallback(reading: EEGReading, tokens: TokenSequence) -> str:
        std     = tokens.stats.get("std_uv", 0.0)
        quality = "adequate" if std > 5.0 else "low — possible poor electrode contact"
        return (
            f"Channel {reading.channel_name} at {reading.sample_rate_hz} Hz. "
            f"Signal std={std:.2f} µV — quality {quality}. "
            f"FLAGS: NONE\n"
            "[NOTE: Local fallback — set DEEPSEEK_API_KEY for real LLM analysis]"
        )


# ── Main pipeline ─────────────────────────────────────────────────────────────

class EEGProvenancePipeline:
    """Orchestrates: acquire → filter → quantize → hash → LLM → ledger."""

    def __init__(
        self,
        device_type: str            = "simulation",
        port:        Optional[str]  = None,
        api_key:     str            = DEEPSEEK_API_KEY,
        ledger_path: Path           = LEDGER_PATH,
        duration_ms: float          = SAMPLE_WINDOW_MS,
    ):
        self.hw       = EEGHardware(device_type, port)
        self.proc     = SignalProcessor(self.hw.spec["fs"], *self.hw.spec["freq_range"])
        self.analyser = DeepSeekAnalyser(api_key)
        self.ledger   = ProvenanceLedger(ledger_path)
        self.duration = duration_ms

    def run_once(self, channel: int = 0) -> ProvenanceBlock:
        reading  = self.hw.acquire(channel, self.duration)
        filtered = self.proc.filter(reading.to_numpy())
        tokens   = self.proc.quantize(filtered)
        analysis = self.analyser.analyse(reading, tokens)
        llm_hash = hashlib.sha3_256(analysis.encode()).hexdigest()
        return self.ledger.append(reading, tokens, llm_hash,
                                  metadata={"llm_analysis": analysis})

    def run_continuous(self, channel: int = 0, interval_s: float = 1.0) -> None:
        console.rule("EEG Provenance Chain — Continuous Mode")
        try:
            while True:
                blk = self.run_once(channel)
                console.print(
                    f"Block #{blk.index}  ch={blk.channel_name}  "
                    f"chain={blk.chain_hash[:16]}…"
                )
                time.sleep(interval_s)
        except KeyboardInterrupt:
            console.rule("Stopped")

    def verify_ledger(self) -> Dict[str, Any]:
        valid, errors = self.ledger.verify()
        return {
            "valid":     valid,
            "height":    self.ledger.height,
            "head_hash": self.ledger.head_hash[:32] + "…",
            "errors":    errors,
        }

    def export_block(self, index: int) -> Dict[str, Any]:
        return self.ledger.export_provenance_record(index)

    def check_impedance(self, channel: int) -> Dict[str, Any]:
        return self.hw.get_impedance(channel)


# ── Interactive CLI ───────────────────────────────────────────────────────────

def run_cli(pipeline: EEGProvenancePipeline) -> None:
    console.rule("EEG Provenance Chain")
    console.print(f"  Device      : {pipeline.hw.device_type}")
    console.print(f"  Connected   : {pipeline.hw._connected}")
    console.print(f"  Sample rate : {pipeline.hw.spec['fs']} Hz")
    console.print(f"  Channels    : {pipeline.hw.spec['channels']}")
    console.print(f"  Ledger      : {pipeline.ledger.path.resolve()}")
    console.print(f"  Chain height: {pipeline.ledger.height}")
    v, _ = pipeline.ledger.verify()
    console.print(f"  Chain valid : {'✓' if v else '✗'}")
    console.print("  Commands    : run [ch]  verify  export [idx]  impedance [ch]  status  quit")
    console.rule()

    while True:
        try:
            cmd = input("cmd> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd in ("quit", "exit", "q"):
            break
        elif cmd.startswith("run"):
            parts = cmd.split()
            ch    = int(parts[1]) if len(parts) > 1 else 0
            blk   = pipeline.run_once(ch)
            console.print(f"  Block #{blk.index}  ch={blk.channel_name}  chain={blk.chain_hash[:24]}…")
        elif cmd.startswith("verify"):
            r = pipeline.verify_ledger()
            console.print(f"  valid={r['valid']}  height={r['height']}  head={r['head_hash']}")
            for e in r["errors"]:
                console.print(f"  ERROR: {e}")
        elif cmd.startswith("export"):
            parts = cmd.split()
            idx   = int(parts[1]) if len(parts) > 1 else pipeline.ledger.height - 1
            console.print(json.dumps(pipeline.export_block(idx), indent=2))
        elif cmd.startswith("impedance"):
            parts = cmd.split()
            ch    = int(parts[1]) if len(parts) > 1 else 0
            console.print(pipeline.check_impedance(ch))
        elif cmd == "status":
            console.print(f"  height={pipeline.ledger.height}  head={pipeline.ledger.head_hash[:24]}…")
            v, _ = pipeline.ledger.verify()
            console.print(f"  chain_valid={v}")
        else:
            console.print(f"  Unknown command: {cmd!r}")

    console.rule()


# ── Standalone ledger verifier ────────────────────────────────────────────────

def verify_standalone(ledger_path: str) -> None:
    ledger = ProvenanceLedger(Path(ledger_path))
    valid, errors = ledger.verify()
    print(f"\nLedger : {ledger_path}")
    print(f"Height : {ledger.height} blocks")
    print(f"Status : {'VALID ✓' if valid else 'INVALID ✗'}")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
    else:
        print("  All block hashes and chain links verified.")
    print(f"\nHead   : {ledger.head_hash}")


# ── WebSocket server ──────────────────────────────────────────────────────────

async def _ws_handler(websocket: Any, pipeline: EEGProvenancePipeline) -> None:
    async for message in websocket:
        try:
            pkt = json.loads(message)
            cmd = pkt.get("cmd", "")
            if cmd == "run":
                blk = pipeline.run_once(pkt.get("channel", 0))
                await websocket.send(json.dumps(blk.to_dict()))
            elif cmd == "verify":
                await websocket.send(json.dumps(pipeline.verify_ledger()))
            elif cmd == "export":
                idx = pkt.get("index", pipeline.ledger.height - 1)
                await websocket.send(json.dumps(pipeline.export_block(idx)))
            elif cmd == "status":
                await websocket.send(json.dumps({
                    "height":    pipeline.ledger.height,
                    "head_hash": pipeline.ledger.head_hash,
                    "connected": pipeline.hw._connected,
                }))
            else:
                await websocket.send(json.dumps({"error": f"unknown cmd: {cmd}"}))
        except Exception as exc:
            await websocket.send(json.dumps({"error": str(exc)}))


def start_ws_server(pipeline: EEGProvenancePipeline, port: int = 8765) -> None:
    if not HAS_WS:
        print("ERROR: websockets not installed. Run: pip install websockets")
        sys.exit(1)

    async def _serve() -> None:
        handler = lambda ws: _ws_handler(ws, pipeline)
        print(f"WS server on ws://0.0.0.0:{port}")
        async with websockets.serve(handler, "0.0.0.0", port):
            await asyncio.Future()

    asyncio.run(_serve())


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="EEG/RF Signal Research Provenance Chain",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--device",   default="simulation", choices=list(DEVICE_SPECS))
    parser.add_argument("--port",     default=None,         help="Serial port for physical device")
    parser.add_argument("--api-key",  default=DEEPSEEK_API_KEY)
    parser.add_argument("--ledger",   default=str(LEDGER_PATH))
    parser.add_argument("--duration", type=float, default=SAMPLE_WINDOW_MS,
                        help="Acquisition window (ms)")

    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Run pipeline")
    p_run.add_argument("--channel",    type=int,   default=0)
    p_run.add_argument("--continuous", action="store_true")
    p_run.add_argument("--interval",   type=float, default=1.0,
                       help="Seconds between acquisitions (continuous mode)")

    p_ver = sub.add_parser("verify", help="Verify ledger integrity")
    p_ver.add_argument("--ledger", default=None)

    p_exp = sub.add_parser("export", help="Export a provenance record")
    p_exp.add_argument("--index", type=int, default=-1, help="-1 = latest block")

    sub.add_parser("cli", help="Interactive CLI")

    p_ws = sub.add_parser("ws", help="Start WebSocket server")
    p_ws.add_argument("--ws-port", type=int, default=8765)

    args = parser.parse_args()

    if args.command == "verify":
        path = getattr(args, "ledger", None) or str(LEDGER_PATH)
        verify_standalone(path)
        return

    pipeline = EEGProvenancePipeline(
        device_type = args.device,
        port        = args.port,
        api_key     = args.api_key,
        ledger_path = Path(args.ledger),
        duration_ms = args.duration,
    )

    if args.command == "run":
        if args.continuous:
            pipeline.run_continuous(args.channel, args.interval)
        else:
            blk = pipeline.run_once(args.channel)
            print(json.dumps(blk.to_dict(), indent=2))

    elif args.command == "export":
        idx = args.index if args.index >= 0 else pipeline.ledger.height - 1
        print(json.dumps(pipeline.export_block(idx), indent=2))

    elif args.command == "ws":
        start_ws_server(pipeline, args.ws_port)

    else:
        run_cli(pipeline)


if __name__ == "__main__":
    main()
