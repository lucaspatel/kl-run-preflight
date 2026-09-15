# Amplicon prep template — what we store, and what's deferred

The EMP amplicon prep template is a flat, tab-delimited sheet (one row per
sample), unlike the sectioned Illumina/PacBio omnibus sheets. It carries no
`[Section]` labels and no `SheetType`, so it loads through the **same** parse →
validate → populate → reconstruct path as the omnibus formats, registered as a
single format (`amplicon` v1) whose layout is resolved from the column header
alone. The single fixture is `tests/data/legacy/good_amplicon_16s_v1.txt`.

Recognised columns are typed into their schema homes; the rest are kept
**verbatim** in `legacy_extra_column`, and reconstruction reads the registered
`amplicon_v1_data` view, so the sheet round-trips byte-exactly with nothing
stored twice. Consumers use the package API, never the tables directly, so this
internal split is private and can be restructured later without data loss.

## Typed

Run-constant facts live on `amplicon_run`, plate-constant facts on
`input_plate`, the Golay barcode on `amplicon_sample`, and the tube barcode /
96-well position / control type on `input_sample` — see the `amplicon_v1_data`
view in `sql/schema.sql` for the authoritative column→home mapping. Blank /
KatharoSeq controls are typed as `input_sample.sample_type` (`extraction_blank`
/ `katharoseq_cells_positive_control`) from the `BLANK.` / `KATHARO.`
`sample_name` prefix; `control_description` is regenerated from the sample type
on reconstruction, so a source value that disagrees is rejected at load.

## Deferred

- **`Kathseq_RackID` / `number_of_cells` → `katharoseq_sample`.** These are the
  format's optional column group. When a sheet carries them they are typed onto
  `katharoseq_sample`; `good_amplicon_16s_v1.txt` omits them, so its KatharoSeq
  controls are typed by name only, with no per-control cell count.
- **More amplicon assays.** `barcodes_are_rc` is stored on `amplicon_run`,
  inferred from the primer at ingest (`_barcodes_are_rc_for_primer`), but only the
  EMP 515f assay is recognised today — an unrecognised primer raises. Extend that
  mapping when another amplicon assay is supported.

## Qiita handoff (barcode roster)

Qiita's golay-demux needs a per-sample `(prep_sample_idx, barcode,
barcodes_are_rc)` roster. Qiita mints `prep_sample.idx` from a `biosample_idx`, so
the bridge is the **biosample accession**, not a shared idx: preflight
`sample_name` / `input_sample.biosample_accession` → Qiita biosample →
`prep_sample.idx`. Flow: register the study's biosamples in Qiita → write
accessions back into the preflight DB (`set_biosample_accession`) → at submit,
read `get_amplicon_sample_info` (its `AmpliconSampleRow` carries `barcode` and
`barcodes_are_rc`) and join on `biosample_accession`.
