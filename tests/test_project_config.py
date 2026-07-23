from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from acceptance_evidence import build_waiver_records  # noqa: E402
import project_config  # noqa: E402
from project_config import (  # noqa: E402
    REVIEW_GATE_STATIC_PATHS,
    REVIEW_IDENTITY_ASSURANCE,
    REVIEW_RECEIPT_SCHEMA_VERSION,
    REQUIRED_REVIEW_CHECKS,
    assets_manifest_sha256,
    configured_paths,
    effective_page_limit,
    load_acceptance_ledger,
    load_project_policy,
    load_taxonomy,
    review_gate_manifest_sha256,
    review_metadata_sha256,
    review_receipt_fingerprint,
    skip_reason,
    validate_review_receipt,
)


def review_receipt_v2(**updates: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": 2,
        "paper_id": "sample",
        "source_sha256": "0" * 64,
        "translation_sha256": "1" * 64,
        "assets_manifest_sha256": "2" * 64,
        "review_metadata_sha256": "4" * 64,
        "review_action": "repair-review",
        "translator": "codex:/root/translator",
        "reviewer": "codex:/root/reviewer",
        "review_base_sha": "6" * 40,
        "review_head_sha": "7" * 40,
        "findings": ["All review dimensions passed against source.pdf."],
        "authorial_voice": {
            "source_valid_items": 2,
            "verified_items": 2,
            "shared_subject_merges": 1,
        },
        "waivers": {},
    }
    receipt.update(updates)
    receipt["fingerprint"] = review_receipt_fingerprint(receipt)
    return receipt


