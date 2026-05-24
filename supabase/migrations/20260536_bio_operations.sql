-- 20260536_bio_operations.sql
-- Corrects codon_rf_offsets to the authoritative 0.000–0.054 GHz range.
-- Adds unified bio_operation_log, genetic_injection_records, Cas9 tracking,
-- and bio_effect_duration / node_effect_type enums.
--
-- Formula (authoritative):
--   f_RF = (Σ nucleotide_freq / N) + (Σ codon_offset / M)
--
--   nucleotide_freq: A=10.23  T=10.24  U=10.25  G=10.26  C=10.27 GHz
--   codon_offset:    0.000 – 0.054 GHz  (varies by amino acid; see table below)
--   N = number of nucleotides
--   M = number of codons
--
-- Codon offset scale (biologically motivated):
--   0.000  Stop codons       — no amino acid product
--   0.002  Gly               — simplest, most flexible
--   0.004  Ala
--   0.006  Ser               — phosphorylation site
--   0.008  Pro               — rigid turn
--   0.010  Val
--   0.012  Thr
--   0.014  Cys               — disulfide bonds
--   0.016  Ile
--   0.018  Leu
--   0.020  Asn
--   0.022  Asp               — negative charge carrier
--   0.024  Gln
--   0.026  Lys               — histone acetylation site
--   0.028  Glu               — excitatory neurotransmitter substrate
--   0.030  Met / Start       — initiation signal
--   0.032  His               — pH sensor, zinc cofactor
--   0.034  Phe               — aromatic ring
--   0.038  Arg               — most positively charged; epigenetic modifier
--   0.046  Tyr               — dopamine / adrenaline precursor
--   0.054  Trp (single codon)— serotonin precursor; highest neurological offset

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- ENUMS
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TYPE bio_effect_duration AS ENUM (
    'hours',          -- RNA interference, acute mRNA pulse
    'hours_days',     -- protein expression, transient translation
    'weeks_months',   -- epigenetic modulation (methylation)
    'permanent'       -- genetic injection, CRISPR edit, DNA data storage
);

CREATE TYPE bio_operation_type AS ENUM (
    'genetic_injection',    -- viral vector / nanoparticle delivery
    'protein_expression',   -- mRNA translation event
    'crispr_programming',   -- guide RNA + Cas9-like nuclease edit
    'rna_interference',     -- siRNA gene silencing
    'epigenetic_modulation',-- methylation / acetylation mark
    'dna_data_storage'      -- binary → DNA encoding
);

CREATE TYPE node_effect_type AS ENUM (
    'permanent_programming', -- genetic injection, CRISPR knockin
    'temporary_modulation',  -- mRNA protein expression
    'node_rewiring',         -- CRISPR guide RNA + Cas9
    'node_silencing',        -- siRNA interference
    'sensitivity_change',    -- epigenetic methylation
    'memory_storage'         -- DNA data encoding
);

