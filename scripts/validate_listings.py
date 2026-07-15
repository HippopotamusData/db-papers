#!/usr/bin/env python3
"""Check that every formal source Listing has one labeled fenced block."""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


PUNCTUATED_SOURCE_CAPTION_RE = re.compile(
    r"(?:^[ \t]*|[ \t]{2,})(?i:Listing)[ \t]+([1-9]\d*)"
    r"[ \t]*[:.](?!\d)[ \t]+(?=\S)",
    re.MULTILINE,
)
BARE_UPPER_SOURCE_CAPTION_RE = re.compile(
    r"(?:^[ \t]*|[ \t]{2,})LISTING[ \t]+([1-9]\d*)"
    r"(?![.\d])(?=[ \t]*$|[ \t]{2,}\S)",
    re.MULTILINE,
)
TRANSLATION_CAPTION_RE = re.compile(
    r"^\s*(?:\*\*)?(?:(?:代码\s*)?清单|Listing)\s*"
    r"([1-9]\d*)(?!\d)\s*[:：.]",
    re.IGNORECASE,
)
FENCE_RE = re.compile(r"^\s*```")
CODE_TOKEN_RE = re.compile(
    r"\b(?:SELECT|FROM|WHERE|JOIN|GROUP|ORDER|INSERT|UPDATE|DELETE|CREATE|"
    r"for|while|if|else|return|class|struct|public|private|void|int|long|double|"
    r"vector|tuple|operator|function)\b",
    re.IGNORECASE,
)
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
LITERAL_RE = re.compile(r"(?:\b\d+(?:\.\d+)?\b|['\"][^'\"\n]{1,40}['\"])")
LISTING_IMAGE_RE = re.compile(
    r"!\[\s*(?:(?:代码\s*)?清单|Listing)\s*([1-9]\d*)(?!\d)[^]]*\]\([^)]*\)",
    re.IGNORECASE,
)
COMMON_IDENTIFIERS = {
    "select", "from", "where", "join", "group", "order", "insert", "update",
    "delete", "create", "for", "while", "else", "return", "class", "struct",
    "public", "private", "void", "int", "long", "double", "vector", "tuple",
    "operator", "function", "auto", "const", "static", "this", "true", "false",
}


def source_listing_numbers(text: str) -> set[int]:
    matches = list(PUNCTUATED_SOURCE_CAPTION_RE.finditer(text))
    matches.extend(BARE_UPPER_SOURCE_CAPTION_RE.finditer(text))
    return {int(match.group(1)) for match in matches}


def source_listing_windows(text: str) -> dict[int, str]:
    """Return conservative caption-neighborhood evidence for risk checks.

    PDF text extraction does not expose a reliable listing boundary. The window is
    therefore a candidate signal only; callers must treat findings as review risks.
    """

    lines = text.splitlines()
    windows: dict[int, str] = {}
    for index, line in enumerate(lines):
        matches = list(PUNCTUATED_SOURCE_CAPTION_RE.finditer(line))
        matches.extend(BARE_UPPER_SOURCE_CAPTION_RE.finditer(line))
        for match in matches:
            number = int(match.group(1))
            start = max(0, index - 24)
            end = min(len(lines), index + 25)
            windows[number] = "\n".join(lines[start:end])
    return windows


def fenced_blocks(lines: list[str]) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    for index, line in enumerate(lines):
        if not FENCE_RE.match(line):
            continue
        if start is None:
            start = index
        else:
            if any(line.strip() for line in lines[start + 1 : index]):
                blocks.append((start, index))
            start = None
    return blocks


def only_blank_lines(lines: list[str], start: int, end: int) -> bool:
    return all(not line.strip() for line in lines[start:end])


def adjacent_fenced_blocks(
    lines: list[str], caption_index: int, blocks: list[tuple[int, int]]
) -> set[tuple[int, int]]:
    following: set[tuple[int, int]] = set()
    for block_start, block_end in blocks:
        if block_start > caption_index and only_blank_lines(
            lines, caption_index + 1, block_start
        ):
            following.add((block_start, block_end))
    if following:
        return following

    preceding: set[tuple[int, int]] = set()
    for block_start, block_end in blocks:
        if block_end < caption_index and only_blank_lines(
            lines, block_end + 1, caption_index
        ):
            preceding.add((block_start, block_end))
    return preceding


