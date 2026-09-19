#!/usr/bin/env python3
"""Check that every formal source Listing has one labeled fenced block."""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from markdown_visibility import reader_visible_markdown


PUNCTUATED_SOURCE_CAPTION_RE = re.compile(
    r"(?:^[ \t\f]*|[ \t]{2,})(?i:Listing)[ \t]+([1-9]\d*)"
    r"[ \t]*[:.](?!\d)[ \t]+(?=\S)",
    re.MULTILINE,
)
BARE_UPPER_SOURCE_CAPTION_RE = re.compile(
    r"(?:^[ \t\f]*|[ \t]{2,})LISTING[ \t]+([1-9]\d*)"
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


def _source_columns(page: str) -> list[list[str]]:
    """Split a layout-text page only at a recurring inter-column whitespace gap.

    Short line-number gutters and indentation inside code are not column evidence:
    both sides must contain prose-sized text on at least five separate lines.
    """
    lines = page.splitlines()
    votes: Counter[int] = Counter()
    for line in lines:
        for gap in re.finditer(r"\S([ \t]{3,})(?=\S)", line):
            left, right = line[:gap.start(1)], line[gap.end(1):]
            if len(re.findall(r"[A-Za-z]{2,}", left)) < 4:
                continue
            if len(re.findall(r"[A-Za-z]{2,}", right)) < 4:
                continue
            for column in range(gap.start(1) + 1, gap.end(1)):
                votes[column] += 1
    if not votes or max(votes.values()) < 5:
        return [lines]
    best = max(votes.values())
    candidates = sorted(column for column, count in votes.items() if count == best)
    split = candidates[len(candidates) // 2]
    return [[line[:split].rstrip() for line in lines],
            [line[split:].rstrip() for line in lines]]


def _source_caption_matches(line: str) -> list[re.Match[str]]:
    return list(PUNCTUATED_SOURCE_CAPTION_RE.finditer(line)) + list(
        BARE_UPPER_SOURCE_CAPTION_RE.finditer(line)
    )


def _code_line(line: str) -> bool:
    """Recognize payload lines, not prose merely mentioning SQL/code keywords."""
    value = line.strip()
    if not value or _source_caption_matches(line):
        return False
    if re.match(r"^\d+(?:\s+|$)", value):  # printed source line numbers (also prompts)
        return True
    value = re.sub(r"^[OP]\s+(?=SELECT\b)", "", value)
    if re.match(r"^(?:SELECT|CREATE|INSERT|UPDATE|DELETE|ALTER|DROP|FROM|WHERE|"
                r"JOIN|LEFT|RIGHT|INNER|OUTER|UNION|GROUP|ORDER|HAVING|LIMIT|"
                r"VALUES|WITH|WITHOUT|SET|EXPLAIN|PRAGMA|AND|OR|ON|USING|CASE|WHEN|"
                r"THEN|ELSE|END|INTERSECT|EXCEPT|OFFSET|FETCH|CROSS|NATURAL)\b", value, re.IGNORECASE):
        return True
    if re.match(r"^(?://|--|/\*|\*/|#|[{}]|\.\.\.|<\??/?[ \t]*[A-Za-z_])", value):
        return True
    if re.match(r"^(?:else|return|template|class|struct|public:|"
                r"private:|inline|const|static|void|int|long|double|auto)\b", value):
        return True
    if re.match(r"^(?:for|while|if)\s*\(", value):
        return True
    # Expression/declaration continuations and SQL result comments.
    return bool(re.search(r"(?:;\s*(?://|--|−−|$)|:=|->|::|\)\s*[{;])", value)
                or re.match(r"^[A-Za-z_]\w*\s*(?:=|\+=|-=)", value))


def _code_start_line(line: str) -> bool:
    """Clause continuations are code only after a payload start is established."""
    value = line.strip()
    if re.match(r"^(?:FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|UNION|GROUP|ORDER|"
                r"HAVING|LIMIT|VALUES|WITHOUT|AND|OR|ON|USING|WHEN|THEN|ELSE|"
                r"END|INTERSECT|EXCEPT|OFFSET|FETCH|CROSS|NATURAL)\b", value, re.I):
        return False
    return _code_line(line)


def _adjacent_source_payload(
    lines: list[str], index: int, claimed: set[int]
) -> tuple[int, int]:
    """Choose the nearest adjacent payload, allowing a wrapped top caption."""
    before = index - 1
    while before >= 0 and not lines[before].strip():
        before -= 1
    after = index + 1
    while after < min(len(lines), index + 8):
        if _source_caption_matches(lines[after]):
            break
        if _code_start_line(lines[after]):
            break
        after += 1
    previous_start = before
    while previous_start >= 0 and lines[previous_start].strip() and not _source_caption_matches(lines[previous_start]):
        previous_start -= 1
    previous_start += 1
    previous_code = sum(_code_line(line) for line in lines[previous_start:before + 1])
    has_before = (
        before >= 0 and before not in claimed
        and previous_start <= before and _code_start_line(lines[previous_start])
        and (_code_line(lines[before]) or previous_code >= 2)
    )
    has_after = after < min(len(lines), index + 8) and _code_start_line(lines[after])
    if has_before and (not has_after or index - before <= after - index):
        end = before + 1
        if not _code_line(lines[before]):
            return previous_start, end
        # Numbered listings can wrap onto unnumbered physical lines. Recover the
        # complete sequence back to line 1, not only the last SQL-bearing line.
        numbered = re.match(r"^\s*(\d+)(?:\s+|$)", lines[before])
        if numbered:
            expected_number = int(numbered.group(1))
            cursor = before
            while cursor >= 0 and not _source_caption_matches(lines[cursor]):
                item = re.match(r"^\s*(\d+)(?:\s+|$)", lines[cursor])
                if item:
                    if int(item.group(1)) != expected_number:
                        break
                    if expected_number == 1:
                        return cursor, end
                    expected_number -= 1
                cursor -= 1
        while before >= 0:
            if _code_line(lines[before]) or not lines[before].strip():
                before -= 1
            else:
                break
        return before + 1, end
    if not has_after:
        return index, index
    start = after
    end = start
    previous_blank = False
    while end < len(lines):
        line = lines[end]
        if _source_caption_matches(line):
            break
        if not line.strip():
            previous_blank = True
            end += 1
            continue
        if _code_line(line):
            previous_blank = False
            end += 1
            continue
        # Indented wraps are part of the same code line, not a later paragraph.
        indent = len(line) - len(line.lstrip())
        base = len(lines[start]) - len(lines[start].lstrip())
        if not previous_blank and indent > base:
            end += 1
            continue
        break
    return start, end


def source_listing_evidence(text: str) -> tuple[dict[int, str], set[int]]:
    """Extract local payloads and flag unclaimed code across layout boundaries.

    Cross-page/column reconstruction is intentionally not guessed. A listing
    ending near the boundary followed by code with no caption of its own needs
    PDF review before source-relative completeness comparisons are meaningful.
    """
    windows: dict[int, str] = {}
    columns = [column for page in text.split("\f") for column in _source_columns(page)]
    metadata: list[tuple[set[int], list[tuple[int, int]]]] = []
    for lines in columns:
        claimed: set[int] = set()
        endings: list[tuple[int, int]] = []
        for index, line in enumerate(lines):
            for match in _source_caption_matches(line):
                start, end = _adjacent_source_payload(lines, index, claimed)
                claimed.update(range(start, end))
                payload = "\n".join(lines[start:end]).strip()
                # Line numbers are layout metadata, not code literals.
                payload = re.sub(r"(?m)^[ \t]*\d+(?:[ \t]+|$)", "", payload)
                number = int(match.group(1))
                if payload or number not in windows:
                    windows[number] = payload
                if payload:
                    endings.append((number, end))
        metadata.append((claimed, endings))
    partial: set[int] = set()
    for index, (lines, (_claimed, endings)) in enumerate(zip(columns, metadata)):
        if not endings or index + 1 == len(columns):
            continue
        number, end = endings[-1]
        if sum(bool(line.strip()) for line in lines[end:]) > 3:
            continue
        following = columns[index + 1]
        next_claimed = metadata[index + 1][0]
        for row, line in enumerate(following[:12]):
            # Strip a potential printed line number, then require actual code;
            # a numbered page header containing author names is not evidence.
            candidate = re.sub(r"^[ \t]*\d+[ \t]+", "", line)
            if _source_caption_matches(line):
                break
            if _code_start_line(candidate):
                if row not in next_claimed:
                    partial.add(number)
                break
    return windows, partial


def source_listing_windows(text: str) -> dict[int, str]:
    """Compatibility accessor for local caption-adjacent source payloads."""
    return source_listing_evidence(text)[0]


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
    translation_text = reader_visible_markdown(translation_text)
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
    source_windows, partial_boundaries = source_listing_evidence(source_text)
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
        if number in partial_boundaries:
            risks.append(
                f"Listing {number} source payload may continue across a PDF page/column "
                "boundary; inspect the complete PDF listing"
            )
            continue
        if not source_window:
            risks.append(
                f"Listing {number} source payload boundary could not be identified; inspect the PDF"
            )
            continue
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
