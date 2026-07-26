from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.ci_validation_scope import (
    ValidationPlan,
    decode_changed_paths,
    emit_github_output,
    paper_metadata_requires_scoped_gate,
    select_paper_ids,
    select_validation_plan,
)

ROOT = Path(__file__).resolve().parents[1]


class CiValidationScopeTests(unittest.TestCase):
    def test_docs_and_catalog_changes_select_no_papers(self) -> None:
        paper_ids = select_paper_ids(
            ["README.md", "CATALOG.md", "docs/workflows/metadata.md"]
        )
        self.assertEqual(paper_ids, [])

    def test_paper_changes_select_only_affected_papers(self) -> None:
        paper_ids = select_paper_ids(
            [
                "papers/storage/paper-b/translation.md",
                "papers/storage/paper-c/source.pdf",
                "papers/query-processing/paper-a/assets/figure-1.png",
                "./papers/query-processing/paper-a/paper.yaml",
                "papers/query-processing/paper-a/notes.txt",
            ]
        )
        self.assertEqual(paper_ids, ["paper-a", "paper-b", "paper-c"])

    def test_nul_delimited_paths_preserve_unicode_and_newlines(self) -> None:
        changed_paths = decode_changed_paths(
            "papers/query-processing/paper-a/assets/图\n1.png\0"
            "README.md\0".encode()
        )
        self.assertEqual(
            select_paper_ids(changed_paths),
            ["paper-a"],
        )

    def test_non_paper_implementation_changes_select_no_papers(self) -> None:
        paper_ids = select_paper_ids(
            [
                "Makefile",
                "scripts/ci_validation_scope.py",
                "scripts/validate_github_math.py",
                "tests/test_validate_resources.py",
            ]
        )
        self.assertEqual(paper_ids, [])

    def test_reader_only_metadata_fields_do_not_require_scoped_gate(self) -> None:
        base = {
            "title": "Original",
            "title_zh": "旧标题",
            "topics": ["query-optimization"],
            "rating": {"score": 4.0},
            "authors": ["Author"],
        }
        for field, value in (
            ("title_zh", "新标题"),
            ("topics", ["query-compilation"]),
            ("rating", {"score": 4.5}),
        ):
            with self.subTest(field=field):
                head = {**base, field: value}
                self.assertFalse(
                    paper_metadata_requires_scoped_gate(base, head)
                )

    def test_publication_bound_metadata_requires_scoped_gate(self) -> None:
        base = {
            "title": "Original",
            "title_zh": "中文标题",
            "authors": ["Author"],
            "reading_status": "translated",
        }
        for field, value in (
            ("title", "Changed"),
            ("authors", ["Other"]),
            ("reading_status", "draft"),
        ):
            with self.subTest(field=field):
                head = {**base, field: value}
                self.assertTrue(
                    paper_metadata_requires_scoped_gate(base, head)
                )

    def test_reader_only_metadata_plan_runs_site_but_not_paper_gate(self) -> None:
        path = "papers/query-processing/paper-a/paper.yaml"
        base = {
            "title": "Original",
            "title_zh": "旧标题",
            "authors": ["Author"],
        }
        head = {**base, "title_zh": "新标题"}
        with mock.patch(
            "scripts.ci_validation_scope.yaml_at_revision",
            side_effect=[base, head],
        ) as load_yaml:
            plan = select_validation_plan(
                [path],
                root=ROOT,
                base_sha="base",
                head_sha="proposed",
            )
        self.assertEqual(
            load_yaml.call_args_list,
            [
                mock.call(ROOT, "base", path, missing_ok=True),
                mock.call(ROOT, "proposed", path, missing_ok=True),
            ],
        )
        self.assertEqual(plan.paper_ids, ())
        self.assertEqual(plan.math_files, ())
        self.assertFalse(plan.math_all)
        self.assertFalse(plan.deep_validate_all)
        self.assertTrue(plan.site_changed)

    def test_paper_metadata_change_requires_trusted_base(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "paper metadata changes require a trusted --base-sha",
        ):
            select_validation_plan(
                ["papers/storage/paper-a/paper.yaml"],
                root=ROOT,
            )

    def test_translation_plan_selects_paper_math_and_site(self) -> None:
        path = "papers/storage/paper-a/translation.md"
        plan = select_validation_plan([path], root=ROOT)
        self.assertEqual(plan.paper_ids, ("paper-a",))
        self.assertEqual(plan.math_files, (path,))
        self.assertFalse(plan.math_all)
        self.assertFalse(plan.deep_validate_all)
        self.assertTrue(plan.site_changed)

    def test_math_profile_change_selects_full_math_only(self) -> None:
        plan = select_validation_plan(
            ["scripts/verify_math_rendering.py"],
            root=ROOT,
        )
        self.assertEqual(plan.paper_ids, ())
        self.assertEqual(plan.math_files, ())
        self.assertTrue(plan.math_all)
        self.assertFalse(plan.deep_validate_all)
        self.assertFalse(plan.site_changed)

    def test_global_validator_and_policy_changes_select_deep_validation(
        self,
    ) -> None:
        for path in (
            "config/policy.yaml",
            "scripts/papers.py",
            "scripts/pdf_metrics.py",
            "scripts/project_config.py",
            "scripts/validate_resources.py",
            "scripts/validate_translations.sh",
        ):
            with self.subTest(path=path):
                plan = select_validation_plan([path], root=ROOT)
                self.assertTrue(plan.deep_validate_all)

    def test_makefile_change_selects_all_implementation_domains(self) -> None:
        plan = select_validation_plan(["Makefile"], root=ROOT)
        self.assertTrue(plan.math_all)
        self.assertTrue(plan.deep_validate_all)
        self.assertTrue(plan.site_changed)

    def test_dev_dependency_change_selects_math_and_deep_validation(
        self,
    ) -> None:
        with mock.patch(
            "scripts.ci_validation_scope.pyproject_groups_at_revision",
            side_effect=[
                (["markdown-it-py==4.2.0"], ["zensical==0.0.24"]),
                (["markdown-it-py==4.3.0"], ["zensical==0.0.24"]),
            ],
        ):
            plan = select_validation_plan(
                ["pyproject.toml"],
                root=ROOT,
                base_sha="base",
                head_sha="proposed",
            )
        self.assertTrue(plan.math_all)
        self.assertTrue(plan.deep_validate_all)
        self.assertFalse(plan.site_changed)

    def test_docs_change_selects_no_validation_domain(self) -> None:
        plan = select_validation_plan(
            ["README.md", "docs/workflows/maintain.md"],
            root=ROOT,
        )
        self.assertEqual(plan, ValidationPlan())

    def test_github_output_is_deterministic(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            emit_github_output(
                ValidationPlan(
                    paper_ids=("paper-a", "paper-b"),
                    math_files=(
                        "papers/query-processing/paper-a/translation.md",
                    ),
                    site_changed=True,
                )
            )
        self.assertEqual(
            output.getvalue(),
            "paper_ids<<__DB_PAPERS__\n"
            "paper-a\n"
            "paper-b\n"
            "__DB_PAPERS__\n"
            "math_files<<__DB_PAPERS__\n"
            "papers/query-processing/paper-a/translation.md\n"
            "__DB_PAPERS__\n"
            "math_all=false\n"
            "deep_validate_all=false\n"
            "site_changed=true\n",
        )

    def test_workflow_uses_minimal_domains_and_conditional_deep_validation(
        self,
    ) -> None:
        workflow = (ROOT / ".github/workflows/check.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("branches: [main]", workflow)
        self.assertIn("run: make check", workflow)
        self.assertIn("Run scoped paper gates", workflow)
        self.assertIn("Run scoped math gate", workflow)
        self.assertIn("Run global deep validation", workflow)
        self.assertIn(
            "steps.scope.outputs.deep_validate_all == 'true'",
            workflow,
        )
        self.assertIn("run: make deep-validate", workflow)
        self.assertIn("Audit changed GitHub math", workflow)
        self.assertIn(
            'git merge-base --is-ancestor "$BEFORE_SHA" "$CURRENT_SHA"',
            workflow,
        )
        self.assertIn(
            'scripts/audit_changed_math.sh "$DIFF_BASE"',
            workflow,
        )
        self.assertIn(
            "AUDIT_ALL: ${{ steps.scope.outputs.math_all }}",
            workflow,
        )
        self.assertIn("run: make bootstrap", workflow)
        self.assertIn(
            ".venv/bin/python scripts/ci_validation_scope.py",
            workflow,
        )
        self.assertIn(
            "PYTHON=.venv/bin/python scripts/audit_changed_math.sh",
            workflow,
        )
        self.assertNotIn("name: Install Python dependencies", workflow)
        self.assertNotIn("name: Install MathJax", workflow)
        self.assertNotIn("make deep-check", workflow)
        self.assertNotIn("workflow_dispatch", workflow)

    def test_pages_workflow_separates_pr_and_full_production_builds(
        self,
    ) -> None:
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Determine site impact", workflow)
        self.assertIn(
            "Successful main check: forcing a complete production build",
            workflow,
        )
        self.assertIn(
            "if: steps.scope.outputs.site_changed == 'true'",
            workflow,
        )
        self.assertIn(
            "needs.site-build.result == 'success'",
            workflow,
        )
        self.assertIn("format('ignored-{0}', github.run_id)", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("run: make bootstrap-site", workflow)
        self.assertIn("run: make site-check", workflow)
        self.assertNotIn("run: make site-check PYTHON=python", workflow)
        self.assertNotIn('git rev-parse "$CURRENT_SHA^"', workflow)
        self.assertNotIn("workflow_dispatch", workflow)


if __name__ == "__main__":
    unittest.main()