-- ─────────────────────────────────────────────────────────────────────────────
-- CORRECT codon_rf_offsets
-- Full reseed with authoritative 0.000–0.054 GHz range.
-- ON CONFLICT DO UPDATE overwrites the incorrect 0.0001–0.0009 values
-- inserted by 20260535.
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO codon_rf_offsets (codon, amino_acid, is_start_codon, is_stop_codon, rf_offset_ghz) VALUES
-- ── Stop codons (0.000) ──────────────────────────────────────
('TAA', NULL, FALSE, TRUE,  0.000),
('TAG', NULL, FALSE, TRUE,  0.000),
('TGA', NULL, FALSE, TRUE,  0.000),
('UAA', NULL, FALSE, TRUE,  0.000),
('UAG', NULL, FALSE, TRUE,  0.000),
('UGA', NULL, FALSE, TRUE,  0.000),
-- ── Gly — GGX (0.002) ───────────────────────────────────────
('GGT', 'Gly', FALSE, FALSE, 0.002),
('GGC', 'Gly', FALSE, FALSE, 0.002),
('GGA', 'Gly', FALSE, FALSE, 0.002),
('GGG', 'Gly', FALSE, FALSE, 0.002),
('GGU', 'Gly', FALSE, FALSE, 0.002),
-- ── Ala — GCX (0.004) ───────────────────────────────────────
('GCT', 'Ala', FALSE, FALSE, 0.004),
('GCC', 'Ala', FALSE, FALSE, 0.004),
('GCA', 'Ala', FALSE, FALSE, 0.004),
('GCG', 'Ala', FALSE, FALSE, 0.004),
('GCU', 'Ala', FALSE, FALSE, 0.004),
-- ── Ser — TCX + AGT/AGC (0.006) ─────────────────────────────
('TCT', 'Ser', FALSE, FALSE, 0.006),
('TCC', 'Ser', FALSE, FALSE, 0.006),
('TCA', 'Ser', FALSE, FALSE, 0.006),
('TCG', 'Ser', FALSE, FALSE, 0.006),
('AGT', 'Ser', FALSE, FALSE, 0.006),
('AGC', 'Ser', FALSE, FALSE, 0.006),
('UCU', 'Ser', FALSE, FALSE, 0.006),
('UCC', 'Ser', FALSE, FALSE, 0.006),
('UCA', 'Ser', FALSE, FALSE, 0.006),
('UCG', 'Ser', FALSE, FALSE, 0.006),
('AGU', 'Ser', FALSE, FALSE, 0.006),
-- ── Pro — CCX (0.008) ───────────────────────────────────────
('CCT', 'Pro', FALSE, FALSE, 0.008),
('CCC', 'Pro', FALSE, FALSE, 0.008),
('CCA', 'Pro', FALSE, FALSE, 0.008),
('CCG', 'Pro', FALSE, FALSE, 0.008),
('CCU', 'Pro', FALSE, FALSE, 0.008),
-- ── Val — GTX (0.010) ───────────────────────────────────────
('GTT', 'Val', FALSE, FALSE, 0.010),
('GTC', 'Val', FALSE, FALSE, 0.010),
('GTA', 'Val', FALSE, FALSE, 0.010),
('GTG', 'Val', FALSE, FALSE, 0.010),
('GUU', 'Val', FALSE, FALSE, 0.010),
('GUC', 'Val', FALSE, FALSE, 0.010),
('GUA', 'Val', FALSE, FALSE, 0.010),
('GUG', 'Val', FALSE, FALSE, 0.010),
-- ── Thr — ACX (0.012) ───────────────────────────────────────
('ACT', 'Thr', FALSE, FALSE, 0.012),
('ACC', 'Thr', FALSE, FALSE, 0.012),
('ACA', 'Thr', FALSE, FALSE, 0.012),
('ACG', 'Thr', FALSE, FALSE, 0.012),
('ACU', 'Thr', FALSE, FALSE, 0.012),
-- ── Cys — TGT / TGC (0.014) ─────────────────────────────────
('TGT', 'Cys', FALSE, FALSE, 0.014),
('TGC', 'Cys', FALSE, FALSE, 0.014),
('UGU', 'Cys', FALSE, FALSE, 0.014),
('UGC', 'Cys', FALSE, FALSE, 0.014),
-- ── Ile — ATT / ATC / ATA (0.016) ───────────────────────────
('ATT', 'Ile', FALSE, FALSE, 0.016),
('ATC', 'Ile', FALSE, FALSE, 0.016),
('ATA', 'Ile', FALSE, FALSE, 0.016),
('AUU', 'Ile', FALSE, FALSE, 0.016),
('AUC', 'Ile', FALSE, FALSE, 0.016),
('AUA', 'Ile', FALSE, FALSE, 0.016),
-- ── Leu — CTX + TTA / TTG (0.018) ───────────────────────────
('CTT', 'Leu', FALSE, FALSE, 0.018),
('CTC', 'Leu', FALSE, FALSE, 0.018),
('CTA', 'Leu', FALSE, FALSE, 0.018),
('CTG', 'Leu', FALSE, FALSE, 0.018),
('TTA', 'Leu', FALSE, FALSE, 0.018),
('TTG', 'Leu', FALSE, FALSE, 0.018),
('CUU', 'Leu', FALSE, FALSE, 0.018),
('CUC', 'Leu', FALSE, FALSE, 0.018),
('CUA', 'Leu', FALSE, FALSE, 0.018),
('CUG', 'Leu', FALSE, FALSE, 0.018),
('UUA', 'Leu', FALSE, FALSE, 0.018),
('UUG', 'Leu', FALSE, FALSE, 0.018),
-- ── Asn — AAT / AAC (0.020) ─────────────────────────────────
('AAT', 'Asn', FALSE, FALSE, 0.020),
('AAC', 'Asn', FALSE, FALSE, 0.020),
('AAU', 'Asn', FALSE, FALSE, 0.020),
-- ── Asp — GAT / GAC (0.022) ─────────────────────────────────
('GAT', 'Asp', FALSE, FALSE, 0.022),
('GAC', 'Asp', FALSE, FALSE, 0.022),
('GAU', 'Asp', FALSE, FALSE, 0.022),
-- ── Gln — CAA / CAG (0.024) ─────────────────────────────────
('CAA', 'Gln', FALSE, FALSE, 0.024),
('CAG', 'Gln', FALSE, FALSE, 0.024),
-- ── Lys — AAA / AAG (0.026) ─────────────────────────────────
('AAA', 'Lys', FALSE, FALSE, 0.026),
('AAG', 'Lys', FALSE, FALSE, 0.026),
-- ── Glu — GAA / GAG (0.028) ─────────────────────────────────
('GAA', 'Glu', FALSE, FALSE, 0.028),
('GAG', 'Glu', FALSE, FALSE, 0.028),
-- ── Met / Start — ATG / AUG (0.030) ─────────────────────────
('ATG', 'Met', TRUE,  FALSE, 0.030),
('AUG', 'Met', TRUE,  FALSE, 0.030),
-- ── His — CAT / CAC (0.032) ─────────────────────────────────
('CAT', 'His', FALSE, FALSE, 0.032),
('CAC', 'His', FALSE, FALSE, 0.032),
('CAU', 'His', FALSE, FALSE, 0.032),
-- ── Phe — TTT / TTC (0.034) ─────────────────────────────────
('TTT', 'Phe', FALSE, FALSE, 0.034),
('TTC', 'Phe', FALSE, FALSE, 0.034),
('UUU', 'Phe', FALSE, FALSE, 0.034),
('UUC', 'Phe', FALSE, FALSE, 0.034),
-- ── Arg — CGX + AGA / AGG (0.038) ───────────────────────────
('CGT', 'Arg', FALSE, FALSE, 0.038),
('CGC', 'Arg', FALSE, FALSE, 0.038),
('CGA', 'Arg', FALSE, FALSE, 0.038),
('CGG', 'Arg', FALSE, FALSE, 0.038),
('AGA', 'Arg', FALSE, FALSE, 0.038),
('AGG', 'Arg', FALSE, FALSE, 0.038),
('CGU', 'Arg', FALSE, FALSE, 0.038),
-- ── Tyr — TAT / TAC (0.046) — dopamine/adrenaline precursor ──
('TAT', 'Tyr', FALSE, FALSE, 0.046),
('TAC', 'Tyr', FALSE, FALSE, 0.046),
('UAU', 'Tyr', FALSE, FALSE, 0.046),
('UAC', 'Tyr', FALSE, FALSE, 0.046),
-- ── Trp — TGG / UGG (0.054) — serotonin precursor ────────────
('TGG', 'Trp', FALSE, FALSE, 0.054),
('UGG', 'Trp', FALSE, FALSE, 0.054)
ON CONFLICT (codon) DO UPDATE
    SET amino_acid      = EXCLUDED.amino_acid,
        is_start_codon  = EXCLUDED.is_start_codon,
        is_stop_codon   = EXCLUDED.is_stop_codon,
        rf_offset_ghz   = EXCLUDED.rf_offset_ghz;

