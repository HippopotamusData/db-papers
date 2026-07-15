#!/usr/bin/env python3
"""Reject Markdown math constructs that are incompatible with GitHub rendering."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


FENCE_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})([^\r\n]*)")
ALT_DELIMITER_RE = re.compile(r"\\[()\[\]]")
OPERATORNAME_RE = re.compile(r"\\operatorname(?:\*)?")
CONFIG_MACRO_RE = re.compile(
    r"\\(?:def|gdef|edef|xdef|let|newcommand|renewcommand|providecommand|"
    r"DeclareMathOperator|require)\b"
)


@dataclass(frozen=True)
class MathIssue:
    offset: int
    code: str
    message: str


def _mask_range(chars: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if chars[index] not in "\r\n":
            chars[index] = " "


def _mask_inline_code(line: str) -> str:
    """Mask ordinary code spans while retaining GitHub's $`...`$ math form."""

    chars = list(line)
    index = 0
    while index < len(line):
        if line[index] != "`":
            index += 1
            continue
        run_end = index + 1
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1
        ticks = line[index:run_end]
        closing = line.find(ticks, run_end)
        if closing < 0:
            index = run_end
            continue
        closing_end = closing + len(ticks)
        github_math = (
            index > 0
            and line[index - 1] == "$"
            and closing_end < len(line)
            and line[closing_end] == "$"
        )
        if not github_math:
            _mask_range(chars, index, closing_end)
        index = closing_end
    return "".join(chars)


def _closing_fence(line: str, marker: str, minimum_length: int) -> bool:
    match = re.match(rf"^ {{0,3}}({re.escape(marker)}{{{minimum_length},}})[ \t]*(?:\r?\n)?$", line)
    return match is not None


def _visible_text(text: str) -> tuple[str, list[MathIssue]]:
    """Mask non-math code and report unsupported math fence spellings."""

    output: list[str] = []
    structural_issues: list[MathIssue] = []
    fence_marker: str | None = None
    fence_length = 0
    math_fence = False
    offset = 0

    for line in text.splitlines(keepends=True):
        if fence_marker is not None:
            if _closing_fence(line, fence_marker, fence_length):
                output.append("".join("\n" if char == "\n" else "\r" if char == "\r" else " " for char in line))
                fence_marker = None
                fence_length = 0
                math_fence = False
            elif math_fence:
                output.append(line)
            else:
                output.append("".join("\n" if char == "\n" else "\r" if char == "\r" else " " for char in line))
            offset += len(line)
            continue

        opening = FENCE_OPEN_RE.match(line)
        if opening:
            run = opening.group(2)
            marker = run[0]
            info = opening.group(3).strip().split(maxsplit=1)
            language = info[0].lower() if info else ""
            math_fence = marker == "`" and language == "math"
            if language in {"latex", "tex"} or (language == "math" and marker != "`"):
                structural_issues.append(
                    MathIssue(
                        offset + len(opening.group(1)),
                        "GHM004",
                        "unsupported math fence; use a ```math fence or a $$ block",
                    )
                )
            fence_marker = marker
            fence_length = len(run)
            output.append("".join("\n" if char == "\n" else "\r" if char == "\r" else " " for char in line))
        else:
            output.append(_mask_inline_code(line))
        offset += len(line)

    return "".join(output), structural_issues


def validate_text(text: str) -> list[MathIssue]:
    visible, issues = _visible_text(text)

    for match in ALT_DELIMITER_RE.finditer(visible):
        replacement = "$...$" if match.group() in {r"\(", r"\)"} else "a $$ block"
        issues.append(
            MathIssue(
                match.start(),
                "GHM002",
                f"GitHub does not use {match.group()} as a math delimiter; use {replacement}",
            )
        )

    for match in OPERATORNAME_RE.finditer(visible):
        issues.append(
            MathIssue(
                match.start(),
                "GHM001",
                r"GitHub rejects \operatorname; use a built-in operator such as \min, or \mathrm{Name}",
            )
        )

    for match in CONFIG_MACRO_RE.finditer(visible):
        issues.append(
            MathIssue(
                match.start(),
                "GHM003",
                f"renderer-dependent macro configuration is forbidden: {match.group()}",
            )
        )

    return sorted(issues, key=lambda issue: (issue.offset, issue.code))


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    previous_newline = text.rfind("\n", 0, offset)
    column = offset - previous_newline
    return line, column


def validate_path(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    messages = []
    for issue in validate_text(text):
        line, column = _line_column(text, issue.offset)
        messages.append(f"{path}:{line}:{column}: {issue.code} {issue.message}")
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    messages: list[str] = []
    try:
        for path in args.paths:
            messages.extend(validate_path(path))
    except (OSError, UnicodeError) as error:
        print(f"ERROR: GitHub math validation could not read input: {error}", file=sys.stderr)
        return 2

    if messages:
        print("\n".join(messages))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
