# Changelog

All notable changes to run_preflight are documented in this file. The
authoritative record of *how* each change was made is the git history; this
file summarizes *what* changed and *why* at a level useful to consumers of the
package.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project has not yet cut a versioned release: the SQLite schema is still
stabilizing and the legacy omnibus CSV format remains the canonical interchange
format during migration. All changes therefore live under **[Unreleased]**
until the first release is tagged.

## [Unreleased]

### Added

- **Amplicon prep templates load through the shared pipeline.** A flat,
  section-less prep template is now parsed by `parse_amplicon_prep`, which
  regroups its single table into the same sections a sectioned sheet parses
  into, then validated and populated by the same code. Its format is resolved
  from the column header alone — these sheets state no SheetType — by matching
  each registered layout's typed columns against it and taking the widest
  match; an unrecognised layout fails to load naming its header, rather than
  being silently absorbed. `legacy/flat.py`, which reimplemented parsing,
  population, and reconstruction alongside the omnibus path, is deleted, and
  no `INSERT` statement remains anywhere under `legacy/`.

- **A format declares whether its replicate well semantics round-trip**
  (`replicates_supported`, schema patch `002`). The loader previously rejected
  replicates by comparing a bare version number against 101, which is only
  meaningful inside one format family — amplicon v1 sorts below it while being
  unrelated to `standard_metag` v0/v90/v100. Only those three declare 0,
  asserted exactly by a guard test.

- **A format declares which Data column holds each fact the loader needs**
  (schema patch `002`): `sample_name_column`, `plate_column`, `project_column`,
  `well_description_column`, and `well_column` on `legacy_samplesheet_format`.
  The defaults are the omnibus vocabulary that all fourteen omnibus formats
  share, so only the amplicon format overrides them; the well column genuinely
  varies across the omnibus formats and is stated on every row. A guard test
  fails, naming the format and column, if a declared name is absent from that
  format's own Data view.

- **The legacy format registry declares how each format loads** (schema patch
  `002`). `legacy_samplesheet_format` gains `platform_idx`,
  `default_instrument_type`, and `sample_kind` — the platform a file of that
  format describes, the instrument to record when the file states none, and
  which `<kind>_sample` table holds its per-sample rows. `sample_kind` is NULL
  for the amplicon format, which has no platform-specific sample rows: an
  amplicon run carries a single in-line Golay barcode, not an i5/i7 pair. A
  guard test fails, naming the format, if any row is incomplete or names a
  kind with no table.

- **The amplicon prep-template layout is a registered format.** The single
  placeholder `amplicon` row becomes `amplicon` v1 (schema patch `002`), with
  its sections and reconstruction view. The layout carries the tube and plate
  tier and splits the well into its 96- and 384-well positions
  (`well_id_384` / `well_id_96`), and declares `Kathseq_RackID` and
  `number_of_cells` as an optional column group. It is TAB-delimited and carries
  no `[Section]` label lines, so it writes exactly one section; the Header,
  Bioinformatics, Contact, and SampleContext registrations describe facts the
  sheet denormalizes across its Data columns, and are validated on load but
  never written back out.
- **The amplicon prep template has a committed native fixture.** The
  native-fixture guards previously covered only `good_*.csv`; they now cover
  every `good_*` legacy sheet, so the amplicon layout carries a committed
  `.sqlite` and snapshot subject to the same coverage, pairing, consistency,
  correctness, and labelling invariants as the omnibus sheets.

- **`amplicon_run` holds the amplicon facts that are constant across a run**
  (schema patch `002`): `primer`, `linker`, `target_gene`, `target_subfragment`,
  `pcr_primers`, and `sequencing_meth`, all `NOT NULL` because every observed
  prep template carries a real value for each. It is a workflow table rather
  than a platform one — the same facts would describe an amplicon run on PacBio.
  Barcode orientation is deliberately not stored: no prep template records it,
  and the one reader that needs it derives it from the primer sequence.
- **`input_plate` carries the plate-tier prep facts** `primer_plate`, `plating`,
  `extractionkit_lot`, `extraction_robot`, `platemap_generation_date`, and
  `plate_contents_description`, all nullable. The last is deliberately not named
  `experiment_design_description`: plates and projects are many-to-many, so a
  plate is a crossing axis rather than a finer grain, and the project-level
  column stays authoritative.
