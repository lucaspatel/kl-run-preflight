"""Round-trip and typed-projection tests for the amplicon prep template.

The prep template is a flat, TAB-delimited sheet with no [Section] labels; it
loads through the same parse → validate → populate path as the sectioned
omnibus sheets, so these tests exercise that shared path end to end. Tests
query tables directly, which production consumers must not — that is fine here.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_preflight import get_amplicon_barcode_roster
from run_preflight.legacy.api import load_legacy_csv, open_file, save_legacy_csv
from run_preflight.legacy.roundtrip import roundtrip_via_api

DATA_DIR = Path(__file__).parent / "data" / "legacy"


class TestAmpliconPrepRoundTrip(unittest.TestCase):
    """Every registered prep-template layout survives load → write."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _assert_roundtrips(self, sheet_name: str):
        normalized, reconstructed = roundtrip_via_api(
            DATA_DIR / sheet_name, self.tmp_dir
        )
        self.assertEqual(normalized, reconstructed)

    def test_amplicon_16s_v1(self):
        self._assert_roundtrips("good_amplicon_16s_v1.txt")

    def test_open_file_accepts_a_prep_template(self):
        # open_file dispatches on content, so a prep template reaches the same
        # loader as an omnibus CSV without the caller naming a format. Column
        # order is normalized on comparison, so the check is on the column set
        # and the row count the write produced.
        sheet = DATA_DIR / "good_amplicon_16s_v1.txt"
        out_path = self.tmp_dir / "out.txt"
        conn = open_file(str(sheet))
        try:
            save_legacy_csv(conn, str(out_path))
        finally:
            conn.close()
        source_lines = sheet.read_text().splitlines()
        written_lines = out_path.read_text().splitlines()
        self.assertEqual(len(written_lines), len(source_lines))
        self.assertEqual(
            set(written_lines[0].split("\t")), set(source_lines[0].split("\t"))
        )


class TestAmpliconPrepProjection(unittest.TestCase):
    """The prep template's facts land in their typed homes, not only verbatim."""

    def _load(self, sheet_name: str):
        return load_legacy_csv(str(DATA_DIR / sheet_name))

    def test_katharoseq_controls_are_typed_by_name(self):
        # Controls are typed from their "KATHARO." / "BLANK." name prefix. This
        # layout carries no per-control cell count, so the katharoseq_sample
        # detail table stays empty (Kathseq_RackID / number_of_cells are the
        # format's optional group, absent from this sheet).
        conn = self._load("good_amplicon_16s_v1.txt")
        try:
            counts = dict(
                conn.execute(
                    "SELECT st.name, COUNT(*) FROM input_sample i "
                    "JOIN sample_type st ON i.sample_type_idx = st.sample_type_idx "
                    "GROUP BY st.name"
                ).fetchall()
            )
            katharoseq_rows = conn.execute(
                "SELECT COUNT(*) FROM katharoseq_sample"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(
            counts,
            {
                "standard": 225,
                "extraction_blank": 44,
                "katharoseq_cells_positive_control": 48,
            },
        )
        self.assertEqual(katharoseq_rows, 0)

    def test_run_and_plate_facts_are_typed_once(self):
        # Facts constant across a run or a plate are stored once at that grain
        # rather than repeated on every sample row.
        conn = self._load("good_amplicon_16s_v1.txt")
        try:
            run = conn.execute(
                "SELECT primer, target_gene, target_subfragment FROM amplicon_run"
            ).fetchall()
            plates = conn.execute(
                "SELECT plate_name, primer_plate, extraction_robot "
                "FROM input_plate ORDER BY plate_name"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(run, [("GTGYCAGCMGCCGCGGTAA", "16S rRNA", "V4")])
        self.assertEqual(len(plates), 4)
        self.assertTrue(all(primer_plate for _, primer_plate, _ in plates))

    def test_no_illumina_sample_rows_for_an_amplicon_run(self):
        # An amplicon run carries a single in-line Golay barcode, not an
        # i5/i7 pair, so it has no platform-specific sample rows.
        conn = self._load("good_amplicon_16s_v1.txt")
        try:
            illumina_rows = conn.execute(
                "SELECT COUNT(*) FROM illumina_sample"
            ).fetchone()[0]
            illumina_run_rows = conn.execute(
                "SELECT COUNT(*) FROM illumina_run"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(illumina_rows, 0)
        self.assertEqual(illumina_run_rows, 1)

    def test_barcode_roster_reads_without_accessions(self):
        conn = self._load("good_amplicon_16s_v1.txt")
        try:
            roster = get_amplicon_barcode_roster(conn)
        finally:
            conn.close()
        self.assertEqual(len(roster), 317)
        self.assertTrue(all(entry.barcode for entry in roster))
        self.assertTrue(all(entry.barcodes_are_rc is True for entry in roster))


class TestAmpliconPrepRejection(unittest.TestCase):
    """A malformed or unrecognised prep template fails at load, not later."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, text: str) -> str:
        path = self.tmp_dir / "sheet.txt"
        path.write_text(text)
        return str(path)

    def test_ragged_row_is_rejected(self):
        sheet = self._write("sample_name\tbarcode\nonly_one_cell\n")
        with self.assertRaises(ValueError) as ctx:
            load_legacy_csv(sheet)
        self.assertIn("line 2", str(ctx.exception))

    def test_header_only_sheet_is_rejected(self):
        sheet = self._write("sample_name\tbarcode\n")
        with self.assertRaises(ValueError) as ctx:
            load_legacy_csv(sheet)
        self.assertIn("no sample rows", str(ctx.exception))

    def test_unrecognised_layout_names_its_header(self):
        sheet = self._write("sample_name\tnot_a_known_column\na\tb\n")
        with self.assertRaises(ValueError) as ctx:
            load_legacy_csv(sheet)
        self.assertIn("No registered amplicon format", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
