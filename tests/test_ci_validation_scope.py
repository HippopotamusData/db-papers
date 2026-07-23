from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from scripts.ci_validation_scope import (
    changed_acceptance_paper_ids,
    emit_github_output,
    select_scope,
)


class CiValidationScopeTests(unittest.TestCase):
    def test_docs_and_catalog_changes_use_fast_gate(self) -> None:
        deep, paper_ids, deep_paths = select_scope(
            ["README.md", "CATALOG.md", "docs/workflows/metadata.md"]
        )
        self.assertFalse(deep)
        self.assertEqual(paper_ids, [])
        self.assertEqual(deep_paths, [])

    def test_paper_changes_select_only_affected_papers(self) -> None:
        deep, paper_ids, deep_paths = select_scope(
            [
                "papers/storage/paper-b/translation.md",
                "papers/query-processing/paper-a/assets/figure-1.png",
                "./papers/query-processing/paper-a/paper.yaml",
                "papers/query-processing/paper-a/notes.txt",
            ]
        )
        self.assertFalse(deep)
        self.assertEqual(paper_ids, ["paper-a", "paper-b"])
        self.assertEqual(deep_paths, [])

    def test_validator_dependency_and_global_policy_changes_use_deep_gate(
        self,
    ) -> None:
        for path in (
            "AGENTS.md",
            ".github/workflows/check.yml",
            "Makefile",
            "config/policy.yaml",
            "docs/translation-policy.md",
            "package-lock.json",
            "pyproject.toml",
            "scripts/ci_validation_scope.py",
            "scripts/pdf_metrics.py",
            "scripts/validate_source_pdf.py",
            "scripts/validate_resources.py",
            "scripts/validate_translations.sh",
            "scripts/validation_policy.py",
        ):
            with self.subTest(path=path):
                deep, _, deep_paths = select_scope([path])
                self.assertTrue(deep)
                self.assertEqual(deep_paths, [path])

    def test_fast_validator_changes_do_not_force_deep_gate(self) -> None:
        deep, paper_ids, deep_paths = select_scope(
            [
                "scripts/validate_github_math.py",
                "tests/test_validate_resources.py",
            ]
        )
        self.assertFalse(deep)
        self.assertEqual(paper_ids, [])
        self.assertEqual(deep_paths, [])

    def test_acceptance_only_change_selects_exact_paper_ids(self) -> None:
        base = {
            "schema_version": 5,
            "review_snapshots": {},
            "entries": {
                "paper-a": {"fingerprint": "a"},
                "paper-b": {"fingerprint": "b"},
            },
        }
        head = {
            "schema_version": 5,
            "review_snapshots": {},
            "entries": {
                "paper-a": {"fingerprint": "changed"},
                "paper-b": {"fingerprint": "b"},
                "paper-c": {"fingerprint": "c"},
            },
        }
        deep, paper_ids, deep_paths = select_scope(
            ["config/acceptance.yaml"],
            acceptance_base=base,
            acceptance_head=head,
        )
        self.assertFalse(deep)
        self.assertEqual(paper_ids, ["paper-a", "paper-c"])
        self.assertEqual(deep_paths, [])

    def test_acceptance_schema_or_top_level_change_forces_deep_gate(self) -> None:
        valid = {"schema_version": 5, "review_snapshots": {}, "entries": {}}
        unsafe_heads = (
            {"schema_version": 6, "review_snapshots": {}, "entries": {}},
            {
                "schema_version": 5,
                "review_snapshots": {},
                "entries": {},
                "unexpected": {},
            },
            {"schema_version": 5, "review_snapshots": {}, "entries": []},
            {
                "schema_version": 5,
                "review_snapshots": {"changed": {}},
                "entries": {},
            },
        )
        for head in unsafe_heads:
            with self.subTest(head=head):
                deep, paper_ids, deep_paths = select_scope(
                    ["config/acceptance.yaml"],
                    acceptance_base=valid,
                    acceptance_head=head,
                )
                self.assertTrue(deep)
                self.assertEqual(paper_ids, [])
                self.assertEqual(deep_paths, ["config/acceptance.yaml"])

    def test_acceptance_change_without_trusted_snapshots_forces_deep_gate(self) -> None:
        deep, paper_ids, deep_paths = select_scope(
            ["config/acceptance.yaml"]
        )
        self.assertTrue(deep)
        self.assertEqual(paper_ids, [])
        self.assertEqual(deep_paths, ["config/acceptance.yaml"])

    def test_acceptance_diff_rejects_invalid_entry_shapes(self) -> None:
        unsafe, paper_ids = changed_acceptance_paper_ids(
            {"schema_version": 5, "review_snapshots": {}, "entries": {}},
            {
                "schema_version": 5,
                "review_snapshots": {},
                "entries": {"paper-a": "not-a-receipt"},
            },
        )
        self.assertTrue(unsafe)
        self.assertEqual(paper_ids, [])

    def test_unknown_diff_base_forces_deep_gate(self) -> None:
        deep, paper_ids, deep_paths = select_scope(
            ["README.md"], force_deep=True
        )
        self.assertTrue(deep)
        self.assertEqual(paper_ids, [])
        self.assertEqual(deep_paths, [])

    def test_github_output_is_deterministic(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            emit_github_output(True, ["paper-a", "paper-b"])
        self.assertEqual(
            output.getvalue(),
            "deep_check=true\n"
            "paper_ids<<__DB_PAPERS__\n"
            "paper-a\n"
            "paper-b\n"
            "__DB_PAPERS__\n",
        )


if __name__ == "__main__":
    unittest.main()
