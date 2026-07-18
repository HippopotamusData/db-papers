from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from markdown_visibility import reader_visible_markdown  # noqa: E402


class MarkdownVisibilityTests(unittest.TestCase):
    def test_html_comments_are_masked_without_moving_offsets(self) -> None:
        text = "可见。\n<!-- 隐藏\n内容 -->\n仍可见。\n"
        visible = reader_visible_markdown(text)
        self.assertEqual(len(visible), len(text))
        self.assertEqual(visible.count("\n"), text.count("\n"))
        self.assertNotIn("隐藏", visible)
        self.assertNotIn("内容", visible)
        self.assertIn("可见", visible)

    def test_unclosed_html_comment_is_hidden_through_end_of_file(self) -> None:
        text = "visible\n<!-- hidden\nstill hidden\n"
        visible = reader_visible_markdown(text)
        self.assertEqual(visible.splitlines()[0], "visible")
        self.assertNotIn("hidden", visible)

    def test_comment_syntax_inside_code_remains_reader_visible(self) -> None:
        text = (
            "Inline `<!-- literal -->` code.\n\n"
            "```html\n<!-- fenced literal -->\n```\n\n"
            "    <!-- indented literal -->\n"
        )
        self.assertEqual(reader_visible_markdown(text), text)

    def test_protected_comment_opener_does_not_hide_a_later_real_comment(
        self,
    ) -> None:
        text = "`<!--` visible <!-- hidden --> tail\n"
        visible = reader_visible_markdown(text)
        self.assertIn("`<!--` visible", visible)
        self.assertNotIn("hidden", visible)
        self.assertIn("tail", visible)

    def test_backticks_hidden_in_separate_comments_cannot_form_code(self) -> None:
        text = (
            "<!-- `a --> visible "
            "<!-- 隐藏中文内容用于虚增覆盖率` --> tail\n"
        )
        visible = reader_visible_markdown(text)
        self.assertEqual(len(visible), len(text))
        self.assertIn("visible", visible)
        self.assertIn("tail", visible)
        self.assertNotIn("隐藏", visible)
        self.assertNotIn("虚增", visible)

    def test_code_span_opened_before_comment_syntax_keeps_it_literal(self) -> None:
        text = "`prefix <!-- literal --> suffix` visible\n"
        self.assertEqual(reader_visible_markdown(text), text)

    def test_comment_hides_complete_code_span_inside_it(self) -> None:
        text = "<!-- hidden `literal` content --> visible\n"
        visible = reader_visible_markdown(text)
        self.assertNotIn("hidden", visible)
        self.assertNotIn("literal", visible)
        self.assertIn("visible", visible)

    def test_raw_html_comment_block_hides_trailing_markdown_on_same_line(
        self,
    ) -> None:
        text = "<!-- hidden --> ![图 1](assets/hidden.png)\n"
        visible = reader_visible_markdown(text)
        self.assertEqual(len(visible), len(text))
        self.assertEqual(visible.count("\n"), text.count("\n"))
        self.assertNotIn("![图 1]", visible)

    def test_inline_comment_keeps_trailing_markdown_reader_visible(self) -> None:
        text = "visible <!-- hidden --> ![图 1](assets/visible.png)\n"
        visible = reader_visible_markdown(text)
        self.assertIn("visible", visible)
        self.assertNotIn("hidden", visible)
        self.assertIn("![图 1](assets/visible.png)", visible)


if __name__ == "__main__":
    unittest.main()
