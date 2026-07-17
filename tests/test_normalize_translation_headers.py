from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from normalize_translation_headers import (  # noqa: E402
    TRANSLATOR_NOTE,
    normalize_all,
    normalize_text,
)


class NormalizeTranslationHeadersTests(unittest.TestCase):
    def test_replaces_old_note_and_uses_evidence_backed_title(self) -> None:
        source = (
            "---\npaper_id: sample\n---\n\n"
            "# 自拟中文标题\n\n"
            "Authors A and B\n\n"
            "## 译者说明\n\n"
            "本轮视觉确认了若干页面。\n\n"
            "## 摘要\n\n正文不变。\n"
        )
        normalized = normalize_text(source, "Canonical Paper Title")
        self.assertIn("# Canonical Paper Title（中文译文）", normalized)
        self.assertIn(f"## 译者说明\n\n{TRANSLATOR_NOTE}", normalized)
        self.assertIn("Authors A and B", normalized)
        self.assertIn("## 摘要\n\n正文不变。", normalized)
        self.assertNotIn("本轮视觉确认", normalized)

    def test_is_idempotent(self) -> None:
        source = (
            "---\npaper_id: sample\n---\n\n"
            "# Canonical Paper Title（中文译文）\n\n"
            f"## 译者说明\n\n{TRANSLATOR_NOTE}\n\n"
            "## 摘要\n\n正文。\n"
        )
        self.assertEqual(normalize_text(source, "Canonical Paper Title"), source)

    def test_canonical_note_does_not_consume_following_author_lines(self) -> None:
        source = (
            "---\npaper_id: sample\n---\n\n"
            "# Canonical Paper Title（中文译文）\n\n"
            f"## 译者说明\n\n{TRANSLATOR_NOTE}\n\n"
            "Alice Example、Bob Example\n\nExample University\n\n"
            "## 摘要\n\n正文。\n"
        )
        normalized = normalize_text(source, "Canonical Paper Title")
        self.assertIn("Alice Example、Bob Example", normalized)
        self.assertIn("Example University", normalized)
        self.assertEqual(normalize_text(normalized, "Canonical Paper Title"), normalized)

    def test_fenced_shell_comments_are_not_mistaken_for_headings(self) -> None:
        source = (
            "---\npaper_id: sample\n---\n\n"
            "# Canonical Paper Title（中文译文）\n\n"
            f"## 译者说明\n\n{TRANSLATOR_NOTE}\n\n"
            "## 示例\n\n```sh\n# shell comment\n## still code\necho ok\n```\n"
        )
        normalized = normalize_text(source, "Canonical Paper Title")
        self.assertIn("# shell comment", normalized)
        self.assertIn("## still code", normalized)
        self.assertEqual(normalize_text(normalized, "Canonical Paper Title"), normalized)

    def test_rejects_multiple_h1_headings(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one H1"):
            normalize_text("# One\n\n# Two\n", "Canonical")

    def test_scoped_check_ignores_another_in_progress_translation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "papers/query-processing/sample-paper"
            other = root / "papers/query-processing/other-paper"
            sample.mkdir(parents=True)
            other.mkdir(parents=True)
            for paper, title in ((sample, "Sample"), (other, "Other")):
                (paper / "paper.yaml").write_text(
                    yaml.safe_dump({"title": title}), encoding="utf-8"
                )
            (sample / "translation.md").write_text(
                "# Sample（中文译文）\n\n"
                f"## 译者说明\n\n{TRANSLATOR_NOTE}\n",
                encoding="utf-8",
            )
            (other / "translation.md").write_text(
                "# Other\n\n# In-progress duplicate\n", encoding="utf-8"
            )

            self.assertEqual(
                normalize_all(root, check=True, paper_id="sample-paper"), []
            )
            with self.assertRaisesRegex(ValueError, "exactly one H1"):
                normalize_all(root, check=True)

    def test_translation_template_matches_canonical_header_contract(self) -> None:
        template_path = REPO_ROOT / "templates/translation.md"
        template = template_path.read_text(encoding="utf-8")
        frontmatter, body = template[4:].split("\n---\n", 1)
        title = yaml.safe_load(frontmatter)["title"]
        self.assertEqual(normalize_text(template, title), template)
        self.assertIn(f"## 译者说明\n\n{TRANSLATOR_NOTE}", body)


if __name__ == "__main__":
    unittest.main()
