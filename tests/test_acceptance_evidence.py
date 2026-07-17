from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from acceptance_evidence import (  # noqa: E402
    build_waiver_records,
    compare_waiver_records,
    decode_waiver_records,
    encode_waiver_records,
    main,
    read_observed_tsv,
    validate_waiver_records,
)


class AcceptanceEvidenceTests(unittest.TestCase):
    def test_candidate_change_changes_fingerprint_and_fails_comparison(self) -> None:
        recorded = build_waiver_records(
            {"resources": ["source Figure 1 has no formal payload candidate"]}
        )
        observed = build_waiver_records(
            {"resources": ["source Figure 99 has no formal payload candidate"]}
        )
        _reviewed, mismatches = compare_waiver_records(recorded, observed)
        self.assertEqual(len(mismatches), 1)
        self.assertTrue(mismatches[0].startswith("changed:resources:"))

    def test_records_round_trip_through_manifest_encoding(self) -> None:
        records = build_waiver_records(
            {
                "listings": ["Listing 2 has weak key-token overlap"],
                "resources": ["source Figure 7 has no formal payload candidate"],
            }
        )
        self.assertEqual(decode_waiver_records(encode_waiver_records(records)), records)

    def test_tsv_candidates_are_deduplicated_and_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "observed.tsv"
            path.write_text(
                "resources\tsecond\nresources\tfirst\nresources\tsecond\n",
                encoding="utf-8",
            )
            records = build_waiver_records(read_observed_tsv(path))
        self.assertEqual(records["resources"]["candidates"], ["first", "second"])

    def test_tampered_fingerprint_is_rejected(self) -> None:
        records = build_waiver_records({"resources": ["Figure 1 candidate"]})
        records["resources"]["fingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_waiver_records(records)

    def test_category_only_or_noncanonical_candidates_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            validate_waiver_records({"resources": "approved"})
        with self.assertRaisesRegex(ValueError, "unknown categories"):
            validate_waiver_records({1: {}})
        records = build_waiver_records({"resources": ["first", "second"]})
        records["resources"]["candidates"] = ["second", "first"]
        with self.assertRaisesRegex(ValueError, "sorted, unique, and trimmed"):
            validate_waiver_records(records)

    def test_summarize_cli_emits_copyable_review_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "observed.tsv"
            path.write_text("resources\tFigure 1 candidate\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["acceptance_evidence.py", "summarize", "--observed", str(path)]
            ), contextlib.redirect_stdout(stdout):
                self.assertEqual(main(), 0)
        record = build_waiver_records({"resources": ["Figure 1 candidate"]})
        self.assertIn(
            f"--waiver resources={record['resources']['fingerprint']}",
            stdout.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
