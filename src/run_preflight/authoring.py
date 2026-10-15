"""Programmatic authoring of a pre-flight directly, without a legacy CSV.

The migrate path (`migrate_legacy_csv_to_db_file`) builds every row by parsing an
omnibus prep template. For a new modality with no legacy sheet — a long-read
PacBio amplicon run — that means inventing a sheet format just to launder it
back out. These builders let a caller write the normalized schema directly: one
`create_run`, a `project` + `input_plate`, one `add_pacbio_sample` per sample,
and one `set_amplicon_details` for the run's amplicon biology.

They are the production-grade siblings of the test seed helpers (`tests/_helpers`)
and follow the same conventions as `db.populate_db`: each INSERT walks the
dependency chain (`project` -> `input_plate` -> `processing_run` ->
`input_sample` -> `compression_sample` -> `prepped_sample` -> `pacbio_sample`),
and **none commit — the caller owns the transaction**, so a whole run is built
atomically and rolled back cleanly on any failure.

Scope: PacBio amplicon only, which is the case the legacy path cannot express.
`create_run` assumes a fresh `create_db` connection (the `one_run_per_db` trigger
forbids a second run).
"""

from __future__ import annotations

import sqlite3

from .constants import ASSAY_AMPLICON, PLATFORM_PACBIO


def _lookup_idx(conn: sqlite3.Connection, table: str, name: str) -> int:
    """Resolve a reference row's primary key by its unique `name`, or raise.

    Uses `rowid`, which aliases the INTEGER PRIMARY KEY, so it is robust to the
    column's actual name (`platform_idx`, `assay_type_idx`, ...).
    """
    row = conn.execute(
        f"SELECT rowid FROM {table} WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        raise ValueError(f"no {table} named {name!r}")
    return row[0]


def create_run(
    conn: sqlite3.Connection,
    *,
    experiment_name: str,
    run_date: str,
    instrument_type: str,
    platform: str = PLATFORM_PACBIO,
    assay: str = ASSAY_AMPLICON,
) -> int:
    """Insert the single `processing_run` and return its run_idx.

    `legacy_format_idx` is left NULL: this run is native, not ingested from a
    legacy sheet. The `one_run_per_db` trigger rejects a second run, so call this
    once on a fresh `create_db` connection. Does not commit.
    """
    platform_idx = _lookup_idx(conn, "sequencing_platform", platform)
    assay_type_idx = _lookup_idx(conn, "assay_type", assay)
    cur = conn.execute(
        "INSERT INTO processing_run "
        "(experiment_name, run_date, instrument_type, assay_type_idx, platform_idx) "
        "VALUES (?, ?, ?, ?, ?)",
        (experiment_name, run_date, instrument_type, assay_type_idx, platform_idx),
    )
    return cur.lastrowid


def add_project(
    conn: sqlite3.Connection,
    *,
    project_name: str,
    library_construction_protocol: str,
    experiment_design_description: str,
    external_project_id: str | None = None,
    bioproject_accession: str | None = None,
    human_filtering: bool = True,
) -> int:
    """Insert one `project` and return its project_idx.

    The schema requires at least one of `external_project_id` or
    `bioproject_accession`; passing neither raises. Does not commit.
    """
    if external_project_id is None and bioproject_accession is None:
        raise ValueError(
            "a project needs an external_project_id or a bioproject_accession"
        )
    cur = conn.execute(
        "INSERT INTO project "
        "(project_name, external_project_id, human_filtering, "
        " library_construction_protocol, experiment_design_description, "
        " bioproject_accession) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            project_name,
            external_project_id,
            1 if human_filtering else 0,
            library_construction_protocol,
            experiment_design_description,
            bioproject_accession,
        ),
    )
    return cur.lastrowid


def add_input_plate(
    conn: sqlite3.Connection,
    primary_project_idx: int,
    *,
    plate_name: str,
) -> int:
    """Insert one `input_plate` under a project and return its plate_idx.

    A pool with no physical plate still needs one plate row to hang samples
    from; name it for the pool. Does not commit.
    """
    cur = conn.execute(
        "INSERT INTO input_plate (plate_name, primary_project_idx) VALUES (?, ?)",
        (plate_name, primary_project_idx),
    )
    return cur.lastrowid


