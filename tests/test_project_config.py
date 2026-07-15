from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from project_config import (  # noqa: E402
    effective_page_limit,
    load_acceptance_ledger,
    load_paper_policy,
    load_project_config,
    load_taxonomy,
)


class ProjectConfigTests(unittest.TestCase):
    def test_repository_configs_match_their_schemas(self) -> None:
        config = load_project_config(ROOT)
        self.assertEqual(config["translation_policy"]["max_source_pages"], 60)
        load_paper_policy(ROOT / config["records"]["paper_policy"])
        load_acceptance_ledger(ROOT / config["records"]["acceptance_ledger"])

    def test_project_schema_rejects_wrong_boolean_type(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            data = yaml.safe_load((ROOT / "config/project.yaml").read_text(encoding="utf-8"))
            data["translation_policy"]["require_complete_references"] = "yes"
            (root / "config/project.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be a boolean"):
                load_project_config(root)

    def test_page_exception_requires_reason_and_positive_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "paper-policy.yaml"
            path.write_text(
                "schema_version: 1\npage_limit_exceptions:\n  sample:\n    max_pages: 0\n    reason: user override\nskipped_reasons: {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "positive integer"):
                load_paper_policy(path)

    def test_page_exception_overrides_only_the_named_paper(self) -> None:
        project = load_project_config(ROOT)
        policy = {
            "page_limit_exceptions": {
                "long-paper": {"max_pages": 80, "reason": "explicit user exception"}
            }
        }
        self.assertEqual(effective_page_limit(project, policy, "long-paper"), 80)
        self.assertEqual(effective_page_limit(project, policy, "other-paper"), 60)

    def test_schema_versions_reject_boolean_and_float_lookalikes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()

            project = yaml.safe_load((ROOT / "config/project.yaml").read_text(encoding="utf-8"))
            project["schema_version"] = 2.0
            (root / "config/project.yaml").write_text(
                yaml.safe_dump(project), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must be integer 2"):
                load_project_config(root)

            policy = root / "paper-policy.yaml"
            policy.write_text(
                "schema_version: 1.0\npage_limit_exceptions: {}\nskipped_reasons: {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_paper_policy(policy)

            acceptance = root / "acceptance.yaml"
            acceptance.write_text("schema_version: true\nentries: {}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_acceptance_ledger(acceptance)

            taxonomy = root / "taxonomy.yaml"
            taxonomy.write_text(
                "schema_version: 1.0\nareas: {}\ntopics: {}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_taxonomy(taxonomy)

    def test_acceptance_entry_requires_controlled_base_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "acceptance.yaml"
            path.write_text(
                "schema_version: 1\nentries:\n  sample:\n"
                "    source_sha256: '" + "0" * 64 + "'\n"
                "    translation_sha256: '" + "1" * 64 + "'\n"
                "    accepted_version: v1\n"
                "    risk_disposition: [anything-goes]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "controlled base acceptance code"):
                load_acceptance_ledger(path)


if __name__ == "__main__":
    unittest.main()
