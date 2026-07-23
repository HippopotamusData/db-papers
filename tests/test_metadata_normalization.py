from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import papers  # noqa: E402
from project_config import load_yaml_text  # noqa: E402


class MetadataNormalizationTests(unittest.TestCase):
    def test_yaml_duplicate_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate key 'title'"):
            load_yaml_text(
                "title: first\ntitle: second\n",
                "fixture",
            )

    def test_reader_metadata_scalars_must_be_trimmed_single_line(self) -> None:
        self.assertTrue(papers.is_trimmed_single_line("A Paper"))
        for value in (
            "",
            " A Paper",
            "A Paper ",
            "A\nPaper",
            "A\rPaper",
            "A\tPaper",
            "A\x1fPaper",
            "A\x7fPaper",
            "A\u0085Paper",
            "A\u2028Paper",
            "A\u2029Paper",
        ):
            with self.subTest(value=value):
                self.assertFalse(papers.is_trimmed_single_line(value))

    def test_catalog_escapes_link_labels_and_destinations(self) -> None:
        self.assertEqual(
            papers.markdown_link_label(r"A [B] | C"),
            r"A \[B\] \| C",
        )
        self.assertEqual(
            papers.markdown_link_destination("https://example.com/a_(b)<>"),
            "<https://example.com/a_(b)%3C%3E>",
        )

    def test_source_urls_reject_markdown_and_control_boundaries(self) -> None:
        self.assertTrue(papers.is_absolute_http_url("https://example.com/a_(b)"))
        for value in (
            " https://example.com",
            "https://example.com/a b",
            "https://example.com/<unsafe>",
            r"https://example.com\@evil.example/paper",
            "https://example.com:bad/paper",
            "https://[::1/paper",
            "https://reader@example.com/paper",
            "file:///tmp/paper.pdf",
        ):
            with self.subTest(value=value):
                self.assertFalse(papers.is_absolute_http_url(value))

    def test_recent_paper_cannot_claim_maximum_durability(self) -> None:
        rating = {
            "score": 4.5,
            "influence_breadth": 4,
            "technical_value": 5,
            "practical_diffusion": 4,
            "durability": 5,
            "reader_payoff": 4,
        }
        errors: list[str] = []
        path = ROOT / "papers/query-processing/sample/paper.yaml"
        papers.validate_rating(errors, path, rating, 2026, current_year=2026)
        self.assertTrue(any("less than five years" in error for error in errors))

        errors = []
        papers.validate_rating(errors, path, rating, 2021, current_year=2026)
        self.assertEqual(errors, [])

    def test_acceptance_lock_is_shared_by_linked_worktrees(self) -> None:
        common_dir = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="/repository/.git\n",
            stderr="",
        )
        with patch.object(papers.subprocess, "run", return_value=common_dir):
            self.assertEqual(
                papers._acceptance_lock_path(Path("/repository")),
                papers._acceptance_lock_path(Path("/repository-worktree")),
            )


if __name__ == "__main__":
    unittest.main()
