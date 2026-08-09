#!/usr/bin/env python3
"""
Maxwell Field Mesh – Full Edition
=================================
Save as: maxwell_field_mesh_full.py
Run:     python3 maxwell_field_mesh_full.py

Features implemented:
  1. Maxwell field signature mathematics on every block
  2. Visualization of E / H / B / Poynting vectors
  3. Gossip protocol for mesh propagation
  4. P2P networking with TCP sockets (localhost demo)

Digital twin / software simulation only.
No real biology, chemicals, RF, or external hardware control.
"""

import hashlib
import json
import math
import random
import socket
import struct
import threading
import time
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

# Optional crypto
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# Optional matplotlib for nicer plots
try:
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def dhash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

def openssl_hash(data: bytes, algo: str = "sha256") -> str:
    algo = algo.lower().replace("-", "_")
    if HAS_CRYPTO:
        mapping = {
            "sha256": hashes.SHA256(),
            "sha3_256": hashes.SHA3_256(),
            "sha384": hashes.SHA384(),
            "sha512": hashes.SHA512(),
        }
        h = hashes.Hash(mapping.get(algo, hashes.SHA256()), backend=default_backend())
        h.update(data)
        return h.finalize().hex()
    return hashlib.sha256(data).hexdigest()


# ──────────────────────────────────────────────────────────────
# Maxwell Field Signature Mathematics
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [(int.from_bytes(h[i*4:(i+1)*4], "big") / 0xFFFFFFFF) * 2.0 - 1.0 for i in range(3)]

def compute_maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
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
    curl_E = [E[1]-E[2]+dB_dt[0], E[2]-E[0]+dB_dt[1], E[0]-E[1]+dB_dt[2]]
    curl_H = [H[1]-H[2]-(J[0]+dD_dt[0]), H[2]-H[0]-(J[1]+dD_dt[1]), H[0]-H[1]-(J[2]+dD_dt[2])]
    div_B = sum(B)
    S = [E[1]*H[2]-E[2]*H[1], E[2]*H[0]-E[0]*H[2], E[0]*H[1]-E[1]*H[0]]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15

    return {
        "E_field": E, "H_field": H, "B_field": B,
        "rho_charge": rho,
        "div_E_residual": div_E,
        "curl_E_residual": curl_E,
        "curl_H_residual": curl_H,
        "div_B": div_B,
        "poynting_vector": S,
        "wave_impedance": nE / nH,
        "next_curl": curl_E,
        "field_energy": nE * nH,
        "field_entropy": sum(abs(x) for x in E + H) / 6.0,
    }


def visualize_vectors(sig: Dict[str, Any], title: str = "Maxwell Fields") -> None:
    """Text + optional 3-D visualization of E, H, B, S."""
    E, H, B, S = sig["E_field"], sig["H_field"], sig["B_field"], sig["poynting_vector"]

    def fmt(v):
        return f"[{v[0]:+.3f}, {v[1]:+.3f}, {v[2]:+.3f}]"

    def mag(v):
        return math.sqrt(sum(x*x for x in v))

    print(f"\n── {title} ──")
    print(f"  E  {fmt(E)}  |E|={mag(E):.3f}")
    print(f"  H  {fmt(H)}  |H|={mag(H):.3f}")
    print(f"  B  {fmt(B)}  |B|={mag(B):.3f}")
    print(f"  S  {fmt(S)}  |S|={mag(S):.3f}  (Poynting)")
    print(f"  Z  = {sig['wave_impedance']:.4f}")
    print(f"  div_E residual = {sig['div_E_residual']:.3e}")
    print(f"  div_B          = {sig['div_B']:.4f}")
    print(f"  energy         = {sig['field_energy']:.4f}")

    if HAS_MPL:
        fig = plt.figure(figsize=(9, 7))
        ax = fig.add_subplot(111, projection="3d")
        origin = [0, 0, 0]
        ax.quiver(*origin, *E, color="r", label="E", arrow_length_ratio=0.15)
        ax.quiver(*origin, *H, color="b", label="H", arrow_length_ratio=0.15)
        ax.quiver(*origin, *B, color="g", label="B", arrow_length_ratio=0.15)
        ax.quiver(*origin, *S, color="m", label="S (Poynting)", arrow_length_ratio=0.15)
        ax.set_xlim([-1.5, 1.5]); ax.set_ylim([-1.5, 1.5]); ax.set_zlim([-1.5, 1.5])
        ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")
        ax.legend()
        ax.set_title(title)
        plt.tight_layout()
        plt.show(block=False)
        plt.pause(1.5)
        plt.close()


