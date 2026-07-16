from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_github_math import MathExpression  # noqa: E402
from verify_math_rendering import (  # noqa: E402
    _github_sequence_failures,
    _load_expressions,
    _normalized_actual_renderer_text,
    _normalized_expected_renderer_text,
    _verify_mathjax,
)


class VerifyMathRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mathjax = ROOT / "node_modules" / "mathjax"
        if not cls.mathjax.exists():
            raise RuntimeError("MathJax test dependency is missing; run npm ci")

    def test_mathjax_accepts_well_formed_tex(self) -> None:
        expressions = [
            {
                "path": "ok.md",
                "line": 1,
                "text": r"x_i^2 + \frac{1}{2}",
                "display": False,
            },
            {
                "path": "ok.md",
                "line": 2,
                "text": r"\begin{aligned}x&=1\\y&=2\end{aligned}",
                "display": True,
            },
        ]
        self.assertEqual(_verify_mathjax(expressions, self.mathjax), [])

    def test_mathjax_rejects_structurally_invalid_tex(self) -> None:
        expressions = [
            {"path": "bad.md", "line": 3, "text": r"x^{1", "display": False},
            {"path": "bad.md", "line": 4, "text": r"\frac{1}", "display": False},
            {"path": "bad.md", "line": 5, "text": r"\left(x", "display": False},
        ]
        failures = _verify_mathjax(expressions, self.mathjax)
        self.assertEqual(len(failures), 3)
        self.assertTrue(all("MathJax:" in failure for failure in failures))

    def test_github_sequence_diff_locates_the_missing_duplicate(self) -> None:
        text = "$a$\n$x$\n$x$\n$y$\n"
        expressions = [
            MathExpression(0, "a", False),
            MathExpression(4, "x", False),
            MathExpression(8, "x", False),
            MathExpression(12, "y", False),
        ]
        failures = _github_sequence_failures(
            Path("paper.md"),
            text,
            expressions,
            ["$a$", "$x$", "$x$", "$y$"],
            ["$a$", "$x$", "$y$"],
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("paper.md:3", failures[0])
        self.assertIn("occurrence 3", failures[0])

    def test_github_comparison_does_not_hide_entity_rewrites(self) -> None:
        text = "$x&#X2B;y$\n"
        expression = MathExpression(0, "x&#X2B;y", False)
        failures = _github_sequence_failures(
            Path("paper.md"),
            text,
            [expression],
            [_normalized_expected_renderer_text(expression)],
            [_normalized_actual_renderer_text("$x+y$")],
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("rewrote math renderer", failures[0])

    def test_github_actual_html_decoding_preserves_raw_alignment(self) -> None:
        expression = MathExpression(0, "x&=y", False)
        self.assertEqual(
            _normalized_expected_renderer_text(expression),
            _normalized_actual_renderer_text("$x&amp;amp;=y$"),
        )

    def test_github_expected_payload_consumes_one_literal_escape(self) -> None:
        expression = MathExpression(0, r"l\\_partkey=5\\%,serial\\#", False)
        self.assertEqual(
            _normalized_expected_renderer_text(expression),
            r"$l\_partkey=5\%,serial\#$",
        )

    def test_loader_sends_github_payload_to_local_mathjax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "translation.md"
            path.write_text(r"正文 $l\\_partkey=5\\%,serial\\#$。", encoding="utf-8")
            serialized, _ = _load_expressions([path])
            self.assertEqual(serialized[0]["text"], r"l\_partkey=5\%,serial\#")
            self.assertEqual(_verify_mathjax(serialized, self.mathjax), [])

    def test_unchecked_loader_uses_only_trusted_dollar_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "translation.md"
            path.write_text(r"正文 $x\notARealCommand$。", encoding="utf-8")
            with self.assertRaises(ValueError):
                _load_expressions([path])
            serialized, _ = _load_expressions([path], validate=False)
            self.assertEqual(serialized[0]["text"], r"x\notARealCommand")

            for invalid in ("正文 $x。", "正文\n$$\nx=1\n"):
                with self.subTest(invalid=invalid):
                    path.write_text(invalid, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "boundary validation"):
                        _load_expressions([path], validate=False)

    def test_loader_rejects_symlink_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.md"
            link = Path(directory) / "translation.md"
            target.write_text("正文 $x$。", encoding="utf-8")
            link.symlink_to(target)
            with self.assertRaisesRegex(OSError, "symlink"):
                _load_expressions([link], validate=False)


if __name__ == "__main__":
    unittest.main()