class ProjectConfigTests(unittest.TestCase):
    def test_yaml_loader_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "outside.yaml"
            target.write_text("value: outside\n", encoding="utf-8")
            linked = root / "paper.yaml"
            linked.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                project_config.load_yaml(linked)

    def test_review_gate_manifest_binds_active_review_procedure(self) -> None:
        self.assertIn("AGENTS.md", REVIEW_GATE_STATIC_PATHS)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in REVIEW_GATE_STATIC_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"{relative}\n", encoding="utf-8")
            scripts = root / "scripts"
            scripts.mkdir(exist_ok=True)
            (scripts / "validator.py").write_text("RULE = 1\n", encoding="utf-8")
            nested = scripts / "helpers/rule.py"
            nested.parent.mkdir()
            nested.write_text("RULE = 2\n", encoding="utf-8")

            initial = review_gate_manifest_sha256(root)
            nested.write_text("RULE = 3\n", encoding="utf-8")
            nested_changed = review_gate_manifest_sha256(root)
            self.assertNotEqual(initial, nested_changed)
            review_workflow = root / "docs/workflows/review.md"
            review_workflow.write_text(
                review_workflow.read_text(encoding="utf-8") + "changed\n",
                encoding="utf-8",
            )
            self.assertNotEqual(
                nested_changed,
                review_gate_manifest_sha256(root),
            )

    def test_repository_policy_and_taxonomy_match_their_schemas(self) -> None:
        paths = configured_paths(ROOT)
        policy = load_project_policy(paths["policy"])
        self.assertEqual(policy["default_max_source_pages"], 60)
        load_taxonomy(ROOT / "config/taxonomy.yaml")
        acceptance = load_acceptance_ledger(paths["acceptance_ledger"])
        self.assertEqual(acceptance["schema_version"], 5)
        self.assertEqual(len(acceptance["entries"]), 144)
        self.assertTrue(
            all(
                receipt["paper_id"] == paper_id
                for paper_id, receipt in acceptance["entries"].items()
            )
        )
        legacy_empty_findings = {
            paper_id
            for paper_id, receipt in acceptance["entries"].items()
            if receipt["schema_version"] == 1 and not receipt["findings"]
        }
        self.assertEqual(
            legacy_empty_findings,
            set(),
        )

    def test_taxonomy_reader_text_must_be_trimmed_single_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "taxonomy.yaml"
            path.write_text(
                "schema_version: 1\n"
                "areas:\n"
                "  query-processing:\n"
                "    label_zh: ' 查询处理'\n"
                "    description: description\n"
                "topics:\n"
                "  query-execution:\n"
                "    label_zh: 查询执行\n"
                "    description: description\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "trimmed"):
                load_taxonomy(path)

    def test_page_exception_requires_authorization_and_higher_limit(self) -> None:
        invalid_records = (
            "    max_source_pages: 80\n",
            "    max_source_pages: 60\n    authorization: explicit user override\n",
        )
        for record in invalid_records:
            with self.subTest(record=record), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "policy.yaml"
                path.write_text(
                    "schema_version: 1\ndefault_max_source_pages: 60\npapers:\n"
                    "  sample:\n"
                    + record,
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_project_policy(path)

    def test_policy_exposes_named_limit_and_skip_reason(self) -> None:
        policy = {
            "default_max_source_pages": 60,
            "papers": {
                "long-paper": {
                    "max_source_pages": 80,
                    "authorization": "explicit user override",
                },
                "skipped-paper": {"skip_reason": "out-of-scope"},
            },
        }
        self.assertEqual(effective_page_limit(policy, "long-paper"), 80)
        self.assertEqual(effective_page_limit(policy, "other-paper"), 60)
        self.assertEqual(skip_reason(policy, "skipped-paper"), "out-of-scope")
        self.assertEqual(skip_reason(policy, "other-paper"), "")

    def test_schema_versions_reject_boolean_and_float_lookalikes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            policy = root / "policy.yaml"
            policy.write_text(
                "schema_version: 1.0\ndefault_max_source_pages: 60\npapers: {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_project_policy(policy)

            acceptance = root / "acceptance.yaml"
            acceptance.write_text(
                "schema_version: true\n"
                "review_snapshots: {}\n"
                "entries: {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must be integer 5"):
                load_acceptance_ledger(acceptance)

            taxonomy = root / "taxonomy.yaml"
            taxonomy.write_text(
                "schema_version: 1.0\nareas: {}\ntopics: {}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_taxonomy(taxonomy)

    def test_acceptance_rejects_unknown_action_and_waiver(self) -> None:
        invalid_updates = (
            {"review_action": "anything-goes"},
            {"review_action": "legacy-migration"},
            {"waivers": {"arbitrary-typo-code": {}}},
        )
        for updates in invalid_updates:
            with self.subTest(updates=updates), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "acceptance.yaml"
                receipt = review_receipt_v2(**updates)
                path.write_text(
                    yaml.safe_dump(
                        {
                            "schema_version": 5,
                            "review_snapshots": {},
                            "entries": {"sample": receipt},
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_acceptance_ledger(path)

    def test_acceptance_rejects_unfrozen_migration_reviewers(self) -> None:
        for reviewer in (
            "pending-v3-re-review",
            "historical-v2-reviewer-unrecorded",
        ):
            with self.subTest(reviewer=reviewer), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "acceptance.yaml"
                receipt = review_receipt_v2(reviewer=reviewer)
                path.write_text(
                    yaml.safe_dump(
                        {
                            "schema_version": 5,
                            "review_snapshots": {},
                            "entries": {"sample": receipt},
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_acceptance_ledger(path)

    def test_acceptance_v5_rejects_receiptless_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "acceptance.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 5,
                        "review_snapshots": {},
                        "entries": {
                            "sample": {
                                "schema_version": 2,
                                "source_sha256": "0" * 64,
                            }
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing keys"):
                load_acceptance_ledger(path)

    def test_acceptance_v5_rejects_legacy_retirement_top_level(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "acceptance.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 5,
                        "review_snapshots": {},
                        "retired_legacy_entry_fingerprints": {},
                        "entries": {},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown keys"):
                load_acceptance_ledger(path)

    def test_content_bound_review_receipt_requires_independent_complete_review(self) -> None:
        receipt = review_receipt_v2()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "acceptance.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 5,
                        "review_snapshots": {},
                        "entries": {"sample": receipt},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            loaded = load_acceptance_ledger(path)
            self.assertEqual(
                loaded["entries"]["sample"]["translator"],
                "codex:/root/translator",
            )

            same_identity = dict(receipt)
            same_identity["reviewer"] = same_identity["translator"]
            same_identity["fingerprint"] = review_receipt_fingerprint(same_identity)
            path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 5,
                        "review_snapshots": {},
                        "entries": {"sample": same_identity},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "translator and reviewer must be different"
            ):
                load_acceptance_ledger(path)

    def test_v2_findings_are_bounded_single_line_summaries(self) -> None:
        invalid_findings = (
            ["first line\nsecond line"],
            ["x" * 501],
            [f"finding {index}" for index in range(9)],
        )
        for findings in invalid_findings:
            with self.subTest(findings=len(findings)):
                receipt = review_receipt_v2(findings=findings)
                with self.assertRaisesRegex(ValueError, "at most 8 single-line"):
                    validate_review_receipt(receipt, "receipt")

    def test_v1_receipt_uses_frozen_schema_rules(self) -> None:
        metadata = {
            "title": "Sample",
            "authors": ["A. Author"],
            "year": 2026,
            "source_url": "https://example.com/sample",
            "future_field": "not part of v1",
        }
        receipt = {
            "schema_version": 1,
            "paper_id": "sample",
            "source_sha256": "0" * 64,
            "translation_sha256": "1" * 64,
            "assets_manifest_sha256": "2" * 64,
            "translation_policy_sha256": "3" * 64,
            "review_metadata_sha256": review_metadata_sha256(metadata, 1),
            "review_gate_manifest_sha256": "5" * 64,
            "review_action": "repair-review",
            "translator": "codex:/root/translator",
            "reviewer": "codex:/root/reviewer",
            "identity_assurance": "self-attested",
            "review_base_sha": "6" * 40,
            "checks": sorted(REQUIRED_REVIEW_CHECKS),
            "findings": [],
            "waivers": {},
        }
        receipt["fingerprint"] = review_receipt_fingerprint(receipt)
        expected_metadata_hash = receipt["review_metadata_sha256"]

        with patch.object(
            project_config,
            "REQUIRED_REVIEW_CHECKS",
            {"future-check"},
        ), patch.object(
            project_config,
            "REVIEW_METADATA_KEYS",
            ("title", "future_field"),
        ), patch.object(
            project_config,
            "REVIEW_IDENTITY_ASSURANCE",
            "future-assurance",
        ), patch.object(
            project_config,
            "REVIEW_ACTIONS",
            {"future-review"},
        ):
            validated = validate_review_receipt(dict(receipt), "receipt")
            self.assertEqual(validated["checks"], receipt["checks"])
            self.assertEqual(
                review_metadata_sha256(metadata, 1),
                expected_metadata_hash,
            )

    def test_unknown_review_receipt_schema_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "supported integer version"):
            validate_review_receipt({"schema_version": 3}, "receipt")

    def test_assets_manifest_digest_changes_with_same_path_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paper = root / "papers/query-processing/sample"
            assets = paper / "assets"
            assets.mkdir(parents=True)
            image = assets / "figure.png"
            image.write_bytes(b"first")
            before = assets_manifest_sha256(paper, root)
            image.write_bytes(b"second")
            self.assertNotEqual(before, assets_manifest_sha256(paper, root))


if __name__ == "__main__":
    unittest.main()
