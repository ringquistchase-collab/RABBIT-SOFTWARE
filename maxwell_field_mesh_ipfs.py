#!/usr/bin/env python3
"""
Maxwell Field Mesh – IPFS + External Connectors Edition
=======================================================
Save as: maxwell_field_mesh_ipfs.py
Run:     python3 maxwell_field_mesh_ipfs.py

Includes:
  - Maxwell field signatures on every block
  - Mesh + gossip + localhost P2P sockets
  - Optional IPFS pinning (local daemon or gateway)
  - Connector stubs for cloud / AI / quantum job interfaces

Digital-twin / software integrity layer only.
No real biological, neural, or medical hardware control.
"""

import hashlib
import json
import math
import random
import socket
import struct
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

# Optional
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def dhash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

def openssl_hash(data: bytes) -> str:
    if HAS_CRYPTO:
        h = hashes.Hash(hashes.SHA256(), backend=default_backend())
        h.update(data)
        return h.finalize().hex()
    return hashlib.sha256(data).hexdigest()


# ──────────────────────────────────────────────────────────────
# Maxwell Field Signature (core)
# ──────────────────────────────────────────────────────────────

def hash_to_vec(data: str, seed: int) -> List[float]:
    h = hashlib.sha256((str(seed) + data).encode()).digest()
    return [(int.from_bytes(h[i*4:(i+1)*4], "big") / 0xFFFFFFFF)*2-1 for i in range(3)]

def compute_maxwell_signature(data_str: str, index: int, prev_curl: List[float]) -> Dict[str, Any]:
    seed = index * 1337
    E = hash_to_vec(data_str, seed)
    H = hash_to_vec(data_str[::-1], seed+1)
    B = hash_to_vec(data_str, seed+2)
    raw = hashlib.sha256(data_str.encode()).hexdigest()
    rho = int(raw[:8], 16) / 1e10
    J = [index*0.01, index*0.007, index*0.003]
    dD_dt = [c*0.1 for c in prev_curl]
    angle = (index % 1.4) % 1.4
    dB_dt = [math.sin(index), math.cos(index), math.tan(angle*0.5)]
    div_E = sum(E) - (rho / 8.854e-12)
    curl_E = [E[1]-E[2]+dB_dt[0], E[2]-E[0]+dB_dt[1], E[0]-E[1]+dB_dt[2]]
    curl_H = [H[1]-H[2]-(J[0]+dD_dt[0]), H[2]-H[0]-(J[1]+dD_dt[1]), H[0]-H[1]-(J[2]+dD_dt[2])]
    div_B = sum(B)
    S = [E[1]*H[2]-E[2]*H[1], E[2]*H[0]-E[0]*H[2], E[0]*H[1]-E[1]*H[0]]
    nE = math.sqrt(sum(x*x for x in E)) or 1e-15
    nH = math.sqrt(sum(x*x for x in H)) or 1e-15
    return {
        "E_field": E, "H_field": H, "B_field": B,
        "div_E_residual": div_E, "curl_E_residual": curl_E,
        "curl_H_residual": curl_H, "div_B": div_B,
        "poynting_vector": S, "wave_impedance": nE/nH,
        "next_curl": curl_E, "field_energy": nE*nH,
    }


# ──────────────────────────────────────────────────────────────
# IPFS Integration (optional)
# ──────────────────────────────────────────────────────────────

class IPFSClient:
    """
    Minimal IPFS client.
    Prefers local daemon (localhost:5001).
    Falls back to public gateway for read-only / demo.
    """
    def __init__(self, api_url: str = "http://127.0.0.1:5001"):
        self.api_url = api_url.rstrip("/")
        self.available = False
        self._check()

    def _check(self):
        if not HAS_REQUESTS:
            print("[IPFS] requests not installed – IPFS disabled")
            return
        try:
            r = requests.post(f"{self.api_url}/api/v0/id", timeout=2)
            if r.status_code == 200:
                self.available = True
                print(f"[IPFS] Connected to local daemon")
            else:
                print("[IPFS] Local daemon not reachable – pinning disabled")
        except Exception:
            print("[IPFS] Local daemon not reachable – pinning disabled")

    def add_json(self, obj: Dict) -> Optional[str]:
        """Add JSON object, return CID (or None)."""
        if not self.available:
            # demo fallback: content-addressed hash only
            return "bafydemo" + dhash(obj)[:40]
        try:
            data = json.dumps(obj, sort_keys=True, default=str).encode()
            files = {"file": ("record.json", data)}
            r = requests.post(f"{self.api_url}/api/v0/add", files=files, timeout=10)
            if r.status_code == 200:
                return r.json().get("Hash")
        except Exception as e:
            print(f"[IPFS] add failed: {e}")
        return None

    def pin(self, cid: str) -> bool:
        if not self.available or not cid:
            return False
        try:
            r = requests.post(f"{self.api_url}/api/v0/pin/add", params={"arg": cid}, timeout=10)
            return r.status_code == 200
        except Exception:
            return False


