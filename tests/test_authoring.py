"""Tests for the programmatic (non-legacy) authoring builders.

Build a PacBio amplicon pre-flight directly with the typed builders and verify
the normalized rows, then the invariants a caller must respect.
"""

from __future__ import annotations

import sqlite3
import unittest

from run_preflight import (
    add_input_plate,
    add_pacbio_sample,
    add_project,
    create_db,
    create_run,
    set_amplicon_details,
)
from run_preflight.constants import IN_MEMORY_PATH


def _build_pool(conn: sqlite3.Connection) -> int:
    """Author a small PacBio amplicon run; return its run_idx."""
    run_idx = create_run(
        conn,
        experiment_name="revio_pool_1",
        run_date="2026-10-17",
        instrument_type="Revio",
    )
    project_idx = add_project(
        conn,
        project_name="full_length_16s",
        library_construction_protocol="PacBio full-length 16S",
        experiment_design_description="rRNA operon survey",
        external_project_id="14458",
    )
    plate_idx = add_input_plate(conn, project_idx, plate_name="revio_pool_1")
    for i, bc in enumerate(("bc1001", "bc1002", "bc1003"), start=1):
        add_pacbio_sample(
            conn,
            run_idx,
            plate_idx,
            barcode_id=bc,
            sample_name=f"GUT.0{i}",
            project_idx=project_idx,
            matrix_tube_id=f"036315790{i}",
            smrt_cell_well_sample_id="1_B01",
            movie_context_id="m84137_260717_104358_s3",
        )
    set_amplicon_details(
        conn,
        run_idx,
        primer="AGAGTTTGATCMTGGCTCAG",
        pcr_primers="FWD:AGAGTTTGATCMTGGCTCAG; REV:TACGGYTACCTTGTTACGACTT",
        target_gene="16S rRNA",
        target_subfragment="full-length (V1-V9)",
        umi_pattern="NNNYRNNNYRNNN",
    )
    return run_idx


class TestAuthoring(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = create_db(IN_MEMORY_PATH)

    def tearDown(self) -> None:
        self.conn.close()

    def test_builds_a_pacbio_amplicon_run(self) -> None:
        run_idx = _build_pool(self.conn)
        self.conn.commit()

        # The run is PacBio + Amplicon.
        assay, platform = self.conn.execute(
            "SELECT at.name, sp.name FROM processing_run pr"
            " JOIN assay_type at ON pr.assay_type_idx = at.assay_type_idx"
            " JOIN sequencing_platform sp ON pr.platform_idx = sp.platform_idx"
            " WHERE pr.run_idx = ?",
            (run_idx,),
        ).fetchone()
        self.assertEqual((assay, platform), ("Amplicon", "PacBio"))
        self.assertIsNone(
            self.conn.execute(
                "SELECT legacy_format_idx FROM processing_run WHERE run_idx = ?",
                (run_idx,),
            ).fetchone()[0]
        )

        # Three pacbio_sample rows, each with its barcode and run details.
        rows = self.conn.execute(
            "SELECT ps.barcode_id, ps.smrt_cell_well_sample_id, ps.movie_context_id"
            " FROM pacbio_sample ps JOIN prepped_sample prs"
            "   ON ps.prepped_sample_idx = prs.prepped_sample_idx"
            " ORDER BY ps.barcode_id"
        ).fetchall()
        self.assertEqual([r[0] for r in rows], ["bc1001", "bc1002", "bc1003"])
        self.assertTrue(all(r[1] == "1_B01" for r in rows))

        # The amplicon_run row carries the primers and the UMI pattern.
        primer, umi, rc = self.conn.execute(
            "SELECT primer, umi_pattern, barcodes_are_rc FROM amplicon_run WHERE run_idx = ?",
            (run_idx,),
        ).fetchone()
        self.assertEqual(primer, "AGAGTTTGATCMTGGCTCAG")
        self.assertEqual(umi, "NNNYRNNNYRNNN")
        self.assertEqual(rc, 0)

    def test_one_run_per_db_forbids_a_second_run(self) -> None:
        create_run(
            self.conn,
            experiment_name="a",
            run_date="2026-10-17",
            instrument_type="Revio",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            create_run(
                self.conn,
                experiment_name="b",
                run_date="2026-10-17",
                instrument_type="Revio",
            )

    def test_sample_needs_an_identity(self) -> None:
        run_idx = create_run(
            self.conn,
            experiment_name="a",
            run_date="2026-10-17",
            instrument_type="Revio",
        )
        project_idx = add_project(
            self.conn,
            project_name="p",
            library_construction_protocol="x",
            experiment_design_description="y",
            external_project_id="1",
        )
        plate_idx = add_input_plate(self.conn, project_idx, plate_name="pl")
        # A matrix tube alone is not an identity.
        with self.assertRaises(ValueError):
            add_pacbio_sample(
                self.conn,
                run_idx,
                plate_idx,
                barcode_id="bc1",
                matrix_tube_id="0363157901",
                project_idx=project_idx,
            )

    def test_a_tube_may_repeat_as_a_replicate(self) -> None:
        run_idx = create_run(
            self.conn,
            experiment_name="a",
            run_date="2026-10-17",
            instrument_type="Revio",
        )
        project_idx = add_project(
            self.conn,
            project_name="p",
            library_construction_protocol="x",
            experiment_design_description="y",
            external_project_id="1",
        )
        plate_idx = add_input_plate(self.conn, project_idx, plate_name="pl")
        # Two prepped samples of one tube (technical replicates) with distinct
        # barcodes; the builder places both without complaint.
        for bc in ("bc1", "bc2"):
            add_pacbio_sample(
                self.conn,
                run_idx,
                plate_idx,
                barcode_id=bc,
                sample_name="GUT.01",
                matrix_tube_id="0363157901",
                project_idx=project_idx,
            )
        count = self.conn.execute(
            "SELECT count(*) FROM input_sample WHERE matrix_tube_id = ?",
            ("0363157901",),
        ).fetchone()[0]
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
