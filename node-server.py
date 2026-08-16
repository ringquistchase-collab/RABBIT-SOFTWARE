"""
Real HTTP node for the mutation-blockchain network.

Run one instance per node, each on its own port, each pointed at the other
nodes as peers:

    python3 node_server.py --port 5001 --peers http://localhost:5002,http://localhost:5003
    python3 node_server.py --port 5002 --peers http://localhost:5001,http://localhost:5003
    python3 node_server.py --port 5003 --peers http://localhost:5001,http://localhost:5002

Endpoints:
    GET  /chain              -> full chain for this node
    GET  /validate            -> whether this node's own chain is internally valid
    POST /mutations           -> submit a mutation/prediction record; THIS node mines
                                  it, appends it, then pushes the mined block to peers
    POST /blocks               -> receive an already-mined block from a peer
    GET  /peers                -> list this node's known peers
    POST /peers                -> add a peer at runtime {"peer": "http://host:port"}

Consensus: simple longest-valid-chain rule. When a node receives a block that
doesn't extend its current tip, it fetches the sender's full chain and, if
that chain is longer and valid, replaces its own (standard "longest chain
wins" resolution used in toy blockchain implementations).
"""

import argparse
import threading
from dataclasses import asdict

import requests
from flask import Flask, request, jsonify

from mutation_blockchain_pipeline import (
    Block, Blockchain, mine_block, maxwell_signature,
)

app = Flask(__name__)
chain_lock = threading.Lock()

# populated in __main__
blockchain: Blockchain = None
peers: set[str] = set()
DIFFICULTY = 4


def block_to_dict(b: Block) -> dict:
    return asdict(b)


def block_from_dict(d: dict) -> Block:
    return Block(
        index=d["index"], timestamp=d["timestamp"],
        prediction_record=d["prediction_record"], maxwell_sig=d["maxwell_sig"],
        previous_hash=d["previous_hash"], nonce=d["nonce"], hash=d["hash"],
    )


@app.route("/chain", methods=["GET"])
def get_chain():
    with chain_lock:
        return jsonify({
            "length": len(blockchain.chain),
            "chain": [block_to_dict(b) for b in blockchain.chain],
        })


@app.route("/validate", methods=["GET"])
def validate():
    with chain_lock:
        return jsonify({"valid": blockchain.is_valid(), "length": len(blockchain.chain)})


@app.route("/peers", methods=["GET"])
def list_peers():
    return jsonify({"peers": sorted(peers)})


@app.route("/peers", methods=["POST"])
def add_peer():
    data = request.get_json(force=True)
    peer = data.get("peer")
    if peer:
        peers.add(peer.rstrip("/"))
    return jsonify({"peers": sorted(peers)})


@app.route("/mutations", methods=["POST"])
def submit_mutation():
    """Accepts a prediction/mutation record, mines it locally, appends it,
    then broadcasts the mined block to every known peer over real HTTP."""
    record = request.get_json(force=True)

    with chain_lock:
        sig = maxwell_signature(record)
        new_block = Block(
            index=blockchain.latest_block().index + 1,
            timestamp=__import__("time").time(),
            prediction_record=record,
            maxwell_sig=sig,
            previous_hash=blockchain.latest_block().hash,
        )
        mined = mine_block(new_block, DIFFICULTY)
        blockchain.chain.append(mined)
        mined_dict = block_to_dict(mined)

    _broadcast_block(mined_dict)
    return jsonify({"status": "mined", "block": mined_dict}), 201


def _broadcast_block(block_dict: dict):
    for peer in list(peers):
        try:
            requests.post(f"{peer}/blocks", json=block_dict, timeout=3)
        except requests.RequestException as e:
            print(f"[warn] could not reach peer {peer}: {e}")


@app.route("/blocks", methods=["POST"])
def receive_block():
    """Receives an already-mined block from a peer. If it extends our current
    tip, accept it directly. If not, resolve via longest-valid-chain."""
    data = request.get_json(force=True)
    incoming = block_from_dict(data)

    with chain_lock:
        tip = blockchain.latest_block()

        # Case 1: block extends our chain cleanly
        if incoming.previous_hash == tip.hash and incoming.index == tip.index + 1:
            if incoming.hash == incoming.compute_hash() and incoming.hash.startswith("0" * DIFFICULTY):
                blockchain.chain.append(incoming)
                return jsonify({"status": "accepted", "length": len(blockchain.chain)}), 201
            return jsonify({"status": "rejected", "reason": "invalid hash/proof"}), 400

        # Case 2: doesn't extend our tip -- ask the sender's peer list for their
        # full chain and resolve via longest-valid-chain.
        sender_candidates = list(peers)
        for peer in sender_candidates:
            try:
                resp = requests.get(f"{peer}/chain", timeout=3)
                remote = resp.json()["chain"]
                remote_chain = [block_from_dict(b) for b in remote]
                candidate = Blockchain(difficulty=DIFFICULTY)
                candidate.chain = remote_chain
                if len(candidate.chain) > len(blockchain.chain) and candidate.is_valid():
                    blockchain.chain = candidate.chain
                    return jsonify({"status": "replaced", "length": len(blockchain.chain)}), 200
            except requests.RequestException:
                continue

        return jsonify({"status": "ignored", "reason": "no longer valid chain found"}), 200


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--peers", type=str, default="", help="Comma-separated peer base URLs")
    parser.add_argument("--difficulty", type=int, default=4)
    args = parser.parse_args()

    DIFFICULTY = args.difficulty
    blockchain = Blockchain(difficulty=DIFFICULTY)
    peers = set(p.strip().rstrip("/") for p in args.peers.split(",") if p.strip())

    print(f"Node starting on port {args.port} with peers: {sorted(peers)}")
    app.run(host="0.0.0.0", port=args.port)
