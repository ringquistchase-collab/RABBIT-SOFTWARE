-- 20260535_bio_rna_integration.sql
-- DNA/RNA → neural node integration layer
--
-- RF mapping formula:  f_RF = (Σ nucleotide_freq) / N + Σ codon_offset / M
--   nucleotide base GHz: A=10.23  T=10.24  U=10.25  G=10.26  C=10.27
--   (T = DNA only, U = RNA only; both share the same 10.24/10.25 band gap)
--
-- Molecule types × node functions:
--   DNA      → 10.2345 GHz band  → node identity / dna_root_sig
--   mRNA     → 10.2456 GHz band  → protein encoding / TFM token type
--   tRNA     → 10.2567 GHz band  → amino acid carry / calibration transport
--   guide_rna→ 10.2678 GHz band  → CRISPR targeting / edit registry
--   siRNA    → 10.2789 GHz band  → gene silencing / node interference mask
--
-- Existing hook: digital_twins.dna_root_hash is the anchor for all molecule
-- records tied to a twin.  calibration_era_baselines.dna_root_sig is the
-- immutable lock that must match before any CRISPR edit is approved.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- ENUMS
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TYPE bio_molecule_type AS ENUM (
    'DNA',
    'mRNA',
    'tRNA',
    'guide_rna',   -- CRISPR guide RNA (gRNA / sgRNA)
    'siRNA'        -- small interfering RNA (gene silencing)
);

CREATE TYPE crispr_edit_type AS ENUM (
    'knockout',      -- disrupt gene function
    'knockin',       -- insert sequence
    'base_edit',     -- single-base correction (C→T / A→G)
    'activation',    -- CRISPRa: upregulate expression
    'silencing'      -- CRISPRi: suppress without cut
);

CREATE TYPE epigenetic_mark_type AS ENUM (
    'methylation',           -- CpG methylation → gene silencing
    'acetylation',           -- histone acetylation → gene activation
    'phosphorylation',       -- rapid stress response
    'deacetylation'          -- HDAC-mediated suppression
);

-- ─────────────────────────────────────────────────────────────────────────────
-- codon_rf_offsets
-- Lookup table: each standard codon maps to an RF offset (GHz).
-- Offset range 0.0001 – 0.0009 GHz so the full formula stays within
-- the 10.23 – 10.28 GHz operating band.
-- Seeded with the standard genetic code start/stop and key regulatory codons.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE codon_rf_offsets (
    codon           CHAR(3)  NOT NULL PRIMARY KEY,   -- e.g. 'ATG', 'AUG', 'TAA'
    amino_acid      TEXT,                             -- NULL for stop codons
    is_start_codon  BOOLEAN  NOT NULL DEFAULT FALSE,
    is_stop_codon   BOOLEAN  NOT NULL DEFAULT FALSE,
    rf_offset_ghz   REAL     NOT NULL                 -- additive offset in the formula
);

-- Seed: start codons (highest offset — maximum expression signal)
INSERT INTO codon_rf_offsets VALUES
    ('ATG', 'Met',  TRUE,  FALSE, 0.0009),   -- DNA start
    ('AUG', 'Met',  TRUE,  FALSE, 0.0009);   -- RNA start (same amino acid, different base)

-- Stop codons
INSERT INTO codon_rf_offsets VALUES
    ('TAA', NULL,   FALSE, TRUE,  0.0001),
    ('TAG', NULL,   FALSE, TRUE,  0.0001),
    ('TGA', NULL,   FALSE, TRUE,  0.0001),
    ('UAA', NULL,   FALSE, TRUE,  0.0001),
    ('UAG', NULL,   FALSE, TRUE,  0.0001),
    ('UGA', NULL,   FALSE, TRUE,  0.0001);

