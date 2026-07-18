from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from scripts.ci_validation_scope import emit_github_output, select_scope


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
            ".github/workflows/check.yml",
            "Makefile",
            "config/policy.yaml",
            "docs/translation-policy.md",
            "package-lock.json",
            "pyproject.toml",
            "scripts/ci_validation_scope.py",
            "scripts/pdf_metrics.py",
            "scripts/validate_resources.py",
            "scripts/validate_translations.sh",
        ):
            with self.subTest(path=path):
                deep, _, deep_paths = select_scope([path])
                self.assertTrue(deep)
                self.assertEqual(deep_paths, [path])

    def test_acceptance_and_fast_validator_changes_do_not_force_deep_gate(
        self,
    ) -> None:
        deep, paper_ids, deep_paths = select_scope(
            [
                "config/acceptance.yaml",
                "scripts/validate_github_math.py",
                "tests/test_validate_resources.py",
            ]
        )
        self.assertFalse(deep)
        self.assertEqual(paper_ids, [])
        self.assertEqual(deep_paths, [])

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
