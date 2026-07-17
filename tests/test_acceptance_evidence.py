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
    @staticmethod
    def resource_candidate(number: int) -> str:
        return (
            f"RISK: source Figure {number} has no formal "
            "translation-side payload candidate"
        )

    def test_candidate_change_changes_fingerprint_and_fails_comparison(self) -> None:
        recorded = build_waiver_records(
            {"resources": [self.resource_candidate(1)]}
        )
        observed = build_waiver_records(
            {"resources": [self.resource_candidate(99)]}
        )
        _reviewed, mismatches = compare_waiver_records(recorded, observed)
        self.assertEqual(len(mismatches), 1)
        self.assertTrue(mismatches[0].startswith("changed:resources:"))

    def test_records_round_trip_through_manifest_encoding(self) -> None:
        records = build_waiver_records(
            {
                "listings": [
                    "RISK: Listing 2 fenced payload has weak key-token overlap "
                    "with source candidate (select, where)"
                ],
                "resources": [self.resource_candidate(7)],
            }
        )
        self.assertEqual(decode_waiver_records(encode_waiver_records(records)), records)

    def test_tsv_candidates_are_deduplicated_and_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "observed.tsv"
            first = self.resource_candidate(1)
            second = self.resource_candidate(2)
            path.write_text(
                f"resources\t{second}\nresources\t{first}\nresources\t{second}\n",
                encoding="utf-8",
            )
            records = build_waiver_records(read_observed_tsv(path))
        self.assertEqual(records["resources"]["candidates"], [first, second])

    def test_tampered_fingerprint_is_rejected(self) -> None:
        records = build_waiver_records({"resources": [self.resource_candidate(1)]})
        records["resources"]["fingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_waiver_records(records)

    def test_category_only_or_noncanonical_candidates_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            validate_waiver_records({"resources": "approved"})
        with self.assertRaisesRegex(ValueError, "unknown categories"):
            validate_waiver_records({1: {}})
        records = build_waiver_records(
            {"resources": [self.resource_candidate(1), self.resource_candidate(2)]}
        )
        records["resources"]["candidates"] = list(
            reversed(records["resources"]["candidates"])
        )
        with self.assertRaisesRegex(ValueError, "sorted, unique, and trimmed"):
            validate_waiver_records(records)

    def test_metric_drift_keeps_the_same_semantic_fingerprint(self) -> None:
        recorded = build_waiver_records(
            {
                "listings": [
                    "RISK: Listing 5 fenced payload has weak distinctive-identifier "
                    "overlap with source candidate (0.14)"
                ]
            }
        )
        observed = build_waiver_records(
            {
                "listings": [
                    "RISK: Listing 5 fenced payload has weak distinctive-identifier "
                    "overlap with source candidate (0.09)"
                ]
            }
        )
        reviewed, mismatches = compare_waiver_records(recorded, observed)
        self.assertEqual(mismatches, [])
        self.assertEqual(len(reviewed), 1)
        self.assertEqual(
            recorded["listings"]["fingerprint"], observed["listings"]["fingerprint"]
        )
        self.assertNotEqual(
            recorded["listings"]["candidates"], observed["listings"]["candidates"]
        )

    def test_new_rule_or_subject_in_same_category_changes_fingerprint(self) -> None:
        base = build_waiver_records(
            {
                "listings": [
                    "RISK: Listing 5 fenced payload shares no literals with source candidate"
                ]
            }
        )
        new_rule = build_waiver_records(
            {
                "listings": [
                    "RISK: Listing 5 fenced payload shares no literals with source candidate",
                    "RISK: Listing 5 fenced payload is short relative to source code "
                    "candidate (10/100)",
                ]
            }
        )
        new_subject = build_waiver_records(
            {
                "listings": [
                    "RISK: Listing 6 fenced payload shares no literals with source candidate"
                ]
            }
        )
        self.assertTrue(compare_waiver_records(base, new_rule)[1])
        self.assertTrue(compare_waiver_records(base, new_subject)[1])

    def test_grouped_subject_addition_changes_fingerprint(self) -> None:
        recorded = build_waiver_records(
            {"resources": ["RISK: translation has unmatched reference identifiers: 1, 2"]}
        )
        observed = build_waiver_records(
            {
                "resources": [
                    "RISK: translation has unmatched reference identifiers: 1, 2, 3"
                ]
            }
        )
        self.assertTrue(compare_waiver_records(recorded, observed)[1])

    def test_duplicate_semantic_finding_and_unknown_rule_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate waiver finding"):
            build_waiver_records(
                {
                    "listings": [
                        "RISK: Listing 1 fenced payload has weak distinctive-identifier "
                        "overlap with source candidate (0.10)",
                        "RISK: Listing 1 fenced payload has weak distinctive-identifier "
                        "overlap with source candidate (0.20)",
                    ]
                }
            )
        with self.assertRaisesRegex(ValueError, "unknown resources waiver candidate"):
            build_waiver_records({"resources": ["RISK: a future unversioned rule"]})

    def test_abridgement_diagnostic_requires_pinned_metric_and_valid_severity(self) -> None:
        valid = (
            "moderate mechanical abridgement risk: CJK/source-word ratio=50/100 "
            "(<0.75; extractor=pypdf-6.14.2; metric=v1)"
        )
        record = build_waiver_records({"abridgement": [valid]})
        self.assertEqual(record["abridgement"]["findings"], ["abridgement:moderate"])
        for invalid in (
            valid.replace("pypdf-6.14.2", "pypdf-6.14.1"),
            valid.replace("metric=v1", "metric=v2"),
            valid.replace("moderate", "high"),
            valid.replace("<0.75", "<0.50"),
            "moderate mechanical abridgement risk: arbitrary future metric",
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "unknown abridgement waiver candidate"
            ):
                build_waiver_records({"abridgement": [invalid]})

    def test_evidence_version_change_is_rejected(self) -> None:
        records = build_waiver_records({"resources": [self.resource_candidate(1)]})
        records["resources"]["evidence_version"] += 1
        with self.assertRaisesRegex(ValueError, "evidence_version"):
            validate_waiver_records(records)

    def test_reviewed_category_is_separate_from_changed_category(self) -> None:
        recorded = build_waiver_records(
            {
                "listings": [
                    "RISK: Listing 1 fenced payload shares no literals with source candidate"
                ],
                "resources": [self.resource_candidate(1)],
            }
        )
        observed = build_waiver_records(
            {
                "listings": [
                    "RISK: Listing 2 fenced payload shares no literals with source candidate"
                ],
                "resources": [self.resource_candidate(1)],
            }
        )
        reviewed, mismatches = compare_waiver_records(recorded, observed)
        self.assertEqual(len(reviewed), 1)
        self.assertTrue(reviewed[0].startswith("reviewed:resources:"))
        self.assertEqual(len(mismatches), 1)
        self.assertTrue(mismatches[0].startswith("changed:listings:"))

    def test_summarize_cli_emits_copyable_review_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "observed.tsv"
            candidate = self.resource_candidate(1)
            path.write_text(f"resources\t{candidate}\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["acceptance_evidence.py", "summarize", "--observed", str(path)]
            ), contextlib.redirect_stdout(stdout):
                self.assertEqual(main(), 0)
        record = build_waiver_records({"resources": [candidate]})
        self.assertIn(
            f"--waiver resources={record['resources']['fingerprint']}",
            stdout.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
