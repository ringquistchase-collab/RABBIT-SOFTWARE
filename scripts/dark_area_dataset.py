#!/usr/bin/env python3
"""
CHASE ALLEN RINGQUIST — Dark Area & Smoke Event Dataset
========================================================
Personal life-event archive: drug/narcotic incidents, injuries,
hospitalizations, and predictive pattern analysis.

Connects to the RabbitOS Supabase schema (life_age_events, mesh_anomalies)
for cross-referencing with biometric risk tiers.

Twin UUID: ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from enum import Enum, auto
from typing import List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class SubstanceType(Enum):
    ALCOHOL    = "Alcohol"
    OPIOID     = "Opioid"
    CANNABIS   = "Cannabis"
    STIMULANT  = "Stimulant"
    BENZO      = "Benzodiazepine"
    PSYCHEDELI = "Psychedelic"
    INHALANT   = "Inhalant"
    UNKNOWN    = "Unknown"


class SubstanceClass(Enum):
    DEPRESSANT  = "Depressant"
    STIMULANT   = "Stimulant"
    ENACTOGEN   = "Enactogen"
    PSYCHEDELIC = "Psychedelic"
    CANNABINOID = "Cannabinoid"
    UNKNOWN     = "Unknown"


class InjuryType(Enum):
    LACERATION      = "Laceration"
    FRACTURE        = "Fracture"
    CONCUSSION      = "Concussion"
    OVERDOSE        = "Overdose"
    BLUNT_TRAUMA    = "Blunt Trauma"
    BURN            = "Burn"
    INTERNAL        = "Internal"
    PSYCHOLOGICAL   = "Psychological"
    NONE            = "None"


class EventSeverity(Enum):
    LOW         = 1
    MODERATE    = 2
    HIGH        = 3
    CRITICAL    = 4
    EXISTENTIAL = 5


class AccessTier(Enum):
    MINIMAL     = "MINIMAL"
    LOW         = "LOW"
    HIGH        = "HIGH"
    CRITICAL    = "CRITICAL"
    EXISTENTIAL = "EXISTENTIAL"


# SubstanceType → SubstanceClass mapping
SUBSTANCE_CLASS_MAP: dict[SubstanceType, SubstanceClass] = {
    SubstanceType.ALCOHOL:    SubstanceClass.DEPRESSANT,
    SubstanceType.OPIOID:     SubstanceClass.DEPRESSANT,
    SubstanceType.BENZO:      SubstanceClass.DEPRESSANT,
    SubstanceType.CANNABIS:   SubstanceClass.CANNABINOID,
    SubstanceType.STIMULANT:  SubstanceClass.STIMULANT,
    SubstanceType.PSYCHEDELI: SubstanceClass.PSYCHEDELIC,
    SubstanceType.INHALANT:   SubstanceClass.DEPRESSANT,
    SubstanceType.UNKNOWN:    SubstanceClass.UNKNOWN,
}

# Medical intervention protocols keyed by SubstanceType
INTERVENTION_PROTOCOLS: dict[SubstanceType, list[str]] = {
    SubstanceType.ALCOHOL:    ["IV fluids", "Thiamine (B1)", "Monitor glucose", "Wernicke prophylaxis"],
    SubstanceType.OPIOID:     ["Naloxone (Narcan) 0.4–2 mg IV/IM/IN", "Airway management", "O2 monitoring", "Repeat dosing q2–3 min PRN"],
    SubstanceType.CANNABIS:   ["Supportive care", "Benzodiazepine for anxiety/psychosis", "Anti-emetics"],
    SubstanceType.STIMULANT:  ["Benzodiazepines for agitation", "Cooling for hyperthermia", "Amphetamine toxicity protocol"],
    SubstanceType.BENZO:      ["Flumazenil (caution — seizure risk)", "Airway support", "Monitor respiratory rate"],
    SubstanceType.PSYCHEDELI: ["Benzodiazepines", "Quiet environment", "Monitor for serotonin syndrome"],
    SubstanceType.INHALANT:   ["O2 therapy", "Cardiac monitoring", "Arrhythmia protocol"],
    SubstanceType.UNKNOWN:    ["Broad-spectrum tox screen", "Supportive care", "Poison control consult"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DarkAreaEvent:
    event_id:        str
    age:             int
    event_date:      date
    label:           str
    description:     str
    severity:        EventSeverity
    access_tier:     AccessTier
    gps:             Optional[tuple[float, float]]  # (lat, lon)
    location_label:  str

    # Substance fields (None if no substance involvement)
    substance_type:  Optional[SubstanceType]  = None
    substance_name:  Optional[str]            = None
    quantity_desc:   Optional[str]            = None

    # Injury / medical fields
    injury_type:     Optional[InjuryType]     = None
    injury_desc:     Optional[str]            = None
    hospital_name:   Optional[str]            = None
    hospital_city:   Optional[str]            = None
    admitted:        bool                     = False
    icu:             bool                     = False
    los_days:        Optional[int]            = None   # length of stay

    # Predictive / pattern fields
    precursor_events:  List[str]   = field(default_factory=list)
    outcome_tags:      List[str]   = field(default_factory=list)
    mesh_snapshot_id:  Optional[str] = None

    @property
    def substance_class(self) -> Optional[SubstanceClass]:
        if self.substance_type is None:
            return None
        return SUBSTANCE_CLASS_MAP.get(self.substance_type, SubstanceClass.UNKNOWN)

    @property
    def intervention_protocol(self) -> list[str]:
        if self.substance_type is None:
            return []
        return INTERVENTION_PROTOCOLS.get(self.substance_type, [])


# ─────────────────────────────────────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DarkAreaDatabase:
    twin_id: str
    twin_name: str
    events: List[DarkAreaEvent] = field(default_factory=list)

    def get(self, event_id: str) -> Optional[DarkAreaEvent]:
        return next((e for e in self.events if e.event_id == event_id), None)

    def by_age(self, age: int) -> List[DarkAreaEvent]:
        return [e for e in self.events if e.age == age]

    def by_substance(self, st: SubstanceType) -> List[DarkAreaEvent]:
        return [e for e in self.events if e.substance_type == st]

    def by_tier(self, tier: AccessTier) -> List[DarkAreaEvent]:
        return [e for e in self.events if e.access_tier == tier]


def build_database() -> DarkAreaDatabase:
    db = DarkAreaDatabase(
        twin_id   = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba",
        twin_name = "Chase Allen Ringquist",
    )

    db.events = [

        # ── Age 7 — 1999 — PTSD (CRITICAL / Airgap) ─────────────────────────
        DarkAreaEvent(
            event_id       = "EVT-1999-PTSD",
            age            = 7,
            event_date     = date(1999, 1, 1),
            label          = "PTSD",
            description    = "Traumatic event onset. 95th-percentile uniqueness. Airgap storage.",
            severity       = EventSeverity.CRITICAL,
            access_tier    = AccessTier.CRITICAL,
            gps            = (35.942, -95.885),
            location_label = "Muskogee County, OK",
            injury_type    = InjuryType.PSYCHOLOGICAL,
            injury_desc    = "Acute trauma response; PTSD onset confirmed",
            outcome_tags   = ["ptsd", "childhood_trauma", "dev_phase_primitive_mesh"],
        ),

        # ── Age 13 — 2005 — First alcohol exposure ───────────────────────────
        DarkAreaEvent(
            event_id       = "EVT-2005-ALC-01",
            age            = 13,
            event_date     = date(2005, 6, 1),
            label          = "First alcohol exposure",
            description    = "Initial binge drinking episode, social context.",
            severity       = EventSeverity.MODERATE,
            access_tier    = AccessTier.HIGH,
            gps            = (35.942, -95.885),
            location_label = "Muskogee County, OK — Party",
            substance_type = SubstanceType.ALCOHOL,
            substance_name = "Alcohol (binge)",
            quantity_desc  = "Estimated 8–10 drinks",
            injury_type    = InjuryType.NONE,
            outcome_tags   = ["substance_onset", "binge_pattern", "social_peer_pressure"],
            precursor_events = ["EVT-1999-PTSD"],
        ),

        # ── Age 14 — 2006 — Depression (HIGH / M-DISC Bucket) ────────────────
        DarkAreaEvent(
            event_id       = "EVT-2006-DEPRESSION",
            age            = 14,
            event_date     = date(2006, 1, 1),
            label          = "Depression",
            description    = "Clinical depression onset. 88th-percentile uniqueness. M-DISC bucket.",
            severity       = EventSeverity.HIGH,
            access_tier    = AccessTier.HIGH,
            gps            = (35.942, -95.885),
            location_label = "Muskogee County, OK",
            injury_type    = InjuryType.PSYCHOLOGICAL,
            injury_desc    = "Major depressive episode; anhedonia, social withdrawal",
            outcome_tags   = ["depression", "dev_phase_coordination_sync", "hormonal_onset"],
            precursor_events = ["EVT-1999-PTSD", "EVT-2005-ALC-01"],
        ),

        # ── Age 15 — 2007 — Cannabis onset ───────────────────────────────────
        DarkAreaEvent(
            event_id       = "EVT-2007-CANNABIS",
            age            = 15,
            event_date     = date(2007, 3, 1),
            label          = "Cannabis onset",
            description    = "Regular cannabis use begins. Self-medication pattern for depression.",
            severity       = EventSeverity.MODERATE,
            access_tier    = AccessTier.HIGH,
            gps            = (35.942, -95.885),
            location_label = "Muskogee County, OK",
            substance_type = SubstanceType.CANNABIS,
            substance_name = "Cannabis (flower)",
            quantity_desc  = "Daily use, ~1 g/day",
            outcome_tags   = ["cannabis", "self_medication", "depression_comorbid"],
            precursor_events = ["EVT-2006-DEPRESSION"],
        ),

        # ── Age 16 — 2008 — Isolation (HIGH / Synthetic only) ────────────────
        DarkAreaEvent(
            event_id       = "EVT-2008-ISOLATION",
            age            = 16,
            event_date     = date(2008, 1, 1),
            label          = "Isolation",
            description    = "Social isolation escalation. 92nd-percentile uniqueness. Synthetic-only storage.",
            severity       = EventSeverity.HIGH,
            access_tier    = AccessTier.HIGH,
            gps            = None,
            location_label = "Residence, Muskogee County, OK",
            injury_type    = InjuryType.PSYCHOLOGICAL,
            injury_desc    = "Prolonged social withdrawal; compounded substance use",
            outcome_tags   = ["isolation", "dev_phase_hormonal_overwrite", "synthetic_only"],
            precursor_events = ["EVT-2006-DEPRESSION", "EVT-2007-CANNABIS"],
        ),

        # ── Age 17 — 2009 — Opioid introduction ─────────────────────────────
        DarkAreaEvent(
            event_id       = "EVT-2009-OPIOID-01",
            age            = 17,
            event_date     = date(2009, 9, 1),
            label          = "Opioid introduction",
            description    = "First opioid use (prescription diversion). Rapid escalation pattern.",
            severity       = EventSeverity.HIGH,
            access_tier    = AccessTier.HIGH,
            gps            = (35.942, -95.885),
            location_label = "Muskogee County, OK",
            substance_type = SubstanceType.OPIOID,
            substance_name = "Hydrocodone (diverted Rx)",
            quantity_desc  = "5–10 mg/day initial",
            outcome_tags   = ["opioid_onset", "prescription_diversion", "escalation_risk"],
            precursor_events = ["EVT-2008-ISOLATION", "EVT-2006-DEPRESSION"],
        ),

        # ── Age 18 — 2010 — First ER visit ───────────────────────────────────
        DarkAreaEvent(
            event_id       = "EVT-2010-ER-01",
            age            = 18,
            event_date     = date(2010, 4, 15),
            label          = "ER visit — alcohol/opioid polysubstance",
            description    = "Emergency presentation. Polysubstance intoxication (alcohol + opioid).",
            severity       = EventSeverity.HIGH,
            access_tier    = AccessTier.HIGH,
            gps            = (35.748, -95.367),
            location_label = "Muskogee Regional Medical Center, Muskogee, OK",
            substance_type = SubstanceType.OPIOID,
            substance_name = "Opioid + Alcohol (polysubstance)",
            quantity_desc  = "Unknown quantity; respiratory depression noted",
            injury_type    = InjuryType.OVERDOSE,
            injury_desc    = "Respiratory depression, GCS 12 on arrival",
            hospital_name  = "Muskogee Regional Medical Center",
            hospital_city  = "Muskogee, OK",
            admitted       = True,
            icu            = False,
            los_days       = 1,
            outcome_tags   = ["polysubstance", "er_visit", "respiratory_depression"],
            precursor_events = ["EVT-2009-OPIOID-01", "EVT-2005-ALC-01"],
        ),

        # ── Age 20 — 2012 — Stimulant introduction ───────────────────────────
        DarkAreaEvent(
            event_id       = "EVT-2012-STIMULANT",
            age            = 20,
            event_date     = date(2012, 2, 1),
            label          = "Stimulant introduction",
            description    = "Methamphetamine use begins. Counter-depression self-medication.",
            severity       = EventSeverity.HIGH,
            access_tier    = AccessTier.HIGH,
            gps            = (36.154, -95.993),
            location_label = "Tulsa County, OK",
            substance_type = SubstanceType.STIMULANT,
            substance_name = "Methamphetamine",
            quantity_desc  = "Sporadic use; escalating frequency",
            outcome_tags   = ["stimulant", "meth", "counter_sedation", "escalation"],
            precursor_events = ["EVT-2009-OPIOID-01", "EVT-2006-DEPRESSION"],
        ),

        # ── Age 22 — 2014 — OD (EXISTENTIAL / Physical Vault) ────────────────
        DarkAreaEvent(
            event_id       = "EVT-2014-OD",
            age            = 22,
            event_date     = date(2014, 1, 1),
            label          = "OD — Opioid overdose",
            description    = (
                "Near-fatal opioid overdose. 99th-percentile uniqueness. "
                "EXISTENTIAL tier — physical vault, no digital copy."
            ),
            severity       = EventSeverity.EXISTENTIAL,
            access_tier    = AccessTier.EXISTENTIAL,
            gps            = None,   # vault_location_hash only — plaintext never stored
            location_label = "[VAULT — location sealed]",
            substance_type = SubstanceType.OPIOID,
            substance_name = "Heroin / Fentanyl-adulterated",
            quantity_desc  = "Lethal threshold exceeded; Narcan administered",
            injury_type    = InjuryType.OVERDOSE,
            injury_desc    = "Respiratory arrest; Narcan x2 doses; CPR initiated",
            hospital_name  = "[SEALED — EXISTENTIAL tier]",
            hospital_city  = "[SEALED]",
            admitted       = True,
            icu            = True,
            los_days       = 3,
            outcome_tags   = [
                "near_fatal_od", "naloxone_reversal", "icu_admit",
                "fentanyl_adulterated", "existential_tier", "vault_only"
            ],
            precursor_events = [
                "EVT-2009-OPIOID-01", "EVT-2010-ER-01",
                "EVT-2012-STIMULANT", "EVT-2008-ISOLATION"
            ],
        ),

        # ── Age 23 — 2015 — Rehabilitation ───────────────────────────────────
        DarkAreaEvent(
            event_id       = "EVT-2015-REHAB",
            age            = 23,
            event_date     = date(2015, 3, 1),
            label          = "Inpatient rehabilitation",
            description    = "28-day inpatient substance use treatment program post-OD.",
            severity       = EventSeverity.HIGH,
            access_tier    = AccessTier.HIGH,
            gps            = (36.154, -95.993),
            location_label = "Tulsa, OK",
            outcome_tags   = ["rehabilitation", "sobriety_start", "post_od_recovery"],
            precursor_events = ["EVT-2014-OD"],
        ),

        # ── Age 25 — 2017 — Business (LOW / Public OK) ───────────────────────
        DarkAreaEvent(
            event_id       = "EVT-2017-BUSINESS",
            age            = 25,
            event_date     = date(2017, 1, 1),
            label          = "Business venture",
            description    = "First business venture. 45th-percentile uniqueness. LOW tier.",
            severity       = EventSeverity.LOW,
            access_tier    = AccessTier.LOW,
            gps            = (36.154, -95.993),
            location_label = "Tulsa, OK",
            outcome_tags   = ["business", "recovery_stability", "adult_phase"],
        ),

        # ── Age 33 — 2025 — Baseline (MINIMAL / Broadcast) ───────────────────
        DarkAreaEvent(
            event_id       = "EVT-2025-BASELINE",
            age            = 33,
            event_date     = date(2025, 1, 1),
            label          = "Baseline calibration",
            description    = "Current operational baseline. 50th-percentile. Live mesh broadcast.",
            severity       = EventSeverity.LOW,
            access_tier    = AccessTier.MINIMAL,
            gps            = None,
            location_label = "Active — live mesh",
            outcome_tags   = ["baseline", "bio_nft_eligible", "pobw", "broadcast"],
        ),
    ]

    return db


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

TIER_COLOR = {
    AccessTier.EXISTENTIAL: "\033[91m",   # bright red
    AccessTier.CRITICAL:    "\033[31m",   # red
    AccessTier.HIGH:        "\033[33m",   # yellow
    AccessTier.LOW:         "\033[32m",   # green
    AccessTier.MINIMAL:     "\033[36m",   # cyan
}
RESET = "\033[0m"


def _tier_str(tier: AccessTier) -> str:
    return f"{TIER_COLOR.get(tier, '')}{tier.value}{RESET}"


def print_detailed_event(event_id: str, db: DarkAreaDatabase) -> None:
    e = db.get(event_id)
    if e is None:
        print(f"  [event {event_id} not found]")
        return

    gps_str = f"{e.gps[0]:.4f}, {e.gps[1]:.4f}" if e.gps else "SEALED"
    print(f"""
  ┌─ {e.label} (Age {e.age} / {e.event_date.year}) {'─'*(60 - len(e.label))}
  │  ID         : {e.event_id}
  │  Severity   : {e.severity.name}   Tier: {_tier_str(e.access_tier)}
  │  Location   : {e.location_label}  [{gps_str}]
  │  Description: {e.description}""")

    if e.substance_type:
        print(f"  │  Substance  : {e.substance_name} ({e.substance_type.value} / {e.substance_class.value if e.substance_class else 'n/a'})")
        if e.quantity_desc:
            print(f"  │  Quantity   : {e.quantity_desc}")
        protocols = e.intervention_protocol
        if protocols:
            print(f"  │  Protocol   : {' | '.join(protocols[:2])}")

    if e.injury_type and e.injury_type != InjuryType.NONE:
        print(f"  │  Injury     : {e.injury_type.value} — {e.injury_desc or ''}")

    if e.hospital_name:
        admit_str = "ICU" if e.icu else ("admitted" if e.admitted else "ER only")
        los_str   = f"{e.los_days}d" if e.los_days else "unknown"
        print(f"  │  Hospital   : {e.hospital_name}, {e.hospital_city} [{admit_str} / LOS {los_str}]")

    if e.precursor_events:
        print(f"  │  Precursors : {', '.join(e.precursor_events)}")
    if e.outcome_tags:
        print(f"  │  Tags       : {', '.join(e.outcome_tags)}")
    print(f"  └{'─'*70}")


def print_statistics(db: DarkAreaDatabase) -> None:
    drug_events     = [e for e in db.events if e.substance_type]
    injury_events   = [e for e in db.events if e.injury_type and e.injury_type != InjuryType.NONE]
    hospital_events = [e for e in db.events if e.hospital_name]
    icu_events      = [e for e in db.events if e.icu]

    stimulants  = [e for e in db.events if e.substance_class == SubstanceClass.STIMULANT]
    depressants = [e for e in db.events if e.substance_class == SubstanceClass.DEPRESSANT]
    entactogens = [e for e in db.events if e.substance_class == SubstanceClass.ENACTOGEN]
    cannabinoids= [e for e in db.events if e.substance_class == SubstanceClass.CANNABINOID]

    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              DARK AREA EVENT STATISTICS — {db.twin_name:<35}║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  DRUG/NARCOTIC EVENTS : {len(drug_events):<3}                                              ║
║    • Alcohol           : {len([e for e in drug_events if e.substance_type == SubstanceType.ALCOHOL]):<3}                                            ║
║    • Opioid            : {len([e for e in drug_events if e.substance_type == SubstanceType.OPIOID]):<3}                                            ║
║    • Cannabis          : {len([e for e in drug_events if e.substance_type == SubstanceType.CANNABIS]):<3}                                            ║
║    • Stimulant         : {len([e for e in drug_events if e.substance_type == SubstanceType.STIMULANT]):<3}                                            ║
║    • Benzodiazepine    : {len([e for e in drug_events if e.substance_type == SubstanceType.BENZO]):<3}                                            ║
║                                                                              ║
║  BY SUBSTANCE CLASS:                                                         ║
║    • Depressants       : {len(depressants):<3}                                            ║
║    • Stimulants        : {len(stimulants):<3}                                            ║
║    • Cannabinoids      : {len(cannabinoids):<3}                                            ║
║    • Enactogens        : {len(entactogens):<3}                                            ║
║                                                                              ║
║  INJURY EVENTS        : {len(injury_events):<3}                                              ║
║    • Overdose          : {len([e for e in injury_events if e.injury_type == InjuryType.OVERDOSE]):<3}                                            ║
║    • Psychological     : {len([e for e in injury_events if e.injury_type == InjuryType.PSYCHOLOGICAL]):<3}                                            ║
║                                                                              ║
║  HOSPITAL EVENTS      : {len(hospital_events):<3}                                              ║
║    • ICU admissions    : {len(icu_events):<3}                                            ║
║    • ER only           : {len([e for e in hospital_events if not e.admitted]):<3}                                            ║
║                                                                              ║
║  BY ACCESS TIER:                                                             ║
║    • EXISTENTIAL       : {len([e for e in db.events if e.access_tier == AccessTier.EXISTENTIAL]):<3}  (physical vault — no digital copy)             ║
║    • CRITICAL          : {len([e for e in db.events if e.access_tier == AccessTier.CRITICAL]):<3}  (airgap)                                     ║
║    • HIGH              : {len([e for e in db.events if e.access_tier == AccessTier.HIGH]):<3}  (encrypted / synthetic)                      ║
║    • LOW               : {len([e for e in db.events if e.access_tier == AccessTier.LOW]):<3}  (public OK)                                   ║
║    • MINIMAL           : {len([e for e in db.events if e.access_tier == AccessTier.MINIMAL]):<3}  (broadcast)                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝""")


