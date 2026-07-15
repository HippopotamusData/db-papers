from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from project_config import (  # noqa: E402
    configured_paths,
    effective_page_limit,
    load_acceptance_ledger,
    load_project_policy,
    load_taxonomy,
    skip_reason,
)


class ProjectConfigTests(unittest.TestCase):
    def test_repository_configs_match_their_schemas(self) -> None:
        paths = configured_paths(ROOT)
        policy = load_project_policy(paths["policy"])
        self.assertEqual(policy["default_max_source_pages"], 60)
        load_acceptance_ledger(paths["acceptance_ledger"])
        load_taxonomy(ROOT / "config/taxonomy.yaml")

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
            with self.assertRaisesRegex(ValueError, "must be integer 2"):
                load_acceptance_ledger(acceptance)

            taxonomy = root / "taxonomy.yaml"
            taxonomy.write_text(
                "schema_version: 1.0\nareas: {}\ntopics: {}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_taxonomy(taxonomy)

    def test_acceptance_rejects_unknown_action_and_waiver(self) -> None:
        base = (
            "schema_version: 2\nentries:\n  sample:\n"
            "    source_sha256: '" + "0" * 64 + "'\n"
            "    translation_sha256: '" + "1" * 64 + "'\n"
        )
        invalid_entries = (
            "    review_action: anything-goes\n",
            "    review_action: section-review\n    waivers: [arbitrary-typo-code]\n",
        )
        for entry in invalid_entries:
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "acceptance.yaml"
                path.write_text(base + entry, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_acceptance_ledger(path)


if __name__ == "__main__":
    unittest.main()