# ──────────────────────────────────────────────────────────────
# Block + Chain
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(self, index: int, payload: Dict, previous_hash: str,
                 prev_curl: List[float], node_id: str, difficulty: int = 3):
        self.index = index
        self.node_id = node_id
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = previous_hash
        self.difficulty = difficulty
        self.nonce = 0
        data_str = json.dumps(payload, sort_keys=True, default=str)
        self.maxwell = compute_maxwell_signature(data_str, index, prev_curl)
        self.hash = self._calc()

    def _calc(self) -> str:
        c = {
            "index": self.index, "node_id": self.node_id, "timestamp": self.timestamp,
            "payload": self.payload, "previous_hash": self.previous_hash, "nonce": self.nonce,
            "div_E": round(self.maxwell["div_E_residual"], 8),
            "div_B": round(self.maxwell["div_B"], 8),
            "impedance": round(self.maxwell["wave_impedance"], 8),
            "poynting": [round(v, 8) for v in self.maxwell["poynting_vector"]],
        }
        return openssl_hash(json.dumps(c, sort_keys=True, default=str).encode(), "sha256")

    def mine(self) -> None:
        target = "0" * self.difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calc()

    def to_dict(self) -> Dict:
        return {
            "index": self.index, "node_id": self.node_id, "timestamp": self.timestamp,
            "payload": self.payload, "previous_hash": self.previous_hash,
            "nonce": self.nonce, "hash": self.hash, "maxwell_signature": self.maxwell,
        }


class MaxwellChain:
    def __init__(self, node_id: str, difficulty: int = 3):
        self.node_id = node_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self._genesis()

    def _genesis(self):
        payload = {"type": "genesis", "node_id": self.node_id, "msg": "Maxwell mesh genesis"}
        b = MaxwellBlock(0, payload, "0"*64, [0.0, 0.0, 0.0], self.node_id, self.difficulty)
        b.mine()
        self.blocks.append(b)

    def add(self, payload: Dict) -> MaxwellBlock:
        prev = self.blocks[-1]
        b = MaxwellBlock(len(self.blocks), payload, prev.hash,
                         prev.maxwell["next_curl"], self.node_id, self.difficulty)
        b.mine()
        self.blocks.append(b)
        return b

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            curr, prev = self.blocks[i], self.blocks[i-1]
            if curr.hash != curr._calc() or curr.previous_hash != prev.hash:
                return False
        return True

    def recent_blocks(self, n: int = 5) -> List[Dict]:
        return [b.to_dict() for b in self.blocks[-n:]]


# ──────────────────────────────────────────────────────────────
# Gossip Protocol
# ──────────────────────────────────────────────────────────────

