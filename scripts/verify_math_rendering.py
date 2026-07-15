#!/usr/bin/env python3
"""Verify already-valid translation math with KaTeX and/or GitHub Markdown."""

from __future__ import annotations

import argparse
from collections import Counter
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from validate_github_math import MathExpression, extract_math_expressions


ROOT = Path(__file__).resolve().parents[1]
MATH_RENDERER_RE = re.compile(
    r"<math-renderer\b[^>]*>(.*?)</math-renderer>", re.DOTALL
)


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _load_expressions(
    paths: list[Path],
) -> tuple[list[dict[str, object]], dict[Path, tuple[str, list[MathExpression]]]]:
    serialized: list[dict[str, object]] = []
    by_path: dict[Path, tuple[str, list[MathExpression]]] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        expressions = extract_math_expressions(text)
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


def _expected_renderer_text(expression: MathExpression) -> str:
    if expression.display:
        return f"$$\n{expression.text}\n$$"
    return f"${expression.text}$"


def _normalized_renderer_text(value: str) -> str:
    value = html.unescape(html.unescape(value))
    if value.startswith("$$") and value.rstrip().endswith("$$"):
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        return "\n".join(lines)
    return value


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
            _normalized_renderer_text(match)
            for match in MATH_RENDERER_RE.findall(rendered)
        ]
        expected = [
            _normalized_renderer_text(_expected_renderer_text(expression))
            for expression in expressions
        ]
        if actual == expected:
            continue
        missing = Counter(expected) - Counter(actual)
        unexpected = Counter(actual) - Counter(expected)
        for index, value in enumerate(expected):
            if missing[value] <= 0:
                continue
            expression = expressions[index]
            failures.append(
                f"{path}:{_line(text, expression.offset)}: GitHub did not create an unchanged math renderer for {value!r}"
            )
            missing[value] -= 1
        for value, count in unexpected.items():
            for _ in range(count):
                failures.append(
                    f"{path}: GitHub created an unexpected or rewritten math renderer for {value!r}"
                )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--katex-module", type=Path)
    parser.add_argument("--github", action="store_true")
    parser.add_argument(
        "--github-context", default="HippopotamusData/db-papers"
    )
    args = parser.parse_args()
    if args.katex_module is None and not args.github:
        parser.error("select --katex-module and/or --github")

    try:
        serialized, by_path = _load_expressions(args.paths)
        failures: list[str] = []
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