- **The legacy format registry records each format's file shape.**
  `legacy_samplesheet_format.delimiter` and `has_section_labels` let a format
  describe its own serialization instead of the reader inferring it. Both are
  `NOT NULL` with defaults matching the omnibus formats, which are
  comma-delimited and section-labelled.
- **Guard test for the section-format registry.** Section formats are folded
  into one `{section_name: section_format}` mapping before any format is known,
  so registering one section name under two formats would resolve by row order
  and change how unrelated files parse. A test now fails, naming the offending
  section, if that ever happens.

- **`amplicon_sample` modelled as a workflow table.** The in-line Golay barcode
  is added to a sample during amplicon PCR and is platform-independent — an
  amplicon-on-PacBio sample would carry the same one — so `amplicon_sample` now
  sits with `metagenomic_absquant_sample` and `metatranscriptomic_sample` rather
  than with the platform tables, keyed on `prepped_sample_idx` with no surrogate.
  `amplicon` is correspondingly no longer a `PlatformSpecificSampleKind`, which
  is the platform/library-prep axis.

### Changed

- **Prep-template facts land in typed homes rather than a verbatim store.**
  The prep template previously typed only nine columns, keeping the rest in
  `legacy_extra_column`; run-constant facts now live on `amplicon_run`,
  plate-constant facts on `input_plate`, the 96-well position on
  `input_sample.well`, the tube barcode on `input_sample.matrix_tube_id`, and
  the Golay barcode on `amplicon_sample`, leaving only the genuinely free-form
  columns verbatim.

- **KatharoSeq and blank controls are typed from their name prefix,
  case-insensitively.** A `KATHARO.` / `BLANK.` prefix types the control
  whatever its capitalisation; when the sheet also carries `Kathseq_RackID` and
  `number_of_cells`, those land on `katharoseq_sample`. Matching is otherwise
  literal: a name such as `BLANK2.2A` is deliberately not treated as a blank,
  because whether a numbered prefix marks one is a question about that sheet's
  convention rather than something the loader should infer.

- **A sheet whose `control_description` disagrees with its sample names is
  rejected at load.** The Data view regenerates that column from the sample
  type, so a disagreeing source value would otherwise be silently rewritten.

- **`get_amplicon_barcode_roster` reads the primer from `amplicon_run`**
  rather than string-matching the verbatim store.

- **Round-trip normalization is delimiter-aware, and its whole-number rule is
  scoped to a cell.** Applied to the whole text it rewrote sample names that
  embed their own values, turning `katharo.ADAPT.21.E11.18000.0` into
  `…18000`.

- **`validate_omnibus` is now `validate_sections`**, and
  `processing_run.source_column_order` is gone — column order is recovered
  from the format's view, so no sheet needs its own header persisted.

- **Reconstruction views may carry a reserved `prepped_sample_idx`.** View
  introspection already hid `run_idx` from the output; it now hides any reserved
  column, and a view with no printable key of its own can carry the row's
  identity for ordering and for matching carried-through columns. Previously
  that identity came from `Sample_ID`, which every omnibus view happens to
  define as the primary key — a coincidence no format without a `Sample_ID`
  column could rely on.

- **A `[Reads]`-less source no longer fails to load.** `illumina_run`'s read
  lengths became nullable so a document recording no run configuration could
  still carry a row, but the loader still indexed the section unconditionally.
  Absent read lengths are now stored as NULL.

- **`prepped_sample.sample_name` is populated only when it differs** from the
  input sample's name, as the column's contract states. It was written on every
  row of any sheet carrying an `orig_name` column.

- **The loader reads Data columns by the names the format declares, and no
  longer sniffs the well column out of the file.** `populate_db` previously
  hardcoded `Sample_Name`, `Sample_Plate`, `Sample_Project`, and
  `Well_description`, and chose the well column by testing whether
  `well_id_384` happened to be present. Both assumed every format speaks the
  omnibus vocabulary. The seeded names reproduce exactly what was hardcoded and
  sniffed, verified by every committed native snapshot regenerating unchanged
  apart from its schema version.

