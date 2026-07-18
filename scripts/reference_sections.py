#!/usr/bin/env python3
"""Select a real bibliography heading without mistaking a TOC or running header."""

from __future__ import annotations

import re
from typing import Pattern


DELIMITED_ENTRY_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:"
    r"\[(?P<square>[A-Za-z0-9][A-Za-z0-9+_.:-]*)\]|"
    r"<(?P<angle>[A-Za-z0-9][A-Za-z0-9+_.:-]*)>|"
    r"\((?P<parenthesized>[1-9]\d{0,2})\)"
    r"(?=\s+[A-Z][A-Za-z0-9'’.-]{1,50},\s*[A-Za-z])|"
    r"(?P<trailing_angle>[A-Za-z][A-Za-z0-9]{0,2})>"
    r")\s+(?P<body>.+?)\s*$"
)
NUMBERED_ENTRY_RE = re.compile(
    r"^\s*[1-9]\d{0,3}[.)]\s+(.+?)\s*$"
)
AUTHOR_ENTRY_RE = re.compile(
    r"^\s*[A-Z][A-Za-z'’ -]{1,50},\s*(?:[A-Z]\.|AND\b)"
)
AUTHOR_KEY_ENTRY_RE = re.compile(
    r"(?:^\s*|[ \t]{4,})"
    r"((?:(?=[A-Za-z0-9+_.:-]*\d)[A-Za-z][A-Za-z0-9+_.:-]{2,}|"
    r"[A-Z][A-Z+_.:-]{2,}))\s+"
    r"((?:[A-Z][A-Za-z'’ -]{1,50},\s*(?:[A-Z](?:\.|[ ,])|AND\b)|"
    r"O\s+S\s*/\s*V\s+S\b).+?)\s*$"
)
BIBLIOGRAPHIC_CUE_RE = re.compile(
    r"\b(?:"
    r"(?:18|19|20)\d{2}[a-z]?|"
    r"pp?\.|vol\.?|proc\.?|proceedings|journal|conference|"
    r"university|press|publisher|doi|https?://|technical report|tech\.?\s+rep\.?"
    r")\b",
    re.IGNORECASE,
)
AUTHOR_CITATION_PREFIX_RE = re.compile(
    r"^(?:"
    r"[A-Z][A-Za-z'’.-]+,\s*(?:[A-Z]\.|AND\b)|"
    r"(?:[A-Z]\.\s*){1,4}[A-Z][A-Za-z'’.-]+"
    r"(?:,?\s+(?:and|&)\s+(?:[A-Z]\.\s*){1,4}[A-Z][A-Za-z'’.-]+)*"
    r"[.,]\s+|"
    r"[A-Z][a-z'’.-]+(?:\s+[A-Z][a-z'’.-]+)+,\s+|"
    r"[A-Z][A-Za-z0-9&'’.-]+\.\s+[A-Z]"
    r")"
)
CORPORATE_TITLE_WITH_YEAR_RE = re.compile(
    r"^[A-Z][A-Za-z0-9&'’.-]*(?:\s+[A-Z][A-Za-z0-9&'’.-]*)+"
    r"\.\s+(?:18|19|20)\d{2}[a-z]?\b"
)
AUTHOR_KEY_STOPWORDS = frozenset({"AND", "FOR", "THE", "WITH"})
LONG_HORIZONTAL_WHITESPACE_RE = re.compile(r"[ \t]{64,}")


def _stabilize_heading_search_text(text: str) -> str:
    """Bound regex ambiguity while preserving every source-text offset.

    ``pdftotext -layout`` may emit hundreds of padding spaces between PDF
    columns.  Heading patterns deliberately accept column separators, but a
    long all-space run gives their optional prefix and indentation branches an
    enormous number of equivalent partitions.  Keep the first four horizontal
    spaces (enough to remain a column separator), replace the rest with form
    feeds accepted by the indentation branch, and preserve the string length so
    match offsets still index the original text exactly.
    """

    return LONG_HORIZONTAL_WHITESPACE_RE.sub(
        lambda match: match.group(0)[:4]
        + "\f" * (len(match.group(0)) - 4),
        text,
    )


def _bibliographic_body_strength(body: str) -> int:
    """Score citation structure without treating citation prose as an entry."""

    author = AUTHOR_CITATION_PREFIX_RE.match(body)
    if author is not None:
        remainder = body[author.end() :]
        return (
            2
            if (
                BIBLIOGRAPHIC_CUE_RE.search(remainder)
                or re.search(r"[\"“][^\"”]{3,}[\"”]", remainder)
                or re.search(r"\b\d{1,7}\s*[-–—]\s*\d{1,7}\b", remainder)
            )
            else 1
        )
    if CORPORATE_TITLE_WITH_YEAR_RE.match(body):
        return 2
    return 0


def _looks_like_bibliographic_body(body: str) -> bool:
    return _bibliographic_body_strength(body) > 0


def _looks_like_numbered_reference_entry(line: str) -> bool:
    match = NUMBERED_ENTRY_RE.search(line)
    if match is None:
        return False
    body = match.group(1)
    letters = "".join(character for character in body if character.isalpha())
    if letters and letters.upper() == letters and not BIBLIOGRAPHIC_CUE_RE.search(body):
        return False
    return _looks_like_bibliographic_body(body)


def _delimited_entry_identifier(match: re.Match[str]) -> str:
    return next(
        value
        for value in (
            match.group("square"),
            match.group("angle"),
            match.group("parenthesized"),
            match.group("trailing_angle"),
        )
        if value is not None
    )


