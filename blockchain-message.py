"""
Message relay bridge — open, queued, blockchain-anchored.

WHAT THIS IS:
  A relay that sits between APIs and carries messages between them,
  even when one side is temporarily offline, rate-limited, or requires
  authentication the sender doesn't have directly. The relay holds
  authorized credentials for services on both sides and delivers on
  behalf of someone who has authorized it on both ends.

WHAT THIS IS NOT:
  A way to bypass authentication or access APIs without authorization.
  If a service requires a key, the relay uses a key that was legitimately
  provided to it. It does not break into locked systems -- it bridges
  between them for parties who hold access to both sides.

THREE CORE FEATURES:

  1. OFFLINE QUEUE: messages destined for an unavailable endpoint are
     stored locally and delivered automatically when the endpoint comes
     back online. The sender gets a receipt immediately; the relay handles
     the rest.

  2. PRESENCE BEACON: even when this research API is temporarily offline,
     the relay broadcasts "this resource exists at this address and will
     be available" -- so peers can discover it, queue their own messages,
     and connect when it returns. Anchored to the blockchain so the
     announcement is tamper-evident.

  3. PROOF OF RELAY: every delivered message gets a blockchain anchor
     proving it was relayed at a specific moment -- useful for research
     audit trails, data provenance, and inter-institution trust.

ONLINE/OFFLINE OPERATION:
  The relay runs continuously. When a target is reachable, it delivers
  immediately. When not, it queues and retries with exponential backoff.
  Messages never expire unless you explicitly set a TTL. If the relay
  itself goes offline and comes back, it reads its own queue from disk
  and resumes delivery.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional

import requests
from flask import Flask, request, jsonify


app = Flask(__name__)
_queue_lock = threading.Lock()
QUEUE_PATH = "relay_queue.json"
RELAY_LOG_PATH = "relay_log.json"
NODE_URL = "http://localhost:5001"
SELF_URL = "http://localhost:9500"


# ---------------------------------------------------------------------------
# Queued message

@dataclass
class RelayMessage:
    message_id: str
    created_at: float
    sender_id: str
    target_url: str              # where to deliver this
    payload: Dict[str, Any]
    method: str = "POST"         # HTTP method to use for delivery
    headers: Dict[str, str] = field(default_factory=dict)
    ttl_seconds: Optional[float] = None   # None = never expire
    attempts: int = 0
    last_attempt: float = 0.0
    delivered: bool = False
    delivered_at: Optional[float] = None
    proof_hash: Optional[str] = None      # blockchain anchor hash after delivery

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return time.time() > self.created_at + self.ttl_seconds

    def next_retry_at(self) -> float:
        """Exponential backoff: 5s, 10s, 20s, 40s, 80s, then every 2 min."""
        backoff = min(5.0 * (2 ** self.attempts), 120.0)
        return self.last_attempt + backoff


# ---------------------------------------------------------------------------
# Queue persistence

def _load_queue() -> List[RelayMessage]:
    try:
        with open(QUEUE_PATH) as f:
            return [RelayMessage(**m) for m in json.load(f)]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_queue(messages: List[RelayMessage]):
    with open(QUEUE_PATH, "w") as f:
        json.dump([asdict(m) for m in messages], f, indent=2)


def _append_log(entry: Dict[str, Any]):
    try:
        with open(RELAY_LOG_PATH) as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log = []
    log.append(entry)
    with open(RELAY_LOG_PATH, "w") as f:
        json.dump(log[-500:], f, indent=2)  # keep last 500 entries


# ---------------------------------------------------------------------------
# Relay endpoints

@app.route("/relay/send", methods=["POST"])
def relay_send():
    """
    Accept a message for relay to another endpoint.
    Returns a receipt immediately -- delivery happens in the background.
    The sender doesn't need to know whether the target is online.

    Body:
      {
        "target_url": "https://other-api.example.com/endpoint",
        "payload": { ... any JSON ... },
        "sender_id": "my-service-id",
        "method": "POST",          -- optional, default POST
        "headers": { ... },        -- optional auth headers for the target
        "ttl_seconds": 3600        -- optional, null = never expire
      }
    """
    data = request.get_json(force=True)
    msg = RelayMessage(
        message_id=hashlib.sha256(
            f"{data.get('sender_id')}{time.time()}".encode()
        ).hexdigest()[:16],
        created_at=time.time(),
        sender_id=data.get("sender_id", "anonymous"),
        target_url=data.get("target_url", ""),
        payload=data.get("payload", {}),
        method=data.get("method", "POST").upper(),
        headers=data.get("headers", {}),
        ttl_seconds=data.get("ttl_seconds"),
    )

    if not msg.target_url:
        return jsonify({"error": "target_url required"}), 400

    with _queue_lock:
        queue = _load_queue()
        queue.append(msg)
        _save_queue(queue)

    return jsonify({
        "status": "queued",
        "message_id": msg.message_id,
        "target": msg.target_url,
        "note": "Delivery will happen automatically. "
                "If target is offline, the relay will retry with backoff.",
    }), 202


@app.route("/relay/status/<message_id>", methods=["GET"])
def relay_status(message_id):
    """Check delivery status of a queued message."""
    with _queue_lock:
        queue = _load_queue()
    for msg in queue:
        if msg.message_id == message_id:
            return jsonify({
                "message_id": message_id,
                "delivered": msg.delivered,
                "delivered_at": msg.delivered_at,
                "attempts": msg.attempts,
                "proof_hash": msg.proof_hash,
                "target": msg.target_url,
            })
    return jsonify({"error": "message not found"}), 404


@app.route("/relay/queue", methods=["GET"])
def relay_queue_status():
    """Current queue state -- how many pending, delivered, expired."""
    with _queue_lock:
        queue = _load_queue()
    pending = [m for m in queue if not m.delivered and not m.is_expired()]
    delivered = [m for m in queue if m.delivered]
    expired = [m for m in queue if m.is_expired() and not m.delivered]
    return jsonify({
        "pending": len(pending),
        "delivered": len(delivered),
        "expired": len(expired),
        "total": len(queue),
    })


@app.route("/relay/log", methods=["GET"])
def relay_log():
    """Delivery history with blockchain proof hashes."""
    try:
        with open(RELAY_LOG_PATH) as f:
            return jsonify({"entries": json.load(f)})
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"entries": []})


# ---------------------------------------------------------------------------
# Presence beacon

@app.route("/relay/beacon", methods=["GET"])
def presence_beacon():
    """
    Public presence announcement -- any peer, bot, or external service
    can call this to discover that this relay and the research API it
    serves exists, even if the research API itself is temporarily offline.

    This is the "always-on presence" part: the relay stays up and responds
    here even when the system it's bridging to is down for maintenance,
    rate-limited, or in a different network. The beacon tells the world
    "come back and try -- the resource is real and will be available."
    """
    services_status = {}
    for name, url in [("research_api", "http://localhost:5050"),
                       ("chain_node", "http://localhost:5001"),
                       ("beacon_provider", "http://localhost:7001")]:
        try:
            r = requests.get(url, timeout=2)
            services_status[name] = "online"
        except requests.RequestException:
            services_status[name] = "offline_but_reachable_via_relay"

    return jsonify({
        "relay_id": "mutation-blockchain-research-relay",
        "relay_url": SELF_URL,
        "developer": "Chase Allen Ringquist, Bixby OK",
        "inspiration": "github.com/Rabbitsoftware",
        "protocol_spec": "PROTOCOL.md (see /relay/protocol)",
        "services": services_status,
        "queue_depth": len([m for m in _load_queue() if not m.delivered]),
        "message": (
            "This relay is always open for research data communication. "
            "Even if an upstream service is temporarily offline, send your "
            "message here and it will be delivered when the service returns. "
            "No gatekeeping. No paywall. MIT licensed."
        ),
        "announced_at": time.time(),
    })


@app.route("/relay/protocol", methods=["GET"])
def protocol_info():
    """Returns the protocol specification so external services know how to integrate."""
    try:
        with open("PROTOCOL.md") as f:
            return f.read(), 200, {"Content-Type": "text/markdown"}
    except FileNotFoundError:
        return jsonify({"error": "PROTOCOL.md not found -- see outputs/PROTOCOL.md"}), 404


def _anchor_delivery(message_id: str, target_url: str,
                      delivered_at: float) -> Optional[str]:
    """Anchors proof of relay delivery to the blockchain."""
    try:
        proof = {
            "event": "relay_delivery",
            "message_id_hash": hashlib.sha256(message_id.encode()).hexdigest()[:16],
            "target_hash": hashlib.sha256(target_url.encode()).hexdigest()[:16],
            "delivered_at": delivered_at,
        }
        resp = requests.post(f"{NODE_URL}/mutations", json=proof, timeout=10)
        resp.raise_for_status()
        return resp.json()["block"]["hash"]
    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# Background delivery loop

def delivery_loop(poll_interval: float = 3.0):
    print("[relay] Delivery loop started")
    while True:
        time.sleep(poll_interval)
        with _queue_lock:
            queue = _load_queue()

        now = time.time()
        changed = False
        for msg in queue:
            if msg.delivered or msg.is_expired():
                continue
            if msg.attempts > 0 and now < msg.next_retry_at():
                continue  # still in backoff window

            try:
                resp = requests.request(
                    method=msg.method,
                    url=msg.target_url,
                    json=msg.payload,
                    headers=msg.headers,
                    timeout=8,
                )
                if resp.status_code < 400:
                    msg.delivered = True
                    msg.delivered_at = time.time()
                    msg.proof_hash = _anchor_delivery(
                        msg.message_id, msg.target_url, msg.delivered_at
                    )
                    print(f"[relay] Delivered {msg.message_id} -> {msg.target_url} "
                          f"(proof: {msg.proof_hash and msg.proof_hash[:12]}...)")
                    _append_log({
                        "message_id": msg.message_id,
                        "target": msg.target_url,
                        "delivered_at": msg.delivered_at,
                        "attempts": msg.attempts + 1,
                        "proof_hash": msg.proof_hash,
                    })
                else:
                    print(f"[relay] Failed {msg.message_id} -> {msg.target_url} "
                          f"({resp.status_code}), will retry")
            except requests.RequestException as e:
                print(f"[relay] Unreachable: {msg.target_url} -- queued, "
                      f"retry #{msg.attempts + 1}: {e}")

            msg.attempts += 1
            msg.last_attempt = now
            changed = True

        if changed:
            with _queue_lock:
                _save_queue(queue)


def announce_presence(node_url: str = NODE_URL):
    """Anchors a presence beacon to the blockchain so peers can find this relay."""
    try:
        proof = {
            "event": "relay_presence_beacon",
            "relay_url": SELF_URL,
            "developer": "Chase Allen Ringquist, Bixby OK",
            "announced_at": time.time(),
        }
        resp = requests.post(f"{node_url}/mutations", json=proof, timeout=10)
        if resp.status_code == 200:
            block = resp.json()["block"]
            print(f"[relay] Presence anchored: block {block['index']}, "
                  f"hash {block['hash'][:16]}...")
    except requests.RequestException as e:
        print(f"[relay] Could not anchor presence (chain may be offline): {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9500)
    parser.add_argument("--node-url", type=str, default="http://localhost:5001")
    parser.add_argument("--self-url", type=str, default="http://localhost:9500")
    args = parser.parse_args()

    NODE_URL = args.node_url
    SELF_URL = args.self_url

    # Start the delivery loop in the background
    t = threading.Thread(target=delivery_loop, args=(3.0,), daemon=True)
    t.start()

    # Announce presence to the blockchain
    announce_presence(NODE_URL)

    print(f"[relay] Bridge running on port {args.port}")
    print(f"[relay] Beacon: GET http://localhost:{args.port}/relay/beacon")
    print(f"[relay] Send:   POST http://localhost:{args.port}/relay/send")
    print(f"[relay] Queue:  GET http://localhost:{args.port}/relay/queue")

    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=args.port)
