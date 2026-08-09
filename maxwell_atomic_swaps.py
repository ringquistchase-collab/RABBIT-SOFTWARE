#!/usr/bin/env python3
"""
Maxwell Cross-Chain Atomic Swaps (HTLC)
=======================================
Save as: maxwell_atomic_swaps.py
Run:     python3 maxwell_atomic_swaps.py

Implements Hash Time-Locked Contract style atomic swaps between
Maxwell specialty chains (and discoverable peer networks).

Flow:
  1. Alice locks asset on Chain A with hashlock H = hash(secret)
  2. Bob locks asset on Chain B with same hashlock H
  3. Alice reveals secret on Chain B → claims Bob's asset
  4. Bob uses same secret on Chain A → claims Alice's asset
  Or: timeouts refund if secret never revealed

All lock / claim / refund events are Maxwell-signed blocks.
Digital twin / software simulation only (ledger balances are virtual).
"""

import hashlib
import json
import math
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def dhash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()

def openssl_hash(data: bytes) -> str:
    if HAS_CRYPTO:
        h = hashes.Hash(hashes.SHA256(), backend=default_backend())
        h.update(data)
        return h.finalize().hex()
    return hashlib.sha256(data).hexdigest()

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ──────────────────────────────────────────────────────────────
# Maxwell signature
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [
        (int.from_bytes(h[i*4:(i+1)*4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
        for i in range(3)
    ]

def maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
    seed = index * 1337
    E = hash_to_vec(data_str, seed)
    H = hash_to_vec(data_str[::-1], seed + 1)
    B = hash_to_vec(data_str, seed + 2)
    raw = hashlib.sha256(data_str.encode()).hexdigest()
    rho = int(raw[:8], 16) / 1e10
    J = [index * 0.01, index * 0.007, index * 0.003]
    dD_dt = [c * 0.1 for c in prev_curl]
    angle = (index % 1.4) % 1.4
    dB_dt = [math.sin(index), math.cos(index), math.tan(angle * 0.5)]
    div_E = sum(E) - (rho / 8.854e-12)
    div_B = sum(B)
    curl_E = [
        E[1] - E[2] + dB_dt[0],
        E[2] - E[0] + dB_dt[1],
        E[0] - E[1] + dB_dt[2],
    ]
    curl_H = [
        H[1] - H[2] - (J[0] + dD_dt[0]),
        H[2] - H[0] - (J[1] + dD_dt[1]),
        H[0] - H[1] - (J[2] + dD_dt[2]),
    ]
    S = [
        E[1]*H[2] - E[2]*H[1],
        E[2]*H[0] - E[0]*H[2],
        E[0]*H[1] - E[1]*H[0],
    ]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15
    return {
        "E": E, "H": H, "B": B,
        "div_E": div_E, "div_B": div_B,
        "curl_E": curl_E, "curl_H": curl_H,
        "poynting": S,
        "impedance": nE / nH,
        "next_curl": curl_E,
        "energy": nE * nH,
    }


# ──────────────────────────────────────────────────────────────
# Block + Chain + simple balances
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(self, index, payload, prev_hash, prev_curl, chain_id, difficulty=3):
        self.index = index
        self.chain_id = chain_id
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0
        self.maxwell = maxwell_signature(dhash(payload), index, prev_curl)
        self.hash = self._calc()

    def _calc(self) -> str:
        c = {
            "index": self.index,
            "chain_id": self.chain_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "div_E": round(self.maxwell["div_E"], 8),
            "div_B": round(self.maxwell["div_B"], 8),
            "Z": round(self.maxwell["impedance"], 8),
        }
        return openssl_hash(json.dumps(c, sort_keys=True, default=str).encode())

    def mine(self):
        target = "0" * self.difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calc()


class MaxwellChain:
    def __init__(self, chain_id: str, difficulty: int = 3):
        self.chain_id = chain_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self.balances: Dict[str, float] = {}
        self.locks: Dict[str, Dict[str, Any]] = {}  # lock_id -> lock state
        genesis = {"type": "genesis", "chain": chain_id}
        b = MaxwellBlock(0, genesis, "0"*64, [0.0, 0.0, 0.0], chain_id, difficulty)
        b.mine()
        self.blocks.append(b)

    def credit(self, account: str, amount: float):
        self.balances[account] = self.balances.get(account, 0.0) + amount

    def add(self, payload: Dict) -> MaxwellBlock:
        prev = self.blocks[-1]
        b = MaxwellBlock(
            len(self.blocks), payload, prev.hash,
            prev.maxwell["next_curl"], self.chain_id, self.difficulty
        )
        b.mine()
        self.blocks.append(b)
        return b

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            if self.blocks[i].previous_hash != self.blocks[i-1].hash:
                return False
        return True


# ──────────────────────────────────────────────────────────────
# HTLC Atomic Swap Engine
# ──────────────────────────────────────────────────────────────

class AtomicSwapEngine:
    """
    Hash Time-Locked Contracts between two Maxwell chains.
    """

    def __init__(self, difficulty: int = 3):
        self.difficulty = difficulty
        self.chains: Dict[str, MaxwellChain] = {}
        for name in ["CHAIN_A", "CHAIN_B", "HUB", "SWAP"]:
            self.chains[name] = MaxwellChain(name, difficulty)
        # seed demo balances
        self.chains["CHAIN_A"].credit("alice", 100.0)
        self.chains["CHAIN_A"].credit("bob", 10.0)
        self.chains["CHAIN_B"].credit("alice", 10.0)
        self.chains["CHAIN_B"].credit("bob", 100.0)
        self.swaps: Dict[str, Dict[str, Any]] = {}
        print("=" * 66)
        print("MAXWELL CROSS-CHAIN ATOMIC SWAPS (HTLC)")
        print("CHAIN_A ↔ CHAIN_B  ·  hashlock + timelock  ·  Maxwell-signed")
        print("=" * 66)

    def _now(self) -> float:
        return time.time()

    def initiate_swap(
        self,
        swap_id: str,
        alice: str,
        bob: str,
        amount_a: float,
        amount_b: float,
        chain_a: str = "CHAIN_A",
        chain_b: str = "CHAIN_B",
        timelock_a_sec: int = 120,
        timelock_b_sec: int = 60,
    ) -> Dict[str, Any]:
        """
        Alice creates secret S, publishes H = hash(S).
        She will lock on chain_a; Bob locks on chain_b with same H.
        Timelock_b < timelock_a so Alice claims first safely.
        """
        secret = secrets.token_bytes(32)
        secret_hex = secret.hex()
        hashlock = sha256_hex(secret)

        swap = {
            "swap_id": swap_id,
            "alice": alice,
            "bob": bob,
            "amount_a": amount_a,
            "amount_b": amount_b,
            "chain_a": chain_a,
            "chain_b": chain_b,
            "hashlock": hashlock,
            "secret": secret_hex,          # Alice keeps this; demo stores for simulation
            "timelock_a": self._now() + timelock_a_sec,
            "timelock_b": self._now() + timelock_b_sec,
            "state": "initiated",
            "lock_a": None,
            "lock_b": None,
            "created_at": ts(),
        }
        self.swaps[swap_id] = swap

        # record intent on SWAP chain
        self.chains["SWAP"].add({
            "type": "swap_initiate",
            "swap_id": swap_id,
            "alice": alice,
            "bob": bob,
            "amount_a": amount_a,
            "amount_b": amount_b,
            "chain_a": chain_a,
            "chain_b": chain_b,
            "hashlock": hashlock,
            "timelock_a": swap["timelock_a"],
            "timelock_b": swap["timelock_b"],
            "ts": ts(),
        })
        self.chains["HUB"].add({
            "type": "cross_link",
            "from_chain": "SWAP",
            "swap_id": swap_id,
            "event": "initiate",
            "ts": ts(),
        })
        return {
            "swap_id": swap_id,
            "hashlock": hashlock,
            "secret_for_alice": secret_hex,  # only initiator should know
            "state": "initiated",
        }

    def lock(
        self,
        swap_id: str,
        party: str,
        which: str,  # "a" or "b"
    ) -> Dict[str, Any]:
        """Lock funds on chain A (Alice) or chain B (Bob)."""
        if swap_id not in self.swaps:
            return {"status": "error", "reason": "unknown_swap"}
        swap = self.swaps[swap_id]
        if which == "a":
            chain = self.chains[swap["chain_a"]]
            locker, amount, counterparty = swap["alice"], swap["amount_a"], swap["bob"]
            timelock = swap["timelock_a"]
            if party != swap["alice"]:
                return {"status": "error", "reason": "only_alice_locks_a"}
        else:
            chain = self.chains[swap["chain_b"]]
            locker, amount, counterparty = swap["bob"], swap["amount_b"], swap["alice"]
            timelock = swap["timelock_b"]
            if party != swap["bob"]:
                return {"status": "error", "reason": "only_bob_locks_b"}

        bal = chain.balances.get(locker, 0.0)
        if bal < amount:
            return {"status": "error", "reason": "insufficient_balance", "balance": bal}

        # debit and create lock
        chain.balances[locker] = bal - amount
        lock_id = dhash({"swap_id": swap_id, "which": which, "hashlock": swap["hashlock"]})[:20]
        lock = {
            "lock_id": lock_id,
            "swap_id": swap_id,
            "which": which,
            "locker": locker,
            "recipient": counterparty,
            "amount": amount,
            "hashlock": swap["hashlock"],
            "timelock": timelock,
            "state": "locked",
        }
        chain.locks[lock_id] = lock
        if which == "a":
            swap["lock_a"] = lock_id
        else:
            swap["lock_b"] = lock_id

        block = chain.add({
            "type": "htlc_lock",
            "lock_id": lock_id,
            "swap_id": swap_id,
            "locker": locker,
            "recipient": counterparty,
            "amount": amount,
            "hashlock": swap["hashlock"],
            "timelock": timelock,
            "ts": ts(),
        })
        self.chains["SWAP"].add({
            "type": "swap_lock",
            "swap_id": swap_id,
            "which": which,
            "lock_id": lock_id,
            "block_hash": block.hash,
            "ts": ts(),
        })
        swap["state"] = "locked_partial" if (swap["lock_a"] is None or swap["lock_b"] is None) else "both_locked"
        return {"status": "locked", "lock_id": lock_id, "block": block.index, "state": swap["state"]}

    def claim(
        self,
        swap_id: str,
        claimer: str,
        which: str,
        secret_hex: str,
    ) -> Dict[str, Any]:
        """
        Claim locked funds by revealing secret.
        secret must satisfy hash(secret) == hashlock.
        """
        if swap_id not in self.swaps:
            return {"status": "error", "reason": "unknown_swap"}
        swap = self.swaps[swap_id]
        lock_id = swap["lock_a"] if which == "a" else swap["lock_b"]
        if not lock_id:
            return {"status": "error", "reason": "no_lock"}

        chain_name = swap["chain_a"] if which == "a" else swap["chain_b"]
        chain = self.chains[chain_name]
        lock = chain.locks.get(lock_id)
        if not lock or lock["state"] != "locked":
            return {"status": "error", "reason": "lock_unavailable"}

        if self._now() > lock["timelock"]:
            return {"status": "error", "reason": "timelock_expired_use_refund"}

        # verify hashlock
        try:
            secret_bytes = bytes.fromhex(secret_hex)
        except ValueError:
            return {"status": "error", "reason": "bad_secret_hex"}
        if sha256_hex(secret_bytes) != lock["hashlock"]:
            return {"status": "error", "reason": "hashlock_mismatch"}

        if claimer != lock["recipient"]:
            return {"status": "error", "reason": "not_recipient"}

        # pay recipient
        chain.balances[claimer] = chain.balances.get(claimer, 0.0) + lock["amount"]
        lock["state"] = "claimed"
        lock["secret_revealed"] = secret_hex

        block = chain.add({
            "type": "htlc_claim",
            "lock_id": lock_id,
            "swap_id": swap_id,
            "claimer": claimer,
            "amount": lock["amount"],
            "secret": secret_hex,  # revealed on-chain
            "hashlock": lock["hashlock"],
            "ts": ts(),
        })
        self.chains["SWAP"].add({
            "type": "swap_claim",
            "swap_id": swap_id,
            "which": which,
            "claimer": claimer,
            "secret_used": True,
            "block_hash": block.hash,
            "ts": ts(),
        })
        # if both claimed, complete
        la = chain.locks.get(swap["lock_a"] or "", {})
        lb = self.chains[swap["chain_b"]].locks.get(swap["lock_b"] or "", {})
        if la.get("state") == "claimed" and lb.get("state") == "claimed":
            swap["state"] = "completed"
        else:
            swap["state"] = "claim_partial"
        return {
            "status": "claimed",
            "block": block.index,
            "amount": lock["amount"],
            "swap_state": swap["state"],
        }

    def refund(self, swap_id: str, which: str, party: str) -> Dict[str, Any]:
        """Refund locker after timelock expiry."""
        if swap_id not in self.swaps:
            return {"status": "error", "reason": "unknown_swap"}
        swap = self.swaps[swap_id]
        lock_id = swap["lock_a"] if which == "a" else swap["lock_b"]
        if not lock_id:
            return {"status": "error", "reason": "no_lock"}
        chain_name = swap["chain_a"] if which == "a" else swap["chain_b"]
        chain = self.chains[chain_name]
        lock = chain.locks.get(lock_id)
        if not lock or lock["state"] != "locked":
            return {"status": "error", "reason": "lock_unavailable"}
        if self._now() <= lock["timelock"]:
            return {"status": "error", "reason": "timelock_not_expired"}
        if party != lock["locker"]:
            return {"status": "error", "reason": "only_locker_refunds"}

        chain.balances[party] = chain.balances.get(party, 0.0) + lock["amount"]
        lock["state"] = "refunded"
        block = chain.add({
            "type": "htlc_refund",
            "lock_id": lock_id,
            "swap_id": swap_id,
            "locker": party,
            "amount": lock["amount"],
            "ts": ts(),
        })
        self.chains["SWAP"].add({
            "type": "swap_refund",
            "swap_id": swap_id,
            "which": which,
            "block_hash": block.hash,
            "ts": ts(),
        })
        swap["state"] = "refunded_partial"
        return {"status": "refunded", "block": block.index, "amount": lock["amount"]}

    def balances(self) -> Dict[str, Dict[str, float]]:
        return {name: dict(ch.balances) for name, ch in self.chains.items()
                if name in ("CHAIN_A", "CHAIN_B")}

    def status(self):
        print("\n── Balances ──")
        for cname, bals in self.balances().items():
            print(f"  {cname}: {bals}")
        print("\n── Chains ──")
        for name, ch in self.chains.items():
            print(f"  {name:8} blocks={len(ch.blocks):2}  valid={ch.validate()}")
        print("\n── Swaps ──")
        for sid, s in self.swaps.items():
            print(f"  {sid}: state={s['state']}  H={s['hashlock'][:16]}…")


# ──────────────────────────────────────────────────────────────
# Demo: successful atomic swap
# ──────────────────────────────────────────────────────────────

def main():
    eng = AtomicSwapEngine(difficulty=3)

    print("\n── Initial balances ──")
    for c, b in eng.balances().items():
        print(f"  {c}: {b}")

    print("\n── 1. Alice initiates swap ──")
    print("  Alice wants 40 on CHAIN_B; offers 25 on CHAIN_A to Bob")
    init = eng.initiate_swap(
        swap_id="swap_001",
        alice="alice",
        bob="bob",
        amount_a=25.0,
        amount_b=40.0,
        timelock_a_sec=3600,   # Alice's lock longer
        timelock_b_sec=1800,   # Bob's lock shorter
    )
    print(f"  hashlock={init['hashlock'][:24]}…")
    secret = init["secret_for_alice"]

    print("\n── 2. Alice locks on CHAIN_A ──")
    print(" ", eng.lock("swap_001", "alice", "a"))

    print("\n── 3. Bob locks on CHAIN_B (same hashlock) ──")
    print(" ", eng.lock("swap_001", "bob", "b"))

    print("\n── 4. Alice claims on CHAIN_B (reveals secret) ──")
    print(" ", eng.claim("swap_001", "alice", "b", secret))

    print("\n── 5. Bob claims on CHAIN_A (uses revealed secret) ──")
    print(" ", eng.claim("swap_001", "bob", "a", secret))

    print("\n── Final balances ──")
    for c, b in eng.balances().items():
        print(f"  {c}: {b}")

    eng.status()

    print("\nAtomic swap properties:")
    print("  • Same hashlock H on both chains")
    print("  • Secret reveal on one chain enables claim on the other")
    print("  • Timelocks allow refund if counterparty never locks/claims")
    print("  • All lock/claim/refund events are Maxwell-signed blocks")
    print("  • SWAP + HUB chains provide audit trail")


if __name__ == "__main__":
    main()