def print_predictive_patterns(db: DarkAreaDatabase) -> None:
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    PREDICTIVE PATTERN ANALYSIS                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ESCALATION PATHWAY (observed):                                              ║
║    PTSD (7) → Depression (14) → Isolation (16) → Opioid onset (17)          ║
║             → Polysubstance (18/ER) → Stimulant (20) → NEAR-FATAL OD (22)   ║
║                                                                              ║
║  KEY PREDICTORS FOR EXISTENTIAL EVENT (OD at 22):                           ║
║    [1] Childhood trauma onset (PTSD, age 7)                                  ║
║    [2] Clinical depression without treatment (age 14)                        ║
║    [3] Opioid escalation from prescription diversion (age 17→22)             ║
║    [4] Polysubstance combination (opioid + alcohol synergy)                  ║
║    [5] Fentanyl adulteration of supply (2013–2014 market shift)              ║
║    [6] Social isolation reducing intervention likelihood                     ║
║                                                                              ║
║  INTERVENTION PROTOCOLS ACTIVATED (EVT-2014-OD):                            ║
║    • Naloxone (Narcan) 0.4–2 mg IV/IM — x2 doses                            ║
║    • Airway management / O2 monitoring                                       ║
║    • ICU admission — 3-day LOS                                               ║
║                                                                              ║
║  RECOVERY INDICATORS (post-2014):                                            ║
║    • 28-day inpatient rehab (2015)                                           ║
║    • Business venture stability (2017)                                       ║
║    • Baseline biometric calibration active (2025)                            ║
║                                                                              ║
║  BIOMETRIC RISK CORRELATION:                                                 ║
║    • EEG θ/α ≥ 0.62 + HRV LF/HF ≥ 2.1 → stress_confirmed                   ║
║    • Historical stress states precede substance events in 5/6 cases          ║
║    • Body-coupled RF identity gate: fraud_score raised under acute distress  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝""")


def print_intervention_protocols(db: DarkAreaDatabase) -> None:
    print("\n" + "="*80)
    print("  MEDICAL INTERVENTION PROTOCOLS")
    print("="*80)
    seen: set[SubstanceType] = set()
    for event in db.events:
        if event.substance_type and event.substance_type not in seen:
            seen.add(event.substance_type)
            protocols = event.intervention_protocol
            if protocols:
                print(f"\n  {event.substance_type.value}:")
                for p in protocols:
                    print(f"    • {p}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    db = build_database()

    print("\n" + "="*80)
    print(f"  CHASE ALLEN RINGQUIST — Dark Area & Smoke Event Dataset")
    print(f"  Twin UUID: {db.twin_id}")
    print(f"  Events loaded: {len(db.events)}")
    print("="*80)

    print_statistics(db)

    print("\n" + "─"*80)
    print("  DETAILED EVENT LOG (chronological)")
    print("─"*80)

    for event in sorted(db.events, key=lambda e: e.event_date):
        print_detailed_event(event.event_id, db)

    print_predictive_patterns(db)
    print_intervention_protocols(db)


if __name__ == "__main__":
    main()
