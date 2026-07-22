#!/usr/bin/env python3
"""Validate translation resources and emit conservative source-coverage candidates."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token
from PIL import Image, UnidentifiedImageError

from markdown_visibility import reader_visible_markdown
from reference_sections import select_reference_heading


LEGACY_IMAGE_RE = re.compile(
    r"!\[([^]]*)\]\((<[^>]+>|[^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)"
)
SOURCE_RESOURCE_PATTERNS = {
    "figure": re.compile(
        r"(?:^[ \t\f]*|[ \t]{2,})(?:Figure|Fig\.)\s*([1-9]\d*)\s*[:.]",
        re.IGNORECASE | re.MULTILINE,
    ),
    "table": re.compile(
        r"(?:^[ \t\f]*|[ \t]{2,})Table\s*([1-9]\d*)\s*[:.]",
        re.IGNORECASE | re.MULTILINE,
    ),
    "algorithm": re.compile(
        # Some proceedings print ``Algorithm 1 Name`` without a colon.  Keep
        # this anchored like a caption and reject the common prose forms so a
        # sentence such as "Algorithm 1 shows ..." is not source evidence.
        r"(?:^[ \t\f]*|[ \t]{2,})Algorithm\s*([1-9]\d*)"
        r"(?:(?:[ \t]*[:.][ \t]*)|(?:[ \t]+(?!(?:shows?|depicts?|presents?|"
        r"describes?|illustrates?|lists?|uses?|is|was|has|can|will)\b)(?=\S)))",
        re.IGNORECASE | re.MULTILINE,
    ),
}
IMAGE_ALT_NUMBER_PATTERNS = {
    "figure": re.compile(r"^\s*(?:图|Figure|Fig\.)\s*([1-9]\d*)(?:[a-z])?(?!\d)", re.IGNORECASE),
    "table": re.compile(r"^\s*(?:表|Table)\s*([1-9]\d*)(?:[a-z])?(?!\d)", re.IGNORECASE),
    "algorithm": re.compile(r"^\s*(?:算法|Algorithm)\s*([1-9]\d*)(?!\d)", re.IGNORECASE),
}
TRANSLATION_CAPTION_PATTERNS = {
    "figure": re.compile(
        r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:图|Figure|Fig\.)\s*"
        r"([1-9]\d*)(?:[a-z])?(?!\d)\s*[:：.]",
        re.IGNORECASE,
    ),
    "table": re.compile(
        r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:表|Table)\s*"
        r"([1-9]\d*)(?:[a-z])?(?!\d)\s*[:：.]",
        re.IGNORECASE,
    ),
    "algorithm": re.compile(
        r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:算法|Algorithm)\s*([1-9]\d*)(?!\d)"
        r"(?:\s*[:：.]|\s+(?!(?:展示|给出|说明|列出|描述|表明|显示|报告|中|的|为))"
        r"(?!(?:shows?|depicts?|presents?|describes?|illustrates?|lists?|uses?|is|was|has|can|will)\b)"
        r"(?=\S))",
        re.IGNORECASE,
    ),
}
SOURCE_REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.\s]+)?(?:REFERENCES|BIBLIOGRAPHY)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
REVIEW_SOURCE_REFERENCE_HEADING_RE = re.compile(
    r"^(?:[^\r\n]*?[ \t]{4,})?[ \t\f]*"
    r"(?P<heading>(?:\d+(?:\.\d+)*[.\s]+)?(?:"
    r"R(?i:[ \t]*E[ \t]*F[ \t]*E[ \t]*R[ \t]*E[ \t]*N[ \t]*C[ \t]*E[ \t]*S)|"
    r"B(?i:[ \t]*I[ \t]*B[ \t]*L[ \t]*I[ \t]*O[ \t]*G[ \t]*R[ \t]*A[ \t]*P[ \t]*H[ \t]*Y)|"
    r"C(?i:[ \t]*I[ \t]*T[ \t]*E[ \t]*D[ \t]+"
    r"A[ \t]*N[ \t]*D[ \t]+G[ \t]*E[ \t]*N[ \t]*E[ \t]*R[ \t]*A[ \t]*L[ \t]+"
    r"R[ \t]*E[ \t]*F[ \t]*E[ \t]*R[ \t]*E[ \t]*N[ \t]*C[ \t]*E[ \t]*S)"
    r"))(?=$|[ \t]{2,}\S)",
    re.MULTILINE,
)
TRANSLATION_REFERENCE_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(?:\d+(?:\.\d+)*[.\s]+)?(?:参考文献|References|Bibliography)"
    r"(?:\s*[（(](?:References|Bibliography)[）)])?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
TRANSLATION_POST_REFERENCE_CONTENT_RE = re.compile(
    r"^(?:\[\^[^\]\r\n]+\]:|#{1,6}\s+\S)",
    re.MULTILINE,
)
BRACKETED_CITATION_GROUP_RE = re.compile(
    r"\[\s*((?:[1-9]\d*(?:\s*[-–—]\s*[1-9]\d*)?"
    r"|[A-Za-z][A-Za-z0-9+_.:-]*)"
    r"(?:\s*[,;]\s*(?:[1-9]\d*(?:\s*[-–—]\s*[1-9]\d*)?"
    r"|[A-Za-z][A-Za-z0-9+_.:-]*))*)\s*\]"
)
SPLIT_BRACKETED_CITATION_RANGE_RE = re.compile(
    r"\[\s*([1-9]\d*)\s*\]\s*[-–—]\s*\[\s*([1-9]\d*)\s*\]"
)
SOURCE_ANGLE_CITATION_RE = re.compile(
    r"<\s*([A-Za-z0-9][A-Za-z0-9]{0,3})\s*>"
)
REFERENCE_ENTRY_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:\[([1-9]\d*|[A-Za-z][A-Za-z0-9+_.:-]*)\]|([1-9]\d*)\.)\s+(.+?)\s*$"
)
REFERENCE_ENTRY_PREFIX_RE = re.compile(
    r"^\s*(?:[-*]\s+)?"
    r"(?:"
    r"\[(?P<square>[1-9]\d*|[A-Za-z][A-Za-z0-9+_.:-]*)\]|"
    r"<(?P<angle>[A-Za-z0-9][A-Za-z0-9+_.:-]*)>|"
    r"\((?P<parenthesized>[1-9]\d{0,2})\)"
    r"(?=\s+[A-Z][A-Za-z0-9'’.-]{1,50},\s*[A-Za-z])|"
    r"(?P<trailing_angle>[A-Za-z][A-Za-z0-9]{0,2})>|"
    r"(?P<decimal>[1-9]\d*)\."
    r")\s+"
)
REFERENCE_ENTRY_COLUMN_RE = re.compile(
    r"(?:\t+| {4,}|\f)(?:[-*]\s+)?"
    r"(?:"
    r"\[(?P<square>[1-9]\d*|[A-Za-z][A-Za-z0-9+_.:-]*)\]|"
    r"<(?P<angle>[A-Za-z0-9][A-Za-z0-9+_.:-]*)>|"
    r"\((?P<parenthesized>[1-9]\d{0,2})\)"
    r"(?=\s+[A-Z][A-Za-z0-9'’.-]{1,50},\s*[A-Za-z])|"
    r"(?P<trailing_angle>[A-Za-z][A-Za-z0-9]{0,2})>|"
    r"(?P<decimal>[1-9]\d*)\."
    r")\s+"
)
REFERENCE_AUTHOR_KEY_PREFIX_RE = re.compile(
    r"^\s*((?:(?=[A-Za-z0-9+_.:-]*\d)[A-Za-z][A-Za-z0-9+_.:-]{2,}|"
    r"[A-Z][A-Z+_.:-]{2,}))\s+"
    r"(?=(?:[A-Z][A-Za-z'’ -]{1,50},\s*(?:[A-Z](?:\.|[ ,])|AND\b)|"
    r"O\s+S\s*/\s*V\s+S\b))"
)
REFERENCE_AUTHOR_KEY_COLUMN_RE = re.compile(
    r"(?:\t+| {4,}|\f)"
    r"((?:(?=[A-Za-z0-9+_.:-]*\d)[A-Za-z][A-Za-z0-9+_.:-]{2,}|"
    r"[A-Z][A-Z+_.:-]{2,}))\s+"
    r"(?=(?:[A-Z][A-Za-z'’ -]{1,50},\s*(?:[A-Z](?:\.|[ ,])|AND\b)|"
    r"O\s+S\s*/\s*V\s+S\b))"
)
SOURCE_LAYOUT_AUTHOR_KEY_RE = re.compile(
    r"(?:(?<= {2})|(?<=\t))"
    r"((?:(?=[A-Za-z0-9+_.:-]*\d)[A-Za-z][A-Za-z0-9+_.:-]{2,}|"
    r"[A-Z][A-Z+_.:-]{2,}))\s+"
    r"(?=(?:[A-Z][A-Za-z'’ -]{1,50},\s*(?:[A-Z](?:\.|[ ,])|AND\b)|"
    r"O\s+S\s*/\s*V\s+S\b))"
)
SOURCE_LAYOUT_BRACKETED_ENTRY_RE = re.compile(
    r"(?:"
    r"\[(?P<square>[1-9]\d*|[A-Za-z][A-Za-z0-9+_.:-]*)\]|"
    r"<(?P<angle>[A-Za-z0-9][A-Za-z0-9+_.:-]*)>|"
    r"\((?P<parenthesized>[1-9]\d{0,2})\)"
    r"(?=\s+[A-Z][A-Za-z0-9'’.-]{1,50},\s*[A-Za-z])|"
    r"(?P<trailing_angle>[A-Za-z][A-Za-z0-9]{0,2})>"
    r")\s+"
)
SOURCE_LAYOUT_DAMAGED_NUMERIC_ENTRY_RE = re.compile(
    r"(?P<boundary>^|[ \t]{2,}|\t+|\f)"
    r"(?P<marker>"
    r"\[[A-Za-z0-9.]{1,3}\]?|"
    r"\([A-Za-z0-9.]{2,4}|"
    r"(?:(?=[A-Za-z0-9.]{0,4}\d)[A-Za-z0-9.]{2,5}?)|"
    r"PI|VI|Ml|WI"
    r")"
    r"(?:[ \t]+|(?=[A-Z][A-Za-z'’.-]{1,50}[.,]))"
    r"(?P<body>[A-Z][A-Za-z'’.-]{1,50}[.,]\s*[A-Za-z])"
)
SOURCE_LAYOUT_AUTHOR_RE = re.compile(
    r"^(?:(?:[A-Z]\.(?:-[A-Z]\.)?\s*){1,4}[A-Z][A-Za-z'’.-]+"
    r"|[A-Z][A-Za-z'’.-]+,\s*(?:[A-Z]\.|AND\b))"
)
SOURCE_LAYOUT_CORPORATE_REFERENCE_RE = re.compile(
    r"^(?:"
    r"[A-Z][A-Za-z0-9&+.'’/-]*(?:\s+[A-Z][A-Za-z0-9&+.'’/-]*){1,12}\."
    r"(?:\s+\S.*)?|"
    r"[A-Z][A-Za-z0-9&+.'’/-]*\.\s+"
    r"(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\.?"
    r")$"
)
SOURCE_LAYOUT_BIBLIOGRAPHIC_CUE_RE = re.compile(
    r"\b(?:(?:18|19|20)\d{2}[a-z]?|pp?\.|vol\.?|proc\.?|"
    r"proceedings|journal|conference|doi|https?://|technical report|"
    r"tech\.?\s+rep\.?)\b",
    re.IGNORECASE,
)
TRUNCATED_NUMERIC_RANGE_RE = re.compile(
    r"\b\d{1,7}\s*[-–—]\s*(?:[.,;:)]\s*)?$"
)
REFERENCE_URL_RE = re.compile(r"https?://[^\s<>]+")
SOURCE_CODE_LINE_RE = re.compile(
    r"^\s*(?:(?:SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|JOIN|CREATE|INSERT|UPDATE|DELETE)\b"
    r"|(?:for|while|if|else|return|class|struct|public|private|void|int|long|double)\b.*[;{}]?)",
    re.IGNORECASE,
)
DISPLAY_MATH_PATTERNS = (
    re.compile(r"\$\$(.+?)\$\$", re.DOTALL),
    re.compile(r"\\\[(.+?)\\\]", re.DOTALL),
    re.compile(r"```(?:math|latex|tex)\s*\n(.+?)^```\s*$", re.IGNORECASE | re.MULTILINE | re.DOTALL),
    re.compile(
        r"\\begin\{(?:equation|align|gather|multline)\*?\}(.+?)"
        r"\\end\{(?:equation|align|gather|multline)\*?\}",
        re.DOTALL,
    ),
)
EQUATION_NUMBER_PATTERN = r"[1-9]\d*(?:\.\d+)*"
EQUATION_NUMBER_RE = re.compile(
    rf"(?:\\tag\{{({EQUATION_NUMBER_PATTERN})\}}|\(({EQUATION_NUMBER_PATTERN})\))"
)
MATH_SIGNAL_RE = re.compile(
    r"(?:=|≤|≥|∑|∏|\\(?:sum|prod|frac|sqrt|min|max|log)\b|[+*/^_])",
    re.IGNORECASE,
)
REFERENCE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+._:/-]{2,}")
REFERENCE_TOKEN_STOPWORDS = {
    "and",
    "the",
    "for",
    "from",
    "with",
    "into",
    "using",
    "proceedings",
    "conference",
    "journal",
    "vol",
    "volume",
    "pages",
}
SOURCE_ABSTRACT_HEADING_RE = re.compile(r"^\s*ABSTRACT\s*$", re.IGNORECASE | re.MULTILINE)
SOURCE_END_HEADING_RE = re.compile(
    r"^\s*(?:[1-9]\d*\.?\s+)?(?:CONCLUSIONS?|SUMMARY)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
TRANSLATION_ABSTRACT_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*"
    r"(?:摘要|Abstract)"
    r"(?:\s*[（(]\s*(?:摘要|Abstract)\s*[)）])?"
    r"\s*$",
    re.IGNORECASE | re.MULTILINE,
)
TRANSLATION_END_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(?:[1-9]\d*\.?\s+)?"
    r"(?:结论|总结|Conclusions?|Summary)"
    r"(?:\s*[（(]\s*(?:结论|总结|Conclusions?|Summary)\s*[)）])?"
    r"\s*$",
    re.IGNORECASE | re.MULTILINE,
)
SOURCE_NUMBERED_HEADING_RE = re.compile(
    r"^\s*([1-9]\d*)\.?\s+([A-Z][A-Za-z0-9 &'()/:,\-]{2,})\s*$",
    re.MULTILINE,
)
TRANSLATION_NUMBERED_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*([1-9]\d*)(?:\.|\s)", re.MULTILINE
)
MIN_USEFUL_IMAGE_AREA = 256
MIN_USEFUL_VISIBLE_PIXELS = 64
MIN_USEFUL_PIXEL_RATIO_PER_MILLE = 1
REFERENCE_AUTHOR_KEY_STOPWORDS = frozenset({"AND", "FOR", "THE", "WITH"})
AUTHOR_KEY_OCR_LEADING_TOKEN_LIMIT = 6
AUTHOR_KEY_OCR_CONTEXT_TOKEN_LIMIT = 16
AUTHOR_KEY_OCR_MIN_LEADING_MATCHES = 3
AUTHOR_KEY_OCR_MIN_CONTEXT_MATCHES = 4
AUTHOR_KEY_OCR_MIN_LEADING_MARGIN = 1
NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_ENTRIES = 10
NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_COLUMN_GAP = 16
NUMERIC_BIBLIOGRAPHY_RECOVERY_MAX_COLUMN_SPREAD = 8
NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_RIGHT_MARKERS = 3
NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_LEFT_MARKERS = 2
NUMERIC_BIBLIOGRAPHY_RECOVERY_BLANK_RUN = 3
NUMERIC_BIBLIOGRAPHY_RECOVERY_MAX_TOKEN_WINDOW = 40
NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_ORDERED_TOKENS = 4
NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_RARE_TOKENS = 2
NUMERIC_BIBLIOGRAPHY_RECOVERY_RARE_DOCUMENT_FREQUENCY = 4
NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_ANCHOR_LENGTH = 4


def _minimum_useful_pixels(area: int) -> int:
    """Scale image-content evidence with canvas size, with a small-image floor."""

    proportional_minimum = (
        area * MIN_USEFUL_PIXEL_RATIO_PER_MILLE + 999
    ) // 1000
    return max(MIN_USEFUL_VISIBLE_PIXELS, proportional_minimum)


@dataclass
class _MarkdownStructure:
    image_links: list[tuple[str, str]]
    image_markers_by_line: dict[int, set[str]]
    inline_lines: set[int]
    fence_markers_by_start: dict[int, str]
    fence_markers_by_end: dict[int, str]


def _canonical_image_target(target: str) -> str:
    """Normalize one local Markdown target for identity and filesystem checks."""

    decoded = unquote(target)
    split = urlsplit(decoded)
    if split.scheme or split.netloc or split.query or split.fragment:
        return decoded
    return PurePosixPath(decoded).as_posix()


def _useful_fence_payload(token: Token, lines: list[str]) -> bool:
    """Require a closed CommonMark fence with substantive payload."""

    if token.map is None or not token.markup:
        return False
    opening_index, end_index = token.map
    if end_index <= opening_index + 1 or end_index > len(lines):
        return False
    closing = lines[end_index - 1].strip()
    fence_character = re.escape(token.markup[0])
    if re.fullmatch(
        rf"{fence_character}{{{len(token.markup)},}}[ \t]*",
        closing,
    ) is None:
        return False
    payload = token.content
    compact = "".join(payload.split())
    payload_tokens = re.findall(
        r"[A-Za-z_][A-Za-z0-9_]*|[\u3400-\u9fff]+|\d+(?:\.\d+)?",
        payload,
    )
    return bool(
        len(compact) >= 8
        and sum(character.isalnum() for character in compact) >= 4
        and len(payload_tokens) >= 2
    )


def _commonmark_structure(text: str) -> _MarkdownStructure:
    """Index reader-active Markdown constructs from the CommonMark parse."""

    text = reader_visible_markdown(text)
    lines = text.splitlines()
    links: list[tuple[str, str]] = []
    markers_by_line: dict[int, set[str]] = {}
    inline_lines: set[int] = set()
    fences_by_start: dict[int, str] = {}
    fences_by_end: dict[int, str] = {}

    for token in MarkdownIt("commonmark").parse(text):
        if token.type == "inline" and token.map is not None:
            start_line, end_line = token.map
            inline_lines.update(range(start_line, end_line))
            image_markers: set[str] = set()
            for child in token.children or []:
                if child.type != "image":
                    continue
                target = child.attrGet("src")
                if target is None:
                    continue
                target = _canonical_image_target(target)
                links.append((child.content, target))
                image_markers.add(f"image:{target}")
            if image_markers and end_line == start_line + 1:
                markers_by_line[start_line] = image_markers
        elif (
            token.type == "fence"
            and token.map is not None
            and _useful_fence_payload(token, lines)
        ):
            opening_index, end_index = token.map
            marker = f"fence-line:{opening_index + 1}"
            fences_by_start[opening_index] = marker
            fences_by_end[end_index - 1] = marker

    return _MarkdownStructure(
        image_links=links,
        image_markers_by_line=markers_by_line,
        inline_lines=inline_lines,
        fence_markers_by_start=fences_by_start,
        fence_markers_by_end=fences_by_end,
    )


def image_links(translation_text: str) -> list[tuple[str, str]]:
    """Return only image nodes produced by the CommonMark inline parser."""

    return _commonmark_structure(translation_text).image_links


def _lexical_absolute(path: Path) -> Path:
    """Return an absolute path without resolving symlinks."""

    return Path(os.path.abspath(os.fspath(path)))


def _git_ignored_paths(paths: Iterable[Path], cwd: Path) -> set[Path]:
    """Return ignored paths with one batched ``git check-ignore`` invocation.

    A paper copied outside a Git worktree is a supported validator/test input, so
    a non-zero result other than the normal "not ignored" status is treated as
    no ignore evidence rather than as a validation failure.
    """

    candidates = sorted({_lexical_absolute(path) for path in paths}, key=os.fspath)
    if not candidates:
        return set()
    payload = b"\0".join(os.fsencode(path) for path in candidates) + b"\0"
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(cwd), "check-ignore", "-z", "--stdin"],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return set()
    if result.returncode not in (0, 1):
        return set()
    return {
        _lexical_absolute(Path(os.fsdecode(value)))
        for value in result.stdout.split(b"\0")
        if value
    }


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    cells: list[str] = []
    cell: list[str] = []
    backslash_run = 0
    last_character_was_delimiter = False
    for character in stripped:
        is_delimiter = character == "|" and backslash_run % 2 == 0
        if is_delimiter:
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(character)
        last_character_was_delimiter = is_delimiter
        if character == "\\":
            backslash_run += 1
        else:
            backslash_run = 0
    cells.append("".join(cell).strip())
    if stripped.startswith("|"):
        cells.pop(0)
    if last_character_was_delimiter:
        cells.pop()
    return cells


def _is_table_delimiter(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell) is not None for cell in cells
    )


def _markdown_table_marker(
    lines: list[str],
    start_index: int,
    inline_lines: set[int],
) -> str | None:
    end_index = start_index
    while (
        end_index < len(lines)
        and len(_table_cells(lines[end_index])) >= 2
    ):
        end_index += 1
    if any(
        line_index not in inline_lines
        for line_index in range(start_index, end_index)
    ):
        return None
    table_lines = lines[start_index:end_index]
    if len(table_lines) < 3 or not _is_table_delimiter(table_lines[1]):
        return None
    header = _table_cells(table_lines[0])
    if not header or len(_table_cells(table_lines[1])) != len(header):
        return None
    data_rows = [_table_cells(row) for row in table_lines[2:]]
    if any(len(row) != len(header) for row in data_rows):
        return None
    nonempty_data_cells = sum(bool(cell) for row in data_rows for cell in row)
    if nonempty_data_cells < 2:
        return None
    return f"table-line:{start_index + 1}"


def _preceding_payload_marker(
    lines: list[str],
    caption_index: int,
    kind: str,
    structure: _MarkdownStructure,
) -> str | None:
    """Recognize a formal payload immediately before its caption.

    The archive commonly follows the Markdown convention ``image`` then
    ``caption``. Tables and fenced figures/algorithms may use the same order. Only an
    adjacent payload, with at most blank lines between it and the caption, is
    accepted, so an earlier prose cross-reference cannot satisfy coverage.
    """

    payload_index = caption_index - 1
    while payload_index >= 0 and not lines[payload_index].strip():
        payload_index -= 1
    if payload_index < 0:
        return None

    image_markers = structure.image_markers_by_line.get(payload_index)
    if image_markers and len(image_markers) == 1:
        return next(iter(image_markers))

    if kind == "table" and len(_table_cells(lines[payload_index])) >= 2:
        table_start = payload_index
        while (
            table_start > 0
            and len(_table_cells(lines[table_start - 1])) >= 2
        ):
            table_start -= 1
        return _markdown_table_marker(
            lines,
            table_start,
            structure.inline_lines,
        )

    if kind in {"figure", "algorithm"}:
        return structure.fence_markers_by_end.get(payload_index)
    return None


def _following_payload_marker(
    lines: list[str],
    caption_index: int,
    kind: str,
    structure: _MarkdownStructure,
) -> str | None:
    payload_index = caption_index + 1
    while payload_index < len(lines) and not lines[payload_index].strip():
        payload_index += 1
    if payload_index >= len(lines):
        return None

    image_markers = structure.image_markers_by_line.get(payload_index)
    if image_markers and len(image_markers) == 1:
        return next(iter(image_markers))
    if kind == "table" and len(_table_cells(lines[payload_index])) >= 2:
        return _markdown_table_marker(
            lines,
            payload_index,
            structure.inline_lines,
        )
    if kind in {"figure", "algorithm"}:
        return structure.fence_markers_by_start.get(payload_index)
    return None


def formal_resource_representations(translation_text: str) -> dict[str, dict[int, set[str]]]:
    """Return formal translation-side representations keyed by type and number.

    Ordinary prose references never enter this map.  Evidence must be either a
    numbered image candidate, or a caption immediately paired with the expected
    payload (fence/image for figures, table/image for tables, fence/image for algorithms).
    Markers identify the payload so a numbered image paired with its caption is
    counted once rather than twice. For figures, a numbered image takes precedence
    over an adjacent fenced transcription because the two can be complementary.
    """

    structure = _commonmark_structure(translation_text)
    representations: dict[str, dict[int, set[str]]] = {
        kind: {} for kind in SOURCE_RESOURCE_PATTERNS
    }

    for alt, target in structure.image_links:
        for kind, pattern in IMAGE_ALT_NUMBER_PATTERNS.items():
            match = pattern.match(alt)
            if match:
                number = int(match.group(1))
                representations[kind].setdefault(number, set()).add(f"image:{target}")

    lines = translation_text.splitlines()
    for kind, caption_pattern in TRANSLATION_CAPTION_PATTERNS.items():
        for index, line in enumerate(lines):
            if index not in structure.inline_lines:
                continue
            caption = caption_pattern.match(line)
            if not caption:
                continue
            payload_index = index + 1
            while payload_index < len(lines) and not lines[payload_index].strip():
                payload_index += 1
            marker: str | None = None
            same_line_images = structure.image_markers_by_line.get(index)
            if same_line_images and len(same_line_images) == 1:
                marker = next(iter(same_line_images))
            if marker is None:
                preceding = _preceding_payload_marker(
                    lines,
                    index,
                    kind,
                    structure,
                )
                following = _following_payload_marker(
                    lines,
                    index,
                    kind,
                    structure,
                )
                if kind == "table":
                    marker = next(
                        (
                            candidate
                            for candidate in (preceding, following)
                            if candidate is not None
                            and candidate.startswith("table-line:")
                        ),
                        preceding or following,
                    )
                elif kind == "algorithm":
                    marker = next(
                        (
                            candidate
                            for candidate in (preceding, following)
                            if candidate is not None
                            and candidate.startswith("fence-line:")
                        ),
                        preceding or following,
                    )
                else:
                    marker = preceding or following
            if marker is not None:
                number = int(caption.group(1))
                representations[kind].setdefault(number, set()).add(marker)

    for markers in representations["figure"].values():
        if any(marker.startswith("image:") for marker in markers):
            markers.difference_update(
                {marker for marker in markers if marker.startswith("fence-line:")}
            )

    owners: dict[str, set[tuple[str, int]]] = {}
    for kind, numbered in representations.items():
        for number, markers in numbered.items():
            for marker in markers:
                owners.setdefault(marker, set()).add((kind, number))
    ambiguous_markers = {
        marker for marker, marker_owners in owners.items()
        if len(marker_owners) > 1
    }
    if ambiguous_markers:
        for numbered in representations.values():
            for number in list(numbered):
                numbered[number].difference_update(ambiguous_markers)
                if not numbered[number]:
                    del numbered[number]
    return representations


def _legacy_image_links(translation_text: str) -> list[tuple[str, str]]:
    """Parse exactly the image syntax used by the frozen receiptless ledger."""

    return [
        (alt, target[1:-1] if target.startswith("<") else target)
        for alt, target in LEGACY_IMAGE_RE.findall(translation_text)
    ]


def _legacy_image_marker(line: str) -> str | None:
    match = LEGACY_IMAGE_RE.search(line)
    if not match:
        return None
    target = match.group(2)
    if target.startswith("<"):
        target = target[1:-1]
    return f"image:{target}"


def _legacy_preceding_payload_marker(
    lines: list[str],
    caption_index: int,
    kind: str,
) -> str | None:
    payload_index = caption_index - 1
    while payload_index >= 0 and not lines[payload_index].strip():
        payload_index -= 1
    if payload_index < 0:
        return None

    marker = _legacy_image_marker(lines[payload_index].lstrip())
    if marker is not None:
        return marker

    if kind == "table" and lines[payload_index].lstrip().startswith("|"):
        table_start = payload_index
        while (
            table_start > 0
            and lines[table_start - 1].lstrip().startswith("|")
        ):
            table_start -= 1
        table_lines = lines[table_start : payload_index + 1]
        if len(table_lines) >= 2 and re.match(
            r"^\s*\|?\s*:?-{3,}",
            table_lines[1],
        ):
            return f"table-line:{table_start + 1}"

    if (
        kind in {"figure", "algorithm"}
        and lines[payload_index].lstrip().startswith("```")
    ):
        opening_index = payload_index - 1
        while opening_index >= 0:
            if lines[opening_index].lstrip().startswith("```"):
                if any(
                    line.strip()
                    for line in lines[opening_index + 1 : payload_index]
                ):
                    return f"fence-line:{opening_index + 1}"
                return None
            opening_index -= 1
    return None


def _legacy_formal_resource_representations(
    translation_text: str,
) -> dict[str, dict[int, set[str]]]:
    """Replay the exact formal-resource mapping used by receiptless records."""

    representations: dict[str, dict[int, set[str]]] = {
        kind: {} for kind in SOURCE_RESOURCE_PATTERNS
    }

    for alt, target in _legacy_image_links(translation_text):
        for kind, pattern in IMAGE_ALT_NUMBER_PATTERNS.items():
            match = pattern.match(alt)
            if match:
                number = int(match.group(1))
                representations[kind].setdefault(number, set()).add(
                    f"image:{target}"
                )

    lines = translation_text.splitlines()
    for kind, caption_pattern in TRANSLATION_CAPTION_PATTERNS.items():
        for index, line in enumerate(lines):
            caption = caption_pattern.match(line)
            if not caption:
                continue
            payload_index = index + 1
            while (
                payload_index < len(lines)
                and not lines[payload_index].strip()
            ):
                payload_index += 1
            marker: str | None = None
            if payload_index < len(lines):
                payload = lines[payload_index].lstrip()
                if kind in {"figure", "table", "algorithm"}:
                    marker = _legacy_image_marker(payload)
                if (
                    marker is None
                    and kind == "table"
                    and payload.startswith("|")
                ):
                    delimiter_index = payload_index + 1
                    if delimiter_index < len(lines) and re.match(
                        r"^\s*\|?\s*:?-{3,}",
                        lines[delimiter_index],
                    ):
                        marker = f"table-line:{payload_index + 1}"
                if (
                    marker is None
                    and kind in {"figure", "algorithm"}
                    and payload.startswith("```")
                ):
                    marker = f"fence-line:{payload_index + 1}"
            if marker is None:
                marker = _legacy_preceding_payload_marker(
                    lines,
                    index,
                    kind,
                )
            if marker is not None:
                number = int(caption.group(1))
                representations[kind].setdefault(number, set()).add(marker)

    for markers in representations["figure"].values():
        if any(marker.startswith("image:") for marker in markers):
            markers.difference_update(
                {
                    marker
                    for marker in markers
                    if marker.startswith("fence-line:")
                }
            )
    return representations


def _legacy_validate_images(
    paper_dir: Path,
    translation_text: str,
    allow_whole_page: bool,
) -> tuple[list[str], list[str]]:
    """Replay the exact image checks used by receiptless accepted records."""

    errors: list[str] = []
    risks: list[str] = []
    links = _legacy_image_links(translation_text)
    targets = [target for _alt, target in links]
    duplicates = sorted(
        target for target, count in Counter(targets).items() if count > 1
    )
    if duplicates:
        errors.append(f"duplicate image references: {', '.join(duplicates)}")

    paper_root = paper_dir.resolve()
    assets = paper_dir / "assets"
    assets_root = assets.resolve()
    asset_paths = (
        sorted(
            (
                path
                for path in assets.rglob("*")
                if path.is_file() or path.is_symlink()
            ),
            key=os.fspath,
        )
        if assets.is_dir()
        else []
    )
    linked_paths = [
        paper_dir.joinpath(*PurePosixPath(target).parts)
        for _alt, target in links
        if PurePosixPath(target).parts
        and PurePosixPath(target).parts[0] == "assets"
        and ".." not in PurePosixPath(target).parts
    ]
    ignored_paths = _git_ignored_paths(
        [*asset_paths, *linked_paths],
        paper_dir,
    )

    referenced: set[Path] = set()
    for _alt, target in links:
        posix = PurePosixPath(target)
        if target.startswith(("http://", "https://", "data:")):
            errors.append(
                f"image link must stay inside this paper's assets/: {target}"
            )
            continue
        if (
            posix.is_absolute()
            or not posix.parts
            or posix.parts[0] != "assets"
            or ".." in posix.parts
        ):
            errors.append(
                f"image link must use a safe assets/ relative path: {target}"
            )
            continue
        lexical = paper_dir.joinpath(*posix.parts)
        lexical_absolute = _lexical_absolute(lexical)
        referenced.add(lexical_absolute)
        if lexical_absolute in ignored_paths:
            errors.append(
                f"translation references git-ignored asset: {target}"
            )
        resolved = lexical.resolve()
        if (
            not assets_root.is_relative_to(paper_root)
            or not resolved.is_relative_to(assets_root)
        ):
            errors.append(
                f"image link resolves outside this paper's assets/: {target}"
            )
            continue
        if not lexical.is_file():
            errors.append(f"broken image reference: {target}")
            continue
        if not allow_whole_page and re.search(
            r"(?:^|[-_.])(?:source\.pdf|original[-_]?page|page[-_]?\d+)",
            lexical.name,
            re.IGNORECASE,
        ):
            errors.append(
                f"whole-page or extraction-residue image is not allowed: {target}"
            )
        try:
            with Image.open(lexical) as image:
                image.verify()
        except (OSError, UnidentifiedImageError) as exc:
            errors.append(f"image is not decodable: {target} ({exc})")

    for asset in asset_paths:
        asset_absolute = _lexical_absolute(asset)
        if asset_absolute in ignored_paths:
            continue
        if asset_absolute not in referenced:
            risks.append(
                "orphan asset is not referenced by translation.md: "
                f"{asset.relative_to(paper_dir)}"
            )
    return errors, risks


def validate_images(
    paper_dir: Path,
    translation_text: str,
    allow_whole_page: bool,
    *,
    legacy_resource_structure: bool = False,
) -> tuple[list[str], list[str]]:
    if legacy_resource_structure:
        return _legacy_validate_images(
            paper_dir,
            translation_text,
            allow_whole_page,
        )
    errors: list[str] = []
    risks: list[str] = []
    links = image_links(translation_text)
    targets = [target for _alt, target in links]
    duplicates = sorted(target for target, count in Counter(targets).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate image references: {', '.join(duplicates)}")

    paper_root = paper_dir.resolve()
    assets = paper_dir / "assets"
    assets_root = assets.resolve()
    asset_paths = (
        sorted(
            (path for path in assets.rglob("*") if path.is_file() or path.is_symlink()),
            key=os.fspath,
        )
        if assets.is_dir()
        else []
    )
    linked_paths = [
        paper_dir.joinpath(*PurePosixPath(target).parts)
        for _alt, target in links
        if PurePosixPath(target).parts
        and PurePosixPath(target).parts[0] == "assets"
        and ".." not in PurePosixPath(target).parts
    ]
    ignored_paths = _git_ignored_paths([*asset_paths, *linked_paths], paper_dir)

    referenced: set[Path] = set()
    file_identities: dict[tuple[int, int], list[str]] = {}
    for _alt, target in links:
        if "\x00" in target:
            errors.append(
                f"image link contains a forbidden NUL byte: {target!r}"
            )
            continue
        posix = PurePosixPath(target)
        if target.startswith(("http://", "https://", "data:")):
            errors.append(f"image link must stay inside this paper's assets/: {target}")
            continue
        if posix.is_absolute() or not posix.parts or posix.parts[0] != "assets" or ".." in posix.parts:
            errors.append(f"image link must use a safe assets/ relative path: {target}")
            continue
        lexical = paper_dir.joinpath(*posix.parts)
        lexical_absolute = _lexical_absolute(lexical)
        referenced.add(lexical_absolute)
        if lexical_absolute in ignored_paths:
            errors.append(f"translation references git-ignored asset: {target}")
        resolved = lexical.resolve()
        if not assets_root.is_relative_to(paper_root) or not resolved.is_relative_to(assets_root):
            errors.append(f"image link resolves outside this paper's assets/: {target}")
            continue
        if not lexical.is_file():
            errors.append(f"broken image reference: {target}")
            continue
        try:
            stat_result = lexical.stat()
            file_identities.setdefault(
                (stat_result.st_dev, stat_result.st_ino),
                [],
            ).append(target)
        except OSError as exc:
            errors.append(f"cannot stat image reference: {target} ({exc})")
            continue
        if not allow_whole_page and re.search(r"(?:^|[-_.])(?:source\.pdf|original[-_]?page|page[-_]?\d+)", lexical.name, re.IGNORECASE):
            errors.append(f"whole-page or extraction-residue image is not allowed: {target}")
        try:
            with Image.open(lexical) as image:
                image.verify()
            with Image.open(lexical) as image:
                width, height = image.size
                area = width * height
                minimum_useful_pixels = _minimum_useful_pixels(area)
                if area < MIN_USEFUL_IMAGE_AREA:
                    errors.append(
                        f"image is too small to be a useful resource: {target} "
                        f"({width}x{height}; minimum area={MIN_USEFUL_IMAGE_AREA})"
                    )
                rgba = image.convert("RGBA")
                alpha = rgba.getchannel("A")
                visible_pixels = sum(alpha.histogram()[1:])
                if visible_pixels < minimum_useful_pixels:
                    errors.append(
                        f"image has too few visible pixels to be a useful resource: "
                        f"{target} ({visible_pixels}; minimum={minimum_useful_pixels})"
                    )
                flattened = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                flattened.alpha_composite(rgba)
                flattened_rgb = flattened.convert("RGB")
                extrema = flattened_rgb.getextrema()
                if all(low == high for low, high in extrema):
                    errors.append(f"image has only one pixel color: {target}")
                quantized = flattened_rgb.quantize(colors=16)
                color_counts = quantized.getcolors() or []
                non_dominant_pixels = (
                    flattened_rgb.width * flattened_rgb.height
                    - max((count for count, _color in color_counts), default=0)
                )
                if non_dominant_pixels < minimum_useful_pixels:
                    errors.append(
                        "image has too little visible variation to be a useful "
                        f"resource: {target} ({non_dominant_pixels}; "
                        f"minimum={minimum_useful_pixels})"
                    )
        except (OSError, UnidentifiedImageError) as exc:
            errors.append(f"image is not decodable: {target} ({exc})")

    for identity_targets in file_identities.values():
        if len(identity_targets) < 2:
            continue
        errors.append(
            "multiple image references resolve to the same asset file: "
            + ", ".join(sorted(identity_targets))
        )

    for asset in asset_paths:
        asset_absolute = _lexical_absolute(asset)
        if asset_absolute in ignored_paths:
            continue
        if asset_absolute not in referenced:
            risks.append(f"orphan asset is not referenced by translation.md: {asset.relative_to(paper_dir)}")
    return errors, risks


def _reference_section(
    text: str,
    heading_pattern: re.Pattern[str],
    *,
    require_single_evidence: bool = True,
) -> tuple[bool, str]:
    heading = select_reference_heading(
        text,
        heading_pattern,
        require_single_evidence=require_single_evidence,
    )
    return (bool(heading), text[heading.end() :] if heading else "")


def _legacy_reference_section(
    text: str,
    heading_pattern: re.Pattern[str],
) -> tuple[bool, str]:
    """Preserve the frozen boundary used by receiptless accepted records."""

    heading = heading_pattern.search(text)
    return (bool(heading), text[heading.end() :] if heading else "")


def _reference_id(bracketed: str | None, decimal: str | None) -> str:
    return (bracketed or decimal or "").casefold()


def _is_author_initials(identifier: str) -> bool:
    """Return whether an apparent author key is actually dotted initials."""

    return re.fullmatch(r"(?:[A-Z]\.){1,4}", identifier, re.IGNORECASE) is not None


def _delimited_reference_marker(
    match: re.Match[str],
) -> tuple[str | None, str | None]:
    """Return one paired/legacy delimiter identifier and decimal identifier."""

    delimited = next(
        (
            value
            for value in (
                match.group("square"),
                match.group("angle"),
                match.group("parenthesized"),
                match.group("trailing_angle"),
            )
            if value is not None
        ),
        None,
    )
    return delimited, match.groupdict().get("decimal")


def _reference_line_starts(
    line: str,
) -> list[tuple[int, int, str | None, str | None]]:
    """Return bibliography entry starts, including layout-text second columns."""

    starts: list[tuple[int, int, str | None, str | None]] = []
    prefix = REFERENCE_ENTRY_PREFIX_RE.match(line)
    search_start = 0
    if prefix is not None:
        delimited, decimal = _delimited_reference_marker(prefix)
        starts.append(
            (
                prefix.start(),
                prefix.end(),
                delimited,
                decimal,
            )
        )
        search_start = prefix.end()
    else:
        author_key_prefix = REFERENCE_AUTHOR_KEY_PREFIX_RE.match(line)
        if (
            author_key_prefix is not None
            and author_key_prefix.group(1).upper()
            not in REFERENCE_AUTHOR_KEY_STOPWORDS
            and not _is_author_initials(author_key_prefix.group(1))
        ):
            starts.append(
                (
                    author_key_prefix.start(),
                    author_key_prefix.end(),
                    author_key_prefix.group(1),
                    None,
                )
            )
            search_start = author_key_prefix.end()
    for match in REFERENCE_ENTRY_COLUMN_RE.finditer(line, search_start):
        delimited, decimal = _delimited_reference_marker(match)
        starts.append(
            (
                match.start(),
                match.end(),
                delimited,
                decimal,
            )
        )
    for match in REFERENCE_AUTHOR_KEY_COLUMN_RE.finditer(line, search_start):
        if match.group(1).upper() in REFERENCE_AUTHOR_KEY_STOPWORDS:
            continue
        if _is_author_initials(match.group(1)):
            continue
        if any(
            body_start == match.end()
            for _start, body_start, _bracketed, _decimal in starts
        ):
            continue
        starts.append(
            (
                match.start(),
                match.end(),
                match.group(1),
                None,
            )
        )
    for match in SOURCE_LAYOUT_AUTHOR_KEY_RE.finditer(line, search_start):
        if (
            match.group(1).upper() in REFERENCE_AUTHOR_KEY_STOPWORDS
            or _is_author_initials(match.group(1))
            or match.start() < 32
            or any(
            body_start == match.end()
            for _start, body_start, _bracketed, _decimal in starts
            )
        ):
            continue
        starts.append(
            (
                match.start(),
                match.end(),
                match.group(1),
                None,
            )
        )
    for match in SOURCE_LAYOUT_BRACKETED_ENTRY_RE.finditer(line, search_start):
        if match.start() < 32 or any(
            body_start == match.end()
            for _start, body_start, _bracketed, _decimal in starts
        ):
            continue
        body = line[match.end() :].lstrip()
        if not (
            SOURCE_LAYOUT_AUTHOR_RE.match(_reference_structure_text(body))
            or (
                match.start() >= 70
                and SOURCE_LAYOUT_BIBLIOGRAPHIC_CUE_RE.search(body)
            )
        ):
            continue
        starts.append(
            (
                match.start(),
                match.end(),
                _delimited_reference_marker(match)[0],
                None,
            )
        )
    for match in SOURCE_LAYOUT_DAMAGED_NUMERIC_ENTRY_RE.finditer(
        line,
        search_start,
    ):
        marker = match.group("marker")
        bare_marker = marker.lstrip("[(").rstrip("]")
        if (
            marker.count(".") >= 2
            or re.fullmatch(r"(?:18|19|20)\d{2}", bare_marker)
        ):
            # Two-column OCR can align author initials or venue years where a
            # damaged reference marker would normally appear.  Neither is
            # credible entry-boundary evidence.
            continue
        marker_start = match.start("marker")
        body_start = match.start("body")
        if any(
            existing_body_start in {marker_start, body_start}
            for _start, existing_body_start, _bracketed, _decimal in starts
        ):
            continue
        starts.append(
            (
                marker_start,
                body_start,
                marker,
                None,
            )
        )
    starts.sort(key=lambda item: item[0])
    return starts


def _page_after_form_feed_has_reference_start(
    lines: list[str],
    line_index: int,
) -> bool:
    """Return whether the immediately following PDF page continues references."""

    _before_feed, _separator, after_feed = lines[line_index].partition("\f")
    page_lines = [after_feed]
    for line in lines[line_index + 1 :]:
        before_next_feed, separator, _after_next_feed = line.partition("\f")
        page_lines.append(before_next_feed)
        if separator:
            break
    return any(_reference_line_starts(line) for line in page_lines)


def _reference_entries(section: str) -> list[tuple[str, str]]:
    # Preserve form-feed page boundaries: ``str.splitlines()`` silently drops
    # them, which can make a final reference absorb an unrelated appendix.
    lines = section.split("\n")
    raw_starts = [_reference_line_starts(line) for line in lines]
    has_bracketed_numeric_style = any(
        bracketed and bracketed.isdigit()
        for starts in raw_starts
        for _start, _body_start, bracketed, _decimal in starts
    )
    decimal_candidates = [
        int(decimal)
        for starts in raw_starts
        for _start, _body_start, _bracketed, decimal in starts
        if decimal and len(decimal) <= 3
    ]
    decimal_limit = max(5, len(decimal_candidates) * 2)

    entries: list[tuple[str, str]] = []
    current_id: str | None = None
    current_lines: list[str] = []
    for line_index, (line, starts) in enumerate(
        zip(lines, raw_starts, strict=True)
    ):
        if (
            "\f" in line
            and current_id is not None
            and not _page_after_form_feed_has_reference_start(lines, line_index)
        ):
            entries.append((current_id, " ".join(current_lines).strip()))
            return entries
        valid_starts = [
            start
            for start in starts
            if not (
                start[3]
                and (
                    has_bracketed_numeric_style
                    or len(start[3]) > 3
                    or int(start[3]) > decimal_limit
                )
            )
        ]
        if valid_starts:
            prefix = line[: valid_starts[0][0]].strip()
            if (
                current_id is not None
                and prefix
                and not prefix.startswith("#")
            ):
                current_lines.append(prefix)
        for index, (start, body_start, bracketed, decimal) in enumerate(
            valid_starts
        ):
            if current_id is not None:
                entries.append((current_id, " ".join(current_lines).strip()))
            body_end = (
                valid_starts[index + 1][0]
                if index + 1 < len(valid_starts)
                else len(line)
            )
            current_id = _reference_id(bracketed, decimal)
            current_lines = [line[body_start:body_end].strip()]
        if (
            not valid_starts
            and current_id is not None
            and line.strip()
            and not line.lstrip().startswith("#")
        ):
            current_lines.append(line.strip())
    if current_id is not None:
        entries.append((current_id, " ".join(current_lines).strip()))
    return entries


def _legacy_reference_entries(section: str) -> list[tuple[str, str]]:
    """Parse exactly the single-column entry shape used by the legacy ledger."""

    lines = section.splitlines()
    raw_matches = [REFERENCE_ENTRY_RE.match(line) for line in lines]
    has_bracketed_numeric_style = any(
        match and match.group(1) and match.group(1).isdigit()
        for match in raw_matches
    )
    decimal_candidates = [
        int(match.group(2))
        for match in raw_matches
        if match and match.group(2) and len(match.group(2)) <= 3
    ]
    decimal_limit = max(5, len(decimal_candidates) * 2)

    entries: list[tuple[str, str]] = []
    current_id: str | None = None
    current_lines: list[str] = []
    for line, match in zip(lines, raw_matches, strict=True):
        if match and match.group(2):
            decimal_value = int(match.group(2))
            if (
                has_bracketed_numeric_style
                or len(match.group(2)) > 3
                or decimal_value > decimal_limit
            ):
                match = None
        if match:
            if current_id is not None:
                entries.append((current_id, " ".join(current_lines).strip()))
            current_id = _reference_id(match.group(1), match.group(2))
            current_lines = [match.group(3).strip()]
        elif (
            current_id is not None
            and line.strip()
            and not line.lstrip().startswith("#")
        ):
            current_lines.append(line.strip())
    if current_id is not None:
        entries.append((current_id, " ".join(current_lines).strip()))
    return entries


def _same_page_preheading_reference_column(
    text: str,
    heading_start: int,
) -> tuple[str, str]:
    """Recover a right bibliography column emitted before its left heading.

    ``pdftotext -layout`` interleaves rows from both PDF columns. When the
    References heading sits low in the left column, right-column entries above
    it consequently precede the heading in extracted text. Recover only a
    repeated, author-shaped pattern and mask those starts from the body used
    for inline-citation comparison.
    """

    page_start = text.rfind("\f", 0, heading_start) + 1
    page_prefix = text[page_start:heading_start]
    candidates: list[tuple[int, int, str]] = []
    corporate_candidates: list[tuple[int, int, str, int]] = []
    strong_numeric_identifiers: list[int] = []
    offset = 0
    for line_with_ending in page_prefix.splitlines(keepends=True):
        line = line_with_ending.rstrip("\r\n")
        line_candidates: list[tuple[int, str]] = []
        for match in SOURCE_LAYOUT_BRACKETED_ENTRY_RE.finditer(line):
            if match.start() < 32:
                continue
            candidate = line[match.start() :].strip()
            body = line[match.end() :].lstrip()
            if SOURCE_LAYOUT_AUTHOR_RE.match(_reference_structure_text(body)):
                line_candidates.append((match.start(), candidate))
                identifier, _decimal = _delimited_reference_marker(match)
                if identifier is not None and identifier.isdigit():
                    strong_numeric_identifiers.append(int(identifier))
            elif SOURCE_LAYOUT_CORPORATE_REFERENCE_RE.match(
                _reference_structure_text(body)
            ):
                identifier, _decimal = _delimited_reference_marker(match)
                if identifier is not None and identifier.isdigit():
                    corporate_candidates.append(
                        (
                            offset + match.start(),
                            offset + len(line),
                            candidate,
                            int(identifier),
                        )
                    )
            elif SOURCE_LAYOUT_BIBLIOGRAPHIC_CUE_RE.search(body):
                # Some corporate/web references have no author-shaped prefix
                # and preserve product casing poorly in the PDF text layer,
                # for example ``[9] Cloudera impala. http://...``.  Treat
                # them only as deferred gap-fill candidates; the contiguous
                # surrounding numeric sequence below still decides whether
                # they belong to the right-hand bibliography column.
                identifier, _decimal = _delimited_reference_marker(match)
                if identifier is not None and identifier.isdigit():
                    corporate_candidates.append(
                        (
                            offset + match.start(),
                            offset + len(line),
                            candidate,
                            int(identifier),
                        )
                    )
        for match in SOURCE_LAYOUT_AUTHOR_KEY_RE.finditer(line):
            if match.group(1).upper() in REFERENCE_AUTHOR_KEY_STOPWORDS:
                continue
            if _is_author_initials(match.group(1)):
                continue
            if re.search(r"[ \t]{2,}$", line[: match.start()]) is None:
                continue
            candidate = line[match.start() :].strip()
            line_candidates.append((match.start(), candidate))
        if line_candidates:
            start, candidate = min(line_candidates, key=lambda item: item[0])
            candidates.append(
                (offset + start, offset + len(line), candidate)
            )
        offset += len(line_with_ending)
    if len(strong_numeric_identifiers) >= 2:
        lower = min(strong_numeric_identifiers)
        upper = max(strong_numeric_identifiers)
        candidates.extend(
            (start, end, candidate)
            for start, end, candidate, identifier in corporate_candidates
            if lower < identifier <= upper + 1
        )
        candidates.sort(key=lambda item: item[0])
    if len(candidates) < 2:
        return "", text[:heading_start]

    recovered_section = "\n".join(
        candidate for _start, _end, candidate in candidates
    )
    masked_prefix = list(page_prefix)
    for start, end, _candidate in candidates:
        masked_prefix[start:end] = " " * (end - start)
    masked_body = text[:page_start] + "".join(masked_prefix)
    return recovered_section, masked_body


def _review_source_reference_parts(
    source_text: str,
) -> tuple[re.Match[str] | None, str, str]:
    """Return heading, bibliography text, and body for review-grade checks."""

    heading = select_reference_heading(
        source_text,
        REVIEW_SOURCE_REFERENCE_HEADING_RE,
    )
    if heading is None:
        return None, "", source_text
    heading_start = heading.start("heading")
    heading_end = heading.end("heading")
    recovered, masked_body = _same_page_preheading_reference_column(
        source_text,
        heading_start,
    )
    section = source_text[heading_end:]
    if recovered:
        section = recovered + "\n" + section
    return heading, section, masked_body


def _reference_structure_text(text: str) -> str:
    """Normalize author text only for structural bibliography recognition."""

    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )


def _reference_tokens(text: str) -> set[str]:
    return {
        token.casefold().strip(".,:;/")
        for token in REFERENCE_TOKEN_RE.findall(text)
        if token.casefold().strip(".,:;/") not in REFERENCE_TOKEN_STOPWORDS
    }


def _reference_token_sequence(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in REFERENCE_TOKEN_RE.findall(text):
        token = raw_token.casefold().strip(".,:;/")
        if (
            token in REFERENCE_TOKEN_STOPWORDS
            or re.search(r"[a-z]", token, re.IGNORECASE) is None
        ):
            continue
        tokens.append(token)
    return tokens


def _complete_numeric_translation_entries(
    translation_section: str,
) -> list[tuple[str, str]] | None:
    """Return a clean, complete ``1..N`` translation bibliography.

    Recovery may use translation bibliography content only as review-candidate
    discovery evidence.  Keep that evidence bounded to the bibliography itself
    so a following author biography or footnote cannot manufacture matches.
    """

    post_reference = TRANSLATION_POST_REFERENCE_CONTENT_RE.search(
        translation_section
    )
    clean_section = (
        translation_section[: post_reference.start()]
        if post_reference is not None
        else translation_section
    )
    entries = _reference_entries(clean_section)
    if len(entries) < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_ENTRIES:
        return None
    expected = [str(index) for index in range(1, len(entries) + 1)]
    if [identifier for identifier, _body in entries] != expected:
        return None
    if any(not body.strip() for _identifier, body in entries):
        return None
    return entries


def _two_column_bibliography_tokens(
    source_text: str,
    source_heading: re.Match[str],
) -> list[str] | None:
    """Reconstruct one same-page two-column bibliography in reading order.

    ``pdftotext -layout`` emits rows, not columns.  Infer the right column only
    from two tight clusters of parsed marker-body starts separated by a large
    layout gap.  The left column begins below the selected heading; the right
    column ends at a real blank run after its last marker.  Any weak geometry
    leaves the ordinary reference errors untouched.
    """

    page_start = source_text.rfind("\f", 0, source_heading.start("heading")) + 1
    page_end = source_text.find("\f", source_heading.end("heading"))
    if page_end < 0:
        page_end = len(source_text)
    page = source_text[page_start:page_end]
    heading_offset = source_heading.start("heading") - page_start
    if heading_offset < 0 or heading_offset > len(page):
        return None
    heading_line = page[:heading_offset].count("\n")
    lines = page.split("\n")

    marker_starts: list[tuple[int, int]] = []
    for line_index, line in enumerate(lines):
        for _start, body_start, delimited, _decimal in _reference_line_starts(
            line
        ):
            if delimited is not None:
                marker_starts.append((body_start, line_index))
    if len(marker_starts) < (
        NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_LEFT_MARKERS
        + NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_RIGHT_MARKERS
    ):
        return None

    positions = sorted(body_start for body_start, _line in marker_starts)
    gaps = [
        (positions[index + 1] - positions[index], index)
        for index in range(len(positions) - 1)
    ]
    largest_gap, split_index = max(gaps, default=(0, -1))
    if largest_gap < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_COLUMN_GAP:
        return None
    left_positions = positions[: split_index + 1]
    right_positions = positions[split_index + 1 :]
    if (
        len(right_positions) < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_RIGHT_MARKERS
        or max(right_positions) - min(right_positions)
        > NUMERIC_BIBLIOGRAPHY_RECOVERY_MAX_COLUMN_SPREAD
    ):
        return None

    right_boundary = right_positions[len(right_positions) // 2]
    left_marker_rows = {
        line_index
        for body_start, line_index in marker_starts
        if body_start in left_positions and line_index > heading_line
    }
    if len(left_marker_rows) < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_LEFT_MARKERS:
        return None
    right_marker_rows = [
        line_index
        for body_start, line_index in marker_starts
        if abs(body_start - right_boundary)
        <= NUMERIC_BIBLIOGRAPHY_RECOVERY_MAX_COLUMN_SPREAD
    ]
    if len(right_marker_rows) < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_RIGHT_MARKERS:
        return None

    last_right_marker_row = max(right_marker_rows)
    right_stop: int | None = None
    blank_run = NUMERIC_BIBLIOGRAPHY_RECOVERY_BLANK_RUN
    for line_index in range(
        last_right_marker_row + 1,
        len(lines) - blank_run + 1,
    ):
        if all(
            not lines[candidate][right_boundary:].strip()
            for candidate in range(line_index, line_index + blank_run)
        ):
            right_stop = line_index
            break
    if right_stop is None:
        return None

    left_column = "\n".join(
        line[:right_boundary] for line in lines[heading_line + 1 :]
    )
    right_column = "\n".join(
        line[right_boundary:] for line in lines[:right_stop]
    )
    ordered_text = _reference_structure_text(
        left_column + "\n" + right_column
    )
    tokens = _reference_token_sequence(ordered_text)
    return tokens or None


@dataclass(frozen=True)
class _NumericReferenceMatch:
    positions: tuple[int, ...]
    ordered_token_count: int
    rare_token_count: int

    @property
    def start(self) -> int:
        return self.positions[0]

    @property
    def end(self) -> int:
        return self.positions[-1]

    @property
    def score(self) -> tuple[int, int, int]:
        return (
            self.ordered_token_count,
            self.rare_token_count,
            -(self.end - self.start + 1),
        )


def _ordered_distinct_reference_matches(
    translation_tokens: list[str],
    source_tokens: list[str],
    *,
    source_offset: int = 0,
) -> list[tuple[str, int]]:
    """Return distinct matched tokens and their strictly increasing indices."""

    distinct_translation_tokens = list(dict.fromkeys(translation_tokens))
    matches: list[tuple[str, int]] = []
    source_cursor = 0
    for token in distinct_translation_tokens:
        try:
            source_index = source_tokens.index(token, source_cursor)
        except ValueError:
            continue
        matches.append((token, source_offset + source_index))
        source_cursor = source_index + 1
    return matches


def _numeric_recovery_match_chain(
    source_tokens: list[str],
    translation_entries: list[tuple[str, str]],
) -> list[_NumericReferenceMatch] | None:
    """Bind every item to a globally non-overlapping ordered proof chain."""

    translation_tokens = {
        identifier: _reference_token_sequence(
            _reference_structure_text(body)
        )
        for identifier, body in translation_entries
    }
    translation_document_frequency = Counter(
        token
        for tokens in translation_tokens.values()
        for token in set(tokens)
    )
    source_counts = Counter(source_tokens)
    source_positions: dict[str, int] = {
        token: index
        for index, token in enumerate(source_tokens)
        if source_counts[token] == 1
    }

    candidate_layers: list[list[_NumericReferenceMatch]] = []
    previous_anchor_end = -1
    for identifier, _body in translation_entries:
        tokens = translation_tokens[identifier]
        token_set = set(tokens)
        anchors = {
            token
            for token in token_set
            if (
                len(token) >= NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_ANCHOR_LENGTH
                and translation_document_frequency[token] == 1
                and token in source_positions
            )
        }
        if not anchors:
            return None
        anchor_positions = sorted(source_positions[token] for token in anchors)
        anchor_start = anchor_positions[0]
        anchor_end = anchor_positions[-1]
        if (
            anchor_start <= previous_anchor_end
            or anchor_end - anchor_start + 1
            > NUMERIC_BIBLIOGRAPHY_RECOVERY_MAX_TOKEN_WINDOW
        ):
            return None

        rare_tokens = {
            token
            for token in token_set
            if (
                len(token) >= NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_ANCHOR_LENGTH
                and translation_document_frequency[token]
                <= NUMERIC_BIBLIOGRAPHY_RECOVERY_RARE_DOCUMENT_FREQUENCY
            )
        }
        candidates_by_positions: dict[
            tuple[int, ...], _NumericReferenceMatch
        ] = {}
        earliest_start = max(
            0,
            anchor_end - NUMERIC_BIBLIOGRAPHY_RECOVERY_MAX_TOKEN_WINDOW + 1,
        )
        for window_start in range(earliest_start, anchor_start + 1):
            window_end = min(
                len(source_tokens),
                window_start + NUMERIC_BIBLIOGRAPHY_RECOVERY_MAX_TOKEN_WINDOW,
            )
            if anchor_end >= window_end:
                continue
            matches = _ordered_distinct_reference_matches(
                tokens,
                source_tokens[window_start:window_end],
                source_offset=window_start,
            )
            for match_start in range(len(matches)):
                proof_tokens: set[str] = set()
                for match_end in range(match_start, len(matches)):
                    token, _position = matches[match_end]
                    proof_tokens.add(token)
                    if (
                        len(proof_tokens)
                        < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_ORDERED_TOKENS
                        or len(proof_tokens & rare_tokens)
                        < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_RARE_TOKENS
                        or not anchors <= proof_tokens
                    ):
                        continue
                    matched_positions = tuple(
                        position
                        for _token, position in matches[
                            match_start : match_end + 1
                        ]
                    )
                    if any(
                        left >= right
                        for left, right in zip(
                            matched_positions,
                            matched_positions[1:],
                        )
                    ):
                        continue
                    candidate = _NumericReferenceMatch(
                        positions=matched_positions,
                        ordered_token_count=len(proof_tokens),
                        rare_token_count=len(proof_tokens & rare_tokens),
                    )
                    candidates_by_positions[matched_positions] = candidate
        if not candidates_by_positions:
            return None
        candidate_layers.append(
            sorted(
                candidates_by_positions.values(),
                key=lambda candidate: (
                    candidate.start,
                    candidate.end,
                    candidate.positions,
                ),
            )
        )
        previous_anchor_end = anchor_end

    # Dynamic programming is required here: the locally highest-scoring proof
    # can overlap the next entry even when a lower-scoring local proof permits
    # a complete chain.  Compatibility is therefore part of selection, not a
    # post-hoc check of the already-chosen windows.
    states: list[
        tuple[tuple[int, int, int], tuple[_NumericReferenceMatch, ...]]
    ] = [
        (candidate.score, (candidate,))
        for candidate in candidate_layers[0]
    ]
    for candidates in candidate_layers[1:]:
        next_states: list[
            tuple[tuple[int, int, int], tuple[_NumericReferenceMatch, ...]]
        ] = []
        for candidate in candidates:
            compatible = [
                (score, chain)
                for score, chain in states
                if candidate.start > chain[-1].end
            ]
            if not compatible:
                continue
            previous_score, previous_chain = max(
                compatible,
                key=lambda state: (
                    state[0],
                    tuple(
                        (-match.start, -match.end, match.positions)
                        for match in state[1]
                    ),
                ),
            )
            next_states.append(
                (
                    tuple(
                        left + right
                        for left, right in zip(
                            previous_score,
                            candidate.score,
                            strict=True,
                        )
                    ),
                    previous_chain + (candidate,),
                )
            )
        if not next_states:
            return None
        states = next_states

    _score, selected_chain = max(
        states,
        key=lambda state: (
            state[0],
            tuple(
                (-match.start, -match.end, match.positions)
                for match in state[1]
            ),
        ),
    )
    if any(
        current.start <= previous.end
        for previous, current in zip(
            selected_chain,
            selected_chain[1:],
        )
    ):
        return None
    return list(selected_chain)


def _parsed_numeric_reference_mappings(
    parsed_source_entries: list[tuple[str, str]],
    translation_entries: list[tuple[str, str]],
) -> list[tuple[str, str]] | None:
    """Cross-check every surviving source marker against entry content."""

    source_counts = Counter(
        identifier for identifier, _body in parsed_source_entries
    )
    if (
        len(parsed_source_entries)
        < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_RIGHT_MARKERS
        or any(count != 1 for count in source_counts.values())
    ):
        return None
    translation_tokens = {
        identifier: set(
            _reference_token_sequence(_reference_structure_text(body))[
                :AUTHOR_KEY_OCR_CONTEXT_TOKEN_LIMIT
            ]
        )
        for identifier, body in translation_entries
    }
    mappings: list[tuple[str, str]] = []
    mapped_targets: set[str] = set()
    for source_identifier, source_body in parsed_source_entries:
        source_tokens = _reference_token_sequence(
            _reference_structure_text(source_body)
        )
        leading_tokens = set(
            source_tokens[:AUTHOR_KEY_OCR_LEADING_TOKEN_LIMIT]
        )
        context_tokens = set(
            source_tokens[:AUTHOR_KEY_OCR_CONTEXT_TOKEN_LIMIT]
        )
        scores = sorted(
            [
                (
                    len(leading_tokens & target_tokens),
                    len(context_tokens & target_tokens),
                    target_identifier,
                )
                for target_identifier, target_tokens in translation_tokens.items()
            ],
            reverse=True,
        )
        best_leading, best_context, target_identifier = scores[0]
        second_leading = scores[1][0] if len(scores) > 1 else 0
        if (
            best_leading < AUTHOR_KEY_OCR_MIN_LEADING_MATCHES
            or best_context < AUTHOR_KEY_OCR_MIN_CONTEXT_MATCHES
            or best_leading - second_leading
            < AUTHOR_KEY_OCR_MIN_LEADING_MARGIN
            or target_identifier in mapped_targets
            or int(target_identifier)
            not in _numeric_reference_ocr_candidates(source_identifier)
        ):
            return None
        mappings.append((source_identifier, target_identifier))
        mapped_targets.add(target_identifier)
    return sorted(mappings, key=lambda mapping: int(mapping[1]))


def _recover_complete_numeric_bibliography(
    source_text: str,
    source_heading: re.Match[str],
    parsed_source_entries: list[tuple[str, str]],
    translation_entries: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[str], dict[str, str]] | None:
    """Recover all numeric items, or recover none, from independent evidence."""

    entry_count = len(translation_entries)
    if entry_count < NUMERIC_BIBLIOGRAPHY_RECOVERY_MIN_ENTRIES:
        return None
    expected_identifiers = {str(index) for index in range(1, entry_count + 1)}
    if (
        len(parsed_source_entries) == entry_count
        and {identifier for identifier, _body in parsed_source_entries}
        == expected_identifiers
    ):
        return None

    source_tokens = _two_column_bibliography_tokens(
        source_text,
        source_heading,
    )
    if source_tokens is None:
        return None
    match_chain = _numeric_recovery_match_chain(
        source_tokens,
        translation_entries,
    )
    if match_chain is None:
        return None
    marker_mappings = _parsed_numeric_reference_mappings(
        parsed_source_entries,
        translation_entries,
    )
    if marker_mappings is None:
        return None

    match_centers = [
        (match.start + match.end) // 2
        for match in match_chain
    ]
    boundaries = [0]
    boundaries.extend(
        (left_center + right_center) // 2 + 1
        for left_center, right_center in zip(
            match_centers,
            match_centers[1:],
        )
    )
    boundaries.append(len(source_tokens))
    recovered_entries = [
        (
            str(index),
            " ".join(source_tokens[boundaries[index - 1] : boundaries[index]]),
        )
        for index in range(1, entry_count + 1)
    ]
    if any(not body for _identifier, body in recovered_entries):
        return None

    mapping_text = ", ".join(
        f"{source_identifier}->{target_identifier}"
        for source_identifier, target_identifier in marker_mappings
    )
    risk = (
        f"source numeric references 1-{entry_count} were recovered by complete "
        "ordered two-column bibliography-content evidence; parsed markers: "
        + mapping_text
    )
    return (
        recovered_entries,
        [risk],
        dict(marker_mappings),
    )


def _numeric_reference_ocr_candidates(identifier: str) -> set[int]:
    """Return numeric readings for one short, visibly damaged entry marker."""

    if identifier.isdigit() and len(identifier) <= 2:
        return {int(identifier)}
    compact = identifier.casefold().strip("[]()<>").replace(".", "")
    if not compact or len(compact) > 5:
        return set()
    variants = {compact}
    removable_leading = frozenset({"r", "p", "v", "m", "w", "i", "l", "1"})
    removable_trailing = frozenset({"i", "l", "1"})
    if compact[0] in removable_leading:
        variants.add(compact[1:])
    if compact[-1] in removable_trailing:
        variants.add(compact[:-1])
    if (
        len(compact) >= 2
        and compact[0] in removable_leading
        and compact[-1] in removable_trailing
    ):
        variants.add(compact[1:-1])

    translation = str.maketrans({"i": "1", "l": "1", "o": "0", "s": "5"})
    candidates: set[int] = set()
    for variant in variants:
        normalized = variant.translate(translation)
        if normalized.isdigit() and int(normalized) > 0:
            candidates.add(int(normalized))
    return candidates


def _normalize_complete_damaged_numeric_series(
    entries: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[str]] | None:
    """Recover a complete bibliography with delimiter-heavy scan OCR.

    Some old two-column scans turn ``[1]`` into markers such as ``[II``,
    ``PI``, or ``r31``.  Recovery is allowed only when a long leading run is
    positionally anchored, at least three fifths of that run independently
    agrees with its expected number, all later damaged markers have a unique
    remaining numeric reading, and the final identifiers are exactly ``1..N``.
    """

    entry_count = len(entries)
    if entry_count < 10:
        return None
    candidate_sets = [
        _numeric_reference_ocr_candidates(identifier)
        for identifier, _body in entries
    ]
    prefix_length = 0
    prefix_evidence = 0
    prefix_outliers = 0
    for index, ((identifier, _body), candidates) in enumerate(
        zip(entries, candidate_sets, strict=True),
        start=1,
    ):
        if (
            identifier.isdigit()
            and 1 <= int(identifier) <= entry_count
            and int(identifier) != index
        ):
            break
        prefix_length = index
        if index in candidates:
            prefix_evidence += 1
        else:
            prefix_outliers += 1
            if len(identifier) > 5 or not re.fullmatch(
                r"[\[\]()<>A-Za-z0-9.]+",
                identifier,
            ):
                return None

    if (
        prefix_length < 10
        or prefix_evidence * 5 < prefix_length * 3
        or prefix_outliers > 8
    ):
        return None

    assigned: list[int | None] = [None] * entry_count
    for index in range(prefix_length):
        assigned[index] = index + 1
    occupied = set(range(1, prefix_length + 1))
    for index in range(prefix_length, entry_count):
        identifier = entries[index][0]
        if identifier.isdigit() and 1 <= int(identifier) <= entry_count:
            value = int(identifier)
            if value in occupied:
                return None
            assigned[index] = value
            occupied.add(value)

    unresolved = {
        index: {
            value
            for value in candidate_sets[index]
            if 1 <= value <= entry_count and value not in occupied
        }
        for index in range(prefix_length, entry_count)
        if assigned[index] is None
    }
    while unresolved:
        singles = [
            (index, next(iter(candidates)))
            for index, candidates in unresolved.items()
            if len(candidates) == 1
        ]
        if not singles:
            return None
        for index, value in singles:
            if value in occupied:
                return None
            assigned[index] = value
            occupied.add(value)
            del unresolved[index]
        for candidates in unresolved.values():
            candidates.difference_update(value for _index, value in singles)
            if not candidates:
                return None

    if any(value is None for value in assigned):
        return None
    numeric_assigned = [int(value) for value in assigned if value is not None]
    if set(numeric_assigned) != set(range(1, entry_count + 1)):
        return None
    normalized = [
        (str(value), body)
        for value, (_identifier, body) in zip(
            numeric_assigned,
            entries,
            strict=True,
        )
    ]
    mappings = ", ".join(
        f"{identifier}->{value}"
        for value, (identifier, _body) in zip(
            numeric_assigned,
            entries,
            strict=True,
        )
        if identifier != str(value)
    )
    if not mappings:
        return None
    return normalized, [
        "source reference identifiers were normalized by complete ordered "
        f"delimiter-OCR evidence: {mappings}"
    ]


def _normalize_source_reference_ocr(
    entries: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[str]]:
    """Normalize only strongly constrained OCR damage in numeric identifiers.

    Old scanned papers occasionally expose a visible numeric bibliography as
    ``[i], [2], ...`` in the PDF text layer.  Only normalize when exactly one
    such lookalike exists, no real ``1`` exists, every other identifier is
    numeric, and the result is the complete contiguous series ``1..N``.  This
    keeps author-key bibliographies untouched and still emits review evidence.

    A second path handles heavily damaged delimiter glyphs in long, otherwise
    positional numeric series. It requires at least six unique entries, at
    least 70 percent exact position/identifier agreement, at most four short
    outliers, and rejects an outlier that is another plausible in-range number.
    The remaining identifiers are normalized to their positions and surfaced
    as review risks rather than accepted silently.
    """

    complete_series = _normalize_complete_damaged_numeric_series(entries)
    if complete_series is not None:
        return complete_series

    identifiers = [identifier for identifier, _body in entries]
    candidates = [
        index
        for index, identifier in enumerate(identifiers)
        if identifier in {"i", "l"}
    ]
    if len(candidates) == 1 and "1" not in identifiers:
        candidate_index = candidates[0]
        normalized_identifiers = identifiers.copy()
        normalized_identifiers[candidate_index] = "1"
        if all(identifier.isdigit() for identifier in normalized_identifiers):
            numeric_identifiers = [
                int(identifier) for identifier in normalized_identifiers
            ]
            if sorted(numeric_identifiers) == list(
                range(1, len(entries) + 1)
            ):
                normalized = entries.copy()
                original, body = normalized[candidate_index]
                normalized[candidate_index] = ("1", body)
                return normalized, [
                    f"source reference identifier {original} was normalized to 1 "
                    "as a contiguous numeric-series OCR candidate"
                ]

    entry_count = len(entries)
    if (
        entry_count < 6
        or len(set(identifiers)) != entry_count
    ):
        return entries, []
    expected = [str(index) for index in range(1, entry_count + 1)]
    mismatches = [
        index
        for index, (identifier, expected_identifier) in enumerate(
            zip(identifiers, expected, strict=True)
        )
        if identifier != expected_identifier
    ]
    exact_count = entry_count - len(mismatches)
    minimum_exact = (entry_count * 7 + 9) // 10
    maximum_outliers = min(4, entry_count // 3)
    if (
        not mismatches
        or exact_count < minimum_exact
        or len(mismatches) > maximum_outliers
    ):
        return entries, []
    for index in mismatches:
        identifier = identifiers[index]
        if len(identifier) > 2 or not identifier.isalnum():
            return entries, []
        if identifier.isdigit() and 1 <= int(identifier) <= entry_count:
            return entries, []

    normalized = [
        (expected_identifier, body)
        for expected_identifier, (_identifier, body) in zip(
            expected,
            entries,
            strict=True,
        )
    ]
    mappings = ", ".join(
        f"{identifiers[index]}->{expected[index]}" for index in mismatches
    )
    return normalized, [
        "source reference identifiers were normalized by ordered contiguous "
        f"OCR evidence: {mappings}"
    ]


def _source_author_key_ocr_normalization(
    source_entries: list[tuple[str, str]],
    translation_entries: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[str], dict[str, str]]:
    """Normalize author-key OCR only with unique leading-content evidence.

    Layout extraction can interleave both bibliography columns in one parsed
    body.  The beginning of that body still belongs to the entry whose marker
    was parsed, so leading tokens carry more authority than later tokens.  The
    mapping is deliberately all-or-nothing: weak evidence, a tied best match,
    duplicate identifiers, or any target collision leaves every source entry
    unchanged so the ordinary missing-reference gate remains deterministic.
    """

    source_counts = Counter(identifier for identifier, _body in source_entries)
    translation_counts = Counter(
        identifier for identifier, _body in translation_entries
    )
    if any(count != 1 for count in source_counts.values()) or any(
        count != 1 for count in translation_counts.values()
    ):
        return source_entries, [], {}

    source_identifiers = set(source_counts)
    translation_identifiers = set(translation_counts)
    unmatched_source_candidates = [
        (identifier, body)
        for identifier, body in source_entries
        if identifier not in translation_identifiers
        and not identifier.isdigit()
        and re.search(r"[a-z]", identifier, re.IGNORECASE)
    ]
    if not unmatched_source_candidates:
        return source_entries, [], {}
    if any(
        re.fullmatch(
            r"[a-z][a-z0-9+_.:-]{0,63}",
            identifier,
            re.IGNORECASE,
        )
        is None
        for identifier, _body in unmatched_source_candidates
    ):
        return source_entries, [], {}
    source_candidates = unmatched_source_candidates

    unmatched_translation_candidates = [
        (identifier, body)
        for identifier, body in translation_entries
        if identifier not in source_identifiers
        and not identifier.isdigit()
        and re.search(r"[a-z]", identifier, re.IGNORECASE)
    ]
    if not unmatched_translation_candidates or any(
        re.fullmatch(
            r"[a-z][a-z0-9+_.:-]{0,63}",
            identifier,
            re.IGNORECASE,
        )
        is None
        for identifier, _body in unmatched_translation_candidates
    ):
        return source_entries, [], {}
    translation_candidates = unmatched_translation_candidates

    mappings: dict[str, str] = {}
    for source_identifier, source_body in source_candidates:
        source_tokens = _reference_token_sequence(source_body)
        leading_tokens = set(
            source_tokens[:AUTHOR_KEY_OCR_LEADING_TOKEN_LIMIT]
        )
        context_tokens = set(
            source_tokens[:AUTHOR_KEY_OCR_CONTEXT_TOKEN_LIMIT]
        )
        scores: list[tuple[int, int, str]] = []
        for translation_identifier, translation_body in translation_candidates:
            translation_tokens = set(
                _reference_token_sequence(translation_body)[
                    :AUTHOR_KEY_OCR_CONTEXT_TOKEN_LIMIT
                ]
            )
            scores.append(
                (
                    len(leading_tokens & translation_tokens),
                    len(context_tokens & translation_tokens),
                    translation_identifier,
                )
            )
        scores.sort(reverse=True)
        best_leading, best_context, best_identifier = scores[0]
        second_leading = scores[1][0] if len(scores) > 1 else 0
        if (
            best_leading < AUTHOR_KEY_OCR_MIN_LEADING_MATCHES
            or best_context < AUTHOR_KEY_OCR_MIN_CONTEXT_MATCHES
            or best_leading - second_leading
            < AUTHOR_KEY_OCR_MIN_LEADING_MARGIN
        ):
            return source_entries, [], {}
        mappings[source_identifier] = best_identifier

    if len(set(mappings.values())) != len(mappings):
        return source_entries, [], {}

    normalized = [
        (mappings.get(identifier, identifier), body)
        for identifier, body in source_entries
    ]
    if len({identifier for identifier, _body in normalized}) != len(normalized):
        return source_entries, [], {}

    mapping_text = ", ".join(
        f"{source_identifier}->{mappings[source_identifier]}"
        for source_identifier in sorted(mappings)
    )
    return (
        normalized,
        [
            "source author-key reference identifiers were normalized by unique "
            f"bibliography-content OCR evidence: {mapping_text}"
        ],
        mappings,
    )


def _normalize_source_author_key_ocr(
    source_entries: list[tuple[str, str]],
    translation_entries: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[str]]:
    normalized, risks, _mappings = _source_author_key_ocr_normalization(
        source_entries,
        translation_entries,
    )
    return normalized, risks


def _citation_identifiers(
    text: str,
    reference_ids: set[str],
    *,
    include_source_angle_ocr: bool = False,
) -> set[str]:
    """Return bracketed body identifiers that belong to the bibliography.

    Restricting candidates to identifiers that occur in the selected
    bibliography keeps ordinary bracketed prose out of the result. Numeric
    groups and ranges are expanded so ``[1, 3]``, ``[1-3]``, and ``[1]-[3]``
    can be compared at identifier granularity. This remains review evidence,
    not proof: an interval such as ``[2, 6]`` can resemble a citation group.
    """

    identifiers: set[str] = set()

    def add_numeric_range(start_text: str, end_text: str) -> None:
        start = int(start_text)
        end = int(end_text)
        if start > end or end - start > 1000:
            return
        identifiers.update(
            str(value)
            for value in range(start, end + 1)
            if str(value) in reference_ids
        )

    for match in SPLIT_BRACKETED_CITATION_RANGE_RE.finditer(text):
        add_numeric_range(match.group(1), match.group(2))

    for match in BRACKETED_CITATION_GROUP_RE.finditer(text):
        group = match.group(1)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9+_.:-]*", group):
            identifier = group.casefold()
            if identifier in reference_ids:
                identifiers.add(identifier)
            continue
        for item in re.split(r"\s*[,;]\s*", group):
            numeric_item = re.fullmatch(
                r"([1-9]\d*)(?:\s*[-–—]\s*([1-9]\d*))?",
                item,
            )
            if numeric_item is None:
                identifier = item.casefold()
                if identifier in reference_ids:
                    identifiers.add(identifier)
                continue
            start, end = numeric_item.groups()
            if end is not None:
                add_numeric_range(start, end)
            elif start in reference_ids:
                identifiers.add(start)
    if include_source_angle_ocr:
        angle_ocr_aliases = {
            "i": "1",
            "l": "1",
            "a": "8",
            "cs": "9",
            "io": "10",
            "i0": "10",
            "lo": "10",
            "l0": "10",
        }
        for match in SOURCE_ANGLE_CITATION_RE.finditer(text):
            raw_identifier = match.group(1).casefold()
            identifier = angle_ocr_aliases.get(
                raw_identifier,
                raw_identifier,
            )
            if identifier in reference_ids:
                identifiers.add(identifier)
    return identifiers


def _translation_citation_body(
    translation_text: str,
    reference_heading: re.Match[str],
) -> str:
    """Exclude bibliography entries while retaining trailing footnotes/end matter."""

    prefix = translation_text[: reference_heading.start()]
    suffix = translation_text[reference_heading.end() :]
    post_reference = TRANSLATION_POST_REFERENCE_CONTENT_RE.search(suffix)
    if post_reference is None:
        return prefix
    return prefix + "\n" + suffix[post_reference.start() :]


def _inline_citation_findings(
    source_text: str,
    translation_text: str,
) -> list[str]:
    """Surface bibliography-backed source citations absent from the body."""

    source_heading, source_section, source_body = _review_source_reference_parts(
        source_text
    )
    translation_heading = select_reference_heading(
        translation_text,
        TRANSLATION_REFERENCE_HEADING_RE,
        require_single_evidence=False,
    )
    if source_heading is None or translation_heading is None:
        return []

    parsed_source_entries = _reference_entries(source_section)
    source_entries = parsed_source_entries
    source_entries, _ocr_risks = _normalize_source_reference_ocr(source_entries)
    translation_section = translation_text[translation_heading.end() :]
    translation_entries = _reference_entries(translation_section)
    source_entries, _author_key_ocr_risks, author_key_mappings = (
        _source_author_key_ocr_normalization(
            source_entries,
            translation_entries,
        )
    )
    numeric_mappings: dict[str, str] = {}
    complete_translation_entries = _complete_numeric_translation_entries(
        translation_section
    )
    if complete_translation_entries is not None:
        numeric_recovery = _recover_complete_numeric_bibliography(
            source_text,
            source_heading,
            parsed_source_entries,
            complete_translation_entries,
        )
        if numeric_recovery is not None:
            source_entries, _numeric_recovery_risks, numeric_mappings = (
                numeric_recovery
            )
    source_reference_ids = {
        identifier for identifier, _body in source_entries
    }
    if not source_reference_ids:
        return []

    citation_mappings = author_key_mappings | numeric_mappings
    source_citations = {
        citation_mappings.get(identifier, identifier)
        for identifier in _citation_identifiers(
            source_body,
            source_reference_ids
            | set(author_key_mappings)
            | set(numeric_mappings),
            include_source_angle_ocr=True,
        )
    }
    translation_citations = _citation_identifiers(
        _translation_citation_body(translation_text, translation_heading),
        source_reference_ids,
    )
    missing = sorted(
        source_citations - translation_citations,
        key=lambda value: (
            not value.isdigit(),
            int(value) if value.isdigit() else value,
        ),
    )
    if not missing:
        return []
    return [
        "source body citation identifiers have no translation-side candidate: "
        + ", ".join(missing)
    ]


def _compact_text_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _has_whitespace_split_url(body: str) -> bool:
    for match in REFERENCE_URL_RE.finditer(body):
        token = match.group()
        following = body[match.end() :].lstrip()
        next_word_match = re.match(r"([A-Za-z0-9][^\s]*)", following)
        if next_word_match is None:
            continue
        next_word = next_word_match.group(1)
        next_lower = next_word.casefold().rstrip(".,;:")
        if re.fullmatch(r"(?:18|19|20)\d{2}[a-z]?", next_lower):
            continue
        if next_lower in {"accessed", "last", "retrieved", "visited"}:
            continue
        if token.endswith("-"):
            return True
        normalized_token = token.rstrip(".,;:")
        parsed = urlsplit(normalized_token)
        if token.endswith(".") and "/" in next_word:
            return True
        if token.endswith("/") and (
            parsed.path not in {"", "/"}
            or any(character in next_word.rstrip(".,;:") for character in "/.-")
        ):
            return True
    return False


def _reference_findings(
    source_text: str,
    translation_text: str,
    *,
    broaden_source_heading: bool = False,
) -> tuple[list[str], list[str]]:
    translation_text = reader_visible_markdown(translation_text)
    errors: list[str] = []
    risks: list[str] = []
    if broaden_source_heading:
        source_heading, source_section, _source_body = (
            _review_source_reference_parts(source_text)
        )
        has_source_heading = source_heading is not None
        source_entry_parser = _reference_entries
    else:
        has_source_heading, source_section = _legacy_reference_section(
            source_text,
            SOURCE_REFERENCE_HEADING_RE,
        )
        source_entry_parser = _legacy_reference_entries
    if not has_source_heading:
        return errors, risks

    if broaden_source_heading:
        has_translation_heading, translation_section = _reference_section(
            translation_text,
            TRANSLATION_REFERENCE_HEADING_RE,
            require_single_evidence=False,
        )
        translation_entry_parser = _reference_entries
    else:
        has_translation_heading, translation_section = _legacy_reference_section(
            translation_text,
            TRANSLATION_REFERENCE_HEADING_RE,
        )
        translation_entry_parser = _legacy_reference_entries
    if not has_translation_heading:
        errors.append("source has a References section but translation has no reference heading")
        translation_section = ""

    parsed_source_entries = source_entry_parser(source_section)
    source_entries = parsed_source_entries
    source_entries, source_ocr_risks = _normalize_source_reference_ocr(source_entries)
    risks.extend(source_ocr_risks)
    translation_entries = translation_entry_parser(translation_section)
    if broaden_source_heading:
        source_entries, source_author_key_ocr_risks = (
            _normalize_source_author_key_ocr(
                source_entries,
                translation_entries,
            )
        )
        risks.extend(source_author_key_ocr_risks)
        complete_translation_entries = _complete_numeric_translation_entries(
            translation_section
        )
        if complete_translation_entries is not None:
            numeric_recovery = _recover_complete_numeric_bibliography(
                source_text,
                source_heading,
                parsed_source_entries,
                complete_translation_entries,
            )
            if numeric_recovery is not None:
                source_entries, numeric_recovery_risks, _numeric_mappings = (
                    numeric_recovery
                )
                risks.extend(numeric_recovery_risks)
    source_counts = Counter(identifier for identifier, _text in source_entries)
    translation_counts = Counter(identifier for identifier, _text in translation_entries)

    source_duplicates = sorted(identifier for identifier, count in source_counts.items() if count > 1)
    if source_duplicates:
        risks.append(
            "source has duplicate reference identifier candidates: "
            + ", ".join(source_duplicates)
        )
    translation_duplicates = sorted(
        identifier for identifier, count in translation_counts.items() if count > 1
    )
    if translation_duplicates:
        errors.append(
            "duplicate translation reference identifiers: "
            + ", ".join(translation_duplicates)
        )
    truncated_ranges = sorted(
        identifier
        for identifier, body in translation_entries
        if TRUNCATED_NUMERIC_RANGE_RE.search(body)
    )
    if truncated_ranges:
        errors.append(
            "translation references have a truncated numeric range: "
            + ", ".join(truncated_ranges)
        )
    split_url_identifiers = sorted(
        identifier
        for identifier, body in translation_entries
        if _has_whitespace_split_url(body)
    )
    if split_url_identifiers:
        errors.append(
            "translation references have a whitespace-split URL: "
            + ", ".join(split_url_identifiers)
        )

    if source_entries:
        missing = sorted(set(source_counts) - set(translation_counts))
        if missing:
            errors.append("missing numbered references: " + ", ".join(missing))
        extra = sorted(set(translation_counts) - set(source_counts))
        if extra:
            risks.append("translation has unmatched reference identifiers: " + ", ".join(extra))
        if len(source_entries) != len(translation_entries):
            risks.append(
                "reference entry-count candidate differs "
                f"({len(source_entries)}/{len(translation_entries)})"
            )

        source_by_id = {identifier: body for identifier, body in source_entries}
        translation_by_id = {identifier: body for identifier, body in translation_entries}
        short_entries: list[str] = []
        low_token_entries: list[str] = []
        for identifier in sorted(set(source_by_id) & set(translation_by_id)):
            source_body = source_by_id[identifier]
            translation_body = translation_by_id[identifier]
            source_length = _compact_text_length(source_body)
            translation_length = _compact_text_length(translation_body)
            if source_length >= 40 and (
                translation_length < 16 or translation_length < source_length * 0.25
            ):
                short_entries.append(identifier)
            source_tokens = _reference_tokens(source_body)
            translation_tokens = _reference_tokens(translation_body)
            if len(source_tokens) >= 4:
                overlap = source_tokens & translation_tokens
                if len(overlap) < 2 and len(overlap) / len(source_tokens) < 0.15:
                    low_token_entries.append(identifier)
        if short_entries:
            risks.append(
                "translation reference content is suspiciously short for: "
                + ", ".join(short_entries)
            )
        if low_token_entries:
            risks.append(
                "translation reference has low source-token overlap for: "
                + ", ".join(low_token_entries)
            )
    else:
        # Unnumbered bibliographies cannot be matched entry-by-entry reliably.
        # Still surface empty or grossly under-covered sections for human review.
        source_length = _compact_text_length(source_section)
        translation_length = _compact_text_length(translation_section)
        source_lines = sum(bool(line.strip()) for line in source_section.splitlines())
        translation_lines = sum(bool(line.strip()) for line in translation_section.splitlines())
        if translation_length == 0:
            risks.append("non-numbered bibliography is empty in translation")
        elif source_length >= 80 and (
            translation_length < max(40, source_length * 0.15)
            or translation_lines < max(1, source_lines * 0.2)
        ):
            risks.append("non-numbered bibliography has very low translation-side coverage")
    return errors, risks


def _equation_numbers_in_formulae(translation_text: str) -> set[str]:
    numbers: set[str] = set()
    for pattern in DISPLAY_MATH_PATTERNS:
        for block in pattern.findall(translation_text):
            for tagged, parenthesized in EQUATION_NUMBER_RE.findall(block):
                numbers.add(tagged or parenthesized)

    for line in translation_text.splitlines():
        matches = list(EQUATION_NUMBER_RE.finditer(line))
        if not matches:
            continue
        formula_body = line[: matches[-1].start()]
        has_math_delimiters = bool(
            re.search(r"\$[^$]+\$|\\\(.+?\\\)", formula_body)
        )
        if MATH_SIGNAL_RE.search(formula_body) or has_math_delimiters:
            for match in matches:
                numbers.add(match.group(1) or match.group(2))
    return numbers


def _section_heading_findings(source_text: str, translation_text: str) -> list[str]:
    """Emit structural heading candidates without claiming semantic completeness."""

    risks: list[str] = []
    if SOURCE_ABSTRACT_HEADING_RE.search(source_text) and not TRANSLATION_ABSTRACT_HEADING_RE.search(
        translation_text
    ):
        risks.append("source Abstract heading has no translation-side heading candidate")
    if SOURCE_END_HEADING_RE.search(source_text) and not TRANSLATION_END_HEADING_RE.search(
        translation_text
    ):
        risks.append("source Conclusion/Summary heading has no translation-side heading candidate")

    try:
        reference_heading = select_reference_heading(
            source_text, SOURCE_REFERENCE_HEADING_RE
        )
    except ValueError:
        reference_heading = None
    heading_source = source_text[: reference_heading.start()] if reference_heading else source_text
    source_sequence: list[int] = []
    expected_number = 1
    for number_text, title in SOURCE_NUMBERED_HEADING_RE.findall(heading_source):
        words = title.split()
        letters = [character for character in title if character.isalpha()]
        uppercase_ratio = (
            sum(character.isupper() for character in letters) / len(letters)
            if letters
            else 0.0
        )
        if len(title) > 100 or len(words) > 12 or uppercase_ratio < 0.65:
            continue
        number = int(number_text)
        if not source_sequence:
            if number == 1:
                source_sequence.append(number)
                expected_number = 2
            continue
        if number == expected_number:
            source_sequence.append(number)
            expected_number += 1
            continue
        break
    source_numbers = set(source_sequence) if len(source_sequence) >= 2 else set()
    translation_numbers = {
        int(number) for number in TRANSLATION_NUMBERED_HEADING_RE.findall(translation_text)
    }
    missing_numbers = sorted(source_numbers - translation_numbers)
    if missing_numbers:
        risks.append(
            "source numbered top-level section headings have no translation-side heading "
            "candidates: " + ", ".join(map(str, missing_numbers))
        )
    return risks


def source_coverage_findings(
    source_text: str,
    translation_text: str,
    require_references: bool,
    require_inline_citations: bool = False,
    *,
    legacy_resource_structure: bool = False,
) -> tuple[list[str], list[str]]:
    if legacy_resource_structure and require_inline_citations:
        raise ValueError(
            "legacy accepted resource structure cannot be combined with "
            "review-grade inline-citation checks"
        )
    if legacy_resource_structure:
        formal_representations = _legacy_formal_resource_representations(
            translation_text
        )
    else:
        translation_text = reader_visible_markdown(translation_text)
        formal_representations = formal_resource_representations(
            translation_text
        )
    errors: list[str] = []
    risks: list[str] = []
    risks.extend(_section_heading_findings(source_text, translation_text))
    for kind, source_pattern in SOURCE_RESOURCE_PATTERNS.items():
        source_numbers = {int(value) for value in source_pattern.findall(source_text)}
        formal_numbers = set(formal_representations[kind])
        for number in sorted(source_numbers - formal_numbers):
            risks.append(
                f"source {kind.title()} {number} has no formal translation-side payload candidate"
            )

    for number, markers in sorted(formal_representations["algorithm"].items()):
        if len(markers) > 1:
            errors.append(f"Algorithm {number} has {len(markers)} formal representations")
    for number, markers in sorted(formal_representations["table"].items()):
        if len(markers) > 1:
            errors.append(f"Table {number} has {len(markers)} formal representations")
    for number, markers in sorted(formal_representations["figure"].items()):
        if len(markers) > 1:
            risks.append(
                f"Figure {number} has {len(markers)} image candidates; "
                "verify subfigures versus duplicate representations"
            )

    if require_references:
        reference_errors, reference_risks = _reference_findings(
            source_text,
            translation_text,
            broaden_source_heading=require_inline_citations,
        )
        errors.extend(reference_errors)
        risks.extend(reference_risks)
        if require_inline_citations:
            risks.extend(_inline_citation_findings(source_text, translation_text))

    source_equations: set[str] = set()
    source_lines = source_text.splitlines()
    for index, line in enumerate(source_lines):
        matches = re.findall(rf"\(({EQUATION_NUMBER_PATTERN})\)\s*$", line)
        if not matches:
            continue
        previous = source_lines[index - 1] if index else ""
        if MATH_SIGNAL_RE.search(line) or (
            line.strip().startswith("(") and MATH_SIGNAL_RE.search(previous)
        ):
            source_equations.update(matches)
    translation_equations = _equation_numbers_in_formulae(translation_text)
    for number in sorted(source_equations):
        if number not in translation_equations:
            risks.append(
                f"source equation ({number}) has no translation-side display/formula candidate"
            )

    source_code_runs = 0
    in_code_run = False
    run_length = 0
    for line in source_lines:
        if SOURCE_CODE_LINE_RE.search(line) and len(line.strip()) < 180:
            run_length += 1
            in_code_run = True
            continue
        if in_code_run:
            if run_length >= 3:
                source_code_runs += 1
            run_length = 0
            in_code_run = False
    if in_code_run and run_length >= 3:
        source_code_runs += 1
    translation_fences = len(re.findall(r"^```[^\n]*$", translation_text, re.MULTILINE)) // 2
    if source_code_runs > translation_fences:
        risks.append(
            "source has more unnumbered code-like block candidates "
            f"than translation fenced blocks ({source_code_runs}/{translation_fences})"
        )
    return errors, risks


def validate_paper(
    paper_dir: Path,
    source_text: str,
    translation_text: str,
    *,
    require_references: bool,
    require_inline_citations: bool,
    allow_whole_page: bool,
    legacy_resource_structure: bool = False,
) -> tuple[list[str], list[str]]:
    image_errors, image_risks = validate_images(
        paper_dir,
        translation_text,
        allow_whole_page,
        legacy_resource_structure=legacy_resource_structure,
    )
    coverage_errors, coverage_risks = source_coverage_findings(
        source_text,
        translation_text,
        require_references,
        require_inline_citations,
        legacy_resource_structure=legacy_resource_structure,
    )
    return image_errors + coverage_errors, image_risks + coverage_risks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper_dir", type=Path)
    parser.add_argument("source_text", type=Path)
    parser.add_argument("--require-complete-references", action="store_true")
    parser.add_argument("--require-inline-citations", action="store_true")
    parser.add_argument("--allow-whole-page-images", action="store_true")
    parser.add_argument(
        "--legacy-accepted-resource-structure",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    try:
        translation_text = (args.paper_dir / "translation.md").read_text(encoding="utf-8")
        source_text = args.source_text.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"ERROR: {exc}")
        return 2
    try:
        errors, risks = validate_paper(
            args.paper_dir,
            source_text,
            translation_text,
            require_references=args.require_complete_references,
            require_inline_citations=args.require_inline_citations,
            allow_whole_page=args.allow_whole_page_images,
            legacy_resource_structure=args.legacy_accepted_resource_structure,
        )
    except ValueError as exc:
        print(f"ERROR: reference-section evidence is ambiguous: {exc}")
        return 2
    for issue in errors:
        print(f"ERROR: {issue}")
    for issue in risks:
        print(f"RISK: {issue}")
    if errors:
        return 1
    if risks:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