- **The loader reads a file's platform, instrument, and per-sample table from
  the registry instead of inferring them from its name.** `populate_db`
  previously substring-matched `SheetType` for `"pacbio"` and `"tellseq"` to
  decide the platform, the instrument, which `_populate_*_sample` to call, and
  whether to write an `illumina_run` row — so a naming coincidence was
  load-bearing, and a future format containing either token would silently take
  that path. Dispatch now goes through a `sample_kind`-keyed map of the same
  functions, which are themselves unchanged. The seeded values reproduce what
  the inference produced, verified by every committed native snapshot
  regenerating identically apart from its schema version.

- **`good_amplicon_16s_v1.txt` marks its KatharoSeq controls.** The sheet named
  48 samples `KATHARO.*` with cell counts encoded in the names, on a plate it
  describes as holding katharoseq and blanks, yet left `control_description`
  empty on every one of them — the only sheet where the sample name and that
  column disagree, and the only one with no `positive_control` value at all.
  Those 48 cells now read `positive_control`. Sample typing reads the name, not
  this column, so the correction records the fact the sheet already stated
  elsewhere.

- **`katharoseq_sample.number_of_cells` is `REAL`, not `INTEGER`** (schema patch
  `002`). KatharoSeq serial dilutions reach fractional cell counts — `38.4` and
  `7.68` both occur in real prep templates — which `INTEGER` silently truncated.

- **Every Illumina run now has an `illumina_run` record.** A run loaded from the
  amplicon prep template is sequenced on Illumina but the prep template
  records no run configuration, so it previously produced a database with
  `platform = Illumina` and no `illumina_run` row — the first break in an
  invariant that held across every other preflight. The amplicon loader now
  inserts an `illumina_run` row whose configuration columns are all NULL,
  meaning "this ran on Illumina; this document does not state the run config".
  A guard test loads every legacy sheet — sectioned and flat — and fails if any
  run's platform and its run-config table disagree.
- **`illumina_run.read1_length` / `read2_length` are nullable** (schema patch
  `002`), so a run whose source document omits read lengths can still carry an
  `illumina_run` row. NULL expresses "not recorded", which `0` cannot. The patch
  rebuilds the table, since SQLite cannot drop `NOT NULL` in place, dropping and
  recreating the four dependent views around the rebuild.
- **Native fixture snapshots record `user_version`.** The snapshots exist to make
  the opaque `.sqlite` diffs reviewable, but omitted the schema version — the one
  piece of structure held outside `sqlite_master`. A database stale in version
  alone compared equal, and the version bump behind a fixture regeneration was
  invisible in review. `capture_db_snapshot` now captures it.
- **`input_sample.matrix_tube_id`** (nullable) — the physical matrix/tube barcode,
  moved off `katharoseq_sample.tube_code` since it is a per-sample fact, not
  KatharoSeq-specific (schema patch `002`).
- Nullable `smrt_cell_well_sample_id` column on `pacbio_sample` recording the SMRT Cell
  position, constrained to `<1|2>_<A-D>01` (`GLOB '[12]_[A-D]01'`), plus a nullable
  `movie_context_id` column, both surfaced by a new `run_pacbio_sample` view mirroring
  `run_illumina_sample`. Shipped as the
  first schema patch (`sql/patches/001_*`); `schema_v0.sql` is now the frozen
  baseline for databases already in the wild, so every schema change flows
  through a patch from here on.
- `get_pacbio_sample_info`, returning per-`pacbio_sample` biosample and
  bioproject accession info keyed by `pacbio_sample_idx` (control/secondary and
  do-not-use handling identical to `get_illumina_sample_info`). Both info
  functions return a `PlatformSampleInfo` NamedTuple per sample, carrying the
  sample's `sample_type` (the DB `sample_type.name`, e.g. `standard` /
  `extraction_blank`), its biosample and bioproject accessions, and the
  platform-specific columns as a `PacbioSampleRow` / `IlluminaSampleRow`
  `kind_row` — so a consumer gets the accession info, the sample type, and the
  run-specific sample fields in one call. The `PacbioSampleRow.syndna_is_twisted`
  column, a SQLite `BOOLEAN` stored as `0`/`1`/`NULL`, is surfaced to consumers
  as `bool | None`. **Breaking:** `get_illumina_sample_info`'s return changes
  from a bare tuple to a `PlatformSampleInfo` NamedTuple, so existing code
  unpacking it positionally must be updated.