def add_pacbio_sample(
    conn: sqlite3.Connection,
    run_idx: int,
    plate_idx: int,
    *,
    barcode_id: str,
    sample_name: str | None = None,
    biosample_accession: str | None = None,
    matrix_tube_id: str | None = None,
    project_idx: int | None = None,
    sample_type_name: str = "standard",
    well: str = "A1",
    smrt_cell_well_sample_id: str | None = None,
    movie_context_id: str | None = None,
) -> int:
    """Create one PacBio sample end to end; return its pacbio_sample_idx.

    Walks `input_sample` -> `compression_sample` -> `prepped_sample` ->
    `pacbio_sample`. Identity follows the schema's rule: a sample needs a
    `sample_name` or a `biosample_accession` (a `matrix_tube_id` alone does not
    satisfy it, though it may be supplied as the physical handle). A control
    passes `project_idx=None` with a control `sample_type_name` (e.g.
    `extraction_blank`), inheriting its project through the plate.

    `barcode_id` is the PacBio barcode that demultiplexes the sample upstream in
    SMRTlink. `smrt_cell_well_sample_id` (if set) is validated by the DB CHECK
    (`[12]_[A-D]01`). Does not commit.
    """
    if sample_name is None and biosample_accession is None:
        raise ValueError(
            "a sample needs a sample_name or a biosample_accession"
            " (a matrix_tube_id alone is not an identity)"
        )
    sample_type_idx = _lookup_idx(conn, "sample_type", sample_type_name)
    ins_idx = conn.execute(
        "INSERT INTO input_sample "
        "(sample_name, input_plate_idx, project_idx, sample_type_idx, "
        " biosample_accession, matrix_tube_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            sample_name,
            plate_idx,
            project_idx,
            sample_type_idx,
            biosample_accession,
            matrix_tube_id,
        ),
    ).lastrowid
    cs_idx = conn.execute(
        "INSERT INTO compression_sample (run_idx, input_sample_idx, compression_well) "
        "VALUES (?, ?, ?)",
        (run_idx, ins_idx, well),
    ).lastrowid
    prs_idx = conn.execute(
        "INSERT INTO prepped_sample (compression_sample_idx, prepped_well) VALUES (?, ?)",
        (cs_idx, well),
    ).lastrowid
    cur = conn.execute(
        "INSERT INTO pacbio_sample "
        "(prepped_sample_idx, barcode_id, smrt_cell_well_sample_id, movie_context_id) "
        "VALUES (?, ?, ?, ?)",
        (prs_idx, barcode_id, smrt_cell_well_sample_id, movie_context_id),
    )
    return cur.lastrowid


def set_amplicon_details(
    conn: sqlite3.Connection,
    run_idx: int,
    *,
    primer: str,
    pcr_primers: str,
    target_gene: str,
    target_subfragment: str,
    umi_pattern: str | None = None,
    linker: str = "",
    sequencing_meth: str = "",
    barcodes_are_rc: bool = False,
) -> None:
    """Insert the run's `amplicon_run` row (its amplicon biology).

    `primer`/`pcr_primers` carry the amplification primers; for a long-read run
    `pcr_primers` is the place to spell the full-length pair (e.g. 27F/1492R).
    `umi_pattern` is the permissive UMI pattern (added in patch 003), NULL for a
    run with no UMI. `barcodes_are_rc` is Golay-specific — it is meaningless for
    PacBio barcodes, so it defaults to False here; see the PR discussion on
    making the column nullable. Does not commit.
    """
    conn.execute(
        "INSERT INTO amplicon_run "
        "(run_idx, primer, linker, target_gene, target_subfragment, "
        " pcr_primers, sequencing_meth, barcodes_are_rc, umi_pattern) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_idx,
            primer,
            linker,
            target_gene,
            target_subfragment,
            pcr_primers,
            sequencing_meth,
            1 if barcodes_are_rc else 0,
            umi_pattern,
        ),
    )
