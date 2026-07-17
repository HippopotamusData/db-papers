from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from acceptance_evidence import build_waiver_records  # noqa: E402
from project_config import (  # noqa: E402
    HISTORICAL_V2_ENTRY_FINGERPRINTS,
    assets_manifest_sha256,
    configured_paths,
    effective_page_limit,
    load_acceptance_ledger,
    load_project_policy,
    load_taxonomy,
    skip_reason,
)


class ProjectConfigTests(unittest.TestCase):
    def test_repository_policy_and_taxonomy_match_their_schemas(self) -> None:
        paths = configured_paths(ROOT)
        policy = load_project_policy(paths["policy"])
        self.assertEqual(policy["default_max_source_pages"], 60)
        load_taxonomy(ROOT / "config/taxonomy.yaml")
        acceptance = load_acceptance_ledger(paths["acceptance_ledger"])
        historical_ids = {
            paper_id
            for paper_id, entry in acceptance["entries"].items()
            if entry["reviewer"] == "historical-v2-reviewer-unrecorded"
        }
        self.assertEqual(historical_ids, set(HISTORICAL_V2_ENTRY_FINGERPRINTS))

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
            acceptance.write_text("schema_version: true\nentries: {}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be integer 3"):
                load_acceptance_ledger(acceptance)

            taxonomy = root / "taxonomy.yaml"
            taxonomy.write_text(
                "schema_version: 1.0\nareas: {}\ntopics: {}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_taxonomy(taxonomy)

    def test_acceptance_rejects_unknown_action_and_waiver(self) -> None:
        base = (
            "schema_version: 3\nentries:\n  sample:\n"
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
                    "schema_version: 3\nentries:\n  sample:\n"
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

    def test_acceptance_v3_requires_reviewer_base_asset_hash_and_exact_waiver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "acceptance.yaml"
            candidate = (
                "RISK: source Figure 1 has no formal translation-side payload candidate"
            )
            path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 3,
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
            entry = load_acceptance_ledger(path)["entries"]["sample"]
            self.assertEqual(entry["reviewer"], "reviewer@example.com")

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
