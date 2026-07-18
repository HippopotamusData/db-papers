#!/usr/bin/env python3
"""Compute deterministic PDF-backed translation coverage metrics."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import pypdf
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from markdown_visibility import reader_visible_markdown
from reference_sections import select_reference_heading


PYPDF_VERSION = "6.14.2"
PDF_METRICS_VERSION = 1
WORD_RE = re.compile(r"\b[A-Za-z]+(?:[-'][A-Za-z]+)*\b")
SOURCE_REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.\s]+)?(?:REFERENCES|BIBLIOGRAPHY)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
TRANSLATION_REFERENCE_HEADING_RE = re.compile(
    r"\s*#{1,6}\s*(?:\d+(?:\.\d+)*[.\s]+)?"
    r"(?:参考文献|References|Bibliography)\s*",
    re.IGNORECASE,
)
CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _require_pinned_pypdf() -> None:
    if pypdf.__version__ != PYPDF_VERSION:
        raise ValueError(
            f"pypdf {PYPDF_VERSION} is required for deterministic PDF metrics "
            f"(found {pypdf.__version__})"
        )


def source_word_count_from_text(
    text: str,
    *,
    evidence_backed_boundary: bool = True,
) -> int:
    lines = text.splitlines()
    heading = (
        select_reference_heading(text, SOURCE_REFERENCE_HEADING_RE)
        if evidence_backed_boundary
        else SOURCE_REFERENCE_HEADING_RE.search(text)
    )
    if heading is None:
        return sum(len(WORD_RE.findall(line)) for line in lines)
    return sum(
        len(WORD_RE.findall(line))
        for line in text[: heading.start()].splitlines()
        if not SOURCE_REFERENCE_HEADING_RE.fullmatch(line)
    )


def source_word_count(
    source_pdf: Path,
    *,
    evidence_backed_boundary: bool = True,
) -> int:
    _require_pinned_pypdf()
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(source_pdf, strict=False)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    count = source_word_count_from_text(
        text,
        evidence_backed_boundary=evidence_backed_boundary,
    )
    if count < 1:
        raise ValueError(f"{source_pdf} produced no source words")
    return count


def translation_cjk_count_from_text(text: str) -> int:
    text = reader_visible_markdown(text)
    count = 0
    for line in text.splitlines():
        if TRANSLATION_REFERENCE_HEADING_RE.fullmatch(line):
            break
        count += len(CJK_RE.findall(line))
    return count


def translation_cjk_count(translation: Path) -> int:
    text = translation.read_text(encoding="utf-8")
    return translation_cjk_count_from_text(text)


def abridgement_candidate_from_counts(
    translated_cjk: int, source_words: int
) -> str | None:
    if source_words < 1:
        raise ValueError("source word count must be positive")
    if translated_cjk < 0:
        raise ValueError("translation CJK count must not be negative")
    if translated_cjk * 100 < source_words * 50:
        severity = "high"
        threshold = "0.50"
    elif translated_cjk * 100 < source_words * 75:
        severity = "moderate"
        threshold = "0.75"
    else:
        return None
    return (
        f"{severity} mechanical abridgement risk: "
        f"CJK/source-word ratio={translated_cjk}/{source_words} "
        f"(<{threshold}; extractor=pypdf-{PYPDF_VERSION}; "
        f"metric=v{PDF_METRICS_VERSION})"
    )


def abridgement_candidate(
    source_pdf: Path,
    translation: Path,
    *,
    evidence_backed_boundary: bool = True,
) -> str | None:
    return abridgement_candidate_from_counts(
        translation_cjk_count(translation),
        source_word_count(
            source_pdf,
            evidence_backed_boundary=evidence_backed_boundary,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    abridgement_parser = subparsers.add_parser("abridgement")
    abridgement_parser.add_argument("source_pdf", type=Path)
    abridgement_parser.add_argument("translation", type=Path)
    abridgement_parser.add_argument(
        "--legacy-accepted-reference-boundary",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    try:
        candidate = abridgement_candidate(
            args.source_pdf,
            args.translation,
            evidence_backed_boundary=not args.legacy_accepted_reference_boundary,
        )
    except (OSError, PdfReadError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if candidate:
        print(candidate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
