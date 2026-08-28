-- Make illumina_run.read1_length and read2_length nullable so a run whose
-- source document does not record read lengths still gets an illumina_run row.
-- NULL means "this document does not state it", which 0 cannot express.
-- Brings a database forward to match schema.sql.
--
-- SQLite cannot drop NOT NULL in place, so the table is rebuilt. Dependent
-- views must be dropped first (SQLite refuses to drop a table a view
-- references) and are recreated verbatim afterwards. The dependency set is
-- transitive: omnibus_standard_metag_v101_bioinformatics selects from
-- omnibus_standard_metag_v90_bioinformatics.
--
-- PRAGMA foreign_keys is deliberately not set here: the migration runner wraps
-- each .sql patch in a transaction, and SQLite silently ignores that pragma
-- inside one. Nothing references illumina_run at this point, so the rebuild is safe with
-- foreign keys enforced.

DROP VIEW omnibus_standard_metag_v101_bioinformatics;
DROP VIEW omnibus_standard_metag_v90_bioinformatics;
DROP VIEW omnibus_illumina_settings;
DROP VIEW omnibus_illumina_reads;

CREATE TABLE illumina_run_new (
    run_idx              INTEGER PRIMARY KEY REFERENCES processing_run(run_idx),
    read1_length        INTEGER,
    read2_length        INTEGER,
    reverse_complement  BOOLEAN,
    mask_short_reads    TEXT,
    override_cycles     TEXT,
    forward_adapter     TEXT,
    reverse_adapter     TEXT,
    barcodes_are_rc     BOOLEAN
);

INSERT INTO illumina_run_new SELECT * FROM illumina_run;
DROP TABLE illumina_run;
ALTER TABLE illumina_run_new RENAME TO illumina_run;

CREATE VIEW omnibus_illumina_reads AS
    SELECT sr.run_idx,
        ir.read1_length AS "read1_length",
        ir.read2_length AS "read2_length"
    FROM processing_run sr
    JOIN illumina_run ir ON sr.run_idx = ir.run_idx;

CREATE VIEW omnibus_illumina_settings AS
    SELECT sr.run_idx,
        ir.reverse_complement AS "ReverseComplement",
        ir.mask_short_reads AS "MaskShortReads",
        ir.override_cycles AS "OverrideCycles"
    FROM processing_run sr
    JOIN illumina_run ir ON sr.run_idx = ir.run_idx;

CREATE VIEW omnibus_standard_metag_v90_bioinformatics AS
    SELECT DISTINCT cs.run_idx,
        p.project_name AS "Sample_Project",
        p.external_project_id AS "QiitaID",
        ir.barcodes_are_rc AS "BarcodesAreRC",
        ir.forward_adapter AS "ForwardAdapter",
        ir.reverse_adapter AS "ReverseAdapter",
        p.human_filtering AS "HumanFiltering",
        p.library_construction_protocol AS "library_construction_protocol",
        p.experiment_design_description AS "experiment_design_description"
    FROM prepped_sample prs
    JOIN compression_sample cs ON prs.compression_sample_idx = cs.compression_sample_idx
    JOIN input_sample ins ON cs.input_sample_idx = ins.input_sample_idx
    JOIN project p ON ins.project_idx = p.project_idx
    JOIN processing_run sr ON cs.run_idx = sr.run_idx
    JOIN illumina_run ir ON sr.run_idx = ir.run_idx
    GROUP BY cs.run_idx, p.project_idx, p.project_name, p.external_project_id,
             ir.barcodes_are_rc, ir.forward_adapter, ir.reverse_adapter,
             p.human_filtering, p.library_construction_protocol,
             p.experiment_design_description;

CREATE VIEW omnibus_standard_metag_v101_bioinformatics AS
    SELECT v90.*,
        EXISTS (SELECT 1 FROM replicated_samples rs
                WHERE rs.run_idx = v90.run_idx) AS "contains_replicates"
    FROM omnibus_standard_metag_v90_bioinformatics v90;
