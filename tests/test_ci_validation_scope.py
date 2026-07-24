from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.ci_validation_scope import (
    changed_acceptance_paper_ids,
    decode_changed_paths,
    emit_github_output,
    select_paper_ids,
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
            emit_github_output(["paper-a", "paper-b"])
        self.assertEqual(
            output.getvalue(),
            "paper_ids<<__DB_PAPERS__\n"
            "paper-a\n"
            "paper-b\n"
            "__DB_PAPERS__\n",
        )

    def test_workflow_never_runs_deep_check(self) -> None:
        workflow = (ROOT / ".github/workflows/check.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("run: make check", workflow)
        self.assertNotIn("make deep-check", workflow)
        self.assertNotIn("deep_check", workflow)


if __name__ == "__main__":
    unittest.main()
