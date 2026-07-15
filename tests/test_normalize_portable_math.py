from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from normalize_portable_math import normalize_text  # noqa: E402


class NormalizePortableMathTests(unittest.TestCase):
    def test_normalizes_boundary_and_markdown_sensitive_tex(self) -> None:
        source = r"中文，$\{a\_b < c\}\;\#1$。"
        expected = r'中文， $\lbrace{}a\char"005F{}b \lt{} c\rbrace{}\thickspace{}\char"0023{}1$。'
        self.assertEqual(normalize_text(source), expected)

    def test_converts_math_fence_and_same_line_display(self) -> None:
        source = "```math\nx<y\n```\n\n> $$z>0$$\n"
        expected = "$$\nx\\lt{}y\n$$\n\n> $$\n> z\\gt{}0\n> $$\n"
        self.assertEqual(normalize_text(source), expected)

    def test_does_not_change_code(self) -> None:
        source = "`中文$x$`\n\n```text\n中文$y$ x<y\n```\n"
        self.assertEqual(normalize_text(source), source)

    def test_is_idempotent(self) -> None:
        source = "中文，$x<y$。\n"
        normalized = normalize_text(source)
        self.assertEqual(normalize_text(normalized), normalized)

    def test_normalizes_markdown_emphasis_tokens_and_github_select_token(self) -> None:
        source = r"值 $M^{valid}_{a_i}*\text{selectivity}$。"
        expected = r"值 $M^{valid}\relax_{a_i}\ast{}\text{selec{}tivity}$。"
        self.assertEqual(normalize_text(source), expected)

    def test_outdents_list_display_math(self) -> None:
        source = "- item\n\n  $$\n  x=1\n  $$\n"
        expected = "- item\n\n$$\nx=1\n$$\n"
        self.assertEqual(normalize_text(source), expected)

    def test_moves_math_out_of_footnote_and_italic_containers(self) -> None:
        source = "text[^a]\n\n*caption $x$*\n\n[^a]: note $y$\n"
        expected = "text（注：note $y$）\n\ncaption $x$\n\n"
        self.assertEqual(normalize_text(source), expected)


if __name__ == "__main__":
    unittest.main()