- `set_pacbio_sample_run_details`, setting the post-creation PacBio
  `smrt_cell_well_sample_id` and/or `movie_context_id` on one `pacbio_sample`,
  addressed by `sample_name` or `pacbio_sample_idx` (a `sample_name` matching
  more than one row raises, directing the caller to `pacbio_sample_idx`).
  Exposes a public `UNCHANGED` sentinel so a field can be left untouched,
  distinct from `None` which clears it; invalid `smrt_cell_well_sample_id`
  values are rejected by the column CHECK.

- Do-not-use flags on `input_sample` (two-state hard floor) and
  `prepped_sample` (two-state per-replicate override: set = exclude this
  replicate, NULL = inherit the input flag), populated at legacy ingest by
  detecting a `.donotuse.` dot-delimited token (case-insensitive) in sample
  names. Settable for native runs via `set_input_sample_do_not_use` (by index
  or biosample accession, the latter flagging all matches in one transaction;
  `value=False` clears the flag) and `set_prepped_sample_do_not_use`
  (`value=True` flags, `value=None` clears to inherit; `False` is rejected).
  Sample fetchers (`get_illumina_sample_rows`, `get_illumina_sample_info`,
  `get_input_sample_project_info`) and the forward writers
  (`save_bclconvert_v1_csv`, `save_legacy_sample_id_map_csv`) exclude flagged
  samples by default and accept `include_do_not_use=True` to return them.
  `save_legacy_csv` and `save_db_file` always include flagged records.
- Standard Python project scaffolding: a root `.gitignore` and an installable
  `pyproject.toml` (setuptools + versioningit, generated `_version.py`,
  `environment.yml`, and a GitHub Actions CI workflow).
- Lossless round-trip support for the PacBio Metag v10 omnibus format, with the
  v11 format refactored to layer on top of the new v10 base view.
- Lossless round-trip support for the standard_metag v0 and v90 formats via
  layered SQL views (v90 base → v0 renames → v101 column additions) and shared
  Illumina header/reads views; `parse_omnibus` now takes section formats
  supplied by the DB through `get_section_formats`.
- Lossless round-trip support for the abs_quant_metag v11, standard_metat v10,
  tellseq_metag v10, and tellseq_absquant v10 formats, each reusing shared views
  where possible plus a format-specific data view and population helper.
- Support for arbitrary extra columns in legacy Data sections via a
  `legacy_extra_column` table, with alphabetical reconstruction; a
  `compression_sample` table normalizing well semantics between `input_sample`
  and `prepped_sample`.
- Database migration infrastructure (`migrate.py`): `PRAGMA user_version`
  stamping, patch discovery, SQL/Python patch dispatch, and an `open_db` entry
  point used by the round-trip helpers.
- Derived per-capability views: leaf views (`run_capability_absquant_mass` /
  `_volume` / `_surface_area`) unioned into a `run_capability` view, with a
  `run_derived_capability` view exposing `(run_idx, capability_family, version)`
  tuples. Derivation reads non-null sample metrics directly, so controls and
  failed samples with legitimately NULL metrics are handled correctly.
- Multi-lane support through per-platform surrogate primary keys
  (`illumina_sample_id` / `tellseq_sample_id` / `pacbio_sample_id`),
  `UNIQUE(prepped_sample_id, COALESCE(lane,-1))` indexes, per-tube consistency
  triggers (i5/i7, barcode, lane uniformity, one-run-per-DB), and a synthetic
  multi-lane round-trip fixture.
- Committed native-format test files under `tests/data/native/`: for every
  good_ legacy CSV, a SQLite database plus a JSON snapshot of its full
  structure and contents, produced by `scripts/generate_native_test_files.py`.
  The `.sqlite` files give downstream consumers ready-to-use native
  run-preflight inputs; `tests/test_native_test_files.py` enforces that every
  good_ legacy CSV has a native pair, that the native directory stays paired
  (`.sqlite` ↔ snapshot), and that each committed `.sqlite` matches both its
  snapshot and a fresh load of its source CSV.
- Content-derived stage signalling for native fixtures: each committed
  `.sqlite` carries a fact-based filename suffix — bare for a true preflight,
  `.accessioned` once NCBI accessions are populated — derived from its contents
  and guarded against drift, so a consumer can pick a fixture matching the
  stage their code needs. Includes an accessioned PacBio fixture that reads
  cleanly through `get_pacbio_sample_info` (a true-preflight fixture raises,
  by design, until its accessions are set).

### Removed

