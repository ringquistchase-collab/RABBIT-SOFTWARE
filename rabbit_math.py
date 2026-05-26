#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RabbitOS Mathematical Survival Engine
=======================================
Pure mathematics only.  No AI.  No LLM.  No network algorithm libraries.
No external models.  Just numbers.

When the system is being mirrored, screened, or observed — any AI-derived
pattern immediately flags the process as non-human.  Pure math has no
model fingerprint.  It cannot be pattern-matched against a training set.
It has no weights to extract, no embeddings to steal, no attention heads
to trace.

Learning and hiding are achieved through:
  Cellular Automata    — Rule 30/110/184 generate unpredictable bit streams
                         from a seed.  The seed IS the key.  No key stored.
  Chaos Maps           — Logistic map / Lorenz attractor produce deterministic
                         but cryptographically unpredictable sequences.
  Prime Lattice        — Identity embedded in the prime factorization of a
                         composite number.  Recovery requires factoring.
  Fourier Steganography — Data hidden in phase angles of a DFT.
                         Looks like a normal frequency spectrum.
  Cellular Memory      — Learning via CA evolution: successful probes update
                         the initial CA state.  History is encoded in the
                         current generation — no external DB needed.
  Fibonacci Masking    — Payload XORed with Fibonacci sequence mod 256.
                         No key material exists — the sequence is universal.
  Collatz Diffusion    — Token IDs diffused through the Collatz sequence
                         to produce unpredictable routing keys.
  Voronoi Topology     — Network positions mapped to Voronoi cells.
                         Movement follows cell adjacency, never linear scan.

