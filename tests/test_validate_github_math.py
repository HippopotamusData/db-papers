from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_github_math import extract_math_expressions, validate_text  # noqa: E402


class ValidateGithubMathTests(unittest.TestCase):
    def codes(self, text: str) -> list[str]:
        return [issue.code for issue in validate_text(text)]

    def test_accepts_portable_math_forms(self) -> None:
        text = r"""行内公式 $\min_i x_i$。
ASCII 标点后的公式 ($x$) 也可移植。

$$
f(x)=\mathrm{Cost}(x)
$$

> $$
> \begin{aligned}
> x &= 1 \\
> y &= 2
> \end{aligned}
> $$
"""
        self.assertEqual(self.codes(text), [])

    def test_accepts_literal_dollar_and_named_markdown_sensitive_symbols(self) -> None:
        text = r"""费用为 \$5；公式 $\lbrace x \lt y \rbrace$。

$$
a\thickspace b \\ [2pt]
c\Vert d
$$
"""
        self.assertEqual(self.codes(text), [])

    def test_rejects_inline_math_after_unsafe_boundary(self) -> None:
        text = r"""中文$x$。
中文逗号，$y$。
（$z$）
Top-$k$，F1@$n$。
"""
        self.assertEqual(
            self.codes(text),
            ["GHM005", "GHM005", "GHM005", "GHM005", "GHM005"],
        )

    def test_rejects_inline_math_before_ascii_identifier(self) -> None:
        self.assertEqual(self.codes(r"算法 $k$NN。"), ["GHM005"])

    def test_rejects_non_space_opening_boundaries_but_accepts_ascii_paren(self) -> None:
        text = "逗号,$x$；冒号:$y$；制表符\t$z$；括号 ($w$)。\n"
        self.assertEqual(self.codes(text), ["GHM005", "GHM005", "GHM005"])

    def test_rejects_github_only_inline_math(self) -> None:
        self.assertEqual(self.codes(r"中文$`x`$。"), ["GHM006"])

    def test_rejects_fenced_math(self) -> None:
        text = r"""```math
\begin{aligned}
x &= 1 \\
y &= 2
\end{aligned}
```
"""
        self.assertEqual(self.codes(text), ["GHM004"])

    def test_ignores_nested_fenced_and_indented_code(self) -> None:
        text = r"""> ```text
> 中文$x$，\operatorname{x}
> ```

    中文$y$，\operatorname{y}
"""
        self.assertEqual(self.codes(text), [])

    def test_ignores_list_fences_equivalent_blockquote_closers_and_html_code(self) -> None:
        text = r"""- ```text
  中文，$x$
  ```

> ```text
> literal $y$
>```

<pre>
中文，$z$
</pre>

正文，$w$。
"""
        self.assertEqual(self.codes(text), ["GHM005"])

    def test_ignores_link_destinations_titles_and_reference_definitions(self) -> None:
        text = "[link](https://example.test/$value \"title (中文，$x$\") and $y$\n\n> [id]: https://example.test/$value\n>   \"中文，$z$\"\n\n1. [two]: https://e.test/\n   \"中文，$w$\"\n"
        self.assertEqual(self.codes(text), [])

    def test_does_not_mask_parentheses_without_a_link_label(self) -> None:
        self.assertEqual(
            self.codes("literal](not-link 中文，$x$)\n"),
            ["GHM005"],
        )

    def test_rejects_operatorname(self) -> None:
        issues = validate_text(r"$\operatorname{Cost}(x)$")
        self.assertEqual([issue.code for issue in issues], ["GHM001"])
        self.assertIn(r"\mathrm{Name}", issues[0].message)

    def test_rejects_known_undefined_custom_join_commands(self) -> None:
        text = r"正文 $A\fullouterjoin B$ 与 $A\leftouterjoin B$。"
        self.assertEqual(self.codes(text), ["GHM013", "GHM013"])

    def test_rejects_commands_outside_verified_profile(self) -> None:
        self.assertEqual(self.codes(r"正文 $\notARealCommand{x}$。"), ["GHM013"])

    def test_rejects_non_ascii_control_sequences(self) -> None:
        self.assertEqual(
            self.codes("正文 $\\不存在{x}$ 与 $\\é{x}$。"),
            ["GHM013", "GHM013"],
        )

    def test_rejects_unknown_or_malformed_environments(self) -> None:
        text = "$$\n\\begin{matrix}x\\end{matrix}\n$$\n\n正文 $\\begin x$。\n"
        self.assertEqual(
            self.codes(text), ["GHM020", "GHM020", "GHM020", "GHM020"]
        )

    def test_rejects_environment_inside_inline_math(self) -> None:
        text = r"正文 $\begin{aligned}x&=1\end{aligned}$。"
        self.assertEqual(self.codes(text), ["GHM020", "GHM020"])

    def test_rejects_contextually_invalid_tag_and_char(self) -> None:
        text = r'正文 $x\tag{1}$、 $\char{nonsense}$ 与 $\char"10FFFF{}$。'
        self.assertEqual(self.codes(text), ["GHM020", "GHM020", "GHM020"])

    def test_rejects_raw_tex_comment_character(self) -> None:
        self.assertEqual(self.codes(r"正文 $x%+y$。"), ["GHM023"])

    def test_rejects_tex_style_math_delimiters(self) -> None:
        self.assertEqual(
            self.codes(r"行内 \(x\)，块级 \[y\]。"),
            ["GHM002", "GHM002", "GHM002", "GHM002"],
        )

    def test_does_not_match_delimiter_or_command_prefixes(self) -> None:
        self.assertEqual(
            self.codes(r"行内 $\\(x)+\operatornames{x}$。"),
            ["GHM009", "GHM013"],
        )

    def test_rejects_macro_configuration(self) -> None:
        text = "$$\n\\newcommand{\\cost}{\\mathrm{cost}}\\cost(x)\n$$\n"
        self.assertEqual(self.codes(text), ["GHM003"])

    def test_checks_math_fence_contents(self) -> None:
        text = "```math\n\\operatorname{Cost}(x)\n```\n"
        self.assertEqual(self.codes(text), ["GHM004"])

    def test_ignores_literal_examples_in_code(self) -> None:
        text = r"""普通代码 `\operatorname{x}` 与 `\(x\)`。

``字面 `$`x`$` 仍是代码``。

跨行代码 `中文$x$
仍在代码中`。

```tex-example
\operatorname{x}
\[x\]
```
"""
        self.assertEqual(self.codes(text), [])

    def test_rejects_unsupported_math_fence_names(self) -> None:
        text = "```latex\nx=1\n```\n\n~~~math\ny=2\n~~~\n"
        self.assertEqual(self.codes(text), ["GHM004", "GHM004"])

    def test_rejects_non_standalone_and_unbalanced_delimiters(self) -> None:
        text = "$$x=1$$\n\ninline $x\n"
        self.assertEqual(self.codes(text), ["GHM007", "GHM008"])

    def test_rejects_empty_inline_and_display_math(self) -> None:
        text = "$ $\n\n$$\n$$\n"
        self.assertEqual(self.codes(text), ["GHM008", "GHM008"])

    def test_rejects_mismatched_display_container(self) -> None:
        text = "> $$\n> x=1\n$$\n"
        self.assertEqual(self.codes(text), ["GHM008", "GHM008"])

    def test_accepts_consistent_blockquote_display(self) -> None:
        text = "> $$\n> x=1\n> $$\n"
        self.assertEqual(self.codes(text), [])

    def test_accepts_equivalent_blockquote_display_spacing(self) -> None:
        text = ">$$\n>  x=1\n>   $$\n"
        self.assertEqual(self.codes(text), [])

    def test_rejects_list_marker_and_list_indented_same_line_display(self) -> None:
        text = "- $$\n\n    $$x$$\n"
        self.assertEqual(self.codes(text), ["GHM007", "GHM007"])

    def test_rejects_double_escaped_command(self) -> None:
        self.assertEqual(self.codes(r"行内 $\\Delta_S$。"), ["GHM009"])

    def test_rejects_markdown_consumed_tex_escapes_and_html_chars(self) -> None:
        text = r"行内 $a\_b + \{x\} + x<y$。"
        self.assertEqual(
            self.codes(text),
            ["GHM010", "GHM010", "GHM010", "GHM011"],
        )

    def test_rejects_raw_pipe_only_in_markdown_table_math(self) -> None:
        text = "| 名称 | 范围 |\n| --- | --- |\n| D | $0\\sim|D|$ |\n\n正文 $|D|$。\n"
        self.assertEqual(self.codes(text), ["GHM012", "GHM012"])

    def test_rejects_table_math_without_outer_pipes(self) -> None:
        text = "名称 | 范围\n--- | ---\nD | $|D|$\n"
        self.assertEqual(self.codes(text), ["GHM012", "GHM012"])

    def test_pipe_row_without_delimiter_is_not_a_table(self) -> None:
        self.assertEqual(self.codes("名称 | $|D|$ | 说明\n"), [])

    def test_table_context_does_not_cross_blockquote_boundary(self) -> None:
        text = "> A | B\n> --- | ---\n> a | b\n正文 $|D|$。\n"
        self.assertEqual(self.codes(text), [])

    def test_rejects_table_math_inside_list_container(self) -> None:
        text = "- A | B\n  --- | ---\n  $|D|$ | x\n"
        self.assertEqual(self.codes(text), ["GHM012", "GHM012"])

    def test_mismatched_header_and_delimiter_columns_are_not_a_table(self) -> None:
        text = "A | B | C\n--- | ---\n$|D|$ prose\n"
        self.assertEqual(self.codes(text), [])

    def test_accepts_standard_tex_subscripts_and_star(self) -> None:
        text = r"正文 $M^{valid} _ {a_i}\ast x$ 与 $\mathrm{Syn} _ 1$。"
        self.assertEqual(self.codes(text), [])

    def test_rejects_markdown_sensitive_star_and_underscore(self) -> None:
        text = r"正文 $p^*$、 $R*S$、 $M^{valid}_{a_i}$、 $AS[K]_0$ 与 $_S$。"
        self.assertEqual(
            self.codes(text),
            [
                "GHM014",
                "GHM014",
                "GHM015",
                "GHM015",
                "GHM015",
                "GHM019",
            ],
        )

    def test_rejects_cross_formula_underscore_pair_candidates(self) -> None:
        text = r"正文 $M^{valid} _{a_i}\subseteq M_{a_i}$。"
        self.assertEqual(self.codes(text), ["GHM015", "GHM015"])

    def test_rejects_underscore_that_can_close_prose_emphasis(self) -> None:
        text = r"_caption $M_ {a}$"
        self.assertEqual(self.codes(text), ["GHM015"])

    def test_rejects_other_markdown_sensitive_tex_tokens(self) -> None:
        text = r"正文 $a~~b$、 $a`b`c$、 $a<b>c$ 与 $x<span>y</span>z$。"
        self.assertEqual(
            self.codes(text),
            [
                "GHM021",
                "GHM021",
                "GHM011",
                "GHM011",
                "GHM011",
                "GHM011",
                "GHM011",
                "GHM011",
            ],
        )

    def test_rejects_github_autolinks_inside_math(self) -> None:
        text = r"正文 $\text{https://example.com}$、 $user@example.com$ 与 $@octocat$。"
        self.assertEqual(self.codes(text), ["GHM022", "GHM022", "GHM022"])

    def test_rejects_footnote_reference_inside_math(self) -> None:
        text = "$x[^1]$\n\n[^1]: note\n"
        self.assertEqual(self.codes(text), ["GHM024"])

    def test_rejects_markdown_links_and_images_inside_math(self) -> None:
        text = (
            "$a+[x](r)+y$\n"
            "$a+![x](r)+y$\n"
            "$a+[x][id]+y$\n"
            "$a+[x][]+y$\n"
            "$a+[id]+y$\n\n"
            "[id]: /target\n"
            "[x]: /target\n"
        )
        self.assertEqual(self.codes(text), ["GHM025"] * 5)

    def test_accepts_bracketed_array_notation_without_link_definitions(self) -> None:
        text = r"正文 $A[i][j]$、 $Q[\vec x _ {in}][\vec x _ {out}]$ 与 $A[x][]$。"
        self.assertEqual(self.codes(text), [])

    def test_rejects_html_entities_inside_math(self) -> None:
        text = r"正文 $x&copy;y$、 $x&#x2B;y$、 $x&#X2B;y$ 与 $x&nbsp;y$。"
        self.assertEqual(
            self.codes(text), ["GHM026", "GHM026", "GHM026", "GHM026"]
        )

    def test_rejects_empty_group_that_detaches_a_script(self) -> None:
        text = r"正文 $\Vert{} _ F$ 与 $\lt{} ^{\ast}$。"
        self.assertEqual(self.codes(text), ["GHM019", "GHM019"])

    def test_rejects_github_select_token(self) -> None:
        self.assertEqual(self.codes(r"正文 $\text{selectivity}$。"), ["GHM016"])

    def test_rejects_math_in_footnotes_and_italic_spans(self) -> None:
        text = "前 *caption $x$ here* 后\n\n[^a]: note $y$\n"
        self.assertEqual(self.codes(text), ["GHM017", "GHM017"])

    def test_rejects_math_in_link_text_but_accepts_bold_math(self) -> None:
        text = "[caption $x$](https://example.test)\n\n**caption $y$**\n\n正文 **$z$** 后。\n\n正文 __$u$__ 后。\n\n> **$w$**\n"
        self.assertEqual(self.codes(text), ["GHM017"])

    def test_void_html_does_not_capture_following_math(self) -> None:
        self.assertEqual(self.codes("正文 <br> 后 $x$。\n"), [])

    def test_rejects_math_inside_inline_html_attribute(self) -> None:
        text = '正文 <span title=" $x$">label</span>\n'
        self.assertEqual(self.codes(text), ["GHM017"])

    def test_rejects_reference_link_and_image_math(self) -> None:
        text = "[caption $x$][id]\n\n![caption $y$][id]\n\n[id]: image.png\n"
        self.assertEqual(self.codes(text), ["GHM017", "GHM017"])

    def test_rejects_multiline_footnote_math(self) -> None:
        text = "text[^a]\n\n[^a]: first\n    note $x$\n\n[^b]:\n    $$\n    y=1\n    $$\n"
        self.assertEqual(self.codes(text), ["GHM017", "GHM017", "GHM017"])

    def test_rejects_list_item_footnote_math(self) -> None:
        text = "- [^a]: note，$x$\n\n1. [^b]: note，$y$\n"
        self.assertEqual(self.codes(text), ["GHM017", "GHM017"])

    def test_rejects_display_math_inside_raw_html_block(self) -> None:
        text = "<div>\n$$\nx=1\n$$\n</div>\n"
        self.assertEqual(self.codes(text), ["GHM017"])

    def test_rejects_math_in_image_alt_text(self) -> None:
        text = "![epsilon $\\epsilon$](figure.png)\n"
        self.assertEqual(self.codes(text), ["GHM017"])

    def test_rejects_list_indented_display_math(self) -> None:
        text = "- item\n\n  $$\n  x=1\n  $$\n"
        self.assertEqual(self.codes(text), ["GHM018", "GHM018"])

    def test_rejects_literal_dollar(self) -> None:
        self.assertEqual(self.codes("费用是 $5.00。\n"), ["GHM008"])

    def test_reports_crlf_line_and_column(self) -> None:
        from validate_github_math import _line_column

        text = "ok\r\n中文$x$\r\n"
        issue = validate_text(text)[0]
        self.assertEqual(_line_column(text, issue.offset), (2, 3))

    def test_cli_exit_codes(self) -> None:
        script = ROOT / "scripts" / "validate_github_math.py"
        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / "good.md"
            bad = Path(directory) / "bad.md"
            good.write_text("正文 $x$。\n", encoding="utf-8")
            bad.write_text("正文，$x$。\n", encoding="utf-8")
            good_result = subprocess.run(
                [sys.executable, str(script), str(good)], capture_output=True, check=False
            )
            bad_result = subprocess.run(
                [sys.executable, str(script), str(bad)], capture_output=True, check=False
            )
            missing_result = subprocess.run(
                [sys.executable, str(script), str(Path(directory) / "missing.md")],
                capture_output=True,
                check=False,
            )
        self.assertEqual(good_result.returncode, 0)
        self.assertEqual(bad_result.returncode, 1)
        self.assertEqual(missing_result.returncode, 2)

    def test_extracts_complete_inline_and_display_expressions(self) -> None:
        text = "正文 $x$。\n\n> $$\n> \\begin{aligned}\n> y &= 1\n> \\end{aligned}\n> $$\n"
        expressions = extract_math_expressions(text)
        self.assertEqual(
            [(expression.text, expression.display) for expression in expressions],
            [
                ("x", False),
                ("\\begin{aligned}\ny &= 1\n\\end{aligned}", True),
            ],
        )


if __name__ == "__main__":
    unittest.main()