- **`good_amplicon_replicate.txt` fixture.** It was synthetic but
  unmarked, used US-style slash dates where every real sheet uses ISO, and
  contained no replicates at all — eight rows with eight distinct `orig_name`
  values — while asserting `contains_replicates` in four spellings.

### Changed

- Raised the supported Python floor to 3.11.
- Reorganized test data into `tests/data/legacy/` (legacy omnibus CSVs) and
  `tests/data/native/` (native SQLite files and snapshots); renamed four
  real-world-named good CSVs to the `good_` convention and the
  reject-by-design pre-v101-replicates CSV to an `unsupported_` prefix so it
  is excluded from the good_ sweep.
- Collapsed `get_illumina_sample_info` and `get_pacbio_sample_info` onto one
  parameterized helper keyed by a `PlatformSpecificSampleKind` (`illumina` /
  `pacbio` / `tellseq`), deriving each kind's table, primary-key column, and
  run view by naming convention rather than a hand-maintained lookup.
- Renamed `update_lane`'s `platform` parameter to `sample_kind` and its
  internal lane-target lookup to the Illumina-platform sample kinds
  (`illumina`, `tellseq`), correcting the prior labelling of TellSeq (a library
  prep, not a platform) as a platform. **Breaking:** callers passing
  `platform=` by keyword must switch to `sample_kind=`.
- Restructured the repository into a `src/run_preflight/` package layout, with
  the SQL schema living inside the package.
- Switched the test runner from `unittest` to `pytest`.
- Consolidated view introspection into a single `introspect_view` /
  `get_view_columns` pair in `db.py`, making the reconstruction writers pure
  formatters with no DB access.
- Centralized boolean-string parsing into `_parse_bool_str` (nullable-aware for
  `syndna_is_twisted`) and routed `assay_type` / `sequencing_platform` lookups
  through `_lookup_id`.
- Added `run_id` to the shared `omnibus_contact` and `omnibus_sample_context`
  views so `_query_view` filters uniformly on `run_id`, removing the prior
  substring-based view dispatch.
- Made the `Lane` column required for all Illumina formats.
- Unified the three per-version Illumina Settings views into a single
  `omnibus_illumina_settings` view exposing `ReverseComplement`,
  `MaskShortReads`, and `OverrideCycles` for all Illumina formats.
- Reset the schema-zero baseline so `schema_v0.sql` matches `schema.sql`, and
  relaxed `illumina_run.reverse_complement` to nullable so an absent value
  round-trips without emitting a default.
- Relaxed `input_sample.sample_name` to nullable, adding a table-level
  `CHECK (sample_name IS NOT NULL OR biosample_accession IS NOT NULL)`.
- Renamed the `project.qiita_id` DB column to `external_project_id`, preserving
  the `QiitaID` / `primary_qiita_study` / `secondary_qiita_studies` CSV emit
  aliases and carrying the change to existing DBs via a rename patch.

### Fixed

- CI lint enforces a stated ruff rule set (`E4`, `E7`, `E9`, `F`) rather than
  inheriting ruff's implicit default, which shifts between ruff releases and so
  silently changed what CI required from one run to the next.
- The CI Python matrix exercises the versions it names. The workflow's
  interpreter pin rewrote only a literal `python=3.9` entry, which the unpinned
  `python` in `environment.yml` did not match, so the substitution was a no-op
  and every matrix job installed the same interpreter. The rewrite now matches a
  pinned or unpinned entry and fails loudly when it does not take.
- Schema patch files under `sql/patches/` are now included in the built
  package, so migrations apply from an installed wheel rather than only from an
  editable checkout.
- Schema patches now apply atomically: each patch body and its `user_version`
  stamp run in one transaction, so a patch failing part-way rolls back instead
  of stranding a half-migrated database that re-fails on every later open.
- The database snapshot used by the drift and native-file guards now captures
  each table's normalized definition, so CHECK, COLLATE, and table-level
  constraints are compared rather than silently ignored.
- Reconstruction now emits tabular Data rows in a deterministic lane-major
  order (by `Lane`, then insertion order), matching the metapool writer's
  layout. Previously multi-lane sheets round-tripped with samples grouped
  and their lanes adjacent, which differed from the source row order.
- Narrowed `cursor.lastrowid` handling at INSERT sites to eliminate Pyright
  `reportArgumentType` warnings.

[Unreleased]: https://github.com/the-miint/kl-run-preflight/commits/main