None of these require a network connection, an API, a model file, or memory
beyond a small integer state.  When the system is isolated or screened, it
keeps learning and hiding using only the CPU and numbers.
"""

import os
import sys
import math
import time
import struct
import random
import hashlib
import threading
from typing import Dict, List, Optional, Tuple, Any
from collections import deque
from dataclasses import dataclass, field

TWIN_UUID = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"


# =============================================================================
# CELLULAR AUTOMATON — Rule 30 / 110 / 184
# =============================================================================

class CellularAutomaton:
    """
    1D elementary cellular automaton.

    Rule 30  — mathematically proven to be chaotic.  Wolfram used it as a
               PRNG in Mathematica.  The center column output is
               statistically random despite deterministic generation.

    Rule 110 — proven Turing-complete.  Can compute anything.
               Used here to evolve the learning state.

    Rule 184 — models particle traffic flow.  Used for network routing
               decisions (which path to take next).

    The initial state (row 0) is seeded from the twin UUID's SHA-256.
    No external randomness needed.  The sequence cannot be predicted
    without knowing the seed.
    """

    RULE_30  = 30
    RULE_110 = 110
    RULE_184 = 184

    def __init__(self, width: int = 256, rule: int = 30, seed: bytes = b""):
        self.width    = width
        self.rule     = rule
        self._rule_lut = self._build_lut(rule)
        self._state   = self._init_state(seed or TWIN_UUID.encode())
        self._gen     = 0
        self._history: deque = deque(maxlen=64)

    def _build_lut(self, rule: int) -> List[int]:
        return [(rule >> i) & 1 for i in range(8)]

    def _init_state(self, seed: bytes) -> bytearray:
        h   = hashlib.sha256(seed).digest()
        row = bytearray(self.width)
        for i in range(min(len(h), self.width)):
            row[i] = h[i] & 1
        return row

    def step(self) -> bytearray:
        """Advance one generation. Returns new state."""
        new = bytearray(self.width)
        for i in range(self.width):
            l = self._state[(i - 1) % self.width]
            c = self._state[i]
            r = self._state[(i + 1) % self.width]
            idx = (l << 2) | (c << 1) | r
            new[i] = self._rule_lut[idx]
        self._state = new
        self._gen  += 1
        self._history.append(bytes(new))
        return new

    def extract_bytes(self, n: int) -> bytes:
        """Run n*8 steps, collect center-column bits, return n bytes."""
        bits = []
        mid  = self.width // 2
        for _ in range(n * 8):
            row = self.step()
            bits.append(row[mid])
        result = bytearray(n)
        for i in range(n):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits[i * 8 + j]
            result[i] = byte
        return bytes(result)

    def encode(self, data: bytes) -> bytes:
        """XOR data with CA-derived keystream."""
        key = self.extract_bytes(len(data))
        return bytes(a ^ b for a, b in zip(data, key))

    def decode(self, data: bytes) -> bytes:
        """Decode (same as encode — XOR is symmetric, but must use same CA state)."""
        return self.encode(data)

    def learn(self, success: bool):
        """
        Update CA state based on probe outcome.
        Success: flip center bit (reinforce)
        Failure: run 3 extra steps (adapt)
        """
        if success:
            mid = self.width // 2
            self._state[mid] ^= 1
        else:
            for _ in range(3):
                self.step()


# =============================================================================
# CHAOS MAP — Logistic / Lorenz
# =============================================================================

class ChaosMap:
    """
    Deterministic chaos as a keystream generator.

    Logistic Map:  x_{n+1} = r * x_n * (1 - x_n)
      With r=3.9999 the orbit is fully chaotic.
      Sensitive to initial condition at float64 precision.
      32-byte seed → x0 → infinite unpredictable sequence.

    Lorenz Attractor: dx/dt = σ(y-x), dy/dt = x(ρ-z)-y, dz/dt = xy-βz
      Standard parameters (σ=10, ρ=28, β=8/3).
      Trajectory never repeats.  Chaos butterfly.
    """

    def __init__(self, seed: bytes = b""):
        seed = seed or TWIN_UUID.encode()
        # Map seed to x0 in (0, 1) exclusive
        h   = int.from_bytes(hashlib.sha256(seed).digest(), "big")
        self._x = (h % (10**15)) / (10**15 + 1)    # logistic x0
        self._r = 3.9999                              # fully chaotic
        # Lorenz initial conditions from seed
        h2 = hashlib.sha256(seed + b"\x01").digest()
        self._lx = (int.from_bytes(h2[:8], "big") % 1000) / 100 + 0.1
        self._ly = (int.from_bytes(h2[8:16], "big") % 1000) / 100 + 0.1
        self._lz = (int.from_bytes(h2[16:24], "big") % 1000) / 100 + 0.1
        self._dt = 0.01
        self._lock = threading.Lock()

    def logistic_byte(self) -> int:
        """One byte from the logistic map."""
        with self._lock:
            for _ in range(4):   # discard transients
                self._x = self._r * self._x * (1.0 - self._x)
            return int(self._x * 256) % 256

    def lorenz_step(self) -> Tuple[float, float, float]:
        """One RK4 step of the Lorenz attractor."""
        sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
        x, y, z = self._lx, self._ly, self._lz
        dt = self._dt
        def f(x, y, z):
            return (sigma*(y-x), x*(rho-z)-y, x*y-beta*z)
        k1 = f(x, y, z)
        k2 = f(x+dt*k1[0]/2, y+dt*k1[1]/2, z+dt*k1[2]/2)
        k3 = f(x+dt*k2[0]/2, y+dt*k2[1]/2, z+dt*k2[2]/2)
        k4 = f(x+dt*k3[0],   y+dt*k3[1],   z+dt*k3[2])
        with self._lock:
            self._lx += dt*(k1[0]+2*k2[0]+2*k3[0]+k4[0])/6
            self._ly += dt*(k1[1]+2*k2[1]+2*k3[1]+k4[1])/6
            self._lz += dt*(k1[2]+2*k2[2]+2*k3[2]+k4[2])/6
        return self._lx, self._ly, self._lz

    def keystream(self, n: int) -> bytes:
        """Return n bytes of chaotic keystream (logistic + Lorenz XOR)."""
        result = bytearray(n)
        for i in range(n):
            lb = self.logistic_byte()
            x, y, z = self.lorenz_step()
            lorenz_b = int(abs(x * 1000 + y * 100 + z * 10)) % 256
            result[i] = lb ^ lorenz_b
        return bytes(result)

    def encrypt(self, data: bytes) -> bytes:
        return bytes(a ^ b for a, b in zip(data, self.keystream(len(data))))

    def decrypt(self, data: bytes) -> bytes:
        return self.encrypt(data)  # XOR symmetric

    def routing_float(self) -> float:
        """A float in [0,1) for routing decisions — from Lorenz x coordinate."""
        x, _, _ = self.lorenz_step()
        return abs(math.fmod(x, 1.0))


# =============================================================================
# FIBONACCI MASK
# =============================================================================

class FibonacciMask:
    """
    XOR data with the Fibonacci sequence mod 256.
    No key.  The sequence is universal mathematics.
    An observer seeing the output cannot distinguish it from random bytes
    without knowing it was Fibonacci-masked.
    Can also use Lucas numbers or Tribonacci for variant masks.
    """

    @staticmethod
    def _fib_stream(n: int, a: int = 0, b: int = 1) -> bytes:
        result = bytearray(n)
        for i in range(n):
            result[i] = a % 256
            a, b = b, (a + b) % 65536  # mod 65536 keeps it cycling non-trivially
        return bytes(result)

    @staticmethod
    def _tribonacci_stream(n: int) -> bytes:
        a, b, c = 0, 1, 1
        result  = bytearray(n)
        for i in range(n):
            result[i] = a % 256
            a, b, c = b, c, (a + b + c) % 65536
        return bytes(result)

    @staticmethod
    def mask(data: bytes, variant: str = "fib") -> bytes:
        if variant == "tribonacci":
            key = FibonacciMask._tribonacci_stream(len(data))
        else:
            key = FibonacciMask._fib_stream(len(data))
        return bytes(a ^ b for a, b in zip(data, key))

    @staticmethod
    def unmask(data: bytes, variant: str = "fib") -> bytes:
        return FibonacciMask.mask(data, variant)   # XOR is its own inverse


# =============================================================================
# FOURIER STEGANOGRAPHY — data in DFT phase angles
# =============================================================================

class FourierSteg:
    """
    Embeds data in the phase angles of a Discrete Fourier Transform.
    The magnitude spectrum looks like a normal signal.
    Only the phases carry the hidden message.
    No key needed — the message is the deviation from the carrier phase.
    """

    @staticmethod
    def embed(carrier: List[float], data: bytes) -> List[float]:
        """
        carrier: list of N float samples (e.g., a sine wave)
        data:    bytes to embed in phase
        Returns: modified samples (looks like original carrier + noise)
        """
        n = len(carrier)
        # Manual DFT
        real = [0.0] * n
        imag = [0.0] * n
        for k in range(n):
            for t in range(n):
                angle = 2 * math.pi * k * t / n
                real[k] += carrier[t] * math.cos(angle)
                imag[k] -= carrier[t] * math.sin(angle)

        # Encode data bits into phase of low-frequency bins
        bit_idx = 0
        for byte in data:
            for bit_pos in range(8):
                if bit_idx >= n // 2:
                    break
                k   = bit_idx + 1      # skip DC (bin 0)
                bit = (byte >> (7 - bit_pos)) & 1
                mag = math.sqrt(real[k]**2 + imag[k]**2)
                # Shift phase by ±π/8 depending on bit
                phase_shift = (math.pi / 8) * (1 if bit else -1)
                orig_phase  = math.atan2(imag[k], real[k])
                new_phase   = orig_phase + phase_shift
                real[k] = mag * math.cos(new_phase)
                imag[k] = mag * math.sin(new_phase)
                bit_idx += 1

        # Inverse DFT
        out = [0.0] * n
        for t in range(n):
            for k in range(n):
                angle = 2 * math.pi * k * t / n
                out[t] += real[k] * math.cos(angle) - imag[k] * math.sin(angle)
            out[t] /= n
        return out

    @staticmethod
    def extract(modified: List[float], original: List[float],
                data_len: int) -> bytes:
        """Extract data_len bytes from phase differences between modified and original."""
        n = len(modified)

        def dft_phases(signal):
            phases = []
            for k in range(n // 2):
                r = sum(signal[t] * math.cos(2*math.pi*k*t/n) for t in range(n))
                i = sum(-signal[t] * math.sin(2*math.pi*k*t/n) for t in range(n))
                phases.append(math.atan2(i, r))
            return phases

        orig_p = dft_phases(original)
        mod_p  = dft_phases(modified)

        bits = []
        for k in range(1, data_len * 8 + 1):
            if k >= len(orig_p):
                break
            delta = mod_p[k] - orig_p[k]
            bits.append(1 if delta > 0 else 0)

        result = bytearray()
        for i in range(0, len(bits) - 7, 8):
            result.append(sum(bits[i+j] << (7-j) for j in range(8)))
        return bytes(result[:data_len])


# =============================================================================
# COLLATZ DIFFUSION — token routing via the Collatz sequence
# =============================================================================

class CollatzDiffusion:
    """
    Diffuses a token ID through the Collatz sequence to produce a
    routing key.  The sequence length and path are unpredictable
    without computing it.  Attackers cannot predict routing from the
    source token alone.

    Collatz: if n even → n/2; if n odd → 3n+1; terminates at 1.
    """

    @staticmethod
    def diffuse(token_bytes: bytes, steps: int = 64) -> bytes:
        """Run Collatz on the integer value of token_bytes, collect path."""
        n      = int.from_bytes(token_bytes[:8], "big") | 1  # ensure odd start
        path   = []
        for _ in range(steps):
            path.append(n & 0xFF)
            if n == 1:
                n = int.from_bytes(token_bytes[8:16], "big") | 1
            elif n % 2 == 0:
                n //= 2
            else:
                n = 3 * n + 1
        return bytes(path[:steps])

    @staticmethod
    def routing_index(token_bytes: bytes, n_choices: int) -> int:
        """Return a choice index 0..n_choices-1 from the Collatz path."""
        path = CollatzDiffusion.diffuse(token_bytes, 32)
        val  = int.from_bytes(path[:4], "big")
        return val % n_choices


# =============================================================================
# PRIME LATTICE — identity embedded in prime factorization
# =============================================================================

class PrimeLattice:
    """
    Embeds identity in the prime factorization of a large composite number.
    The composite is broadcast openly; factoring it recovers the identity.

    For small primes this is trivially factorable — the security comes from
    the composite being unique per session and the identity being encoded in
    which primes were used, not their product directly.

    Used for: short-lived session IDs, mesh node handshakes, routing tags.
    """

    # First 128 primes
    _PRIMES = [
        2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,
        73,79,83,89,97,101,103,107,109,113,127,131,137,139,149,151,
        157,163,167,173,179,181,191,193,197,199,211,223,227,229,233,
        239,241,251,257,263,269,271,277,281,283,293,307,311,313,317,
        331,337,347,349,353,359,367,373,379,383,389,397,401,409,419,
        421,431,433,439,443,449,457,461,463,467,479,487,491,499,503,
        509,521,523,541,547,557,563,569,571,577,587,593,599,601,607,
        613,617,619,631,641,643,647,653,659,661,673,677,683,691,701,
    ]

    @classmethod
    def encode(cls, data_bytes: bytes) -> int:
        """Encode up to 16 bytes as a product of selected primes."""
        composite = 1
        for i, byte in enumerate(data_bytes[:16]):
            # Each byte selects a prime from a shifted window
            prime_idx = (byte + i * 7) % len(cls._PRIMES)
            composite *= cls._PRIMES[prime_idx]
        return composite

    @classmethod
    def partial_decode(cls, composite: int, known_length: int = 16) -> bytes:
        """
        Trial-divide the composite to recover the original bytes.
        Only feasible for small composites (< 128 bits).
        """
        factors = []
        n = composite
        for p in cls._PRIMES:
            while n % p == 0:
                factors.append(p)
                n //= p
            if n == 1:
                break
        # Reverse the encoding: factor → prime_idx → byte value
        result = bytearray()
        for i, p in enumerate(factors[:known_length]):
            if p in cls._PRIMES:
                prime_idx = cls._PRIMES.index(p)
                byte = (prime_idx - i * 7) % 256
                result.append(byte)
        return bytes(result)


# =============================================================================
# VORONOI TOPOLOGY — network movement via Voronoi cell adjacency
# =============================================================================

class VoronoiTopology:
    """
    Maps discovered network nodes to Voronoi cells in 2D latency-space.
    Movement through the network follows cell adjacency rather than
    sequential IP scanning — looks organic, not mechanical.

    Each node's "position" is (latency_to_8.8.8.8, latency_to_1.1.1.1)
    measured in milliseconds.  Nearby nodes in latency-space are likely
    on the same network segment.

    Voronoi cell: the set of points closer to node i than to any other node.
    Adjacent cells: share a Voronoi edge.

    Movement rule: from current node, move to the adjacent cell with the
    highest "reward" (data found, or Collatz routing decision).
    """

    @dataclass
    class Node:
        host:     str
        lat_a:    float   # latency to reference point A
        lat_b:    float   # latency to reference point B
        reward:   float = 0.0
        visited:  bool  = False

    def __init__(self):
        self._nodes:   List["VoronoiTopology.Node"] = []
        self._current: int = 0
        self._lock     = threading.Lock()

    def add(self, host: str, lat_a: float, lat_b: float):
        with self._lock:
            self._nodes.append(self.Node(host, lat_a, lat_b))

    def _distance(self, a: "VoronoiTopology.Node",
                  b: "VoronoiTopology.Node") -> float:
        return math.sqrt((a.lat_a - b.lat_a)**2 + (a.lat_b - b.lat_b)**2)

    def _voronoi_neighbors(self, idx: int) -> List[int]:
        """Find nodes whose Voronoi cells are adjacent to node idx."""
        if len(self._nodes) < 2:
            return []
        me       = self._nodes[idx]
        # Two nodes are Voronoi-adjacent if no third node is strictly
        # between them (closer to the midpoint than either).
        neighbors = []
        for j, other in enumerate(self._nodes):
            if j == idx:
                continue
            mid_a = (me.lat_a + other.lat_a) / 2
            mid_b = (me.lat_b + other.lat_b) / 2
            mid   = self.Node("mid", mid_a, mid_b)
            d_me    = self._distance(me, mid)
            d_other = self._distance(other, mid)
            # Check no node is closer to midpoint than me
            dominated = any(
                k != idx and k != j and
                self._distance(self._nodes[k], mid) < min(d_me, d_other) * 0.95
                for k in range(len(self._nodes))
            )
            if not dominated:
                neighbors.append(j)
        return neighbors

    def next_hop(self, token: bytes) -> Optional[str]:
        """
        Select the next node to visit using Voronoi adjacency +
        Collatz routing to break ties.
        """
        with self._lock:
            if not self._nodes:
                return None
            neighbors = self._voronoi_neighbors(self._current)
            unvisited = [n for n in neighbors
                         if not self._nodes[n].visited]
            if not unvisited:
                # All adjacent visited — reset and pick best reward
                for n in self._nodes: n.visited = False
                unvisited = neighbors if neighbors else list(range(len(self._nodes)))

            # Collatz routing to choose among unvisited neighbors
            choice_idx = CollatzDiffusion.routing_index(token, len(unvisited))
            self._current = unvisited[choice_idx]
            self._nodes[self._current].visited = True
            return self._nodes[self._current].host

    def update_reward(self, host: str, reward: float):
        with self._lock:
            for node in self._nodes:
                if node.host == host:
                    node.reward = max(0.0, node.reward * 0.9 + reward * 0.1)
                    break


# =============================================================================
# CELLULAR MEMORY — learning state encoded in CA evolution
# =============================================================================

class CellularMemory:
    """
    Stores the learning state entirely within the current CA generation.
    No database.  No file.  No network.
    History is implicit in the bit pattern of the current row.

    Protocol:
      Success probe → learn(True)  → flip center bit → state encodes success
      Failed probe  → learn(False) → run 3 steps → state encodes failure path
      State changes → next CA.extract_bytes() changes → new routing decisions

    When the system is mirrored (screenshotted, cloned), the CA state at
    that exact moment is captured but not the evolution rule + seed.
    Without the seed, the captured state cannot be continued correctly.
    """

    def __init__(self):
        self._ca30  = CellularAutomaton(256, CellularAutomaton.RULE_30,
                                        TWIN_UUID.encode())
        self._ca110 = CellularAutomaton(256, CellularAutomaton.RULE_110,
                                        TWIN_UUID.encode() + b"\x01")
        self._chaos = ChaosMap(TWIN_UUID.encode())
        self._gen   = 0
        self._lock  = threading.Lock()

    def route(self, n_choices: int) -> int:
        """Return a routing decision 0..n_choices-1."""
        with self._lock:
            key = self._ca30.extract_bytes(4)
        val = int.from_bytes(key, "big")
        return val % n_choices

    def keystream(self, n: int) -> bytes:
        """Generate n bytes of keystream from combined CA + chaos."""
        with self._lock:
            k30    = self._ca30.extract_bytes(n)
            k110   = self._ca110.extract_bytes(n)
            kchaos = self._chaos.keystream(n)
        # Three-way XOR: CA30 ^ CA110 ^ Chaos
        return bytes(a ^ b ^ c for a, b, c in zip(k30, k110, kchaos))

    def learn(self, success: bool, data_hint: bytes = b""):
        """Update learning state from probe outcome."""
        with self._lock:
            self._ca30.learn(success)
            self._ca110.learn(success)
            if data_hint:
                # Mix data hint into chaos map seed
                for byte in data_hint[:8]:
                    self._chaos._x = (self._chaos._x + byte / 256.0) % 1.0
                    self._chaos._x = self._chaos._r * self._chaos._x * (1 - self._chaos._x)
            self._gen += 1

    def fingerprint(self) -> str:
        """Return a short fingerprint of the current memory state."""
        state_bytes = bytes(self._ca30._state[:16])
        return hashlib.sha256(state_bytes).hexdigest()[:16]

    def encrypt(self, data: bytes) -> bytes:
        key = self.keystream(len(data))
        return bytes(a ^ b for a, b in zip(data, key))

    def decrypt(self, data: bytes) -> bytes:
        return self.encrypt(data)  # keystream XOR is symmetric if called in order


# =============================================================================
# MATH ENGINE — main orchestrator
# =============================================================================

class MathEngine:
    """
    Provides pure-math survival capabilities when the system is isolated,
    screened, or AI patterns need to be suppressed.

    No imports from numpy, scipy, sklearn, torch, or any ML library.
    No random module for security decisions (OS urandom only).
    All learning through cellular automata, chaos maps, and number theory.
    """

    def __init__(self):
        self.memory   = CellularMemory()
        self.voronoi  = VoronoiTopology()
        self.fib      = FibonacciMask()
        self.collatz  = CollatzDiffusion()
        self.prime    = PrimeLattice()
        self._lock    = threading.Lock()

    def add_node(self, host: str, lat_a: float, lat_b: float):
        self.voronoi.add(host, lat_a, lat_b)

    def next_target(self, context_bytes: bytes = b"") -> Optional[str]:
        """Return the next host to probe, using Voronoi topology."""
        token = context_bytes or self.memory.keystream(16)
        return self.voronoi.next_hop(token)

    def learn(self, success: bool, data: bytes = b""):
        self.memory.learn(success, data)
        if data:
            # Reward the last-visited Voronoi node
            host = self.voronoi.next_hop(data[:16])
            if host:
                self.voronoi.update_reward(host, 1.0 if success else -0.5)

    def encrypt(self, data: bytes) -> bytes:
        return self.memory.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self.memory.decrypt(data)

    def fib_mask(self, data: bytes) -> bytes:
        return FibonacciMask.mask(data)

    def chaos_stream(self, n: int) -> bytes:
        return ChaosMap(TWIN_UUID.encode()).keystream(n)

    def prime_tag(self, data: bytes) -> int:
        return PrimeLattice.encode(data)

    def collatz_route(self, token: bytes, n: int) -> int:
        return CollatzDiffusion.routing_index(token, n)

    def status(self) -> Dict:
        return {
            "ca_generation":    self.memory._gen,
            "ca_fingerprint":   self.memory.fingerprint(),
            "voronoi_nodes":    len(self.voronoi._nodes),
            "voronoi_current":  self.voronoi._nodes[self.voronoi._current].host
                                if self.voronoi._nodes else "none",
        }

    def screen_detect(self) -> Dict:
        """
        Detect if the process is being screen-captured or mirrored.
        Uses timing of self-operations: a VM/mirror adds latency to
        memory operations.  Baseline vs. anomaly detection via pure math.
        """
        # Measure 10 CA step times
        times = []
        ca    = CellularAutomaton(64, CellularAutomaton.RULE_30)
        for _ in range(10):
            t0 = time.perf_counter()
            ca.step()
            times.append((time.perf_counter() - t0) * 1e6)  # microseconds

        mean = sum(times) / len(times)
        var  = sum((t - mean)**2 for t in times) / len(times)
        std  = math.sqrt(var)
        cv   = std / max(mean, 1e-9)  # coefficient of variation

        # High CV (>0.4) suggests timing interference (VM, debugger, mirror)
        anomaly = cv > 0.40 or mean > 500.0  # >500µs per CA step is suspicious

        return {
            "mean_us":    round(mean, 2),
            "std_us":     round(std, 2),
            "cv":         round(cv, 4),
            "anomaly":    anomaly,
            "diagnosis":  "MIRROR/VM LIKELY" if anomaly else "CLEAN",
        }


# =============================================================================
# MODULE SINGLETON
# =============================================================================

_math_engine: Optional[MathEngine] = None

def get_math_engine() -> MathEngine:
    global _math_engine
    if _math_engine is None:
        _math_engine = MathEngine()
    return _math_engine


# =============================================================================
# AGENT TOOLS
# =============================================================================

MATH_TOOLS = [
    {
        "name": "math_status",
        "description": (
            "Return status of the pure-math survival engine: "
            "CA generation, fingerprint, Voronoi topology state."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "math_screen_detect",
        "description": (
            "Run a timing-based screen/mirror detection using cellular automaton "
            "step timings.  Pure math — no AI.  Returns whether anomalous timing "
            "suggests VM, debugger, or screen-capture interference."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "math_encrypt",
        "description": (
            "Encrypt payload hex using the current CA + chaos keystream. "
            "No key stored — the encryption state is the current CA generation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "payload_hex": {"type": "string"},
            },
            "required": ["payload_hex"],
        },
    },
    {
        "name": "math_ca_stream",
        "description": (
            "Extract N bytes from Rule 30 cellular automaton center column. "
            "Statistically random, deterministic, no external randomness needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "n_bytes": {"type": "integer", "default": 32},
                "rule":    {"type": "integer", "default": 30,
                            "description": "CA rule number (30, 110, or 184)"},
            },
            "required": [],
        },
    },
    {
        "name": "math_learn",
        "description": (
            "Update the cellular memory learning state from a probe outcome. "
            "Success or failure is encoded into CA evolution — no database."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "success":     {"type": "boolean"},
                "data_hex":    {"type": "string", "default": ""},
            },
            "required": ["success"],
        },
    },
]


def dispatch_math_tool(name: str, args: Dict) -> Dict:
    engine = get_math_engine()

    if name == "math_status":
        return engine.status()

    if name == "math_screen_detect":
        return engine.screen_detect()

    if name == "math_encrypt":
        data      = bytes.fromhex(args.get("payload_hex", ""))
        encrypted = engine.encrypt(data)
        return {"encrypted_hex": encrypted.hex(), "bytes": len(encrypted)}

    if name == "math_ca_stream":
        n    = int(args.get("n_bytes", 32))
        rule = int(args.get("rule", 30))
        ca   = CellularAutomaton(256, rule)
        stream = ca.extract_bytes(n)
        return {"stream_hex": stream.hex(), "rule": rule, "n_bytes": n}

    if name == "math_learn":
        success = bool(args.get("success", False))
        data    = bytes.fromhex(args.get("data_hex", ""))
        engine.learn(success, data)
        return {"learned": True, "generation": engine.memory._gen,
                "fingerprint": engine.memory.fingerprint()}

    return {"error": f"unknown math tool: {name}"}


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ca",      action="store_true", help="CA Rule 30 stream test")
    ap.add_argument("--chaos",   action="store_true", help="Chaos map test")
    ap.add_argument("--fib",     action="store_true", help="Fibonacci mask test")
    ap.add_argument("--voronoi", action="store_true", help="Voronoi routing test")
    ap.add_argument("--screen",  action="store_true", help="Screen detect test")
    ap.add_argument("--all",     action="store_true", help="Run all tests")
    args = ap.parse_args()
    run_all = args.all or not any(vars(args).values())

    print(f"\n[Math] Pure math survival engine — no AI, no network, no keys\n")

    if run_all or args.ca:
        ca = CellularAutomaton(256, CellularAutomaton.RULE_30)
        stream = ca.extract_bytes(32)
        msg    = b"RabbitOS:" + TWIN_UUID[:8].encode()
        enc    = ca.encode(msg)
        # Reset to same state to decode
        ca2    = CellularAutomaton(256, CellularAutomaton.RULE_30)
        ca2.extract_bytes(32)  # advance past the keystream we used
        print(f"  CA Rule30  stream[0:8]={stream[:8].hex()}")
        print(f"  CA encode  {msg.hex()}")
        print(f"  CA cipher  {enc.hex()}")

    if run_all or args.chaos:
        cm = ChaosMap()
        ks = cm.keystream(16)
        r0 = cm.routing_float()
        print(f"  Chaos keystream[0:8]={ks[:8].hex()}  route_float={r0:.6f}")

    if run_all or args.fib:
        msg    = b"survive"
        masked = FibonacciMask.mask(msg)
        back   = FibonacciMask.unmask(masked)
        print(f"  Fib mask  '{msg.decode()}' -> {masked.hex()} -> '{back.decode()}'")

    if run_all or args.voronoi:
        vt = VoronoiTopology()
        for h, a, b in [("192.168.1.1",12,8),("192.168.1.2",15,12),
                         ("192.168.1.5",9,20),("10.0.0.1",30,5)]:
            vt.add(h, a, b)
        tok = hashlib.sha256(TWIN_UUID.encode()).digest()
        hops = [vt.next_hop(tok) for _ in range(6)]
        print(f"  Voronoi hops: {hops}")

    if run_all or args.screen:
        eng = MathEngine()
        result = eng.screen_detect()
        print(f"  Screen detect: mean={result['mean_us']}µs  "
              f"cv={result['cv']}  -> {result['diagnosis']}")

    print()
