#!/usr/bin/env python3
"""Validate the GitHub-first Markdown-math profile used by translations.

The profile guarantees GitHub's Markdown boundary and command constraints while
retaining conventional dollar delimiters and self-contained TeX that mainstream
Markdown readers can usually display without semantics-changing rewrites.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.common.utils import normalizeReference

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
PORTABLE_COMMANDS = frozenset(
    """
    Big Delta Gamma Join Leftrightarrow Longleftrightarrow Omega Phi Pi Pr
    Rightarrow Theta Vert Xi alpha approx arg ast bar begin beta big bigcup bigl
    bigr bigwedge bmod bot bowtie cap cdot cdots char chi circ coloneqq cup deg
    delta div ell emptyset end epsilon equiv exists exp forall frac gamma ge
    geq gg gt hat in infty lVert lambda land langle lbrace lceil ldots le left
    leftarrow leftrightarrow leq lfloor lim ll ln log longrightarrow lor lt
    ltimes lvert mapsto mathbb mathbf mathbin mathcal mathit mathrel mathrm max
    mid min models mu ne neg negthinspace neq nexists not notin odot phi pi pm
    pmod prod propto qquad quad rVert rangle rbrace rceil rfloor rho right
    rightarrow rtimes rvert setminus sigma sim simeq sqrt subset subseteq sum
    tag tau text texttt therefore theta thickspace thinspace tilde times to
    triangleq underbrace varnothing vdots vec vee wedge widehat widetilde
    xrightarrow
    """.split()
)
PORTABLE_ENVIRONMENTS = frozenset({"aligned", "cases"})
MARKDOWN = MarkdownIt("commonmark", {"html": True})
HTML_CODE_TAG_RE = re.compile(r"</?(?:code|pre)\b[^>]*>", re.IGNORECASE)
FOOTNOTE_START_RE = re.compile(
    r"^ {0,3}(?:(?:[-+*]|\d{1,9}[.)])[ \t]+)?\[\^[^]\r\n]+\]:"
)
INLINE_MATH_CANDIDATE_RE = re.compile(r"(?<!\\)\$(?!\$).*?(?<!\\)\$")
DISPLAY_MATH_CANDIDATE_RE = re.compile(r"(?m)^[ \t]*(?:> ?)*\$\$[ \t]*$")
MATH_PLACEHOLDER = "MATHPORTABLETOKEN"
STRONG_MATH_PREFIX_RE = re.compile(
    r"^(?: {0,3}>[ \t]?)*(?: {0,3}(?:[-+*]|\d+[.)])[ \t]+)?(?:\*\*|__)$"
)
VOID_HTML_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


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


def _mask_block_code(text: str) -> tuple[list[str], list[MathIssue]]:
    """Mask CommonMark code and raw HTML blocks while preserving offsets."""

    chars = list(text)
    issues: list[MathIssue] = []
    lines = text.splitlines(keepends=True)
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line)
    starts.append(len(text))

    for token in MARKDOWN.parse(text):
        if token.map is None:
            continue
        start_line, end_line = token.map
        start = starts[start_line]
        end = starts[min(end_line, len(lines))]
        if token.type in {"fence", "code_block"}:
            if token.type == "fence":
                language = token.info.strip().split(maxsplit=1)[0].lower() if token.info.strip() else ""
                if language in {"math", "latex", "tex"}:
                    issues.append(
                        MathIssue(
                            start,
                            "GHM004",
                            "fenced math is not portable; use a display block with standalone $$ delimiters",
                        )
                    )
            _mask_range(chars, start, end)
        elif token.type == "html_block":
            lowered = token.content.lstrip().lower()
            if not lowered.startswith(("<pre", "<code")) and (
                INLINE_MATH_CANDIDATE_RE.search(token.content)
                or DISPLAY_MATH_CANDIDATE_RE.search(token.content)
            ):
                issues.append(
                    MathIssue(
                        start,
                        "GHM017",
                        "math inside a raw HTML block is not portable; use ordinary Markdown",
                    )
                )
            _mask_range(chars, start, end)

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
            line_start = text.rfind("\n", 0, cursor) + 1
            line_end = text.find("\n", closing_end)
            if line_end < 0:
                line_end = len(text)
            opening_dollars = [
                index
                for index in range(line_start, cursor)
                if chars[index] == "$" and not _escaped(chars, index)
            ]
            closing_dollars = [
                index
                for index in range(closing_end, line_end)
                if chars[index] == "$" and not _escaped(chars, index)
            ]
            if len(opening_dollars) % 2 and closing_dollars:
                issues.append(
                    MathIssue(
                        cursor,
                        "GHM021",
                        "raw backticks inside a formula are consumed as a Markdown code span; use a standard TeX command after checking the notation",
                    )
                )
            _mask_range(chars, cursor, closing_end)
            cursor = closing_end
    return chars, issues


def _mask_inline_html_code(chars: list[str]) -> list[str]:
    """Mask inline ``code``/``pre`` HTML containers without parsing math."""

    visible = "".join(chars)
    math_payload_ranges = _math_payload_ranges(visible)
    opened: int | None = None
    for match in HTML_CODE_TAG_RE.finditer(visible):
        # A raw HTML tag inside inline or display math is part of the TeX
        # payload, not a Markdown code container. Keep it visible so the math
        # parser rejects the HTML-sensitive angle brackets instead of
        # validating a sanitized expression.
        if any(
            start <= match.start() and match.end() <= end
            for start, end in math_payload_ranges
        ):
            continue
        tag = match.group()
        closing = tag.lstrip().startswith("</")
        self_closing = tag.rstrip().endswith("/>")
        if self_closing:
            continue
        if not closing and opened is None:
            opened = match.start()
        elif closing and opened is not None:
            _mask_range(chars, opened, match.end())
            opened = None
    if opened is not None:
        _mask_range(chars, opened, len(chars))
    return chars


def _math_payload_ranges(text: str) -> list[tuple[int, int]]:
    """Return source ranges that may become inline or display TeX payloads."""

    ranges: list[tuple[int, int]] = []
    display_start: int | None = None
    display_quote_depth = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        delimiter = DISPLAY_DELIMITER_RE.match(line)
        if delimiter:
            quote_depth = delimiter.group("prefix").count(">")
            if display_start is None:
                display_start = offset + len(line)
                display_quote_depth = quote_depth
            elif quote_depth == display_quote_depth:
                ranges.append((display_start, offset))
                display_start = None
                display_quote_depth = 0
            offset += len(line)
            continue
        if display_start is None:
            ranges.extend(
                (offset + opening + 1, offset + closing)
                for opening, closing in _inline_math_pairs(line)
            )
        offset += len(line)
    if display_start is not None:
        ranges.append((display_start, len(text)))
    return ranges


def _range_inside_inline_math(
    chars: list[str], start: int, end: int
) -> bool:
    line_start = "".join(chars).rfind("\n", 0, start) + 1
    joined = "".join(chars)
    line_end = joined.find("\n", end)
    if line_end < 0:
        line_end = len(chars)
    before = [
        index
        for index in range(line_start, start)
        if chars[index] == "$" and not _escaped(chars, index)
    ]
    after = [
        index
        for index in range(end, line_end)
        if chars[index] == "$" and not _escaped(chars, index)
    ]
    return len(before) % 2 == 1 and bool(after)


def _mask_link_destinations(
    chars: list[str],
) -> tuple[list[str], list[MathIssue]]:
    """Mask inline-link destinations/titles while retaining their labels."""

    issues: list[MathIssue] = []
    cursor = 0
    label_stack: list[int] = []
    while cursor < len(chars):
        if chars[cursor] == "[" and not _escaped(chars, cursor):
            label_stack.append(cursor)
            cursor += 1
            continue
        if chars[cursor] != "]" or _escaped(chars, cursor) or not label_stack:
            cursor += 1
            continue
        label_start = label_stack.pop()
        opening = cursor + 1
        if opening >= len(chars) or chars[opening] != "(":
            cursor += 1
            continue
        closing = _inline_link_close(chars, opening)
        if closing is None:
            cursor += 1
            continue
        if _range_inside_inline_math(chars, label_start, closing):
            issue_offset = (
                label_start - 1
                if label_start > 0 and chars[label_start - 1] == "!"
                else label_start
            )
            issues.append(
                MathIssue(
                    issue_offset,
                    "GHM025",
                    "Markdown links and images suppress the math node; move them outside math",
                )
            )
        _mask_range(chars, opening, closing)
        cursor = closing

    visible = "".join(chars)
    for match in re.finditer(r"<(?:https?://|mailto:)[^>\r\n]*>", visible, re.IGNORECASE):
        _mask_range(chars, match.start(), match.end())

    line_starts: list[int] = []
    offset = 0
    for line in visible.splitlines(keepends=True):
        line_starts.append(offset)
        offset += len(line)
    line_starts.append(len(visible))
    environment: dict[str, object] = {}
    MARKDOWN.parse(visible, environment)
    references = environment.get("references", {})
    if isinstance(references, dict):
        for reference in references.values():
            if not isinstance(reference, dict):
                continue
            line_map = reference.get("map")
            if (
                isinstance(line_map, list)
                and len(line_map) == 2
                and all(isinstance(value, int) for value in line_map)
            ):
                start_line, end_line = line_map
                _mask_range(chars, line_starts[start_line], line_starts[end_line])
    return chars, issues


def _inline_link_close(chars: list[str], opening: int) -> int | None:
    """Return the end of a CommonMark inline-link destination and title."""

    cursor = opening + 1
    while cursor < len(chars) and chars[cursor] in " \t\r\n":
        cursor += 1
    if cursor >= len(chars):
        return None
    if chars[cursor] == "<":
        cursor += 1
        while cursor < len(chars) and (
            chars[cursor] != ">" or _escaped(chars, cursor)
        ):
            if chars[cursor] in "\r\n":
                return None
            cursor += 1
        if cursor >= len(chars):
            return None
        cursor += 1
    else:
        depth = 0
        while cursor < len(chars):
            char = chars[cursor]
            if char in " \t\r\n" and depth == 0:
                break
            if char == "(" and not _escaped(chars, cursor):
                depth += 1
            elif char == ")" and not _escaped(chars, cursor):
                if depth == 0:
                    return cursor + 1
                depth -= 1
            cursor += 1
        if depth:
            return None
    while cursor < len(chars) and chars[cursor] in " \t\r\n":
        cursor += 1
    if cursor < len(chars) and chars[cursor] in "\"'(":
        opener = chars[cursor]
        closer = ")" if opener == "(" else opener
        cursor += 1
        while cursor < len(chars) and (
            chars[cursor] != closer or _escaped(chars, cursor)
        ):
            cursor += 1
        if cursor >= len(chars):
            return None
        cursor += 1
        while cursor < len(chars) and chars[cursor] in " \t\r\n":
            cursor += 1
    return cursor + 1 if cursor < len(chars) and chars[cursor] == ")" else None


def _markdown_visible(text: str) -> tuple[str, list[MathIssue]]:
    chars, issues = _mask_block_code(text)
    chars, inline_issues = _mask_inline_code(text, chars)
    issues.extend(inline_issues)
    chars = _mask_inline_html_code(chars)
    chars, link_issues = _mask_link_destinations(chars)
    issues.extend(link_issues)
    footnote_lines = _footnote_math_lines(text)
    offset = 0
    for line_number, line in enumerate(text.splitlines(keepends=True)):
        if line_number in footnote_lines:
            _mask_range(chars, offset, offset + len(line))
        offset += len(line)
    return "".join(chars), issues


def _has_math_candidate(text: str) -> bool:
    return bool(
        INLINE_MATH_CANDIDATE_RE.search(text)
        or DISPLAY_MATH_CANDIDATE_RE.search(text)
    )


def _footnote_math_lines(text: str) -> set[int]:
    physical_lines = text.splitlines(keepends=True)
    code_lines: set[int] = set()
    for token in MARKDOWN.parse(text):
        if token.map is not None and token.type in {"fence", "code_block", "html_block"}:
            code_lines.update(range(token.map[0], token.map[1]))

    result: set[int] = set()
    line_number = 0
    while line_number < len(physical_lines):
        line = physical_lines[line_number]
        quote = _quote_prefix(line)
        logical = line[len(quote) :]
        match = FOOTNOTE_START_RE.match(logical)
        if match is None or line_number in code_lines:
            line_number += 1
            continue
        if _has_math_candidate(logical[match.end() :]):
            result.add(line_number)

        continuation = line_number + 1
        while continuation < len(physical_lines):
            candidate = physical_lines[continuation]
            candidate_quote = _quote_prefix(candidate)
            candidate_logical = candidate[len(candidate_quote) :]
            if not candidate_logical.strip():
                continuation += 1
                continue
            if candidate_quote.count(">") != quote.count(">"):
                break
            if not (
                candidate_logical.startswith("\t")
                or candidate_logical.startswith("    ")
            ):
                break
            if _has_math_candidate(candidate_logical.lstrip(" \t")):
                result.add(continuation)
            continuation += 1
        line_number = continuation
    return result


def nonportable_math_lines(text: str) -> set[int]:
    """Return zero-based lines containing math in nonportable Markdown containers."""

    lines: set[int] = set()
    for token in MARKDOWN.parse(text):
        if token.type != "inline" or token.map is None:
            continue
        has_nonportable_math = False
        link_depth = 0
        for child in token.children or []:
            if child.type == "link_open":
                link_depth += 1
            elif child.type == "link_close":
                link_depth = max(0, link_depth - 1)
            elif child.type == "image" and INLINE_MATH_CANDIDATE_RE.search(child.content):
                has_nonportable_math = True
            elif (
                child.type == "text"
                and link_depth
                and INLINE_MATH_CANDIDATE_RE.search(child.content)
            ):
                has_nonportable_math = True

        masked_content = INLINE_MATH_CANDIDATE_RE.sub(MATH_PLACEHOLDER, token.content)
        children = MARKDOWN.parseInline(masked_content)[0].children or []
        em_depth = 0
        html_depth = 0
        for child in children:
            if child.type == "em_open":
                em_depth += 1
                continue
            if child.type == "em_close":
                em_depth = max(0, em_depth - 1)
                continue
            if child.type == "html_inline":
                if MATH_PLACEHOLDER in child.content:
                    has_nonportable_math = True
                tag = re.match(r"<\s*(/)?\s*([A-Za-z][A-Za-z0-9-]*)", child.content)
                if tag and tag.group(2).lower() not in {"code", "pre"}:
                    if tag.group(2).lower() in VOID_HTML_TAGS:
                        continue
                    if tag.group(1):
                        html_depth = max(0, html_depth - 1)
                    elif not child.content.rstrip().endswith("/>"):
                        html_depth += 1
                continue
            if (
                child.type == "text"
                and (em_depth or html_depth)
                and MATH_PLACEHOLDER in child.content
            ):
                has_nonportable_math = True
        if has_nonportable_math:
            lines.update(range(token.map[0], token.map[1]))

    lines.update(_footnote_math_lines(text))
    return lines


def _markdown_container_issues(text: str) -> list[MathIssue]:
    starts: list[int] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        starts.append(offset)
        offset += len(line)
    return [
        MathIssue(
            starts[line] if line < len(starts) else len(text),
            "GHM017",
            "math inside italic text, links, footnote definitions, image alt text, or raw HTML is not portable; use ordinary Markdown",
        )
        for line in sorted(nonportable_math_lines(text))
    ]


def _safe_opening_boundary(line: str, index: int) -> bool:
    if index == 0:
        return True
    if line[index - 1] in {" ", "("}:
        return True
    if index >= 2 and line[index - 2 : index] in {"**", "__"}:
        return True
    return bool(index >= 2 and STRONG_MATH_PREFIX_RE.fullmatch(line[:index]))


def _safe_closing_boundary(line: str, index: int) -> bool:
    if index + 1 >= len(line) or line[index + 1] in "\r\n":
        return True
    if line[index + 1 : index + 3] in {"**", "__"}:
        return True
    return ASCII_WORD_RE.fullmatch(line[index + 1]) is None


def _ends_with_strong_close(markdown: str) -> bool:
    tokens = MARKDOWN.parseInline(markdown)
    children = tokens[0].children if tokens else None
    meaningful = [
        child
        for child in children or []
        if child.type != "text" or child.content
    ]
    return bool(meaningful and meaningful[-1].type == "strong_close")


def _unescaped_dollars(line: str) -> list[int]:
    return [
        index
        for index, char in enumerate(line)
        if char == "$" and not _escaped(line, index)
    ]


TABLE_DELIMITER_CELL_RE = re.compile(r"^:?-+:?$")


def _table_content(line: str) -> tuple[tuple[int, int], str]:
    """Return normalized Markdown container context and table candidate text."""

    content = line.rstrip("\r\n")
    quote = _quote_prefix(content)
    remainder = content[len(quote) :]
    indent = len(remainder) - len(remainder.lstrip(" "))
    list_item = re.match(
        r"^(?P<indent> {0,3})(?P<marker>[-+*]|\d{1,9}[.)])(?P<space>[ \t]+)(?P<body>.*)$",
        remainder,
    )
    if list_item is not None:
        indent = len(list_item.group("indent")) + len(list_item.group("marker")) + len(list_item.group("space"))
        remainder = list_item.group("body")
    return (quote.count(">"), indent), remainder.strip()


def _unescaped_pipes(text: str) -> list[int]:
    return [
        index
        for index, char in enumerate(text)
        if char == "|" and not _escaped(text, index)
    ]


def _inline_math_pairs(text: str) -> list[tuple[int, int]]:
    """Return same-line dollar pairs when no display delimiter is present."""

    dollars = _unescaped_dollars(text)
    if any(
        index + 1 < len(text) and text[index + 1] == "$"
        for index in dollars
    ):
        return []
    return [
        (dollars[pair_start], dollars[pair_start + 1])
        for pair_start in range(0, len(dollars) - 1, 2)
    ]


def _mask_inline_math_payloads(text: str) -> str:
    """Mask paired inline-math payloads while preserving source offsets.

    GFM discovers tables before it creates math nodes, so a raw pipe inside a
    header formula can make an intended table disappear. Header discovery uses
    this masked view, then the validator inspects the original payload and
    emits GHM012 for every raw pipe.
    """

    chars = list(text)
    for opening, closing in _inline_math_pairs(text):
        _mask_range(chars, opening + 1, closing)
    return "".join(chars)


def _table_cells(
    line: str,
    *,
    mask_math: bool = False,
    allow_single_cell: bool = False,
) -> tuple[tuple[int, int], list[str]] | None:
    """Split a GFM table candidate on unescaped pipes.

    Leading and trailing pipes are optional in GFM. Inline code has already
    been masked before this helper is called. Header discovery may additionally
    mask paired inline-math payloads so raw pipes cannot hide an intended table
    from GHM012; body rows retain their original pipes.
    """

    context, content = _table_content(line)
    if mask_math:
        content = _mask_inline_math_payloads(content)
    pipes = _unescaped_pipes(content)
    if not pipes:
        if allow_single_cell and content.strip():
            return context, [content.strip()]
        return None

    cells: list[str] = []
    start = 0
    for pipe in pipes:
        cells.append(content[start:pipe].strip())
        start = pipe + 1
    cells.append(content[start:].strip())
    if content.startswith("|"):
        cells.pop(0)
    if content.endswith("|") and not _escaped(content, len(content) - 1):
        cells.pop()
    return context, cells


def _is_table_delimiter(line: str) -> bool:
    parts = _table_cells(line)
    return bool(
        parts
        and parts[1]
        and all(TABLE_DELIMITER_CELL_RE.fullmatch(cell) for cell in parts[1])
    )


def _table_row_offsets(visible: str) -> set[int]:
    """Locate GFM table rows from delimiter-row context.

    A leading or trailing pipe is optional, so row shape alone is insufficient.
    Once a delimiter row is found, the preceding line is the header and
    following pipe-containing lines are body rows until the block ends.
    """

    lines = visible.splitlines(keepends=True)
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line)

    terminating_lines = {
        token.map[0]
        for token in MARKDOWN.parse(visible)
        if token.map is not None
        and token.type
        in {
            "blockquote_open",
            "bullet_list_open",
            "code_block",
            "fence",
            "heading_open",
            "html_block",
            "list_item_open",
            "ordered_list_open",
        }
    }

    rows: set[int] = set()
    for index, line in enumerate(lines):
        if index == 0 or not _is_table_delimiter(line):
            continue
        delimiter_parts = _table_cells(line)
        header = lines[index - 1]
        header_parts = _table_cells(
            header,
            mask_math=True,
            allow_single_cell=bool(
                delimiter_parts and len(delimiter_parts[1]) == 1
            ),
        )
        if (
            not header.strip()
            or delimiter_parts is None
            or header_parts is None
            or header_parts[0] != delimiter_parts[0]
            or len(header_parts[1]) != len(delimiter_parts[1])
        ):
            continue
        rows.update({starts[index - 1], starts[index]})
        body = index + 1
        while body < len(lines):
            candidate = lines[body]
            candidate_context, candidate_content = _table_content(candidate)
            if (
                not candidate.strip()
                or candidate_context != delimiter_parts[0]
                or body in terminating_lines
                or re.fullmatch(
                    r"(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,}",
                    candidate_content,
                )
            ):
                break
            rows.add(starts[body])
            body += 1
    return rows


def _parse_math(text: str) -> tuple[list[MathFragment], list[MathIssue]]:
    visible, issues = _markdown_visible(text)
    table_rows = _table_row_offsets(visible)
    fragments: list[MathFragment] = []
    display_start: int | None = None
    display_quote_depth = 0
    display_has_content = False
    offset = 0

    for line in visible.splitlines(keepends=True):
        delimiter = DISPLAY_DELIMITER_RE.match(line)
        if delimiter:
            if offset in table_rows:
                issues.append(
                    MathIssue(
                        offset + delimiter.start(),
                        "GHM007",
                        "display math is not parsed inside a Markdown table; use an inline formula or move the block outside the table",
                    )
                )
                offset += len(line)
                continue
            prefix = delimiter.group("prefix")
            quote_depth = prefix.count(">")
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
                display_quote_depth = quote_depth
                display_has_content = False
            elif quote_depth == display_quote_depth:
                if not display_has_content:
                    issues.append(
                        MathIssue(
                            display_start,
                            "GHM008",
                            "display math must contain a non-empty TeX payload",
                        )
                    )
                display_start = None
                display_quote_depth = 0
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
            quote = _quote_prefix(line)
            if quote.count(">") != display_quote_depth:
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
                logical = line[len(quote) :]
                logical_offset = offset + len(quote)
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

        table_row = offset in table_rows
        for opening, closing in _inline_math_pairs(line):
            boundary = opening
            while boundary > 0 and line[boundary - 1] == " ":
                boundary -= 1
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
            elif (
                boundary < opening
                and boundary >= 2
                and line[boundary - 1] in {"@", "-"}
                and line[boundary - 2].isascii()
                and line[boundary - 2].isalnum()
            ):
                issues.append(
                    MathIssue(
                        offset + opening,
                        "GHM027",
                        "a visible space split an ASCII joined label before math; keep the complete label in one formula",
                    )
                )
            elif (
                boundary < opening
                and boundary >= 2
                and line[boundary - 2 : boundary] == "**"
                and not _escaped(line, boundary - 2)
                and not _ends_with_strong_close(line[:boundary])
            ):
                issues.append(
                    MathIssue(
                        offset + opening,
                        "GHM028",
                        "a visible space detached math from an opening strong-emphasis marker; restore **$...$** or rewrite the label",
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

    return extract_math_expressions_unchecked(text)


def extract_math_expressions_unchecked(text: str) -> list[MathExpression]:
    """Extract canonical dollar-delimited expressions without trusting TeX policy."""

    _, boundary_issues = _parse_math(text)
    boundary_issues.extend(_alternative_delimiter_issues(text))
    boundary_issues.extend(_markdown_container_issues(text))
    if boundary_issues:
        raise ValueError("trusted Markdown math boundary validation failed")

    visible, _ = _markdown_visible(text)
    expressions: list[MathExpression] = []
    display_start: int | None = None
    display_quote_depth = 0
    display_lines: list[str] = []
    offset = 0
    for line in visible.splitlines(keepends=True):
        delimiter = DISPLAY_DELIMITER_RE.match(line)
        if delimiter:
            if display_start is None:
                display_start = offset + delimiter.start()
                display_quote_depth = delimiter.group("prefix").count(">")
                display_lines = []
            else:
                expressions.append(
                    MathExpression(display_start, "\n".join(display_lines), True)
                )
                display_start = None
                display_quote_depth = 0
                display_lines = []
            offset += len(line)
            continue
        if display_start is not None:
            quote = _quote_prefix(line)
            logical = line[len(quote) :] if quote.count(">") == display_quote_depth else line
            display_lines.append(logical.rstrip("\r\n"))
            offset += len(line)
            continue

        dollars = _unescaped_dollars(line)
        for pair_start in range(0, len(dollars) - 1, 2):
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


def _tex_issues(
    fragment: MathFragment, reference_labels: frozenset[str] = frozenset()
) -> list[MathIssue]:
    issues: list[MathIssue] = []
    payload = fragment.text
    for match in re.finditer(r'\\(?:[A-Za-z]+|char"[0-9A-Fa-f]+)\{\}[ \t]*(?=[_^])', payload):
        issues.append(
            MathIssue(
                fragment.offset + match.start(),
                "GHM019",
                "an empty group detaches the following script from its mathematical base; remove only that empty group",
            )
        )
    cursor = 0
    while cursor < len(payload):
        char = payload[cursor]
        if char == "*":
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM014",
                    r"raw * is consumed as Markdown emphasis; after checking its exact role, use a standard TeX command such as \ast",
                )
            )
        if char == "_" and not _escaped(payload, cursor):
            if cursor == 0:
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM019",
                        "a subscript operator needs an explicit mathematical base",
                    )
                )
            previous_is_ascii_word = (
                cursor > 0
                and payload[cursor - 1].isascii()
                and payload[cursor - 1].isalnum()
            )
            next_is_ascii_word = (
                cursor + 1 < len(payload)
                and payload[cursor + 1].isascii()
                and payload[cursor + 1].isalnum()
            )
            previous_is_space = cursor > 0 and payload[cursor - 1] == " "
            next_is_space = cursor + 1 < len(payload) and payload[cursor + 1] == " "
            if not (previous_is_space and next_is_space) and not (
                previous_is_ascii_word and next_is_ascii_word
            ):
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM015",
                        "raw _ can pair with another Markdown emphasis delimiter; surround this subscript operator with TeX-ignored ASCII spaces",
                    )
                )
        if payload.startswith("~~", cursor):
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM021",
                    r"raw ~~ is consumed as GFM strikethrough; use a standard TeX relation or spacing command that preserves the paper's meaning",
                )
            )
        if char == "`":
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM021",
                    "raw backticks are consumed as Markdown code spans; use a standard TeX command after checking the notation",
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
            elif command not in PORTABLE_COMMANDS:
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM013",
                        f"TeX command is outside the repository's GitHub-verified profile: \\{command}",
                    )
                )
            if command in {"begin", "end"}:
                environment = re.match(r"\{([A-Za-z][A-Za-z0-9*_-]*)\}", payload[command_end:])
                if not fragment.display:
                    issues.append(
                        MathIssue(
                            fragment.offset + cursor,
                            "GHM020",
                            f"\\{command} environments are only allowed in display math",
                        )
                    )
                if environment is None:
                    issues.append(
                        MathIssue(
                            fragment.offset + cursor,
                            "GHM020",
                            f"\\{command} must be followed by an explicit environment name",
                        )
                    )
                elif environment.group(1) not in PORTABLE_ENVIRONMENTS:
                    issues.append(
                        MathIssue(
                            fragment.offset + cursor,
                            "GHM020",
                            f"environment is outside the GitHub-verified profile: {environment.group(1)}",
                        )
                    )
            elif command == "tag" and not fragment.display:
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM020",
                        r"\tag is only allowed in display math",
                    )
                )
            elif command == "char" and re.match(
                r'"(?:0023|0025|005F)\{\}', payload[command_end:]
            ) is None:
                issues.append(
                    MathIssue(
                        fragment.offset + cursor,
                        "GHM020",
                        r'\char is limited to the verified complete forms \char"0023{}, \char"0025{}, and \char"005F{}',
                    )
                )
            cursor = command_end
            continue
        if next_char not in " \t":
            issues.append(
                MathIssue(
                    fragment.offset + cursor,
                    "GHM013",
                    f"unsupported TeX control sequence after backslash: {next_char!r}",
                )
            )
        cursor = run_end + 1
    for match in re.finditer(r"(?<!\\)%", payload):
        issues.append(
            MathIssue(
                fragment.offset + match.start(),
                "GHM023",
                r'raw % starts a TeX comment and silently discards the rest of the line; use the verified \char"0025{} form for a literal percent sign',
            )
        )
    if any(issue.code == "GHM003" for issue in issues):
        issues = [issue for issue in issues if issue.code != "GHM013"]
    for match in re.finditer(r"select", payload, re.IGNORECASE):
        issues.append(
            MathIssue(
                fragment.offset + match.start(),
                "GHM016",
                r"GitHub suppresses math containing the raw token 'select'; move the word outside math or, after checking the exact text, encode it as selec{}t",
            )
        )
    for match in re.finditer(
        r"https?://|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(?<![A-Za-z0-9._%+-])@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?",
        payload,
        re.IGNORECASE,
    ):
        issues.append(
            MathIssue(
                fragment.offset + match.start(),
                "GHM022",
                "GitHub autolink or user-mention syntax changes the math node; move URLs, email addresses, and mentions outside math",
            )
        )
    for match in re.finditer(r"\[\^[^]\r\n]+\]", payload):
        issues.append(
            MathIssue(
                fragment.offset + match.start(),
                "GHM024",
                "GitHub footnote references suppress the math node; move the footnote marker outside math",
            )
        )
    reference_link_ranges: list[tuple[int, int]] = []
    markdown_link_offsets: set[int] = set()
    for match in re.finditer(
        r"!?\[(?P<label>[^]\r\n]+)\]\[(?P<target>[^]\r\n]*)\]", payload
    ):
        target = match.group("target") or match.group("label")
        if normalizeReference(target) not in reference_labels:
            continue
        markdown_link_offsets.add(match.start())
        reference_link_ranges.append(match.span())
    for match in re.finditer(r"!?\[(?!\^)([^]\r\n]+)\](?![\[(])", payload):
        if any(start <= match.start() < end for start, end in reference_link_ranges):
            continue
        normalized = normalizeReference(match.group(1))
        if normalized in reference_labels:
            markdown_link_offsets.add(match.start())
    for offset in sorted(markdown_link_offsets):
        issues.append(
            MathIssue(
                fragment.offset + offset,
                "GHM025",
                "Markdown links and images suppress the math node; move them outside math",
            )
        )
    for match in re.finditer(
        r"&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);", payload
    ):
        issues.append(
            MathIssue(
                fragment.offset + match.start(),
                "GHM026",
                "HTML entities rewrite the TeX payload before rendering; use a verified TeX command",
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
    issues.extend(_markdown_container_issues(text))
    environment: dict[str, object] = {}
    MARKDOWN.parse(text, environment)
    references = environment.get("references", {})
    reference_labels = frozenset(references) if isinstance(references, dict) else frozenset()
    for fragment in fragments:
        issues.extend(_tex_issues(fragment, reference_labels))
    ordered = sorted(issues, key=lambda issue: (issue.offset, issue.code, issue.message))
    deduplicated: list[MathIssue] = []
    seen: set[tuple[int, str, str]] = set()
    for issue in ordered:
        key = (issue.offset, issue.code, issue.message)
        if key not in seen:
            deduplicated.append(issue)
            seen.add(key)
    return deduplicated


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
