from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.ci_validation_scope import (
    ValidationPlan,
    changed_acceptance_paper_ids,
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
                "papers/query-processing/paper-a/assets/figure-1.png",
                "./papers/query-processing/paper-a/paper.yaml",
                "papers/query-processing/paper-a/notes.txt",
            ]
        )
        self.assertEqual(paper_ids, ["paper-a", "paper-b"])

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

    def test_acceptance_bound_metadata_requires_scoped_gate(self) -> None:
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
        ):
            plan = select_validation_plan(
                [path],
                root=ROOT,
                base_sha="base",
            )
        self.assertEqual(plan.paper_ids, ())
        self.assertEqual(plan.math_files, ())
        self.assertFalse(plan.math_all)
        self.assertTrue(plan.site_changed)

    def test_translation_plan_selects_paper_math_and_site(self) -> None:
        path = "papers/storage/paper-a/translation.md"
        plan = select_validation_plan([path], root=ROOT)
        self.assertEqual(plan.paper_ids, ("paper-a",))
        self.assertEqual(plan.math_files, (path,))
        self.assertFalse(plan.math_all)
        self.assertTrue(plan.site_changed)

    def test_math_profile_change_selects_full_math_only(self) -> None:
        plan = select_validation_plan(
            ["scripts/verify_math_rendering.py"],
            root=ROOT,
        )
        self.assertEqual(plan.paper_ids, ())
        self.assertEqual(plan.math_files, ())
        self.assertTrue(plan.math_all)
        self.assertFalse(plan.site_changed)

    def test_docs_change_selects_no_validation_domain(self) -> None:
        plan = select_validation_plan(
            ["README.md", "docs/workflows/maintain.md"],
            root=ROOT,
        )
        self.assertEqual(plan, ValidationPlan())

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
        paper_ids = select_paper_ids(
            ["config/acceptance.yaml"],
            acceptance_base=base,
            acceptance_head=head,
        )
        self.assertEqual(paper_ids, ["paper-a", "paper-c"])

    def test_review_snapshot_changes_are_rejected(self) -> None:
        base = {
            "schema_version": 5,
            "review_snapshots": {"old": {}},
            "entries": {"paper-a": {"fingerprint": "a"}},
        }
        head = {
            "schema_version": 5,
            "review_snapshots": {"old": {}, "new": {}},
            "entries": {"paper-a": {"fingerprint": "changed"}},
        }
        with self.assertRaises(ValueError):
            changed_acceptance_paper_ids(base, head)

    def test_acceptance_schema_or_top_level_change_is_rejected(self) -> None:
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
            {"schema_version": 5, "review_snapshots": [], "entries": {}},
        )
        for head in unsafe_heads:
            with self.subTest(head=head):
                with self.assertRaises(ValueError):
                    select_paper_ids(
                        ["config/acceptance.yaml"],
                        acceptance_base=valid,
                        acceptance_head=head,
                    )

    def test_acceptance_change_without_trusted_ledgers_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            select_paper_ids(["config/acceptance.yaml"])

    def test_acceptance_diff_rejects_invalid_entry_shapes(self) -> None:
        with self.assertRaises(ValueError):
            changed_acceptance_paper_ids(
                {"schema_version": 5, "review_snapshots": {}, "entries": {}},
                {
                    "schema_version": 5,
                    "review_snapshots": {},
                    "entries": {"paper-a": "not-a-receipt"},
                },
            )

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
            "site_changed=true\n",
        )

    def test_workflow_uses_minimal_domains_and_never_runs_deep_check(
        self,
    ) -> None:
        workflow = (ROOT / ".github/workflows/check.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("branches: [main]", workflow)
        self.assertIn("run: make check", workflow)
        self.assertIn("Run scoped paper gates", workflow)
        self.assertIn("Run scoped math gate", workflow)
        self.assertNotIn("make deep-check", workflow)
        self.assertNotIn("deep_check", workflow)

    def test_pages_workflow_skips_build_for_unaffected_changes(self) -> None:
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Determine site impact", workflow)
        self.assertIn(
            "if: steps.scope.outputs.site_changed == 'true'",
            workflow,
        )
        self.assertIn(
            "needs.site-build.outputs.site_changed == 'true'",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
