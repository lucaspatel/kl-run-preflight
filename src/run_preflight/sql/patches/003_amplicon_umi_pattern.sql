-- Add the UMI pattern to amplicon_run.
--
-- Long-read (PacBio) amplicon protocols carry unique molecular identifiers in
-- the construct flanking the 16S primers. The UMI *values* are detected and
-- extracted downstream (in rrna-operon), but the permissive UMI *pattern* is a
-- per-run protocol fact — different protocols use different patterns — so the
-- pre-flight records it. NULL for runs that carry no UMI (every amplicon run to
-- date), so the column is nullable and purely additive.
--
-- PRAGMA foreign_keys is deliberately not set: the migration runner wraps each
-- .sql patch in a transaction, and SQLite silently ignores that pragma inside
-- one.

ALTER TABLE amplicon_run ADD COLUMN umi_pattern TEXT;