class GossipMessage:
    def __init__(self, msg_type: str, sender: str, payload: Any):
        self.msg_type = msg_type          # "block", "peer_list", "heartbeat", "request_blocks"
        self.sender = sender
        self.payload = payload
        self.timestamp = ts()
        self.id = dhash({"type": msg_type, "sender": sender, "ts": self.timestamp, "p": str(payload)[:64]})

    def to_dict(self) -> Dict:
        return {
            "msg_type": self.msg_type,
            "sender": self.sender,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "GossipMessage":
        m = cls(d["msg_type"], d["sender"], d["payload"])
        m.timestamp = d.get("timestamp", ts())
        m.id = d.get("id", "")
        return m


# ──────────────────────────────────────────────────────────────
# Mesh Node with Gossip + optional Sockets
# ──────────────────────────────────────────────────────────────

class MeshNode:
    def __init__(self, node_id: str, port: int, difficulty: int = 3):
        self.node_id = node_id
        self.port = port
        self.chain = MaxwellChain(node_id, difficulty)
        self.peers: Dict[str, Tuple[str, int]] = {}   # node_id -> (host, port)
        self.seen_msg_ids: Set[str] = set()
        self.energy = 10.0
        self.lock = threading.Lock()
        self.running = False
        self.server_sock: Optional[socket.socket] = None

    def add_peer(self, peer_id: str, host: str, port: int):
        self.peers[peer_id] = (host, port)

    def create_block(self, payload: Dict) -> MaxwellBlock:
        with self.lock:
            block = self.chain.add(payload)
            self.energy += 0.05
            # gossip the new block
            msg = GossipMessage("block", self.node_id, block.to_dict())
            self._gossip(msg)
            return block

    def _gossip(self, msg: GossipMessage, fanout: int = 3):
        """Send message to a random subset of peers (gossip fanout)."""
        if msg.id in self.seen_msg_ids:
            return
        self.seen_msg_ids.add(msg.id)
        # keep seen set bounded
        if len(self.seen_msg_ids) > 5000:
            self.seen_msg_ids = set(list(self.seen_msg_ids)[-2000:])

        targets = list(self.peers.items())
        random.shuffle(targets)
        for peer_id, (host, port) in targets[:fanout]:
            self._send(host, port, msg.to_dict())

    def _send(self, host: str, port: int, data: Dict):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.8)
                s.connect((host, port))
                raw = json.dumps(data).encode()
                s.sendall(struct.pack("!I", len(raw)) + raw)
        except Exception:
            pass  # peer may be down – gossip is best-effort

    def _handle_client(self, conn: socket.socket):
        try:
            header = conn.recv(4)
            if len(header) < 4:
                return
            length = struct.unpack("!I", header)[0]
            data = b""
            while len(data) < length:
                chunk = conn.recv(min(4096, length - len(data)))
                if not chunk:
                    break
                data += chunk
            msg_dict = json.loads(data.decode())
            msg = GossipMessage.from_dict(msg_dict)
            self._on_message(msg)
        except Exception:
            pass
        finally:
            conn.close()

    def _on_message(self, msg: GossipMessage):
        if msg.id in self.seen_msg_ids:
            return
        self.seen_msg_ids.add(msg.id)

        if msg.msg_type == "block":
            # accept foreign block announcement (demo: just record energy)
            self.energy += 0.02
            # re-gossip
            self._gossip(msg)
        elif msg.msg_type == "peer_list":
            for pid, info in msg.payload.items():
                if pid != self.node_id and pid not in self.peers:
                    self.peers[pid] = (info[0], info[1])
        elif msg.msg_type == "heartbeat":
            pass
        elif msg.msg_type == "request_blocks":
            # reply with recent blocks
            recent = self.chain.recent_blocks(3)
            reply = GossipMessage("block", self.node_id, recent)
            if msg.sender in self.peers:
                host, port = self.peers[msg.sender]
                self._send(host, port, reply.to_dict())

    def start_server(self):
        self.running = True
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", self.port))
        self.server_sock.listen(8)
        self.server_sock.settimeout(1.0)

        def loop():
            while self.running:
                try:
                    conn, _ = self.server_sock.accept()
                    t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                    t.start()
                except socket.timeout:
                    continue
                except Exception:
                    break

        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

    def gossip_heartbeat(self):
        msg = GossipMessage("heartbeat", self.node_id, {"energy": self.energy, "blocks": len(self.chain.blocks)})
        self._gossip(msg)

    def gossip_peers(self):
        peer_info = {pid: list(addr) for pid, addr in self.peers.items()}
        peer_info[self.node_id] = ["127.0.0.1", self.port]
        msg = GossipMessage("peer_list", self.node_id, peer_info)
        self._gossip(msg)

    def status(self) -> Dict:
        last = self.chain.blocks[-1]
        return {
            "node_id": self.node_id,
            "port": self.port,
            "blocks": len(self.chain.blocks),
            "peers": list(self.peers.keys()),
            "energy": round(self.energy, 3),
            "valid": self.chain.validate(),
            "last_Z": round(last.maxwell["wave_impedance"], 4),
            "last_hash": last.hash[:14] + "...",
        }


