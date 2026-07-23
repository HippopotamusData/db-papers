#!/usr/bin/env python3
"""Validate that source.pdf is readable and matches its paper metadata."""

from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from project_config import load_yaml


MIN_EDGE_TEXT_TOKENS = 10
MIN_FIRST_TEXT_TOKENS = 20
MIN_TITLE_TOKEN_COVERAGE = 0.70
MIN_AUTHOR_COVERAGE = 0.50
PAPER_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def normalized_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    return re.findall(r"[a-z0-9]{2,}", normalized)


def token_coverage(expected: list[str], observed: set[str]) -> float:
    if not expected:
        return 0.0
    return sum(token in observed for token in expected) / len(expected)


def author_coverage(authors: Any, observed: set[str]) -> float:
    if not authors:
        return 1.0
    matches: list[bool] = []
    for author in authors:
        tokens = normalized_tokens(author)
        matches.append(bool(tokens) and any(token in observed for token in tokens[-2:]))
    return sum(matches) / len(matches)


def extract_text(pages: Any) -> str:
    return " ".join(page.extract_text() or "" for page in pages)


def validate_source_pdf(metadata_path: Path, pdf_path: Path) -> list[str]:
    errors: list[str] = []
    if metadata_path.is_symlink() or pdf_path.is_symlink():
        return [f"{pdf_path}: metadata and PDF must be regular, non-symlink files"]
    try:
        metadata = load_yaml(metadata_path)
    except ValueError as exc:
        return [str(exc)]

    try:
        with pdf_path.open("rb") as stream:
            signature = stream.read(5)
        if signature != b"%PDF-":
            return [f"{pdf_path}: file does not start with the PDF signature"]
        reader = PdfReader(str(pdf_path), strict=False)
        if reader.is_encrypted:
            return [f"{pdf_path}: encrypted PDFs are not accepted"]
        page_count = len(reader.pages)
        if page_count == 0:
            return [f"{pdf_path}: PDF has no pages"]
        first_pages = reader.pages[: min(2, page_count)]
        last_pages = reader.pages[max(0, page_count - 2) :]
    except (OSError, ValueError, PyPdfError) as exc:
        return [f"{pdf_path}: cannot read PDF: {exc}"]

    try:
        first_tokens = normalized_tokens(extract_text(first_pages))
        last_tokens = normalized_tokens(extract_text(last_pages))
    except Exception as exc:  # pypdf exposes several parser-specific exceptions.
        return [f"{pdf_path}: text extraction failed: {exc}"]

    if len(first_tokens) < MIN_FIRST_TEXT_TOKENS:
        errors.append(
            f"{pdf_path}: first pages contain too little extractable text "
            f"({len(first_tokens)} tokens; need {MIN_FIRST_TEXT_TOKENS})"
        )
    if len(last_tokens) < MIN_EDGE_TEXT_TOKENS:
        errors.append(
            f"{pdf_path}: last pages contain too little extractable text "
            f"({len(last_tokens)} tokens; need {MIN_EDGE_TEXT_TOKENS})"
        )

    observed = set(first_tokens)
    title = metadata.get("title")
    title_tokens = normalized_tokens(title) if isinstance(title, str) else []
    title_match = token_coverage(title_tokens, observed)
    if title_match < MIN_TITLE_TOKEN_COVERAGE:
        errors.append(
            f"{pdf_path}: first pages match only {title_match:.0%} of title tokens "
            f"(need {MIN_TITLE_TOKEN_COVERAGE:.0%})"
        )

    authors = metadata.get("authors")
    if not isinstance(authors, list):
        authors = []
    authors_match = author_coverage(authors, observed)
    if authors_match < MIN_AUTHOR_COVERAGE:
        errors.append(
            f"{pdf_path}: first pages match only {authors_match:.0%} of authors "
            f"(need {MIN_AUTHOR_COVERAGE:.0%})"
        )
    return errors


def validate_source_tree(
    root: Path,
    paper_id: str | None = None,
) -> tuple[int, list[str]]:
    if paper_id is not None and not PAPER_ID_RE.fullmatch(paper_id):
        return 0, [f"paper ID must be kebab-case: {paper_id}"]
    metadata_paths = sorted(root.glob("papers/*/*/paper.yaml"))
    if paper_id is not None:
        metadata_paths = [
            path for path in metadata_paths if path.parent.name == paper_id
        ]
        if len(metadata_paths) != 1:
            return 0, [f"paper ID must resolve exactly once: {paper_id}"]
    count = 0
    errors: list[str] = []
    for metadata_path in metadata_paths:
        pdf_path = metadata_path.parent / "source.pdf"
        if not pdf_path.is_file() and not pdf_path.is_symlink():
            continue
        count += 1
        errors.extend(validate_source_pdf(metadata_path, pdf_path))
    return count, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument(
        "--root",
        type=Path,
        help="validate every source.pdf under one repository root",
    )
    parser.add_argument("--paper-id", help="limit --root validation to one paper")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    # Some old publisher PDFs trigger recoverable pypdf warnings. They should
    # not obscure this command's deterministic verdict.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    if args.root is not None:
        if args.metadata is not None or args.pdf is not None:
            parser.error("--root cannot be combined with --metadata or --pdf")
        count, errors = validate_source_tree(args.root, args.paper_id)
        success = f"Source PDF identity verified: {count} file(s)."
    else:
        if args.metadata is None or args.pdf is None or args.paper_id is not None:
            parser.error(
                "--metadata and --pdf are required together; "
                "--paper-id requires --root"
            )
        errors = validate_source_pdf(args.metadata, args.pdf)
        success = f"Source PDF identity verified: {args.pdf}"
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if args.verbose:
        print(success)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