# ──────────────────────────────────────────────────────────────
# External System Connectors (stubs – safe interfaces only)
# ──────────────────────────────────────────────────────────────

class ExternalConnector:
    """
    Safe software interfaces for external systems.
    These are intentionally high-level and do not control hardware.
    """
    def __init__(self):
        self.log: List[Dict] = []

    def submit_ai_job(self, model: str, payload: Dict) -> Dict:
        """Stub for AI / LLM service."""
        job = {
            "type": "ai_job",
            "model": model,
            "payload_hash": dhash(payload),
            "status": "queued_demo",
            "ts": ts(),
        }
        self.log.append(job)
        return job

    def submit_quantum_job(self, backend: str, circuit_desc: str) -> Dict:
        """Stub for quantum cloud backend (IBM, Google, etc.)."""
        job = {
            "type": "quantum_job",
            "backend": backend,
            "circuit_hash": dhash(circuit_desc),
            "status": "queued_demo",
            "ts": ts(),
        }
        self.log.append(job)
        return job

    def publish_cloud_event(self, topic: str, data: Dict) -> Dict:
        """Stub for cloud pub/sub or object storage event."""
        event = {
            "type": "cloud_event",
            "topic": topic,
            "data_hash": dhash(data),
            "status": "published_demo",
            "ts": ts(),
        }
        self.log.append(event)
        return event


# ──────────────────────────────────────────────────────────────
# Block / Chain / Node (condensed)
# ──────────────────────────────────────────────────────────────

class MaxwellBlock:
    def __init__(self, index, payload, prev_hash, prev_curl, node_id, difficulty=3):
        self.index = index
        self.node_id = node_id
        self.timestamp = ts()
        self.payload = payload
        self.previous_hash = prev_hash
        self.difficulty = difficulty
        self.nonce = 0
        self.maxwell = compute_maxwell_signature(
            json.dumps(payload, sort_keys=True, default=str), index, prev_curl
        )
        self.ipfs_cid: Optional[str] = None
        self.hash = self._calc()

    def _calc(self):
        c = {
            "index": self.index, "node_id": self.node_id, "timestamp": self.timestamp,
            "payload": self.payload, "previous_hash": self.previous_hash, "nonce": self.nonce,
            "div_E": round(self.maxwell["div_E_residual"], 8),
            "div_B": round(self.maxwell["div_B"], 8),
            "impedance": round(self.maxwell["wave_impedance"], 8),
            "ipfs_cid": self.ipfs_cid,
        }
        return openssl_hash(json.dumps(c, sort_keys=True, default=str).encode())

    def mine(self):
        target = "0" * self.difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self._calc()

    def to_dict(self):
        return {
            "index": self.index, "node_id": self.node_id, "timestamp": self.timestamp,
            "payload": self.payload, "previous_hash": self.previous_hash,
            "nonce": self.nonce, "hash": self.hash,
            "maxwell_signature": self.maxwell, "ipfs_cid": self.ipfs_cid,
        }


class MaxwellChain:
    def __init__(self, node_id, difficulty=3):
        self.node_id = node_id
        self.difficulty = difficulty
        self.blocks: List[MaxwellBlock] = []
        self._genesis()

    def _genesis(self):
        p = {"type": "genesis", "node": self.node_id}
        b = MaxwellBlock(0, p, "0"*64, [0.,0.,0.], self.node_id, self.difficulty)
        b.mine()
        self.blocks.append(b)

    def add(self, payload, ipfs: Optional[IPFSClient] = None) -> MaxwellBlock:
        prev = self.blocks[-1]
        b = MaxwellBlock(len(self.blocks), payload, prev.hash,
                         prev.maxwell["next_curl"], self.node_id, self.difficulty)
        if ipfs:
            cid = ipfs.add_json(b.to_dict())
            b.ipfs_cid = cid
            b.hash = b._calc()          # re-hash with CID
            if cid:
                ipfs.pin(cid)
        b.mine()
        self.blocks.append(b)
        return b

    def validate(self) -> bool:
        for i in range(1, len(self.blocks)):
            if self.blocks[i].previous_hash != self.blocks[i-1].hash:
                return False
        return True


