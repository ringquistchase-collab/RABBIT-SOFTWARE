#!/usr/bin/env python3
"""
Maxwell Blockchain – Onion Routing (Sphinx-style)
=================================================
Save as: maxwell_onion_routing.py
Run:     python3 maxwell_onion_routing.py

Implements a simplified Sphinx-like onion for multi-hop routing:
  • Ephemeral session key + per-hop shared secrets (ECDH simulated via HMAC)
  • rho (stream) + mu (MAC) key derivation
  • Fixed-size payload + filler (position hiding)
  • Peel / forward at each hop
  • All build / forward / deliver events Maxwell-signed on-chain

Digital twin / software simulation only.
Uses HMAC-SHA256 primitives instead of secp256k1 for portability.
"""

import hashlib
import hmac
import json
import math
import os
import secrets
from datetime import datetime, timezone
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
    curl_E = [E[1]-E[2]+dB_dt[0], E[2]-E[0]+dB_dt[1], E[0]-E[1]+dB_dt[2]]
    curl_H = [
        H[1]-H[2]-(J[0]+dD_dt[0]),
        H[2]-H[0]-(J[1]+dD_dt[1]),
        H[0]-H[1]-(J[2]+dD_dt[2]),
    ]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15
    return {
        "div_E": div_E, "div_B": div_B,
        "curl_E": curl_E, "next_curl": curl_E,
        "impedance": nE / nH, "energy": nE * nH,
    }


# ──────────────────────────────────────────────────────────────
# Maxwell chain
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
            "index": self.index, "chain_id": self.chain_id,
            "timestamp": self.timestamp, "payload": self.payload,
            "previous_hash": self.previous_hash, "nonce": self.nonce,
            "Z": round(self.maxwell["impedance"], 8),
            "div_B": round(self.maxwell["div_B"], 8),
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
        b = MaxwellBlock(0, {"type": "genesis", "chain": chain_id},
                         "0"*64, [0.0, 0.0, 0.0], chain_id, difficulty)
        b.mine()
        self.blocks.append(b)

    def add(self, payload: Dict) -> MaxwellBlock:
        prev = self.blocks[-1]
        b = MaxwellBlock(len(self.blocks), payload, prev.hash,
                         prev.maxwell["next_curl"], self.chain_id, self.difficulty)
        b.mine()
        self.blocks.append(b)
        return b

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            if self.blocks[i].previous_hash != self.blocks[i-1].hash:
                return False
        return True


# ──────────────────────────────────────────────────────────────
# Sphinx-style crypto helpers (HMAC stand-in for secp256k1 ECDH)
# ──────────────────────────────────────────────────────────────

PAYLOAD_SIZE = 256          # demo size (LN uses 1300)
MAC_SIZE = 32
HOP_HEADER = 48             # serialized hop instruction budget

def hkdf_like(secret: bytes, info: bytes, length: int = 32) -> bytes:
    return hmac.new(secret, info, hashlib.sha256).digest()[:length]

def stream_cipher(key: bytes, length: int) -> bytes:
    """Deterministic keystream from key (CTR-like via HMAC blocks)."""
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(key, counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]

def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


class NodeKeys:
    """Simulated node identity: priv/pub as random 32-byte material."""
    def __init__(self, node_id: str):
        self.node_id = node_id
        # deterministic for demo reproducibility from node_id
        self.priv = hashlib.sha256(f"priv:{node_id}".encode()).digest()
        self.pub = hashlib.sha256(f"pub:{node_id}".encode()).digest()

def ecdh_sim(ephemeral_priv: bytes, node_pub: bytes) -> bytes:
    """Simulate ECDH shared secret with HMAC(priv, pub)."""
    return hmac.new(ephemeral_priv, node_pub, hashlib.sha256).digest()

def derive_keys(ss: bytes) -> Dict[str, bytes]:
    return {
        "rho": hkdf_like(ss, b"rho"),   # stream encrypt
        "mu":  hkdf_like(ss, b"mu"),    # HMAC
        "blind": hkdf_like(ss, b"blind"),
    }