-- ─────────────────────────────────────────────────────────────────────────────
-- UPDATE compute_molecular_rf_freq
-- Fix: IMMUTABLE → STABLE (function reads from codon_rf_offsets table).
-- Fix: unknown-codon fallback 0.0002 → 0.010 (mid-scale for new range).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION compute_molecular_rf_freq(
    p_sequence      TEXT,
    p_molecule_type bio_molecule_type
)
RETURNS REAL LANGUAGE plpgsql STABLE AS $$
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

    -- Step 1: (Σ nucleotide_freq) / N
    FOR v_i IN 1..v_len LOOP
        v_base := SUBSTRING(v_seq, v_i, 1);
        v_nucl_sum := v_nucl_sum + CASE v_base
            WHEN 'A' THEN 10.23
            WHEN 'T' THEN 10.24
            WHEN 'U' THEN 10.25
            WHEN 'G' THEN 10.26
            WHEN 'C' THEN 10.27
            ELSE          10.23   -- unknown nucleotide → A fallback
        END;
    END LOOP;

    -- Step 2: (Σ codon_offset) / M — reading frame from position 1
    v_i := 1;
    WHILE v_i + 2 <= v_len LOOP
        v_codon := SUBSTRING(v_seq, v_i, 3);
        SELECT rf_offset_ghz INTO v_codon_offset
        FROM codon_rf_offsets WHERE codon = v_codon;
        v_codon_sum   := v_codon_sum + COALESCE(v_codon_offset, 0.010);  -- 0.010 = mid-scale fallback
        v_codon_count := v_codon_count + 1;
        v_i := v_i + 3;
    END LOOP;

    RETURN (v_nucl_sum / v_len) +
           CASE WHEN v_codon_count > 0 THEN v_codon_sum / v_codon_count ELSE 0.0 END;