def _looks_like_bracketed_reference_entry(line: str) -> bool:
    match = DELIMITED_ENTRY_RE.search(line)
    if match is None:
        return False
    identifier = _delimited_entry_identifier(match)
    body = match.group("body")
    if re.match(r"^\s*(?:=|:=|<-|->|[<>≤≥+*/^])", body):
        return False
    if not identifier.isdigit():
        if identifier.casefold() in {"i", "l"}:
            # Old scans commonly OCR the first numeric marker ``[1]`` as
            # ``[i]`` or ``[l]``.  Accept it as heading evidence only when
            # the body itself has strong author-and-venue structure; the
            # resource parser separately requires a complete contiguous
            # numeric series before normalizing the identifier.
            return _bibliographic_body_strength(body) >= 2
        return bool(
            len(identifier) >= 3
            and _looks_like_bibliographic_body(body)
        )
    return _looks_like_bibliographic_body(body)


def _looks_like_author_reference_entry(line: str) -> bool:
    if re.match(
        rf"^\s*(?:{'|'.join(sorted(AUTHOR_KEY_STOPWORDS))})\b",
        line,
        re.IGNORECASE,
    ):
        return False
    if AUTHOR_ENTRY_RE.search(line):
        return True
    return bool(
        re.match(r"^\s*[A-Z][A-Za-z'’ -]{1,50}\.\s+\S", line)
        and BIBLIOGRAPHIC_CUE_RE.search(line)
    )


def _looks_like_author_key_reference_entry(line: str) -> bool:
    match = AUTHOR_KEY_ENTRY_RE.search(line)
    if match is None:
        return False
    identifier, body = match.groups()
    return bool(
        len(identifier) >= 3
        and identifier.upper() not in AUTHOR_KEY_STOPWORDS
        and (
            _looks_like_bibliographic_body(body)
            or re.match(r"^O\s+S\s*/\s*V\s+S\b", body)
        )
    )


def _reference_evidence_score(section: str) -> int:
    lines = [line.strip() for line in section.splitlines() if line.strip()][:40]
    wrapped_strong_entry_starts = 0
    for index, line in enumerate(lines):
        window_tail = " ".join(lines[index + 1 : index + 4])
        delimited = DELIMITED_ENTRY_RE.search(line)
        if delimited is not None:
            identifier = _delimited_entry_identifier(delimited)
            if identifier.isdigit() or identifier.casefold() in {"i", "l"}:
                body = " ".join(
                    part
                    for part in (delimited.group("body"), window_tail)
                    if part
                )
                if _bibliographic_body_strength(body) >= 2:
                    wrapped_strong_entry_starts += 1
                    continue
        # Some old PDFs expose bibliography text but drop the numeric marker
        # entirely.  A wrapped author citation with a later venue/year cue is
        # still stronger evidence than a TOC label or running header.
        window = " ".join(part for part in (line, window_tail) if part)
        if _bibliographic_body_strength(window) >= 2:
            wrapped_strong_entry_starts += 1

    strong_entry_starts = sum(
        bool(
            (
                (match := DELIMITED_ENTRY_RE.search(line))
                and _bibliographic_body_strength(match.group("body")) >= 2
            )
            or (
                _looks_like_author_reference_entry(line)
                and BIBLIOGRAPHIC_CUE_RE.search(line)
            )
            or (
                (match := AUTHOR_KEY_ENTRY_RE.search(line))
                and match.group(1).upper() not in AUTHOR_KEY_STOPWORDS
                and _bibliographic_body_strength(match.group(2)) >= 2
            )
            or (
                (match := NUMBERED_ENTRY_RE.search(line))
                and _bibliographic_body_strength(match.group(1)) >= 2
            )
        )
        for line in lines
    )
    weak_entry_starts = sum(
        bool(
            _looks_like_bracketed_reference_entry(line)
            or _looks_like_author_reference_entry(line)
            or _looks_like_author_key_reference_entry(line)
            or _looks_like_numbered_reference_entry(line)
        )
        for line in lines
    )
    cue_lines = sum(bool(BIBLIOGRAPHIC_CUE_RE.search(line)) for line in lines)
    early_cue_lines = sum(
        bool(BIBLIOGRAPHIC_CUE_RE.search(line)) for line in lines[:12]
    )
    if (
        strong_entry_starts >= 1 or wrapped_strong_entry_starts >= 1
    ):
        return 2
    if weak_entry_starts >= 2 or (
        cue_lines >= 8 and early_cue_lines >= 2
    ):
        return 1
    return 0


def select_reference_heading(
    text: str,
    heading_pattern: Pattern[str],
    *,
    require_single_evidence: bool = True,
) -> re.Match[str] | None:
    """Return the first evidence-backed bibliography heading.

    Every heading needs nearby bibliography evidence, including a lone heading:
    otherwise a table-of-contents label could silently shrink the body
    denominator. With multiple headings, entry-shaped evidence outranks generic
    bibliographic cues, and the first equally strong candidate wins so later
    running page headers do not move the boundary.
    """

    search_text = _stabilize_heading_search_text(text)
    matches = list(heading_pattern.finditer(search_text))
    if not matches:
        return None
    if len(matches) == 1 and not require_single_evidence:
        return matches[0]
    scored: list[tuple[int, re.Match[str]]] = []
    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        score = _reference_evidence_score(text[match.end() : section_end])
        if score:
            scored.append((score, match))
    if scored:
        strongest = max(score for score, _match in scored)
        return next(match for score, match in scored if score == strongest)
    raise ValueError(
        "References/Bibliography heading lacks enough nearby entry evidence "
        "to distinguish a bibliography from a TOC or running header"
    )
