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
    HISTORICAL_V2_ENTRY_FINGERPRINTS,
    LEGACY_RECEIPTLESS_ENTRY_FINGERPRINTS,
    REVIEW_GATE_STATIC_PATHS,
    REVIEW_IDENTITY_ASSURANCE,
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
    validate_repository_legacy_freeze,
)


class ProjectConfigTests(unittest.TestCase):
    def test_review_gate_manifest_binds_active_review_procedure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in REVIEW_GATE_STATIC_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"{relative}\n", encoding="utf-8")
            scripts = root / "scripts"
            scripts.mkdir(exist_ok=True)
            (scripts / "validator.py").write_text("RULE = 1\n", encoding="utf-8")

            initial = review_gate_manifest_sha256(root)
            review_workflow = root / "docs/workflows/review.md"
            review_workflow.write_text(
                review_workflow.read_text(encoding="utf-8") + "changed\n",
                encoding="utf-8",
            )
            self.assertNotEqual(initial, review_gate_manifest_sha256(root))

    def test_repository_policy_and_taxonomy_match_their_schemas(self) -> None:
        paths = configured_paths(ROOT)
        policy = load_project_policy(paths["policy"])
        self.assertEqual(policy["default_max_source_pages"], 60)
        load_taxonomy(ROOT / "config/taxonomy.yaml")
        acceptance = load_acceptance_ledger(paths["acceptance_ledger"])
        retired_ids = set(
            acceptance["retired_legacy_entry_fingerprints"]
        )
        historical_ids = {
            paper_id
            for paper_id, entry in acceptance["entries"].items()
            if entry["reviewer"] == "historical-v2-reviewer-unrecorded"
        }
        self.assertEqual(
            historical_ids,
            set(HISTORICAL_V2_ENTRY_FINGERPRINTS) - retired_ids,
        )
        receiptless_ids = {
            paper_id
            for paper_id, entry in acceptance["entries"].items()
            if "review_receipt" not in entry
        }
        self.assertEqual(
            receiptless_ids,
            set(LEGACY_RECEIPTLESS_ENTRY_FINGERPRINTS) - retired_ids,
        )
        self.assertTrue(
            all(
                "review_receipt" in acceptance["entries"][paper_id]
                for paper_id in retired_ids
            )
        )

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
                "retired_legacy_entry_fingerprints: {}\n"
                "entries: {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must be integer 4"):
                load_acceptance_ledger(acceptance)

            taxonomy = root / "taxonomy.yaml"
            taxonomy.write_text(
                "schema_version: 1.0\nareas: {}\ntopics: {}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_taxonomy(taxonomy)

    def test_acceptance_rejects_unknown_action_and_waiver(self) -> None:
        base = (
            "schema_version: 4\n"
            "retired_legacy_entry_fingerprints: {}\n"
            "entries:\n  sample:\n"
            "    source_sha256: '" + "0" * 64 + "'\n"
            "    translation_sha256: '" + "1" * 64 + "'\n"
            "    assets_manifest_sha256: '" + "2" * 64 + "'\n"
            "    reviewer: reviewer@example.com\n"
            "    review_base_sha: '" + "3" * 40 + "'\n"
        )
        invalid_entries = (
            "    review_action: anything-goes\n",
            "    review_action: legacy-migration\n",
            "    review_action: section-review\n    waivers:\n      arbitrary-typo-code:\n        fingerprint: '"
            + "4" * 64
            + "'\n        candidates: [candidate]\n",
        )
        for entry in invalid_entries:
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "acceptance.yaml"
                path.write_text(base + entry, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_acceptance_ledger(path)

    def test_acceptance_rejects_unfrozen_migration_reviewers(self) -> None:
        for reviewer in (
            "pending-v3-re-review",
            "historical-v2-reviewer-unrecorded",
        ):
            with self.subTest(reviewer=reviewer), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "acceptance.yaml"
                path.write_text(
                    "schema_version: 4\n"
                    "retired_legacy_entry_fingerprints: {}\n"
                    "entries:\n  sample:\n"
                    f"    source_sha256: '{'0' * 64}'\n"
                    f"    translation_sha256: '{'1' * 64}'\n"
                    f"    assets_manifest_sha256: '{'2' * 64}'\n"
                    "    review_action: repair-review\n"
                    f"    reviewer: {reviewer}\n"
                    f"    review_base_sha: '{'3' * 40}'\n",
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_acceptance_ledger(path)

    def test_acceptance_v4_rejects_unfrozen_receiptless_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "acceptance.yaml"
            candidate = (
                "RISK: source Figure 1 has no formal translation-side payload candidate"
            )
            path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 4,
                        "retired_legacy_entry_fingerprints": {},
                        "entries": {
                            "sample": {
                                "source_sha256": "0" * 64,
                                "translation_sha256": "1" * 64,
                                "assets_manifest_sha256": "2" * 64,
                                "review_action": "repair-review",
                                "reviewer": "reviewer@example.com",
                                "review_base_sha": "3" * 40,
                                "waivers": build_waiver_records(
                                    {"resources": [candidate]}
                                ),
                            }
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "receiptless legacy evidence"):
                load_acceptance_ledger(path)

    def test_repository_legacy_retirement_requires_exact_fingerprint_and_receipt(
        self,
    ) -> None:
        frozen = "a" * 64
        data = {
            "retired_legacy_entry_fingerprints": {"sample": frozen},
            "entries": {
                "sample": {
                    "reviewer": "human:reviewer@example.com",
                    "review_receipt": {},
                }
            },
        }
        with patch(
            "project_config.LEGACY_RECEIPTLESS_ENTRY_FINGERPRINTS",
            {"sample": frozen},
        ), patch(
            "project_config.HISTORICAL_V2_ENTRY_FINGERPRINTS",
            {},
        ):
            validate_repository_legacy_freeze(data, "ledger")

            data["retired_legacy_entry_fingerprints"]["sample"] = "b" * 64
            with self.assertRaisesRegex(
                ValueError,
                "changed retired legacy fingerprints",
            ):
                validate_repository_legacy_freeze(data, "ledger")

            data["retired_legacy_entry_fingerprints"]["sample"] = frozen
            data["entries"]["sample"].pop("review_receipt")
            with self.assertRaisesRegex(
                ValueError,
                "retired legacy entries without review receipts",
            ):
                validate_repository_legacy_freeze(data, "ledger")

    def test_content_bound_review_receipt_requires_independent_complete_review(self) -> None:
        receipt = {
            "schema_version": 1,
            "paper_id": "sample",
            "source_sha256": "0" * 64,
            "translation_sha256": "1" * 64,
            "assets_manifest_sha256": "2" * 64,
            "translation_policy_sha256": "3" * 64,
            "review_metadata_sha256": "4" * 64,
            "review_gate_manifest_sha256": "5" * 64,
            "review_action": "repair-review",
            "translator": "codex:/root/translator",
            "reviewer": "codex:/root/reviewer",
            "identity_assurance": REVIEW_IDENTITY_ASSURANCE,
            "review_base_sha": "6" * 40,
            "checks": sorted(REQUIRED_REVIEW_CHECKS),
            "findings": ["translation.md:10 repaired a source-backed omission"],
            "waivers": {},
        }
        receipt["fingerprint"] = review_receipt_fingerprint(receipt)
        entry = {
            "source_sha256": receipt["source_sha256"],
            "translation_sha256": receipt["translation_sha256"],
            "assets_manifest_sha256": receipt["assets_manifest_sha256"],
            "review_action": receipt["review_action"],
            "reviewer": receipt["reviewer"],
            "review_base_sha": receipt["review_base_sha"],
            "review_receipt": receipt,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "acceptance.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 4,
                        "retired_legacy_entry_fingerprints": {},
                        "entries": {"sample": entry},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            loaded = load_acceptance_ledger(path)
            self.assertEqual(
                loaded["entries"]["sample"]["review_receipt"]["translator"],
                "codex:/root/translator",
            )

            same_identity = dict(receipt)
            same_identity["reviewer"] = same_identity["translator"]
            same_identity["fingerprint"] = review_receipt_fingerprint(same_identity)
            entry["reviewer"] = same_identity["reviewer"]
            entry["review_receipt"] = same_identity
            path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 4,
                        "retired_legacy_entry_fingerprints": {},
                        "entries": {"sample": entry},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "translator and reviewer must be different"
            ):
                load_acceptance_ledger(path)

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
            validate_review_receipt({"schema_version": 2}, "receipt")

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