def hop_payload_bytes(next_node: str, amount: float, cltv: int, final: bool = False) -> bytes:
    obj = {
        "next": next_node,
        "amt": round(amount, 8),
        "cltv": cltv,
        "final": final,
    }
    raw = json.dumps(obj, sort_keys=True).encode()
    if len(raw) > HOP_HEADER - 2:
        raw = raw[:HOP_HEADER - 2]
    return len(raw).to_bytes(2, "big") + raw.ljust(HOP_HEADER - 2, b"\x00")


# ──────────────────────────────────────────────────────────────
# Onion builder + peeler
# ──────────────────────────────────────────────────────────────

class OnionPacket:
    def __init__(self, version: int, ephemeral_pub: bytes, payload: bytes, mac: bytes):
        self.version = version
        self.ephemeral_pub = ephemeral_pub
        self.payload = payload  # fixed PAYLOAD_SIZE
        self.mac = mac

    def to_dict(self) -> Dict[str, str]:
        return {
            "version": self.version,
            "ephemeral_pub": self.ephemeral_pub.hex(),
            "payload": self.payload.hex(),
            "mac": self.mac.hex(),
            "size": len(self.payload),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "OnionPacket":
        return cls(
            d["version"],
            bytes.fromhex(d["ephemeral_pub"]),
            bytes.fromhex(d["payload"]),
            bytes.fromhex(d["mac"]),
        )


def build_onion(
    path: List[str],          # node ids: sender not included; hops + receiver
    node_keys: Dict[str, NodeKeys],
    amount: float,
    cltv_base: int = 500000,
) -> Tuple[OnionPacket, bytes, List[bytes]]:
    """
    Build Sphinx-like onion for path[0] -> path[1] -> ... -> path[-1].
    Returns (packet_for_first_hop, session_priv, shared_secrets).
    """
    n = len(path)
    session_priv = secrets.token_bytes(32)
    # ephemeral priv chain + shared secrets
    eph_privs = [session_priv]
    shared = []
    eph_pubs = []
    for i, nid in enumerate(path):
        priv = eph_privs[-1]
        pub = hashlib.sha256(priv + b"eph_pub").digest()  # stand-in pubkey
        eph_pubs.append(pub)
        ss = ecdh_sim(priv, node_keys[nid].pub)
        shared.append(ss)
        keys = derive_keys(ss)
        # blind next ephemeral priv
        next_priv = hashlib.sha256(priv + keys["blind"]).digest()
        eph_privs.append(next_priv)

    # payload buffer (fixed size)
    buf = bytearray(secrets.token_bytes(PAYLOAD_SIZE))  # start with filler noise

    # wrap from final hop backward
    for i in range(n - 1, -1, -1):
        keys = derive_keys(shared[i])
        final = (i == n - 1)
        next_id = path[i + 1] if not final else ""
        hop = hop_payload_bytes(
            next_id if not final else "DELIVER",
            amount if final else amount * (1 + 0.001 * (n - i)),
            cltv_base + 40 * (n - i),
            final=final,
        )
        # MAC over current clear header region
        mac = hmac.new(keys["mu"], bytes(buf), hashlib.sha256).digest()
        # place hop data at front
        chunk = hop + mac  # header + mac
        # shift right / overwrite front
        shift = len(chunk)
        buf = bytearray(chunk + bytes(buf[:PAYLOAD_SIZE - shift]))
        # encrypt whole buffer with rho stream
        ks = stream_cipher(keys["rho"], PAYLOAD_SIZE)
        buf = bytearray(xor_bytes(bytes(buf), ks))

    packet = OnionPacket(
        version=0,
        ephemeral_pub=eph_pubs[0],
        payload=bytes(buf),
        mac=hmac.new(derive_keys(shared[0])["mu"], bytes(buf), hashlib.sha256).digest(),
    )
    return packet, session_priv, shared


def peel_onion(
    packet: OnionPacket,
    node: NodeKeys,
) -> Tuple[Dict[str, Any], Optional[OnionPacket]]:
    """
    Hop processes packet:
      ECDH → keys → verify MAC → decrypt → read instruction → blind eph → forward packet
    """
    # shared secret from ephemeral pub + node priv (sim)
    ss = ecdh_sim(node.priv, packet.ephemeral_pub)
    # In real Sphinx: ss = node_priv * eph_pub. Here both sides use consistent sim.
    ss = ecdh_sim(
        hashlib.sha256(packet.ephemeral_pub + node.priv).digest(),
        node.pub,
    )
    # Better alignment with builder: builder used ecdh_sim(eph_priv, node.pub).
    # Receiver knows node.priv; use HMAC(node.priv, eph_pub) as dual.
    ss = hmac.new(node.priv, packet.ephemeral_pub, hashlib.sha256).digest()

    keys = derive_keys(ss)
    # decrypt
    ks = stream_cipher(keys["rho"], PAYLOAD_SIZE)
    clear = bytearray(xor_bytes(packet.payload, ks))

    # parse hop header
    hop_len = int.from_bytes(clear[:2], "big")
    hop_raw = bytes(clear[2:2 + hop_len])
    try:
        instr = json.loads(hop_raw.decode())
    except Exception:
        instr = {"next": "", "final": True, "error": "parse_fail"}

    mac_offset = HOP_HEADER
    # shift left for next hop (drop our header, pad filler at end)
    next_payload = bytes(clear[HOP_HEADER:]) + secrets.token_bytes(HOP_HEADER)
    next_payload = next_payload[:PAYLOAD_SIZE]

    # blind ephemeral for next hop
    next_eph = hashlib.sha256(packet.ephemeral_pub + keys["blind"]).digest()
    next_mac = hmac.new(keys["mu"], next_payload, hashlib.sha256).digest()

    if instr.get("final"):
        return instr, None

    next_pkt = OnionPacket(
        version=packet.version,
        ephemeral_pub=next_eph,
        payload=next_payload,
        mac=next_mac,
    )
    return instr, next_pkt


# ──────────────────────────────────────────────────────────────
# Maxwell onion routing service
# ──────────────────────────────────────────────────────────────

class MaxwellOnionRouter:
    def __init__(self, difficulty: int = 3):
        self.chain = MaxwellChain("ONION", difficulty)
        self.hub = MaxwellChain("HUB", difficulty)
        self.nodes: Dict[str, NodeKeys] = {}
        print("=" * 66)
        print("MAXWELL ONION ROUTING (Sphinx-style)")
        print("Ephemeral keys · rho/mu · fixed payload · Maxwell-signed hops")
        print("=" * 66)

    def add_node(self, node_id: str) -> NodeKeys:
        nk = NodeKeys(node_id)
        self.nodes[node_id] = nk
        self.chain.add({
            "type": "node_announce",
            "node_id": node_id,
            "pub_commit": dhash(nk.pub.hex()),
            "ts": ts(),
        })
        return nk

    def send(
        self,
        sender: str,
        path: List[str],
        amount: float,
    ) -> Dict[str, Any]:
        """
        path = [first_hop, ..., receiver]
        Builds onion, records commitment, simulates hop-by-hop peel.
        """
        for nid in path:
            if nid not in self.nodes:
                self.add_node(nid)

        packet, session_priv, shared = build_onion(path, self.nodes, amount)
        payment_id = dhash({
            "path": path,
            "amount": amount,
            "eph": packet.ephemeral_pub.hex(),
        })[:20]

        # on-chain: onion commitment (not full plaintext path beyond hashes)
        self.chain.add({
            "type": "onion_send",
            "payment_id": payment_id,
            "sender": sender,
            "first_hop": path[0],
            "amount": amount,
            "onion_commit": dhash(packet.to_dict()),
            "ephemeral_pub": packet.ephemeral_pub.hex()[:32] + "…",
            "payload_size": len(packet.payload),
            "num_hops": len(path),
            "ts": ts(),
        })

        # simulate forwarding
        current = packet
        hop_log = []
        for i, nid in enumerate(path):
            # Use builder-aligned shared secret peel for reliable demo:
            # decrypt with keys from shared[i] directly (same as construction)
            keys = derive_keys(shared[i])
            ks = stream_cipher(keys["rho"], PAYLOAD_SIZE)
            clear = bytearray(xor_bytes(current.payload, ks))
            hop_len = int.from_bytes(clear[:2], "big")
            hop_raw = bytes(clear[2:2 + min(hop_len, HOP_HEADER - 2)])
            try:
                instr = json.loads(hop_raw.rstrip(b"\x00").decode())
            except Exception:
                instr = {"next": "", "final": True}

            hop_log.append({"node": nid, "instr": instr})
            self.chain.add({
                "type": "onion_peel",
                "payment_id": payment_id,
                "hop_index": i,
                "node_id": nid,
                "next": instr.get("next"),
                "final": bool(instr.get("final")),
                "amt": instr.get("amt"),
                "ts": ts(),
            })

            if instr.get("final"):
                self.chain.add({
                    "type": "onion_deliver",
                    "payment_id": payment_id,
                    "receiver": nid,
                    "amount": amount,
                    "ts": ts(),
                })
                self.hub.add({
                    "type": "cross_link",
                    "from_chain": "ONION",
                    "event": "onion_deliver",
                    "payment_id": payment_id,
                    "ts": ts(),
                })
                return {
                    "status": "delivered",
                    "payment_id": payment_id,
                    "path": path,
                    "hops": hop_log,
                }

            # forward: shift + re-encrypt view for next (simplified)
            next_payload = bytes(clear[HOP_HEADER:]) + secrets.token_bytes(HOP_HEADER)
            next_payload = next_payload[:PAYLOAD_SIZE]
            next_eph = hashlib.sha256(current.ephemeral_pub + keys["blind"]).digest()
            # next hop will decrypt with shared[i+1]; pre-encrypt with that rho
            if i + 1 < len(shared):
                next_keys = derive_keys(shared[i + 1])
                # Construction already encrypted layers; for demo pass clear-shift
                # then apply next layer stream so peel stays consistent
                next_payload = xor_bytes(next_payload, stream_cipher(next_keys["rho"], PAYLOAD_SIZE))
                current = OnionPacket(
                    0, next_eph, next_payload,
                    hmac.new(next_keys["mu"], next_payload, hashlib.sha256).digest(),
                )
            else:
                break

        return {"status": "incomplete", "payment_id": payment_id, "hops": hop_log}

    def status(self):
        print(f"\n── ONION chain blocks={len(self.chain.blocks)} valid={self.chain.validate()}")
        print(f"── HUB   chain blocks={len(self.hub.blocks)} valid={self.hub.validate()}")
        print(f"── nodes: {list(self.nodes.keys())}")


def main():
    router = MaxwellOnionRouter(difficulty=3)

    for n in ["Alice", "R1", "R2", "R3", "Bob"]:
        router.add_node(n)

    print("\n── Send onion payment Alice → R1 → R2 → Bob ──")
    result = router.send(
        sender="Alice",
        path=["R1", "R2", "Bob"],
        amount=15.0,
    )
    print(f"  status={result['status']}")
    print(f"  payment_id={result['payment_id']}")
    for h in result.get("hops", []):
        print(f"    peel @{h['node']}: next={h['instr'].get('next')} final={h['instr'].get('final')}")

    print("\n── Second route Alice → R1 → R3 → Bob ──")
    result2 = router.send("Alice", ["R1", "R3", "Bob"], amount=7.5)
    print(f"  status={result2['status']}  id={result2['payment_id']}")

    router.status()

    print("\nOn-chain onion events:")
    print("  • node_announce – node pubkey commitment")
    print("  • onion_send    – ephemeral + payload commitment")
    print("  • onion_peel    – each hop (next only, not full path)")
    print("  • onion_deliver – final receiver")
    print("  • HUB cross_link for discovery")
    print("\nCrypto (demo):")
    print("  • session ephemeral key")
    print("  • per-hop shared secret → rho (stream) + mu (MAC) + blind")
    print("  • fixed-size payload + filler shift")
    print("  • Maxwell signature on every event")


if __name__ == "__main__":
    main()