-- Key amino acid codons (regulatory / biologically active in the RABBIT context)
INSERT INTO codon_rf_offsets VALUES
    ('GCT', 'Ala', FALSE, FALSE, 0.0003),
    ('GCC', 'Ala', FALSE, FALSE, 0.0003),
    ('TGT', 'Cys', FALSE, FALSE, 0.0005),   -- cysteine: disulfide bridge signal
    ('GAT', 'Asp', FALSE, FALSE, 0.0004),
    ('GAA', 'Glu', FALSE, FALSE, 0.0004),
    ('TTC', 'Phe', FALSE, FALSE, 0.0003),
    ('GGT', 'Gly', FALSE, FALSE, 0.0002),
    ('CAT', 'His', FALSE, FALSE, 0.0006),   -- histidine: pH sensor
    ('ATT', 'Ile', FALSE, FALSE, 0.0003),
    ('AAA', 'Lys', FALSE, FALSE, 0.0005),   -- lysine: histone modification site
    ('CTT', 'Leu', FALSE, FALSE, 0.0003),
    ('AAT', 'Asn', FALSE, FALSE, 0.0004),
    ('CCT', 'Pro', FALSE, FALSE, 0.0004),
    ('CAA', 'Gln', FALSE, FALSE, 0.0004),
    ('CGT', 'Arg', FALSE, FALSE, 0.0007),   -- arginine: most positively charged; epigenetic
    ('TCT', 'Ser', FALSE, FALSE, 0.0003),
    ('ACT', 'Thr', FALSE, FALSE, 0.0004),
    ('GTT', 'Val', FALSE, FALSE, 0.0003),
    ('TGG', 'Trp', FALSE, FALSE, 0.0008),   -- tryptophan: single codon; serotonin precursor
    ('TAT', 'Tyr', FALSE, FALSE, 0.0006),   -- tyrosine: dopamine/adrenaline precursor
    -- RNA equivalents for key codons
    ('GCU', 'Ala', FALSE, FALSE, 0.0003),
    ('UGU', 'Cys', FALSE, FALSE, 0.0005),
    ('GAU', 'Asp', FALSE, FALSE, 0.0004),
    ('GAA', 'Glu', FALSE, FALSE, 0.0004),
    ('UUC', 'Phe', FALSE, FALSE, 0.0003),
    ('GGU', 'Gly', FALSE, FALSE, 0.0002),
    ('CAU', 'His', FALSE, FALSE, 0.0006),
    ('AUU', 'Ile', FALSE, FALSE, 0.0003),
    ('AAA', 'Lys', FALSE, FALSE, 0.0005),
    ('CUU', 'Leu', FALSE, FALSE, 0.0003),
    ('AAU', 'Asn', FALSE, FALSE, 0.0004),
    ('CCU', 'Pro', FALSE, FALSE, 0.0004),
    ('CAA', 'Gln', FALSE, FALSE, 0.0004),
    ('CGU', 'Arg', FALSE, FALSE, 0.0007),
    ('UCU', 'Ser', FALSE, FALSE, 0.0003),
    ('ACU', 'Thr', FALSE, FALSE, 0.0004),
    ('GUU', 'Val', FALSE, FALSE, 0.0003),
    ('UGG', 'Trp', FALSE, FALSE, 0.0008),
    ('UAU', 'Tyr', FALSE, FALSE, 0.0006)
ON CONFLICT (codon) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- compute_molecular_rf_freq(sequence, molecule_type)
-- Implements f_RF = (Σ nucleotide_freq) / N + Σ codon_offset / M
-- Returns the computed GHz frequency for a given nucleotide sequence.
-- Unknown nucleotides use A's base freq (10.23) as fallback.
-- Unknown codons use 0.0002 as default offset.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION compute_molecular_rf_freq(
    p_sequence      TEXT,
    p_molecule_type bio_molecule_type
)
RETURNS REAL LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    v_seq           TEXT    := UPPER(TRIM(p_sequence));
    v_len           INTEGER := LENGTH(v_seq);
    v_nucl_sum      REAL    := 0.0;
    v_codon_sum     REAL    := 0.0;
    v_codon_count   INTEGER := 0;
    v_codon_offset  REAL;
    v_i             INTEGER;
    v_base          CHAR;
    v_codon         CHAR(3);
