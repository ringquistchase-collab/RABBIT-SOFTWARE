#!/usr/bin/env python3
"""
Maxwell Lightning-Style Routing
===============================
Save as: maxwell_lightning_routing.py
Run:     python3 maxwell_lightning_routing.py

Lightning-inspired payment channel routing on Maxwell chains:
  • Bidirectional payment channels (virtual balances)
  • Network graph + Dijkstra pathfinding (fee-aware)
  • Multi-hop HTLC along the path
  • Onion-style hop instructions (simplified)
  • Channel open / route / settle / fail → Maxwell-signed blocks

Digital twin / software simulation only.
"""

import hashlib
import json
import math
import heapq
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Set

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

def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


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
    S = [E[1]*H[2]-E[2]*H[1], E[2]*H[0]-E[0]*H[2], E[0]*H[1]-E[1]*H[0]]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15
    return {
        "div_E": div_E, "div_B": div_B,
        "curl_E": curl_E, "curl_H": curl_H,
        "poynting": S, "impedance": nE / nH,
        "next_curl": curl_E, "energy": nE * nH,
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
# Payment channel graph
# ──────────────────────────────────────────────────────────────

class Channel:
    def __init__(
        self,
        channel_id: str,
        node_u: str,
        node_v: str,
        capacity: float,
        balance_u: float,
        base_fee: float = 1.0,
        fee_rate: float = 0.001,  # proportional
        cltv_delta: int = 40,
    ):
        self.channel_id = channel_id
        self.node_u = node_u
        self.node_v = node_v
        self.capacity = capacity
        # balance_u = funds on u's side; balance_v = capacity - balance_u
        self.balance_u = balance_u
        self.base_fee = base_fee
        self.fee_rate = fee_rate
        self.cltv_delta = cltv_delta
        self.active = True

    @property
    def balance_v(self) -> float:
        return self.capacity - self.balance_u

    def fee_to_forward(self, amount: float, from_node: str) -> float:
        return self.base_fee + amount * self.fee_rate

    def can_forward(self, amount: float, from_node: str) -> bool:
        if not self.active:
            return False
        if from_node == self.node_u:
            return self.balance_u >= amount
        if from_node == self.node_v:
            return self.balance_v >= amount
        return False

    def apply_forward(self, amount: float, from_node: str) -> bool:
        if not self.can_forward(amount, from_node):
            return False
        if from_node == self.node_u:
            self.balance_u -= amount
        else:
            self.balance_u += amount  # v sends toward u → u side increases
        return True

    def peer(self, node: str) -> Optional[str]:
        if node == self.node_u:
            return self.node_v
        if node == self.node_v:
            return self.node_u
        return None

    def to_public(self) -> Dict:
        """Gossip view: capacity known, balances private."""
        return {
            "channel_id": self.channel_id,
            "nodes": [self.node_u, self.node_v],
            "capacity": self.capacity,
            "base_fee": self.base_fee,
            "fee_rate": self.fee_rate,
            "cltv_delta": self.cltv_delta,
            "active": self.active,
        }


class ChannelGraph:
    def __init__(self):
        self.channels: Dict[str, Channel] = {}
        self.adj: Dict[str, List[str]] = {}  # node -> [channel_ids]

    def add_channel(self, ch: Channel):
        self.channels[ch.channel_id] = ch
        self.adj.setdefault(ch.node_u, []).append(ch.channel_id)
        self.adj.setdefault(ch.node_v, []).append(ch.channel_id)

    def neighbors(self, node: str) -> List[Tuple[str, Channel]]:
        out = []
        for cid in self.adj.get(node, []):
            ch = self.channels[cid]
            peer = ch.peer(node)
            if peer:
                out.append((peer, ch))
        return out

    def dijkstra_path(
        self,
        source: str,
        target: str,
        amount: float,
    ) -> Optional[Tuple[List[str], List[str], float]]:
        """
        Fee-aware pathfinding (Lightning-style).
        Cost = fee + small hop penalty.
        Returns (node_path, channel_ids, total_fee) or None.
        """
        # dist[node] = (cost, amount_needed_at_node)
        dist = {source: (0.0, amount)}
        prev: Dict[str, Tuple[str, str]] = {}  # node -> (prev_node, channel_id)
        pq = [(0.0, source, amount)]  # cost, node, amt_to_deliver_here

        while pq:
            cost, node, amt = heapq.heappop(pq)
            if node == target:
                break
            if cost > dist.get(node, (1e18,))[0]:
                continue
            for peer, ch in self.neighbors(node):
                # fee charged by this channel to forward `amt` toward peer
                fee = ch.fee_to_forward(amt, node)
                send_amt = amt + fee  # must send more upstream to cover fee
                if not ch.can_forward(send_amt, node):
                    # try without requiring full private balance knowledge:
                    # use capacity as upper bound for pathfinding (LN uncertainty)
                    if send_amt > ch.capacity:
                        continue
                new_cost = cost + fee + 0.01  # hop penalty
                if new_cost < dist.get(peer, (1e18,))[0]:
                    dist[peer] = (new_cost, amt)
                    prev[peer] = (node, ch.channel_id)
                    heapq.heappush(pq, (new_cost, peer, amt))

        if target not in prev and source != target:
            return None

        # reconstruct
        nodes = [target]
        cids = []
        cur = target
        while cur != source:
            if cur not in prev:
                return None
            pnode, cid = prev[cur]
            cids.append(cid)
            nodes.append(pnode)
            cur = pnode
        nodes.reverse()
        cids.reverse()
        total_fee = dist[target][0]
        return nodes, cids, total_fee


# ──────────────────────────────────────────────────────────────
# Lightning-style router on Maxwell
# ──────────────────────────────────────────────────────────────

class MaxwellLightning:
    def __init__(self, difficulty: int = 3):
        self.graph = ChannelGraph()
        self.chain = MaxwellChain("LIGHTNING", difficulty)
        self.hub = MaxwellChain("HUB", difficulty)
        self.pending_htlcs: Dict[str, Dict] = {}
        print("=" * 66)
        print("MAXWELL LIGHTNING-STYLE ROUTING")
        print("Channels · Dijkstra pathfinding · multi-hop HTLC · Maxwell chain")
        print("=" * 66)

    def open_channel(
        self,
        node_u: str,
        node_v: str,
        capacity: float,
        balance_u: float,
        base_fee: float = 1.0,
        fee_rate: float = 0.001,
    ) -> Channel:
        cid = dhash({"u": node_u, "v": node_v, "c": capacity})[:16]
        ch = Channel(cid, node_u, node_v, capacity, balance_u, base_fee, fee_rate)
        self.graph.add_channel(ch)
        self.chain.add({
            "type": "channel_open",
            "channel": ch.to_public(),
            "balance_u_commit": dhash(balance_u),  # private balance not revealed
            "ts": ts(),
        })
        self.hub.add({
            "type": "cross_link",
            "from_chain": "LIGHTNING",
            "event": "channel_open",
            "channel_id": cid,
            "ts": ts(),
        })
        return ch

    def pay(
        self,
        sender: str,
        receiver: str,
        amount: float,
    ) -> Dict[str, Any]:
        """Source-based pathfind + multi-hop HTLC simulate."""
        found = self.graph.dijkstra_path(sender, receiver, amount)
        if not found:
            self.chain.add({
                "type": "payment_fail",
                "sender": sender,
                "receiver": receiver,
                "amount": amount,
                "reason": "no_path",
                "ts": ts(),
            })
            return {"status": "fail", "reason": "no_path"}

        nodes, cids, total_fee = found
        secret = secrets.token_bytes(32)
        hashlock = sha256_hex(secret)
        payment_id = dhash({"s": sender, "r": receiver, "a": amount, "h": hashlock})[:20]

        # Build hop amounts (fees accumulate backward)
        # Simplified: each hop forwards `amount` + remaining downstream fees
        hop_amounts = []
        amt = amount
        for i in range(len(cids) - 1, -1, -1):
            ch = self.graph.channels[cids[i]]
            from_node = nodes[i]
            fee = ch.fee_to_forward(amt, from_node)
            hop_amounts.append(amt + fee)
            amt = amt + fee
        hop_amounts.reverse()

        # Onion-style instructions (simplified: list of hops)
        onion = []
        for i, cid in enumerate(cids):
            onion.append({
                "hop": i,
                "channel_id": cid,
                "from": nodes[i],
                "to": nodes[i + 1],
                "amount": hop_amounts[i],
                "hashlock": hashlock,
            })

        # Attempt forward along path
        for hop in onion:
            ch = self.graph.channels[hop["channel_id"]]
            if not ch.apply_forward(hop["amount"], hop["from"]):
                self.chain.add({
                    "type": "payment_fail",
                    "payment_id": payment_id,
                    "reason": "insufficient_liquidity",
                    "failed_hop": hop,
                    "ts": ts(),
                })
                return {"status": "fail", "reason": "liquidity", "hop": hop}

        # Success: record route + settlement (secret revealed at end)
        self.pending_htlcs[payment_id] = {
            "hashlock": hashlock,
            "secret": secret.hex(),
            "path": nodes,
            "channels": cids,
        }
        block = self.chain.add({
            "type": "payment_route",
            "payment_id": payment_id,
            "sender": sender,
            "receiver": receiver,
            "amount": amount,
            "total_fee": total_fee,
            "path": nodes,
            "channels": cids,
            "hashlock": hashlock,
            "onion_commit": dhash(onion),
            "ts": ts(),
        })
        # settle: reveal secret
        self.chain.add({
            "type": "payment_settle",
            "payment_id": payment_id,
            "secret": secret.hex(),
            "hashlock": hashlock,
            "ts": ts(),
        })
        self.hub.add({
            "type": "cross_link",
            "from_chain": "LIGHTNING",
            "event": "payment_settle",
            "payment_id": payment_id,
            "ts": ts(),
        })
        return {
            "status": "success",
            "payment_id": payment_id,
            "path": nodes,
            "channels": cids,
            "total_fee": total_fee,
            "block": block.index,
            "hashlock": hashlock,
        }

    def status(self):
        print("\n── Channels ──")
        for ch in self.graph.channels.values():
            print(f"  {ch.channel_id[:10]}…  {ch.node_u}-{ch.node_v}  "
                  f"cap={ch.capacity}  bal_u={ch.balance_u:.1f}  "
                  f"fee={ch.base_fee}+{ch.fee_rate}")
        print(f"\n── LIGHTNING chain blocks={len(self.chain.blocks)}  "
              f"valid={self.chain.validate()}")
        print(f"── HUB chain blocks={len(self.hub.blocks)}  "
              f"valid={self.hub.validate()}")


def main():
    ln = MaxwellLightning(difficulty=3)

    # Topology: Alice — R1 — R2 — Bob
    #            \      |
    #             --- R3 ---
    print("\n── Open channels ──")
    ln.open_channel("Alice", "R1", capacity=100, balance_u=60, base_fee=1, fee_rate=0.001)
    ln.open_channel("R1", "R2", capacity=80, balance_u=40, base_fee=1, fee_rate=0.002)
    ln.open_channel("R2", "Bob", capacity=100, balance_u=50, base_fee=1, fee_rate=0.001)
    ln.open_channel("Alice", "R3", capacity=50, balance_u=30, base_fee=2, fee_rate=0.001)
    ln.open_channel("R3", "R2", capacity=60, balance_u=30, base_fee=1, fee_rate=0.001)
    ln.open_channel("R1", "Bob", capacity=40, balance_u=20, base_fee=3, fee_rate=0.002)
    print("  6 channels opened")

    print("\n── Pay Alice → Bob (amount=10) ──")
    result = ln.pay("Alice", "Bob", 10.0)
    print(f"  status={result['status']}")
    if result["status"] == "success":
        print(f"  path={' → '.join(result['path'])}")
        print(f"  fee≈{result['total_fee']:.4f}")
        print(f"  payment_id={result['payment_id']}")
        print(f"  hashlock={result['hashlock'][:20]}…")

    print("\n── Pay Alice → Bob again (amount=5) ──")
    result2 = ln.pay("Alice", "Bob", 5.0)
    print(f"  status={result2['status']}  path={result2.get('path')}")

    ln.status()

    print("\nMapped from Lightning:")
    print("  • Channel graph + public capacity / fees")
    print("  • Dijkstra pathfinding with fee + hop cost")
    print("  • Multi-hop forward with hashlock")
    print("  • Secret reveal settles payment")
    print("  • All opens/routes/settles on Maxwell LIGHTNING + HUB chains")


if __name__ == "__main__":
    main()