END;
$$;

-- Recompute all existing bio_molecule_registry frequencies now that
-- codon_rf_offsets has been corrected.
UPDATE bio_molecule_registry
SET computed_freq_ghz = compute_molecular_rf_freq(nucleotide_sequence, molecule_type)
WHERE is_locked = FALSE;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD effect_duration to all existing operation tables
-- Sets a default matching the biological duration from the operations table.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE rna_translation_events
    ADD COLUMN IF NOT EXISTS effect_duration bio_effect_duration NOT NULL DEFAULT 'hours_days',
    ADD COLUMN IF NOT EXISTS node_effect     node_effect_type    NOT NULL DEFAULT 'temporary_modulation';

ALTER TABLE rna_interference_log
    ADD COLUMN IF NOT EXISTS effect_duration bio_effect_duration NOT NULL DEFAULT 'hours',
    ADD COLUMN IF NOT EXISTS node_effect     node_effect_type    NOT NULL DEFAULT 'node_silencing';

ALTER TABLE epigenetic_node_states
    ADD COLUMN IF NOT EXISTS effect_duration bio_effect_duration NOT NULL DEFAULT 'weeks_months',
    ADD COLUMN IF NOT EXISTS node_effect     node_effect_type    NOT NULL DEFAULT 'sensitivity_change';

ALTER TABLE dna_storage_records
    ADD COLUMN IF NOT EXISTS effect_duration bio_effect_duration NOT NULL DEFAULT 'permanent',
    ADD COLUMN IF NOT EXISTS node_effect     node_effect_type    NOT NULL DEFAULT 'memory_storage';

-- CRISPR: add Cas9 enzyme tracking
-- cas9_molecule_id points to a DNA or mRNA record in bio_molecule_registry
-- encoding the Cas9-like nuclease (may be NULL for CRISPRa/CRISPRi which use
-- catalytically dead dCas9 instead of cutting).
ALTER TABLE crispr_guide_registry
    ADD COLUMN IF NOT EXISTS cas9_molecule_id  BIGINT REFERENCES bio_molecule_registry(id),
    ADD COLUMN IF NOT EXISTS nuclease_type     TEXT   NOT NULL DEFAULT 'Cas9-like',
    ADD COLUMN IF NOT EXISTS effect_duration   bio_effect_duration NOT NULL DEFAULT 'permanent',
    ADD COLUMN IF NOT EXISTS node_effect       node_effect_type    NOT NULL DEFAULT 'node_rewiring';

