#!/usr/bin/env python3
"""Validate the portable Markdown-math subset used by translations.

The accepted subset is deliberately smaller than any one renderer's syntax. It
targets the intersection exercised by GitHub, GitBook, and VS Code's Markdown
preview, while accounting for GitHub's Markdown pass before its math renderer.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


FENCE_OPEN_RE = re.compile(
    r"^(?P<quote>(?: {0,3}>[ \t]?)*)(?P<indent> {0,3})"
    r"(?P<run>`{3,}|~{3,})(?P<info>[^\r\n]*)(?:\r?\n)?$"
)
QUOTE_PREFIX_RE = re.compile(r"^(?: {0,3}>[ \t]?)*")
DISPLAY_DELIMITER_RE = re.compile(
    r"^(?P<prefix>(?: {0,3}>[ \t]?)* {0,3})\$\$[ \t]*(?:\r?\n)?$"
)
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]")
CONTROL_WORD_RE = re.compile(r"[A-Za-z@]")
MARKDOWN_ESCAPABLE = frozenset(r'!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~')
CONFIG_COMMANDS = frozenset(
    {
        "DeclareMathOperator",
        "def",
        "edef",
        "gdef",
        "let",
        "newcommand",
        "newenvironment",
        "providecommand",
        "renewcommand",
        "renewenvironment",
        "require",
        "xdef",
    }
)
KNOWN_UNSUPPORTED_COMMANDS = frozenset({"fullouterjoin", "leftouterjoin"})


@dataclass(frozen=True)
class MathIssue:
    offset: int
    code: str
    message: str


@dataclass(frozen=True)
class MathFragment:
    """A TeX payload and its source location, excluding dollar delimiters."""

    offset: int
    text: str
    display: bool
    table_row: bool = False


@dataclass(frozen=True)
class MathExpression:
    """A complete inline or display expression ready for renderer verification."""

    offset: int
    text: str
    display: bool


def _mask_range(chars: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if chars[index] not in "\r\n":
            chars[index] = " "


def _escaped(text: str | list[str], index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _quote_prefix(line: str) -> str:
    return QUOTE_PREFIX_RE.match(line).group()  # type: ignore[union-attr]


def _fence_close(line: str, quote: str, marker: str, minimum: int) -> bool:
    if not line.startswith(quote):
        return False
    remainder = line[len(quote) :]
    match = re.match(r"^( {0,3})(`+|~+)[ \t]*(?:\r?\n)?$", remainder)
    return bool(
        match
        and match.group(2)[0] == marker
        and len(match.group(2)) >= minimum
    )


def _mask_block_code(text: str) -> tuple[list[str], list[MathIssue]]:
    """Mask fenced and top-level indented code while preserving offsets."""

    chars = list(text)
    issues: list[MathIssue] = []
    fence_marker: str | None = None
    fence_length = 0
    fence_quote = ""
    display_math = False
    offset = 0

    for line in text.splitlines(keepends=True):
        if fence_marker is not None:
            _mask_range(chars, offset, offset + len(line))
            if _fence_close(line, fence_quote, fence_marker, fence_length):
                fence_marker = None
                fence_length = 0
                fence_quote = ""
            offset += len(line)
            continue

        # Once a portable display block has opened, indentation belongs to TeX
        # rather than to a Markdown indented-code block.
        if DISPLAY_DELIMITER_RE.match(line):
            display_math = not display_math
            offset += len(line)
            continue
        if display_math:
            offset += len(line)
            continue

        opening = FENCE_OPEN_RE.match(line)
        if opening:
            run = opening.group("run")
            info = opening.group("info").strip()
            # A backtick fence cannot contain a backtick in its info string.
            if run[0] == "`" and "`" in info:
                opening = None
            else:
                language = info.split(maxsplit=1)[0].lower() if info else ""
                if language in {"math", "latex", "tex"}:
                    issues.append(
                        MathIssue(
                            offset + opening.start("run"),
                            "GHM004",
                            "fenced math is not portable; use a display block with standalone $$ delimiters",
                        )
                    )
                fence_marker = run[0]
                fence_length = len(run)
                fence_quote = opening.group("quote")
                _mask_range(chars, offset, offset + len(line))
                offset += len(line)
                continue

        quote = _quote_prefix(line)
        remainder = line[len(quote) :]
        if remainder.startswith("\t") or remainder.startswith("    "):
            _mask_range(chars, offset, offset + len(line))
        offset += len(line)

    return chars, issues


def _tick_run(chars: list[str], start: int) -> int:
    end = start
    while end < len(chars) and chars[end] == "`":
        end += 1
    return end - start


def _find_exact_tick_close(chars: list[str], start: int, length: int) -> int | None:
    cursor = start
    while cursor < len(chars):
        if chars[cursor] != "`" or _escaped(chars, cursor):
            cursor += 1
            continue
        run_length = _tick_run(chars, cursor)
        if run_length == length:
            return cursor
        cursor += run_length
    return None


def _mask_inline_code(
    text: str, chars: list[str]
) -> tuple[list[str], list[MathIssue]]:
    """Mask CommonMark code spans, including multiline and exact tick runs."""

    issues: list[MathIssue] = []
    cursor = 0
    while cursor < len(chars):
        if chars[cursor] != "`" or _escaped(chars, cursor):
            cursor += 1
            continue
        run_length = _tick_run(chars, cursor)
        closing = _find_exact_tick_close(chars, cursor + run_length, run_length)
        if closing is None:
            cursor += run_length
            continue
        closing_end = closing + run_length
        github_math = (
            cursor > 0
            and chars[cursor - 1] == "$"
            and not _escaped(chars, cursor - 1)
            and closing_end < len(chars)
            and chars[closing_end] == "$"
            and not _escaped(chars, closing_end)
        )
        if github_math:
            issues.append(
                MathIssue(
                    cursor - 1,
                    "GHM006",
                    "GitHub-only $`...`$ math is not portable; use ordinary $...$",
                )
            )
            _mask_range(chars, cursor - 1, closing_end + 1)
            cursor = closing_end + 1
        else:
            _mask_range(chars, cursor, closing_end)
            cursor = closing_end
    return chars, issues


def _markdown_visible(text: str) -> tuple[str, list[MathIssue]]:
    chars, issues = _mask_block_code(text)
    chars, inline_issues = _mask_inline_code(text, chars)
    issues.extend(inline_issues)
    return "".join(chars), issues


def _safe_opening_boundary(line: str, index: int) -> bool:
    if index == 0:
        return True
    return line[index - 1] in {" ", "("}


def _safe_closing_boundary(line: str, index: int) -> bool:
    if index + 1 >= len(line) or line[index + 1] in "\r\n":
        return True
    return ASCII_WORD_RE.fullmatch(line[index + 1]) is None


def _unescaped_dollars(line: str) -> list[int]:
    return [
        index
        for index, char in enumerate(line)
        if char == "$" and not _escaped(line, index)
    ]


def _looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _parse_math(text: str) -> tuple[list[MathFragment], list[MathIssue]]:
    visible, issues = _markdown_visible(text)
    fragments: list[MathFragment] = []
    display_start: int | None = None
    display_prefix = ""
    display_has_content = False
    offset = 0

    for line in visible.splitlines(keepends=True):
        delimiter = DISPLAY_DELIMITER_RE.match(line)
        if delimiter:
            prefix = delimiter.group("prefix")
            if ">" not in prefix and prefix:
                issues.append(
                    MathIssue(
                        offset + delimiter.start(),
                        "GHM018",
                        "list-indented display math is not portable; outdent the complete $$ block",
                    )
                )
            if display_start is None:
                display_start = offset + delimiter.start()
                display_prefix = prefix
                display_has_content = False
            elif prefix == display_prefix:
                if not display_has_content:
                    issues.append(
                        MathIssue(
                            display_start,
                            "GHM008",
                            "display math must contain a non-empty TeX payload",
                        )
                    )
                display_start = None
                display_prefix = ""
                display_has_content = False
            else:
                issues.append(
                    MathIssue(
                        offset + delimiter.start(),
                        "GHM008",
                        "display delimiters must use the same Markdown container prefix",
                    )
                )
            offset += len(line)
            continue

        if display_start is not None:
            if display_prefix and not line.startswith(display_prefix):
                issues.append(
                    MathIssue(
                        offset,
                        "GHM008",
                        "each display-math line must retain the opening Markdown container prefix",
                    )
                )
                logical = line
                logical_offset = offset
            else:
                logical = line[len(display_prefix) :]
                logical_offset = offset + len(display_prefix)
            if logical.strip():
                display_has_content = True
            dollars = _unescaped_dollars(logical)
            if dollars:
                issues.append(
                    MathIssue(
                        logical_offset + dollars[0],
                        "GHM008",
                        "unescaped $ is not allowed inside a display-math payload",
                    )
                )
            fragments.append(MathFragment(logical_offset, logical, True))
            offset += len(line)
            continue

        dollars = _unescaped_dollars(line)
        if not dollars:
            offset += len(line)
            continue

        if any(
            index + 1 < len(line) and line[index + 1] == "$"
            for index in dollars
        ):
            first = next(
                index
                for index in dollars
                if index + 1 < len(line) and line[index + 1] == "$"
            )
            issues.append(
                MathIssue(
                    offset + first,
                    "GHM007",
                    "display-math $$ delimiters must each occupy their own Markdown container line",
                )
            )
            offset += len(line)
            continue

        if len(dollars) % 2:
            issues.append(
                MathIssue(
                    offset + dollars[-1],
                    "GHM008",
                    "literal dollars must be escaped as \\$; inline math must use a same-line pair",
                )
            )

        table_row = _looks_like_table_row(line)
        stripped = line.strip()
        nonportable_container = (
            (stripped.startswith("[^") and "]:" in stripped)
            or (
                stripped.startswith("*")
                and not stripped.startswith("**")
                and stripped.endswith("*")
                and not stripped.endswith("**")
            )
        )
        for pair_start in range(0, len(dollars) - 1, 2):
            opening = dollars[pair_start]
            closing = dollars[pair_start + 1]
            payload = line[opening + 1 : closing]
            if not payload or payload[0].isspace() or payload[-1].isspace():
                issues.append(
                    MathIssue(
                        offset + opening,
                        "GHM008",
                        "inline math must be non-empty and have no whitespace next to its $ delimiters",
                    )
                )
            if not _safe_opening_boundary(line, opening):
                previous = line[opening - 1]
                issues.append(
                    MathIssue(
                        offset + opening,
                        "GHM005",
                        f"unsafe inline-math opening after {previous!r}; use an ASCII space before $ or rewrite the phrase",
                    )
                )
            if not _safe_closing_boundary(line, closing):
                following = line[closing + 1]
                issues.append(
                    MathIssue(
                        offset + closing,
                        "GHM005",
                        f"unsafe inline-math closing before {following!r}; add a boundary or keep the complete identifier in one formula",
                    )
                )
            if nonportable_container:
                issues.append(
                    MathIssue(
                        offset + opening,
                        "GHM017",
                        "GitHub does not render math inside footnote definitions or italic spans; move the formula into ordinary Markdown",
                    )
                )
            image_alt_start = line.rfind("![", 0, opening)
            image_alt_end = line.find("](", closing)
            if image_alt_start >= 0 and image_alt_end > closing:
                issues.append(
                    MathIssue(
                        offset + opening,
                        "GHM017",
                        "GitHub does not render math inside image alt text; use plain alt text and put the formula in the caption",
                    )
                )
            fragments.append(
                MathFragment(offset + opening + 1, payload, False, table_row)
            )
        offset += len(line)

    if display_start is not None:
        issues.append(
            MathIssue(
                display_start,
                "GHM008",
                "unbalanced display-math $$ delimiter",
            )
        )
    return fragments, issues


def extract_math_fragments(text: str) -> list[MathFragment]:
    """Return candidate TeX payloads; callers should validate before trusting them."""

    fragments, _ = _parse_math(text)
    return fragments


def extract_math_expressions(text: str) -> list[MathExpression]:
    """Extract complete expressions after the portable syntax gate succeeds."""

    issues = validate_text(text)
    if issues:
        raise ValueError("portable math validation must succeed before extraction")

    visible, _ = _markdown_visible(text)
    expressions: list[MathExpression] = []
    display_start: int | None = None
    display_prefix = ""
    display_lines: list[str] = []
    offset = 0
    for line in visible.splitlines(keepends=True):
        delimiter = DISPLAY_DELIMITER_RE.match(line)
        if delimiter:
            if display_start is None:
                display_start = offset + delimiter.start()
                display_prefix = delimiter.group("prefix")
                display_lines = []
            else:
                expressions.append(
                    MathExpression(display_start, "\n".join(display_lines), True)
                )
                display_start = None
                display_prefix = ""
                display_lines = []
            offset += len(line)
            continue
        if display_start is not None:
            logical = line[len(display_prefix) :] if display_prefix else line
            display_lines.append(logical.rstrip("\r\n"))
            offset += len(line)
            continue

        dollars = _unescaped_dollars(line)
        for pair_start in range(0, len(dollars), 2):
            opening = dollars[pair_start]
            closing = dollars[pair_start + 1]
            expressions.append(
                MathExpression(
                    offset + opening,
                    line[opening + 1 : closing],
                    False,
                )
            )
        offset += len(line)
    return expressions


def _tex_issues(fragment: MathFragment) -> list[MathIssue]:
    issues: list[MathIssue] = []
    payload = fragment.text
    cursor = 0
    while cursor < len(payload):
        char = payload[cursor]
        if char == "*":
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM014",
                    r"raw * is consumed as Markdown emphasis; use \ast",
                )
            )
        if char == "_" and (
            cursor == 0
            or not (
                payload[cursor - 1].isascii()
                and payload[cursor - 1].isalnum()
            )
        ):
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM015",
                    r"this _ can participate in Markdown emphasis; rewrite the notation or put \relax before _",
                )
            )
        if char in "<>":
            replacement = r"\lt" if char == "<" else r"\gt"
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM011",
                    f"raw {char} is HTML-sensitive inside Markdown math; use {replacement}",
                )
            )
        if char == "|" and fragment.table_row:
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM012",
                    r"raw | splits Markdown table cells; use \mid, \lvert, or \rvert",
                )
            )
        if char != "\\":
            cursor += 1
            continue

        run_end = cursor + 1
        while run_end < len(payload) and payload[run_end] == "\\":
            run_end += 1
        run_length = run_end - cursor
        if run_length >= 2:
            allowed_row_break = (
                fragment.display
                and run_length == 2
                and (
                    run_end >= len(payload)
                    or payload[run_end] in " \t\r\n["
                )
            )
            if not allowed_row_break:
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM009",
                        r"double backslashes are only allowed as a display-math row break",
                    )
                )
            cursor = run_end
            continue

        if run_end >= len(payload):
            cursor = run_end
            continue
        next_char = payload[run_end]
        if next_char in "()[]":
            cursor = run_end + 1
            continue
        if next_char in MARKDOWN_ESCAPABLE:
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM010",
                    f"Markdown consumes \\{next_char} before math rendering; use a named TeX command or rewrite the expression",
                )
            )
            cursor = run_end + 1
            continue
        if CONTROL_WORD_RE.fullmatch(next_char):
            command_end = run_end + 1
            while command_end < len(payload) and CONTROL_WORD_RE.fullmatch(
                payload[command_end]
            ):
                command_end += 1
            command = payload[run_end:command_end]
            if command == "operatorname":
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM001",
                        r"GitHub rejects \operatorname; use a built-in operator or \mathrm{Name}",
                    )
                )
            elif command in CONFIG_COMMANDS:
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM003",
                        f"renderer-dependent macro configuration is forbidden: \\{command}",
                    )
                )
            elif command in KNOWN_UNSUPPORTED_COMMANDS:
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM013",
                        f"unsupported custom TeX command: \\{command}; use a self-contained standard expression",
                    )
                )
            cursor = command_end
            continue
        cursor = run_end + 1
    for match in re.finditer(r"select", payload, re.IGNORECASE):
        issues.append(
            MathIssue(
                fragment.offset + match.start(),
                "GHM016",
                r"GitHub suppresses math containing the raw token 'select'; split it as selec{}t",
            )
        )
    return issues


def _alternative_delimiter_issues(text: str) -> list[MathIssue]:
    visible, _ = _markdown_visible(text)
    issues: list[MathIssue] = []
    cursor = 0
    while cursor + 1 < len(visible):
        if (
            visible[cursor] == "\\"
            and not _escaped(visible, cursor)
            and visible[cursor + 1] in "()[]"
        ):
            delimiter = visible[cursor : cursor + 2]
            replacement = "$...$" if delimiter in {r"\(", r"\)"} else "a $$ block"
            issues.append(
                MathIssue(
                    cursor,
                    "GHM002",
                    f"GitHub does not use {delimiter} as a math delimiter; use {replacement}",
                )
            )
            cursor += 2
        else:
            cursor += 1
    return issues


def validate_text(text: str) -> list[MathIssue]:
    fragments, issues = _parse_math(text)
    issues.extend(_alternative_delimiter_issues(text))
    for fragment in fragments:
        issues.extend(_tex_issues(fragment))
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
        print(f"ERROR: portable math validation could not read input: {error}", file=sys.stderr)
        return 2

    if messages:
        print("\n".join(messages))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
