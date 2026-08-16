"""
Mutation-to-Blockchain Pipeline
================================

Implements the flow:

    CANCER SAMPLE
        -> DNA / mutation data
        -> NORMAL vs TUMOR comparison
        -> mutation trajectory
        -> prediction record
        -> Maxwell signature + SHA-256
        -> MINING
        -> BLOCK N (previous_hash -> BLOCK N+1)
        -> NETWORK NODES
        -> chain validation

Notes on interpretation
------------------------
- "Mutation data" is modeled as a simple list of variant calls (gene, position,
  ref/alt allele, variant allele frequency). In a real pipeline this would come
  from a VCF file produced by a somatic variant caller (e.g. Mutect2).
- "Maxwell signature" is not a standard bioinformatics or cryptographic term,
  so this implementation treats it as a custom deterministic feature-weighted
  signature function (distinct from the SHA-256 hash) that summarizes the
  mutation trajectory into a fixed-length fingerprint. Swap `maxwell_signature()`
  out for whatever specific algorithm you actually have in mind.
- "MINING" is implemented as simple proof-of-work (find a nonce so the block
  hash has N leading zero hex digits), same idea as Bitcoin-style mining.
- "NETWORK NODES" are simulated as multiple independent Blockchain instances
  that receive mined blocks and independently validate the chain.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


# ---------------------------------------------------------------------------
# 1. DNA / mutation data
# ---------------------------------------------------------------------------

@dataclass
class Variant:
    gene: str
    chromosome: str
    position: int
    ref: str
    alt: str
    vaf: float  # variant allele frequency, 0.0-1.0

    def key(self) -> str:
        return f"{self.chromosome}:{self.position}:{self.ref}>{self.alt}:{self.gene}"


def known_cancer_cell_variants() -> List[Variant]:
    """
    A small, fixed (non-random) panel of well-known somatic driver mutations,
    standing in for a real single-cell / tumor sequencing readout. Used for
    the streaming demo so results are reproducible rather than randomized.
    """
    return [
        Variant(gene="TP53",  chromosome="17", position=7577121,  ref="C", alt="T", vaf=0.42),  # R175H
        Variant(gene="KRAS",  chromosome="12", position=25245350, ref="C", alt="T", vaf=0.38),   # G12D
        Variant(gene="EGFR",  chromosome="7",  position=55191822, ref="T", alt="G", vaf=0.31),   # L858R
        Variant(gene="PIK3CA",chromosome="3",  position=178952085,ref="A", alt="G", vaf=0.22),   # E545G
        Variant(gene="APC",   chromosome="5",  position=112175639,ref="G", alt="A", vaf=0.15),
    ]


def load_sample_variants(sample_id: str, tumor: bool, seed: int = 0) -> List[Variant]:
    """
    Stand-in for parsing a VCF. Generates a small synthetic variant set so the
    pipeline is runnable end to end. Replace with real VCF parsing
    (e.g. via `cyvcf2` or `pysam`) for actual sequencing data.
    """
    rng = random.Random(f"{sample_id}-{seed}-{tumor}")
    genes = ["TP53", "KRAS", "EGFR", "BRCA1", "PIK3CA", "APC", "PTEN"]
    n_variants = rng.randint(3, 6) if tumor else rng.randint(0, 2)

    variants = []
    for _ in range(n_variants):
        variants.append(
            Variant(
                gene=rng.choice(genes),
                chromosome=str(rng.randint(1, 22)),
                position=rng.randint(1_000_000, 250_000_000),
                ref=rng.choice("ACGT"),
                alt=rng.choice("ACGT"),
                vaf=round(rng.uniform(0.05, 0.6) if tumor else rng.uniform(0.0, 0.03), 3),
            )
        )
    return variants


# ---------------------------------------------------------------------------
# 2. NORMAL vs TUMOR comparison -> mutation trajectory
# ---------------------------------------------------------------------------

def compare_normal_tumor(normal: List[Variant], tumor: List[Variant]) -> Dict[str, Any]:
    """
    Compares normal and tumor variant sets and produces a "mutation
    trajectory": which variants are somatic (tumor-only), shared/germline,
    and an aggregate mutation burden / average VAF.
    """
    normal_keys = {v.key() for v in normal}

    somatic = [v for v in tumor if v.key() not in normal_keys]
    germline = [v for v in tumor if v.key() in normal_keys]

    avg_vaf = round(sum(v.vaf for v in somatic) / len(somatic), 4) if somatic else 0.0

    trajectory = {
        "somatic_variants": [asdict(v) for v in somatic],
        "germline_variants": [asdict(v) for v in germline],
        "tumor_mutation_burden": len(somatic),
        "average_somatic_vaf": avg_vaf,
        "genes_affected": sorted({v.gene for v in somatic}),
    }
    return trajectory


@dataclass
class PatientContext:
    """
    Non-genomic covariates that a real risk model would condition on. None of
    this affects the SHA-256/mining mechanics -- it's just additional fields
    in the record that get hashed in like everything else. The `risk_score`
    heuristic below is adjusted to use them, but this is still a toy formula,
    not a validated clinical model.
    """
    age: int
    sex: str                  # kept as a plain descriptive field
    nutrition_score: float    # 0.0 (poor diet/DNA-repair-relevant deficiency) - 1.0 (good)
    days_since_diagnosis: int


def default_patient_context() -> PatientContext:
    return PatientContext(age=58, sex="F", nutrition_score=0.6, days_since_diagnosis=120)


# ---------------------------------------------------------------------------
# 3. Prediction record
# ---------------------------------------------------------------------------

def build_prediction_record(sample_id: str, trajectory: Dict[str, Any],
                             patient: PatientContext = None) -> Dict[str, Any]:
    """
    Turns a mutation trajectory into a prediction record. `risk_score` here is
    a toy heuristic (burden * avg VAF, adjusted by age/nutrition/time, capped
    at 1.0) -- swap in a real model (e.g. a trained classifier or a Cox
    proportional-hazards model) for anything clinically meaningful.
    """
    burden = trajectory["tumor_mutation_burden"]
    avg_vaf = trajectory["average_somatic_vaf"]
    base_risk = burden * avg_vaf * 0.5

    if patient is None:
        patient = default_patient_context()

    # Toy adjustment factors -- illustrative only, not derived from real
    # epidemiological data:
    age_factor = 1.0 + max(0, patient.age - 50) * 0.01       # risk creeps up past 50
    nutrition_factor = 1.15 - (patient.nutrition_score * 0.3) # poor nutrition (~0) -> 1.15x, good (~1) -> 0.85x
    time_factor = 1.0 + min(patient.days_since_diagnosis, 730) / 3650  # slow drift with time since diagnosis

    risk_score = round(min(1.0, base_risk * age_factor * nutrition_factor * time_factor), 4)

    record = {
        "sample_id": sample_id,
        "timestamp": time.time(),
        "tumor_mutation_burden": burden,
        "average_somatic_vaf": avg_vaf,
        "genes_affected": trajectory["genes_affected"],
        "patient_age": patient.age,
        "patient_sex": patient.sex,
        "nutrition_score": patient.nutrition_score,
        "days_since_diagnosis": patient.days_since_diagnosis,
        "risk_score": risk_score,
    }
    return record


# ---------------------------------------------------------------------------
# 4. Maxwell signature + SHA-256
# ---------------------------------------------------------------------------

def maxwell_signature(record: Dict[str, Any], length: int = 16) -> str:
    """
    Custom deterministic fingerprint of a prediction record, independent of
    the SHA-256 block hash. Weights each field, mixes it through repeated
    hashing rounds, and truncates to `length` hex characters. This is a
    placeholder algorithm -- replace with the actual "Maxwell signature"
    spec if you have one.
    """
    weights = {
        "tumor_mutation_burden": 3,
        "average_somatic_vaf": 5,
        "risk_score": 7,
    }
    payload = ""
    for field_name, weight in weights.items():
        payload += f"{field_name}:{record.get(field_name)}:{weight};"
    payload += "genes:" + ",".join(record.get("genes_affected", []))

    digest = payload.encode()
    for _ in range(weights["risk_score"]):  # a few mixing rounds
        digest = hashlib.sha256(digest).digest()

    return digest.hex()[:length]


def sha256_hash(data: Dict[str, Any]) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialized).hexdigest()


# ---------------------------------------------------------------------------
# 5. Block + mining
# ---------------------------------------------------------------------------

@dataclass
class Block:
    index: int
    timestamp: float
    prediction_record: Dict[str, Any]
    maxwell_sig: str
    previous_hash: str
    nonce: int = 0
    hash: str = ""

    def compute_hash(self) -> str:
        block_body = {
            "index": self.index,
            "timestamp": self.timestamp,
            "prediction_record": self.prediction_record,
            "maxwell_sig": self.maxwell_sig,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }
        return sha256_hash(block_body)


def mine_block(block: Block, difficulty: int = 4) -> Block:
    """
    Simple proof-of-work: increment nonce until the block hash starts with
    `difficulty` leading zero hex digits.
    """
    target_prefix = "0" * difficulty
    while True:
        candidate_hash = block.compute_hash()
        if candidate_hash.startswith(target_prefix):
            block.hash = candidate_hash
            return block
        block.nonce += 1


# ---------------------------------------------------------------------------
# 6. Blockchain (per network node)
# ---------------------------------------------------------------------------

class Blockchain:
    def __init__(self, difficulty: int = 4):
        self.difficulty = difficulty
        self.chain: List[Block] = [self._create_genesis_block()]

    def _create_genesis_block(self) -> Block:
        # Fixed timestamp so every node in the network derives an identical
        # genesis block/hash -- otherwise each node's chain would start from
        # a different root and never validate against a mined block's
        # previous_hash.
        genesis = Block(
            index=0,
            timestamp=0.0,
            prediction_record={"note": "genesis block"},
            maxwell_sig="0" * 16,
            previous_hash="0" * 64,
        )
        genesis.hash = genesis.compute_hash()
        return genesis

    def latest_block(self) -> Block:
        return self.chain[-1]

    def add_prediction(self, prediction_record: Dict[str, Any]) -> Block:
        sig = maxwell_signature(prediction_record)
        new_block = Block(
            index=self.latest_block().index + 1,
            timestamp=time.time(),
            prediction_record=prediction_record,
            maxwell_sig=sig,
            previous_hash=self.latest_block().hash,
        )
        mined = mine_block(new_block, self.difficulty)
        self.chain.append(mined)
        return mined

    def is_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            current, prev = self.chain[i], self.chain[i - 1]
            if current.hash != current.compute_hash():
                return False
            if current.previous_hash != prev.hash:
                return False
            if not current.hash.startswith("0" * self.difficulty):
                return False
        return True


# ---------------------------------------------------------------------------
# 7. Network of nodes + chain validation across the network
# ---------------------------------------------------------------------------

class Network:
    """Simulates several nodes, each holding its own copy of the chain."""

    def __init__(self, n_nodes: int = 3, difficulty: int = 4):
        self.nodes = [Blockchain(difficulty=difficulty) for _ in range(n_nodes)]

    def broadcast_prediction(self, prediction_record: Dict[str, Any]) -> None:
        """One node mines the block; the mined block is then propagated
        (re-appended, not re-mined) to every other node, mirroring how a
        real P2P network shares an already-solved block."""
        miner = self.nodes[0]
        mined_block = miner.add_prediction(prediction_record)

        for node in self.nodes[1:]:
            replicated = Block(
                index=mined_block.index,
                timestamp=mined_block.timestamp,
                prediction_record=mined_block.prediction_record,
                maxwell_sig=mined_block.maxwell_sig,
                previous_hash=mined_block.previous_hash,
                nonce=mined_block.nonce,
                hash=mined_block.hash,
            )
            node.chain.append(replicated)

    def validate_network(self) -> Dict[str, bool]:
        return {f"node_{i}": node.is_valid() for i, node in enumerate(self.nodes)}

    def consensus_check(self) -> bool:
        """All nodes should have identical chain tip hashes."""
        tip_hashes = {node.latest_block().hash for node in self.nodes}
        return len(tip_hashes) == 1


# ---------------------------------------------------------------------------
# 7b. Streaming / per-mutation mining ("mine it out of the cell as found")
# ---------------------------------------------------------------------------
#
# Instead of waiting for the whole sample to be sequenced and building one
# summary block, this treats the cell as a live variant stream: each variant
# is checked against normal the instant it "arrives". Germline/shared
# variants are discarded. The first time a somatic mutation is confirmed,
# it is immediately packaged into its own small record and mined into its
# own block, chained onto whatever the network's current tip is.

def stream_cell_variants(cell_variants: List[Variant], delay: float = 0.0):
    """Simulates a real-time sequencer emitting one variant call at a time."""
    for v in cell_variants:
        if delay:
            time.sleep(delay)
        yield v


def build_mutation_record(cell_id: str, variant: Variant) -> Dict[str, Any]:
    """A record for a single confirmed somatic mutation (not a whole sample)."""
    return {
        "cell_id": cell_id,
        "gene": variant.gene,
        "chromosome": variant.chromosome,
        "position": variant.position,
        "ref": variant.ref,
        "alt": variant.alt,
        "vaf": variant.vaf,
        "timestamp": time.time(),
    }


def run_streaming_pipeline(cell_id: str, cell_variants: List[Variant],
                            normal_variants: List[Variant], difficulty: int = 4,
                            n_nodes: int = 3, delay: float = 0.0) -> Network:
    """
    Streams variant calls for one cell/sample. Each confirmed somatic
    mutation is mined into its own block the moment it's found -- i.e. the
    mutation is "mined out of the cell block" individually, rather than
    batching the whole sample into one summary block.
    """
    normal_keys = {v.key() for v in normal_variants}
    network = Network(n_nodes=n_nodes, difficulty=difficulty)

    print(f"=== Streaming cell: {cell_id} ({len(cell_variants)} variant calls incoming) ===\n")

    for variant in stream_cell_variants(cell_variants, delay=delay):
        if variant.key() in normal_keys:
            print(f"  [germline/shared] {variant.gene} {variant.chromosome}:{variant.position} "
                  f"{variant.ref}>{variant.alt} -- discarded, not mined")
            continue

        record = build_mutation_record(cell_id, variant)
        t0 = time.time()
        network.broadcast_prediction(record)
        elapsed = time.time() - t0

        mined = network.nodes[0].latest_block()
        valid = all(network.validate_network().values())
        print(f"  [somatic -> MINED] block {mined.index} | {variant.gene} "
              f"{variant.chromosome}:{variant.position} {variant.ref}>{variant.alt} vaf={variant.vaf} "
              f"| nonce={mined.nonce} mined_in={elapsed:.2f}s | hash={mined.hash[:16]}... "
              f"| chain_valid={valid}")

    print(f"\nFinal chain length for {cell_id}: {len(network.nodes[0].chain)} blocks "
          f"(1 genesis + {len(network.nodes[0].chain) - 1} somatic mutations)")
    print(f"Consensus across {n_nodes} nodes: {network.consensus_check()}")
    return network


# ---------------------------------------------------------------------------
# Demo run: full pipeline end to end
# ---------------------------------------------------------------------------

def run_pipeline(sample_id: str, difficulty: int = 4, n_nodes: int = 3) -> None:
    print(f"=== Pipeline run for sample: {sample_id} ===\n")

    # 1. DNA / mutation data
    normal_variants = load_sample_variants(sample_id, tumor=False)
    tumor_variants = load_sample_variants(sample_id, tumor=True)
    print(f"Normal variants: {len(normal_variants)} | Tumor variants: {len(tumor_variants)}")

    # 2. Normal vs tumor -> trajectory
    trajectory = compare_normal_tumor(normal_variants, tumor_variants)
    print(f"Mutation trajectory: burden={trajectory['tumor_mutation_burden']}, "
          f"avg_vaf={trajectory['average_somatic_vaf']}, genes={trajectory['genes_affected']}")

    # 3. Prediction record
    record = build_prediction_record(sample_id, trajectory)
    print(f"Prediction record: risk_score={record['risk_score']}")

    # 4. Signatures
    sig = maxwell_signature(record)
    h = sha256_hash(record)
    print(f"Maxwell signature: {sig}")
    print(f"SHA-256:            {h}\n")

    # 5-7. Mining + network of nodes + validation
    print(f"Mining block on a {n_nodes}-node network (difficulty={difficulty})...")
    network = Network(n_nodes=n_nodes, difficulty=difficulty)
    network.broadcast_prediction(record)

    mined = network.nodes[0].latest_block()
    print(f"Block {mined.index} mined: hash={mined.hash} nonce={mined.nonce}")
    print(f"previous_hash -> {mined.previous_hash}\n")

    print("Per-node chain validation:", network.validate_network())
    print("Network consensus (all tips match):", network.consensus_check())


def run_continuous(difficulty: int = 4, n_nodes: int = 3, interval: float = 5.0,
                    max_blocks: int | None = None) -> None:
    """
    Runs the pipeline forever (or until `max_blocks` is reached / Ctrl+C):
    generates a new sample, builds a prediction record, mines a block on a
    shared network, and validates the chain across all nodes -- then waits
    `interval` seconds and repeats.
    """
    network = Network(n_nodes=n_nodes, difficulty=difficulty)
    sample_counter = 0

    print(f"Starting continuous run (difficulty={difficulty}, nodes={n_nodes}, "
          f"interval={interval}s). Press Ctrl+C to stop.\n")

    try:
        while max_blocks is None or sample_counter < max_blocks:
            sample_counter += 1
            sample_id = f"PATIENT-{sample_counter:03d}"

            normal_variants = load_sample_variants(sample_id, tumor=False, seed=sample_counter)
            tumor_variants = load_sample_variants(sample_id, tumor=True, seed=sample_counter)
            trajectory = compare_normal_tumor(normal_variants, tumor_variants)
            record = build_prediction_record(sample_id, trajectory)

            t0 = time.time()
            network.broadcast_prediction(record)
            elapsed = time.time() - t0

            mined = network.nodes[0].latest_block()
            validity = network.validate_network()
            consensus = network.consensus_check()

            print(f"[{time.strftime('%H:%M:%S')}] block {mined.index} | {sample_id} | "
                  f"burden={record['tumor_mutation_burden']} risk={record['risk_score']} | "
                  f"nonce={mined.nonce} mined_in={elapsed:.2f}s | hash={mined.hash[:16]}... | "
                  f"nodes_valid={all(validity.values())} consensus={consensus}")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cancer mutation -> blockchain pipeline")
    parser.add_argument("--continuous", action="store_true",
                         help="Run forever, mining one whole-sample block per interval")
    parser.add_argument("--stream", action="store_true",
                         help="Stream a single cell's variants and mine each somatic mutation as it's found")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between blocks in continuous mode")
    parser.add_argument("--delay", type=float, default=0.0, help="Seconds between variant calls in streaming mode")
    parser.add_argument("--difficulty", type=int, default=4, help="Leading zero hex digits required for mining")
    parser.add_argument("--nodes", type=int, default=3, help="Number of simulated network nodes")
    parser.add_argument("--max-blocks", type=int, default=None, help="Stop after this many blocks (continuous mode only)")
    args = parser.parse_args()

    if args.stream:
        cell_variants = known_cancer_cell_variants()
        normal_baseline = load_sample_variants("NORMAL-BASELINE", tumor=False, seed=1)
        run_streaming_pipeline(cell_id="CELL-001", cell_variants=cell_variants,
                                normal_variants=normal_baseline, difficulty=args.difficulty,
                                n_nodes=args.nodes, delay=args.delay)
    elif args.continuous:
        run_continuous(difficulty=args.difficulty, n_nodes=args.nodes,
                        interval=args.interval, max_blocks=args.max_blocks)
    else:
        run_pipeline(sample_id="PATIENT-001", difficulty=args.difficulty, n_nodes=args.nodes)
