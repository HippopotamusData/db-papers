from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fix_portable_math  # noqa: E402
from fix_portable_math import safe_fix_text  # noqa: E402


class FixPortableMathTests(unittest.TestCase):
    def test_fixes_boundary_without_changing_tex(self) -> None:
        source = r"中文，$\{a\_b < c\}\;\#1$。"
        expected = r"中文， $\{a\_b < c\}\;\#1$。"
        self.assertEqual(safe_fix_text(source), expected)

    def test_does_not_guess_at_display_or_fence_repairs(self) -> None:
        source = "```math\nx<y\n```\n\n> $$z>0$$\n"
        self.assertEqual(safe_fix_text(source), source)

    def test_does_not_change_code(self) -> None:
        source = """`中文$x$`

- ```text
  中文，$y$
  $$
  keep
  $$
  ```

<pre>
中文，$z$
</pre>
"""
        self.assertEqual(safe_fix_text(source), source)

    def test_is_idempotent(self) -> None:
        source = "中文，$x<y$。\n"
        fixed = safe_fix_text(source)
        self.assertEqual(safe_fix_text(fixed), fixed)

    def test_does_not_rewrite_tex_payload(self) -> None:
        source = r"值 $M^{valid}_{a_i}*\text{selectivity}$。"
        self.assertEqual(safe_fix_text(source), source)

    def test_does_not_move_or_repair_ambiguous_blocks(self) -> None:
        for source in (
            "- item\n\n  $$\n  x=1\n  $$\n",
            "```math\nx=1\n",
            "intro\n  $$\n  keep\n  also\ntail\n",
            "$$x$$",
        ):
            with self.subTest(source=source):
                self.assertEqual(safe_fix_text(source), source)

    def test_does_not_move_footnotes_or_remove_italics(self) -> None:
        source = "text[^a]\n\n前 *中，$x$ 中* 后\n\n[^a]: note，$y$\n"
        self.assertEqual(safe_fix_text(source), source)

    def test_does_not_break_markdown_emphasis_or_identifiers(self) -> None:
        for source in ("**$x$**", "*$x$*", "Top-$k$", "F1@$k$"):
            with self.subTest(source=source):
                self.assertEqual(safe_fix_text(source), source)

    def test_safety_assertion_rejects_visible_token_splits(self) -> None:
        for source in ("F1@$k$", "Top-$k$", "**$x$-label**"):
            with self.subTest(source=source):
                opening = source.index("$")
                fixed = source[:opening] + " " + source[opening:]
                with self.assertRaisesRegex(
                    ValueError, "split a visible label or detach emphasis"
                ):
                    fix_portable_math._assert_safe(
                        source, fixed, [(opening, " ")]
                    )

    def test_does_not_guess_after_unicode_symbols_or_fullwidth_open_paren(self) -> None:
        for source in ("参数（$x$）", "α$x$", "∈$S$", "😀$z$"):
            with self.subTest(source=source):
                self.assertEqual(safe_fix_text(source), source)

    def test_code_span_dollar_does_not_remove_italics(self) -> None:
        source = "*caption with `US$` price*\n"
        self.assertEqual(safe_fix_text(source), source)

    def test_does_not_edit_html_attributes_or_link_titles(self) -> None:
        sources = (
            '<span title="中文，$x$">label</span>\n',
            '[link](https://e.test/ "title (中文，$x$")\n',
            '[id]: https://e.test/\n  "中文，$x$"\n',
            '> [id]: https://e.test/\n>   "中文，$x$"\n',
            '1. [id]: https://e.test/\n   "中文，$x$"\n',
            '- [^a]: note，$x$\n',
        )
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(safe_fix_text(source), source)

    def test_cli_check_is_read_only_and_fix_requires_safe_flag(self) -> None:
        script = ROOT / "scripts" / "fix_portable_math.py"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "translation.md"
            original = "中文，$x$。\n"
            fixed = "中文， $x$。\n"
            path.write_text(original, encoding="utf-8")

            check = subprocess.run(
                [sys.executable, str(script), "check", str(path)],
                capture_output=True,
                check=False,
                text=True,
            )
            unsafe_fix = subprocess.run(
                [sys.executable, str(script), "fix", str(path)],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(check.returncode, 1)
            self.assertIn(str(path), check.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertNotEqual(unsafe_fix.returncode, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

            safe_fix = subprocess.run(
                [sys.executable, str(script), "fix", "--safe", str(path)],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(safe_fix.returncode, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), fixed)

    def test_batch_write_failure_rolls_back_replaced_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.md"
            second = Path(directory) / "second.md"
            first.write_text("中文，$x$。\n", encoding="utf-8")
            second.write_text("中文，$y$。\n", encoding="utf-8")
            planned = [
                (first, "中文，$x$。\n", "中文， $x$。\n"),
                (second, "中文，$y$。\n", "中文， $y$。\n"),
            ]
            real_replace = os.replace
            calls = 0

            def fail_second_replace(source: Path, target: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated replacement failure")
                real_replace(source, target)

            with mock.patch.object(
                fix_portable_math.os, "replace", side_effect=fail_second_replace
            ):
                with self.assertRaisesRegex(OSError, "simulated replacement failure"):
                    fix_portable_math._commit_planned(planned)

            self.assertEqual(first.read_text(encoding="utf-8"), planned[0][1])
            self.assertEqual(second.read_text(encoding="utf-8"), planned[1][1])
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])

    def test_batch_rejects_symlink_and_concurrent_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.md"
            second = Path(directory) / "second.md"
            link = Path(directory) / "link.md"
            first.write_text("中文，$x$。\n", encoding="utf-8")
            second.write_text("中文，$y$。\n", encoding="utf-8")
            link.symlink_to(first)

            with self.assertRaisesRegex(OSError, "symlink"):
                fix_portable_math._commit_planned(
                    [(link, first.read_text(encoding="utf-8"), "changed\n")]
                )
            self.assertTrue(link.is_symlink())

            second.write_text("user update\n", encoding="utf-8")
            planned = [
                (first, "中文，$x$。\n", "中文， $x$。\n"),
                (second, "中文，$y$。\n", "中文， $y$。\n"),
            ]
            with self.assertRaisesRegex(OSError, "target changed after planning"):
                fix_portable_math._commit_planned(planned)
            self.assertEqual(first.read_text(encoding="utf-8"), planned[0][1])
            self.assertEqual(second.read_text(encoding="utf-8"), "user update\n")

    def test_batch_rollback_preserves_edit_after_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.md"
            second = Path(directory) / "second.md"
            first.write_text("中文，$x$。\n", encoding="utf-8")
            second.write_text("中文，$y$。\n", encoding="utf-8")
            planned = [
                (first, "中文，$x$。\n", "中文， $x$。\n"),
                (second, "中文，$y$。\n", "中文， $y$。\n"),
            ]
            real_replace = os.replace
            calls = 0

            def edit_then_fail(source: Path, target: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    first.write_text("user update after replacement\n", encoding="utf-8")
                    raise OSError("simulated replacement failure")
                real_replace(source, target)

            with mock.patch.object(
                fix_portable_math.os, "replace", side_effect=edit_then_fail
            ):
                with self.assertRaisesRegex(
                    OSError, "concurrent edit preserved; rollback incomplete"
                ):
                    fix_portable_math._commit_planned(planned)

            self.assertEqual(
                first.read_text(encoding="utf-8"), "user update after replacement\n"
            )
            self.assertEqual(second.read_text(encoding="utf-8"), planned[1][1])
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