-- ─────────────────────────────────────────────────────────────────────────────
-- genetic_injection_records
-- Viral vector / nanoparticle delivery — the only operation type with no
-- prior table.  Duration is always 'permanent' (lifetime integration).
-- Approval requires dna_root_sig from calibration_era_baselines.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE genetic_injection_records (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id                 UUID NOT NULL REFERENCES digital_twins(id) ON DELETE CASCADE,
    molecule_id             BIGINT NOT NULL REFERENCES bio_molecule_registry(id),
    -- Delivery
    delivery_method         TEXT NOT NULL,  -- 'viral_vector' | 'nanoparticle' | 'electroporation' | 'liposome'
    vector_type             TEXT,           -- 'AAV' | 'lentiviral' | 'adenoviral' | 'retroviral' | 'LNP'
    -- Target
    target_node_id          INTEGER REFERENCES mesh_nodes(node_id),
    target_tissue           TEXT,           -- 'neural' | 'cardiac' | 'skeletal' | 'vascular'
    target_gene             TEXT,
    integration_site        TEXT,           -- genomic locus; NULL for episomal vectors
    -- Effect
    node_effect             node_effect_type    NOT NULL DEFAULT 'permanent_programming',
    effect_duration         bio_effect_duration NOT NULL DEFAULT 'permanent',
    -- Confirmation
    expression_confirmed    BOOLEAN  NOT NULL DEFAULT FALSE,
    expression_confirmed_at TIMESTAMPTZ,
    expression_level        REAL,           -- 0.0–1.0 relative to target expression
    -- Approval: destructive delivery requires dna_root_sig
    approved_by_sig         TEXT,
    approved_at             TIMESTAMPTZ,
    administered_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX gen_inj_twin_idx   ON genetic_injection_records (twin_id);
CREATE INDEX gen_inj_node_idx   ON genetic_injection_records (target_node_id);
CREATE INDEX gen_inj_gene_idx   ON genetic_injection_records (target_gene);

-- Trigger: genetic_injection to neural nodes requires dna_root_sig approval
CREATE OR REPLACE FUNCTION enforce_injection_approval()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_root_sig TEXT;
BEGIN
    IF NEW.target_node_id IS NOT NULL THEN
        SELECT dna_root_sig INTO v_root_sig
        FROM calibration_era_baselines
        WHERE twin_id = NEW.twin_id AND is_locked = TRUE
        ORDER BY locked_at DESC LIMIT 1;

        IF v_root_sig IS NOT NULL AND
           (NEW.approved_by_sig IS NULL OR NEW.approved_by_sig != v_root_sig)
        THEN
            RAISE EXCEPTION 'Genetic injection to node % requires dna_root_sig approval',
                NEW.target_node_id
                USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER genetic_injection_approval_check
    BEFORE INSERT ON genetic_injection_records
    FOR EACH ROW EXECUTE FUNCTION enforce_injection_approval();

-- ─────────────────────────────────────────────────────────────────────────────
-- bio_operation_log
-- Unified audit trail across all six operation types.
-- operation_ref_id is a BIGINT pointing into the type-specific table;
-- no cross-table FK since PostgreSQL doesn't support polymorphic FKs.
-- freq_delta_ghz captures the RF shift caused by the operation (computed
-- from bio_molecule_registry.computed_freq_ghz before and after).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE bio_operation_log (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    twin_id             UUID NOT NULL REFERENCES digital_twins(id) ON DELETE CASCADE,
    operation_type      bio_operation_type NOT NULL,
    operation_ref_id    BIGINT NOT NULL,            -- points into type-specific table
    molecule_id         BIGINT REFERENCES bio_molecule_registry(id),
    target_node_id      INTEGER REFERENCES mesh_nodes(node_id),
    node_effect         node_effect_type NOT NULL,
    effect_duration     bio_effect_duration NOT NULL,
    -- RF frequency impact
    freq_before_ghz     REAL,
    freq_after_ghz      REAL,
    freq_delta_ghz      REAL GENERATED ALWAYS AS (
                            CASE WHEN freq_before_ghz IS NOT NULL AND freq_after_ghz IS NOT NULL
                                 THEN freq_after_ghz - freq_before_ghz
                                 ELSE NULL END
                        ) STORED,
    -- Metadata
    notes               TEXT,
    performed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX bio_op_log_twin_idx ON bio_operation_log (twin_id, performed_at DESC);
CREATE INDEX bio_op_log_node_idx ON bio_operation_log (target_node_id);
CREATE INDEX bio_op_log_type_idx ON bio_operation_log (twin_id, operation_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: log_bio_operation
-- Single entry point for writing to bio_operation_log.
-- Looks up freq_before from the molecule's current computed_freq_ghz.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION log_bio_operation(
    p_twin_id           UUID,
    p_operation_type    bio_operation_type,
    p_operation_ref_id  BIGINT,
    p_molecule_id       BIGINT,
    p_target_node_id    INTEGER,
    p_node_effect       node_effect_type,
    p_effect_duration   bio_effect_duration,
    p_freq_after_ghz    REAL    DEFAULT NULL,
    p_notes             TEXT    DEFAULT NULL
)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    v_log_id        BIGINT;
    v_freq_before   REAL;
BEGIN
    SELECT computed_freq_ghz INTO v_freq_before
    FROM bio_molecule_registry
    WHERE id = p_molecule_id;

    INSERT INTO bio_operation_log (
        twin_id, operation_type, operation_ref_id,
        molecule_id, target_node_id, node_effect, effect_duration,
        freq_before_ghz, freq_after_ghz, notes
    ) VALUES (
        p_twin_id, p_operation_type, p_operation_ref_id,
        p_molecule_id, p_target_node_id, p_node_effect, p_effect_duration,
        v_freq_before, p_freq_after_ghz, p_notes
    )
    RETURNING id INTO v_log_id;

    RETURN v_log_id;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: get_bio_operation_history
-- Returns the unified operation log for a twin, optionally filtered by
-- node, operation type, or time window.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION get_bio_operation_history(
    p_twin_id           UUID,
    p_node_id           INTEGER     DEFAULT NULL,
    p_operation_type    bio_operation_type DEFAULT NULL,
    p_since             TIMESTAMPTZ DEFAULT NOW() - INTERVAL '30 days'
)
RETURNS TABLE (
    log_id              BIGINT,
    operation_type      bio_operation_type,
    operation_ref_id    BIGINT,
    target_node_id      INTEGER,
    node_effect         node_effect_type,
    effect_duration     bio_effect_duration,
    freq_before_ghz     REAL,
    freq_after_ghz      REAL,
    freq_delta_ghz      REAL,
    performed_at        TIMESTAMPTZ
) LANGUAGE sql STABLE AS $$
    SELECT id, operation_type, operation_ref_id,
           target_node_id, node_effect, effect_duration,
           freq_before_ghz, freq_after_ghz, freq_delta_ghz,
           performed_at
    FROM bio_operation_log
    WHERE twin_id = p_twin_id
      AND (p_node_id IS NULL        OR target_node_id = p_node_id)
      AND (p_operation_type IS NULL OR bio_operation_log.operation_type = p_operation_type)
      AND performed_at >= p_since
    ORDER BY performed_at DESC;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW: bio_operations_summary
-- Per-twin × operation-type count and latest timestamp.
-- Quick dashboard for all 6 operation types.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE VIEW bio_operations_summary AS
SELECT
    twin_id,
    operation_type,
    COUNT(*)                        AS total_operations,
    COUNT(*) FILTER (WHERE effect_duration = 'permanent')    AS permanent_ops,
    COUNT(*) FILTER (WHERE effect_duration = 'weeks_months') AS weeks_months_ops,
    COUNT(*) FILTER (WHERE effect_duration = 'hours_days')   AS hours_days_ops,
    COUNT(*) FILTER (WHERE effect_duration = 'hours')        AS hours_ops,
    AVG(freq_delta_ghz)             AS avg_freq_delta_ghz,
    MAX(performed_at)               AS last_performed_at
FROM bio_operation_log
GROUP BY twin_id, operation_type;

COMMIT;