BEGIN
    IF v_len = 0 THEN RETURN 10.23; END IF;

    -- Step 1: sum nucleotide frequencies
    FOR v_i IN 1..v_len LOOP
        v_base := SUBSTRING(v_seq, v_i, 1);
        v_nucl_sum := v_nucl_sum + CASE v_base
            WHEN 'A' THEN 10.23
            WHEN 'T' THEN 10.24
            WHEN 'U' THEN 10.25   -- RNA uracil
            WHEN 'G' THEN 10.26
            WHEN 'C' THEN 10.27
            ELSE 10.23            -- unknown → A fallback
        END;
    END LOOP;

    -- Step 2: sum codon offsets (reading frame: triplets from position 1)
    v_i := 1;
    WHILE v_i + 2 <= v_len LOOP
        v_codon := SUBSTRING(v_seq, v_i, 3);
        SELECT rf_offset_ghz INTO v_codon_offset
        FROM codon_rf_offsets WHERE codon = v_codon;
        v_codon_sum   := v_codon_sum + COALESCE(v_codon_offset, 0.0002);
        v_codon_count := v_codon_count + 1;
        v_i := v_i + 3;
    END LOOP;

    -- f_RF = (Σ nucleotide_freq) / N + Σ codon_offset / M
    RETURN (v_nucl_sum / v_len) +
           CASE WHEN v_codon_count > 0 THEN v_codon_sum / v_codon_count ELSE 0.0 END;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- bio_molecule_registry
-- Central registry linking a biological molecule to a twin and a mesh node.
-- computed_freq_ghz is generated by the formula above and stored for fast lookup.
-- Anchored to digital_twins.dna_root_hash — no molecule can be registered
-- without a valid twin record.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE bio_molecule_registry (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id             UUID NOT NULL REFERENCES digital_twins(id) ON DELETE CASCADE,
    linked_node_id      INTEGER REFERENCES mesh_nodes(node_id),    -- may be NULL for whole-twin molecules
    molecule_type       bio_molecule_type NOT NULL,
    nucleotide_sequence TEXT NOT NULL,
    sequence_length_bp  INTEGER GENERATED ALWAYS AS (LENGTH(nucleotide_sequence)) STORED,
    computed_freq_ghz   REAL,                                       -- set by trigger on insert
    -- Source / provenance
    source_region       TEXT,    -- e.g. 'BRCA1 exon 11', 'BDNF promoter'
    gene_symbol         TEXT,    -- e.g. 'BDNF', 'COMT', 'MAOA'
    chromosome          TEXT,    -- e.g. '11p13'
    -- Lock: once anchored to a dna_root_sig, sequence is immutable
    dna_root_sig        TEXT,
    is_locked           BOOLEAN NOT NULL DEFAULT FALSE,
    locked_at           TIMESTAMPTZ,
    registered_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (twin_id, molecule_type, nucleotide_sequence)
);

CREATE INDEX bio_mol_twin_idx  ON bio_molecule_registry (twin_id);
CREATE INDEX bio_mol_node_idx  ON bio_molecule_registry (linked_node_id);
CREATE INDEX bio_mol_type_idx  ON bio_molecule_registry (twin_id, molecule_type);
CREATE INDEX bio_mol_gene_idx  ON bio_molecule_registry (gene_symbol);