def listing_findings(source_text: str, translation_text: str) -> tuple[list[str], list[str]]:
    source_numbers = source_listing_numbers(source_text)
    if not source_numbers:
        return [], []

    lines = translation_text.splitlines()
    blocks = fenced_blocks(lines)
    fenced_line_indexes = {
        index
        for block_start, block_end in blocks
        for index in range(block_start, block_end + 1)
    }
    payloads: dict[int, set[tuple[int, int]]] = defaultdict(set)
    for index, line in enumerate(lines):
        if index in fenced_line_indexes:
            continue
        match = TRANSLATION_CAPTION_RE.match(line)
        if match:
            payloads[int(match.group(1))].update(
                adjacent_fenced_blocks(lines, index, blocks)
            )

    errors = [
        f"Listing {number} has no labeled fenced payload"
        for number in sorted(source_numbers)
        if not payloads[number]
    ]
    errors.extend(
        f"Listing {number} has duplicate fenced payloads"
        for number in sorted(source_numbers)
        if len(payloads[number]) > 1
    )

    listing_images = Counter(int(value) for value in LISTING_IMAGE_RE.findall(translation_text))
    for number in sorted(source_numbers):
        formal_count = len(payloads[number]) + listing_images[number]
        if formal_count > 1:
            errors.append(f"Listing {number} has {formal_count} formal representations")

    risks: list[str] = []
    source_windows = source_listing_windows(source_text)
    for number in sorted(source_numbers):
        if len(payloads[number]) != 1:
            continue
        block_start, block_end = next(iter(payloads[number]))
        payload = "\n".join(lines[block_start + 1 : block_end]).strip()
        compact_payload = re.sub(r"\s+", "", payload)
        if len(compact_payload) < 24:
            risks.append(
                f"Listing {number} fenced payload is suspiciously short ({len(compact_payload)} non-space chars)"
            )
            continue

        source_window = source_windows.get(number, "")
        source_tokens = {token.casefold() for token in CODE_TOKEN_RE.findall(source_window)}
        payload_tokens = {token.casefold() for token in CODE_TOKEN_RE.findall(payload)}
        if len(source_tokens) >= 3 and len(source_tokens & payload_tokens) < 2:
            expected = ", ".join(sorted(source_tokens)[:8])
            risks.append(
                f"Listing {number} fenced payload has weak key-token overlap with source candidate ({expected})"
            )
        source_syntax = sum(source_window.count(token) for token in (";", "{", "}"))
        payload_syntax = sum(payload.count(token) for token in (";", "{", "}"))
        if source_syntax >= 8 and payload_syntax == 0:
            risks.append(
                f"Listing {number} fenced payload omits all brace/semicolon tokens present in source candidate"
            )

        source_code_lines = [
            line
            for line in source_window.splitlines()
            if re.search(r"(?:[;{}]|:=|->|::|\b(?:SELECT|FROM|WHERE|JOIN)\b)", line, re.IGNORECASE)
        ]
        source_candidate = "\n".join(source_code_lines)
        source_identifiers = {
            token.casefold()
            for token in IDENTIFIER_RE.findall(source_candidate)
            if token.casefold() not in COMMON_IDENTIFIERS
        }
        payload_identifiers = {
            token.casefold()
            for token in IDENTIFIER_RE.findall(payload)
            if token.casefold() not in COMMON_IDENTIFIERS
        }
        if len(source_identifiers) >= 3:
            overlap = len(source_identifiers & payload_identifiers) / len(source_identifiers)
            if overlap < 0.35:
                risks.append(
                    f"Listing {number} fenced payload has weak distinctive-identifier overlap "
                    f"with source candidate ({overlap:.2f})"
                )

        source_literals = set(LITERAL_RE.findall(source_candidate))
        payload_literals = set(LITERAL_RE.findall(payload))
        if len(source_literals) >= 2 and not source_literals.intersection(payload_literals):
            risks.append(
                f"Listing {number} fenced payload shares no literals with source candidate"
            )

        compact_source_candidate = re.sub(r"\s+", "", source_candidate)
        if (
            len(compact_source_candidate) >= 80
            and len(compact_payload) / len(compact_source_candidate) < 0.35
        ):
            risks.append(
                f"Listing {number} fenced payload is short relative to source code candidate "
                f"({len(compact_payload)}/{len(compact_source_candidate)})"
            )
    return errors, risks


def listing_issues(source_text: str, translation_text: str) -> list[str]:
    """Compatibility helper returning all deterministic errors and review risks."""
    errors, risks = listing_findings(source_text, translation_text)
    return errors + risks


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: validate_listings.py SOURCE_TEXT TRANSLATION",
            file=sys.stderr,
        )
        return 2

    source_path = Path(sys.argv[1])
    translation_path = Path(sys.argv[2])
    try:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        translation_text = translation_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 2

    errors, risks = listing_findings(source_text, translation_text)
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
