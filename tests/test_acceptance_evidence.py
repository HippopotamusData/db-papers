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

import acceptance_evidence  # noqa: E402
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

    @staticmethod
    def f1_numeric_recovery_candidate() -> str:
        mappings = ", ".join(
            f"{index}->{index}" for index in range(1, 25) if index != 16
        )
        return (
            "RISK: source numeric references 1-24 were recovered by complete "
            "ordered two-column bibliography-content evidence; parsed markers: "
            f"{mappings}"
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

    def test_removed_reviewed_findings_do_not_invalidate_acceptance(self) -> None:
        recorded = build_waiver_records(
            {
                "resources": [
                    "RISK: translation has unmatched reference identifiers: 1, 2, 3"
                ]
            }
        )
        observed = build_waiver_records(
            {
                "resources": [
                    "RISK: translation has unmatched reference identifiers: 2"
                ]
            }
        )
        reviewed, mismatches = compare_waiver_records(recorded, observed)
        self.assertEqual(mismatches, [])
        self.assertEqual(len(reviewed), 1)
        self.assertTrue(reviewed[0].startswith("reviewed:resources:"))

    def test_resolved_waiver_category_does_not_invalidate_acceptance(self) -> None:
        recorded = build_waiver_records(
            {"resources": [self.resource_candidate(1)]}
        )
        reviewed, mismatches = compare_waiver_records(recorded, {})
        self.assertEqual(reviewed, [])
        self.assertEqual(mismatches, [])

    def test_missing_inline_citation_subjects_are_content_bound(self) -> None:
        recorded = build_waiver_records(
            {
                "resources": [
                    "RISK: source body citation identifiers have no "
                    "translation-side candidate: 2"
                ]
            }
        )
        observed = build_waiver_records(
            {
                "resources": [
                    "RISK: source body citation identifiers have no "
                    "translation-side candidate: 2, 4"
                ]
            }
        )
        self.assertEqual(
            recorded["resources"]["findings"],
            ["missing-inline-citation:2"],
        )
        self.assertTrue(compare_waiver_records(recorded, observed)[1])

    def test_ordered_reference_ocr_mappings_are_item_bound(self) -> None:
        candidate = (
            "RISK: source reference identifiers were normalized by ordered "
            "contiguous OCR evidence: l->1, cs->9, lo->10, 19->14"
        )
        record = build_waiver_records({"resources": [candidate]})
        self.assertEqual(
            record["resources"]["findings"],
            [
                "source-reference-ocr-normalization:19:14",
                "source-reference-ocr-normalization:cs:9",
                "source-reference-ocr-normalization:l:1",
                "source-reference-ocr-normalization:lo:10",
            ],
        )

    def test_complete_delimiter_ocr_mappings_are_item_bound(self) -> None:
        candidate = (
            "RISK: source reference identifiers were normalized by complete "
            "ordered delimiter-OCR evidence: [ii->1, pi->2, i.581->58"
        )
        record = build_waiver_records({"resources": [candidate]})
        self.assertEqual(
            record["resources"]["findings"],
            [
                "source-reference-ocr-normalization:%5bii:1",
                "source-reference-ocr-normalization:i.581:58",
                "source-reference-ocr-normalization:pi:2",
            ],
        )

    def test_author_key_content_mappings_are_v2_item_bound_and_stable(self) -> None:
        first = (
            "RISK: source author-key reference identifiers were normalized by "
            "unique bibliography-content OCR evidence: "
            "br0w85->brow85, sel179->seli79"
        )
        reordered = (
            "RISK: source author-key reference identifiers were normalized by "
            "unique bibliography-content OCR evidence: "
            "sel179->seli79, br0w85->brow85"
        )

        first_record = build_waiver_records(
            {"resources": [first]},
            evidence_versions={"resources": 2},
        )
        reordered_record = build_waiver_records(
            {"resources": [reordered]},
            evidence_versions={"resources": 2},
        )
        current_record = build_waiver_records({"resources": [first]})

        self.assertEqual(first_record["resources"]["evidence_version"], 2)
        self.assertEqual(
            first_record["resources"]["findings"],
            [
                "source-reference-ocr-normalization:br0w85:brow85",
                "source-reference-ocr-normalization:sel179:seli79",
            ],
        )
        self.assertEqual(
            first_record["resources"]["fingerprint"],
            reordered_record["resources"]["fingerprint"],
        )
        self.assertEqual(
            decode_waiver_records(encode_waiver_records(first_record)),
            first_record,
        )
        self.assertEqual(current_record["resources"]["evidence_version"], 4)
        self.assertEqual(
            current_record["resources"]["findings"],
            first_record["resources"]["findings"],
        )

    def test_author_key_content_mapping_is_unknown_to_frozen_v1(self) -> None:
        candidate = (
            "RISK: source author-key reference identifiers were normalized by "
            "unique bibliography-content OCR evidence: br0w85->brow85"
        )
        with self.assertRaisesRegex(
            ValueError, "unknown resources waiver candidate"
        ):
            build_waiver_records(
                {"resources": [candidate]},
                evidence_versions={"resources": 1},
            )

    def test_author_key_content_mapping_rejects_non_bijective_candidates(self) -> None:
        prefix = (
            "RISK: source author-key reference identifiers were normalized by "
            "unique bibliography-content OCR evidence: "
        )
        for mappings in (
            "bad85->good85, bad85->other85",
            "bad85->good85, other85->good85",
            "same85->same85",
        ):
            with self.subTest(mappings=mappings), self.assertRaisesRegex(
                ValueError, "unknown resources waiver candidate"
            ):
                build_waiver_records(
                    {"resources": [prefix + mappings]},
                    evidence_versions={"resources": 2},
                )

    def test_author_key_mapping_is_globally_bijective_across_diagnostics(self) -> None:
        prefix = (
            "RISK: source author-key reference identifiers were normalized by "
            "unique bibliography-content OCR evidence: "
        )
        candidate_sets = (
            [prefix + "bad85->good85", prefix + "bad85->other85"],
            [prefix + "bad85->good85", prefix + "other85->good85"],
        )
        for candidates in candidate_sets:
            with self.subTest(candidates=candidates), self.assertRaisesRegex(
                ValueError, "global one-to-one mapping"
            ):
                build_waiver_records(
                    {"resources": candidates},
                    evidence_versions={"resources": 2},
                )

    def test_numeric_bibliography_recovery_is_v3_item_bound_and_stable(
        self,
    ) -> None:
        first = (
            "RISK: source numeric references 1-10 were recovered by complete "
            "ordered two-column bibliography-content evidence; parsed markers: "
            "l->1, 2->2, lo->10"
        )
        reordered = (
            "RISK: source numeric references 1-10 were recovered by complete "
            "ordered two-column bibliography-content evidence; parsed markers: "
            "lo->10, 2->2, l->1"
        )

        first_record = build_waiver_records(
            {"resources": [first]}, evidence_versions={"resources": 3}
        )
        reordered_record = build_waiver_records(
            {"resources": [reordered]}, evidence_versions={"resources": 3}
        )

        self.assertEqual(first_record["resources"]["evidence_version"], 3)
        self.assertEqual(
            first_record["resources"]["findings"],
            sorted(
                [
                    *(
                        f"source-reference-content-recovery:{index}"
                        for index in range(1, 11)
                    ),
                    "source-reference-marker-content-mapping:l:1",
                    "source-reference-marker-content-mapping:2:2",
                    "source-reference-marker-content-mapping:lo:10",
                ]
            ),
        )
        self.assertEqual(
            first_record["resources"]["fingerprint"],
            reordered_record["resources"]["fingerprint"],
        )
        with self.assertRaisesRegex(
            ValueError, "unknown resources waiver candidate"
        ):
            build_waiver_records(
                {"resources": [first]},
                evidence_versions={"resources": 2},
            )

    def test_f1_split_reference_recovery_is_bound_to_all_24_entries(self) -> None:
        record = build_waiver_records(
            {"resources": [self.f1_numeric_recovery_candidate()]},
            evidence_versions={"resources": 3},
        )["resources"]

        self.assertEqual(record["evidence_version"], 3)
        self.assertEqual(
            record["fingerprint"],
            "8cd5f1d10f915e3515282a9a7076ca7105d4940b57e3e6eacb7998d4753222f8",
        )
        self.assertEqual(len(record["findings"]), 47)
        self.assertIn("source-reference-content-recovery:16", record["findings"])
        self.assertIn(
            "source-reference-marker-content-mapping:15:15", record["findings"]
        )
        self.assertNotIn(
            "source-reference-marker-content-mapping:16:16", record["findings"]
        )
        self.assertIn(
            "source-reference-marker-content-mapping:17:17", record["findings"]
        )

    def test_numeric_bibliography_recovery_v3_rejects_weak_or_conflicting_claims(
        self,
    ) -> None:
        prefix = (
            "RISK: source numeric references 1-10 were recovered by complete "
            "ordered two-column bibliography-content evidence; parsed markers: "
        )
        invalid = (
            prefix + "l->1, 2->3, lo->10",
            prefix + "l->1, i->1, lo->10",
            prefix + "l->1, l->2, lo->10",
            prefix + "l->1, lo->10",
            prefix + "x->10, 2->2, l->1",
            prefix + "l->2, 3->3, lo->10",
            prefix + "O->9, 2->2, l->1",
            prefix.replace("1-10", "1-9") + "l->1, 2->2, is->9",
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaisesRegex(
                ValueError, "unknown resources waiver candidate"
            ):
                build_waiver_records(
                    {"resources": [candidate]},
                    evidence_versions={"resources": 3},
                )

    def test_numeric_bibliography_recovery_v3_accepts_real_scan_aliases(
        self,
    ) -> None:
        candidate = (
            "RISK: source numeric references 1-15 were recovered by complete "
            "ordered two-column bibliography-content evidence; parsed markers: "
            "l->1, lo->10, is->15"
        )

        record = build_waiver_records(
            {"resources": [candidate]},
            evidence_versions={"resources": 3},
        )["resources"]

        self.assertIn(
            "source-reference-marker-content-mapping:l:1",
            record["findings"],
        )
        self.assertIn(
            "source-reference-marker-content-mapping:lo:10",
            record["findings"],
        )
        self.assertIn(
            "source-reference-marker-content-mapping:is:15",
            record["findings"],
        )

    def test_frozen_v1_and_v2_fingerprints_do_not_follow_default_version(
        self,
    ) -> None:
        candidate = self.resource_candidate(1)
        expected = {
            1: "2ecf32a9ed88aec8cedf6b05e3c2c8e853484cf1cdb89200dffef1395d3e98ea",
            2: "8de0fe7af03400709132f595d15c9c6c123cb06154c140f10c8237d294479791",
        }
        for version, fingerprint in expected.items():
            with self.subTest(version=version):
                record = build_waiver_records(
                    {"resources": [candidate]},
                    evidence_versions={"resources": version},
                )["resources"]
                self.assertEqual(record["fingerprint"], fingerprint)

    def test_hierarchical_equation_number_is_v4_item_bound(self) -> None:
        candidate = (
            "RISK: source equation (2.1) has no translation-side "
            "display/formula candidate"
        )

        record = build_waiver_records({"resources": [candidate]})["resources"]

        self.assertEqual(record["evidence_version"], 4)
        self.assertEqual(record["findings"], ["missing-display-equation:2.1"])
        self.assertEqual(
            record["fingerprint"],
            "6adc5ecbb158df420ee50a85c01268c232f2b86466fb145244f23c5a51b2a6c9",
        )

    def test_frozen_v3_integer_equation_record_remains_valid(self) -> None:
        candidate = (
            "RISK: source equation (2) has no translation-side "
            "display/formula candidate"
        )
        record = build_waiver_records(
            {"resources": [candidate]},
            evidence_versions={"resources": 3},
        )

        self.assertEqual(record["resources"]["evidence_version"], 3)
        self.assertEqual(validate_waiver_records(record), record)
        self.assertEqual(
            record["resources"]["findings"], ["missing-display-equation:2"]
        )

    def test_dotted_equation_is_unknown_to_v3_and_compare_upgrades_to_v4(
        self,
    ) -> None:
        integer_candidate = (
            "RISK: source equation (2) has no translation-side "
            "display/formula candidate"
        )
        dotted_candidate = (
            "RISK: source equation (2.1) has no translation-side "
            "display/formula candidate"
        )
        recorded = build_waiver_records(
            {"resources": [integer_candidate]},
            evidence_versions={"resources": 3},
        )

        with self.assertRaisesRegex(
            ValueError, "unknown resources waiver candidate"
        ):
            build_waiver_records(
                {"resources": [dotted_candidate]},
                evidence_versions={"resources": 3},
            )

        observed = acceptance_evidence.build_observed_waiver_records_for_compare(
            recorded,
            {"resources": [dotted_candidate]},
        )
        self.assertEqual(observed["resources"]["evidence_version"], 4)
        _reviewed, mismatches = compare_waiver_records(recorded, observed)
        self.assertEqual(len(mismatches), 1)
        self.assertTrue(mismatches[0].startswith("changed:resources:"))

    def test_v1_numeric_ocr_mappings_do_not_use_author_key_bijection(self) -> None:
        candidates = [
            "RISK: source reference identifier i was normalized to 1 as a "
            "contiguous numeric-series OCR candidate",
            "RISK: source reference identifiers were normalized by ordered "
            "contiguous OCR evidence: i->2",
        ]

        record = build_waiver_records(
            {"resources": candidates},
            evidence_versions={"resources": 1},
        )

        self.assertEqual(
            record["resources"]["findings"],
            [
                "source-reference-ocr-normalization:i:1",
                "source-reference-ocr-normalization:i:2",
            ],
        )

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
        high = (
            "high mechanical abridgement risk: CJK/source-word ratio=49/100 "
            "(<0.50; extractor=pypdf-6.14.2; metric=v1)"
        )
        record = build_waiver_records({"abridgement": [valid]})
        self.assertEqual(record["abridgement"]["findings"], ["abridgement:moderate"])
        self.assertEqual(
            build_waiver_records({"abridgement": [high]})["abridgement"][
                "findings"
            ],
            ["abridgement:high"],
        )
        for invalid in (
            valid.replace("pypdf-6.14.2", "pypdf-6.14.1"),
            valid.replace("metric=v1", "metric=v2"),
            valid.replace("moderate", "high"),
            valid.replace("<0.75", "<0.50"),
            valid.replace("50/100", "75/100"),
            "moderate mechanical abridgement risk: arbitrary future metric",
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "unknown abridgement waiver candidate"
            ):
                build_waiver_records({"abridgement": [invalid]})

    def test_versioned_abridgement_parsers_ignore_live_metric_drift(self) -> None:
        candidate = (
            "moderate mechanical abridgement risk: CJK/source-word ratio=50/100 "
            "(<0.75; extractor=pypdf-6.14.2; metric=v1)"
        )
        records_by_version = {
            version: build_waiver_records(
                {"abridgement": [candidate]},
                evidence_versions={"abridgement": version},
            )
            for version in (1, 2, 3, 4)
        }

        with (
            patch.object(
                acceptance_evidence,
                "PYPDF_VERSION",
                "99.0.0",
                create=True,
            ),
            patch.object(
                acceptance_evidence,
                "PDF_METRICS_VERSION",
                99,
                create=True,
            ),
            patch.object(
                acceptance_evidence,
                "abridgement_candidate_from_counts",
                return_value=None,
                create=True,
            ),
        ):
            for version, records in records_by_version.items():
                with self.subTest(version=version):
                    encoded = encode_waiver_records(records)
                    self.assertEqual(validate_waiver_records(records), records)
                    self.assertEqual(decode_waiver_records(encoded), records)
                    reviewed, mismatches = compare_waiver_records(records, records)
                    self.assertEqual(mismatches, [])
                    self.assertEqual(len(reviewed), 1)

    def test_evidence_version_change_is_rejected(self) -> None:
        records = build_waiver_records({"resources": [self.resource_candidate(1)]})
        records["resources"]["evidence_version"] += 1
        with self.assertRaisesRegex(ValueError, "evidence_version"):
            validate_waiver_records(records)

    def test_v1_evidence_uses_its_frozen_parser(self) -> None:
        records = build_waiver_records(
            {"resources": [self.resource_candidate(1)]},
            evidence_versions={"resources": 1},
        )
        with patch.object(acceptance_evidence, "WAIVER_EVIDENCE_VERSION", 99):
            self.assertEqual(validate_waiver_records(records), records)

    def test_compare_cli_replays_recorded_v1_parser(self) -> None:
        candidate = self.resource_candidate(1)
        records = build_waiver_records(
            {"resources": [candidate]},
            evidence_versions={"resources": 1},
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "observed.tsv"
            path.write_text(f"resources\t{candidate}\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(
                sys,
                "argv",
                [
                    "acceptance_evidence.py",
                    "compare",
                    "--recorded",
                    encode_waiver_records(records),
                    "--observed",
                    str(path),
                ],
            ), contextlib.redirect_stdout(stdout):
                self.assertEqual(main(), 0)
        self.assertTrue(stdout.getvalue().startswith("reviewed:resources:"))

    def test_compare_cli_reports_current_v4_recovery_as_changed_from_f1_v1(
        self,
    ) -> None:
        old_candidates = [
            "RISK: reference entry-count candidate differs (23/24)",
            "RISK: translation has unmatched reference identifiers: 16",
        ]
        records = build_waiver_records(
            {"resources": old_candidates},
            evidence_versions={"resources": 1},
        )
        old_fingerprint = (
            "ca23b69d2401f2d36ffc874119618e07fb2874fb2a0366789c23f693bb69b7e2"
        )
        new_fingerprint = (
            "4de007761dd4e125d3b3d10554f602eb0962c01465478b2edcd6bc5f9b8cb84f"
        )
        self.assertEqual(records["resources"]["fingerprint"], old_fingerprint)

        candidate = self.f1_numeric_recovery_candidate()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "observed.tsv"
            path.write_text(f"resources\t{candidate}\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(
                sys,
                "argv",
                [
                    "acceptance_evidence.py",
                    "compare",
                    "--recorded",
                    encode_waiver_records(records),
                    "--observed",
                    str(path),
                ],
            ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(main(), 1)

        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            stdout.getvalue().strip(),
            f"changed:resources:{old_fingerprint}:{new_fingerprint}:{candidate}",
        )
        self.assertNotIn("unknown resources waiver candidate", stdout.getvalue())

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
