"""
CRISPR guide-design stage.

Takes a confirmed somatic mutation (from the trajectory/mutation-calling
stage) and simulates designing a corrective guide RNA around it, plus a toy
off-target risk estimate.

IMPORTANT — what this is and isn't:
- This is a SIMPLIFIED SIMULATION for pipeline-architecture purposes, not a
  real bioinformatics tool. Real guide design needs the actual reference
  genome sequence flanking the mutation (we don't have one loaded here --
  no genome FASTA is attached to this conversation), real PAM-site
  scanning against that sequence, and a validated off-target model (e.g.
  CFD score, Cas-OFFinder alignment against the whole genome).
- Because we don't have a real reference genome available, the "flanking
  sequence" here is deterministically generated from the variant's
  position as a stand-in -- it is NOT the person's actual DNA sequence at
  that locus. Treat every score/sequence this module produces as
  illustrative, not usable for any real editing decision.
- Same privacy pattern as person_profile.py: only a hash reference and a
  minimal derived score go on-chain; the full guide design goes in the
  off-chain store.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any

from person_profile import OffChainStore, sha256_str, sha256_obj


PAM = "NGG"  # SpCas9 canonical PAM, most common Cas9 variant


@dataclass
class GuideDesign:
    target_gene: str
    target_locus: str          # "chr:pos"
    guide_sequence: str        # 20nt guide, simulated
    pam_site: str
    on_target_score: float     # 0-1, simulated
    off_target_risk: float     # 0-1, simulated (higher = riskier)
    predicted_off_target_sites: int
    simulated: bool = True     # always True -- flags this as not-real-bio


def _deterministic_flank(chromosome: str, position: int, length: int = 23) -> str:
    """
    Generates a deterministic pseudo-sequence seeded by locus, standing in
    for a real reference-genome lookup (we have no genome FASTA loaded).
    Same locus always yields the same sequence, so results are reproducible,
    but this is NOT the person's real DNA sequence.
    """
    rng = random.Random(f"{chromosome}:{position}")
    return "".join(rng.choice("ACGT") for _ in range(length))


def design_guide_rna(gene: str, chromosome: str, position: int) -> GuideDesign:
    seq = _deterministic_flank(chromosome, position, length=23)
    guide_seq = seq[:20]
    pam_site = seq[20:23]

    # Toy scoring -- NOT a validated on-target/off-target model.
    rng = random.Random(f"score:{chromosome}:{position}")
    gc_content = (guide_seq.count("G") + guide_seq.count("C")) / len(guide_seq)
    on_target = round(min(1.0, 0.4 + gc_content * 0.6 + rng.uniform(-0.05, 0.05)), 3)
    off_target_risk = round(max(0.0, rng.uniform(0.05, 0.4)), 3)
    predicted_sites = rng.randint(0, 5)

    return GuideDesign(
        target_gene=gene,
        target_locus=f"{chromosome}:{position}",
        guide_sequence=guide_seq,
        pam_site=pam_site,
        on_target_score=on_target,
        off_target_risk=off_target_risk,
        predicted_off_target_sites=predicted_sites,
    )


def build_crispr_record(person_id: str, mutation_record: Dict[str, Any],
                         guide: GuideDesign, store: OffChainStore) -> Dict[str, Any]:
    """
    Same on-chain/off-chain split as build_integrated_record: full guide
    design detail (sequence, scores) goes off-chain; on-chain gets only a
    hash reference plus a go/no-go-style summary flag.
    """
    full_bundle = {
        "person_id": person_id,
        "mutation": mutation_record,
        "guide_design": asdict(guide),
        "generated_at": time.time(),
    }
    bundle_hash = sha256_obj(full_bundle)
    store.save_bundle(bundle_hash, full_bundle)

    # Simple viability flag -- real triage would be far more involved and
    # would sit behind clinical/regulatory review, not a threshold like this.
    viable_candidate = guide.on_target_score > 0.6 and guide.off_target_risk < 0.25

    on_chain_record = {
        "person_id_hash": sha256_str(person_id),
        "off_chain_ref": bundle_hash,
        "target_gene": guide.target_gene,
        "viable_candidate": viable_candidate,
        "timestamp": time.time(),
    }
    return on_chain_record