class MeshNode:
    def __init__(self, node_id: str, port: int, difficulty: int = 3):
        self.node_id = node_id
        self.port = port
        self.chain = MaxwellChain(node_id, difficulty)
        self.peers: Dict[str, Tuple[str, int]] = {}
        self.energy = 10.0
        self.running = False
        self.server_sock = None

    def start(self):
        self.running = True
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", self.port))
        self.server_sock.listen(5)
        self.server_sock.settimeout(1.0)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while self.running:
            try:
                conn, _ = self.server_sock.accept()
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except Exception:
                continue

    def _handle(self, conn):
        try:
            hdr = conn.recv(4)
            if len(hdr) < 4: return
            ln = struct.unpack("!I", hdr)[0]
            data = b""
            while len(data) < ln:
                data += conn.recv(4096)
            # best-effort receive
        except Exception:
            pass
        finally:
            conn.close()

    def stop(self):
        self.running = False
        if self.server_sock:
            try: self.server_sock.close()
            except: pass

    def add_peer(self, pid, host, port):
        self.peers[pid] = (host, port)

    def status(self):
        last = self.chain.blocks[-1]
        return {
            "node": self.node_id, "port": self.port,
            "blocks": len(self.chain.blocks),
            "peers": len(self.peers),
            "valid": self.chain.validate(),
            "Z": round(last.maxwell["wave_impedance"], 4),
            "cid": last.ipfs_cid,
        }


# ──────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────

class MaxwellFieldMesh:
    def __init__(self, base_port=47100, difficulty=3):
        self.nodes: Dict[str, MeshNode] = {}
        self.base_port = base_port
        self.difficulty = difficulty
        self.ipfs = IPFSClient()
        self.connectors = ExternalConnector()
        print("=" * 64)
        print("MAXWELL FIELD MESH + IPFS + External Connectors")
        print("Software integrity layer only – no biological hardware control")
        print("=" * 64)

    def add_node(self, nid: str) -> MeshNode:
        port = self.base_port + len(self.nodes)
        n = MeshNode(nid, port, self.difficulty)
        n.start()
        self.nodes[nid] = n
        print(f"[+] {nid} @ 127.0.0.1:{port}")
        return n

    def connect_mesh(self, density=0.7):
        ids = list(self.nodes)
        for i, a in enumerate(ids):
            for b in ids[i+1:]:
                if random.random() < density:
                    self.nodes[a].add_peer(b, "127.0.0.1", self.nodes[b].port)
                    self.nodes[b].add_peer(a, "127.0.0.1", self.nodes[a].port)

    def record(self, nid: str, payload: Dict) -> Optional[MaxwellBlock]:
        if nid not in self.nodes:
            return None
        block = self.nodes[nid].chain.add(payload, ipfs=self.ipfs)
        print(f"[{nid}] #{block.index} mined  Z={block.maxwell['wave_impedance']:.3f}  "
              f"CID={str(block.ipfs_cid)[:20]}...")
        return block

    def status(self):
        print("\n── Status ──")
        for n in self.nodes.values():
            s = n.status()
            print(f"  {s['node']:10} blocks={s['blocks']}  peers={s['peers']}  "
                  f"valid={s['valid']}  Z={s['Z']}  cid={str(s['cid'])[:16]}")

    def shutdown(self):
        for n in self.nodes.values():
            n.stop()


def main():
    mesh = MaxwellFieldMesh()
    for name in ["ALPHA", "BETA", "GAMMA", "DELTA"]:
        mesh.add_node(name)
    time.sleep(0.3)
    mesh.connect_mesh()

    # Demo records
    for i in range(5):
        nid = random.choice(list(mesh.nodes))
        payload = {
            "type": "integrity_record",
            "cycle": i,
            "note": "Maxwell + IPFS demo",
            "value": round(random.random(), 4),
        }
        block = mesh.record(nid, payload)

        # Optional external connectors (stubs)
        if i == 2:
            mesh.connectors.submit_ai_job("demo-model", payload)
            mesh.connectors.submit_quantum_job("demo-qpu", "H-gate circuit sketch")
            mesh.connectors.publish_cloud_event("maxwell.records", payload)

    mesh.status()
    print("\nExternal connector log (stubs):")
    for e in mesh.connectors.log:
        print(" ", e)

    print("\nNotes:")
    print(" • IPFS: starts local daemon (`ipfs daemon`) for real pinning")
    print(" • Connectors are safe software stubs only")
    print(" • No biological / neural / medical hardware control")
    mesh.shutdown()


if __name__ == "__main__":
    main()
