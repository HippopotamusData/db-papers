#!/usr/bin/env python3
"""Verify already-valid translation math with MathJax, GitHub, and/or KaTeX."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from validate_github_math import (
    MathExpression,
    extract_math_expressions,
    extract_math_expressions_unchecked,
)


ROOT = Path(__file__).resolve().parents[1]
MATH_RENDERER_RE = re.compile(
    r"<math-renderer\b[^>]*>(.*?)</math-renderer>", re.DOTALL
)


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _load_expressions(
    paths: list[Path],
    *,
    validate: bool = True,
) -> tuple[list[dict[str, object]], dict[Path, tuple[str, list[MathExpression]]]]:
    serialized: list[dict[str, object]] = []
    by_path: dict[Path, tuple[str, list[MathExpression]]] = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise OSError(f"refusing a symlink or non-regular input: {path}")
        text = path.read_text(encoding="utf-8")
        expressions = (
            extract_math_expressions(text)
            if validate
            else extract_math_expressions_unchecked(text)
        )
        by_path[path] = (text, expressions)
        for expression in expressions:
            serialized.append(
                {
                    "path": str(path),
                    "line": _line(text, expression.offset),
                    "text": expression.text,
                    "display": expression.display,
                }
            )
    return serialized, by_path


def _verify_katex(
    expressions: list[dict[str, object]], module: Path
) -> list[str]:
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "render_katex.cjs"), str(module)],
        input=json.dumps(expressions),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 2:
        raise RuntimeError(result.stderr.strip() or "KaTeX verifier failed")
    failures = json.loads(result.stdout)
    return [
        f"{failure['path']}:{failure['line']}: KaTeX: {failure['error']}"
        for failure in failures
    ]


def _verify_mathjax(
    expressions: list[dict[str, object]], module: Path
) -> list[str]:
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "render_mathjax.cjs"), str(module)],
        input=json.dumps(expressions),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 2:
        raise RuntimeError(result.stderr.strip() or "MathJax verifier failed")
    failures = json.loads(result.stdout)
    return [
        f"{failure['path']}:{failure['line']}: MathJax: {failure['error']}"
        for failure in failures
    ]


def _expected_renderer_text(expression: MathExpression) -> str:
    if expression.display:
        return f"$$\n{expression.text}\n$$"
    return f"${expression.text}$"


def _normalized_renderer_whitespace(value: str) -> str:
    if value.startswith("$$") and value.rstrip().endswith("$$"):
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        return "\n".join(lines)
    return value


def _normalized_expected_renderer_text(expression: MathExpression) -> str:
    return _normalized_renderer_whitespace(_expected_renderer_text(expression))


def _normalized_actual_renderer_text(value: str) -> str:
    return _normalized_renderer_whitespace(html.unescape(html.unescape(value)))


def _github_html(text: str, context: str) -> str:
    payload = json.dumps({"text": text, "mode": "gfm", "context": context})
    last_error = "GitHub Markdown API failed"
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["gh", "api", "--method", "POST", "markdown", "--input", "-"],
                input=payload,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            last_error = "GitHub Markdown API timed out"
        else:
            if result.returncode == 0:
                return result.stdout
            last_error = result.stderr.strip() or last_error
        if attempt < 2:
            time.sleep(attempt + 1)
    raise RuntimeError(last_error)


def _verify_github(
    by_path: dict[Path, tuple[str, list[MathExpression]]], context: str
) -> list[str]:
    failures: list[str] = []
    for path, (text, expressions) in by_path.items():
        rendered = _github_html(text, context)
        actual = [
            _normalized_actual_renderer_text(match)
            for match in MATH_RENDERER_RE.findall(rendered)
        ]
        expected = [
            _normalized_expected_renderer_text(expression)
            for expression in expressions
        ]
        failures.extend(
            _github_sequence_failures(path, text, expressions, expected, actual)
        )
    return failures


def _github_sequence_failures(
    path: Path,
    text: str,
    expressions: list[MathExpression],
    expected: list[str],
    actual: list[str],
) -> list[str]:
    failures: list[str] = []
    matcher = SequenceMatcher(a=expected, b=actual, autojunk=False)
    for operation, expected_start, expected_end, actual_start, actual_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        expected_values = expected[expected_start:expected_end]
        actual_values = actual[actual_start:actual_end]
        paired = min(len(expected_values), len(actual_values))
        for relative in range(paired):
            index = expected_start + relative
            expression = expressions[index]
            failures.append(
                f"{path}:{_line(text, expression.offset)}: GitHub rewrote math renderer from {expected_values[relative]!r} to {actual_values[relative]!r}"
            )
        for relative in range(paired, len(expected_values)):
            index = expected_start + relative
            expression = expressions[index]
            failures.append(
                f"{path}:{_line(text, expression.offset)}: GitHub did not create a math renderer for occurrence {index + 1}: {expected_values[relative]!r}"
            )
        for relative in range(paired, len(actual_values)):
            failures.append(
                f"{path}: GitHub created unexpected math renderer occurrence {actual_start + relative + 1}: {actual_values[relative]!r}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--mathjax-module", type=Path)
    parser.add_argument("--katex-module", type=Path)
    parser.add_argument("--github", action="store_true")
    parser.add_argument(
        "--unchecked-input",
        action="store_true",
        help="extract fixed dollar delimiters without trusting the target tree's TeX profile",
    )
    parser.add_argument(
        "--github-context", default="HippopotamusData/db-papers"
    )
    args = parser.parse_args()
    if args.mathjax_module is None and args.katex_module is None and not args.github:
        parser.error("select --mathjax-module, --katex-module, and/or --github")
    if args.unchecked_input and (
        not args.github
        or args.mathjax_module is not None
        or args.katex_module is not None
    ):
        parser.error("--unchecked-input is limited to the GitHub node audit")

    try:
        serialized, by_path = _load_expressions(
            args.paths, validate=not args.unchecked_input
        )
        failures: list[str] = []
        if args.mathjax_module is not None:
            failures.extend(_verify_mathjax(serialized, args.mathjax_module))
        if args.katex_module is not None:
            failures.extend(_verify_katex(serialized, args.katex_module))
        if args.github:
            failures.extend(_verify_github(by_path, args.github_context))
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: math rendering verification failed: {error}", file=sys.stderr)
        return 2

    if failures:
        print("\n".join(failures))
        return 1
    print(
        f"OK: verified {len(serialized)} expressions in {len(args.paths)} files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
