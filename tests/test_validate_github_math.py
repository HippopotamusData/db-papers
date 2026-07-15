from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_github_math import validate_text  # noqa: E402


class ValidateGithubMathTests(unittest.TestCase):
    def codes(self, text: str) -> list[str]:
        return [issue.code for issue in validate_text(text)]

    def test_accepts_documented_github_math_forms(self) -> None:
        text = r"""行内公式 $\min_i x_i$。
冲突字符使用 $`\sqrt{\$4}`$。

$$
f(x)=\mathrm{Cost}(x)
$$

```math
\begin{aligned}
x &= 1 \\
y &= 2
\end{aligned}
```
"""
        self.assertEqual(self.codes(text), [])

    def test_rejects_operatorname(self) -> None:
        issues = validate_text(r"$\operatorname{Cost}(x)$")
        self.assertEqual([issue.code for issue in issues], ["GHM001"])
        self.assertIn(r"\mathrm{Name}", issues[0].message)

    def test_rejects_tex_style_math_delimiters(self) -> None:
        self.assertEqual(
            self.codes(r"行内 \(x\)，块级 \[y\]。"),
            ["GHM002", "GHM002", "GHM002", "GHM002"],
        )

    def test_rejects_macro_configuration(self) -> None:
        text = r"$$\newcommand{\cost}{\mathrm{cost}}\cost(x)$$"
        self.assertEqual(self.codes(text), ["GHM003"])

    def test_checks_math_fence_contents(self) -> None:
        text = "```math\n\\operatorname{Cost}(x)\n```\n"
        self.assertEqual(self.codes(text), ["GHM001"])

    def test_ignores_literal_examples_in_code(self) -> None:
        text = r"""普通代码 `\operatorname{x}` 与 `\(x\)`。

```tex-example
\operatorname{x}
\[x\]
```
"""
        self.assertEqual(self.codes(text), [])

    def test_rejects_unsupported_math_fence_names(self) -> None:
        text = "```latex\nx=1\n```\n\n~~~math\ny=2\n~~~\n"
        self.assertEqual(self.codes(text), ["GHM004", "GHM004"])


if __name__ == "__main__":
    unittest.main()
