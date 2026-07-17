#!/usr/bin/env python3
"""Validate translation resources and emit conservative source-coverage candidates."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError


IMAGE_RE = re.compile(r"!\[([^]]*)\]\((<[^>]+>|[^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
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
TRANSLATION_REFERENCE_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(?:\d+(?:\.\d+)*[.\s]+)?(?:参考文献|References|Bibliography)"
    r"(?:\s*[（(](?:References|Bibliography)[）)])?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
REFERENCE_ENTRY_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:\[([1-9]\d*|[A-Za-z][A-Za-z0-9+_.:-]*)\]|([1-9]\d*)\.)\s+(.+?)\s*$"
)
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
EQUATION_NUMBER_RE = re.compile(r"(?:\\tag\{([1-9]\d*)\}|\(([1-9]\d*)\))")
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
    r"^\s*#{1,6}\s*(?:摘要|Abstract)\s*$", re.IGNORECASE | re.MULTILINE
)
TRANSLATION_END_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(?:[1-9]\d*\.?\s+)?(?:结论|总结|Conclusions?|Summary)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
SOURCE_NUMBERED_HEADING_RE = re.compile(
    r"^\s*([1-9]\d*)\.?\s+([A-Z][A-Za-z0-9 &'()/:,\-]{2,})\s*$",
    re.MULTILINE,
)
TRANSLATION_NUMBERED_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*([1-9]\d*)(?:\.|\s)", re.MULTILINE
)


def image_links(translation_text: str) -> list[tuple[str, str]]:
    return [(alt, target[1:-1] if target.startswith("<") else target) for alt, target in IMAGE_RE.findall(translation_text)]


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


def _image_marker(line: str) -> str | None:
    match = IMAGE_RE.search(line)
    if not match:
        return None
    target = match.group(2)
    if target.startswith("<"):
        target = target[1:-1]
    return f"image:{target}"


def _preceding_payload_marker(
    lines: list[str], caption_index: int, kind: str
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

    marker = _image_marker(lines[payload_index].lstrip())
    if marker is not None:
        return marker

    if kind == "table" and lines[payload_index].lstrip().startswith("|"):
        table_start = payload_index
        while table_start > 0 and lines[table_start - 1].lstrip().startswith("|"):
            table_start -= 1
        table_lines = lines[table_start : payload_index + 1]
        if len(table_lines) >= 2 and re.match(r"^\s*\|?\s*:?-{3,}", table_lines[1]):
            return f"table-line:{table_start + 1}"

    if kind in {"figure", "algorithm"} and lines[payload_index].lstrip().startswith("```"):
        opening_index = payload_index - 1
        while opening_index >= 0:
            if lines[opening_index].lstrip().startswith("```"):
                if any(line.strip() for line in lines[opening_index + 1 : payload_index]):
                    return f"fence-line:{opening_index + 1}"
                return None
            opening_index -= 1
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

    representations: dict[str, dict[int, set[str]]] = {
        kind: {} for kind in SOURCE_RESOURCE_PATTERNS
    }

    for alt, target in image_links(translation_text):
        for kind, pattern in IMAGE_ALT_NUMBER_PATTERNS.items():
            match = pattern.match(alt)
            if match:
                number = int(match.group(1))
                representations[kind].setdefault(number, set()).add(f"image:{target}")

    lines = translation_text.splitlines()
    for kind, caption_pattern in TRANSLATION_CAPTION_PATTERNS.items():
        for index, line in enumerate(lines):
            caption = caption_pattern.match(line)
            if not caption:
                continue
            payload_index = index + 1
            while payload_index < len(lines) and not lines[payload_index].strip():
                payload_index += 1
            marker: str | None = None
            if payload_index < len(lines):
                payload = lines[payload_index].lstrip()
                if kind in {"figure", "table", "algorithm"}:
                    marker = _image_marker(payload)
                if marker is None and kind == "table" and payload.startswith("|"):
                    delimiter_index = payload_index + 1
                    if delimiter_index < len(lines) and re.match(
                        r"^\s*\|?\s*:?-{3,}", lines[delimiter_index]
                    ):
                        marker = f"table-line:{payload_index + 1}"
                if marker is None and kind in {"figure", "algorithm"} and payload.startswith("```"):
                    marker = f"fence-line:{payload_index + 1}"
            if marker is None:
                marker = _preceding_payload_marker(lines, index, kind)
            if marker is not None:
                number = int(caption.group(1))
                representations[kind].setdefault(number, set()).add(marker)

    for markers in representations["figure"].values():
        if any(marker.startswith("image:") for marker in markers):
            markers.difference_update(
                {marker for marker in markers if marker.startswith("fence-line:")}
            )
    return representations


def validate_images(paper_dir: Path, translation_text: str, allow_whole_page: bool) -> tuple[list[str], list[str]]:
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
    for _alt, target in links:
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
        if not allow_whole_page and re.search(r"(?:^|[-_.])(?:source\.pdf|original[-_]?page|page[-_]?\d+)", lexical.name, re.IGNORECASE):
            errors.append(f"whole-page or extraction-residue image is not allowed: {target}")
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
            risks.append(f"orphan asset is not referenced by translation.md: {asset.relative_to(paper_dir)}")
    return errors, risks


def _reference_section(text: str, heading_pattern: re.Pattern[str]) -> tuple[bool, str]:
    heading = heading_pattern.search(text)
    return (bool(heading), text[heading.end() :] if heading else "")


def _reference_id(bracketed: str | None, decimal: str | None) -> str:
    return (bracketed or decimal or "").casefold()


def _reference_entries(section: str) -> list[tuple[str, str]]:
    raw_matches = [
        REFERENCE_ENTRY_RE.match(line)
        for line in section.splitlines()
    ]
    has_bracketed_numeric_style = any(
        match and match.group(1) and match.group(1).isdigit() for match in raw_matches
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
    for line, match in zip(section.splitlines(), raw_matches, strict=True):
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
        elif current_id is not None and line.strip() and not line.lstrip().startswith("#"):
            current_lines.append(line.strip())
    if current_id is not None:
        entries.append((current_id, " ".join(current_lines).strip()))
    return entries


def _reference_tokens(text: str) -> set[str]:
    return {
        token.casefold().strip(".,:;/")
        for token in REFERENCE_TOKEN_RE.findall(text)
        if token.casefold().strip(".,:;/") not in REFERENCE_TOKEN_STOPWORDS
    }


def _normalize_source_reference_ocr(
    entries: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[str]]:
    """Normalize one conservative ``i``/``l`` -> ``1`` OCR candidate.

    Old scanned papers occasionally expose a visible numeric bibliography as
    ``[i], [2], ...`` in the PDF text layer.  Only normalize when exactly one
    such lookalike exists, no real ``1`` exists, every other identifier is
    numeric, and the result is the complete contiguous series ``1..N``.  This
    keeps author-key bibliographies untouched and still emits review evidence.
    """

    identifiers = [identifier for identifier, _body in entries]
    candidates = [
        index for index, identifier in enumerate(identifiers) if identifier in {"i", "l"}
    ]
    if len(candidates) != 1 or "1" in identifiers:
        return entries, []
    candidate_index = candidates[0]
    normalized_identifiers = identifiers.copy()
    normalized_identifiers[candidate_index] = "1"
    if not all(identifier.isdigit() for identifier in normalized_identifiers):
        return entries, []
    numeric_identifiers = [int(identifier) for identifier in normalized_identifiers]
    if sorted(numeric_identifiers) != list(range(1, len(entries) + 1)):
        return entries, []
    normalized = entries.copy()
    original, body = normalized[candidate_index]
    normalized[candidate_index] = ("1", body)
    return normalized, [
        f"source reference identifier {original} was normalized to 1 as a contiguous numeric-series OCR candidate"
    ]


def _compact_text_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _reference_findings(source_text: str, translation_text: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    risks: list[str] = []
    has_source_heading, source_section = _reference_section(
        source_text, SOURCE_REFERENCE_HEADING_RE
    )
    if not has_source_heading:
        return errors, risks

    has_translation_heading, translation_section = _reference_section(
        translation_text, TRANSLATION_REFERENCE_HEADING_RE
    )
    if not has_translation_heading:
        errors.append("source has a References section but translation has no reference heading")
        translation_section = ""

    source_entries = _reference_entries(source_section)
    source_entries, source_ocr_risks = _normalize_source_reference_ocr(source_entries)
    risks.extend(source_ocr_risks)
    translation_entries = _reference_entries(translation_section)
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


def _equation_numbers_in_formulae(translation_text: str) -> set[int]:
    numbers: set[int] = set()
    for pattern in DISPLAY_MATH_PATTERNS:
        for block in pattern.findall(translation_text):
            for tagged, parenthesized in EQUATION_NUMBER_RE.findall(block):
                numbers.add(int(tagged or parenthesized))

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
                numbers.add(int(match.group(1) or match.group(2)))
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

    reference_heading = SOURCE_REFERENCE_HEADING_RE.search(source_text)
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


def source_coverage_findings(source_text: str, translation_text: str, require_references: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    risks: list[str] = []
    formal_representations = formal_resource_representations(translation_text)
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
        reference_errors, reference_risks = _reference_findings(source_text, translation_text)
        errors.extend(reference_errors)
        risks.extend(reference_risks)

    source_equations: set[int] = set()
    source_lines = source_text.splitlines()
    for index, line in enumerate(source_lines):
        matches = re.findall(r"\(([1-9]\d*)\)\s*$", line)
        if not matches:
            continue
        previous = source_lines[index - 1] if index else ""
        if MATH_SIGNAL_RE.search(line) or (
            line.strip().startswith("(") and MATH_SIGNAL_RE.search(previous)
        ):
            source_equations.update(int(value) for value in matches)
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
    allow_whole_page: bool,
) -> tuple[list[str], list[str]]:
    image_errors, image_risks = validate_images(paper_dir, translation_text, allow_whole_page)
    coverage_errors, coverage_risks = source_coverage_findings(
        source_text, translation_text, require_references
    )
    return image_errors + coverage_errors, image_risks + coverage_risks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper_dir", type=Path)
    parser.add_argument("source_text", type=Path)
    parser.add_argument("--require-complete-references", action="store_true")
    parser.add_argument("--allow-whole-page-images", action="store_true")
    args = parser.parse_args()
    try:
        translation_text = (args.paper_dir / "translation.md").read_text(encoding="utf-8")
        source_text = args.source_text.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"ERROR: {exc}")
        return 2
    errors, risks = validate_paper(
        args.paper_dir,
        source_text,
        translation_text,
        require_references=args.require_complete_references,
        allow_whole_page=args.allow_whole_page_images,
    )
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