-- Trigger: auto-compute RF frequency on insert; block mutation on locked records
CREATE OR REPLACE FUNCTION bio_molecule_registry_manage()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.computed_freq_ghz := compute_molecular_rf_freq(
            NEW.nucleotide_sequence, NEW.molecule_type
        );
        RETURN NEW;
    END IF;

    -- UPDATE path: block sequence changes on locked records
    IF OLD.is_locked AND NEW.nucleotide_sequence != OLD.nucleotide_sequence THEN
        RAISE EXCEPTION 'Cannot mutate locked bio molecule sequence (id=%)', OLD.id
            USING ERRCODE = '55000';
    END IF;
    -- Recompute if sequence changed
    IF NEW.nucleotide_sequence != OLD.nucleotide_sequence THEN
        NEW.computed_freq_ghz := compute_molecular_rf_freq(
            NEW.nucleotide_sequence, NEW.molecule_type
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER bio_molecule_registry_trigger
    BEFORE INSERT OR UPDATE ON bio_molecule_registry
    FOR EACH ROW EXECUTE FUNCTION bio_molecule_registry_manage();

-- ─────────────────────────────────────────────────────────────────────────────
-- rna_translation_events
-- mRNA → protein encoding events.
-- Captures which mRNA (template_molecule_id) was translated, what product
-- emerged, and how efficiently (0.0–1.0).
-- tRNA records are linked here as amino_acid_carriers[].
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE rna_translation_events (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id                 UUID NOT NULL REFERENCES digital_twins(id) ON DELETE CASCADE,
    template_molecule_id    BIGINT NOT NULL REFERENCES bio_molecule_registry(id),
    -- tRNA molecules involved (array of bio_molecule_registry IDs)
    trna_carrier_ids        BIGINT[],
    product_name            TEXT NOT NULL,     -- protein or peptide name
    product_function        TEXT,              -- e.g. 'BDNF: neuroplasticity signal'
    codon_sequence          TEXT[],            -- parsed triplets ['ATG','GCT',...]
    translation_efficiency  REAL NOT NULL CHECK (translation_efficiency BETWEEN 0.0 AND 1.0),
    ribosomal_site          TEXT,              -- '5-UTR', 'AUG+12', etc.
    -- Node effect: which mesh node does the expressed protein affect
    target_node_id          INTEGER REFERENCES mesh_nodes(node_id),
    expression_delta        REAL,              -- +/- effect on node signal amplitude
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX rna_trans_twin_idx     ON rna_translation_events (twin_id, detected_at DESC);
CREATE INDEX rna_trans_template_idx ON rna_translation_events (template_molecule_id);
CREATE INDEX rna_trans_node_idx     ON rna_translation_events (target_node_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- rna_interference_log
-- siRNA gene silencing events.
-- Each row records an siRNA molecule suppressing a target mRNA.
-- silencing_efficiency: 0.0 (no effect) → 1.0 (complete knockdown).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE rna_interference_log (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id                 UUID NOT NULL REFERENCES digital_twins(id) ON DELETE CASCADE,
    sirna_molecule_id       BIGINT NOT NULL REFERENCES bio_molecule_registry(id),
    target_molecule_id      BIGINT NOT NULL REFERENCES bio_molecule_registry(id),
    silencing_efficiency    REAL NOT NULL CHECK (silencing_efficiency BETWEEN 0.0 AND 1.0),
    -- Off-target risk: sequence complementarity to unintended transcripts
    off_target_score        REAL NOT NULL DEFAULT 0.0
                            CHECK (off_target_score BETWEEN 0.0 AND 1.0),
    -- Affected mesh node
    target_node_id          INTEGER REFERENCES mesh_nodes(node_id),
    node_signal_suppression REAL,   -- fraction by which node amplitude is dampened
    -- Duration estimate (e.g. siRNA half-life ~2-3 days in vivo)
    estimated_duration_h    REAL,
    applied_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at              TIMESTAMPTZ
);

CREATE INDEX rna_intf_twin_idx   ON rna_interference_log (twin_id, applied_at DESC);
CREATE INDEX rna_intf_target_idx ON rna_interference_log (target_molecule_id);
CREATE INDEX rna_intf_node_idx   ON rna_interference_log (target_node_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- crispr_guide_registry
-- Guide RNA (gRNA / sgRNA) sequences for CRISPR operations.
-- Each guide targets a specific genomic locus (target_sequence + PAM site).
-- Approval requires matching the twin's locked dna_root_sig.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE crispr_guide_registry (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id             UUID NOT NULL REFERENCES digital_twins(id) ON DELETE CASCADE,
    guide_molecule_id   BIGINT NOT NULL REFERENCES bio_molecule_registry(id),
    edit_type           crispr_edit_type NOT NULL,
    -- Target locus
    target_sequence     TEXT NOT NULL,    -- 20-nt protospacer
    pam_site            TEXT NOT NULL DEFAULT 'NGG',
    target_gene         TEXT,
    target_chromosome   TEXT,
    -- Specificity scores
    on_target_score     REAL NOT NULL CHECK (on_target_score BETWEEN 0.0 AND 1.0),
    off_target_score    REAL NOT NULL DEFAULT 0.0
                        CHECK (off_target_score BETWEEN 0.0 AND 1.0),
    -- Approval gate: must match the twin's calibration-era dna_root_sig
    -- before any knockin/knockout is applied
    approved_by_sig     TEXT,
    approved_at         TIMESTAMPTZ,
    -- Execution record
    executed_at         TIMESTAMPTZ,
    execution_outcome   TEXT,
    designed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX crispr_twin_idx  ON crispr_guide_registry (twin_id);
CREATE INDEX crispr_gene_idx  ON crispr_guide_registry (target_gene);
CREATE INDEX crispr_exec_idx  ON crispr_guide_registry (twin_id, executed_at);

-- Trigger: block execution without dna_root_sig approval for destructive edits
CREATE OR REPLACE FUNCTION enforce_crispr_approval()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_root_sig TEXT;
BEGIN
    IF NEW.executed_at IS NOT NULL AND OLD.executed_at IS NULL THEN
        -- Destructive edits (knockout/knockin/base_edit) require approval
        IF NEW.edit_type IN ('knockout', 'knockin', 'base_edit') THEN
            IF NEW.approved_by_sig IS NULL THEN
                RAISE EXCEPTION 'CRISPR edit type % requires dna_root_sig approval', NEW.edit_type
                    USING ERRCODE = '55000';
            END IF;
            -- Verify sig matches the twin's locked calibration baseline
            SELECT dna_root_sig INTO v_root_sig
            FROM calibration_era_baselines
            WHERE twin_id = NEW.twin_id AND is_locked = TRUE
            ORDER BY locked_at DESC LIMIT 1;
            IF v_root_sig IS NULL OR v_root_sig != NEW.approved_by_sig THEN
                RAISE EXCEPTION 'CRISPR approval sig does not match locked dna_root_sig'
                    USING ERRCODE = '55000';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER crispr_approval_check
    BEFORE UPDATE ON crispr_guide_registry
    FOR EACH ROW EXECUTE FUNCTION enforce_crispr_approval();

-- ─────────────────────────────────────────────────────────────────────────────
-- epigenetic_node_states
-- Per-node epigenetic mark snapshot.
-- expression_modifier: +1.0 = fully activated, -1.0 = fully silenced.
-- Linked to bio_molecule_registry for the molecule that caused the mark.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE epigenetic_node_states (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id             UUID NOT NULL REFERENCES digital_twins(id) ON DELETE CASCADE,
    node_id             INTEGER NOT NULL REFERENCES mesh_nodes(node_id),
    mark_type           epigenetic_mark_type NOT NULL,
    -- Quantitative levels (0.0 – 1.0)
    mark_level          REAL NOT NULL CHECK (mark_level BETWEEN 0.0 AND 1.0),
    expression_modifier REAL NOT NULL CHECK (expression_modifier BETWEEN -1.0 AND 1.0),
    -- Source molecule (the molecule that induced this epigenetic change)
    source_molecule_id  BIGINT REFERENCES bio_molecule_registry(id),
    -- Life event context (e.g. trauma → methylation of stress-response genes)
    life_event_id       BIGINT REFERENCES life_age_events(id),
    dev_phase           TEXT,   -- references calibration_era dev_phase context
    -- Reversibility
    is_reversible       BOOLEAN NOT NULL DEFAULT TRUE,
    -- Heritability flag: can this mark be passed to child nodes / next-gen baselines?
    is_heritable        BOOLEAN NOT NULL DEFAULT FALSE,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ   -- NULL = permanent
);

CREATE INDEX epig_twin_node_idx ON epigenetic_node_states (twin_id, node_id, recorded_at DESC);
CREATE INDEX epig_molecule_idx  ON epigenetic_node_states (source_molecule_id);
CREATE INDEX epig_life_evt_idx  ON epigenetic_node_states (life_event_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- dna_storage_records
-- DNA as a data storage medium.  data_payload_jsonb is the original data;
-- encoded_sequence is its DNA encoding (A=00, T=01, G=10, C=11 binary→base4).
-- Mirrors PersonNodeNetwork's "Store/retrieve data in DNA format" operation.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE dna_storage_records (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id             UUID NOT NULL REFERENCES digital_twins(id) ON DELETE CASCADE,
    storage_molecule_id BIGINT REFERENCES bio_molecule_registry(id),
    data_label          TEXT NOT NULL,
    data_hash           TEXT NOT NULL,          -- SHA-256 of original payload
    encoded_sequence    TEXT NOT NULL,          -- DNA base-4 encoding of data
    data_size_bp        INTEGER GENERATED ALWAYS AS (LENGTH(encoded_sequence)) STORED,
    data_payload_jsonb  JSONB,                  -- original data (optional; may be omitted)
    error_correction    TEXT NOT NULL DEFAULT 'REED_SOLOMON', -- encoding scheme
    retrieval_count     INTEGER NOT NULL DEFAULT 0,
    last_retrieved_at   TIMESTAMPTZ,
    stored_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (twin_id, data_hash)
);

CREATE INDEX dna_store_twin_idx ON dna_storage_records (twin_id);
CREATE INDEX dna_store_hash_idx ON dna_storage_records (data_hash);

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: register_bio_molecule
-- Inserts into bio_molecule_registry; computed_freq_ghz is set by trigger.
-- Returns the new record ID and computed frequency.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION register_bio_molecule(
    p_twin_id       UUID,
    p_sequence      TEXT,
    p_type          bio_molecule_type,
    p_node_id       INTEGER   DEFAULT NULL,
    p_gene_symbol   TEXT      DEFAULT NULL,
    p_source_region TEXT      DEFAULT NULL,
    p_chromosome    TEXT      DEFAULT NULL
)
RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE
    v_id   BIGINT;
    v_freq REAL;
BEGIN
    INSERT INTO bio_molecule_registry (
        twin_id, linked_node_id, molecule_type,
        nucleotide_sequence, gene_symbol, source_region, chromosome
    ) VALUES (
        p_twin_id, p_node_id, p_type,
        UPPER(TRIM(p_sequence)), p_gene_symbol, p_source_region, p_chromosome
    )
    ON CONFLICT (twin_id, molecule_type, nucleotide_sequence) DO UPDATE
        SET gene_symbol   = COALESCE(EXCLUDED.gene_symbol,   bio_molecule_registry.gene_symbol),
            source_region = COALESCE(EXCLUDED.source_region, bio_molecule_registry.source_region)
    RETURNING id, computed_freq_ghz INTO v_id, v_freq;

    RETURN jsonb_build_object(
        'molecule_id',        v_id,
        'molecule_type',      p_type,
        'computed_freq_ghz',  v_freq,
        'sequence_length_bp', LENGTH(UPPER(TRIM(p_sequence)))
    );
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: apply_rna_interference
-- Records an siRNA silencing event and optionally dampens the target node.
-- Returns the silencing result including estimated node suppression.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION apply_rna_interference(
    p_twin_id               UUID,
    p_sirna_molecule_id     BIGINT,
    p_target_molecule_id    BIGINT,
    p_silencing_efficiency  REAL,
    p_off_target_score      REAL    DEFAULT 0.0,
    p_duration_h            REAL    DEFAULT 48.0
)
RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE
    v_log_id        BIGINT;
    v_target_node   INTEGER;
    v_suppression   REAL;
    v_sirna_type    bio_molecule_type;
BEGIN
    -- Validate molecule type
    SELECT molecule_type INTO v_sirna_type
    FROM bio_molecule_registry WHERE id = p_sirna_molecule_id;

    IF v_sirna_type != 'siRNA' THEN
        RAISE EXCEPTION 'Molecule % is not siRNA (type: %)', p_sirna_molecule_id, v_sirna_type
            USING ERRCODE = '22023';
    END IF;

    -- Look up which node the target molecule is linked to
    SELECT linked_node_id INTO v_target_node
    FROM bio_molecule_registry WHERE id = p_target_molecule_id;

    -- Node suppression = silencing_efficiency × (1 - off_target_score)
    v_suppression := p_silencing_efficiency * (1.0 - p_off_target_score);

    INSERT INTO rna_interference_log (
        twin_id, sirna_molecule_id, target_molecule_id,
        silencing_efficiency, off_target_score,
        target_node_id, node_signal_suppression,
        estimated_duration_h,
        expires_at
    ) VALUES (
        p_twin_id, p_sirna_molecule_id, p_target_molecule_id,
        p_silencing_efficiency, p_off_target_score,
        v_target_node, v_suppression,
        p_duration_h,
        NOW() + (p_duration_h || ' hours')::INTERVAL
    )
    RETURNING id INTO v_log_id;

    RETURN jsonb_build_object(
        'log_id',                 v_log_id,
        'silencing_efficiency',   p_silencing_efficiency,
        'off_target_score',       p_off_target_score,
        'node_signal_suppression', v_suppression,
        'target_node_id',         v_target_node,
        'expires_at',             NOW() + (p_duration_h || ' hours')::INTERVAL
    );
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: design_crispr_guide
-- Registers a guide RNA and its target locus.
-- Does NOT execute the edit — a separate UPDATE (with approved_by_sig) is
-- required for knockout/knockin/base_edit to set executed_at.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION design_crispr_guide(
    p_twin_id           UUID,
    p_guide_molecule_id BIGINT,
    p_edit_type         crispr_edit_type,
    p_target_sequence   TEXT,
    p_target_gene       TEXT    DEFAULT NULL,
    p_pam_site          TEXT    DEFAULT 'NGG',
    p_on_target_score   REAL    DEFAULT 0.8,
    p_off_target_score  REAL    DEFAULT 0.1
)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    v_guide_id BIGINT;
    v_guide_type bio_molecule_type;
BEGIN
    SELECT molecule_type INTO v_guide_type
    FROM bio_molecule_registry WHERE id = p_guide_molecule_id;

    IF v_guide_type != 'guide_rna' THEN
        RAISE EXCEPTION 'Molecule % is not guide_rna (type: %)', p_guide_molecule_id, v_guide_type
            USING ERRCODE = '22023';
    END IF;

    INSERT INTO crispr_guide_registry (
        twin_id, guide_molecule_id, edit_type,
        target_sequence, pam_site, target_gene,
        on_target_score, off_target_score
    ) VALUES (
        p_twin_id, p_guide_molecule_id, p_edit_type,
        UPPER(TRIM(p_target_sequence)), p_pam_site, p_target_gene,
        p_on_target_score, p_off_target_score
    )
    RETURNING id INTO v_guide_id;

    RETURN v_guide_id;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: get_molecular_rf_spectrum
-- Returns all molecules for a twin with their computed GHz frequencies,
-- sorted by frequency — a "spectrum view" of the twin's molecular biology.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION get_molecular_rf_spectrum(p_twin_id UUID)
RETURNS TABLE (
    molecule_id         BIGINT,
    molecule_type       bio_molecule_type,
    gene_symbol         TEXT,
    linked_node_id      INTEGER,
    nucleotide_sequence TEXT,
    sequence_length_bp  INTEGER,
    computed_freq_ghz   REAL,
    is_locked           BOOLEAN
)
LANGUAGE sql STABLE AS $$
    SELECT id, molecule_type, gene_symbol, linked_node_id,
           nucleotide_sequence, sequence_length_bp,
           computed_freq_ghz, is_locked
    FROM bio_molecule_registry
    WHERE twin_id = p_twin_id
    ORDER BY computed_freq_ghz ASC, molecule_type, gene_symbol;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: get_bio_node_state
-- Returns the complete biological state for a single node:
-- molecule registry entries, active siRNA suppressions, epigenetic marks,
-- and any CRISPR guides targeting its linked gene.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION get_bio_node_state(p_twin_id UUID, p_node_id INTEGER)
RETURNS JSONB LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_object(
        'node_id',       p_node_id,
        'molecules',     (
            SELECT jsonb_agg(jsonb_build_object(
                'molecule_id',   id,
                'type',          molecule_type,
                'gene',          gene_symbol,
                'freq_ghz',      computed_freq_ghz,
                'locked',        is_locked
            ))
            FROM bio_molecule_registry
            WHERE twin_id = p_twin_id AND linked_node_id = p_node_id
        ),
        'active_silencing', (
            SELECT jsonb_agg(jsonb_build_object(
                'log_id',        id,
                'efficiency',    silencing_efficiency,
                'suppression',   node_signal_suppression,
                'expires_at',    expires_at
            ))
            FROM rna_interference_log
            WHERE twin_id = p_twin_id
              AND target_node_id = p_node_id
              AND (expires_at IS NULL OR expires_at > NOW())
        ),
        'epigenetic_marks', (
            SELECT jsonb_agg(jsonb_build_object(
                'mark_type',    mark_type,
                'level',        mark_level,
                'modifier',     expression_modifier,
                'reversible',   is_reversible,
                'heritable',    is_heritable
            ))
            FROM epigenetic_node_states
            WHERE twin_id = p_twin_id
              AND node_id = p_node_id
              AND (expires_at IS NULL OR expires_at > NOW())
        ),
        'crispr_guides', (
            SELECT jsonb_agg(jsonb_build_object(
                'guide_id',       g.id,
                'edit_type',      g.edit_type,
                'target_gene',    g.target_gene,
                'on_target',      g.on_target_score,
                'approved',       g.approved_by_sig IS NOT NULL,
                'executed',       g.executed_at IS NOT NULL
            ))
            FROM crispr_guide_registry g
            JOIN bio_molecule_registry m ON m.id = g.guide_molecule_id
            WHERE g.twin_id = p_twin_id
              AND m.linked_node_id = p_node_id
        )
    );
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW: molecular_node_map
-- Joins bio_molecule_registry with mesh_nodes for a full spectrum view.
-- Shows which biological molecules underpin each mesh node's carrier frequency.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE VIEW molecular_node_map AS
SELECT
    m.twin_id,
    m.linked_node_id                        AS node_id,
    n.node_code,
    n.modality,
    m.id                                    AS molecule_id,
    m.molecule_type,
    m.gene_symbol,
    m.source_region,
    m.chromosome,
    m.computed_freq_ghz,
    m.sequence_length_bp,
    m.is_locked,
    n.node_carrier_ghz                      AS sdr_carrier_ghz,
    ABS(m.computed_freq_ghz - n.node_carrier_ghz) AS freq_alignment_delta
FROM bio_molecule_registry m
JOIN mesh_nodes n ON n.node_id = m.linked_node_id
ORDER BY m.twin_id, m.computed_freq_ghz;

COMMIT;
