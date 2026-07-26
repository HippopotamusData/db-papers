from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import project_config  # noqa: E402
from project_config import (  # noqa: E402
    configured_paths,
    effective_page_limit,
    load_project_policy,
    load_taxonomy,
    skip_reason,
)


class ProjectConfigTests(unittest.TestCase):
    def test_yaml_loader_rejects_duplicate_mapping_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            project_config.load_yaml_text("value: first\nvalue: second\n", "test")

    def test_yaml_loader_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "outside.yaml"
            target.write_text("value: outside\n", encoding="utf-8")
            linked = root / "paper.yaml"
            linked.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                project_config.load_yaml(linked)

    def test_repository_policy_and_taxonomy_match_their_schemas(self) -> None:
        paths = configured_paths(ROOT)
        policy = load_project_policy(paths["policy"])
        self.assertEqual(policy["default_max_source_pages"], 60)
        load_taxonomy(ROOT / "config/taxonomy.yaml")
        self.assertEqual(
            set(paths),
            {"metadata", "source", "translation", "policy"},
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

            taxonomy = root / "taxonomy.yaml"
            taxonomy.write_text(
                "schema_version: 1.0\nareas: {}\ntopics: {}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must be integer 1"):
                load_taxonomy(taxonomy)

if __name__ == "__main__":
    unittest.main()