# ──────────────────────────────────────────────────────────────
# Mesh Network Orchestrator
# ──────────────────────────────────────────────────────────────

class MaxwellFieldMesh:
    def __init__(self, base_port: int = 47000, difficulty: int = 3):
        self.base_port = base_port
        self.difficulty = difficulty
        self.nodes: Dict[str, MeshNode] = {}
        print("=" * 68)
        print("MAXWELL FIELD MESH  –  Signatures · Gossip · P2P Sockets · Visualization")
        print("=" * 68)

    def add_node(self, node_id: str) -> MeshNode:
        port = self.base_port + len(self.nodes)
        node = MeshNode(node_id, port, self.difficulty)
        self.nodes[node_id] = node
        node.start_server()
        print(f"[+] {node_id} listening on 127.0.0.1:{port}")
        return node

    def connect_all(self, density: float = 0.8):
        ids = list(self.nodes.keys())
        for i, a in enumerate(ids):
            for b in ids[i+1:]:
                if random.random() < density:
                    na, nb = self.nodes[a], self.nodes[b]
                    na.add_peer(b, "127.0.0.1", nb.port)
                    nb.add_peer(a, "127.0.0.1", na.port)
                    print(f"[↔] {a} ↔ {b}")

    def bootstrap_gossip(self):
        for node in self.nodes.values():
            node.gossip_peers()
            node.gossip_heartbeat()

    def create_record(self, node_id: str, payload: Dict) -> Optional[MaxwellBlock]:
        if node_id not in self.nodes:
            return None
        block = self.nodes[node_id].create_block(payload)
        print(f"[{node_id}] mined #{block.index}  nonce={block.nonce}  "
              f"Z={block.maxwell['wave_impedance']:.3f}  hash={block.hash[:14]}...")
        return block

    def status(self):
        print("\n── Mesh Status ──")
        for n in self.nodes.values():
            s = n.status()
            print(f"  {s['node_id']:12} port={s['port']}  blocks={s['blocks']:2}  "
                  f"peers={len(s['peers'])}  valid={s['valid']}  Z={s['last_Z']:.3f}")

    def shutdown(self):
        for n in self.nodes.values():
            n.stop()


# ──────────────────────────────────────────────────────────────
# Main Demo
# ──────────────────────────────────────────────────────────────

def main():
    mesh = MaxwellFieldMesh(base_port=47000, difficulty=3)

    node_names = ["ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON"]
    for name in node_names:
        mesh.add_node(name)

    time.sleep(0.4)          # let servers start
    mesh.connect_all(density=0.75)
    mesh.bootstrap_gossip()
    time.sleep(0.3)

    print("\n── Creating Maxwell-signed records + gossip propagation ──\n")

    payloads = [
        {"type": "sensor", "value": round(random.random(), 4)},
        {"type": "research", "title": "field continuity study"},
        {"type": "dna_proxy", "hash": dhash("ATGCGTA")},
        {"type": "eeg_proxy", "band": "alpha", "power": round(random.uniform(0.2, 0.9), 3)},
        {"type": "api_fp", "service": "demo", "fp": dhash("secret")[:16]},
    ]

    for i in range(6):
        nid = random.choice(node_names)
        p = random.choice(payloads).copy()
        p["cycle"] = i
        block = mesh.create_record(nid, p)
        if block and i % 2 == 0:
            visualize_vectors(block.maxwell, title=f"{nid} block #{block.index}")
        time.sleep(0.25)

    # final gossip round
    mesh.bootstrap_gossip()
    time.sleep(0.5)

    mesh.status()

    # show one detailed signature
    sample = mesh.nodes["ALPHA"].chain.blocks[-1]
    print("\n── Detailed Maxwell Signature (ALPHA last block) ──")
    visualize_vectors(sample.maxwell, title="ALPHA final block")

    print("\nAll three features active:")
    print("  ✓ Maxwell field vector visualization")
    print("  ✓ Gossip protocol (fanout + peer exchange + heartbeat)")
    print("  ✓ P2P TCP sockets on localhost ports 47000+")
    print("\nShutting down sockets...")
    mesh.shutdown()
    print("Done.")


if __name__ == "__main__":
    main()
