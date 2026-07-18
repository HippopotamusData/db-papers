#!/usr/bin/env python3
"""Mask Markdown syntax hidden by comments or raw HTML blocks."""

from __future__ import annotations

import argparse
import re
import string
import sys
from pathlib import Path

from markdown_it import MarkdownIt


HTML_COMMENT_OPEN = "<!--"
HTML_COMMENT_CLOSE = "-->"
BACKTICK_RUN_RE = re.compile(r"`+")
BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")
MARKDOWN_CONTROL_CHARACTERS = frozenset(string.punctuation)


def _markdown_block_ranges(
    text: str,
    token_types: set[str],
) -> list[tuple[int, int]]:
    """Return source offsets for selected CommonMark block-token types."""

    line_offsets = [0]
    for match in re.finditer(r"\n", text):
        line_offsets.append(match.end())
    line_offsets.append(len(text))

    ranges: list[tuple[int, int]] = []
    for token in MarkdownIt("commonmark").parse(text):
        if token.type not in token_types or token.map is None:
            continue
        start_line, end_line = token.map
        start = line_offsets[min(start_line, len(line_offsets) - 1)]
        end = line_offsets[min(end_line, len(line_offsets) - 1)]
        ranges.append((start, end))
    return ranges


def _block_code_ranges(text: str) -> list[tuple[int, int]]:
    """Return source offsets for CommonMark fenced and indented code blocks."""

    return _markdown_block_ranges(text, {"fence", "code_block"})


def _raw_html_block_ranges(text: str) -> list[tuple[int, int]]:
    """Return blocks where CommonMark leaves Markdown punctuation literal."""

    return _markdown_block_ranges(text, {"html_block"})


def _contains(ranges: list[tuple[int, int]], offset: int) -> bool:
    return any(start <= offset < end for start, end in ranges)


def _next_comment(
    text: str,
    cursor: int,
    block_ranges: list[tuple[int, int]],
) -> int:
    while True:
        opening = text.find(HTML_COMMENT_OPEN, cursor)
        if opening < 0:
            return -1
        containing = next(
            (
                (start, end)
                for start, end in block_ranges
                if start <= opening < end
            ),
            None,
        )
        if containing is None:
            return opening
        cursor = containing[1]


def _next_backtick(
    text: str,
    cursor: int,
    block_ranges: list[tuple[int, int]],
) -> re.Match[str] | None:
    return next(
        (
            match
            for match in BACKTICK_RUN_RE.finditer(text, cursor)
            if not _contains(block_ranges, match.start())
        ),
        None,
    )


def _comment_ranges(text: str) -> list[tuple[int, int]]:
    """Parse inline code and comments in reader-precedence order.

    A comment opener encountered before a backtick hides every delimiter inside
    that comment. Conversely, a valid code span opened first makes comment-like
    bytes literal until its matching delimiter. Pairing all backticks globally
    before finding comments lets delimiters hidden in separate comments form a
    fictitious code span and expose the later comment, so both constructs must
    be handled by one left-to-right state machine.
    """

    block_ranges = _block_code_ranges(text)
    comments: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        comment = _next_comment(text, cursor, block_ranges)
        backtick = _next_backtick(text, cursor, block_ranges)
        if comment < 0 and backtick is None:
            break
        if comment >= 0 and (
            backtick is None or comment < backtick.start()
        ):
            closing = text.find(
                HTML_COMMENT_CLOSE,
                comment + len(HTML_COMMENT_OPEN),
            )
            end = (
                len(text)
                if closing < 0
                else closing + len(HTML_COMMENT_CLOSE)
            )
            comments.append((comment, end))
            cursor = end
            continue

        assert backtick is not None
        closing_match: re.Match[str] | None = None
        for candidate in BACKTICK_RUN_RE.finditer(text, backtick.end()):
            if _contains(block_ranges, candidate.start()):
                continue
            if BLANK_LINE_RE.search(
                text,
                backtick.end(),
                candidate.start(),
            ):
                break
            if len(candidate.group()) == len(backtick.group()):
                closing_match = candidate
                break
        cursor = (
            closing_match.end()
            if closing_match is not None
            else backtick.end()
        )
    return comments


def reader_visible_markdown(text: str) -> str:
    """Mask reader-hidden Markdown syntax without moving source positions.

    Translation quality gates must reason about what a Markdown reader can see.
    Keeping every newline and byte position stable lets diagnostics still point
    to the original file. Treating an unclosed comment as hidden through EOF is
    fail-closed for coverage: hidden prose cannot inflate completeness signals.
    CommonMark raw HTML blocks keep ordinary text reader-visible but do not
    parse Markdown syntax. Their ASCII control punctuation is therefore
    neutralized, including syntax after a same-line comment close, while words
    remain available to reader-visible prose and coverage checks.
    """

    characters = list(text)
    for opening, end in _raw_html_block_ranges(text):
        for index in range(opening, end):
            if characters[index] in MARKDOWN_CONTROL_CHARACTERS:
                characters[index] = " "
    for opening, end in _comment_ranges(text):
        for index in range(opening, end):
            if characters[index] not in "\r\n":
                characters[index] = " "
    return "".join(characters)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        text = args.source.read_text(encoding="utf-8")
        args.destination.write_text(
            reader_visible_markdown(text),
            encoding="utf-8",
        )
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: cannot prepare reader-visible Markdown: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
